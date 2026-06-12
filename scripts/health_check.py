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

# When running inside GitHub Actions, live API calls (Claude, Gemini, SerpAPI)
# are treated as warnings not failures. A transient API hiccup at 07:00 UTC
# should never block the whole pipeline — the pipeline itself handles API
# failures gracefully. All non-API checks (env vars, imports, weights, file
# sizes, classifier tests) remain hard failures in both environments.
IS_CI = os.environ.get("GITHUB_ACTIONS") == "true"
if IS_CI:
    print(f"\n  ℹ️  Running in GitHub Actions — live API checks are WARNINGS (not failures)")

results: list[tuple[str, str, str]] = []  # (status, name, detail)

def check(name: str, fn):
    """Hard check — failure always counts as a failed check."""
    try:
        detail = fn()
        results.append((PASS, name, detail or ""))
        print(f"  {PASS}  {name}" + (f" — {detail}" if detail else ""))
    except Exception as exc:
        results.append((FAIL, name, str(exc)))
        print(f"  {FAIL}  {name} — {exc}")

def check_api(name: str, fn):
    """Soft check — failure is a WARNING in CI, a hard FAILURE when run locally.
    Use this for live API calls (Claude, Gemini, SerpAPI) where a transient
    network issue should not block the Monday pipeline from running."""
    try:
        detail = fn()
        results.append((PASS, name, detail or ""))
        print(f"  {PASS}  {name}" + (f" — {detail}" if detail else ""))
    except Exception as exc:
        if IS_CI:
            results.append((WARN, name, f"CI WARNING (non-blocking): {exc}"))
            print(f"  {WARN}  {name} — CI WARNING (non-blocking): {exc}")
        else:
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

check_api("Claude API call", check_claude_api)


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

check_api("Gemini API call", check_gemini_api)


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

check_api("SerpAPI credits", check_serpapi_credits)


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

from scripts.fetch_serp import _classify_result, _is_junk_snippet, _is_domain_title

# ── 8a. Junk snippet detector — explicit unit tests ──────────────────────────
# Every pattern that has ever caused bad data to appear in the report
# must be listed here. Add a new row any time a new junk format is found.
JUNK_SNIPPET_TESTS = [
    # (snippet, should_be_junk, description)

    # JSON-LD structured data (schema.org) — help.ivisa.com bug June 2026
    ('{"@context":"https://schema.org","@type":"WebSite","inLanguage":"en","name":"iVisa Help Center"}',
     True, "JSON-LD schema.org blob (help.ivisa.com bug)"),

    ('{"@context": "https://schema.org", "@type": "Organization", "name": "iVisa"}',
     True, "JSON-LD with space after colon variant"),

    # Google Play / YouTube WIZ_global_data — play.google.com bug June 2026
    ('window.WIZ_global_data = {"AfY8Hf":false,"DMjf6c":false,"WFaiLe":false}',
     True, "window.WIZ_global_data JS blob (play.google.com bug)"),

    ('window.google = {"kEI":"abc123","kEXPI":"12345"}',
     True, "window.google JS assignment"),

    # Feature-detection inline script — heise.de / ivisaconsulting.com bug June 2026
    # Leaked into June 8 data; '-->' prefix + window.Intl property access
    ("--> if (!window.Intl || !window.Intl.Segmenter) { (function() { var script = document.crea",
     True, "Leading '-->' inline feature-detection script (window.Intl)"),

    # Client-side redirect snippet — ivisa.ru bug June 2026 (leaked into June 8 data)
    ('Redirecting... window.location.replace("/ru"); Redirecting to /ru ...',
     True, "JS redirect snippet (window.location.replace)"),

    # localStorage config parse — heise.de bug June 2026 (leaked into June 8 data)
    ('var config = JSON.parse(window.localStorage["akwaConfig-v2"] || \'{}\') var scheme = config.',
     True, "localStorage JSON.parse JS junk"),

    # WordPress junk (pre-existing catches — must still work)
    ('var theplus_ajax_url = "https://example.com/wp-admin/admin-ajax.php"; var nonce = "x"',
     True, "WordPress admin-ajax JS junk"),

    # ── Structural detection — catches NEVER-BEFORE-SEEN variants by shape, ──
    #    not by specific string. This is what breaks the whack-a-mole cycle.
    ('{"id":123,"name":"iVisa","ok":true}',
     True, "Generic JSON object (braces) — unknown variant"),
    ('<div class="app"><span>iVisa</span></div>',
     True, "HTML markup snippet"),
    ('const f = (x) => { return x + 1; }',
     True, "JS arrow function"),
    ('if (a && b || c) { doThing(); }',
     True, "JS boolean operators + braces"),
    ('See https://a.com/x and https://b.com/y and https://c.com/z',
     True, "Dumped multi-URL list"),

    # Real text — must NOT be flagged as junk
    ("iVisa makes visa applications fast, easy, and secure for travelers worldwide.",
     False, "Normal article snippet — must NOT be flagged as junk"),

    ("No, iVisa is a legitimate service trusted by millions of travelers.",
     False, "Debunking snippet — must NOT be flagged as junk"),

    # Real reviews with parentheses / symbols — must NOT trip the broadened detector
    ("Through the app, cost was around $80 for a 24-hour application (Standard is NOT an ETA).",
     False, "Real app review with parentheses — must NOT be flagged as junk"),

    ("Careful! My mum was sent this app by a travel agent, but she ended up paying 160$ CAD.",
     False, "Real cautionary review — must NOT be flagged as junk"),

    ("The iVisa app is not affiliated with, endorsed by, or representing any government or embassy.",
     False, "Standard disclaimer copy — must NOT be flagged as junk"),

    # Multilingual prose — structural detection must be language-agnostic.
    # These are real non-English snippets that MUST survive (localized keywords).
    ("iVisaを使えば、ETAやeVisa、ESTAなどの渡航書類をオンラインで簡単に申請できます。",
     False, "Japanese app description — must NOT be flagged as junk"),
    ("Mit iVisa kannst du dein UK ETA, Neuseeland-Visum und weitere Reisedokumente online beantragen.",
     False, "German app description — must NOT be flagged as junk"),
    ("iVisa semplifica e accelera il processo di richiesta del visto con un sistema online sicuro.",
     False, "Italian app description — must NOT be flagged as junk"),
    ("Easily apply for travel visas and documents like ETA, eVisa, ESTA, NZeTA & more.",
     False, "Real snippet with single ampersand — must NOT be flagged as junk"),
]

print("  8a. Junk snippet detector:")
for snippet, expect_junk, desc in JUNK_SNIPPET_TESTS:
    got_junk = _is_junk_snippet(snippet)
    ok = got_junk == expect_junk
    status = PASS if ok else FAIL
    label = "junk" if expect_junk else "clean"
    results.append((status, f"Junk detect [{label}]: {desc}", f"got_junk={got_junk} expected={expect_junk}"))
    print(f"    {status}  [{label}] {desc}")
    if not ok:
        print(f"          got_junk={got_junk}, expected={expect_junk}")
        print(f"          snippet: {snippet[:80]}")

# ── 8b. Sentiment classifier — end-to-end cases ───────────────────────────────
# Each row is a real example that has appeared in a live report.
# Add new rows whenever a classification bug is reported — never delete old ones.
SENTIMENT_TESTS = [
    # (domain, title, snippet, expected, description)

    # ── Cases from June 2026 bugs ────────────────────────────────────────────
    # heise.de: "Consumer advice center warns of UK travel permit scam"
    # Bug: "warns" (verb) was missing from NEGATIVE_TEXT_SIGNALS; only "warning" (noun) was there
    ("heise.de",
     "iVisa.com — Consumer advice center warns of UK travel permit scam",
     "The consumer advice center has flagged iVisa.com in connection with a UK travel permit scam.",
     "negative", "heise.de warns-of-scam (consumer protection warning)"),

    # Reddit "Was using ivisa a mistake" — should be negative (doubt/regret)
    ("reddit.com",
     "Was using iVisa a mistake?",
     "I paid $50 for an e-visa that I could have gotten for free. Feeling ripped off.",
     "negative", "Reddit 'mistake' thread — doubt/regret framing"),

    # JSON-LD snippet cleared → re-evaluated on domain alone (help.ivisa.com = owned → positive)
    ("help.ivisa.com",
     "iVisa Help Center",
     '{"@context":"https://schema.org","@type":"WebSite","name":"iVisa Help Center"}',
     "positive", "help.ivisa.com with JSON-LD snippet → cleared → owned domain → positive"),

    # play.google.com WIZ blob cleared → owned domain → positive
    ("play.google.com",
     "iVisa: ETA, eVisa, ESTA, Visa - Apps on Google Play",
     'window.WIZ_global_data = {"AfY8Hf":false,"DMjf6c":false}',
     "positive", "play.google.com WIZ blob → cleared → owned domain → positive"),

    # ── Existing regression cases ────────────────────────────────────────────
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

print("  8b. Sentiment classifier:")
for domain, title, snippet, expected, desc in SENTIMENT_TESTS:
    # Apply sanitization exactly as the pipeline does
    clean_title   = "" if _is_domain_title(title, domain) else title
    clean_snippet = "" if _is_junk_snippet(snippet) else snippet
    result = _classify_result(domain, clean_title, clean_snippet)
    ok = result == expected
    status = PASS if ok else FAIL
    results.append((status, f"Sentiment: {desc}", f"got={result} expected={expected}"))
    print(f"    {status}  {desc}")
    if not ok:
        print(f"          got '{result}', expected '{expected}'")


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

        # ── TRIPWIRE ──────────────────────────────────────────────────────────
        # Parse the embedded REPORT_DATA and run the REAL junk detector over every
        # scraped snippet/title field. If any survived the safety gate, fail loudly
        # here (runs as a CI pre-flight) so a broken report is never published.
        # We use _is_junk_snippet (not naive substring matching) so legitimate
        # prose — e.g. an LLM saying "within their policy window." — never trips it.
        import re as _re2, json as _json2
        m = _re2.search(r"const REPORT_DATA = (\{.*?\});\n", content, _re2.DOTALL)
        if m:
            payload = _json2.loads(m.group(1))
            leaks = []
            def _scan(o, path=""):
                if isinstance(o, dict):
                    s = o.get("snippet")
                    if isinstance(s, str) and s.strip() and _is_junk_snippet(s):
                        leaks.append((path, s[:60]))
                    t = o.get("title")
                    if isinstance(t, str) and _is_junk_snippet(t):
                        leaks.append((path+"/title", t[:60]))
                    for k, v in o.items():
                        _scan(v, path+"/"+str(k))
                elif isinstance(o, list):
                    for i, x in enumerate(o):
                        _scan(x, f"{path}[{i}]")
            _scan(payload)
            if leaks:
                raise Exception(
                    f"Junk leaked into report payload after safety gate: {leaks[:3]} — do NOT publish."
                )

    return f"{size_kb} KB, all sections present, no junk in payload, no unreplaced placeholders"

check("HTML report generation + junk tripwire", check_report_gen)


# ── 10. Snippet coverage in sample data ──────────────────────────────────────
print(f"\n{SEP}")
print("  10. Snippet Coverage (SERP results must show text)")
print(SEP)

def check_snippet_coverage():
    """
    Every informational keyword must have snippets for at least 50% of results.
    Branded 'iVisa' keyword is exempt — Google serves it as sitelinks/app cards.
    If this fails, the SerpAPI organic fallback in fetch_serp.py is broken.
    Uses the most recent historical run (real data), not synthetic sample_data.json.
    """
    import json, pathlib
    from scripts.config import HISTORICAL_DIR, SAMPLE_DATA_FILE

    # Prefer most recent real run; fall back to sample data with lower bar
    hist_files = sorted(pathlib.Path(HISTORICAL_DIR).glob("*.json"), reverse=True)
    if hist_files:
        data_file = hist_files[0]
        is_sample = False
    else:
        data_file = SAMPLE_DATA_FILE
        is_sample = True

    with open(data_file, "r") as f:
        data = json.load(f)

    if is_sample:
        return "No historical run data yet — skipping (sample_data.json has no real snippets)"

    serp_results = data.get("serp_data", {}).get("results", {})
    if not serp_results:
        return "No SERP results in sample data — skipping"

    # Exempt branded single-word query: Google serves sitelinks there, not standard organic
    EXEMPT_KEYWORDS = {"iVisa", "ivisa"}
    MIN_COVERAGE = 0.50  # at least 50% of results must have a snippet

    failures = []
    checked = 0

    for country_code, kw_results in serp_results.items():
        for keyword, results in kw_results.items():
            if keyword.strip().lower() in {k.lower() for k in EXEMPT_KEYWORDS}:
                continue
            if not results:
                continue
            has_snip = sum(1 for r in results if r.get("snippet", "").strip())
            coverage = has_snip / len(results)
            checked += 1
            if coverage < MIN_COVERAGE:
                failures.append(
                    f"'{keyword}' ({country_code}): {has_snip}/{len(results)} snippets ({coverage:.0%})"
                )

    if failures:
        raise Exception(
            f"Low snippet coverage on {len(failures)} keyword(s) — "
            f"SerpAPI fallback may be broken:\n    " + "\n    ".join(failures[:5])
        )

    return f"{checked} keyword/country combos checked — all above {MIN_COVERAGE:.0%} threshold"

check("Snippet coverage in sample data", check_snippet_coverage)


# ── 11. Gemini model is not a preview/dated model ─────────────────────────────
print(f"\n{SEP}")
print("  11. Gemini model safety check")
print(SEP)

def check_gemini_model():
    from scripts.config import GEMINI_MODEL
    import re
    # Preview models contain a date like -05-20 or "preview" — they expire silently
    if re.search(r'preview|\d{2}-\d{2}', GEMINI_MODEL, re.IGNORECASE):
        raise Exception(
            f"GEMINI_MODEL='{GEMINI_MODEL}' looks like a preview/dated model. "
            f"Update to a stable model (e.g. 'gemini-2.0-flash') in scripts/config.py"
        )
    return f"model='{GEMINI_MODEL}' — no preview/date suffix ✓"

check("Gemini model is stable (not preview)", check_gemini_model)


# ── 12. Formula weights sum to 1.0 ───────────────────────────────────────────
print(f"\n{SEP}")
print("  12. Formula & Country Weights")
print(SEP)

def check_weights():
    from scripts.config import (
        WEIGHT_SERP, WEIGHT_AI_OVERVIEW, WEIGHT_LLM, WEIGHT_EARNED_MEDIA, COUNTRIES
    )
    formula_total = WEIGHT_SERP + WEIGHT_AI_OVERVIEW + WEIGHT_LLM + WEIGHT_EARNED_MEDIA
    if abs(formula_total - 1.0) > 0.001:
        raise Exception(
            f"CSOV formula weights sum to {formula_total:.4f}, not 1.0 — "
            f"scores will be wrong. Fix in scripts/config.py."
        )
    country_total = sum(c["weight"] for c in COUNTRIES.values())
    # Country weights intentionally sum to ~0.95 (not 1.0) — the scoring
    # functions divide by actual sum so this is handled. Warn if badly off.
    if abs(country_total - 1.0) > 0.10:
        raise Exception(
            f"Country weights sum to {country_total:.3f} — too far from 1.0. "
            f"Check COUNTRIES weights in scripts/config.py."
        )
    return (
        f"CSOV weights = {formula_total:.2f} ✓ | "
        f"country weights = {country_total:.2f} (normalised in scoring)"
    )

check("CSOV formula + country weights", check_weights)


# ── 13. Historical data integrity ─────────────────────────────────────────────
print(f"\n{SEP}")
print("  13. Historical Data Integrity")
print(SEP)

def check_historical_data():
    import json, pathlib
    from datetime import date, timedelta
    from scripts.config import HISTORICAL_DIR

    hist_dir = pathlib.Path(HISTORICAL_DIR)
    files = sorted(hist_dir.glob("*.json"), reverse=True)
    if not files:
        return "No historical files yet — first run will create them"

    # Latest file must be valid JSON with a csov_score
    latest = files[0]
    with open(latest) as f:
        data = json.load(f)

    if "csov_score" not in data:
        raise Exception(f"{latest.name} is missing 'csov_score' field — corrupt snapshot?")

    score = data["csov_score"]
    if not (0 <= score <= 100):
        raise Exception(f"{latest.name} has invalid csov_score={score} (must be 0–100)")

    # Warn if latest file is older than 8 days (missed a Monday run)
    try:
        file_date = date.fromisoformat(latest.stem)
        days_old = (date.today() - file_date).days
        if days_old > 8:
            raise Exception(
                f"Latest snapshot is {days_old} days old ({latest.name}) — "
                f"a Monday run may have been missed or failed silently."
            )
    except ValueError:
        pass  # filename isn't a date — skip age check

    return f"{len(files)} snapshots, latest={latest.name}, score={score}"

check("Historical data integrity", check_historical_data)


# ── 14. Sentiment distribution sanity ────────────────────────────────────────
print(f"\n{SEP}")
print("  14. Sentiment Distribution Sanity")
print(SEP)

def check_sentiment_distribution():
    import json, pathlib
    from scripts.config import HISTORICAL_DIR

    files = sorted(pathlib.Path(HISTORICAL_DIR).glob("*.json"), reverse=True)
    if not files:
        return "No historical data yet — skipping"

    with open(files[0]) as f:
        data = json.load(f)

    serp = data.get("serp_data", {}).get("results", {})
    sentiments = []
    for country in serp.values():
        for kw_results in country.values():
            for r in kw_results:
                s = r.get("sentiment")
                if s:
                    sentiments.append(s)

    if len(sentiments) < 10:
        return f"Only {len(sentiments)} classified results — not enough to check distribution"

    from collections import Counter
    counts = Counter(sentiments)
    total = len(sentiments)
    pos_pct = counts.get("positive", 0) / total
    neg_pct = counts.get("negative", 0) / total

    # If >90% are all one class, classification is probably broken
    if pos_pct > 0.90:
        raise Exception(
            f"{pos_pct:.0%} of results are positive — classification looks broken "
            f"(positive signals matching everything)"
        )
    if neg_pct > 0.90:
        raise Exception(
            f"{neg_pct:.0%} of results are negative — classification looks broken "
            f"(negative signals matching everything)"
        )

    return (
        f"{total} results: {pos_pct:.0%} positive, "
        f"{counts.get('neutral',0)/total:.0%} neutral, "
        f"{neg_pct:.0%} negative — distribution looks healthy"
    )

check("Sentiment distribution sanity", check_sentiment_distribution)


# ── 15. Report file size sanity ───────────────────────────────────────────────
print(f"\n{SEP}")
print("  15. Report File Size")
print(SEP)

def check_report_size():
    import pathlib
    from scripts.config import DOCS_DIR

    index = pathlib.Path(DOCS_DIR) / "index.html"
    if not index.exists():
        raise Exception("docs/index.html does not exist — report was never generated")

    kb = index.stat().st_size // 1024
    if kb < 200:
        raise Exception(
            f"docs/index.html is only {kb} KB — expected > 200 KB. "
            f"A major section is likely missing (SERP table, LLM data, etc.)"
        )
    return f"{kb} KB ✓"

check("Report file size > 200 KB", check_report_size)


# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
passed   = sum(1 for r in results if r[0] == PASS)
failed   = sum(1 for r in results if r[0] == FAIL)
warnings = sum(1 for r in results if r[0] == WARN)
total    = len(results)

if failed == 0 and warnings == 0:
    print(f"  {PASS}  ALL {total} CHECKS PASSED — Monday automation is ready!")
elif failed == 0 and warnings > 0:
    print(f"  {WARN}  {passed}/{total} passed, {warnings} warning(s) — pipeline will still run")
    print()
    for status, name, detail in results:
        if status == WARN:
            print(f"       {WARN} {name}: {detail}")
else:
    print(f"  {FAIL}  {failed}/{total} checks FAILED — fix before Monday")
    print()
    for status, name, detail in results:
        if status == FAIL:
            print(f"       {FAIL} {name}: {detail}")
        elif status == WARN:
            print(f"       {WARN} {name}: {detail}")
print(SEP)
sys.exit(0 if failed == 0 else 1)
