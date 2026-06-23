# iVisa CSOV Dashboard — Full Project Context

> **For new Claude sessions:** Read this entire file before doing anything.
> It replaces all memory from previous sessions and is the single source of truth.
> After reading it, you will have full context to continue exactly where we left off.

---

## Who You're Working With

**Paula Votobernales** (paula.votobernales@ivisa.com)
Brand & Creative Manager at iVisa.com, part of the Growth team.

**Her goal:** Increase brand-driven and brand-assisted Growth Service Bookings by strengthening trust, expanding high-intent reach, and enabling product launches and acquisition channels to convert more efficiently.

**Her scope:** Social media, online reputation strategy, creatives (video, copy, images).

**Working style:** Fast executor, proactive, non-technical. Always give terminal commands as a single copy-pasteable line. Never multi-line Python in the shell. Use `python3` not `python` (Mac runs Python 3.9 via Xcode). Explain things in plain English, no jargon.

**Brand voice:** Approachable, Reliable, Straightforward. Standard case. Uses contractions.

**Brand identity:** Manrope font · #00EA80 hero green · #0A2540 navy · #08ADE4 sky blue.

---

## What This Project Is

An automated **weekly CSOV (Credibility Share of Voice) dashboard** for iVisa. It runs every Monday at 07:00 UTC via GitHub Actions, fetches live data from four sources, calculates a composite reputation score, generates an HTML report, publishes it to GitHub Pages, and sends a Slack notification.

**The score measures iVisa's online reputation** — how positive, neutral, or negative the results are for brand-intent searches across 10 countries and 11 keywords.

---

## Repo & Access

| | |
|---|---|
| **GitHub** | https://github.com/paulavotobernales-94/-ivisa-csov |
| **GitHub Pages (live report)** | https://paulavotobernales-94.github.io/-ivisa-csov |
| **Local folder** | `~/Desktop/Reputation and PR/ivisa-csov/` |

---

## CSOV Formula

```
CSOV = (SERP × 0.35) + (AI_Overview × 0.25) + (LLM × 0.25) + (Earned_Media × 0.15)
```

`SCORING_VERSION = "1.0"` — governs this weighting scheme. Do not change weights without updating this version.

---

## Run Commands (all from the repo folder)

```bash
# Full live run + Slack notification
python3 main.py --slack

# Dry run — no API calls, uses sample data
python3 main.py --dry-run

# Pre-Monday validation (run before every Monday)
python3 scripts/health_check.py
```

---

## API Keys & Services

All keys live in `.env` in the repo root AND in GitHub repo Secrets (for Actions).

| Key | Service | Notes |
|---|---|---|
| `SEMRUSH_API_KEY` | SERP rankings | |
| `AHREFS_API_KEY` | SERP rankings | Returns 404 for SERP endpoint — pipeline falls back to SerpAPI automatically |
| `CLAUDE_API_KEY` | LLM sentiment scoring | |
| `GEMINI_API_KEY` | LLM monitoring | Free tier — daily quota can exhaust mid-run, pipeline handles gracefully |
| `SERPAPI_KEY` | Google SERP + AI Overviews + Earned Media | Renewal: June 26, 2026 |
| `SLACK_WEBHOOK_URL` | Slack notifications | |
| `GITHUB_PAGES_URL` | Set in GitHub repo vars (not secrets) | |

**Models:**
- Claude: `claude-haiku-4-5-20251001`
- Gemini: `gemini-2.0-flash` — **ALWAYS use stable models with no date suffix.** Preview models (e.g. `gemini-2.5-flash-preview-05-20`) expire silently every ~3 months. If Gemini returns "model not found", update `GEMINI_MODEL` in `scripts/config.py`. Reference: https://ai.google.dev/gemini-api/docs/models

---

## Countries Tracked (10)

| Code | Country | Weight | hl | Notes |
|---|---|---|---|---|
| us | United States | 35% | en | English |
| gb | United Kingdom | 14% | en | English |
| au | Australia | 10% | en | English |
| de | Germany | 8% | de | Localized keywords ✓ |
| ca | Canada | 7% | en | English |
| fr | France | 7% | fr | Localized keywords ✓ |
| jp | Japan | 4% | ja | Localized keywords ✓ (10 unique kw) |
| nl | Netherlands | 4% | nl | Localized keywords ✓ |
| it | Italy | 3% | it | Localized keywords ✓ |
| es | Spain | 3% | es | Localized keywords ✓ (replaced Switzerland, June 12 2026) |

**✅ DONE (June 12 2026):** Localized per-country keywords are live. `scripts/config.py` now has `KEYWORDS_BY_COUNTRY` (per-country lists); `fetch_serp.py` and `fetch_ai_overviews.py` iterate per-country keywords; SerpAPI gets the local `hl=` language per country (`serpapi_hl` field in `COUNTRIES`); and a Claude multilingual fallback (`_classify_with_claude` in `fetch_serp.py`) classifies non-English results the English rules can't. **Switzerland was replaced by Spain** (Spain inherited Switzerland's 3% weight — weights still sum to 0.95, formula unchanged).

---

## Keywords Tracked (per-country, localized)

Each country has its own keyword list in `KEYWORDS_BY_COUNTRY` (`scripts/config.py`) — 11 keywords each, except Japan (10 unique). English markets (US/UK/AU/CA) use English keywords (the four lists differ slightly); DE/FR/JP/NL/IT/ES use native-language keywords from Paula's June 2026 keyword sheet. The legacy global `KEYWORDS` list is kept only as a fallback for any country missing from the dict.

**Source sheet:** "Keywords top 10 countries csov report" (Google Sheets). Cleanups applied vs. raw sheet: Japan deduped (`ivisaとは` appeared twice → 10 unique); NL row 11 `s iVisa…` → `is iVisa…`; France/Spain typos fixed in-sheet by Paula.

---

## File Structure

```
main.py                          Entry point — orchestrates all fetches, scoring, report
scripts/config.py                All constants: keywords, countries, weights, API keys, models
scripts/fetch_serp.py            SERP data via SEMrush + Ahrefs + SerpAPI organic fallback
scripts/fetch_ai_overviews.py    Google AI Overview scraping via SerpAPI
scripts/fetch_llm.py             Claude + Gemini LLM monitoring with retry logic
scripts/fetch_earned_media.py    Earned media via SerpAPI (news, blogs, Reddit, YouTube, IG, TikTok)
scripts/calculate_csov.py        Score calculation + action items
scripts/generate_report.py       HTML report generation + archive index
scripts/send_slack.py            Slack webhook notification
scripts/health_check.py          Pre-run validation — 15 checks including classifier unit tests
scripts/backfill_historical.py   Historical backfill for Jan–May 2026
data/historical/                 Weekly JSON snapshots (one file per run date)
data/sample_data.json            Synthetic data used for dry runs and report generation tests
docs/                            Generated HTML reports (served via GitHub Pages)
docs/index.html                  Latest weekly report
docs/reports/index.html          Archive page — links to all past reports
docs/ivisa_logo.png              Real iVisa logo (transparent background PNG)
.github/workflows/weekly-report.yml   GitHub Actions — Monday 07:00 UTC automation
```

---

## Period Framework

- **Period 1 (Feb–May 2026):** DROPPED from report display. Data was unreliable because scoring rules changed mid-period. Historical JSON files are kept in `data/historical/` but Period 1 is never shown in charts, comparisons, or scoring.
- **Period 2 (Jun–Sep 2026):** Active tracking period. Target: 70+ across all four components.

**Never re-add Period 1 comparisons to any section of the report or scoring logic.**

---

## Live Scores (for reference)

| Date | CSOV | SERP | AIO | LLM | EM | Notes |
|---|---|---|---|---|---|---|
| May 29 2026 | 56.0 | 59.0 | 51.2 | 49.2 | 68.2 | |
| June 3 2026 | 55.7 | — | — | — | — | |
| June 4 2026 | 56.0 | — | — | — | — | |
| June 8 2026 | **55.7** | 59.9 | 49.2 | 49.5 | 67.3 | **Canonical score.** Two runs happened (9:53 AM manual + 8:30 PM delayed cron). 8:30 PM run overwrote the JSON and HTML. 55.7 is the stored, accepted baseline. |

---

## Sentiment Classification Rules (CRITICAL — read carefully)

These rules were developed through multiple iterations. Do not revert them.

### Core philosophy
Classify from **title + snippet text content**, NOT from domain name alone.
- Trustpilot, Sitejabber, Tripadvisor → NOT automatically positive. They surface 1-star reviews.
- Neutral = mixed signals (both positive and negative present).
- Editorial/press domains with no negative signals → positive (earned press coverage).

### iVisa-owned domains (always positive unless complaint language present)
`ivisa.com`, `play.google.com`, `apps.apple.com`, `linkedin.com`, `facebook.com`, `instagram.com`, `twitter.com`, `x.com`, `youtube.com`

### Always-negative domains (structural complaint sites)
`bbb.org`, `ripoffreport.com`, `scamalert.com`, `complaints.com`, `pissedconsumer.com`, `complaintsboard.com`, `scamadviser.com`

### Review aggregators → excluded from earned media (NOT earned media)
`trustpilot.com`, `sitejabber.com`, `tripadvisor.com`, `yelp.com`

### Junk snippet detection (`_is_junk_snippet()`)
Clear to `""` before classification if snippet contains:
- JSON-LD structured data: `{"@context"` or `"@type"` when snippet starts with `{`
- Google WIZ blobs: `window.WIZ_global_data`, `window.google`
- Any `window.SOMETHING = {` pattern
- WordPress: `wp-admin`, `_nonce`, `admin-ajax`
- Multiple `var ` assignments
- Code character ratio > 15%
- **(June 11 2026) Generalized JS detection:** leading `-->`, `<!--`, `//`; any browser-object property access (`window.`, `document.`, `navigator.`, `location.` followed by a property); client-side redirects (`location.replace`, `.location.href`); inline `(function(`, `function(`, `JSON.parse(`. These caught variants that hardcoded patterns missed: `--> if (!window.Intl...` (heise.de / ivisaconsulting.com) and `Redirecting... window.location.replace("/ru")` (ivisa.ru).

**This sanitization must happen BEFORE enrichment fallbacks AND in the SerpAPI organic fallback output.**

**(June 11 2026) Sanitization now also runs at INGESTION** — `_fetch_semrush_keyword()` and `_fetch_ahrefs_keyword()` clear junk snippets/domain-titles before classification. Previously sanitization only ran inside `enrich_with_serpapi_organic()`, and only for keyword/country pairs present in the organic feed — so junk from SEMrush-only keywords leaked straight into storage and the report (root cause of the recurring play.google.com / "google play SERP" breakage).

### Junk handling = 3 DURABLE LAYERS (June 11 2026 — why it kept recurring before)
The bug recurred ~4 times because every prior fix was a **denylist** of known-bad strings — a new junk shape always slipped through. The fix is structural + defense-in-depth, so it stops being whack-a-mole:

1. **Structural detection (root cause).** `_is_junk_snippet()` now rejects by the *shape* of code/JSON/HTML, not by specific strings: any `{` `}` (JSON/JS objects), `</` `/>` or `<tag` (HTML), `=>` `();` (JS), `&&` `||`, ≥2 `://` (dumped URLs), and code-only character density. Human prose **in any language** (English, German, Japanese, Italian) never has these, so never-before-seen junk variants are caught automatically. Precise patterns (`window\.\w`) mean legit prose like "within their policy window." is NOT flagged.
2. **Permanent gate in the report generator.** `_sanitize_report_data()` in `generate_report.py` runs over the ENTIRE payload right before `json.dumps`. Every snippet/title passes the junk filter + app-store fallbacks here. No matter what the fetch layer stored, junk physically cannot reach the published page. Text-only — never recomputes sentiment or scores.
3. **CI tripwire (fails loudly before publish).** `health_check.py` Section 9 parses the rendered `REPORT_DATA` and runs the real `_is_junk_snippet()` over every snippet/title; if any survived the gate it raises, failing the GitHub Actions pre-flight so a broken report is never published or Slacked. Uses the real detector (not substring matching) so LLM prose containing the word "window." never trips it.

**Only scraped `snippet`/`title` fields can carry junk.** LLM text fields (`gemini_response`, etc.) are generated prose and are intentionally NOT sanitized.

### Scam-question title rule
If title contains `"scam?"` AND snippet does NOT contain debunking signals → force `negative`.
"Was using iVisa a mistake" → `negative` (regret framing).

### Title subtitle detection
Positive words after `?` in title → `positive` even if title contains "scam".
Example: "Is iVisa a Scam? Inside the Refund Policy That's Restoring..." → `positive`.

### Removed from POSITIVE_TEXT_SIGNALS (caused false positives)
`"trust"` (single word), `"my experience"`, `"helpful"`, `"convenient"`, `"official"`, `"verified"`, `"it works"`

### Consumer protection / authority warnings (added June 2026)
Added to NEGATIVE_TEXT_SIGNALS in `fetch_serp.py` AND NEGATIVE_SIGNALS in `fetch_earned_media.py`:
`"warns of"`, `"warns users"`, `"warns travellers"`, `"warns travelers"`,
`"consumer advice center"`, `"consumer advice centre"`, `"consumer protection warns"`,
`"travel permit scam"`, `"permit scam"`

**Why:** "warns" (verb) was missing — only "warning" (noun) was covered. heise.de article "Consumer advice center warns of UK travel permit scam" was not classifying negative.

### Disclaimer phrases ("not affiliated with government")
These are standard legal compliance copy on all third-party visa services.
Only classify negative when ALSO paired with actual complaint language (scam, fraud, misleading, etc.).

---

## SERP Data Source Behaviour (important quirks)

### Ahrefs 404
Ahrefs returns 404 for the SERP endpoint. Pipeline falls back to SerpAPI organic automatically. This is expected, not a bug.

### SEMrush vs SerpAPI organic disagreement
Google serves branded "iVisa" keyword as sitelinks/app cards, not standard organic results. SEMrush's database tracks different URLs than what SerpAPI organic captures live — they often disagree completely on which domains rank.

**Fix:** After enrichment, if a keyword's SEMrush/Ahrefs results have < 40% snippet coverage, discard that data and use live SerpAPI organic results instead. These match what Google actually shows.

**Never re-add logic that trusts SEMrush position data for display when SerpAPI organic disagrees.** SerpAPI organic is the source of truth for what users actually see.

**This fallback also sanitizes junk snippets** from organic results before storing them.

### Germany / non-English country SERP mismatch
Same root cause as branded "iVisa" keyword — SEMrush database diverges from live Google.de results. The < 40% snippet coverage fallback handles this. When localized keywords are implemented, add `hl=` language parameter to SerpAPI calls per country.

---

## Gemini API — DISABLED (Claude-only LLM, June 15 2026)

**`USE_GEMINI = False` in `config.py`.** Decision (June 15 2026): the `GEMINI_API_KEY`'s free tier consistently refuses EVERY call with RESOURCE_EXHAUSTED — first call, every run, even the non-grounded fallback retry — i.e. Google grants this project ~zero free Gemini quota. Rather than show empty "No response" columns, the **LLM score is now Claude-only**. No score change resulted (Gemini was already contributing nothing). What this does:
- `fetch_llm.py` `_get_gemini_client()` returns None when `USE_GEMINI` is False → no Gemini calls.
- `generate_report.py` hides the Gemini table column when there's no Gemini data (`.gemini-col` + `hasGemini` JS toggle); LLM copy says "Scored by Claude".
- `check_completeness.py` treats Claude-only as OK (no false "Gemini missing" warning); flags MISSING only if Claude itself fails.
- **TO RE-ENABLE:** set `USE_GEMINI = True` after enabling billing on the Google Cloud project behind `GEMINI_API_KEY` (gemini-2.0-flash ≈ pennies/month at this volume). The report auto-shows the Gemini column again once data is present.

### (Historical) Free-tier behaviour, kept for reference
Gemini 2.0 Flash free tier (per **project**, resets midnight Pacific): ~1,500 requests/day, ~15/min. A single report run (~50 Gemini calls) is well within that — so a normal daily cap should NOT block a run.

**⚠️ The real blocker (found June 12 2026): Google-Search GROUNDING quota.** The brand/general queries call Gemini with `with_grounding=True` (GoogleSearch tool) so it can cite live sources. Grounding has its **own, much smaller** free quota, separate from the 1,500/day text quota. When it's exhausted, EVERY grounded call 429s from the very first one — even on a day with no prior runs — which is exactly the "Gemini did nothing again" symptom. The error is still `RESOURCE_EXHAUSTED` / `free_tier`, so it's easy to mistake for "daily quota used up." It is NOT your usage.

**Fix (June 12 2026): grounding fallback in `_ask_gemini`.** If a *grounded* call is quota-blocked, it retries the SAME query WITHOUT grounding — using the generous text quota — so Gemini still produces a response, gets sentiment-scored, and averages with Claude as intended. Only the cited source links are lost. Gemini is disabled for the run **only if a non-grounded call is also quota-blocked** (i.e. the core text quota is genuinely gone). The first such failure logs the FULL error (names `…PerDay` / `…PerMinute` / grounding) once, then a run-level flag stops further doomed calls.

**Guaranteed fix if you also want the source links back:** enable billing on the Google Cloud project for this API key (lifts free-tier caps).

**Distinguish from transient rate limits:** `resource_exhausted` / `free_tier` → grounding fallback, then skip. `rate` / `429` → retry with 15s backoff.

**Completeness:** the data-completeness gate now reports LLM as PARTIAL (warn) when only one model answered, MISSING (block + no Slack + non-zero exit) when neither did — so a hollow LLM score can't ship silently.

---

## AI Overview Scoring

- No AI Overview appearing = neutral (50), not a problem.
- No 0.3 penalty for "not cited" — sentiment of what appears is what matters.

---

## Earned Media — What Counts

Earned media = what **other** people/outlets say about iVisa. iVisa's OWN posts never count.

**Sources that count:** Google News, travel editorial press, Reddit (excl. r/ivisa), YouTube, Instagram, TikTok, Pinterest — **only from accounts iVisa does NOT own.**

**Excluded — review aggregators:** Trustpilot, Sitejabber, TripAdvisor, BBB, Yelp — user-review platforms, not earned media.

### iVisa-owned social accounts (EXCLUDED from earned media — June 15 2026)
Posts from these are iVisa's own content, not earned media. Enforced in `fetch_earned_media.py` via `IVISA_OWNED_SOCIAL` (URL-substring match in `_is_ivisa_owned`):

- Instagram: https://www.instagram.com/ivisa_travel/
- TikTok: https://www.tiktok.com/@ivisa_travel
- YouTube: https://www.youtube.com/@iVisa_travel
- Facebook: https://www.facebook.com/iVisaTravel/
- Pinterest: https://www.pinterest.com/iVisa__Travel/
- LinkedIn: https://www.linkedin.com/company/ivisa/

(Previously only `ivisa.com`, `blog.ivisa.com`, `help.ivisa.com`, and `r/ivisa` were excluded — so iVisa's own `@ivisa_travel` TikTok/IG posts were wrongly counting as earned media. Fixed June 15 2026.)

---

## Report Design Rules

- **Header:** White background so the black+green iVisa logo shows correctly.
- **Colors:** #00EA80 green, #0A2540 navy, #08ADE4 sky blue, Manrope font.
- **SERP table:** Google-style — domain small above title, title is clickable blue link, snippet below. Paginated 5+5.
- **Past Reports dropdown:** Top-right of header. Click to expand list of past weekly reports.
- **Logo:** Real PNG from `docs/ivisa_logo.png` (transparent background).
- **"What's Driving the Score" section:** Always visible, standalone.

---

## Code Rules

### No nested f-strings for multi-line HTML
Use a placeholder string and `.replace()` instead.
**Why:** Python raises SyntaxError for f-strings containing the same quote type as the outer string.

### None-type refactor audit
When a value changes from `float` to `float | None`, audit every downstream consumer: return statements, formatters, report renderers, fallback dicts. Grep every call site. Verify `round()`, `str()`, arithmetic won't be called on None unguarded.
**Why:** June 2026 — changing AI Overview score from `50.0` to `None` for missing data caused `round(score, 2)` to crash, killing the entire AI Overview fetch and SERP enrichment, producing an empty report.

### Python compatibility
Paula's Mac runs Python 3.9 (Xcode). All scripts need `from __future__ import annotations` at top.

### Terminal commands for Paula
Always single copy-pasteable line. Multi-line Python with `"` quotes causes `dquote>` shell error.
Use `python3` not `python`.

---

## Health Check (15 checks + classifier unit tests)

`python3 scripts/health_check.py` — run before every Monday.

Runs automatically in GitHub Actions as a pre-flight step before the pipeline.

**Section 8 contains classifier unit tests** — explicit cases for every junk pattern and sentiment scenario that has appeared in a live report. Add a new test case any time a classification bug is found. The pattern is: write the failing test first, then fix the code, then verify it passes.

Current test cases cover:
- JSON-LD schema.org blobs (help.ivisa.com bug June 2026)
- `window.WIZ_global_data` blobs (play.google.com bug June 2026)
- `window.google` assignment
- WordPress admin-ajax junk
- heise.de "Consumer advice center warns of UK travel permit scam" → negative
- Reddit "Was using iVisa a mistake?" → negative
- help.ivisa.com with JSON-LD → cleared → owned domain → positive
- Tripadvisor scam-question thread → negative
- Debunking article with positive subtitle → positive
- Structural complaint domain → negative
- And more

---

## GitHub Actions Automation

Runs every Monday at 07:00 UTC (09:00 Madrid CEST / 08:00 Madrid CET).
Can be triggered manually via `workflow_dispatch` with optional `dry_run` input.

**Timezone note:** `0 7 * * 1` = 9 AM Madrid in summer (CEST, UTC+2). In winter (CET, UTC+1) this fires at 8 AM Madrid instead — accepted trade-off, not a bug.

**Known reliability issue (mitigated June 12 2026):** GitHub's cron is best-effort and the top of the hour (`0`) is the most over-subscribed slot — that's why a single `0 7 * * 1` run often fired hours late or "next day." **Fix:** the workflow now has THREE staggered off-peak cron slots — `5 7`, `35 7`, `5 8` (≈09:05 / 09:35 / 10:05 Madrid CEST). The idempotency guard means only the FIRST slot that succeeds produces/publishes a report; later slots see today's snapshot and exit. If a run FAILS on missing data it does NOT save a snapshot, so the next slot retries cleanly. GitHub still can't guarantee an exact minute, so the manual "Run workflow" button remains the ultimate backup (the guard prevents duplicates). Note: staggered slots are not a hard lock — a rare simultaneous double-fire could double-post, but that's far less likely than the old single-slot misses.

**Steps:**
1. Checkout repo
2. Set up Python 3.11
3. Install dependencies
4. **Pre-flight health check** (warns in CI for API issues, hard-fails only for config errors)
5. Run CSOV pipeline — scheduled cron uses `python main.py --slack`, manual trigger uses `python main.py --slack --force`
6. Commit and push report to `docs/` and `data/historical/`
7. Deploy `docs/` to GitHub Pages

**Idempotency guard (added June 9 2026):** `main.py` checks if `data/historical/YYYY-MM-DD.json` already exists before running. If it does AND the run is a scheduled cron (no `--force`), it exits immediately without fetching data or sending Slack. This prevents duplicate reports when GitHub's delayed cron fires after a manual run.

| How triggered | Blocked if already ran today? |
|---|---|
| Automated Monday cron | ✅ Yes — no duplicate |
| "Run workflow" button in GitHub | ❌ No — always runs (passes `--force`) |
| `python3 main.py --slack` locally | ❌ No — always runs |
| `python3 main.py --slack --force` | ❌ No — always runs |

---

## Known Data Quirks Summary

| Issue | Status |
|---|---|
| Ahrefs API → 404 for SERP endpoint | Expected — pipeline falls back to SerpAPI organic |
| SEMrush vs SerpAPI disagreement on branded "iVisa" keyword | Fixed — < 40% snippet coverage triggers SerpAPI organic fallback |
| Gemini free tier quota exhaustion | Fixed — detects `resource_exhausted` and skips immediately |
| JSON-LD snippets from help.ivisa.com | Fixed — `_is_junk_snippet()` now detects JSON-LD |
| `window.WIZ_global_data` from play.google.com | Fixed — explicitly caught in `_is_junk_snippet()` |
| heise.de "warns of scam" not classifying negative | Fixed — "warns of" added to NEGATIVE_TEXT_SIGNALS |
| Germany / non-English SERP mismatch | Partially fixed by snippet coverage fallback. Full fix pending: localized keywords + `hl=` parameter |
| Non-English countries use English keywords | **PENDING** — Paula to provide localized keyword lists for DE, FR, JP, NL, IT, CH |
| Duplicate Slack reports (cron fires late after manual run) | Fixed June 9 2026 — idempotency guard in main.py, `--force` flag added |
| Main dashboard trend chart shows backfilled May data | **FIXED June 12 2026** — `TREND_CHART_START_DATE = "2026-06-15"` in `config.py`; `main.py` filters history to that date onward. All pre-cutoff snapshots stay on disk, just not plotted. First chart point = Mon June 15 2026 (first final-version run). |

---

## Pending / Deferred Work

### 0. Clean up main dashboard trend chart — ✅ DONE (June 12 2026)
The trend chart + CSV now start at `TREND_CHART_START_DATE` (`config.py`), set to **2026-06-15** — the first Monday with the final keyword/scoring version. `main.py` skips any historical snapshot dated before the cutoff and only adds the current week if it's on/after it. All historical JSON + archived HTML stay on disk; they're just not plotted. (Paula moved the start from June 8 → June 15 so only fully-legit final-version data shows.)

### 1. Localized keywords per country — ✅ DONE (June 12 2026)
Per-country localized keywords are live. `KEYWORDS_BY_COUNTRY` in `config.py`; per-country `hl` via `serpapi_hl`; Claude multilingual fallback in `fetch_serp.py`; Switzerland → Spain (3%). health_check §8c/§8d cover routing + config. See the June 12 update-log entry and the Sentiment Classification section for details.

### 2. Per-country LLM monitoring (DEFERRED — v1.1)
`run_llm_by_country()` exists in `fetch_llm.py` but is NOT called in the pipeline. Runs per-country LLM queries with language-specific prompts and Gemini locale grounding. Kept for v1.1.

### 3. Brand24 / n8n automation
No API available on current plan. Deferred indefinitely.

---

## CONTEXT.md Update Log

| Date | What was added |
|---|---|
| June 5 2026 | Initial creation — full project context from sessions May–June 2026 |
| June 9 2026 | Idempotency guard for duplicate runs, `--force` flag, GitHub Actions workflow update, June 8 canonical score (55.7), trend chart cleanup added as pending task |
| June 11 2026 | Hardened `_is_junk_snippet()` (generalized JS detection) + added ingestion-level sanitization in SEMrush/Ahrefs fetchers — fixes recurring play.google.com / JS-blob leakage into the report. Added 6 new `health_check.py` Section 8 cases. June 8 canonical report/score untouched. |
| June 11 2026 | Added `_APP_STORE_LISTINGS` + `_apply_app_store_fallbacks()` in `fetch_serp.py` (final pass in `enrich_with_serpapi_organic`): iVisa Google Play / App Store results now show canonical title + description instead of a bare "Android Apps on Google Play" card when the live scrape returns a generic title or blank snippet. Only fills gaps — real review snippets/titles untouched. Same fallbacks applied to live June 8 report; score still 55.73. |
| June 11 2026 | **DURABLE junk fix (stops the recurring breakage).** 3 layers: (1) structural detection in `_is_junk_snippet()` — catches junk by code/JSON/HTML shape, language-agnostic, so unseen variants are caught; (2) permanent safety gate `_sanitize_report_data()` in `generate_report.py` runs over the whole payload before render; (3) CI tripwire in `health_check.py` §9 fails the run if any junk survived. Added structural + multilingual (JP/DE/IT) test cases. All text-only — scores untouched. |
| June 12 2026 | **Localized per-country keywords live.** `KEYWORDS_BY_COUNTRY` in `config.py` (11 kw each, Japan 10); `fetch_serp.py` + `fetch_ai_overviews.py` iterate per-country; SerpAPI uses local `hl=` per country (`serpapi_hl`); Claude multilingual fallback `_classify_with_claude()` classifies non-English results the English rules miss (cached, graceful skip if no key). **Switzerland → Spain** (Spain = 3%, weights still 0.95, CSOV formula + SCORING_VERSION unchanged). Report/Slack copy updated; health_check §8c (LLM routing) + §8d (keyword config) added. |
| June 23 2026 | **Concurrency control** added to the workflow (`concurrency: weekly-csov-report, cancel-in-progress:false`) — the 3 staggered cron slots were firing clustered/in-parallel on June 22 and each produced a report ("3 reports, 3 scores"). Now they serialize, so the first produces the report and the rest hit the idempotency guard and exit → exactly one report per Monday. |
| June 23 2026 | **Report display fixes:** (1) AI Overview & LLM expanded cells were capped at `max-height:400px/600px` with `overflow:hidden` → text stayed clipped even after "tap to expand"; now `max-height:none; overflow:visible` so the full text shows. (2) Platform domains with a snippet but no title (e.g. Quora showing "www.quora.com") now get a real title via `_platform_title()` in the report gate. (3) Content-less SERP rows — a bare domain with no title AND no snippet (e.g. an editorial domain SEMrush returned domain-only that couldn't be enriched, like lakelandcurrents) — are now hidden from the table (display-only; iVisa-owned always kept). This is the catch-all for the recurring "empty result / snippet not showing" complaint: prior fixes patched symptoms (junk text → homepage titles → platform snippets); the root cause is SEMrush returning domain-only results with no snippet that live Google results don't match, so there is genuinely no text to show — those rows are now dropped rather than shown empty. |
| June 15 2026 | **Fixed result links 404-ing to "There isn't a GitHub Pages site here".** Cause: some SerpAPI results return a relative Google redirect link (`/goto?url=CAES…`) with no domain; rendered on the Pages PROJECT site (`/-ivisa-csov/`) the browser resolved `/goto…` to the root github.io domain → 404. Fixes: (1) drop relative/non-http links at ingestion in `fetch_ai_overviews.py` (`parse_item`, `_extract_sources`) and `fetch_earned_media.py` (`_parse_organic_results`); (2) render guard in `generate_report.py` — a result links ONLY to an absolute http(s) URL, else falls back to `https://domain`, else renders as plain text (never a relative href). |
| June 15 2026 | **Award/recognition language now classifies positive.** Bug: "iVisa wins Travel Commerce Solution Provider of the Year" (Yahoo Finance / GLOBE NEWSWIRE press release) was scored NEUTRAL — the classifiers' positive-signal lists had trust/quality words but no award terms, and Yahoo Finance wasn't in the editorial-positive domains, so nothing matched → default neutral. Fix: added "wins / winner / award / awarded / award-winning / provider of the year / of the year / leading / top-rated / best-in-class / recognized / honored / breakthrough award / milestone / launches / expands / partners with / named winner" to POSITIVE_SIGNALS in `fetch_earned_media.py` AND POSITIVE_TEXT_SIGNALS in `fetch_serp.py`. Negative signals are still counted first, so a complaint always wins. health_check §8b case added. |
| June 15 2026 | **Gemini disabled → Claude-only LLM** (`USE_GEMINI=False`). Free tier refused every call (RESOURCE_EXHAUSTED, even non-grounded) — Google gives this key ~zero quota. Report hides the Gemini column (`.gemini-col`/`hasGemini`), copy says "Scored by Claude", completeness treats Claude-only as OK. No score change (Gemini was already empty). Re-enable by setting `USE_GEMINI=True` after enabling Google Cloud billing. **Also:** earned media now excludes iVisa-owned social accounts (`IVISA_OWNED_SOCIAL`: @ivisa_travel IG/TikTok/YouTube, /iVisaTravel FB, /iVisa__Travel Pinterest, /company/ivisa LinkedIn). |
| June 15 2026 | **Missing-snippet / generic-homepage-title fix** (the "travelsloth / Lakeland Currents" issue — title shows but no snippet, or a generic site homepage title). Root cause: SEMrush returns many results domain-only (no title/snippet); when enrichment can't match them to live Google organic it fetched the site HOMEPAGE `<title>` or a canned platform title, with no snippet. Fixes: (1) `_PLATFORM_SNIPPETS` in `fetch_serp.py` — neutral one-line descriptors for facebook/instagram/linkedin/youtube/x/reddit/quora/tripadvisor/trustpilot/sitejabber/bbb/yelp/glassdoor/indeed/ivisa.com, filled DISPLAY-ONLY in the report gate (no reclassify, no score change); cut title-but-no-snippet results 103→33 on June 12 data. (2) `_fetch_page_title` now REJECTS a fetched title if neither title nor body mentions "ivisa" — stops generic homepages ("News - Lakeland Currents", "Travelsloth - …", "Home - Adventures & Sunsets") from attaching. Remaining blanks are real titles w/o snippet (YouTube videos, forum posts) which is acceptable. NOTE: there was NO prior travelsloth fix in this file — the app-store fix only covered Google Play/App Store. |
| June 12 2026 | **Data completeness gate** added — `scripts/check_completeness.py` + wired into `main.py`. Detects silently-missing components (esp. LLM: if both Claude+Gemini fail → MISSING/block; if one fails → PARTIAL/warn). Logs a completeness summary every run, refuses Slack when a core component is MISSING, and exits non-zero so the Monday automation can't publish a hollow report. **Also fixed a junk-detector false positive**: the structural bracket/symbol density check flagged real titles like "[UK] iVisa.com UK-ETA is a scam" as junk — removed it (the specific `{}`/tag/operator checks still catch real code). First live test run June 12: CSOV 58.5 (+2.8); SERP 109/109 combos, EM 30 mentions, AIO 46/109; **Gemini free-tier quota exhausted → LLM ran Claude-only (valid, flagged PARTIAL)**; safety gate blanked junk before render; report clean. |

---

*Last updated: June 10, 2026. Update this file any time significant decisions are made, new bugs are fixed, or new features are built.*
