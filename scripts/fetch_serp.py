from __future__ import annotations

"""
fetch_serp.py — Pulls SERP rankings from SEMrush and Ahrefs APIs.

Scoring philosophy:
  The SERP score measures whether the top-10 results for each keyword
  are positive, neutral, or negative about iVisa — regardless of whether
  iVisa.com itself ranks. A blog post saying "iVisa is legit" scores positive
  even if it's not on iVisa.com. A complaint on BBB scores negative.

Returns a dict shaped:
{
  "country_code": {
    "keyword": [
      {
        "position": int,
        "url": str,
        "domain": str,
        "title": str,
        "is_ivisa": bool,
        "sentiment": "positive" | "negative" | "neutral",
        "source": "semrush" | "ahrefs"
      }, ...
    ]
  }
}
"""

import csv
import io
import logging
import re
import time
from typing import Any

import requests

from scripts.config import (
    AHREFS_API_KEY,
    CLAUDE_API_KEY,
    CLAUDE_MODEL,
    COUNTRIES,
    KEYWORDS,
    KEYWORDS_BY_COUNTRY,
    NEGATIVE_DOMAINS,
    SEMRUSH_API_KEY,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentiment classification
#
# Philosophy: classify from CONTENT (title + snippet), not from domain.
# Trustpilot, Tripadvisor, Sitejabber etc. are NOT automatically positive —
# they surface user reviews that can be 1-star and very negative.
# The only domain-level signal we keep is NEGATIVE domains (complaint sites)
# because their structural purpose is to host complaints regardless of content.
#
# Neutral means MIXED: text contains both positive and negative signals,
# or takes a "it works but has downsides" position.
# Example: "iVisa isn't a scam, it's a platform that charges service fees
# but handles all the work for you" → neutral (mixed signals present).
# ---------------------------------------------------------------------------

# Signals that indicate POSITIVE content about iVisa
# Read as: the text is defending, recommending, or vouching for iVisa
POSITIVE_TEXT_SIGNALS = [
    # Explicit legitimacy defence
    "not a scam", "isn't a scam", "is not a scam", "no scam",
    "why is this not a scam", "why you can use ivisa", "why use ivisa",
    "yes ivisa is trustworthy", "ivisa is trustworthy", "ivisa is legitimate",
    "ivisa is legit", "ivisa is safe", "ivisa is real", "ivisa is reliable",
    "ivisa is trusted", "ivisa is worth it", "ivisa is approved",
    "ivisa is verified", "ivisa is not fake",
    # Positive framing — specific phrases only (avoid over-broad single words)
    "is legit", "is legitimate", "safe to use", "is trusted", "is reliable",
    "honest review", "worth it", "worth the money", "recommend", "recommended",
    "highly recommend", "would use again", "used it successfully", "worked for me",
    "worked perfectly", "it works", "great service", "excellent service",
    "fast service", "easy to use", "convenient", "approved",
    "5 star", "five star", "4 star", "positive experience",
    "used ivisa", "tried ivisa", "helped me", "no issues",
    "no problems", "smooth process", "everything went well",
    "government approved", "accredited",
    # Editorial/press coverage framing
    "review", "how ivisa works", "ivisa launches", "ivisa partners",
    "ivisa expands", "ivisa raises", "ivisa announces",
    # Awards & recognition (press releases) — e.g. "iVisa wins ... Provider of
    # the Year". Negative signals are counted alongside, so a complaint still wins.
    "wins", "winner", "award", "awarded", "award-winning", "provider of the year",
    "of the year", "best-in-class", "named winner", "breakthrough award",
    # Intent-to-recommend
    "should i use ivisa", "can i trust ivisa", "is ivisa worth",
    "best visa service", "best way to apply", "how to use ivisa",
    "guide to ivisa", "ivisa tutorial",
]

# Signals that indicate NEGATIVE content about iVisa
NEGATIVE_TEXT_SIGNALS = [
    "scam", "fraud", "fraudulent", "fake", "fake website", "not legitimate",
    "not legit", "not safe", "not trusted", "not real", "not reliable",
    "avoid", "avoid ivisa", "stay away", "do not use", "don't use",
    "beware", "warning", "danger", "dangerous",
    "complaint", "complaints", "problem", "problems", "issue", "issues",
    "rip off", "ripoff", "overcharged", "hidden fees", "hidden charges",
    "refund denied", "won't refund", "no refund", "lost money",
    "stole", "stolen", "steal", "cheat", "cheated", "mislead", "misleading",
    "suspicious", "shady", "untrustworthy", "terrible service", "worst service",
    "worst experience", "never again", "waste of money", "waste of time",
    "disappointing", "disappointed", "horrible", "awful", "nightmare",
    "con ", "con man", "scammed", "got scammed", "money back",
    # NOTE: "not affiliated with", "not government", "not official" are intentionally
    # NOT here — they are standard legal disclaimers on all third-party visa services.
    # They only become negative signals when combined with actual complaint language
    # (handled separately in _classify_result via _is_disclaimer_complaint).
    # Questions that imply doubt or regret — should never score positive
    "was it a mistake", "was using ivisa a mistake", "is ivisa a mistake",
    "mistake", "regret", "regretted", "wish i hadn't", "should have avoided",
    "fell for", "got tricked", "got fooled", "bad experience", "bad service",
    "worse than", "not worth", "not worth it", "don't recommend",
    "do not recommend", "would not recommend", "would not use again",
    # Implied negatives — "looks good BUT..." complaint structure
    "however they are not", "but they are not", "they are not what",
    "looks professional but", "looks clean but", "looks legit but",
    "however they", "however it is not", "but it is not",
    "i have applied", "i applied for", "still waiting", "no response",
    "they took my money", "took my money", "no visa", "never received",
    "do not trust", "cannot trust", "don't trust",
    "poor quality", "low quality", "very poor", "very bad",
    "very disappointed", "extremely disappointed", "totally disappointed",
    "unprofessional", "incompetent", "useless", "pathetic",
    "i want my money back", "demanding refund", "filed a complaint",
    "reported to", "legal action", "reported them",
    # Consumer protection / authority warnings
    # e.g. "Consumer advice center warns of UK travel permit scam"
    # "warns" (not "warning" — the noun) needs explicit coverage
    "warns of", "warns users", "warns travellers", "warns travelers",
    "consumer advice center", "consumer advice centre", "consumer protection warns",
    "travel permit scam", "permit scam",
]

# Disclaimer phrases that are only negative when paired with real complaint signals
# e.g. "not affiliated with any government" alone = compliance copy, not a complaint
# but "not affiliated with any government — misleading customers" = negative
DISCLAIMER_PHRASES = [
    "not affiliated with", "not government", "not official",
    "not affiliated", "not endorsed by", "independent service",
    "not a government", "third-party service", "not the government",
]

# When a disclaimer phrase appears, these must ALSO appear to classify as negative
COMPLAINT_SIGNALS = [
    "scam", "fraud", "mislead", "misleading", "complaint", "complaints",
    "warning", "beware", "avoid", "fake", "suspicious", "shady",
    "rip off", "ripoff", "cheat", "cheated", "stolen", "took my money",
]

def _is_disclaimer_complaint(text: str) -> bool:
    """Return True only if a disclaimer phrase is paired with real complaint language."""
    has_disclaimer = any(d in text for d in DISCLAIMER_PHRASES)
    if not has_disclaimer:
        return False
    return any(c in text for c in COMPLAINT_SIGNALS)

# iVisa-owned and official branded properties — positive by default unless
# the title/snippet contains explicit complaint language
IVISA_OWNED_DOMAINS = [
    "ivisa.com",
    "play.google.com",   # iVisa app on Google Play
    "apps.apple.com",    # iVisa app on App Store
    "linkedin.com",      # iVisa company page
    "facebook.com",      # iVisa Facebook page
    "instagram.com",     # iVisa Instagram
    "twitter.com",
    "x.com",
    "youtube.com",       # iVisa YouTube channel
]

# Debunking article signals — when these appear in the snippet alongside
# a "scam?" style title, the "scam" in the title is the question not the claim
DEBUNKING_SIGNALS = [
    "the answer is no", "not a scam", "isn't a scam", "is not a scam",
    "legitimate", "legit", "restoring trust", "restoring traveler trust",
    "the truth is", "verdict:", "conclusion:", "in short,",
    # Title subtitle signals — positive framing after the scam question
    "restoring", "why trust", "why travelers", "travelers trust",
    "inside the", "the truth about", "explained", "honest review",
]

# Title subtitle debunking — positive words that appear after "?" in the title
# indicate the article is framing the scam question as a hook, not a claim
TITLE_SUBTITLE_POSITIVE = [
    "restoring", "why trust", "why travelers", "travelers trust", "trust the",
    "legitimate", "legit", "safe", "reliable", "secure", "honest",
    "the truth", "inside the", "explained", "worth it", "recommend",
]

# Press/editorial domains — classified from content but given benefit of doubt
# when title is neutral (no signals): treated as positive not neutral
EDITORIAL_DOMAINS = [
    "yahoo.com", "yahoo.finance", "finance.yahoo.com", "news.yahoo.com",
    "forbes.com", "businessinsider.com", "cnbc.com", "reuters.com",
    "apnews.com", "bloomberg.com", "techcrunch.com", "theguardian.com",
    "bbc.com", "bbc.co.uk", "nytimes.com", "wsj.com", "ft.com",
    "skift.com", "travelpulse.com", "lonelyplanet.com", "nomadicmatt.com",
    "thepointsguy.com", "travelweekly.com", "phocuswire.com",
    "prnewswire.com", "businesswire.com", "globenewswire.com",
    "accesswire.com", "einpresswire.com",  # press release wires
    "europeanbusinessreview.com", "lakelandcurrents.com",
    "travelandleisure.com", "condénast.com", "cntraveler.com",
    "smarter-travel.com", "smartertravel.com",
]

# Structural complaint site domains — always negative regardless of text
# (We deliberately exclude Trustpilot, Tripadvisor, Sitejabber — their sentiment
# depends entirely on what the review says, not the domain itself)
ALWAYS_NEGATIVE_DOMAINS = [
    "bbb.org",
    "ripoffreport.com",
    "scamalert.com",
    "complaints.com",
    "pissedconsumer.com",
    "complaintsboard.com",
    "scamadviser.com",
    "reviewopedia.com",
]


# ---------------------------------------------------------------------------
# Data quality guards — detect junk titles / snippets from SerpAPI
# ---------------------------------------------------------------------------

import re as _re

def _is_domain_title(title: str, domain: str = "") -> bool:
    """
    Returns True if the title is just a URL or domain string, not real article text.
    Examples of junk: "www.europeanbusinessreview.com", "https://example.com/page"
    """
    t = title.strip()
    if not t:
        return False
    # No spaces + contains a dot → looks like a domain or URL
    if " " not in t and "." in t:
        return True
    # Starts with http or www
    if t.lower().startswith(("http://", "https://", "www.")):
        return True
    # Title is identical to the domain (with or without www.)
    if domain and t.lower().lstrip("www.").lstrip(".") == domain.lower().lstrip("www.").lstrip("."):
        return True
    return False


def _is_junk_snippet(snippet: str) -> bool:
    """
    Returns True if the snippet looks like JavaScript, PHP, JSON-LD structured
    data, or other non-content code instead of article/page text.
    Examples: "var theplus_ajax_url = ...", window.WIZ_global_data blobs,
              {"@context":"https://schema.org",...} JSON-LD payloads
    """
    s = snippet.strip()
    if not s:
        return False
    # JSON-LD structured data (schema.org markup captured as snippet text)
    # e.g. {"@context":"https://schema.org","@type":"WebSite","name":"iVisa Help Center"...}
    if s.startswith('{') and ('"@context"' in s or '"@type"' in s):
        return True
    if '{"@context"' in s or '"@context": "https://schema.org"' in s:
        return True
    # Leading HTML-comment-wrapped inline script: "--> if (!window.Intl ...)"
    # Google/CDN sites embed feature-detection scripts that SerpAPI captures raw.
    if s.startswith('-->') or s.startswith('<!--') or s.startswith('//'):
        return True
    # Any browser-object property access — window.X / document.X — is JS, never prose.
    # Catches window.WIZ_global_data, window.google, window.location.replace,
    # window.Intl.Segmenter, window.localStorage, document.createElement, etc.
    if _re.search(r'\b(?:window|document|navigator|location)\.\w', s):
        return True
    # Client-side redirect snippets, e.g. 'Redirecting... window.location.replace("/ru")'
    if 'location.replace' in s or '.location.href' in s:
        return True
    # Generic window.SOMETHING = { ... } assignment
    if _re.search(r'window\.\w+\s*=\s*\{', s):
        return True
    # Inline JS function / parse calls that only appear in scraped script tags
    if '(function(' in s or 'JSON.parse(' in s or _re.search(r'\bfunction\s*\(', s):
        return True
    # JavaScript variable assignments (most common junk pattern from WP sites)
    if _re.search(r'\bvar\s+\w+\s*=\s*["\']?https?://', s):
        return True
    # WordPress nonce / admin-ajax patterns
    if "wp-admin" in s or "_nonce" in s or "admin-ajax" in s:
        return True
    # Generic JS assignment blob — many var x = "..." patterns
    if s.count("var ") >= 2:
        return True

    # ── Structural code / markup detection (language-agnostic) ────────────────
    # THE DURABLE GUARD. Instead of enumerating every junk variant (a losing game
    # — there is always a new one), reject anything carrying the structural
    # punctuation of code, JSON, or HTML. Human prose, in ANY language (English,
    # German, Japanese, Italian…), does not contain these. This is what stops the
    # whack-a-mole: a never-before-seen JS/JSON blob still gets caught because it
    # still has braces, tags, or operators.
    if "{" in s or "}" in s:            # JSON / JS object literals
        return True
    if "</" in s or "/>" in s:          # HTML closing / self-closing tags
        return True
    if _re.search(r"<[a-zA-Z!/]", s):   # opening HTML/markup tag
        return True
    if "=>" in s or "();" in s:         # JS arrow fns / empty call
        return True
    if "&&" in s or "||" in s:          # boolean operators
        return True
    if s.count("://") >= 2:             # multiple raw URLs = dumped link list
        return True
    # NOTE: no broad bracket/symbol density check here — legitimate titles and
    # snippets routinely contain "[UK]", "[2026]", "(see below)", "&", etc.
    # The specific structural checks above ({ } < > => && || window. …) already
    # catch real code/JSON/HTML; a density check on []<>= caused false positives
    # on real earned-media titles like "[UK] iVisa.com UK-ETA is a scam".

    # High ratio of special/code characters → probably code
    code_chars = sum(1 for c in s if c in '{}[];=()"\\'  )
    if len(s) > 20 and code_chars / len(s) > 0.15:
        return True
    return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_result(domain: str, title: str, snippet: str = "") -> str:
    """
    Return 'positive', 'negative', or 'neutral' for a SERP result.

    Classification logic (in order of priority):
    1. Structural complaint domains → always negative
    2. iVisa-owned/branded domains → positive unless explicit complaint language present
    3. Debunking articles ("Is iVisa a scam? No.") → strip title "scam" as question,
       re-evaluate snippet alone → positive if snippet is clean, neutral if mixed
    4. Disclaimer-only "not affiliated/not government" → negative ONLY if also
       paired with real complaint language (scam, fraud, misleading, etc.)
    5. Count positive and negative signals in combined text
    6. Mixed signals → neutral; only negative → negative; only positive → positive
    7. Editorial/press domains with no signals → positive
    8. Everything else → neutral
    """
    domain_lower = domain.lower().strip()
    title_lower  = title.lower().strip()
    snippet_lower = snippet.lower().strip()
    full_text = f"{title_lower} {snippet_lower}"

    # 1. Structural complaint domains — always negative
    for d in ALWAYS_NEGATIVE_DOMAINS:
        if d in domain_lower:
            return "negative"

    # 2. iVisa-owned / branded official channels — positive by default
    # unless snippet/title contains explicit complaint language
    is_ivisa_owned = any(d in domain_lower for d in IVISA_OWNED_DOMAINS)
    if is_ivisa_owned:
        has_complaint = any(c in full_text for c in COMPLAINT_SIGNALS)
        # Also check hard negative signals (stolen, scammed, etc.)
        hard_neg = sum(1 for s in NEGATIVE_TEXT_SIGNALS if s in full_text)
        if not has_complaint and hard_neg == 0:
            return "positive"
        # If complaint/hard negative present even on owned domain → negative
        return "negative"

    # 3. Debunking articles — title asks "is ivisa a scam?" but snippet answers "no"
    title_has_scam_question = (
        "scam" in title_lower and
        any(q in title_lower for q in ["is ivisa", "is it a", "is this a", "a scam?", "scam?"])
    )
    if title_has_scam_question:
        # Check if the title itself has a positive subtitle after the "?"
        # e.g. "Is iVisa a Scam? Inside the Refund Policy That's Restoring..."
        title_after_q = title_lower.split("?", 1)[1].strip() if "?" in title_lower else ""
        title_subtitle_positive = any(p in title_after_q for p in TITLE_SUBTITLE_POSITIVE)

        snippet_debunks = (
            title_subtitle_positive or
            any(d in snippet_lower for d in DEBUNKING_SIGNALS) or
            snippet_lower.startswith("no,") or
            snippet_lower.startswith("no.") or
            snippet_lower.startswith("no ")
        )
        if snippet_debunks:
            # Evaluate snippet alone (not title) for remaining signals
            pos_hits_snip = sum(1 for s in POSITIVE_TEXT_SIGNALS if s in snippet_lower)
            neg_hits_snip = sum(1 for s in NEGATIVE_TEXT_SIGNALS if s in snippet_lower)
            # Also check if snippet discusses real issues (mixed) vs pure defence
            has_concern = any(c in snippet_lower for c in [
                "refund", "fee", "expensive", "cost", "complaint", "issue",
                "however", "but ", "although", "drawback", "downside",
            ])
            if has_concern:
                return "neutral"   # debunking but acknowledges real concerns
            if neg_hits_snip == 0:
                return "positive"  # clean debunking with no remaining negatives
            return "neutral"
        else:
            # Title raises "scam?" but snippet does NOT debunk it.
            # This is a forum thread, user question, or complaint page —
            # negative for brand regardless of any incidental positive words in snippet.
            return "negative"

    # 4. Disclaimer phrases ("not affiliated with", "not government") —
    # only negative if paired with actual complaint language
    if _is_disclaimer_complaint(full_text):
        return "negative"
    # Strip disclaimer phrases from signal counting so they don't bias the score
    cleaned_text = full_text
    for d in DISCLAIMER_PHRASES:
        cleaned_text = cleaned_text.replace(d, "")

    # 5. Count signals in cleaned text
    pos_hits = sum(1 for s in POSITIVE_TEXT_SIGNALS if s in cleaned_text)
    neg_hits = sum(1 for s in NEGATIVE_TEXT_SIGNALS if s in cleaned_text)

    # 6. Mixed signals = neutral; only negative = negative; only positive = positive
    if pos_hits > 0 and neg_hits > 0:
        return "neutral"
    if neg_hits > 0:
        return "negative"
    if pos_hits > 0:
        return "positive"

    # 7. Editorial/press domains with no signals → positive
    is_editorial = any(d in domain_lower for d in EDITORIAL_DOMAINS)
    if is_editorial:
        return "positive"

    # 8. Everything else → neutral
    return "neutral"


# ---------------------------------------------------------------------------
# Multilingual sentiment fallback (Claude)
# In non-English markets the snippets are in the local language, so the English
# signal words above don't match and the rule classifier returns an
# inconclusive "neutral". For exactly those cases we ask Claude to classify.
# Cached per text (snippets repeat across keywords/countries); one Haiku call
# per unique unmatched snippet; skipped entirely if CLAUDE_API_KEY is unset.
# ---------------------------------------------------------------------------
_LLM_SENTIMENT_CACHE: dict[str, str] = {}


def _rule_signals_inconclusive(domain: str, title: str, snippet: str) -> bool:
    """True only when the English rule classifier had NO signal to act on:
    non-owned, non-complaint, non-editorial, and zero positive/negative English
    signal words. These are the local-language results worth an LLM call —
    confident neutrals (mixed signals) and domain-based verdicts are left alone."""
    domain_lower = domain.lower()
    if any(d in domain_lower for d in ALWAYS_NEGATIVE_DOMAINS):
        return False
    if any(d in domain_lower for d in IVISA_OWNED_DOMAINS):
        return False
    if any(d in domain_lower for d in EDITORIAL_DOMAINS):
        return False
    text = f"{title.lower()} {snippet.lower()}"
    pos = sum(1 for s in POSITIVE_TEXT_SIGNALS if s in text)
    neg = sum(1 for s in NEGATIVE_TEXT_SIGNALS if s in text)
    return pos == 0 and neg == 0


def _classify_with_claude(title: str, snippet: str) -> str | None:
    """Classify a (typically non-English) SERP result as positive/negative/neutral
    via Claude. Returns None on any failure so the caller keeps the existing value."""
    text = f"{title}\n{snippet}".strip()
    if not text or not CLAUDE_API_KEY:
        return None
    if text in _LLM_SENTIMENT_CACHE:
        return _LLM_SENTIMENT_CACHE[text]
    prompt = (
        "This is a Google search result about iVisa, an online visa / travel-document "
        "service. The text may be in any language. Classify how it reflects on iVisa's "
        "reputation. Reply with EXACTLY one word: positive, negative, or neutral.\n"
        "- positive: defends, recommends, praises, or is iVisa's own official listing\n"
        "- negative: scam/fraud accusation, complaint, warning, regret, or strong criticism\n"
        "- neutral: mixed pros and cons, purely factual, or not really about iVisa\n\n"
        f"Result:\n{text[:1200]}"
    )
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=5,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip().lower()
        label = (
            "positive" if "positive" in raw else
            "negative" if "negative" in raw else
            "neutral"  if "neutral"  in raw else None
        )
        if label:
            _LLM_SENTIMENT_CACHE[text] = label
        return label
    except Exception as exc:
        logger.warning("Claude multilingual classify failed: %s", exc)
        return None


def _is_ivisa(domain: str) -> bool:
    return "ivisa.com" in domain.lower()


def _position_score(results: list[dict]) -> float:
    """
    Score one keyword based on the sentiment of its top-10 SERP results.

    Logic:
    - Each result is positive (1.0), neutral (0.5), or negative (0.0).
    - Results are weighted by position: pos 1 = 10 pts, pos 2 = 9 pts … pos 10 = 1 pt.
    - Final score = weighted_average * 100

    Meaning:
    - 100 = all top-10 results are positive about iVisa
    -  50 = all top-10 results are neutral (mixed / no strong signal)
    -   0 = all top-10 results are negative about iVisa
    """
    if not results:
        return 50.0  # neutral baseline when no data

    SENTIMENT_SCORE = {"positive": 1.0, "neutral": 0.5, "negative": 0.0}

    total_weight = 0.0
    weighted_score = 0.0

    for item in results[:10]:
        pos = item.get("position", 0)
        if pos < 1 or pos > 10:
            continue
        weight = float(11 - pos)  # pos 1 → 10, pos 10 → 1
        sentiment = item.get("sentiment", "neutral")
        weighted_score += weight * SENTIMENT_SCORE.get(sentiment, 0.5)
        total_weight += weight

    if total_weight == 0:
        return 50.0

    return round((weighted_score / total_weight) * 100, 2)


# ---------------------------------------------------------------------------
# SEMrush
# ---------------------------------------------------------------------------

def _fetch_semrush_keyword(keyword: str, database: str) -> list[dict]:
    """Fetch top-10 organic results for one keyword from SEMrush."""
    if not SEMRUSH_API_KEY:
        logger.warning("SEMRUSH_API_KEY not set — skipping SEMrush fetch.")
        return []

    url = "https://api.semrush.com/"
    params = {
        "type": "phrase_organic",
        "key": SEMRUSH_API_KEY,
        "phrase": keyword,
        "database": database,
        "display_limit": 10,
        "export_columns": "Po,Ur,Dn,Tt",
    }

    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("SEMrush request failed for '%s' (%s): %s", keyword, database, exc)
        return []

    text = resp.text.strip()
    if not text or text.startswith("ERROR"):
        logger.warning("SEMrush returned no data for '%s' (%s): %s", keyword, database, text[:120])
        return []

    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    results = []
    for row in reader:
        try:
            pos = int(row.get("Position", 0))
        except (ValueError, TypeError):
            pos = 0
        domain  = row.get("Domain", "").strip()
        title   = row.get("Title", "").strip()
        snippet = row.get("Snippet", "").strip()
        # Sanitize junk at ingestion so it never enters storage — enrichment only
        # runs for keyword/country pairs present in the organic feed, so junk from
        # SEMrush-only keywords would otherwise leak straight into the report.
        if _is_junk_snippet(snippet):
            snippet = ""
        if _is_domain_title(title, domain):
            title = ""
        results.append({
            "position": pos,
            "url": row.get("URL", "").strip(),
            "domain": domain,
            "title": title,
            "snippet": snippet,
            "is_ivisa": _is_ivisa(domain),
            "sentiment": _classify_result(domain, title, snippet),
            "source": "semrush",
        })
    return results


# ---------------------------------------------------------------------------
# Ahrefs
# ---------------------------------------------------------------------------

def _fetch_ahrefs_keyword(keyword: str, country: str) -> list[dict]:
    """Fetch top-10 SERP overview for one keyword from Ahrefs v3 API."""
    if not AHREFS_API_KEY:
        logger.warning("AHREFS_API_KEY not set — skipping Ahrefs fetch.")
        return []

    url = "https://api.ahrefs.com/v3/serp-overview"
    params = {
        "target": keyword,
        "country": country,
        "mode": "phrase",
        "limit": 10,
    }
    headers = {"Authorization": f"Bearer {AHREFS_API_KEY}"}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Ahrefs request failed for '%s' (%s): %s", keyword, country, exc)
        return []

    try:
        data = resp.json()
    except ValueError as exc:
        logger.error("Ahrefs JSON parse error for '%s': %s", keyword, exc)
        return []

    results = []
    for item in data.get("serp", []):
        domain  = item.get("domain", "").strip()
        title   = item.get("title", "").strip()
        snippet = item.get("snippet", "").strip()
        # Sanitize junk at ingestion (see SEMrush fetcher note above).
        if _is_junk_snippet(snippet):
            snippet = ""
        if _is_domain_title(title, domain):
            title = ""
        results.append({
            "position": item.get("position", 0),
            "url": item.get("url", "").strip(),
            "domain": domain,
            "title": title,
            "snippet": snippet,
            "is_ivisa": _is_ivisa(domain),
            "sentiment": _classify_result(domain, title, snippet),
            "source": "ahrefs",
        })
    return results


# ---------------------------------------------------------------------------
# Merge & de-duplicate results
# ---------------------------------------------------------------------------

def _merge_results(semrush: list[dict], ahrefs: list[dict]) -> list[dict]:
    """
    Prefer SEMrush data; backfill with Ahrefs for positions not covered.
    Returns list sorted by position ascending.
    """
    seen_positions: set[int] = set()
    merged = []

    for item in semrush:
        if item["position"] not in seen_positions:
            merged.append(item)
            seen_positions.add(item["position"])

    for item in ahrefs:
        if item["position"] not in seen_positions:
            merged.append(item)
            seen_positions.add(item["position"])

    merged.sort(key=lambda x: x["position"])
    return merged[:10]


# ---------------------------------------------------------------------------
# Country / Global score calculation
# ---------------------------------------------------------------------------

def _country_serp_score(keyword_results: dict[str, list[dict]]) -> float:
    """Average keyword scores across all keywords for one country."""
    scores = [_position_score(results) for results in keyword_results.values()]
    return round(sum(scores) / len(scores), 2) if scores else 0.0


def calculate_global_serp_score(country_scores: dict[str, float]) -> float:
    """Weighted average across countries."""
    total = 0.0
    weight_sum = 0.0
    for code, score in country_scores.items():
        weight = COUNTRIES[code]["weight"]
        total += score * weight
        weight_sum += weight
    return round(total / weight_sum, 2) if weight_sum else 0.0


# ---------------------------------------------------------------------------
# SerpAPI organic enrichment
# Fallback titles for social/platform domains that never appear in organic results
# but do rank in Google's social/app panels (tracked by SEMrush as domain-level).
_PLATFORM_TITLES: dict[str, str] = {
    "ivisa.com":       "iVisa — Official Website",
    "reddit.com":      "iVisa — Community Discussions on Reddit",
    "facebook.com":    "iVisa — Facebook Page",
    "instagram.com":   "iVisa — Instagram (@iVisaTravel)",
    "linkedin.com":    "iVisa — Company Profile on LinkedIn",
    "youtube.com":     "iVisa — YouTube Channel",
    "twitter.com":     "iVisa — Twitter / X",
    "x.com":           "iVisa — Twitter / X",
    "trustpilot.com":  "iVisa Reviews on Trustpilot",
    "tripadvisor.com": "iVisa Reviews on Tripadvisor",
    "sitejabber.com":  "iVisa Reviews on Sitejabber",
    "bbb.org":         "iVisa — Better Business Bureau Profile",
    "yelp.com":        "iVisa — Yelp Reviews",
    "glassdoor.com":   "iVisa — Glassdoor Company Profile",
    "indeed.com":      "iVisa — Indeed Company Profile",
    "apps.apple.com":  "iVisa: ETA, eVisa, ESTA, Visa — App Store",
    "play.google.com": "iVisa: Online Travel Visas — Apps on Google Play",
    "quora.com":       "iVisa — Traveler Questions & Answers on Quora",
    "pinterest.com":   "iVisa — Pinterest",
}


def _platform_title(domain: str) -> str:
    """Return a canned title for a known platform domain, else ''. Used to replace
    a missing/domain-only title (e.g. 'www.quora.com') with a readable label."""
    bare = (domain or "").lower().lstrip("www.").lstrip(".")
    return _PLATFORM_TITLES.get(bare, "")


# iVisa-owned app-store listings — canonical title + description used when the
# live scrape returns a generic store title (e.g. "Android Apps on Google Play")
# or a blank snippet. The listing copy is controlled by iVisa and stable, so this
# is safe brand copy, not invented content. Prevents bare "Android Apps on Google
# Play" cards with no description from appearing in the report.
_APP_STORE_LISTINGS: dict[str, tuple[str, str]] = {
    "play.google.com": (
        "iVisa: Online Travel Visas — Apps on Google Play",
        "The iVisa app is a private platform that helps users prepare visa and "
        "travel document applications. Easily apply for ETA, eVisa, ESTA, NZeTA and more.",
    ),
    "apps.apple.com": (
        "iVisa: ETA, eVisa, ESTA, Visa — App Store",
        "iVisa is your one-stop shop for visas and other travel requirements. "
        "Apply for travel documents online in a few easy steps.",
    ),
}

# Generic store/listing titles that carry no iVisa-specific info — treat as missing
# so the canonical _APP_STORE_LISTINGS title replaces them.
_GENERIC_PLATFORM_TITLES = {
    "android apps on google play", "apps on google play", "google play",
    "google play store", "app store", "app store - apple", "apps on app store",
    "app store - apple inc.", "‎app store",
}


def _apply_app_store_fallbacks(item: dict) -> None:
    """Fill iVisa app-store listings with canonical title/snippet when the live
    scrape left them generic or blank. Only fills gaps — real review snippets and
    specific titles are left untouched."""
    bare = item.get("domain", "").lower().lstrip("www.").lstrip(".")
    listing = _APP_STORE_LISTINGS.get(bare)
    if not listing:
        return
    fb_title, fb_snippet = listing
    title = (item.get("title") or "").strip()
    if not title or title.lower() in _GENERIC_PLATFORM_TITLES:
        item["title"] = fb_title
    if not (item.get("snippet") or "").strip():
        item["snippet"] = fb_snippet


# Accurate one-line descriptions for social / review / owned domains. SEMrush
# ranks these at the domain level (no per-page snippet), and they don't appear in
# organic results with body text — so without this they render as a title with a
# blank preview line. These are neutral factual descriptors (NOT sentiment-bearing),
# applied display-only so they never change a result's classification or score.
_PLATFORM_SNIPPETS: dict[str, str] = {
    "ivisa.com":       "Apply for your visa, ETA, or travel document online with iVisa — fast, simple, and secure.",
    "facebook.com":    "iVisa's official Facebook page — product updates, travel tips, and customer support.",
    "instagram.com":   "iVisa on Instagram — travel inspiration and visa tips.",
    "linkedin.com":    "iVisa's official company profile on LinkedIn.",
    "youtube.com":     "Video reviews and how-to guides about iVisa on YouTube.",
    "twitter.com":     "iVisa on X (Twitter) — updates and customer support.",
    "x.com":           "iVisa on X (Twitter) — updates and customer support.",
    "reddit.com":      "Traveler discussions and reviews of iVisa on Reddit.",
    "quora.com":       "Traveler questions and answers about iVisa on Quora.",
    "tripadvisor.com": "Traveler reviews and ratings for iVisa on Tripadvisor.",
    "trustpilot.com":  "Customer reviews and ratings for iVisa on Trustpilot.",
    "sitejabber.com":  "Customer reviews for iVisa on Sitejabber.",
    "bbb.org":         "iVisa's Better Business Bureau profile and customer feedback.",
    "yelp.com":        "Customer reviews for iVisa on Yelp.",
    "glassdoor.com":   "Employee reviews and company information for iVisa on Glassdoor.",
    "indeed.com":      "Company information and reviews for iVisa on Indeed.",
}


def _platform_snippet(domain: str) -> str:
    """Return a canned descriptor for a known platform domain, else ''."""
    bare = (domain or "").lower().lstrip("www.").lstrip(".")
    return _PLATFORM_SNIPPETS.get(bare, "")


_BAD_TITLES = {
    "just a moment", "just a moment...", "attention required",
    "403 forbidden", "404 not found", "502 bad gateway", "503 service unavailable",
    "500 internal server error", "access denied", "error", "cloudflare",
    "please wait", "checking your browser", "ray id", "enable javascript",
    "site not found", "page not found",
}


def _fetch_page_title(url: str, timeout: int = 4) -> tuple[str, str]:
    """
    Last-resort: fetch a page and extract its <title> tag and a short body snippet.
    Returns (title, body_snippet) — empty strings on any error or bad page.
    Filters out Cloudflare challenge pages, error pages, etc.
    """
    if not url:
        return "", ""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; iVisaBot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        html = resp.text

        # Extract title
        match = re.search(r"<title[^>]*>([^<]{1,200})</title>", html, re.IGNORECASE)
        title = match.group(1).strip() if match else ""

        # Reject bot-protection / error page titles
        if title.lower() in _BAD_TITLES:
            return "", ""

        # Reject error responses entirely — don't save body either
        if resp.status_code >= 400 or title.lower() in _BAD_TITLES:
            return "", ""

        # Extract a short plain-text body snippet (strip tags, collapse whitespace)
        body = re.sub(r"<[^>]+>", " ", html)
        body = re.sub(r"\s+", " ", body).strip()[:1000]

        # Reject GENERIC HOMEPAGE titles. SEMrush often gives only a domain, so we
        # fetch https://<domain> — the site HOMEPAGE — and grab its <title>, e.g.
        # "News - Lakeland Currents", "Travelsloth - Alles für Backpacker", "Home -
        # Adventures & Sunsets". If neither the title nor the page body even mentions
        # iVisa, this isn't the iVisa article — attaching its generic title (with no
        # snippet) just clutters the report. Better to return nothing.
        if "ivisa" not in (title + " " + body).lower():
            return "", ""

        # Reject body that looks like an error/challenge page
        body_check = body.lower()
        if any(bad in body_check for bad in ("502 bad gateway", "503 service", "just a moment", "checking your browser", "enable javascript and cookies")):
            return title, ""

        return title, body
    except Exception:
        return "", ""


# ---------------------------------------------------------------------------

def enrich_with_serpapi_organic(serp_data: dict, organic_data: dict) -> dict:
    """
    Enrich SERP results using organic data already fetched by fetch_ai_overviews.

    Two jobs:
    1. Fill in page titles (SEMrush/Ahrefs don't return titles).
    2. Replace empty keyword results (keywords with no SEMrush/Ahrefs coverage)
       with SerpAPI organic results — same API call, zero extra cost.

    organic_data shape: { country_code: { keyword: [ {position, url, domain, title, snippet} ] } }
    """
    results = serp_data.get("results", {})

    for country_code, keyword_organic in organic_data.items():
        if country_code not in results:
            results[country_code] = {}

        for keyword, organic_list in keyword_organic.items():
            existing = results[country_code].get(keyword, [])

            if not existing:
                # No SEMrush/Ahrefs data at all — use SerpAPI organic as source
                # Sanitize snippets/titles from organic source before storing
                organic_clean = []
                for r in organic_list:
                    if not (r.get("position") and r.get("url")):
                        continue
                    snippet_clean = r.get("snippet", "")
                    if _is_junk_snippet(snippet_clean):
                        snippet_clean = ""
                    title_clean = r.get("title", "")
                    if _is_domain_title(title_clean, r.get("domain", "")):
                        title_clean = ""
                    organic_clean.append({
                        "position": r["position"],
                        "url": r["url"],
                        "domain": r["domain"],
                        "title": title_clean,
                        "snippet": snippet_clean,
                        "is_ivisa": _is_ivisa(r["domain"]),
                        "sentiment": _classify_result(
                            r["domain"], title_clean, snippet_clean
                        ),
                        "source": "serpapi",
                    })
                results[country_code][keyword] = organic_clean
            else:
                # SEMrush/Ahrefs data exists — fill in missing titles + snippets
                url_map    = {r["url"]: r for r in organic_list if r.get("url")}
                # Normalize domains: strip www. for matching
                domain_map = {
                    r["domain"].lstrip("www.").lstrip("."): r
                    for r in organic_list if r.get("domain")
                }

                for item in existing:
                    url    = item.get("url", "")
                    domain = item.get("domain", "").lstrip("www.").lstrip(".")

                    # ── Sanitize junk data before enrichment ──────────────────
                    # Treat domain-as-title and JS snippets as missing data so
                    # the enrichment fallbacks below can replace them properly.
                    if _is_domain_title(item.get("title", ""), item.get("domain", "")):
                        item["title"] = ""
                    if _is_junk_snippet(item.get("snippet", "")):
                        item["snippet"] = ""

                    # Try URL match first, fall back to normalized domain match
                    organic_match = url_map.get(url) or domain_map.get(domain)
                    if organic_match:
                        if not item.get("title"):
                            item["title"] = organic_match.get("title", "")
                        if not item.get("snippet"):
                            item["snippet"] = organic_match.get("snippet", "")
                        if not item.get("url") and organic_match.get("url"):
                            item["url"] = organic_match.get("url", "")

                    # Fallback 1: platform title map for known social/app domains
                    if not item.get("title"):
                        bare = item.get("domain", "").lstrip("www.").lstrip(".")
                        fallback = _PLATFORM_TITLES.get(bare)
                        if fallback:
                            item["title"] = fallback

                    # Fallback 2: fetch the page directly to grab its <title> tag + body
                    # If URL is missing, construct one from the domain
                    if not item.get("title"):
                        fetch_url = item.get("url") or f"https://{item.get('domain', '').lstrip('www.').lstrip('.')}"
                        if fetch_url and fetch_url != "https://":
                            fetched_title, fetched_body = _fetch_page_title(fetch_url)
                            if fetched_title:
                                item["title"] = fetched_title
                                if not item.get("url"):
                                    item["url"] = fetch_url
                            # Use body snippet for sentiment even if title was already known
                            if fetched_body and not item.get("snippet"):
                                item["snippet"] = fetched_body[:300]

                    # Re-classify with title + snippet now that both are available
                    item["sentiment"] = _classify_result(
                        item.get("domain", ""),
                        item.get("title", ""),
                        item.get("snippet", ""),
                    )

                # ── Snippet coverage check ────────────────────────────────────
                # If SEMrush/Ahrefs results have < 40% snippet coverage after all
                # enrichment attempts, the two sources disagree on what ranks for
                # this keyword (common for branded queries like "iVisa"). Fall back
                # to live SerpAPI organic results which have real snippet text.
                if organic_list:
                    has_snip = sum(1 for it in existing if it.get("snippet", "").strip())
                    if existing and has_snip / len(existing) < 0.40:
                        logger.debug(
                            "  Low snippet coverage (%d/%d) for '%s' (%s) — using live SerpAPI organic",
                            has_snip, len(existing), keyword, country_code,
                        )
                        fallback_results = []
                        for r in organic_list:
                            if not (r.get("position") and r.get("url")):
                                continue
                            # Sanitize junk snippets in the organic fallback too
                            snippet_clean = r.get("snippet", "")
                            if _is_junk_snippet(snippet_clean):
                                snippet_clean = ""
                            title_clean = r.get("title", "")
                            if _is_domain_title(title_clean, r.get("domain", "")):
                                title_clean = ""
                            fallback_results.append({
                                "position":  r["position"],
                                "url":       r["url"],
                                "domain":    r["domain"],
                                "title":     title_clean,
                                "snippet":   snippet_clean,
                                "is_ivisa":  _is_ivisa(r["domain"]),
                                "sentiment": _classify_result(
                                    r["domain"], title_clean, snippet_clean
                                ),
                                "source":    "serpapi",
                            })
                        results[country_code][keyword] = fallback_results

    # Final normalization pass: ensure iVisa app-store listings always show real
    # copy (covers every path above — organic-as-source, enriched, and fallback).
    for country_code in results:
        for keyword, items in results[country_code].items():
            for item in items:
                _apply_app_store_fallbacks(item)
                item["sentiment"] = _classify_result(
                    item.get("domain", ""),
                    item.get("title", ""),
                    item.get("snippet", ""),
                )

    # Multilingual sentiment fallback — for non-English markets, upgrade the
    # results the English rules couldn't classify (inconclusive neutral) using
    # Claude. No-ops when CLAUDE_API_KEY is unset (results stay neutral).
    llm_upgraded = 0
    for country_code in results:
        if COUNTRIES.get(country_code, {}).get("serpapi_hl", "en") == "en":
            continue
        for keyword, items in results[country_code].items():
            for item in items:
                if item.get("sentiment") != "neutral":
                    continue
                title = item.get("title", "") or ""
                snippet = item.get("snippet", "") or ""
                if not (title or snippet):
                    continue
                if _rule_signals_inconclusive(item.get("domain", ""), title, snippet):
                    label = _classify_with_claude(title, snippet)
                    if label and label != "neutral":
                        item["sentiment"] = label
                        llm_upgraded += 1
    if llm_upgraded:
        logger.info("  → Multilingual fallback: Claude re-classified %d non-English result(s).", llm_upgraded)

    # Recompute scores with enriched data
    for country_code in list(results.keys()):
        serp_data["country_scores"][country_code] = _country_serp_score(results[country_code])

    serp_data["global_score"] = calculate_global_serp_score(serp_data["country_scores"])
    serp_data["results"] = results
    logger.info("  → SERP enriched with SerpAPI organic data. New global score: %.1f", serp_data["global_score"])
    return serp_data


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_serp_data() -> dict[str, Any]:
    """
    Fetch SERP data for all keywords × countries.

    Returns:
    {
      "results": { country_code: { keyword: [result, ...] } },
      "country_scores": { country_code: float },
      "global_score": float,
    }
    """
    results: dict[str, dict[str, list[dict]]] = {}
    country_scores: dict[str, float] = {}

    for country_code, country_info in COUNTRIES.items():
        logger.info("  Fetching SERP for country: %s (%s)", country_info["name"], country_code)
        results[country_code] = {}

        for keyword in KEYWORDS_BY_COUNTRY.get(country_code, KEYWORDS):
            logger.debug("    Keyword: %s", keyword)

            semrush_data = _fetch_semrush_keyword(keyword, country_info["semrush_db"])
            # Be gentle with rate limits
            time.sleep(0.3)
            ahrefs_data = _fetch_ahrefs_keyword(keyword, country_info["ahrefs_country"])
            time.sleep(0.3)

            merged = _merge_results(semrush_data, ahrefs_data)
            results[country_code][keyword] = merged

        country_scores[country_code] = _country_serp_score(results[country_code])
        logger.info("    → Country SERP score: %.1f", country_scores[country_code])

    global_score = calculate_global_serp_score(country_scores)
    logger.info("  → Global SERP Score: %.1f", global_score)

    return {
        "results": results,
        "country_scores": country_scores,
        "global_score": global_score,
    }
