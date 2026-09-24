#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Fetch Hugging Face Daily Papers for a UTC date (falls back one day if empty).

Usage:
    uv run fetch_hf_papers.py                                  # Today (UTC)
    uv run fetch_hf_papers.py --date 2026-09-23
    uv run fetch_hf_papers.py --out .cache/hf-papers-2026-09-24.json

Output: JSON to --out (or stdout). Progress and errors go to stderr.
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_URL = "https://huggingface.co/api/daily_papers?date={date}"
USER_AGENT = "briefing-digest/1.0 (+https://briefing.kamata.page/)"
MAX_ABSTRACT_CHARS = 1700
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds, doubled each retry
TIMEOUT = 30


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


def parse_papers(entries: list[dict]) -> list[dict]:
    papers = []
    for entry in entries:
        paper = entry.get("paper") or {}
        arxiv_id = paper.get("id")
        if not arxiv_id:
            continue
        abstract = " ".join((paper.get("summary") or entry.get("summary") or "").split())
        papers.append(
            {
                "arxiv_id": arxiv_id,
                "title": " ".join((entry.get("title") or paper.get("title") or "").split()),
                "abstract": abstract[:MAX_ABSTRACT_CHARS],
                "upvotes": paper.get("upvotes") or 0,
                "num_comments": entry.get("numComments") or 0,
                "hf_url": f"https://huggingface.co/papers/{arxiv_id}",
                "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}",
                "github_url": paper.get("githubRepo") or None,
                "ai_summary": paper.get("ai_summary") or None,
            }
        )
    return sorted(papers, key=lambda p: p["upvotes"], reverse=True)


def fetch_with_fallback(fetch, day: date) -> tuple[str, list[dict], bool]:
    """fetch(date_str) -> raw entries. Returns (date_str, papers, fallback_used)."""
    papers = parse_papers(fetch(day.isoformat()))
    if papers:
        return day.isoformat(), papers, False
    previous = (day - timedelta(days=1)).isoformat()
    return previous, parse_papers(fetch(previous)), True


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
    parser.add_argument("--date", help="UTC date (YYYY-MM-DD). Defaults to today in UTC.")
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    requested = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()

    def fetch(day: str) -> list[dict]:
        print(f"Fetching daily papers for {day}...", file=sys.stderr)
        return http_get_json(API_URL.format(date=day)) or []

    day, papers, fallback = fetch_with_fallback(fetch, requested)
    write_output(
        {"requested_date": requested.isoformat(), "date": day, "fallback": fallback, "papers": papers},
        args.out,
    )
    print(f"Done: {len(papers)} papers for {day}{' (fallback)' if fallback else ''}", file=sys.stderr)


if __name__ == "__main__":
    main()
