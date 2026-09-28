#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Fetch Hugging Face Daily Papers for the UTC dates since the previous digest.

Usage:
    uv run fetch_hf_papers.py                                  # Today (UTC)
    uv run fetch_hf_papers.py --date 2026-09-23
    uv run fetch_hf_papers.py --out .cache/hf-papers-2026-09-24.json --state-dir hf-papers

With --state-dir, the dates run from the day after the UTC date of the newest commit
on main that touched it and was made before today (local date, minus a 1-hour margin),
up to today in UTC, at most 7 days. Papers of those dates are merged by arxiv id and
the top MAX_PAPERS by upvotes are kept.
Otherwise (or when that range is a single date) only one date is fetched: --date or
today in UTC, falling back one day if it has no papers.

Output: JSON to --out (or stdout). Progress and errors go to stderr.
"""

import argparse
import json
import os
import subprocess
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
MAX_PAPERS = 50  # cap for a multi-date period
MAX_LOOKBACK_DAYS = 7
STATE_MARGIN = timedelta(hours=1)  # the digest is committed after fetching and summarizing


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
# Period
# ---------------------------------------------------------------------------


def commit_times(state_dir: str) -> list[datetime]:
    """Times of recent commits on main that touched state_dir; [] if git fails."""
    cmd = ["git", "log", "-n", "20", "--format=%ct", "main", "--", state_dir]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return [datetime.fromtimestamp(int(t), timezone.utc) for t in out.split()]


def compute_dates(times: list[datetime], now: datetime) -> list[date]:
    """UTC dates to fetch from state-dir commit times (see the module docstring)."""
    end = now.astimezone(timezone.utc).date()
    today = now.astimezone().date()
    prior = [t for t in times if t.astimezone().date() < today]
    if not prior:
        return [end]
    start = (max(prior) - STATE_MARGIN).astimezone(timezone.utc).date() + timedelta(days=1)
    start = max(start, end - timedelta(days=MAX_LOOKBACK_DAYS - 1))
    if start >= end:
        return [end]
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


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


def merge_papers(per_date: list[list[dict]], limit: int = MAX_PAPERS) -> list[dict]:
    """Merge papers of several dates, keeping one entry per arxiv id, top `limit` by upvotes."""
    merged: dict[str, dict] = {}
    for papers in per_date:
        for paper in papers:
            current = merged.get(paper["arxiv_id"])
            if current is None or paper["upvotes"] > current["upvotes"]:
                merged[paper["arxiv_id"]] = paper
    return sorted(merged.values(), key=lambda p: p["upvotes"], reverse=True)[:limit]


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
    parser.add_argument("--state-dir", help="digest output dir whose last commit on main starts the period")
    args = parser.parse_args(argv)

    def fetch(day: str) -> list[dict]:
        print(f"Fetching daily papers for {day}...", file=sys.stderr)
        return http_get_json(API_URL.format(date=day)) or []

    if args.date or not args.state_dir:
        dates = [date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()]
    else:
        dates = compute_dates(commit_times(args.state_dir), datetime.now(timezone.utc))

    if len(dates) == 1:
        day, papers, fallback = fetch_with_fallback(fetch, dates[0])
        fetched = [day]
    else:
        fetched = [d.isoformat() for d in dates]
        papers = merge_papers([parse_papers(fetch(d)) for d in fetched])
        fallback = False

    write_output(
        {
            "requested_date": dates[-1].isoformat(),
            "dates": fetched,
            "date": fetched[0] if len(fetched) == 1 else f"{fetched[0]}〜{fetched[-1]}",
            "fallback": fallback,
            "papers": papers,
        },
        args.out,
    )
    print(f"Done: {len(papers)} papers for {', '.join(fetched)}{' (fallback)' if fallback else ''}", file=sys.stderr)


if __name__ == "__main__":
    main()
