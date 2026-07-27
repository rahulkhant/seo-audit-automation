"""
Main orchestrator: runs all four agents in sequence.

Purpose of this file
--------------------
This is the single command that runs a complete SEO audit, start to finish:

  Agent 1 (crawl)      -> collects raw data from every page on the site
  Agent 2 (storage)    -> saves that data into the database as a new run
  Agent 3 (validation) -> checks the stored data against our SEO rules
  Agent 4 (dashboard)  -> builds the HTML report from the findings
  Notification         -> emails a short summary of what was found

Each agent still works independently and can be run on its own (as we did
while building and testing each one) -- this file just chains them together
so a full audit is one command instead of four.

Usage
-----
    python main.py
        Audits the default site (SITE_ROOT_URL below).

    python main.py https://example.com
        Audits a different site instead -- useful once we add more company
        websites later.
"""

import sys
import time

from agent1_crawl.crawl_runner import run_full_crawl, save_crawl_result
from agent2_storage.database import get_connection, save_crawl_result as save_crawl_result_to_db
from agent3_validation.run_validation import run_validation_and_save
from agent4_dashboard.build_dashboard import build_and_save_dashboard, compute_trend
from notifications.send_digest_email import send_digest_email

# The site this audit runs against by default. Override by passing a
# different URL as a command-line argument (see the usage note above).
SITE_ROOT_URL = "https://simprosys.com"

DASHBOARD_URL = "https://rahulkhant.github.io/seo-audit-automation/"


def run_full_audit(site_root_url):
    started_at = time.time()

    print("=" * 60)
    print(f"Starting SEO audit for {site_root_url}")
    print("=" * 60)

    print("\n[1/5] Agent 1: Crawling the site...")
    crawl_result = run_full_crawl(site_root_url)
    save_crawl_result(crawl_result)  # Also writes data/latest_crawl.json for debugging.

    print("\n[2/5] Agent 2: Saving crawl data to the database...")
    connection = get_connection()
    try:
        run_id = save_crawl_result_to_db(connection, crawl_result)
    finally:
        connection.close()
    print(f"    -> Saved as run_id={run_id}")

    print("\n[3/5] Agent 3: Validating against SEO rules...")
    validated_run_id, findings = run_validation_and_save(run_id)
    print(f"    -> {len(findings)} findings saved")

    print("\n[4/5] Agent 4: Building the dashboard...")
    dashboard_run_id, dashboard_path = build_and_save_dashboard(run_id)
    print(f"    -> Dashboard saved to {dashboard_path}")

    print("\n[5/5] Sending summary email...")
    connection = get_connection()
    try:
        trend = compute_trend(connection, run_id)
    finally:
        connection.close()
    was_sent = send_digest_email(run_id, findings, trend, DASHBOARD_URL)
    print(f"    -> Email sent" if was_sent else "    -> Email skipped (see message above)")

    duration_seconds = round(time.time() - started_at, 1)

    print("\n" + "=" * 60)
    print(f"Audit complete in {duration_seconds} seconds.")
    print(f"Run #{run_id}: {len(crawl_result['pages'])} pages crawled, {len(findings)} findings.")
    print("=" * 60)

    return run_id


if __name__ == "__main__":
    target_site = sys.argv[1] if len(sys.argv) > 1 else SITE_ROOT_URL
    run_full_audit(target_site)
