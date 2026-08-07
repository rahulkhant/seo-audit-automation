---
description: "Manually trigger the SEO audit GitHub Actions workflow for a specific project, watch it run to completion, and report back the results (pages crawled, findings, email status, dashboard link)."
---

You are running the SEO audit for one registered project on demand,
instead of waiting for the weekly automatic schedule (which runs every
registered project -- this skill targets just one).

Do the following, in order:

1. Confirm the working directory is the project repo. If not already there,
   change to `/Users/rahul/Desktop/Automation/seo-audit-automation`.

2. Ask which project to audit, unless the user's request already named one.
   Validate it against the registry:
   `.venv/bin/python3 -c "from projects import list_projects; print(' '.join(slug for slug, _ in list_projects()))"`
   If the name given isn't in that list, say so and ask again rather than
   guessing which one they meant.

3. Make sure the `gh` CLI is on PATH for this shell:
   `export PATH="$HOME/.local/bin:$PATH"`

4. Trigger the workflow for that one project:
   `gh workflow run seo-audit.yml -f project=<project>`

5. Find the run that was just triggered (wait a few seconds first so it
   registers):
   `gh run list --workflow=seo-audit.yml --limit 1 --json databaseId,status,url`

6. Watch that run until it finishes. This normally takes 6-10 minutes per
   project (Playwright setup + crawling with a 3-second politeness delay
   per page). Run this in the background so you aren't blocked, and report
   back to the user once it completes rather than making them wait:
   `gh run watch <run-id> --exit-status`

7. Once it finishes:
   - If it succeeded: tell the user it completed successfully, remind them
     to check their email for the summary, and give them that project's
     dashboard link:
     `.venv/bin/python3 -c "from projects import dashboard_url; print(dashboard_url('<project>'))"`
   - If it failed: pull the failing step's logs with
     `gh run view <run-id> --log-failed` and explain what went wrong in
     plain language -- don't just paste raw logs.

8. Pull the latest commit locally afterward (`git pull --ff-only`) so the
   local copy of the database and dashboard matches what the workflow
   committed, in case further local work happens in the same session.

Keep the user updated at each meaningful stage (triggered, running,
complete) rather than going silent for the full 6-10 minutes.
