"""
Agent 3, Step 3b: Per-page rule checks.

Purpose of this file
--------------------
This file contains the actual rule-checking logic for everything that can
be judged by looking at ONE page on its own -- title length, meta
description, canonical tag correctness, image alt text, and so on.

Checks that need to compare MULTIPLE pages against each other (broken
internal links, orphan pages, duplicate titles across the site) live
separately in step 3c, since those need the full set of crawled pages at
once, not just one.

Every check function below returns a list of "finding" dictionaries -- one
per problem it detects (a page can have zero, one, or several findings per
check). Every finding has the same shape, matching exactly what you asked
for originally: the affected page, the issue, what was expected, what was
actually found, and how severe it is:

    {
        "page_url": "...",
        "rule": "short-rule-name",
        "issue": "Human-readable description of the problem",
        "expected": "...",
        "actual": "...",
        "severity": "critical" | "warning" | "info",
    }

This file does not decide how findings are displayed or stored -- it only
produces them. Step 3d (saving findings) and Agent 4 (dashboard) handle
what happens to this list afterward.
"""

import json
import re

from agent3_validation import rules_config as rules


def make_finding(page_url, rule, issue, expected, actual, severity):
    """Small helper so every finding dictionary is built the same way,
    instead of repeating this dictionary shape by hand in every check."""
    return {
        "page_url": page_url,
        "rule": rule,
        "issue": issue,
        "expected": expected,
        "actual": actual,
        "severity": severity,
    }


def load_page_for_checks(page_row):
    """
    Takes one raw row from the "pages" database table (as a dictionary) and
    decodes all the JSON-text columns back into real Python lists/dicts, so
    the check functions below can work with normal Python data instead of
    JSON strings.
    """
    def _decode(json_text):
        return json.loads(json_text) if json_text else None

    page = dict(page_row)
    page["redirect_chain"] = _decode(page.get("redirect_chain_json")) or []
    page["canonical_urls"] = _decode(page.get("canonical_urls_json")) or []
    page["h1_texts"] = _decode(page.get("h1_texts_json")) or []
    page["images"] = _decode(page.get("images_json")) or []
    page["internal_links"] = _decode(page.get("internal_links_json")) or []
    page["external_links"] = _decode(page.get("external_links_json")) or []
    page["schema_blocks"] = _decode(page.get("schema_blocks_json")) or []
    page["mixed_content_urls"] = _decode(page.get("mixed_content_urls_json")) or []
    page["js_rendering_comparison"] = _decode(page.get("js_rendering_comparison_json"))
    return page


# --- URL structure ---
def _check_url_structure(page):
    findings = []
    url = page["url"]

    if "_" in url:
        findings.append(make_finding(
            url, "url-underscore",
            "URL contains an underscore instead of a hyphen.",
            "Hyphens only (e.g. /shopify-seo)", url, rules.SEVERITY_WARNING,
        ))

    # We only check the path/query part for uppercase letters, not the
    # "https://" or domain part, since domains are effectively
    # case-insensitive and this isn't something you control per-page.
    path_and_query = url.split("://", 1)[-1].split("/", 1)[-1]
    if path_and_query != path_and_query.lower():
        findings.append(make_finding(
            url, "url-uppercase",
            "URL contains uppercase letters.",
            "All lowercase", url, rules.SEVERITY_WARNING,
        ))

    if re.search(r"/\d{4}/\d{2}(/\d{2})?/", url):
        findings.append(make_finding(
            url, "url-unnecessary-date",
            "URL contains a date pattern, which isn't needed for non-news content.",
            "No date in URL", url, rules.SEVERITY_WARNING,
        ))

    if len(url) > rules.URL_MAX_RECOMMENDED_LENGTH:
        findings.append(make_finding(
            url, "url-too-long",
            f"URL is longer than the recommended {rules.URL_MAX_RECOMMENDED_LENGTH} characters.",
            f"Under {rules.URL_MAX_RECOMMENDED_LENGTH} characters", f"{len(url)} characters",
            rules.SEVERITY_INFO,
        ))

    return findings


# --- Meta title ---
def _check_title(page):
    findings = []
    title = page.get("title")

    if not title:
        findings.append(make_finding(
            page["url"], "title-missing", "Page is missing a title tag.",
            "A title tag present", "None", rules.SEVERITY_CRITICAL,
        ))
        return findings

    length = len(title)
    if not (rules.TITLE_MIN_LENGTH <= length <= rules.TITLE_MAX_LENGTH):
        findings.append(make_finding(
            page["url"], "title-length",
            "Title length is outside the recommended range.",
            f"{rules.TITLE_MIN_LENGTH}-{rules.TITLE_MAX_LENGTH} characters",
            f"{length} characters (\"{title}\")", rules.SEVERITY_WARNING,
        ))
    return findings


# --- Meta description ---
def _check_meta_description(page):
    findings = []
    description = page.get("meta_description")

    if not description:
        findings.append(make_finding(
            page["url"], "meta-description-missing", "Page is missing a meta description.",
            "A meta description present", "None", rules.SEVERITY_CRITICAL,
        ))
        return findings

    length = len(description)
    if not (rules.META_DESCRIPTION_MIN_LENGTH <= length <= rules.META_DESCRIPTION_MAX_LENGTH):
        findings.append(make_finding(
            page["url"], "meta-description-length",
            "Meta description length is outside the recommended range.",
            f"{rules.META_DESCRIPTION_MIN_LENGTH}-{rules.META_DESCRIPTION_MAX_LENGTH} characters",
            f"{length} characters", rules.SEVERITY_WARNING,
        ))
    return findings


# --- Open Graph & Twitter tags ---
# These affect how a page looks when shared on social media, not search
# rankings directly, so we treat problems here as low-urgency (INFO).
def _check_social_tags(page):
    findings = []
    url = page["url"]

    if not page.get("og_title"):
        findings.append(make_finding(url, "og-title-missing", "Missing Open Graph title.", "Present", "None", rules.SEVERITY_INFO))
    elif len(page["og_title"]) > rules.OG_TITLE_MAX_LENGTH:
        findings.append(make_finding(
            url, "og-title-length", "Open Graph title is longer than recommended.",
            f"Under {rules.OG_TITLE_MAX_LENGTH} characters", f"{len(page['og_title'])} characters",
            rules.SEVERITY_INFO,
        ))

    if not page.get("og_description"):
        findings.append(make_finding(url, "og-description-missing", "Missing Open Graph description.", "Present", "None", rules.SEVERITY_INFO))
    elif not (rules.OG_DESCRIPTION_MIN_LENGTH <= len(page["og_description"]) <= rules.OG_DESCRIPTION_MAX_LENGTH):
        findings.append(make_finding(
            url, "og-description-length", "Open Graph description length is outside the recommended range.",
            f"{rules.OG_DESCRIPTION_MIN_LENGTH}-{rules.OG_DESCRIPTION_MAX_LENGTH} characters",
            f"{len(page['og_description'])} characters", rules.SEVERITY_INFO,
        ))

    if not page.get("twitter_title"):
        findings.append(make_finding(url, "twitter-title-missing", "Missing Twitter title.", "Present", "None", rules.SEVERITY_INFO))

    if not page.get("twitter_description"):
        findings.append(make_finding(url, "twitter-description-missing", "Missing Twitter description.", "Present", "None", rules.SEVERITY_INFO))
    elif not (rules.TWITTER_DESCRIPTION_MIN_LENGTH <= len(page["twitter_description"]) <= rules.TWITTER_DESCRIPTION_MAX_LENGTH):
        findings.append(make_finding(
            url, "twitter-description-length", "Twitter description length is outside the recommended range.",
            f"{rules.TWITTER_DESCRIPTION_MIN_LENGTH}-{rules.TWITTER_DESCRIPTION_MAX_LENGTH} characters",
            f"{len(page['twitter_description'])} characters", rules.SEVERITY_INFO,
        ))

    return findings


# --- Canonical tag ---
def _check_canonical(page):
    findings = []
    url = page["url"]
    canonical_urls = page["canonical_urls"]

    if len(canonical_urls) == 0:
        findings.append(make_finding(url, "canonical-missing", "Page has no canonical tag.", "Exactly one canonical tag", "None", rules.SEVERITY_CRITICAL))
        return findings

    if len(canonical_urls) > 1:
        findings.append(make_finding(
            url, "canonical-duplicate", "Page has more than one canonical tag.",
            "Exactly one canonical tag", f"{len(canonical_urls)} canonical tags", rules.SEVERITY_CRITICAL,
        ))

    canonical_url = canonical_urls[0]
    if not canonical_url.startswith(("http://", "https://")):
        findings.append(make_finding(
            url, "canonical-not-absolute", "Canonical tag uses a relative URL instead of an absolute one.",
            "Absolute URL (starting with https://)", canonical_url, rules.SEVERITY_WARNING,
        ))
    elif canonical_url.startswith("http://"):
        findings.append(make_finding(
            url, "canonical-not-https", "Canonical tag points to an HTTP (not HTTPS) URL.",
            "HTTPS canonical URL", canonical_url, rules.SEVERITY_CRITICAL,
        ))

    return findings


# --- Headings (H1) ---
def _check_headings(page):
    findings = []
    url = page["url"]
    h1_texts = page["h1_texts"]

    if len(h1_texts) == 0:
        findings.append(make_finding(
            url, "h1-missing", "Page has no H1 heading.",
            "Exactly one H1 heading", "None", rules.SEVERITY_WARNING,
        ))
    elif len(h1_texts) > 1:
        findings.append(make_finding(
            url, "h1-multiple", "Page has more than one H1 heading.",
            "Exactly one H1 heading", f"{len(h1_texts)} H1 headings", rules.SEVERITY_WARNING,
        ))

    return findings


# --- Robots meta tag ---
def _check_robots_meta(page):
    findings = []
    url = page["url"]
    content = (page.get("robots_meta_content") or "").lower()

    if "noindex" in content and "index" in content.replace("noindex", ""):
        findings.append(make_finding(
            url, "robots-conflicting-directives", "Robots meta tag has conflicting directives (both index and noindex).",
            "One consistent directive", content, rules.SEVERITY_CRITICAL,
        ))
    elif "noindex" in content:
        # Every page we crawl comes from the sitemap, so a page that is
        # both in the sitemap AND marked noindex is a contradictory signal
        # worth a human double-checking (it may well be intentional).
        findings.append(make_finding(
            url, "robots-noindex-in-sitemap", "Page is marked noindex but is also listed in the sitemap.",
            "index, follow (or removed from sitemap)", content, rules.SEVERITY_WARNING,
        ))

    return findings


# --- Non-HTML sitemap entries ---
def _check_is_html(page):
    if page.get("is_html") == 0:
        return [make_finding(
            page["url"], "sitemap-non-html-entry", "This sitemap entry is not an HTML page.",
            "An HTML page", page.get("raw_content_type") or "unknown content type", rules.SEVERITY_WARNING,
        )]
    return []


# --- Image alt text ---
def _check_image_alt_text(page):
    # Only images missing the "alt" attribute entirely (alt is None) count
    # as a problem. An intentionally empty alt="" is valid for purely
    # decorative images per your document, so we don't flag those.
    missing_count = sum(1 for image in page["images"] if image.get("alt") is None)
    if missing_count > 0:
        return [make_finding(
            page["url"], "image-alt-missing", f"{missing_count} image(s) on this page have no alt attribute at all.",
            "Every meaningful image has alt text", f"{missing_count} missing", rules.SEVERITY_WARNING,
        )]
    return []


# --- Schema markup (JSON-LD) ---
def _check_schema_markup(page):
    findings = []
    url = page["url"]
    schema_blocks = page["schema_blocks"]

    invalid_count = sum(1 for block in schema_blocks if not block.get("valid_json"))
    if invalid_count > 0:
        findings.append(make_finding(
            url, "schema-invalid-json", f"{invalid_count} structured data block(s) contain invalid JSON.",
            "Valid JSON-LD", f"{invalid_count} invalid block(s)", rules.SEVERITY_CRITICAL,
        ))

    if len(schema_blocks) == 0:
        findings.append(make_finding(
            url, "schema-missing", "No structured data (schema markup) found on this page.",
            "At least one relevant schema block", "None found", rules.SEVERITY_INFO,
        ))

    return findings


# --- Mixed content ---
def _check_mixed_content(page):
    mixed_content = page["mixed_content_urls"]
    if mixed_content:
        return [make_finding(
            page["url"], "mixed-content", f"{len(mixed_content)} resource(s) load over HTTP on this HTTPS page.",
            "All resources loaded over HTTPS", f"{len(mixed_content)} HTTP resource(s)", rules.SEVERITY_WARNING,
        )]
    return []


# --- HTTPS / SSL ---
def _check_https_ssl(page):
    findings = []
    url = page["url"]

    if page.get("ssl_valid") == 0:
        findings.append(make_finding(url, "ssl-invalid", "This page's SSL certificate is invalid.", "Valid SSL certificate", "Invalid", rules.SEVERITY_CRITICAL))

    if page.get("redirected_http_to_https") == 0:
        findings.append(make_finding(
            url, "https-not-enforced", "The HTTP version of this page does not redirect to HTTPS.",
            "HTTP redirects (301) to HTTPS", "Does not redirect to HTTPS", rules.SEVERITY_CRITICAL,
        ))

    return findings


# --- Redirects ---
def _check_redirects(page):
    findings = []
    url = page["url"]
    chain = page["redirect_chain"]

    if len(chain) > rules.MAX_ACCEPTABLE_REDIRECT_HOPS:
        findings.append(make_finding(
            url, "redirect-chain", "This URL goes through more than one redirect before reaching its final page.",
            f"At most {rules.MAX_ACCEPTABLE_REDIRECT_HOPS} redirect hop", f"{len(chain)} redirect hops", rules.SEVERITY_WARNING,
        ))

    visited_urls = [step["url"] for step in chain]
    if len(visited_urls) != len(set(visited_urls)):
        findings.append(make_finding(
            url, "redirect-loop", "A redirect loop was detected for this URL.",
            "No repeated URLs in the redirect chain", "Repeated URL(s) found", rules.SEVERITY_CRITICAL,
        ))
    elif chain:
        # Any redirect at all on a sitemap URL is worth a soft mention:
        # ideally the sitemap should list the final destination directly.
        findings.append(make_finding(
            url, "sitemap-url-redirects", "This sitemap URL redirects instead of pointing directly to the final page.",
            "Sitemap URL loads directly (200 OK, no redirect)", f"Redirects via {len(chain)} hop(s)", rules.SEVERITY_INFO,
        ))

    return findings


# --- JS rendering / SSR vs CSR ---
def _check_js_rendering(page):
    findings = []
    url = page["url"]
    comparison = page["js_rendering_comparison"]
    if not comparison:
        return findings

    core_content_differs = not (
        comparison.get("title_matches") and comparison.get("meta_description_matches") and comparison.get("h1_matches")
    )
    if core_content_differs:
        findings.append(make_finding(
            url, "js-rendering-content-differs",
            "Title, meta description, or H1 differs between the raw HTML and the JavaScript-rendered version.",
            "Identical core content before and after JavaScript runs",
            "Content differs -- may rely on JavaScript for key SEO content",
            rules.SEVERITY_WARNING,
        ))

    raw_links = comparison.get("raw_internal_link_count", 0)
    rendered_links = comparison.get("rendered_internal_link_count", 0)
    # A reasonable default of our own (not from your document): a rendered
    # link count at least 50% higher than the raw count suggests a
    # meaningful number of links are added only by JavaScript.
    if raw_links and rendered_links > raw_links * 1.5:
        findings.append(make_finding(
            url, "js-added-internal-links",
            "A significant number of internal links only appear after JavaScript runs.",
            "Similar internal link count before and after JavaScript",
            f"{raw_links} raw vs {rendered_links} rendered", rules.SEVERITY_INFO,
        ))

    return findings


# --- Crawlability (status code) ---
def _check_status_code(page):
    status_code = page.get("raw_status_code")
    if status_code is None:
        return [make_finding(
            page["url"], "page-fetch-failed", "This page could not be fetched at all.",
            "A successful response", page.get("raw_error") or "Unknown error", rules.SEVERITY_CRITICAL,
        )]
    if status_code != 200:
        return [make_finding(
            page["url"], "page-not-200", "This page did not return a 200 OK status.",
            "200 OK", str(status_code), rules.SEVERITY_CRITICAL,
        )]
    return []


# All per-page checks, run in order, for a single page.
ALL_PAGE_CHECKS = [
    _check_status_code,
    _check_url_structure,
    _check_title,
    _check_meta_description,
    _check_social_tags,
    _check_canonical,
    _check_headings,
    _check_robots_meta,
    _check_is_html,
    _check_image_alt_text,
    _check_schema_markup,
    _check_mixed_content,
    _check_https_ssl,
    _check_redirects,
    _check_js_rendering,
]


def check_page(page_row):
    """
    Main entry point for this file. Takes one raw database row (from the
    "pages" table) and returns every finding produced by every per-page
    check above.
    """
    page = load_page_for_checks(page_row)

    # A page that couldn't be fetched at all, or isn't actually an HTML
    # page, doesn't have meaningful title/meta/canonical/etc. data to check
    # -- running those checks on it would just produce confusing,
    # misleading findings (e.g. "missing title" for a file that was never
    # a webpage to begin with). We still report the fetch failure /
    # non-HTML status itself, just skip the rest.
    if page.get("raw_status_code") is None or page.get("is_html") == 0:
        return _check_status_code(page) + _check_is_html(page)

    findings = []
    for check_function in ALL_PAGE_CHECKS:
        findings.extend(check_function(page))
    return findings
