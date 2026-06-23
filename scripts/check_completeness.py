from __future__ import annotations

"""
check_completeness.py — Data completeness / degradation gate.

The pipeline is built to "fail gracefully": if an API errors or hits a quota,
the affected component silently falls back to a default score (LLM→50,
earned media→60, AI Overview→50) and the report still renders. That is what
lets a hollow report ship looking normal — e.g. Gemini quota + a Claude hiccup
leaving the LLM score as a meaningless default.

This module inspects the assembled report payload and reports, per component,
whether the data is OK, PARTIAL (degraded but usable), or MISSING (no real
signal — the score is a hollow default). main.py logs this every run, refuses
to send Slack when a core component is MISSING, and exits non-zero so the
Monday automation fails loudly instead of publishing a hollow report.
"""

from typing import Any

# Number of brand queries we expect the LLM step to score (config.BRAND_QUERIES)
_EXPECTED_BRAND_QUERIES = 20


def assess_completeness(payload: dict[str, Any]) -> dict[str, Any]:
    """Return {"components": {...}, "errors": [...], "warnings": [...], "ok": bool}.

    status per component: "ok" | "partial" | "low" | "missing".
    errors  → MISSING core data (should block publish).
    warnings→ degraded-but-usable (note, don't block).
    ok      → True when there are no errors.
    """
    components: dict[str, dict] = {}
    errors: list[str] = []
    warnings: list[str] = []

    # ── SERP ──────────────────────────────────────────────────────────────────
    serp = payload.get("serp_data", {}) or {}
    results = serp.get("results", {}) or {}
    total = covered = 0
    for _cc, kws in results.items():
        for _kw, rows in (kws or {}).items():
            total += 1
            if rows:
                covered += 1
    if total == 0 or covered == 0:
        components["serp"] = {"status": "missing", "detail": "no SERP results for any keyword/country"}
        errors.append("SERP: no results at all — SEMrush/Ahrefs/SerpAPI all returned nothing")
    elif covered / total < 0.5:
        components["serp"] = {"status": "partial", "detail": f"{covered}/{total} keyword-country combos have results"}
        warnings.append(f"SERP: only {covered}/{total} keyword-country combos returned results")
    else:
        components["serp"] = {"status": "ok", "detail": f"{covered}/{total} keyword-country combos have results"}

    # ── LLM (the silent-default risk) ───────────────────────────────────────────
    llm = payload.get("llm_data", {}) or {}
    pa = ((llm.get("part_a", {}) or {}).get("results", []) or [])
    claude_ans = sum(1 for r in pa if r.get("claude_sentiment") is not None)
    gemini_ans = sum(1 for r in pa if r.get("gemini_sentiment") is not None)
    both_none = sum(1 for r in pa if r.get("claude_sentiment") is None and r.get("gemini_sentiment") is None)

    try:
        from scripts.config import USE_GEMINI as _USE_GEMINI
    except Exception:
        _USE_GEMINI = True

    if not _USE_GEMINI:
        # Claude-only by design — Gemini absence is expected, not a degradation.
        if not pa or claude_ans == 0:
            components["llm"] = {"status": "missing",
                                 "detail": "Claude produced no brand-query sentiment — LLM score is a hollow default"}
            errors.append("LLM: Claude produced no sentiment (Gemini is disabled) — the LLM score is a meaningless default (50)")
        else:
            components["llm"] = {"status": "ok",
                                 "detail": f"Claude-only (Gemini disabled): {claude_ans}/{len(pa)} brand queries scored"}
    elif not pa or (claude_ans == 0 and gemini_ans == 0):
        components["llm"] = {"status": "missing",
                             "detail": "no brand-query sentiment from either Claude or Gemini — LLM score is a hollow default"}
        errors.append("LLM: neither Claude nor Gemini produced any sentiment — the LLM score is a meaningless default (50)")
    elif claude_ans == 0 or gemini_ans == 0:
        down = "Gemini" if gemini_ans == 0 else "Claude"
        up = "Claude" if down == "Gemini" else "Gemini"
        up_n = claude_ans if up == "Claude" else gemini_ans
        components["llm"] = {"status": "partial",
                             "detail": f"{down} returned nothing (quota/error); {up} scored {up_n}/{len(pa)} brand queries"}
        warnings.append(f"LLM: {down} produced no data (quota/error) — running on {up} only ({up_n}/{len(pa)} queries scored)")
    else:
        components["llm"] = {"status": "ok",
                             "detail": f"Claude {claude_ans}/{len(pa)} + Gemini {gemini_ans}/{len(pa)} brand queries scored"}

    # Even if not fully missing: flag if many queries defaulted to 50 (both models blank)
    if pa and components["llm"]["status"] != "missing" and both_none / len(pa) > 0.30:
        warnings.append(f"LLM: {both_none}/{len(pa)} brand queries were scored by NEITHER model (defaulted to 50)")
    if pa and len(pa) < _EXPECTED_BRAND_QUERIES:
        warnings.append(f"LLM: only {len(pa)}/{_EXPECTED_BRAND_QUERIES} brand queries ran")

    # ── AI Overview ─────────────────────────────────────────────────────────────
    aio = payload.get("ai_overview_data", {}) or {}
    ares = aio.get("results", {}) or {}
    a_total = a_appeared = 0
    for _cc, kws in ares.items():
        for _kw, r in (kws or {}).items():
            a_total += 1
            if isinstance(r, dict) and r.get("has_ai_overview"):
                a_appeared += 1
    if a_total == 0:
        components["ai_overview"] = {"status": "missing", "detail": "no AI Overview data fetched (SerpAPI may be down)"}
        errors.append("AI Overview: no data fetched — SerpAPI may have failed")
    else:
        # Absence of overviews is acceptable (neutral baseline) — informational only.
        components["ai_overview"] = {"status": "ok", "detail": f"{a_appeared}/{a_total} keywords showed an AI Overview"}

    # ── Earned Media ────────────────────────────────────────────────────────────
    em = payload.get("earned_media", {}) or {}
    mentions = em.get("mentions", []) or []
    if len(mentions) == 0:
        components["earned_media"] = {"status": "low", "detail": "0 mentions found — score is the default baseline"}
        warnings.append("Earned Media: 0 mentions found — score is the default baseline (not necessarily an error, but verify)")
    else:
        components["earned_media"] = {"status": "ok", "detail": f"{len(mentions)} mentions"}

    return {
        "components": components,
        "errors": errors,
        "warnings": warnings,
        "ok": len(errors) == 0,
    }


def _is_num_0_100(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 100


def validate_payload_shape(payload: dict[str, Any]) -> list[str]:
    """Return a list of structural problems in the report payload (empty = OK).

    Guards against the "None where a number was expected" class (which once
    produced an empty report) and any malformed score before it reaches the page.
    """
    errs: list[str] = []
    if not _is_num_0_100(payload.get("csov_score")):
        errs.append(f"csov_score is not a 0–100 number: {payload.get('csov_score')!r}")

    comps = payload.get("components", {}) or {}
    for k in ("serp", "ai_overview", "llm", "earned_media"):
        v = comps.get(k)
        score = v.get("score") if isinstance(v, dict) else v
        if not _is_num_0_100(score):
            errs.append(f"component '{k}' score is not a 0–100 number: {score!r}")

    cd = payload.get("country_data", {}) or {}
    if not cd:
        errs.append("country_data is empty")
    for code, info in cd.items():
        if not _is_num_0_100((info or {}).get("csov_score")):
            errs.append(f"country '{code}' csov_score is not a 0–100 number: {(info or {}).get('csov_score')!r}")

    for key in ("serp_data", "ai_overview_data", "llm_data", "earned_media"):
        if key not in payload:
            errs.append(f"missing top-level key: {key}")

    return errs


def score_sanity(payload: dict[str, Any], prev_csov: float | None, max_jump: float = 15.0) -> list[str]:
    """Return warnings for implausible score movement (a silent scoring/classifier
    bug usually shows up as an unusually large week-over-week swing)."""
    warns: list[str] = []
    cs = payload.get("csov_score")
    if isinstance(cs, (int, float)) and isinstance(prev_csov, (int, float)):
        if abs(cs - prev_csov) > max_jump:
            warns.append(
                f"CSOV moved {cs - prev_csov:+.1f} vs last run ({prev_csov} → {cs}) — "
                f"larger than ±{max_jump:.0f}; verify it's a real change, not a data/classifier bug."
            )
    return warns


def format_completeness(assessment: dict[str, Any]) -> str:
    """Human-readable multi-line summary for the run log."""
    icon = {"ok": "✅", "partial": "⚠️", "low": "⚠️", "missing": "⛔"}
    lines = ["", "=" * 60, "DATA COMPLETENESS CHECK", "=" * 60]
    for name, info in assessment["components"].items():
        lines.append(f"  {icon.get(info['status'], '?')} {name:<13} [{info['status'].upper()}] — {info['detail']}")
    if assessment["warnings"]:
        lines.append("  warnings:")
        lines += [f"    • {w}" for w in assessment["warnings"]]
    if assessment["errors"]:
        lines.append("  ERRORS (missing data — do NOT publish):")
        lines += [f"    ⛔ {e}" for e in assessment["errors"]]
    lines.append("=" * 60)
    return "\n".join(lines)
