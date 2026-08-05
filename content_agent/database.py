"""
Content Agent: Storage.

Purpose of this file
--------------------
The Outliner Agent (and later the Writer and QA Checker agents) needs
somewhere permanent to save its work, the same way the SEO audit's Agent 2
saves crawl results. Rather than inventing a second database file, this
reuses the exact same SQLite file (agent2_storage.get_connection()) --
one database for the whole platform -- but owns its own table, kept
separate from the audit's runs/pages/findings tables so the two modules
stay independently replaceable, per the project's modular-design principle.

The tables
----------
"content_briefs" -- one row per outline produced by the Outliner Agent.
The full section-by-section breakdown (headings, word budgets, points to
cover, keyword mapping) is stored as JSON in one column, the same pattern
Agent 2 already uses for nested audit data (images, links, etc.) that
doesn't fit neatly into flat columns.

"content_drafts" -- one row per brief's written draft (Writer Agent).
Overwrite-only by design (per Rahul, 2026-08-04): brief_id is UNIQUE, so
saving a new draft for the same brief replaces the old one rather than
keeping version history -- simpler for now, revisit only if that turns
out to actually be needed. "status" on content_briefs moves to "drafted"
once a draft exists, so the Content page can show progress without a
second lookup.

"content_qa_reviews" -- one row per brief's QA report (QA Checker Agent),
same overwrite-only pattern as drafts. Stores the full itemized report
(word count, keyword coverage/density, readability, sentence complexity,
passive voice, banned-phrase hits -- all computed fresh by
content_agent/qa_checks.py at save time, never trusted from the skill
conversation) plus the skill's own judgment_adjustment/judgment_notes and
the combined score. Status moves to "qa_reviewed".
"""

import json
from datetime import datetime, timezone

from agent2_storage.database import get_connection as _get_audit_connection

CREATE_CONTENT_BRIEFS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS content_briefs (
    brief_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,

    topic TEXT NOT NULL,
    primary_keyword TEXT NOT NULL,
    secondary_keywords_json TEXT,
    content_format TEXT,
    target_word_count INTEGER,
    target_audience TEXT,
    search_intent TEXT,
    tone_of_voice TEXT,
    cta TEXT,
    other_notes TEXT,

    sections_json TEXT NOT NULL,

    status TEXT NOT NULL DEFAULT 'outlined'
)
"""

CREATE_CONTENT_DRAFTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS content_drafts (
    draft_id INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id INTEGER NOT NULL UNIQUE REFERENCES content_briefs(brief_id),
    created_at TEXT NOT NULL,

    -- [{"heading": ..., "level": ..., "content": "...", "word_count": N}, ...]
    -- word_count is a plain len(content.split()) count, computed once at
    -- save time -- deterministic, not the model's own claim about itself.
    sections_json TEXT NOT NULL
)
"""

CREATE_CONTENT_QA_REVIEWS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS content_qa_reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id INTEGER NOT NULL UNIQUE REFERENCES content_briefs(brief_id),
    created_at TEXT NOT NULL,

    score REAL NOT NULL,
    -- {"deterministic": {...run_deterministic_checks() output...},
    --  "deductions": [...], "judgment_adjustment": N, "judgment_notes": "..."}
    report_json TEXT NOT NULL
)
"""


def get_connection(db_path=None):
    """Same physical database file as the SEO audit (agent2_storage), with
    the content_briefs table created if it doesn't exist yet. `db_path` is
    an override for testing only -- normal use always shares the one real
    database file."""
    connection = _get_audit_connection(db_path) if db_path else _get_audit_connection()
    connection.execute(CREATE_CONTENT_BRIEFS_TABLE_SQL)
    connection.execute(CREATE_CONTENT_DRAFTS_TABLE_SQL)
    connection.execute(CREATE_CONTENT_QA_REVIEWS_TABLE_SQL)
    connection.commit()
    return connection


def save_brief(connection, brief):
    """
    Saves one completed outline. `brief` is a plain dict with the shape
    produced by the Outliner Agent (see .claude/skills/blog-outline/SKILL.md):

        {
            "topic": "...", "primary_keyword": "...",
            "secondary_keywords": [...], "content_format": "...",
            "target_word_count": 1200, "target_audience": "...",
            "search_intent": "...", "tone_of_voice": "...", "cta": "...",
            "other_notes": "...",
            "sections": [
                {"heading": "...", "level": "H2", "word_budget": 180,
                 "points_to_cover": "...", "keywords": [...], "notes": "..."},
                ...
            ],
        }

    Returns the new brief_id.
    """
    created_at = datetime.now(timezone.utc).isoformat()

    cursor = connection.execute(
        """
        INSERT INTO content_briefs (
            created_at, topic, primary_keyword, secondary_keywords_json,
            content_format, target_word_count, target_audience,
            search_intent, tone_of_voice, cta, other_notes, sections_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            created_at,
            brief["topic"],
            brief["primary_keyword"],
            json.dumps(brief.get("secondary_keywords") or []),
            brief.get("content_format"),
            brief.get("target_word_count"),
            brief.get("target_audience"),
            brief.get("search_intent"),
            brief.get("tone_of_voice"),
            brief.get("cta"),
            brief.get("other_notes"),
            json.dumps(brief["sections"]),
        ),
    )
    connection.commit()
    return cursor.lastrowid


def load_all_briefs(connection):
    """All briefs, newest first -- same ordering convention as
    agent4_dashboard.build_dashboard.load_all_runs."""
    rows = connection.execute(
        "SELECT * FROM content_briefs ORDER BY brief_id DESC"
    ).fetchall()

    briefs = []
    for row in rows:
        brief = dict(row)
        brief["secondary_keywords"] = json.loads(brief["secondary_keywords_json"] or "[]")
        brief["sections"] = json.loads(brief["sections_json"])
        briefs.append(brief)
    return briefs


def load_brief(connection, brief_id):
    """One brief by id, or None -- used by the Writer Agent to load the
    spec it's writing from."""
    row = connection.execute(
        "SELECT * FROM content_briefs WHERE brief_id = ?", (brief_id,)
    ).fetchone()
    if row is None:
        return None
    brief = dict(row)
    brief["secondary_keywords"] = json.loads(brief["secondary_keywords_json"] or "[]")
    brief["sections"] = json.loads(brief["sections_json"])
    return brief


def save_draft(connection, brief_id, sections):
    """
    Saves (or overwrites -- see module docstring) the draft for one brief.
    `sections` is a list of {"heading", "level", "content", "word_count"}
    dicts, one per section in the brief's own order. Also flips the
    brief's status to "drafted".

    Returns the draft_id.
    """
    created_at = datetime.now(timezone.utc).isoformat()

    connection.execute(
        """
        INSERT INTO content_drafts (brief_id, created_at, sections_json)
        VALUES (?, ?, ?)
        ON CONFLICT(brief_id) DO UPDATE SET
            created_at = excluded.created_at,
            sections_json = excluded.sections_json
        """,
        (brief_id, created_at, json.dumps(sections)),
    )
    connection.execute(
        "UPDATE content_briefs SET status = 'drafted' WHERE brief_id = ?", (brief_id,)
    )
    connection.commit()

    # cursor.lastrowid is not reliable here: on the ON CONFLICT DO UPDATE
    # path SQLite doesn't update last_insert_rowid(), so it could silently
    # return a stale id from an unrelated earlier insert on this same
    # connection. brief_id is UNIQUE, so just look the row up directly.
    row = connection.execute(
        "SELECT draft_id FROM content_drafts WHERE brief_id = ?", (brief_id,)
    ).fetchone()
    return row["draft_id"]


def load_draft_for_brief(connection, brief_id):
    """The one draft for a brief, or None if it hasn't been written yet."""
    row = connection.execute(
        "SELECT * FROM content_drafts WHERE brief_id = ?", (brief_id,)
    ).fetchone()
    if row is None:
        return None
    draft = dict(row)
    draft["sections"] = json.loads(draft["sections_json"])
    return draft


def load_all_drafts_by_brief(connection):
    """{brief_id: draft} for every draft that exists -- lets the dashboard
    look up a brief's draft (if any) without a query per row."""
    rows = connection.execute("SELECT * FROM content_drafts").fetchall()
    drafts = {}
    for row in rows:
        draft = dict(row)
        draft["sections"] = json.loads(draft["sections_json"])
        drafts[draft["brief_id"]] = draft
    return drafts


def save_qa_review(connection, brief_id, score, report):
    """
    Saves (or overwrites -- same pattern as save_draft) the QA report for
    one brief. `report` is the full report dict (deterministic checks +
    deductions + judgment_adjustment/judgment_notes) produced by
    content_agent.save_qa_review's CLI, not raw model output. Also flips
    the brief's status to "qa_reviewed".

    Returns the review_id.
    """
    created_at = datetime.now(timezone.utc).isoformat()

    connection.execute(
        """
        INSERT INTO content_qa_reviews (brief_id, created_at, score, report_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(brief_id) DO UPDATE SET
            created_at = excluded.created_at,
            score = excluded.score,
            report_json = excluded.report_json
        """,
        (brief_id, created_at, score, json.dumps(report)),
    )
    connection.execute(
        "UPDATE content_briefs SET status = 'qa_reviewed' WHERE brief_id = ?", (brief_id,)
    )
    connection.commit()

    # Same lastrowid caveat as save_draft -- look the row up directly
    # rather than trusting cursor.lastrowid on the ON CONFLICT DO UPDATE path.
    row = connection.execute(
        "SELECT review_id FROM content_qa_reviews WHERE brief_id = ?", (brief_id,)
    ).fetchone()
    return row["review_id"]


def load_qa_review_for_brief(connection, brief_id):
    """The one QA review for a brief, or None if it hasn't been reviewed yet."""
    row = connection.execute(
        "SELECT * FROM content_qa_reviews WHERE brief_id = ?", (brief_id,)
    ).fetchone()
    if row is None:
        return None
    review = dict(row)
    review["report"] = json.loads(review["report_json"])
    return review


def load_all_qa_reviews_by_brief(connection):
    """{brief_id: review} for every QA review that exists."""
    rows = connection.execute("SELECT * FROM content_qa_reviews").fetchall()
    reviews = {}
    for row in rows:
        review = dict(row)
        review["report"] = json.loads(review["report_json"])
        reviews[review["brief_id"]] = review
    return reviews
