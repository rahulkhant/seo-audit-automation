"""
Agent 4: Dashboard.

Purpose of this file
--------------------
Takes Agent 3's findings (stored in the database) and builds a single,
self-contained HTML file that presents them clearly: how many issues exist,
broken down by severity, how that compares to the previous run (new issues,
resolved issues), and a full, filterable table of every finding.

This file writes its output to "docs/index.html". We use a folder named
"docs" because that's one of GitHub Pages' built-in options for "publish
this folder as a website" -- no extra hosting setup needed later, just a
checkbox in the repository's settings.

This file does not run any checks itself -- it only reads what Agent 3
already saved and turns it into something readable.
"""

import html
from collections import Counter
from datetime import datetime
from pathlib import Path

from agent2_storage.database import get_connection

OUTPUT_FILE_PATH = Path(__file__).resolve().parent.parent / "docs" / "index.html"

# How many findings to show per page in the table -- keeps the page from
# becoming an unreadable multi-thousand-row wall on a large site.
ROWS_PER_PAGE = 25

# How many distinct rules to show in the "findings by rule" chart. Any
# remaining rules beyond this are summed into an "Other" bar so the chart
# stays readable rather than growing without bound.
MAX_RULES_IN_CHART = 12

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


def _format_timestamp(iso_timestamp):
    """Converts the stored ISO timestamp (e.g. "2026-07-27T11:03:12+00:00")
    into a friendlier, human-readable form for display."""
    parsed = datetime.fromisoformat(iso_timestamp)
    return parsed.strftime("%b %d, %Y, %I:%M %p UTC")


def _load_run_info(connection, run_id):
    row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def _load_findings(connection, run_id):
    rows = connection.execute(
        "SELECT * FROM findings WHERE run_id = ? ORDER BY page_url", (run_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def _compute_trend(connection, current_run_id):
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


def _render_stat_tiles(run_info, findings):
    counts_by_severity = {severity: 0 for severity in SEVERITY_ORDER}
    for finding in findings:
        counts_by_severity[finding["severity"]] = counts_by_severity.get(finding["severity"], 0) + 1

    tiles = [f"""
        <div class="stat-tile">
          <div class="stat-tile-label">Pages Audited</div>
          <div class="stat-tile-value">{run_info['total_pages_crawled']}</div>
        </div>
    """]
    for severity in SEVERITY_ORDER:
        meta = SEVERITY_DISPLAY[severity]
        tiles.append(f"""
        <div class="stat-tile stat-tile-{severity}">
          <div class="stat-tile-label">{meta['icon']} {meta['label']}</div>
          <div class="stat-tile-value">{counts_by_severity[severity]}</div>
        </div>
        """)
    return "".join(tiles)


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


def _render_rules_chart(findings):
    """
    Horizontal bar chart: which rules are triggering the most findings,
    right now, in this run. Each bar is colored by that rule's severity, so
    the chart doubles as a quick "what matters most" view. Bars beyond
    MAX_RULES_IN_CHART are summed into a single "Other" bar (in a neutral
    color, since it mixes severities) rather than letting the chart grow
    without bound.
    """
    counts_by_rule = Counter(finding["rule"] for finding in findings)
    severity_by_rule = {finding["rule"]: finding["severity"] for finding in findings}

    if not counts_by_rule:
        return '<p class="chart-empty">No findings to chart.</p>'

    most_common = counts_by_rule.most_common()
    top_rules = most_common[:MAX_RULES_IN_CHART]
    other_count = sum(count for _, count in most_common[MAX_RULES_IN_CHART:])
    if other_count:
        top_rules.append(("Other", other_count))

    row_height = 22
    row_gap = 10
    row_step = row_height + row_gap
    label_column_width = 230
    bar_area_width = 380
    chart_width = label_column_width + bar_area_width + 60
    chart_height = len(top_rules) * row_step

    max_count = top_rules[0][1] if top_rules else 1

    bars_svg = []
    for index, (rule, count) in enumerate(top_rules):
        y = index * row_step
        bar_width = (count / max_count) * bar_area_width if max_count else 0
        color = SEVERITY_DISPLAY.get(severity_by_rule.get(rule), {}).get("color", "#898781")
        display_name = "Other rules (combined)" if rule == "Other" else rule
        bars_svg.append(f"""
          <text x="0" y="{y + row_height / 2 + 4}" class="chart-row-label">{html.escape(display_name)}</text>
          <rect x="{label_column_width}" y="{y}" width="{bar_width:.1f}" height="{row_height}" rx="4" fill="{color}">
            <title>{html.escape(display_name)}: {count} finding(s)</title>
          </rect>
          <text x="{label_column_width + bar_width + 8:.1f}" y="{y + row_height / 2 + 4}" class="chart-value-label">{count}</text>
        """)

    return f"""
    <svg viewBox="0 0 {chart_width} {chart_height}" class="rules-chart" role="img" aria-label="Findings by rule">
      {"".join(bars_svg)}
    </svg>
    """


def _render_history_chart(connection):
    """
    Stacked bar chart: how many findings of each severity were found on
    every run recorded so far, letting you see at a glance whether things
    are trending better or worse over time. With only one run recorded,
    this simply shows a single bar -- it fills in as more weekly runs
    accumulate.
    """
    rows = connection.execute(
        """
        SELECT r.run_id, r.run_timestamp,
               SUM(CASE WHEN f.severity = 'critical' THEN 1 ELSE 0 END) AS critical_count,
               SUM(CASE WHEN f.severity = 'warning' THEN 1 ELSE 0 END) AS warning_count,
               SUM(CASE WHEN f.severity = 'info' THEN 1 ELSE 0 END) AS info_count
        FROM runs r
        LEFT JOIN findings f ON f.run_id = r.run_id
        GROUP BY r.run_id
        ORDER BY r.run_id
        """
    ).fetchall()

    if not rows:
        return '<p class="chart-empty">No runs to chart yet.</p>'

    bar_width = 44
    bar_gap = 28
    max_bar_height = 200
    segment_gap = 2  # thin gap between stacked segments, per accessibility guidance
    label_area_height = 34
    # A minimum width keeps the chart's aspect ratio sane when only one or
    # two runs exist -- without this, a narrow viewBox stretched to the
    # card's full width would blow up the height absurdly.
    chart_width = max(len(rows) * (bar_width + bar_gap), 320)
    chart_height = max_bar_height + label_area_height

    max_total = max((row["critical_count"] + row["warning_count"] + row["info_count"]) for row in rows) or 1

    bars_svg = []
    for index, row in enumerate(rows):
        x = index * (bar_width + bar_gap)
        total = row["critical_count"] + row["warning_count"] + row["info_count"]
        run_date = datetime.fromisoformat(row["run_timestamp"]).strftime("%b %d")

        # Stack order (bottom to top): critical, warning, info.
        segments = [
            ("critical", row["critical_count"]),
            ("warning", row["warning_count"]),
            ("info", row["info_count"]),
        ]

        # Any non-zero count gets at least this much height, even if its
        # true proportional share would round down to nothing -- a real
        # (if small) number of critical issues should never look like zero.
        min_segment_height = 4

        y_cursor = max_bar_height
        for severity, count in segments:
            if count <= 0:
                continue
            raw_height = (count / max_total) * max_bar_height if max_total else 0
            segment_height = max(raw_height, min_segment_height)
            y_cursor -= segment_height
            color = SEVERITY_DISPLAY[severity]["color"]
            bars_svg.append(f"""
              <rect x="{x}" y="{y_cursor:.1f}" width="{bar_width}" height="{max(segment_height - segment_gap, 0):.1f}" rx="3" fill="{color}">
                <title>Run #{row['run_id']} ({run_date}): {SEVERITY_DISPLAY[severity]['label']} = {count}</title>
              </rect>
            """)

        bars_svg.append(f"""
          <text x="{x + bar_width / 2}" y="{max_bar_height + 16}" class="chart-axis-label" text-anchor="middle">{run_date}</text>
          <text x="{x + bar_width / 2}" y="{max_bar_height + 30}" class="chart-axis-label" text-anchor="middle">({total})</text>
        """)

    legend_items = "".join(
        f'<span class="chart-legend-item"><span class="chart-legend-swatch" style="background:{SEVERITY_DISPLAY[s]["color"]}"></span>{SEVERITY_DISPLAY[s]["icon"]} {SEVERITY_DISPLAY[s]["label"]}</span>'
        for s in SEVERITY_ORDER
    )

    return f"""
    <svg viewBox="0 0 {chart_width} {chart_height}" class="history-chart" role="img" aria-label="Findings over time by severity">
      {"".join(bars_svg)}
    </svg>
    <div class="chart-legend">{legend_items}</div>
    """


def _render_findings_table(findings):
    severity_rank = {severity: index for index, severity in enumerate(SEVERITY_ORDER)}
    sorted_findings = sorted(findings, key=lambda f: severity_rank.get(f["severity"], 99))

    rows_html = []
    for finding in sorted_findings:
        meta = SEVERITY_DISPLAY.get(finding["severity"], SEVERITY_DISPLAY["info"])
        rows_html.append(f"""
        <tr data-severity="{html.escape(finding['severity'])}">
          <td><span class="severity-badge" style="--badge-color: {meta['color']}">{meta['icon']} {meta['label']}</span></td>
          <td><a href="{html.escape(finding['page_url'])}" target="_blank" rel="noopener">{html.escape(finding['page_url'])}</a></td>
          <td>{html.escape(finding['issue'])}</td>
          <td class="muted">{html.escape(finding['expected'] or '')}</td>
          <td class="muted">{html.escape(finding['actual'] or '')}</td>
        </tr>
        """)

    return "".join(rows_html)


def generate_dashboard_html(connection, run_id):
    run_info = _load_run_info(connection, run_id)
    findings = _load_findings(connection, run_id)
    trend = _compute_trend(connection, run_id)

    filter_buttons = ['<button class="filter-button active" data-filter="all">All</button>']
    for severity in SEVERITY_ORDER:
        meta = SEVERITY_DISPLAY[severity]
        filter_buttons.append(
            f'<button class="filter-button" data-filter="{severity}">{meta["icon"]} {meta["label"]}</button>'
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SEO Audit Dashboard - {html.escape(run_info['site_root_url'])}</title>
<style>
  :root {{
    color-scheme: light;
    --surface-page: #f9f9f7;
    --surface-card: #fcfcfb;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --text-muted: #898781;
    --border-hairline: rgba(11,11,11,0.10);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) {{
      color-scheme: dark;
      --surface-page: #0d0d0d;
      --surface-card: #1a1a19;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted: #898781;
      --border-hairline: rgba(255,255,255,0.10);
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --surface-page: #0d0d0d;
    --surface-card: #1a1a19;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted: #898781;
    --border-hairline: rgba(255,255,255,0.10);
  }}

  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--surface-page);
    color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 24px;
  }}
  .page-wrap {{ max-width: 1100px; margin: 0 auto; }}
  header h1 {{ font-size: 1.4rem; margin-bottom: 4px; }}
  header p {{ color: var(--text-secondary); margin-top: 0; }}

  .stat-tiles {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 12px;
    margin: 20px 0;
  }}
  .stat-tile {{
    background: var(--surface-card);
    border: 1px solid var(--border-hairline);
    border-radius: 8px;
    padding: 16px;
  }}
  .stat-tile-label {{ color: var(--text-secondary); font-size: 0.85rem; }}
  .stat-tile-value {{ font-size: 2rem; font-weight: 600; font-variant-numeric: proportional-nums; }}
  .stat-tile-critical .stat-tile-value {{ color: {SEVERITY_DISPLAY['critical']['color']}; }}
  .stat-tile-warning .stat-tile-value {{ color: {SEVERITY_DISPLAY['warning']['color']}; }}

  .trend-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
    background: var(--surface-card);
    border: 1px solid var(--border-hairline);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 20px;
  }}
  .trend-number {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
  .trend-new {{ color: {SEVERITY_DISPLAY['critical']['color']}; }}
  .trend-resolved {{ color: #0ca30c; }}
  .trend-note {{ color: var(--text-secondary); }}

  .chart-section {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
    gap: 12px;
    margin-bottom: 20px;
  }}
  .chart-card {{
    background: var(--surface-card);
    border: 1px solid var(--border-hairline);
    border-radius: 8px;
    padding: 16px;
  }}
  .chart-card h2 {{ font-size: 0.95rem; margin: 0 0 12px 0; }}
  .chart-empty {{ color: var(--text-secondary); font-size: 0.9rem; }}
  .rules-chart, .history-chart {{ width: 100%; height: auto; }}
  .chart-row-label {{ font-size: 11px; fill: var(--text-secondary); dominant-baseline: middle; }}
  .chart-value-label {{ font-size: 11px; fill: var(--text-primary); font-variant-numeric: tabular-nums; dominant-baseline: middle; }}
  .chart-axis-label {{ font-size: 10px; fill: var(--text-muted); }}
  .chart-legend {{ display: flex; gap: 16px; margin-top: 10px; flex-wrap: wrap; }}
  .chart-legend-item {{ display: inline-flex; align-items: center; gap: 6px; font-size: 0.8rem; color: var(--text-secondary); }}
  .chart-legend-swatch {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}

  .filter-bar {{ margin-bottom: 12px; }}
  .pagination-bar {{ display: flex; align-items: center; gap: 12px; margin-top: 14px; }}
  .pagination-bar .filter-button:disabled {{ opacity: 0.4; cursor: default; }}
  #page-indicator {{ color: var(--text-secondary); font-size: 0.85rem; }}
  .filter-button {{
    font-family: inherit;
    font-size: 0.85rem;
    padding: 6px 12px;
    margin-right: 6px;
    border-radius: 999px;
    border: 1px solid var(--border-hairline);
    background: var(--surface-card);
    color: var(--text-primary);
    cursor: pointer;
  }}
  .filter-button.active {{ background: var(--text-primary); color: var(--surface-page); }}

  table {{ width: 100%; table-layout: fixed; border-collapse: collapse; background: var(--surface-card); border-radius: 8px; overflow: hidden; }}
  th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border-hairline); font-size: 0.9rem; vertical-align: top; word-wrap: break-word; overflow-wrap: break-word; }}
  th {{ color: var(--text-secondary); font-weight: 600; font-size: 0.8rem; text-transform: uppercase; }}
  td.muted {{ color: var(--text-secondary); }}
  a {{ color: inherit; }}
  col.col-severity {{ width: 9%; }}
  col.col-page {{ width: 22%; }}
  col.col-issue {{ width: 29%; }}
  col.col-expected {{ width: 20%; }}
  col.col-actual {{ width: 20%; }}

  .severity-badge {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--badge-color);
    white-space: nowrap;
  }}

  .table-wrap {{ overflow-x: auto; }}
</style>
</head>
<body>
<div class="page-wrap">
  <header>
    <h1>SEO Audit Dashboard</h1>
    <p>{html.escape(run_info['site_root_url'])} &middot; Run #{run_id} &middot; {html.escape(_format_timestamp(run_info['run_timestamp']))}</p>
  </header>

  <div class="stat-tiles">
    {_render_stat_tiles(run_info, findings)}
  </div>

  {_render_trend_section(trend)}

  <div class="chart-section">
    <div class="chart-card">
      <h2>Findings by Rule (top {MAX_RULES_IN_CHART})</h2>
      {_render_rules_chart(findings)}
    </div>
    <div class="chart-card">
      <h2>Findings Over Time</h2>
      {_render_history_chart(connection)}
    </div>
  </div>

  <div class="filter-bar">
    {''.join(filter_buttons)}
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
        {_render_findings_table(findings)}
      </tbody>
    </table>
  </div>

  <div class="pagination-bar">
    <button id="prev-page" class="filter-button">&larr; Prev</button>
    <span id="page-indicator"></span>
    <button id="next-page" class="filter-button">Next &rarr;</button>
  </div>
</div>

<script>
  (function () {{
    var rowsPerPage = {ROWS_PER_PAGE};
    var currentPage = 1;
    var currentFilter = "all";
    var allRows = Array.from(document.querySelectorAll("#findings-table tbody tr"));

    function getFilteredRows() {{
      return allRows.filter(function (row) {{
        return currentFilter === "all" || row.getAttribute("data-severity") === currentFilter;
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

    document.querySelectorAll(".filter-button[data-filter]").forEach(function (button) {{
      button.addEventListener("click", function () {{
        document.querySelectorAll(".filter-button[data-filter]").forEach(function (b) {{ b.classList.remove("active"); }});
        button.classList.add("active");
        currentFilter = button.getAttribute("data-filter");
        currentPage = 1;
        render();
      }});
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


def build_and_save_dashboard(run_id=None, output_path=OUTPUT_FILE_PATH):
    connection = get_connection()
    try:
        if run_id is None:
            row = connection.execute("SELECT MAX(run_id) FROM runs").fetchone()
            run_id = row[0]

        html_content = generate_dashboard_html(connection, run_id)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as output_file:
            output_file.write(html_content)
        return run_id, output_path
    finally:
        connection.close()


if __name__ == "__main__":
    saved_run_id, saved_path = build_and_save_dashboard()
    print(f"Dashboard built for run_id={saved_run_id}")
    print(f"Saved to: {saved_path}")
