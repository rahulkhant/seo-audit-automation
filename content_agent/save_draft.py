"""
Content Agent, Writer step: save-to-database entry point.

Purpose of this file
--------------------
Same division of labor as save_brief.py: the Writer Agent's actual prose
generation happens as part of a Claude Code skill conversation (see
.claude/skills/blog-write/SKILL.md), not in Python -- there's no separate
API call to make here. This file is the hand-off point once a draft is
finished, plus the one piece of real validation/computation that belongs
in code, not the model's judgment: word counts are computed from the
actual text (len(content.split())), never trusted as a number the model
reports about itself.

Usage
-----
    python -m content_agent.save_draft <project> path/to/draft.json

Input JSON shape:
    {
        "brief_id": 1,
        "sections": [
            {"heading": "...", "level": "H2", "content": "..."},
            ...
        ]
    }

Prints the new draft_id on success.
"""

import json
import sys

from content_agent.database import get_connection, load_brief, save_draft
from projects import db_path


def _validate(payload, brief):
    if not payload.get("brief_id"):
        raise ValueError("Draft is missing required field: brief_id")
    if brief is None:
        raise ValueError(f"No brief found with brief_id={payload['brief_id']}")

    sections = payload.get("sections")
    if not isinstance(sections, list) or len(sections) == 0:
        raise ValueError("Draft must have a non-empty 'sections' list")
    if len(sections) != len(brief["sections"]):
        raise ValueError(
            f"Draft has {len(sections)} section(s) but the brief has "
            f"{len(brief['sections'])} -- every brief section needs exactly one "
            f"draft section, in the same order."
        )
    for index, section in enumerate(sections):
        if not (section.get("content") or "").strip():
            brief_heading = brief["sections"][index]["heading"] or brief["sections"][index]["level"]
            raise ValueError(f"Section {index} ('{brief_heading}') has no content")


def _with_word_counts(sections):
    return [
        {**section, "word_count": len(section["content"].split())}
        for section in sections
    ]


def main():
    if len(sys.argv) != 3:
        print("Usage: python -m content_agent.save_draft <project> path/to/draft.json", file=sys.stderr)
        sys.exit(1)

    project, draft_path = sys.argv[1], sys.argv[2]
    with open(draft_path, "r", encoding="utf-8") as draft_file:
        payload = json.load(draft_file)

    connection = get_connection(db_path(project))
    try:
        brief = load_brief(connection, payload.get("brief_id"))
        _validate(payload, brief)

        sections = _with_word_counts(payload["sections"])
        draft_id = save_draft(connection, payload["brief_id"], sections)
    finally:
        connection.close()

    print(f"Saved draft_id={draft_id}")


if __name__ == "__main__":
    main()
