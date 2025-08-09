#!/usr/bin/env python3
import json
import csv
import time
import re
import urllib.parse
from typing import Optional, List, Set
from dataclasses import dataclass, asdict
from collections import deque

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.sajeevavahini.com"
START_PATH = "/telugu-bible-dictionary/"
ALLOWED_PREFIX = "/telugu-bible-dictionary"
MAX_PAGES_DEFAULT = 100
REQUEST_DELAY_SECS = 1.0

@dataclass
class PageData:
    url: str
    title: str
    heading: Optional[str]
    text: str
    html: str


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc and parsed.netloc.lower() != urllib.parse.urlparse(BASE_URL).netloc.lower():
        return ""
    path = re.sub(r"/+", "/", parsed.path)
    normalized = urllib.parse.urlunparse((
        "https",
        urllib.parse.urlparse(BASE_URL).netloc,
        path if path.endswith('/') or '.' in path.split('/')[-1] else (path + '/'),
        "",
        parsed.query,
        "",
    ))
    return normalized


def extract_content(html: str) -> PageData:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("title").get_text(strip=True) if soup.find("title") else ""
    heading_tag = soup.find(["h1", "h2"]) or soup.select_one(".page-title, .entry-title")
    heading = heading_tag.get_text(strip=True) if heading_tag else None

    candidates = [
        "article",
        "#content",
        ".content",
        ".page-content",
        ".entry-content",
        ".container",
        ".col-md-9",
        "main",
    ]
    main = None
    for sel in candidates:
        main = soup.select_one(sel)
        if main and len(main.get_text(strip=True)) > 100:
            break
    if main is None:
        main = soup.body or soup
    for sel in ["nav", "footer", "header", "aside", "script", "style", "noscript", ".sidebar", ".breadcrumbs", ".site-footer", ".site-header"]:
        for node in main.select(sel):
            node.decompose()
    text = main.get_text(separator="\n", strip=True)
    return PageData(url="", title=title, heading=heading, text=text, html=str(main))


def find_links(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        abs_url = urllib.parse.urljoin(BASE_URL, href)
        norm = normalize_url(abs_url)
        if not norm:
            continue
        path = urllib.parse.urlparse(norm).path
        if not path.startswith(ALLOWED_PREFIX):
            continue
        if any(path.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".pdf", ".zip", ".rar"]):
            continue
        links.append(norm)
    return links


def parse_cookie_header(cookie_header: str):
    items = []
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        items.append({
            "name": name,
            "value": value,
            "domain": urllib.parse.urlparse(BASE_URL).hostname or "www.sajeevavahini.com",
            "path": "/",
            "httpOnly": False,
            "secure": True,
            # no expiration so it's a session cookie
        })
    return items


def crawl_playwright(max_pages: int, output_jsonl: str, output_csv: Optional[str], storage_state_path: Optional[str], cookie_header: Optional[str], headless: bool) -> List[PageData]:
    results: List[PageData] = []
    visited: Set[str] = set()
    queue: deque[str] = deque([urllib.parse.urljoin(BASE_URL, START_PATH)])

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context_kwargs = dict(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            locale="en-US",
            viewport={"width": 1366, "height": 900},
            java_script_enabled=True,
            timezone_id="Asia/Kolkata",
        )
        if storage_state_path:
            try:
                context_kwargs["storage_state"] = storage_state_path
            except Exception:
                pass
        context = browser.new_context(**context_kwargs)
        # Stealth-like evasions
        context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            """
        )
        extra_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.sajeevavahini.com/",
        }
        context.set_extra_http_headers(extra_headers)
        if cookie_header:
            try:
                context.add_cookies(parse_cookie_header(cookie_header))
            except Exception:
                pass

        # Optionally reduce resource load
        page = context.new_page()
        try:
            page.route("**/*", lambda route: route.continue_() if route.request.resource_type in ["document", "xhr", "fetch", "script"] else route.abort())
        except Exception:
            pass

        while queue and len(visited) < max_pages:
            url = queue.popleft()
            if url in visited:
                continue
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
                # Allow time for potential Cloudflare challenge to complete
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                # Fallback waits
                page.wait_for_selector("body", timeout=10000)
                time.sleep(6)
            except Exception as e:
                # Save debug artifacts
                try:
                    page.screenshot(path=f"/workspace/debug_failed_{len(visited)}.png", full_page=True)
                    with open(f"/workspace/debug_failed_{len(visited)}.html", "w", encoding="utf-8") as fh:
                        fh.write(page.content())
                except Exception:
                    pass
                continue

            status = resp.status if resp else 0
            html = page.content()
            title_text = ""
            try:
                title_text = page.title()
            except Exception:
                pass

            # Detect Cloudflare interstitial
            if (status and status >= 400) or ("cf-browser-verification" in html or "Just a moment" in html or "cf-chl-" in html):
                # Give it more time and retry once
                time.sleep(8)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                html = page.content()
                try:
                    title_text = page.title()
                except Exception:
                    pass

            # If still blocked, dump debug and skip
            if (status and status >= 400) or ("cf-browser-verification" in html or "Just a moment" in html or "cf-chl-" in html):
                try:
                    page.screenshot(path=f"/workspace/debug_cf_{len(visited)}.png", full_page=True)
                    with open(f"/workspace/debug_cf_{len(visited)}.html", "w", encoding="utf-8") as fh:
                        fh.write(html)
                except Exception:
                    pass
                visited.add(url)
                time.sleep(REQUEST_DELAY_SECS)
                continue

            pdata = extract_content(html)
            pdata.url = url
            if not pdata.title:
                pdata.title = title_text
            results.append(pdata)
            visited.add(url)

            for link in find_links(html):
                if link not in visited:
                    queue.append(link)

            time.sleep(REQUEST_DELAY_SECS)

        # Persist storage state for reuse
        if storage_state_path:
            try:
                context.storage_state(path=storage_state_path)
            except Exception:
                pass

        context.close()
        browser.close()

    with open(output_jsonl, "w", encoding="utf-8") as f:
        for page_data in results:
            f.write(json.dumps(asdict(page_data), ensure_ascii=False) + "\n")

    if output_csv:
        with open(output_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["url", "title", "heading", "text"])
            writer.writeheader()
            for page_data in results:
                writer.writerow({
                    "url": page_data.url,
                    "title": page_data.title,
                    "heading": page_data.heading or "",
                    "text": page_data.text,
                })

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Crawl Telugu Bible Dictionary via Playwright and extract content")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES_DEFAULT, help="Maximum number of pages to crawl")
    parser.add_argument("--jsonl", default="/workspace/sajeevavahini_dict.jsonl", help="Output JSONL path")
    parser.add_argument("--csv", default="/workspace/sajeevavahini_dict.csv", help="Output CSV path (empty to disable)")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY_SECS, help="Delay between requests (seconds)")
    parser.add_argument("--storage-state", default="/workspace/storage_state.json", help="Path to persist/reuse browser storage state (cookies, etc.)")
    parser.add_argument("--cookie", default="", help="Optional Cookie header string copied from a real browser session")
    parser.add_argument("--headless", action="store_true", help="Run browser headless (default)")
    parser.add_argument("--headed", dest="headless", action="store_false", help="Run browser with UI (headed)")
    parser.set_defaults(headless=True)

    args = parser.parse_args()
    REQUEST_DELAY_SECS = max(0.0, args.delay)
    crawl_playwright(
        max_pages=args.max_pages,
        output_jsonl=args.jsonl,
        output_csv=(args.csv or None),
        storage_state_path=args.storage_state,
        cookie_header=(args.cookie or None),
        headless=args.headless,
    )