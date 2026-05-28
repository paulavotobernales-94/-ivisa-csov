"""
fetch_serp.py — Pulls SERP rankings from SEMrush and Ahrefs APIs.

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
    POSITION_POINTS,
    SEMRUSH_API_KEY,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_domain(domain: str) -> str:
    """Return 'positive', 'negative', or 'neutral' for a root domain."""
    domain = domain.lower().strip()
    for d in POSITIVE_DOMAINS:
        if d in domain:
            return "positive"
    for d in NEGATIVE_DOMAINS:
        if d in domain:
            return "negative"
    for d in NEUTRAL_DOMAINS:
        if d in domain:
            return "neutral"
    return "neutral"


def _is_ivisa(domain: str) -> bool:
    return "ivisa.com" in domain.lower()


def _position_score(results: list[dict]) -> float:
    """
    Given a list of SERP result dicts for one keyword,
    return the keyword score (0–100).
    """
    for item in results:
        if item.get("is_ivisa") and item.get("position") in POSITION_POINTS:
            pts = POSITION_POINTS[item["position"]]
            return (pts / 5.0) * 100.0
    return 0.0


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
        results.append({
            "position": pos,
            "url": row.get("URL", "").strip(),
            "domain": domain,
            "title": row.get("Title", "").strip(),
            "is_ivisa": _is_ivisa(domain),
            "sentiment": _classify_domain(domain),
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
        results.append({
            "position": item.get("position", 0),
            "url": item.get("url", "").strip(),
            "domain": domain,
            "title": item.get("title", "").strip(),
            "is_ivisa": _is_ivisa(domain),
            "sentiment": _classify_domain(domain),
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
