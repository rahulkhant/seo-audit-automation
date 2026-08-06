"""
Keyword Research module: dashboard page.

Purpose of this file
--------------------
Builds docs/keyword-research.html -- the master cumulative keyword list's
insights (competitor overlap, opportunity keywords, trending keywords,
per-competitor summary, and the full searchable unique keyword table),
plus a Batch History tab listing every research run individually, using
the same Metronic shell as every other dashboard page.

This file does no analysis itself -- it only reads what
keyword_research.database already saved and what keyword_research.analytics
already computed, and turns it into something readable, same division of
labor as Agent 4 for the audit pipeline.

Generates:
  - docs/keyword-research.html
  - docs/keyword_research_exports/master-keywords-latest.xlsx (the full
    deduped master list, always overwritten -- same "always the latest
    snapshot" pattern as reporting-hub-latest.pdf)
  - docs/keyword_research_exports/master-insights-latest.pdf
  - docs/keyword_research_exports/batch-XXXX-keywords.xlsx (one per batch,
    permanent -- that batch's own keyword list as saved)
  - docs/keyword_research_exports/batch-XXXX-insights.pdf
"""

import html
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from playwright.sync_api import sync_playwright

from keyword_research.database import get_connection, load_all_batches, load_keywords_for_batch, load_master_keywords
from keyword_research.analytics import run_all_analytics
from agent4_dashboard.build_dashboard_metronic import (
    ICON_DOWNLOAD,
    ICON_KEYWORDS,
    ICON_NEW,
    ICON_RESOLVED,
    ICON_TOTAL,
    MX_PRIMARY_COLOR,
    MX_RESOLVED_COLOR,
    MX_SEVERITY,
    _render_sidebar_nav,
    _render_topbar,
    _shared_head,
)

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
KEYWORD_RESEARCH_FILE_PATH = DOCS_DIR / "keyword-research.html"
EXPORTS_DIR_PATH = DOCS_DIR / "keyword_research_exports"
MASTER_XLSX_FILENAME = "master-keywords-latest.xlsx"
MASTER_PDF_FILENAME = "master-insights-latest.pdf"

_TABLE_ROWS_PER_PAGE = 25

_KEYWORD_RESEARCH_STYLE = """
  .tabs { display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 1px solid var(--mx-border); }
  .tab-button {
    padding: 10px 18px; border: none; background: transparent; font-family: inherit; font-size: 0.9rem;
    font-weight: 600; color: var(--mx-text-gray-600); cursor: pointer; border-bottom: 2px solid transparent;
    margin-bottom: -1px;
  }
  .tab-button:hover { color: var(--mx-text-dark); }
  .tab-button.active { color: var(--mx-primary); border-bottom-color: var(--mx-primary); }
  .tab-panel[hidden] { display: none; }

  .reports-row { display: flex; gap: 10px; margin-bottom: 20px; }
  .card-header-actions { margin-left: auto; }
  .card-header { display: flex; align-items: center; }
  .empty-state { color: var(--mx-text-gray-600); font-size: 0.9rem; padding: 40px 0; text-align: center; }
  .muted { color: var(--mx-text-gray-600); font-size: 0.85rem; }
  .pill-tag {
    display: inline-flex; align-items: center; padding: 4px 10px; border-radius: 999px;
    font-weight: 600; font-size: 0.75rem; color: var(--pill-color);
    background-color: color-mix(in srgb, var(--pill-color) 15%, transparent); white-space: nowrap;
  }
  .find-controls { display: flex; gap: 12px; padding: 16px 22px; border-bottom: 1px solid var(--mx-border); }
  #kw-search-input { flex: 1; min-width: 260px; }

  .batch-list { display: flex; flex-direction: column; gap: 10px; }
  .batch-row {
    background: var(--mx-card-bg); border: 1px solid var(--mx-border); border-radius: 10px;
    padding: 16px 20px; display: flex; align-items: center; justify-content: space-between;
    gap: 16px; cursor: pointer;
  }
  .batch-row:hover { border-color: var(--mx-primary); }
  .batch-row-main { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .batch-label { font-weight: 700; font-size: 0.98rem; }
  .batch-meta { color: var(--mx-text-gray-600); font-size: 0.83rem; }
  .batch-row-right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }

  dialog.batch-modal[open] {
    position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); margin: 0;
    width: min(760px, 92vw); max-height: 84vh; padding: 0; border: none; border-radius: 14px;
    background: var(--mx-card-bg); color: var(--mx-text-dark); display: flex; flex-direction: column;
  }
  dialog.batch-modal::backdrop { background: rgba(15, 15, 20, 0.55); }
  body:has(dialog.batch-modal[open]) { overflow: hidden; }
  .batch-modal-header {
    display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
    padding: 20px 24px; border-bottom: 1px solid var(--mx-border); flex-shrink: 0;
  }
  .batch-modal-title { font-size: 1.05rem; font-weight: 700; }
  .batch-modal-meta { color: var(--mx-text-gray-600); font-size: 0.85rem; margin-top: 4px; }
  .batch-modal-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
  .btn-icon-close {
    width: 34px; height: 34px; border-radius: 8px; border: 1px solid var(--mx-border); background: transparent;
    color: var(--mx-text-gray-600); cursor: pointer; display: flex; align-items: center; justify-content: center;
    font-family: inherit; font-size: 1rem; line-height: 1;
  }
  .btn-icon-close:hover { background: var(--mx-body-bg); }
  .batch-modal-body { padding: 20px 24px 24px; overflow-y: auto; flex: 1 1 auto; min-height: 0; }
  .batch-modal-body .card { margin-bottom: 16px; }
  .batch-modal-body .card:last-child { margin-bottom: 0; }
"""

_KEYWORD_RESEARCH_SCRIPT = """
document.querySelectorAll(".tab-button").forEach(function (button) {
  button.addEventListener("click", function () {
    document.querySelectorAll(".tab-button").forEach(function (b) { b.classList.remove("active"); });
    document.querySelectorAll(".tab-panel").forEach(function (p) { p.hidden = true; });
    button.classList.add("active");
    document.getElementById("tab-panel-" + button.dataset.tab).hidden = false;
  });
});
document.querySelectorAll(".batch-row").forEach(function (row) {
  row.addEventListener("click", function (event) {
    if (event.target.closest("[data-no-row-click]")) { return; }
    var modal = document.getElementById(row.getAttribute("data-modal-target"));
    if (modal) { modal.showModal(); }
  });
});
document.querySelectorAll(".batch-modal-close").forEach(function (button) {
  button.addEventListener("click", function () {
    button.closest("dialog").close();
  });
});

(function () {
  var rowsPerPage = __ROWS_PER_PAGE__;
  var currentPage = 1;
  var currentSearch = "";
  var allRows = Array.from(document.querySelectorAll("#kw-table tbody tr"));
  var prevButton = document.getElementById("kw-prev-page");
  if (!prevButton) { return; }

  function getFilteredRows() {
    return allRows.filter(function (row) {
      return currentSearch === "" || row.getAttribute("data-search").indexOf(currentSearch) !== -1;
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

    document.getElementById("kw-page-indicator").textContent =
      "Page " + currentPage + " of " + totalPages + " (" + filteredRows.length + " keywords)";
    prevButton.disabled = currentPage <= 1;
    document.getElementById("kw-next-page").disabled = currentPage >= totalPages;
  }

  document.getElementById("kw-search-input").addEventListener("input", function (event) {
    currentSearch = event.target.value.trim().toLowerCase();
    currentPage = 1;
    render();
  });
  prevButton.addEventListener("click", function () {
    if (currentPage > 1) { currentPage -= 1; render(); }
  });
  document.getElementById("kw-next-page").addEventListener("click", function () {
    currentPage += 1; render();
  });

  render();
})();

document.querySelectorAll("table[data-paginate]").forEach(function (table) {
  var pagId = table.getAttribute("data-paginate");
  var rowsPerPage = parseInt(table.getAttribute("data-rows-per-page"), 10) || 25;
  var rows = Array.from(table.querySelectorAll("tbody tr"));
  var prevButton = document.getElementById("pg-prev-" + pagId);
  var nextButton = document.getElementById("pg-next-" + pagId);
  var indicator = document.getElementById("pg-indicator-" + pagId);
  if (!prevButton || !nextButton || !indicator) { return; }
  var currentPage = 1;

  function render() {
    var totalPages = Math.max(1, Math.ceil(rows.length / rowsPerPage));
    if (currentPage > totalPages) { currentPage = totalPages; }
    var startIndex = (currentPage - 1) * rowsPerPage;
    rows.forEach(function (row, index) {
      row.style.display = (index >= startIndex && index < startIndex + rowsPerPage) ? "" : "none";
    });
    indicator.textContent = "Page " + currentPage + " of " + totalPages + " (" + rows.length + " keywords)";
    prevButton.disabled = currentPage <= 1;
    nextButton.disabled = currentPage >= totalPages;
  }

  prevButton.addEventListener("click", function () {
    if (currentPage > 1) { currentPage -= 1; render(); }
  });
  nextButton.addEventListener("click", function () {
    currentPage += 1; render();
  });

  render();
});
"""


def _batch_xlsx_filename(batch_id):
    return f"batch-{batch_id:04d}-keywords.xlsx"


def _batch_pdf_filename(batch_id):
    return f"batch-{batch_id:04d}-insights.pdf"


def _format_created_at(iso_timestamp):
    return datetime.fromisoformat(iso_timestamp).strftime("%b %d, %Y, %I:%M %p UTC")


def _format_number(value):
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value:,}" if isinstance(value, int) else f"{value:,.1f}"


def _format_percent(value):
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


# --- KPI tiles ---

def _render_kpi_tiles(analytics):
    trending_count = len(analytics["trending_keywords"]["rising"]) + len(analytics["trending_keywords"]["declining"])
    tiles = [
        ("Unique Keywords", analytics["total_keywords"], MX_PRIMARY_COLOR, ICON_KEYWORDS),
        ("Competitors Tracked", analytics["total_competitors"], MX_SEVERITY["info"]["color"], ICON_TOTAL),
        ("Opportunity Keywords", len(analytics["opportunity_keywords"]), MX_RESOLVED_COLOR, ICON_RESOLVED),
        ("Trending Keywords", trending_count, MX_SEVERITY["warning"]["color"], ICON_NEW),
    ]
    cards = [
        f"""
        <div class="kpi-card">
          <div class="kpi-icon" style="--kpi-color: {color}">{icon}</div>
          <div>
            <div class="kpi-value">{_format_number(value)}</div>
            <div class="kpi-label">{html.escape(label)}</div>
          </div>
        </div>
        """
        for label, value, color, icon in tiles
    ]
    return f'<section class="kpi-row">{"".join(cards)}</section>'


# --- Analytics cards (shared between the live master tab and the per-batch modal) ---

def _render_overlap_card(overlap):
    if not overlap["most_contested"]:
        body = '<div class="empty-state">No keyword is shared by more than one competitor yet.</div>'
    else:
        rows = "".join(
            f"""<tr>
              <td>{html.escape(k["keyword"])}</td>
              <td>{k["competitor_count"]}</td>
              <td>{html.escape(", ".join(k["competitors"]))}</td>
            </tr>"""
            for k in overlap["most_contested"]
        )
        body = f"""
        <div class="table-wrap">
          <table>
            <thead><tr><th>Keyword</th><th>Shared by</th><th>Competitors</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
        <div class="muted" style="padding: 10px 22px;">{overlap['unique_to_one_competitor_count']} keyword(s) are unique to a single competitor -- potential content gaps for everyone else.</div>
        """
    return f"""
    <div class="card">
      <div class="card-header"><div class="card-header-title">Competitor Overlap -- Most Contested Keywords</div></div>
      {body}
    </div>
    """


def _render_opportunity_card(opportunities, card_id):
    if not opportunities:
        body = '<div class="empty-state">No keywords currently meet the high-volume, low-difficulty cutoff.</div>'
    else:
        pag_id = f"opp-{card_id}"
        rows = "".join(
            f"""<tr>
              <td>{html.escape(k["keyword"])}</td>
              <td>{_format_number(k["avg_monthly_search_volume"])}</td>
              <td>{_format_number(k["difficulty"])}</td>
              <td>{html.escape(", ".join(k["competitors"]))}</td>
            </tr>"""
            for k in opportunities
        )
        body = f"""
        <div class="table-wrap">
          <table data-paginate="{pag_id}" data-rows-per-page="{_TABLE_ROWS_PER_PAGE}">
            <thead><tr><th>Keyword</th><th>Volume</th><th>Difficulty</th><th>Competitors</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
        <div class="pagination-bar">
          <button id="pg-prev-{pag_id}" class="btn btn-light">&larr; Prev</button>
          <span id="pg-indicator-{pag_id}"></span>
          <button id="pg-next-{pag_id}" class="btn btn-light">Next &rarr;</button>
        </div>
        """
    return f"""
    <div class="card">
      <div class="card-header"><div class="card-header-title">Opportunity Keywords (high volume, low difficulty)</div></div>
      {body}
    </div>
    """


def _render_trending_card(trending):
    def _rows(items):
        if not items:
            return '<tr><td colspan="4" class="muted">None</td></tr>'
        return "".join(
            f"""<tr>
              <td>{html.escape(k["keyword"])}</td>
              <td>{_format_percent(k["yoy_change"])}</td>
              <td>{_format_number(k["avg_monthly_search_volume"])}</td>
              <td>{html.escape(", ".join(k["competitors"]))}</td>
            </tr>"""
            for k in items
        )

    return f"""
    <div class="card">
      <div class="card-header"><div class="card-header-title">Trending Keywords (year-over-year)</div></div>
      <div class="card-body">
        <div style="font-weight:600; margin-bottom:8px;">Rising</div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Keyword</th><th>YoY Change</th><th>Volume</th><th>Competitors</th></tr></thead>
            <tbody>{_rows(trending["rising"])}</tbody>
          </table>
        </div>
        <div style="font-weight:600; margin: 18px 0 8px;">Declining</div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Keyword</th><th>YoY Change</th><th>Volume</th><th>Competitors</th></tr></thead>
            <tbody>{_rows(trending["declining"])}</tbody>
          </table>
        </div>
      </div>
    </div>
    """


def _render_per_competitor_card(summary):
    if not summary:
        body = '<div class="empty-state">No competitor data yet.</div>'
    else:
        rows = "".join(
            f"""<tr>
              <td>{html.escape(s["competitor"])}</td>
              <td>{s["keyword_count"]}</td>
              <td>{s["unique_keyword_count"]}</td>
              <td>{_format_number(s["avg_volume"])}</td>
              <td>{_format_number(s["avg_difficulty"])}</td>
            </tr>"""
            for s in summary
        )
        body = f"""
        <div class="table-wrap">
          <table>
            <thead><tr><th>Competitor</th><th>Keywords</th><th>Unique to Them</th><th>Avg Volume</th><th>Avg Difficulty</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
        """
    return f"""
    <div class="card">
      <div class="card-header"><div class="card-header-title">Per-Competitor Summary</div></div>
      {body}
    </div>
    """


def _render_analytics_cards(analytics, card_id):
    return (
        _render_overlap_card(analytics["competitor_overlap"])
        + _render_opportunity_card(analytics["opportunity_keywords"], card_id)
        + _render_trending_card(analytics["trending_keywords"])
        + _render_per_competitor_card(analytics["per_competitor_summary"])
    )


# --- Full keyword table (master tab only -- searchable + paginated) ---

def _render_keyword_table_row(keyword):
    search_blob = html.escape(
        (keyword["keyword"] + " " + ", ".join(keyword["competitors"])).lower()
    )
    return f"""
    <tr data-search="{search_blob}">
      <td>{html.escape(keyword["keyword"])}</td>
      <td>{_format_number(keyword["avg_monthly_search_volume"])}</td>
      <td>{_format_number(keyword["difficulty"])}</td>
      <td>{_format_percent(keyword["yoy_change"])}</td>
      <td>{html.escape(", ".join(keyword["competitors"]))}</td>
    </tr>
    """


def _render_keyword_table_card(keywords):
    if not keywords:
        body = '<div class="empty-state">No keywords in the master list yet -- run /keyword-research with at least one batch marked "include in master."</div>'
    else:
        rows = "".join(_render_keyword_table_row(k) for k in keywords)
        body = f"""
        <div class="find-controls">
          <input type="search" id="kw-search-input" placeholder="Search keyword or competitor...">
        </div>
        <div class="table-wrap">
          <table id="kw-table">
            <thead><tr><th>Keyword</th><th>Volume</th><th>Difficulty</th><th>YoY Change</th><th>Competitors</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
        <div class="pagination-bar">
          <button id="kw-prev-page" class="btn btn-light">&larr; Prev</button>
          <span id="kw-page-indicator"></span>
          <button id="kw-next-page" class="btn btn-light">Next &rarr;</button>
        </div>
        """
    return f"""
    <div class="card">
      <div class="card-header">
        <div class="card-header-title">Full Master Keyword List</div>
        <div class="card-header-actions">
          <a class="btn btn-light" href="keyword_research_exports/{MASTER_XLSX_FILENAME}">{ICON_DOWNLOAD}<span>Download Excel</span></a>
        </div>
      </div>
      {body}
    </div>
    """


# --- Batch History tab ---

def _render_batch_row(batch, unique_keyword_count):
    modal_id = f"batch-modal-{batch['batch_id']}"
    label = batch["label"] or f"Batch #{batch['batch_id']}"
    meta = " &middot; ".join([
        f"{batch['sheet_count']} sheet(s)",
        f"{batch['competitor_count']} competitor(s)",
        f"{unique_keyword_count} unique keyword(s)",
        html.escape(_format_created_at(batch["created_at"])),
    ])
    master_color = MX_RESOLVED_COLOR if batch["include_in_master"] else MX_SEVERITY["info"]["color"]
    master_label = "In Master List" if batch["include_in_master"] else "Standalone"
    return f"""
    <div class="batch-row" data-modal-target="{modal_id}">
      <div class="batch-row-main">
        <div class="batch-label">{html.escape(label)}</div>
        <div class="batch-meta">{meta}</div>
      </div>
      <div class="batch-row-right">
        <span class="pill-tag" style="--pill-color: {master_color}">{master_label}</span>
        <a class="btn btn-light" data-no-row-click href="keyword_research_exports/{_batch_xlsx_filename(batch['batch_id'])}">{ICON_DOWNLOAD}<span>Excel</span></a>
        <a class="btn btn-light" data-no-row-click href="keyword_research_exports/{_batch_pdf_filename(batch['batch_id'])}">{ICON_DOWNLOAD}<span>PDF</span></a>
      </div>
    </div>
    """


def _render_batch_modal(batch, batch_analytics):
    modal_id = f"batch-modal-{batch['batch_id']}"
    label = batch["label"] or f"Batch #{batch['batch_id']}"
    meta = html.escape(_format_created_at(batch["created_at"]))
    return f"""
    <dialog class="batch-modal" id="{modal_id}">
      <div class="batch-modal-header">
        <div>
          <div class="batch-modal-title">{html.escape(label)}</div>
          <div class="batch-modal-meta">{meta}</div>
        </div>
        <div class="batch-modal-actions">
          <a class="btn btn-light" href="keyword_research_exports/{_batch_xlsx_filename(batch['batch_id'])}">{ICON_DOWNLOAD}<span>Excel</span></a>
          <a class="btn btn-light" href="keyword_research_exports/{_batch_pdf_filename(batch['batch_id'])}">{ICON_DOWNLOAD}<span>PDF</span></a>
          <button class="btn-icon-close batch-modal-close" type="button" aria-label="Close">&#10005;</button>
        </div>
      </div>
      <div class="batch-modal-body">
        {_render_kpi_tiles(batch_analytics)}
        {_render_analytics_cards(batch_analytics, f"batch-{batch['batch_id']}")}
      </div>
    </dialog>
    """


def generate_keyword_research_page_html(master_keywords, master_analytics, batches, batch_analytics_by_id):
    subtitle_html = f"{master_analytics['total_keywords']} unique keyword(s) &middot; {len(batches)} batch(es) recorded"

    insights_body = (
        _render_kpi_tiles(master_analytics)
        + f'<div class="reports-row"><a class="btn btn-light" href="keyword_research_exports/{MASTER_PDF_FILENAME}">{ICON_DOWNLOAD}<span>Download Master Insights PDF</span></a></div>'
        + _render_analytics_cards(master_analytics, "master")
        + _render_keyword_table_card(master_keywords)
    )

    if not batches:
        history_body = '<div class="empty-state">No batches recorded yet -- run /keyword-research to import your first set of competitor sheets.</div>'
    else:
        batch_rows = "".join(
            _render_batch_row(b, batch_analytics_by_id[b["batch_id"]]["total_keywords"])
            for b in batches
        )
        batch_modals = "".join(
            _render_batch_modal(b, batch_analytics_by_id[b["batch_id"]])
            for b in batches
        )
        history_body = f'<div class="batch-list">{batch_rows}</div>{batch_modals}'

    return f"""<!doctype html>
<html lang="en">
<head>
{_shared_head("Keyword Research")}
<style>{_KEYWORD_RESEARCH_STYLE}</style>
</head>
<body>
<div class="app">
  {_render_sidebar_nav("keyword-research")}
  <div class="main">
    {_render_topbar("Keyword Research", subtitle_html)}
    <main class="content">
      <div class="tabs">
        <button class="tab-button active" data-tab="insights">Insights</button>
        <button class="tab-button" data-tab="history">Batch History</button>
      </div>
      <div class="tab-panel" id="tab-panel-insights">{insights_body}</div>
      <div class="tab-panel" id="tab-panel-history" hidden>{history_body}</div>
    </main>
  </div>
</div>
<script>{_KEYWORD_RESEARCH_SCRIPT.replace("__ROWS_PER_PAGE__", str(_TABLE_ROWS_PER_PAGE))}</script>
</body>
</html>
"""


# --- Excel export (openpyxl, self-contained -- no server/account needed) ---

def _write_keywords_excel(keywords, xlsx_path):
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Keywords"
    header = ["Keyword", "Avg Monthly Search Volume", "Difficulty", "YoY Change (%)", "Competitors"]
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for keyword in keywords:
        sheet.append([
            keyword["keyword"],
            keyword["avg_monthly_search_volume"],
            keyword["difficulty"],
            keyword["yoy_change"],
            ", ".join(keyword["competitors"]),
        ])
    sheet.freeze_panes = "A2"
    sheet.column_dimensions["A"].width = 40
    sheet.column_dimensions["E"].width = 50
    workbook.save(xlsx_path)
    return xlsx_path


# --- PDF insights report (plain HTML/CSS via Playwright, same
# self-contained philosophy as every other PDF in this project) ---

_PRINT_STYLE = """
  * { box-sizing: border-box; }
  body { margin: 0; background: #ffffff; color: #0b0b0b; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; padding: 24px; }
  h1 { font-size: 1.3rem; margin-bottom: 4px; }
  h2 { font-size: 1rem; margin: 26px 0 8px; }
  header p { color: #52514e; margin-top: 0; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
  th, td { text-align: left; padding: 7px 10px; font-size: 0.8rem; vertical-align: top; border: 1px solid #cfcec8; }
  th { color: #52514e; font-weight: 600; font-size: 0.7rem; text-transform: uppercase; background: #f6f5f1; }
"""


def _print_rows(items, columns):
    return "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(col(item)))}</td>" for col in columns) + "</tr>"
        for item in items
    ) or f'<tr><td colspan="{len(columns)}">None</td></tr>'


def _generate_insights_print_html(title, subtitle, analytics):
    overlap_rows = _print_rows(
        analytics["competitor_overlap"]["most_contested"],
        [lambda k: k["keyword"], lambda k: k["competitor_count"], lambda k: ", ".join(k["competitors"])],
    )
    opportunity_rows = _print_rows(
        analytics["opportunity_keywords"],
        [lambda k: k["keyword"], lambda k: _format_number(k["avg_monthly_search_volume"]),
         lambda k: _format_number(k["difficulty"]), lambda k: ", ".join(k["competitors"])],
    )
    rising_rows = _print_rows(
        analytics["trending_keywords"]["rising"],
        [lambda k: k["keyword"], lambda k: _format_percent(k["yoy_change"]),
         lambda k: _format_number(k["avg_monthly_search_volume"])],
    )
    declining_rows = _print_rows(
        analytics["trending_keywords"]["declining"],
        [lambda k: k["keyword"], lambda k: _format_percent(k["yoy_change"]),
         lambda k: _format_number(k["avg_monthly_search_volume"])],
    )
    competitor_rows = _print_rows(
        analytics["per_competitor_summary"],
        [lambda s: s["competitor"], lambda s: s["keyword_count"], lambda s: s["unique_keyword_count"],
         lambda s: _format_number(s["avg_volume"]), lambda s: _format_number(s["avg_difficulty"])],
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>{_PRINT_STYLE}</style>
</head>
<body>
  <header>
    <h1>{html.escape(title)}</h1>
    <p>{html.escape(subtitle)} &middot; {analytics['total_keywords']} unique keyword(s) across {analytics['total_competitors']} competitor(s)</p>
  </header>

  <h2>Competitor Overlap -- Most Contested Keywords</h2>
  <table>
    <thead><tr><th>Keyword</th><th>Shared by</th><th>Competitors</th></tr></thead>
    <tbody>{overlap_rows}</tbody>
  </table>
  <p>{analytics['competitor_overlap']['unique_to_one_competitor_count']} keyword(s) are unique to a single competitor.</p>

  <h2>Opportunity Keywords (high volume, low difficulty)</h2>
  <table>
    <thead><tr><th>Keyword</th><th>Volume</th><th>Difficulty</th><th>Competitors</th></tr></thead>
    <tbody>{opportunity_rows}</tbody>
  </table>

  <h2>Trending Keywords -- Rising</h2>
  <table>
    <thead><tr><th>Keyword</th><th>YoY Change</th><th>Volume</th></tr></thead>
    <tbody>{rising_rows}</tbody>
  </table>

  <h2>Trending Keywords -- Declining</h2>
  <table>
    <thead><tr><th>Keyword</th><th>YoY Change</th><th>Volume</th></tr></thead>
    <tbody>{declining_rows}</tbody>
  </table>

  <h2>Per-Competitor Summary</h2>
  <table>
    <thead><tr><th>Competitor</th><th>Keywords</th><th>Unique to Them</th><th>Avg Volume</th><th>Avg Difficulty</th></tr></thead>
    <tbody>{competitor_rows}</tbody>
  </table>
</body>
</html>
"""


def _render_pdf(print_html, pdf_path):
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(print_html)
        page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin={"top": "20px", "bottom": "20px", "left": "20px", "right": "20px"},
        )
        browser.close()
    return pdf_path


def build_and_save_keyword_research_page():
    connection = get_connection()
    try:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        batches = load_all_batches(connection)
        master_keywords = load_master_keywords(connection)
        master_analytics = run_all_analytics(master_keywords)

        _write_keywords_excel(master_keywords, EXPORTS_DIR_PATH / MASTER_XLSX_FILENAME)
        _render_pdf(
            _generate_insights_print_html("Master Keyword Insights", "Cumulative across every included batch", master_analytics),
            EXPORTS_DIR_PATH / MASTER_PDF_FILENAME,
        )

        batch_analytics_by_id = {}
        for batch in batches:
            batch_keywords = load_keywords_for_batch(connection, batch["batch_id"])
            batch_analytics = run_all_analytics(batch_keywords)
            batch_analytics_by_id[batch["batch_id"]] = batch_analytics

            _write_keywords_excel(batch_keywords, EXPORTS_DIR_PATH / _batch_xlsx_filename(batch["batch_id"]))
            label = batch["label"] or f"Batch #{batch['batch_id']}"
            _render_pdf(
                _generate_insights_print_html(f"Keyword Insights -- {label}", _format_created_at(batch["created_at"]), batch_analytics),
                EXPORTS_DIR_PATH / _batch_pdf_filename(batch["batch_id"]),
            )

        page_html = generate_keyword_research_page_html(master_keywords, master_analytics, batches, batch_analytics_by_id)
        with open(KEYWORD_RESEARCH_FILE_PATH, "w", encoding="utf-8") as page_file:
            page_file.write(page_html)

        return KEYWORD_RESEARCH_FILE_PATH
    finally:
        connection.close()


if __name__ == "__main__":
    saved_path = build_and_save_keyword_research_page()
    print(f"Keyword Research page built: {saved_path}")
