"""
config.py — Central configuration for iVisa CSOV Dashboard.
All constants, environment variable loading, and shared data structures.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────────────────────────
SEMRUSH_API_KEY   = os.environ.get("SEMRUSH_API_KEY", "")
AHREFS_API_KEY    = os.environ.get("AHREFS_API_KEY", "")
CLAUDE_API_KEY    = os.environ.get("CLAUDE_API_KEY", "")
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
SERPAPI_KEY       = os.environ.get("SERPAPI_KEY", "")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
GITHUB_PAGES_URL  = os.environ.get("GITHUB_PAGES_URL", "https://paulavotobernales-94.github.io/-ivisa-csov")

# ── CSOV Formula Weights ──────────────────────────────────────────────────────
WEIGHT_SERP         = 0.35
WEIGHT_AI_OVERVIEW  = 0.25
WEIGHT_LLM          = 0.25
WEIGHT_EARNED_MEDIA = 0.15

# ── Keywords Tracked ─────────────────────────────────────────────────────────
KEYWORDS = [
    "iVisa",
    "what is iVisa",
    "iVisa scam",
    "ivisa legit",
    "is ivisa a scam",
    "is ivisa legit",
    "ivisa reviews",
    "ivisa fake or real",
    "is ivisa safe",
    "iVisa affiliated with the gov",
    "ivisa fee",
]

# ── Countries Tracked ─────────────────────────────────────────────────────────
COUNTRIES = {
    "us": {"name": "United States", "flag": "🇺🇸", "semrush_db": "us", "ahrefs_country": "us", "weight": 0.35},
    "gb": {"name": "United Kingdom", "flag": "🇬🇧", "semrush_db": "uk", "ahrefs_country": "gb", "weight": 0.14},
    "au": {"name": "Australia",      "flag": "🇦🇺", "semrush_db": "au", "ahrefs_country": "au", "weight": 0.10},
    "de": {"name": "Germany",        "flag": "🇩🇪", "semrush_db": "de", "ahrefs_country": "de", "weight": 0.08},
    "ca": {"name": "Canada",         "flag": "🇨🇦", "semrush_db": "ca", "ahrefs_country": "ca", "weight": 0.07},
    "fr": {"name": "France",         "flag": "🇫🇷", "semrush_db": "fr", "ahrefs_country": "fr", "weight": 0.07},
    "jp": {"name": "Japan",          "flag": "🇯🇵", "semrush_db": "jp", "ahrefs_country": "jp", "weight": 0.04},
    "nl": {"name": "Netherlands",    "flag": "🇳🇱", "semrush_db": "nl", "ahrefs_country": "nl", "weight": 0.04},
    "it": {"name": "Italy",          "flag": "🇮🇹", "semrush_db": "it", "ahrefs_country": "it", "weight": 0.03},
    "ch": {"name": "Switzerland",    "flag": "🇨🇭", "semrush_db": "ch", "ahrefs_country": "ch", "weight": 0.03},
}

# ── Domain Sentiment Classification ───────────────────────────────────────────
# NOTE: SERP classification no longer uses positive/neutral domain lists.
# Sentiment is determined purely from title + snippet text content.
# Only structural complaint domains are kept as always-negative signals,
# because their purpose is to host complaints regardless of content.
# Trustpilot, Tripadvisor, Sitejabber etc. are NOT in positive_domains —
# they can surface 1-star reviews that are very negative.
NEGATIVE_DOMAINS = [
    "bbb.org", "scamalert.com", "ripoffreport.com",
    "complaints.com", "pissedconsumer.com", "complaintsboard.com",
    "scamadviser.com",
]
# Kept for backward compat / earned media module
POSITIVE_DOMAINS = []
NEUTRAL_DOMAINS  = []

# ── SERP Position → Points Mapping ────────────────────────────────────────────
POSITION_POINTS = {
    1: 5.0, 2: 4.0, 3: 3.5, 4: 3.0, 5: 2.5,
    6: 2.0, 7: 1.5, 8: 1.0, 9: 0.5, 10: 0.25,
}

# ── LLM Queries ───────────────────────────────────────────────────────────────
BRAND_QUERIES = [
    "Is iVisa legit?",
    "Is iVisa a scam?",
    "Should I use iVisa?",
    "Can I trust iVisa?",
    "iVisa reviews - honest opinion",
    "Is iVisa safe to use?",
    "Is iVisa legitimate or a scam?",
    "iVisa customer service quality",
    "Is iVisa real or fake?",
    "Is iVisa affiliated with the government?",
    "Are iVisa processing fees worth it?",
    "iVisa vs applying directly to government",
    "iVisa company reputation",
    "Has anyone successfully used iVisa?",
    "Is iVisa approved by governments?",
    "Does iVisa have hidden fees?",
    "Is iVisa refund policy trustworthy?",
    "Is iVisa better than applying directly?",
    "Is iVisa secure with personal information?",
    "iVisa reliability for visa applications",
]

GENERAL_QUERIES = [
    "Best visa application service",
    "Best visa processing services 2025",
    "Safest way to apply for a visa online",
    "How to apply for a US visa safely",
    "Top rated visa application companies",
    "Most trusted visa services",
    "How to avoid visa scams online",
    "Legitimate visa application websites",
    "Best online visa services for travelers",
    "Visa application service recommendations",
    "Which visa service should I use?",
    "How to get a visa quickly and safely",
    "Best tourist visa application services",
    "Trusted online visa processing",
    "Visa services with good reviews",
    "Online visa application companies comparison",
    "Most reliable passport and visa services",
    "Which visa agency is best?",
    "Travel document services review",
    "Electronic visa application services",
    "e-visa application best service",
    "How to apply for travel documents online",
    "International visa services comparison",
    "Best sites for visa applications",
    "Fastest visa processing services",
    "Visa service with best customer support",
    "Can I apply for visa online safely?",
    "Recommended visa services for travelers",
    "Travel visa services trusted reviews",
    "How do I avoid fake visa websites?",
]

# ── Claude LLM Settings ───────────────────────────────────────────────────────
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
GEMINI_MODEL = "gemini-2.5-flash-preview-05-20"

SENTIMENT_PROMPT_TEMPLATE = (
    "Rate the overall sentiment of this response about iVisa from 0 to 100. "
    "Use this scale strictly: "
    "0-20 = active scam warning or strong negative recommendation (do not use, fraud, dangerous); "
    "21-40 = mostly negative but acknowledges some value; "
    "41-60 = balanced/neutral, lists both pros and cons or gives factual description without strong stance; "
    "61-80 = mostly positive with minor caveats; "
    "81-100 = strongly positive, recommended, trusted. "
    "A response that says iVisa is convenient but expensive with pros and cons should score 41-55. "
    "Respond with a number only:\n\n{text}"
)

# ── Paths ─────────────────────────────────────────────────────────────────────
import pathlib

ROOT_DIR          = pathlib.Path(__file__).parent.parent
DATA_DIR          = ROOT_DIR / "data"
HISTORICAL_DIR    = DATA_DIR / "historical"
DOCS_DIR          = ROOT_DIR / "docs"
EARNED_MEDIA_FILE = DATA_DIR / "earned_media.json"
SAMPLE_DATA_FILE  = DATA_DIR / "sample_data.json"

DEFAULT_EARNED_MEDIA_SCORE = 60
