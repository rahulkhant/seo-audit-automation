---
description: "Activity Agent: log Rahul's day-to-day work as a bullet list, match it against tasks still open from previous days, save it to the database, rebuild the Activity & Performance dashboard page, and push -- so today's log is live without a separate manual step."
---

You are running the Activity Agent -- a new module, separate from both the
SEO audit pipeline and the Content Agent. Rahul reports his day's work as a
bullet list at the end of the day (morning through evening, completed and
still-in-progress items together). Your job is narrower than it sounds:
this isn't just saving a daily note, it's tracking real tasks that can span
several days -- something started Monday might still be open Wednesday and
only finish Friday. The one thing a formula can't do here is decide
whether a bullet in today's list is a brand new task or the continuation
of something already open from a previous day -- that's your judgment
call, made visibly, not silently.

Do the following, in order:

## 1. Confirm working directory
If not already there, change to `/Users/rahul/Desktop/Automation/seo-audit-automation`.

## 2. Which project is this for?
Every project has its own separate activity log and dashboard. Ask which
project today's log belongs to, unless it's already clear from context,
and validate it:
```
.venv/bin/python3 -c "from projects import list_projects; print(' '.join(slug for slug, _ in list_projects()))"
```
If the name given isn't in that list, ask again rather than guessing.

## 3. Get the date and the bullet list
If the user already gave both in their message, use those. Otherwise ask:
- **Which date** this log is for (default: today).
- **The bullet list** of what was worked on, morning through evening --
  completed items and still-in-progress ones together, exactly as Rahul
  wants to report them.

If a log already exists for that date (check via the query below), confirm
with the user that they want to overwrite it before continuing -- this
skill replaces that day's entries, it doesn't keep old versions (see
`activity_agent/database.py`'s module docstring).
```
.venv/bin/python3 -c "
from activity_agent.database import get_connection, load_log_by_date
from projects import db_path
connection = get_connection(db_path('<project>'))
print(load_log_by_date(connection, '<log_date>'))
connection.close()
"
```

## 4. Load tasks still open from previous days
```
.venv/bin/python3 -c "
from activity_agent.database import get_connection, load_open_tasks
from projects import db_path
connection = get_connection(db_path('<project>'))
for t in load_open_tasks(connection):
    print(f\"task_id={t['task_id']}  [{t['status']}]  {t['description']}  (category: {t['category']}, target: {t['target_notes']})\")
connection.close()
"
```
This is the list you'll match today's bullets against.

## 5. Match today's bullets to tasks -- this is your judgment step
For each bullet Rahul gave you, decide:
- **Is this continuing an open task from step 4?** Match by meaning, not
  exact wording -- "finished the GMC blog" should match an open task
  called "Regenerate GMC blog draft with mixed content" if that's clearly
  what it refers to. When genuinely unsure, ask rather than guessing.
- **Or is this a brand new task?** If it doesn't match anything currently
  open, it's new.
- **What's today's status** for that task: `not_started` (planned for
  today, nothing happened yet), `in_progress` (worked on it, not done),
  `completed` (finished today), or `blocked` (stuck on something outside
  Rahul's control).
- **Category** -- Rahul will tell you what categories he's using; don't
  invent your own scheme.
- **Priority**, if Rahul's report includes one (e.g. High/Medium/Low) --
  optional, leave it out if he doesn't give one.
- **day_note** -- a short, specific note of what actually happened with
  this task today (not a restatement of the task's name). If Rahul's
  report includes time spent, fold just the DURATION into the note --
  "15 min", "45 min", "1 hr 5 min" -- never a start-end time range (e.g.
  not "09:30-09:45"). Rahul corrected this 2026-08-05: a computed
  duration reads faster than a range he'd have to subtract himself. Use
  the report's own "Time Spent" value directly rather than computing it
  from a start/end range yourself -- the two don't always agree (a range
  can include an interruption the Time Spent column already excludes),
  and the explicit figure is the more trustworthy one. There's no
  dedicated time-tracking field yet -- this is still just text inside the
  note (see step 6).
- **target_notes** -- only if Rahul mentions a goal or deadline for a
  task (new or existing). Leave it out otherwise; don't invent one.

**Show Rahul the matched/structured breakdown before saving anything** --
one line per task: which existing task it's continuing (or "NEW") plus
the status and note you're about to save. This is the one place a
mismatch would otherwise go unnoticed, so a quick confirm here matters
more than in the other Content Agent skills.

## 6. Assemble and save
Build the entries list as JSON (one entry per bullet/task from step 5:
`{"task_id": ... or omit for new, "description": ..., "category": ...,
"day_status": ..., "day_note": ..., "target_notes": ...}`), write it to a
temp file alongside `log_date`, `raw_input` (the bullet list verbatim),
and `daily_notes` (an optional one-line summary of the day, only if it
adds something the entries don't already say), then:
```
.venv/bin/python3 -m activity_agent.save_activity_log <project> <path-to-log.json>
```

## 7. Rebuild the dashboard
```
.venv/bin/python3 -m agent4_dashboard.build_dashboard_metronic <project>
.venv/bin/python3 -m agent4_dashboard.build_reporting_hub <project>
.venv/bin/python3 -m content_agent.build_content_page <project>
.venv/bin/python3 -m activity_agent.build_activity_page <project>
```
(All four -- the sidebar now has a fifth nav item, so every page needs
regenerating to stay in sync, same reason `/blog-outline` rebuilds more
than just its own page.)

## 8. Commit and push -- automatically, no separate confirmation step
Same established pattern as the Content Agent skills.
```
git add data/<project>/ docs/<project>/activity.html docs/<project>/activity_reports/ docs/<project>/index.html docs/<project>/history.html docs/<project>/reporting.html docs/<project>/content.html docs/<project>/reports/reporting-hub-latest.pdf
git commit -m "Log activity: <log_date>"
git push
```

## 9. Report back
Tell Rahul: how many tasks were logged (new vs. continued), how many were
completed/in-progress/not-started/blocked today, any tasks still open
that haven't moved in a while (worth a nudge), and the dashboard link:
```
.venv/bin/python3 -c "from projects import dashboard_url; print(dashboard_url('<project>') + 'activity.html')"
```

If Rahul's report included time ranges or time-spent figures per task,
mention that these are currently only preserved as text inside each
entry's `day_note`, not as a structured field -- there's no time-per-task
or hours-worked KPI yet. Worth flagging as a possible future addition if
he wants that tracked properly (a dedicated `time_spent_minutes` field
plus a "hours logged" KPI/chart), not something to build unprompted.
