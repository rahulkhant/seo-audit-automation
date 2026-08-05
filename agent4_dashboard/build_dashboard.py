"""
Agent 4: Shared report data + PDF archive.

Purpose of this file
--------------------
The interactive dashboard itself now lives in build_dashboard_metronic.py
(docs/index.html, docs/history.html) -- this file has two remaining jobs:

  1. Shared data-loading helpers (load_run_info, load_findings, etc.) and
     rule/category/severity metadata that both the dashboard builder and
     the PDF builder need, kept in one place so they can't drift apart.
  2. Permanently archiving every run as a PDF (docs/reports/run-XXXX.pdf)
     -- unlike the dashboard, which gets overwritten each run with only
     the latest report, the PDF archive keeps a complete, permanent copy
     of every week's report.

This file does not run any checks itself -- it only reads what Agent 3
already saved and turns it into something readable.
"""

import html
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from agent2_storage.database import get_connection

REPORTS_DIR_PATH = Path(__file__).resolve().parent.parent / "docs" / "reports"

# How many findings to show per page in the dashboard table -- keeps the
# page from becoming an unreadable multi-thousand-row wall on a large site.
ROWS_PER_PAGE = 25

# Visual meaning for each severity level: a label, an icon (so severity is
# never communicated by color alone -- important for colorblind readers),
# and colors taken from a validated, colorblind-safe status palette.
# "info" deliberately uses a neutral gray rather than a "success" green,
# since low-urgency findings aren't necessarily good news.
SEVERITY_DISPLAY = {
    "critical": {"label": "Critical", "icon": "⛔", "color": "#d03b3b"},
    "warning": {"label": "Warning", "icon": "⚠", "color": "#fab219"},
    "info": {"label": "Info", "icon": "ℹ", "color": "#898781"},
}
SEVERITY_ORDER = ["critical", "warning", "info"]

# Groups every rule Agent 3 can produce into an SEO checklist category, so
# the dashboard can be browsed by "type of issue" (per your document's
# structure) instead of by severity. Each entry is
# (category_id, category_label, {rule names in this category}).
# category_id is used internally (URLs/data attributes); category_label is
# what's actually displayed.
CATEGORIES = [
    ("meta-title-description", "Meta Title & Description", {
        "title-missing", "title-length", "meta-description-missing", "meta-description-length",
        "duplicate-title", "duplicate-meta-description",
    }),
    ("headings", "Headings", {"h1-missing", "h1-multiple"}),
    ("social-tags", "Social Tags (OG & Twitter)", {
        "og-title-missing", "og-title-length", "og-description-missing", "og-description-length",
        "twitter-title-missing", "twitter-title-length", "twitter-description-missing", "twitter-description-length",
    }),
    ("url-structure", "URL Structure", {"url-underscore", "url-uppercase", "url-unnecessary-date", "url-too-long"}),
    ("canonical-tags", "Canonical Tags", {
        "canonical-missing", "canonical-duplicate", "canonical-not-absolute", "canonical-not-https",
        "canonical-target-broken",
    }),
    ("robots-indexability", "Robots & Indexability", {
        "robots-conflicting-directives", "robots-noindex-in-sitemap", "sitemap-non-html-entry",
        "page-not-200", "page-fetch-failed",
    }),
    ("images-alt-text", "Images & Alt Text", {"image-alt-missing"}),
    ("structured-data", "Structured Data (Schema)", {"schema-invalid-json", "schema-missing"}),
    ("https-security", "HTTPS & Security", {"ssl-invalid", "https-not-enforced", "mixed-content"}),
    ("redirects", "Redirects", {"redirect-chain", "redirect-loop", "sitemap-url-redirects"}),
    ("internal-linking", "Internal Linking", {"internal-link-broken", "internal-link-unverified", "orphan-page"}),
]

# Reverse lookup: rule name -> (category_id, category_label). Any rule not
# found here falls back to "other" (see _categorize_rule) so a future rule
# added to Agent 3 without updating this list still shows up somewhere,
# rather than silently vanishing from the dashboard.
_RULE_TO_CATEGORY = {}
for _category_id, _category_label, _rule_names in CATEGORIES:
    for _rule_name in _rule_names:
        _RULE_TO_CATEGORY[_rule_name] = (_category_id, _category_label)


def _categorize_rule(rule):
    return _RULE_TO_CATEGORY.get(rule, ("other", "Other"))


def _format_timestamp(iso_timestamp):
    """Converts the stored ISO timestamp (e.g. "2026-07-27T11:03:12+00:00")
    into a friendlier, human-readable form for display."""
    parsed = datetime.fromisoformat(iso_timestamp)
    return parsed.strftime("%b %d, %Y, %I:%M %p UTC")


def _pdf_filename(run_id):
    """The archived PDF's filename for a given run. Zero-padded so
    filenames still sort correctly once run numbers reach double/triple
    digits (plain "run-10.pdf" would otherwise sort before "run-2.pdf")."""
    return f"run-{run_id:04d}.pdf"


def load_run_info(connection, run_id):
    row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def load_all_runs(connection):
    rows = connection.execute("SELECT * FROM runs ORDER BY run_id DESC").fetchall()
    return [dict(row) for row in rows]


def load_findings(connection, run_id):
    rows = connection.execute(
        "SELECT * FROM findings WHERE run_id = ? ORDER BY page_url", (run_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def compute_trend(connection, current_run_id):
    """
    Compares this run's findings against the immediately previous run (if
    one exists), to show what's new and what's been resolved since then.
    A finding is identified by its (page_url, rule) pair -- if that same
    combination shows up in both runs, it's the "same" issue persisting.
    """
    previous_run_row = connection.execute(
        "SELECT run_id FROM runs WHERE run_id < ? ORDER BY run_id DESC LIMIT 1",
        (current_run_id,),
    ).fetchone()
    if previous_run_row is None:
        return None  # This is the first run ever -- nothing to compare against.

    previous_run_id = previous_run_row["run_id"]

    def _finding_keys(run_id):
        rows = connection.execute(
            "SELECT page_url, rule FROM findings WHERE run_id = ?", (run_id,)
        ).fetchall()
        return {(row["page_url"], row["rule"]) for row in rows}

    current_keys = _finding_keys(current_run_id)
    previous_keys = _finding_keys(previous_run_id)

    return {
        "previous_run_id": previous_run_id,
        "new_count": len(current_keys - previous_keys),
        "resolved_count": len(previous_keys - current_keys),
        "recurring_count": len(current_keys & previous_keys),
    }


def _render_trend_section(trend):
    if trend is None:
        return '<p class="trend-note">This is the first recorded run -- no previous run to compare against yet.</p>'

    return f"""
    <div class="trend-row">
      <div class="trend-item"><span class="trend-number trend-new">{trend['new_count']}</span> new since last run</div>
      <div class="trend-item"><span class="trend-number trend-resolved">{trend['resolved_count']}</span> resolved since last run</div>
      <div class="trend-item"><span class="trend-number trend-recurring">{trend['recurring_count']}</span> still present from last run</div>
    </div>
    """


def _render_findings_table_rows(findings):
    """
    Renders one <tr> per finding, tagged with data attributes the print
    report reuses verbatim (harmless, unused there) and the dashboard's own
    JavaScript uses to filter by category, search, and paginate.

    The "data-search" attribute is a global, lowercased blob of every
    visible column's text (severity label, page URL, issue, expected,
    actual) -- not just the page URL. Several columns already embed page
    metadata worth searching (e.g. the "Actual" column for a title-length
    finding literally contains the page's real title text), so a true
    global search naturally covers title/meta/description content too,
    without needing separate hidden fields for each.
    """
    severity_rank = {severity: index for index, severity in enumerate(SEVERITY_ORDER)}
    sorted_findings = sorted(findings, key=lambda f: severity_rank.get(f["severity"], 99))

    rows_html = []
    for finding in sorted_findings:
        meta = SEVERITY_DISPLAY.get(finding["severity"], SEVERITY_DISPLAY["info"])
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


def _generate_print_html(connection, run_id):
    """
    Builds a simplified, PDF-friendly version of the report: every finding
    in one continuous table (no pagination, no sidebar, no search, no
    JavaScript -- none of that means anything on a printed/PDF page), using
    plain light-mode colors directly rather than the dashboard's
    light/dark CSS variables, since a PDF has no viewer theme to adapt to.

    The severity column is intentionally wider than it looks like it needs
    to be, and the severity badge text is allowed to wrap (rather than
    "nowrap"): an earlier version had a narrow, non-wrapping severity
    column, which caused the "Critical"/"Warning" badge text to visually
    overflow into the Page column with no border to contain it. Explicit
    borders on every cell (not just a bottom line) are the other half of
    the fix -- they make column boundaries visible even if text ever
    comes close to them again.
    """
    run_info = load_run_info(connection, run_id)
    findings = load_findings(connection, run_id)
    trend = compute_trend(connection, run_id)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SEO Audit Report - {html.escape(run_info['site_root_url'])} - Run #{run_id}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: #ffffff;
    color: #0b0b0b;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 24px;
  }}
  h1 {{ font-size: 1.4rem; margin-bottom: 4px; }}
  header p {{ color: #52514e; margin-top: 0; }}

  .stat-tiles {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 20px 0; }}
  .stat-tile {{ border: 1px solid #e1e0d9; border-radius: 8px; padding: 16px; }}
  .stat-tile-label {{ color: #52514e; font-size: 0.85rem; }}
  .stat-tile-value {{ font-size: 1.8rem; font-weight: 600; }}
  .stat-tile-critical .stat-tile-value {{ color: {SEVERITY_DISPLAY['critical']['color']}; }}
  .stat-tile-warning .stat-tile-value {{ color: {SEVERITY_DISPLAY['warning']['color']}; }}

  .trend-row {{ display: flex; flex-wrap: wrap; gap: 20px; border: 1px solid #e1e0d9; border-radius: 8px; padding: 16px; margin-bottom: 20px; font-size: 0.9rem; }}
  .trend-number {{ font-weight: 700; }}
  .trend-new {{ color: {SEVERITY_DISPLAY['critical']['color']}; }}
  .trend-resolved {{ color: #0ca30c; }}
  .trend-note {{ color: #52514e; }}

  table {{ width: 100%; table-layout: fixed; border-collapse: collapse; }}
  th, td {{
    text-align: left; padding: 8px 10px; font-size: 0.8rem; vertical-align: top;
    word-wrap: break-word; overflow-wrap: break-word;
    border: 1px solid #cfcec8;
  }}
  th {{ color: #52514e; font-weight: 600; font-size: 0.7rem; text-transform: uppercase; }}
  td.muted {{ color: #52514e; }}
  a {{ color: inherit; }}
  col.col-severity {{ width: 13%; }}
  col.col-page {{ width: 21%; }}
  col.col-issue {{ width: 27%; }}
  col.col-expected {{ width: 19%; }}
  col.col-actual {{ width: 20%; }}
  .severity-badge {{
    display: inline-flex; align-items: center; gap: 4px; font-size: 0.72rem; font-weight: 600;
    color: var(--badge-color); white-space: normal; word-break: break-word;
  }}
  tr {{ break-inside: avoid; }}
</style>
</head>
<body>
  <header>
    <h1>SEO Audit Report</h1>
    <p>{html.escape(run_info['site_root_url'])} &middot; Run #{run_id} &middot; {html.escape(_format_timestamp(run_info['run_timestamp']))}</p>
  </header>

  <div class="stat-tiles">
    <div class="stat-tile">
      <div class="stat-tile-label">Pages Audited</div>
      <div class="stat-tile-value">{run_info['total_pages_crawled']}</div>
    </div>
    {"".join(
        f'<div class="stat-tile stat-tile-{s}">'
        f'<div class="stat-tile-label">{SEVERITY_DISPLAY[s]["icon"]} {SEVERITY_DISPLAY[s]["label"]}</div>'
        f'<div class="stat-tile-value">{sum(1 for f in findings if f["severity"] == s)}</div></div>'
        for s in SEVERITY_ORDER
    )}
  </div>

  {_render_trend_section(trend)}

  <table>
    <colgroup>
      <col class="col-severity"><col class="col-page"><col class="col-issue">
      <col class="col-expected"><col class="col-actual">
    </colgroup>
    <thead>
      <tr><th>Severity</th><th>Page</th><th>Issue</th><th>Expected</th><th>Actual</th></tr>
    </thead>
    <tbody>
      {_render_findings_table_rows(findings)}
    </tbody>
  </table>
</body>
</html>
"""


def _save_pdf_report(connection, run_id, reports_dir=REPORTS_DIR_PATH):
    """
    Renders this run's full report to a permanent PDF file using
    Playwright -- the same headless Chromium we already use for crawling,
    just printing a page to PDF instead of reading one.
    """
    print_html = _generate_print_html(connection, run_id)
    reports_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = reports_dir / _pdf_filename(run_id)

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


def build_and_save_pdf_report(run_id=None):
    connection = get_connection()
    try:
        if run_id is None:
            row = connection.execute("SELECT MAX(run_id) FROM runs").fetchone()
            run_id = row[0]

        pdf_path = _save_pdf_report(connection, run_id)
        return run_id, pdf_path
    finally:
        connection.close()


if __name__ == "__main__":
    saved_run_id, saved_pdf_path = build_and_save_pdf_report()
    print(f"PDF report archived for run_id={saved_run_id}")
    print(f"Saved to: {saved_pdf_path}")
