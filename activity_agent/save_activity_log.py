"""
Activity Agent: save-to-database entry point.

Purpose of this file
--------------------
Same division of labor as content_agent's save_* scripts: matching today's
bullet list against existing open tasks (continuing an existing task vs.
starting a new one) is the model's judgment, done live in the
/log-activity skill conversation -- this file is the hand-off point once
that's decided, plus the one piece of real validation that belongs in
code: every entry must reference either a real existing task_id or supply
a description for a new one, and day_status must be a real status.

Usage
-----
    python -m activity_agent.save_activity_log path/to/log.json

Input JSON shape:
    {
        "log_date": "2026-08-05",
        "raw_input": "the original bullet list, verbatim",
        "daily_notes": "optional one-line summary of the day",
        "entries": [
            {
                "task_id": 7,                 # omit/null for a new task
                "description": "...",
                "category": "...",
                "day_status": "in_progress" | "completed" | "blocked",
                "day_note": "...",
                "target_notes": "..."
            },
            ...
        ]
    }

Prints the new log_id on success.
"""

import json
import re
import sys

from activity_agent.database import VALID_STATUSES, get_connection, load_task, save_activity_log

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate(payload, connection):
    log_date = payload.get("log_date")
    if not log_date or not _DATE_RE.match(log_date):
        raise ValueError("log_date is required and must be in YYYY-MM-DD format")

    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) == 0:
        raise ValueError("Log must have a non-empty 'entries' list")

    for index, entry in enumerate(entries):
        if entry.get("day_status") not in VALID_STATUSES:
            raise ValueError(
                f"Entry {index}: day_status must be one of {VALID_STATUSES}, "
                f"got {entry.get('day_status')!r}"
            )
        task_id = entry.get("task_id")
        if task_id is None:
            if not (entry.get("description") or "").strip():
                raise ValueError(f"Entry {index}: new tasks require a non-empty 'description'")
        elif load_task(connection, task_id) is None:
            raise ValueError(f"Entry {index}: no existing task found with task_id={task_id}")


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m activity_agent.save_activity_log path/to/log.json", file=sys.stderr)
        sys.exit(1)

    log_path = sys.argv[1]
    with open(log_path, "r", encoding="utf-8") as log_file:
        payload = json.load(log_file)

    connection = get_connection()
    try:
        _validate(payload, connection)
        log_id = save_activity_log(
            connection,
            payload["log_date"],
            payload.get("raw_input"),
            payload.get("daily_notes"),
            payload["entries"],
        )
    finally:
        connection.close()

    print(f"Saved log_id={log_id}")


if __name__ == "__main__":
    main()
