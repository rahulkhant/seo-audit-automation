"""
Agent 1, Step 1a: Sitemap & robots.txt discovery.

Purpose of this file
--------------------
Before we can check any SEO rules, we need to know WHICH pages exist on the
website. This file answers that question by doing two things, in order:

1. Reading the site's robots.txt file, which tells us:
   - Where the XML sitemap(s) are located.
   - Which URLs the site owner has asked crawlers NOT to visit ("Disallow"
     rules).
   - How many seconds to wait between requests ("Crawl-delay"), so our own
     crawler is polite and doesn't overload the site's server.

2. Reading the XML sitemap itself, which lists every URL the site wants
   search engines (and, in our case, our own audit tool) to know about.

The end result of this file is a simple, structured "crawl plan": a list of
URLs we are allowed and intended to crawl, plus a few pieces of housekeeping
information (crawl delay, and any URLs that show up in the sitemap despite
being disallowed in robots.txt -- which is itself a real SEO problem worth
flagging later).

This file does NOT fetch full page content (title, meta tags, etc.) -- that
happens in the next step (Agent 1, step 1b). This step only figures out the
list of pages to visit.
"""

import urllib.robotparser
import xml.etree.ElementTree as ElementTree

import requests


# We identify our own crawler with a custom User-Agent string. Sites can see
# this in their server logs, and some can be configured to treat unknown
# crawlers differently, so it's good practice to identify ourselves clearly
# rather than pretending to be a regular web browser.
CRAWLER_USER_AGENT = "SimprosysSEOAuditBot/1.0"

# Sitemaps sometimes group URLs using the XML "namespace" shown below. When
# reading values out of the XML, we have to include this namespace prefix or
# Python's XML parser won't find the tags. This is a technical detail of how
# the sitemaps.org standard is written, not something specific to our site.
SITEMAP_XML_NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _fetch_robots_txt_info(site_root_url, user_agent):
    """
    Downloads and reads the site's robots.txt file.

    Returns a dictionary with:
      - "parser": a configured RobotFileParser object we can later ask
        "is this URL allowed?" (used when filtering sitemap URLs, and again
        later in step 1b before crawling each page).
      - "crawl_delay_seconds": how many seconds robots.txt asks us to wait
        between requests. Defaults to 1 second if the site doesn't specify
        one, as a safe minimum politeness delay.
      - "sitemap_urls": any sitemap locations robots.txt explicitly points to.
        Some sites list one, some list several, some list none (in which
        case we fall back to the standard /sitemap.xml location).
    """
    robots_txt_url = site_root_url.rstrip("/") + "/robots.txt"

    # RobotFileParser is part of Python's standard library and already knows
    # how to read and interpret robots.txt rules (Disallow, Allow,
    # Crawl-delay, Sitemap), so we don't need to write our own parser.
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_txt_url)
    parser.read()

    # crawl_delay() returns None if robots.txt didn't specify one.
    crawl_delay_seconds = parser.crawl_delay(user_agent)
    if crawl_delay_seconds is None:
        crawl_delay_seconds = 1

    # site_maps() returns None if robots.txt has no "Sitemap:" lines at all.
    sitemap_urls = parser.site_maps() or []

    return {
        "parser": parser,
        "crawl_delay_seconds": crawl_delay_seconds,
        "sitemap_urls": sitemap_urls,
    }


def _fetch_sitemap_urls(sitemap_url, user_agent):
    """
    Downloads one sitemap.xml file and returns every page URL listed inside
    it, as a plain list of strings.

    Note: this function assumes a standard "flat" sitemap (a <urlset> full of
    <url><loc>...</loc></url> entries), which is what simprosys.com actually
    uses. Some larger sites instead use a "sitemap index" file that points to
    several smaller sitemap files -- we are not handling that case here since
    it doesn't apply to our current site, but it's a known limitation if we
    add a site later that uses that pattern.
    """
    response = requests.get(
        sitemap_url,
        headers={"User-Agent": user_agent},
        timeout=30,
    )
    response.raise_for_status()  # Stops here with an error if the fetch failed.

    xml_root = ElementTree.fromstring(response.content)

    # Find every <loc> tag inside the sitemap and pull out its text content
    # (the actual URL). ".//" means "search at any depth", and the namespace
    # dictionary is required for Python to match the sitemaps.org tag names.
    return [
        loc_element.text.strip()
        for loc_element in xml_root.findall(".//sm:loc", SITEMAP_XML_NAMESPACE)
        if loc_element.text
    ]


def discover_urls_to_crawl(site_root_url, user_agent=CRAWLER_USER_AGENT):
    """
    Main entry point for this file. Given a site's root URL (e.g.
    "https://simprosys.com"), figures out the full list of URLs we should
    crawl next.

    Returns a dictionary with:
      - "urls_to_crawl": list of URLs that are both in the sitemap AND
        allowed by robots.txt. This is what Agent 1's next step (1b) will
        actually visit.
      - "disallowed_but_in_sitemap": list of URLs that appear in the sitemap
        but are blocked by robots.txt. Having any URLs here is itself a real
        SEO problem (the best-practice document says sitemaps should only
        ever contain crawlable, indexable pages) -- we keep this list so
        Agent 3 can report it later, rather than silently dropping the
        information.
      - "crawl_delay_seconds": how long to wait between requests when we
        get to step 1b (politeness setting).
      - "sitemap_url_used": which sitemap URL we actually read, useful for
        debugging.
    """
    robots_info = _fetch_robots_txt_info(site_root_url, user_agent)

    # Prefer the sitemap location(s) robots.txt points to. If robots.txt
    # didn't mention any, fall back to the conventional /sitemap.xml path.
    sitemap_urls_to_check = robots_info["sitemap_urls"] or [
        site_root_url.rstrip("/") + "/sitemap.xml"
    ]

    # Most sites (including ours) only declare one sitemap, but we loop over
    # all declared sitemaps and combine their URLs, in case more than one
    # is listed.
    all_sitemap_page_urls = []
    for sitemap_url in sitemap_urls_to_check:
        all_sitemap_page_urls.extend(_fetch_sitemap_urls(sitemap_url, user_agent))

    # Now split the sitemap's URLs into "allowed to crawl" vs "disallowed by
    # robots.txt", using the robots.txt rules we already parsed above.
    urls_to_crawl = []
    disallowed_but_in_sitemap = []
    robots_parser = robots_info["parser"]
    for page_url in all_sitemap_page_urls:
        if robots_parser.can_fetch(user_agent, page_url):
            urls_to_crawl.append(page_url)
        else:
            disallowed_but_in_sitemap.append(page_url)

    return {
        "urls_to_crawl": urls_to_crawl,
        "disallowed_but_in_sitemap": disallowed_but_in_sitemap,
        "crawl_delay_seconds": robots_info["crawl_delay_seconds"],
        "sitemap_url_used": ", ".join(sitemap_urls_to_check),
    }


# This block only runs when you execute this file directly
# (e.g. "python sitemap_discovery.py"), not when it's imported by another
# file. It's here so we can manually test this step on its own, before
# building anything else on top of it.
if __name__ == "__main__":
    crawl_plan = discover_urls_to_crawl("https://simprosys.com")

    print(f"Sitemap(s) used: {crawl_plan['sitemap_url_used']}")
    print(f"Crawl delay to respect: {crawl_plan['crawl_delay_seconds']} second(s)")
    print(f"Total URLs to crawl: {len(crawl_plan['urls_to_crawl'])}")
    print(f"URLs disallowed but present in sitemap: {len(crawl_plan['disallowed_but_in_sitemap'])}")

    if crawl_plan["disallowed_but_in_sitemap"]:
        print("\nThese URLs are in the sitemap but blocked by robots.txt (a real issue to flag later):")
        for blocked_url in crawl_plan["disallowed_but_in_sitemap"]:
            print(f"  - {blocked_url}")

    print("\nFirst 10 URLs we will crawl:")
    for url in crawl_plan["urls_to_crawl"][:10]:
        print(f"  - {url}")
