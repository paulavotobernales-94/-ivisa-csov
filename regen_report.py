"""Quick script: re-enrich SERP data and regenerate HTML from latest saved data."""
from __future__ import annotations
import json, pathlib, sys, os
sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.chdir(pathlib.Path(__file__).parent)
from dotenv import load_dotenv
load_dotenv()

from scripts.fetch_serp import enrich_with_serpapi_organic
from scripts.generate_report import generate_report
from scripts.config import HISTORICAL_DIR, DOCS_DIR

# Load latest historical file
hfiles = sorted(pathlib.Path(HISTORICAL_DIR).glob("*.json"))
latest = hfiles[-1]
print(f"Loading: {latest}")
data = json.loads(latest.read_text())

# Re-enrich SERP with domain-fallback titles using existing AI overview organic data
# (organic_data not stored; run enrichment with empty organic to trigger fallback titles only)
from scripts.fetch_serp import _PLATFORM_TITLES
results = data.get("serp_data", {}).get("results", {})
fixed = 0
for country, kws in results.items():
    for kw, items in kws.items():
        for item in items:
            if not item.get("title"):
                bare = item.get("domain", "").lstrip("www.").lstrip(".")
                fallback = _PLATFORM_TITLES.get(bare)
                if fallback:
                    item["title"] = fallback
                    fixed += 1
print(f"Applied {fixed} fallback titles")

# Save updated data back
latest.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")

# Regenerate reports
out1 = pathlib.Path(DOCS_DIR) / "index.html"
out2 = pathlib.Path(DOCS_DIR) / f"reports/{latest.stem}.html"
generate_report(data, str(out1))
generate_report(data, str(out2))
print(f"Reports regenerated: {out1}, {out2}")
