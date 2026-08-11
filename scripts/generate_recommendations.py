from __future__ import annotations

"""
generate_recommendations.py — Claude-analyzed PR action items.

Replaces the canned, template-based action items with a genuine weekly analysis:
Claude is given THIS WEEK's actual reputation evidence (the real negative SERP
snippets, the verbatim AI-Overview concerns, low-sentiment LLM answers, the earned-
media picture, and the week-over-week CSOV move) and asked to act as iVisa's Head of
Brand Reputation & PR — producing a small set of prioritized, evidence-grounded,
specific recommendations in iVisa's voice.

Design safeguards:
  • temperature=0 → stable, reproducible output (same data ⇒ same plan).
  • Grounded ONLY in the evidence passed in; the prompt forbids invented facts.
  • Pure add-on: if Claude is unavailable or the output can't be parsed, the caller
    falls back to the existing rule-based generate_action_items(). Nothing breaks.
  • Read-only: never touches scores; produces text only.
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# How many recommendations to ask for.
_DEFAULT_N = 5
# Caps so the prompt stays focused (and cheap) even on a noisy week.
_MAX_SERP_NEG = 12
_MAX_LLM_LOW = 5
_MAX_EM_NEG = 8
_MAX_EM_POS = 4


def _ask_claude(prompt: str, max_tokens: int = 1600) -> str | None:
    """Single deterministic Claude call. Returns text or None on any failure."""
    try:
        from scripts.config import CLAUDE_API_KEY, CLAUDE_MODEL
    except Exception:
        return None
    if not CLAUDE_API_KEY:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            temperature=0,  # deterministic — same data ⇒ same recommendations
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip() if msg.content else None
    except Exception as exc:
        logger.warning("  Recommendation Claude call failed: %s", exc)
        return None


def _short(text: str, n: int = 240) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    return text[:n]


def _collect_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    """Pull the week's real signals out of the report payload into a compact,
    grounded evidence pack for the prompt."""
    comps = payload.get("components", {}) or {}

    def _score(k: str):
        v = comps.get(k)
        return v.get("score") if isinstance(v, dict) else v

    ev: dict[str, Any] = {
        "csov": payload.get("csov_score"),
        "prev_csov": payload.get("previous_csov_score"),
        "scores": {
            "serp": _score("serp"),
            "ai_overview": _score("ai_overview"),
            "llm": _score("llm"),
            "earned_media": _score("earned_media"),
        },
    }

    # ── SERP: negative results, worst (highest-ranked) first ──────────────────
    serp_neg: list[dict] = []
    for cc, kws in (payload.get("serp_data", {}) or {}).get("results", {}).items():
        for kw, rows in (kws or {}).items():
            for r in (rows or []):
                if r.get("sentiment") == "negative":
                    serp_neg.append({
                        "keyword": kw,
                        "country": cc,
                        "position": r.get("position", 99),
                        "title": _short(r.get("title", ""), 140),
                        "snippet": _short(r.get("snippet", ""), 200),
                        "domain": r.get("domain", ""),
                    })
    serp_neg.sort(key=lambda x: x["position"])
    # de-dup by (title, domain)
    seen = set(); serp_dedup = []
    for r in serp_neg:
        key = (r["title"], r["domain"])
        if key not in seen:
            seen.add(key); serp_dedup.append(r)
    ev["serp_negatives"] = serp_dedup[:_MAX_SERP_NEG]

    # ── AI Overview: aggregated negative topics + how widespread ──────────────
    topic_counts: dict[str, int] = {}
    for cc, kws in (payload.get("ai_overview_data", {}) or {}).get("results", {}).items():
        for kw, res in (kws or {}).items():
            if isinstance(res, dict):
                for t in (res.get("negative_topics", []) or []):
                    topic_counts[t] = topic_counts.get(t, 0) + 1
    ev["ai_overview_negative_topics"] = sorted(
        ({"topic": t, "appearances": c} for t, c in topic_counts.items()),
        key=lambda x: x["appearances"], reverse=True,
    )

    # ── LLM: lowest-sentiment brand answers (what Claude tells a customer) ─────
    pa = ((payload.get("llm_data", {}) or {}).get("part_a", {}) or {}).get("results", []) or []
    scored = [r for r in pa if isinstance(r.get("claude_sentiment"), (int, float))]
    scored.sort(key=lambda r: r.get("claude_sentiment", 100))
    ev["llm_low_answers"] = [{
        "query": _short(r.get("query") or r.get("prompt") or r.get("question") or "", 120),
        "sentiment": round(r.get("claude_sentiment", 0), 1),
        "answer": _short(r.get("claude_response") or r.get("response") or "", 260),
    } for r in scored[:_MAX_LLM_LOW]]

    # ── Earned media: negatives to counter + positives to amplify ─────────────
    mentions = (payload.get("earned_media", {}) or {}).get("mentions", []) or []
    ev["earned_media_negatives"] = [{
        "title": _short(m.get("title", ""), 140),
        "domain": m.get("domain", ""),
        "source": m.get("source", ""),
        "snippet": _short(m.get("snippet", ""), 180),
    } for m in mentions if m.get("sentiment") == "negative"][:_MAX_EM_NEG]
    ev["earned_media_positives"] = [{
        "title": _short(m.get("title", ""), 140),
        "domain": m.get("domain", ""),
    } for m in mentions if m.get("sentiment") == "positive"][:_MAX_EM_POS]
    ev["earned_media_counts"] = (payload.get("earned_media", {}) or {}).get(
        "counts", {"total": len(mentions)}
    )

    return ev


def _build_prompt(ev: dict[str, Any], n: int) -> str:
    delta = ""
    if isinstance(ev.get("csov"), (int, float)) and isinstance(ev.get("prev_csov"), (int, float)):
        d = ev["csov"] - ev["prev_csov"]
        delta = f" (last week {ev['prev_csov']}, change {d:+.1f})"

    return f"""You are the Head of Brand Reputation & PR at iVisa (ivisa.com), a global online \
travel-document and visa service. You are sharp, strategic and specific. Below is THIS \
WEEK's reputation data from our CSOV monitoring across 10 countries (score is 0-100; \
higher = more positive brand signals across search, Google AI Overviews, LLM answers and \
earned media).

Overall CSOV: {ev.get('csov')}{delta}
Component scores: SERP {ev['scores'].get('serp')}, AI Overview {ev['scores'].get('ai_overview')}, \
LLM {ev['scores'].get('llm')}, Earned Media {ev['scores'].get('earned_media')}

NEGATIVE SEARCH RESULTS (keyword · country · rank · outlet — headline / snippet):
{json.dumps(ev.get('serp_negatives', []), ensure_ascii=False, indent=1)}

GOOGLE AI OVERVIEW — concerns it raises about iVisa (topic · how many keywords it appeared for):
{json.dumps(ev.get('ai_overview_negative_topics', []), ensure_ascii=False, indent=1)}

WHAT CLAUDE TELLS A CUSTOMER ASKING ABOUT iVISA — lowest-sentiment answers (query · sentiment · answer):
{json.dumps(ev.get('llm_low_answers', []), ensure_ascii=False, indent=1)}

EARNED MEDIA — negative coverage to counter:
{json.dumps(ev.get('earned_media_negatives', []), ensure_ascii=False, indent=1)}
EARNED MEDIA — positive coverage we could amplify:
{json.dumps(ev.get('earned_media_positives', []), ensure_ascii=False, indent=1)}
Earned media mix this week: {json.dumps(ev.get('earned_media_counts', {}), ensure_ascii=False)}

TASK: Give the brand team the {n} most important actions to take THIS WEEK to protect and \
grow iVisa's reputation and brand-driven bookings.

RULES:
- Ground EVERY recommendation in the SPECIFIC evidence above — name the actual keyword, \
outlet, AI-Overview concern, country or headline it responds to. If the data does not \
support a point, do not make it.
- Do NOT invent facts, statistics, partnerships, or sources. Only reason from what is above.
- Prioritise by impact on trust and on brand-driven bookings. Lead with the biggest risk or \
the biggest opportunity.
- Be concrete: name the exact asset to create or page to fix, the specific narrative to \
counter, or the exact outlet/story to pitch or amplify. No generic advice like "engage \
journalists" or "publish more content".
- iVisa brand voice: approachable, reliable, straightforward. Sentence case, contractions ok.

Return ONLY a JSON array of exactly {n} objects, each with these keys:
  "priority": one of "High","Medium","Low"
  "focus": a short 2-4 word label
  "insight": one sentence stating what the data shows, citing the specific evidence
  "action": one or two sentences with the concrete move
No text before or after the JSON array."""


def _parse_items(raw: str) -> list[str]:
    """Parse Claude's JSON array into display-ready recommendation strings."""
    if not raw:
        return []
    # Extract the JSON array (tolerate code fences / stray prose).
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        data = json.loads(raw[start:end + 1])
    except Exception:
        return []
    items: list[str] = []
    for obj in data:
        if not isinstance(obj, dict):
            continue
        pr = str(obj.get("priority", "")).strip().title() or "Medium"
        focus = str(obj.get("focus", "")).strip()
        insight = str(obj.get("insight", "")).strip()
        action = str(obj.get("action", "")).strip()
        if not (insight or action):
            continue
        head = f"[{pr}] {focus}".strip()
        parts = [p for p in (insight, f"Action: {action}" if action else "") if p]
        items.append(f"{head} — " + " ".join(parts))
    return items


def generate_smart_action_items(payload: dict[str, Any], n: int = _DEFAULT_N) -> list[str] | None:
    """Return a list of Claude-analyzed, evidence-grounded PR recommendations, or
    None if Claude is unavailable / the output can't be parsed (caller then falls
    back to the rule-based generate_action_items)."""
    try:
        ev = _collect_evidence(payload)
        prompt = _build_prompt(ev, n)
        raw = _ask_claude(prompt)
        items = _parse_items(raw or "")
        return items or None
    except Exception as exc:
        logger.warning("  Smart recommendations unavailable (%s) — falling back.", exc)
        return None
