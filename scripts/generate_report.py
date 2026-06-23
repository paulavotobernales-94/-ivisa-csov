"""
generate_report.py — Generates a self-contained interactive HTML report.
All data is embedded as JSON in the HTML; no external data fetching at view time.
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>iVisa Credibility Share of Voice Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    /* iVisa brand palette — matched from ivisa.com */
    --green:      #00EA80;   /* iVisa hero green — CTA, accents, highlights */
    --green-mid:  #00D474;   /* green-500 — positive signals */
    --green-dark: #0DB770;   /* green-600 — text on light bg */
    --navy:       #0A2540;   /* deep navy — headlines, header bg */
    --navy-light: #133A5E;   /* slightly lighter navy */
    --blue:       #394FE1;   /* electric blue — links, tabs */
    --sky:        #08ADE4;   /* light blue — secondary data */
    --yellow:     #F59E0B;   /* amber — warning/neutral */
    --red:        #EF4444;   /* red — negative */
    --bg:         #F4FBF7;   /* very light mint — page background */
    --card:       #ffffff;
    --border:     #D8EDE4;   /* soft green-tinted border */
    --text:       #0A2540;   /* same as navy for body text */
    --muted:      #5A7A6A;
    --radius:     12px;
    --shadow:     0 1px 3px rgba(10,37,64,.07), 0 4px 16px rgba(10,37,64,.06);
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Manrope', Arial, sans-serif;
         background: var(--bg); color: var(--text); line-height: 1.5; }

  /* ── Header ── */
  .header { background: #fff;
             color: var(--navy); padding: 18px 32px; display: flex; align-items: center;
             justify-content: space-between; gap: 16px; flex-wrap: wrap;
             border-bottom: 3px solid var(--green);
             box-shadow: 0 2px 8px rgba(0,0,0,.06); }
  .header-brand { display: flex; align-items: center; gap: 14px; }
  .header-logo { display: flex; align-items: center; gap: 10px; }
  .header-title h1 { font-size: 1.25rem; font-weight: 700; color: var(--navy); }
  .header-title p  { font-size: .8rem; color: var(--muted); }
  .header-meta { text-align: right; font-size: .8rem; color: var(--muted); }
  .header-meta strong { display: block; font-size: 1rem; opacity: 1; }

  /* ── Past Reports Dropdown ── */
  .past-reports-wrap { position: relative; display: inline-block; }
  .past-reports-btn {
    display: flex; align-items: center; gap: 6px;
    background: var(--navy); color: #fff;
    border: none; border-radius: 8px; padding: 8px 14px;
    font-size: .82rem; font-weight: 600; font-family: inherit;
    cursor: pointer; white-space: nowrap;
    transition: background .15s;
  }
  .past-reports-btn:hover { background: var(--navy-light); }
  .past-reports-btn svg { flex-shrink: 0; }
  .past-reports-menu {
    display: none; position: absolute; right: 0; top: calc(100% + 6px);
    background: #fff; border: 1px solid var(--border); border-radius: 10px;
    box-shadow: 0 8px 24px rgba(10,37,64,.12);
    min-width: 200px; z-index: 999; overflow: hidden;
  }
  .past-reports-menu.open { display: block; }
  .past-reports-menu a {
    display: block; padding: 10px 16px; font-size: .82rem; color: var(--navy);
    text-decoration: none; border-bottom: 1px solid var(--border);
    transition: background .1s;
  }
  .past-reports-menu a:last-child { border-bottom: none; }
  .past-reports-menu a:hover { background: var(--bg); color: var(--blue); }

  /* ── Layout ── */
  .container { max-width: 1280px; margin: 0 auto; padding: 32px 24px; }
  .section-title { font-size: 1.1rem; font-weight: 800; color: var(--navy);
                   margin-bottom: 16px; padding-bottom: 8px;
                   border-bottom: 3px solid var(--green); }

  /* ── Hero ── */
  .hero { display: flex; gap: 24px; align-items: stretch; margin-bottom: 32px; flex-wrap: wrap; }
  .hero-score-card { background: var(--card); border-radius: var(--radius);
                      box-shadow: var(--shadow); padding: 32px;
                      display: flex; flex-direction: column; align-items: center;
                      justify-content: center; gap: 12px; flex: 0 0 320px; }
  .hero-score-number { font-size: 5rem; font-weight: 900; color: var(--navy); line-height: 1; }
  .hero-score-denom  { font-size: 1.5rem; color: var(--muted); font-weight: 400; }
  .hero-score-label  { font-size: .9rem; color: var(--muted); text-transform: uppercase;
                        letter-spacing: .06em; }
  .badge { display: inline-flex; align-items: center; gap: 5px; padding: 4px 12px;
            border-radius: 20px; font-size: .82rem; font-weight: 700; }
  .badge-up   { background: #D0F7E6; color: var(--green-dark); }
  .badge-down { background: #FEE2E2; color: var(--red); }
  .badge-flat { background: #EAF2EC; color: var(--muted); }
  .hero-week  { font-size: .85rem; color: var(--muted); }

  /* ── Gauge ── */
  .gauge-wrap { width: 180px; height: 100px; position: relative; }
  .gauge-wrap svg { width: 100%; height: 100%; }

  /* ── Component Cards ── */
  .component-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
                     margin-bottom: 32px; }
  @media(max-width:900px){ .component-grid { grid-template-columns: repeat(2,1fr); } }
  @media(max-width:500px){ .component-grid { grid-template-columns: 1fr; } }
  .comp-card { background: var(--card); border-radius: var(--radius); box-shadow: var(--shadow);
               padding: 20px; display: flex; flex-direction: column; gap: 10px; }
  .comp-card-header { display: flex; justify-content: space-between; align-items: flex-start; }
  .comp-card-title  { font-size: .8rem; text-transform: uppercase; letter-spacing: .05em;
                       color: var(--muted); font-weight: 600; }
  .comp-card-weight { font-size: .75rem; color: var(--muted); background: var(--bg);
                       padding: 2px 8px; border-radius: 10px; }
  .comp-score { font-size: 2.2rem; font-weight: 800; color: var(--navy); line-height: 1; }
  .comp-score span { font-size: 1rem; color: var(--muted); font-weight: 400; }
  .progress-bar { height: 7px; background: var(--border); border-radius: 4px; overflow: hidden; }
  .progress-fill { height: 100%; border-radius: 4px; transition: width .6s ease; }
  .fill-green  { background: linear-gradient(90deg, var(--green-mid) 0%, var(--green) 100%); }
  .fill-yellow { background: var(--yellow); }
  .fill-red    { background: var(--red); }
  .fill-blue   { background: var(--blue); }

  /* ── Charts ── */
  .chart-card { background: var(--card); border-radius: var(--radius); box-shadow: var(--shadow);
                 padding: 24px; margin-bottom: 32px; }
  .chart-container { position: relative; height: 300px; }

  /* ── Country Grid ── */
  .country-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px;
                   margin-bottom: 32px; }
  @media(max-width:900px){ .country-grid { grid-template-columns: repeat(3,1fr); } }
  @media(max-width:500px){ .country-grid { grid-template-columns: repeat(2,1fr); } }
  .country-card { background: var(--card); border-radius: var(--radius); box-shadow: var(--shadow);
                   padding: 16px; cursor: pointer; transition: transform .15s, box-shadow .15s;
                   border: 2px solid transparent; }
  .country-card:hover  { transform: translateY(-2px); box-shadow: 0 6px 24px rgba(0,0,0,.12); }
  .country-card.active { border-color: var(--blue); }
  .country-flag  { font-size: 2rem; margin-bottom: 6px; }
  .country-name  { font-size: .8rem; font-weight: 600; color: var(--navy); margin-bottom: 4px; }
  .country-score { font-size: 1.5rem; font-weight: 800; color: var(--navy); }
  .mini-bar-wrap { display: flex; gap: 2px; margin-top: 8px; height: 5px; border-radius: 3px; overflow:hidden; }
  .mini-seg { height: 100%; }

  /* ── Country Selector + Tables ── */
  .country-detail { background: var(--card); border-radius: var(--radius); box-shadow: var(--shadow);
                     padding: 24px; margin-bottom: 32px; }
  .tab-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; }
  .tab-btn { padding: 7px 16px; border-radius: 8px; border: 1.5px solid var(--border);
              background: #fff; font-size: .85rem; cursor: pointer; transition: all .15s;
              font-weight: 600; color: var(--muted); }
  .tab-btn:hover  { border-color: var(--blue); color: var(--blue); }
  .tab-btn.active { background: var(--blue); color: #fff; border-color: var(--blue); }
  .tab-content { display: none; }
  .tab-content.active { display: block; }

  /* ── Tables ── */
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: .85rem; }
  th { background: var(--bg); padding: 10px 14px; text-align: left; font-weight: 600;
       color: var(--muted); font-size: .78rem; text-transform: uppercase;
       letter-spacing: .04em; border-bottom: 2px solid var(--border); }
  td { padding: 10px 14px; border-bottom: 1px solid var(--border); vertical-align: middle; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #f8fafc; }
  .pos-badge { display: inline-flex; align-items: center; justify-content: center;
               width: 28px; height: 28px; border-radius: 8px; font-weight: 700;
               font-size: .85rem; }
  .pos-1 { background: #fef3c7; color: #92400e; }
  .pos-top3 { background: #dbeafe; color: #1e40af; }
  .pos-mid   { background: #f1f5f9; color: var(--muted); }
  .pos-bad   { background: #fee2e2; color: var(--red); }
  .pill { padding: 2px 10px; border-radius: 10px; font-size: .75rem; font-weight: 700; }
  .pill-pos  { background: #D0F7E6; color: var(--green-dark); }
  .pill-neg  { background: #FEE2E2; color: var(--red); }
  .pill-neu  { background: #EAF2EC; color: var(--muted); }
  .pill-yes  { background: #D0F7E6; color: var(--green-dark); }
  .pill-no   { background: #EAF2EC; color: var(--muted); }
  .domain-link { color: var(--blue); text-decoration: none; font-size: .8rem; font-weight: 500; }
  .domain-link:hover { text-decoration: underline; }
  .ivisa-row td { background: #E8EBFF !important; font-weight: 700; }

  /* ── Methodology Panel ── */
  .method-panel { background: var(--card); border-radius: var(--radius); box-shadow: var(--shadow);
                   padding: 0; margin-bottom: 32px; overflow: hidden; }
  .method-toggle { width: 100%; text-align: left; padding: 16px 24px; border: none; background: none;
                    cursor: pointer; display: flex; justify-content: space-between; align-items: center;
                    font-size: .9rem; font-weight: 600; color: var(--navy); }
  .method-toggle:hover { background: var(--bg); }
  .method-body { display: none; padding: 0 24px 24px; border-top: 1px solid var(--border); }
  .method-body.open { display: block; }
  .method-grid { display: grid; grid-template-columns: repeat(2,1fr); gap: 20px; margin-top: 16px; }
  @media(max-width:700px){ .method-grid { grid-template-columns: 1fr; } }
  .method-item { background: var(--bg); border-radius: 10px; padding: 16px; }
  .method-item h4 { font-size: .85rem; font-weight: 700; color: var(--navy); margin-bottom: 8px; }
  .method-item p, .method-item li { font-size: .8rem; color: var(--muted); line-height: 1.6; }
  .method-item ul { padding-left: 16px; }
  .method-formula { font-family: monospace; background: var(--navy); color: var(--green);
                     padding: 10px 14px; border-radius: 8px; font-size: .8rem;
                     margin-top: 10px; white-space: pre-wrap; font-weight: 700; }

  /* ── LLM Section ── */
  .llm-tabs { display: flex; gap: 8px; margin-bottom: 16px; }
  .llm-response-full { font-size: .78rem; color: var(--muted); line-height: 1.5;
                        max-height: 100px; overflow: hidden; transition: max-height .3s;
                        cursor: pointer; }
  .llm-response-full.expanded { max-height: none; overflow: visible; }
  .llm-expand-hint { font-size: .72rem; color: var(--blue); cursor: pointer; margin-top: 3px; }

  /* ── AIO text ── */
  .aio-text-cell { font-size: .78rem; color: var(--muted); line-height: 1.5;
                    max-height: 60px; overflow: hidden; cursor: pointer; }
  .aio-text-cell.expanded { max-height: none; overflow: visible; }

  /* ── Sentiment Counts ── */
  .sent-counts { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
  .sent-chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 9px;
               border-radius: 12px; font-size: .74rem; font-weight: 700; }
  .sent-chip-pos { background: #D0F7E6; color: var(--green-dark); }
  .sent-chip-neu { background: #EAF2EC; color: var(--muted); }
  .sent-chip-neg { background: #FEE2E2; color: var(--red); }

  /* ── Period Framework ── */
  .period-panel { background: var(--card); border-radius: var(--radius); box-shadow: var(--shadow);
                   padding: 24px; margin-bottom: 32px; }
  .period-grid  { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 16px; }
  @media(max-width:700px){ .period-grid { grid-template-columns: 1fr; } }
  .period-col   { background: var(--bg); border-radius: 10px; padding: 16px; }
  .period-col h4 { font-size: .88rem; font-weight: 700; color: var(--navy); margin-bottom: 12px; }
  .period-row   { display: flex; justify-content: space-between; align-items: center;
                   padding: 6px 0; border-bottom: 1px solid var(--border); font-size: .83rem; }
  .period-row:last-child { border-bottom: none; }
  .period-label { color: var(--muted); }
  .period-val   { font-weight: 700; color: var(--navy); }
  .period-delta-pos { color: var(--green); font-weight: 700; }
  .period-delta-neg { color: var(--red); font-weight: 700; }
  .period-target { background: #eff6ff; color: var(--blue); padding: 2px 8px;
                    border-radius: 8px; font-size: .78rem; font-weight: 600; }

  /* ── Earned Media ── */
  .mentions-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
  @media(max-width:800px){ .mentions-grid { grid-template-columns: 1fr; } }
  .mention-card { background: var(--bg); border-radius: 10px; padding: 16px;
                   border: 1px solid var(--border); }
  .mention-source { font-size: .75rem; text-transform: uppercase; letter-spacing: .05em;
                     color: var(--muted); font-weight: 600; margin-bottom: 6px; }
  .mention-title  { font-size: .9rem; font-weight: 600; color: var(--navy); margin-bottom: 6px; }
  .mention-footer { display: flex; gap: 8px; align-items: center; font-size: .78rem; color: var(--muted); }

  /* ── Action Items ── */
  .actions-list { list-style: none; display: flex; flex-direction: column; gap: 10px; }
  .action-item  { display: flex; gap: 12px; align-items: flex-start; background: var(--card);
                   border-radius: 10px; padding: 14px 16px; border-left: 4px solid var(--green);
                   box-shadow: var(--shadow); }
  .action-icon  { font-size: 1.1rem; flex-shrink: 0; margin-top: 1px; }
  .action-text  { font-size: .9rem; color: var(--text); }

  /* ── Footer ── */
  .footer { text-align: center; padding: 24px; font-size: .78rem; color: var(--muted);
             border-top: 1px solid var(--border); margin-top: 16px; }

  /* ── Hero chart ── */
  .hero-chart { flex: 1; min-width: 280px; }
</style>
</head>
<body>

<!-- HEADER -->
<header class="header">
  <div class="header-brand">
    <div class="header-logo">
      <img src="ivisa_logo.png" alt="iVisa" style="height:32px;width:auto;" onerror="this.style.display='none';document.getElementById('logoFallback').style.display='flex';">
      <span id="logoFallback" style="display:none;align-items:center;gap:8px;"><svg width="36" height="28" viewBox="0 0 36 28" fill="none"><path d="M2 6 C6 6 10 14 14 20 C18 10 24 2 34 2" stroke="#00EA80" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg><span style="font-size:1.4rem;font-weight:900;color:var(--navy);">iVISA</span></span>
    </div>
    <div class="header-title">
      <p style="font-size:.82rem;opacity:.7;margin-top:2px;">Credibility Share of Voice Dashboard</p>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;justify-content:flex-end;">
    <div class="past-reports-wrap">
      <button class="past-reports-btn" onclick="toggleArchiveMenu()" id="archiveBtn">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M3 7h18M3 12h18M3 17h18"/></svg>
        Past Reports
      </button>
      <div class="past-reports-menu" id="archiveMenu">
        __ARCHIVE_LINKS_PLACEHOLDER__
      </div>
    </div>
    <div class="header-meta">
      <strong id="weekRange">Loading...</strong>
      Updated every Monday
    </div>
  </div>
</header>

<div class="container">

  <!-- HERO -->
  <div class="hero" style="margin-bottom:32px;">
    <div class="hero-score-card">
      <div class="gauge-wrap" id="gaugeWrap"></div>
      <div class="hero-score-number" id="heroScore">--</div>
      <div class="hero-score-denom">/100 CSOV</div>
      <div id="heroBadge"></div>
      <div class="hero-week" id="heroWeek"></div>
    </div>
    <div class="hero-chart chart-card" style="flex:1;min-width:280px;">
      <div class="section-title" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
        <span id="trendChartTitle">CSOV Trend</span>
        <div style="display:flex;align-items:center;gap:8px;">
          <div id="viewToggle" style="display:flex;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden;font-size:11px;">
            <button onclick="setChartView('weekly')"  id="btn-weekly"  style="padding:4px 10px;border:none;cursor:pointer;font-family:inherit;background:#00EA80;color:#0A2540;font-weight:600;">Weekly</button>
            <button onclick="setChartView('monthly')" id="btn-monthly" style="padding:4px 10px;border:none;cursor:pointer;font-family:inherit;background:transparent;color:#64748b;">Monthly</button>
          </div>
          <button onclick="downloadTrendCSV()" style="font-size:11px;padding:4px 10px;border:1px solid #00EA80;background:transparent;color:#00EA80;border-radius:6px;cursor:pointer;font-family:inherit;">⬇ Download CSV</button>
        </div>
      </div>
      <div class="chart-container"><canvas id="trendChart"></canvas></div>
    </div>
  </div>

  <!-- COMPONENT CARDS -->
  <div class="section-title">Component Breakdown</div>
  <div class="component-grid" id="componentGrid"></div>

  <!-- METHODOLOGY PANEL -->
  <div class="method-panel">
    <button class="method-toggle" onclick="toggleMethod(this)">
      ℹ️ How is this score calculated? — Click to expand scoring methodology
      <span id="methodArrow">▼</span>
    </button>
    <div class="method-body" id="methodBody">
      <div class="method-grid">
        <div class="method-item" style="grid-column:1/-1;">
          <h4>🧮 What does the score mean?</h4>
          <p><strong>The CSOV score measures what % of online signals about iVisa are positive.</strong>
          A score of 50 = perfectly neutral (equal positive and negative signals). Above 50 = more positive. Below 50 = more negative than positive.
          So a score of 68 means: "68% of everything the internet says about iVisa — in search results, AI answers, LLM responses, and press — leans positive."</p>
          <div class="method-formula">CSOV = (SERP × 35%) + (AI Overview × 25%) + (LLM × 25%) + (Earned Media × 15%)</div>
          <p style="margin-top:8px;">Country scores use the same formula with country-specific SERP and AI Overview data. The global score is a weighted average across 10 countries.</p>
        </div>

        <div class="method-item">
          <h4>🔍 SERP Score (35%) — How it's calculated</h4>
          <p>We check the <strong>top 10 Google results</strong> for up to 11 brand keywords across 10 countries (~1,100 results), in each market's local language. Each result is classified:</p>
          <p style="margin-top:8px;">We classify each result by reading the <strong>title + preview snippet text</strong> — not by domain. Trustpilot with a 1-star review is negative. Forbes praising iVisa is positive. The content decides, not the website name.</p>
          <p style="margin-top:8px;"><strong>🔴 Negative</strong> — text contains: "scam", "fraud", "fake", "avoid", "warning", "do not use", "beware", "rip off", "never again", "not legit", "not safe", "overcharged", "refund denied", "stay away", "suspicious" — <em>or</em> the domain is a structural complaint site (bbb.org, ripoffreport.com, scamalert.com)</p>
          <p style="margin-top:8px;"><strong>🟢 Positive</strong> — text contains: "not a scam", "is legit", "is safe", "trusted", "recommend", "works", "my experience was good", "why use iVisa", "yes iVisa is trustworthy", "honest review", "no issues", "smooth process", "helped me", "great service"</p>
          <p style="margin-top:8px;"><strong>⚪ Neutral (mixed)</strong> — text contains <em>both</em> positive and negative signals (e.g. "iVisa isn't a scam, it charges fees but does the work for you") — or no strong signal either way.</p>
          <p style="margin-top:8px;">Position weighting: result #1 counts <strong>10×</strong> more than result #10. Score = (weighted positive sum ÷ total weight) × 100.</p>
        </div>

        <div class="method-item">
          <h4>🤖 AI Overview Score (25%) — How it's calculated</h4>
          <p>Checks what Google's AI-generated answer box says when it appears for iVisa keywords. We care about the <strong>quality and sentiment</strong> of what it says — not just whether iVisa appears.</p>
          <ul style="margin-top:8px;">
            <li><strong>AI Overview appears</strong> → Claude reads the full text and scores sentiment 0–100. Fully positive ("highly rated, trusted service, streamlined process") = 75–90. Mixed with a "Drawbacks" or "Criticisms" section (fees, refund policy, third-party status) = 45–60. Negative overview = below 40.</li>
            <li><strong>No AI Overview shown</strong> → score = 50 (neutral baseline — no appearance is not a problem, just no signal)</li>
          </ul>
          <p style="margin-top:8px;">When specific weaknesses appear in the AI Overview text (e.g. refund policy, fees), the Action Items section generates a targeted content recommendation to counter that narrative.</p>
          <p style="margin-top:8px;">Final score = weighted average across up to 11 keywords × 10 countries, weighted by country traffic share.</p>
        </div>

        <div class="method-item">
          <h4>💬 LLM Score (25%) — How it's calculated</h4>
          <p>We ask Claude 50 questions and analyse its responses. Two parts:</p>
          <ul style="margin-top:8px;">
            <li><strong>Part A (20 direct brand questions):</strong> "Is iVisa legit?", "Can I trust iVisa?", "Is iVisa a scam?" etc.
            Claude reads each response and scores its sentiment 0–100. 100 = "strongly recommended", 0 = "avoid completely".</li>
            <li><strong>Part B (30 general travel questions):</strong> "Best visa service?", "Safest way to apply for a visa online?" etc.
            Score = (mention rate × 40%) + (average sentiment when mentioned × 60%).</li>
          </ul>
          <p style="margin-top:8px;">LLM Score = (Part A score + Part B score) ÷ 2. Scored by Claude (Gemini is currently disabled).</p>
        </div>

        <div class="method-item">
          <h4>📰 Earned Media Score (15%) — How it's calculated</h4>
          <p>We search for iVisa mentions across third-party channels only (iVisa-owned accounts are excluded). <strong>Review aggregators (Trustpilot, Sitejabber, TripAdvisor, BBB) are also excluded</strong> — they reflect customer feedback, not editorial coverage, and are tracked separately in the SERP component.</p>
          <p style="margin-top:8px;">Sources counted in Earned Media:</p>
          <ul style="margin-top:8px;">
            <li>📰 <strong>Google News</strong> — press articles mentioning iVisa</li>
            <li>✈️ <strong>Travel editorial & press</strong> — Forbes, Lonely Planet, Skift, Nomadicmatt, The Points Guy, BBC, Guardian, etc.</li>
            <li>💬 <strong>Reddit</strong> — excluding r/ivisa (iVisa-owned)</li>
            <li>▶️ <strong>YouTube</strong> — third-party video reviews and travel content</li>
            <li>📸 <strong>Instagram &amp; 🎵 TikTok</strong> — excluding @ivisa official accounts</li>
          </ul>
          <p style="margin-top:8px;">Each mention is classified positive/neutral/negative from title + snippet text signals. Score = simple average across all mentions (no position weighting).</p>
        </div>

        <div class="method-item">
          <h4>📊 Score Thresholds &amp; Measurement Periods</h4>
          <ul>
            <li>🟢 <strong>75–100:</strong> Healthy — maintain strategy</li>
            <li>🟡 <strong>55–74:</strong> Needs attention — some risks present</li>
            <li>🔴 <strong>0–54:</strong> Critical — active reputation risk</li>
          </ul>
          <p style="margin-top:8px;"><strong>Data sources:</strong> SEMrush, Ahrefs, SerpAPI (Google), Claude (Anthropic), Gemini (Google).</p>
        </div>
      </div>
    </div>
  </div>

  <!-- WHAT'S DRIVING THE SCORE THIS WEEK -->
  <div class="period-panel" id="scoreAnalysisPanel" style="margin-bottom:24px;">
    <div class="section-title" style="margin-bottom:4px;">🔍 What's Driving the Score This Week</div>
    <p style="font-size:.82rem;color:var(--muted);margin-bottom:14px;">Auto-generated from SERP, AI Overview, LLM and country data</p>
    <ul id="scoreAnalysisList" style="list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:10px;"></ul>
  </div>

  <!-- COUNTRY BREAKDOWN -->
  <div class="section-title">Country Breakdown</div>
  <div class="country-grid" id="countryGrid"></div>

  <!-- DETAIL SECTION -->
  <div class="country-detail">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:10px;">
      <h2 class="section-title" style="margin:0;border:none;" id="detailTitle">United States — Detail</h2>
      <div class="tab-bar" id="countryTabs"></div>
    </div>

    <!-- SERP Tab -->
    <div class="tab-content active" id="tab-serp">
      <h3 style="font-size:.9rem;font-weight:600;color:var(--muted);margin-bottom:4px;">Top 10 SERP Results per Keyword</h3>
      <p style="font-size:.78rem;color:var(--muted);margin-bottom:16px;">
        Score = weighted sentiment of all 10 results (pos 1 = highest weight).
        🟢 Positive &nbsp;⚪ Neutral &nbsp;🔴 Negative
      </p>
      <div id="serpKeywordBlocks"></div>
    </div>

    <!-- AI Overview Tab -->
    <div class="tab-content" id="tab-aio">
      <h3 style="font-size:.9rem;font-weight:600;color:var(--muted);margin-bottom:4px;">Google AI Overview Results</h3>
      <p style="font-size:.78rem;color:var(--muted);margin-bottom:16px;">
        Score logic: AI Overview appears → Claude sentiment score (0–100) &nbsp;|&nbsp;
        No AI overview → not counted. Click AI Overview text to expand.
      </p>
      <div class="table-wrap"><table id="aioTable">
        <thead><tr>
          <th>Keyword</th><th>AI Overview?</th><th>iVisa Cited?</th>
          <th>AI Overview Text</th><th>What to fix</th><th>Sources</th><th style="text-align:right;">Score</th>
        </tr></thead>
        <tbody id="aioTableBody"></tbody>
      </table></div>
    </div>

    <!-- LLM Tab -->
    <div class="tab-content" id="tab-llm">
      <p style="font-size:.78rem;color:var(--muted);margin-bottom:6px;">
        <strong>Part A:</strong> 20 direct brand queries scored 0–100 sentiment by Claude. &nbsp;
        <strong>Part B:</strong> 30 general travel queries — score = mention rate (40%) + sentiment when cited (60%). &nbsp;
        LLM Score = (A + B) / 2. Click any response to expand.
      </p>
      <p style="font-size:.76rem;color:var(--muted);margin-bottom:12px;">
        🌐 <strong>Global score</strong> — LLM responses are the same regardless of country (AI models don't have location-specific knowledge).
      </p>
      <div id="llmCountryNote" style="display:none;font-size:.78rem;color:#64748b;background:#f8fafc;border-left:3px solid #08ADE4;padding:6px 10px;margin-bottom:10px;border-radius:4px;"></div>
      <div id="llmCountrySection" style="display:none;"></div>
      <div class="llm-tabs">
        <button class="tab-btn active" onclick="showLlmTab('parta',this)">Part A — Brand Queries (20)</button>
        <button class="tab-btn"        onclick="showLlmTab('partb',this)">Part B — General Queries (30)</button>
      </div>
      <div id="llm-parta">
        <div class="table-wrap"><table>
          <thead><tr><th>Query</th><th>Claude Response &amp; Score</th><th class="gemini-col">Gemini Response, Score &amp; Sources</th><th>Avg</th><th>What to Fix</th></tr></thead>
          <tbody id="llmPartABody"></tbody>
        </table></div>
      </div>
      <div id="llm-partb" style="display:none;">
        <div class="table-wrap"><table>
          <thead><tr><th>Query</th><th>Claude Response</th><th class="gemini-col">Gemini Response</th><th>iVisa Mentioned?</th><th>Avg Sentiment</th></tr></thead>
          <tbody id="llmPartBBody"></tbody>
        </table></div>
      </div>
    </div>

    <!-- Earned Media Tab -->
    <div class="tab-content" id="tab-em">
      <div id="emCountryNote" style="display:none;font-size:.78rem;color:#64748b;background:#f8fafc;border-left:3px solid #00EA80;padding:6px 10px;margin-bottom:10px;border-radius:4px;"></div>
      <div id="emCountrySection" style="display:none;"></div>
      <div class="mentions-grid" id="mentionsGrid"></div>
    </div>
  </div>

  <!-- ACTION ITEMS -->
  <div class="chart-card" style="margin-bottom:32px;">
    <div class="section-title" id="actionItemsTitle">Action Items — SERP</div>
    <ul class="actions-list" id="actionsList"></ul>
  </div>

</div>

<!-- FOOTER -->
<footer class="footer">
  Generated automatically every Friday at 10 AM UTC &bull; iVisa Brand Team &bull; Credibility Share of Voice Dashboard
</footer>

<script>
// ── Embedded Data ──────────────────────────────────────────────────────────
const REPORT_DATA = __REPORT_DATA_PLACEHOLDER__;

// ── Past Reports Dropdown ───────────────────────────────────────────────────
function toggleArchiveMenu() {
  const menu = document.getElementById('archiveMenu');
  menu.classList.toggle('open');
}
document.addEventListener('click', function(e) {
  const wrap = document.querySelector('.past-reports-wrap');
  if (wrap && !wrap.contains(e.target)) {
    document.getElementById('archiveMenu').classList.remove('open');
  }
});

// ── Utilities ──────────────────────────────────────────────────────────────
function scoreColor(s) {
  if (s >= 75) return '#00EA80';
  if (s >= 55) return '#F59E0B';
  return '#EF4444';
}
function fillClass(s) {
  if (s >= 75) return 'fill-green';
  if (s >= 55) return 'fill-yellow';
  return 'fill-red';
}
function posBadge(p) {
  const cls = p === 1 ? 'pos-1' : p <= 3 ? 'pos-top3' : p <= 7 ? 'pos-mid' : 'pos-bad';
  return `<span class="pos-badge ${cls}">${p}</span>`;
}
function pillSentiment(s) {
  const map = { positive:'pill-pos', negative:'pill-neg', neutral:'pill-neu' };
  return `<span class="pill ${map[s]||'pill-neu'}">${s||'neutral'}</span>`;
}
function pillBool(b, labelY='Yes', labelN='No') {
  return b
    ? `<span class="pill pill-yes">${labelY}</span>`
    : `<span class="pill pill-no">${labelN}</span>`;
}
function fmtScore(v) {
  return v == null ? '—' : Number(v).toFixed(1);
}

// ── Gauge SVG ──────────────────────────────────────────────────────────────
function buildGauge(score) {
  const pct   = Math.min(Math.max(score, 0), 100) / 100;
  const angle = -180 + pct * 180;   // -180° to 0°
  const r = 70, cx = 90, cy = 90;
  const toRad = d => d * Math.PI / 180;
  const arcX  = cx + r * Math.cos(toRad(angle - 90));
  const arcY  = cy + r * Math.sin(toRad(angle - 90));
  const color = score >= 75 ? '#00EA80' : score >= 55 ? '#F59E0B' : '#EF4444';

  return `<svg viewBox="0 0 180 95" xmlns="http://www.w3.org/2000/svg">
    <path d="M20,90 A70,70 0 0,1 160,90" fill="none" stroke="#e2e8f0" stroke-width="14" stroke-linecap="round"/>
    <path d="M20,90 A70,70 0 0,1 ${arcX.toFixed(2)},${arcY.toFixed(2)}" fill="none"
          stroke="${color}" stroke-width="14" stroke-linecap="round"/>
    <circle cx="${arcX.toFixed(2)}" cy="${arcY.toFixed(2)}" r="6" fill="${color}"/>
  </svg>`;
}

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const D = REPORT_DATA;

  // Header
  document.getElementById('weekRange').textContent = D.week_label || '';
  document.getElementById('heroWeek').textContent  = 'Week of ' + (D.week_start || '');

  // Hero score
  const csov = D.csov_score || 0;
  document.getElementById('heroScore').textContent  = csov.toFixed(1);
  document.getElementById('gaugeWrap').innerHTML = buildGauge(csov);

  // Trend badge
  const prev  = D.previous_csov_score;
  const diff  = prev != null ? csov - prev : null;
  const bdEl  = document.getElementById('heroBadge');
  if (diff != null) {
    const cls  = diff > 0 ? 'badge-up' : diff < 0 ? 'badge-down' : 'badge-flat';
    const sign = diff > 0 ? '+' : '';
    bdEl.innerHTML = `<span class="badge ${cls}">${sign}${diff.toFixed(1)} MoM</span>`;
  }

  // Component Cards
  buildComponentCards(D.components);

  // Trend Chart
  buildTrendChart(D.historical);

  // Country Grid
  buildCountryGrid(D.country_data);

  // Country Detail Tabs
  buildCountryTabs(D.country_data);

  // LLM Tables
  buildLlmTables(D.llm_data);

  // Earned Media
  buildEarnedMedia(D.earned_media);

  // Score Analysis — What's Driving the Score This Week
  buildScoreAnalysis(D);

  // Actions
  buildActions(D.action_items);

  // Select first country by default
  const firstCode = Object.keys(D.country_data)[0];
  if (firstCode) selectCountry(firstCode, D);
});

// ── Component Cards ────────────────────────────────────────────────────────
function buildComponentCards(components) {
  const grid = document.getElementById('componentGrid');
  const items = [
    { key: 'serp',         label: 'SERP Score',        icon: '🔍', weight: '35%' },
    { key: 'ai_overview',  label: 'AI Overview Score',  icon: '🤖', weight: '25%' },
    { key: 'llm',          label: 'LLM Score',          icon: '💬', weight: '25%' },
    { key: 'earned_media', label: 'Earned Media Score', icon: '📰', weight: '15%' },
  ];

  // Pre-compute sentiment counts per component from raw data
  const D = REPORT_DATA;
  function serpSentCounts() {
    const c = { positive: 0, neutral: 0, negative: 0 };
    Object.values(D.serp_data?.results || {}).forEach(countryKws => {
      Object.values(countryKws).forEach(results => {
        (results || []).forEach(r => { if (r.sentiment) c[r.sentiment] = (c[r.sentiment]||0) + 1; });
      });
    });
    return c;
  }
  function aioSentCounts() {
    const c = { positive: 0, neutral: 0, negative: 0 };
    Object.values(D.ai_overview_data?.results || {}).forEach(countryKws => {
      Object.values(countryKws).forEach(r => {
        if (r.has_ai_overview && r.sentiment_score != null) {
          const s = r.sentiment_score >= 65 ? 'positive' : r.sentiment_score >= 40 ? 'neutral' : 'negative';
          c[s]++;
        }
      });
    });
    return c;
  }
  function llmSentCounts() {
    const c = { positive: 0, neutral: 0, negative: 0 };
    (D.llm_data?.part_a?.results || []).forEach(r => {
      const avg = r.avg_sentiment;
      if (avg != null) { const s = avg >= 65 ? 'positive' : avg >= 40 ? 'neutral' : 'negative'; c[s]++; }
    });
    return c;
  }
  function emSentCounts() {
    const counts = D.earned_media?.counts;
    if (counts) return { positive: counts.positive||0, neutral: counts.neutral||0, negative: counts.negative||0 };
    return { positive: 0, neutral: 0, negative: 0 };
  }
  const sentCountsMap = { serp: serpSentCounts(), ai_overview: aioSentCounts(), llm: llmSentCounts(), earned_media: emSentCounts() };

  function sentCountsHtml(counts) {
    if (!counts || (!counts.positive && !counts.neutral && !counts.negative)) return '';
    return `<div class="sent-counts">
      <span class="sent-chip sent-chip-pos">🟢 ${counts.positive}</span>
      <span class="sent-chip sent-chip-neu">⚪ ${counts.neutral}</span>
      <span class="sent-chip sent-chip-neg">🔴 ${counts.negative}</span>
    </div>`;
  }

  items.forEach(({ key, label, icon, weight }) => {
    const comp  = components[key] || {};
    const score = comp.score || 0;
    const prev  = comp.prev_score;
    const diff  = prev != null ? (score - prev) : null;
    const trend = diff != null
      ? `<span class="badge ${diff>0?'badge-up':diff<0?'badge-down':'badge-flat'}">${diff>0?'+':''}${diff.toFixed(1)}</span>`
      : '';

    grid.innerHTML += `
      <div class="comp-card">
        <div class="comp-card-header">
          <span class="comp-card-title">${icon} ${label}</span>
          <span class="comp-card-weight">${weight}</span>
        </div>
        <div class="comp-score">${score.toFixed(1)}<span>/100</span></div>
        <div class="progress-bar">
          <div class="progress-fill ${fillClass(score)}" style="width:${score}%"></div>
        </div>
        ${sentCountsHtml(sentCountsMap[key])}
        ${trend}
      </div>`;
  });
}

// ── Trend Chart ────────────────────────────────────────────────────────────

// Parse "Jun 01 – Jun 07, 2026" or "May 2026" → { year, month } of the END date
function parseWeekLabel(label) {
  // Monthly label e.g. "May 2026"
  const mono = label.match(/^(\w+)\s+(\d{4})$/);
  if (mono) {
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return { year: +mono[2], month: months.indexOf(mono[1]) + 1 };
  }
  // Weekly label e.g. "Jun 01 – Jun 07, 2026" — use the end date
  const weekly = label.match(/(\w+)\s+\d+\s*[–-]\s*(\w+)\s+\d+,\s*(\d{4})/);
  if (weekly) {
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return { year: +weekly[3], month: months.indexOf(weekly[2]) + 1 };
  }
  return null;
}

function avgLast2(items, field) {
  const vals = items.slice(-2).map(x => x[field] || 0);
  return vals.length ? +(vals.reduce((a,b)=>a+b,0)/vals.length).toFixed(2) : 0;
}

// Aggregate weekly history → monthly points (avg of last 2 weeks of each month)
function toMonthly(history) {
  const byMonth = {};
  history.forEach(h => {
    const p = parseWeekLabel(h.week_label);
    if (!p) return;
    const key = `${p.year}-${String(p.month).padStart(2,'0')}`;
    if (!byMonth[key]) byMonth[key] = { items: [], year: p.year, month: p.month };
    byMonth[key].items.push(h);
  });
  const monthNames = ['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return Object.keys(byMonth).sort().map(key => {
    const g = byMonth[key];
    return {
      week_label:   `${monthNames[g.month]} ${g.year}`,
      csov:         avgLast2(g.items, 'csov'),
      serp:         avgLast2(g.items, 'serp'),
      ai_overview:  avgLast2(g.items, 'ai_overview'),
      llm:          avgLast2(g.items, 'llm'),
      earned_media: avgLast2(g.items, 'earned_media'),
    };
  });
}


let _trendChart = null;
let _currentView = 'weekly';

function setChartView(view) {
  _currentView = view;
  // Update toggle button styles
  ['weekly','monthly'].forEach(v => {
    const btn = document.getElementById('btn-' + v);
    if (!btn) return;
    if (v === view) {
      btn.style.background = '#00EA80'; btn.style.color = '#0A2540'; btn.style.fontWeight = '600';
    } else {
      btn.style.background = 'transparent'; btn.style.color = '#64748b'; btn.style.fontWeight = 'normal';
    }
  });
  const raw = REPORT_DATA.historical || REPORT_DATA.history || [];
  const history = view === 'monthly' ? toMonthly(raw) : raw;
  _renderTrendChart(history, view);
}

function buildTrendChart(history) {
  if (!history || !history.length) return;
  _renderTrendChart(history, 'weekly');
}

function _renderTrendChart(history, view) {
  if (!history || !history.length) return;
  const labels = history.map(h => h.week_label);

  // Dynamic title
  const viewLabel = view === 'monthly' ? 'Monthly' : view === 'period' ? 'Period' : 'Weekly';
  const titleEl = document.getElementById('trendChartTitle');
  if (titleEl) {
    if (history.length > 1) {
      titleEl.textContent = `CSOV Trend (${viewLabel}) — ${history[0].week_label} to ${history[history.length-1].week_label}`;
    } else {
      titleEl.textContent = `CSOV Trend (${viewLabel}) — ${history[0].week_label}`;
    }
  }

  const datasets = [
    {
      label: 'Overall CSOV',
      data: history.map(h=>h.csov),
      borderColor: '#00EA80', backgroundColor: 'rgba(0,234,128,.10)',
      tension: .35, fill: true, borderWidth: 3,
      pointRadius: 5, pointBackgroundColor: '#00EA80',
    },
    {
      label: 'SERP',
      data: history.map(h=>h.serp),
      borderColor: '#0A2540', backgroundColor: 'transparent',
      tension: .35, fill: false, borderWidth: 2, borderDash: [],
      pointRadius: 4, pointBackgroundColor: '#0A2540',
    },
    {
      label: 'AI Overview',
      data: history.map(h=>h.ai_overview),
      borderColor: '#08ADE4', backgroundColor: 'transparent',
      tension: .35, fill: false, borderWidth: 2, borderDash: [6, 3],
      pointRadius: 4, pointBackgroundColor: '#08ADE4',
    },
    {
      label: 'LLM',
      data: history.map(h=>h.llm),
      borderColor: '#F59E0B', backgroundColor: 'transparent',
      tension: .35, fill: false, borderWidth: 2, borderDash: [3, 3],
      pointRadius: 4, pointBackgroundColor: '#F59E0B',
    },
    {
      label: 'Earned Media',
      data: history.map(h=>h.earned_media),
      borderColor: '#E0144C', backgroundColor: 'transparent',
      tension: .35, fill: false, borderWidth: 2, borderDash: [8, 4],
      pointRadius: 4, pointBackgroundColor: '#E0144C',
    },
  ];

  if (_trendChart) { _trendChart.destroy(); }
  _trendChart = new Chart(document.getElementById('trendChart'), {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { boxWidth: 14, padding: 18, font: { size: 12, family: 'Manrope' }, usePointStyle: true }
        },
        tooltip: { mode: 'index', intersect: false },
      },
      scales: {
        y: { min: 0, max: 100, grid: { color: '#f1f5f9' }, ticks: { font: { size: 11 } } },
        x: { grid: { display: false }, ticks: { font: { size: 11 }, maxRotation: 30 } },
      },
    },
  });
}

// ── CSV Download ────────────────────────────────────────────────────────────
function downloadTrendCSV() {
  const raw = REPORT_DATA.historical || REPORT_DATA.history || [];
  if (!raw.length) { alert('No historical data available yet.'); return; }
  const history = _currentView === 'monthly' ? toMonthly(raw) : raw;
  const headers = ['Date','Overall CSOV','SERP','AI Overview','LLM','Earned Media'];
  const rows = history.map(h => [
    h.week_label,
    (h.csov        || 0).toFixed(2),
    (h.serp        || 0).toFixed(2),
    (h.ai_overview || 0).toFixed(2),
    (h.llm         || 0).toFixed(2),
    (h.earned_media|| 0).toFixed(2),
  ]);
  const escape = v => '"' + String(v).replace(/"/g, '""') + '"';
  const csv = [headers, ...rows].map(r => r.map(escape).join(',')).join('\\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = 'ivisa_csov_history.csv'; a.click();
  URL.revokeObjectURL(url);
}

// ── Country Grid ───────────────────────────────────────────────────────────
function buildCountryGrid(countryData) {
  const grid = document.getElementById('countryGrid');
  Object.entries(countryData).forEach(([code, country]) => {
    const score = (country.csov_score || 0).toFixed(1);
    const c     = country.components || {};
    const segs  = [
      { w: (c.serp||0)*0.35,         color:'#00EA80' },
      { w: (c.ai_overview||0)*0.25,  color:'#08ADE4' },
      { w: (c.llm||0)*0.25,          color:'#F59E0B' },
      { w: (c.earned_media||0)*0.15, color:'#0A2540' },
    ];
    const total = segs.reduce((s,x)=>s+x.w,0)||1;

    const compRows = [
      { label: 'SERP',     val: (c.serp||0).toFixed(1),         color: '#00EA80' },
      { label: 'AI Ovw',   val: (c.ai_overview||0).toFixed(1),  color: '#08ADE4' },
      { label: 'LLM',      val: (c.llm||0).toFixed(1),          color: '#F59E0B' },
      { label: 'Earned',   val: (c.earned_media||0).toFixed(1),  color: '#0A2540' },
    ];
    grid.innerHTML += `
      <div class="country-card" id="cc-${code}" onclick="selectCountry('${code}', REPORT_DATA)">
        <div class="country-flag">${country.flag||''}</div>
        <div class="country-name">${country.name}</div>
        <div class="country-score" style="color:${scoreColor(country.csov_score||0)}">${score}</div>
        <div class="mini-bar-wrap">
          ${segs.map(s=>`<div class="mini-seg" style="width:${(s.w/total*100).toFixed(1)}%;background:${s.color}"></div>`).join('')}
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:3px 8px;margin-top:7px;">
          ${compRows.map(r=>`
            <div style="display:flex;align-items:center;gap:4px;">
              <span style="width:8px;height:8px;border-radius:50%;background:${r.color};flex-shrink:0;display:inline-block;"></span>
              <span style="font-size:10px;color:#666;">${r.label}</span>
              <span style="font-size:10px;font-weight:600;color:#333;margin-left:auto;">${r.val}</span>
            </div>`).join('')}
        </div>
      </div>`;
  });
}

// ── Country Selection ──────────────────────────────────────────────────────
let activeCountry = null;
function selectCountry(code, D) {
  if (activeCountry) document.getElementById('cc-'+activeCountry)?.classList.remove('active');
  activeCountry = code;
  document.getElementById('cc-'+code)?.classList.add('active');

  const country = D.country_data[code];
  document.getElementById('detailTitle').textContent = `${country.flag} ${country.name} — Detail`;

  // SERP Table — per country
  buildSerpTable(D.serp_data?.results?.[code] || {});

  // AI Overview Table — per country
  buildAioTable(D.ai_overview_data?.results?.[code] || {});

  // LLM — show per-country queries if available, else show global note
  const llmNote = document.getElementById('llmCountryNote');
  const llmCountrySection = document.getElementById('llmCountrySection');

  const llmCountryData = D.llm_by_country?.[code];
  if (llmCountryData && llmCountryData.queries && llmCountryData.queries.length) {
    // Hide fallback note
    if (llmNote) llmNote.style.display = 'none';
    // Build or update the per-country queries table
    _buildLlmCountrySection(country.name, country.flag || '', llmCountryData);
  } else {
    // No per-country data — show fallback note, hide country section
    if (llmNote) {
      llmNote.textContent = `Showing global LLM data — queries run across all markets, not per country.`;
      llmNote.style.display = 'block';
    }
    if (llmCountrySection) llmCountrySection.style.display = 'none';
  }

  // Earned Media — show per-country mentions if available, else show global note
  const emNote = document.getElementById('emCountryNote');
  const emCountrySection = document.getElementById('emCountrySection');

  const emCountryData = D.earned_media_by_country?.[code];
  if (emCountryData && emCountryData.mentions && emCountryData.mentions.length) {
    // Hide fallback note
    if (emNote) emNote.style.display = 'none';
    // Render country-specific mentions
    _renderEmCountrySection(country.name, country.flag || '', emCountryData);
  } else {
    if (emNote) {
      emNote.textContent = `Showing global Earned Media — mentions tracked across all platforms, not per country.`;
      emNote.style.display = 'block';
    }
    if (emCountrySection) emCountrySection.style.display = 'none';
  }
}

// ── Per-country LLM section ────────────────────────────────────────────────
function _buildLlmCountrySection(countryName, flag, data) {
  const container = document.getElementById('llmCountrySection');
  if (!container) return;
  container.style.display = 'block';

  const rows = (data.queries || []).map(q => {
    const claudeScore = q.claude_sentiment != null ? q.claude_sentiment.toFixed(1) : '—';
    const geminiScore = q.gemini_sentiment != null ? q.gemini_sentiment.toFixed(1) : '—';
    const avgScore    = q.avg_sentiment   != null ? q.avg_sentiment.toFixed(1)    : '—';
    const avgNum      = parseFloat(avgScore);
    const scoreColor  = isNaN(avgNum) ? 'var(--muted)' : avgNum >= 65 ? 'var(--green-dark)' : avgNum >= 45 ? 'var(--yellow)' : 'var(--red)';
    return `<tr>
      <td style="padding:6px 8px;font-size:.78rem;line-height:1.4;">${q.query}</td>
      <td style="padding:6px 8px;text-align:center;font-size:.8rem;">${claudeScore}</td>
      <td style="padding:6px 8px;text-align:center;font-size:.8rem;">${geminiScore}</td>
      <td style="padding:6px 8px;text-align:center;font-weight:700;font-size:.8rem;color:${scoreColor};">${avgScore}</td>
    </tr>`;
  }).join('');

  container.innerHTML = `
    <div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:16px;">
      <p style="font-weight:700;font-size:.88rem;color:var(--navy);margin-bottom:10px;">
        🌍 ${flag} ${countryName} — Brand Perception (5 queries)
        <span style="font-weight:400;font-size:.78rem;color:var(--muted);margin-left:6px;">avg sentiment: ${data.avg_sentiment?.toFixed(1) ?? '—'}/100</span>
      </p>
      <div style="overflow-x:auto;">
        <table style="width:100%;border-collapse:collapse;font-family:inherit;">
          <thead>
            <tr style="border-bottom:2px solid var(--border);">
              <th style="padding:6px 8px;text-align:left;font-size:.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;">Query</th>
              <th style="padding:6px 8px;text-align:center;font-size:.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;">Claude</th>
              <th style="padding:6px 8px;text-align:center;font-size:.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;">Gemini</th>
              <th style="padding:6px 8px;text-align:center;font-size:.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;">Avg</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
}

// ── Per-country EM section ──────────────────────────────────────────────────
function _renderEmCountrySection(countryName, flag, data) {
  const container = document.getElementById('emCountrySection');
  if (!container) return;
  container.style.display = 'block';

  const mentions = data.mentions || [];
  const counts   = data.counts   || {};
  const score    = data.score    || 0;

  const SOURCE_ICONS = { news:'📰', blog:'✈️', reddit:'💬', youtube:'▶️', instagram:'📸', tiktok:'🎵' };
  const SENT_LABEL   = { positive:'🟢 positive', neutral:'⚪ neutral', negative:'🔴 negative' };

  const cards = mentions.map(m => {
    const sentCls = m.sentiment === 'positive' ? 'pill-pos' : m.sentiment === 'negative' ? 'pill-neg' : 'pill-neu';
    const icon = SOURCE_ICONS[m.source] || '🔗';
    const snippet = m.snippet ? m.snippet.substring(0, 160) + (m.snippet.length > 160 ? '…' : '') : '';
    return `<div class="mention-card" data-source="${m.source}" data-sentiment="${m.sentiment}">
      <div class="mention-source">${icon} ${(m.source||'').toUpperCase()} · <span style="color:var(--muted);font-size:.72rem;">${m.domain||''}</span></div>
      <div class="mention-title" style="margin:6px 0;">
        ${m.url
          ? `<a href="${m.url}" target="_blank" style="color:var(--navy);text-decoration:none;font-size:.88rem;line-height:1.4;" onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'">${m.title || 'View article →'}</a>`
          : `<span style="font-size:.88rem;">${m.title || 'Untitled'}</span>`}
      </div>
      ${snippet ? `<div style="font-size:.76rem;color:#555;line-height:1.45;margin-bottom:8px;">${snippet}</div>` : ''}
      <div class="mention-footer">
        <span class="pill ${sentCls}">${SENT_LABEL[m.sentiment]||m.sentiment}</span>
        ${m.date ? `<span style="font-size:.72rem;color:var(--muted);">📅 ${m.date}</span>` : ''}
        ${m.url  ? `<a class="domain-link" href="${m.url}" target="_blank">View →</a>` : ''}
      </div>
    </div>`;
  }).join('');

  container.innerHTML = `
    <div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:16px;">
      <p style="font-weight:700;font-size:.88rem;color:var(--navy);margin-bottom:8px;">
        🌍 ${flag} ${countryName} — Earned Media (${counts.total||0} mentions · score: ${score.toFixed ? score.toFixed(1) : score}/100)
      </p>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px;">
        <span class="sent-chip sent-chip-pos">🟢 ${counts.positive||0} positive</span>
        <span class="sent-chip sent-chip-neu">⚪ ${counts.neutral||0} neutral</span>
        <span class="sent-chip sent-chip-neg">🔴 ${counts.negative||0} negative</span>
      </div>
      <div class="mentions-grid">${cards}</div>
    </div>`;
}

// ── Country Tabs ───────────────────────────────────────────────────────────
function buildCountryTabs(countryData) {
  // These are top-level section tabs: SERP / AI Overview / LLM / Earned Media
  const tabBar = document.getElementById('countryTabs');
  const tabs = [
    { id: 'serp', label: '🔍 SERP' },
    { id: 'aio',  label: '🤖 AI Overview' },
    { id: 'llm',  label: '💬 LLM' },
    { id: 'em',   label: '📰 Earned Media' },
  ];
  tabs.forEach((t, i) => {
    tabBar.innerHTML += `
      <button class="tab-btn${i===0?' active':''}" onclick="showTab('${t.id}',this)">${t.label}</button>`;
  });
}

function showTab(id, btn) {
  document.querySelectorAll('.tab-content').forEach(el=>el.classList.remove('active'));
  document.querySelectorAll('#countryTabs .tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  btn.classList.add('active');
  // Swap action items to match active tab
  const tabLabels = {serp:'SERP', aio:'AI Overview', llm:'LLM', em:'Earned Media'};
  const actionKey = {serp:'serp', aio:'ai_overview', llm:'llm', em:'earned_media'}[id] || 'serp';
  document.getElementById('actionItemsTitle').textContent = 'Action Items — ' + (tabLabels[id] || 'SERP');
  buildActions((REPORT_DATA.action_items_by_tab || {})[actionKey] || REPORT_DATA.action_items || []);
}
function showLlmTab(part, btn) {
  document.getElementById('llm-parta').style.display = part==='parta'?'block':'none';
  document.getElementById('llm-partb').style.display = part==='partb'?'block':'none';
  document.querySelectorAll('.llm-tabs .tab-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
}

// ── SERP Blocks (per-keyword grouped) ─────────────────────────────────────
function buildSerpTable(countryResults) {
  const container = document.getElementById('serpKeywordBlocks');
  container.innerHTML = '';

  if (!countryResults || !Object.keys(countryResults).length) {
    container.innerHTML = '<p style="color:var(--muted);padding:24px;text-align:center;">No SERP data available for this country.</p>';
    return;
  }

  // Sentiment helpers
  const SENT_SCORE = { positive: 1.0, neutral: 0.5, negative: 0.0 };
  function kwScore(results) {
    let totalW = 0, weightedS = 0;
    (results || []).slice(0,10).forEach(r => {
      const pos = r.position || 0;
      if (pos < 1 || pos > 10) return;
      const w = 11 - pos;
      weightedS += w * (SENT_SCORE[r.sentiment] ?? 0.5);
      totalW += w;
    });
    return totalW ? Math.round((weightedS / totalW) * 100) : 50;
  }
  function sentEmoji(s) {
    return s === 'positive' ? '🟢' : s === 'negative' ? '🔴' : '⚪';
  }

  Object.entries(countryResults).forEach(([kw, results]) => {
    const score = kwScore(results);
    const scoreColor = score >= 70 ? 'var(--green)' : score >= 45 ? 'var(--yellow)' : 'var(--red)';

    // Sentiment counts for this keyword
    const kwCounts = { positive: 0, neutral: 0, negative: 0 };
    (results || []).slice(0,10).forEach(r => { if (r.sentiment) kwCounts[r.sentiment]++; });
    const countsHtml = `
      <span class="sent-chip sent-chip-pos">🟢 ${kwCounts.positive}</span>
      <span class="sent-chip sent-chip-neu">⚪ ${kwCounts.neutral}</span>
      <span class="sent-chip sent-chip-neg">🔴 ${kwCounts.negative}</span>`;

    const allResults = (results || []).slice(0, 10);
    const kwId = 'serp-' + kw.replace(/[^a-z0-9]/gi, '_');

    function makeRows(items) {
      if (!items.length) return '<tr><td colspan="3" style="text-align:center;color:var(--muted);padding:12px;">No data</td></tr>';
      return items.map(r => {
        const title    = r.title || '—';
        const snippet  = (r.snippet || '').trim();
        // Snippet: first 15 words + expand toggle if longer
        const words    = snippet.split(/\s+/).filter(Boolean);
        const shortSnip = words.slice(0,15).join(' ');
        const hasMore   = words.length > 15;
        const snippetHtml = snippet
          ? `<div style="font-size:.76rem;color:#555;margin-top:3px;line-height:1.45;">
               <span class="snip-short">${shortSnip}${hasMore ? '…' : ''}</span>
               ${hasMore ? `<span class="snip-full" style="display:none;">${snippet}</span>
               <span onclick="this.previousElementSibling.style.display=this.previousElementSibling.style.display==='none'?'inline':'none';this.previousElementSibling.previousElementSibling.style.display=this.previousElementSibling.previousElementSibling.style.display==='none'?'inline':'none';this.textContent=this.textContent==='more'?'less':'more';" style="color:var(--green);cursor:pointer;font-size:.72rem;margin-left:3px;">more</span>` : ''}
             </div>`
          : '';
        const domainDisplay = r.domain || '';
        // Only ever link to a real absolute http(s) URL. A relative/redirect link
        // (e.g. "/goto?url=...") would resolve to a GitHub Pages 404, so fall back
        // to the domain homepage, or render plain text if neither is valid.
        const linkUrl = (r.url && /^https?:\/\//i.test(r.url))
          ? r.url
          : (r.domain ? 'https://' + r.domain.replace(/^https?:\/\//i,'') : '');
        // When title is missing, use domain as display text
        const displayTitle = title !== '—' ? title : (r.domain || '—');
        const titleHtml = linkUrl
          ? `<a href="${linkUrl}" target="_blank" style="font-size:.83rem;font-weight:${r.is_ivisa?'700':'600'};color:#1a0dab;text-decoration:none;line-height:1.3;" onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'">${displayTitle}</a>`
          : `<span style="font-size:.83rem;font-weight:${r.is_ivisa?'700':'600'};color:var(--navy);line-height:1.3;">${displayTitle}</span>`;
        return `<tr class="${r.is_ivisa ? 'ivisa-row' : ''}">
          <td style="vertical-align:top;padding-top:10px;">${r.position ? posBadge(r.position) : '—'}</td>
          <td style="vertical-align:top;">
            <div style="font-size:.72rem;color:var(--muted);margin-bottom:2px;">${domainDisplay}</div>
            ${titleHtml}
            ${snippetHtml}
          </td>
          <td style="text-align:center;vertical-align:top;padding-top:10px;">${sentEmoji(r.sentiment)} ${pillSentiment(r.sentiment)}</td>
        </tr>`;
      }).join('');
    }

    const page1rows = makeRows(allResults.slice(0,5));
    const page2rows = allResults.length > 5 ? makeRows(allResults.slice(5,10)) : '';
    const pagerHtml = page2rows ? `
      <div style="display:flex;gap:8px;margin-top:8px;align-items:center;">
        <button onclick="serpPage('${kwId}',1,this)" style="font-size:.78rem;padding:2px 10px;border:1px solid var(--green);background:var(--green);color:#fff;border-radius:6px;cursor:pointer;font-family:inherit;" data-active="1">1–5</button>
        <button onclick="serpPage('${kwId}',2,this)" style="font-size:.78rem;padding:2px 10px;border:1px solid var(--green);background:transparent;color:var(--green);border-radius:6px;cursor:pointer;font-family:inherit;" data-active="0">6–10</button>
        <span style="font-size:.75rem;color:var(--muted);">Showing results 1–5 of ${allResults.length}</span>
      </div>` : '';

    container.innerHTML += `
      <div style="margin-bottom:28px;">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px;flex-wrap:wrap;">
          <span style="font-size:.85rem;font-weight:700;color:var(--navy);">${kw}</span>
          <span style="font-size:.8rem;font-weight:700;color:${scoreColor};background:var(--bg);
                       padding:2px 10px;border-radius:10px;border:1px solid var(--border);">
            SERP Score: ${score}/100
          </span>
          <div class="sent-counts" style="margin-top:0;">${countsHtml}</div>
        </div>
        <div class="table-wrap">
          <table style="font-size:.82rem;" id="${kwId}">
            <thead><tr>
              <th style="width:40px;">Pos</th>
              <th>Page</th>
              <th style="text-align:center;width:110px;">Sentiment</th>
            </tr></thead>
            <tbody id="${kwId}-body">${page1rows}</tbody>
          </table>
          ${pagerHtml}
          ${page2rows ? `<div id="${kwId}-p2" style="display:none"><table style="font-size:.82rem;width:100%;"><thead><tr><th style="width:40px;">Pos</th><th>Page</th><th style="text-align:center;width:110px;">Sentiment</th></tr></thead><tbody>${page2rows}</tbody></table></div>` : ''}
        </div>
      </div>`;
  });
}

// ── SERP Pagination ────────────────────────────────────────────────────────
function serpPage(kwId, page, btn) {
  const p1 = document.getElementById(kwId + '-body').closest('table').parentNode;
  const p2 = document.getElementById(kwId + '-p2');
  const btns = btn.parentNode.querySelectorAll('button');
  const label = btn.parentNode.querySelector('span');
  if (page === 1) {
    p1.querySelector('table').style.display = '';
    if (p2) p2.style.display = 'none';
    if (label) label.textContent = 'Showing results 1–5';
  } else {
    p1.querySelector('table').style.display = 'none';
    if (p2) p2.style.display = '';
    if (label) label.textContent = 'Showing results 6–10';
  }
  btns.forEach(b => {
    b.style.background = b === btn ? 'var(--green)' : 'transparent';
    b.style.color = b === btn ? '#fff' : 'var(--green)';
  });
}

// ── Methodology toggle ─────────────────────────────────────────────────────
function toggleMethod(btn) {
  const body  = document.getElementById('methodBody');
  const arrow = document.getElementById('methodArrow');
  const open  = body.classList.toggle('open');
  arrow.textContent = open ? '▲' : '▼';
}

// ── AIO Table ──────────────────────────────────────────────────────────────
let aioExpandCount = 0;
// Read the AIO text for the specific concerns it raises and turn each into a
// short "what the AI says + what to do about it" recommendation for the team.
function aioWhatToFix(aioText) {
  if (!aioText) return '<span style="color:var(--muted);font-size:.75rem;">—</span>';
  const t = aioText.toLowerCase();
  // Ordered by how prominently the concern usually drives sentiment. `cat` is used
  // to de-duplicate (e.g. two pricing patterns shouldn't both show).
  const checks = [
    { cat:'price', re:/cheaper|apply directly|directly with|official (government )?(channel|site|website|source|portal)|for free|free of charge|without paying|save money|do it yourself|yourself for/,
      icon:'💸', label:'Price vs. applying directly',
      fix:'The AI tells travelers it is cheaper to go straight to the official government site. Reframe the fee as value — time saved, guided error-free forms, document checks, support and the refund guarantee — and show a clear government-fee vs service-fee breakdown so the small premium reads as worth it.' },
    { cat:'price', re:/fee|markup|overpriced|expensive|cost|charge|pricey|premium/,
      icon:'💸', label:'Fees seen as high',
      fix:'The AI frames iVisa as pricier than alternatives. Make the value of the service fee explicit and show a transparent price breakdown so pricing feels justified, not hidden.' },
    { cat:'official', re:/not.*government|not.*official|third.?party|middleman|not.*agency|private company|not affiliated/,
      icon:'🏛️', label:'"Not official / third-party"',
      fix:'The AI stresses iVisa is not a government agency. Position iVisa clearly as a legitimate independent service that simplifies the process, and lead with trust signals (verified reviews, success rate, years operating) high on the page.' },
    { cat:'support', re:/customer service|support|unresponsive|difficult to reach|no response|hard to reach|communication|poor communication/,
      icon:'📞', label:'Customer-service & communication',
      fix:'The AI surfaces support/communication complaints (slow or unclear responses, errors). Highlight live support channels and response-time commitments, and proactively answer the top complaint themes (refunds, delays, errors) in help/FAQ content.' },
    { cat:'time', re:/processing time|slow|delay|takes.*long|longer than|waiting/,
      icon:'⏱️', label:'Processing-time concerns',
      fix:'The AI notes processing can take longer. Show realistic timelines plus expedited options, and surface on-time delivery stats to set expectations.' },
    { cat:'refund', re:/refund|cancel|non.?refund/,
      icon:'↩️', label:'Refund-policy concerns',
      fix:'The AI flags refund/cancellation worries. Make the refund guarantee prominent and in plain language.' },
    { cat:'transparency', re:/hidden fee|extra charge|additional fee|surprise charge/,
      icon:'🔍', label:'Fee transparency',
      fix:'The AI mentions hidden/extra charges. Show the full price (service fee vs government fee) upfront — no checkout surprises.' },
    { cat:'privacy', re:/data breach|privacy|personal information|data security|identity/,
      icon:'🔒', label:'Data & privacy',
      fix:'The AI raises data-security concerns. Surface security certifications, data handling and privacy practices.' },
    { cat:'legit', re:/scam|fraud|not legit|avoid using|illegitimate/,
      icon:'⚠️', label:'Legitimacy doubts',
      fix:'The AI surfaces scam/legitimacy questions. Lead with proof — reviews, press coverage, success numbers — and a clear "is iVisa legit?" explainer.' },
  ];
  const seen = new Set();
  const out = [];
  for (const c of checks) {
    if (out.length >= 4) break;
    if (!seen.has(c.cat) && c.re.test(t)) {
      seen.add(c.cat);
      out.push(`<div style="margin-bottom:8px;">
        <div style="font-size:.72rem;font-weight:700;color:var(--red);">${c.icon} ${c.label}</div>
        <div style="font-size:.69rem;color:#555;line-height:1.4;margin-top:1px;">${c.fix}</div>
      </div>`);
    }
  }
  if (!out.length) return '<span style="color:var(--green);font-size:.75rem;">✅ No major issues detected</span>';
  return out.join('');
}

function buildAioTable(countryResults) {
  const tbody = document.getElementById('aioTableBody');
  tbody.innerHTML = '';
  Object.entries(countryResults).forEach(([kw, r]) => {
    const textId = 'aio-text-' + (++aioExpandCount);
    const aioText = r.ai_overview_text || '';
    const sources = (r.sources || []);
    const sourcesHtml = sources.length
      ? sources.slice(0,5).map(u => `<a class="domain-link" href="${u}" target="_blank" style="display:block;font-size:.72rem;margin-bottom:2px;">${u.replace(/^https?:\/\//,'').substring(0,50)}…</a>`).join('')
      : '<span style="color:var(--muted);font-size:.75rem;">—</span>';

    const scoreVal = r.score != null ? parseFloat(r.score) : null;
    const scoreHtml = scoreVal != null
      ? `<span style="font-weight:700;color:${scoreColor(scoreVal)}">${fmtScore(scoreVal)}</span>
         <div class="progress-bar" style="width:60px;margin-top:4px">
           <div class="progress-fill ${fillClass(scoreVal)}" style="width:${scoreVal}%"></div>
         </div>`
      : '<span style="color:var(--muted);font-size:.75rem;">Not counted</span>';

    tbody.innerHTML += `
      <tr>
        <td style="font-weight:600;min-width:140px">${kw}</td>
        <td>${r.has_ai_overview == null ? '<span class="pill pill-neu">No data</span>' : pillBool(r.has_ai_overview)}</td>
        <td>${r.ivisa_cited == null ? '<span class="pill pill-neu">—</span>' : pillBool(r.ivisa_cited, '✅ Cited', '❌ Not cited')}</td>
        <td style="max-width:240px">
          ${aioText
            ? `<div class="aio-text-cell" id="${textId}" onclick="this.classList.toggle('expanded')">${aioText}</div>
               <div class="llm-expand-hint" onclick="document.getElementById('${textId}').classList.toggle('expanded')">▼ tap to expand</div>`
            : '<span style="color:var(--muted);font-size:.75rem;">No AI overview found</span>'}
        </td>
        <td style="min-width:160px;vertical-align:top;padding-top:10px;">${aioWhatToFix(aioText)}</td>
        <td style="min-width:180px">${sourcesHtml}</td>
        <td style="text-align:right">${scoreHtml}</td>
      </tr>`;
  });
  if (!tbody.innerHTML) tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:24px;">No AI Overview data available</td></tr>';
}

// ── LLM Tables ─────────────────────────────────────────────────────────────
let llmExpandCount = 0;
function llmResponseCell(text, score) {
  // Guard against Python None serialized as the string "None" or "null"
  if (!text || text === 'None' || text === 'null' || text === 'undefined')
    return '<span style="color:var(--muted);font-size:.75rem;">No response</span>';
  const id = 'llm-r-' + (++llmExpandCount);
  const scoreHtml = score != null
    ? `<span style="font-weight:700;color:${scoreColor(score)};margin-right:6px;">${fmtScore(score)}/100</span>`
    : '';
  return `${scoreHtml}
    <div class="llm-response-full" id="${id}" onclick="this.classList.toggle('expanded')">${text}</div>
    <div class="llm-expand-hint" onclick="document.getElementById('${id}').classList.toggle('expanded')">▼ click to expand</div>`;
}

function buildLlmTables(llmData) {
  if (!llmData) return;

  const partA  = llmData.part_a?.results || [];
  const partB  = llmData.part_b?.results || [];
  // Hide the Gemini column entirely when there's no Gemini data (e.g. Gemini
  // disabled / Claude-only) so the table never shows a wall of "No response".
  const hasGemini = partA.concat(partB).some(
    r => r.gemini_sentiment != null || (r.gemini_response || '').trim()
  );

  const tbodyA = document.getElementById('llmPartABody');
  partA.forEach(r => {
    tbodyA.innerHTML += `
      <tr>
        <td style="max-width:200px;font-weight:600;">${r.query}</td>
        <td style="max-width:280px">${llmResponseCell(r.claude_response, r.claude_sentiment)}</td>
        <td class="gemini-col" style="max-width:280px">
          ${llmResponseCell(r.gemini_response, r.gemini_sentiment)}
          ${(r.gemini_sources||[]).length ? `<div style="margin-top:5px;">${(r.gemini_sources||[]).slice(0,3).map(u=>`<a href="${u}" target="_blank" style="display:block;font-size:.7rem;color:#08ADE4;word-break:break-all;margin-bottom:2px;">${u.replace(/^https?:\/\//,'').substring(0,55)}…</a>`).join('')}</div>` : ''}
        </td>
        <td style="text-align:center">
          <span style="font-weight:800;font-size:1.1rem;color:${scoreColor(r.avg_sentiment||0)}">${fmtScore(r.avg_sentiment)}</span>
          <div class="progress-bar" style="width:60px;margin:4px auto 0">
            <div class="progress-fill ${fillClass(r.avg_sentiment||0)}" style="width:${r.avg_sentiment||0}%"></div>
          </div>
        </td>
        <td style="min-width:170px;max-width:220px;vertical-align:top;padding-top:10px;">${aioWhatToFix(r.claude_response)}</td>
      </tr>`;
  });
  if (!tbodyA.innerHTML) tbodyA.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:24px;">No LLM Part A data — check API keys.</td></tr>';

  const tbodyB = document.getElementById('llmPartBBody');
  partB.forEach(r => {
    const mentioned = r.claude_mentions_ivisa || r.gemini_mentions_ivisa;
    const mentionDetail = hasGemini
      ? `Claude: ${r.claude_mentions_ivisa?'✓':'✗'} &nbsp; Gemini: ${r.gemini_mentions_ivisa?'✓':'✗'}`
      : `Claude: ${r.claude_mentions_ivisa?'✓':'✗'}`;
    tbodyB.innerHTML += `
      <tr>
        <td style="max-width:200px;font-weight:600;">${r.query}</td>
        <td style="max-width:240px">${llmResponseCell(r.claude_response, null)}</td>
        <td class="gemini-col" style="max-width:240px">${llmResponseCell(r.gemini_response, null)}</td>
        <td style="text-align:center">
          ${mentioned
            ? `<span class="pill pill-yes">✅ iVisa mentioned</span><br>
               <small style="color:var(--muted);font-size:.7rem;">${mentionDetail}</small>`
            : '<span class="pill pill-no">Not mentioned</span>'}
        </td>
        <td style="text-align:center">${r.avg_sentiment != null
          ? `<span style="font-weight:700;color:${scoreColor(r.avg_sentiment)}">${fmtScore(r.avg_sentiment)}</span>`
          : '<span style="color:var(--muted)">—</span>'}</td>
      </tr>`;
  });
  if (!tbodyB.innerHTML) tbodyB.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:24px;">No LLM Part B data — check API keys.</td></tr>';

  // Claude-only (or any run with no Gemini data): drop the empty Gemini column.
  if (!hasGemini) {
    document.querySelectorAll('.gemini-col').forEach(el => { el.style.display = 'none'; });
  }
}

// ── Earned Media ───────────────────────────────────────────────────────────
// ── Earned Media active filter state ─────────────────────────────────────
let _emActiveFilter = 'all';
let _emMentions = [];

function _renderEmCards(filter) {
  _emActiveFilter = filter;
  const grid = document.getElementById('mentionsGrid');
  const filtered = filter === 'all' ? _emMentions : _emMentions.filter(m => m.source === filter);
  const SOURCE_ICONS = { news:'📰', blog:'✈️', reddit:'💬', youtube:'▶️', instagram:'📸', tiktok:'🎵' };
  const SENT_LABEL   = { positive:'🟢 positive', neutral:'⚪ neutral', negative:'🔴 negative' };

  if (!filtered.length) {
    grid.innerHTML = '<div style="grid-column:1/-1;padding:24px;text-align:center;color:var(--muted);">No mentions for this filter.</div>';
    return;
  }

  grid.innerHTML = filtered.map(m => {
    const sentCls = m.sentiment === 'positive' ? 'pill-pos' : m.sentiment === 'negative' ? 'pill-neg' : 'pill-neu';
    const icon = SOURCE_ICONS[m.source] || '🔗';
    const snippetText = m.snippet ? m.snippet.substring(0, 160) + (m.snippet.length > 160 ? '…' : '') : '';
    return `
      <div class="mention-card" data-source="${m.source}" data-sentiment="${m.sentiment}">
        <div class="mention-source">${icon} ${(m.source||'').toUpperCase()} · <span style="color:var(--muted);font-size:.72rem;">${m.domain||''}</span></div>
        <div class="mention-title" style="margin:6px 0;">
          ${m.url
            ? `<a href="${m.url}" target="_blank" style="color:var(--navy);text-decoration:none;font-size:.88rem;line-height:1.4;" onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'">${m.title || 'View article →'}</a>`
            : `<span style="font-size:.88rem;">${m.title || 'Untitled'}</span>`}
        </div>
        ${snippetText ? `<div style="font-size:.76rem;color:#555;line-height:1.45;margin-bottom:8px;">${snippetText}</div>` : ''}
        <div class="mention-footer">
          <span class="pill ${sentCls}">${SENT_LABEL[m.sentiment]||m.sentiment}</span>
          ${m.date ? `<span style="font-size:.72rem;color:var(--muted);">📅 ${m.date}</span>` : ''}
          ${m.url ? `<a class="domain-link" href="${m.url}" target="_blank">View →</a>` : ''}
        </div>
      </div>`;
  }).join('');

  // Update filter button states
  document.querySelectorAll('.em-filter-btn').forEach(btn => {
    btn.style.background = btn.dataset.filter === filter ? 'var(--green)' : 'transparent';
    btn.style.color      = btn.dataset.filter === filter ? '#fff' : 'var(--navy)';
  });
  // Update count label
  const countEl = document.getElementById('emFilterCount');
  if (countEl) countEl.textContent = `Showing ${filtered.length} of ${_emMentions.length}`;
}

function buildEarnedMedia(earnedMedia) {
  const container = document.getElementById('tab-em');
  const grid      = document.getElementById('mentionsGrid');
  _emMentions     = earnedMedia?.mentions || [];
  let   counts    = earnedMedia?.counts || {};
  const srcBreak  = earnedMedia?.source_breakdown || {};
  const score     = earnedMedia?.score || 0;

  // Keep the summary bar consistent with the cards: if counts is missing or its
  // total doesn't match the mentions actually shown, derive it from the list.
  // (Live data always supplies counts; this guards against any payload that
  // doesn't, so we never show "0 mentions total" above real cards.)
  if (!counts.total || counts.total !== _emMentions.length) {
    const c = { total: _emMentions.length, positive: 0, neutral: 0, negative: 0 };
    _emMentions.forEach(m => { const s = m.sentiment || 'neutral'; if (c[s] !== undefined) c[s]++; });
    counts = c;
  }

  // Scope note + summary bar
  const existing = container.querySelector('.em-summary');
  if (!existing) {
    const sources = Object.entries(srcBreak).filter(([,v])=>v>0);
    const filterBtns = [['all','All'],...sources.map(([s])=>[s,s.charAt(0).toUpperCase()+s.slice(1)])];
    const summaryEl = document.createElement('div');
    summaryEl.className = 'em-summary';
    summaryEl.innerHTML = `
      <p style="font-size:.76rem;color:var(--muted);margin-bottom:12px;">
        🌐 <strong>Global score</strong> — third-party coverage mentioning iVisa across news, blogs, Reddit, YouTube, and social media (last 90 days).
        LLM scores are also global. SERP and AI Overview are per-country.
      </p>
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px;">
        <span style="font-size:.88rem;font-weight:700;color:var(--navy);">${counts.total||0} mentions total</span>
        <span class="sent-chip sent-chip-pos">🟢 ${counts.positive||0} positive</span>
        <span class="sent-chip sent-chip-neu">⚪ ${counts.neutral||0} neutral</span>
        <span class="sent-chip sent-chip-neg">🔴 ${counts.negative||0} negative</span>
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px;align-items:center;">
        ${filterBtns.map(([f,label])=>`
          <button class="em-filter-btn tab-btn${f==='all'?' active':''}"
            data-filter="${f}"
            onclick="_renderEmCards('${f}')"
            style="font-size:.75rem;padding:3px 12px;border:1px solid var(--green);border-radius:20px;cursor:pointer;font-family:inherit;${f==='all'?'background:var(--green);color:#fff;':'background:transparent;color:var(--navy);'}">
            ${label}${f!=='all'?' ('+srcBreak[f]+')':''}
          </button>`).join('')}
        <span id="emFilterCount" style="font-size:.72rem;color:var(--muted);margin-left:8px;"></span>
      </div>`;
    container.insertBefore(summaryEl, grid);
  }

  if (!_emMentions.length) {
    grid.innerHTML = `<div style="grid-column:1/-1;background:var(--bg);border-radius:10px;padding:20px;border:1px solid var(--border);">
      <p style="font-weight:700;color:var(--navy);margin-bottom:8px;">📰 Earned Media — Score: ${score}/100</p>
      <p style="font-size:.85rem;color:var(--muted);line-height:1.6;">No mentions found for the last 90 days, or SERPAPI_KEY not set.</p>
    </div>`;
    return;
  }
  _renderEmCards('all');
}

// ── Score Analysis ─────────────────────────────────────────────────────────
function buildScoreAnalysis(D) {
  const panel = document.getElementById('scoreAnalysisPanel');
  const list  = document.getElementById('scoreAnalysisList');
  if (!panel || !list) return;

  const insights = [];
  const history  = D.historical  || D.history || [];
  const serp     = D.serp_data   || {};
  const aio      = D.ai_overview_data || {};
  const current  = {
    csov:         D.csov_score || 0,
    serp:         D.components?.serp?.score || 0,
    ai_overview:  D.components?.ai_overview?.score || 0,
    llm:          D.components?.llm?.score || 0,
    earned_media: D.components?.earned_media?.score || 0,
  };

  // ── Country-level SERP analysis ──────────────────────────────────────────
  const countryScores = serp.country_scores || {};
  const countryNames  = { us:'United States', gb:'United Kingdom', au:'Australia',
                          de:'Germany', ca:'Canada', fr:'France',
                          jp:'Japan', nl:'Netherlands', it:'Italy', es:'Spain' };

  // Lowest-scoring countries
  const sortedCountries = Object.entries(countryScores).sort((a,b) => a[1]-b[1]);
  if (sortedCountries.length >= 2) {
    const bottom2 = sortedCountries.slice(0,2).map(([c,s]) => `${countryNames[c]||c} (${s.toFixed(0)})`);
    insights.push({ icon:'🌍', text:`<strong>Countries dragging SERP scores down:</strong> ${bottom2.join(' and ')} have the lowest SERP sentiment this week — check local review sites and complaint pages ranking for your keywords in those markets.` });
  }

  // Best-performing country
  const top = sortedCountries[sortedCountries.length - 1];
  if (top) {
    insights.push({ icon:'✅', text:`<strong>Strongest market:</strong> ${countryNames[top[0]]||top[0]} leads SERP sentiment at ${top[1].toFixed(0)}/100 — positive coverage is holding well here.` });
  }

  // ── Negative SERP sources ────────────────────────────────────────────────
  const serpResults = serp.results || {};
  let negCount = 0; let negDomains = {};
  let posCount = 0;
  Object.values(serpResults).forEach(countryKws => {
    Object.values(countryKws).forEach(results => {
      (results||[]).forEach(r => {
        if (r.sentiment === 'negative') { negCount++; negDomains[r.domain] = (negDomains[r.domain]||0)+1; }
        if (r.sentiment === 'positive') posCount++;
      });
    });
  });
  const topNegDomains = Object.entries(negDomains).sort((a,b)=>b[1]-a[1]).slice(0,3).map(([d])=>d);
  if (negCount > 0) {
    insights.push({ icon:'⚠️', text:`<strong>${negCount} negative SERP appearances</strong> detected across all markets this week${topNegDomains.length ? ' — most frequent on: ' + topNegDomains.join(', ') : ''}. These are the pages pushing sentiment scores down.` });
  }
  if (posCount > 0) {
    insights.push({ icon:'📈', text:`<strong>${posCount} positive SERP results</strong> are working in iVisa's favour — review sites, travel blogs, and editorial content ranking positively for reputation keywords.` });
  }

  // ── AI Overview topics ───────────────────────────────────────────────────
  const aioResults = aio.results || {};
  const topicCount = {};
  Object.values(aioResults).forEach(countryKws => {
    Object.values(countryKws).forEach(result => {
      (result.negative_topics||[]).forEach(t => { topicCount[t] = (topicCount[t]||0)+1; });
    });
  });
  const topTopics = Object.entries(topicCount).sort((a,b)=>b[1]-a[1]).slice(0,2);
  if (topTopics.length) {
    const topicStr = topTopics.map(([t,n]) => `"${t}" (${n} keyword${n>1?'s':''})`).join(' and ');
    insights.push({ icon:'🤖', text:`<strong>Google AI Overviews are surfacing concerns about ${topicStr}</strong> — these are the specific topics being cited negatively in AI summaries. Content addressing these directly will improve the AI Overview score.` });
  }

  // ── Week-over-week trend ─────────────────────────────────────────────────
  if (history.length >= 2) {
    const prev = history[history.length - 2];
    const curr = history[history.length - 1];
    const diff = (curr.csov || 0) - (prev.csov || 0);
    if (Math.abs(diff) >= 1) {
      const dir = diff > 0 ? '↑' : '↓';
      const cls = diff > 0 ? 'color:var(--green-dark)' : 'color:var(--red)';
      insights.push({ icon: diff > 0 ? '📈' : '📉', text:`<strong style="${cls}">Overall CSOV ${dir}${Math.abs(diff).toFixed(1)} vs last week</strong> — ${diff > 0 ? 'positive momentum, keep publishing trust-building content.' : 'score dipped — check which component dropped most in the breakdown above.'}` });
    }
  }

  if (!insights.length) {
    insights.push({ icon:'💡', text:'No significant signals detected this week — run with live API keys for full analysis.' });
  }

  panel.style.display = 'block';
  insights.forEach(({ icon, text }) => {
    list.innerHTML += `<li style="display:flex;gap:12px;align-items:flex-start;padding:10px 14px;background:var(--bg);border-radius:8px;font-size:.875rem;line-height:1.55;">
      <span style="font-size:1.1rem;flex-shrink:0;margin-top:1px;">${icon}</span>
      <span>${text}</span>
    </li>`;
  });
}

// ── Action Items ───────────────────────────────────────────────────────────
function buildActions(actions) {
  const list = document.getElementById('actionsList');
  const icons = ['🎯','📈','🔗','✍️','💡','⚠️','🚀'];
  (actions || []).forEach((a, i) => {
    list.innerHTML += `
      <li class="action-item">
        <span class="action-icon">${icons[i % icons.length]}</span>
        <span class="action-text">${a}</span>
      </li>`;
  });
  if (!actions?.length) {
    list.innerHTML = '<li class="action-item"><span class="action-icon">✅</span><span class="action-text">All scores are healthy — maintain current strategy.</span></li>';
  }
}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Week label helpers
# ---------------------------------------------------------------------------

def _week_range(run_date: date) -> tuple[str, str, str]:
    """Return (week_start_str, week_end_str, label) for the week containing run_date."""
    # Week Mon–Sun
    monday = run_date - timedelta(days=run_date.weekday())
    sunday = monday + timedelta(days=6)
    label = f"{monday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')}"
    return monday.strftime("%B %d, %Y"), sunday.strftime("%B %d, %Y"), label


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _sanitize_report_data(report_data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """
    FINAL SAFETY GATE — runs over the entire report payload right before it is
    serialized into the HTML. Every result's snippet/title passes through the
    junk filter and app-store fallbacks here, so no matter what the fetch layer
    stored, a junk/code snippet physically cannot reach the published page.

    This is purely text cleanup: it never recomputes sentiment or scores, so the
    displayed numbers are untouched.

    Returns (report_data, blanked_count).
    """
    from scripts.fetch_serp import (
        _is_junk_snippet, _is_domain_title, _apply_app_store_fallbacks,
        _platform_snippet, _platform_title,
    )
    blanked = 0

    def walk(o: Any) -> None:
        nonlocal blanked
        if isinstance(o, dict):
            domain = o.get("domain", "") if isinstance(o.get("domain", ""), str) else ""
            snip = o.get("snippet")
            if isinstance(snip, str) and snip.strip() and _is_junk_snippet(snip):
                o["snippet"] = ""
                blanked += 1
            title = o.get("title")
            if isinstance(title, str) and _is_domain_title(title, domain):
                o["title"] = ""
            if domain:
                _apply_app_store_fallbacks(o)
                # Fill a blank snippet/title for known social/review/owned domains
                # (SEMrush ranks these domain-level with no body). Display-only —
                # sentiment/score are NOT touched.
                if "snippet" in o and not (o.get("snippet") or "").strip():
                    ps = _platform_snippet(domain)
                    if ps:
                        o["snippet"] = ps
                if "title" in o and not (o.get("title") or "").strip():
                    pt = _platform_title(domain)
                    if pt:
                        o["title"] = pt
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(report_data)

    # ── Drop content-less SERP rows ──────────────────────────────────────────
    # After all fills above, any SERP result that STILL has no snippet AND no real
    # title (just a bare domain) carries zero information — e.g. an editorial domain
    # SEMrush returned at the domain level that we couldn't enrich. Showing it as a
    # bare "lakelandcurrents.com" link with nothing under it is the recurring
    # "empty result" complaint. Hide these from the table (display-only; iVisa-owned
    # results are always kept).
    def _is_contentless(r: dict) -> bool:
        if not isinstance(r, dict):
            return False
        if r.get("is_ivisa"):
            return False
        title = (r.get("title") or "").strip()
        snippet = (r.get("snippet") or "").strip()
        dom = (r.get("domain") or "").lower().lstrip("www.").lstrip(".")
        title_is_domain = title.lower().lstrip("www.").lstrip(".").rstrip("/") in ("", dom)
        return not snippet and title_is_domain

    dropped = 0
    serp_results = (report_data.get("serp_data", {}) or {}).get("results", {}) or {}
    for _cc, kws in serp_results.items():
        for _kw, rows in kws.items():
            if isinstance(rows, list):
                kept = [r for r in rows if not _is_contentless(r)]
                dropped += len(rows) - len(kept)
                rows[:] = kept
    if dropped:
        logger.info("  Report gate: hid %d content-less SERP row(s) (bare domain, no snippet).", dropped)

    return report_data, blanked


def generate_report(report_data: dict[str, Any], output_path: str) -> None:
    """
    Render the self-contained HTML report and write it to output_path.

    report_data must contain all the keys the JS template expects.
    """
    import pathlib

    run_date = date.today()
    week_start, week_end, week_label = _week_range(run_date)

    # Enrich report_data with meta
    report_data.setdefault("week_label", week_label)
    report_data.setdefault("week_start", week_start)
    report_data.setdefault("week_end", week_end)
    report_data.setdefault("generated_at", datetime.utcnow().isoformat() + "Z")

    # FINAL SAFETY GATE — strip any junk/code snippet before it can reach the page.
    report_data, _blanked = _sanitize_report_data(report_data)
    if _blanked:
        logger.info("  Report safety gate: blanked %d junk snippet(s) before render.", _blanked)

    # Embed JSON safely
    json_str = json.dumps(report_data, ensure_ascii=False, default=str)
    html = HTML_TEMPLATE.replace("__REPORT_DATA_PLACEHOLDER__", json_str)

    # Build past-reports dropdown links from docs/reports/
    from scripts.config import DOCS_DIR
    reports_dir = DOCS_DIR / "reports"
    archive_links = ""
    try:
        archive_files = sorted(
            [f for f in reports_dir.glob("*.html") if f.stem != "index"],
            reverse=True,
        )
        for af in archive_files:
            stem = af.stem  # e.g. "2026-06-02"
            try:
                d = date.fromisoformat(stem)
                label = d.strftime("%b %d, %Y")
            except ValueError:
                label = stem
            archive_links += f'<a href="reports/{af.name}">{label}</a>\n'
    except Exception:
        pass
    if not archive_links:
        archive_links = '<span style="padding:10px 16px;display:block;color:var(--muted);font-size:.82rem;">No archived reports yet</span>'
    # Add "View all reports" link at the bottom of the dropdown
    archive_links += '<a href="reports/index.html" style="font-weight:700;border-top:2px solid var(--border);color:var(--blue);">📋 View all reports →</a>\n'
    html = html.replace("__ARCHIVE_LINKS_PLACEHOLDER__", archive_links)

    out = pathlib.Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    logger.info("  Report written to: %s (%d KB)", output_path, len(html) // 1024)


def generate_reports_index(reports_dir: str, output_path: str) -> None:
    """
    Generate docs/reports/index.html — a clean archive page listing all weekly reports.
    Linked from the main dashboard header dropdown.
    """
    import pathlib
    from datetime import date

    reports_path = pathlib.Path(reports_dir)
    archive_files = sorted(
        [f for f in reports_path.glob("*.html") if f.stem != "index"],
        reverse=True,
    )

    rows = ""
    for af in archive_files:
        stem = af.stem
        try:
            d = date.fromisoformat(stem)
            # Week range Mon–Sun
            from datetime import timedelta
            mon = d - timedelta(days=d.weekday())
            sun = mon + timedelta(days=6)
            label = f"Week of {mon.strftime('%b %d')} – {sun.strftime('%b %d, %Y')}"
            date_label = d.strftime("%b %d, %Y")
        except ValueError:
            label = stem
            date_label = stem

        rows += f"""
        <tr>
          <td style="padding:12px 16px;font-weight:600;color:var(--navy);">{label}</td>
          <td style="padding:12px 16px;color:var(--muted);font-size:.85rem;">{date_label}</td>
          <td style="padding:12px 16px;">
            <a href="{af.name}" style="color:var(--blue);font-weight:600;text-decoration:none;
               padding:6px 14px;border:1.5px solid var(--blue);border-radius:6px;font-size:.82rem;">
              View Report →
            </a>
          </td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>iVisa CSOV — All Reports</title>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --navy:#0A2540; --blue:#394FE1; --green:#00EA80;
    --bg:#F4FBF7; --card:#fff; --border:#D8EDE4;
    --muted:#5A7A6A; --text:#0A2540;
  }}
  *, *::before, *::after {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:'Manrope',Arial,sans-serif; background:var(--bg); color:var(--text); }}
  .header {{ background:#fff; padding:18px 32px; display:flex; align-items:center;
             justify-content:space-between; border-bottom:3px solid var(--green);
             box-shadow:0 2px 8px rgba(0,0,0,.06); }}
  .header h1 {{ font-size:1.15rem; font-weight:800; color:var(--navy); }}
  .header a {{ font-size:.82rem; color:var(--blue); text-decoration:none; font-weight:600; }}
  .container {{ max-width:900px; margin:0 auto; padding:32px 24px; }}
  h2 {{ font-size:1rem; font-weight:800; color:var(--navy);
        border-bottom:3px solid var(--green); padding-bottom:8px; margin-bottom:20px; }}
  table {{ width:100%; border-collapse:collapse; background:var(--card);
           border-radius:12px; overflow:hidden;
           box-shadow:0 1px 3px rgba(10,37,64,.07),0 4px 16px rgba(10,37,64,.06); }}
  thead {{ background:var(--navy); color:#fff; }}
  thead th {{ padding:12px 16px; text-align:left; font-size:.82rem; font-weight:700; letter-spacing:.04em; }}
  tbody tr {{ border-bottom:1px solid var(--border); }}
  tbody tr:last-child {{ border-bottom:none; }}
  tbody tr:hover {{ background:var(--bg); }}
</style>
</head>
<body>
<header class="header">
  <h1>📋 iVisa CSOV — All Weekly Reports</h1>
  <a href="../index.html">← Back to Dashboard</a>
</header>
<div class="container">
  <h2>Reports Archive</h2>
  REPORTS_TABLE_PLACEHOLDER
</div>
</body>
</html>"""

    if not archive_files:
        table_html = "<p style='color:var(--muted);'>No reports archived yet.</p>"
    else:
        table_html = (
            "<table><thead><tr>"
            "<th>Week</th><th>Run Date</th><th>Report</th>"
            "</tr></thead><tbody>" + rows + "</tbody></table>"
        )
    html = html.replace("  REPORTS_TABLE_PLACEHOLDER", table_html)

    out = pathlib.Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    logger.info("  Reports index written: %s", output_path)
