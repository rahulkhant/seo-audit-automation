"""
Activity Agent: Storage.

Purpose of this file
--------------------
Rahul reports his day's work as a bullet list every day, but this isn't a
simple one-blob-per-day log -- a task he starts on Monday might still be
"in progress" on Wednesday and only get marked "completed" on Friday. So
this needs two linked things, not one: the tasks themselves (which persist
and carry a status across days) and each day's log (which records which
tasks were touched that day and what happened to them). Same shared
SQLite file as the rest of the platform (agent2_storage.get_connection()),
own tables, per the modular-design principle already used by content_agent.

The tables
----------
"activity_tasks" -- one row per real piece of work, persists across
however many days it takes to finish. `status` is one of "in_progress",
"completed", "blocked". `target_notes` is an optional free-text goal or
deadline ("finish by Friday", "waiting on client approval") -- this is
what makes the "performance" tracking real: not just "did something
happen" but "is it moving toward what was actually intended."

"activity_daily_logs" -- one row per calendar date Rahul reports on.
`log_date` is UNIQUE and overwrite-only (same pattern as content_agent's
drafts/QA reviews): if he corrects or adds to the same day later, saving
again replaces that day's entries rather than duplicating them. `raw_input`
keeps the original bullet list verbatim, mostly so a real record of what
was actually said exists if the structured parse ever needs re-checking.

"activity_log_entries" -- the join: which task was touched on which day,
with that day's own status snapshot and a short note of what happened
that day specifically. A task worked on for five days has one row in
activity_tasks and five rows here, one per day -- this is what lets the
dashboard show both "what's the current state of this task" and "what
actually happened, day by day."
"""

import json
from datetime import datetime, timezone

from agent2_storage.database import get_connection as _get_audit_connection

VALID_STATUSES = ("in_progress", "completed", "blocked")

CREATE_ACTIVITY_TASKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS activity_tasks (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    category TEXT,
    status TEXT NOT NULL DEFAULT 'in_progress',
    target_notes TEXT,
    first_logged_date TEXT NOT NULL,
    last_updated_date TEXT NOT NULL,
    completed_date TEXT
)
"""

CREATE_ACTIVITY_DAILY_LOGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS activity_daily_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    raw_input TEXT,
    daily_notes TEXT
)
"""

CREATE_ACTIVITY_LOG_ENTRIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS activity_log_entries (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id INTEGER NOT NULL REFERENCES activity_daily_logs(log_id),
    task_id INTEGER NOT NULL REFERENCES activity_tasks(task_id),
    day_status TEXT NOT NULL,
    day_note TEXT
)
"""


def get_connection(db_path=None):
    """Same physical database file as the SEO audit and Content Agent,
    with the activity tables created if they don't exist yet. `db_path` is
    an override for testing only."""
    connection = _get_audit_connection(db_path) if db_path else _get_audit_connection()
    connection.execute(CREATE_ACTIVITY_TASKS_TABLE_SQL)
    connection.execute(CREATE_ACTIVITY_DAILY_LOGS_TABLE_SQL)
    connection.execute(CREATE_ACTIVITY_LOG_ENTRIES_TABLE_SQL)
    connection.commit()
    return connection


def save_activity_log(connection, log_date, raw_input, daily_notes, entries):
    """
    Saves (or overwrites -- see module docstring) one day's activity log.

    `entries` is a list of dicts, one per task touched that day:
        {
            "task_id": 7,             # omit/None to create a new task
            "description": "...",     # required for new tasks, optional
                                       # update for existing ones
            "category": "...",
            "day_status": "in_progress" | "completed" | "blocked",
            "day_note": "what happened with this task today",
            "target_notes": "...",    # optional goal/deadline, new or updated
        }

    Returns the log_id.
    """
    created_at = datetime.now(timezone.utc).isoformat()

    connection.execute(
        """
        INSERT INTO activity_daily_logs (log_date, created_at, raw_input, daily_notes)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(log_date) DO UPDATE SET
            created_at = excluded.created_at,
            raw_input = excluded.raw_input,
            daily_notes = excluded.daily_notes
        """,
        (log_date, created_at, raw_input, daily_notes),
    )
    # log_date is UNIQUE, so look the row up directly rather than trusting
    # cursor.lastrowid -- same caveat as content_agent.database on the
    # ON CONFLICT DO UPDATE path.
    log_id = connection.execute(
        "SELECT log_id FROM activity_daily_logs WHERE log_date = ?", (log_date,)
    ).fetchone()["log_id"]

    # Overwrite-only: re-saving this date replaces its entries rather than
    # accumulating duplicates. The tasks themselves are untouched here --
    # only this day's link to them is rebuilt.
    connection.execute("DELETE FROM activity_log_entries WHERE log_id = ?", (log_id,))

    for entry in entries:
        day_status = entry["day_status"]
        if day_status not in VALID_STATUSES:
            raise ValueError(f"day_status must be one of {VALID_STATUSES}, got {day_status!r}")

        task_id = entry.get("task_id")
        completed_date = log_date if day_status == "completed" else None

        if task_id is None:
            cursor = connection.execute(
                """
                INSERT INTO activity_tasks (
                    description, category, status, target_notes,
                    first_logged_date, last_updated_date, completed_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["description"],
                    entry.get("category"),
                    day_status,
                    entry.get("target_notes"),
                    log_date,
                    log_date,
                    completed_date,
                ),
            )
            task_id = cursor.lastrowid
        else:
            connection.execute(
                """
                UPDATE activity_tasks SET
                    description = COALESCE(?, description),
                    category = COALESCE(?, category),
                    status = ?,
                    target_notes = COALESCE(?, target_notes),
                    last_updated_date = ?,
                    completed_date = ?
                WHERE task_id = ?
                """,
                (
                    entry.get("description"),
                    entry.get("category"),
                    day_status,
                    entry.get("target_notes"),
                    log_date,
                    completed_date,
                    task_id,
                ),
            )

        connection.execute(
            "INSERT INTO activity_log_entries (log_id, task_id, day_status, day_note) VALUES (?, ?, ?, ?)",
            (log_id, task_id, day_status, entry.get("day_note")),
        )

    connection.commit()
    return log_id


def load_open_tasks(connection):
    """Tasks not yet completed (in_progress or blocked), most recently
    touched first -- what the skill loads to match today's bullets against
    before deciding what's a continuation vs. a brand new task."""
    rows = connection.execute(
        "SELECT * FROM activity_tasks WHERE status != 'completed' ORDER BY last_updated_date DESC, task_id DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def load_all_tasks(connection):
    rows = connection.execute("SELECT * FROM activity_tasks ORDER BY task_id DESC").fetchall()
    return [dict(row) for row in rows]


def load_task(connection, task_id):
    row = connection.execute(
        "SELECT * FROM activity_tasks WHERE task_id = ?", (task_id,)
    ).fetchone()
    return dict(row) if row else None


def load_all_daily_logs(connection):
    """Every day's log, newest first, WITHOUT its entries (see
    load_entries_for_log) -- used for the chronological list view."""
    rows = connection.execute(
        "SELECT * FROM activity_daily_logs ORDER BY log_date DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def load_log_by_date(connection, log_date):
    row = connection.execute(
        "SELECT * FROM activity_daily_logs WHERE log_date = ?", (log_date,)
    ).fetchone()
    return dict(row) if row else None


def load_entries_for_log(connection, log_id):
    """Every task touched on one day, joined with that task's own current
    (all-time) state -- so a day's view can show both "what happened this
    day" (day_status/day_note) and "where does this task actually stand
    now" (the task's own status/target_notes), which can differ once later
    days move the task further along."""
    rows = connection.execute(
        """
        SELECT
            e.entry_id, e.log_id, e.task_id, e.day_status, e.day_note,
            t.description, t.category, t.status AS current_status,
            t.target_notes, t.completed_date
        FROM activity_log_entries e
        JOIN activity_tasks t ON t.task_id = e.task_id
        WHERE e.log_id = ?
        ORDER BY e.entry_id
        """,
        (log_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def load_all_logs_with_entries(connection):
    """Every daily log, newest first, each with its entries attached --
    the shape the dashboard page and PDF generators actually want, so they
    don't have to do the per-log query themselves."""
    logs = load_all_daily_logs(connection)
    for log in logs:
        log["entries"] = load_entries_for_log(connection, log["log_id"])
    return logs
