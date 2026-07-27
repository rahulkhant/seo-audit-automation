"""
Agent 1, Step 1c: Full-site crawl runner.

Purpose of this file
--------------------
This file ties together the previous two steps into the actual, complete
Agent 1:

  1a (sitemap_discovery.py) -> get the list of URLs to crawl
  1b (page_extractor.py)    -> extract SEO data from ONE page

This file loops over EVERY url from step 1a, calling step 1b for each one,
while being polite to the website (respecting the crawl delay from
robots.txt) and resilient to errors (one broken page should never stop the
whole crawl).

The final result of this file is a single JSON file written to
"data/latest_crawl.json" -- this is the handoff point to Agent 2 (storage).
We use a plain file (rather than, say, calling Agent 2's code directly) so
each agent stays independent and testable on its own, exactly as we planned:
you can re-run Agent 1 by itself and inspect its output before Agent 2 ever
touches it.
"""

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from agent1_crawl.sitemap_discovery import discover_urls_to_crawl
from agent1_crawl.page_extractor import extract_page_data

# Where Agent 1's final output gets written, for Agent 2 to read later.
# This path is relative to the project's root folder (seo-audit-automation/).
OUTPUT_FILE_PATH = Path(__file__).resolve().parent.parent / "data" / "latest_crawl.json"


def run_full_crawl(site_root_url):
    """
    Runs the complete Agent 1 process for one website:
      1. Discover which URLs to crawl (step 1a).
      2. Visit each one, extracting SEO data (step 1b), waiting between
         each page as robots.txt asks us to.
      3. Collect everything into one combined result dictionary.

    Returns that result dictionary. (Saving it to a file happens separately,
    in save_crawl_result(), so this function stays focused on just crawling.)
    """
    print(f"Discovering URLs to crawl for {site_root_url} ...")
    crawl_plan = discover_urls_to_crawl(site_root_url)
    urls_to_crawl = crawl_plan["urls_to_crawl"]
    crawl_delay_seconds = crawl_plan["crawl_delay_seconds"]

    print(f"Found {len(urls_to_crawl)} URLs to crawl.")
    print(f"Respecting a {crawl_delay_seconds}-second delay between pages, as requested by robots.txt.\n")

    page_results = []
    crawl_errors = []
    started_at = time.time()

    # We launch ONE browser and reuse it for every page, rather than
    # starting a new browser per page, since launching a browser is slow.
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for index, url in enumerate(urls_to_crawl, start=1):
                print(f"[{index}/{len(urls_to_crawl)}] Crawling: {url}")
                try:
                    page_data = extract_page_data(url, browser)
                    page_results.append(page_data)

                    raw_status = page_data["raw_fetch"]["status_code"]
                    if page_data["rendered_fetch"] is None:
                        # This URL wasn't an HTML page (e.g. an XML file),
                        # so rendering was skipped entirely -- nothing wrong,
                        # just nothing to report for that part.
                        print(f"    -> raw status: {raw_status}, not an HTML page (rendering skipped)")
                    else:
                        rendered_status = page_data["rendered_fetch"]["status_code"]
                        print(f"    -> raw status: {raw_status}, rendered status: {rendered_status}")
                except Exception as unexpected_error:  # noqa: BLE001 - a single page's failure must never stop the whole crawl.
                    print(f"    -> FAILED: {unexpected_error}")
                    crawl_errors.append({"url": url, "error": str(unexpected_error)})

                # Politeness pause. We skip waiting after the very last page
                # since there's nothing left to be polite before.
                if index < len(urls_to_crawl):
                    time.sleep(crawl_delay_seconds)
        finally:
            browser.close()

    finished_at = time.time()
    duration_seconds = round(finished_at - started_at, 1)
    print(f"\nCrawl finished in {duration_seconds} seconds.")
    print(f"Pages successfully crawled: {len(page_results)}")
    print(f"Pages that failed: {len(crawl_errors)}")

    return {
        "site_root_url": site_root_url,
        "sitemap_url_used": crawl_plan["sitemap_url_used"],
        "disallowed_but_in_sitemap": crawl_plan["disallowed_but_in_sitemap"],
        "crawl_duration_seconds": duration_seconds,
        "pages": page_results,
        "crawl_errors": crawl_errors,
    }


def save_crawl_result(crawl_result, output_path=OUTPUT_FILE_PATH):
    """
    Saves the crawl result to a JSON file, creating the "data" folder first
    if it doesn't exist yet. This file is what Agent 2 will read next.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(crawl_result, output_file, indent=2, ensure_ascii=False)
    print(f"\nSaved crawl result to: {output_path}")


# Manual test: run this file directly to perform a full crawl of the real
# site and save the result, before we build Agent 2 on top of it.
if __name__ == "__main__":
    result = run_full_crawl("https://simprosys.com")
    save_crawl_result(result)
