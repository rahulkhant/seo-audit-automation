"""
Agent 3, Step 3c: Cross-page (site-wide) rule checks.

Purpose of this file
--------------------
Some SEO rules can't be judged by looking at a single page alone -- they
need the FULL set of pages from one crawl run, compared against each other:

  - A broken internal link can only be confirmed by looking up what status
    code the LINKED-TO page actually returned when WE crawled it.
  - An orphan page can only be found by checking whether ANY other page
    links to it.
  - Duplicate titles/descriptions can only be found by comparing every
    page's title against every other page's title.

This file takes the full list of pages from one run and produces findings
using the same shape as Agent 3's per-page checks (page_checks.py), so
Agent 4 can treat all findings the same way regardless of which file
produced them.

Note on scope: this file only reads data we already collected during the
crawl (Agent 1) -- it does not make any new network requests itself. If an
internal link points to a URL we never crawled (e.g. it's outside the
sitemap), we flag that as "not independently verified" rather than fetching
it live, to keep Agent 3 a pure "check the stored data" step.
"""

import re
from collections import defaultdict
from urllib.parse import urlparse

from agent3_validation import rules_config as rules
from agent3_validation.page_checks import load_page_for_checks, make_finding


def _is_excluded_from_full_audit(url):
    """Same rule as page_checks.py's _is_excluded_from_full_audit --
    duplicated locally rather than imported across modules, since it's a
    tiny predicate over the same rules.EXCLUDED_URL_PATH_PREFIXES config."""
    path = urlparse(url).path.rstrip("/")
    return any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in rules.EXCLUDED_URL_PATH_PREFIXES
    )


def _normalize_url(url):
    """
    Strips URL fragments (the "#section" part) and normalizes trailing
    slashes, so the same page isn't treated as two different URLs just
    because one link has a trailing slash and another doesn't (e.g.
    "https://simprosys.com" and "https://simprosys.com/" are the same
    page).
    """
    url_without_fragment = url.split("#", 1)[0]
    is_bare_domain_root = re.match(r"^https?://[^/]+/?$", url_without_fragment)
    if is_bare_domain_root:
        return url_without_fragment.rstrip("/") + "/"
    return url_without_fragment.rstrip("/")


def _check_broken_internal_links(pages):
    """
    For every internal link on every page, checks whether the page it
    points to actually loaded successfully (status 200) in this same crawl.

    Genuinely BROKEN links (target returned a non-200 status) are reported
    once per source page, since that's directly actionable -- you need to
    go fix the link on each specific page. UNVERIFIED links (target simply
    isn't in our crawled sitemap at all, e.g. shared nav/footer links to a
    page outside the sitemap) are instead grouped into one finding per
    unique target URL, since the same shared link often appears on most or
    all pages -- reporting it once per page would just be noise repeating
    the same root cause.
    """
    findings = []

    # Build a quick lookup: normalized URL -> status code, for every page
    # we actually crawled in this run.
    status_by_url = {
        _normalize_url(page["url"]): page.get("raw_status_code") for page in pages
    }

    # Tracks, for each unverified target URL, which pages link to it --
    # used to build the consolidated site-wide findings below.
    unverified_targets_to_source_pages = defaultdict(list)

    for page in pages:
        # A page can legitimately link to the same URL more than once (e.g.
        # the same page linked from both the header nav and the footer).
        # We only want to consider each target ONCE per page, not once per
        # repeated link, so we de-duplicate by target URL first.
        unique_target_urls = {_normalize_url(link["href"]) for link in page["internal_links"]}

        for target_url in unique_target_urls:
            target_status = status_by_url.get(target_url)

            if target_status is None:
                unverified_targets_to_source_pages[target_url].append(page["url"])
            elif target_status != 200:
                findings.append(make_finding(
                    page["url"], "internal-link-broken",
                    f"This internal link points to a page that returned status {target_status}.",
                    "200 OK", f"{target_status} ({target_url})", rules.SEVERITY_CRITICAL,
                ))

    for target_url, source_pages in unverified_targets_to_source_pages.items():
        example_pages = ", ".join(source_pages[:3])
        if len(source_pages) > 3:
            example_pages += f", and {len(source_pages) - 3} more"
        findings.append(make_finding(
            target_url, "internal-link-unverified",
            f"This URL is linked internally from {len(source_pages)} page(s) but is outside our crawled sitemap, so it wasn't independently checked.",
            "Either added to the sitemap (if it's a real page) or confirmed as intentionally excluded",
            f"Linked from: {example_pages}", rules.SEVERITY_INFO,
        ))

    return findings


def _check_orphan_pages(pages):
    """
    Finds pages that are in our crawl (i.e. in the sitemap) but that no
    OTHER page links to internally. Per your document, every important
    page should be reachable through at least one internal link.
    """
    linked_to_urls = set()
    for page in pages:
        for link in page["internal_links"]:
            linked_to_urls.add(_normalize_url(link["href"]))

    findings = []
    for page in pages:
        normalized_own_url = _normalize_url(page["url"])
        if page.get("is_html") == 0:
            continue  # Not a real page (e.g. the sitemap.xml entry) -- skip.
        if normalized_own_url not in linked_to_urls:
            findings.append(make_finding(
                page["url"], "orphan-page",
                "No other crawled page links to this page internally.",
                "At least one internal link pointing to this page", "0 internal links found",
                rules.SEVERITY_WARNING,
            ))

    return findings


def _check_duplicate_text(pages, field_name, rule_name, human_label):
    """
    Shared logic for finding duplicate titles / duplicate meta descriptions
    across the site. Groups pages by their exact text for the given field,
    then flags every page in any group with 2 or more members.

    Excluded pages (e.g. temporary job postings, see rules_config.py) still
    count toward the group -- a permanent page that happens to duplicate a
    job posting's text is still a real, reportable problem on that
    permanent page -- but the excluded page itself is never the one
    reported, since it isn't meant to be audited.
    """
    pages_by_text = defaultdict(list)
    for page in pages:
        text_value = page.get(field_name)
        if text_value:
            pages_by_text[text_value].append(page["url"])

    findings = []
    for text_value, urls_sharing_it in pages_by_text.items():
        if len(urls_sharing_it) < 2:
            continue
        for url in urls_sharing_it:
            if _is_excluded_from_full_audit(url):
                continue
            other_urls = [u for u in urls_sharing_it if u != url]
            findings.append(make_finding(
                url, rule_name, f"This page's {human_label} is identical to {len(other_urls)} other page(s).",
                f"A unique {human_label} per page", f"Also used by: {', '.join(other_urls)}",
                rules.SEVERITY_CRITICAL,
            ))

    return findings


def _check_canonical_targets(pages):
    """
    For pages whose canonical tag points to another URL we crawled in this
    same run, verifies that the canonical target actually loaded
    successfully (200 OK). A canonical pointing to a broken or redirecting
    page defeats its purpose.

    Excluded pages (e.g. temporary job postings) are still valid canonical
    TARGETS for this lookup, but are never reported as the subject -- see
    _check_duplicate_text for the same reasoning.
    """
    status_by_url = {_normalize_url(page["url"]): page.get("raw_status_code") for page in pages}

    findings = []
    for page in pages:
        if _is_excluded_from_full_audit(page["url"]):
            continue
        for canonical_url in page["canonical_urls"]:
            normalized_canonical = _normalize_url(canonical_url)
            target_status = status_by_url.get(normalized_canonical)
            if target_status is not None and target_status != 200:
                findings.append(make_finding(
                    page["url"], "canonical-target-broken",
                    "This page's canonical tag points to a page that didn't return 200 OK.",
                    "Canonical target returns 200 OK", f"{target_status} ({canonical_url})",
                    rules.SEVERITY_CRITICAL,
                ))

    return findings


def check_site(page_rows):
    """
    Main entry point for this file. Takes every raw database row (from the
    "pages" table) for ONE run and returns every cross-page finding.
    """
    pages = [load_page_for_checks(row) for row in page_rows]
    # These checks only make sense for real HTML pages with actual link
    # data, so we work from the full list but each check internally skips
    # non-HTML entries where relevant.
    html_pages = [page for page in pages if page.get("is_html") != 0]
    # Temporary pages (e.g. job postings, see rules_config.py) are excluded
    # from being the SUBJECT of the duplicate-content/canonical-target
    # checks -- but they still count toward detecting a duplicate/broken
    # target on a PERMANENT page (see _check_duplicate_text and
    # _check_canonical_targets), so we pass the full html_pages list, not a
    # pre-filtered one.

    findings = []
    findings.extend(_check_broken_internal_links(html_pages))
    findings.extend(_check_orphan_pages(pages))
    findings.extend(_check_duplicate_text(html_pages, "title", "duplicate-title", "title tag"))
    findings.extend(_check_duplicate_text(html_pages, "meta_description", "duplicate-meta-description", "meta description"))
    findings.extend(_check_canonical_targets(html_pages))
    return findings
