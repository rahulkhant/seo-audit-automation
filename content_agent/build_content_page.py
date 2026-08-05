"""
Content Agent: dashboard page.

Purpose of this file
--------------------
Builds docs/content.html -- everything the Content Agent has produced,
using the same Metronic shell (sidebar, topbar, card styling) as the SEO
audit's dashboard pages, so the whole platform reads as one system rather
than a bolted-on second app.

Redesigned 2026-08-05 (per Rahul's request, now that all three agents
exist) into three tabs -- Outline / Draft / QA Checker -- switched
client-side, no page reload. Each tab lists every brief with its own
per-stage view (a brief with no draft yet shows a "not drafted" placeholder
in the Draft tab rather than being hidden, so it's obvious at a glance
where every piece of content actually stands). Clicking a real card in any
tab opens the same scrollable <dialog> modal pattern -- reused identically
across all three tabs, per Rahul's explicit ask for one consistent format.

Generates one PDF per brief per stage it's reached:
  - docs/content_briefs/brief-XXXX.pdf  (structured spec, tables)
  - docs/content_drafts/draft-XXXX.pdf  (reads like an article)
  - docs/content_qa/qa-XXXX.pdf         (the full QA report)

This file does not produce or judge any content itself -- it only reads
what the Outliner/Writer/QA Checker agents already saved and turns it
into something readable, the same division of labor as Agent 4 for the
audit pipeline.
"""

import html
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from content_agent.database import (
    get_connection,
    load_all_briefs,
    load_all_drafts_by_brief,
    load_all_qa_reviews_by_brief,
)
from agent4_dashboard.build_dashboard_metronic import (
    ICON_DOWNLOAD,
    MX_RESOLVED_COLOR,
    MX_SEVERITY,
    _render_sidebar_nav,
    _render_topbar,
    _shared_head,
)

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
CONTENT_FILE_PATH = DOCS_DIR / "content.html"
BRIEFS_PDF_DIR = DOCS_DIR / "content_briefs"
DRAFTS_PDF_DIR = DOCS_DIR / "content_drafts"
QA_PDF_DIR = DOCS_DIR / "content_qa"

_CONTENT_PAGE_STYLE = """
  .tabs { display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 1px solid var(--mx-border); }
  .tab-button {
    padding: 10px 18px; border: none; background: transparent; font-family: inherit; font-size: 0.9rem;
    font-weight: 600; color: var(--mx-text-gray-600); cursor: pointer; border-bottom: 2px solid transparent;
    margin-bottom: -1px;
  }
  .tab-button:hover { color: var(--mx-text-dark); }
  .tab-button.active { color: var(--mx-primary); border-bottom-color: var(--mx-primary); }
  .tab-panel[hidden] { display: none; }

  .brief-list { display: flex; flex-direction: column; gap: 10px; }
  .brief-row {
    background: var(--mx-card-bg); border: 1px solid var(--mx-border); border-radius: 10px;
    padding: 16px 20px; display: flex; align-items: center; justify-content: space-between;
    gap: 16px; cursor: pointer;
  }
  .brief-row:hover { border-color: var(--mx-primary); }
  .pending-row {
    background: var(--mx-card-bg); border: 1px dashed var(--mx-border); border-radius: 10px;
    padding: 16px 20px; display: flex; align-items: center; justify-content: space-between;
    gap: 16px; color: var(--mx-text-gray-500);
  }
  .brief-row-main, .pending-row-main { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .brief-topic { font-weight: 700; font-size: 0.98rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .brief-meta, .pending-meta { color: var(--mx-text-gray-600); font-size: 0.83rem; }
  .brief-row-right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
  .status-badge {
    display: inline-flex; align-items: center; padding: 5px 12px; border-radius: 999px;
    font-weight: 600; font-size: 0.78rem; color: var(--mx-primary);
    background-color: var(--mx-primary-light); white-space: nowrap;
  }
  .score-badge {
    display: inline-flex; align-items: center; padding: 5px 12px; border-radius: 999px;
    font-weight: 700; font-size: 0.85rem; color: var(--score-color);
    background-color: color-mix(in srgb, var(--score-color) 15%, transparent); white-space: nowrap;
  }
  .empty-state { color: var(--mx-text-gray-600); font-size: 0.9rem; padding: 40px 0; text-align: center; }

  /* Base rule intentionally does NOT set "display" -- the browser's own
     "dialog:not([open]) { display: none; }" default has to stay in charge
     while a dialog is closed. Scoped to [open] so closed dialogs stay
     properly hidden (see git history for why this matters). */
  dialog.brief-modal[open] {
    position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); margin: 0;
    width: min(720px, 92vw); max-height: 82vh; padding: 0; border: none; border-radius: 14px;
    background: var(--mx-card-bg); color: var(--mx-text-dark); display: flex; flex-direction: column;
  }
  dialog.brief-modal::backdrop { background: rgba(15, 15, 20, 0.55); }
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

  dl.brief-field-table { display: grid; grid-template-columns: 190px 1fr; row-gap: 10px; column-gap: 16px; margin: 0 0 22px; font-size: 0.88rem; }
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

  .draft-article h2 { font-size: 1.1rem; margin: 28px 0 8px; }
  .draft-article h3 { font-size: 1.02rem; margin: 24px 0 6px; }
  .draft-article h4 { font-size: 0.94rem; margin: 20px 0 6px; }
  .draft-article p { font-size: 0.9rem; line-height: 1.6; margin: 0 0 12px; }

  .qa-score-hero { display: flex; align-items: baseline; gap: 8px; margin-bottom: 4px; }
  .qa-score-value { font-size: 2.2rem; font-weight: 800; color: var(--score-color); }
  .qa-score-value span { font-size: 1.1rem; font-weight: 600; color: var(--mx-text-gray-500); }
  .qa-section-title { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.03em; font-weight: 600; color: var(--mx-text-gray-500); margin: 20px 0 8px; }
  .qa-deductions-list, .qa-notes { font-size: 0.87rem; }
  .qa-deductions-list ul { margin: 0; padding-left: 18px; }
  .qa-deductions-list li { margin-bottom: 4px; }
  .qa-clean { color: __RESOLVED_COLOR__; font-weight: 600; font-size: 0.87rem; }
"""

_CONTENT_PAGE_SCRIPT = """
document.querySelectorAll(".tab-button").forEach(function (button) {
  button.addEventListener("click", function () {
    document.querySelectorAll(".tab-button").forEach(function (b) { b.classList.remove("active"); });
    document.querySelectorAll(".tab-panel").forEach(function (p) { p.hidden = true; });
    button.classList.add("active");
    document.getElementById("tab-panel-" + button.dataset.tab).hidden = false;
  });
});
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


def _qa_pdf_filename(brief_id):
    return f"qa-{brief_id:04d}.pdf"


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


# Shared by the on-page draft article view and the draft PDF, so a
# section's heading renders as the same real HTML heading level in both
# places rather than two independently-maintained mappings.
_DRAFT_HEADING_TAG = {"H2": "h2", "H3": "h3", "H4": "h4"}


def _render_draft_section_html(section):
    """Renders one draft section as real heading + paragraph tags --
    shared building block for both the on-page modal and the print PDF,
    which differ only in surrounding page chrome/CSS, not this part."""
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


def _format_status(status):
    """'qa_reviewed' -> 'QA Reviewed' -- CSS text-transform:capitalize only
    handles the first letter of the whole string, so a raw snake_case
    status like this would otherwise render as 'Qa_reviewed'."""
    words = status.split("_")
    return " ".join("QA" if word == "qa" else word.capitalize() for word in words)


def _flesch_label(score):
    if score >= 90:
        return "Very easy"
    if score >= 80:
        return "Easy"
    if score >= 70:
        return "Fairly easy"
    if score >= 60:
        return "Plain English"
    if score >= 50:
        return "Fairly difficult"
    if score >= 30:
        return "Difficult"
    return "Very difficult"


def _score_color(score):
    if score >= 8:
        return MX_RESOLVED_COLOR
    if score >= 6:
        return MX_SEVERITY["warning"]["color"]
    return MX_SEVERITY["critical"]["color"]


# --- Tabs (live page) ---

def _render_pending_row(topic, message):
    return f"""
    <div class="pending-row">
      <div class="pending-row-main">
        <div class="brief-topic">{html.escape(topic)}</div>
        <div class="pending-meta">{html.escape(message)}</div>
      </div>
    </div>
    """


# -- Outline tab --

def _render_outline_section_item(section):
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


def _render_outline_row(brief):
    modal_id = f"outline-modal-{brief['brief_id']}"
    return f"""
    <div class="brief-row" data-modal-target="{modal_id}">
      <div class="brief-row-main">
        <div class="brief-topic">{html.escape(brief["topic"])}</div>
        <div class="brief-meta">{_brief_meta_line(brief)}</div>
      </div>
      <div class="brief-row-right">
        <span class="status-badge">{html.escape(_format_status(brief["status"]))}</span>
        <a class="btn btn-light" data-no-row-click href="content_briefs/{_brief_pdf_filename(brief['brief_id'])}">{ICON_DOWNLOAD}<span>PDF</span></a>
      </div>
    </div>
    """


def _render_outline_modal(brief):
    modal_id = f"outline-modal-{brief['brief_id']}"
    fields_html = "".join(
        f"<dt>{html.escape(label)}</dt><dd>{html.escape(str(value))}</dd>"
        for label, value in _brief_fields(brief)
    )
    sections_html = "".join(_render_outline_section_item(section) for section in brief["sections"])

    return f"""
    <dialog class="brief-modal" id="{modal_id}">
      <div class="brief-modal-header">
        <div>
          <div class="brief-modal-title">{html.escape(brief["topic"])}</div>
          <div class="brief-modal-meta">{_brief_meta_line(brief)}</div>
        </div>
        <div class="brief-modal-actions">
          <a class="btn btn-light" href="content_briefs/{_brief_pdf_filename(brief['brief_id'])}">{ICON_DOWNLOAD}<span>Download PDF</span></a>
          <button class="btn-icon-close brief-modal-close" type="button" aria-label="Close">&#10005;</button>
        </div>
      </div>
      <div class="brief-modal-body">
        <dl class="brief-field-table">{fields_html}</dl>
        <div class="section-list">{sections_html}</div>
      </div>
    </dialog>
    """


# -- Draft tab --

def _render_draft_row(brief, draft):
    if draft is None:
        return _render_pending_row(brief["topic"], "Not drafted yet -- run /blog-write")

    total_words = sum(s["word_count"] for s in draft["sections"])
    modal_id = f"draft-modal-{brief['brief_id']}"
    meta = f"{total_words} words (target {brief['target_word_count']}) &middot; {html.escape(_format_created_at(draft['created_at']))}"
    return f"""
    <div class="brief-row" data-modal-target="{modal_id}">
      <div class="brief-row-main">
        <div class="brief-topic">{html.escape(brief["topic"])}</div>
        <div class="brief-meta">{meta}</div>
      </div>
      <div class="brief-row-right">
        <a class="btn btn-light" data-no-row-click href="content_drafts/{_draft_pdf_filename(brief['brief_id'])}">{ICON_DOWNLOAD}<span>PDF</span></a>
      </div>
    </div>
    """


def _render_draft_modal(brief, draft):
    if draft is None:
        return ""
    total_words = sum(s["word_count"] for s in draft["sections"])
    modal_id = f"draft-modal-{brief['brief_id']}"
    meta = f"{total_words} words (target {brief['target_word_count']}) &middot; {html.escape(_format_created_at(draft['created_at']))}"
    article_html = "".join(_render_draft_section_html(section) for section in draft["sections"])

    return f"""
    <dialog class="brief-modal" id="{modal_id}">
      <div class="brief-modal-header">
        <div>
          <div class="brief-modal-title">{html.escape(brief["topic"])}</div>
          <div class="brief-modal-meta">{meta}</div>
        </div>
        <div class="brief-modal-actions">
          <a class="btn btn-light" href="content_drafts/{_draft_pdf_filename(brief['brief_id'])}">{ICON_DOWNLOAD}<span>Download PDF</span></a>
          <button class="btn-icon-close brief-modal-close" type="button" aria-label="Close">&#10005;</button>
        </div>
      </div>
      <div class="brief-modal-body">
        <div class="draft-article">{article_html}</div>
      </div>
    </dialog>
    """


# -- QA Checker tab --

def _render_qa_row(brief, review):
    if review is None:
        return _render_pending_row(brief["topic"], "Not reviewed yet -- run /blog-qa")

    modal_id = f"qa-modal-{brief['brief_id']}"
    color = _score_color(review["score"])
    meta = html.escape(_format_created_at(review["created_at"]))
    return f"""
    <div class="brief-row" data-modal-target="{modal_id}">
      <div class="brief-row-main">
        <div class="brief-topic">{html.escape(brief["topic"])}</div>
        <div class="brief-meta">{meta}</div>
      </div>
      <div class="brief-row-right">
        <span class="score-badge" style="--score-color: {color}">{review['score']}/10</span>
        <a class="btn btn-light" data-no-row-click href="content_qa/{_qa_pdf_filename(brief['brief_id'])}">{ICON_DOWNLOAD}<span>PDF</span></a>
      </div>
    </div>
    """


def _qa_report_fields(report):
    det = report["deterministic"]
    wc = det["word_count"]
    kw = det["keyword_coverage"]
    density = det["keyword_density"]
    readability = det["readability"]
    complexity = det["sentence_complexity"]
    passive = det["passive_voice"]
    banned = det["banned_phrases"]

    missing_kw = len(kw["section_keyword_misses"])
    banned_summary = (
        ", ".join(f'"{phrase}" x{count}' for phrase, count in banned.items())
        if banned
        else "None found"
    )

    return [
        ("Word count", f"{wc['actual']} / {wc['target']} target ({wc['deviation_pct']}% off)"),
        ("Keyword coverage", f"{missing_kw} section keyword(s) missing" if missing_kw else "All assigned keywords present"),
        ("Primary keyword placement", "Intro + conclusion ✓" if kw["primary_keyword_in_intro"] and kw["primary_keyword_in_conclusion"] else "Missing from intro and/or conclusion"),
        ("Primary keyword density", f"{density['primary_density_pct']}% ({density['primary_keyword_count']} occurrences)"),
        ("Readability (Flesch Reading Ease)", f"{readability['flesch_reading_ease']} — {_flesch_label(readability['flesch_reading_ease'])}"),
        ("Avg. sentence length", f"{complexity['avg_sentence_length']} words (σ {complexity['sentence_length_stdev']})"),
        ("Passive voice", f"{passive['percentage']}% of sentences"),
        ("Banned phrases found", banned_summary),
    ]


def _render_qa_modal(brief, review):
    if review is None:
        return ""
    modal_id = f"qa-modal-{brief['brief_id']}"
    report = review["report"]
    color = _score_color(review["score"])
    meta = html.escape(_format_created_at(review["created_at"]))

    fields_html = "".join(
        f"<dt>{html.escape(label)}</dt><dd>{html.escape(str(value))}</dd>"
        for label, value in _qa_report_fields(report)
    )

    deductions = report.get("deductions") or []
    deductions_html = (
        f'<ul>{"".join(f"<li>{html.escape(d)}</li>" for d in deductions)}</ul>'
        if deductions
        else '<div class="qa-clean">No deductions — clean pass.</div>'
    )

    judgment_notes = report.get("judgment_notes") or "—"

    return f"""
    <dialog class="brief-modal" id="{modal_id}">
      <div class="brief-modal-header">
        <div>
          <div class="brief-modal-title">{html.escape(brief["topic"])}</div>
          <div class="brief-modal-meta">{meta}</div>
        </div>
        <div class="brief-modal-actions">
          <a class="btn btn-light" href="content_qa/{_qa_pdf_filename(brief['brief_id'])}">{ICON_DOWNLOAD}<span>Download PDF</span></a>
          <button class="btn-icon-close brief-modal-close" type="button" aria-label="Close">&#10005;</button>
        </div>
      </div>
      <div class="brief-modal-body">
        <div class="qa-score-hero"><span class="qa-score-value" style="--score-color: {color}">{review['score']}<span>/10</span></span></div>
        <dl class="brief-field-table">{fields_html}</dl>
        <div class="qa-section-title">Deductions</div>
        <div class="qa-deductions-list">{deductions_html}</div>
        <div class="qa-section-title">Judgment Notes</div>
        <div class="qa-notes">{html.escape(judgment_notes)}</div>
      </div>
    </dialog>
    """


def generate_content_page_html(briefs, drafts_by_brief, qa_reviews_by_brief):
    subtitle_html = f"{len(briefs)} outline(s) created"

    if not briefs:
        body = '<div class="empty-state">No content outlines yet -- run the /blog-outline skill to create one.</div>'
    else:
        outline_rows = "".join(_render_outline_row(b) for b in briefs)
        outline_modals = "".join(_render_outline_modal(b) for b in briefs)

        draft_rows = "".join(_render_draft_row(b, drafts_by_brief.get(b["brief_id"])) for b in briefs)
        draft_modals = "".join(
            _render_draft_modal(b, drafts_by_brief.get(b["brief_id"])) for b in briefs
        )

        qa_rows = "".join(_render_qa_row(b, qa_reviews_by_brief.get(b["brief_id"])) for b in briefs)
        qa_modals = "".join(
            _render_qa_modal(b, qa_reviews_by_brief.get(b["brief_id"])) for b in briefs
        )

        body = f"""
        <div class="tabs">
          <button class="tab-button active" data-tab="outline">Outline</button>
          <button class="tab-button" data-tab="draft">Draft</button>
          <button class="tab-button" data-tab="qa">QA Checker</button>
        </div>
        <div class="tab-panel" id="tab-panel-outline">
          <div class="brief-list">{outline_rows}</div>
        </div>
        <div class="tab-panel" id="tab-panel-draft" hidden>
          <div class="brief-list">{draft_rows}</div>
        </div>
        <div class="tab-panel" id="tab-panel-qa" hidden>
          <div class="brief-list">{qa_rows}</div>
        </div>
        {outline_modals}{draft_modals}{qa_modals}
        """

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
<script>{_CONTENT_PAGE_SCRIPT}</script>
</body>
</html>
"""


# --- PDFs: plain HTML/CSS, self-contained, no charts/CDN dependency
# (same philosophy as the Reporting Hub's PDF) ---

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


def _generate_draft_print_html(brief, draft):
    total_words = sum(section["word_count"] for section in draft["sections"])
    body_html = "".join(_render_draft_section_html(section) for section in draft["sections"])

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


def _generate_qa_print_html(brief, review):
    report = review["report"]
    color = _score_color(review["score"])
    fields_rows = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(str(value))}</td></tr>"
        for label, value in _qa_report_fields(report)
    )
    deductions = report.get("deductions") or []
    deductions_html = (
        "".join(f"<li>{html.escape(d)}</li>" for d in deductions)
        if deductions
        else "<li>No deductions — clean pass.</li>"
    )
    judgment_notes = report.get("judgment_notes") or "—"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>QA Report - {html.escape(brief["topic"])}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #ffffff; color: #0b0b0b; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; padding: 24px; }}
  h1 {{ font-size: 1.3rem; margin-bottom: 4px; }}
  h2 {{ font-size: 1rem; margin: 26px 0 8px; }}
  header p {{ color: #52514e; margin-top: 0; }}
  .score {{ font-size: 2.4rem; font-weight: 800; color: {color}; margin-bottom: 16px; }}
  .score span {{ font-size: 1.1rem; color: #52514e; font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 8px; }}
  th, td {{ text-align: left; padding: 7px 10px; font-size: 0.85rem; vertical-align: top; border: 1px solid #cfcec8; }}
  th {{ width: 220px; color: #52514e; font-weight: 600; font-size: 0.72rem; text-transform: uppercase; background: #f6f5f1; }}
  ul {{ margin: 0; padding-left: 20px; font-size: 0.87rem; }}
  li {{ margin-bottom: 4px; }}
  p.notes {{ font-size: 0.87rem; }}
</style>
</head>
<body>
  <header>
    <h1>{html.escape(brief["topic"])}</h1>
    <p>QA report &middot; reviewed {html.escape(_format_created_at(review["created_at"]))}</p>
  </header>
  <div class="score">{review['score']}<span>/10</span></div>
  <table>{fields_rows}</table>
  <h2>Deductions</h2>
  <ul>{deductions_html}</ul>
  <h2>Judgment Notes</h2>
  <p class="notes">{html.escape(judgment_notes)}</p>
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


def build_and_save_content_page():
    connection = get_connection()
    try:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        briefs = load_all_briefs(connection)
        drafts_by_brief = load_all_drafts_by_brief(connection)
        qa_reviews_by_brief = load_all_qa_reviews_by_brief(connection)

        for brief in briefs:
            _render_pdf(_generate_brief_print_html(brief), BRIEFS_PDF_DIR / _brief_pdf_filename(brief["brief_id"]))

            draft = drafts_by_brief.get(brief["brief_id"])
            if draft:
                _render_pdf(
                    _generate_draft_print_html(brief, draft),
                    DRAFTS_PDF_DIR / _draft_pdf_filename(brief["brief_id"]),
                )

            review = qa_reviews_by_brief.get(brief["brief_id"])
            if review:
                _render_pdf(
                    _generate_qa_print_html(brief, review),
                    QA_PDF_DIR / _qa_pdf_filename(brief["brief_id"]),
                )

        content_html = generate_content_page_html(briefs, drafts_by_brief, qa_reviews_by_brief)
        with open(CONTENT_FILE_PATH, "w", encoding="utf-8") as content_file:
            content_file.write(content_html)

        return CONTENT_FILE_PATH
    finally:
        connection.close()


if __name__ == "__main__":
    saved_path = build_and_save_content_page()
    print(f"Content page built: {saved_path}")
