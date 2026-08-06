# SEO Automation Platform — Roadmap Discussion (Draft)

**Status: exploratory, NOT finalized.** This document captures the *thinking* behind where this project is headed, discussed 2026-07-30. It exists so the reasoning isn't lost between conversations — it is deliberately not a committed plan. A finalized roadmap will replace/supersede this once priorities are locked in.

---

## 1. The vision (in Rahul's words)

The ultimate goal is a complete **SEO automation platform** for Simprosys — an internal tool/dashboard/web app that automates as much of the SEO workflow as possible, run from a single place, covering:

- Technical SEO audits
- On-page SEO
- Off-page SEO
- Keyword research
- Competitor analysis
- SWOT analysis
- Content planning / SEO content calendar
- Reporting
- Other recurring SEO tasks

Primary motivations: reduce manual work, and reduce dependency on third-party SEO tool subscriptions by building equivalent functionality in-house.

## 2. The development philosophy (carry forward to every module)

Same approach that built the SEO audit tool, applied platform-wide:

- **Rule-based / deterministic scripts first**, not AI reasoning models, for as much of the system as possible — cheaper, more predictable, easier to maintain and debug.
- Keep strengthening the rule-based logic until it's highly reliable, rather than reaching for AI to paper over gaps.
- **Modular design** — each module independently replaceable/upgradeable. If a specific module genuinely needs AI judgment later, a "thinking model" gets integrated *only* into that module, without touching the rest of the system.
- This mirrors the existing "general playbook" already written down in `PROJECT_REPORT.md` (Appendix) for the audit tool — this is that same discipline, scaled up to a full platform rather than a new approach.

## 3. Key constraint discovered during this discussion: multi-user

The platform needs to be usable by **multiple people**, not just Rahul. This changes the foundation significantly:

- The current setup (SQLite committed to git, static GitHub Pages, single weekly cron) assumes a single writer and no live editing or login. It cannot safely support concurrent edits or real authentication as-is.
- Several previously-separate concerns turn out to be the *same underlying gap*: the "Run Audit" button needing safe auth, the content calendar needing real writes, and the planned login wall — all need some form of real backend + shared database + multi-user auth. Solving this once as a deliberate "platform foundation" avoids three separate ad-hoc patches.

## 4. Roadmap sketch (phases, not yet prioritized/ordered by Rahul)

### Phase 0 — Platform Foundation
*Recommended to do before/alongside the next new module, given multi-user is now a confirmed requirement.*
- Real multi-user auth with roles (e.g. admin vs. viewer) — likely Cloudflare Access or a proper auth provider, not a single-email allowlist.
- A shared, concurrency-safe database instead of SQLite-in-git — e.g. Cloudflare D1 or a small managed Postgres (Supabase/Neon-style). Small-team usage should fit comfortably in free/low-cost tiers.
- A minimal backend/API layer (e.g. Cloudflare Workers) so the dashboard can accept writes — unlocks the content calendar, the "Run Audit" button, and any future editable module.
- Existing audit pipeline (crawl → validate → build dashboard) keeps running as-is; this phase gives it (and everything after) a real home instead of a static-file workaround.
- Honest cost note: this is the one place "no subscriptions" gets slightly relaxed — a backend + shared DB likely won't stay purely free forever at real usage, though small internal-team tools typically fit free/low-cost tiers.

### Phase 1 — Technical & On-Page SEO Audit *(already live, ongoing)*
Continues as-is. Current explicit priority: keep proving out rule accuracy over real weekly runs before adding scope.

### Phase 2 — SEO Content Calendar
Multi-user planning/tracking, replacing the spreadsheet. Fully rule-based (data management, not analysis) — no AI needed. Can cross-reference live audit findings for any URL already in the calendar. Needs Phase 0.

### Phase 3 — Reporting Hub
Consolidates audit history + content calendar status (and later other modules) into one exportable stakeholder view — extends the existing dashboard/PDF work. Fully rule-based (aggregation, not judgment).

### Phase 4 — Keyword Research
Mechanical version buildable on owned/free data: Google Search Console (own query/impression/click data per page), Google Trends, autocomplete/People-Also-Ask scraping. True search-volume/difficulty numbers realistically need a paid data source — Simprosys already has an Ahrefs connector available (currently unauthorized) that could be leaned on selectively rather than rebuilt from scratch.

### Phase 5 — Competitor Analysis
Reuses Agent 1's crawler almost directly — point it at a competitor's sitemap, run the same mechanical comparisons (title/meta length, schema presence, page speed, content length) side-by-side. Strong rule-based fit, cheap to build once the crawler exists.

### Phase 6 — Off-Page SEO
Hardest module to keep rule-based-and-free — a real backlink index requires crawling the whole web, impractical in-house. Search Console gives owned inbound-link data for free (partial win); a full picture likely still needs a paid backlink tool. Best treated as "assisted by a paid tool" rather than forced fully in-house.

### Phase 7 — SWOT / Strategic Synthesis
Clearest, most honest candidate for the AI-judgment phase — a real SWOT is inherently comparative/interpretive, not mechanical. Synthesizes outputs from every other module (audit + keyword + competitor + off-page) once they exist. Building this last, scoped to just this one module, matches the stated modular philosophy exactly.

## 5a. Progress since this document was first written (2026-07-30, same day)

Work continued within Phase 1 (rule-accuracy hardening) and on the dashboard itself, both still pre-Phase-0:

- **Rule refinements**: identified and implemented exclusions for pages that shouldn't be judged by evergreen-content rules — `/job-description` (temporary job postings, implemented as a partial suppression at validation), `/simprotips/search` and `simprosys.com/sitemap.xml` (blog search utility page and the sitemap's own self-listing, both implemented 2026-07-30 as full exclusions at crawl discovery, per Rahul's explicit request). See `PROJECT_REPORT.md` §6 for full detail — this is exactly the kind of accuracy-hardening work Rahul said should come before Phase 0/2.
- **Dashboard fully redesigned to Metronic style**, replacing the classic design entirely (not kept as an option) — see `PROJECT_REPORT.md` §6. This happened independently of the Phase 0 foundation work above; it's a pure visual/UX change to the existing static-site dashboard, not a move toward multi-user editing yet.
- **Real-world reminder of the "local code has no effect until pushed" gotcha**: a rule change was tested locally, then a real audit run was triggered expecting to see it reflected — it wasn't, because the change hadn't been committed/pushed yet. Worth keeping in mind for every future module: nothing is "live" until it's on `origin/main` and a fresh run has happened after that.
- As of this update, the `/job-description` fix and the Metronic dashboard promotion are sitting locally, not yet committed/pushed (see `PROJECT_REPORT.md` §11 for the current blocker).

## 5b. Decision: build the "rule-based only" modules first (2026-08-03)

Rahul confirmed the priority order among Phases 2-7 (previously left open, §5 above): start with whichever modules are **fully rule-based and can just write into the existing static dashboard**, deferring anything that needs the Phase 0 multi-user foundation (real writes/auth/backend). Identified as fitting that bar, in build order:

1. **Reporting Hub** (was Phase 3) — pure aggregation of data already in `data/seo_audit_history.db`, zero new infrastructure. **Built 2026-08-03** — see `PROJECT_REPORT.md` §6, `agent4_dashboard/build_reporting_hub.py`.
2. **Competitor Analysis** (was Phase 5) — reuses Agent 1's crawler against a competitor sitemap, same mechanical checks side-by-side. Not started yet.
3. **Keyword Research — mechanical slice only** (was Phase 4) — Search Console query/impression/click data, Trends, autocomplete/PAA. Needs a new GSC API credential but no live-write backend. Not started yet.
4. **Off-Page SEO — owned-data slice only** (was Phase 6) — GSC's own inbound-links report, same credential as #3. The full paid-tool-dependent backlink index stays out of scope. Not started yet.

Explicitly excluded from this "rule-based, no new infra" bucket: **Content Calendar** (Phase 2, needs real multi-user writes → needs Phase 0) and **SWOT** (Phase 7, inherently judgment-based, not rule-based).

## 5c. New module: Content Agent (2026-08-04) — not one of the original Phases 2-7

Rahul's own idea, closest in spirit to the Content Calendar phase but distinct from it: a **Content Agent** to help produce blog posts, split into three agents — **Outliner, Writer, QA Checker** (rate a draft out of 10). First proposed as a full research-grounded pipeline (SERP scraping, paid search API); Rahul judged that too big/complex and scoped it down himself: he owns the research (topic, keywords, heading hierarchy, CTA) entirely, the agents only need to outline/write/score.

Key constraint that shaped the build: **no budget for a paid API/tools plan**. Ruled out a standalone script calling the Anthropic API directly (real per-call billing) in favor of building each agent as a **Claude Code skill**, run interactively — no separate API key, rides on existing Claude Code access, and is naturally human-in-the-loop (Rahul triggers each step and watches it happen) rather than unattended automation like the audit cron.

**Outliner Agent built 2026-08-04** — see `PROJECT_REPORT.md` §12, `content_agent/`, `.claude/skills/blog-outline/SKILL.md`. Rahul's own framing for how this stays accurate without paid research tools: the brief (from Outliner) + shared example blogs + the QA Checker's score-out-of-10 gate together do the job that expensive live-web research would otherwise do — consistency comes from those three things, not from which door reaches Claude.

**Writer Agent built same day, 2026-08-04** — `/blog-write` (`.claude/skills/blog-write/SKILL.md`), writes prose section-by-section from a saved brief, real word counts computed from the text itself (never trusted from the model). Two explicit decisions Rahul made when asked rather than defaulted: **PDF-only export** (not Markdown, despite the recommendation to make editing easier — matches the brief's existing pattern), and **overwrite-only, no draft version history** (simpler for now; add versioning later only if actually needed).

**QA Checker Agent built 2026-08-05** — `/blog-qa` (`.claude/skills/blog-qa/SKILL.md`), completing all three planned agents. Per Rahul's explicit steer: instead of just a bare score, it's a full report (word count, keyword coverage/density, readability, sentence complexity, passive voice, banned phrases), all computed deterministically in `content_agent/qa_checks.py` and recomputed fresh at save time — never trusted from the skill conversation. The skill adds only one genuinely judgment-based input, a small `judgment_adjustment` capped at ±2.0, plus a short qualitative note. **Scoring math is explicitly a v1** — Rahul wants to research proper scoring approaches and update the deduction values later; every deduction is itemized with its reason specifically so that's easy to do without touching the rest.

Also per Rahul's request: a shared **banned AI-cliche phrase list** (`content_agent/banned_phrases.py`, ~37 phrases) used in two places — the Writer's instructions mirror it directly (avoid these while writing, so QA is a safety net rather than routine rework), and the QA Checker scans for it (catch anything that slipped through). The two copies have to be kept in sync by hand since a skill file is markdown, not something that can import a Python list.

**Dashboard reorganized into three tabs same day** (Outline / Draft / QA Checker, `content_agent/build_content_page.py`) — client-side switching, every brief shown in every tab with a placeholder row for stages it hasn't reached yet, and the same scrollable modal format reused identically across all three per Rahul's explicit ask for one consistent format.

**A real bug found by testing against real data**: the QA Checker's "is this the conclusion" detection originally matched on the section's `level` field against the synthetic `"conclusion"` sentinel `word_budget.py` uses for unheaded slots -- which silently missed the actual Google Merchant Center brief's real, Rahul-authored "Conclusion" H2 (stored with level `"H2"`, not the sentinel). Fixed to detect by position (first/last section) instead. Worth remembering as a general lesson: test QA/validation logic against real, human-authored data, not just the synthetic shapes a function was designed around -- real briefs don't always match the assumptions baked into helper code.

**Dash-usage check + mixed-content formatting added 2026-08-05, both from Rahul reading the actual GMC draft**: he flagged two things at once (see `PROJECT_REPORT.md` §12 for the full detail) -- the draft leaned on `--`/em-dash asides as a repetitive sentence construction, and it was written as unbroken prose even where the content was genuinely list-shaped (steps, options, a caveat worth calling out). Both got the same prevention (Writer skill instructions) + detection (QA Checker, `qa_checks.py`) treatment as the banned-phrase list, and the GMC draft was regenerated and re-reviewed against the new rules the same day (0 dash-asides, several sections reformatted into real lists, 9.5/10 final QA score). Confirms the pattern established with the banned-phrase list: catching a real quality issue Rahul notices by reading actual output, then building both a skill-level instruction and a deterministic QA check for it, works well and should keep being the default response to this kind of feedback.

## 5d. New module: Activity Agent (2026-08-05) — not one of the original Phases 2-7, and separate from the Content Agent

Rahul's own idea, same "not one of the original phases" category as the Content Agent (§5c): a day-to-day work log, "Activity & Performance," so he can report what he did each day and see it structured on the dashboard rather than keeping it in his head or a separate document. Explicitly scoped as its own section, not folded into the Reporting Hub's existing cross-module activity feed — he was clear this stays separate.

The design turned out to be more than "one log per day" once he explained what "performance" meant to him: tasks aren't always finished same-day, and he wants to track progress toward a defined goal, not just log that something happened. See `PROJECT_REPORT.md` §13 for the full build — the short version is that `activity_agent/database.py` tracks tasks as persistent entities that can span several days (status: in_progress/completed/blocked, plus an optional target/deadline note) linked to day-by-day log entries, rather than one flat blob per date. The `/log-activity` skill's one real judgment call is matching today's bullet list against tasks still open from previous days before saving — everything else (KPI counts, category rollups, week/month PDF ranges) is deterministic, same rule-based-where-possible split as every other module on this platform.

Inputs Rahul confirmed before this was built: reports come in as a bullet list (not freeform paragraphs), categories are supplied by him per report rather than fixed in advance, and daily/weekly/monthly PDFs were wanted now with a custom date-range export explicitly deferred to later.

## 5e. New module: Keyword Research (2026-08-06) — not one of the original Phases 2-7

Grew out of a real problem Rahul described, not a platform-roadmap item: he had 10,000+ competitor keywords spread across 28 Google Sheets (25+ competitors, exported from Google Keyword Planner) and was manually deduplicating them by hand. Scoped through the same conversational back-and-forth as the other modules before any code was written — three separate rounds of clarifying questions (report focus, how to handle conflicting numbers for the same keyword across sources, and whether this should be reusable) rather than guessing, since getting the analysis wrong across 10k+ rows would be expensive to redo.

Key decisions, all Rahul's explicit choices (2026-08-06):
- **All four requested insight views** (competitor overlap, opportunity keywords, trending keywords, per-competitor summary) — "all of the above you suggest me."
- **Conflicting values for the same keyword across sources**: keep whichever sheet's numbers were seen first, rather than averaging or flagging disagreements — simplest, and good enough since these numbers are usually close across sources anyway.
- **Reusable, dashboard-integrated module**, not a one-off script — "i want to add it in our dashboard so whenever i need it then i'll working on it without any script."
- **Both a cumulative master list AND standalone per-batch reports**, not one or the other — "sometimes i have master sheet and sometimes don't have so that." This is why every batch gets its own permanent record regardless of whether it feeds the master aggregation.

See `PROJECT_REPORT.md` §14 for the full build. Same rule-based-where-possible split as every other module: which competitor/sheet actually gets pulled from Google Sheets and read is a skill-level, judgment-adjacent step (matching column names that vary slightly across exports, handling a sheet that isn't reachable); everything after that — dedup, percentile-based opportunity thresholds, overlap/trending/summary math — is plain deterministic Python, fully reproducible for the same input.

Two follow-up asks landed the same day, after the first 23-competitor batch was live:
- **Pagination on the Opportunity Keywords table** — it had no cap (unlike the other three insight views, which are top-N), and with the real data that's thousands of rows.
- **Inconsistent spacing between cards dashboard-wide** — traced to the shared `.card` class never having had a `margin-bottom`, so stacked cards touched while grid rows (KPI tiles, the two-column chart row) kept their gap. Fixed once in the shared stylesheet, not per-page.

## 5f. Keyword quality filters (2026-08-06)

Rahul's follow-up ask: strip keywords containing brand names, and keywords with a word repeated inside them ("hotel hotel management") — "not showing them in the whole dashboard or module," entirely, not just hidden in the UI. Confirmed scope through a quick back-and-forth: "brand" means both his 28 tracked competitors *and* the much bigger real source of noise — specific hotel/resort property names that Google Keyword Planner surfaces (kk royal, radisson, byke old anchor...). No dictionary of hotel brand names exists anywhere, and Rahul explicitly declined a review round or keeping a log of what gets dropped — "just dropped them... if in future we require then we'll think about it."

Built as an elimination heuristic instead of a brand list: a word not in a real English dictionary, not known industry jargon, and not a real place name is almost always a proper noun in this dataset. See `PROJECT_REPORT.md` §14 for the mechanics and the explicitly disclosed limitation (an unusual town/hotel name could land on the wrong side of it — fix by extending an allow-list, not by rebuilding it).

## 5. Open questions / not yet decided

- No priority order confirmed yet among Phases 2-7 (explicitly deferred by Rahul, 2026-07-30).
- Exact technology choices for Phase 0 (which auth provider, which database) not yet decided — the above are illustrative options, not commitments.
- Whether Phase 0 happens as its own dedicated effort before Phase 2, or gets built incrementally alongside the first module that needs it, is still open.
- Which existing third-party tools (if any — Ahrefs, or others) Simprosys currently pays for and wants to keep leaning on selectively vs. fully replace, not yet enumerated.

---

*Next step when ready: revisit this document, lock in a priority order and Phase 0 technology choices, and produce a finalized roadmap (likely as an update to `PROJECT_REPORT.md` or a dedicated `ROADMAP.md`).*
