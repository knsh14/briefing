import urllib.parse

from fetch_hackernews import (
    html_to_text,
    merge_keyword_hits,
    parse_comment,
    parse_hit,
    search_url,
    select_top,
)


def hit(story_id, points, title="t", url="https://example.com/a"):
    return {
        "objectID": str(story_id),
        "title": title,
        "url": url,
        "points": points,
        "num_comments": 3,
        "author": "alice",
        "created_at": "2026-09-23T17:06:16Z",
    }


def query_of(url):
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


def test_search_url_for_top_stories():
    q = query_of(search_url(100))
    assert q["tags"] == ["story"]
    assert q["numericFilters"] == ["created_at_i>100"]
    assert "query" not in q


def test_search_url_for_keyword_is_title_only_and_exact():
    q = query_of(search_url(100, "uv", 10))
    assert q["numericFilters"] == ["created_at_i>100,points>=10"]
    assert q["query"] == ["uv"]
    assert q["restrictSearchableAttributes"] == ["title"]
    assert q["typoTolerance"] == ["false"]


def test_parse_hit_uses_hn_url_for_text_posts_and_zero_points():
    story = parse_hit({"objectID": "1", "title": "Ask HN: x", "url": None, "points": None})
    assert story["url"] == "https://news.ycombinator.com/item?id=1"
    assert story["hn_url"] == "https://news.ycombinator.com/item?id=1"
    assert story["points"] == 0
    assert story["num_comments"] == 0


def test_select_top_sorts_by_points_dedupes_and_limits():
    top = select_top([hit(1, 5), hit(2, 50), hit(3, 20), hit(2, 50)], n=2)
    assert [s["id"] for s in top] == ["2", "3"]


def test_merge_keyword_hits_dedupes_records_keywords_and_excludes_top():
    merged = merge_keyword_hits(
        {"LLM": [hit(1, 30), hit(2, 15)], "Claude": [hit(2, 15), hit(3, 12)]},
        exclude_ids={"1"},
    )
    assert [s["id"] for s in merged] == ["2", "3"]
    assert merged[0]["matched_keywords"] == ["LLM", "Claude"]
    assert merged[1]["matched_keywords"] == ["Claude"]


def test_merge_keyword_hits_keeps_highest_points_up_to_limit():
    merged = merge_keyword_hits({"x": [hit(i, i) for i in range(1, 30)]}, exclude_ids=set(), limit=20)
    assert len(merged) == 20
    assert merged[0]["id"] == "29"
    assert merged[-1]["id"] == "10"


def test_html_to_text_unescapes_and_splits_paragraphs():
    assert html_to_text("It&#x27;s<p>second <i>para</i>") == "It's\n\nsecond para"


def test_parse_comment_skips_deleted_dead_and_non_comments():
    assert parse_comment(None) is None
    assert parse_comment({"type": "comment", "deleted": True}) is None
    assert parse_comment({"type": "comment", "dead": True, "text": "x"}) is None
    assert parse_comment({"type": "story", "text": "x"}) is None
    assert parse_comment({"type": "comment", "text": ""}) is None


def test_parse_comment_truncates():
    comment = parse_comment({"type": "comment", "by": "u", "text": "a" * 600}, max_chars=500)
    assert comment == {"author": "u", "text": "a" * 500}
