"""
Project registry.

Purpose of this file
--------------------
This platform now serves multiple, unrelated projects (different sites,
different industries) instead of just Simprosys. Every project shares the
exact same Python code -- there is only ever one copy of agent2_storage,
content_agent, activity_agent, keyword_research, and the dashboard build
scripts. What's NOT shared is the data: each project gets its own SQLite
database file and its own dashboard output folder, so nothing from one
project can ever leak into another's.

This file is the one place that maps a short project "slug" (what you type
on the command line, and what every skill will ask for) to everything else
that depends on it: the real site URL to crawl, where its database lives,
where its dashboard gets built, and what its public dashboard URL is.

Adding a new project is just adding one entry to PROJECTS below -- no other
code changes needed anywhere in the codebase.

Why a plain Python dict instead of a YAML/JSON config file
------------------------------------------------------------
Nothing in this codebase reads external config files today (no PyYAML, no
config library in requirements.txt) -- the existing convention everywhere
else is plain, heavily-commented Python. A dict edited directly is also
simpler for Rahul to hand to an AI assistant ("add a project here") than
teaching a new file format.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

PROJECTS = {
    "simprosys": {
        "display_name": "Simprosys",
        "site_url": "https://simprosys.com",
        # None means "use the NOTIFICATION_RECIPIENT environment variable,
        # same as before multi-project support existed." Set a real address
        # here only if a specific project's audit email should go somewhere
        # other than that default.
        "notification_recipient": None,
    },
}


def get_project(slug):
    """Looks up one project's registry entry. Raises a clear, readable
    error (not a bare KeyError) if the slug isn't registered -- every skill
    and CLI script should let this error surface as-is rather than catching
    it, so a typo'd project name fails loudly instead of silently writing
    into the wrong place."""
    if slug not in PROJECTS:
        known = ", ".join(sorted(PROJECTS))
        raise ValueError(f"Unknown project '{slug}'. Registered projects: {known}")
    return PROJECTS[slug]


def list_projects():
    """Every registered project, as (slug, entry) pairs, sorted by slug --
    used by the landing page and by the GitHub Actions workflow to loop
    over "every project" without hardcoding the list a second time."""
    return sorted(PROJECTS.items())


def data_dir(slug):
    """Where this project's non-database generated data lives (currently
    just the debug latest_crawl.json snapshot)."""
    get_project(slug)
    return REPO_ROOT / "data" / slug


def db_path(slug):
    """Where this project's SQLite database file lives. Passed straight
    into agent2_storage.database.get_connection(db_path=...)."""
    return data_dir(slug) / "seo_audit_history.db"


def docs_dir(slug):
    """Where this project's dashboard gets built. Every build script writes
    its HTML/PDF/Excel output under here instead of the repo-wide docs/
    folder directly."""
    get_project(slug)
    return REPO_ROOT / "docs" / slug


def dashboard_url(slug):
    """The project's public dashboard URL, for email notifications and for
    skills to report back to Rahul."""
    get_project(slug)
    return f"https://rahulkhant.github.io/seo-audit-automation/{slug}/"
