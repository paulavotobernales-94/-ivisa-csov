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
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        logger.info("  Historical snapshot saved: %s", fname)
    except OSError as exc:
        logger.error("  Could not save historical data: %s", exc)


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
    from scripts.config import HISTORICAL_DIR
    history = []
    try:
        from datetime import timedelta
        _today = date.today()
        monday = _today - timedelta(days=_today.weekday())
        sunday = monday + timedelta(days=6)
        current_week_label = f"{monday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')}"

        hfiles = sorted(HISTORICAL_DIR.glob("*.json"))
        # Deduplicate by week_label — keep latest file per week
        seen_labels: dict = {}
        for hf in hfiles:
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
        # can never poison the chart for this week.
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
        "csov_score":          csov_result["csov_score"],
        "previous_csov_score": previous_csov,
        "components":          components,
        "country_data":        country_data,
        "serp_data":           serp_data,
        "ai_overview_data":    ai_overview_data,
        "llm_data":            llm_data,
        "earned_media":        earned_media_data,
        "historical":          history,
        "action_items":        action_items,
        "action_items_by_tab": action_items_by_tab,
        "formula":             csov_result.get("formula", ""),
        "period1_baseline":    period1_baseline,
        "scoring_version":     SCORING_VERSION,
    }


# ── Main Pipeline ─────────────────────────────────────────────────────────────

def run(dry_run: bool = False, send_slack: bool = False) -> None:
    from scripts.config import (
        COUNTRIES,
        DATA_DIR,
        DOCS_DIR,
        HISTORICAL_DIR,
        SAMPLE_DATA_FILE,
    )

    run_date   = date.today()
    date_str   = run_date.isoformat()
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
        logger.info("[5/6] Generating HTML report...")

    # ── LIVE RUN ──────────────────────────────────────────────────────────────
    else:
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

        logger.info("[5/6] Generating HTML report...")
        report_payload = _build_report_payload(
            serp_data         = serp_data,
            ai_overview_data  = ai_overview_data,
            llm_data          = llm_data,
            earned_media_data = {**earned_media_data, **{"score": earned_media_data.get("score", 60)}},
            csov_result       = csov_result,
            action_items         = action_items,
            action_items_by_tab  = action_items_by_tab,
            previous_csov        = prev_csov,
            country_configs   = COUNTRIES,
        )
        report_payload["previous_csov_score"] = prev_csov

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

        logger.info("  Reports saved:")
        logger.info("    • %s", index_path)
        logger.info("    • %s", archive_path)
    except Exception as exc:
        logger.error("Report generation failed: %s", exc)

    # ── Save Historical Data ───────────────────────────────────────────────────
    if not dry_run:
        slack_label = "sending Slack notification" if send_slack else "skipping Slack (use --slack to send)"
        logger.info("[6/6] Saving historical snapshot... (%s)", slack_label)
        _save_historical(report_payload, HISTORICAL_DIR, run_date)

        # Slack — only when explicitly requested (--slack flag or Monday automation)
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
    args = parser.parse_args()
    run(dry_run=args.dry_run, send_slack=args.slack)
