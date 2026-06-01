from __future__ import annotations

"""
fetch_serp.py — Pulls SERP rankings from SEMrush and Ahrefs APIs.

Scoring philosophy:
  The SERP score measures whether the top-10 results for each keyword
  are positive, neutral, or negative about iVisa — regardless of whether
  iVisa.com itself ranks. A blog post saying "iVisa is legit" scores positive
  even if it's not on iVisa.com. A complaint on BBB scores negative.

Returns a dict shaped:
{
  "country_code": {
    "keyword": [
      {
        "position": int,
        "url": str,
        "domain": str,
        "title": str,
        "is_ivisa": bool,
        "sentiment": "positive" | "negative" | "neutral",
        "source": "semrush" | "ahrefs"
      }, ...
    ]
  }
}
"""

import csv
import io
import logging
import time
from typing import Any

import requests

from scripts.config import (
    AHREFS_API_KEY,
    COUNTRIES,
    KEYWORDS,
    NEGATIVE_DOMAINS,
    SEMRUSH_API_KEY,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentiment classification
#
# Philosophy: classify from CONTENT (title + snippet), not from domain.
# Trustpilot, Tripadvisor, Sitejabber etc. are NOT automatically positive —
# they surface user reviews that can be 1-star and very negative.
# The only domain-level signal we keep is NEGATIVE domains (complaint sites)
# because their structural purpose is to host complaints regardless of content.
#
# Neutral means MIXED: text contains both positive and negative signals,
# or takes a "it works but has downsides" position.
# Example: "iVisa isn't a scam, it's a platform that charges service fees
# but handles all the work for you" → neutral (mixed signals present).
# ---------------------------------------------------------------------------

# Signals that indicate POSITIVE content about iVisa
# Read as: the text is defending, recommending, or vouching for iVisa
POSITIVE_TEXT_SIGNALS = [
    # Explicit legitimacy defence
    "not a scam", "isn't a scam", "is not a scam", "no scam",
    "why is this not a scam", "why you can use ivisa", "why use ivisa",
    "yes ivisa is trustworthy", "ivisa is trustworthy", "ivisa is legitimate",
    "ivisa is legit", "ivisa is safe", "ivisa is real", "ivisa is reliable",
    "ivisa is trusted", "ivisa is worth it", "ivisa is approved",
    "ivisa is verified", "ivisa is not fake",
    # Positive framing — specific phrases only (avoid over-broad single words)
    "is legit", "is legitimate", "safe to use", "is trusted", "is reliable",
    "honest review", "worth it", "worth the money", "recommend", "recommended",
    "highly recommend", "would use again", "used it successfully", "worked for me",
    "worked perfectly", "it works", "great service", "excellent service",
    "fast service", "easy to use", "convenient", "approved",
    "5 star", "five star", "4 star", "positive experience",
    "used ivisa", "tried ivisa", "helped me", "no issues",
    "no problems", "smooth process", "everything went well",
    "government approved", "accredited",
    # Editorial/press coverage framing
    "review", "how ivisa works", "ivisa launches", "ivisa partners",
    "ivisa expands", "ivisa raises", "ivisa announces",
    # Intent-to-recommend
    "should i use ivisa", "can i trust ivisa", "is ivisa worth",
    "best visa service", "best way to apply", "how to use ivisa",
    "guide to ivisa", "ivisa tutorial",
]

# Signals that indicate NEGATIVE content about iVisa
NEGATIVE_TEXT_SIGNALS = [
    "scam", "fraud", "fraudulent", "fake", "fake website", "not legitimate",
    "not legit", "not safe", "not trusted", "not real", "not reliable",
    "avoid", "avoid ivisa", "stay away", "do not use", "don't use",
    "beware", "warning", "danger", "dangerous",
    "complaint", "complaints", "problem", "problems", "issue", "issues",
    "rip off", "ripoff", "overcharged", "hidden fees", "hidden charges",
    "refund denied", "won't refund", "no refund", "lost money",
    "stole", "stolen", "steal", "cheat", "cheated", "mislead", "misleading",
    "suspicious", "shady", "untrustworthy", "terrible service", "worst service",
    "worst experience", "never again", "waste of money", "waste of time",
    "disappointing", "disappointed", "horrible", "awful", "nightmare",
    "con ", "con man", "scammed", "got scammed", "money back",
    "not affiliated with", "not government", "not official",
    # Questions that imply doubt or regret — should never score positive
    "was it a mistake", "was using ivisa a mistake", "is ivisa a mistake",
    "mistake", "regret", "regretted", "wish i hadn't", "should have avoided",
    "fell for", "got tricked", "got fooled", "bad experience", "bad service",
    "worse than", "not worth", "not worth it", "don't recommend",
    "do not recommend", "would not recommend", "would not use again",
]

# Press/editorial domains — classified from content but given benefit of doubt
# when title is neutral (no signals): treated as positive not neutral
EDITORIAL_DOMAINS = [
    "yahoo.com", "yahoo.finance", "finance.yahoo.com", "news.yahoo.com",
    "forbes.com", "businessinsider.com", "cnbc.com", "reuters.com",
    "apnews.com", "bloomberg.com", "techcrunch.com", "theguardian.com",
    "bbc.com", "bbc.co.uk", "nytimes.com", "wsj.com", "ft.com",
    "skift.com", "travelpulse.com", "lonelyplanet.com", "nomadicmatt.com",
    "thepointsguy.com", "travelweekly.com", "phocuswire.com",
    "prnewswire.com", "businesswire.com", "globenewswire.com",
    "accesswire.com", "einpresswire.com",  # press release wires
]

# Structural complaint site domains — always negative regardless of text
# (We deliberately exclude Trustpilot, Tripadvisor, Sitejabber — their sentiment
# depends entirely on what the review says, not the domain itself)
ALWAYS_NEGATIVE_DOMAINS = [
    "bbb.org",
    "ripoffreport.com",
    "scamalert.com",
    "complaints.com",
    "pissedconsumer.com",
    "complaintsboard.com",
    "scamadviser.com",
    "reviewopedia.com",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_result(domain: str, title: str, snippet: str = "") -> str:
    """
    Return 'positive', 'negative', or 'neutral' for a SERP result.

    Classification logic (in order of priority):
    1. Structural complaint domains → always negative
    2. Count positive and negative signals in (title + snippet) combined
    3. If BOTH positive and negative signals present → neutral (mixed/balanced)
    4. If only negative signals → negative
    5. If only positive signals → positive
    6. No signals → neutral (default)

    This means a Trustpilot page with "iVisa — terrible service, took my money"
    is correctly classified as negative. And "iVisa isn't a scam, it's pricey but
    delivers" is correctly classified as neutral.
    """
    domain_lower = domain.lower().strip()
    # Combine title + snippet for full text analysis
    full_text = f"{title} {snippet}".lower()

    # 1. Structural complaint domains — always negative
    for d in ALWAYS_NEGATIVE_DOMAINS:
        if d in domain_lower:
            return "negative"

    # 2. Count signals in the combined text
    pos_hits = sum(1 for s in POSITIVE_TEXT_SIGNALS if s in full_text)
    neg_hits = sum(1 for s in NEGATIVE_TEXT_SIGNALS if s in full_text)

    # 3. Mixed signals = neutral (e.g. "not a scam but expensive" has both)
    if pos_hits > 0 and neg_hits > 0:
        return "neutral"

    # 4. Clear negative
    if neg_hits > 0:
        return "negative"

    # 5. Clear positive
    if pos_hits > 0:
        return "positive"

    # 6. No signals — editorial/press domains default to positive
    # (Yahoo Finance, Reuters, Forbes, PR Newswire etc. covering iVisa
    # without negative signals = editorial coverage, counts as positive)
    is_editorial = any(d in domain_lower for d in EDITORIAL_DOMAINS)
    if is_editorial:
        return "positive"

    # 7. Everything else — default neutral
    return "neutral"


def _is_ivisa(domain: str) -> bool:
    return "ivisa.com" in domain.lower()


def _position_score(results: list[dict]) -> float:
    """
    Score one keyword based on the sentiment of its top-10 SERP results.

    Logic:
    - Each result is positive (1.0), neutral (0.5), or negative (0.0).
    - Results are weighted by position: pos 1 = 10 pts, pos 2 = 9 pts … pos 10 = 1 pt.
    - Final score = weighted_average * 100

    Meaning:
    - 100 = all top-10 results are positive about iVisa
    -  50 = all top-10 results are neutral (mixed / no strong signal)
    -   0 = all top-10 results are negative about iVisa
    """
    if not results:
        return 50.0  # neutral baseline when no data

    SENTIMENT_SCORE = {"positive": 1.0, "neutral": 0.5, "negative": 0.0}

    total_weight = 0.0
    weighted_score = 0.0

    for item in results[:10]:
        pos = item.get("position", 0)
        if pos < 1 or pos > 10:
            continue
        weight = float(11 - pos)  # pos 1 → 10, pos 10 → 1
        sentiment = item.get("sentiment", "neutral")
        weighted_score += weight * SENTIMENT_SCORE.get(sentiment, 0.5)
        total_weight += weight

    if total_weight == 0:
        return 50.0

    return round((weighted_score / total_weight) * 100, 2)


# ---------------------------------------------------------------------------
# SEMrush
# ---------------------------------------------------------------------------

def _fetch_semrush_keyword(keyword: str, database: str) -> list[dict]:
    """Fetch top-10 organic results for one keyword from SEMrush."""
    if not SEMRUSH_API_KEY:
        logger.warning("SEMRUSH_API_KEY not set — skipping SEMrush fetch.")
        return []

    url = "https://api.semrush.com/"
    params = {
        "type": "phrase_organic",
        "key": SEMRUSH_API_KEY,
        "phrase": keyword,
        "database": database,
        "display_limit": 10,
        "export_columns": "Po,Ur,Dn,Tt",
    }

    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("SEMrush request failed for '%s' (%s): %s", keyword, database, exc)
        return []

    text = resp.text.strip()
    if not text or text.startswith("ERROR"):
        logger.warning("SEMrush returned no data for '%s' (%s): %s", keyword, database, text[:120])
        return []

    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    results = []
    for row in reader:
        try:
            pos = int(row.get("Position", 0))
        except (ValueError, TypeError):
            pos = 0
        domain  = row.get("Domain", "").strip()
        title   = row.get("Title", "").strip()
        snippet = row.get("Snippet", "").strip()
        results.append({
            "position": pos,
            "url": row.get("URL", "").strip(),
            "domain": domain,
            "title": title,
            "snippet": snippet,
            "is_ivisa": _is_ivisa(domain),
            "sentiment": _classify_result(domain, title, snippet),
            "source": "semrush",
        })
    return results


# ---------------------------------------------------------------------------
# Ahrefs
# ---------------------------------------------------------------------------

def _fetch_ahrefs_keyword(keyword: str, country: str) -> list[dict]:
    """Fetch top-10 SERP overview for one keyword from Ahrefs v3 API."""
    if not AHREFS_API_KEY:
        logger.warning("AHREFS_API_KEY not set — skipping Ahrefs fetch.")
        return []

    url = "https://api.ahrefs.com/v3/serp-overview"
    params = {
        "target": keyword,
        "country": country,
        "mode": "phrase",
        "limit": 10,
    }
    headers = {"Authorization": f"Bearer {AHREFS_API_KEY}"}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Ahrefs request failed for '%s' (%s): %s", keyword, country, exc)
        return []

    try:
        data = resp.json()
    except ValueError as exc:
        logger.error("Ahrefs JSON parse error for '%s': %s", keyword, exc)
        return []

    results = []
    for item in data.get("serp", []):
        domain  = item.get("domain", "").strip()
        title   = item.get("title", "").strip()
        snippet = item.get("snippet", "").strip()
        results.append({
            "position": item.get("position", 0),
            "url": item.get("url", "").strip(),
            "domain": domain,
            "title": title,
            "snippet": snippet,
            "is_ivisa": _is_ivisa(domain),
            "sentiment": _classify_result(domain, title, snippet),
            "source": "ahrefs",
        })
    return results


# ---------------------------------------------------------------------------
# Merge & de-duplicate results
# ---------------------------------------------------------------------------

def _merge_results(semrush: list[dict], ahrefs: list[dict]) -> list[dict]:
    """
    Prefer SEMrush data; backfill with Ahrefs for positions not covered.
    Returns list sorted by position ascending.
    """
    seen_positions: set[int] = set()
    merged = []

    for item in semrush:
        if item["position"] not in seen_positions:
            merged.append(item)
            seen_positions.add(item["position"])

    for item in ahrefs:
        if item["position"] not in seen_positions:
            merged.append(item)
            seen_positions.add(item["position"])

    merged.sort(key=lambda x: x["position"])
    return merged[:10]


# ---------------------------------------------------------------------------
# Country / Global score calculation
# ---------------------------------------------------------------------------

def _country_serp_score(keyword_results: dict[str, list[dict]]) -> float:
    """Average keyword scores across all keywords for one country."""
    scores = [_position_score(results) for results in keyword_results.values()]
    return round(sum(scores) / len(scores), 2) if scores else 0.0


def calculate_global_serp_score(country_scores: dict[str, float]) -> float:
    """Weighted average across countries."""
    total = 0.0
    weight_sum = 0.0
    for code, score in country_scores.items():
        weight = COUNTRIES[code]["weight"]
        total += score * weight
        weight_sum += weight
    return round(total / weight_sum, 2) if weight_sum else 0.0


# ---------------------------------------------------------------------------
# SerpAPI organic enrichment
# ---------------------------------------------------------------------------

def enrich_with_serpapi_organic(serp_data: dict, organic_data: dict) -> dict:
    """
    Enrich SERP results using organic data already fetched by fetch_ai_overviews.

    Two jobs:
    1. Fill in page titles (SEMrush/Ahrefs don't return titles).
    2. Replace empty keyword results (keywords with no SEMrush/Ahrefs coverage)
       with SerpAPI organic results — same API call, zero extra cost.

    organic_data shape: { country_code: { keyword: [ {position, url, domain, title, snippet} ] } }
    """
    results = serp_data.get("results", {})

    for country_code, keyword_organic in organic_data.items():
        if country_code not in results:
            results[country_code] = {}

        for keyword, organic_list in keyword_organic.items():
            existing = results[country_code].get(keyword, [])

            if not existing:
                # No SEMrush/Ahrefs data at all — use SerpAPI organic as source
                results[country_code][keyword] = [
                    {
                        "position": r["position"],
                        "url": r["url"],
                        "domain": r["domain"],
                        "title": r["title"],
                        "snippet": r.get("snippet", ""),
                        "is_ivisa": _is_ivisa(r["domain"]),
                        "sentiment": _classify_result(
                            r["domain"], r["title"], r.get("snippet", "")
                        ),
                        "source": "serpapi",
                    }
                    for r in organic_list
                    if r.get("position") and r.get("url")
                ]
            else:
                # SEMrush/Ahrefs data exists — fill in missing titles + snippets
                url_map = {r["url"]: r for r in organic_list if r.get("url")}

                for item in existing:
                    url = item.get("url", "")
                    organic_match = url_map.get(url)
                    if organic_match:
                        if not item.get("title"):
                            item["title"] = organic_match.get("title", "")
                        if not item.get("snippet"):
                            item["snippet"] = organic_match.get("snippet", "")

                    # Re-classify with title + snippet now that both are available
                    item["sentiment"] = _classify_result(
                        item.get("domain", ""),
                        item.get("title", ""),
                        item.get("snippet", ""),
                    )

    # Recompute scores with enriched data
    for country_code in list(results.keys()):
        serp_data["country_scores"][country_code] = _country_serp_score(results[country_code])

    serp_data["global_score"] = calculate_global_serp_score(serp_data["country_scores"])
    serp_data["results"] = results
    logger.info("  → SERP enriched with SerpAPI organic data. New global score: %.1f", serp_data["global_score"])
    return serp_data


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_serp_data() -> dict[str, Any]:
    """
    Fetch SERP data for all keywords × countries.

    Returns:
    {
      "results": { country_code: { keyword: [result, ...] } },
      "country_scores": { country_code: float },
      "global_score": float,
    }
    """
    results: dict[str, dict[str, list[dict]]] = {}
    country_scores: dict[str, float] = {}

    for country_code, country_info in COUNTRIES.items():
        logger.info("  Fetching SERP for country: %s (%s)", country_info["name"], country_code)
        results[country_code] = {}

        for keyword in KEYWORDS:
            logger.debug("    Keyword: %s", keyword)

            semrush_data = _fetch_semrush_keyword(keyword, country_info["semrush_db"])
            # Be gentle with rate limits
            time.sleep(0.3)
            ahrefs_data = _fetch_ahrefs_keyword(keyword, country_info["ahrefs_country"])
            time.sleep(0.3)

            merged = _merge_results(semrush_data, ahrefs_data)
            results[country_code][keyword] = merged

        country_scores[country_code] = _country_serp_score(results[country_code])
        logger.info("    → Country SERP score: %.1f", country_scores[country_code])

    global_score = calculate_global_serp_score(country_scores)
    logger.info("  → Global SERP Score: %.1f", global_score)

    return {
        "results": results,
        "country_scores": country_scores,
        "global_score": global_score,
    }
