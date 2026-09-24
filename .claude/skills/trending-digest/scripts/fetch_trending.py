#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["beautifulsoup4>=4.12"]
# ///
"""Fetch today's GitHub Trending repositories (all languages) with README excerpts.

Usage:
    uv run fetch_trending.py
    uv run fetch_trending.py --out .cache/trending-2026-09-24.json

Output: JSON to --out (or stdout). Exits 1 if no repository could be parsed.
Requires an authenticated `gh` CLI for README excerpts (missing READMEs are left empty).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRENDING_URL = "https://github.com/trending?since=daily"
USER_AGENT = "Mozilla/5.0 (compatible; briefing-digest/1.0; +https://briefing.kamata.page/)"
MAX_REPOS = 25
MAX_README_CHARS = 1200
# Quotes, backslashes and newlines grow when JSON-escaped; keep the escaped value
# well under the Read tool's 2,000-character line limit.
MAX_README_JSON_CHARS = 1900
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds, doubled each retry
TIMEOUT = 30
WORKERS = 8


# ---------------------------------------------------------------------------
# HTTP / gh
# ---------------------------------------------------------------------------


def http_get_text(url: str) -> str:
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001 - any network error is retried
            last_error = e
            print(f"  retry {attempt + 1}/{MAX_RETRIES} {url}: {e}", file=sys.stderr)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF * 2**attempt)
    raise RuntimeError(f"GET {url} failed: {last_error}")


def fetch_readme(repo: str) -> str:
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/readme", "-H", "Accept: application/vnd.github.raw"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except Exception as e:  # noqa: BLE001
        print(f"  readme failed {repo}: {e}", file=sys.stderr)
        return ""
    if result.returncode != 0:
        print(f"  readme failed {repo}: {result.stderr.strip()}", file=sys.stderr)
        return ""
    return readme_excerpt(result.stdout)


def readme_excerpt(text: str) -> str:
    """Cut to MAX_README_CHARS, and shorter if the JSON-escaped value would exceed MAX_README_JSON_CHARS."""
    excerpt = text[:MAX_README_CHARS]
    escaped_len = 2  # the surrounding quotes
    for i, ch in enumerate(excerpt):
        escaped_len += len(json.dumps(ch, ensure_ascii=False)) - 2
        if escaped_len >= MAX_README_JSON_CHARS:
            return excerpt[:i]
    return excerpt


# ---------------------------------------------------------------------------
# Parsing (pure)
# ---------------------------------------------------------------------------


def parse_count(text: str | None) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def parse_trending(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    repos = []
    for row in soup.select("article.Box-row"):
        link = row.select_one("h2 a[href]")
        if not link:
            continue
        repo = link["href"].strip("/")
        description = row.select_one("p")
        language = row.select_one('[itemprop="programmingLanguage"]')
        stars = row.select_one('a[href$="/stargazers"]')
        forks = row.select_one('a[href$="/forks"]')
        today = row.find(string=re.compile(r"stars?\s+today"))
        repos.append(
            {
                "rank": len(repos) + 1,
                "repo": repo,
                "url": f"https://github.com/{repo}",
                "description": " ".join(description.get_text().split()) if description else "",
                "language": language.get_text(strip=True) if language else "",
                "stars": parse_count(stars.get_text() if stars else ""),
                "forks": parse_count(forks.get_text() if forks else ""),
                "stars_today": parse_count(today),
            }
        )
    return repos[:MAX_REPOS]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


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
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    print("Fetching GitHub Trending...", file=sys.stderr)
    repos = parse_trending(http_get_text(TRENDING_URL))
    if not repos:
        write_output({"error": "no repositories parsed; GitHub Trending HTML may have changed", "repos": []}, args.out)
        sys.exit(1)

    print(f"Fetching READMEs for {len(repos)} repos...", file=sys.stderr)
    with ThreadPoolExecutor(WORKERS) as pool:
        for repo, readme in zip(repos, pool.map(lambda r: fetch_readme(r["repo"]), repos)):
            repo["readme_excerpt"] = readme

    write_output({"since": "daily", "repos": repos}, args.out)
    print(f"Done: {len(repos)} repos", file=sys.stderr)


if __name__ == "__main__":
    main()
