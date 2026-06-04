"""
health_check.py — Pre-run validation for iVisa CSOV pipeline.

Checks every component with minimal API calls (1–2 queries each).
No SerpAPI calls — that's the most expensive resource.

Usage:
  python3 scripts/health_check.py

Green = Monday automation will run fine.
Red   = Fix the issue before Monday.
"""

from __future__ import annotations
import os
import sys
import time
import pathlib

# Ensure project root is on sys.path so `scripts.*` imports work
ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Load .env before anything else
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

PASS  = "✅"
FAIL  = "❌"
WARN  = "⚠️ "
SEP   = "─" * 56

results: list[tuple[str, str, str]] = []  # (status, name, detail)

def check(name: str, fn):
    try:
        detail = fn()
        results.append((PASS, name, detail or ""))
        print(f"  {PASS}  {name}" + (f" — {detail}" if detail else ""))
    except Exception as exc:
        results.append((FAIL, name, str(exc)))
        print(f"  {FAIL}  {name} — {exc}")


# ── 1. Environment variables ──────────────────────────────────────────────────
print(f"\n{SEP}")
print("  1. Environment Variables")
print(SEP)

REQUIRED_KEYS = [
    "SEMRUSH_API_KEY", "AHREFS_API_KEY", "CLAUDE_API_KEY",
    "GEMINI_API_KEY", "SERPAPI_KEY", "SLACK_WEBHOOK_URL",
]
for key in REQUIRED_KEYS:
    val = os.environ.get(key, "")
    if val:
        results.append((PASS, key, f"set ({len(val)} chars)"))
        print(f"  {PASS}  {key} — set ({len(val)} chars)")
    else:
        results.append((FAIL, key, "MISSING"))
        print(f"  {FAIL}  {key} — MISSING")


# ── 2. Python imports ─────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  2. Python Package Imports")
print(SEP)

def check_anthropic():
    import anthropic
    return f"version {anthropic.__version__}"

def check_google_genai():
    from google import genai
    return "google-genai OK"

def check_requests():
    import requests
    return f"version {requests.__version__}"

def check_dotenv():
    import dotenv
    return "python-dotenv OK"

check("anthropic",    check_anthropic)
check("google-genai", check_google_genai)
check("requests",     check_requests)
check("python-dotenv",check_dotenv)


# ── 3. Claude API ─────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  3. Claude API")
print(SEP)

def check_claude_api():
    from scripts.config import CLAUDE_API_KEY, CLAUDE_MODEL
    if not CLAUDE_API_KEY:
        raise Exception("CLAUDE_API_KEY not set")
    import anthropic
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=20,
        messages=[{"role": "user", "content": "Reply with the single word: OK"}],
    )
    text = msg.content[0].text.strip()
    return f"model={CLAUDE_MODEL} response='{text}'"

check("Claude API call", check_claude_api)


# ── 4. Gemini API ─────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  4. Gemini API")
print(SEP)

def check_gemini_api():
    from scripts.config import GEMINI_API_KEY, GEMINI_MODEL
    if not GEMINI_API_KEY:
        raise Exception("GEMINI_API_KEY not set")
    from google import genai as google_genai
    client = google_genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents="Reply with the single word: OK",
    )
    text = response.text.strip() if response.text else "NO RESPONSE"
    return f"model={GEMINI_MODEL} response='{text[:40]}'"

check("Gemini API call", check_gemini_api)


# ── 5. SerpAPI (balance check only — no search query) ────────────────────────
print(f"\n{SEP}")
print("  5. SerpAPI (credits check — no search query burned)")
print(SEP)

def check_serpapi_credits():
    import urllib.request, json
    from scripts.config import SERPAPI_KEY
    if not SERPAPI_KEY:
        raise Exception("SERPAPI_KEY not set")
    url = f"https://serpapi.com/account?api_key={SERPAPI_KEY}"
    with urllib.request.urlopen(url, timeout=8) as resp:
        data = json.loads(resp.read().decode())
    remaining = data.get("plan_searches_left") or data.get("total_searches_left", "?")
    if isinstance(remaining, int) and remaining < 100:
        raise Exception(f"CRITICAL: only {remaining} credits left — do NOT run before renewal (June 26)")
    if isinstance(remaining, int) and remaining < 300:
        return f"LOW: {remaining} credits remaining — use sparingly"
    return f"{remaining} credits remaining"

check("SerpAPI credits", check_serpapi_credits)


# ── 6. Serper.dev (AI Overviews) ──────────────────────────────────────────────
print(f"\n{SEP}")
print("  6. Serper.dev API (AI Overview source)")
print(SEP)

def check_serper():
    import requests as req
    serper_key = os.environ.get("SERPER_API_KEY", "")
    # Serper key may be embedded in fetch_ai_overviews.py
    if not serper_key:
        from scripts import fetch_ai_overviews
        import inspect
        src = inspect.getsource(fetch_ai_overviews)
        import re
        m = re.search(r'SERPER_API_KEY.*?=.*?os\.environ.*?get\(["\']([^"\']+)', src)
        key_name = m.group(1) if m else "SERPER_API_KEY"
        serper_key = os.environ.get(key_name, "")
    if not serper_key:
        return "SERPER_API_KEY not set — AI Overview data will be empty"
    return f"key set ({len(serper_key)} chars)"

check("Serper.dev key", check_serper)


# ── 7. Slack webhook ──────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  7. Slack Webhook")
print(SEP)

def check_slack():
    import requests as req
    from scripts.config import SLACK_WEBHOOK_URL
    if not SLACK_WEBHOOK_URL:
        raise Exception("SLACK_WEBHOOK_URL not set")
    # Just validate the URL format — don't actually send
    if not SLACK_WEBHOOK_URL.startswith("https://hooks.slack.com/"):
        raise Exception(f"Unexpected webhook URL format: {SLACK_WEBHOOK_URL[:40]}")
    return "webhook URL format OK (not sending test message)"

check("Slack webhook URL", check_slack)


# ── 8. Sentiment classification rules ────────────────────────────────────────
print(f"\n{SEP}")
print("  8. Sentiment Classification Rules")
print(SEP)

SENTIMENT_TESTS = [
    # (domain, title, snippet, expected, description)
    ("tripadvisor.com",
     "ivisa https://www.ivisa.com is it a scam or geniune visa",
     "Today I applied again but through the app of UK Eta: 20€ and application accepted…",
     "negative", "Tripadvisor scam-question forum thread"),

    ("lakelandcurrents.com",
     "Is iVisa a Scam? Inside the Refund Policy That's Restoring ...",
     "It's a fair question for any traveler to ask, often after applying through iVisa.",
     "positive", "Debunking article with positive subtitle"),

    ("europeanbusinessreview.com",
     "Is iVisa Legit? Why Travelers Worldwide Trust the Service",
     "Learn why iVisa is considered a reliable and secure online visa processing service, trusted by",
     "positive", "Editorial domain — positive article"),

    ("forbes.com",
     "Is iVisa a scam?",
     "No, iVisa is a legitimate service used by millions of travelers worldwide.",
     "positive", "Clean debunking — no concerns in snippet"),

    ("tripadvisor.com",
     "Is iVisa a scam?",
     "No, but the fees can be expensive and refund policy is strict.",
     "neutral", "Debunking but acknowledges concerns"),

    ("ripoffreport.com",
     "iVisa complaint",
     "Lost my money, worst service ever.",
     "negative", "Structural complaint domain — always negative"),

    ("ivisa.com",
     "iVisa — Fast, Simple, Secure Visa Applications",
     "Apply for your visa online in minutes.",
     "positive", "iVisa owned domain — no complaints"),

    ("1883magazine.com",
     "1883 Magazine | Celebrity Interviews, Fashion, Beauty, Music & Film",
     'var theplus_ajax_url = "https://1883magazine.com/wp-admin/admin-ajax.php"; var nonce = "abc123"',
     "neutral", "JS junk snippet → cleared → no signals → neutral"),
]

from scripts.fetch_serp import _classify_result, _is_junk_snippet, _is_domain_title

all_passed = True
for domain, title, snippet, expected, desc in SENTIMENT_TESTS:
    # Apply sanitization as pipeline does
    clean_title   = "" if _is_domain_title(title, domain) else title
    clean_snippet = "" if _is_junk_snippet(snippet) else snippet
    result = _classify_result(domain, clean_title, clean_snippet)
    ok = result == expected
    if not ok:
        all_passed = False
    status = PASS if ok else FAIL
    results.append((status, f"Sentiment: {desc}", f"got={result} expected={expected}"))
    print(f"  {status}  {desc}")
    if not ok:
        print(f"        got '{result}', expected '{expected}'")


# ── 9. Report generation (dry run) ───────────────────────────────────────────
print(f"\n{SEP}")
print("  9. Report Generation (dry run)")
print(SEP)

def check_report_gen():
    import json, pathlib
    from scripts.config import SAMPLE_DATA_FILE
    from scripts.generate_report import generate_report, generate_reports_index
    import tempfile, os as _os

    with open(SAMPLE_DATA_FILE, "r") as f:
        data = json.load(f)

    with tempfile.TemporaryDirectory() as tmpdir:
        out = _os.path.join(tmpdir, "test_report.html")
        generate_report(data, out)
        size_kb = _os.path.getsize(out) // 1024

        # Check no placeholder left un-replaced
        content = open(out).read()
        placeholders = [p for p in ["__REPORT_DATA_PLACEHOLDER__", "__ARCHIVE_LINKS_PLACEHOLDER__"] if p in content]
        if placeholders:
            raise Exception(f"Unreplaced placeholders found: {placeholders}")

        # Check key sections present
        for section in ["scoreAnalysisPanel", "trendChart", "countryGrid"]:
            if section not in content:
                raise Exception(f"Missing section: {section}")

    return f"{size_kb} KB, all sections present, no unreplaced placeholders"

check("HTML report generation", check_report_gen)


# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)
total  = len(results)

if failed == 0:
    print(f"  {PASS}  ALL {total} CHECKS PASSED — Monday automation is ready!")
else:
    print(f"  {FAIL}  {failed}/{total} checks FAILED — fix before Monday")
    print()
    for status, name, detail in results:
        if status == FAIL:
            print(f"       {FAIL} {name}: {detail}")
print(SEP)
sys.exit(0 if failed == 0 else 1)
