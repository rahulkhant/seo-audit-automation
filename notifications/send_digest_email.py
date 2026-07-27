"""
Notification step: sends a short summary email after each audit run.

Purpose of this file
--------------------
This isn't a fifth "agent" -- it's the final step the orchestrator
(main.py) runs after Agent 4 builds the dashboard: send a short email so
you know a run happened and roughly what it found, without having to
remember to check the dashboard yourself.

Credentials (your email address and app password) are never written into
this file. They're loaded from environment variables, which locally come
from a ".env" file (never committed to git -- see .gitignore) and, later,
from GitHub Secrets when this runs in GitHub Actions.
"""

import os
import smtplib
from email.mime.text import MIMEText

from dotenv import load_dotenv

# Reads the local ".env" file (if present) into environment variables.
# In GitHub Actions, the environment variables are set directly by GitHub
# Secrets instead, and this call simply has no ".env" file to find, which
# is fine -- os.environ.get() below still finds the same variable names.
load_dotenv()

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _count_by_severity(findings):
    counts = {"critical": 0, "warning": 0, "info": 0}
    for finding in findings:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
    return counts


def _build_subject(counts):
    """The subject line reflects the audit's status at a glance, so you
    know roughly how urgent it is without even opening the email."""
    if counts["critical"] > 0:
        return f"SEO Audit: {counts['critical']} Critical Issue(s) Found"
    if counts["warning"] > 0:
        return f"SEO Audit: {counts['warning']} Warning(s) Found"
    return "SEO Audit: All Clear"


def _build_body(run_id, counts, trend, dashboard_url):
    lines = [
        f"SEO Audit Summary -- Run #{run_id}",
        "",
        f"Critical: {counts['critical']}",
        f"Warning:  {counts['warning']}",
        f"Info:     {counts['info']}",
        "",
    ]

    if trend is None:
        lines.append("This is the first recorded run -- no previous run to compare against yet.")
    else:
        lines.append(
            f"Since last run: {trend['new_count']} new, {trend['resolved_count']} resolved, "
            f"{trend['recurring_count']} still present."
        )

    lines.append("")
    lines.append(f"View the full dashboard: {dashboard_url}")
    return "\n".join(lines)


def send_digest_email(run_id, findings, trend, dashboard_url):
    """
    Sends the summary email. Returns True if it was sent, False if the
    required environment variables aren't set. Returning False instead of
    raising an error means a missing/misconfigured email setup never
    crashes the rest of the audit -- it just skips this last step with a
    clear message about why.
    """
    sender_address = os.environ.get("SMTP_EMAIL_ADDRESS")
    app_password = os.environ.get("SMTP_APP_PASSWORD")
    recipient_address = os.environ.get("NOTIFICATION_RECIPIENT")

    if not (sender_address and app_password and recipient_address):
        print("Email notification skipped: SMTP_EMAIL_ADDRESS / SMTP_APP_PASSWORD / NOTIFICATION_RECIPIENT not set.")
        return False

    counts = _count_by_severity(findings)
    message = MIMEText(_build_body(run_id, counts, trend, dashboard_url))
    message["Subject"] = _build_subject(counts)
    message["From"] = sender_address
    message["To"] = recipient_address

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(sender_address, app_password)
        server.send_message(message)

    return True


# Manual test: send a real email using the most recently stored run.
if __name__ == "__main__":
    from agent2_storage.database import get_connection
    from agent4_dashboard.build_dashboard import compute_trend, load_findings

    connection = get_connection()
    try:
        most_recent_run_id = connection.execute("SELECT MAX(run_id) FROM runs").fetchone()[0]
        run_findings = load_findings(connection, most_recent_run_id)
        run_trend = compute_trend(connection, most_recent_run_id)
    finally:
        connection.close()

    # Placeholder until Phase 3 sets up GitHub Pages and we have a real
    # published URL to link to.
    placeholder_dashboard_url = "(dashboard link will go here once GitHub Pages is set up)"

    was_sent = send_digest_email(most_recent_run_id, run_findings, run_trend, placeholder_dashboard_url)
    print("Email sent!" if was_sent else "Email NOT sent -- see message above.")
