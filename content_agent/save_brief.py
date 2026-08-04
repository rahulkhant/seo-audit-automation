"""
Content Agent, Outliner step: save-to-database entry point.

Purpose of this file
--------------------
The Outliner Agent's actual "brief writing" (deciding what each section
should cover) happens as part of a Claude Code skill conversation, not in
Python -- there's no API call to make here, since the model doing the
outlining is already the one running the skill (see
.claude/skills/blog-outline/SKILL.md). This file is just the hand-off
point: once the skill has produced the finished brief as JSON, this script
persists it to the database, the same way every other agent in this
project ends its work with a "save" step.

Usage
-----
    python -m content_agent.save_brief path/to/brief.json

Prints the new brief_id on success, so the skill can reference it (e.g.
when telling the user which page/row to look at on the dashboard).
"""

import json
import sys

from content_agent.database import get_connection, save_brief

REQUIRED_FIELDS = ["topic", "primary_keyword", "target_word_count", "sections"]


def _validate(brief):
    missing = [field for field in REQUIRED_FIELDS if not brief.get(field)]
    if missing:
        raise ValueError(f"Brief is missing required field(s): {', '.join(missing)}")
    if not isinstance(brief["sections"], list) or len(brief["sections"]) == 0:
        raise ValueError("Brief must have a non-empty 'sections' list")


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m content_agent.save_brief path/to/brief.json", file=sys.stderr)
        sys.exit(1)

    brief_path = sys.argv[1]
    with open(brief_path, "r", encoding="utf-8") as brief_file:
        brief = json.load(brief_file)

    _validate(brief)

    connection = get_connection()
    try:
        brief_id = save_brief(connection, brief)
    finally:
        connection.close()

    print(f"Saved brief_id={brief_id}")


if __name__ == "__main__":
    main()
