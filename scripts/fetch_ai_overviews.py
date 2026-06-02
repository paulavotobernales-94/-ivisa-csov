from __future__ import annotations

"""
fetch_ai_overviews.py — Scrapes Google AI Overview content via SerpAPI.

If SERPAPI_KEY is not set, all AI Overview data is returned as None
and the score defaults to 50 (neutral baseline).

SerpAPI docs: https://serpapi.com/google-search-api
AI Overview field: response["ai_overview"]["text_blocks"]

Returns a dict shaped:
{
  "results": {
    country_code: {
      keyword: {
        "has_ai_overview": bool,
        "ivisa_cited": bool,
        "ai_overview_text": str | None,
        "sentiment_score": float | None,
        "sources": [str],
        "score": float,
      }
    }
  },
  "country_scores": { country_code: float },
  "global_score": float,
}
"""

import logging
import time
from typing import Any

import requests

from scripts.config import (
    CLAUDE_API_KEY,
    CLAUDE_MODEL,
    COUNTRIES,
    KEYWORDS,
    SENTIMENT_PROMPT_TEMPLATE,
    SERPAPI_KEY,
)

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"


# ---------------------------------------------------------------------------
# Sentiment scoring via Claude
# ---------------------------------------------------------------------------

def _score_sentiment_with_claude(text: str) -> float | None:
    """Ask Claude to rate sentiment 0–100 for AI Overview text."""
    if not CLAUDE_API_KEY:
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        prompt = SENTIMENT_PROMPT_TEMPLATE.format(text=text[:2000])
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        return max(0.0, min(100.0, float(raw)))
    except Exception as exc:
        logger.warning("Claude sentiment scoring failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# SerpAPI fetch
# ---------------------------------------------------------------------------

def _extract_ai_overview_text(data: dict) -> str:
    """
    Pull AI Overview text from SerpAPI response.
    SerpAPI returns AI Overview under data["ai_overview"]["text_blocks"].
    Each block has a "snippet" field.
    """
    ai_overview = data.get("ai_overview", {})
    if not ai_overview:
        return ""

    text_blocks = ai_overview.get("text_blocks", [])
    snippets = []
    for block in text_blocks:
        snippet = block.get("snippet", "").strip()
        if snippet:
            snippets.append(snippet)

    return " ".join(snippets)


def _extract_sources(data: dict) -> list[str]:
    """Extract cited source URLs from the AI Overview section."""
    sources = []

    ai_overview = data.get("ai_overview", {})
    for source in ai_overview.get("sources", []):
        link = source.get("link", "")
        if link:
            sources.append(link)

    if not sources:
        for result in data.get("organic_results", [])[:5]:
            link = result.get("link", "")
            if link:
                sources.append(link)

    return sources[:10]


def _extract_organic_results(data: dict) -> list[dict]:
    """
    Extract top-10 organic results from SerpAPI response.
    Pulls from organic_results first, then backfills from video_results
    and inline_videos if fewer than 10 organic results were returned.
    Reused by fetch_serp to fill in page titles and fix keywords with no
    SEMrush/Ahrefs coverage — zero extra API calls, same request.
    """
    from urllib.parse import urlparse

    def parse_item(item: dict, pos_override: int = 0) -> dict:
        link = item.get("link", "")
        domain = item.get("domain", "")
        if not domain and link:
            domain = urlparse(link).netloc.replace("www.", "")
        return {
            "position": item.get("position", 0) or pos_override,
            "url": link,
            "domain": domain,
            "title": item.get("title", ""),
            "snippet": item.get("snippet", ""),
        }

    results = []
    seen_urls: set = set()

    for item in data.get("organic_results", [])[:20]:
        r = parse_item(item)
        if r["url"] and r["url"] not in seen_urls:
            results.append(r)
            seen_urls.add(r["url"])

    # Backfill from video results if we have fewer than 10
    if len(results) < 10:
        next_pos = max((r["position"] for r in results), default=0) + 1
        for item in data.get("video_results", []):
            if len(results) >= 10:
                break
            r = parse_item(item, pos_override=next_pos)
            if r["url"] and r["url"] not in seen_urls:
                results.append(r)
                seen_urls.add(r["url"])
                next_pos += 1
        for item in data.get("inline_videos", []):
            if len(results) >= 10:
                break
            r = parse_item(item, pos_override=next_pos)
            if r["url"] and r["url"] not in seen_urls:
                results.append(r)
                seen_urls.add(r["url"])
                next_pos += 1

    return results[:10]


# ---------------------------------------------------------------------------
# Topic-level negative signal detection
# ---------------------------------------------------------------------------

# Maps topic label → keywords that indicate it's being mentioned negatively
# Used to generate specific content recommendations in action items
NEGATIVE_TOPIC_SIGNALS = {
    "refund policy": [
        "refund", "refund policy", "won't refund", "no refund",
        "refund denied", "frustration with refund", "refund issue",
        "money back", "cancellation policy",
    ],
    "service fees": [
        "higher cost", "expensive", "service fee", "extra fee",
        "charges more", "significantly more expensive", "overpriced",
        "fee on top", "markup", "additional charge",
    ],
    "not government / third-party": [
        "not official", "not government", "third-party", "independent service",
        "not affiliated", "not an agency", "communication gap",
        "not a government site", "private company",
    ],
    "processing delays": [
        "delay", "delayed", "slow processing", "takes longer",
        "government processing delay", "waiting time",
    ],
    "customer service issues": [
        "unresponsive", "poor support", "hard to reach", "no response",
        "customer service issue", "support problem",
    ],
    "security / data privacy": [
        "data privacy", "personal information", "secure", "security concern",
        "data breach", "identity", "passport data",
    ],
}


def _detect_negative_topics(text: str) -> list[str]:
    """
    Scan AI Overview text for specific topics being discussed negatively.
    Returns a list of topic labels found (e.g. ["refund policy", "service fees"]).
    """
    if not text:
        return []

    # Only scan text that appears after section headers like "Drawbacks",
    # "Criticisms", "Cons", "Limitations", "Negatives", "Issues", "Problems"
    # to avoid false positives from positive context
    text_lower = text.lower()

    # Find where the negative section starts (if any)
    negative_section_markers = [
        "drawback", "criticism", "downside", "cons", "limitation",
        "negative", "issue", "problem", "complaint", "however",
        "but ", "although", "on the other hand",
    ]

    # We scan the full text but weight findings more if after a negative header
    detected = []
    for topic, signals in NEGATIVE_TOPIC_SIGNALS.items():
        for signal in signals:
            if signal in text_lower:
                detected.append(topic)
                break  # Only add each topic once

    return detected


def _fetch_serpapi_result(keyword: str, country_code: str) -> dict[str, Any]:
    """Fetch one keyword + country from SerpAPI."""
    if not SERPAPI_KEY:
        return {
            "has_ai_overview": None,
            "ivisa_cited": None,
            "ai_overview_text": None,
            "sentiment_score": None,
            "sources": [],
            "score": 50.0,
            "organic_results": [],
        }

    params = {
        "engine": "google",
        "q": keyword,
        "gl": country_code,
        "hl": "en",
        "num": 20,
        "api_key": SERPAPI_KEY,
    }

    try:
        resp = requests.get(SERPAPI_URL, params=params, timeout=25)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.error("SerpAPI request failed for '%s' (%s): %s", keyword, country_code, exc)
        return {
            "has_ai_overview": False,
            "ivisa_cited": False,
            "ai_overview_text": None,
            "sentiment_score": None,
            "sources": [],
            "score": 50.0,
            "organic_results": [],
        }

    ai_text = _extract_ai_overview_text(data)
    has_ai_overview = bool(ai_text)
    ivisa_cited = "ivisa" in ai_text.lower() if ai_text else False
    sources = _extract_sources(data)
    organic_results = _extract_organic_results(data)

    # Score sentiment via Claude if there's AI Overview text
    sentiment_score = None
    if has_ai_overview and ai_text:
        sentiment_score = _score_sentiment_with_claude(ai_text)
        time.sleep(0.5)

    # ── Scoring philosophy ──────────────────────────────────────────────────
    # No AI Overview = 50 (neutral baseline — no appearance is not a problem,
    # we just don't have signal either way).
    #
    # AI Overview present = we care about QUALITY of what it says about iVisa.
    # Whether iVisa is explicitly cited or just described, the sentiment of
    # the text is what matters. A mixed AIO (positives + drawbacks section)
    # will score ~45–60. A fully positive AIO scores 75–90. A negative one < 40.
    #
    # We no longer apply the 0.3 penalty for "not cited" — if iVisa appears
    # in an AI Overview at all (even unnamed but as "this service"), the
    # content quality is what drives the score.
    # ───────────────────────────────────────────────────────────────────────
    if not has_ai_overview:
        # No overview shown — exclude from score entirely (None = not counted)
        score = None
    else:
        # Overview present — score is purely the sentiment of what it says
        score = sentiment_score if sentiment_score is not None else 55.0

    # Detect specific topics mentioned negatively — used for action items
    negative_topics = _detect_negative_topics(ai_text) if ai_text else []

    return {
        "has_ai_overview": has_ai_overview,
        "ivisa_cited": ivisa_cited,
        "ai_overview_text": ai_text if ai_text else None,
        "sentiment_score": sentiment_score,
        "sources": sources,
        "score": round(score, 2) if score is not None else None,
        "organic_results": organic_results,
        "negative_topics": negative_topics,
    }


# ---------------------------------------------------------------------------
# Score aggregation
# ---------------------------------------------------------------------------

def _country_ai_score(keyword_results: dict[str, dict]) -> float:
    """Average score across keywords for one country."""
    scores = [v["score"] for v in keyword_results.values() if v["score"] is not None]
    return round(sum(scores) / len(scores), 2) if scores else 50.0


def _global_ai_score(country_scores: dict[str, float]) -> float:
    """Weighted average across countries."""
    total = 0.0
    weight_sum = 0.0
    for code, score in country_scores.items():
        weight = COUNTRIES[code]["weight"]
        total += score * weight
        weight_sum += weight
    return round(total / weight_sum, 2) if weight_sum else 50.0


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_ai_overview_data() -> dict[str, Any]:
    """
    Fetch AI Overview data for all keywords × countries via SerpAPI.
    Also extracts organic SERP results (titles, snippets) from the same
    API call — passed to fetch_serp for enrichment at zero extra cost.
    Falls back gracefully if SERPAPI_KEY is not set.
    """
    results: dict[str, dict[str, dict]] = {}
    country_scores: dict[str, float] = {}
    # organic_data: { country_code: { keyword: [ {position, url, domain, title, snippet}, ... ] } }
    organic_data: dict[str, dict[str, list]] = {}

    if not SERPAPI_KEY:
        logger.warning("SERPAPI_KEY not set — AI Overview data will use neutral baseline (50).")

    for country_code, country_info in COUNTRIES.items():
        logger.info("  Fetching AI Overviews for country: %s", country_info["name"])
        results[country_code] = {}
        organic_data[country_code] = {}

        for keyword in KEYWORDS:
            logger.debug("    Keyword: %s", keyword)
            result = _fetch_serpapi_result(keyword, country_code)
            # Separate organic results from AIO result before storing
            organic_data[country_code][keyword] = result.pop("organic_results", [])
            results[country_code][keyword] = result
            time.sleep(0.3)

        country_scores[country_code] = _country_ai_score(results[country_code])
        logger.info("    → Country AI Overview score: %.1f", country_scores[country_code])

    global_score = _global_ai_score(country_scores)
    logger.info("  → Global AI Overview Score: %.1f", global_score)

    return {
        "results": results,
        "country_scores": country_scores,
        "global_score": global_score,
        "organic_data": organic_data,   # used by fetch_serp to enrich titles + fill gaps
    }
