"""
Agent 2: Storage.

Purpose of this file
--------------------
Agent 1 produces one JSON file per crawl (data/latest_crawl.json). That file
only ever holds the MOST RECENT crawl -- it gets overwritten every time
Agent 1 runs. Agent 2's job is to take that snapshot and save it permanently
into a SQLite database, where every run adds NEW rows instead of overwriting
anything. That's what makes trend tracking possible later: Agent 3 and
Agent 4 will be able to compare "this week" against "last week" for the same
page, because both weeks' data will still be sitting in the database.

Why SQLite specifically
------------------------
SQLite stores the entire database as a single file (no separate server to
install or manage), which keeps this project simple to run both on your
machine and later inside GitHub Actions.

The two tables
--------------
- "runs": one row per audit run (when it happened, how many pages, etc.)
- "pages": one row per page, per run, linked back to its run via run_id.
  The same URL will have a new row every time we crawl it again, which is
  exactly the history we want.

Nested data (like the list of images on a page, or all its internal links)
doesn't fit neatly into a single table column, so we store it as a JSON
text string inside the column. It's still saved completely -- Agent 3 just
needs to decode it back into a Python list/dict when it reads it, using
Python's built-in `json` module.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Where the permanent database file lives. Like data/latest_crawl.json, this
# sits in the "data" folder, which is gitignored -- this is generated data,
# not source code, so it doesn't belong in git history.
DB_FILE_PATH = Path(__file__).resolve().parent.parent / "data" / "seo_audit_history.db"

CREATE_RUNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_root_url TEXT NOT NULL,
    run_timestamp TEXT NOT NULL,
    crawl_duration_seconds REAL,
    total_pages_crawled INTEGER,
    total_crawl_errors INTEGER,
    sitemap_url_used TEXT,
    disallowed_but_in_sitemap_json TEXT,
    crawl_errors_json TEXT
)
"""

CREATE_PAGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pages (
    page_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(run_id),
    url TEXT NOT NULL,

    raw_status_code INTEGER,
    raw_content_type TEXT,
    is_html INTEGER,
    raw_error TEXT,
    ssl_valid INTEGER,
    redirect_chain_json TEXT,

    rendered_status_code INTEGER,
    rendered_error TEXT,

    redirected_http_to_https INTEGER,

    title TEXT,
    meta_description TEXT,
    og_title TEXT,
    og_description TEXT,
    twitter_title TEXT,
    twitter_description TEXT,
    robots_meta_content TEXT,
    canonical_urls_json TEXT,
    h1_texts_json TEXT,
    images_json TEXT,
    internal_links_json TEXT,
    external_links_json TEXT,
    schema_blocks_json TEXT,
    mixed_content_urls_json TEXT,
    js_rendering_comparison_json TEXT
)
"""

# Agent 3 (validation) writes its results here -- one row per rule
# violation it finds, linked back to the run that produced it.
CREATE_FINDINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS findings (
    finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(run_id),
    page_url TEXT NOT NULL,
    rule TEXT NOT NULL,
    issue TEXT NOT NULL,
    expected TEXT,
    actual TEXT,
    severity TEXT NOT NULL
)
"""


def _to_json_or_none(value):
    """Converts a Python list/dict into a JSON string for storage, or
    returns None as-is (SQLite stores that as NULL)."""
    return json.dumps(value) if value is not None else None


def get_connection(db_path=DB_FILE_PATH):
    """
    Opens a connection to the SQLite database file, creating the file and
    its tables if they don't already exist. Safe to call every time the
    program runs -- "CREATE TABLE IF NOT EXISTS" does nothing if the tables
    are already there.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    # Row objects let callers access columns by name (e.g. row["title"])
    # and convert cleanly to dictionaries -- Agent 3's checks rely on this.
    connection.row_factory = sqlite3.Row
    connection.execute(CREATE_RUNS_TABLE_SQL)
    connection.execute(CREATE_PAGES_TABLE_SQL)
    connection.execute(CREATE_FINDINGS_TABLE_SQL)
    connection.commit()
    return connection


def save_findings(connection, run_id, findings):
    """
    Saves Agent 3's validation findings for one run. Each finding
    dictionary (produced by page_checks.py / site_checks.py) becomes one
    row, linked back to the run it was found in.
    """
    connection.executemany(
        """
        INSERT INTO findings (run_id, page_url, rule, issue, expected, actual, severity)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                run_id,
                finding["page_url"],
                finding["rule"],
                finding["issue"],
                finding["expected"],
                finding["actual"],
                finding["severity"],
            )
            for finding in findings
        ],
    )
    connection.commit()


def save_crawl_result(connection, crawl_result):
    """
    Saves one full crawl result (Agent 1's output) into the database as a
    new run, plus one new row per page. Returns the new run_id, which
    Agent 3 will later use to know "which run should I check the rules
    against."
    """
    run_timestamp = datetime.now(timezone.utc).isoformat()

    cursor = connection.execute(
        """
        INSERT INTO runs (
            site_root_url, run_timestamp, crawl_duration_seconds,
            total_pages_crawled, total_crawl_errors, sitemap_url_used,
            disallowed_but_in_sitemap_json, crawl_errors_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            crawl_result["site_root_url"],
            run_timestamp,
            crawl_result["crawl_duration_seconds"],
            len(crawl_result["pages"]),
            len(crawl_result["crawl_errors"]),
            crawl_result["sitemap_url_used"],
            _to_json_or_none(crawl_result["disallowed_but_in_sitemap"]),
            _to_json_or_none(crawl_result["crawl_errors"]),
        ),
    )
    run_id = cursor.lastrowid

    for page in crawl_result["pages"]:
        raw_fetch = page["raw_fetch"] or {}
        rendered_fetch = page["rendered_fetch"] or {}
        https_redirect_check = page["https_redirect_check"] or {}
        seo_data = page["seo_data"] or {}

        connection.execute(
            """
            INSERT INTO pages (
                run_id, url,
                raw_status_code, raw_content_type, is_html, raw_error, ssl_valid, redirect_chain_json,
                rendered_status_code, rendered_error,
                redirected_http_to_https,
                title, meta_description, og_title, og_description,
                twitter_title, twitter_description, robots_meta_content,
                canonical_urls_json, h1_texts_json, images_json,
                internal_links_json, external_links_json, schema_blocks_json,
                mixed_content_urls_json, js_rendering_comparison_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                page["url"],
                raw_fetch.get("status_code"),
                raw_fetch.get("content_type"),
                raw_fetch.get("is_html"),
                raw_fetch.get("error"),
                raw_fetch.get("ssl_valid"),
                _to_json_or_none(raw_fetch.get("redirect_chain")),
                rendered_fetch.get("status_code"),
                rendered_fetch.get("error"),
                https_redirect_check.get("redirected_to_https"),
                seo_data.get("title"),
                seo_data.get("meta_description"),
                seo_data.get("og_title"),
                seo_data.get("og_description"),
                seo_data.get("twitter_title"),
                seo_data.get("twitter_description"),
                seo_data.get("robots_meta_content"),
                _to_json_or_none(seo_data.get("canonical_urls")),
                _to_json_or_none(seo_data.get("h1_texts")),
                _to_json_or_none(seo_data.get("images")),
                _to_json_or_none(seo_data.get("internal_links")),
                _to_json_or_none(seo_data.get("external_links")),
                _to_json_or_none(seo_data.get("schema_blocks")),
                _to_json_or_none(seo_data.get("mixed_content_urls")),
                _to_json_or_none(page["js_rendering_comparison"]),
            ),
        )

    connection.commit()
    return run_id


# Manual test: load Agent 1's latest crawl output and save it into the
# database, then read a few things back to prove the round trip worked.
if __name__ == "__main__":
    crawl_result_path = Path(__file__).resolve().parent.parent / "data" / "latest_crawl.json"
    with open(crawl_result_path, "r", encoding="utf-8") as crawl_result_file:
        loaded_crawl_result = json.load(crawl_result_file)

    db_connection = get_connection()
    saved_run_id = save_crawl_result(db_connection, loaded_crawl_result)
    print(f"Saved crawl result as run_id={saved_run_id}")

    # Read back a summary to prove the data actually landed correctly.
    total_runs = db_connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    total_pages_this_run = db_connection.execute(
        "SELECT COUNT(*) FROM pages WHERE run_id = ?", (saved_run_id,)
    ).fetchone()[0]
    pages_missing_title = db_connection.execute(
        "SELECT COUNT(*) FROM pages WHERE run_id = ? AND (title IS NULL OR title = '')",
        (saved_run_id,),
    ).fetchone()[0]
    pages_missing_meta_description = db_connection.execute(
        "SELECT COUNT(*) FROM pages WHERE run_id = ? AND (meta_description IS NULL OR meta_description = '')",
        (saved_run_id,),
    ).fetchone()[0]

    print(f"Total runs stored in database (all time): {total_runs}")
    print(f"Pages stored for this run: {total_pages_this_run}")
    print(f"Pages missing a title tag: {pages_missing_title}")
    print(f"Pages missing a meta description: {pages_missing_meta_description}")

    db_connection.close()
