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
)

logger = logging.getLogger(__name__)


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
    """Return a google.genai Client, or None if unavailable."""
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

def _ask_claude(client, prompt: str, max_tokens: int = 500) -> str | None:
    """Send a prompt to Claude. Returns text or None on failure."""
    if client is None:
        return None
    try:
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as exc:
        logger.warning("Claude query failed: %s", exc)
        return None


def _ask_gemini(client, prompt: str) -> str | None:
    """Send a prompt to Gemini via google.genai Client. Returns text or None."""
    if client is None:
        return None
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text.strip()
    except Exception as exc:
        logger.warning("Gemini query failed: %s", exc)
        return None


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
        raw = _ask_gemini(gemini_model, prompt)
        if raw:
            try:
                # Gemini sometimes wraps the number in prose — extract first number
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
        gemini_response = _ask_gemini(gemini_model, query)
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
            raw = _ask_gemini(gemini_model, SENTIMENT_PROMPT_TEMPLATE.format(text=gemini_response[:2000]))
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
        gemini_response = _ask_gemini(gemini_model, query)
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
            raw = _ask_gemini(gemini_model, SENTIMENT_PROMPT_TEMPLATE.format(text=gemini_response[:2000]))
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
            "claude_mentions_ivisa": claude_mentions,
            "gemini_mentions_ivisa": gemini_mentions,
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
