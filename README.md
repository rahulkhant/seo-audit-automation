# SEO Audit Automation

Weekly automated On-Page & Technical SEO audit for our company website(s).

## How it works

Four independent stages run in sequence, orchestrated by `main.py`:

1. `agent1_crawl/` — crawls the site and collects raw SEO-relevant data for each page.
2. `agent2_storage/` — stores the collected data in a SQLite database, keeping history across runs for trend tracking.
3. `agent3_validation/` — checks stored data against our SEO rules (`config/`) and records failures with page, rule, expected value, actual value, and severity.
4. `agent4_dashboard/` — builds a static HTML dashboard from the validation results, published via GitHub Pages, and sends a summary email.

## Status

Phase 0 — project scaffolding only. No functional code yet.
