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
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip() if msg.content else None
    except Exception as exc:
        logger.warning("  Recommendation Claude call failed: %s", exc)
        return None


def _short(text: str, n: int = 240) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    return text[:n]


def _domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace("www.", "").lower()
    except Exception:
        return ""


def _collect_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    """Pull the week's real signals — negative AND positive, across all four
    channels — into a compact, grounded evidence pack for the prompt."""
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

    # ── SERP: negatives to fix (worst-ranked first) + positives to protect ────
    serp_neg: list[dict] = []
    serp_pos: list[dict] = []
    n_pos = n_neg = 0
    for cc, kws in (payload.get("serp_data", {}) or {}).get("results", {}).items():
        for kw, rows in (kws or {}).items():
            for r in (rows or []):
                sent = r.get("sentiment")
                if sent == "negative":
                    n_neg += 1
                    serp_neg.append({
                        "keyword": kw, "country": cc, "position": r.get("position", 99),
                        "title": _short(r.get("title", ""), 140),
                        "snippet": _short(r.get("snippet", ""), 200),
                        "domain": r.get("domain", ""),
                    })
                elif sent == "positive":
                    n_pos += 1
                    if r.get("position", 99) <= 5:
                        serp_pos.append({
                            "keyword": kw, "position": r.get("position", 99),
                            "title": _short(r.get("title", ""), 120),
                            "domain": r.get("domain", ""),
                        })

    def _dedup(rows, keyfn, cap):
        seen = set(); out = []
        for r in rows:
            k = keyfn(r)
            if k not in seen:
                seen.add(k); out.append(r)
            if len(out) >= cap:
                break
        return out

    serp_neg.sort(key=lambda x: x["position"])
    serp_pos.sort(key=lambda x: x["position"])
    ev["serp_negatives"] = _dedup(serp_neg, lambda r: (r["title"], r["domain"]), _MAX_SERP_NEG)
    ev["serp_positives"] = _dedup(serp_pos, lambda r: (r["title"], r["domain"]), 6)
    ev["serp_balance"] = {"positive": n_pos, "negative": n_neg}

    # ── AI Overview: MENTIONS + what it says + sources it cites + concerns ─────
    aio_results = (payload.get("ai_overview_data", {}) or {}).get("results", {}) or {}
    slots = with_ov = cited = 0
    topic_counts: dict[str, int] = {}
    src_domains: dict[str, int] = {}
    examples: list[dict] = []
    uncited: list[str] = []
    for cc, kws in aio_results.items():
        for kw, res in (kws or {}).items():
            if not isinstance(res, dict):
                continue
            slots += 1
            if not res.get("has_ai_overview"):
                continue
            with_ov += 1
            is_cited = bool(res.get("ivisa_cited"))
            if is_cited:
                cited += 1
            elif kw not in uncited:
                uncited.append(kw)
            for t in (res.get("negative_topics", []) or []):
                topic_counts[t] = topic_counts.get(t, 0) + 1
            for s in (res.get("sources", []) or []):
                d = _domain(s)
                if d:
                    src_domains[d] = src_domains.get(d, 0) + 1
            examples.append({
                "keyword": kw, "country": cc, "ivisa_cited": is_cited,
                "sentiment": res.get("sentiment_score") or res.get("score"),
                "text": _short(res.get("ai_overview_text", ""), 260),
                "sources": [_domain(s) for s in (res.get("sources", []) or [])][:3],
            })
    # keep a spread of examples: lowest + highest sentiment (what it says, good & bad)
    examples.sort(key=lambda e: (e["sentiment"] if isinstance(e["sentiment"], (int, float)) else 50))
    aio_examples = examples[:3] + examples[-2:] if len(examples) > 5 else examples
    ev["ai_overview"] = {
        "coverage": {"keyword_slots": slots, "with_overview": with_ov, "ivisa_cited": cited},
        "negative_topics": sorted(
            ({"topic": t, "appearances": c} for t, c in topic_counts.items()),
            key=lambda x: x["appearances"], reverse=True),
        "top_cited_sources": sorted(
            ({"domain": d, "times_cited": c} for d, c in src_domains.items()),
            key=lambda x: x["times_cited"], reverse=True)[:8],
        "examples": aio_examples,
        "keywords_overview_but_ivisa_not_cited": uncited[:8],
    }

    # ── LLM: lowest AND highest-sentiment brand answers ───────────────────────
    pa = ((payload.get("llm_data", {}) or {}).get("part_a", {}) or {}).get("results", []) or []
    scored = [r for r in pa if isinstance(r.get("claude_sentiment"), (int, float))]
    scored.sort(key=lambda r: r.get("claude_sentiment", 100))

    def _llm_row(r):
        return {
            "query": _short(r.get("query") or r.get("prompt") or r.get("question") or "", 120),
            "sentiment": round(r.get("claude_sentiment", 0), 1),
            "answer": _short(r.get("claude_response") or r.get("response") or "", 260),
        }

    ev["llm_low_answers"] = [_llm_row(r) for r in scored[:_MAX_LLM_LOW]]
    ev["llm_best_answers"] = [_llm_row(r) for r in scored[-2:]] if len(scored) > _MAX_LLM_LOW else []
    pb = (payload.get("llm_data", {}) or {}).get("part_b", {}) or {}
    ev["llm_mention_rate"] = pb.get("mention_rate")

    # ── Earned media: negatives to counter + positives to amplify + mix ───────
    mentions = (payload.get("earned_media", {}) or {}).get("mentions", []) or []
    ev["earned_media_negatives"] = [{
        "title": _short(m.get("title", ""), 140), "domain": m.get("domain", ""),
        "source": m.get("source", ""), "snippet": _short(m.get("snippet", ""), 180),
    } for m in mentions if m.get("sentiment") == "negative"][:_MAX_EM_NEG]
    ev["earned_media_positives"] = [{
        "title": _short(m.get("title", ""), 140), "domain": m.get("domain", ""),
        "source": m.get("source", ""),
    } for m in mentions if m.get("sentiment") == "positive"][:_MAX_EM_POS]
    ev["earned_media_counts"] = (payload.get("earned_media", {}) or {}).get(
        "counts", {"total": len(mentions)})

    return ev


def _build_prompt(ev: dict[str, Any], n: int) -> str:
    delta = ""
    if isinstance(ev.get("csov"), (int, float)) and isinstance(ev.get("prev_csov"), (int, float)):
        d = ev["csov"] - ev["prev_csov"]
        delta = f" (last week {ev['prev_csov']}, change {d:+.1f})"

    aio = ev.get("ai_overview", {}) or {}
    cov = aio.get("coverage", {}) or {}

    return f"""You are the Head of Brand Reputation & PR at iVisa (ivisa.com), a global online \
travel-document and visa service. You are sharp, strategic and specific. Below is THIS \
WEEK's reputation data from our CSOV monitoring across 10 countries (score is 0-100; \
higher = more positive brand signals across search, Google AI Overviews, LLM answers and \
earned media). The data covers BOTH problems to fix and strengths to build on.

Overall CSOV: {ev.get('csov')}{delta}
Component scores: SERP {ev['scores'].get('serp')}, AI Overview {ev['scores'].get('ai_overview')}, \
LLM {ev['scores'].get('llm')}, Earned Media {ev['scores'].get('earned_media')}

── SEARCH RESULTS ──
Overall sentiment mix (top-10 results across all keywords/countries): {json.dumps(ev.get('serp_balance', {}), ensure_ascii=False)}
Negative results to fix (keyword · country · rank · outlet — headline / snippet):
{json.dumps(ev.get('serp_negatives', []), ensure_ascii=False, indent=1)}
Strong positive results ranking high we could protect/amplify:
{json.dumps(ev.get('serp_positives', []), ensure_ascii=False, indent=1)}

── GOOGLE AI OVERVIEW (does the AI mention iVisa, what does it say, what does it cite) ──
Coverage: of {cov.get('keyword_slots')} keyword slots, {cov.get('with_overview')} showed an AI Overview and iVisa was CITED in {cov.get('ivisa_cited')} of them.
Concerns the overview raises (topic · # keywords): {json.dumps(aio.get('negative_topics', []), ensure_ascii=False)}
Sources Google's AI cites most when describing iVisa (domain · times): {json.dumps(aio.get('top_cited_sources', []), ensure_ascii=False)}
Keywords that show an overview but do NOT cite iVisa (a visibility gap): {json.dumps(aio.get('keywords_overview_but_ivisa_not_cited', []), ensure_ascii=False)}
Verbatim overview examples (what the AI actually says — keyword · cited? · sentiment · text · its sources):
{json.dumps(aio.get('examples', []), ensure_ascii=False, indent=1)}

── LLM ANSWERS (what Claude tells a customer who asks about iVisa) ──
Brand-mention rate in general answers: {ev.get('llm_mention_rate')}
Lowest-sentiment answers (query · sentiment · answer):
{json.dumps(ev.get('llm_low_answers', []), ensure_ascii=False, indent=1)}
Most positive answers (to reinforce):
{json.dumps(ev.get('llm_best_answers', []), ensure_ascii=False, indent=1)}

── EARNED MEDIA ──
Mix this week: {json.dumps(ev.get('earned_media_counts', {}), ensure_ascii=False)}
Negative coverage to counter:
{json.dumps(ev.get('earned_media_negatives', []), ensure_ascii=False, indent=1)}
Positive coverage to amplify:
{json.dumps(ev.get('earned_media_positives', []), ensure_ascii=False, indent=1)}

TASK: Give the brand team the {n} most important actions to take THIS WEEK to protect and \
grow iVisa's reputation and brand-driven bookings.

RULES:
- Consider ALL FOUR channels (search, AI Overview, LLM answers, earned media) and balance \
DEFENSE (counter/fix what's negative) with OFFENSE (amplify and build on what's already \
positive). Not every action should be about a problem.
- For AI Overview specifically, reason about what the overview actually says, whether iVisa \
is cited, the visibility gaps (overviews that don't cite iVisa), and the SOURCES Google's AI \
pulls from — influencing those sources (e.g. the Reddit/review/editorial pages it cites) is \
a concrete lever.
- Ground EVERY recommendation in the SPECIFIC evidence above — name the actual keyword, \
outlet, AI-Overview concern or source, country, or headline it responds to. If the data does \
not support a point, do not make it.
- Do NOT invent facts, statistics, partnerships, or sources. Only reason from what is above.
- Prioritise by impact on trust and on brand-driven bookings. Lead with the biggest risk OR \
the biggest opportunity.
- Be concrete: name the exact asset to create or page to fix, the specific narrative to \
counter, the exact source to influence, or the exact story/outlet to pitch or amplify. No \
generic advice like "engage journalists" or "publish more content".
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
