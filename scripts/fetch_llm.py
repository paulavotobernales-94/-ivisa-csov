from __future__ import annotations

"""
fetch_llm.py — Query Claude and Gemini to measure iVisa's LLM visibility.

Part A: 20 brand-specific queries — average sentiment scored by both models.
Part B: 30 general queries — detect iVisa mentions, score sentiment where cited.

LLM_Score = (Part_A_score + Part_B_score) / 2

Returns:
{
  "part_a": {
    "results": [
      {
        "query": str,
        "claude_response": str,
        "gemini_response": str,
        "claude_sentiment": float,
        "gemini_sentiment": float,
        "avg_sentiment": float,
      }, ...
    ],
    "score": float,
  },
  "part_b": {
    "results": [
      {
        "query": str,
        "claude_mentions_ivisa": bool,
        "gemini_mentions_ivisa": bool,
        "claude_sentiment": float | None,
        "gemini_sentiment": float | None,
        "avg_sentiment": float | None,
      }, ...
    ],
    "mention_rate": float,
    "avg_positive_sentiment": float,
    "score": float,
  },
  "global_score": float,
}
"""

import logging
import time
from typing import Any

from scripts.config import (
    BRAND_QUERIES,
    CLAUDE_API_KEY,
    CLAUDE_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GENERAL_QUERIES,
    SENTIMENT_PROMPT_TEMPLATE,
    USE_GEMINI,
)

logger = logging.getLogger(__name__)

# Set True once Gemini returns a free-tier/quota 429 in a run, so we stop firing
# ~50 more calls that will all fail (saves minutes) and log the reason just once.
_gemini_quota_hit = False


# ---------------------------------------------------------------------------
# Model clients (lazy init)
# ---------------------------------------------------------------------------

def _get_claude_client():
    if not CLAUDE_API_KEY:
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    except Exception as exc:
        logger.error("Failed to init Claude client: %s", exc)
        return None


def _get_gemini_client():
    """Return a google.genai Client, or None if unavailable/disabled."""
    if not USE_GEMINI:
        logger.info("  Gemini is disabled (USE_GEMINI=False) — LLM scores will be Claude-only.")
        return None
    if not GEMINI_API_KEY:
        return None
    try:
        from google import genai as google_genai
        return google_genai.Client(api_key=GEMINI_API_KEY)
    except ImportError:
        logger.error("google-genai not installed. Run: pip3 install google-genai")
        return None
    except Exception as exc:
        logger.error("Failed to init Gemini client: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Single-call helpers
# ---------------------------------------------------------------------------

def _ask_claude(client, prompt: str, max_tokens: int = 500, retries: int = 2) -> str | None:
    """Send a prompt to Claude with retry on rate-limit. Returns text or None on failure."""
    if client is None:
        return None
    for attempt in range(retries + 1):
        try:
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            text = message.content[0].text.strip() if message.content else None
            return text if text else None
        except Exception as exc:
            exc_str = str(exc).lower()
            if attempt < retries and ("rate" in exc_str or "529" in exc_str or "overloaded" in exc_str):
                wait = 10 * (attempt + 1)
                logger.warning("Claude rate limit (attempt %d/%d) — retrying in %ds", attempt+1, retries+1, wait)
                time.sleep(wait)
            else:
                logger.warning("Claude query failed: %s", exc)
                return None
    return None


def _ask_gemini(client, prompt: str, with_grounding: bool = False, retries: int = 2) -> tuple[str | None, list[str]]:
    """
    Send a prompt to Gemini via google.genai Client with retry on rate-limit.
    Returns (text, sources) — sources is a list of URLs from grounding (if enabled).
    Falls back to (None, []) on error.
    """
    global _gemini_quota_hit
    if client is None or _gemini_quota_hit:
        return None, []
    use_grounding = with_grounding   # may be dropped mid-loop if grounding quota is hit
    for attempt in range(retries + 1):
        try:
            kwargs = {"model": GEMINI_MODEL, "contents": prompt}
            if use_grounding:
                try:
                    import google.genai.types as genai_types
                    kwargs["config"] = genai_types.GenerateContentConfig(
                        tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
                    )
                except Exception:
                    pass  # grounding not available — fall through without it

            response = client.models.generate_content(**kwargs)
            text = response.text.strip() if response.text else None

            # Extract grounding sources if available
            sources = []
            if use_grounding:
                try:
                    chunks = response.candidates[0].grounding_metadata.grounding_chunks
                    for chunk in chunks:
                        url = getattr(getattr(chunk, 'web', None), 'uri', None)
                        if url:
                            sources.append(url)
                except Exception:
                    pass

            return text, sources
        except Exception as exc:
            exc_str = str(exc).lower()
            # RESOURCE_EXHAUSTED / free_tier = a quota was hit (per-day, per-minute,
            # or the separate Google-Search GROUNDING quota — which is much smaller).
            quota_exhausted = "resource_exhausted" in exc_str or "free_tier" in exc_str
            transient_limit = not quota_exhausted and ("rate" in exc_str or "429" in exc_str)

            # Grounding fallback: the grounding tool has its own tiny free quota.
            # If a GROUNDED call is quota-blocked, retry WITHOUT grounding — the plain
            # text quota (~1,500/day) is generous, so Gemini's sentiment still gets
            # produced and averaged with Claude (we just lose the cited source links).
            if quota_exhausted and use_grounding:
                logger.warning(
                    "Gemini grounding quota hit — retrying this query WITHOUT grounding "
                    "(sentiment still scored; source links unavailable)."
                )
                use_grounding = False
                continue

            if attempt < retries and transient_limit:
                wait = 15 * (attempt + 1)
                logger.warning("Gemini rate limit (attempt %d/%d) — retrying in %ds", attempt+1, retries+1, wait)
                time.sleep(wait)
            else:
                if quota_exhausted:
                    # We get here only if a NON-grounded call is also quota-blocked,
                    # i.e. the core text quota is genuinely gone — disable Gemini.
                    if not _gemini_quota_hit:
                        # Full error names the exact quota (…PerDay / …PerMinute / grounding).
                        logger.warning(
                            "Gemini free-tier text quota hit (model=%s, grounding already off) — "
                            "disabling Gemini for the rest of this run. FULL ERROR: %s",
                            GEMINI_MODEL, str(exc)[:600],
                        )
                    _gemini_quota_hit = True
                else:
                    logger.warning("Gemini query failed (model=%s): %s", GEMINI_MODEL, exc)
                return None, []
    return None, []


def _score_sentiment(text: str, claude_client, gemini_model) -> tuple[float | None, float | None]:
    """
    Return (claude_score, gemini_score) for sentiment of text (0–100 each).
    Uses Claude for scoring both to save quota; Gemini scored via Claude too.
    Actually we use each model to score its own output is the correct approach,
    but to avoid double API calls we use Claude as the sentiment judge for both.
    """
    if not text:
        return None, None

    prompt = SENTIMENT_PROMPT_TEMPLATE.format(text=text[:2000])

    claude_score = None
    if claude_client:
        raw = _ask_claude(claude_client, prompt, max_tokens=10)
        if raw:
            try:
                claude_score = max(0.0, min(100.0, float(raw)))
            except ValueError:
                pass

    gemini_score = None
    if gemini_model:
        raw, _ = _ask_gemini(gemini_model, prompt)
        if raw:
            try:
                import re
                nums = re.findall(r'\d+(?:\.\d+)?', raw)
                if nums:
                    gemini_score = max(0.0, min(100.0, float(nums[0])))
            except ValueError:
                pass

    return claude_score, gemini_score


# ---------------------------------------------------------------------------
# Part A — Brand queries
# ---------------------------------------------------------------------------

def _run_part_a(claude_client, gemini_model) -> dict[str, Any]:
    """Run 20 brand queries; score sentiment with both models."""
    results = []

    for query in BRAND_QUERIES:
        logger.debug("  Part A query: %s", query)

        claude_response = _ask_claude(claude_client, query)
        time.sleep(0.5)
        gemini_response, gemini_sources = _ask_gemini(gemini_model, query, with_grounding=True)
        time.sleep(0.5)

        # Score Claude's response
        claude_sentiment = None
        if claude_response:
            raw = _ask_claude(claude_client, SENTIMENT_PROMPT_TEMPLATE.format(text=claude_response[:2000]), max_tokens=10)
            if raw:
                try:
                    claude_sentiment = max(0.0, min(100.0, float(raw)))
                except ValueError:
                    pass
            time.sleep(0.3)

        # Score Gemini's response
        gemini_sentiment = None
        if gemini_response:
            import re
            raw, _ = _ask_gemini(gemini_model, SENTIMENT_PROMPT_TEMPLATE.format(text=gemini_response[:2000]))
            if raw:
                try:
                    nums = re.findall(r'\d+(?:\.\d+)?', raw)
                    if nums:
                        gemini_sentiment = max(0.0, min(100.0, float(nums[0])))
                except ValueError:
                    pass
            time.sleep(0.3)

        scores = [s for s in [claude_sentiment, gemini_sentiment] if s is not None]
        avg_sentiment = round(sum(scores) / len(scores), 2) if scores else 50.0

        results.append({
            "query": query,
            "claude_response": claude_response,
            "gemini_response": gemini_response,
            "gemini_sources": gemini_sources,
            "claude_sentiment": claude_sentiment,
            "gemini_sentiment": gemini_sentiment,
            "avg_sentiment": avg_sentiment,
        })

    avg_scores = [r["avg_sentiment"] for r in results]
    score = round(sum(avg_scores) / len(avg_scores), 2) if avg_scores else 50.0

    return {"results": results, "score": score}


# ---------------------------------------------------------------------------
# Part B — General queries (mention detection)
# ---------------------------------------------------------------------------

def _run_part_b(claude_client, gemini_model) -> dict[str, Any]:
    """Run 30 general queries; detect iVisa mentions and score sentiment."""
    import re

    results = []
    mention_count = 0
    positive_sentiments = []

    for query in GENERAL_QUERIES:
        logger.debug("  Part B query: %s", query)

        claude_response = _ask_claude(claude_client, query)
        time.sleep(0.5)
        gemini_response, gemini_sources = _ask_gemini(gemini_model, query, with_grounding=True)
        time.sleep(0.5)

        claude_mentions = "ivisa" in (claude_response or "").lower()
        gemini_mentions = "ivisa" in (gemini_response or "").lower()
        either_mentions = claude_mentions or gemini_mentions

        if either_mentions:
            mention_count += 1

        # Score sentiment only when mentioned
        claude_sentiment = None
        gemini_sentiment = None

        if claude_mentions and claude_response:
            raw = _ask_claude(claude_client, SENTIMENT_PROMPT_TEMPLATE.format(text=claude_response[:2000]), max_tokens=10)
            if raw:
                try:
                    claude_sentiment = max(0.0, min(100.0, float(raw)))
                except ValueError:
                    pass
            time.sleep(0.3)

        if gemini_mentions and gemini_response:
            raw, _ = _ask_gemini(gemini_model, SENTIMENT_PROMPT_TEMPLATE.format(text=gemini_response[:2000]))
            if raw:
                try:
                    nums = re.findall(r'\d+(?:\.\d+)?', raw)
                    if nums:
                        gemini_sentiment = max(0.0, min(100.0, float(nums[0])))
                except ValueError:
                    pass
            time.sleep(0.3)

        scores = [s for s in [claude_sentiment, gemini_sentiment] if s is not None]
        avg_sentiment = round(sum(scores) / len(scores), 2) if scores else None

        if avg_sentiment is not None:
            positive_sentiments.append(avg_sentiment)

        results.append({
            "query": query,
            "claude_response": claude_response,   # store the response so the report can show it
            "gemini_response": gemini_response,
            "claude_mentions_ivisa": claude_mentions,
            "gemini_mentions_ivisa": gemini_mentions,
            "gemini_sources": gemini_sources,
            "claude_sentiment": claude_sentiment,
            "gemini_sentiment": gemini_sentiment,
            "avg_sentiment": avg_sentiment,
        })

    mention_rate = mention_count / len(GENERAL_QUERIES) if GENERAL_QUERIES else 0.0
    avg_positive = round(sum(positive_sentiments) / len(positive_sentiments), 2) if positive_sentiments else 50.0
    score = round(mention_rate * 100 * 0.4 + avg_positive * 0.6, 2)

    return {
        "results": results,
        "mention_rate": round(mention_rate, 4),
        "avg_positive_sentiment": avg_positive,
        "score": score,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_llm_data() -> dict[str, Any]:
    """
    Query both Claude and Gemini for brand and general queries.
    Calculates LLM_Score = (Part_A + Part_B) / 2.
    Gracefully handles missing API keys.
    """
    claude_client = _get_claude_client()
    gemini_model = _get_gemini_client()

    if not claude_client and not gemini_model:
        logger.warning("No LLM API keys set — returning default LLM score of 50.")
        return {
            "part_a": {"results": [], "score": 50.0},
            "part_b": {"results": [], "mention_rate": 0.0, "avg_positive_sentiment": 50.0, "score": 50.0},
            "global_score": 50.0,
        }

    logger.info("  Running Part A — brand queries (%d queries)", len(BRAND_QUERIES))
    part_a = _run_part_a(claude_client, gemini_model)
    logger.info("  → Part A score: %.1f", part_a["score"])

    logger.info("  Running Part B — general queries (%d queries)", len(GENERAL_QUERIES))
    part_b = _run_part_b(claude_client, gemini_model)
    logger.info("  → Part B score: %.1f (mention rate: %.1f%%)", part_b["score"], part_b["mention_rate"] * 100)

    global_score = round((part_a["score"] + part_b["score"]) / 2, 2)
    logger.info("  → Global LLM Score: %.1f", global_score)

    return {
        "part_a": part_a,
        "part_b": part_b,
        "global_score": global_score,
    }


# ---------------------------------------------------------------------------
# Per-country LLM brand perception
# ---------------------------------------------------------------------------

COUNTRY_BRAND_QUERY_TEMPLATES = [
    "Is iVisa trustworthy for travelers from {country_name}?",
    "Is iVisa legit for {country_name} passport holders?",
    "Is iVisa safe to use in {country_name}?",
    "iVisa review {country_name}",
    "Should I use iVisa from {country_name}?",
]


def run_llm_by_country(countries: dict, claude_client, gemini_model) -> dict:
    """
    Run 5 country-specific brand queries against Claude and Gemini for each country.

    Args:
        countries: dict of {code: {"name": str, ...}} from config.COUNTRIES
        claude_client: Anthropic client instance (or None)
        gemini_model:  google.genai Client instance (or None)

    Returns:
        {
          country_code: {
            "queries": [
              {
                "query": str,
                "claude_response": str | None,
                "gemini_response": str | None,
                "claude_sentiment": float | None,
                "gemini_sentiment": float | None,
                "avg_sentiment": float,
              }, ...
            ],
            "avg_sentiment": float,
          }, ...
        }
    """
    import re as _re

    results: dict = {}

    for code, config in countries.items():
        country_name = config.get("name", code)
        logger.info("  [LLM by country] %s (%s)...", country_name, code)

        query_results = []

        try:
            for template in COUNTRY_BRAND_QUERY_TEMPLATES:
                query = template.format(country_name=country_name)

                claude_response = _ask_claude(claude_client, query)
                time.sleep(0.5)
                gemini_response, _ = _ask_gemini(gemini_model, query, with_grounding=True)
                time.sleep(0.5)

                # Score Claude response using Claude
                claude_sentiment = None
                if claude_response:
                    raw = _ask_claude(
                        claude_client,
                        SENTIMENT_PROMPT_TEMPLATE.format(text=claude_response[:2000]),
                        max_tokens=10,
                    )
                    if raw:
                        try:
                            claude_sentiment = max(0.0, min(100.0, float(raw)))
                        except ValueError:
                            pass
                    time.sleep(0.3)

                # Score Gemini response using Gemini
                gemini_sentiment = None
                if gemini_response:
                    raw_g, _ = _ask_gemini(
                        gemini_model,
                        SENTIMENT_PROMPT_TEMPLATE.format(text=gemini_response[:2000]),
                    )
                    if raw_g:
                        try:
                            nums = _re.findall(r'\d+(?:\.\d+)?', raw_g)
                            if nums:
                                gemini_sentiment = max(0.0, min(100.0, float(nums[0])))
                        except ValueError:
                            pass
                    time.sleep(0.3)

                scores = [s for s in [claude_sentiment, gemini_sentiment] if s is not None]
                avg_sentiment = round(sum(scores) / len(scores), 2) if scores else 50.0

                query_results.append({
                    "query": query,
                    "claude_response": claude_response,
                    "gemini_response": gemini_response,
                    "claude_sentiment": claude_sentiment,
                    "gemini_sentiment": gemini_sentiment,
                    "avg_sentiment": avg_sentiment,
                })

        except Exception as exc:
            logger.error("  [LLM by country] %s failed: %s", code, exc)

        if query_results:
            avg = round(sum(r["avg_sentiment"] for r in query_results) / len(query_results), 2)
        else:
            avg = 50.0

        logger.info("    → %s LLM: avg sentiment %.1f", code, avg)

        results[code] = {
            "queries": query_results,
            "avg_sentiment": avg,
        }

    return results
