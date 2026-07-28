"""
Agent 4: Dashboard.

Purpose of this file
--------------------
Takes Agent 3's findings (stored in the database) and builds the site's
two pages:

  - docs/index.html   -- the Main Dashboard: a health-at-a-glance chart,
    a left sidebar organized by SEO checklist category (not severity),
    a search box, and a table of findings for whatever category (or
    search) is currently selected.
  - docs/history.html -- a simple, single-line-per-row list of every past
    run, each with a "Download PDF" link only -- old reports are never
    viewable inside the dashboard itself, only downloadable.

It also permanently archives every run as a PDF (docs/reports/run-XXXX.pdf)
-- unlike docs/index.html, which gets overwritten each run with only the
latest report, the PDF archive keeps a complete, permanent copy of every
week's report.

This file writes its output into "docs/". We use a folder named "docs"
because that's one of GitHub Pages' built-in options for "publish this
folder as a website" -- no extra hosting setup needed later.

This file does not run any checks itself -- it only reads what Agent 3
already saved and turns it into something readable.
"""

import html
import math
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from agent2_storage.database import get_connection

OUTPUT_FILE_PATH = Path(__file__).resolve().parent.parent / "docs" / "index.html"
HISTORY_FILE_PATH = Path(__file__).resolve().parent.parent / "docs" / "history.html"
REPORTS_DIR_PATH = Path(__file__).resolve().parent.parent / "docs" / "reports"

# How many findings to show per page in the table -- keeps the page from
# becoming an unreadable multi-thousand-row wall on a large site.
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
        "twitter-title-missing", "twitter-description-missing", "twitter-description-length",
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
    ("js-rendering", "JavaScript Rendering", {"js-rendering-content-differs", "js-added-internal-links"}),
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


def _render_health_donut(run_info, findings):
    """
    A single donut chart showing the proportion of critical/warning/info
    findings -- the "SEO health at a glance" visual that replaces the four
    separate stat tiles. Built as plain SVG (stacked partial circles using
    stroke-dasharray) so the file stays fully self-contained, no charting
    library needed.
    """
    counts = {severity: 0 for severity in SEVERITY_ORDER}
    for finding in findings:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
    total = sum(counts.values())

    radius = 70
    stroke_width = 26
    center = 90
    circumference = 2 * math.pi * radius

    segments_svg = []
    if total == 0:
        segments_svg.append(
            f'<circle cx="{center}" cy="{center}" r="{radius}" fill="none" '
            f'stroke="#e1e0d9" stroke-width="{stroke_width}" />'
        )
    else:
        cumulative_length = 0
        for severity in SEVERITY_ORDER:
            count = counts[severity]
            if count == 0:
                continue
            segment_length = (count / total) * circumference
            color = SEVERITY_DISPLAY[severity]["color"]
            # Rotating -90deg starts the first segment at the top (12
            # o'clock) instead of the default 3 o'clock, which reads more
            # naturally as a "gauge".
            segments_svg.append(
                f'<circle cx="{center}" cy="{center}" r="{radius}" fill="none" stroke="{color}" '
                f'stroke-width="{stroke_width}" '
                f'stroke-dasharray="{segment_length:.2f} {circumference - segment_length:.2f}" '
                f'stroke-dashoffset="{-cumulative_length:.2f}" transform="rotate(-90 {center} {center})">'
                f"<title>{SEVERITY_DISPLAY[severity]['label']}: {count}</title>"
                f"</circle>"
            )
            cumulative_length += segment_length

    legend_items = "".join(
        f'<div class="donut-legend-item"><span class="donut-legend-swatch" style="background:{SEVERITY_DISPLAY[s]["color"]}"></span>'
        f'{SEVERITY_DISPLAY[s]["icon"]} {SEVERITY_DISPLAY[s]["label"]}: <strong>{counts[s]}</strong></div>'
        for s in SEVERITY_ORDER
    )

    return f"""
    <div class="health-overview">
      <svg viewBox="0 0 {center * 2} {center * 2}" class="donut-chart" role="img" aria-label="SEO health overview">
        {"".join(segments_svg)}
        <text x="{center}" y="{center - 6}" text-anchor="middle" class="donut-total-number">{total}</text>
        <text x="{center}" y="{center + 16}" text-anchor="middle" class="donut-total-label">Total Issues</text>
      </svg>
      <div class="donut-legend">
        <div class="donut-legend-item donut-legend-pages">Pages Audited: <strong>{run_info['total_pages_crawled']}</strong></div>
        {legend_items}
      </div>
    </div>
    """


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
    Renders one <tr> per finding, tagged with data attributes the
    dashboard's JavaScript uses to filter by category, search by page URL,
    and paginate -- all three filters are just CSS display:none/"" toggles
    driven by these attributes, no server involved.
    """
    severity_rank = {severity: index for index, severity in enumerate(SEVERITY_ORDER)}
    sorted_findings = sorted(findings, key=lambda f: severity_rank.get(f["severity"], 99))

    rows_html = []
    for finding in sorted_findings:
        meta = SEVERITY_DISPLAY.get(finding["severity"], SEVERITY_DISPLAY["info"])
        category_id, _ = _categorize_rule(finding["rule"])
        rows_html.append(f"""
        <tr data-severity="{html.escape(finding['severity'])}" data-category="{category_id}" data-page="{html.escape(finding['page_url'].lower())}">
          <td><span class="severity-badge" style="--badge-color: {meta['color']}">{meta['icon']} {meta['label']}</span></td>
          <td><a href="{html.escape(finding['page_url'])}" target="_blank" rel="noopener">{html.escape(finding['page_url'])}</a></td>
          <td>{html.escape(finding['issue'])}</td>
          <td class="muted">{html.escape(finding['expected'] or '')}</td>
          <td class="muted">{html.escape(finding['actual'] or '')}</td>
        </tr>
        """)

    return "".join(rows_html)


def _render_sidebar(findings):
    """
    Left-hand navigation: "All Issues" plus one entry per SEO checklist
    category, each showing how many findings currently fall into it.
    Categories with zero findings still appear (so the checklist reads as
    complete), just visually muted.
    """
    counts_by_category = {category_id: 0 for category_id, _, _ in CATEGORIES}
    for finding in findings:
        category_id, _ = _categorize_rule(finding["rule"])
        counts_by_category[category_id] = counts_by_category.get(category_id, 0) + 1

    items = [
        f'<button class="nav-item active" data-category="all">'
        f'<span>All Issues</span><span class="nav-count">{len(findings)}</span></button>'
    ]
    for category_id, category_label, _ in CATEGORIES:
        count = counts_by_category.get(category_id, 0)
        empty_class = " nav-item-empty" if count == 0 else ""
        items.append(
            f'<button class="nav-item{empty_class}" data-category="{category_id}">'
            f'<span>{html.escape(category_label)}</span><span class="nav-count">{count}</span></button>'
        )

    return "".join(items)


def _shared_page_head_style():
    """CSS shared by both the Main Dashboard and the History page --
    surfaces, ink colors, and the top nav linking the two pages together."""
    return """
  :root {
    color-scheme: light;
    --surface-page: #f9f9f7;
    --surface-card: #fcfcfb;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --text-muted: #898781;
    --border-hairline: rgba(11,11,11,0.10);
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) {
      color-scheme: dark;
      --surface-page: #0d0d0d;
      --surface-card: #1a1a19;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted: #898781;
      --border-hairline: rgba(255,255,255,0.10);
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --surface-page: #0d0d0d;
    --surface-card: #1a1a19;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted: #898781;
    --border-hairline: rgba(255,255,255,0.10);
  }

  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--surface-page);
    color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 24px;
  }
  a { color: inherit; }

  .top-nav { display: flex; gap: 8px; margin-bottom: 20px; }
  .top-nav a {
    text-decoration: none;
    font-size: 0.85rem;
    font-weight: 600;
    padding: 8px 14px;
    border-radius: 999px;
    border: 1px solid var(--border-hairline);
    background: var(--surface-card);
  }
  .top-nav a.active { background: var(--text-primary); color: var(--surface-page); }

  table { width: 100%; table-layout: fixed; border-collapse: collapse; background: var(--surface-card); }
  th, td {
    text-align: left; padding: 10px 12px; font-size: 0.9rem; vertical-align: top;
    word-wrap: break-word; overflow-wrap: break-word;
    border: 1px solid var(--border-hairline);
  }
  th { color: var(--text-secondary); font-weight: 600; font-size: 0.8rem; text-transform: uppercase; }
  td.muted { color: var(--text-secondary); }
  .table-wrap { overflow-x: auto; border: 1px solid var(--border-hairline); border-radius: 8px; }
  .table-wrap table { border: none; }

  .severity-badge {
    display: inline-flex; align-items: center; gap: 4px; font-size: 0.8rem; font-weight: 600;
    color: var(--badge-color); white-space: nowrap;
  }

  .download-pdf-link {
    display: inline-flex; align-items: center; gap: 6px; font-size: 0.85rem; font-weight: 600;
    text-decoration: none; padding: 8px 14px; border-radius: 999px; border: 1px solid var(--border-hairline);
    background: var(--surface-card); color: var(--text-primary); white-space: nowrap;
  }
"""


def generate_dashboard_html(connection, run_id):
    run_info = load_run_info(connection, run_id)
    findings = load_findings(connection, run_id)
    trend = compute_trend(connection, run_id)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SEO Audit Dashboard - {html.escape(run_info['site_root_url'])}</title>
<style>
{_shared_page_head_style()}
  .app-shell {{ display: flex; align-items: flex-start; gap: 24px; max-width: 1300px; margin: 0 auto; }}
  .sidebar {{ width: 260px; flex-shrink: 0; position: sticky; top: 24px; }}
  .content {{ flex: 1; min-width: 0; }}

  .nav-item {{
    display: flex; align-items: center; justify-content: space-between; width: 100%; text-align: left;
    background: none; border: none; padding: 10px 12px; border-radius: 6px; cursor: pointer;
    font-family: inherit; font-size: 0.88rem; color: var(--text-primary); margin-bottom: 2px;
  }}
  .nav-item:hover {{ background: var(--surface-card); }}
  .nav-item.active {{ background: var(--text-primary); color: var(--surface-page); }}
  .nav-count {{ color: var(--text-secondary); font-size: 0.78rem; font-variant-numeric: tabular-nums; }}
  .nav-item.active .nav-count {{ color: var(--surface-page); opacity: 0.75; }}
  .nav-item-empty:not(.active) {{ color: var(--text-muted); }}

  header h1 {{ font-size: 1.4rem; margin-bottom: 4px; }}
  header p {{ color: var(--text-secondary); margin-top: 0; }}
  .header-row {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }}

  .health-overview {{
    display: flex; align-items: center; gap: 28px; flex-wrap: wrap;
    background: var(--surface-card); border: 1px solid var(--border-hairline); border-radius: 8px;
    padding: 20px; margin: 20px 0;
  }}
  .donut-chart {{ width: 150px; height: 150px; flex-shrink: 0; }}
  .donut-total-number {{ font-size: 34px; font-weight: 700; fill: var(--text-primary); }}
  .donut-total-label {{ font-size: 11px; fill: var(--text-secondary); }}
  .donut-legend {{ display: flex; flex-direction: column; gap: 8px; }}
  .donut-legend-item {{ font-size: 0.9rem; color: var(--text-secondary); }}
  .donut-legend-item strong {{ color: var(--text-primary); font-variant-numeric: tabular-nums; }}
  .donut-legend-swatch {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; margin-right: 6px; }}
  .donut-legend-pages {{ margin-bottom: 4px; padding-bottom: 8px; border-bottom: 1px solid var(--border-hairline); }}

  .trend-row {{
    display: flex; flex-wrap: wrap; gap: 20px; background: var(--surface-card);
    border: 1px solid var(--border-hairline); border-radius: 8px; padding: 16px; margin-bottom: 20px;
  }}
  .trend-number {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
  .trend-new {{ color: {SEVERITY_DISPLAY['critical']['color']}; }}
  .trend-resolved {{ color: #0ca30c; }}
  .trend-note {{ color: var(--text-secondary); }}

  .search-bar {{ margin-bottom: 12px; }}
  .search-bar input {{
    width: 100%; max-width: 420px; font-family: inherit; font-size: 0.9rem; padding: 9px 14px;
    border-radius: 999px; border: 1px solid var(--border-hairline); background: var(--surface-card);
    color: var(--text-primary);
  }}

  .pagination-bar {{ display: flex; align-items: center; gap: 12px; margin-top: 14px; }}
  .pagination-bar button {{
    font-family: inherit; font-size: 0.85rem; padding: 6px 12px; border-radius: 999px;
    border: 1px solid var(--border-hairline); background: var(--surface-card); color: var(--text-primary); cursor: pointer;
  }}
  .pagination-bar button:disabled {{ opacity: 0.4; cursor: default; }}
  #page-indicator {{ color: var(--text-secondary); font-size: 0.85rem; }}

  col.col-severity {{ width: 12%; }}
  col.col-page {{ width: 22%; }}
  col.col-issue {{ width: 27%; }}
  col.col-expected {{ width: 19%; }}
  col.col-actual {{ width: 20%; }}

  @media (max-width: 800px) {{
    .app-shell {{ flex-direction: column; }}
    .sidebar {{ width: 100%; position: static; }}
  }}
</style>
</head>
<body>
<div class="top-nav">
  <a href="index.html" class="active">Main Dashboard</a>
  <a href="history.html">History</a>
</div>

<div class="app-shell">
  <aside class="sidebar">
    <nav id="category-nav">
      {_render_sidebar(findings)}
    </nav>
  </aside>

  <div class="content">
    <header>
      <div class="header-row">
        <div>
          <h1>SEO Audit Dashboard</h1>
          <p>{html.escape(run_info['site_root_url'])} &middot; Run #{run_id} &middot; {html.escape(_format_timestamp(run_info['run_timestamp']))}</p>
        </div>
        <a class="download-pdf-link" href="reports/{_pdf_filename(run_id)}">&#8681; Download PDF</a>
      </div>
    </header>

    {_render_health_donut(run_info, findings)}

    {_render_trend_section(trend)}

    <div class="search-bar">
      <input type="search" id="search-input" placeholder="Search by page URL...">
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
          {_render_findings_table_rows(findings)}
        </tbody>
      </table>
    </div>

    <div class="pagination-bar">
      <button id="prev-page">&larr; Prev</button>
      <span id="page-indicator"></span>
      <button id="next-page">Next &rarr;</button>
    </div>
  </div>
</div>

<script>
  (function () {{
    var rowsPerPage = {ROWS_PER_PAGE};
    var currentPage = 1;
    var currentCategory = "all";
    var currentSearch = "";
    var allRows = Array.from(document.querySelectorAll("#findings-table tbody tr"));

    function getFilteredRows() {{
      return allRows.filter(function (row) {{
        var matchesCategory = currentCategory === "all" || row.getAttribute("data-category") === currentCategory;
        var matchesSearch = currentSearch === "" || row.getAttribute("data-page").indexOf(currentSearch) !== -1;
        return matchesCategory && matchesSearch;
      }});
    }}

    function render() {{
      var filteredRows = getFilteredRows();
      var totalPages = Math.max(1, Math.ceil(filteredRows.length / rowsPerPage));
      if (currentPage > totalPages) {{ currentPage = totalPages; }}

      allRows.forEach(function (row) {{ row.style.display = "none"; }});
      var startIndex = (currentPage - 1) * rowsPerPage;
      filteredRows.slice(startIndex, startIndex + rowsPerPage).forEach(function (row) {{
        row.style.display = "";
      }});

      document.getElementById("page-indicator").textContent =
        "Page " + currentPage + " of " + totalPages + " (" + filteredRows.length + " findings)";
      document.getElementById("prev-page").disabled = currentPage <= 1;
      document.getElementById("next-page").disabled = currentPage >= totalPages;
    }}

    document.querySelectorAll("#category-nav .nav-item").forEach(function (button) {{
      button.addEventListener("click", function () {{
        document.querySelectorAll("#category-nav .nav-item").forEach(function (b) {{ b.classList.remove("active"); }});
        button.classList.add("active");
        currentCategory = button.getAttribute("data-category");
        currentPage = 1;
        render();
      }});
    }});

    document.getElementById("search-input").addEventListener("input", function (event) {{
      currentSearch = event.target.value.trim().toLowerCase();
      currentPage = 1;
      render();
    }});

    document.getElementById("prev-page").addEventListener("click", function () {{
      if (currentPage > 1) {{ currentPage -= 1; render(); }}
    }});
    document.getElementById("next-page").addEventListener("click", function () {{
      currentPage += 1; render();
    }});

    render();
  }})();
</script>
</body>
</html>
"""


def generate_history_html(connection):
    """
    A simple, single-line-per-run list of every past audit, each with a
    "Download PDF" link only -- deliberately no link into an interactive
    view of old reports, per the requirement that historical reports are
    downloadable, not browsable, within the dashboard.
    """
    runs = load_all_runs(connection)

    rows_html = []
    for run in runs:
        findings = load_findings(connection, run["run_id"])
        counts = {severity: 0 for severity in SEVERITY_ORDER}
        for finding in findings:
            counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1

        severity_summary = " &nbsp; ".join(
            f'<span class="severity-badge" style="--badge-color: {SEVERITY_DISPLAY[s]["color"]}">'
            f'{SEVERITY_DISPLAY[s]["icon"]} {counts[s]}</span>'
            for s in SEVERITY_ORDER
        )

        rows_html.append(f"""
        <tr>
          <td>Run #{run['run_id']}</td>
          <td>{html.escape(_format_timestamp(run['run_timestamp']))}</td>
          <td>{run['total_pages_crawled']}</td>
          <td>{severity_summary}</td>
          <td><a class="download-pdf-link" href="reports/{_pdf_filename(run['run_id'])}">&#8681; Download PDF</a></td>
        </tr>
        """)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SEO Audit Report History</title>
<style>
{_shared_page_head_style()}
  .page-wrap {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 4px; }}
  header p {{ color: var(--text-secondary); margin-top: 0; margin-bottom: 20px; }}
  col.col-run {{ width: 12%; }}
  col.col-date {{ width: 24%; }}
  col.col-pages {{ width: 14%; }}
  col.col-severity {{ width: 30%; }}
  col.col-download {{ width: 20%; }}
</style>
</head>
<body>
<div class="page-wrap">
  <div class="top-nav">
    <a href="index.html">Main Dashboard</a>
    <a href="history.html" class="active">History</a>
  </div>

  <header>
    <h1>Report History</h1>
    <p>Every past audit run. Older reports are downloadable as PDF only -- they aren't viewable directly here.</p>
  </header>

  <div class="table-wrap">
    <table>
      <colgroup>
        <col class="col-run"><col class="col-date"><col class="col-pages">
        <col class="col-severity"><col class="col-download">
      </colgroup>
      <thead>
        <tr><th>Run</th><th>Date</th><th>Pages Audited</th><th>Severity Summary</th><th>Report</th></tr>
      </thead>
      <tbody>
        {"".join(rows_html)}
      </tbody>
    </table>
  </div>
</div>
</body>
</html>
"""


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


def build_and_save_dashboard(run_id=None, output_path=OUTPUT_FILE_PATH, history_path=HISTORY_FILE_PATH):
    connection = get_connection()
    try:
        if run_id is None:
            row = connection.execute("SELECT MAX(run_id) FROM runs").fetchone()
            run_id = row[0]

        html_content = generate_dashboard_html(connection, run_id)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as output_file:
            output_file.write(html_content)

        history_html = generate_history_html(connection)
        with open(history_path, "w", encoding="utf-8") as history_file:
            history_file.write(history_html)

        pdf_path = _save_pdf_report(connection, run_id)
        print(f"    -> PDF report archived to {pdf_path}")
        print(f"    -> History page updated at {history_path}")

        return run_id, output_path
    finally:
        connection.close()


if __name__ == "__main__":
    saved_run_id, saved_path = build_and_save_dashboard()
    print(f"Dashboard built for run_id={saved_run_id}")
    print(f"Saved to: {saved_path}")
