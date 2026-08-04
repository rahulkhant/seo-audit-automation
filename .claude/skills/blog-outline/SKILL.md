---
description: "Content Agent, step 1 of 3 (Outliner): collect blog inputs from the user, expand the given heading hierarchy into a full section-by-section writing brief, save it to the database, rebuild the dashboard's Content page, and push -- so the outline is live without a separate manual step."
---

You are running the Outliner Agent -- the first of three planned Content
Agent modules (Outliner, Writer, QA Checker; only this one exists so far).
Rahul owns the research: topic, keywords, heading hierarchy, and CTA all
come from him. Your job is to turn that into a precise, section-by-section
writing brief that a future Writer step (human or AI) can follow without
guessing -- and to do it the same rule-based-where-possible way as the
rest of this project: word-count math is deterministic Python, only "what
should this section actually say" is your own judgment.

Do the following, in order:

## 1. Confirm working directory
If not already there, change to `/Users/rahul/Desktop/Automation/seo-audit-automation`.

## 2. Collect the inputs
If the user's request already included some of these, don't re-ask for
them -- only ask conversationally for what's missing:

- **Topic**
- **Primary keyword**
- **Secondary keywords** (a list; can be empty)
- **Content format** (how-to guide, listicle, comparison, ultimate guide, etc.)
- **Target word count** (a number)
- **Heading hierarchy** -- the user's own H2/H3 list (NOT the H1/title --
  that's the topic). Ask for it as a simple ordered list with each
  heading's level noted (e.g. "H2: What is X / H3: Common mistakes / H2: How it works").
- **Target audience**
- **Search intent** (informational, commercial, transactional, navigational)
- **Tone of voice**
- **CTA** -- what action/link the post should drive toward
- **Other notes** (anything else that must be covered or avoided) -- optional

## 3. Validate before doing anything else
- Topic and primary keyword must be non-empty text.
- Target word count must be a positive whole number.
- Headings list must have at least one entry, each with a level of H2 or
  H3, and no H3 should appear before any H2 (that's a broken hierarchy).

If anything is missing or doesn't make sense, ask the user to clarify
rather than guessing or silently proceeding with a bad assumption.

## 4. Load reference examples, if any exist
```
ls content_agent/example_blogs/*.md content_agent/example_blogs/*.txt 2>/dev/null
```
If files exist, read them for a sense of typical section pacing and tone.
If none exist yet, proceed without -- don't nag the user about it every
single run, a one-line mention is enough.

## 5. Compute word budgets (deterministic -- run this, don't estimate by hand)
Build the headings list (excluding H1) as JSON and run:
```
.venv/bin/python3 -c "
import json, sys
from content_agent.word_budget import allocate_word_budget
headings = json.loads(sys.argv[1])
target = int(sys.argv[2])
print(json.dumps(allocate_word_budget(headings, target)))
" '<headings-json>' <target_word_count>
```
This returns the section list with `word_budget` already filled in,
including the intro/conclusion slots. Do not recompute or override these
numbers yourself -- they're the one part of this whole agent that's
supposed to be exactly reproducible math, not judgment.

## 6. Write the actual brief content (this is your judgment step)
For every section in the budgeted list (including intro and conclusion),
decide and fill in:
- `points_to_cover`: 2-4 sentences of what this section must actually say
  -- specific angles/points, not a restatement of the heading.
- `keywords`: which keyword(s) belong naturally in this section. Make sure
  every secondary keyword lands in at least one section across the whole
  brief, and the primary keyword covers the highest-value spots (intro,
  at least one H2, conclusion).
- `notes`: anything section-specific worth flagging -- most importantly,
  note the CTA placement (usually the conclusion, but say so explicitly
  rather than leaving it implicit).

Show the assembled outline in the chat as you build it, so Rahul sees it
forming in real time -- he's not approving a hidden step, this whole
process should be visible.

## 7. Save the brief
Write the finished brief as JSON (matching the shape in
`content_agent/database.py`'s `save_brief` docstring) to a temp file, then:
```
.venv/bin/python3 -m content_agent.save_brief <path-to-brief.json>
```
This prints the new `brief_id`.

## 8. Rebuild the dashboard
```
.venv/bin/python3 -m agent4_dashboard.build_dashboard_metronic
.venv/bin/python3 -m agent4_dashboard.build_reporting_hub
.venv/bin/python3 -m content_agent.build_content_page
```
(All three, not just the Content page -- the shared sidebar now includes
a "Content" link, so every page needs regenerating to stay in sync.)

## 9. Commit and push -- automatically, no separate confirmation step
This was an explicit decision: this skill pushes on its own, the same way
the SEO audit's GitHub Actions workflow already does.
```
git add data/seo_audit_history.db docs/content.html docs/content_briefs/ docs/index.html docs/history.html docs/reporting.html docs/reports/reporting-hub-latest.pdf
git commit -m "Add content outline: <topic>"
git push
```

## 10. Report back
Tell Rahul: the brief_id, a short summary of the outline, and the
dashboard link: https://rahulkhant.github.io/seo-audit-automation/content.html
