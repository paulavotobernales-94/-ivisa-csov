from __future__ import annotations

"""
send_slack.py — Sends a Slack summary message with the CSOV report link.
"""

import json
import logging

import requests

from scripts.config import GITHUB_PAGES_URL, SLACK_WEBHOOK_URL

logger = logging.getLogger(__name__)


def _score_emoji(score: float) -> str:
    if score >= 75:
        return "🟢"
    elif score >= 55:
        return "🟡"
    return "🔴"


def _trend_text(current: float, previous: float | None) -> str:
    if previous is None:
        return ""
    diff = current - previous
    if diff > 0:
        return f"+{diff:.1f} ↑"
    elif diff < 0:
        return f"{diff:.1f} ↓"
    return "→ no change"


def send_slack_notification(report_data: dict) -> bool:
    """
    Post a Slack message summarising the CSOV report.
    Returns True on success, False on failure.
    """
    if not SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL not set — skipping Slack notification.")
        return False

    csov = report_data.get("csov_score", 0)
    prev_csov = report_data.get("previous_csov_score")
    components = report_data.get("components", {})
    week_label = report_data.get("week_label", "")
    report_url = f"{GITHUB_PAGES_URL}/index.html"

    trend = _trend_text(csov, prev_csov)
    emoji = _score_emoji(csov)

    serp  = components.get("serp", {}).get("score", 0)
    aio   = components.get("ai_overview", {}).get("score", 0)
    llm   = components.get("llm", {}).get("score", 0)
    em    = components.get("earned_media", {}).get("score", 0)

    actions = report_data.get("action_items", [])
    action_text = "\n".join(f"• {a}" for a in actions[:3]) if actions else "• No critical actions needed."

    message = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} iVisa Credibility Share of Voice — {week_label}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"Weekly global reputation snapshot across 10 countries and up to 11 localized keywords. "
                        f"Score measures positive vs. negative brand signals in search, AI, and media."
                    ),
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*🌍 Global CSOV Score*\n`{csov:.1f} / 100`  {trend}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*📊 Full Report*\n<{report_url}|View breakdown by country & keyword →>",
                    },
                ],
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Component Breakdown*\n"
                        f"{_score_emoji(serp)} *SERP Sentiment:* {serp:.1f}/100  _(35% weight)_\n"
                        f"{_score_emoji(aio)} *AI Overview:* {aio:.1f}/100  _(25% weight)_\n"
                        f"{_score_emoji(llm)} *LLM Mentions:* {llm:.1f}/100  _(25% weight)_\n"
                        f"{_score_emoji(em)} *Earned Media:* {em:.1f}/100  _(15% weight)_"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Top Action Items*\n{action_text}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"Auto-generated every Monday at 9 AM Madrid time  •  iVisa Brand Team  •  "
                            f"<{report_url}|Full CSOV Dashboard>"
                        ),
                    }
                ],
            },
        ]
    }

    try:
        resp = requests.post(
            SLACK_WEBHOOK_URL,
            data=json.dumps(message),
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("  Slack notification sent successfully.")
        return True
    except requests.RequestException as exc:
        logger.error("  Failed to send Slack notification: %s", exc)
        return False
