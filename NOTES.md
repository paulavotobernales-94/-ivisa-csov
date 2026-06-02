# iVisa CSOV Dashboard — Dev Notes

Rules and lessons learned to avoid repeating past mistakes.

---

## None-type refactor rule (June 2026)

**Rule:** When changing a value's type from `float` to `float | None` (or any similar widening), treat it as a full type refactor and audit every downstream consumer before finishing the change.

**Checklist:**
- Grep every place the value is used — return statements, formatters, report renderers, fallback dicts
- Verify `round()`, `str()`, arithmetic, and any built-in that doesn't accept None won't be called on it unguarded
- Make sure `except` fallback blocks in `main.py` return the **full expected shape** of a successful response, including all keys (e.g. `organic_data`)
- Mentally trace the None path end-to-end: "what happens when this keyword has no data?" and check every line

**What went wrong:** We changed the AI Overview score from `50.0` to `None` for keywords with no overview. The averaging logic was updated correctly, but the `return` statement still called `round(score, 2)`. This threw a `TypeError` that crashed the entire AI Overview fetch — which also killed SERP enrichment (no `organic_data` passed through), causing blank titles, missing keywords, and an empty AI Overview table in the live report.

---
