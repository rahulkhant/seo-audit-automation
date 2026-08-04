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

The one table (for now)
------------------------
"content_briefs" -- one row per outline produced by the Outliner Agent.
The full section-by-section breakdown (headings, word budgets, points to
cover, keyword mapping) is stored as JSON in one column, the same pattern
Agent 2 already uses for nested audit data (images, links, etc.) that
doesn't fit neatly into flat columns.

"status" exists now so the Writer and QA Checker agents (not built yet)
have somewhere to record progress against the same row later, instead of
needing a schema change when they arrive.
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

    -- "outlined" is the only stage that exists today. "drafted" and
    -- "qa_reviewed" are reserved for the Writer and QA Checker agents.
    status TEXT NOT NULL DEFAULT 'outlined'
)
"""


def get_connection(db_path=None):
    """Same physical database file as the SEO audit (agent2_storage), with
    the content_briefs table created if it doesn't exist yet. `db_path` is
    an override for testing only -- normal use always shares the one real
    database file."""
    connection = _get_audit_connection(db_path) if db_path else _get_audit_connection()
    connection.execute(CREATE_CONTENT_BRIEFS_TABLE_SQL)
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
