"""
Content Agent: dashboard page.

Purpose of this file
--------------------
Builds docs/content.html -- a list of every outline the Outliner Agent has
produced, using the same Metronic shell (sidebar, topbar, card styling) as
the SEO audit's dashboard pages, so the whole platform reads as one
system rather than a bolted-on second app.

Redesigned 2026-08-04 (per Rahul's feedback on the first real outline):
the list itself stays a short, aligned row per brief -- topic, format,
word count, status, a Download PDF button -- and clicking a row opens the
full section-by-section brief in a modal (native <dialog>) with its own
internal scrollbar, instead of expanding inline and pushing the whole page
down. With several outlines on the page at once, only the modal you
actually opened scrolls, not the entire dashboard.

Also generates one PDF per brief (docs/content_briefs/brief-XXXX.pdf),
plain tables/lists like the SEO audit's other PDF exports, so a finished
outline can be handed to a writer without needing dashboard access.

This file does not produce or judge any content itself -- it only reads
what the Outliner Agent already saved (via content_agent.save_brief) and
turns it into something readable, the same division of labor as Agent 4
for the audit pipeline.
"""

import html
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from content_agent.database import get_connection, load_all_briefs
from agent4_dashboard.build_dashboard_metronic import (
    ICON_DOWNLOAD,
    _render_sidebar_nav,
    _render_topbar,
    _shared_head,
)

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
CONTENT_FILE_PATH = DOCS_DIR / "content.html"
BRIEFS_PDF_DIR = DOCS_DIR / "content_briefs"

_CONTENT_PAGE_STYLE = """
  .brief-list { display: flex; flex-direction: column; gap: 10px; }
  .brief-row {
    background: var(--mx-card-bg); border: 1px solid var(--mx-border); border-radius: 10px;
    padding: 16px 20px; display: flex; align-items: center; justify-content: space-between;
    gap: 16px; cursor: pointer;
  }
  .brief-row:hover { border-color: var(--mx-primary); }
  .brief-row-main { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .brief-topic { font-weight: 700; font-size: 0.98rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .brief-meta { color: var(--mx-text-gray-600); font-size: 0.83rem; }
  .brief-row-right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
  .status-badge {
    display: inline-flex; align-items: center; padding: 5px 12px; border-radius: 999px;
    font-weight: 600; font-size: 0.78rem; color: var(--mx-primary);
    background-color: var(--mx-primary-light); white-space: nowrap; text-transform: capitalize;
  }
  .empty-state { color: var(--mx-text-gray-600); font-size: 0.9rem; padding: 40px 0; text-align: center; }

  /* Base rule intentionally does NOT set "display" -- the browser's own
     "dialog:not([open]) { display: none; }" default has to stay in charge
     while a dialog is closed. An earlier version set display:flex here
     unconditionally, which -- being equal specificity and later in the
     cascade -- overrode that default and left every dialog visible (and
     intercepting clicks) even when closed. Everything below is scoped to
     [open] specifically so closed dialogs stay properly hidden. */
  dialog.brief-modal[open] {
    position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); margin: 0;
    width: min(720px, 92vw); max-height: 82vh; padding: 0; border: none; border-radius: 14px;
    background: var(--mx-card-bg); color: var(--mx-text-dark); display: flex; flex-direction: column;
  }
  dialog.brief-modal::backdrop { background: rgba(15, 15, 20, 0.55); }
  /* Native <dialog> doesn't lock the page behind it from scrolling on its
     own -- without this, the main content could still scroll under the
     modal, which is exactly the "don't scroll the full screen" bug. */
  body:has(dialog.brief-modal[open]) { overflow: hidden; }
  .brief-modal-header {
    display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
    padding: 20px 24px; border-bottom: 1px solid var(--mx-border); flex-shrink: 0;
  }
  .brief-modal-title { font-size: 1.05rem; font-weight: 700; }
  .brief-modal-meta { color: var(--mx-text-gray-600); font-size: 0.85rem; margin-top: 4px; }
  .brief-modal-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
  .btn-icon-close {
    width: 34px; height: 34px; border-radius: 8px; border: 1px solid var(--mx-border); background: transparent;
    color: var(--mx-text-gray-600); cursor: pointer; display: flex; align-items: center; justify-content: center;
    font-family: inherit; font-size: 1rem; line-height: 1;
  }
  .btn-icon-close:hover { background: var(--mx-body-bg); }
  .brief-modal-body { padding: 20px 24px 24px; overflow-y: auto; flex: 1 1 auto; min-height: 0; }

  dl.brief-field-table { display: grid; grid-template-columns: 150px 1fr; row-gap: 10px; column-gap: 16px; margin: 0 0 22px; font-size: 0.88rem; }
  dl.brief-field-table dt { color: var(--mx-text-gray-500); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.03em; font-weight: 600; padding-top: 2px; }
  dl.brief-field-table dd { margin: 0; }

  .section-list { display: flex; flex-direction: column; gap: 10px; }
  .section-item { border: 1px solid var(--mx-border); border-radius: 8px; padding: 12px 16px; }
  .section-item-header { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
  .section-heading { font-weight: 600; }
  .section-level { color: var(--mx-text-gray-500); font-size: 0.72rem; text-transform: uppercase; font-weight: 700; }
  .section-budget { color: var(--mx-primary); font-size: 0.82rem; font-weight: 600; margin-left: auto; }
  .section-points { font-size: 0.87rem; margin-top: 6px; }
  .section-keywords { color: var(--mx-text-gray-600); font-size: 0.8rem; margin-top: 6px; }
"""

_MODAL_SCRIPT = """
document.querySelectorAll(".brief-row").forEach(function (row) {
  row.addEventListener("click", function (event) {
    if (event.target.closest("[data-no-row-click]")) { return; }
    var modal = document.getElementById(row.getAttribute("data-modal-target"));
    if (modal) { modal.showModal(); }
  });
});
document.querySelectorAll(".brief-modal-close").forEach(function (button) {
  button.addEventListener("click", function () {
    button.closest("dialog").close();
  });
});
"""


def _pdf_filename(brief_id):
    return f"brief-{brief_id:04d}.pdf"


def _format_created_at(iso_timestamp):
    return datetime.fromisoformat(iso_timestamp).strftime("%b %d, %Y, %I:%M %p UTC")


def _brief_meta_line(brief):
    total_budget = sum(s["word_budget"] for s in brief["sections"])
    return " &middot; ".join(filter(None, [
        html.escape(brief["content_format"]) if brief.get("content_format") else None,
        f"{brief['target_word_count']} words target ({total_budget} allocated)",
        html.escape(_format_created_at(brief["created_at"])),
    ]))


def _brief_fields(brief):
    return [
        ("Primary keyword", brief["primary_keyword"]),
        ("Secondary keywords", ", ".join(brief["secondary_keywords"]) or "—"),
        ("Target audience", brief.get("target_audience") or "—"),
        ("Search intent", brief.get("search_intent") or "—"),
        ("Tone of voice", brief.get("tone_of_voice") or "—"),
        ("CTA", brief.get("cta") or "—"),
    ]


# --- Live page ---

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


def _render_brief_row(brief):
    modal_id = f"brief-modal-{brief['brief_id']}"
    return f"""
    <div class="brief-row" data-modal-target="{modal_id}">
      <div class="brief-row-main">
        <div class="brief-topic">{html.escape(brief["topic"])}</div>
        <div class="brief-meta">{_brief_meta_line(brief)}</div>
      </div>
      <div class="brief-row-right">
        <span class="status-badge">{html.escape(brief["status"])}</span>
        <a class="btn btn-light" data-no-row-click href="content_briefs/{_pdf_filename(brief['brief_id'])}">{ICON_DOWNLOAD}<span>PDF</span></a>
      </div>
    </div>
    """


def _render_brief_modal(brief):
    modal_id = f"brief-modal-{brief['brief_id']}"
    fields_html = "".join(
        f"<dt>{html.escape(label)}</dt><dd>{html.escape(str(value))}</dd>"
        for label, value in _brief_fields(brief)
    )
    sections_html = "".join(_render_section_item(section) for section in brief["sections"])

    return f"""
    <dialog class="brief-modal" id="{modal_id}">
      <div class="brief-modal-header">
        <div>
          <div class="brief-modal-title">{html.escape(brief["topic"])}</div>
          <div class="brief-modal-meta">{_brief_meta_line(brief)}</div>
        </div>
        <div class="brief-modal-actions">
          <a class="btn btn-light" href="content_briefs/{_pdf_filename(brief['brief_id'])}">{ICON_DOWNLOAD}<span>Download PDF</span></a>
          <button class="btn-icon-close brief-modal-close" type="button" aria-label="Close">&#10005;</button>
        </div>
      </div>
      <div class="brief-modal-body">
        <dl class="brief-field-table">{fields_html}</dl>
        <div class="section-list">{sections_html}</div>
      </div>
    </dialog>
    """


def generate_content_page_html(briefs):
    subtitle_html = f"{len(briefs)} outline(s) created"
    if briefs:
        rows_html = "".join(_render_brief_row(b) for b in briefs)
        modals_html = "".join(_render_brief_modal(b) for b in briefs)
        body = f'<div class="brief-list">{rows_html}</div>{modals_html}'
    else:
        body = '<div class="empty-state">No content outlines yet -- run the /blog-outline skill to create one.</div>'

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
<script>{_MODAL_SCRIPT}</script>
</body>
</html>
"""


# --- Per-brief PDF, plain tables/lists, self-contained (same philosophy as
# the Reporting Hub PDF -- no charts/CDN dependency, safe for an unattended
# Playwright render, and this one specifically needs to be a clean,
# shareable document a writer can open on its own). ---

def _render_section_item_print(section):
    label = section["heading"] or section["level"].capitalize()
    level_tag = "" if section["level"] in ("intro", "conclusion") else section["level"]
    keywords = section.get("keywords") or []
    keywords_line = f'<div class="muted">Keywords: {html.escape(", ".join(keywords))}</div>' if keywords else ""
    notes_line = f'<div class="muted">Note: {html.escape(section["notes"])}</div>' if section.get("notes") else ""
    return f"""
    <div class="section-item">
      <div class="section-item-header">
        {f'<span class="section-level">{html.escape(level_tag)}</span>' if level_tag else ""}
        <strong>{html.escape(label)}</strong>
        <span class="section-budget">{section['word_budget']} words</span>
      </div>
      <div>{html.escape(section.get("points_to_cover") or "")}</div>
      {keywords_line}
      {notes_line}
    </div>
    """


def _generate_brief_print_html(brief):
    fields_rows = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(str(value))}</td></tr>"
        for label, value in _brief_fields(brief)
    )
    sections_html = "".join(_render_section_item_print(section) for section in brief["sections"])

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Content Brief - {html.escape(brief["topic"])}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #ffffff; color: #0b0b0b; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; padding: 24px; }}
  h1 {{ font-size: 1.3rem; margin-bottom: 4px; }}
  header p {{ color: #52514e; margin-top: 0; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 22px; }}
  th, td {{ text-align: left; padding: 7px 10px; font-size: 0.85rem; vertical-align: top; border: 1px solid #cfcec8; }}
  th {{ width: 170px; color: #52514e; font-weight: 600; font-size: 0.72rem; text-transform: uppercase; background: #f6f5f1; }}
  .section-item {{ border: 1px solid #cfcec8; border-radius: 6px; padding: 10px 14px; margin-bottom: 8px; break-inside: avoid; }}
  .section-item-header {{ display: flex; align-items: baseline; gap: 10px; }}
  .section-level {{ color: #7a7a72; font-size: 0.7rem; text-transform: uppercase; font-weight: 700; }}
  .section-budget {{ color: #0a63c9; font-size: 0.8rem; font-weight: 600; margin-left: auto; }}
  .muted {{ color: #52514e; font-size: 0.8rem; margin-top: 4px; }}
</style>
</head>
<body>
  <header>
    <h1>{html.escape(brief["topic"])}</h1>
    <p>{_brief_meta_line(brief)}</p>
  </header>
  <table>{fields_rows}</table>
  <div class="section-list">{sections_html}</div>
</body>
</html>
"""


def _save_brief_pdf(brief, briefs_dir=BRIEFS_PDF_DIR):
    print_html = _generate_brief_print_html(brief)
    briefs_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = briefs_dir / _pdf_filename(brief["brief_id"])

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


def build_and_save_content_page():
    connection = get_connection()
    try:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        briefs = load_all_briefs(connection)

        for brief in briefs:
            _save_brief_pdf(brief)

        content_html = generate_content_page_html(briefs)
        with open(CONTENT_FILE_PATH, "w", encoding="utf-8") as content_file:
            content_file.write(content_html)

        return CONTENT_FILE_PATH
    finally:
        connection.close()


if __name__ == "__main__":
    saved_path = build_and_save_content_page()
    print(f"Content page built: {saved_path}")
