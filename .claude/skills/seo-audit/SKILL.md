---
description: "Manually trigger the SEO audit GitHub Actions workflow, watch it run to completion, and report back the results (pages crawled, findings, email status, dashboard link)."
---

You are running the SEO audit for the simprosys.com project on demand,
instead of waiting for the weekly automatic schedule.

Do the following, in order:

1. Confirm the working directory is the project repo. If not already there,
   change to `/Users/rahul/Desktop/Automation/seo-audit-automation`.

2. Make sure the `gh` CLI is on PATH for this shell:
   `export PATH="$HOME/.local/bin:$PATH"`

3. Trigger the workflow:
   `gh workflow run seo-audit.yml`

4. Find the run that was just triggered (wait a few seconds first so it
   registers):
   `gh run list --workflow=seo-audit.yml --limit 1 --json databaseId,status,url`

5. Watch that run until it finishes. This normally takes 6-10 minutes
   (Playwright setup + crawling 76 pages with a 3-second politeness delay
   per page). Run this in the background so you aren't blocked, and report
   back to the user once it completes rather than making them wait:
   `gh run watch <run-id> --exit-status`

6. Once it finishes:
   - If it succeeded: tell the user it completed successfully, remind them
     to check their email (rahulkhant@simprosys.com) for the summary, and
     give them the dashboard link: https://rahulkhant.github.io/seo-audit-automation/
   - If it failed: pull the failing step's logs with
     `gh run view <run-id> --log-failed` and explain what went wrong in
     plain language -- don't just paste raw logs.

7. Pull the latest commit locally afterward (`git pull --ff-only`) so the
   local copy of the database and dashboard matches what the workflow
   committed, in case further local work happens in the same session.

Keep the user updated at each meaningful stage (triggered, running,
complete) rather than going silent for the full 6-10 minutes.
