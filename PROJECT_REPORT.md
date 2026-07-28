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
Agent 1 (Crawl)  ->  Agent 2 (Storage)  ->  Agent 3 (Validation)  ->  Agent 4 (Dashboard)  ->  Notification
  crawl_runner.py      database.py          run_validation.py         build_dashboard.py       send_digest_email.py
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
│   └── index.html                   # The dashboard -- served by GitHub Pages
├── agent1_crawl/
│   ├── sitemap_discovery.py         # Reads robots.txt + sitemap.xml -> list of URLs to crawl
│   ├── page_extractor.py            # Fetches ONE page (raw + Playwright-rendered), extracts SEO data
│   └── crawl_runner.py              # Loops over all URLs politely, saves data/latest_crawl.json
├── agent2_storage/
│   └── database.py                  # SQLite schema (runs/pages/findings tables) + save functions
├── agent3_validation/
│   ├── rules_config.py              # All thresholds (title length, meta length, etc.)
│   ├── page_checks.py               # Per-page rule checks (28 rules)
│   ├── site_checks.py               # Cross-page rule checks (6 rules)
│   └── run_validation.py            # Runs all checks, saves findings to DB
├── agent4_dashboard/
│   └── build_dashboard.py           # Builds docs/index.html from findings (stat tiles, trend, paginated table)
├── notifications/
│   └── send_digest_email.py         # Sends the summary email via Gmail SMTP
├── .github/
│   └── workflows/seo-audit.yml      # Weekly schedule (Mon 06:00 UTC) + manual trigger
└── .claude/
    └── skills/seo-audit/SKILL.md    # Claude Code custom skill: type /seo-audit to trigger a run
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
| Playwright (headless Chromium) | Needed to render JS-dependent content and to compare raw vs. rendered HTML for the JS-rendering checks. |
| `requests` for raw fetches | Faster than a full browser load when we only need the pre-JS HTML/status code. |
| SQLite | Single-file database, no server to manage, trivial to run both locally and in GitHub Actions. |
| GitHub Actions | Free scheduled automation, no server to maintain, ties directly to the repo. |
| GitHub Pages | Free static hosting for the dashboard, directly from the `/docs` folder. |
| Gmail SMTP + App Password | Uses the existing company email, no third-party email service needed. |

## 6. Phase 1 scope: what's implemented now

**Deliberately scoped to 100% mechanical, deterministic checks only** — no AI/LLM judgment calls, no external paid APIs. This was a considered decision to prove the pipeline's accuracy first (see §2).

### 34 rules currently implemented

**Per-page checks** (`agent3_validation/page_checks.py`):
`page-fetch-failed`, `page-not-200`, `url-underscore`, `url-uppercase`, `url-unnecessary-date`, `url-too-long`, `title-missing`, `title-length`, `meta-description-missing`, `meta-description-length`, `og-title-missing`, `og-title-length`, `og-description-missing`, `og-description-length`, `twitter-title-missing`, `twitter-description-missing`, `twitter-description-length`, `canonical-missing`, `canonical-duplicate`, `canonical-not-absolute`, `canonical-not-https`, `robots-conflicting-directives`, `robots-noindex-in-sitemap`, `sitemap-non-html-entry`, `image-alt-missing`, `schema-invalid-json`, `schema-missing`, `mixed-content`, `ssl-invalid`, `https-not-enforced`, `redirect-chain`, `redirect-loop`, `sitemap-url-redirects`, `js-rendering-content-differs`, `js-added-internal-links`

**Cross-page checks** (`agent3_validation/site_checks.py`):
`internal-link-broken`, `internal-link-unverified`, `orphan-page`, `duplicate-title`, `duplicate-meta-description`, `canonical-target-broken`

### Severity tiers
- **Critical** — real, broken, likely-blocking issues (missing canonical, duplicate title/meta, broken links, invalid schema, SSL/HTTPS failures, redirect loops).
- **Warning** — real best-practice violations, not fatal alone (length issues, mixed content, orphan pages, JS-rendering content differences).
- **Info** — low-urgency or can't-be-fully-certain findings (OG/Twitter tag issues, missing schema, unverified external-to-crawl links, minor JS-added-link gaps).

### Thresholds (from the source SEO checklist document, "SEO Skils" Google Doc)
Title 40–50 chars, meta description 140–150, OG title ≤50, OG description 110–150, Twitter description 100–150, internal links 5–15/page. URL length (75 chars) is Rahul's own default — the source doc didn't specify an exact number.

## 7. Key decisions and non-obvious gotchas

- **Database must be committed to git.** GitHub Actions runners start from a fresh checkout every time — if `data/seo_audit_history.db` were gitignored, every scheduled run would lose all history. The workflow's last step commits the updated `.db` and `docs/` back to the repo. (`data/latest_crawl.json` stays gitignored — it's a disposable intermediate artifact, fully captured in the DB.)
- **Repo is public, not private.** GitHub Pages for a *private* repo requires a paid plan (GitHub Pro+). Rahul explicitly chose "make it public" over paying or skipping live hosting. The dashboard/findings are technically visible to anyone with the URL (not indexed/promoted, but not access-controlled).
- **Character encoding bug (real, found and fixed):** Python's `requests` library defaulted to ISO-8859-1 instead of UTF-8 for raw HTML fetches (since the server's `Content-Type` header didn't specify a charset), which silently mangled special characters and caused ~50 false "JS rendering differs" findings. Fixed by forcing `response.encoding = "utf-8"`. **Lesson for future projects: always force UTF-8 explicitly when fetching HTML with `requests`.**
- **Duplicate-link findings bug (found and fixed):** a page linking to the same URL twice (e.g., header nav + footer) was generating duplicate findings per occurrence instead of per unique link. Fixed by de-duplicating link targets per page before checking. Unverified (not-in-sitemap) links were further consolidated from "one finding per page" to "one finding per unique target URL, listing which pages reference it" — otherwise a single shared nav link outside the sitemap generated ~75 near-identical low-value findings.
- **Non-HTML sitemap entries:** the site's own sitemap.xml lists itself (`https://simprosys.com/sitemap.xml`) as a page — a real, genuine finding, not a crawler bug. The crawler now checks `Content-Type` and skips browser-rendering for non-HTML entries, and Agent 3 reports it distinctly from a real "missing title tag" bug.
- **Minimum chart segment height:** (relevant if charts are ever re-added) a proportionally-tiny-but-real count (e.g., 4 critical findings out of 439) can visually round down to 0px in a bar chart and look like zero — enforce a minimum visible height for any non-zero value.

## 8. Deployment / operations

- **Schedule**: every Monday, 06:00 UTC, via `.github/workflows/seo-audit.yml`.
- **Manual trigger, three ways**:
  1. GitHub website → Actions tab → "Weekly SEO Audit" → Run workflow button.
  2. Terminal: `cd ~/Desktop/Automation/seo-audit-automation && gh workflow run seo-audit.yml`
  3. In Claude Code: type **`/seo-audit`** (custom Skill at `.claude/skills/seo-audit/SKILL.md` — triggers the workflow, watches it, reports back).
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
- **Dashboard redesign (charts)** — charts (findings-by-rule bar chart, findings-over-time trend chart) were built, then explicitly removed at Rahul's request ("not relatable for our actual output for now"). Pagination was kept. Rahul intends to specify an exact desired dashboard design in a future session rather than have it guessed at.
- **PDF report archiving — DONE (2026-07-28)**: every run now gets a permanent PDF snapshot at `docs/reports/run-XXXX.pdf` (filename zero-padded, derived from `run_id`, so runs never overwrite each other), with a "Download PDF" link on the dashboard header for the current run. Built via Playwright's `page.pdf()` against a simplified, non-paginated print-HTML variant (`_generate_print_html` in `build_dashboard.py`) — reuses the same stat-tile/trend/table renderers as the interactive dashboard rather than duplicating them.
- **Login-gated dashboard + Report History page — designed, not yet built.** Rahul wants a real login wall (starting with just himself, extensible to teammates later) plus a Report History page listing every past PDF (download-only, no in-dashboard viewing of old reports). **Important finding from this design discussion, still true whenever this gets built**: the repo is currently *public* (required for free-tier GitHub Pages on a private repo), which means the underlying data (database, all PDFs) is already reachable directly through the repo regardless of any login wall placed in front of a *hosted* view — a login wall only matters once the repo goes back to private. The recommended path (agreed in principle, not yet implemented): migrate hosting from GitHub Pages to **Cloudflare Pages** (deploys fine from a private repo, still free, no code changes to what Agent 4 generates), make the **repo private again**, then add **Cloudflare Access** in front of the Cloudflare Pages site (real login via Google/Microsoft/email-OTP, email allow-list starting with just `rahulkhant@simprosys.com`). Cloudflare Access needs to sit in front of a domain Cloudflare controls — a `*.github.io` address doesn't qualify, but a Cloudflare Pages site's own `*.pages.dev` address does, without needing any custom domain or Simprosys IT/DNS involvement. Rahul deliberately postponed this whole piece to prioritize proving rule accuracy first — do this once that's solid, likely alongside or after the Claude API phase.

## 11. Current live status (as of this report)

- Latest confirmed successful run: Run #1 via manual cloud trigger — 76 pages, 4 critical / 189 warning / 246 info findings, dashboard live, email delivered, PDF archived.
- All four agents + orchestrator + notification step individually tested and verified against real site data before being wired together.
- Weekly schedule is live and will run unattended starting the next Monday 06:00 UTC.
- Current priority (per Rahul, 2026-07-28): validate accuracy/reliability of the existing mechanical rule set over real weekly runs before adding the Claude API phase or the login-gated dashboard redesign.

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
