from __future__ import annotations

"""
main.py — iVisa CSOV Weekly Reputation Dashboard
Entry point for the weekly report pipeline.

Usage:
  python main.py            # Live run (requires all API keys) — no Slack
  python main.py --slack    # Live run + send Slack notification
  python main.py --dry-run  # Load sample data, skip all API calls
"""

import argparse
import json
import logging
import pathlib
import sys
from datetime import date, datetime

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


SCORING_VERSION = "1.0"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_previous_csov(historical_dir: pathlib.Path) -> float | None:
    """Load the most recent historical CSOV score for MoM comparison."""
    try:
        files = sorted(historical_dir.glob("*.json"), reverse=True)
        if not files:
            return None
        with open(files[0], "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("csov_score")
    except Exception as exc:
        logger.warning("Could not load previous CSOV: %s", exc)
        return None


def _save_historical(data: dict, historical_dir: pathlib.Path, run_date: date) -> None:
    """Save today's report data as a historical snapshot."""
    fname = historical_dir / f"{run_date.isoformat()}.json"
    try:
        with open(fname, "w", encoding="utf-8") as f:
            # Use default=str only for non-serialisable types (date, Path, etc.)
            # but never convert None → "None" (that breaks Gemini/LLM display)
            def _json_default(obj):
                import datetime
                if isinstance(obj, (datetime.date, datetime.datetime)):
                    return obj.isoformat()
                return str(obj)
            json.dump(data, f, ensure_ascii=False, indent=2, default=_json_default)
        logger.info("  Historical snapshot saved: %s", fname)
    except OSError as exc:
        logger.error("  Could not save historical data: %s", exc)


def _check_render(html_path: str) -> str | None:
    """Headless-render the generated report and return a problem string if the page
    failed to populate (a RUNTIME JS error — the kind that makes it hang on
    'Loading…'), else None. Best-effort: returns None (skip) if node / puppeteer /
    the script aren't available, so it never blocks a local run that lacks the tool."""
    import shutil, subprocess, os
    if not os.path.exists(html_path):
        return "generated report file not found"
    node = shutil.which("node")
    script = pathlib.Path(__file__).parent / "scripts" / "check_render.js"
    if not node or not script.exists():
        logger.info("  Render check skipped (node or check_render.js unavailable).")
        return None
    try:
        proc = subprocess.run([node, str(script), html_path],
                              capture_output=True, text=True, timeout=120)
    except Exception as exc:
        logger.warning("  Render check could not run (%s) — skipping.", exc)
        return None
    if proc.returncode == 0:
        logger.info("  ✓ %s", (proc.stdout.strip().splitlines() or ["render OK"])[-1])
        return None
    if proc.returncode == 2:  # puppeteer/usage unavailable → best-effort skip
        logger.info("  Render check skipped (%s).", (proc.stderr.strip() or "tooling unavailable"))
        return None
    return "; ".join((proc.stderr.strip().splitlines() or ["page did not populate"])[:3])


def _build_report_payload(
    serp_data: dict,
    ai_overview_data: dict,
    llm_data: dict,
    earned_media_data: dict,
    csov_result: dict,
    action_items: list[str],
    action_items_by_tab: dict,
    previous_csov: float | None,
    country_configs: dict,
    earned_media_by_country: dict | None = None,
    llm_by_country: dict | None = None,
) -> dict:
    """Assemble all data into the shape expected by generate_report."""
    # Build country_data for the country grid + component breakdown
    country_data = {}
    for code, config in country_configs.items():
        country_data[code] = {
            "name":       config["name"],
            "flag":       config["flag"],
            "weight":     config["weight"],
            "csov_score": round(
                (serp_data["country_scores"].get(code, 0)         * 0.35) +
                (ai_overview_data["country_scores"].get(code, 0)  * 0.25) +
                (llm_data.get("global_score", 0)                  * 0.25) +
                (earned_media_data.get("score", 60)               * 0.15),
                2,
            ),
            "components": {
                "serp":         serp_data["country_scores"].get(code, 0),
                "ai_overview":  ai_overview_data["country_scores"].get(code, 0),
                "llm":          llm_data.get("global_score", 0),
                "earned_media": earned_media_data.get("score", 60),
            },
        }

    # Add prev_score to component cards
    components = dict(csov_result["components"])
    # We don't have per-component history, so leave prev_score absent
    # (JS will hide the badge if it's null)

    # Build historical (last 8 weeks from historical dir if available,
    # otherwise just the current week as a single point)
    from scripts.config import HISTORICAL_DIR, TREND_CHART_START_DATE
    history = []
    try:
        from datetime import timedelta
        _today = date.today()
        monday = _today - timedelta(days=_today.weekday())
        sunday = monday + timedelta(days=6)
        current_week_label = f"{monday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')}"

        hfiles = sorted(HISTORICAL_DIR.glob("*.json"))
        # Trend starts at the first legit final-version run (TREND_CHART_START_DATE).
        # Pre-cutoff snapshots (backfilled Jan–May, June test runs) stay on disk for
        # reference but are NOT plotted — that early data isn't reliable.
        seen_labels: dict = {}
        for hf in hfiles:
            if hf.stem < TREND_CHART_START_DATE:
                continue
            with open(hf, "r", encoding="utf-8") as f:
                hd = json.load(f)
            label = hd.get("week_label", hf.stem)
            seen_labels[label] = {
                "week_label":   label,
                "csov":         hd.get("csov_score", 0),
                "serp":         hd.get("components", {}).get("serp", {}).get("score", 0),
                "ai_overview":  hd.get("components", {}).get("ai_overview", {}).get("score", 0),
                "llm":          hd.get("components", {}).get("llm", {}).get("score", 0),
                "earned_media": hd.get("components", {}).get("earned_media", {}).get("score", 0),
            }

        # Always overwrite the current week with live scores so a prior broken run
        # can never poison the chart — but only if this week is on/after the cutoff.
        if monday.isoformat() >= TREND_CHART_START_DATE:
            seen_labels[current_week_label] = {
                "week_label":   current_week_label,
                "csov":         csov_result.get("csov_score", 0),
                "serp":         csov_result.get("components", {}).get("serp", {}).get("score", 0),
                "ai_overview":  csov_result.get("components", {}).get("ai_overview", {}).get("score", 0),
                "llm":          csov_result.get("components", {}).get("llm", {}).get("score", 0),
                "earned_media": csov_result.get("components", {}).get("earned_media", {}).get("score", 0),
            }

        history = list(seen_labels.values())[-8:]
    except Exception as exc:
        logger.warning("Could not load historical series: %s", exc)

    # Load Period 1 baseline if available
    period1_baseline = None
    try:
        from scripts.config import DATA_DIR
        p1_path = DATA_DIR / "period1_baseline.json"
        if p1_path.exists():
            with open(p1_path, "r", encoding="utf-8") as f:
                period1_baseline = json.load(f)
    except Exception:
        pass

    return {
        "csov_score":               csov_result["csov_score"],
        "previous_csov_score":      previous_csov,
        "components":               components,
        "country_data":             country_data,
        "serp_data":                serp_data,
        "ai_overview_data":         ai_overview_data,
        "llm_data":                 llm_data,
        "earned_media":             earned_media_data,
        "earned_media_by_country":  earned_media_by_country or {},
        "llm_by_country":           llm_by_country or {},
        "historical":               history,
        "action_items":             action_items,
        "action_items_by_tab":      action_items_by_tab,
        "formula":                  csov_result.get("formula", ""),
        "period1_baseline":         period1_baseline,
        "scoring_version":          SCORING_VERSION,
    }


# ── Main Pipeline ─────────────────────────────────────────────────────────────

def run(dry_run: bool = False, send_slack: bool = False, force: bool = False) -> None:
    from scripts.config import (
        COUNTRIES,
        DATA_DIR,
        DOCS_DIR,
        HISTORICAL_DIR,
        SAMPLE_DATA_FILE,
    )

    run_date   = date.today()
    date_str   = run_date.isoformat()

    # ── Idempotency guard ─────────────────────────────────────────────────────
    # Prevents duplicate Slack messages when GitHub's cron fires late AND
    # a manual run already completed. Only active on scheduled (cron) runs —
    # manual triggers (workflow_dispatch or local) always pass --force and
    # are never blocked.
    if not dry_run and send_slack and not force:
        _today_file = HISTORICAL_DIR / f"{date_str}.json"
        if _today_file.exists():
            logger.info(
                "⏭  Report for %s already exists (%s). Skipping duplicate "
                "automated run. Use --force to override.",
                date_str, _today_file.name,
            )
            sys.exit(0)

    prev_csov  = _load_previous_csov(HISTORICAL_DIR)

    logger.info("=" * 60)
    logger.info("iVisa CSOV Dashboard — %s%s", date_str, " [DRY RUN]" if dry_run else "")
    logger.info("=" * 60)

    # ── DRY RUN: load sample data ─────────────────────────────────────────────
    if dry_run:
        logger.info("[1/6] Loading sample data (dry-run mode)...")
        try:
            with open(SAMPLE_DATA_FILE, "r", encoding="utf-8") as f:
                report_payload = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logger.error("Could not load sample_data.json: %s", exc)
            sys.exit(1)

        logger.info("[2-4/6] Skipping API calls (dry-run).")

    # ── LIVE RUN ──────────────────────────────────────────────────────────────
    else:
        # 0. SerpAPI credits check
        try:
            import urllib.request
            from scripts.config import SERPAPI_KEY
            if SERPAPI_KEY:
                url = f"https://serpapi.com/account?api_key={SERPAPI_KEY}"
                with urllib.request.urlopen(url, timeout=8) as resp:
                    account = json.loads(resp.read().decode())
                remaining = account.get("total_searches_left", None)
                plan_searches = account.get("plan_searches_left", None)
                display = plan_searches if plan_searches is not None else remaining
                if display is not None:
                    if display < 100:
                        logger.warning("⚠️  SerpAPI credits CRITICAL: %d remaining — report data will be incomplete!", display)
                    elif display < 300:
                        logger.warning("⚠️  SerpAPI credits LOW: %d remaining — consider skipping this run until renewal.", display)
                    else:
                        logger.info("  SerpAPI credits: %d remaining ✓", display)
        except Exception as exc:
            logger.warning("  Could not check SerpAPI credits: %s", exc)

        # 1. SERP
        logger.info("[1/6] Fetching SERP data (SEMrush + Ahrefs)...")
        try:
            from scripts.fetch_serp import fetch_serp_data
            serp_data = fetch_serp_data()
        except Exception as exc:
            logger.error("SERP fetch failed: %s — using zeroed scores.", exc)
            serp_data = {
                "results":        {c: {kw: [] for kw in __import__("scripts.config", fromlist=["KEYWORDS"]).KEYWORDS} for c in COUNTRIES},
                "country_scores": {c: 0.0 for c in COUNTRIES},
                "global_score":   0.0,
            }

        # 2. AI Overviews
        logger.info("[2/6] Fetching AI Overview data (Serper.dev)...")
        try:
            from scripts.fetch_ai_overviews import fetch_ai_overview_data
            ai_overview_data = fetch_ai_overview_data()
        except Exception as exc:
            logger.error("AI Overview fetch failed: %s — using zeroed scores.", exc)
            ai_overview_data = {
                "results":        {c: {} for c in COUNTRIES},
                "country_scores": {c: 0.0 for c in COUNTRIES},
                "global_score":   0.0,
            }

        # 3. LLM
        logger.info("[3/6] Querying LLMs (Claude + Gemini)...")
        try:
            from scripts.fetch_llm import fetch_llm_data
            llm_data = fetch_llm_data()
        except Exception as exc:
            logger.error("LLM fetch failed: %s — using default score 50.", exc)
            llm_data = {
                "part_a":      {"results": [], "score": 50.0},
                "part_b":      {"results": [], "mention_rate": 0.0, "avg_positive_sentiment": 50.0, "score": 50.0},
                "global_score": 50.0,
            }

        # 2b. Enrich SERP with SerpAPI organic results (titles + fill gaps)
        logger.info("[2b/6] Enriching SERP data with SerpAPI organic titles...")
        try:
            from scripts.fetch_serp import enrich_with_serpapi_organic
            serp_data = enrich_with_serpapi_organic(serp_data, ai_overview_data.get("organic_data", {}))
        except Exception as exc:
            logger.warning("SERP enrichment skipped: %s", exc)

        # 4. Earned Media + CSOV calculation
        logger.info("[4/6] Fetching earned media (SerpAPI) & calculating CSOV...")
        try:
            from scripts.calculate_csov import calculate_csov, generate_action_items, generate_action_items_by_tab
            from scripts.fetch_earned_media import fetch_earned_media_data
            earned_media_data = fetch_earned_media_data()
            csov_result       = calculate_csov(
                serp_score          = serp_data["global_score"],
                ai_overview_score   = ai_overview_data["global_score"],
                llm_score           = llm_data["global_score"],
                earned_media_score  = earned_media_data["score"],
            )
            action_items          = generate_action_items(csov_result["components"], serp_data, ai_overview_data)
            action_items_by_tab   = generate_action_items_by_tab(csov_result["components"], serp_data, ai_overview_data)
        except Exception as exc:
            logger.error("CSOV calculation failed: %s", exc)
            earned_media_data    = {"score": 60, "mentions": []}
            csov_result          = {"csov_score": 0.0, "components": {}, "formula": ""}
            action_items         = ["Recalculation required — see logs for errors."]
            action_items_by_tab  = {}

        # 4b. Per-country Earned Media
        logger.info("[4b/6] Fetching per-country earned media...")
        earned_media_by_country: dict = {}
        try:
            from scripts.fetch_earned_media import fetch_earned_media_by_country
            earned_media_by_country = fetch_earned_media_by_country(COUNTRIES)
        except Exception as exc:
            logger.error("Per-country EM fetch failed: %s — skipping.", exc)

        # 4c. Per-country LLM brand perception — deferred to v1.1
        # (requires language-specific queries + Gemini locale grounding)
        llm_by_country: dict = {}

        report_payload = _build_report_payload(
            serp_data                = serp_data,
            ai_overview_data         = ai_overview_data,
            llm_data                 = llm_data,
            earned_media_data        = {**earned_media_data, **{"score": earned_media_data.get("score", 60)}},
            csov_result              = csov_result,
            action_items             = action_items,
            action_items_by_tab      = action_items_by_tab,
            previous_csov            = prev_csov,
            country_configs          = COUNTRIES,
            earned_media_by_country  = earned_media_by_country,
            llm_by_country           = llm_by_country,
        )

    # ── Data completeness gate ──────────────────────────────────────────────
    # Detect silently-missing components (e.g. Gemini quota + Claude hiccup
    # leaving the LLM score a hollow default) BEFORE the report ships.
    from scripts.check_completeness import (
        assess_completeness, format_completeness, validate_payload_shape, score_sanity,
    )
    completeness = assess_completeness(report_payload)
    report_payload["data_completeness"] = completeness
    logger.info(format_completeness(completeness))

    # Payload shape — every score must be a real 0–100 number (guards the
    # None-where-a-number-was-expected class). A bad shape is a hard failure.
    shape_errors = validate_payload_shape(report_payload)
    if shape_errors:
        for e in shape_errors:
            logger.error("  ⛔ payload shape: %s", e)
        if not completeness["ok"]:
            completeness["errors"].extend(shape_errors)
        else:
            completeness["errors"].extend(shape_errors)
            completeness["ok"] = False

    # Score sanity — flag implausibly large week-over-week swings (warn only).
    for w in score_sanity(report_payload, prev_csov):
        logger.warning("  ⚠️ score sanity: %s", w)

    # ── HTML Report ───────────────────────────────────────────────────────────
    logger.info("[5/6] Generating HTML report...")
    try:
        from scripts.generate_report import generate_report

        # Primary: docs/index.html (GitHub Pages)
        index_path = DOCS_DIR / "index.html"
        generate_report(report_payload, str(index_path))

        # Archive copy: docs/reports/YYYY-MM-DD.html
        archive_path = DOCS_DIR / "reports" / f"{date_str}.html"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        generate_report(report_payload, str(archive_path))

        # Reports archive index: docs/reports/index.html
        try:
            from scripts.generate_report import generate_reports_index
            reports_index_path = DOCS_DIR / "reports" / "index.html"
            generate_reports_index(str(DOCS_DIR / "reports"), str(reports_index_path))
            logger.info("    • %s", reports_index_path)
        except Exception as exc_idx:
            logger.warning("  Reports index generation failed: %s", exc_idx)

        logger.info("  Reports saved:")
        logger.info("    • %s", index_path)
        logger.info("    • %s", archive_path)
    except Exception as exc:
        logger.error("Report generation failed: %s", exc)

    # ── Headless render check ───────────────────────────────────────────────────
    # Confirm the generated page actually populates (catches RUNTIME JS errors that
    # syntax/data checks miss — the "stuck on Loading…" class). Runs BEFORE Slack/
    # save so a broken page is never notified or published. Best-effort: skips if
    # puppeteer isn't installed (the workflow installs it in CI).
    if not dry_run:
        _render_problem = _check_render(str(DOCS_DIR / "index.html"))
        if _render_problem:
            logger.error("  ⛔ RENDER CHECK FAILED — page did not populate: %s", _render_problem)
            completeness.setdefault("errors", []).append("Render: " + _render_problem)
            completeness["ok"] = False

    # ── Completeness gate: bail BEFORE saving on missing core data ──────────────
    # If a core component is missing we do NOT save a snapshot, do NOT Slack, and
    # exit non-zero. Not saving is deliberate: it leaves no YYYY-MM-DD.json, so the
    # next staggered Monday cron slot retries cleanly instead of being blocked by
    # the duplicate-guard. Transient API outages thus self-heal within ~30 min.
    if not dry_run and not completeness["ok"]:
        logger.error(
            "⛔ DATA COMPLETENESS FAILED — missing: %s. NOT saving a snapshot, NOT "
            "sending Slack, exiting non-zero so this report is NOT published and a "
            "later run can retry.",
            "; ".join(completeness["errors"]),
        )
        sys.exit(1)

    # ── Save Historical Data ───────────────────────────────────────────────────
    if not dry_run:
        slack_label = "sending Slack notification" if send_slack else "skipping Slack (use --slack to send)"
        logger.info("[6/6] Saving historical snapshot... (%s)", slack_label)
        _save_historical(report_payload, HISTORICAL_DIR, run_date)

        if send_slack:
            try:
                from scripts.send_slack import send_slack_notification
                send_slack_notification({
                    **report_payload,
                    "week_label": report_payload.get("week_label", date_str),
                })
            except Exception as exc:
                logger.error("Slack notification failed: %s", exc)
        else:
            logger.info("  Slack skipped. Run with --slack to send.")
    else:
        logger.info("[6/6] Skipping historical save & Slack (dry-run).")

    csov_score = report_payload.get("csov_score", 0)
    logger.info("=" * 60)
    logger.info("DONE. CSOV Score this week: %.1f / 100", csov_score)
    if prev_csov is not None:
        diff = csov_score - prev_csov
        logger.info("      Change vs last week:  %+.1f", diff)
    logger.info("=" * 60)


# ── CLI Entry Point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="iVisa CSOV Weekly Reputation Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py            # Live run (requires API keys in .env)
  python main.py --dry-run  # Demo run using sample data
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load sample data instead of calling APIs. No API keys required.",
    )
    parser.add_argument(
        "--slack",
        action="store_true",
        help="Send Slack notification after the run. Omit to skip Slack (for manual/test runs).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force run even if today's report already exists (bypasses duplicate-run guard).",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run, send_slack=args.slack, force=args.force)
