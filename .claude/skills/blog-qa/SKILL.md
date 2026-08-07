---
description: "Content Agent, step 3 of 3 (QA Checker): run the deterministic checks on a finished draft (word count, keyword coverage/density, readability, sentence complexity, passive voice, banned phrases), add a small judgment-based score adjustment, save the combined report, rebuild the dashboard's Content page, and push."
---

You are running the QA Checker Agent -- the third and last of the three
planned Content Agent modules (Outliner and Writer both built). Almost
all of this report is deterministic Python, computed fresh from the
draft every time, never trusted as something you claim about your own
output -- your only real job here is the one thing a formula can't do:
read the draft and judge whether it actually flows naturally and matches
the intended voice.

A note on the scoring math (Rahul, 2026-08-05): the point deductions in
content_agent/qa_checks.py are a reasonable v1, not final -- he wants to
research proper scoring approaches and update this later. Don't try to
"fix" the math yourself; just use it as-is and mention in your summary if
a deduction seems off, so it's a data point for that future review.

Do the following, in order:

## 1. Confirm working directory
If not already there, change to `/Users/rahul/Desktop/Automation/seo-audit-automation`.

## 2. Which project is this for?
Every project has its own separate content database and dashboard. Ask
which project this review belongs to, unless it's already clear from
context, and validate it:
```
.venv/bin/python3 -c "from projects import list_projects; print(' '.join(slug for slug, _ in list_projects()))"
```
If the name given isn't in that list, ask again rather than guessing.

## 3. Pick which brief to review
If the user named a topic or brief_id, use that. Otherwise list drafted
briefs and ask:
```
.venv/bin/python3 -c "
from content_agent.database import get_connection, load_all_briefs
from projects import db_path
connection = get_connection(db_path('<project>'))
for b in load_all_briefs(connection):
    print(f\"brief_id={b['brief_id']}  [{b['status']}]  {b['topic']}\")
connection.close()
"
```
Only briefs with status "drafted" or "qa_reviewed" have something to
check. If the brief already has a QA review, confirm with the user before
overwriting it -- same overwrite-only pattern as drafts, no version
history kept (see content_agent/database.py's module docstring).

## 4. Preview the deterministic report
```
.venv/bin/python3 -c "
import json
from content_agent.database import get_connection, load_brief, load_draft_for_brief
from content_agent.qa_checks import run_deterministic_checks, compute_score
from projects import db_path
connection = get_connection(db_path('<project>'))
brief = load_brief(connection, <brief_id>)
draft = load_draft_for_brief(connection, <brief_id>)
connection.close()
deterministic = run_deterministic_checks(brief, draft)
print(json.dumps(deterministic, indent=2))
print(json.dumps(compute_score(deterministic), indent=2))
"
```
Read this output carefully -- it's the deterministic half of the report
in full, including word count, keyword coverage/density, readability,
sentence complexity, passive voice, and any banned phrases found, plus
what the score would be with zero judgment adjustment. This is real
signal for step 4: a high passive-voice percentage or a difficult
readability score is worth actually reading those sections for, not
just noting the number.

## 5. Read the full draft and form your judgment
Load the draft's full text (same brief_id) and read it end to end --
not skimmed. Decide:
- **judgment_adjustment**: a number from -2.0 to +2.0. This is a small
  nudge on top of the deterministic score, not the dominant factor --
  `save_qa_review.py` will reject anything outside that range. Negative
  for real flow/naturalness problems the deterministic checks can't see
  (e.g. repetitive sentence openings, a section that reads stitched-in
  rather than connected to its neighbors); positive only if the writing
  is genuinely better than the deterministic score alone suggests.
  Zero is a completely valid answer -- don't invent a reason to adjust.
- **judgment_notes**: 2-4 sentences, specific. Not "reads well" --
  name what's actually good or actually off, ideally pointing at a
  specific section if there's an issue worth flagging.

## 6. Save
Write `{"judgment_adjustment": ..., "judgment_notes": "..."}` to a temp
file, then:
```
.venv/bin/python3 -m content_agent.save_qa_review <project> <brief_id> <path-to-judgment.json>
```
This recomputes the deterministic report fresh (never trusting step 4's
output directly -- that was a preview, not the saved source of truth),
combines it with your judgment, and prints the final review_id and score.

## 7. Rebuild the dashboard
```
.venv/bin/python3 -m agent4_dashboard.build_dashboard_metronic <project>
.venv/bin/python3 -m agent4_dashboard.build_reporting_hub <project>
.venv/bin/python3 -m content_agent.build_content_page <project>
```

## 8. Commit and push -- automatically, no separate confirmation step
Same established pattern as `/blog-outline` and `/blog-write`.
```
git add data/<project>/ docs/<project>/content.html docs/<project>/content_qa/ docs/<project>/index.html docs/<project>/history.html docs/<project>/reporting.html docs/<project>/reports/reporting-hub-latest.pdf
git commit -m "Add QA review: <topic>"
git push
```

## 9. Report back
Tell Rahul: the final score out of 10, every deduction with its reason
(not just the number), your judgment notes, and the dashboard link:
```
.venv/bin/python3 -c "from projects import dashboard_url; print(dashboard_url('<project>') + 'content.html')"
```
