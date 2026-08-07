"""
Main orchestrator: runs all four agents in sequence.

Purpose of this file
--------------------
This is the single command that runs a complete SEO audit, start to finish:

  Agent 1 (crawl)      -> collects raw data from every page on the site
  Agent 2 (storage)    -> saves that data into the database as a new run
  Agent 3 (validation) -> checks the stored data against our SEO rules
  Agent 4 (dashboard)  -> builds the HTML dashboard + PDF archive from the findings
  Notification         -> emails a short summary of what was found

Each agent still works independently and can be run on its own (as we did
while building and testing each one) -- this file just chains them together
so a full audit is one command instead of four.

Usage
-----
    python main.py <project>
        Audits the given registered project (see projects.py). There is no
        default anymore -- crawling a different site now means registering
        a project there first, not passing an ad hoc URL, so every run's
        data and dashboard land in the right place automatically.
"""

import sys
import time

from agent1_crawl.crawl_runner import run_full_crawl, save_crawl_result
from agent2_storage.database import get_connection, save_crawl_result as save_crawl_result_to_db
from agent3_validation.run_validation import run_validation_and_save
from agent4_dashboard.build_dashboard import build_and_save_pdf_report, compute_trend
from agent4_dashboard.build_dashboard_metronic import build_and_save_dashboard
from agent4_dashboard.build_reporting_hub import build_and_save_reporting_hub
from build_landing_page import build_and_save_landing_page, build_redirect_stubs
from notifications.send_digest_email import send_digest_email
from projects import data_dir, db_path, dashboard_url, get_project


def run_full_audit(project):
    started_at = time.time()
    site_root_url = get_project(project)["site_url"]

    print("=" * 60)
    print(f"Starting SEO audit for project '{project}' ({site_root_url})")
    print("=" * 60)

    print("\n[1/5] Agent 1: Crawling the site...")
    crawl_result = run_full_crawl(site_root_url)
    # Also writes <project>/latest_crawl.json for debugging.
    save_crawl_result(crawl_result, data_dir(project) / "latest_crawl.json")

    print("\n[2/5] Agent 2: Saving crawl data to the database...")
    connection = get_connection(db_path(project))
    try:
        run_id = save_crawl_result_to_db(connection, crawl_result)
    finally:
        connection.close()
    print(f"    -> Saved as run_id={run_id}")

    print("\n[3/5] Agent 3: Validating against SEO rules...")
    validated_run_id, findings = run_validation_and_save(project, run_id)
    print(f"    -> {len(findings)} findings saved")

    print("\n[4/5] Agent 4: Building the dashboard...")
    dashboard_run_id, dashboard_path = build_and_save_dashboard(project, run_id)
    print(f"    -> Dashboard saved to {dashboard_path}")
    pdf_run_id, pdf_path = build_and_save_pdf_report(project, run_id)
    print(f"    -> PDF report archived to {pdf_path}")
    reporting_html_path, reporting_pdf_path = build_and_save_reporting_hub(project)
    print(f"    -> Reporting Hub saved to {reporting_html_path} (PDF: {reporting_pdf_path})")
    landing_path = build_and_save_landing_page()
    build_redirect_stubs()
    print(f"    -> Landing page refreshed at {landing_path}")

    print("\n[5/5] Sending summary email...")
    connection = get_connection(db_path(project))
    try:
        trend = compute_trend(connection, run_id)
    finally:
        connection.close()
    notification_recipient = get_project(project)["notification_recipient"]
    was_sent = send_digest_email(run_id, findings, trend, dashboard_url(project), notification_recipient)
    print(f"    -> Email sent" if was_sent else "    -> Email skipped (see message above)")

    duration_seconds = round(time.time() - started_at, 1)

    print("\n" + "=" * 60)
    print(f"Audit complete in {duration_seconds} seconds.")
    print(f"Run #{run_id}: {len(crawl_result['pages'])} pages crawled, {len(findings)} findings.")
    print("=" * 60)

    return run_id


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python main.py <project>", file=sys.stderr)
        sys.exit(1)
    run_full_audit(sys.argv[1])
