#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["feedparser>=6.0", "trafilatura>=1.12"]
# ///
"""Fetch recent posts from RSS/Atom feeds and write one text file per feed.

Usage:
    uv run fetch_feeds.py --config feeds.json --out-dir .cache/blogs-2026-09-24 --state-dir blogs
    uv run fetch_feeds.py --config feeds.json --out-dir DIR --since 2026-09-20

The period starts at local midnight of a start date: --since if given, otherwise
the newest YYYY-MM-DD.md in --state-dir dated before today (the local date,
matching how state files are named), capped at 7 days before today.

Output (in --out-dir, cleared first):
    manifest.json   {since, feeds: [{name, url, file, count}], errors: [{name, url, error}]}
    NN-<slug>.txt   Posts of one feed, wrapped to short lines for the Read tool.
A non-empty --out-dir without manifest.json is refused (exit 1), so a mistyped
path cannot delete unrelated files.
Progress and errors go to stderr.
"""

import argparse
import json
import os
import re
import shutil
import sys
import textwrap
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from html import unescape
from html.parser import HTMLParser

import feedparser
import trafilatura


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = "Mozilla/5.0 (briefing-digest/1.0; +https://briefing.kamata.page/)"
DATE_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
MAX_LOOKBACK_DAYS = 7
DEFAULT_MAX_ITEMS = 5
MIN_FEED_BODY_CHARS = 1500
MAX_BODY_CHARS = 8000
WRAP_WIDTH = 200
MAX_ERROR_CHARS = 500
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds, doubled each retry
TIMEOUT = 30
WORKERS = 8


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def error_text(e: BaseException, max_chars: int = MAX_ERROR_CHARS) -> str:
    return str(e)[:max_chars]


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def http_get_bytes(url: str) -> bytes:
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except Exception as e:  # noqa: BLE001 - any network error is retried
            last_error = e
            print(f"  retry {attempt + 1}/{MAX_RETRIES} {url}: {e}", file=sys.stderr)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF * 2**attempt)
    raise RuntimeError(f"GET {url} failed: {last_error}")


# ---------------------------------------------------------------------------
# Period
# ---------------------------------------------------------------------------


def dates_in_dir(path: str | None) -> list[date]:
    if not path or not os.path.isdir(path):
        return []
    out = []
    for name in os.listdir(path):
        m = DATE_FILE_RE.match(name)
        if m:
            out.append(date.fromisoformat(m.group(1)))
    return out


def compute_since(existing: list[date], today: date) -> date:
    floor = today - timedelta(days=MAX_LOOKBACK_DAYS)
    prior = [d for d in existing if d < today]
    return max(max(prior), floor) if prior else floor


# ---------------------------------------------------------------------------
# Parsing (pure)
# ---------------------------------------------------------------------------


def html_to_text(html: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>|</p>|</h\d>|</li>|</div>", "\n", html or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def entry_datetime(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None


class _HrefParser(HTMLParser):
    """Collects every <a href> in document order."""

    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        for key, value in attrs:
            if key == "href" and value:
                self.hrefs.append(value)


def extract_links(html: str, base_url: str) -> list[str]:
    """Return every <a href> in html, resolved against base_url."""
    parser = _HrefParser()
    parser.feed(html or "")
    return [urllib.parse.urljoin(base_url, href) for href in parser.hrefs]


def normalize_url(url: str) -> str:
    """Normalize a URL for comparison: ignore scheme, trailing slash, query and fragment."""
    parsed = urllib.parse.urlsplit(url)
    return f"{parsed.netloc}{parsed.path.rstrip('/')}"


def select_entries(entries, since: date, max_items: int, allowed_links: set[str] | None = None) -> list[dict]:
    # State files are named by local date, so the period starts at local midnight.
    since_dt = datetime.combine(since, dtime.min).astimezone()
    picked = []
    for entry in entries:
        published = entry_datetime(entry)
        if published is None or published < since_dt:
            continue
        link = entry.get("link") or ""
        if allowed_links is not None and normalize_url(link) not in allowed_links:
            continue
        contents = entry.get("content") or []
        picked.append(
            {
                "title": " ".join((entry.get("title") or "").split()),
                "link": link,
                "published": published.isoformat(),
                "author": entry.get("author") or "",
                "feed_text": html_to_text(contents[0].get("value", "")) if contents else "",
                "summary": html_to_text(entry.get("summary", "")),
            }
        )
    picked.sort(key=lambda item: item["published"], reverse=True)
    return picked[:max_items]


def choose_body(feed_text: str, summary: str, fetch_page) -> tuple[str, str]:
    """Return (body, source). fetch_page() is called only when the feed text is short."""
    if len(feed_text) >= MIN_FEED_BODY_CHARS:
        return feed_text[:MAX_BODY_CHARS], "feed"
    page_text = fetch_page()
    if page_text:
        return page_text[:MAX_BODY_CHARS], "page"
    if feed_text:
        return feed_text[:MAX_BODY_CHARS], "feed"
    return summary[:MAX_BODY_CHARS], "summary"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "feed"


def format_feed(name: str, url: str, items: list[dict]) -> str:
    lines = [f"# {name}", f"Feed: {url}", ""]
    for i, item in enumerate(items, 1):
        lines += [
            f"## {i}. {item['title']}",
            f"Link: {item['link']}",
            f"Published: {item['published']}",
            f"Author: {item['author']}",
            f"Body-Source: {item['body_source']}",
            "",
        ]
        for paragraph in item["body"].split("\n"):
            lines += textwrap.wrap(paragraph, WRAP_WIDTH) or [""]
            lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def extract_page(url: str) -> str | None:
    if not url:
        return None
    try:
        html = http_get_bytes(url).decode("utf-8", errors="replace")
        return trafilatura.extract(html) or None
    except Exception as e:  # noqa: BLE001 - fall back to feed text
        print(f"  page extract failed {url}: {e}", file=sys.stderr)
        return None


def fetch_allowed_links(page_urls: list[str]) -> set[str]:
    """Fetch each page and collect its normalized article links. Raises if any page fetch fails."""
    allowed = set()
    for page_url in page_urls:
        html = http_get_bytes(page_url).decode("utf-8", errors="replace")
        allowed.update(normalize_url(href) for href in extract_links(html, page_url))
    return allowed


def process_feed(index: int, feed: dict, since: date, max_items: int, out_dir: str) -> dict:
    name, url = feed["name"], feed["url"]
    print(f"Fetching {name}...", file=sys.stderr)
    parsed = feedparser.parse(http_get_bytes(url))
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"unparseable feed: {parsed.get('bozo_exception')}")
    include_links_from = feed.get("include_links_from")
    allowed_links = fetch_allowed_links(include_links_from) if include_links_from else None
    items = select_entries(parsed.entries, since, max_items, allowed_links)
    for item in items:
        link = item["link"]
        item["body"], item["body_source"] = choose_body(
            item.pop("feed_text"), item.pop("summary"), lambda: extract_page(link)
        )
    file_name = f"{index:02d}-{slugify(name)}.txt"
    if items:
        with open(os.path.join(out_dir, file_name), "w", encoding="utf-8") as f:
            f.write(format_feed(name, url, items))
    return {"name": name, "url": url, "file": file_name, "count": len(items)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def reset_out_dir(path: str) -> None:
    """Clear a previous run's output. Refuse a non-empty directory without manifest.json."""
    names = os.listdir(path) if os.path.isdir(path) else []
    if names and "manifest.json" not in names:
        print(f"Refusing to clear --out-dir {path}: it is not empty and has no manifest.json", file=sys.stderr)
        sys.exit(1)
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--state-dir")
    parser.add_argument("--since", help="YYYY-MM-DD; overrides --state-dir")
    args = parser.parse_args(argv)

    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)
    feeds = config["feeds"]
    max_items = config.get("max_items_per_feed", DEFAULT_MAX_ITEMS)
    today = date.today()  # local date: state files are named by local date
    since = date.fromisoformat(args.since) if args.since else compute_since(dates_in_dir(args.state_dir), today)

    reset_out_dir(args.out_dir)

    def work(pair):
        index, feed = pair
        try:
            return process_feed(index, feed, since, max_items, args.out_dir), None
        except Exception as e:  # noqa: BLE001 - one feed's failure must not stop the rest
            return None, {"name": feed["name"], "url": feed["url"], "error": error_text(e)}

    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(work, enumerate(feeds, 1)))

    manifest = {
        "since": since.isoformat(),
        "feeds": [r for r, _ in results if r and r["count"]],
        "errors": [e for _, e in results if e],
    }
    with open(os.path.join(args.out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    total = sum(feed["count"] for feed in manifest["feeds"])
    print(
        f"Done: {total} posts from {len(manifest['feeds'])} feeds since {since}, {len(manifest['errors'])} errors",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
