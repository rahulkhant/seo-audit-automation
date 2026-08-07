"""
Top-level landing page: the project picker.

Purpose of this file
--------------------
Now that every project gets its own complete dashboard under
docs/<slug>/, something needs to live at the actual root (docs/index.html)
so visiting the site at all has somewhere sensible to land. This is that
page -- a simple list of every registered project (projects.py), linking
into each one's own docs/<slug>/index.html.

Deliberately not part of the Metronic shell the per-project dashboards
share (agent4_dashboard/build_dashboard_metronic.py's sidebar/topbar) --
there's no "active page" or per-project data to show here, just a plain
picker, so it doesn't need any of that machinery.

Rebuilt every time main.py runs (cheap, and keeps it current automatically
as projects get added -- no separate step to remember).
"""

import html
from pathlib import Path

from projects import list_projects

REPO_ROOT = Path(__file__).resolve().parent
LANDING_FILE_PATH = REPO_ROOT / "docs" / "index.html"

_STYLE = """
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: #f5f8fa; color: #181c32; font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    body { background: #15151f; color: #ffffff; }
    .project-card { background: #1c1c28; border-color: #2b2b3a; }
    .project-card:hover { border-color: #009ef7; }
  }
  .wrap { max-width: 640px; width: 100%; padding: 40px 24px; }
  h1 { font-size: 1.4rem; margin: 0 0 4px; }
  p.sub { color: #7e8299; margin: 0 0 28px; font-size: 0.92rem; }
  .project-list { display: flex; flex-direction: column; gap: 12px; }
  .project-card {
    display: block; padding: 18px 22px; border-radius: 12px; border: 1px solid #eff2f5;
    background: #ffffff; text-decoration: none; color: inherit;
  }
  .project-card:hover { border-color: #009ef7; }
  .project-name { font-size: 1.05rem; font-weight: 700; }
  .project-site { color: #7e8299; font-size: 0.85rem; margin-top: 3px; }
  .empty-state { color: #7e8299; font-size: 0.92rem; }
"""


def _render_project_card(slug, entry):
    return f"""
    <a class="project-card" href="{html.escape(slug)}/index.html">
      <div class="project-name">{html.escape(entry['display_name'])}</div>
      <div class="project-site">{html.escape(entry['site_url'])}</div>
    </a>
    """


def generate_landing_page_html():
    projects = list_projects()
    if not projects:
        body = '<div class="empty-state">No projects registered yet -- add one to projects.py.</div>'
    else:
        body = f'<div class="project-list">{"".join(_render_project_card(slug, entry) for slug, entry in projects)}</div>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SEO Audit Automation</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{_STYLE}</style>
</head>
<body>
  <div class="wrap">
    <h1>SEO Audit Automation</h1>
    <p class="sub">Pick a project to open its dashboard.</p>
    {body}
  </div>
</body>
</html>
"""


def build_and_save_landing_page():
    LANDING_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LANDING_FILE_PATH, "w", encoding="utf-8") as landing_file:
        landing_file.write(generate_landing_page_html())
    return LANDING_FILE_PATH


# --- One-time-migration redirect stubs -------------------------------------
#
# Before multi-project support, every page lived at the docs/ root (e.g.
# docs/content.html). Those URLs are shared/bookmarked, so rather than let
# them 404 after everything moved under docs/simprosys/, each old path gets
# a tiny stub that bounces straight to its new home. docs/index.html itself
# doesn't need one -- it's now the landing page above, which is a sensible
# place to land on its own, not a dead end.
#
# This list is intentionally fixed (not derived from projects.py): it's
# specifically the old single-project URL scheme, which only ever pointed
# at Simprosys. It doesn't grow as new projects are registered.
_REDIRECT_STUBS = {
    "history.html": "simprosys/history.html",
    "reporting.html": "simprosys/reporting.html",
    "content.html": "simprosys/content.html",
    "activity.html": "simprosys/activity.html",
    "keyword-research.html": "simprosys/keyword-research.html",
}


def _render_redirect_stub(destination):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0; url={html.escape(destination)}">
<title>Redirecting...</title>
</head>
<body>
<p>This page has moved. Redirecting to <a href="{html.escape(destination)}">{html.escape(destination)}</a>...</p>
<script>window.location.replace({destination!r});</script>
</body>
</html>
"""


def build_redirect_stubs():
    paths = []
    for old_name, destination in _REDIRECT_STUBS.items():
        stub_path = LANDING_FILE_PATH.parent / old_name
        with open(stub_path, "w", encoding="utf-8") as stub_file:
            stub_file.write(_render_redirect_stub(destination))
        paths.append(stub_path)
    return paths


if __name__ == "__main__":
    saved_path = build_and_save_landing_page()
    print(f"Landing page built: {saved_path}")
    stub_paths = build_redirect_stubs()
    print(f"Redirect stubs written: {', '.join(str(p) for p in stub_paths)}")
