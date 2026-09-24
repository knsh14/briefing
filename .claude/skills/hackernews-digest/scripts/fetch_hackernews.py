#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Fetch top Hacker News stories and keyword matches from the last 24 hours.

Usage:
    uv run fetch_hackernews.py                               # Use keywords.json next to the skill
    uv run fetch_hackernews.py path/to/keywords.json
    uv run fetch_hackernews.py --out .cache/hackernews-2026-09-24.json

Output: JSON to --out (or stdout). Progress and errors go to stderr.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import unescape


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEARCH_URL = "https://hn.algolia.com/api/v1/search"
FIREBASE_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
HN_ITEM_URL = "https://news.ycombinator.com/item?id={id}"
USER_AGENT = "briefing-digest/1.0 (+https://briefing.kamata.page/)"
WINDOW_SECONDS = 24 * 60 * 60
HITS_PER_PAGE = 200
TOP_N = 30
MAX_KEYWORD_MATCHES = 20
MAX_COMMENTS = 3
MAX_COMMENT_CHARS = 500
DEFAULT_MIN_POINTS = 10
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds, doubled each retry
TIMEOUT = 30
WORKERS = 8


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def http_get_json(url: str):
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.load(resp)
        except Exception as e:  # noqa: BLE001 - any network error is retried
            last_error = e
            print(f"  retry {attempt + 1}/{MAX_RETRIES} {url}: {e}", file=sys.stderr)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF * 2**attempt)
    raise RuntimeError(f"GET {url} failed: {last_error}")


# ---------------------------------------------------------------------------
# Parsing (pure)
# ---------------------------------------------------------------------------


def search_url(since_ts: int, query: str = "", min_points: int = 0) -> str:
    filters = [f"created_at_i>{since_ts}"]
    if min_points:
        filters.append(f"points>={min_points}")
    params = {"tags": "story", "numericFilters": ",".join(filters), "hitsPerPage": HITS_PER_PAGE}
    if query:
        params["query"] = query
        params["restrictSearchableAttributes"] = "title"
        params["typoTolerance"] = "false"
    return f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"


def parse_hit(hit: dict) -> dict:
    story_id = str(hit["objectID"])
    hn_url = HN_ITEM_URL.format(id=story_id)
    return {
        "id": story_id,
        "title": hit.get("title") or "",
        "url": hit.get("url") or hn_url,
        "hn_url": hn_url,
        "points": hit.get("points") or 0,
        "num_comments": hit.get("num_comments") or 0,
        "author": hit.get("author") or "",
        "created_at": hit.get("created_at") or "",
    }


def by_points(stories) -> list[dict]:
    return sorted(stories, key=lambda s: s["points"], reverse=True)


def select_top(hits: list[dict], n: int = TOP_N) -> list[dict]:
    seen: set[str] = set()
    out = []
    for story in by_points(parse_hit(h) for h in hits):
        if story["id"] in seen:
            continue
        seen.add(story["id"])
        out.append(story)
    return out[:n]


def merge_keyword_hits(
    keyword_hits: dict[str, list[dict]], exclude_ids: set[str], limit: int = MAX_KEYWORD_MATCHES
) -> list[dict]:
    merged: dict[str, dict] = {}
    for keyword, hits in keyword_hits.items():
        for hit in hits:
            story = parse_hit(hit)
            if story["id"] in exclude_ids:
                continue
            entry = merged.setdefault(story["id"], {**story, "matched_keywords": []})
            if keyword not in entry["matched_keywords"]:
                entry["matched_keywords"].append(keyword)
    return by_points(merged.values())[:limit]


def html_to_text(html: str) -> str:
    text = re.sub(r"<p>", "\n\n", html or "")
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def parse_comment(item: dict | None, max_chars: int = MAX_COMMENT_CHARS) -> dict | None:
    if not item or item.get("deleted") or item.get("dead") or item.get("type") != "comment":
        return None
    text = html_to_text(item.get("text", ""))
    if not text:
        return None
    return {"author": item.get("by", ""), "text": text[:max_chars]}


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def fetch_comments(story_id: str) -> list[dict]:
    """First MAX_COMMENTS live top-level comments, in HN's ranked order (`kids`)."""
    story = http_get_json(FIREBASE_ITEM_URL.format(id=story_id)) or {}
    comments = []
    for kid in story.get("kids", []):
        if len(comments) >= MAX_COMMENTS:
            break
        comment = parse_comment(http_get_json(FIREBASE_ITEM_URL.format(id=kid)))
        if comment:
            comments.append(comment)
    return comments


def attach_comments(stories: list[dict]) -> None:
    def work(story: dict) -> None:
        try:
            story["comments"] = fetch_comments(story["id"])
        except Exception as e:  # noqa: BLE001 - one story's failure must not stop the rest
            story["comments"] = []
            story["error"] = str(e)

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(work, stories))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def default_config_path() -> str:
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(skill_dir, "keywords.json")


def write_output(data: dict, out: str | None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"Wrote {out}", file=sys.stderr)
    else:
        print(text)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", default=default_config_path())
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)
    min_points = config.get("min_points", DEFAULT_MIN_POINTS)

    now = int(time.time())
    since_ts = now - WINDOW_SECONDS
    errors = []

    print("Fetching top stories...", file=sys.stderr)
    top = select_top(http_get_json(search_url(since_ts))["hits"])

    keyword_hits = {}
    for keyword in config.get("keywords", []):
        print(f"Searching '{keyword}'...", file=sys.stderr)
        try:
            keyword_hits[keyword] = http_get_json(search_url(since_ts, keyword, min_points))["hits"]
        except Exception as e:  # noqa: BLE001
            errors.append({"keyword": keyword, "error": str(e)})
    matches = merge_keyword_hits(keyword_hits, {s["id"] for s in top})

    print(f"Fetching comments for {len(top) + len(matches)} stories...", file=sys.stderr)
    attach_comments(top + matches)

    write_output(
        {
            "generated_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "since": datetime.fromtimestamp(since_ts, timezone.utc).isoformat(),
            "top": top,
            "keyword_matches": matches,
            "errors": errors,
        },
        args.out,
    )
    print(f"Done: {len(top)} top, {len(matches)} keyword matches, {len(errors)} errors", file=sys.stderr)


if __name__ == "__main__":
    main()
