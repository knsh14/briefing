from fetch_trending import parse_count, parse_trending

ROW_FULL = """
<article class="Box-row">
  <div class="float-right d-flex"><a href="/login?return_to=%2Fanthropics%2Ffinancial-services">Star</a></div>
  <h2 class="h3 lh-condensed">
    <a href="/anthropics/financial-services" class="Link"><svg></svg>
      <span class="text-normal">anthropics /</span>
      financial-services</a>
  </h2>
  <p class="col-9 color-fg-muted my-1 tmp-pr-4">
    Agents for   financial services
  </p>
  <div class="f6 color-fg-muted mt-2">
    <span class="d-inline-block ml-0 mr-3"><span itemprop="programmingLanguage">Python</span></span>
    <a href="/anthropics/financial-services/stargazers" class="Link"><svg aria-label="star"></svg>
      37,048</a>
    <a href="/anthropics/financial-services/forks" class="Link"><svg aria-label="fork"></svg>
      5,388</a>
    <span class="d-inline-block float-sm-right"><svg></svg>
      664 stars today
    </span>
  </div>
</article>
"""

ROW_MINIMAL = """
<article class="Box-row">
  <h2 class="h3 lh-condensed"><a href="/someone/tool">someone / tool</a></h2>
  <div class="f6 color-fg-muted mt-2">
    <a href="/someone/tool/stargazers">12</a>
    <span class="d-inline-block float-sm-right">1 star today</span>
  </div>
</article>
"""


def test_parse_count():
    assert parse_count("\n  37,048") == 37048
    assert parse_count("664 stars today") == 664
    assert parse_count("") == 0
    assert parse_count(None) == 0


def test_parse_trending_full_row():
    repos = parse_trending(f"<html><body>{ROW_FULL}</body></html>")
    assert repos == [
        {
            "rank": 1,
            "repo": "anthropics/financial-services",
            "url": "https://github.com/anthropics/financial-services",
            "description": "Agents for financial services",
            "language": "Python",
            "stars": 37048,
            "forks": 5388,
            "stars_today": 664,
        }
    ]


def test_parse_trending_minimal_row_and_order():
    repos = parse_trending(f"<html><body>{ROW_FULL}{ROW_MINIMAL}</body></html>")
    assert [r["repo"] for r in repos] == ["anthropics/financial-services", "someone/tool"]
    minimal = repos[1]
    assert minimal["rank"] == 2
    assert (minimal["description"], minimal["language"], minimal["forks"], minimal["stars_today"]) == ("", "", 0, 1)


def test_parse_trending_empty_page():
    assert parse_trending("<html><body>nothing</body></html>") == []
