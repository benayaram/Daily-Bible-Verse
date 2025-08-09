#!/usr/bin/env python3
import os
import re
import time
import json
import csv
import urllib.parse
from collections import deque
from dataclasses import dataclass, asdict
from typing import Set, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

BASE_URL = "https://www.sajeevavahini.com"
START_PATH = "/telugu-bible-dictionary"
START_URL = urllib.parse.urljoin(BASE_URL, START_PATH)
ALLOWED_PREFIX = "/telugu-bible-dictionary"
USER_AGENT = "Mozilla/5.0 (compatible; telugu-dict-scraper/1.0; +https://example.com/bot)"
REQUEST_TIMEOUT_SECS = 20
REQUEST_DELAY_SECS = 1.0  # be polite
MAX_PAGES_DEFAULT = 100  # can be overridden via CLI

@dataclass
class PageData:
    url: str
    title: str
    heading: Optional[str]
    text: str
    html: str


def is_allowed_by_robots(session: requests.Session, url: str) -> bool:
    # Very simple robots.txt check: fetch robots.txt once and look for disallow lines
    # Note: For robust compliance, use urllib.robotparser; kept simple and cached here.
    robots_url = urllib.parse.urljoin(BASE_URL, "/robots.txt")
    try:
        resp = session.get(robots_url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECS)
        if resp.status_code != 200:
            return True  # Assume allowed if robots not accessible
        disallows = []
        user_agent_block = None
        current_agent = None
        for line in resp.text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("user-agent:"):
                current_agent = line.split(":", 1)[1].strip()
                user_agent_block = (current_agent == "*") or ("telugu-dict-scraper" in current_agent)
            elif user_agent_block and line.lower().startswith("disallow:"):
                path = line.split(":", 1)[1].strip() or "/"
                disallows.append(path)
        path = urllib.parse.urlparse(url).path
        for dis in disallows:
            if path.startswith(dis):
                return False
        return True
    except Exception:
        return True


def normalize_url(url: str) -> str:
    # Remove fragments, normalize scheme/host, keep query if present
    parsed = urllib.parse.urlparse(url)
    # Only keep site URLs
    if parsed.netloc and parsed.netloc.lower() != urllib.parse.urlparse(BASE_URL).netloc.lower():
        return ""
    # Normalize path
    path = re.sub(r"/+", "/", parsed.path)
    # Rebuild
    normalized = urllib.parse.urlunparse((
        "https",
        urllib.parse.urlparse(BASE_URL).netloc,
        path,
        "",
        parsed.query,
        "",
    ))
    return normalized


def extract_content(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    # Try to extract the main article content
    title = soup.find("title").get_text(strip=True) if soup.find("title") else ""
    # Try main heading
    heading_tag = soup.find(["h1", "h2"]) or soup.select_one(".page-title, .entry-title")
    heading = heading_tag.get_text(strip=True) if heading_tag else None
    # Main content containers candidates
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
    # Remove nav/footer/script/style/sidebar
    for sel in ["nav", "footer", "header", "aside", "script", "style", "noscript", ".sidebar", ".breadcrumbs", ".site-footer", ".site-header"]:
        for node in main.select(sel):
            node.decompose()
    text = main.get_text(separator="\n", strip=True)
    html = str(main)
    return {"title": title, "heading": heading, "text": text, "html": html}


def find_links(soup: BeautifulSoup) -> List[str]:
    links: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Resolve relative URLs
        abs_url = urllib.parse.urljoin(BASE_URL, href)
        norm = normalize_url(abs_url)
        if not norm:
            continue
        path = urllib.parse.urlparse(norm).path
        if not path.startswith(ALLOWED_PREFIX):
            continue
        # Heuristic: avoid media, mailto, tel, anchors
        if any(path.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".pdf", ".zip", ".rar"]):
            continue
        links.append(norm)
    return links


def crawl(max_pages: int = MAX_PAGES_DEFAULT, output_jsonl: str = "output.jsonl", output_csv: Optional[str] = "output.csv") -> List[PageData]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    if not is_allowed_by_robots(session, START_URL):
        raise SystemExit("Blocked by robots.txt for the start URL")

    visited: Set[str] = set()
    queue: deque[str] = deque([START_URL])
    results: List[PageData] = []

    pbar = tqdm(total=max_pages, desc="Crawling pages")
    while queue and len(visited) < max_pages:
        url = queue.popleft()
        if url in visited:
            continue
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT_SECS)
        except Exception as e:
            tqdm.write(f"Request failed: {url} :: {e}")
            continue
        if resp.status_code != 200:
            tqdm.write(f"Non-200 status {resp.status_code} for {url}")
            continue

        visited.add(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        content = extract_content(soup)
        page = PageData(
            url=url,
            title=content["title"],
            heading=content["heading"],
            text=content["text"],
            html=content["html"],
        )
        results.append(page)

        # Queue new links
        for link in find_links(soup):
            if link not in visited:
                queue.append(link)

        pbar.update(1)
        time.sleep(REQUEST_DELAY_SECS)
    pbar.close()

    # Write JSONL
    with open(output_jsonl, "w", encoding="utf-8") as f:
        for page in results:
            f.write(json.dumps(asdict(page), ensure_ascii=False) + "\n")

    # Optional CSV
    if output_csv:
        with open(output_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["url", "title", "heading", "text"])
            writer.writeheader()
            for page in results:
                writer.writerow({
                    "url": page.url,
                    "title": page.title,
                    "heading": page.heading or "",
                    "text": page.text,
                })

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Crawl Telugu Bible Dictionary pages and extract content")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES_DEFAULT, help="Maximum number of pages to crawl")
    parser.add_argument("--jsonl", default="/workspace/sajeevavahini_dict.jsonl", help="Output JSONL path")
    parser.add_argument("--csv", default="/workspace/sajeevavahini_dict.csv", help="Output CSV path (empty to disable)")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY_SECS, help="Delay between requests (seconds)")

    args = parser.parse_args()

    REQUEST_DELAY_SECS = max(0.0, args.delay)
    crawl(max_pages=args.max_pages, output_jsonl=args.jsonl, output_csv=(args.csv or None))