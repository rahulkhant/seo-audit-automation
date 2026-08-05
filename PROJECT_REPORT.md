# SEO Audit Automation — Project Report

**Purpose of this document**: a complete, self-contained record of this project — what it is, how it's built, what's live, and what's intentionally deferred. Written so it can be handed to any future AI assistant (or read by yourself months from now) without needing to re-explain any context from scratch.

---

## 1. What this project is

An automated, unattended weekly technical + on-page SEO audit for the company website **simprosys.com**, built for **Rahul Khant, SEO Executive at Simprosys**, who has no coding background. Every week (and on-demand), the system crawls the site, checks it against a defined SEO rulebook, and delivers the results as a dashboard + email — with zero manual work once set up.

- **Owner / user**: Rahul Khant (rahulkhant@simprosys.com)
- **GitHub account**: `rahulkhant` (company account, not personal)
- **Repository**: https://github.com/rahulkhant/seo-audit-automation (public — see §7 for why)
- **Live dashboard**: https://rahulkhant.github.io/seo-audit-automation/
- **Local project path**: `/Users/rahul/Desktop/Automation/seo-audit-automation`

## 2. How Rahul likes to work (carry this forward to any future project)

- **No coding background** — every piece of code must be written with detailed comments explaining the *why*, not just the *what*.
- **Staged build process** — build one small piece, explain it, get explicit approval, *then* move to the next piece. Never dump a large finished system unreviewed.
- **Test against real data, not assumptions** — every component was tested against the live simprosys.com site before moving on, and unexpected results were investigated (not hand-waved) until the root cause was understood. This caught several real bugs (see §8).
- **Prove accuracy before adding scope** — deliberately shipped a smaller, 100%-mechanical rule set first rather than a bigger one with AI-judgment calls mixed in, specifically to build trust in the system before expanding it.
- Prefers being asked before consequential/irreversible actions (e.g., making the repo public was a real decision point, not assumed).

## 3. Architecture

Four independent, modular "agents" (really: pipeline stages), each with a single responsibility, tied together by one orchestrator:

```
Agent 1 (Crawl)  ->  Agent 2 (Storage)  ->  Agent 3 (Validation)  ->  Agent 4 (Dashboard)     ->  Notification
  crawl_runner.py      database.py          run_validation.py         build_dashboard_metronic.py  send_digest_email.py
                                                                       (+ build_dashboard.py for PDF archive)
                                                                       (+ build_reporting_hub.py for trends page)
```

`main.py` runs all five steps in sequence. Each stage also works standalone (useful for testing/debugging without re-running the whole pipeline).

### Repository structure
```
seo-audit-automation/
├── main.py                          # Orchestrator: runs all 5 steps in sequence
├── requirements.txt                 # requests, beautifulsoup4, playwright, python-dotenv
├── .env / .env.example              # SMTP credentials (real file gitignored)
├── .gitignore
├── data/
│   ├── seo_audit_history.db         # SQLite -- COMMITTED to git (see §7, persistence)
│   └── latest_crawl.json            # Intermediate debug artifact -- gitignored
├── docs/
│   ├── index.html                   # Main Dashboard -- Metronic-styled (served by GitHub Pages)
│   ├── history.html                 # Report History -- one line per past run, PDF download only
│   ├── reporting.html                # Reporting Hub -- trend charts + category-by-run table across all runs
│   ├── content.html                  # Content Outlines -- Outline/Draft/QA Checker tabs, every brief
│   ├── content_briefs/brief-XXXX.pdf  # One outline PDF per brief (structured spec)
│   ├── content_drafts/draft-XXXX.pdf  # One draft PDF per written draft (reads like an article)
│   ├── content_qa/qa-XXXX.pdf         # One QA report PDF per reviewed brief
│   └── reports/
│       ├── run-XXXX.pdf              # Permanent PDF archive, one file per run
│       └── reporting-hub-latest.pdf  # Trend summary PDF -- overwritten every run, not archived per-run
├── agent1_crawl/
│   ├── sitemap_discovery.py         # Reads robots.txt + sitemap.xml -> list of URLs to crawl
│   ├── page_extractor.py            # Fetches ONE page (raw + Playwright-rendered), extracts SEO data
│   └── crawl_runner.py              # Loops over all URLs politely, saves data/latest_crawl.json
├── agent2_storage/
│   └── database.py                  # SQLite schema (runs/pages/findings tables) + save functions
├── agent3_validation/
│   ├── rules_config.py              # All thresholds (title length, meta length, etc.) + EXCLUDED_URL_PATH_PREFIXES
│   ├── page_checks.py               # Per-page rule checks (35 rules)
│   ├── site_checks.py               # Cross-page rule checks (6 rules)
│   └── run_validation.py            # Runs all checks, saves findings to DB
├── agent4_dashboard/
│   ├── build_dashboard.py           # Shared data-loading helpers + PDF archive builder (build_and_save_pdf_report)
│   ├── build_dashboard_metronic.py  # Builds docs/index.html + docs/history.html (Metronic-styled dashboard)
│   └── build_reporting_hub.py       # Builds docs/reporting.html + reporting-hub-latest.pdf (trends across all runs)
├── notifications/
│   └── send_digest_email.py         # Sends the summary email via Gmail SMTP
├── content_agent/                   # Content Agent (all three agents built) -- see §12
│   ├── database.py                  # content_briefs/content_drafts/content_qa_reviews tables + save/load
│   ├── word_budget.py               # Deterministic per-section word-count allocator
│   ├── banned_phrases.py            # Shared AI-cliche phrase list (Writer avoids, QA Checker detects)
│   ├── qa_checks.py                 # Deterministic QA checks (word count, keywords, readability, etc.) + scoring
│   ├── save_brief.py                # CLI: persists a finished brief (called by the blog-outline skill)
│   ├── save_draft.py                # CLI: persists a finished draft, computes real word counts (blog-write skill)
│   ├── save_qa_review.py            # CLI: recomputes deterministic checks fresh + saves the QA report (blog-qa skill)
│   ├── build_content_page.py        # Builds docs/content.html (3 tabs) + per-brief/draft/QA PDFs
│   └── example_blogs/               # Reference posts for style/structure (empty until Rahul adds some)
├── .github/
│   └── workflows/seo-audit.yml      # Weekly schedule (Mon 06:00 UTC) + manual trigger
└── .claude/
    └── skills/
        ├── seo-audit/SKILL.md       # Claude Code custom skill: type /seo-audit to trigger a run
        ├── blog-outline/SKILL.md    # Claude Code custom skill: type /blog-outline to run the Outliner Agent
        ├── blog-qa/SKILL.md         # Claude Code custom skill: type /blog-qa to run the QA Checker Agent
        └── blog-write/SKILL.md      # Claude Code custom skill: type /blog-write to run the Writer Agent
```

## 4. The site being audited

- **simprosys.com** — WordPress backend, frontend built with Astro (initially described as "React"; investigation showed it's actually server-rendered via Astro, with React used only for interactive islands — raw HTML already contains title/meta/H1 for most pages).
- Sitemap: `https://simprosys.com/sitemap.xml` — one flat sitemap covering the whole host, **including** the `/simprotips` blog subpath (confirmed same host, same sitemap).
- 76 pages total as of the last crawl.
- `robots.txt` specifies `Crawl-delay: 3` — the crawler respects this exactly.
- **Not yet included** (deliberately deferred, see §6): `support.simprosys.com` (Frappe framework backend, ~334 pages, separate host/sitemap/robots.txt) — planned as "website #2" once this system is proven reliable on the main site.

## 5. Technology choices and why

| Choice | Reasoning |
|---|---|
| Python | Simple, readable, well-commented easily — good fit for a non-coder to review. |
| Playwright (headless Chromium) | Renders JS-dependent content -- the rendered HTML is the source of truth for every check, since that's what a real visitor/Google ultimately sees. The raw (pre-JS) fetch is kept for status-code checks and speed, not for a JS-rendering comparison rule (removed 2026-08-03, see §6). |
| `requests` for raw fetches | Faster than a full browser load when we only need the pre-JS HTML/status code. |
| SQLite | Single-file database, no server to manage, trivial to run both locally and in GitHub Actions. |
| GitHub Actions | Free scheduled automation, no server to maintain, ties directly to the repo. |
| GitHub Pages | Free static hosting for the dashboard, directly from the `/docs` folder. |
| Gmail SMTP + App Password | Uses the existing company email, no third-party email service needed. |

## 6. Phase 1 scope: what's implemented now

**Deliberately scoped to 100% mechanical, deterministic checks only** — no AI/LLM judgment calls, no external paid APIs. This was a considered decision to prove the pipeline's accuracy first (see §2).

### 41 rules currently implemented

**Per-page checks** (`agent3_validation/page_checks.py`, 35 rules):
`page-fetch-failed`, `page-not-200`, `url-underscore`, `url-uppercase`, `url-unnecessary-date`, `url-too-long`, `title-missing`, `title-length`, `meta-description-missing`, `meta-description-length`, `og-title-missing`, `og-title-length`, `og-description-missing`, `og-description-length`, `twitter-title-missing`, `twitter-description-missing`, `twitter-description-length`, `canonical-missing`, `canonical-duplicate`, `canonical-not-absolute`, `canonical-not-https`, `h1-missing`, `h1-multiple`, `robots-conflicting-directives`, `robots-noindex-in-sitemap`, `sitemap-non-html-entry`, `image-alt-missing`, `schema-invalid-json`, `schema-missing`, `mixed-content`, `ssl-invalid`, `https-not-enforced`, `redirect-chain`, `redirect-loop`, `sitemap-url-redirects`

**Cross-page checks** (`agent3_validation/site_checks.py`, 6 rules):
`internal-link-broken`, `internal-link-unverified`, `orphan-page`, `duplicate-title`, `duplicate-meta-description`, `canonical-target-broken`

**`h1-missing`/`h1-multiple` added 2026-07-28** — previously H1 text was only used internally for the JS-rendering comparison, never checked as its own rule; added so the dashboard's "Headings" category has real content.

**JS-rendering checks removed (2026-08-03), per Rahul's request** — `js-rendering-content-differs` and `js-added-internal-links` (and the "JavaScript Rendering" dashboard category) were dropped entirely, along with `_check_js_rendering()` in `page_checks.py`. This is a validation-layer-only change: Agent 1 still fetches every page twice (raw + Playwright-rendered) and still uses the rendered version as the source of truth for every other check -- that part of the crawler was deliberately left untouched. The raw-vs-rendered comparison data (`js_rendering_comparison_json`) is still collected and stored by Agent 1/2; it's simply no longer read by Agent 3.

### Excluded URL patterns (added 2026-07-30)

`agent3_validation/rules_config.py` defines `EXCLUDED_URL_PATH_PREFIXES = ["/job-description"]` — pages under this path (Simprosys's job-posting pages) are intentionally temporary: created when a role opens, removed entirely when it closes. Applying evergreen-content rules (title/meta/OG length, duplicate-title, etc.) to pages designed to disappear just creates noise.

What still runs on excluded pages vs. what doesn't:
- **Skipped**: title, meta description, OG/Twitter, canonical, H1, images, robots meta, mixed content, SSL, redirects, URL structure — see `page_checks.py`'s `check_page()`.
- **Kept**: fetch-status checks (`page-fetch-failed`, `page-not-200`) — so if a job closes and its URL is removed from the live site while `sitemap.xml` still lists it, that stale-sitemap-entry problem still gets caught — and schema checks (`schema-missing`, `schema-invalid-json`), since job postings use `JobPosting` structured data for Google for Jobs visibility.
- **Cross-page checks** (`site_checks.py`): excluded pages are never reported as the *subject* of `duplicate-title`/`duplicate-meta-description`/`canonical-target-broken`, but still count as valid comparison targets — a permanent page that happens to duplicate an excluded page's text still gets flagged correctly. This mattered in practice: `/work-at-simprosys` and `/job-description` share an identical title/meta today, and the fix had to preserve the finding on `/work-at-simprosys` while suppressing it on `/job-description`. `orphan-page` and the internal-link-integrity checks are left running on excluded pages unchanged.

**`/simprotips/search` and `/sitemap.xml` fully excluded (implemented 2026-07-30, per Rahul's explicit request)** — unlike `/job-description` above, these aren't partial suppressions: `agent1_crawl/sitemap_discovery.py` defines its own `EXCLUDED_URL_PATH_PREFIXES = ["/simprotips/search", "/sitemap.xml"]` and drops matching URLs at the discovery stage (`discover_urls_to_crawl()`), before the crawl even visits them. Neither has real content worth auditing — `/simprotips/search` is a blog search-results utility page, and `/sitemap.xml` lists itself as one of its own `<loc>` entries, a build artifact rather than a real page — so there's no "hygiene" signal worth preserving by crawling either and suppressing findings after the fact. They simply never enter the crawl plan, the pages table, or any dashboard/checklist again from the next run onward. (A real site URL missing *from* the sitemap is still caught separately, unaffected by this — see the existing `internal-link-unverified` rule in `site_checks.py`.)

### Dashboard organization (redesigned 2026-07-30, Metronic-inspired)

The dashboard was redesigned twice: first (2026-07-28) into a category-sidebar/donut-chart layout, then (2026-07-30) into a full **Metronic-style** admin dashboard (Keenthemes' visual language — sidebar app nav, topbar, KPI cards, card-wrapped tables, pill badges), at Rahul's explicit request to replace the classic look entirely. This is a hand-rolled look-alike, not an import of Metronic's actual paid CSS/JS — same approach as the earlier hand-rolled donut chart.

Built by `agent4_dashboard/build_dashboard_metronic.py` (writes `docs/index.html` + `docs/history.html` directly — there is no separate "classic" version anymore, it was fully removed, not kept as an option). `agent4_dashboard/build_dashboard.py` now only holds shared data-loading helpers (`load_run_info`, `load_findings`, `compute_trend`, `CATEGORIES`/`_categorize_rule`, etc.) and the PDF-archive builder (`build_and_save_pdf_report`) — both modules import from it so there's no duplicated DB logic.

- **Sidebar**: true primary navigation now — just **Dashboard** and **History** — not a category-filter rail like the previous design.
- **Topbar**: page title, run info, Download PDF button.
- **KPI tile row**: Total / Critical / Warning / Info counts as four cards.
- **Health chart**: a real **ApexCharts** donut (loaded via one CDN `<script>` tag — the same charting library Metronic itself uses) replaced the earlier hand-rolled SVG donut, paired with a Trend card (new/resolved/recurring since last run).
- **Findings card**: category filtering moved here as a dropdown (replacing the old sidebar rail), alongside the global search box and the paginated findings table — same underlying search/filter/pagination JS logic as before, just restyled. Search still matches every visible column's text per row (severity, page URL, issue, expected, actual, category), not just the URL.
- **Severity badges**: pill-shaped, pastel background via CSS `color-mix()`, matching Metronic's signature "light" badge style.
- **History page** (`docs/history.html`): same sidebar/topbar shell, one row per past run (date, pages audited, severity summary, Download PDF button) — still deliberately no link into an interactive view of old runs.

### Reporting Hub (added 2026-08-03) — the platform's first "rule-based script → dashboard" module

Built by `agent4_dashboard/build_reporting_hub.py`, writing `docs/reporting.html` (third sidebar item, same shell/shared CSS as the other two pages) + `docs/reports/reporting-hub-latest.pdf`. Where the main Dashboard only ever shows the *latest* run, Reporting Hub answers "are we actually improving over time?" by aggregating every run recorded so far — pure aggregation of data Agent 3 already saved, no new data collection, no judgment calls (the first concrete build from the platform roadmap's "rule-based first" phase — see `roadmap_discussion.md`).

- **Findings Over Time**: a stacked ApexCharts area chart (critical/warning/info) across every run, x-axis labeled by run number (not date) — runs have been bunched together this week from manual triggers rather than the normal weekly cadence, so per-run labeling was chosen deliberately over calendar-week grouping to keep the first version simple; worth revisiting once run cadence settles back to weekly.
- **New / Resolved / Recurring by Run**: a grouped bar chart generalizing the Dashboard's existing "Since Last Run" trend card (`compute_trend()`, `build_dashboard.py`) across the whole run history instead of just the latest two runs.
- **Category Breakdown by Run**: a plain table, one row per SEO checklist category (same `CATEGORIES` list the Dashboard uses) and one column per run — deliberately just the raw numbers, no computed "improving/declining" verdict, matching the project's rule-based-not-judgment philosophy.
- **PDF export** (`reporting-hub-latest.pdf`): same three tables, but deliberately **no charts** — the live page's charts render client-side via the ApexCharts CDN script in the visitor's own browser, which is fine, but baking that into an unattended Playwright PDF render would add a CDN network dependency to the automated pipeline for little benefit. Plain tables keep the PDF fully self-contained, consistent with the existing per-run PDF report's design. Unlike `run-XXXX.pdf` (archived permanently, one per run), this file is **overwritten every run** — it always summarizes the full history to date, so there's no single "point in time" version worth keeping.

### Severity tiers
- **Critical** — real, broken, likely-blocking issues (missing canonical, duplicate title/meta, broken links, invalid schema, SSL/HTTPS failures, redirect loops).
- **Warning** — real best-practice violations, not fatal alone (length issues, mixed content, orphan pages).
- **Info** — low-urgency or can't-be-fully-certain findings (OG/Twitter tag issues, missing schema, unverified external-to-crawl links, minor JS-added-link gaps).

### Thresholds
Title ≤60 chars, meta description ≤160, OG title ≤60, OG description ≤160, Twitter title ≤60, Twitter description ≤160 (max-only limits, no minimums; set to 55/155 on 2026-07-30, raised by 5 chars each on 2026-07-31, both per Rahul's numbers). Internal links 5–15/page. URL length (75 chars) is Rahul's own default — the source doc didn't specify an exact number. **Updated 2026-08-05**: this 75-char budget applies only to the last URL path segment (the slug), not the whole URL — the domain and any category folder (e.g. `/blogs/`) in front of it don't count, since blog/article URLs need real length there and that prefix isn't something a content editor controls anyway. Query strings/fragments are stripped before measuring. See `agent3_validation/page_checks.py`'s `_check_url_structure()`. Fixed 21 false-positive `url-too-long` findings on real `/simprotips/` blog posts that the old whole-URL check was generating; under the corrected logic, 0 of the site's 74 pages currently trip it.

## 7. Key decisions and non-obvious gotchas

- **Database must be committed to git.** GitHub Actions runners start from a fresh checkout every time — if `data/seo_audit_history.db` were gitignored, every scheduled run would lose all history. The workflow's last step commits the updated `.db` and `docs/` back to the repo. (`data/latest_crawl.json` stays gitignored — it's a disposable intermediate artifact, fully captured in the DB.)
- **Repo is public, not private.** GitHub Pages for a *private* repo requires a paid plan (GitHub Pro+). Rahul explicitly chose "make it public" over paying or skipping live hosting. The dashboard/findings are technically visible to anyone with the URL (not indexed/promoted, but not access-controlled).
- **Character encoding bug (real, found and fixed):** Python's `requests` library defaulted to ISO-8859-1 instead of UTF-8 for raw HTML fetches (since the server's `Content-Type` header didn't specify a charset), which silently mangled special characters and caused ~50 false "JS rendering differs" findings. Fixed by forcing `response.encoding = "utf-8"`. **Lesson for future projects: always force UTF-8 explicitly when fetching HTML with `requests`.**
- **Duplicate-link findings bug (found and fixed):** a page linking to the same URL twice (e.g., header nav + footer) was generating duplicate findings per occurrence instead of per unique link. Fixed by de-duplicating link targets per page before checking. Unverified (not-in-sitemap) links were further consolidated from "one finding per page" to "one finding per unique target URL, listing which pages reference it" — otherwise a single shared nav link outside the sitemap generated ~75 near-identical low-value findings.
- **Non-HTML sitemap entries:** the site's own sitemap.xml lists itself (`https://simprosys.com/sitemap.xml`) as a page — a real, genuine finding, not a crawler bug. The crawler now checks `Content-Type` and skips browser-rendering for non-HTML entries, and Agent 3 reports it distinctly from a real "missing title tag" bug.
- **Minimum chart segment height:** (relevant if charts are ever re-added) a proportionally-tiny-but-real count (e.g., 4 critical findings out of 439) can visually round down to 0px in a bar chart and look like zero — enforce a minimum visible height for any non-zero value.
- **Local code changes have zero effect on scheduled/manually-triggered cloud runs until pushed.** GitHub Actions always runs whatever is currently on `origin/main`, not whatever is sitting uncommitted on the local machine. This caused real confusion on 2026-07-30: a rule change (the `/job-description` exclusion) was written and tested locally, then `/seo-audit` was run expecting to see it reflected — but the workflow used the old, unpushed rules, so nothing changed. **Lesson: after any Agent 3 rule change, commit + push *before* triggering a real audit run, or the run will silently use stale logic.**
- **Regenerating the dashboard locally can accidentally overwrite a "permanent" archived PDF.** `_save_pdf_report` always writes to the same `run-XXXX.pdf` filename for a given `run_id` — there's no protection against re-running it against an already-archived run. This happened once during local testing (re-running `build_dashboard` for run #2 while testing an unrelated change silently regenerated `run-0002.pdf`); caught via `git diff`/`git checkout` before it was committed. **Lesson: avoid re-running the dashboard/PDF builder locally against an old `run_id` unless you intend to regenerate that historical PDF.**

## 8. Deployment / operations

- **Schedule**: every Monday, 06:00 UTC, via `.github/workflows/seo-audit.yml`.
- **Manual trigger, three ways**:
  1. GitHub website → Actions tab → "Weekly SEO Audit" → Run workflow button.
  2. Terminal: `cd ~/Desktop/Automation/seo-audit-automation && gh workflow run seo-audit.yml`
  3. In Claude Code: type **`/seo-audit`** (custom Skill at `.claude/skills/seo-audit/SKILL.md` — triggers the workflow, watches it, reports back). **Known quirk**: as of 2026-07-28 this hasn't registered as a recognized slash command even across multiple new chat sessions since the file was created — if `/seo-audit` still returns "Unknown command," just ask in plain English ("run the audit") instead; the underlying steps are identical either way. Worth re-testing occasionally in case it's a propagation delay rather than a permanent issue.
- **Secrets** (GitHub repo secrets, not in code): `SMTP_EMAIL_ADDRESS`, `SMTP_APP_PASSWORD` (Gmail App Password, not the real account password), `NOTIFICATION_RECIPIENT`.
- **Local dev environment**: Python 3.9.6 (macOS system Python), virtualenv at `.venv/`, `pip install -r requirements.txt` then `python -m playwright install chromium`.
- **Local git identity** (set locally for this project only, not globally): name "Rahul Khant", email `rahulkhant@simprosys.com`.
- **`gh` CLI**: installed as a portable binary at `~/.local/bin/gh` (no Homebrew on this machine), authenticated as the `rahulkhant` GitHub account.

## 9. Explicitly deferred to a future "Phase 2" (the Claude/AI-judgment phase)

These were identified early on as needing subjective/semantic judgment rather than pure rule-checking, and were deliberately parked until an AI API key is added:

- **Keyword checks** — primary/secondary keyword presence in title/H1/URL (needs a per-page keyword-mapping input from Rahul, which doesn't exist yet), search-intent matching, keyword stuffing detection.
- **Keyword cannibalization** — detecting when multiple pages compete for the same search intent.
- **Core Web Vitals** — LCP/INP/CLS via Google PageSpeed Insights API (mechanical, just needs an API integration — not actually an AI-judgment task, was deferred purely for phase-1 simplicity, not because it needs AI).
- **Image alt-text *accuracy*** — currently we only check *presence*, not whether the alt text meaningfully describes the image (needs vision-capable judgment).
- **Schema-matches-visible-content** — currently we only validate JSON syntax + presence, not e.g. whether the schema's price/rating actually matches what's shown on the page.

**Design note for whoever implements this next**: Agent 3's output format (`page_url`, `rule`, `issue`, `expected`, `actual`, `severity`) doesn't need to change — these become additional rule entries. Recommended to run AI-judged checks selectively (e.g., only on pages already flagged, or in batches) rather than on all pages every run, to control API cost.

## 10. Also deferred / not yet built

- **Website #2**: `support.simprosys.com` (Frappe backend, ~334 pages) — add once Phase 1 accuracy is proven on the main site.
- **Multiple email recipients** — currently just `rahulkhant@simprosys.com`; Rahul said to add more later if needed.
- **PDF report archiving — DONE (2026-07-28)**: every run gets a permanent PDF snapshot at `docs/reports/run-XXXX.pdf`, with a "Download PDF" link on the dashboard for the current run.
- **Dashboard redesign — DONE (2026-07-28, then fully replaced 2026-07-30)**: first a category-sidebar/donut-chart design, then a full Metronic-style redesign (KPI tiles, ApexCharts donut, sidebar app nav, pill badges) at Rahul's explicit request — the classic design was removed entirely, not kept as an alternative. See §6 "Dashboard organization" for full detail. (An initial version of the Metronic redesign was shipped as a side-by-side `/metronic-preview` comparison so Rahul could evaluate it against the classic design before committing; once approved, it was promoted to be the only dashboard and the preview subfolder was deleted.)
- **Login-gated dashboard access — designed, not yet built.** Rahul wants a real login wall (starting with just himself, extensible to teammates later). **Important finding from this design discussion, still true whenever this gets built**: the repo is currently *public* (required for free-tier GitHub Pages on a private repo), which means the underlying data (database, all PDFs) is already reachable directly through the repo regardless of any login wall placed in front of a *hosted* view — a login wall only matters once the repo goes back to private. The recommended path (agreed in principle, not yet implemented): migrate hosting from GitHub Pages to **Cloudflare Pages** (deploys fine from a private repo, still free, no code changes to what Agent 4 generates), make the **repo private again**, then add **Cloudflare Access** in front of the Cloudflare Pages site (real login via Google/Microsoft/email-OTP, email allow-list starting with just `rahulkhant@simprosys.com`). Cloudflare Access needs to sit in front of a domain Cloudflare controls — a `*.github.io` address doesn't qualify, but a Cloudflare Pages site's own `*.pages.dev` address does, without needing any custom domain or Simprosys IT/DNS involvement. Rahul deliberately postponed this to prioritize proving rule accuracy first — do this once that's solid, likely alongside or after the Claude API phase. (Note: the History page itself is already built per the redesign above; this remaining item is *only* the login wall.)

## 11. Current live status (as of this report, 2026-07-30)

- Latest confirmed successful run: Run #3 — 76 pages, 4 critical / 190 warning / 246 info findings, PDF archived, email delivered. This run used the *old* rules (pre-`/job-description`-exclusion) and the *old* dashboard code, since both were still local/uncommitted at run time.
- **Local working tree currently has uncommitted, unpushed work**: the `/job-description` exclusion rule, the full Metronic dashboard promotion (classic dashboard removed), and this report's updates. None of this is live on GitHub or reflected in Run #3 yet — it needs to be committed, pushed, and then a fresh audit run triggered before it actually shows up on the live dashboard (see the "local code has zero effect until pushed" gotcha in §7).
- **Known blocker (2026-07-30)**: `git commit`/`git push` were being denied by the Claude Code session's permission system even after explicit user approval and an added allow-rule in `.claude/settings.local.json` — suspected to need a session reload to pick up the new permission rule. Unresolved as of this report; whoever picks this up next should check whether the commit/push finally went through, and if not, try a fresh session.
- All four agents + orchestrator + notification step individually tested and verified against real site data before being wired together.
- Weekly schedule is live and will continue running unattended every Monday 06:00 UTC (using whatever is on `origin/main` at the time).
- Current priority (per Rahul, 2026-07-28, still true): validate accuracy/reliability of the existing mechanical rule set over real weekly runs before adding the Claude API phase or the login-gated dashboard redesign. The `/job-description`, `/simprotips/search`, and `sitemap.xml` exclusions (§6) are part of this same accuracy-hardening effort, not new scope.
- **Broader context (2026-07-30)**: Rahul's long-term goal is a full internal SEO automation platform (technical/on-page audits, keyword research, competitor analysis, SWOT, content calendar, reporting, etc.), built module-by-module with the same rule-based-first philosophy, eventually usable by multiple people at Simprosys. See `roadmap_discussion.md` for the (not-yet-finalized) phased plan.

## 12. Content Agent module (all three agents built, 2026-08-05)

First concrete build from the "rule-based script → dashboard" platform priority list (`roadmap_discussion.md` §5b) — a separate module from the SEO audit pipeline (agents 1-4), not a new stage in `main.py`. Three agents, all built: **Outliner**, **Writer**, **QA Checker**.

**Why this isn't a fully automated pipeline**: generating blog prose genuinely needs an LLM — there's no rule-based way to write coherent content, the same honest carve-out already made for a future SWOT module. Rahul has no budget for a separate paid API/tools plan, so rather than a standalone script calling the Anthropic API directly (real per-call billing, needs its own API key), this is built as a **Claude Code skill** — `/blog-outline` — run interactively in a Claude Code session. The model doing the outlining *is* the assistant running the skill; there's no second API call happening. This also means it's inherently human-in-the-loop by design (Rahul triggers each run and sees the outline form in the chat), not unattended automation like the weekly audit cron.

**Division of responsibility, deliberately narrow for the Outliner**: Rahul owns the research — topic, primary/secondary keywords, heading hierarchy, target audience, search intent, tone, CTA all come from him. The Outliner's job is narrower than "research and plan a blog" — it expands his given headings into a precise section-by-section brief (word budget, specific points to cover, keyword mapping, CTA placement) so a future Writer step can't misinterpret a bare heading.

**What's rule-based vs. judgment, same split as the rest of the project**:
- `content_agent/word_budget.py` — per-section word-count allocation is plain deterministic Python (10% intro, 10% conclusion, remainder split evenly across given headings). Same inputs always produce the same numbers; this is intentionally *not* left to the model's judgment.
- Everything else in the brief (what each section should actually say) is the model's judgment step, done live in the skill conversation, visible to Rahul as it's produced.

**Storage**: `content_agent/database.py` adds three tables to the *same* SQLite file the SEO audit already uses (via `agent2_storage.get_connection()`) — one database for the whole platform, but each module owns its own tables, per the modular-design principle: `content_briefs`, `content_drafts`, and `content_qa_reviews`. `status` on `content_briefs` moves through `outlined` → `drafted` → `qa_reviewed` as each agent runs, so the dashboard can show progress without extra lookups.

**Dashboard, redesigned into three tabs (2026-08-05)**: `docs/content.html` (`content_agent/build_content_page.py`) has one sidebar entry but three client-side tabs — **Outline / Draft / QA Checker** — switched with no page reload. Every brief appears in every tab regardless of how far it's progressed: a brief with no draft yet shows a dashed "not drafted — run /blog-write" placeholder row in the Draft tab rather than being hidden, so it's obvious at a glance where each piece of content stands. Clicking any real row opens the same scrollable `<dialog>` modal pattern (native `<dialog>`, explicit `position:fixed` + `translate` centering, own internal scrollbar, `[open]`-scoped CSS so closed dialogs stay hidden) reused identically across all three tabs, per Rahul's explicit ask for one consistent format. This replaced the original single-list-with-mixed-content design from 2026-08-04, once there were three real stages to show rather than two.

**Workflow, per Rahul's explicit instruction**: all three skills commit and push automatically at the end — no separate manual step, matching how the audit's GitHub Actions workflow already auto-commits every run.
- **Outliner** (`/blog-outline`): collect inputs conversationally → validate → load `content_agent/example_blogs/` for style reference if any exist → compute word budgets (`content_agent/word_budget.py`, deterministic) → write the brief → save via `content_agent.save_brief` → rebuild dashboard → `git add`/`commit`/`push`.
- **Writer** (`/blog-write`): pick a not-yet-drafted brief → load it in full → write actual prose section by section (the one step that's genuinely the model's judgment, not rule-based) → save via `content_agent.save_draft`, which computes real word counts from the text itself (`len(content.split())`, never the model's own claimed count) → rebuild dashboard → commit/push. Also avoids the banned-phrase list (see QA Checker below) proactively, so QA is a safety net rather than something that routinely sends drafts back. **Overwrite-only, no version history** (Rahul's explicit call): `content_drafts.brief_id` is `UNIQUE`, upsert via `ON CONFLICT DO UPDATE`.
- **QA Checker** (`/blog-qa`, added 2026-08-05): pick a drafted brief → `content_agent/qa_checks.py` computes a full deterministic report fresh from the brief+draft (never trusted from the skill conversation) — word count vs. target, keyword coverage per assigned section, primary-keyword density (stuffing check), Flesch Reading Ease readability, sentence-length complexity, a passive-voice heuristic, and banned-phrase hits — then the skill reads the draft itself and adds one small judgment number (`judgment_adjustment`, capped at ±2.0 by `save_qa_review.py` so it stays a nudge, not the dominant factor) plus a short qualitative note. Combined into an itemized score out of 10 (see "Scoring math" below) via `content_agent.save_qa_review`, which recomputes the deterministic half itself rather than trusting whatever the skill passed in. Same overwrite-only pattern as drafts.
- Each brief gets one PDF per stage it's reached: **Outline PDF** (`docs/content_briefs/brief-XXXX.pdf`, structured tables), **Draft PDF** (`docs/content_drafts/draft-XXXX.pdf`, reads like an actual article), and **QA PDF** (`docs/content_qa/qa-XXXX.pdf`, the full report). All plain HTML/CSS, no charts/CDN dependency, same self-contained-PDF philosophy as the Reporting Hub's PDF.

**A real bug caught by testing against real data, not synthetic examples**: the QA Checker's keyword-coverage check originally detected "is this the intro/conclusion" by matching the section's `level` field against the literal strings `"intro"`/`"conclusion"` — the synthetic sentinel values `word_budget.py` uses for unheaded slots. That silently failed for any brief with a real, Rahul-authored heading like "Conclusion" (stored with its actual level, e.g. `"H2"`, not the sentinel) — exactly the Google Merchant Center brief's own case. Fixed to detect intro/conclusion by **position** (first/last section in the list) instead of the level string, which is correct regardless of whether a brief used the synthetic slot or a real heading.

**Scoring math is a deliberate v1, not final** (Rahul, 2026-08-05): he wants to research proper scoring approaches and update `content_agent/qa_checks.py`'s deduction values later. Every deduction is itemized with its reason in the saved report rather than folded into an opaque number, specifically so it stays easy to adjust any one number later without touching the others.

**Banned AI-cliche phrase list** (`content_agent/banned_phrases.py`, ~37 phrases — "unlock", "dive into", "game-changer", "leverage" as a verb, etc.): used in two places that must be kept in sync by hand, since a skill file is markdown and can't literally import a Python list — the Writer's instructions mirror the list directly (prevention), and the QA Checker's `find_banned_phrases()` scans the finished draft for anything that slipped through (detection).

---

## Appendix: general playbook (for building *other* future automations, not just this one)

This is the process that was followed, useful as a repeatable template:

1. **Understand & scope conversationally first** — no code until the checklist/rules/architecture are fully discussed and agreed. Ask about existing systems, platforms, and constraints before assuming anything.
2. **Design the architecture as independent, single-responsibility stages** connected by simple data handoffs (files or a shared database) rather than tightly-coupled code — makes each piece independently testable.
3. **Scope the first version down to what's provable and deterministic**; explicitly park anything needing AI judgment or paid APIs for a later phase, and write down *why* and *where it will plug back in*.
4. **Build in small, reviewable stages** — one file/function at a time, heavily commented, tested against real data immediately, not mocked data.
5. **Investigate every surprising result** rather than assuming the code is right or the anomaly doesn't matter — this is where real bugs (encoding, duplicate findings) got caught before they undermined trust in the system.
6. **Only after each piece is proven alone**, wire them together into one orchestrator, and test the orchestrator end-to-end from a completely clean state (delete all local data, run once, confirm it rebuilds everything correctly).
7. **Move to cloud deployment last**, and always manually trigger the very first cloud run to confirm it behaves identically to local before trusting an unattended schedule.
8. **Document the finished state** (this report) so future work — whether by the same person, a teammate, or a different AI session — never has to start from zero context again.
