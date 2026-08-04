"""
Content Agent: dashboard page.

Purpose of this file
--------------------
Builds docs/content.html -- a list of every outline the Outliner Agent has
produced, using the same Metronic shell (sidebar, topbar, card styling) as
the SEO audit's dashboard pages, so the whole platform reads as one
system rather than a bolted-on second app. Each outline is shown as an
expandable card (plain HTML <details>/<summary>, no JavaScript needed)
with its full section-by-section breakdown.

This file does not produce or judge any content itself -- it only reads
what the Outliner Agent already saved (via content_agent.save_brief) and
turns it into something readable, the same division of labor as Agent 4
for the audit pipeline.
"""

import html
from datetime import datetime
from pathlib import Path

from content_agent.database import get_connection, load_all_briefs
from agent4_dashboard.build_dashboard_metronic import (
    _render_sidebar_nav,
    _render_topbar,
    _shared_head,
)

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
CONTENT_FILE_PATH = DOCS_DIR / "content.html"

_CONTENT_PAGE_STYLE = """
  .brief-list { display: flex; flex-direction: column; gap: 16px; }
  .brief-card { background: var(--mx-card-bg); border: 1px solid var(--mx-border); border-radius: 12px; overflow: hidden; }
  .brief-summary {
    list-style: none; cursor: pointer; padding: 18px 22px; display: flex; align-items: center;
    justify-content: space-between; gap: 16px; flex-wrap: wrap;
  }
  .brief-summary::-webkit-details-marker { display: none; }
  .brief-summary-main { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .brief-topic { font-weight: 700; font-size: 1rem; }
  .brief-meta { color: var(--mx-text-gray-600); font-size: 0.85rem; }
  .brief-summary-right { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
  .status-badge {
    display: inline-flex; align-items: center; padding: 5px 12px; border-radius: 999px;
    font-weight: 600; font-size: 0.78rem; color: var(--mx-primary);
    background-color: var(--mx-primary-light); white-space: nowrap; text-transform: capitalize;
  }
  .brief-body { padding: 0 22px 22px; border-top: 1px solid var(--mx-border); }
  .brief-field-row { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 14px; margin: 18px 0; }
  .brief-field-label { color: var(--mx-text-gray-500); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.03em; font-weight: 600; }
  .brief-field-value { font-size: 0.9rem; margin-top: 3px; }
  .section-list { display: flex; flex-direction: column; gap: 10px; margin-top: 8px; }
  .section-item { border: 1px solid var(--mx-border); border-radius: 8px; padding: 12px 16px; }
  .section-item-header { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
  .section-heading { font-weight: 600; }
  .section-level { color: var(--mx-text-gray-500); font-size: 0.72rem; text-transform: uppercase; font-weight: 700; }
  .section-budget { color: var(--mx-primary); font-size: 0.82rem; font-weight: 600; margin-left: auto; }
  .section-points { font-size: 0.87rem; margin-top: 6px; }
  .section-keywords { color: var(--mx-text-gray-600); font-size: 0.8rem; margin-top: 6px; }
  .empty-state { color: var(--mx-text-gray-600); font-size: 0.9rem; padding: 40px 0; text-align: center; }
"""


def _render_section_item(section):
    label = section["heading"] or section["level"].capitalize()
    level_tag = "" if section["level"] in ("intro", "conclusion") else section["level"]
    keywords = section.get("keywords") or []
    keywords_html = (
        f'<div class="section-keywords">Keywords: {html.escape(", ".join(keywords))}</div>'
        if keywords
        else ""
    )
    notes_html = (
        f'<div class="section-keywords">Note: {html.escape(section["notes"])}</div>'
        if section.get("notes")
        else ""
    )
    return f"""
    <div class="section-item">
      <div class="section-item-header">
        {f'<span class="section-level">{html.escape(level_tag)}</span>' if level_tag else ""}
        <span class="section-heading">{html.escape(label)}</span>
        <span class="section-budget">{section['word_budget']} words</span>
      </div>
      <div class="section-points">{html.escape(section.get("points_to_cover") or "")}</div>
      {keywords_html}
      {notes_html}
    </div>
    """


def _format_created_at(iso_timestamp):
    return datetime.fromisoformat(iso_timestamp).strftime("%b %d, %Y, %I:%M %p UTC")


def _render_brief_card(brief):
    total_budget = sum(s["word_budget"] for s in brief["sections"])
    meta_line = " &middot; ".join(filter(None, [
        html.escape(brief["content_format"]) if brief.get("content_format") else None,
        f"{brief['target_word_count']} words target",
        html.escape(_format_created_at(brief["created_at"])),
    ]))

    fields = [
        ("Primary keyword", brief["primary_keyword"]),
        ("Secondary keywords", ", ".join(brief["secondary_keywords"]) or "—"),
        ("Target audience", brief.get("target_audience") or "—"),
        ("Search intent", brief.get("search_intent") or "—"),
        ("Tone of voice", brief.get("tone_of_voice") or "—"),
        ("CTA", brief.get("cta") or "—"),
    ]
    fields_html = "".join(
        f'<div><div class="brief-field-label">{html.escape(label)}</div>'
        f'<div class="brief-field-value">{html.escape(str(value))}</div></div>'
        for label, value in fields
    )
    other_notes_html = (
        f'<div class="brief-field-label">Other notes</div>'
        f'<div class="brief-field-value">{html.escape(brief["other_notes"])}</div>'
        if brief.get("other_notes")
        else ""
    )

    sections_html = "".join(_render_section_item(section) for section in brief["sections"])

    return f"""
    <details class="brief-card">
      <summary class="brief-summary">
        <div class="brief-summary-main">
          <div class="brief-topic">{html.escape(brief["topic"])}</div>
          <div class="brief-meta">{meta_line} &middot; {total_budget} words allocated</div>
        </div>
        <div class="brief-summary-right">
          <span class="status-badge">{html.escape(brief["status"])}</span>
        </div>
      </summary>
      <div class="brief-body">
        <div class="brief-field-row">{fields_html}</div>
        {other_notes_html}
        <div class="section-list">{sections_html}</div>
      </div>
    </details>
    """


def generate_content_page_html(briefs):
    subtitle_html = f"{len(briefs)} outline(s) created"
    body = (
        f'<div class="brief-list">{"".join(_render_brief_card(b) for b in briefs)}</div>'
        if briefs
        else '<div class="empty-state">No content outlines yet -- run the /blog-outline skill to create one.</div>'
    )

    return f"""<!doctype html>
<html lang="en">
<head>
{_shared_head("Content Outlines")}
<style>{_CONTENT_PAGE_STYLE}</style>
</head>
<body>
<div class="app">
  {_render_sidebar_nav("content")}
  <div class="main">
    {_render_topbar("Content Outlines", subtitle_html)}
    <main class="content">
      {body}
    </main>
  </div>
</div>
</body>
</html>
"""


def build_and_save_content_page():
    connection = get_connection()
    try:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        briefs = load_all_briefs(connection)

        content_html = generate_content_page_html(briefs)
        with open(CONTENT_FILE_PATH, "w", encoding="utf-8") as content_file:
            content_file.write(content_html)

        return CONTENT_FILE_PATH
    finally:
        connection.close()


if __name__ == "__main__":
    saved_path = build_and_save_content_page()
    print(f"Content page built: {saved_path}")
