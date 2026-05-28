"""
calculate_csov.py — Combines all component scores into the final CSOV score.

CSOV = (SERP × 0.35) + (AI_Overview × 0.25) + (LLM × 0.25) + (Earned_Media × 0.15)

Also reads earned media data from data/earned_media.json.
"""

import json
import logging
from typing import Any

from scripts.config import (
    DEFAULT_EARNED_MEDIA_SCORE,
    EARNED_MEDIA_FILE,
    WEIGHT_AI_OVERVIEW,
    WEIGHT_EARNED_MEDIA,
    WEIGHT_LLM,
    WEIGHT_SERP,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Earned Media
# ---------------------------------------------------------------------------

def load_earned_media() -> dict[str, Any]:
    """
    Load earned media data from data/earned_media.json.
    Returns default score of 60 if file is missing or malformed.
    """
    try:
        if not EARNED_MEDIA_FILE.exists():
            logger.warning("earned_media.json not found — using default score %d.", DEFAULT_EARNED_MEDIA_SCORE)
            return {"score": DEFAULT_EARNED_MEDIA_SCORE, "mentions": []}

        with open(EARNED_MEDIA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        score = float(data.get("score", DEFAULT_EARNED_MEDIA_SCORE))
        score = max(0.0, min(100.0, score))
        logger.info("  Earned Media Score loaded: %.1f", score)
        return {
            "score": score,
            "mentions": data.get("mentions", []),
            "raw": data,
        }

    except (json.JSONDecodeError, ValueError, OSError) as exc:
        logger.error("Failed to load earned_media.json: %s — using default.", exc)
        return {"score": DEFAULT_EARNED_MEDIA_SCORE, "mentions": []}


# ---------------------------------------------------------------------------
# CSOV Calculation
# ---------------------------------------------------------------------------

def calculate_csov(
    serp_score: float,
    ai_overview_score: float,
    llm_score: float,
    earned_media_score: float,
) -> dict[str, Any]:
    """
    Apply the CSOV formula and return a detailed breakdown dict.
    """
    components = {
        "serp": {
            "score": round(serp_score, 2),
            "weight": WEIGHT_SERP,
            "weighted_contribution": round(serp_score * WEIGHT_SERP, 2),
            "label": "SERP Score",
        },
        "ai_overview": {
            "score": round(ai_overview_score, 2),
            "weight": WEIGHT_AI_OVERVIEW,
            "weighted_contribution": round(ai_overview_score * WEIGHT_AI_OVERVIEW, 2),
            "label": "AI Overview Score",
        },
        "llm": {
            "score": round(llm_score, 2),
            "weight": WEIGHT_LLM,
            "weighted_contribution": round(llm_score * WEIGHT_LLM, 2),
            "label": "LLM Score",
        },
        "earned_media": {
            "score": round(earned_media_score, 2),
            "weight": WEIGHT_EARNED_MEDIA,
            "weighted_contribution": round(earned_media_score * WEIGHT_EARNED_MEDIA, 2),
            "label": "Earned Media Score",
        },
    }

    csov = sum(c["weighted_contribution"] for c in components.values())
    csov = round(csov, 2)

    logger.info(
        "  CSOV = SERP(%.1f×%.2f) + AIO(%.1f×%.2f) + LLM(%.1f×%.2f) + EM(%.1f×%.2f) = %.2f",
        serp_score, WEIGHT_SERP,
        ai_overview_score, WEIGHT_AI_OVERVIEW,
        llm_score, WEIGHT_LLM,
        earned_media_score, WEIGHT_EARNED_MEDIA,
        csov,
    )

    return {
        "csov_score": csov,
        "components": components,
        "formula": "CSOV = (SERP × 0.35) + (AI_Overview × 0.25) + (LLM × 0.25) + (Earned_Media × 0.15)",
    }


# ---------------------------------------------------------------------------
# Action Items Generator
# ---------------------------------------------------------------------------

def generate_action_items(components: dict[str, dict], serp_data: dict, ai_data: dict) -> list[str]:
    """
    Auto-generate action items based on lowest-scoring components and specifics.

    SERP logic: score reflects sentiment of all top-10 results per keyword
    (positive/neutral/negative), not iVisa's own ranking position.
    """
    actions = []
    scores = {k: v["score"] for k, v in components.items()}

    # ── SERP-based actions ────────────────────────────────────────────────────
    if serp_data and serp_data.get("results"):
        # Collect keywords with negative results in top positions
        negative_kw: dict[str, int] = {}   # keyword → count of negative results
        high_risk_kw: list[str] = []        # keyword with negative result at pos 1-3

        for country_results in serp_data["results"].values():
            for kw, results in country_results.items():
                for r in results:
                    if r.get("sentiment") == "negative":
                        negative_kw[kw] = negative_kw.get(kw, 0) + 1
                        if r.get("position", 99) <= 3:
                            if kw not in high_risk_kw:
                                high_risk_kw.append(kw)

        total_negatives = sum(negative_kw.values())

        if high_risk_kw:
            kw_list = ", ".join(high_risk_kw[:3])
            actions.append(
                f"High-priority SERP risk: negative results appearing in top 3 positions for "
                f"'{kw_list}' — publish positive, authoritative content to push these down."
            )
        elif total_negatives > 5:
            top_kw = sorted(negative_kw, key=lambda k: negative_kw[k], reverse=True)[:3]
            actions.append(
                f"Address {total_negatives} negative SERP appearances — most frequent for: "
                f"{', '.join(top_kw)}. Respond on review sites and strengthen positive content."
            )

    if scores["serp"] < 50:
        actions.append(
            "SERP landscape is mostly negative — prioritize content that ranks positively for "
            "reputation keywords ('is iVisa legit', 'iVisa reviews', 'is iVisa safe')."
        )
    elif scores["serp"] < 70:
        actions.append(
            "Strengthen SERP sentiment by building more positive third-party mentions: "
            "travel blogs, review aggregators, and press coverage referencing iVisa positively."
        )

    # ── AI Overview actions ───────────────────────────────────────────────────
    if scores["ai_overview"] < 50:
        actions.append(
            "Create more AI-citable content — structured FAQs and authoritative pages about iVisa's legitimacy and safety."
        )
        uncited = []
        if ai_data and ai_data.get("results"):
            for country_results in ai_data["results"].values():
                for kw, result in country_results.items():
                    if result.get("has_ai_overview") and not result.get("ivisa_cited"):
                        uncited.append(kw)
            if uncited:
                top_uncited = list(set(uncited))[:3]
                actions.append(
                    f"Optimize content for AI citation on: {', '.join(top_uncited)}."
                )
    elif scores["ai_overview"] < 70:
        actions.append(
            "Add FAQ schema and HowTo schema to key trust pages to help Google pull iVisa into AI Overviews."
        )

    # ── LLM actions ───────────────────────────────────────────────────────────
    if scores["llm"] < 50:
        actions.append(
            "Increase iVisa brand presence in LLM training signals: publish more third-party reviews, press coverage, and expert endorsements."
        )
    elif scores["llm"] < 70:
        actions.append(
            "Submit iVisa info to trusted review aggregators and travel publications to improve LLM mention rate."
        )

    # ── Earned media actions ──────────────────────────────────────────────────
    if scores["earned_media"] < 50:
        actions.append(
            "Launch a proactive PR campaign targeting travel media and review platforms to build earned media volume."
        )
    elif scores["earned_media"] < 70:
        actions.append(
            "Engage proactively with travel journalists and bloggers — target Forbes Travel, Skift, and TravelPulse for iVisa features."
        )

    if not actions:
        actions.append("All scores are healthy — maintain current SEO, PR, and content strategy.")

    return actions
