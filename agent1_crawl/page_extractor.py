"""
Agent 1, Step 1b: Single-page extraction.

Purpose of this file
--------------------
Step 1a (sitemap_discovery.py) gave us the list of URLs to crawl. This file
is responsible for visiting ONE page at a time and pulling out every piece
of raw data our SEO rule checks (Agent 3) will need later -- title tags,
meta tags, links, images, structured data, and so on.

Why we fetch each page TWICE
-----------------------------
We deliberately fetch every page in two different ways:

1. "Raw" fetch -- a plain, fast HTTP request (no browser, no JavaScript).
   This is what a very basic crawler sees: the HTML exactly as the server
   first sent it, before any JavaScript has run.

2. "Rendered" fetch -- using Playwright to open the page in a real
   (headless, i.e. invisible) browser, let JavaScript run, and then read the
   final page content. This is what a real visitor -- and Google -- actually
   sees.

Comparing these two versions is exactly how the "JS Rendering" and "SSR vs
CSR" checks from our SEO checklist work: if important content (title, meta
description, H1, links) only appears in the rendered version and not the raw
version, that's a sign the site is relying on JavaScript for SEO-critical
content, which is a real risk worth flagging.

What this file does NOT do
---------------------------
It does not decide whether any of this data passes or fails our SEO rules.
It only collects the raw facts about one page. Agent 3 (validation) is where
those facts get compared against our rules later.
"""

import json
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Reuse the same identity we used for sitemap discovery, so the site's
# server logs show one consistent, honest crawler identity throughout.
CRAWLER_USER_AGENT = "SimprosysSEOAuditBot/1.0"

# How long to wait for a plain HTTP request before giving up. Without a
# timeout, a single unresponsive page could freeze the entire crawl.
REQUEST_TIMEOUT_SECONDS = 30


def _get_domain(url):
    """Returns just the hostname of a URL, e.g. "simprosys.com" from
    "https://simprosys.com/about-us". Used to tell internal links (same
    site) apart from external links (other sites)."""
    return urlparse(url).netloc.lower()


def _extract_seo_elements_from_html(html_content, page_url):
    """
    Parses one HTML document (it doesn't matter whether the HTML came from
    the raw fetch or the rendered fetch -- this function works on either)
    and pulls out every element our SEO checklist cares about.

    Returns a dictionary of plain data (strings, lists, numbers) -- no
    parsing objects -- so it's easy to store and compare later.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    page_domain = _get_domain(page_url)

    # --- Title tag ---
    title_tag = soup.find("title")
    title_text = title_tag.get_text(strip=True) if title_tag else None

    # --- Meta description ---
    meta_description_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = (
        meta_description_tag.get("content", "").strip()
        if meta_description_tag
        else None
    )

    # --- Open Graph and Twitter tags ---
    # These use "property" (Open Graph) or "name" (Twitter) attributes
    # instead of the usual "name" attribute meta tags use, so we look them
    # up slightly differently than the meta description above.
    def _get_meta_content(attr_name, attr_value):
        tag = soup.find("meta", attrs={attr_name: attr_value})
        return tag.get("content", "").strip() if tag else None

    og_title = _get_meta_content("property", "og:title")
    og_description = _get_meta_content("property", "og:description")
    twitter_title = _get_meta_content("name", "twitter:title")
    twitter_description = _get_meta_content("name", "twitter:description")

    # --- Robots meta tag (index/follow directives) ---
    robots_meta_tag = soup.find("meta", attrs={"name": "robots"})
    robots_meta_content = (
        robots_meta_tag.get("content", "").strip() if robots_meta_tag else None
    )

    # --- Canonical tag(s) ---
    # We collect ALL canonical tags found (not just the first) because
    # "only one canonical tag per page" is itself one of our SEO rules --
    # if a page has two, we need to know that to flag it later.
    canonical_urls = [
        tag.get("href", "").strip()
        for tag in soup.find_all("link", attrs={"rel": "canonical"})
        if tag.get("href")
    ]

    # --- Headings (H1) ---
    h1_texts = [tag.get_text(strip=True) for tag in soup.find_all("h1")]

    # --- Images and their alt text ---
    images = [
        {"src": tag.get("src", ""), "alt": tag.get("alt")}
        for tag in soup.find_all("img")
    ]

    # --- Links: split into internal (same site) vs external (other sites) ---
    # Note: for now, "internal" means the EXACT SAME hostname as the page
    # itself (e.g. "simprosys.com"). Links to subdomains like
    # "support.simprosys.com" currently count as external, since we are only
    # crawling simprosys.com in this phase. We'll revisit this once
    # support.simprosys.com is added as its own site.
    internal_links = []
    external_links = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        anchor_text = tag.get_text(strip=True)
        # Skip non-page links like "mailto:" links, "tel:" links, or
        # same-page anchors ("#section") -- these aren't pages to check.
        if href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        absolute_url = urljoin(page_url, href)
        link_record = {"href": absolute_url, "anchor_text": anchor_text}
        if _get_domain(absolute_url) == page_domain:
            internal_links.append(link_record)
        else:
            external_links.append(link_record)

    # --- Schema markup (JSON-LD structured data) ---
    # We store the raw text plus whether it's valid JSON, so Agent 3 can
    # later check the schema's type and required fields. We don't validate
    # the schema's *content* here -- just whether it parses at all.
    schema_blocks = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw_text = tag.string or ""
        try:
            parsed = json.loads(raw_text)
            schema_blocks.append({"raw": raw_text, "valid_json": True, "parsed": parsed})
        except (json.JSONDecodeError, TypeError):
            schema_blocks.append({"raw": raw_text, "valid_json": False, "parsed": None})

    # --- Mixed content check ---
    # If this page is served over HTTPS but loads any resource (image,
    # script, or stylesheet) over plain HTTP, that's "mixed content" -- a
    # real HTTPS/SSL issue from our checklist.
    mixed_content_urls = []
    if page_url.startswith("https://"):
        resource_tags = (
            soup.find_all("img", src=True)
            + soup.find_all("script", src=True)
            + soup.find_all("link", href=True)
        )
        for tag in resource_tags:
            resource_url = tag.get("src") or tag.get("href")
            if resource_url and resource_url.startswith("http://"):
                mixed_content_urls.append(resource_url)

    return {
        "title": title_text,
        "meta_description": meta_description,
        "og_title": og_title,
        "og_description": og_description,
        "twitter_title": twitter_title,
        "twitter_description": twitter_description,
        "robots_meta_content": robots_meta_content,
        "canonical_urls": canonical_urls,
        "h1_texts": h1_texts,
        "images": images,
        "internal_links": internal_links,
        "external_links": external_links,
        "schema_blocks": schema_blocks,
        "mixed_content_urls": mixed_content_urls,
    }


def _fetch_raw_html(url):
    """
    Does a plain, fast HTTP GET request for the given URL -- no browser, no
    JavaScript. Also records the redirect chain (useful for detecting
    redirect loops/chains) and whether HTTPS worked correctly.

    Returns a dictionary describing what happened, including an "error"
    field (None if everything worked) so a single broken page can't crash
    the whole crawl.
    """
    try:
        response = requests.get(
            url,
            headers={"User-Agent": CRAWLER_USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        redirect_chain = [
            {"url": step.url, "status_code": step.status_code}
            for step in response.history
        ]
        # Content-Type tells us whether this URL actually served a webpage
        # at all. Without this, a non-HTML resource (like an XML file
        # mistakenly listed in the sitemap) would look identical to a real
        # HTML page with every SEO tag missing -- which would be misleading
        # when Agent 3 checks it against our rules later.
        content_type = response.headers.get("Content-Type", "")

        # By default, the "requests" library falls back to an old
        # HTTP-spec default (ISO-8859-1) when a server's Content-Type
        # header doesn't explicitly state a character encoding -- even
        # though the real content is almost always UTF-8 on the modern
        # web. Without this fix, special characters (curly quotes,
        # em-dashes, accented letters) get scrambled, which would show up
        # as a fake "content differs after JavaScript" finding later, even
        # though nothing is actually wrong with the page.
        response.encoding = "utf-8"
        return {
            "status_code": response.status_code,
            "final_url": response.url,
            "redirect_chain": redirect_chain,
            "raw_html": response.text,
            "content_type": content_type,
            "is_html": "html" in content_type.lower(),
            "ssl_valid": True,
            "error": None,
        }
    except requests.exceptions.SSLError as ssl_error:
        return {
            "status_code": None,
            "final_url": url,
            "redirect_chain": [],
            "raw_html": "",
            "content_type": None,
            "is_html": None,
            "ssl_valid": False,
            "error": f"SSL error: {ssl_error}",
        }
    except requests.exceptions.RequestException as request_error:
        return {
            "status_code": None,
            "final_url": url,
            "redirect_chain": [],
            "raw_html": "",
            "content_type": None,
            "is_html": None,
            "ssl_valid": None,
            "error": f"Request failed: {request_error}",
        }


def _check_https_redirect(https_url):
    """
    Checks whether the plain-HTTP version of this URL correctly redirects to
    HTTPS, as our checklist requires. We only send a lightweight HEAD
    request (asking for headers only, not the full page) since we just need
    to see the redirect result, not the page content.
    """
    http_url = "http://" + https_url.split("://", 1)[1]
    try:
        response = requests.head(
            http_url,
            headers={"User-Agent": CRAWLER_USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        return {
            "http_url_tested": http_url,
            "final_url": response.url,
            "redirected_to_https": response.url.startswith("https://"),
            "error": None,
        }
    except requests.exceptions.RequestException as request_error:
        return {
            "http_url_tested": http_url,
            "final_url": None,
            "redirected_to_https": None,
            "error": f"Request failed: {request_error}",
        }


def _fetch_rendered_html(url, browser):
    """
    Uses an already-running Playwright browser to open the page for real,
    let JavaScript finish running, and read the final HTML.

    We accept an existing `browser` object (instead of starting a new
    browser each time) because launching a browser is slow -- we want to
    launch it ONCE and reuse it for every page we crawl.
    """
    page = browser.new_page(user_agent=CRAWLER_USER_AGENT)
    try:
        # "networkidle" waits until the page has stopped making new network
        # requests for a short period -- a reasonable sign that JavaScript
        # has finished loading dynamic content.
        response = page.goto(url, wait_until="networkidle", timeout=45000)
        rendered_html = page.content()
        return {
            "status_code": response.status if response else None,
            "final_url": page.url,
            "rendered_html": rendered_html,
            "error": None,
        }
    except Exception as playwright_error:  # noqa: BLE001 - deliberately broad: a single page's rendering problem must not crash the whole crawl.
        return {
            "status_code": None,
            "final_url": url,
            "rendered_html": "",
            "error": f"Rendering failed: {playwright_error}",
        }
    finally:
        # Always close the page (browser tab) we opened, even if an error
        # happened above, so we don't leak memory across hundreds of pages.
        page.close()


def _compare_raw_vs_rendered(raw_seo_data, rendered_seo_data):
    """
    Compares the key SEO elements between the raw (pre-JavaScript) and
    rendered (post-JavaScript) versions of the page. A meaningful
    difference here is exactly what our "JS Rendering" and "SSR vs CSR"
    checklist rules are looking for: important content that only exists
    after JavaScript runs is a risk, because search engines may not always
    process it.
    """
    return {
        "title_matches": raw_seo_data["title"] == rendered_seo_data["title"],
        "meta_description_matches": (
            raw_seo_data["meta_description"] == rendered_seo_data["meta_description"]
        ),
        "h1_matches": raw_seo_data["h1_texts"] == rendered_seo_data["h1_texts"],
        "raw_internal_link_count": len(raw_seo_data["internal_links"]),
        "rendered_internal_link_count": len(rendered_seo_data["internal_links"]),
    }


def extract_page_data(url, browser):
    """
    Main entry point for this file. Given one URL and an already-running
    Playwright browser, gathers everything Agent 3 will need to check this
    page against our SEO rules.

    Returns a single dictionary representing everything we know about this
    one page -- this is the record that gets handed to Agent 2 (storage).
    """
    raw_fetch = _fetch_raw_html(url)

    # If this URL isn't actually an HTML page (e.g. an XML file mistakenly
    # listed in the sitemap), there's no point opening a browser to "render"
    # it, and no SEO tags to extract -- we just record that fact and stop
    # here for this URL.
    if raw_fetch["is_html"] is False:
        return {
            "url": url,
            "raw_fetch": {key: value for key, value in raw_fetch.items() if key != "raw_html"},
            "https_redirect_check": None,
            "rendered_fetch": None,
            "seo_data": None,
            "js_rendering_comparison": None,
        }

    https_redirect_check = _check_https_redirect(url)
    rendered_fetch = _fetch_rendered_html(url, browser)

    raw_seo_data = _extract_seo_elements_from_html(raw_fetch["raw_html"], url) if raw_fetch["raw_html"] else None
    rendered_seo_data = (
        _extract_seo_elements_from_html(rendered_fetch["rendered_html"], url)
        if rendered_fetch["rendered_html"]
        else None
    )

    js_rendering_comparison = (
        _compare_raw_vs_rendered(raw_seo_data, rendered_seo_data)
        if raw_seo_data and rendered_seo_data
        else None
    )

    # We've now pulled everything we need out of the raw and rendered HTML
    # (into raw_seo_data / rendered_seo_data / js_rendering_comparison
    # above), so we deliberately do NOT keep the full HTML text itself in
    # the output. Each page's full HTML can be well over 1MB, and we don't
    # need it again downstream -- keeping it would make our stored history
    # balloon in size for no benefit. We keep everything else (status
    # codes, redirect chains, errors) since those are small and useful.
    raw_fetch_without_html = {key: value for key, value in raw_fetch.items() if key != "raw_html"}
    rendered_fetch_without_html = {
        key: value for key, value in rendered_fetch.items() if key != "rendered_html"
    }

    return {
        "url": url,
        "raw_fetch": raw_fetch_without_html,
        "https_redirect_check": https_redirect_check,
        "rendered_fetch": rendered_fetch_without_html,
        # We treat the RENDERED version as "the truth" for actual rule
        # checking, since that's the closest to what a real visitor (and
        # modern Google crawling) ultimately sees. The raw version is kept
        # only for the JS-rendering comparison above.
        "seo_data": rendered_seo_data or raw_seo_data,
        "js_rendering_comparison": js_rendering_comparison,
    }


# Manual test: run this file directly to try extraction on a small handful
# of real pages before we plug it into the full crawl (step 1c).
if __name__ == "__main__":
    from playwright.sync_api import sync_playwright

    test_urls = [
        "https://simprosys.com/",
        "https://simprosys.com/google-shopping-feed",
        "https://simprosys.com/simprotips",
    ]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for test_url in test_urls:
                print(f"\n=== {test_url} ===")
                page_data = extract_page_data(test_url, browser)

                print(f"Raw fetch status: {page_data['raw_fetch']['status_code']}")
                print(f"Rendered fetch status: {page_data['rendered_fetch']['status_code']}")
                print(f"HTTP -> HTTPS redirect OK: {page_data['https_redirect_check']['redirected_to_https']}")

                seo = page_data["seo_data"]
                print(f"Title: {seo['title']}")
                print(f"Meta description: {seo['meta_description']}")
                print(f"Canonical tag(s): {seo['canonical_urls']}")
                print(f"Robots meta: {seo['robots_meta_content']}")
                print(f"H1s: {seo['h1_texts']}")
                print(f"Images found: {len(seo['images'])}")
                print(f"Internal links: {len(seo['internal_links'])}, External links: {len(seo['external_links'])}")
                print(f"Schema blocks found: {len(seo['schema_blocks'])}")
                print(f"Mixed content resources: {seo['mixed_content_urls']}")
                print(f"JS rendering comparison: {page_data['js_rendering_comparison']}")
        finally:
            browser.close()
