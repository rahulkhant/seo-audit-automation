"""
Activity Agent: dashboard page.

Purpose of this file
--------------------
Builds docs/activity.html -- Rahul's day-to-day work log turned into an
"Activity & Performance" view, using the same Metronic shell (sidebar,
topbar, card styling) as every other dashboard page, so this reads as
part of the same system rather than a bolted-on tracker.

"Performance" here means two things, both computed fresh from
activity_agent.database every build, never stored redundantly:
  - Activity volume/consistency: tasks completed this week, days logged
    this month.
  - Progress against what's still open: the Open Tasks card shows every
    task not yet completed, alongside its target/goal note (if one was
    given), so it's visible at a glance whether something is on track or
    has been sitting blocked for a while -- not just a count of "things
    happened."

This file does not decide what happened each day or judge progress --
that's the /log-activity skill's job (matching bullets to tasks,
deciding day_status). This only reads what was already saved and turns
it into something readable, same division of labor as Agent 4 for the
audit pipeline and build_content_page.py for the Content Agent.

Generates:
  - docs/activity.html (KPI tiles, category chart, Open Tasks card,
    chronological day-by-day list with a modal per day)
  - docs/activity_reports/daily-YYYY-MM-DD.pdf -- one per logged day
  - docs/activity_reports/weekly-latest.pdf -- always the CURRENT
    Mon-Sun week at build time, overwritten every run (same "always the
    latest snapshot" pattern as reporting-hub-latest.pdf, not a per-week
    permanent archive -- revisit only if Rahul actually wants history here)
  - docs/activity_reports/monthly-latest.pdf -- same idea, current
    calendar month
"""

import html
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

from activity_agent.database import get_connection, load_all_logs_with_entries, load_open_tasks
from agent4_dashboard.build_dashboard_metronic import (
    ICON_DOWNLOAD,
    ICON_HISTORY,
    ICON_NEW,
    ICON_RESOLVED,
    ICON_TOTAL,
    ICON_WARNING,
    MX_PRIMARY_COLOR,
    MX_RESOLVED_COLOR,
    MX_SEVERITY,
    _render_sidebar_nav,
    _render_topbar,
    _shared_head,
)

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
ACTIVITY_FILE_PATH = DOCS_DIR / "activity.html"
REPORTS_DIR_PATH = DOCS_DIR / "activity_reports"
WEEKLY_PDF_FILENAME = "weekly-latest.pdf"
MONTHLY_PDF_FILENAME = "monthly-latest.pdf"

_BLOCKED_COLOR = MX_SEVERITY["critical"]["color"]
_NOT_STARTED_COLOR = "#8a8a8a"
_STATUS_LABEL = {
    "not_started": "Not Started", "in_progress": "In Progress",
    "completed": "Completed", "blocked": "Blocked",
}
_STATUS_COLOR = {
    "not_started": _NOT_STARTED_COLOR, "in_progress": MX_PRIMARY_COLOR,
    "completed": MX_RESOLVED_COLOR, "blocked": _BLOCKED_COLOR,
}

_ACTIVITY_PAGE_STYLE = """
  /* 5 KPI tiles here, not the shared 4-column grid built for the audit
     dashboard's Critical/Warning/Info set -- auto-fit instead of a fixed
     column count so this still collapses gracefully on narrow screens
     without duplicating the shared style's breakpoint values. */
  .kpi-row { grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
  .reports-row { display: flex; gap: 10px; margin-bottom: 20px; }
  .task-list { display: flex; flex-direction: column; gap: 10px; }
  .task-row {
    background: var(--mx-card-bg); border: 1px solid var(--mx-border); border-radius: 10px;
    padding: 14px 20px; display: flex; align-items: center; justify-content: space-between; gap: 16px;
  }
  .task-row-main { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .task-desc { font-weight: 700; font-size: 0.94rem; }
  .task-meta { color: var(--mx-text-gray-600); font-size: 0.82rem; }
  .task-target { color: var(--mx-primary); font-size: 0.82rem; margin-top: 2px; }
  .status-pill {
    display: inline-flex; align-items: center; padding: 5px 12px; border-radius: 999px;
    font-weight: 600; font-size: 0.78rem; color: var(--pill-color);
    background-color: color-mix(in srgb, var(--pill-color) 15%, transparent); white-space: nowrap; flex-shrink: 0;
  }
  .empty-state { color: var(--mx-text-gray-600); font-size: 0.9rem; padding: 40px 0; text-align: center; }

  .log-list { display: flex; flex-direction: column; gap: 10px; }
  .log-row {
    background: var(--mx-card-bg); border: 1px solid var(--mx-border); border-radius: 10px;
    padding: 16px 20px; display: flex; align-items: center; justify-content: space-between;
    gap: 16px; cursor: pointer;
  }
  .log-row:hover { border-color: var(--mx-primary); }
  .log-row-main { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .log-date { font-weight: 700; font-size: 0.98rem; }
  .log-meta { color: var(--mx-text-gray-600); font-size: 0.83rem; }
  .log-row-right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
  .log-counts { display: flex; gap: 6px; }

  dialog.log-modal[open] {
    position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); margin: 0;
    width: min(680px, 92vw); max-height: 82vh; padding: 0; border: none; border-radius: 14px;
    background: var(--mx-card-bg); color: var(--mx-text-dark); display: flex; flex-direction: column;
  }
  dialog.log-modal::backdrop { background: rgba(15, 15, 20, 0.55); }
  body:has(dialog.log-modal[open]) { overflow: hidden; }
  .log-modal-header {
    display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
    padding: 20px 24px; border-bottom: 1px solid var(--mx-border); flex-shrink: 0;
  }
  .log-modal-title { font-size: 1.05rem; font-weight: 700; }
  .log-modal-meta { color: var(--mx-text-gray-600); font-size: 0.85rem; margin-top: 4px; }
  .log-modal-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
  .btn-icon-close {
    width: 34px; height: 34px; border-radius: 8px; border: 1px solid var(--mx-border); background: transparent;
    color: var(--mx-text-gray-600); cursor: pointer; display: flex; align-items: center; justify-content: center;
    font-family: inherit; font-size: 1rem; line-height: 1;
  }
  .btn-icon-close:hover { background: var(--mx-body-bg); }
  .log-modal-body { padding: 20px 24px 24px; overflow-y: auto; flex: 1 1 auto; min-height: 0; }
  .log-entry-item { border: 1px solid var(--mx-border); border-radius: 8px; padding: 12px 16px; margin-bottom: 10px; }
  .log-entry-header { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
  .log-entry-desc { font-weight: 600; }
  .log-entry-category { color: var(--mx-text-gray-500); font-size: 0.72rem; text-transform: uppercase; font-weight: 700; }
  .log-entry-note { font-size: 0.87rem; margin-top: 6px; }
  .log-entry-target { color: var(--mx-primary); font-size: 0.82rem; margin-top: 6px; }
"""

_ACTIVITY_PAGE_SCRIPT = """
document.querySelectorAll(".log-row").forEach(function (row) {
  row.addEventListener("click", function (event) {
    if (event.target.closest("[data-no-row-click]")) { return; }
    var modal = document.getElementById(row.getAttribute("data-modal-target"));
    if (modal) { modal.showModal(); }
  });
});
document.querySelectorAll(".log-modal-close").forEach(function (button) {
  button.addEventListener("click", function () {
    button.closest("dialog").close();
  });
});
"""


# --- Date range helpers -- current week/month at build time, not tied to
# any particular logged date, so "This Week"/"This Month" always means
# what a reader would expect when they look at the live page. ---

def _week_range(today):
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _month_range(today):
    first = today.replace(day=1)
    next_month = first.replace(year=first.year + 1, month=1) if first.month == 12 else first.replace(month=first.month + 1)
    last = next_month - timedelta(days=1)
    return first, last


def _format_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %d, %Y")


def _format_created_at(iso_timestamp):
    return datetime.fromisoformat(iso_timestamp).strftime("%b %d, %Y, %I:%M %p UTC")


# --- Data shaping ---

def _compute_kpis(open_tasks, logs, today):
    week_start, week_end = _week_range(today)
    month_start, month_end = _month_range(today)

    completed_this_week = 0
    for log in logs:
        log_date = datetime.strptime(log["log_date"], "%Y-%m-%d").date()
        if not (week_start <= log_date <= week_end):
            continue
        for entry in log["entries"]:
            if entry["day_status"] == "completed":
                completed_this_week += 1

    not_started_count = sum(1 for t in open_tasks if t["status"] == "not_started")
    in_progress_count = sum(1 for t in open_tasks if t["status"] == "in_progress")
    blocked_count = sum(1 for t in open_tasks if t["status"] == "blocked")

    days_logged_this_month = sum(
        1 for log in logs
        if month_start <= datetime.strptime(log["log_date"], "%Y-%m-%d").date() <= month_end
    )

    return {
        "completed_this_week": completed_this_week,
        "not_started": not_started_count,
        "in_progress": in_progress_count,
        "blocked": blocked_count,
        "days_logged_this_month": days_logged_this_month,
    }


def _category_breakdown(logs, start_date, end_date):
    counts = {}
    for log in logs:
        log_date = datetime.strptime(log["log_date"], "%Y-%m-%d").date()
        if not (start_date <= log_date <= end_date):
            continue
        for entry in log["entries"]:
            category = entry.get("category") or "Uncategorized"
            counts[category] = counts.get(category, 0) + 1
    return counts


def _logs_in_range(logs, start_date, end_date):
    return [
        log for log in logs
        if start_date <= datetime.strptime(log["log_date"], "%Y-%m-%d").date() <= end_date
    ]


# --- Live page: KPI tiles ---

def _render_kpi_tiles(kpis):
    tiles = [
        ("Completed This Week", kpis["completed_this_week"], MX_RESOLVED_COLOR, ICON_RESOLVED),
        ("In Progress", kpis["in_progress"], MX_PRIMARY_COLOR, ICON_TOTAL),
        ("Not Started", kpis["not_started"], _NOT_STARTED_COLOR, ICON_NEW),
        ("Blocked", kpis["blocked"], _BLOCKED_COLOR, ICON_WARNING),
        ("Days Logged This Month", kpis["days_logged_this_month"], MX_SEVERITY["info"]["color"], ICON_HISTORY),
    ]
    cards = [
        f"""
        <div class="kpi-card">
          <div class="kpi-icon" style="--kpi-color: {color}">{icon}</div>
          <div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-label">{html.escape(label)}</div>
          </div>
        </div>
        """
        for label, value, color, icon in tiles
    ]
    return f'<section class="kpi-row">{"".join(cards)}</section>'


# --- Live page: category donut (ApexCharts, same CDN as the other pages) ---

_CATEGORY_CHART_SCRIPT_TEMPLATE = """
var categoryChartEl = document.querySelector("#categoryChart");
if (categoryChartEl && window.ApexCharts) {
  var categoryChart = new ApexCharts(categoryChartEl, {
    chart: { type: "donut", height: 300, fontFamily: "Inter, sans-serif" },
    series: __SERIES__,
    labels: __LABELS__,
    legend: { position: "bottom" },
    dataLabels: { enabled: false }
  });
  categoryChart.render();
}
"""


def _render_category_chart_script(category_counts):
    if not category_counts:
        return ""
    script = _CATEGORY_CHART_SCRIPT_TEMPLATE
    script = script.replace("__SERIES__", json.dumps(list(category_counts.values())))
    script = script.replace("__LABELS__", json.dumps(list(category_counts.keys())))
    return script


def _render_category_chart_card(category_counts):
    body = '<div id="categoryChart"></div>' if category_counts else '<div class="chart-empty">No activity logged this month yet.</div>'
    return f"""
    <div class="card chart-card">
      <div class="card-header"><div class="card-header-title">Work Distribution This Month</div></div>
      <div class="card-body">{body}</div>
    </div>
    """


# --- Live page: Open Tasks ---

def _render_open_task_row(task):
    color = _STATUS_COLOR.get(task["status"], MX_PRIMARY_COLOR)
    meta = " &middot; ".join(filter(None, [
        html.escape(task["category"]) if task.get("category") else None,
        f"Priority: {html.escape(task['priority'])}" if task.get("priority") else None,
        f"started {_format_date(task['first_logged_date'])}",
        f"last update {_format_date(task['last_updated_date'])}",
    ]))
    target_html = (
        f'<div class="task-target">Target: {html.escape(task["target_notes"])}</div>'
        if task.get("target_notes")
        else ""
    )
    return f"""
    <div class="task-row">
      <div class="task-row-main">
        <div class="task-desc">{html.escape(task["description"])}</div>
        <div class="task-meta">{meta}</div>
        {target_html}
      </div>
      <span class="status-pill" style="--pill-color: {color}">{_STATUS_LABEL.get(task["status"], task["status"])}</span>
    </div>
    """


def _render_open_tasks_card(open_tasks):
    if not open_tasks:
        body = '<div class="empty-state">Nothing open right now.</div>'
    else:
        body = f'<div class="task-list">{"".join(_render_open_task_row(t) for t in open_tasks)}</div>'
    return f"""
    <div class="card">
      <div class="card-header"><div class="card-header-title">Open Tasks ({len(open_tasks)})</div></div>
      <div class="card-body">{body}</div>
    </div>
    """


# --- Live page: chronological day list + modal ---

def _daily_pdf_filename(log_date):
    return f"daily-{log_date}.pdf"


def _render_log_row(log):
    completed = sum(1 for e in log["entries"] if e["day_status"] == "completed")
    in_progress = sum(1 for e in log["entries"] if e["day_status"] == "in_progress")
    not_started = sum(1 for e in log["entries"] if e["day_status"] == "not_started")
    blocked = sum(1 for e in log["entries"] if e["day_status"] == "blocked")
    modal_id = f"log-modal-{log['log_id']}"

    counts_html = "".join(filter(None, [
        f'<span class="status-pill" style="--pill-color: {MX_RESOLVED_COLOR}">{completed} done</span>' if completed else None,
        f'<span class="status-pill" style="--pill-color: {MX_PRIMARY_COLOR}">{in_progress} in progress</span>' if in_progress else None,
        f'<span class="status-pill" style="--pill-color: {_NOT_STARTED_COLOR}">{not_started} not started</span>' if not_started else None,
        f'<span class="status-pill" style="--pill-color: {_BLOCKED_COLOR}">{blocked} blocked</span>' if blocked else None,
    ]))

    return f"""
    <div class="log-row" data-modal-target="{modal_id}">
      <div class="log-row-main">
        <div class="log-date">{_format_date(log["log_date"])}</div>
        <div class="log-meta">{html.escape(log["daily_notes"]) if log.get("daily_notes") else f"{len(log['entries'])} task(s) touched"}</div>
      </div>
      <div class="log-row-right">
        <div class="log-counts">{counts_html}</div>
        <a class="btn btn-light" data-no-row-click href="activity_reports/{_daily_pdf_filename(log['log_date'])}">{ICON_DOWNLOAD}<span>PDF</span></a>
      </div>
    </div>
    """


def _render_log_entry_item(entry):
    color = _STATUS_COLOR.get(entry["day_status"], MX_PRIMARY_COLOR)
    category_html = f'<span class="log-entry-category">{html.escape(entry["category"])}</span>' if entry.get("category") else ""
    priority_html = f'<span class="log-entry-category">Priority: {html.escape(entry["priority"])}</span>' if entry.get("priority") else ""
    target_html = (
        f'<div class="log-entry-target">Target: {html.escape(entry["target_notes"])}</div>'
        if entry.get("target_notes")
        else ""
    )
    return f"""
    <div class="log-entry-item">
      <div class="log-entry-header">
        {category_html}
        {priority_html}
        <span class="log-entry-desc">{html.escape(entry["description"])}</span>
        <span class="status-pill" style="--pill-color: {color}; margin-left: auto;">{_STATUS_LABEL.get(entry["day_status"], entry["day_status"])}</span>
      </div>
      {f'<div class="log-entry-note">{html.escape(entry["day_note"])}</div>' if entry.get("day_note") else ""}
      {target_html}
    </div>
    """


def _render_log_modal(log):
    modal_id = f"log-modal-{log['log_id']}"
    entries_html = "".join(_render_log_entry_item(e) for e in log["entries"])
    meta = f"Logged {_format_created_at(log['created_at'])}"

    return f"""
    <dialog class="log-modal" id="{modal_id}">
      <div class="log-modal-header">
        <div>
          <div class="log-modal-title">{_format_date(log["log_date"])}</div>
          <div class="log-modal-meta">{html.escape(meta)}</div>
        </div>
        <div class="log-modal-actions">
          <a class="btn btn-light" href="activity_reports/{_daily_pdf_filename(log['log_date'])}">{ICON_DOWNLOAD}<span>Download PDF</span></a>
          <button class="btn-icon-close log-modal-close" type="button" aria-label="Close">&#10005;</button>
        </div>
      </div>
      <div class="log-modal-body">
        {entries_html}
      </div>
    </dialog>
    """


def generate_activity_page_html(open_tasks, logs, today):
    kpis = _compute_kpis(open_tasks, logs, today)
    month_start, month_end = _month_range(today)
    category_counts = _category_breakdown(logs, month_start, month_end)

    subtitle_html = f"{len(logs)} day(s) logged"

    if not logs:
        log_section = '<div class="empty-state">No activity logged yet -- run the /log-activity skill at the end of the day to start tracking.</div>'
    else:
        log_rows = "".join(_render_log_row(log) for log in logs)
        log_modals = "".join(_render_log_modal(log) for log in logs)
        log_section = f'<div class="log-list">{log_rows}</div>{log_modals}'

    apex_cdn_tag = '<script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>' if category_counts else ""
    chart_script = _render_category_chart_script(category_counts)

    return f"""<!doctype html>
<html lang="en">
<head>
{_shared_head("Activity & Performance")}
<style>{_ACTIVITY_PAGE_STYLE}</style>
</head>
<body>
<div class="app">
  {_render_sidebar_nav("activity")}
  <div class="main">
    {_render_topbar("Activity & Performance", subtitle_html)}
    <main class="content">
      {_render_kpi_tiles(kpis)}
      <div class="reports-row">
        <a class="btn btn-light" href="activity_reports/{WEEKLY_PDF_FILENAME}">{ICON_DOWNLOAD}<span>This Week's PDF</span></a>
        <a class="btn btn-light" href="activity_reports/{MONTHLY_PDF_FILENAME}">{ICON_DOWNLOAD}<span>This Month's PDF</span></a>
      </div>
      {_render_category_chart_card(category_counts)}
      {_render_open_tasks_card(open_tasks)}
      <div class="card">
        <div class="card-header"><div class="card-header-title">Daily Log</div></div>
        <div class="card-body">{log_section}</div>
      </div>
    </main>
  </div>
</div>
{apex_cdn_tag}
<script>{chart_script}</script>
<script>{_ACTIVITY_PAGE_SCRIPT}</script>
</body>
</html>
"""


# --- PDFs: plain HTML/CSS, self-contained, no charts/CDN dependency
# (same philosophy as the Reporting Hub's and Content Agent's PDFs) ---

_PRINT_STYLE = """
  * { box-sizing: border-box; }
  body { margin: 0; background: #ffffff; color: #0b0b0b; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; padding: 24px; }
  h1 { font-size: 1.3rem; margin-bottom: 4px; }
  h2 { font-size: 1rem; margin: 26px 0 8px; }
  header p { color: #52514e; margin-top: 0; }
  .day-block { margin-bottom: 18px; break-inside: avoid; }
  .day-heading { font-size: 1rem; font-weight: 700; margin-bottom: 6px; }
  .day-notes { color: #52514e; font-size: 0.85rem; margin-bottom: 8px; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
  th, td { text-align: left; padding: 7px 10px; font-size: 0.83rem; vertical-align: top; border: 1px solid #cfcec8; }
  th { color: #52514e; font-weight: 600; font-size: 0.7rem; text-transform: uppercase; background: #f6f5f1; }
"""


def _entry_rows_html(entries):
    return "".join(
        f"""<tr>
          <td>{html.escape(entry.get("category") or "—")}</td>
          <td>{html.escape(entry["description"])}</td>
          <td>{html.escape(entry.get("priority") or "—")}</td>
          <td>{html.escape(_STATUS_LABEL.get(entry["day_status"], entry["day_status"]))}</td>
          <td>{html.escape(entry.get("day_note") or "—")}</td>
          <td>{html.escape(entry.get("target_notes") or "—")}</td>
        </tr>"""
        for entry in entries
    )


def _generate_daily_print_html(log):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Activity Log - {html.escape(log["log_date"])}</title>
<style>{_PRINT_STYLE}</style>
</head>
<body>
  <header>
    <h1>Activity Log &mdash; {_format_date(log["log_date"])}</h1>
    <p>{html.escape(log["daily_notes"]) if log.get("daily_notes") else f"{len(log['entries'])} task(s) touched"}</p>
  </header>
  <table>
    <thead><tr><th>Category</th><th>Task</th><th>Priority</th><th>Status</th><th>Note</th><th>Target</th></tr></thead>
    <tbody>{_entry_rows_html(log["entries"])}</tbody>
  </table>
</body>
</html>
"""


def _generate_range_print_html(title, subtitle, logs_in_range):
    if not logs_in_range:
        body_html = "<p>No activity logged in this period yet.</p>"
    else:
        blocks = []
        for log in logs_in_range:
            blocks.append(f"""
            <div class="day-block">
              <div class="day-heading">{_format_date(log["log_date"])}</div>
              {f'<div class="day-notes">{html.escape(log["daily_notes"])}</div>' if log.get("daily_notes") else ""}
              <table>
                <thead><tr><th>Category</th><th>Task</th><th>Priority</th><th>Status</th><th>Note</th><th>Target</th></tr></thead>
                <tbody>{_entry_rows_html(log["entries"])}</tbody>
              </table>
            </div>
            """)
        body_html = "".join(blocks)

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
    <p>{html.escape(subtitle)}</p>
  </header>
  {body_html}
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


def build_and_save_activity_page():
    connection = get_connection()
    try:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        today = date.today()
        open_tasks = load_open_tasks(connection)
        logs = load_all_logs_with_entries(connection)

        for log in logs:
            _render_pdf(_generate_daily_print_html(log), REPORTS_DIR_PATH / _daily_pdf_filename(log["log_date"]))

        week_start, week_end = _week_range(today)
        weekly_logs = _logs_in_range(logs, week_start, week_end)
        _render_pdf(
            _generate_range_print_html(
                "Weekly Activity Report",
                f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}",
                weekly_logs,
            ),
            REPORTS_DIR_PATH / WEEKLY_PDF_FILENAME,
        )

        month_start, month_end = _month_range(today)
        monthly_logs = _logs_in_range(logs, month_start, month_end)
        _render_pdf(
            _generate_range_print_html(
                "Monthly Activity Report",
                month_start.strftime("%B %Y"),
                monthly_logs,
            ),
            REPORTS_DIR_PATH / MONTHLY_PDF_FILENAME,
        )

        activity_html = generate_activity_page_html(open_tasks, logs, today)
        with open(ACTIVITY_FILE_PATH, "w", encoding="utf-8") as activity_file:
            activity_file.write(activity_html)

        return ACTIVITY_FILE_PATH
    finally:
        connection.close()


if __name__ == "__main__":
    saved_path = build_and_save_activity_page()
    print(f"Activity page built: {saved_path}")
