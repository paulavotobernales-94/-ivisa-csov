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

    # Sources cited inside the AI Overview
    ai_overview = data.get("ai_overview", {})
    for source in ai_overview.get("sources", []):
        link = source.get("link", "")
        if link:
            sources.append(link)

    # Fallback: top organic results if no AI overview sources
    if not sources:
        for result in data.get("organic_results", [])[:5]:
            link = result.get("link", "")
            if link:
                sources.append(link)

    return sources[:10]  # cap at 10


def _fetch_serpapi_result(keyword: str, country_code: str) -> dict[str, Any]:
    """Fetch one keyword + country from SerpAPI."""
    if not SERPAPI_KEY:
        return {
            "has_ai_overview": None,
            "ivisa_cited": None,
            "ai_overview_text": None,
            "sentiment_score": None,
            "sources": [],
            "score": 50.0,  # neutral when data unavailable
        }

    params = {
        "engine": "google",
        "q": keyword,
        "gl": country_code,
        "hl": "en",
        "num": 10,
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
        }

    ai_text = _extract_ai_overview_text(data)
    has_ai_overview = bool(ai_text)
    ivisa_cited = "ivisa" in ai_text.lower() if ai_text else False
    sources = _extract_sources(data)

    # Score sentiment via Claude if there's AI Overview text
    sentiment_score = None
    if has_ai_overview and ai_text:
        sentiment_score = _score_sentiment_with_claude(ai_text)
        time.sleep(0.5)  # gentle on Claude rate limits

    # Compute keyword score
    if not has_ai_overview:
        score = 50.0  # neutral baseline when Google shows no AI overview
    elif ivisa_cited:
        score = sentiment_score if sentiment_score is not None else 70.0
    else:
        score = (sentiment_score * 0.3) if sentiment_score is not None else 15.0

    return {
        "has_ai_overview": has_ai_overview,
        "ivisa_cited": ivisa_cited,
        "ai_overview_text": ai_text if ai_text else None,
        "sentiment_score": sentiment_score,
        "sources": sources,
        "score": round(score, 2),
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
    Falls back gracefully if SERPAPI_KEY is not set.
    """
    results: dict[str, dict[str, dict]] = {}
    country_scores: dict[str, float] = {}

    if not SERPAPI_KEY:
        logger.warning("SERPAPI_KEY not set — AI Overview data will use neutral baseline (50).")

    for country_code, country_info in COUNTRIES.items():
        logger.info("  Fetching AI Overviews for country: %s", country_info["name"])
        results[country_code] = {}

        for keyword in KEYWORDS:
            logger.debug("    Keyword: %s", keyword)
            result = _fetch_serpapi_result(keyword, country_code)
            results[country_code][keyword] = result
            time.sleep(0.3)  # stay within SerpAPI rate limits

        country_scores[country_code] = _country_ai_score(results[country_code])
        logger.info("    → Country AI Overview score: %.1f", country_scores[country_code])

    global_score = _global_ai_score(country_scores)
    logger.info("  → Global AI Overview Score: %.1f", global_score)

    return {
        "results": results,
        "country_scores": country_scores,
        "global_score": global_score,
    }
