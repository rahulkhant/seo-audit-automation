"""
Agent 4: Dashboard (Metronic-inspired design).

Purpose of this file
--------------------
Builds the site's two dashboard pages, styled after the "Metronic"
admin-dashboard design system (Keenthemes) -- sidebar app navigation, a
topbar, KPI stat cards, card-wrapped tables, pill severity badges, and a
real ApexCharts donut chart -- while reusing the shared data-loading
functions and PDF archive from build_dashboard.py, so there is zero
duplicated database logic.

This is NOT a Metronic license/asset import -- Metronic itself is a paid
Keenthemes template. Everything here (CSS, icons, layout) is hand-rolled to
look like Metronic's visual language, the same way the previous dashboard's
donut chart was hand-rolled SVG rather than a charting library.

Output:
  - docs/index.html
  - docs/history.html
"""

import html
from pathlib import Path

from agent2_storage.database import get_connection
from agent4_dashboard.build_dashboard import (
    CATEGORIES,
    ROWS_PER_PAGE,
    SEVERITY_ORDER,
    _categorize_rule,
    _format_timestamp,
    _pdf_filename,
    compute_trend,
    load_all_runs,
    load_findings,
    load_run_info,
)

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
INDEX_FILE_PATH = DOCS_DIR / "index.html"
HISTORY_FILE_PATH = DOCS_DIR / "history.html"

# Metronic's real default-theme semantic colors (Keenthemes) -- used here
# purely as color values, deliberately different from the classic
# dashboard's SEVERITY_DISPLAY palette so this preview reads as authentically
# "Metronic" rather than the existing look with new fonts.
MX_SEVERITY = {
    "critical": {"label": "Critical", "icon": "⛔", "color": "#f1416c"},
    "warning": {"label": "Warning", "icon": "⚠", "color": "#ffc700"},
    "info": {"label": "Info", "icon": "ℹ", "color": "#7239ea"},
}
MX_RESOLVED_COLOR = "#50cd89"
MX_PRIMARY_COLOR = "#009ef7"

# Small hand-drawn line icons -- Metronic's own icon pack ("Keenicons") is
# proprietary to the paid template, so these are simple generic stand-ins,
# not sourced from any specific licensed icon set.
ICON_HOME = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11.5 12 4l8 7.5"/><path d="M6 10v9a1 1 0 0 0 1 1h4v-6h2v6h4a1 1 0 0 0 1-1v-9"/></svg>'
ICON_HISTORY = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>'
ICON_DOWNLOAD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11"/><path d="M7.5 11 12 15.5 16.5 11"/><path d="M5 18.5h14"/></svg>'
ICON_TOTAL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h11"/><path d="M8 12h11"/><path d="M8 18h11"/><path d="M4 6h.01"/><path d="M4 12h.01"/><path d="M4 18h.01"/></svg>'
ICON_CRITICAL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 3.5h7l5 5v7l-5 5h-7l-5-5v-7z"/><path d="M12 8v5"/><path d="M12 16.5h.01"/></svg>'
ICON_WARNING = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4 2 20h20z"/><path d="M12 10v4"/><path d="M12 17h.01"/></svg>'
ICON_INFO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 11v5"/><path d="M12 8h.01"/></svg>'
ICON_NEW = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 8.5v7"/><path d="M8.5 12h7"/></svg>'
ICON_RESOLVED = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5 9 17.5 20 6.5"/></svg>'
ICON_RECURRING = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9a8 8 0 0 1 13.5-4.5L20 7"/><path d="M20 4v3.5h-3.5"/><path d="M20 15a8 8 0 0 1-13.5 4.5L4 17"/><path d="M4 20v-3.5h3.5"/></svg>'


def _mx_shared_style():
    """CSS shared by both Metronic-preview pages -- Metronic's real default
    palette, Inter typography, dark-navy sidebar, card/topbar layout."""
    return """
  :root {
    color-scheme: light;
    --mx-body-bg: #f5f8fa;
    --mx-card-bg: #ffffff;
    --mx-border: #eff2f5;
    --mx-text-dark: #181c32;
    --mx-text-gray-700: #3f4254;
    --mx-text-gray-600: #7e8299;
    --mx-text-gray-500: #a1a5b7;
    --mx-primary: #009ef7;
    --mx-primary-light: rgba(0,158,247,0.1);
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) {
      color-scheme: dark;
      --mx-body-bg: #15151f;
      --mx-card-bg: #1c1c28;
      --mx-border: #2b2b3a;
      --mx-text-dark: #ffffff;
      --mx-text-gray-700: #cdcddb;
      --mx-text-gray-600: #9899ac;
      --mx-text-gray-500: #6d6d80;
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --mx-body-bg: #15151f;
    --mx-card-bg: #1c1c28;
    --mx-border: #2b2b3a;
    --mx-text-dark: #ffffff;
    --mx-text-gray-700: #cdcddb;
    --mx-text-gray-600: #9899ac;
    --mx-text-gray-500: #6d6d80;
  }

  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--mx-body-bg);
    color: var(--mx-text-dark);
    font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  a { color: inherit; }

  .app { display: flex; min-height: 100vh; align-items: stretch; }

  .sidebar {
    width: 264px; flex-shrink: 0; background: #1e1e2d; color: #92929f;
    display: flex; flex-direction: column; position: sticky; top: 0; height: 100vh;
  }
  .sidebar-brand {
    padding: 22px 24px; font-size: 1.05rem; font-weight: 700; color: #ffffff;
    display: flex; align-items: center; gap: 10px;
  }
  .brand-badge {
    width: 32px; height: 32px; border-radius: 8px; background: var(--mx-primary);
    display: flex; align-items: center; justify-content: center; font-weight: 700; color: #fff; font-size: 0.9rem;
  }
  .sidebar-nav { padding: 8px 12px; display: flex; flex-direction: column; gap: 2px; flex: 1; }
  .sidebar-link {
    display: flex; align-items: center; gap: 12px; padding: 11px 14px; border-radius: 8px;
    text-decoration: none; color: #92929f; font-size: 0.92rem; font-weight: 500;
  }
  .sidebar-link svg { width: 18px; height: 18px; flex-shrink: 0; }
  .sidebar-link:hover { color: #ffffff; background: rgba(255,255,255,0.06); }
  .sidebar-link.active { color: #ffffff; background: rgba(255,255,255,0.06); box-shadow: inset 3px 0 0 var(--mx-primary); }

  .main { flex: 1; min-width: 0; display: flex; flex-direction: column; }

  .topbar {
    display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;
    padding: 20px 32px; background: var(--mx-card-bg); border-bottom: 1px solid var(--mx-border);
  }
  .topbar-title { font-size: 1.25rem; font-weight: 700; }
  .topbar-sub { color: var(--mx-text-gray-600); font-size: 0.87rem; margin-top: 3px; }

  .btn {
    display: inline-flex; align-items: center; gap: 8px; font-weight: 600; font-size: 0.87rem;
    padding: 10px 18px; border-radius: 8px; text-decoration: none; border: none; cursor: pointer;
    font-family: inherit; white-space: nowrap;
  }
  .btn svg { width: 16px; height: 16px; }
  .btn-primary { background: var(--mx-primary); color: #ffffff; }
  .btn-primary:hover { background: #008fdd; }
  .btn-light { background: var(--mx-primary-light); color: var(--mx-primary); }
  .btn-light:hover { background: rgba(0,158,247,0.18); }
  .btn:disabled { opacity: 0.4; cursor: default; }

  .content { padding: 28px 32px 48px; max-width: 1360px; width: 100%; margin: 0 auto; }

  .kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 20px; }
  .kpi-card {
    background: var(--mx-card-bg); border: 1px solid var(--mx-border); border-radius: 12px;
    padding: 20px; display: flex; align-items: center; gap: 16px;
  }
  .kpi-icon {
    width: 48px; height: 48px; border-radius: 10px; display: flex; align-items: center; justify-content: center;
    flex-shrink: 0; color: var(--kpi-color); background-color: color-mix(in srgb, var(--kpi-color) 15%, transparent);
  }
  .kpi-icon svg { width: 22px; height: 22px; }
  .kpi-value { font-size: 1.6rem; font-weight: 700; line-height: 1.1; }
  .kpi-label { color: var(--mx-text-gray-600); font-size: 0.85rem; margin-top: 3px; }

  .row-2col { display: grid; grid-template-columns: 1.1fr 1fr; gap: 20px; margin-bottom: 20px; align-items: stretch; }

  .card { background: var(--mx-card-bg); border: 1px solid var(--mx-border); border-radius: 12px; }
  .card-header {
    display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
    padding: 18px 22px; border-bottom: 1px solid var(--mx-border);
  }
  .card-header-title { font-size: 1.02rem; font-weight: 700; }
  .card-body { padding: 20px 22px; }

  .chart-pages-audited { text-align: center; color: var(--mx-text-gray-600); font-size: 0.85rem; margin-top: 8px; }
  .chart-empty, .trend-empty { color: var(--mx-text-gray-600); font-size: 0.9rem; padding: 24px 0; text-align: center; }

  .trend-list { display: flex; flex-direction: column; gap: 16px; padding: 22px; }
  .trend-list-item { display: flex; align-items: center; gap: 12px; }
  .trend-icon {
    width: 38px; height: 38px; border-radius: 9px; display: flex; align-items: center; justify-content: center;
    flex-shrink: 0; color: var(--kpi-color); background-color: color-mix(in srgb, var(--kpi-color) 15%, transparent);
  }
  .trend-icon svg { width: 18px; height: 18px; }
  .trend-value { font-weight: 700; font-size: 1.05rem; }
  .trend-desc { color: var(--mx-text-gray-600); font-size: 0.85rem; }

  .card-header-controls { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
  #category-select, #search-input {
    font-family: inherit; font-size: 0.87rem; padding: 9px 14px; border-radius: 8px;
    border: 1px solid var(--mx-border); background: var(--mx-body-bg); color: var(--mx-text-dark);
  }
  #category-select { min-width: 230px; }
  #search-input { min-width: 260px; }

  .table-wrap { overflow-x: auto; }
  table { width: 100%; table-layout: fixed; border-collapse: collapse; }
  thead th {
    text-align: left; padding: 12px 22px; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.03em;
    color: var(--mx-text-gray-500); font-weight: 600; border-bottom: 1px solid var(--mx-border); white-space: nowrap;
  }
  tbody td {
    padding: 14px 22px; font-size: 0.87rem; vertical-align: top; border-bottom: 1px solid var(--mx-border);
    word-wrap: break-word; overflow-wrap: break-word;
  }
  tbody tr:hover { background: var(--mx-body-bg); }
  td.muted { color: var(--mx-text-gray-600); }

  .severity-badge {
    display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 999px;
    font-weight: 600; font-size: 0.78rem; color: var(--badge-color); white-space: nowrap;
    background-color: color-mix(in srgb, var(--badge-color) 14%, transparent);
  }

  .pagination-bar { display: flex; align-items: center; gap: 12px; padding: 18px 22px; }
  #page-indicator { color: var(--mx-text-gray-600); font-size: 0.85rem; }

  col.col-severity { width: 12%; }
  col.col-page { width: 22%; }
  col.col-issue { width: 27%; }
  col.col-expected { width: 19%; }
  col.col-actual { width: 20%; }
  col.col-run { width: 12%; }
  col.col-date { width: 24%; }
  col.col-pages { width: 14%; }
  col.col-hist-severity { width: 30%; }
  col.col-download { width: 20%; }

  @media (max-width: 960px) {
    .row-2col { grid-template-columns: 1fr; }
    .kpi-row { grid-template-columns: repeat(2, 1fr); }
  }
  @media (max-width: 720px) {
    .app { flex-direction: column; }
    .sidebar { width: 100%; height: auto; position: static; flex-direction: row; align-items: center; }
    .sidebar-nav { flex-direction: row; }
    .kpi-row { grid-template-columns: 1fr; }
    .content { padding: 20px; }
  }
"""


# Client-side filter/search/pagination -- identical behavior to the classic
# dashboard (cached <tr> elements, data-category/data-search attributes,
# pure style.display toggling), only the markup/classes it targets changed.
# Placeholder tokens (not an f-string) so none of the JS's own { } need
# escaping.
_CLIENT_SCRIPT_TEMPLATE = """
(function () {
  var rowsPerPage = __ROWS_PER_PAGE__;
  var currentPage = 1;
  var currentCategory = "all";
  var currentSearch = "";
  var allRows = Array.from(document.querySelectorAll("#findings-table tbody tr"));
  var prevButton = document.getElementById("prev-page");

  function getFilteredRows() {
    return allRows.filter(function (row) {
      var matchesCategory = currentCategory === "all" || row.getAttribute("data-category") === currentCategory;
      var matchesSearch = currentSearch === "" || row.getAttribute("data-search").indexOf(currentSearch) !== -1;
      return matchesCategory && matchesSearch;
    });
  }

  function render() {
    var filteredRows = getFilteredRows();
    var totalPages = Math.max(1, Math.ceil(filteredRows.length / rowsPerPage));
    if (currentPage > totalPages) { currentPage = totalPages; }

    allRows.forEach(function (row) { row.style.display = "none"; });
    var startIndex = (currentPage - 1) * rowsPerPage;
    filteredRows.slice(startIndex, startIndex + rowsPerPage).forEach(function (row) {
      row.style.display = "";
    });

    document.getElementById("page-indicator").textContent =
      "Page " + currentPage + " of " + totalPages + " (" + filteredRows.length + " findings)";
    prevButton.disabled = currentPage <= 1;
    document.getElementById("next-page").disabled = currentPage >= totalPages;
  }

  if (prevButton) {
    document.getElementById("category-select").addEventListener("change", function (event) {
      currentCategory = event.target.value;
      currentPage = 1;
      render();
    });

    document.getElementById("search-input").addEventListener("input", function (event) {
      currentSearch = event.target.value.trim().toLowerCase();
      currentPage = 1;
      render();
    });

    prevButton.addEventListener("click", function () {
      if (currentPage > 1) { currentPage -= 1; render(); }
    });
    document.getElementById("next-page").addEventListener("click", function () {
      currentPage += 1; render();
    });

    render();
  }
})();
"""

# ApexCharts donut init -- same severity counts as the KPI tiles, rendered
# via the one small CDN-loaded chart library (real Metronic itself uses
# ApexCharts, so this is the authentic choice rather than an imitation).
_CHART_SCRIPT_TEMPLATE = """
var chartEl = document.querySelector("#healthChart");
if (chartEl && window.ApexCharts) {
  var chart = new ApexCharts(chartEl, {
    chart: { type: "donut", height: 260, fontFamily: "Inter, sans-serif" },
    series: [__CRITICAL__, __WARNING__, __INFO__],
    labels: ["Critical", "Warning", "Info"],
    colors: ["__CRITICAL_COLOR__", "__WARNING_COLOR__", "__INFO_COLOR__"],
    legend: { position: "bottom" },
    dataLabels: { enabled: false },
    stroke: { width: 0 },
    plotOptions: {
      pie: {
        donut: {
          size: "68%",
          labels: {
            show: true,
            total: { show: true, label: "Total Issues", showAlways: true, fontSize: "13px" }
          }
        }
      }
    }
  });
  chart.render();
}
"""


def _render_client_script():
    return _CLIENT_SCRIPT_TEMPLATE.replace("__ROWS_PER_PAGE__", str(ROWS_PER_PAGE))


def _render_chart_init_script(counts):
    script = _CHART_SCRIPT_TEMPLATE
    script = script.replace("__CRITICAL__", str(counts["critical"]))
    script = script.replace("__WARNING__", str(counts["warning"]))
    script = script.replace("__INFO__", str(counts["info"]))
    script = script.replace("__CRITICAL_COLOR__", MX_SEVERITY["critical"]["color"])
    script = script.replace("__WARNING_COLOR__", MX_SEVERITY["warning"]["color"])
    script = script.replace("__INFO_COLOR__", MX_SEVERITY["info"]["color"])
    return script


def _render_sidebar_nav(active_page):
    """Primary navigation -- Dashboard / History -- with categories living
    in the Findings card's own filter control instead of the sidebar (see
    _render_findings_card)."""
    dashboard_class = "sidebar-link active" if active_page == "dashboard" else "sidebar-link"
    history_class = "sidebar-link active" if active_page == "history" else "sidebar-link"
    return f"""
    <aside class="sidebar">
      <div class="sidebar-brand">
        <span class="brand-badge">S</span>
        <span>Simprosys SEO</span>
      </div>
      <nav class="sidebar-nav">
        <a class="{dashboard_class}" href="index.html">{ICON_HOME}<span>Dashboard</span></a>
        <a class="{history_class}" href="history.html">{ICON_HISTORY}<span>History</span></a>
      </nav>
    </aside>
    """


def _render_topbar(title, subtitle_html, pdf_href=None):
    download_link = (
        f'<a class="btn btn-primary" href="{pdf_href}">{ICON_DOWNLOAD}<span>Download PDF</span></a>'
        if pdf_href
        else ""
    )
    return f"""
    <header class="topbar">
      <div>
        <div class="topbar-title">{html.escape(title)}</div>
        <div class="topbar-sub">{subtitle_html}</div>
      </div>
      {download_link}
    </header>
    """


def _render_kpi_tiles(counts, total):
    tiles = [
        ("Total Findings", total, MX_PRIMARY_COLOR, ICON_TOTAL),
        ("Critical", counts["critical"], MX_SEVERITY["critical"]["color"], ICON_CRITICAL),
        ("Warning", counts["warning"], MX_SEVERITY["warning"]["color"], ICON_WARNING),
        ("Info", counts["info"], MX_SEVERITY["info"]["color"], ICON_INFO),
    ]
    cards = [
        f"""
        <div class="kpi-card">
          <div class="kpi-icon" style="--kpi-color: {color}">{icon}</div>
          <div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-label">{label}</div>
          </div>
        </div>
        """
        for label, value, color, icon in tiles
    ]
    return f'<section class="kpi-row">{"".join(cards)}</section>'


def _render_chart_card(counts, total, run_info):
    if total == 0:
        chart_body = '<div class="chart-empty">No findings recorded for this run.</div>'
    else:
        chart_body = '<div id="healthChart"></div>'
    return f"""
    <div class="card chart-card">
      <div class="card-header"><div class="card-header-title">Health Overview</div></div>
      <div class="card-body">
        {chart_body}
        <div class="chart-pages-audited">Pages Audited: <strong>{run_info['total_pages_crawled']}</strong></div>
      </div>
    </div>
    """


def _render_trend_card(trend):
    if trend is None:
        body = '<p class="trend-empty">This is the first recorded run -- no previous run to compare against yet.</p>'
    else:
        items = [
            (ICON_NEW, MX_SEVERITY["critical"]["color"], trend["new_count"], "new since last run"),
            (ICON_RESOLVED, MX_RESOLVED_COLOR, trend["resolved_count"], "resolved since last run"),
            (ICON_RECURRING, MX_SEVERITY["info"]["color"], trend["recurring_count"], "still present from last run"),
        ]
        rows = [
            f"""
            <div class="trend-list-item">
              <div class="trend-icon" style="--kpi-color: {color}">{icon}</div>
              <div>
                <div class="trend-value">{value}</div>
                <div class="trend-desc">{label}</div>
              </div>
            </div>
            """
            for icon, color, value, label in items
        ]
        body = f'<div class="trend-list">{"".join(rows)}</div>'
    return f"""
    <div class="card trend-card">
      <div class="card-header"><div class="card-header-title">Since Last Run</div></div>
      {body}
    </div>
    """


def _render_category_options(findings):
    """<option> per SEO checklist category (with a live count), standing in
    for the classic dashboard's sidebar category rail -- same CATEGORIES
    list and _categorize_rule mapping, just a dropdown instead of buttons."""
    counts_by_category = {category_id: 0 for category_id, _, _ in CATEGORIES}
    for finding in findings:
        category_id, _ = _categorize_rule(finding["rule"])
        counts_by_category[category_id] = counts_by_category.get(category_id, 0) + 1

    options = [f'<option value="all">All Issues ({len(findings)})</option>']
    for category_id, category_label, _ in CATEGORIES:
        count = counts_by_category.get(category_id, 0)
        options.append(f'<option value="{category_id}">{html.escape(category_label)} ({count})</option>')
    return "".join(options)


def _render_findings_table_rows_mx(findings):
    """Same structure/data-attributes as the classic dashboard's
    _render_findings_table_rows, using Metronic's severity colors/badge
    style instead."""
    severity_rank = {severity: index for index, severity in enumerate(SEVERITY_ORDER)}
    sorted_findings = sorted(findings, key=lambda f: severity_rank.get(f["severity"], 99))

    rows_html = []
    for finding in sorted_findings:
        meta = MX_SEVERITY.get(finding["severity"], MX_SEVERITY["info"])
        category_id, category_label = _categorize_rule(finding["rule"])
        searchable_text = " ".join([
            meta["label"],
            finding["page_url"],
            finding["issue"],
            finding["expected"] or "",
            finding["actual"] or "",
            category_label,
        ]).lower()
        rows_html.append(f"""
        <tr data-severity="{html.escape(finding['severity'])}" data-category="{category_id}" data-search="{html.escape(searchable_text)}">
          <td><span class="severity-badge" style="--badge-color: {meta['color']}">{meta['icon']} {meta['label']}</span></td>
          <td><a href="{html.escape(finding['page_url'])}" target="_blank" rel="noopener">{html.escape(finding['page_url'])}</a></td>
          <td>{html.escape(finding['issue'])}</td>
          <td class="muted">{html.escape(finding['expected'] or '')}</td>
          <td class="muted">{html.escape(finding['actual'] or '')}</td>
        </tr>
        """)

    return "".join(rows_html)


def _render_findings_card(findings):
    return f"""
    <section class="card findings-card">
      <div class="card-header">
        <div class="card-header-title">Findings</div>
        <div class="card-header-controls">
          <select id="category-select">
            {_render_category_options(findings)}
          </select>
          <input type="search" id="search-input" placeholder="Search page, issue, severity, expected/actual values...">
        </div>
      </div>
      <div class="table-wrap">
        <table id="findings-table">
          <colgroup>
            <col class="col-severity"><col class="col-page"><col class="col-issue">
            <col class="col-expected"><col class="col-actual">
          </colgroup>
          <thead>
            <tr><th>Severity</th><th>Page</th><th>Issue</th><th>Expected</th><th>Actual</th></tr>
          </thead>
          <tbody>
            {_render_findings_table_rows_mx(findings)}
          </tbody>
        </table>
      </div>
      <div class="pagination-bar">
        <button id="prev-page" class="btn btn-light">&larr; Prev</button>
        <span id="page-indicator"></span>
        <button id="next-page" class="btn btn-light">Next &rarr;</button>
      </div>
    </section>
    """


def _shared_head(title):
    return f"""
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
{_mx_shared_style()}
</style>
"""


def generate_metronic_index_html(connection, run_id):
    run_info = load_run_info(connection, run_id)
    findings = load_findings(connection, run_id)
    trend = compute_trend(connection, run_id)

    counts = {severity: 0 for severity in SEVERITY_ORDER}
    for finding in findings:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
    total = len(findings)

    subtitle_html = (
        f"{html.escape(run_info['site_root_url'])} &middot; Run #{run_id} &middot; "
        f"{html.escape(_format_timestamp(run_info['run_timestamp']))}"
    )
    pdf_href = f"reports/{_pdf_filename(run_id)}"

    apex_cdn_tag = (
        '<script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>' if total > 0 else ""
    )
    chart_init_script = _render_chart_init_script(counts) if total > 0 else ""

    return f"""<!doctype html>
<html lang="en">
<head>
{_shared_head(f"SEO Audit Dashboard - {run_info['site_root_url']}")}
</head>
<body>
<div class="app">
  {_render_sidebar_nav("dashboard")}
  <div class="main">
    {_render_topbar("SEO Audit Dashboard", subtitle_html, pdf_href)}
    <main class="content">
      {_render_kpi_tiles(counts, total)}
      <section class="row-2col">
        {_render_chart_card(counts, total, run_info)}
        {_render_trend_card(trend)}
      </section>
      {_render_findings_card(findings)}
    </main>
  </div>
</div>
{apex_cdn_tag}
<script>
{chart_init_script}
{_render_client_script()}
</script>
</body>
</html>
"""


def _render_history_rows_mx(connection, runs):
    rows_html = []
    for run in runs:
        findings = load_findings(connection, run["run_id"])
        counts = {severity: 0 for severity in SEVERITY_ORDER}
        for finding in findings:
            counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1

        severity_summary = " &nbsp; ".join(
            f'<span class="severity-badge" style="--badge-color: {MX_SEVERITY[s]["color"]}">'
            f'{MX_SEVERITY[s]["icon"]} {counts[s]}</span>'
            for s in SEVERITY_ORDER
        )

        rows_html.append(f"""
        <tr>
          <td>Run #{run['run_id']}</td>
          <td>{html.escape(_format_timestamp(run['run_timestamp']))}</td>
          <td>{run['total_pages_crawled']}</td>
          <td>{severity_summary}</td>
          <td><a class="btn btn-light" href="reports/{_pdf_filename(run['run_id'])}">{ICON_DOWNLOAD}<span>Download PDF</span></a></td>
        </tr>
        """)
    return "".join(rows_html)


def generate_metronic_history_html(connection):
    """Same run-by-run data and "PDF download only, never browsable" rule
    as the classic history page -- restyled only."""
    runs = load_all_runs(connection)
    rows_html = _render_history_rows_mx(connection, runs)

    return f"""<!doctype html>
<html lang="en">
<head>
{_shared_head("SEO Audit Report History")}
</head>
<body>
<div class="app">
  {_render_sidebar_nav("history")}
  <div class="main">
    {_render_topbar("Report History", "Every past audit run. Older reports are downloadable as PDF only.")}
    <main class="content">
      <section class="card">
        <div class="table-wrap">
          <table>
            <colgroup>
              <col class="col-run"><col class="col-date"><col class="col-pages">
              <col class="col-hist-severity"><col class="col-download">
            </colgroup>
            <thead>
              <tr><th>Run</th><th>Date</th><th>Pages Audited</th><th>Severity Summary</th><th>Report</th></tr>
            </thead>
            <tbody>
              {rows_html}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  </div>
</div>
</body>
</html>
"""


def build_and_save_dashboard(run_id=None):
    connection = get_connection()
    try:
        if run_id is None:
            row = connection.execute("SELECT MAX(run_id) FROM runs").fetchone()
            run_id = row[0]

        DOCS_DIR.mkdir(parents=True, exist_ok=True)

        index_html = generate_metronic_index_html(connection, run_id)
        with open(INDEX_FILE_PATH, "w", encoding="utf-8") as index_file:
            index_file.write(index_html)

        history_html = generate_metronic_history_html(connection)
        with open(HISTORY_FILE_PATH, "w", encoding="utf-8") as history_file:
            history_file.write(history_html)

        return run_id, INDEX_FILE_PATH
    finally:
        connection.close()


if __name__ == "__main__":
    saved_run_id, saved_path = build_and_save_dashboard()
    print(f"Dashboard built for run_id={saved_run_id}")
    print(f"Saved to: {saved_path}")
