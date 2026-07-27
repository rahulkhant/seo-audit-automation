"""
Agent 3, Step 3d: Ties everything together and saves the results.

Purpose of this file
--------------------
This is Agent 3's main entry point -- the equivalent of Agent 1's
crawl_runner.py. It:

  1. Connects to the database Agent 2 manages.
  2. Loads every page from the most recent crawl run.
  3. Runs every per-page check (3b) and every cross-page check (3c)
     against that data.
  4. Saves all the findings into the "findings" table, linked to that run,
     so Agent 4 (the dashboard) can read them.

This file makes no network requests of its own -- it only reads what
Agent 1 already collected and Agent 2 already stored, exactly matching
Agent 3's job description: validate stored data against our SEO rules.
"""

from agent2_storage.database import get_connection, save_findings
from agent3_validation.page_checks import check_page
from agent3_validation.site_checks import check_site


def get_most_recent_run_id(connection):
    """Finds the run_id of the latest crawl stored in the database."""
    row = connection.execute("SELECT MAX(run_id) FROM runs").fetchone()
    return row[0]


def validate_run(connection, run_id):
    """
    Runs every SEO check (per-page and cross-page) against one run's worth
    of crawled pages, and returns the combined list of findings. Does not
    save anything itself -- that's a separate step (see save_findings_for_run
    below), so this function stays easy to test on its own.
    """
    page_rows = connection.execute("SELECT * FROM pages WHERE run_id = ?", (run_id,)).fetchall()

    findings = []
    for page_row in page_rows:
        findings.extend(check_page(page_row))
    findings.extend(check_site(page_rows))
    return findings


def run_validation_and_save(run_id=None):
    """
    Main entry point. Validates the given run (or the most recent one, if
    none is specified) and saves the findings to the database. Returns the
    run_id that was validated and the findings, so the caller (or our
    manual test below) can print a summary.
    """
    connection = get_connection()
    try:
        if run_id is None:
            run_id = get_most_recent_run_id(connection)

        findings = validate_run(connection, run_id)
        save_findings(connection, run_id, findings)
        return run_id, findings
    finally:
        connection.close()


# Manual test: validate the most recent crawl run and print a summary.
if __name__ == "__main__":
    from collections import Counter

    validated_run_id, all_findings = run_validation_and_save()

    print(f"Validated run_id={validated_run_id}")
    print(f"Total findings saved: {len(all_findings)}")
    print("By severity:", dict(Counter(f["severity"] for f in all_findings)))
    print()
    print("By rule:")
    for rule, count in Counter(f["rule"] for f in all_findings).most_common():
        print(f"  {rule}: {count}")
