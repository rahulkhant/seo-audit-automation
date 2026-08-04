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

Extended 2026-08-04 for the Writer Agent: if a brief has a saved draft
(content_agent.save_draft), each section shows its written text alongside
the original plan, and a second PDF is generated per draft
(docs/content_drafts/draft-XXXX.pdf) -- unlike the brief's PDF (a
structured spec, rendered as tables), the draft's PDF reads like an actual
article, since the point is handing a finished piece to a human editor,
not a data sheet.

This file does not produce or judge any content itself -- it only reads
what the Outliner/Writer Agents already saved (via content_agent.save_brief
/ content_agent.save_draft) and turns it into something readable, the same
division of labor as Agent 4 for the audit pipeline.
"""

import html
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from content_agent.database import get_connection, load_all_briefs, load_all_drafts_by_brief
from agent4_dashboard.build_dashboard_metronic import (
    ICON_DOWNLOAD,
    MX_RESOLVED_COLOR,
    _render_sidebar_nav,
    _render_topbar,
    _shared_head,
)

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
CONTENT_FILE_PATH = DOCS_DIR / "content.html"
BRIEFS_PDF_DIR = DOCS_DIR / "content_briefs"
DRAFTS_PDF_DIR = DOCS_DIR / "content_drafts"

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
  .section-actual { color: __RESOLVED_COLOR__; font-size: 0.8rem; font-weight: 600; }
  .section-draft { margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--mx-border); }
  .section-draft-label { color: var(--mx-text-gray-500); font-size: 0.7rem; text-transform: uppercase; font-weight: 600; letter-spacing: 0.03em; margin-bottom: 4px; }
  .section-draft-text { font-size: 0.88rem; white-space: pre-wrap; }
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


def _brief_pdf_filename(brief_id):
    return f"brief-{brief_id:04d}.pdf"


def _draft_pdf_filename(brief_id):
    return f"draft-{brief_id:04d}.pdf"


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

def _render_section_item(section, draft_section=None):
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
    actual_words_html = (
        f' &middot; <span class="section-actual">{draft_section["word_count"]} written</span>'
        if draft_section
        else ""
    )
    draft_html = (
        f"""
        <div class="section-draft">
          <div class="section-draft-label">Draft</div>
          <div class="section-draft-text">{html.escape(draft_section["content"])}</div>
        </div>
        """
        if draft_section
        else ""
    )
    return f"""
    <div class="section-item">
      <div class="section-item-header">
        {f'<span class="section-level">{html.escape(level_tag)}</span>' if level_tag else ""}
        <span class="section-heading">{html.escape(label)}</span>
        <span class="section-budget">{section['word_budget']} words{actual_words_html}</span>
      </div>
      <div class="section-points">{html.escape(section.get("points_to_cover") or "")}</div>
      {keywords_html}
      {notes_html}
      {draft_html}
    </div>
    """


def _render_brief_row(brief, draft):
    modal_id = f"brief-modal-{brief['brief_id']}"
    draft_pdf_button = (
        f'<a class="btn btn-light" data-no-row-click href="content_drafts/{_draft_pdf_filename(brief["brief_id"])}">{ICON_DOWNLOAD}<span>Draft</span></a>'
        if draft
        else ""
    )
    return f"""
    <div class="brief-row" data-modal-target="{modal_id}">
      <div class="brief-row-main">
        <div class="brief-topic">{html.escape(brief["topic"])}</div>
        <div class="brief-meta">{_brief_meta_line(brief)}</div>
      </div>
      <div class="brief-row-right">
        <span class="status-badge">{html.escape(brief["status"])}</span>
        <a class="btn btn-light" data-no-row-click href="content_briefs/{_brief_pdf_filename(brief['brief_id'])}">{ICON_DOWNLOAD}<span>Outline</span></a>
        {draft_pdf_button}
      </div>
    </div>
    """


def _render_brief_modal(brief, draft):
    modal_id = f"brief-modal-{brief['brief_id']}"
    fields_html = "".join(
        f"<dt>{html.escape(label)}</dt><dd>{html.escape(str(value))}</dd>"
        for label, value in _brief_fields(brief)
    )
    draft_sections_by_index = draft["sections"] if draft else [None] * len(brief["sections"])
    sections_html = "".join(
        _render_section_item(section, draft_section)
        for section, draft_section in zip(brief["sections"], draft_sections_by_index)
    )
    draft_pdf_button = (
        f'<a class="btn btn-light" href="content_drafts/{_draft_pdf_filename(brief["brief_id"])}">{ICON_DOWNLOAD}<span>Download Draft PDF</span></a>'
        if draft
        else ""
    )

    return f"""
    <dialog class="brief-modal" id="{modal_id}">
      <div class="brief-modal-header">
        <div>
          <div class="brief-modal-title">{html.escape(brief["topic"])}</div>
          <div class="brief-modal-meta">{_brief_meta_line(brief)}</div>
        </div>
        <div class="brief-modal-actions">
          <a class="btn btn-light" href="content_briefs/{_brief_pdf_filename(brief['brief_id'])}">{ICON_DOWNLOAD}<span>Download Outline PDF</span></a>
          {draft_pdf_button}
          <button class="btn-icon-close brief-modal-close" type="button" aria-label="Close">&#10005;</button>
        </div>
      </div>
      <div class="brief-modal-body">
        <dl class="brief-field-table">{fields_html}</dl>
        <div class="section-list">{sections_html}</div>
      </div>
    </dialog>
    """


def generate_content_page_html(briefs, drafts_by_brief):
    subtitle_html = f"{len(briefs)} outline(s) created"
    if briefs:
        rows_html = "".join(_render_brief_row(b, drafts_by_brief.get(b["brief_id"])) for b in briefs)
        modals_html = "".join(_render_brief_modal(b, drafts_by_brief.get(b["brief_id"])) for b in briefs)
        body = f'<div class="brief-list">{rows_html}</div>{modals_html}'
    else:
        body = '<div class="empty-state">No content outlines yet -- run the /blog-outline skill to create one.</div>'

    return f"""<!doctype html>
<html lang="en">
<head>
{_shared_head("Content Outlines")}
<style>{_CONTENT_PAGE_STYLE.replace("__RESOLVED_COLOR__", MX_RESOLVED_COLOR)}</style>
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
    pdf_path = briefs_dir / _brief_pdf_filename(brief["brief_id"])

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


# --- Per-draft PDF: unlike the brief's PDF (a structured spec, rendered as
# tables), this one is meant to read like an actual article -- real
# headings, real paragraphs -- since the whole point is handing a finished
# draft to a human editor/writer to read and mark up, not a data sheet. ---

_DRAFT_HEADING_TAG = {"H2": "h2", "H3": "h3", "H4": "h4"}


def _render_draft_section_print(section):
    heading = section.get("heading")
    heading_html = ""
    if heading:
        tag = _DRAFT_HEADING_TAG.get(section["level"], "h2")
        heading_html = f"<{tag}>{html.escape(heading)}</{tag}>"
    paragraphs_html = "".join(
        f"<p>{html.escape(paragraph)}</p>"
        for paragraph in section["content"].split("\n\n")
        if paragraph.strip()
    )
    return f"{heading_html}{paragraphs_html}"


def _generate_draft_print_html(brief, draft):
    total_words = sum(section["word_count"] for section in draft["sections"])
    body_html = "".join(_render_draft_section_print(section) for section in draft["sections"])

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(brief["topic"])}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: #ffffff; color: #14140f; padding: 40px 56px; max-width: 720px;
    font-family: Georgia, "Times New Roman", serif; line-height: 1.6; font-size: 0.98rem;
  }}
  h1 {{ font-family: system-ui, -apple-system, sans-serif; font-size: 1.7rem; margin-bottom: 6px; }}
  header p {{ font-family: system-ui, -apple-system, sans-serif; color: #6b6a63; font-size: 0.85rem; margin-top: 0; margin-bottom: 32px; }}
  h2 {{ font-family: system-ui, -apple-system, sans-serif; font-size: 1.25rem; margin: 32px 0 10px; }}
  h3 {{ font-family: system-ui, -apple-system, sans-serif; font-size: 1.08rem; margin: 26px 0 8px; }}
  h4 {{ font-family: system-ui, -apple-system, sans-serif; font-size: 0.98rem; margin: 22px 0 6px; }}
  p {{ margin: 0 0 14px; }}
</style>
</head>
<body>
  <header>
    <h1>{html.escape(brief["topic"])}</h1>
    <p>{total_words} words &middot; draft generated {html.escape(_format_created_at(draft["created_at"]))}</p>
  </header>
  {body_html}
</body>
</html>
"""


def _save_draft_pdf(brief, draft, drafts_dir=DRAFTS_PDF_DIR):
    print_html = _generate_draft_print_html(brief, draft)
    drafts_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = drafts_dir / _draft_pdf_filename(brief["brief_id"])

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
        drafts_by_brief = load_all_drafts_by_brief(connection)

        for brief in briefs:
            _save_brief_pdf(brief)
            draft = drafts_by_brief.get(brief["brief_id"])
            if draft:
                _save_draft_pdf(brief, draft)

        content_html = generate_content_page_html(briefs, drafts_by_brief)
        with open(CONTENT_FILE_PATH, "w", encoding="utf-8") as content_file:
            content_file.write(content_html)

        return CONTENT_FILE_PATH
    finally:
        connection.close()


if __name__ == "__main__":
    saved_path = build_and_save_content_page()
    print(f"Content page built: {saved_path}")
