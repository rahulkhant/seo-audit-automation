"""
Keyword Research module: storage.

Purpose of this file
--------------------
Rahul periodically pulls competitor keyword exports (Keyword, Avg. Monthly
Search Volume, Difficulty, YoY change) from many Google Sheets at once --
his first real batch was 28 sheets across 25+ competitors. Each run of the
/keyword-research skill is one "batch." Same shared SQLite file as the
rest of the platform (agent2_storage.get_connection()), own tables, per
the project's modular-design principle.

The tables
----------
"keyword_research_batches" -- one row per research run. `include_in_master`
controls whether this batch's keywords count toward the cumulative master
keyword list (Rahul's explicit ask, 2026-08-06: sometimes a batch should
feed the running master list, sometimes it's a one-off check that
shouldn't be folded in). Every batch is kept and viewable individually
either way -- this flag only affects the master aggregation, it never
deletes or hides a batch's own report.

"keyword_research_keywords" -- one row per UNIQUE keyword WITHIN a batch
(duplicates across the batch's own sheets are already collapsed by the
time this is saved). `competitors_json` lists every competitor whose
sheet contained this keyword in this batch -- this is what the
competitor-overlap analysis reads. Numeric fields (volume/difficulty/
yoy_change) keep whichever sheet's value was seen first for that keyword,
per Rahul's explicit choice (2026-08-06) over averaging or flagging
disagreements.

The master keyword list is NOT stored as its own table -- same philosophy
as the Reporting Hub (agent4_dashboard/build_reporting_hub.py): it's pure
aggregation of data already saved here, computed at dashboard-build time
from whichever batches have include_in_master=1, so there's one source of
truth (batches + their keywords) instead of a second copy of the data.
"""

import json
import re
from datetime import datetime, timezone

from agent2_storage.database import get_connection as _get_audit_connection

CREATE_BATCHES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS keyword_research_batches (
    batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    label TEXT,
    include_in_master INTEGER NOT NULL DEFAULT 1,
    sheet_count INTEGER NOT NULL,
    competitor_count INTEGER NOT NULL,
    raw_keyword_count INTEGER NOT NULL,
    unique_keyword_count INTEGER NOT NULL
)
"""

CREATE_KEYWORDS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS keyword_research_keywords (
    keyword_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES keyword_research_batches(batch_id),
    keyword TEXT NOT NULL,
    keyword_normalized TEXT NOT NULL,
    avg_monthly_search_volume REAL,
    difficulty REAL,
    yoy_change REAL,
    competitors_json TEXT NOT NULL
)
"""


def get_connection(db_path=None):
    """Same physical database file as the rest of the platform, with the
    Keyword Research tables created if they don't exist yet. `db_path` is
    an override for testing only."""
    connection = _get_audit_connection(db_path) if db_path else _get_audit_connection()
    connection.execute(CREATE_BATCHES_TABLE_SQL)
    connection.execute(CREATE_KEYWORDS_TABLE_SQL)
    connection.commit()
    return connection


def normalize_keyword(text):
    """Lowercased, trimmed, internal whitespace collapsed -- so "SEO Tools",
    " seo  tools", and "seo tools " are all recognized as the same keyword
    for dedup purposes, while the original text (from whichever sheet was
    seen first) is what's actually displayed."""
    return re.sub(r"\s+", " ", text.strip().lower())


def dedupe_keyword_appearances(appearances):
    """
    The one dedup algorithm used both when saving a new batch (raw sheet
    rows, one competitor per row) and when aggregating the cross-batch
    master list (each batch's already-deduped keywords, expanded back into
    one appearance per competitor they were seen under -- see
    load_master_keywords below).

    `appearances` is an ordered iterable of dicts:
        {"keyword": str, "avg_monthly_search_volume": num,
         "difficulty": num, "yoy_change": num, "competitor": str}
    Earlier entries win for the numeric fields (Rahul's explicit choice
    over averaging). Every distinct competitor seen for a keyword is kept,
    in first-seen order, regardless of which appearance "won" numerically.

    Returns an ordered list of unique keyword dicts:
        {"keyword": str, "avg_monthly_search_volume": num,
         "difficulty": num, "yoy_change": num, "competitors": [str, ...]}
    """
    by_normalized = {}
    order = []
    for appearance in appearances:
        normalized = normalize_keyword(appearance["keyword"])
        if normalized not in by_normalized:
            by_normalized[normalized] = {
                "keyword": appearance["keyword"].strip(),
                "avg_monthly_search_volume": appearance.get("avg_monthly_search_volume"),
                "difficulty": appearance.get("difficulty"),
                "yoy_change": appearance.get("yoy_change"),
                "competitors": [],
            }
            order.append(normalized)
        competitor = appearance.get("competitor")
        if competitor and competitor not in by_normalized[normalized]["competitors"]:
            by_normalized[normalized]["competitors"].append(competitor)
    return [by_normalized[normalized] for normalized in order]


def save_batch(connection, label, include_in_master, sheets):
    """
    Saves one research batch. `sheets` is a list of
    {"competitor": str, "rows": [{"keyword":.., "avg_monthly_search_volume":..,
    "difficulty":.., "yoy_change":..}, ...]}. Rows are flattened into
    atomic (keyword, competitor) appearances in sheet order, then deduped
    with dedupe_keyword_appearances -- this is the batch's own internal
    dedup, independent of any other batch.

    Returns the new batch_id.
    """
    appearances = []
    for sheet in sheets:
        competitor = sheet["competitor"]
        for row in sheet["rows"]:
            appearances.append({
                "keyword": row["keyword"],
                "avg_monthly_search_volume": row.get("avg_monthly_search_volume"),
                "difficulty": row.get("difficulty"),
                "yoy_change": row.get("yoy_change"),
                "competitor": competitor,
            })

    unique_keywords = dedupe_keyword_appearances(appearances)
    competitor_count = len({sheet["competitor"] for sheet in sheets})
    created_at = datetime.now(timezone.utc).isoformat()

    cursor = connection.execute(
        """
        INSERT INTO keyword_research_batches (
            created_at, label, include_in_master, sheet_count,
            competitor_count, raw_keyword_count, unique_keyword_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            created_at, label, 1 if include_in_master else 0, len(sheets),
            competitor_count, len(appearances), len(unique_keywords),
        ),
    )
    batch_id = cursor.lastrowid

    for keyword in unique_keywords:
        connection.execute(
            """
            INSERT INTO keyword_research_keywords (
                batch_id, keyword, keyword_normalized, avg_monthly_search_volume,
                difficulty, yoy_change, competitors_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id, keyword["keyword"], normalize_keyword(keyword["keyword"]),
                keyword["avg_monthly_search_volume"], keyword["difficulty"],
                keyword["yoy_change"], json.dumps(keyword["competitors"]),
            ),
        )

    connection.commit()
    return batch_id


def load_all_batches(connection):
    """Every batch, newest first -- same ordering convention as
    content_agent.database.load_all_briefs."""
    rows = connection.execute(
        "SELECT * FROM keyword_research_batches ORDER BY batch_id DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def load_batch(connection, batch_id):
    row = connection.execute(
        "SELECT * FROM keyword_research_batches WHERE batch_id = ?", (batch_id,)
    ).fetchone()
    return dict(row) if row else None


def load_keywords_for_batch(connection, batch_id):
    """One batch's own unique keyword list, as saved -- for viewing or
    exporting that specific batch's report on its own."""
    rows = connection.execute(
        "SELECT * FROM keyword_research_keywords WHERE batch_id = ? ORDER BY keyword_id",
        (batch_id,),
    ).fetchall()
    keywords = []
    for row in rows:
        keyword = dict(row)
        keyword["competitors"] = json.loads(keyword["competitors_json"])
        keywords.append(keyword)
    return keywords


def load_master_keywords(connection):
    """
    The cumulative keyword list: every batch with include_in_master=1,
    oldest first (so the first batch chronologically wins on numeric
    values, consistent with the within-batch rule), re-deduped across all
    of them together. A keyword already saved by an earlier included batch
    keeps that batch's numeric values even if a later included batch also
    has it -- but the later batch's competitor(s) still get added to the
    keyword's competitor list, so overlap analysis reflects every batch,
    not just whichever one happened to be first.
    """
    batches = [b for b in load_all_batches(connection) if b["include_in_master"]]
    batches.sort(key=lambda b: b["created_at"])  # oldest first

    appearances = []
    for batch in batches:
        for keyword in load_keywords_for_batch(connection, batch["batch_id"]):
            for competitor in keyword["competitors"]:
                appearances.append({
                    "keyword": keyword["keyword"],
                    "avg_monthly_search_volume": keyword["avg_monthly_search_volume"],
                    "difficulty": keyword["difficulty"],
                    "yoy_change": keyword["yoy_change"],
                    "competitor": competitor,
                })

    return dedupe_keyword_appearances(appearances)
