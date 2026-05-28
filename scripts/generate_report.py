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
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --blue:    #2563EB;
    --navy:    #1e3a5f;
    --green:   #16a34a;
    --yellow:  #d97706;
    --red:     #dc2626;
    --bg:      #f8fafc;
    --card:    #ffffff;
    --border:  #e2e8f0;
    --text:    #1e293b;
    --muted:   #64748b;
    --radius:  12px;
    --shadow:  0 1px 3px rgba(0,0,0,.08), 0 4px 16px rgba(0,0,0,.06);
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: var(--bg); color: var(--text); line-height: 1.5; }

  /* ── Header ── */
  .header { background: linear-gradient(135deg, var(--navy) 0%, #2d5a9e 100%);
             color: #fff; padding: 20px 32px; display: flex; align-items: center;
             justify-content: space-between; gap: 16px; flex-wrap: wrap; }
  .header-brand { display: flex; align-items: center; gap: 14px; }
  .header-logo { width: 42px; height: 42px; background: var(--blue);
                  border-radius: 10px; display: flex; align-items: center;
                  justify-content: center; font-weight: 900; font-size: 18px; }
  .header-title h1 { font-size: 1.25rem; font-weight: 700; }
  .header-title p  { font-size: .8rem; opacity: .75; }
  .header-meta { text-align: right; font-size: .8rem; opacity: .8; }
  .header-meta strong { display: block; font-size: 1rem; opacity: 1; }

  /* ── Layout ── */
  .container { max-width: 1280px; margin: 0 auto; padding: 32px 24px; }
  .section-title { font-size: 1.1rem; font-weight: 700; color: var(--navy);
                   margin-bottom: 16px; padding-bottom: 8px;
                   border-bottom: 2px solid var(--blue); }

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
            border-radius: 20px; font-size: .82rem; font-weight: 600; }
  .badge-up   { background: #dcfce7; color: var(--green); }
  .badge-down { background: #fee2e2; color: var(--red); }
  .badge-flat { background: #f1f5f9; color: var(--muted); }
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
  .progress-bar { height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
  .progress-fill { height: 100%; border-radius: 3px; transition: width .6s ease; }
  .fill-green  { background: var(--green); }
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
              font-weight: 500; color: var(--muted); }
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
  .pill { padding: 2px 10px; border-radius: 10px; font-size: .75rem; font-weight: 600; }
  .pill-pos  { background: #dcfce7; color: var(--green); }
  .pill-neg  { background: #fee2e2; color: var(--red); }
  .pill-neu  { background: #f1f5f9; color: var(--muted); }
  .pill-yes  { background: #dbeafe; color: var(--blue); }
  .pill-no   { background: #f1f5f9; color: var(--muted); }
  .domain-link { color: var(--blue); text-decoration: none; font-size: .8rem; }
  .domain-link:hover { text-decoration: underline; }
  .ivisa-row td { background: #eff6ff !important; font-weight: 600; }

  /* ── LLM Section ── */
  .llm-tabs { display: flex; gap: 8px; margin-bottom: 16px; }
  .llm-response { font-size: .8rem; color: var(--muted); max-width: 300px;
                   white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

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
  .action-item  { display: flex; gap: 12px; align-items: flex-start; background: var(--bg);
                   border-radius: 10px; padding: 14px 16px; border-left: 4px solid var(--blue); }
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
    <div class="header-logo">iV</div>
    <div class="header-title">
      <h1>iVisa</h1>
      <p>Credibility Share of Voice Dashboard</p>
    </div>
  </div>
  <div class="header-meta">
    <strong id="weekRange">Loading...</strong>
    Updated every Friday
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
      <div class="section-title">CSOV Trend — Last 8 Weeks</div>
      <div class="chart-container"><canvas id="trendChart"></canvas></div>
    </div>
  </div>

  <!-- COMPONENT CARDS -->
  <div class="section-title">Component Breakdown</div>
  <div class="component-grid" id="componentGrid"></div>

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
      <h3 style="font-size:.9rem;font-weight:600;color:var(--muted);margin-bottom:12px;">AI Overview Results</h3>
      <div class="table-wrap"><table id="aioTable">
        <thead><tr>
          <th>Keyword</th><th>AI Overview?</th><th>iVisa Cited?</th>
          <th>Sentiment</th><th>Score</th>
        </tr></thead>
        <tbody id="aioTableBody"></tbody>
      </table></div>
    </div>

    <!-- LLM Tab -->
    <div class="tab-content" id="tab-llm">
      <div class="llm-tabs">
        <button class="tab-btn active" onclick="showLlmTab('parta',this)">Part A — Brand Queries</button>
        <button class="tab-btn"        onclick="showLlmTab('partb',this)">Part B — General Queries</button>
      </div>
      <div id="llm-parta">
        <div class="table-wrap"><table>
          <thead><tr><th>Query</th><th>Claude Score</th><th>Gemini Score</th><th>Avg Sentiment</th></tr></thead>
          <tbody id="llmPartABody"></tbody>
        </table></div>
      </div>
      <div id="llm-partb" style="display:none;">
        <div class="table-wrap"><table>
          <thead><tr><th>Query</th><th>Claude Mentions?</th><th>Gemini Mentions?</th><th>Avg Sentiment</th></tr></thead>
          <tbody id="llmPartBBody"></tbody>
        </table></div>
      </div>
    </div>

    <!-- Earned Media Tab -->
    <div class="tab-content" id="tab-em">
      <div class="mentions-grid" id="mentionsGrid"></div>
    </div>
  </div>

  <!-- ACTION ITEMS -->
  <div class="chart-card" style="margin-bottom:32px;">
    <div class="section-title">Action Items</div>
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

// ── Utilities ──────────────────────────────────────────────────────────────
function scoreColor(s) {
  if (s >= 75) return 'var(--green)';
  if (s >= 55) return 'var(--yellow)';
  return 'var(--red)';
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
  const color = score >= 75 ? '#16a34a' : score >= 55 ? '#d97706' : '#dc2626';

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
        ${trend}
      </div>`;
  });
}

// ── Trend Chart ────────────────────────────────────────────────────────────
function buildTrendChart(history) {
  if (!history || !history.length) return;
  const labels   = history.map(h => h.week_label);
  const datasets = [
    { label: 'Overall CSOV',  data: history.map(h=>h.csov),         borderColor:'#2563EB', backgroundColor:'rgba(37,99,235,.1)',  tension:.35, fill:false, borderWidth:3 },
    { label: 'SERP',          data: history.map(h=>h.serp),         borderColor:'#16a34a', backgroundColor:'transparent',          tension:.35, fill:false, borderWidth:2 },
    { label: 'AI Overview',   data: history.map(h=>h.ai_overview),  borderColor:'#d97706', backgroundColor:'transparent',          tension:.35, fill:false, borderWidth:2 },
    { label: 'LLM',           data: history.map(h=>h.llm),          borderColor:'#7c3aed', backgroundColor:'transparent',          tension:.35, fill:false, borderWidth:2 },
    { label: 'Earned Media',  data: history.map(h=>h.earned_media), borderColor:'#ec4899', backgroundColor:'transparent',          tension:.35, fill:false, borderWidth:2 },
  ];

  new Chart(document.getElementById('trendChart'), {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16, font: { size: 11 } } } },
      scales: {
        y: { min: 0, max: 100, grid: { color: '#f1f5f9' }, ticks: { font: { size: 11 } } },
        x: { grid: { display: false }, ticks: { font: { size: 11 } } },
      },
    },
  });
}

// ── Country Grid ───────────────────────────────────────────────────────────
function buildCountryGrid(countryData) {
  const grid = document.getElementById('countryGrid');
  Object.entries(countryData).forEach(([code, country]) => {
    const score = (country.csov_score || 0).toFixed(1);
    const c     = country.components || {};
    const segs  = [
      { w: (c.serp||0)*0.35, color:'#2563EB' },
      { w: (c.ai_overview||0)*0.25, color:'#d97706' },
      { w: (c.llm||0)*0.25,  color:'#7c3aed' },
      { w: (c.earned_media||0)*0.15, color:'#ec4899' },
    ];
    const total = segs.reduce((s,x)=>s+x.w,0)||1;

    grid.innerHTML += `
      <div class="country-card" id="cc-${code}" onclick="selectCountry('${code}', REPORT_DATA)">
        <div class="country-flag">${country.flag||''}</div>
        <div class="country-name">${country.name}</div>
        <div class="country-score" style="color:${scoreColor(country.csov_score||0)}">${score}</div>
        <div class="mini-bar-wrap">
          ${segs.map(s=>`<div class="mini-seg" style="width:${(s.w/total*100).toFixed(1)}%;background:${s.color}"></div>`).join('')}
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

  // SERP Table
  buildSerpTable(D.serp_data?.results?.[code] || {});
  // AIO Table
  buildAioTable(D.ai_overview_data?.results?.[code] || {});
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

    let rows = '';
    (results || []).slice(0,10).forEach(r => {
      const titleText = (r.title || '').substring(0, 70) + ((r.title||'').length > 70 ? '…' : '');
      const urlShort  = (r.url || '').replace(/^https?:\/\//, '').substring(0, 55);
      rows += `
        <tr class="${r.is_ivisa ? 'ivisa-row' : ''}">
          <td>${r.position ? posBadge(r.position) : '—'}</td>
          <td>
            <div style="font-size:.82rem;font-weight:${r.is_ivisa?'700':'400'};color:var(--text);">${titleText || '—'}</div>
            <a class="domain-link" href="${r.url||'#'}" target="_blank" style="font-size:.75rem;">${urlShort}</a>
          </td>
          <td><a class="domain-link" href="https://${r.domain}" target="_blank">${r.domain||'—'}</a></td>
          <td style="text-align:center">${sentEmoji(r.sentiment)} ${pillSentiment(r.sentiment)}</td>
        </tr>`;
    });

    if (!rows) {
      rows = '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:12px;">No data</td></tr>';
    }

    container.innerHTML += `
      <div style="margin-bottom:28px;">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
          <span style="font-size:.85rem;font-weight:700;color:var(--navy);">${kw}</span>
          <span style="font-size:.8rem;font-weight:700;color:${scoreColor};background:var(--bg);
                       padding:2px 10px;border-radius:10px;border:1px solid var(--border);">
            SERP Score: ${score}/100
          </span>
        </div>
        <div class="table-wrap">
          <table style="font-size:.82rem;">
            <thead><tr>
              <th style="width:40px;">Pos</th>
              <th>Page Title / URL</th>
              <th>Domain</th>
              <th style="text-align:center;">Sentiment</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`;
  });
}

// ── AIO Table ──────────────────────────────────────────────────────────────
function buildAioTable(countryResults) {
  const tbody = document.getElementById('aioTableBody');
  tbody.innerHTML = '';
  Object.entries(countryResults).forEach(([kw, r]) => {
    tbody.innerHTML += `
      <tr>
        <td>${kw}</td>
        <td>${r.has_ai_overview == null ? '<span class="pill pill-neu">No data</span>' : pillBool(r.has_ai_overview)}</td>
        <td>${r.ivisa_cited == null     ? '<span class="pill pill-neu">—</span>'      : pillBool(r.ivisa_cited, 'Cited', 'Not cited')}</td>
        <td>${r.sentiment_score != null ? fmtScore(r.sentiment_score)+'%' : '—'}</td>
        <td>${r.score != null           ? fmtScore(r.score) : '—'}</td>
      </tr>`;
  });
  if (!tbody.innerHTML) tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:24px;">No AI Overview data available</td></tr>';
}

// ── LLM Tables ─────────────────────────────────────────────────────────────
function buildLlmTables(llmData) {
  if (!llmData) return;

  // Part A
  const partA = llmData.part_a?.results || [];
  const tbodyA = document.getElementById('llmPartABody');
  partA.forEach(r => {
    tbodyA.innerHTML += `
      <tr>
        <td style="max-width:260px">${r.query}</td>
        <td>
          <span style="font-weight:700;color:${scoreColor(r.claude_sentiment||0)}">${fmtScore(r.claude_sentiment)}</span>
          <div class="llm-response">${(r.claude_response||'').substring(0,80)}…</div>
        </td>
        <td>
          <span style="font-weight:700;color:${scoreColor(r.gemini_sentiment||0)}">${fmtScore(r.gemini_sentiment)}</span>
          <div class="llm-response">${(r.gemini_response||'').substring(0,80)}…</div>
        </td>
        <td>
          <span style="font-weight:700;color:${scoreColor(r.avg_sentiment||0)}">${fmtScore(r.avg_sentiment)}</span>
          <div class="progress-bar" style="width:80px">
            <div class="progress-fill ${fillClass(r.avg_sentiment||0)}" style="width:${r.avg_sentiment||0}%"></div>
          </div>
        </td>
      </tr>`;
  });
  if (!tbodyA.innerHTML) tbodyA.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:24px;">No LLM Part A data</td></tr>';

  // Part B
  const partB = llmData.part_b?.results || [];
  const tbodyB = document.getElementById('llmPartBBody');
  partB.forEach(r => {
    tbodyB.innerHTML += `
      <tr>
        <td style="max-width:260px">${r.query}</td>
        <td>${pillBool(r.claude_mentions_ivisa, 'Yes ✓', 'No')}</td>
        <td>${pillBool(r.gemini_mentions_ivisa, 'Yes ✓', 'No')}</td>
        <td>${r.avg_sentiment != null
          ? `<span style="font-weight:700;color:${scoreColor(r.avg_sentiment)}">${fmtScore(r.avg_sentiment)}</span>`
          : '—'}</td>
      </tr>`;
  });
  if (!tbodyB.innerHTML) tbodyB.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:24px;">No LLM Part B data</td></tr>';
}

// ── Earned Media ───────────────────────────────────────────────────────────
function buildEarnedMedia(earnedMedia) {
  const grid = document.getElementById('mentionsGrid');
  const mentions = earnedMedia?.mentions || [];

  if (!mentions.length) {
    grid.innerHTML = '<p style="color:var(--muted);grid-column:1/-1;">No earned media mentions on record. Update data/earned_media.json with Brand24 export.</p>';
    return;
  }

  mentions.forEach(m => {
    const sentCls = m.sentiment === 'positive' ? 'pill-pos' : m.sentiment === 'negative' ? 'pill-neg' : 'pill-neu';
    grid.innerHTML += `
      <div class="mention-card">
        <div class="mention-source">${m.source || 'Unknown Source'}</div>
        <div class="mention-title">${m.title || 'Untitled mention'}</div>
        <div class="mention-footer">
          <span class="pill ${sentCls}">${m.sentiment || 'neutral'}</span>
          <span>${m.date || ''}</span>
          ${m.url ? `<a class="domain-link" href="${m.url}" target="_blank">View →</a>` : ''}
        </div>
      </div>`;
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

    # Embed JSON safely
    json_str = json.dumps(report_data, ensure_ascii=False, default=str)
    html = HTML_TEMPLATE.replace("__REPORT_DATA_PLACEHOLDER__", json_str)

    out = pathlib.Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    logger.info("  Report written to: %s (%d KB)", output_path, len(html) // 1024)
