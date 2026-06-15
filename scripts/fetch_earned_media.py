from __future__ import annotations

"""
fetch_earned_media.py — Fetches earned media mentions via SerpAPI.

Earned media = third-party coverage of iVisa that iVisa does NOT own or control.
Sources tracked:
  • Google News (tbm=nws) — press coverage, news articles
  • Travel blogs & press — site: searches on top travel domains
  • Reddit — site:reddit.com searches (excluding r/ivisa)
  • YouTube — site:youtube.com searches
  • Instagram — site:instagram.com searches (third-party only)
  • TikTok — site:tiktok.com searches

iVisa-owned channels excluded:
  ivisa.com, blog.ivisa.com, help.ivisa.com,
  @ivisa on Instagram, @ivisa on TikTok, r/ivisa

Scoring:
  - Each mention is classified: positive / neutral / negative
  - Score = weighted average: positive=1.0, neutral=0.5, negative=0.0
  - Final score × 100  →  0–100

Returns a dict shaped:
{
  "score": float,          # 0-100
  "mentions": [
    {
      "title": str,
      "url": str,
      "source": str,       # "news" | "blog" | "reddit" | "youtube" | "instagram" | "tiktok"
      "domain": str,
      "sentiment": "positive" | "neutral" | "negative",
      "snippet": str,
      "date": str | None,
    }, ...
  ],
  "counts": {
    "total": int,
    "positive": int,
    "neutral": int,
    "negative": int,
  },
  "source_breakdown": {
    "news": int,
    "blog": int,
    "reddit": int,
    "youtube": int,
    "instagram": int,
    "tiktok": int,
  },
}
"""

import logging
import re
import time
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse

import requests

from scripts.config import SERPAPI_KEY

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"

# ---------------------------------------------------------------------------
# iVisa-owned channels — always excluded
# ---------------------------------------------------------------------------

IVISA_OWNED_DOMAINS = {
    "ivisa.com",
    "blog.ivisa.com",
    "help.ivisa.com",
}

IVISA_OWNED_SNIPPETS = [
    "ivisa.com/blog",
    "r/ivisa",
    "/r/ivisa",
]

# iVisa's OWN social-media accounts — posts from these are NOT earned media
# (earned media = what OTHER people/outlets say about iVisa). A URL is excluded
# if it contains any of these handle paths (case-insensitive). Confirmed handles
# (June 2026): IG @ivisa_travel, TikTok @ivisa_travel, YouTube @iVisa_travel,
# Facebook /iVisaTravel, Pinterest /iVisa__Travel, LinkedIn /company/ivisa.
IVISA_OWNED_SOCIAL = [
    "instagram.com/ivisa_travel",
    "tiktok.com/@ivisa_travel",
    "youtube.com/@ivisa_travel",
    "facebook.com/ivisatravel",
    "pinterest.com/ivisa__travel",
    "linkedin.com/company/ivisa",
    # Defensive extras for common handle variants / redirects
    "instagram.com/ivisa",
    "tiktok.com/@ivisa",
    "youtube.com/@ivisa",
    "facebook.com/ivisa",
    "x.com/ivisa",
    "twitter.com/ivisa",
]

# ---------------------------------------------------------------------------
# Sentiment classification
# ---------------------------------------------------------------------------

POSITIVE_SIGNALS = [
    "legit", "legitimate", "safe", "trusted", "reliable", "recommend",
    "honest", "worth it", "approved", "verified", "best", "real",
    "worked", "works", "helped", "guide", "how to use", "review", "pros",
    "easy", "convenient", "fast", "efficient", "excellent", "great",
    "helpful", "officially", "trusted service", "5 star", "five star",
]

NEGATIVE_SIGNALS = [
    "scam", "fraud", "fake", "danger", "problem", "complaint",
    "steal", "stolen", "worst", "terrible", "rip off", "ripoff", "warning",
    "cheat", "mislead", "suspicious", "beware", "do not use", "don't use",
    "stay away", "con ", "overcharged", "refund denied", "lost money",
    "never again", "waste of", "disappointed", "not legit", "not safe",
    "not legitimate", "not trusted", "shady", "unresponsive", "scammed",
    "avoid ivisa", "avoid using ivisa", "avoid this service",
    # Consumer protection / authority warnings
    # e.g. "Consumer advice center warns of UK travel permit scam" (heise.de)
    "warns of", "warns users", "warns travellers", "warns travelers",
    "consumer advice center", "consumer advice centre", "consumer protection warns",
    "travel permit scam", "permit scam",
]

POSITIVE_DOMAINS_EM = [
    # Editorial, press, and travel media only — no review aggregators
    "forbes.com", "travelpulse.com", "skift.com", "travel.state.gov",
    "nytimes.com", "theguardian.com", "bbc.com", "cnbc.com",
    "businessinsider.com", "lonelyplanet.com",
    "nomadicmatt.com", "thepointsguy.com", "moneysavingexpert.com",
    "globenewswire.com", "prnewswire.com", "businesswire.com",
    "accesswire.com", "einpresswire.com",
]

# Review aggregators and complaint sites — excluded from earned media score
# (Trustpilot, Sitejabber, TripAdvisor are NOT earned media — they are
# user-review platforms that can be highly negative regardless of brand effort)
REVIEW_AGGREGATORS = [
    "trustpilot.com", "sitejabber.com", "tripadvisor.com",
    "yelp.com", "consumerreports.org", "consumers.co",
]

NEGATIVE_DOMAINS_EM = [
    "bbb.org", "scamalert.com", "ripoffreport.com",
    "complaints.com", "pissedconsumer.com", "complaintsboard.com",
]


def _is_review_aggregator(domain: str) -> bool:
    """Return True if domain is a review aggregator — excluded from earned media."""
    d = domain.lower().strip()
    return any(r in d for r in REVIEW_AGGREGATORS)


def _classify_mention(domain: str, title: str, snippet: str = "") -> str:
    """Return 'positive', 'negative', or 'neutral' for a mention."""
    domain_lower = domain.lower().strip()
    text = f"{title} {snippet}".lower()

    # Review aggregators are excluded upstream — skip classification
    if _is_review_aggregator(domain_lower):
        return "excluded"

    for d in NEGATIVE_DOMAINS_EM:
        if d in domain_lower:
            return "negative"

    for signal in NEGATIVE_SIGNALS:
        if signal in text:
            return "negative"

    for d in POSITIVE_DOMAINS_EM:
        if d in domain_lower:
            # Still check for negative signals in title/snippet
            for signal in NEGATIVE_SIGNALS:
                if signal in text:
                    return "negative"
            return "positive"

    for signal in POSITIVE_SIGNALS:
        if signal in text:
            return "positive"

    return "neutral"


def _is_ivisa_owned(url: str, domain: str) -> bool:
    """Return True if this result is from an iVisa-owned channel (website,
    blog, owned subreddit, OR an official iVisa social-media account)."""
    domain_lower = domain.lower().strip()
    for owned in IVISA_OWNED_DOMAINS:
        if owned in domain_lower:
            return True
    url_lower = url.lower()
    for snippet in IVISA_OWNED_SNIPPETS:
        if snippet in url_lower:
            return True
    for handle in IVISA_OWNED_SOCIAL:
        if handle in url_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# SerpAPI query helpers
# ---------------------------------------------------------------------------

def _serpapi_search(params: dict) -> list[dict]:
    """Run a SerpAPI search; return list of result dicts."""
    if not SERPAPI_KEY:
        return []
    params["api_key"] = SERPAPI_KEY
    try:
        resp = requests.get(SERPAPI_URL, params=params, timeout=25)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.error("SerpAPI earned media request failed: %s", exc)
        return {}


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "").lower()
    except Exception:
        return ""


def _mentions_ivisa(text: str) -> bool:
    """Return True if text mentions iVisa as a brand."""
    return bool(re.search(r'\bivisa\b', text, re.IGNORECASE))


def _fetch_article_body(url: str, timeout: int = 4) -> str:
    """Best-effort fetch of article body text. Returns '' on failure."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; iVisaBot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        # Strip tags, return plain text
        text = re.sub(r'<[^>]+>', ' ', resp.text)
        text = re.sub(r'\s+', ' ', text)
        return text[:5000]  # cap at 5000 chars
    except Exception:
        return ""


def _parse_organic_results(data: dict, source_label: str) -> list[dict]:
    """Parse organic_results from SerpAPI response into mention dicts."""
    mentions = []
    for item in data.get("organic_results", []):
        url = item.get("link", "")
        if not url:
            continue
        domain = item.get("domain", "") or _extract_domain(url)
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        date_str = item.get("date", None)

        if _is_ivisa_owned(url, domain):
            continue
        if _is_review_aggregator(domain):
            continue

        # Must mention iVisa in title or snippet
        if not _mentions_ivisa(title) and not _mentions_ivisa(snippet):
            continue

        sentiment = _classify_mention(domain, title, snippet)
        if sentiment == "excluded":
            continue
        mentions.append({
            "title": title,
            "url": url,
            "source": source_label,
            "domain": domain,
            "sentiment": sentiment,
            "snippet": snippet,
            "date": date_str,
        })
    return mentions


def _parse_news_results(data: dict, require_ivisa_mention: bool = True) -> list[dict]:
    """Parse news_results from SerpAPI Google News response.

    If require_ivisa_mention=True, only include articles where iVisa appears
    in the title, snippet, or article body (best-effort fetch).
    """
    mentions = []
    items = data.get("news_results", data.get("organic_results", []))
    for item in items:
        url = item.get("link", "")
        if not url:
            continue
        domain = _extract_domain(url)
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        date_str = item.get("date", None)

        if _is_ivisa_owned(url, domain):
            continue
        if _is_review_aggregator(domain):
            continue

        # Check if iVisa is mentioned in title or snippet
        body_text = ""
        if require_ivisa_mention and not _mentions_ivisa(title) and not _mentions_ivisa(snippet):
            # Not in title/snippet — try fetching article body
            body_text = _fetch_article_body(url)
            if not _mentions_ivisa(body_text):
                continue  # iVisa not mentioned anywhere — skip

        sentiment = _classify_mention(domain, title, snippet + " " + body_text[:500])
        if sentiment == "excluded":
            continue
        mentions.append({
            "title": title,
            "url": url,
            "source": "news",
            "domain": domain,
            "sentiment": sentiment,
            "snippet": snippet,
            "date": date_str,
        })
    return mentions


# ---------------------------------------------------------------------------
# Source-specific fetchers
# ---------------------------------------------------------------------------

TRAVEL_BLOG_SITES = [
    "site:lonelyplanet.com",
    "site:nomadicmatt.com",
    "site:thepointsguy.com",
    "site:travelpulse.com",
    "site:skift.com",
    "site:forbes.com/travel",
    "site:businessinsider.com",
    "site:condénast.com OR site:cntraveler.com",
    "site:afar.com",
    "site:matadornetwork.com",
]

EM_QUERIES = [
    "iVisa review",
    "iVisa legit",
    "iVisa visa service",
    "is iVisa safe",
    "iVisa scam",
]


def _fetch_google_news(query: str, date_range: tuple[str, str] | None = None) -> list[dict]:
    """Fetch Google News results for a query. date_range = (YYYY-MM-DD, YYYY-MM-DD)."""
    params = {
        "engine": "google",
        "q": query,
        "tbm": "nws",
        "gl": "us",
        "hl": "en",
        "num": 10,
    }
    if date_range:
        start, end = date_range
        # SerpAPI/Google date format: MM/DD/YYYY
        start_fmt = _date_to_google_fmt(start)
        end_fmt = _date_to_google_fmt(end)
        params["tbs"] = f"cdr:1,cd_min:{start_fmt},cd_max:{end_fmt}"

    data = _serpapi_search(params)
    return _parse_news_results(data)


def _fetch_travel_blogs(date_range: tuple[str, str] | None = None) -> list[dict]:
    """Fetch iVisa mentions from top travel blog/press sites."""
    all_mentions = []
    # Batch query across travel sites
    sites_combined = " OR ".join([
        "site:lonelyplanet.com",
        "site:nomadicmatt.com",
        "site:thepointsguy.com",
        "site:travelpulse.com",
        "site:skift.com",
        "site:forbes.com",
        "site:businessinsider.com",
        "site:cntraveler.com",
        "site:afar.com",
        "site:matadornetwork.com",
    ])
    params = {
        "engine": "google",
        "q": f"iVisa ({sites_combined})",
        "gl": "us",
        "hl": "en",
        "num": 20,
    }
    if date_range:
        start_fmt = _date_to_google_fmt(date_range[0])
        end_fmt   = _date_to_google_fmt(date_range[1])
        params["tbs"] = f"cdr:1,cd_min:{start_fmt},cd_max:{end_fmt}"

    data = _serpapi_search(params)
    mentions = _parse_organic_results(data, "blog")
    all_mentions.extend(mentions)
    return all_mentions


def _fetch_reddit(date_range: tuple[str, str] | None = None) -> list[dict]:
    """Fetch Reddit mentions of iVisa (excluding r/ivisa subreddit)."""
    params = {
        "engine": "google",
        "q": "iVisa site:reddit.com -site:reddit.com/r/ivisa",
        "gl": "us",
        "hl": "en",
        "num": 20,
    }
    if date_range:
        start_fmt = _date_to_google_fmt(date_range[0])
        end_fmt   = _date_to_google_fmt(date_range[1])
        params["tbs"] = f"cdr:1,cd_min:{start_fmt},cd_max:{end_fmt}"

    data = _serpapi_search(params)
    return _parse_organic_results(data, "reddit")


def _fetch_youtube(date_range: tuple[str, str] | None = None) -> list[dict]:
    """Fetch YouTube mentions/reviews of iVisa."""
    params = {
        "engine": "google",
        "q": "iVisa review site:youtube.com",
        "gl": "us",
        "hl": "en",
        "num": 10,
    }
    if date_range:
        start_fmt = _date_to_google_fmt(date_range[0])
        end_fmt   = _date_to_google_fmt(date_range[1])
        params["tbs"] = f"cdr:1,cd_min:{start_fmt},cd_max:{end_fmt}"

    data = _serpapi_search(params)
    return _parse_organic_results(data, "youtube")


def _fetch_instagram(date_range: tuple[str, str] | None = None) -> list[dict]:
    """Fetch Instagram third-party mentions of iVisa."""
    params = {
        "engine": "google",
        "q": "iVisa site:instagram.com -site:instagram.com/ivisa",
        "gl": "us",
        "hl": "en",
        "num": 10,
    }
    if date_range:
        start_fmt = _date_to_google_fmt(date_range[0])
        end_fmt   = _date_to_google_fmt(date_range[1])
        params["tbs"] = f"cdr:1,cd_min:{start_fmt},cd_max:{end_fmt}"

    data = _serpapi_search(params)
    return _parse_organic_results(data, "instagram")


def _fetch_tiktok(date_range: tuple[str, str] | None = None) -> list[dict]:
    """Fetch TikTok third-party mentions of iVisa."""
    params = {
        "engine": "google",
        "q": "iVisa site:tiktok.com -site:tiktok.com/@ivisa",
        "gl": "us",
        "hl": "en",
        "num": 10,
    }
    if date_range:
        start_fmt = _date_to_google_fmt(date_range[0])
        end_fmt   = _date_to_google_fmt(date_range[1])
        params["tbs"] = f"cdr:1,cd_min:{start_fmt},cd_max:{end_fmt}"

    data = _serpapi_search(params)
    return _parse_organic_results(data, "tiktok")


def _date_to_google_fmt(iso_date: str) -> str:
    """Convert YYYY-MM-DD to MM/DD/YYYY for Google tbs parameter."""
    parts = iso_date.split("-")
    if len(parts) == 3:
        return f"{parts[1]}/{parts[2]}/{parts[0]}"
    return iso_date


# ---------------------------------------------------------------------------
# Score calculation
# ---------------------------------------------------------------------------

def _calculate_em_score(mentions: list[dict]) -> float:
    """
    Score earned media: positive=1.0, neutral=0.5, negative=0.0.
    Simple average (no position weighting — all mentions count equally).
    Returns 50.0 if no mentions.
    """
    if not mentions:
        return 50.0

    SCORE_MAP = {"positive": 1.0, "neutral": 0.5, "negative": 0.0}
    scores = [SCORE_MAP.get(m.get("sentiment", "neutral"), 0.5) for m in mentions]
    return round((sum(scores) / len(scores)) * 100, 2)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_earned_media_data(date_range: tuple[str, str] | None = None) -> dict[str, Any]:
    """
    Fetch all earned media mentions for iVisa across all sources.

    Args:
        date_range: Optional (start_date, end_date) as YYYY-MM-DD strings.
                    If None, fetches recent results (no date filter).

    Returns:
        {
          "score": float,
          "mentions": [...],
          "counts": {"total": int, "positive": int, "neutral": int, "negative": int},
          "source_breakdown": {"news": int, "blog": int, ...},
        }
    """
    if not SERPAPI_KEY:
        logger.warning("SERPAPI_KEY not set — using default earned media score (50).")
        return {
            "score": 50.0,
            "mentions": [],
            "counts": {"total": 0, "positive": 0, "neutral": 0, "negative": 0},
            "source_breakdown": {"news": 0, "blog": 0, "reddit": 0, "youtube": 0, "instagram": 0, "tiktok": 0},
        }

    # Default: last 90 days
    if date_range is None:
        today = date.today()
        date_range = ((today - timedelta(days=90)).isoformat(), today.isoformat())

    all_mentions: list[dict] = []
    date_str = f" [{date_range[0]} → {date_range[1]}]"
    logger.info("  Fetching earned media%s...", date_str)

    # 1. Google News — query each EM search term
    for query in EM_QUERIES:
        mentions = _fetch_google_news(query, date_range)
        all_mentions.extend(mentions)
        logger.debug("    News '%s': %d mentions", query, len(mentions))
        time.sleep(0.3)

    # 2. Travel blogs & press
    blog_mentions = _fetch_travel_blogs(date_range)
    all_mentions.extend(blog_mentions)
    logger.info("    Travel blogs: %d mentions", len(blog_mentions))
    time.sleep(0.3)

    # 3. Reddit
    reddit_mentions = _fetch_reddit(date_range)
    all_mentions.extend(reddit_mentions)
    logger.info("    Reddit: %d mentions", len(reddit_mentions))
    time.sleep(0.3)

    # 4. YouTube
    youtube_mentions = _fetch_youtube(date_range)
    all_mentions.extend(youtube_mentions)
    logger.info("    YouTube: %d mentions", len(youtube_mentions))
    time.sleep(0.3)

    # 5. Instagram
    ig_mentions = _fetch_instagram(date_range)
    all_mentions.extend(ig_mentions)
    logger.info("    Instagram: %d mentions", len(ig_mentions))
    time.sleep(0.3)

    # 6. TikTok
    tt_mentions = _fetch_tiktok(date_range)
    all_mentions.extend(tt_mentions)
    logger.info("    TikTok: %d mentions", len(tt_mentions))

    # De-duplicate by URL
    seen_urls: set[str] = set()
    unique_mentions: list[dict] = []
    for m in all_mentions:
        if m["url"] not in seen_urls:
            seen_urls.add(m["url"])
            unique_mentions.append(m)

    # Sort: newest first (date desc), then by source type
    SOURCE_ORDER = {"news": 0, "blog": 1, "reddit": 2, "youtube": 3, "instagram": 4, "tiktok": 5}
    unique_mentions.sort(key=lambda m: (
        m.get("date") or "0000",  # date desc (lexicographic works for most formats)
        SOURCE_ORDER.get(m.get("source", "blog"), 9),
    ), reverse=True)

    # Counts
    counts = {"total": len(unique_mentions), "positive": 0, "neutral": 0, "negative": 0}
    source_breakdown = {"news": 0, "blog": 0, "reddit": 0, "youtube": 0, "instagram": 0, "tiktok": 0}
    for m in unique_mentions:
        s = m.get("sentiment", "neutral")
        if s in counts:
            counts[s] += 1
        src = m.get("source", "blog")
        if src in source_breakdown:
            source_breakdown[src] += 1

    score = _calculate_em_score(unique_mentions)
    logger.info("  → Earned Media Score: %.1f (%d mentions: %d pos / %d neutral / %d neg)",
                score, counts["total"], counts["positive"], counts["neutral"], counts["negative"])

    return {
        "score": score,
        "mentions": unique_mentions,
        "counts": counts,
        "source_breakdown": source_breakdown,
    }


# ---------------------------------------------------------------------------
# Per-country earned media
# ---------------------------------------------------------------------------

def fetch_earned_media_by_country(countries: dict) -> dict:
    """
    Fetch earned media mentions for iVisa per country using gl= parameter.

    Args:
        countries: dict of {code: {"name": str, "flag": str, ...}} from config.COUNTRIES

    Returns:
        {
          country_code: {
            "score": float,
            "mentions": [...],
            "counts": {"total": int, "positive": int, "neutral": int, "negative": int},
          }, ...
        }
    """
    if not SERPAPI_KEY:
        logger.warning("SERPAPI_KEY not set — skipping per-country earned media fetch.")
        return {}

    today = date.today()
    date_range = ((today - timedelta(days=90)).isoformat(), today.isoformat())
    start_fmt = _date_to_google_fmt(date_range[0])
    end_fmt = _date_to_google_fmt(date_range[1])
    tbs = f"cdr:1,cd_min:{start_fmt},cd_max:{end_fmt}"

    results: dict = {}

    for code, config in countries.items():
        country_name = config.get("name", code)
        gl = code.lower()
        logger.info("  [EM by country] %s (%s)...", country_name, code)

        all_mentions: list[dict] = []

        try:
            # 1. Google News for each EM query
            for query in EM_QUERIES:
                params = {
                    "engine": "google",
                    "q": query,
                    "tbm": "nws",
                    "gl": gl,
                    "hl": "en",
                    "num": 10,
                    "tbs": tbs,
                }
                data = _serpapi_search(params)
                all_mentions.extend(_parse_news_results(data))
                time.sleep(0.3)

            # 2. Travel blogs
            sites_combined = " OR ".join([
                "site:lonelyplanet.com", "site:nomadicmatt.com",
                "site:thepointsguy.com", "site:travelpulse.com",
                "site:skift.com", "site:forbes.com", "site:businessinsider.com",
                "site:cntraveler.com", "site:afar.com", "site:matadornetwork.com",
            ])
            params = {
                "engine": "google",
                "q": f"iVisa ({sites_combined})",
                "gl": gl,
                "hl": "en",
                "num": 20,
                "tbs": tbs,
            }
            data = _serpapi_search(params)
            all_mentions.extend(_parse_organic_results(data, "blog"))
            time.sleep(0.3)

            # 3. Reddit
            params = {
                "engine": "google",
                "q": "iVisa site:reddit.com -site:reddit.com/r/ivisa",
                "gl": gl,
                "hl": "en",
                "num": 20,
                "tbs": tbs,
            }
            data = _serpapi_search(params)
            all_mentions.extend(_parse_organic_results(data, "reddit"))
            time.sleep(0.3)

            # 4. YouTube
            params = {
                "engine": "google",
                "q": "iVisa review site:youtube.com",
                "gl": gl,
                "hl": "en",
                "num": 10,
                "tbs": tbs,
            }
            data = _serpapi_search(params)
            all_mentions.extend(_parse_organic_results(data, "youtube"))
            time.sleep(0.3)

        except Exception as exc:
            logger.error("  [EM by country] %s failed: %s", code, exc)

        # De-duplicate
        seen: set[str] = set()
        unique: list[dict] = []
        for m in all_mentions:
            if m["url"] not in seen:
                seen.add(m["url"])
                unique.append(m)

        counts = {"total": len(unique), "positive": 0, "neutral": 0, "negative": 0}
        for m in unique:
            s = m.get("sentiment", "neutral")
            if s in counts:
                counts[s] += 1

        score = _calculate_em_score(unique)
        logger.info("    → %s EM: %.1f (%d mentions)", code, score, counts["total"])

        results[code] = {
            "score": score,
            "mentions": unique,
            "counts": counts,
        }

    return results
