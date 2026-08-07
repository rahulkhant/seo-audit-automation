"""
Content Agent, QA Checker step: save-to-database entry point.

Purpose of this file
--------------------
Same division of labor as save_brief.py/save_draft.py: the QA Checker
skill (.claude/skills/blog-qa/SKILL.md) supplies only the one genuinely
judgment-based input -- a small score adjustment and a short note on
tone/flow/naturalness. Everything else in the report (word count, keyword
coverage/density, readability, sentence complexity, passive voice,
banned-phrase hits) is recomputed fresh here, in Python, from the brief
and draft already in the database -- never trusted as something the
model reports about its own output.

Usage
-----
    python -m content_agent.save_qa_review <project> <brief_id> path/to/judgment.json

judgment.json shape:
    {
        "judgment_adjustment": -1.0,
        "judgment_notes": "Reads naturally and matches the brief's tone;
            a couple of sentences in the guidelines section feel slightly
            repetitive back to back."
    }

Prints the new review_id and final score on success.
"""

import json
import sys

from content_agent.database import (
    get_connection,
    load_brief,
    load_draft_for_brief,
    save_qa_review,
)
from content_agent.qa_checks import compute_score, run_deterministic_checks
from projects import db_path

MAX_JUDGMENT_ADJUSTMENT = 2.0


def _validate_judgment(payload):
    if "judgment_adjustment" not in payload:
        raise ValueError("judgment.json is missing required field: judgment_adjustment")
    adjustment = payload["judgment_adjustment"]
    if not isinstance(adjustment, (int, float)):
        raise ValueError("judgment_adjustment must be a number")
    if abs(adjustment) > MAX_JUDGMENT_ADJUSTMENT:
        raise ValueError(
            f"judgment_adjustment ({adjustment}) exceeds the +/-{MAX_JUDGMENT_ADJUSTMENT} cap -- "
            f"the judgment half is meant to be a small nudge on top of the deterministic score, "
            f"not the dominant factor."
        )


def main():
    if len(sys.argv) != 4:
        print("Usage: python -m content_agent.save_qa_review <project> <brief_id> path/to/judgment.json", file=sys.stderr)
        sys.exit(1)

    project = sys.argv[1]
    brief_id = int(sys.argv[2])
    judgment_path = sys.argv[3]
    with open(judgment_path, "r", encoding="utf-8") as judgment_file:
        judgment = json.load(judgment_file)

    _validate_judgment(judgment)

    connection = get_connection(db_path(project))
    try:
        brief = load_brief(connection, brief_id)
        if brief is None:
            raise ValueError(f"No brief found with brief_id={brief_id}")
        draft = load_draft_for_brief(connection, brief_id)
        if draft is None:
            raise ValueError(f"Brief {brief_id} has no draft yet -- run /blog-write first")

        deterministic = run_deterministic_checks(brief, draft)
        result = compute_score(
            deterministic,
            judgment_adjustment=judgment["judgment_adjustment"],
            judgment_notes=judgment.get("judgment_notes", ""),
        )
        report = {"deterministic": deterministic, **result}

        review_id = save_qa_review(connection, brief_id, result["score"], report)
    finally:
        connection.close()

    print(f"Saved review_id={review_id}, score={result['score']}/10")


if __name__ == "__main__":
    main()
