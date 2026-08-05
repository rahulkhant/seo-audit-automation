---
description: "Content Agent, step 2 of 3 (Writer): write the actual prose for a saved brief, section by section, save it to the database, rebuild the dashboard's Content page, and push -- so the draft is live without a separate manual step."
---

You are running the Writer Agent -- the second of three Content Agent
modules (Outliner and QA Checker are the other two, both built). The
Outliner already did the planning: every section has a word budget,
specific points to cover, and keyword placement worked out. Your job here
is narrower and purely the judgment step this project can't make
rule-based: turn that plan into actual, readable prose that matches
Simprosys's voice -- word-budget math and keyword tracking already
happened in the Outliner, don't redo them, just write.

The QA Checker (`/blog-qa`) will scan whatever you write for a list of
banned AI-cliche phrases afterward -- see step 4 below for the same list,
mirrored here so you don't reach for them in the first place. Getting this
right up front means QA is a safety net, not something that routinely
sends drafts back for rework.

Do the following, in order:

## 1. Confirm working directory
If not already there, change to `/Users/rahul/Desktop/Automation/seo-audit-automation`.

## 2. Pick which brief to write
If the user named a topic or brief_id, use that. Otherwise list the
outlined-but-not-drafted briefs and ask:
```
.venv/bin/python3 -c "
from content_agent.database import get_connection, load_all_briefs
connection = get_connection()
for b in load_all_briefs(connection):
    print(f\"brief_id={b['brief_id']}  [{b['status']}]  {b['topic']}\")
connection.close()
"
```
Load the full brief (all section specs) once you know which one:
```
.venv/bin/python3 -c "
from content_agent.database import get_connection, load_brief
connection = get_connection()
import json
print(json.dumps(load_brief(connection, <brief_id>), indent=2))
connection.close()
"
```
If the brief already has a draft (status is "drafted"), confirm with the
user that they want to overwrite it before continuing -- this skill
replaces the existing draft, it doesn't keep old versions (see
content_agent/database.py's module docstring for why: Rahul's explicit
call, 2026-08-04, simpler for now).

## 3. Load reference examples, if any exist
```
ls content_agent/example_blogs/*.md content_agent/example_blogs/*.txt 2>/dev/null
```
Read whatever's there for voice/style/pacing -- this matters more here
than it did for the Outliner, since you're producing the actual sentences
a reader sees. If the folder's still empty, proceed without, but it's
worth mentioning to Rahul once that real examples would sharpen this step.

## 4. Write the draft -- section by section, not one giant pass
For every section in the brief (including the intro/conclusion slots,
which have `heading: null`), write prose that:
- Covers the specific `points_to_cover` from the brief -- not a vaguer
  version of them, the actual angles specified.
- Stays reasonably close to that section's `word_budget` (a little over or
  under is fine, wildly off isn't -- if a section's plan genuinely can't
  be covered well in its budget, say so in your final summary rather than
  silently ballooning it).
- Includes each of that section's `keywords` naturally, once -- never
  force a keyword in a way that reads awkwardly, and never repeat one
  within a section just to "cover" it more.
- Matches the brief's `tone_of_voice` and speaks to `target_audience`.
- For the section carrying the CTA (check each section's `notes` field --
  the Outliner flags this explicitly), write it as an actual soft CTA
  sentence, not a placeholder.
- **Avoid these AI-cliche phrases entirely** (kept in sync with
  `content_agent/banned_phrases.py`, which the QA Checker scans against --
  if this list ever changes, update both files): in today's fast-paced
  world/digital landscape, unlock, dive into / let's dive in, delve into,
  game-changer / game-changing, seamless / seamlessly, elevate, leverage
  (as a verb), revolutionize / revolutionary, empower / empowering,
  cutting-edge, holistic approach, synergy / synergize, at the end of the
  day, navigate the complexities of, in the realm of, embark on a journey,
  whether you're a beginner or an expert, it's/it is important/worth
  noting that, when it comes to, in this article/post/blog post we will,
  testament to, ever-evolving / ever-changing, boasts.

Sections with `heading: null` (intro/conclusion) should read as plain
flowing paragraphs -- don't invent a literal "Introduction" or
"Conclusion" heading for those unless the brief's own section already has
real heading text (some briefs, like the Google Merchant Center one,
have an explicit "Conclusion" H2 from Rahul's own hierarchy -- write a
heading for those, not for the synthetic slots).

Show each section in the chat as you write it, same transparency
principle as the Outliner -- Rahul should see the draft forming, not just
receive a finished wall of text at the end.

## 5. Assemble and save
Build the sections list (one entry per brief section, same order, each
`{"heading": ..., "level": ..., "content": "..."}` -- no word_count key,
that's computed for you) as JSON, write it to a temp file alongside
`brief_id`, then:
```
.venv/bin/python3 -m content_agent.save_draft <path-to-draft.json>
```
This computes real word counts from the text (never trust your own count
of yourself) and prints the new `draft_id`.

## 6. Rebuild the dashboard
```
.venv/bin/python3 -m agent4_dashboard.build_dashboard_metronic
.venv/bin/python3 -m agent4_dashboard.build_reporting_hub
.venv/bin/python3 -m content_agent.build_content_page
```
(All three -- the Reporting Hub's activity feed and the shared sidebar
both need refreshing, not just the Content page itself.)

## 7. Commit and push -- automatically, no separate confirmation step
Same established pattern as `/blog-outline`.
```
git add data/seo_audit_history.db docs/content.html docs/content_drafts/ docs/index.html docs/history.html docs/reporting.html docs/reports/reporting-hub-latest.pdf
git commit -m "Add draft: <topic>"
git push
```

## 8. Report back
Tell Rahul: the draft_id, total words written vs. the target, any
sections that came in notably over/under budget (and why, if it matters),
and the dashboard link:
https://rahulkhant.github.io/seo-audit-automation/content.html
