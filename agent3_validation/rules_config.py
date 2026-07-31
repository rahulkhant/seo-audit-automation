"""
Agent 3, Step 3a: Rule thresholds and configuration.

Purpose of this file
--------------------
This file holds every NUMBER and THRESHOLD our SEO rules check against --
title length limits, meta description length limits, how many internal
links is "normal", and so on. It holds no logic (no "if" statements, no
checking code) -- just the numbers themselves, each with a comment
explaining where it came from.

Why keep these separate from the checking logic
-------------------------------------------------
Keeping thresholds in one place, separate from the code that uses them,
means you can review and adjust any number here (e.g. "actually we want
titles up to 60 characters, not 50") without touching any actual logic --
and without needing to understand Python code to do it.

A note on where these numbers come from
-----------------------------------------
Most of the numbers below are taken directly from your SEO checklist
document. A few (marked clearly below) are reasonable general best-practice
defaults I've added because your document described the rule but didn't
specify an exact number -- these are the ones most worth double-checking
and adjusting to your own judgment.
"""

# --- Severity levels used throughout Agent 3 ---
# CRITICAL: a real problem that likely blocks indexing/ranking or is
#           factually broken (e.g. a 404, invalid structured data).
# WARNING:  a real best-practice violation, but not likely to be fatal on
#           its own (e.g. a meta description that's slightly too long).
# INFO:     worth knowing about, low urgency, or something we can't be
#           fully certain is even a problem (e.g. a link count outside the
#           "typical" range, which varies a lot by page type).
SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


# --- Meta Title (max-only, no min; updated 2026-07-31) ---
TITLE_MAX_LENGTH = 60

# --- Meta Description (max-only, no min; updated 2026-07-31) ---
META_DESCRIPTION_MAX_LENGTH = 160

# --- Open Graph title (max-only, no min; updated 2026-07-31) ---
OG_TITLE_MAX_LENGTH = 60

# --- Open Graph description (max-only, no min; updated 2026-07-31) ---
OG_DESCRIPTION_MAX_LENGTH = 160

# --- Twitter title (max-only, no min; updated 2026-07-31) ---
TWITTER_TITLE_MAX_LENGTH = 60

# --- Twitter description (max-only, no min; updated 2026-07-31) ---
TWITTER_DESCRIPTION_MAX_LENGTH = 160

# --- Internal link count per page (from your document: "5-15 relevant links") ---
# Your document notes this "depends on page length", so we treat pages
# outside this range as low-urgency (INFO), not a hard rule violation.
INTERNAL_LINK_COUNT_MIN = 5
INTERNAL_LINK_COUNT_MAX = 15

# --- URL length ---
# NOT specified as an exact number in your document (it just says "keep it
# short"). This is my own reasonable default based on common SEO guidance,
# flagged as low-urgency (INFO) rather than a hard rule. Worth adjusting if
# you have a different number in mind.
URL_MAX_RECOMMENDED_LENGTH = 75

# --- Redirect chains ---
# Your document says to avoid redirect chains (A -> B -> C) and loops.
# A "chain" here means more than one redirect hop before reaching the
# final page.
MAX_ACCEPTABLE_REDIRECT_HOPS = 1

# --- Pages excluded from the full content-quality audit ---
# Job-posting pages under /job-description are intentionally temporary --
# created when a role opens, removed entirely when it closes. Applying the
# evergreen-content rules (title/meta/OG length, duplicate-title,
# canonical-target-broken, etc.) to pages designed to disappear just
# creates noise. Pages matching one of these path prefixes still get their
# fetch-status check (page-fetch-failed / page-not-200 -- so a closed job
# still listed in sitemap.xml gets caught as a real stale-sitemap-entry
# problem) and their schema check (job postings use JobPosting structured
# data for Google for Jobs) -- see page_checks.py's check_page() and
# site_checks.py's check_site() for exactly what's skipped.
EXCLUDED_URL_PATH_PREFIXES = ["/job-description"]
