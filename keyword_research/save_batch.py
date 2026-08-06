"""
Keyword Research module: save-to-database entry point.

Purpose of this file
--------------------
The /keyword-research skill does the actual fetching (reading each Google
Sheet) and hands off a finished batch here. This is the one place real
validation belongs in code rather than the skill's own judgment: every
sheet needs a competitor name and at least one row, and every row needs
an actual keyword.

Usage
-----
    python -m keyword_research.save_batch path/to/batch.json

Input JSON shape:
    {
        "label": "Q3 2026 competitor scan",   -- optional
        "include_in_master": true,
        "sheets": [
            {
                "competitor": "Competitor A",
                "rows": [
                    {"keyword": "...", "avg_monthly_search_volume": 1200,
                     "difficulty": 34, "yoy_change": 12.5},
                    ...
                ]
            },
            ...
        ]
    }

Prints the new batch_id on success.
"""

import json
import sys

from keyword_research.database import get_connection, save_batch


def _validate(payload):
    sheets = payload.get("sheets")
    if not isinstance(sheets, list) or len(sheets) == 0:
        raise ValueError("Batch must have a non-empty 'sheets' list")

    for index, sheet in enumerate(sheets):
        if not (sheet.get("competitor") or "").strip():
            raise ValueError(f"Sheet {index}: missing 'competitor' name")
        rows = sheet.get("rows")
        if not isinstance(rows, list) or len(rows) == 0:
            raise ValueError(f"Sheet {index} ('{sheet['competitor']}'): no rows found")
        for row_index, row in enumerate(rows):
            if not (row.get("keyword") or "").strip():
                raise ValueError(
                    f"Sheet {index} ('{sheet['competitor']}'), row {row_index}: missing 'keyword'"
                )


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m keyword_research.save_batch path/to/batch.json", file=sys.stderr)
        sys.exit(1)

    batch_path = sys.argv[1]
    with open(batch_path, "r", encoding="utf-8") as batch_file:
        payload = json.load(batch_file)

    _validate(payload)

    connection = get_connection()
    try:
        batch_id = save_batch(
            connection,
            payload.get("label"),
            payload.get("include_in_master", True),
            payload["sheets"],
        )
    finally:
        connection.close()

    print(f"Saved batch_id={batch_id}")


if __name__ == "__main__":
    main()
