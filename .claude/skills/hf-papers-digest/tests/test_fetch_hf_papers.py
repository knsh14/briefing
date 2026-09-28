import time
from datetime import date, datetime, timezone

import pytest

from fetch_hf_papers import compute_dates, fetch_with_fallback, merge_papers, parse_papers


def entry(arxiv_id, upvotes, github=None, summary="An  abstract\nwith  spaces."):
    return {
        "title": f"Paper {arxiv_id}",
        "numComments": 2,
        "paper": {
            "id": arxiv_id,
            "title": f"Paper {arxiv_id}",
            "summary": summary,
            "upvotes": upvotes,
            "githubRepo": github,
        },
    }


def test_parse_papers_maps_fields_and_sorts_by_upvotes():
    papers = parse_papers([entry("2609.1", 3), entry("2609.2", 115, github="https://github.com/a/b")])
    assert [p["arxiv_id"] for p in papers] == ["2609.2", "2609.1"]
    top = papers[0]
    assert top == {
        "arxiv_id": "2609.2",
        "title": "Paper 2609.2",
        "abstract": "An abstract with spaces.",
        "upvotes": 115,
        "num_comments": 2,
        "hf_url": "https://huggingface.co/papers/2609.2",
        "arxiv_url": "https://arxiv.org/abs/2609.2",
        "github_url": "https://github.com/a/b",
        "ai_summary": None,
    }


def test_parse_papers_truncates_abstract_and_skips_entries_without_id():
    papers = parse_papers([entry("2609.3", 1, summary="x" * 3000), {"paper": {}}])
    assert len(papers) == 1
    assert len(papers[0]["abstract"]) == 1700


def test_fetch_with_fallback_uses_requested_day_when_present():
    calls = []

    def fetch(day):
        calls.append(day)
        return [entry("2609.1", 1)]

    assert fetch_with_fallback(fetch, date(2026, 9, 24))[0] == "2026-09-24"
    assert calls == ["2026-09-24"]


def test_fetch_with_fallback_goes_back_one_day_when_empty():
    def fetch(day):
        return [] if day == "2026-09-24" else [entry("2609.1", 1)]

    day, papers, fallback = fetch_with_fallback(fetch, date(2026, 9, 24))
    assert (day, len(papers), fallback) == ("2026-09-23", 1, True)


@pytest.fixture
def jst(monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_compute_dates_defaults_to_today_utc(jst):
    assert compute_dates([], utc(2026, 9, 28, 1, 0)) == [date(2026, 9, 28)]


def test_compute_dates_runs_from_day_after_last_prior_commit_and_ignores_today(jst):
    # Now: 09-28 09:00 JST. Last digest committed 09-25 07:54 JST (09-24 22:54 UTC).
    now = utc(2026, 9, 28, 0, 0)
    times = [utc(2026, 9, 27, 23, 30), utc(2026, 9, 24, 22, 54)]
    assert compute_dates(times, now) == [date(2026, 9, 25), date(2026, 9, 26), date(2026, 9, 27), date(2026, 9, 28)]


def test_compute_dates_single_date_when_last_commit_is_on_the_same_utc_date(jst):
    # Committed 09-28 10:00 JST (01:00 UTC); now 09-29 07:00 JST (09-28 22:00 UTC).
    assert compute_dates([utc(2026, 9, 28, 1, 0)], utc(2026, 9, 28, 22, 0)) == [date(2026, 9, 28)]


def test_compute_dates_caps_lookback_at_seven_days(jst):
    got = compute_dates([utc(2026, 8, 1, 3, 0)], utc(2026, 9, 28, 3, 0))
    assert got == [date(2026, 9, d) for d in range(22, 29)]


def test_merge_papers_dedupes_by_id_keeps_top_upvotes_and_limits():
    day1 = parse_papers([entry("2609.1", 5), entry("2609.2", 1)])
    day2 = parse_papers([entry("2609.1", 9), entry("2609.3", 7)])
    merged = merge_papers([day1, day2], limit=2)
    assert [(p["arxiv_id"], p["upvotes"]) for p in merged] == [("2609.1", 9), ("2609.3", 7)]
