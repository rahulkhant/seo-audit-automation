---
description: "Content Agent, full pipeline in one command: collect blog inputs once, then automatically run the Outliner, Writer, and QA Checker back to back with no further input needed -- save everything, rebuild the dashboard once, and push."
---

You are running the full Content Agent pipeline in one pass: Outliner,
then Writer, then QA Checker, one after another, with no separate
command needed between stages. Rahul (or a teammate) gives the research
inputs once at the very start -- topic, keywords, heading hierarchy, CTA,
etc. -- and everything after that runs automatically: the Writer and QA
Checker stages need no further input from whoever is running this.

This merges `/blog-outline`, `/blog-write`, and `/blog-qa` into one
command for the common case: writing a full blog post start to finish.
The three original skills still exist separately in
`.claude/skills/blog-outline/`, `blog-write/`, `blog-qa/` for targeted
reruns where you only want one stage -- e.g. regenerating just a draft
after a writing-rule change (like the no-dash-aside/mixed-content fixes),
or re-running just the QA check on an existing draft. Use those directly
for that. This command always creates a brand new brief and takes it all
the way through, so there's no overwrite/conflict question to ask here --
unlike the individual skills, which can target an already-existing
brief_id and need to confirm before replacing something.

Do the following, in order:

## 1. Confirm working directory
If not already there, change to `/Users/rahul/Desktop/Automation/seo-audit-automation`.

## 2. Collect the inputs (once, up front -- Outliner stage)
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

This is the only input gathering step in the whole pipeline -- nothing
after this point should require going back to ask for more.

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
If files exist, read them now -- you'll want them both for the outline's
pacing (step 6) and for the draft's voice/style later (step 8). If none
exist yet, proceed without, a one-line mention is enough.

## 5. Compute word budgets (deterministic -- Outliner stage, run this, don't estimate by hand)
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
numbers yourself.

## 6. Write the outline content (Outliner judgment step)
For every section in the budgeted list (including intro and conclusion),
decide and fill in:
- `points_to_cover`: 2-4 sentences of what this section must actually say
  -- specific angles/points, not a restatement of the heading.
- `keywords`: which keyword(s) belong naturally in this section. Make sure
  every secondary keyword lands in at least one section across the whole
  brief, and the primary keyword covers the highest-value spots (intro,
  at least one H2, conclusion).
- `notes`: anything section-specific worth flagging -- most importantly,
  note the CTA placement (usually the conclusion, but say so explicitly).

Show the assembled outline in the chat as you build it, so whoever's
running this sees it forming in real time.

## 7. Save the brief
Write the finished brief as JSON (matching the shape in
`content_agent/database.py`'s `save_brief` docstring) to a temp file, then:
```
.venv/bin/python3 -m content_agent.save_brief <path-to-brief.json>
```
This prints the new `brief_id`. Don't rebuild the dashboard or commit yet
-- that happens once at the very end (step 12), after all three stages
are done.

## 8. Write the draft -- no further input needed (Writer stage)
Using the brief_id from step 7, write the draft section by section (not
one giant pass). For every section in the brief (including the
intro/conclusion slots, which have `heading: null`), write prose that:
- Covers the specific `points_to_cover` from the brief -- the actual
  angles specified, not a vaguer version of them.
- Stays reasonably close to that section's `word_budget` (a little over
  or under is fine, wildly off isn't -- flag it in the final summary
  rather than silently ballooning a section).
- Includes each of that section's `keywords` naturally, once.
- Matches the brief's `tone_of_voice` and speaks to `target_audience`.
- For the section carrying the CTA (check each section's `notes` field),
  write it as an actual soft CTA sentence, not a placeholder.
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
- **Never use a dash-based aside** -- neither a literal `--` nor a real
  em-dash `—`. Rewrite the thought as two sentences, or use a comma or
  colon instead. `content_agent/qa_checks.py`'s `check_dash_usage()`
  scans for this too, same prevention + detection split as the
  banned-phrase list.

Sections with `heading: null` (intro/conclusion) should read as plain
flowing paragraphs -- don't invent a literal "Introduction" or
"Conclusion" heading for those unless the brief's own section already has
real heading text.

**Use mixed content, not only paragraphs.** Within a section's `content`
string, blank-line-separated blocks are parsed into real formatting by
`content_agent/build_content_page.py`'s `_parse_content_blocks()`:
- A block where every line starts with `- ` becomes a bullet list.
- A block where every line starts with `1. ` (`2. `, `3. `, ...) becomes
  a numbered list.
- A block starting with `Note: ` becomes a styled callout box.
- Anything else stays a plain paragraph.

Pick the format the content actually calls for: sequential steps ->
numbered list; unordered options/rules/examples -> bullet list; a
specific caveat worth making visually distinct -> note; general
explanation that doesn't reduce to a list -> stays prose. Not every
section needs a list.

Show each section in the chat as you write it, same transparency
principle as the outline step.

## 9. Save the draft
Build the sections list (one entry per brief section, same order, each
`{"heading": ..., "level": ..., "content": "..."}` -- no word_count key,
that's computed for you) as JSON, write it to a temp file alongside
`brief_id`, then:
```
.venv/bin/python3 -m content_agent.save_draft <path-to-draft.json>
```
This computes real word counts from the text and prints the new
`draft_id`. Still no rebuild/commit yet.

## 10. Run the QA Checker -- no further input needed
Preview the deterministic report:
```
.venv/bin/python3 -c "
import json
from content_agent.database import get_connection, load_brief, load_draft_for_brief
from content_agent.qa_checks import run_deterministic_checks, compute_score
connection = get_connection()
brief = load_brief(connection, <brief_id>)
draft = load_draft_for_brief(connection, <brief_id>)
connection.close()
deterministic = run_deterministic_checks(brief, draft)
print(json.dumps(deterministic, indent=2))
print(json.dumps(compute_score(deterministic), indent=2))
"
```
Read this carefully -- word count, keyword coverage/density, readability,
sentence complexity, passive voice, banned phrases, dash usage, plus what
the score would be with zero judgment adjustment.

Then read the full draft end to end (not skimmed) and decide:
- **judgment_adjustment**: -2.0 to +2.0, a small nudge on top of the
  deterministic score, not the dominant factor. Negative for real
  flow/naturalness problems the deterministic checks can't see; positive
  only if the writing is genuinely better than the deterministic score
  alone suggests. Zero is a completely valid answer.
- **judgment_notes**: 2-4 sentences, specific -- name what's actually
  good or off, pointing at a specific section if there's an issue.

A note on the scoring math (Rahul, 2026-08-05): the point deductions in
`content_agent/qa_checks.py` are a reasonable v1, not final -- don't try
to "fix" the math yourself; just use it as-is and mention in the summary
if a deduction seems off.

## 11. Save the QA review
Write `{"judgment_adjustment": ..., "judgment_notes": "..."}` to a temp
file, then:
```
.venv/bin/python3 -m content_agent.save_qa_review <brief_id> <path-to-judgment.json>
```
This recomputes the deterministic report fresh and prints the final
review_id and score.

## 12. Rebuild the dashboard -- once, for all three stages together
```
.venv/bin/python3 -m agent4_dashboard.build_dashboard_metronic
.venv/bin/python3 -m agent4_dashboard.build_reporting_hub
.venv/bin/python3 -m content_agent.build_content_page
```
(All three -- the Reporting Hub's activity feed and the shared sidebar
both need refreshing, not just the Content page.)

## 13. Commit and push -- automatically, no separate confirmation step
One commit covering the outline, draft, and QA review together.
```
git add data/seo_audit_history.db docs/content.html docs/content_briefs/ docs/content_drafts/ docs/content_qa/ docs/index.html docs/history.html docs/reporting.html docs/reports/reporting-hub-latest.pdf
git commit -m "Add blog post: <topic>"
git push
```

## 14. Report back
Tell whoever's running this, in one summary covering all three stages:
- The brief_id and a short summary of the outline.
- The draft's total word count vs. the target, and any sections that
  came in notably over/under budget.
- The final QA score out of 10, every deduction with its reason, and the
  judgment notes.
- The dashboard link: https://rahulkhant.github.io/seo-audit-automation/content.html
