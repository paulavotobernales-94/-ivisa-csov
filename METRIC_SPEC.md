# CSOV Metric Specification
## Version 1.0 — Locked June 2026

---

## What Is CSOV?

CSOV stands for **Content Share of Voice**. It measures how positively iVisa appears across the digital touchpoints a potential customer encounters when researching visa and travel documentation services.

Unlike traditional share-of-voice metrics (which only count how often a brand appears), CSOV weights appearances by their *sentiment*. A result that warns people away from iVisa is worse than no result at all. A result that recommends iVisa is worth more than a neutral mention.

The score runs from **0 to 100**. A score of 100 would mean every relevant result, AI answer, and media mention is strongly positive. In practice, scores in the 60–75 range reflect a healthy online reputation for a service business in a trust-sensitive category.

CSOV is calculated weekly and compared to the prior week to track momentum.

---

## The Four Components

The overall CSOV score is a weighted average of four components:

| Component | Weight | What It Measures |
|---|---|---|
| SERP (Search Engine Results Pages) | 35% | How iVisa appears in Google search results for high-intent queries, across key markets |
| AI Overview | 25% | How positively Google's AI-generated answer panels describe iVisa |
| LLM (Large Language Models) | 25% | How iVisa is portrayed when people ask Claude and Gemini about visa services |
| Earned Media | 15% | The sentiment of recent press, editorial, and media coverage |

### SERP — 35%

**Data source:** SEMrush and Ahrefs for keyword ranking data; SerpAPI for organic result titles and snippets.

**What it measures:** For each tracked keyword (e.g., "is iVisa legit", "iVisa review", "iVisa scam"), we pull the top 10 organic results and classify each one as positive, neutral, or negative. Results are position-weighted — rank 1 carries more weight than rank 10, because that's what most users actually see. The component score is the weighted average sentiment across all keywords and countries.

**Countries tracked:** Results are gathered per country (weighted by market importance) and then rolled up to a global SERP score.

### AI Overview — 25%

**Data source:** Google AI Overviews, retrieved via Serper.dev; sentiment scored by Claude (claude-haiku-4-5).

**What it measures:** When Google shows an AI-generated summary above the organic results (an "AI Overview"), we extract the text and score how positively it describes iVisa. The scoring uses a 0–100 prompt: *"Rate how positive this response is about iVisa as a trustworthy visa service, from 0 (very negative/scam warning) to 100 (very positive/recommended)."*

**Important:** If Google doesn't show an AI Overview for a given query, that query is **excluded from the score entirely** — it doesn't count as a zero. The absence of an AI Overview is neutral, not a negative signal.

### LLM — 25%

**Data source:** Claude API (claude-haiku-4-5) and Google Gemini (gemini-2.0-flash), queried with a standard set of travel and visa-related prompts.

**What it measures:** How LLMs respond when a user asks questions like "What's the best way to get a tourist visa?" or "Is iVisa a legitimate service?" We score both whether iVisa is mentioned at all, and how positively it's described when it is. The 0–100 scoring prompt is the same one used for AI Overviews.

### Earned Media — 15%

**Data source:** SerpAPI news and web searches for recent iVisa mentions.

**What it measures:** The sentiment of press coverage, editorial articles, travel media, and PR wire mentions. Each mention is classified as positive, neutral, or negative, and the component score is the weighted average.

---

## Sentiment Classification Rules

### SERP Classification

Classification is based on the **content of each result** (its title and snippet), not on the domain alone. A Trustpilot page that says "excellent service" is positive. A Trustpilot page that says "took my money, no visa" is negative. The domain doesn't determine the verdict — what it actually says does.

**Priority order:**

1. **Structural complaint domains → always negative**, regardless of content (see list below)
2. **Count positive and negative signals** in the combined title + snippet
3. Both positive and negative signals present → **neutral** (mixed/balanced)
4. Only negative signals → **negative**
5. Only positive signals → **positive**
6. No signals on an editorial/press domain → **positive** (editorial coverage without negative signals counts as positive)
7. No signals on any other domain → **neutral**

**Positive text signals** (partial list — text must contain one of these phrases):

Explicit legitimacy: "not a scam", "isn't a scam", "is not a scam", "ivisa is trustworthy", "ivisa is legitimate", "ivisa is legit", "ivisa is safe", "ivisa is reliable", "ivisa is worth it"

General positive: "recommend", "highly recommend", "would use again", "worked for me", "great service", "excellent service", "fast service", "easy to use", "5 star", "five star", "no issues", "smooth process", "everything went well", "approved", "government approved", "accredited"

Editorial framing: "how ivisa works", "ivisa launches", "ivisa partners", "ivisa expands", "ivisa raises", "ivisa announces", "guide to ivisa", "best visa service"

**Negative text signals** (partial list — text must contain one of these phrases):

Direct: "scam", "fraud", "fraudulent", "fake", "not legitimate", "not legit", "avoid", "stay away", "do not use", "beware", "warning"

Experience-based: "rip off", "ripoff", "overcharged", "hidden fees", "refund denied", "won't refund", "lost money", "stole", "stolen", "cheat", "cheated", "misleading"

Sentiment: "terrible service", "worst service", "worst experience", "never again", "waste of money", "disappointing", "horrible", "awful", "nightmare", "scammed", "bad experience", "not worth it", "do not recommend", "would not recommend"

Doubt-implying questions: "was it a mistake", "is ivisa a mistake", "regret", "wish i hadn't", "got tricked", "got fooled"

**Always-negative domains** (structural complaint sites — classified negative regardless of content):

- bbb.org
- ripoffreport.com
- scamalert.com
- complaints.com
- pissedconsumer.com
- complaintsboard.com
- scamadviser.com
- reviewopedia.com

**Editorial domains** (no-signal result defaults to positive, not neutral):

yahoo.com, finance.yahoo.com, forbes.com, businessinsider.com, cnbc.com, reuters.com, apnews.com, bloomberg.com, techcrunch.com, theguardian.com, bbc.com, nytimes.com, wsj.com, ft.com, skift.com, travelpulse.com, lonelyplanet.com, nomadicmatt.com, thepointsguy.com, travelweekly.com, phocuswire.com, prnewswire.com, businesswire.com, globenewswire.com, accesswire.com, einpresswire.com

**Why Trustpilot, TripAdvisor, and Sitejabber are NOT in the always-negative or always-positive lists:**

These platforms host user reviews that can be anything from 5-star to 1-star. Classifying them by domain alone would be wrong — a Trustpilot result with "iVisa is amazing, got my visa in 2 days" should score positive. A Trustpilot result with "complete scam, lost $200" should score negative. So we read the content and let the text signals decide.

### Earned Media Classification

Earned media uses a simplified version of the same content-first logic, applied to news and editorial mentions.

**Priority order:**

1. Review aggregators (Trustpilot, Sitejabber, TripAdvisor, Yelp, ConsumerReports) → **excluded entirely** (not classified, not counted)
2. Structural complaint domains (bbb.org, scamalert.com, ripoffreport.com, complaints.com, pissedconsumer.com, complaintsboard.com) → **negative**
3. Any negative signal in the text → **negative**
4. Known positive editorial/press domains with no negative signals → **positive** (Forbes, Reuters, BBC, Skift, Lonely Planet, PR Newswire, etc.)
5. Any positive signal in the text → **positive**
6. No signals → **neutral**

**Positive signals for earned media:** legit, legitimate, safe, trusted, reliable, recommend, honest, worth it, approved, verified, best, real, worked, works, helped, guide, how to use, review, pros, easy, convenient, fast, efficient, excellent, great, helpful, officially, trusted service, 5 star, five star

**Negative signals for earned media:** scam, fraud, fake, danger, problem, complaint, steal, stolen, worst, terrible, rip off, ripoff, warning, cheat, mislead, suspicious, beware, do not use, don't use, stay away, con, overcharged, refund denied, lost money, never again, waste of, disappointed, not legit, not safe, not legitimate, not trusted, shady, unresponsive, scammed, avoid ivisa, avoid using ivisa, avoid this service

**Why review aggregators are excluded from earned media:**

Review aggregators (Trustpilot, Sitejabber, TripAdvisor, Yelp) are not earned media — they're user-generated review platforms. Their content is outside iVisa's PR and editorial influence, and they can surface very negative content even when the brand's actual press coverage is positive. Including them would conflate customer satisfaction with media reputation, which are separate signals tracked separately. They're excluded from earned media scoring, not suppressed.

---

## Score Calculation

### Sentiment to Score Conversion (SERP and Earned Media)

| Classification | Score Value |
|---|---|
| Positive | 1.0 (full credit) |
| Neutral | 0.5 (half credit) |
| Negative | 0.0 (no credit) |

### Position Weighting (SERP only)

SERP results are weighted by rank position. Rank 1 carries the most weight because the vast majority of clicks go to the top results. The weighting follows an inverse-rank curve — the exact weights are defined in `scripts/fetch_serp.py`.

### AI Overview and LLM Scores

Both are 0–100 continuous scores (not bucketed into positive/neutral/negative). They're fed directly into the weighted average formula as-is.

### Overall CSOV Formula

```
CSOV = (SERP_score × 0.35) + (AI_Overview_score × 0.25) + (LLM_score × 0.25) + (Earned_Media_score × 0.15)
```

Where each component score is on a 0–100 scale.

---

## What's Deliberately Excluded and Why

**Review aggregators (Trustpilot, Sitejabber, TripAdvisor, Yelp, ConsumerReports):**
Excluded from earned media because they measure customer satisfaction, not PR/media reputation. They're user-generated and not responsive to brand communications activity. If we tracked them here, a bad week for customer support would tank the brand reputation score even if our media presence was excellent. These platforms are monitored separately as part of customer experience tracking.

**Structural complaint sites (BBB, RipoffReport, ScamAlert, etc.):**
These domains exist specifically to aggregate complaints. Any result from them is treated as negative regardless of the specific text, because the structural purpose of these sites is to host complaints and warnings. Unlike review platforms, they don't have a positive counterpart that would balance the signal.

**Paid/sponsored search results:**
We score organic results only. Paid results reflect ad spend, not organic brand perception.

---

## Baseline: v1.0

The v1.0 baseline was locked in June 2026. It's calculated as the average of two consecutive weeks of data:

- **Period 1:** May 25–31, 2026
- **Period 2:** June 1–7, 2026

These two weeks establish the starting point for all future trend comparisons. When you see a CSOV score described as "up 3 points from baseline," it means 3 points above this v1.0 average.

---

## Data Integrity and Version Control

Every weekly data snapshot is saved with a `scoring_version` field (e.g., `"scoring_version": "1.0"`). This means we always know which version of the scoring logic produced a given historical result.

**If the scoring logic changes** — a new signal is added, a domain is moved, the weights shift — you must:

1. Bump the version number (e.g., 1.0 → 1.1 for minor changes, 1.0 → 2.0 for structural changes)
2. Add an entry to the Change Log below
3. Document what changed and why
4. Note that historical data before the version change is not directly comparable to data after it

This matters because trend charts are only meaningful if the underlying measurement is consistent. A CSOV drop from 68 to 62 should mean "our reputation got worse," not "we changed the formula."

---

## Change Log

### v1.0 — June 2026
- Initial release. Baseline locked on two weeks of data (May 25–31 and June 1–7, 2026).
- Components: SERP 35%, AI Overview 25%, LLM 25%, Earned Media 15%.
- Sentiment classification: content-first for SERP and Earned Media; 0–100 Claude prompt for AI Overview and LLM.
- Trustpilot, Sitejabber, TripAdvisor, Yelp: excluded from earned media.
- Always-negative domains: bbb.org, ripoffreport.com, scamalert.com, complaints.com, pissedconsumer.com, complaintsboard.com, scamadviser.com, reviewopedia.com.
- No-AI-Overview queries: excluded (not counted as zero).
- AI Overview scoring: content quality only; no penalty for iVisa not being explicitly cited.
