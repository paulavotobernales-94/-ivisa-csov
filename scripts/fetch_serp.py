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
    NEUTRAL_DOMAINS,
    POSITIVE_DOMAINS,
    SEMRUSH_API_KEY,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentiment signals for title-based classification
# ---------------------------------------------------------------------------

# Words in a page title that strongly signal POSITIVE content about iVisa
POSITIVE_TITLE_SIGNALS = [
    "legit", "legitimate", "safe", "trusted", "trust", "reliable", "review",
    "honest", "worth", "recommend", "guide", "official", "best", "how to",
    "real", "verified", "approved", "faq", "is it", "should i", "pros",
    "everything you need", "comparison", "honest review", "my experience",
    "used ivisa", "tried ivisa", "work", "works", "worked", "helped",
]

# Words in a page title that strongly signal NEGATIVE content
NEGATIVE_TITLE_SIGNALS = [
    "scam", "fraud", "fake", "avoid", "danger", "problem", "complaint",
    "steal", "stolen", "worst", "terrible", "rip off", "ripoff", "warning",
    "cheat", "mislead", "suspicious", "beware", "do not use", "don't use",
    "stay away", "con ", "overcharged", "refund denied", "lost money",
    "never again", "waste of", "disappointed", "not legit", "not safe",
    "not legitimate", "not trusted", "not reliable",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_result(domain: str, title: str) -> str:
    """
    Return 'positive', 'negative', or 'neutral' for a SERP result.

    Priority order:
    1. Negative domain → always negative (BBB, ripoffreport, scamalert, etc.)
    2. Negative title keywords → negative (scam, fraud, avoid, etc.)
    3. Positive domain → positive (trustpilot, forbes, ivisa.com itself, etc.)
    4. Positive title keywords → positive
    5. Neutral domain → neutral
    6. Default → neutral
    """
    domain_lower = domain.lower().strip()
    title_lower = (title or "").lower()

    # Negative domain — strongest signal, overrides title
    for d in NEGATIVE_DOMAINS:
        if d in domain_lower:
            return "negative"

    # Negative title signals
    for signal in NEGATIVE_TITLE_SIGNALS:
        if signal in title_lower:
            return "negative"

    # Positive domain (trusted review sites, iVisa's own pages, travel press)
    for d in POSITIVE_DOMAINS:
        if d in domain_lower:
            return "positive"

    # Positive title signals
    for signal in POSITIVE_TITLE_SIGNALS:
        if signal in title_lower:
            return "positive"

    # Neutral domain list (reddit, quora, twitter/X, yelp)
    for d in NEUTRAL_DOMAINS:
        if d in domain_lower:
            return "neutral"

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
        domain = row.get("Domain", "").strip()
        title  = row.get("Title", "").strip()
        results.append({
            "position": pos,
            "url": row.get("URL", "").strip(),
            "domain": domain,
            "title": title,
            "is_ivisa": _is_ivisa(domain),
            "sentiment": _classify_result(domain, title),
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
        domain = item.get("domain", "").strip()
        title  = item.get("title", "").strip()
        results.append({
            "position": item.get("position", 0),
            "url": item.get("url", "").strip(),
            "domain": domain,
            "title": title,
            "is_ivisa": _is_ivisa(domain),
            "sentiment": _classify_result(domain, title),
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
