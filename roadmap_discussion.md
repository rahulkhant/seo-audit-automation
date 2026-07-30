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

- **Rule refinements**: identified and (partially) implemented exclusions for pages that shouldn't be judged by evergreen-content rules — `/job-description` (temporary job postings, implemented), `/simprotips/search` (blog search utility page, agreed but not yet implemented), and `simprosys.com/sitemap.xml` (build artifact, agreed but not yet implemented). See `PROJECT_REPORT.md` §6 for full detail — this is exactly the kind of accuracy-hardening work Rahul said should come before Phase 0/2.
- **Dashboard fully redesigned to Metronic style**, replacing the classic design entirely (not kept as an option) — see `PROJECT_REPORT.md` §6. This happened independently of the Phase 0 foundation work above; it's a pure visual/UX change to the existing static-site dashboard, not a move toward multi-user editing yet.
- **Real-world reminder of the "local code has no effect until pushed" gotcha**: a rule change was tested locally, then a real audit run was triggered expecting to see it reflected — it wasn't, because the change hadn't been committed/pushed yet. Worth keeping in mind for every future module: nothing is "live" until it's on `origin/main` and a fresh run has happened after that.
- As of this update, the `/job-description` fix and the Metronic dashboard promotion are sitting locally, not yet committed/pushed (see `PROJECT_REPORT.md` §11 for the current blocker).

## 5. Open questions / not yet decided

- No priority order confirmed yet among Phases 2-7 (explicitly deferred by Rahul, 2026-07-30).
- Exact technology choices for Phase 0 (which auth provider, which database) not yet decided — the above are illustrative options, not commitments.
- Whether Phase 0 happens as its own dedicated effort before Phase 2, or gets built incrementally alongside the first module that needs it, is still open.
- Which existing third-party tools (if any — Ahrefs, or others) Simprosys currently pays for and wants to keep leaning on selectively vs. fully replace, not yet enumerated.

---

*Next step when ready: revisit this document, lock in a priority order and Phase 0 technology choices, and produce a finalized roadmap (likely as an update to `PROJECT_REPORT.md` or a dedicated `ROADMAP.md`).*
