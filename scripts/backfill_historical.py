"""
backfill_historical.py — Creates historical monthly snapshots for Jan–May 2026.

Usage:
  python -m scripts.backfill_historical           # Backfill Jan–May 2026
  python -m scripts.backfill_historical --month 2026-03  # Single month

Strategy:
  - SERP, AI Overview, and LLM scores can't be backdated (no time-travel API).
    We use current scores as baseline estimates for all historical months.
  - Earned Media CAN be fetched historically via SerpAPI date filtering.
    We fetch earned media for the last week of each month.
  - Period 1 baseline = Feb–May 2026 (average of those months).
  - Period 2 goal = Jun–Sep 2026 (tracked weekly going forward).

Months and date windows:
  Jan 2026: Jan 25 – Jan 31
  Feb 2026: Feb 22 – Feb 28
  Mar 2026: Mar 25 – Mar 31
  Apr 2026: Apr 24 – Apr 30
  May 2026: May 25 – May 29 (today)
"""

import argparse
import json
import logging
import pathlib
import sys
from datetime import date, datetime

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Month windows: (snapshot_date, start_date, end_date) ─────────────────────
BACKFILL_MONTHS = [
    ("2026-01-31", "2026-01-25", "2026-01-31"),
    ("2026-02-28", "2026-02-22", "2026-02-28"),
    ("2026-03-31", "2026-03-25", "2026-03-31"),
    ("2026-04-30", "2026-04-24", "2026-04-30"),
    ("2026-05-29", "2026-05-25", "2026-05-29"),
]


def _week_label(snapshot_date: str) -> str:
    dt = datetime.strptime(snapshot_date, "%Y-%m-%d")
    return dt.strftime("Week of %b %-d, %Y")


def _load_latest_scores(historical_dir: pathlib.Path) -> dict:
    """Load the most recent historical snapshot to use as baseline SERP/AIO/LLM scores."""
    try:
        files = sorted(historical_dir.glob("*.json"), reverse=True)
        for f in files:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            comps = data.get("components", {})
            if comps.get("serp") and comps.get("ai_overview") and comps.get("llm"):
                logger.info("  Using baseline scores from: %s", f.name)
                return {
                    "serp_score":        comps["serp"].get("score", 50.0),
                    "ai_overview_score": comps["ai_overview"].get("score", 50.0),
                    "llm_score":         comps["llm"].get("score", 50.0),
                    "serp_data":         data.get("serp_data", {}),
                    "ai_overview_data":  data.get("ai_overview_data", {}),
                    "llm_data":          data.get("llm_data", {}),
                    "country_data":      data.get("country_data", {}),
                }
    except Exception as exc:
        logger.warning("Could not load latest scores: %s — using defaults (50)", exc)

    return {
        "serp_score":        50.0,
        "ai_overview_score": 50.0,
        "llm_score":         50.0,
        "serp_data":         {"results": {}, "country_scores": {}, "global_score": 50.0},
        "ai_overview_data":  {"results": {}, "country_scores": {}, "global_score": 50.0},
        "llm_data":          {"global_score": 50.0, "part_a": {}, "part_b": {}},
        "country_data":      {},
    }


def _build_snapshot(
    snapshot_date: str,
    date_range: tuple[str, str],
    baseline: dict,
    historical_dir: pathlib.Path,
    skip_if_exists: bool = True,
) -> bool:
    """
    Build and save one monthly snapshot.
    Returns True if saved, False if skipped.
    """
    from scripts.calculate_csov import calculate_csov
    from scripts.fetch_earned_media import fetch_earned_media_data

    out_path = historical_dir / f"{snapshot_date}.json"

    if skip_if_exists and out_path.exists():
        logger.info("  Snapshot %s already exists — skipping.", snapshot_date)
        return False

    logger.info("  Building snapshot: %s  (earned media: %s → %s)", snapshot_date, *date_range)

    # Fetch earned media for this date window
    em_data = fetch_earned_media_data(date_range=date_range)

    # Calculate CSOV using baseline SERP/AIO/LLM + this month's earned media
    csov_result = calculate_csov(
        serp_score         = baseline["serp_score"],
        ai_overview_score  = baseline["ai_overview_score"],
        llm_score          = baseline["llm_score"],
        earned_media_score = em_data["score"],
    )

    snapshot = {
        "week_label":          _week_label(snapshot_date),
        "snapshot_date":       snapshot_date,
        "date_range":          {"start": date_range[0], "end": date_range[1]},
        "csov_score":          csov_result["csov_score"],
        "components":          csov_result["components"],
        "formula":             csov_result["formula"],
        "country_data":        baseline.get("country_data", {}),
        "serp_data":           baseline.get("serp_data", {}),
        "ai_overview_data":    baseline.get("ai_overview_data", {}),
        "llm_data":            baseline.get("llm_data", {}),
        "earned_media":        em_data,
        "backfill":            True,
        "note": (
            "Historical backfill: SERP/AIO/LLM scores are current baselines; "
            "Earned Media is fetched from the date window shown above."
        ),
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)

    logger.info(
        "    → Saved %s  |  CSOV=%.1f  EM=%.1f (%d mentions)",
        out_path.name,
        csov_result["csov_score"],
        em_data["score"],
        em_data["counts"]["total"],
    )
    return True


def _calculate_period_baseline(historical_dir: pathlib.Path, months: list[str]) -> dict:
    """
    Calculate Period 1 baseline: average CSOV and component scores across given months.
    months: list of YYYY-MM-DD snapshot dates.
    """
    scores = []
    for snapshot_date in months:
        path = historical_dir / f"{snapshot_date}.json"
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            scores.append({
                "csov":          data.get("csov_score", 0),
                "serp":          data.get("components", {}).get("serp", {}).get("score", 0),
                "ai_overview":   data.get("components", {}).get("ai_overview", {}).get("score", 0),
                "llm":           data.get("components", {}).get("llm", {}).get("score", 0),
                "earned_media":  data.get("components", {}).get("earned_media", {}).get("score", 0),
            })
        except Exception as exc:
            logger.warning("Could not load snapshot %s: %s", snapshot_date, exc)

    if not scores:
        return {}

    n = len(scores)
    baseline = {
        "period":        "P1",
        "label":         "Period 1 Baseline (Feb–May 2026)",
        "months_used":   n,
        "csov":          round(sum(s["csov"] for s in scores) / n, 2),
        "serp":          round(sum(s["serp"] for s in scores) / n, 2),
        "ai_overview":   round(sum(s["ai_overview"] for s in scores) / n, 2),
        "llm":           round(sum(s["llm"] for s in scores) / n, 2),
        "earned_media":  round(sum(s["earned_media"] for s in scores) / n, 2),
    }
    return baseline


def run(target_month: str | None = None, force: bool = False) -> None:
    """
    Main backfill runner.

    Args:
        target_month: YYYY-MM to run single month. None = run all.
        force: If True, overwrite existing snapshots.
    """
    from scripts.config import DATA_DIR, HISTORICAL_DIR

    HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)
    baseline = _load_latest_scores(HISTORICAL_DIR)

    logger.info("=" * 60)
    logger.info("iVisa CSOV — Historical Backfill")
    logger.info("=" * 60)

    months_to_run = BACKFILL_MONTHS
    if target_month:
        months_to_run = [
            m for m in BACKFILL_MONTHS
            if m[0].startswith(target_month)
        ]
        if not months_to_run:
            logger.error("No matching month for: %s", target_month)
            sys.exit(1)

    saved_count = 0
    for snapshot_date, start_date, end_date in months_to_run:
        saved = _build_snapshot(
            snapshot_date  = snapshot_date,
            date_range     = (start_date, end_date),
            baseline       = baseline,
            historical_dir = HISTORICAL_DIR,
            skip_if_exists = not force,
        )
        if saved:
            saved_count += 1

    # Calculate and save Period 1 baseline (Feb–May)
    p1_months = ["2026-02-28", "2026-03-31", "2026-04-30", "2026-05-29"]
    p1_baseline = _calculate_period_baseline(HISTORICAL_DIR, p1_months)
    if p1_baseline:
        p1_path = DATA_DIR / "period1_baseline.json"
        with open(p1_path, "w", encoding="utf-8") as f:
            json.dump(p1_baseline, f, ensure_ascii=False, indent=2)
        logger.info("")
        logger.info("Period 1 Baseline (Feb–May 2026):")
        logger.info("  CSOV:         %.1f", p1_baseline["csov"])
        logger.info("  SERP:         %.1f", p1_baseline["serp"])
        logger.info("  AI Overview:  %.1f", p1_baseline["ai_overview"])
        logger.info("  LLM:          %.1f", p1_baseline["llm"])
        logger.info("  Earned Media: %.1f", p1_baseline["earned_media"])
        logger.info("  Saved → %s", p1_path)

    logger.info("=" * 60)
    logger.info("Done. %d snapshots saved.", saved_count)
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="iVisa CSOV — Historical Backfill",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.backfill_historical               # All months Jan–May
  python -m scripts.backfill_historical --month 2026-03  # March only
  python -m scripts.backfill_historical --force       # Overwrite existing
        """,
    )
    parser.add_argument("--month", help="YYYY-MM to backfill single month")
    parser.add_argument("--force", action="store_true", help="Overwrite existing snapshots")
    args = parser.parse_args()
    run(target_month=args.month, force=args.force)
