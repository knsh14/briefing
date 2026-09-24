from datetime import date

from fetch_hf_papers import fetch_with_fallback, parse_papers


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
