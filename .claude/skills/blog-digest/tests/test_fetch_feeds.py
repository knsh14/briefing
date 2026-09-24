import os
import time
from datetime import date

import feedparser
import pytest

from fetch_feeds import (
    MAX_ERROR_CHARS,
    choose_body,
    compute_since,
    dates_in_dir,
    error_text,
    format_feed,
    html_to_text,
    select_entries,
    slugify,
)

RSS = """<?xml version="1.0"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel><title>Blog</title>
<item><title>New  post</title><link>https://b.example/new</link>
<pubDate>Tue, 22 Sep 2026 10:00:00 +0000</pubDate>
<description>&lt;p&gt;Short summary&lt;/p&gt;</description>
<content:encoded>&lt;p&gt;Full &lt;b&gt;body&lt;/b&gt;&lt;/p&gt;&lt;p&gt;Second&lt;/p&gt;</content:encoded></item>
<item><title>Newer post</title><link>https://b.example/newer</link>
<pubDate>Wed, 23 Sep 2026 10:00:00 +0000</pubDate>
<description>Only summary</description></item>
<item><title>Old post</title><link>https://b.example/old</link>
<pubDate>Mon, 14 Sep 2026 10:00:00 +0000</pubDate></item>
<item><title>No date</title><link>https://b.example/nodate</link></item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>A</title>
<entry><title>Atom post</title><link href="https://a.example/p"/>
<updated>2026-09-21T09:00:00Z</updated><author><name>Ann</name></author>
<content type="html">&lt;p&gt;Hello&lt;/p&gt;</content></entry>
</feed>"""


def test_compute_since_defaults_to_seven_days_back():
    assert compute_since([], date(2026, 9, 24)) == date(2026, 9, 17)


def test_compute_since_uses_latest_prior_file_and_ignores_today():
    dates = [date(2026, 9, 20), date(2026, 9, 22), date(2026, 9, 24)]
    assert compute_since(dates, date(2026, 9, 24)) == date(2026, 9, 22)


def test_compute_since_caps_lookback_at_seven_days():
    assert compute_since([date(2026, 8, 1)], date(2026, 9, 24)) == date(2026, 9, 17)


def test_dates_in_dir_reads_only_date_files(tmp_path):
    (tmp_path / "2026-09-22.md").write_text("x")
    (tmp_path / "notes.md").write_text("x")
    assert dates_in_dir(str(tmp_path)) == [date(2026, 9, 22)]
    assert dates_in_dir(str(tmp_path / "missing")) == []
    assert dates_in_dir(None) == []


def test_html_to_text_keeps_paragraph_breaks():
    assert html_to_text("<p>Full <b>body</b></p><p>Second&amp;more</p>") == "Full body\nSecond&more"


def test_select_entries_filters_by_since_sorts_newest_first_and_limits():
    items = select_entries(feedparser.parse(RSS).entries, date(2026, 9, 17), max_items=5)
    assert [i["title"] for i in items] == ["Newer post", "New post"]
    assert items[1]["feed_text"] == "Full body\nSecond"
    assert items[0]["feed_text"] == ""
    assert items[0]["summary"] == "Only summary"
    assert items[0]["published"] == "2026-09-23T10:00:00+00:00"
    assert len(select_entries(feedparser.parse(RSS).entries, date(2026, 9, 17), max_items=1)) == 1


@pytest.fixture
def tokyo_tz():
    """Run the test with the local time zone set to Asia/Tokyo (UTC+9), whatever the machine's is."""
    old = os.environ.get("TZ")
    os.environ["TZ"] = "Asia/Tokyo"
    time.tzset()
    yield
    if old is None:
        del os.environ["TZ"]
    else:
        os.environ["TZ"] = old
    time.tzset()


def test_select_entries_period_starts_at_local_midnight(tokyo_tz):
    rss = """<?xml version="1.0"?><rss version="2.0"><channel><title>B</title>
<item><title>After local midnight</title><link>https://b.example/a</link>
<pubDate>Wed, 23 Sep 2026 15:30:00 +0000</pubDate></item>
<item><title>Before local midnight</title><link>https://b.example/b</link>
<pubDate>Wed, 23 Sep 2026 14:30:00 +0000</pubDate></item>
</channel></rss>"""
    # 2026-09-24 00:30 JST is included; 2026-09-23 23:30 JST is not.
    items = select_entries(feedparser.parse(rss).entries, date(2026, 9, 24), max_items=5)
    assert [i["title"] for i in items] == ["After local midnight"]


def test_select_entries_reads_atom_updated_and_author():
    items = select_entries(feedparser.parse(ATOM).entries, date(2026, 9, 17), max_items=5)
    assert items == [
        {
            "title": "Atom post",
            "link": "https://a.example/p",
            "published": "2026-09-21T09:00:00+00:00",
            "author": "Ann",
            "feed_text": "Hello",
            "summary": "Hello",
        }
    ]


def test_choose_body_prefers_long_feed_text_without_fetching():
    def boom():
        raise AssertionError("page must not be fetched")

    assert choose_body("x" * 1500, "s", boom) == ("x" * 1500, "feed")


def test_choose_body_uses_page_when_feed_is_short():
    assert choose_body("short", "s", lambda: "page text") == ("page text", "page")


def test_choose_body_falls_back_to_feed_then_summary():
    assert choose_body("short", "s", lambda: None) == ("short", "feed")
    assert choose_body("", "summary", lambda: None) == ("summary", "summary")


def test_choose_body_truncates_to_max():
    body, _ = choose_body("", "", lambda: "y" * 9000)
    assert len(body) == 8000


def test_error_text_truncates():
    assert error_text(ValueError("short")) == "short"
    assert error_text(ValueError("x" * 600)) == "x" * MAX_ERROR_CHARS
    assert len(error_text(ValueError("x" * 600))) == MAX_ERROR_CHARS


def test_slugify():
    assert slugify("Kent Beck (Tidy First?)") == "kent-beck-tidy-first"
    assert slugify("企業") == "feed"


def test_format_feed_wraps_long_lines():
    text = format_feed(
        "Blog",
        "https://b.example/feed",
        [
            {
                "title": "T",
                "link": "https://b.example/t",
                "published": "2026-09-23T10:00:00+00:00",
                "author": "",
                "body_source": "page",
                "body": "word " * 200 + "\n" + "長" * 450,
            }
        ],
    )
    assert text.startswith("# Blog\nFeed: https://b.example/feed\n")
    assert "## 1. T\nLink: https://b.example/t\n" in text
    assert "Body-Source: page\n" in text
    assert max(len(line) for line in text.splitlines()) <= 200


def test_main_uses_local_date_for_period(tmp_path, monkeypatch):
    import json
    import fetch_feeds

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2030, 1, 10)

    monkeypatch.setattr(fetch_feeds, "date", FakeDate)
    seen = {}

    def fake_process_feed(index, feed, since, max_items, out_dir):
        seen["since"] = since
        return {"name": feed["name"], "url": feed["url"], "file": "01-x.txt", "count": 0}

    monkeypatch.setattr(fetch_feeds, "process_feed", fake_process_feed)
    state = tmp_path / "blogs"
    state.mkdir()
    (state / "2030-01-08.md").write_text("x")
    (state / "2030-01-10.md").write_text("x")  # today's own file is ignored
    config = tmp_path / "feeds.json"
    config.write_text(json.dumps({"feeds": [{"name": "A", "url": "https://a.example/feed"}]}))
    out = tmp_path / "out"
    fetch_feeds.main(["--config", str(config), "--out-dir", str(out), "--state-dir", str(state)])
    assert seen["since"] == date(2030, 1, 8)
    assert json.loads((out / "manifest.json").read_text())["since"] == "2030-01-08"


def _write_config(tmp_path):
    import json

    config = tmp_path / "feeds.json"
    config.write_text(json.dumps({"feeds": [{"name": "A", "url": "https://a.example/feed"}]}))
    return config


def _stub_process_feed(monkeypatch):
    import fetch_feeds

    def fake_process_feed(index, feed, since, max_items, out_dir):
        return {"name": feed["name"], "url": feed["url"], "file": "01-a.txt", "count": 0}

    monkeypatch.setattr(fetch_feeds, "process_feed", fake_process_feed)


def test_main_refuses_to_clear_non_empty_out_dir_without_manifest(tmp_path, monkeypatch, capsys):
    import fetch_feeds

    _stub_process_feed(monkeypatch)
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_text("not ours")
    with pytest.raises(SystemExit) as exc:
        fetch_feeds.main(["--config", str(_write_config(tmp_path)), "--out-dir", str(out), "--since", "2030-01-01"])
    assert exc.value.code not in (0, None)
    assert "manifest.json" in capsys.readouterr().err
    assert (out / "keep.txt").read_text() == "not ours"
    assert not (out / "manifest.json").exists()


def test_main_clears_previous_output_dir_with_manifest(tmp_path, monkeypatch):
    import fetch_feeds

    _stub_process_feed(monkeypatch)
    out = tmp_path / "out"
    out.mkdir()
    (out / "manifest.json").write_text("{}")
    (out / "01-old.txt").write_text("stale")
    fetch_feeds.main(["--config", str(_write_config(tmp_path)), "--out-dir", str(out), "--since", "2030-01-01"])
    assert not (out / "01-old.txt").exists()
    assert (out / "manifest.json").exists()


def test_main_clears_leftovers_of_an_interrupted_run(tmp_path, monkeypatch):
    import fetch_feeds

    _stub_process_feed(monkeypatch)
    out = tmp_path / "out"
    out.mkdir()
    (out / "03-some-blog.txt").write_text("written before the run was killed")
    fetch_feeds.main(["--config", str(_write_config(tmp_path)), "--out-dir", str(out), "--since", "2030-01-01"])
    assert not (out / "03-some-blog.txt").exists()
    assert (out / "manifest.json").exists()
