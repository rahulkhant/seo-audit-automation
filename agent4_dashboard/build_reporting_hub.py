"""
Agent 4: Reporting Hub -- trends across every past run.

Purpose of this file
--------------------
Everything else in agent4_dashboard/ answers "what's wrong right now" (the
latest run's findings). This file answers a different question -- "are we
actually getting better over time?" -- by aggregating every run recorded so
far into one page of trend charts plus a category-by-run breakdown table.

Like the rest of Agent 4, this is pure aggregation of data Agent 3 already
saved -- no new data collection, no judgment calls, just a different way of
looking at numbers that already exist in data/seo_audit_history.db. It
reuses the same CATEGORIES mapping and compute_trend() logic the main
dashboard already uses for its single-run "Since Last Run" card, just
gathered across every run instead of only the latest one.

Output:
  - docs/reporting.html (live, browsable, chart-based -- same Metronic
    shell/sidebar as the other two pages)
  - docs/reports/reporting-hub-latest.pdf -- unlike the per-run PDF archive
    in build_dashboard.py, this file is overwritten every run rather than
    kept permanently per run_id: it always summarizes the FULL history to
    date, so there's no single "point in time" version worth archiving.
    It's deliberately plain tables, no charts -- charts here would mean
    baking a CDN-loaded charting library into an unattended Playwright PDF
    render, an extra network dependency this automation doesn't need to
    take on. The live HTML page keeps the real charts since those render
    client-side, in the visitor's own browser.
"""

import html
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from agent2_storage.database import get_connection
from agent4_dashboard.build_dashboard import (
    CATEGORIES,
    SEVERITY_ORDER,
    _categorize_rule,
    _format_timestamp,
    compute_trend,
    load_all_runs,
    load_findings,
)
from agent4_dashboard.build_dashboard_metronic import (
    MX_RESOLVED_COLOR,
    MX_SEVERITY,
    _render_sidebar_nav,
    _render_topbar,
    _shared_head,
)

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
REPORTING_FILE_PATH = DOCS_DIR / "reporting.html"
REPORTS_DIR_PATH = DOCS_DIR / "reports"
REPORTING_PDF_FILENAME = "reporting-hub-latest.pdf"

# Reuse the exact same "new since last run" color the main dashboard's trend
# card uses for consistency across pages.
_NEW_COLOR = MX_SEVERITY["critical"]["color"]
_RECURRING_COLOR = MX_SEVERITY["info"]["color"]


def _load_reporting_hub_data(connection):
    """
    One entry per run, oldest first, with severity counts, category counts,
    and the total/resolved/recurring trend vs. the immediately previous run
    (None for the very first run, same as the dashboard's trend card).
    """
    runs_oldest_first = list(reversed(load_all_runs(connection)))

    per_run = []
    for run in runs_oldest_first:
        findings = load_findings(connection, run["run_id"])
        severity_counts = {severity: 0 for severity in SEVERITY_ORDER}
        category_counts = {category_id: 0 for category_id, _, _ in CATEGORIES}
        for finding in findings:
            severity_counts[finding["severity"]] = severity_counts.get(finding["severity"], 0) + 1
            category_id, _ = _categorize_rule(finding["rule"])
            category_counts[category_id] = category_counts.get(category_id, 0) + 1

        per_run.append({
            "run": run,
            "severity_counts": severity_counts,
            "category_counts": category_counts,
            "total": len(findings),
            "trend": compute_trend(connection, run["run_id"]),
        })
    return per_run


# --- Live page: ApexCharts (client-side, same CDN as the main dashboard) ---

_TREND_CHART_SCRIPT_TEMPLATE = """
var trendChartEl = document.querySelector("#trendChart");
if (trendChartEl && window.ApexCharts) {
  var trendChart = new ApexCharts(trendChartEl, {
    chart: { type: "area", height: 300, fontFamily: "Inter, sans-serif", stacked: true, toolbar: { show: false } },
    series: [
      { name: "Critical", data: __CRITICAL_DATA__ },
      { name: "Warning", data: __WARNING_DATA__ },
      { name: "Info", data: __INFO_DATA__ }
    ],
    xaxis: { categories: __RUN_LABELS__ },
    colors: ["__CRITICAL_COLOR__", "__WARNING_COLOR__", "__INFO_COLOR__"],
    legend: { position: "bottom" },
    dataLabels: { enabled: false },
    stroke: { curve: "smooth", width: 2 }
  });
  trendChart.render();
}
"""

_CHANGE_CHART_SCRIPT_TEMPLATE = """
var changeChartEl = document.querySelector("#changeChart");
if (changeChartEl && window.ApexCharts) {
  var changeChart = new ApexCharts(changeChartEl, {
    chart: { type: "bar", height: 300, fontFamily: "Inter, sans-serif", toolbar: { show: false } },
    series: [
      { name: "New", data: __NEW_DATA__ },
      { name: "Resolved", data: __RESOLVED_DATA__ },
      { name: "Recurring", data: __RECURRING_DATA__ }
    ],
    xaxis: { categories: __RUN_LABELS__ },
    colors: ["__NEW_COLOR__", "__RESOLVED_COLOR__", "__RECURRING_COLOR__"],
    legend: { position: "bottom" },
    dataLabels: { enabled: false },
    plotOptions: { bar: { columnWidth: "55%" } }
  });
  changeChart.render();
}
"""


def _run_label(run_row):
    return f"Run #{run_row['run_id']}"


def _render_trend_chart_script(per_run):
    if not per_run:
        return ""
    script = _TREND_CHART_SCRIPT_TEMPLATE
    script = script.replace("__RUN_LABELS__", json.dumps([_run_label(r["run"]) for r in per_run]))
    script = script.replace("__CRITICAL_DATA__", json.dumps([r["severity_counts"]["critical"] for r in per_run]))
    script = script.replace("__WARNING_DATA__", json.dumps([r["severity_counts"]["warning"] for r in per_run]))
    script = script.replace("__INFO_DATA__", json.dumps([r["severity_counts"]["info"] for r in per_run]))
    script = script.replace("__CRITICAL_COLOR__", MX_SEVERITY["critical"]["color"])
    script = script.replace("__WARNING_COLOR__", MX_SEVERITY["warning"]["color"])
    script = script.replace("__INFO_COLOR__", MX_SEVERITY["info"]["color"])
    return script


def _render_change_chart_script(per_run):
    runs_with_trend = [r for r in per_run if r["trend"] is not None]
    if not runs_with_trend:
        return ""

    run_labels = json.dumps([_run_label(r["run"]) for r in runs_with_trend])
    script = _CHANGE_CHART_SCRIPT_TEMPLATE
    script = script.replace("__RUN_LABELS__", run_labels)
    script = script.replace("__NEW_DATA__", json.dumps([r["trend"]["new_count"] for r in runs_with_trend]))
    script = script.replace("__RESOLVED_DATA__", json.dumps([r["trend"]["resolved_count"] for r in runs_with_trend]))
    script = script.replace("__RECURRING_DATA__", json.dumps([r["trend"]["recurring_count"] for r in runs_with_trend]))
    script = script.replace("__NEW_COLOR__", _NEW_COLOR)
    script = script.replace("__RESOLVED_COLOR__", MX_RESOLVED_COLOR)
    script = script.replace("__RECURRING_COLOR__", _RECURRING_COLOR)
    return script


def _render_trend_chart_card(per_run):
    body = '<div id="trendChart"></div>' if per_run else '<div class="chart-empty">No runs recorded yet.</div>'
    return f"""
    <div class="card">
      <div class="card-header"><div class="card-header-title">Findings Over Time</div></div>
      <div class="card-body">{body}</div>
    </div>
    """


def _render_change_chart_card(per_run):
    has_trend = any(r["trend"] is not None for r in per_run)
    body = '<div id="changeChart"></div>' if has_trend else '<div class="chart-empty">Need at least two runs to compare.</div>'
    return f"""
    <div class="card">
      <div class="card-header"><div class="card-header-title">New / Resolved / Recurring by Run</div></div>
      <div class="card-body">{body}</div>
    </div>
    """


def _render_category_table_rows(per_run):
    rows_html = []
    for category_id, category_label, _ in CATEGORIES:
        cells = "".join(f"<td>{r['category_counts'].get(category_id, 0)}</td>" for r in per_run)
        rows_html.append(f"<tr><td>{html.escape(category_label)}</td>{cells}</tr>")

    total_cells = "".join(f"<td><strong>{r['total']}</strong></td>" for r in per_run)
    rows_html.append(f"<tr><td><strong>Total</strong></td>{total_cells}</tr>")
    return "".join(rows_html)


def _render_category_table_card(per_run):
    if not per_run:
        body = '<div class="chart-empty">No runs recorded yet.</div>'
    else:
        header_cells = "".join(f"<th>{html.escape(_run_label(r['run']))}</th>" for r in per_run)
        body = f"""
        <div class="table-wrap">
          <table style="table-layout: auto">
            <thead><tr><th>Category</th>{header_cells}</tr></thead>
            <tbody>{_render_category_table_rows(per_run)}</tbody>
          </table>
        </div>
        """
    return f"""
    <div class="card">
      <div class="card-header"><div class="card-header-title">Category Breakdown by Run</div></div>
      {body}
    </div>
    """


def generate_reporting_hub_html(per_run):
    total_runs = len(per_run)
    latest = per_run[-1] if per_run else None
    subtitle_html = f"{total_runs} run(s) recorded"
    if latest:
        subtitle_html += (
            f" &middot; latest: Run #{latest['run']['run_id']}, "
            f"{html.escape(_format_timestamp(latest['run']['run_timestamp']))}"
        )

    apex_cdn_tag = '<script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>' if per_run else ""
    chart_scripts = _render_trend_chart_script(per_run) + _render_change_chart_script(per_run)
    pdf_href = f"reports/{REPORTING_PDF_FILENAME}"

    return f"""<!doctype html>
<html lang="en">
<head>
{_shared_head("SEO Reporting Hub")}
</head>
<body>
<div class="app">
  {_render_sidebar_nav("reporting")}
  <div class="main">
    {_render_topbar("Reporting Hub", subtitle_html, pdf_href)}
    <main class="content">
      {_render_trend_chart_card(per_run)}
      {_render_change_chart_card(per_run)}
      {_render_category_table_card(per_run)}
    </main>
  </div>
</div>
{apex_cdn_tag}
<script>
{chart_scripts}
</script>
</body>
</html>
"""


# --- PDF export: plain tables only, no charting library / CDN dependency,
# consistent with the existing per-run PDF report's philosophy of staying
# fully self-contained for an unattended Playwright render. ---

def _generate_reporting_print_html(per_run):
    total_runs = len(per_run)

    findings_rows = "".join(
        f"""<tr>
          <td>Run #{r['run']['run_id']}</td>
          <td>{html.escape(_format_timestamp(r['run']['run_timestamp']))}</td>
          <td>{r['run']['total_pages_crawled']}</td>
          <td>{r['severity_counts']['critical']}</td>
          <td>{r['severity_counts']['warning']}</td>
          <td>{r['severity_counts']['info']}</td>
          <td><strong>{r['total']}</strong></td>
        </tr>"""
        for r in per_run
    )

    runs_with_trend = [r for r in per_run if r["trend"] is not None]
    change_rows = "".join(
        f"""<tr>
          <td>Run #{r['run']['run_id']}</td>
          <td>{r['trend']['new_count']}</td>
          <td>{r['trend']['resolved_count']}</td>
          <td>{r['trend']['recurring_count']}</td>
        </tr>"""
        for r in runs_with_trend
    ) or '<tr><td colspan="4">Need at least two runs to compare.</td></tr>'

    category_header_cells = "".join(f"<th>{html.escape(_run_label(r['run']))}</th>" for r in per_run)
    category_rows = _render_category_table_rows(per_run) if per_run else ""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SEO Reporting Hub -- Trend Summary</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #ffffff; color: #0b0b0b; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; padding: 24px; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 4px; }}
  h2 {{ font-size: 1.05rem; margin: 28px 0 10px; }}
  header p {{ color: #52514e; margin-top: 0; }}
  table {{ width: 100%; table-layout: auto; border-collapse: collapse; margin-bottom: 8px; }}
  th, td {{ text-align: left; padding: 8px 10px; font-size: 0.8rem; vertical-align: top; border: 1px solid #cfcec8; }}
  th {{ color: #52514e; font-weight: 600; font-size: 0.7rem; text-transform: uppercase; }}
  tr {{ break-inside: avoid; }}
</style>
</head>
<body>
  <header>
    <h1>SEO Reporting Hub</h1>
    <p>Trend summary across {total_runs} recorded run(s)</p>
  </header>

  <h2>Findings by Run</h2>
  <table>
    <thead><tr><th>Run</th><th>Date</th><th>Pages Audited</th><th>Critical</th><th>Warning</th><th>Info</th><th>Total</th></tr></thead>
    <tbody>{findings_rows}</tbody>
  </table>

  <h2>New / Resolved / Recurring by Run</h2>
  <table>
    <thead><tr><th>Run</th><th>New</th><th>Resolved</th><th>Recurring</th></tr></thead>
    <tbody>{change_rows}</tbody>
  </table>

  <h2>Category Breakdown by Run</h2>
  <table>
    <thead><tr><th>Category</th>{category_header_cells}</tr></thead>
    <tbody>{category_rows}</tbody>
  </table>
</body>
</html>
"""


def _save_reporting_hub_pdf(per_run, reports_dir=REPORTS_DIR_PATH):
    print_html = _generate_reporting_print_html(per_run)
    reports_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = reports_dir / REPORTING_PDF_FILENAME

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


def build_and_save_reporting_hub():
    connection = get_connection()
    try:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        per_run = _load_reporting_hub_data(connection)

        reporting_html = generate_reporting_hub_html(per_run)
        with open(REPORTING_FILE_PATH, "w", encoding="utf-8") as reporting_file:
            reporting_file.write(reporting_html)

        pdf_path = _save_reporting_hub_pdf(per_run)
        return REPORTING_FILE_PATH, pdf_path
    finally:
        connection.close()


if __name__ == "__main__":
    saved_html_path, saved_pdf_path = build_and_save_reporting_hub()
    print(f"Reporting Hub built: {saved_html_path}")
    print(f"PDF summary saved to: {saved_pdf_path}")
