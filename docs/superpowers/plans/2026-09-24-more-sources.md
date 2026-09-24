# 情報源の追加 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** daily-digest に Hacker News、HF Daily Papers、個人ブログ、企業ブログ、GitHub Trending の5情報源を加え、サイトで閲覧できるようにする。

**Architecture:** 情報源ごとに `.claude/skills/<name>-digest/` を作り、取得は `uv run` で動く Python スクリプト、要約は SKILL.md の手順に沿って Claude が行う。スクリプトは `.cache/` に JSON（ブログはフィードごとのテキスト）を書き、SKILL は Read で読む。サイトは「種類」の一覧 `KINDS` を1か所に定義し、1つのテンプレートで全種類の詳細ページを出す。

**Tech Stack:** Python 3.11+（標準ライブラリ、feedparser、trafilatura、beautifulsoup4、pytest）、uv、gh CLI、Eleventy 3、Node.js の `node:test`。

**Spec:** `docs/superpowers/specs/2026-09-24-more-sources-design.md`

## Global Constraints

- スキル名と出力ディレクトリ: `hackernews-digest` → `hackernews/`、`hf-papers-digest` → `hf-papers/`、`blog-digest` → `blogs/`、`company-blog-digest` → `company-blogs/`、`trending-digest` → `trending/`。
- 既存スキル名（`arxiv-digest`、`github-digest`、`daily-digest`）と既存 URL（`/{date}/arxiv/`、`/{date}/github/`）は変えない。
- 新スクリプトは PEP 723 のインライン依存を持ち、`uv run <script>.py` で実行する（`uv run python ...` ではない）。
- HTTP は User-Agent 付き、タイムアウト30秒、最大3回リトライ（2秒から倍々のバックオフ）。
- スクリプトの結果は `--out <path>`（ブログは `--out-dir <dir>`）に書く。SKILL からは `.cache/` 配下を指定する。`.cache/` は git 管理外。
- JSON は `indent=2`、`ensure_ascii=False`。1つの文字列値が2,000字を超えないように切る（Read ツールが2,000字超の行を切り詰めるため）。
- 数値: HN 上位30件、キーワード一致は合計20件、コメントは1記事3件・各500字、既定 `min_points` 10。HF の abstract 1,700字。フィード本文は8,000字・200字折り返し・フィード内容を使う閾値1,500字・1フィード既定5件・遡り上限7日。Trending は最大25件・README 1,200字。
- すべての subagent は `model: "opus"` を指定する（既存の約束）。
- 要約文は日本語。タイトル、固有名詞、識別子は原語のまま。取得データにないことを外部知識で補わない。
- Python テストは `.claude/skills/<skill>/tests/` に置き、`uv run --with pytest ... pytest <dir> -q` で実行する。
- サイトの変更後は `cd site && npm test` が通ること。

### 共通ブロック A: 校正ステップ

新しい5つの SKILL.md の「文章校正」ステップには、次の本文をそのまま入れる。`{出力パス}` は各スキルの出力ファイルに置き換える。

```markdown
保存した `{出力パス}` を、次の2段階で校正・修正する。

1. **文章規範チェック（`japanese-tech-writing` スキル）**
   `Skill` ツールで `japanese-tech-writing` を呼び出し、対象ファイルを明示的に指定して、その文章規範に沿って推敲する。特に LLM が生成しがちな表現を重点的に直す。
   - ダッシュ（`—` `―` `——`）・中黒（・）の不使用
   - LLM っぽい空句（「重要なのは〜」「正面から」「多角的に」など）の排除
   - 冗長な言い換え・繰り返しの削除、一文一行の整形
   - ねじれ文・助詞の誤用の修正

2. **機械チェック（`textlint-proofreader` スキル）**
   `Skill` ツールで `textlint-proofreader` を呼び出し、同じファイルを指定して表記揺れ等を機械的に検出・修正する。

自動修正可能な指摘は適用し、残った手動対応分は完了報告に含める。

> タイトル、技術用語、識別子は原語のまま残す。校正対象は日本語の地の文に限る。
```

---

### Task 1: サイトを「種類」一覧で汎用化する

**Files:**
- Modify: `site/lib/load.js`
- Modify: `site/src/_data/digests.js`
- Create: `site/src/kind.njk`
- Delete: `site/src/arxiv.njk`, `site/src/github.njk`
- Modify: `site/src/_includes/daynav.njk`
- Modify: `site/src/index.njk`
- Modify: `site/src/feed.njk`（subtitle のみ）
- Modify: `site/src/style.css:80,91`
- Modify: `site/eleventy.config.js`
- Modify: `site/scripts/check-build.mjs`
- Test: `site/test/load.test.js`

**Interfaces:**
- Produces: `KINDS: {key: string, label: string}[]`、`SERIES: string[]`（`"daily"` と KINDS の key）、`readSeries(dir)`（存在しない dir は `[]`）、`buildDays(series, render)`（各 day は SERIES の全キーを持ち、無い種類は `null`）、`buildPages(days): {day, kind}[]`。`digests` データは `{days, kinds, pages, latest, feed}`。

- [ ] **Step 1: 失敗するテストを書く**

`site/test/load.test.js` を次の内容に置き換える。

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DATE_RE, KINDS, SERIES, readSeries, buildDays, buildPages } from "../lib/load.js";

const upper = (s) => s.toUpperCase();
const empty = Object.fromEntries(SERIES.map((k) => [k, null]));

test("DATE_RE matches only YYYY-MM-DD.md", () => {
  assert.ok(DATE_RE.test("2026-08-11.md"));
  assert.equal(DATE_RE.exec("2026-08-11.md")[1], "2026-08-11");
  assert.ok(!DATE_RE.test("SKILL.md"));
  assert.ok(!DATE_RE.test("2026-08-11.txt"));
  assert.ok(!DATE_RE.test("icons"));
});

test("KINDS keeps existing kinds and adds the new sources in nav order", () => {
  assert.deepEqual(KINDS.map((k) => k.key), [
    "arxiv", "hf-papers", "hackernews", "github", "trending", "blogs", "company-blogs",
  ]);
  assert.deepEqual(SERIES, ["daily", ...KINDS.map((k) => k.key)]);
});

test("readSeries returns only date files with their text", (t) => {
  const dir = mkdtempSync(join(tmpdir(), "briefing-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  writeFileSync(join(dir, "2026-08-11.md"), "# a");
  writeFileSync(join(dir, "2026-08-10.md"), "# b");
  writeFileSync(join(dir, "SKILL.md"), "skip");
  mkdirSync(join(dir, "icons"));
  const out = readSeries(dir).sort((x, y) => x.date.localeCompare(y.date));
  assert.deepEqual(out, [
    { date: "2026-08-10", text: "# b" },
    { date: "2026-08-11", text: "# a" },
  ]);
});

test("readSeries returns [] for a missing directory", () => {
  assert.deepEqual(readSeries(join(tmpdir(), "briefing-does-not-exist-xyz")), []);
});

test("buildDays groups by date, newest first, with prev/next", () => {
  const days = buildDays(
    {
      daily: [{ date: "2026-08-11", text: "d11" }],
      arxiv: [{ date: "2026-08-11", text: "a11" }, { date: "2026-08-10", text: "a10" }],
      github: [{ date: "2026-08-09", text: "g09" }],
      hackernews: [{ date: "2026-08-10", text: "h10" }],
    },
    upper,
  );
  assert.deepEqual(days.map((d) => d.date), ["2026-08-11", "2026-08-10", "2026-08-09"]);
  assert.deepEqual(days[0], {
    ...empty,
    date: "2026-08-11",
    daily: { html: "D11" },
    arxiv: { html: "A11" },
    prev: "2026-08-10",
    next: null,
  });
  assert.deepEqual(days[1], {
    ...empty,
    date: "2026-08-10",
    arxiv: { html: "A10" },
    hackernews: { html: "H10" },
    prev: "2026-08-09",
    next: "2026-08-11",
  });
  assert.equal(days[2].prev, null);
  assert.equal(days[2].next, "2026-08-10");
});

test("buildDays returns [] when every series is empty", () => {
  assert.deepEqual(buildDays({ daily: [], arxiv: [], github: [] }, upper), []);
});

test("buildPages yields one page per existing (day, kind) in KINDS order", () => {
  const days = buildDays(
    {
      daily: [{ date: "2026-08-11", text: "d" }],
      github: [{ date: "2026-08-11", text: "g" }],
      "hf-papers": [{ date: "2026-08-11", text: "h" }],
      blogs: [{ date: "2026-08-10", text: "b" }],
    },
    upper,
  );
  const pages = buildPages(days).map((p) => `${p.day.date}/${p.kind.key}`);
  assert.deepEqual(pages, ["2026-08-11/hf-papers", "2026-08-11/github", "2026-08-10/blogs"]);
});
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `cd site && node --test`
Expected: FAIL（`KINDS` / `SERIES` / `buildPages` が export されていない）

- [ ] **Step 3: `site/lib/load.js` を実装する**

```js
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

export const DATE_RE = /^(\d{4}-\d{2}-\d{2})\.md$/;

// 詳細ページの種類。並び順がナビゲーションとトップページの表示順になる。
export const KINDS = [
  { key: "arxiv", label: "arXiv" },
  { key: "hf-papers", label: "HF Papers" },
  { key: "hackernews", label: "HN" },
  { key: "github", label: "GitHub" },
  { key: "trending", label: "Trending" },
  { key: "blogs", label: "Blogs" },
  { key: "company-blogs", label: "企業ブログ" },
];

// リポジトリ直下のディレクトリ名と一致する。
export const SERIES = ["daily", ...KINDS.map((k) => k.key)];

export function readSeries(dir) {
  if (!existsSync(dir)) return [];
  const out = [];
  for (const name of readdirSync(dir)) {
    const m = DATE_RE.exec(name);
    if (!m) continue;
    out.push({ date: m[1], text: readFileSync(join(dir, name), "utf8") });
  }
  return out;
}

export function buildDays(series, render) {
  const byDate = new Map();
  for (const key of SERIES) {
    for (const { date, text } of series[key] ?? []) {
      if (!byDate.has(date)) {
        byDate.set(date, { date, ...Object.fromEntries(SERIES.map((k) => [k, null])) });
      }
      byDate.get(date)[key] = { html: render(text) };
    }
  }
  const days = [...byDate.values()].sort((a, b) => b.date.localeCompare(a.date));
  days.forEach((day, i) => {
    day.next = i > 0 ? days[i - 1].date : null;
    day.prev = i < days.length - 1 ? days[i + 1].date : null;
  });
  return days;
}

export function buildPages(days) {
  return days.flatMap((day) =>
    KINDS.filter((kind) => day[kind.key]).map((kind) => ({ day, kind })),
  );
}
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `cd site && node --test`
Expected: PASS（全テスト）

- [ ] **Step 5: データとテンプレートを差し替える**

`site/src/_data/digests.js`:

```js
// site/src/_data/digests.js
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { KINDS, SERIES, readSeries, buildDays, buildPages } from "../../lib/load.js";
import { renderMarkdown } from "../../lib/render.js";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");

export default function () {
  const days = buildDays(
    Object.fromEntries(SERIES.map((key) => [key, readSeries(resolve(repoRoot, key))])),
    renderMarkdown,
  );
  return {
    days,
    kinds: KINDS,
    pages: buildPages(days),
    latest: days[0]?.date ?? null,
    feed: days.filter((d) => d.daily).slice(0, 30),
  };
}
```

`site/src/kind.njk` を作る。

```njk
---
pagination:
  data: digests.pages
  size: 1
  alias: entry
permalink: "/{{ entry.day.date }}/{{ entry.kind.key }}/"
layout: base.njk
eleventyComputed:
  title: "{{ entry.day.date }} {{ entry.kind.label }} | briefing"
---
{% set day = entry.day %}
{% set current = entry.kind.key %}
{% include "daynav.njk" %}
<article class="digest">
  {{ day[entry.kind.key].html | safe }}
</article>
```

削除する。

```bash
git rm site/src/arxiv.njk site/src/github.njk
```

`site/src/_includes/daynav.njk`:

```njk
{# 期待する変数: day, current ("daily" または KINDS の key) #}
<nav class="daynav" aria-label="日付">
  <div class="daynav-dates">
    {% if day.prev %}<a href="/{{ day.prev }}/">← {{ day.prev }}</a>{% else %}<span></span>{% endif %}
    <strong>{{ day.date }}</strong>
    {% if day.next %}<a href="/{{ day.next }}/">{{ day.next }} →</a>{% else %}<span></span>{% endif %}
  </div>
  <div class="daynav-kinds">
    <a href="/{{ day.date }}/"{% if current == "daily" %} aria-current="page"{% endif %}>統合</a>
    {% for kind in digests.kinds %}
    {% if day[kind.key] %}<a href="/{{ day.date }}/{{ kind.key }}/"{% if current == kind.key %} aria-current="page"{% endif %}>{{ kind.label }}</a>{% endif %}
    {% endfor %}
  </div>
</nav>
```

`site/src/index.njk`:

```njk
---
permalink: "/"
layout: base.njk
title: "briefing"
---
<h1>briefing</h1>
<p>arXiv、HF Daily Papers、Hacker News、GitHub、GitHub Trending、技術ブログの日次ダイジェスト。</p>
<ul class="daylist">
{% for day in digests.days %}
  <li>
    <a class="daylist-date" href="/{{ day.date }}/">{{ day.date }}</a>
    <span class="daylist-kinds">
      {% if day.daily %}<a href="/{{ day.date }}/">統合</a>{% endif %}
      {% for kind in digests.kinds %}
      {% if day[kind.key] %}<a href="/{{ day.date }}/{{ kind.key }}/">{{ kind.label }}</a>{% endif %}
      {% endfor %}
    </span>
  </li>
{% endfor %}
</ul>
```

`site/src/feed.njk` の subtitle 行を置き換える。

```xml
  <subtitle>arXiv、HF Daily Papers、Hacker News、GitHub、GitHub Trending、技術ブログの日次ダイジェスト</subtitle>
```

`site/src/style.css` の80行目と91行目を置き換える。リンクが8個に増えても狭い画面で折り返すようにする。

```css
.daynav-kinds { display: flex; flex-wrap: wrap; gap: 0.25rem 0.75rem; }
.daynav-kinds a[aria-current="page"] { font-weight: 700; color: var(--fg); }
```

```css
.daylist-kinds { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 0.25rem 0.75rem; }
.daylist-kinds a { color: var(--muted); }
```

（元の `.daynav-kinds a { margin-left: 0.75rem; }` と `.daylist-kinds a { margin-left: 0.75rem; color: var(--muted); }` を消し、上の行に置き換える。`.daynav-kinds a[aria-current="page"]` の行は残す。）

`site/eleventy.config.js`:

```js
// site/eleventy.config.js
import { SERIES } from "./lib/load.js";

export default function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy({ "../github/icons": "icons" });
  eleventyConfig.addPassthroughCopy("src/style.css");

  for (const key of SERIES) eleventyConfig.addWatchTarget(`../${key}/`);
  eleventyConfig.addWatchTarget("./lib/");

  return {
    dir: {
      input: "src",
      output: "_site",
      includes: "_includes",
      data: "_data",
    },
    markdownTemplateEngine: false,
    htmlTemplateEngine: "njk",
  };
}
```

`site/scripts/check-build.mjs`:

```js
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { DATE_RE, KINDS, SERIES } from "../lib/load.js";

const site = resolve(import.meta.dirname, "../_site");
const repoRoot = resolve(import.meta.dirname, "../..");
const failures = [];
const must = (cond, msg) => { if (!cond) failures.push(msg); };

const datesIn = (dir) => {
  const path = resolve(repoRoot, dir);
  if (!existsSync(path)) return [];
  return readdirSync(path).map((n) => DATE_RE.exec(n)?.[1]).filter(Boolean);
};
const newestDate = (dir) => datesIn(dir).sort().at(-1);

const latest = SERIES.map((dir) => newestDate(dir)).filter(Boolean).sort().at(-1);
must(latest, `${SERIES.map((s) => `${s}/`).join(", ")} のどれにも日付ファイルがない`);

const latestDaily = newestDate("daily");
must(latestDaily, "daily/ に日付ファイルがない");

for (const p of ["index.html", "404.html", "feed.xml", "_redirects", "style.css", "icons/git-pull-request.svg", "icons/issue-opened.svg", `${latest}/index.html`]) {
  must(existsSync(resolve(site, p)), `_site/${p} がない`);
}

if (existsSync(resolve(site, "_redirects"))) {
  const redirects = readFileSync(resolve(site, "_redirects"), "utf8");
  must(redirects.includes(`/latest   /${latest}/  302`), `_redirects に /latest → /${latest}/ がない`);
  must(redirects.includes(`/latest/  /${latest}/  302`), `_redirects に /latest/ → /${latest}/ がない`);
}

if (existsSync(resolve(site, "feed.xml"))) {
  const feed = readFileSync(resolve(site, "feed.xml"), "utf8");
  must(feed.includes(`<id>https://briefing.kamata.page/${latestDaily}/</id>`), "feed.xml に最新日のエントリがない");
}

for (const { key } of KINDS) {
  for (const date of datesIn(key)) {
    must(existsSync(resolve(site, date, key, "index.html")), `_site/${date}/${key}/index.html がない`);
  }
}

if (failures.length) {
  console.error(failures.map((f) => `✘ ${f}`).join("\n"));
  process.exit(1);
}
console.log(`✔ build ok (latest: ${latest}, latest daily: ${latestDaily})`);
```

- [ ] **Step 6: ビルドと既存ページが変わらないことを確認する**

Run: `cd site && npm test`
Expected: テスト PASS、ビルド成功、`✔ build ok ...`。

続けて、既存 URL が残っていることを確かめる。

Run: `ls site/_site/$(ls arxiv | grep -E '^[0-9]{4}' | sort | tail -1 | sed 's/\.md$//')/arxiv/index.html site/_site/$(ls github | grep -E '^[0-9]{4}' | sort | tail -1 | sed 's/\.md$//')/github/index.html`
Expected: 2ファイルとも存在する。

- [ ] **Step 7: 新しい種類のページが出ることを一時ファイルで確認する**

```bash
mkdir -p hackernews && printf '# HN テスト\n' > hackernews/2099-01-01.md
cd site && npm run build && ls _site/2099-01-01/hackernews/index.html && grep -o '/2099-01-01/hackernews/' _site/index.html | head -1
cd .. && rm -r hackernews && cd site && npm run build
```

Expected: `_site/2099-01-01/hackernews/index.html` が存在し、トップページに `/2099-01-01/hackernews/` へのリンクがある。最後の再ビルドで一時ファイルの影響が消える。

- [ ] **Step 8: Commit**

```bash
git add site
git commit -m "site: 詳細ページの種類を KINDS で一元化し、新しい情報源に備える"
```

---

### Task 2: hackernews-digest の取得スクリプト

**Files:**
- Create: `.claude/skills/hackernews-digest/scripts/fetch_hackernews.py`
- Create: `.claude/skills/hackernews-digest/keywords.json`
- Test: `.claude/skills/hackernews-digest/tests/conftest.py`
- Test: `.claude/skills/hackernews-digest/tests/test_fetch_hackernews.py`

**Interfaces:**
- Produces: CLI `uv run fetch_hackernews.py [keywords.json] [--out PATH]`。出力 JSON は `{generated_at, since, top: Story[], keyword_matches: Story[], errors: [{keyword, error}]}`。`Story = {id, title, url, hn_url, points, num_comments, author, created_at, comments: [{author, text}], matched_keywords?: string[], error?: string}`。

- [ ] **Step 1: テストの土台と失敗するテストを書く**

`.claude/skills/hackernews-digest/tests/conftest.py`:

```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
```

`.claude/skills/hackernews-digest/tests/test_fetch_hackernews.py`:

```python
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
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run --with pytest pytest .claude/skills/hackernews-digest/tests -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'fetch_hackernews'`）

- [ ] **Step 3: スクリプトを実装する**

`.claude/skills/hackernews-digest/scripts/fetch_hackernews.py`:

```python
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
```

`.claude/skills/hackernews-digest/keywords.json`:

```json
{
  "keywords": ["LLM", "Claude", "Anthropic", "openpilot", "comma.ai", "self-driving", "autonomous driving", "robotics", "Neovim", "Vim", "Ghostty", "terminal", "uv", "Python", "Rust", "QMK", "mechanical keyboard"],
  "min_points": 10
}
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run --with pytest pytest .claude/skills/hackernews-digest/tests -q`
Expected: PASS（9 passed）

- [ ] **Step 5: 実ネットワークで1回動かす**

Run: `uv run .claude/skills/hackernews-digest/scripts/fetch_hackernews.py --out .cache/hn-smoke.json && python3 -c "import json;d=json.load(open('.cache/hn-smoke.json'));print(len(d['top']),len(d['keyword_matches']),len(d['errors']));print(max(len(l) for l in open('.cache/hn-smoke.json')))"`
Expected: 1行目が `30 <0〜20> 0`。2行目（最長の行の長さ）が2000未満。

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/hackernews-digest
git commit -m "hackernews-digest: HN 上位記事とキーワード一致の取得スクリプトを追加"
```

---

### Task 3: hf-papers-digest の取得スクリプト

**Files:**
- Create: `.claude/skills/hf-papers-digest/scripts/fetch_hf_papers.py`
- Test: `.claude/skills/hf-papers-digest/tests/conftest.py`
- Test: `.claude/skills/hf-papers-digest/tests/test_fetch_hf_papers.py`

**Interfaces:**
- Produces: CLI `uv run fetch_hf_papers.py [--date YYYY-MM-DD] [--out PATH]`。出力 JSON は `{requested_date, date, fallback: bool, papers: Paper[]}`。`Paper = {arxiv_id, title, abstract, upvotes, num_comments, hf_url, arxiv_url, github_url|null, ai_summary|null}`。

- [ ] **Step 1: 失敗するテストを書く**

`.claude/skills/hf-papers-digest/tests/conftest.py`:

```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
```

`.claude/skills/hf-papers-digest/tests/test_fetch_hf_papers.py`:

```python
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
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run --with pytest pytest .claude/skills/hf-papers-digest/tests -q`
Expected: FAIL（`No module named 'fetch_hf_papers'`）

- [ ] **Step 3: スクリプトを実装する**

`.claude/skills/hf-papers-digest/scripts/fetch_hf_papers.py`:

```python
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
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run --with pytest pytest .claude/skills/hf-papers-digest/tests -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 実ネットワークで1回動かす**

Run: `uv run .claude/skills/hf-papers-digest/scripts/fetch_hf_papers.py --out .cache/hf-smoke.json && python3 -c "import json;d=json.load(open('.cache/hf-smoke.json'));print(d['date'],d['fallback'],len(d['papers']));print(max(len(l) for l in open('.cache/hf-smoke.json')))"`
Expected: 1行目が `<日付> <True|False> <1以上>`。2行目が2000未満。

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/hf-papers-digest
git commit -m "hf-papers-digest: HF Daily Papers の取得スクリプトを追加"
```

---

### Task 4: フィード取得スクリプトと feeds.json（blog-digest / company-blog-digest 共用）

**Files:**
- Create: `.claude/skills/blog-digest/scripts/fetch_feeds.py`
- Create: `.claude/skills/blog-digest/feeds.json`
- Create: `.claude/skills/company-blog-digest/feeds.json`
- Test: `.claude/skills/blog-digest/tests/conftest.py`
- Test: `.claude/skills/blog-digest/tests/test_fetch_feeds.py`

**Interfaces:**
- Produces: CLI `uv run fetch_feeds.py --config FEEDS.json --out-dir DIR [--state-dir DIR] [--since YYYY-MM-DD]`。`DIR/manifest.json` = `{since, feeds: [{name, url, file, count}], errors: [{name, url, error}]}`（`feeds` は記事1件以上のものだけ）。`DIR/NN-<slug>.txt` はフィードごとの記事本文（後述の形式）。

- [ ] **Step 1: 失敗するテストを書く**

`.claude/skills/blog-digest/tests/conftest.py`:

```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
```

`.claude/skills/blog-digest/tests/test_fetch_feeds.py`:

```python
from datetime import date

import feedparser

from fetch_feeds import (
    choose_body,
    compute_since,
    dates_in_dir,
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
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run --with pytest --with feedparser --with trafilatura pytest .claude/skills/blog-digest/tests -q`
Expected: FAIL（`No module named 'fetch_feeds'`）

- [ ] **Step 3: スクリプトを実装する**

`.claude/skills/blog-digest/scripts/fetch_feeds.py`:

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["feedparser>=6.0", "trafilatura>=1.12"]
# ///
"""Fetch recent posts from RSS/Atom feeds and write one text file per feed.

Usage:
    uv run fetch_feeds.py --config feeds.json --out-dir .cache/blogs-2026-09-24 --state-dir blogs
    uv run fetch_feeds.py --config feeds.json --out-dir DIR --since 2026-09-20

The period starts at 00:00 UTC of --since, or of the newest YYYY-MM-DD.md in
--state-dir dated before today, capped at 7 days back.

Output (in --out-dir, cleared first):
    manifest.json   {since, feeds: [{name, url, file, count}], errors: [{name, url, error}]}
    NN-<slug>.txt   Posts of one feed, wrapped to short lines for the Read tool.
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
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from html import unescape

import feedparser
import trafilatura


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = "Mozilla/5.0 (compatible; briefing-digest/1.0; +https://briefing.kamata.page/)"
DATE_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
MAX_LOOKBACK_DAYS = 7
DEFAULT_MAX_ITEMS = 5
MIN_FEED_BODY_CHARS = 1500
MAX_BODY_CHARS = 8000
WRAP_WIDTH = 200
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds, doubled each retry
TIMEOUT = 30
WORKERS = 8


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


def select_entries(entries, since: date, max_items: int) -> list[dict]:
    since_dt = datetime.combine(since, dtime.min, tzinfo=timezone.utc)
    picked = []
    for entry in entries:
        published = entry_datetime(entry)
        if published is None or published < since_dt:
            continue
        contents = entry.get("content") or []
        picked.append(
            {
                "title": " ".join((entry.get("title") or "").split()),
                "link": entry.get("link") or "",
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


def process_feed(index: int, feed: dict, since: date, max_items: int, out_dir: str) -> dict:
    name, url = feed["name"], feed["url"]
    print(f"Fetching {name}...", file=sys.stderr)
    parsed = feedparser.parse(http_get_bytes(url))
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"unparseable feed: {parsed.get('bozo_exception')}")
    items = select_entries(parsed.entries, since, max_items)
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
    today = datetime.now(timezone.utc).date()
    since = date.fromisoformat(args.since) if args.since else compute_since(dates_in_dir(args.state_dir), today)

    shutil.rmtree(args.out_dir, ignore_errors=True)
    os.makedirs(args.out_dir)

    def work(pair):
        index, feed = pair
        try:
            return process_feed(index, feed, since, max_items, args.out_dir), None
        except Exception as e:  # noqa: BLE001 - one feed's failure must not stop the rest
            return None, {"name": feed["name"], "url": feed["url"], "error": str(e)}

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
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run --with pytest --with feedparser --with trafilatura pytest .claude/skills/blog-digest/tests -q`
Expected: PASS（13 passed）

- [ ] **Step 5: feeds.json を2つ作る**

`.claude/skills/blog-digest/feeds.json`:

```json
{
  "max_items_per_feed": 5,
  "feeds": [
    {"name": "Simon Willison", "url": "https://simonwillison.net/atom/everything/"},
    {"name": "The Pragmatic Engineer", "url": "https://newsletter.pragmaticengineer.com/feed"},
    {"name": "Import AI", "url": "https://importai.substack.com/feed"},
    {"name": "Latent Space", "url": "https://www.latent.space/feed"},
    {"name": "Ahead of AI", "url": "https://magazine.sebastianraschka.com/feed"},
    {"name": "Lilian Weng", "url": "https://lilianweng.github.io/index.xml"},
    {"name": "Mitchell Hashimoto", "url": "https://mitchellh.com/feed.xml"},
    {"name": "Julia Evans", "url": "https://jvns.ca/atom.xml"},
    {"name": "Will Larson", "url": "https://lethain.com/feeds/"},
    {"name": "Cal Newport", "url": "https://calnewport.com/feed/"},
    {"name": "Kent Beck (Tidy First?)", "url": "https://tidyfirst.substack.com/feed"},
    {"name": "Martin Fowler", "url": "https://martinfowler.com/feed.atom"},
    {"name": "Charity Majors", "url": "https://charity.wtf/feed/"},
    {"name": "Camille Fournier (Elided Branches)", "url": "https://www.elidedbranches.com/feeds/posts/default"},
    {"name": "Paul Graham", "url": "http://www.aaronsw.com/2002/feeds/pgessays.rss"},
    {"name": "Dan Luu", "url": "https://danluu.com/atom.xml"},
    {"name": "Addy Osmani", "url": "https://addyo.substack.com/feed"},
    {"name": "Eugene Yan", "url": "https://eugeneyan.com/rss/"},
    {"name": "Hamel Husain", "url": "https://hamel.dev/index.xml"}
  ]
}
```

`.claude/skills/company-blog-digest/feeds.json`:

```json
{
  "max_items_per_feed": 5,
  "feeds": [
    {"name": "OpenAI", "url": "https://openai.com/news/rss.xml"},
    {"name": "Google DeepMind", "url": "https://deepmind.google/blog/feed/basic/"},
    {"name": "Hugging Face", "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "comma.ai", "url": "https://blog.comma.ai/feed.xml"},
    {"name": "GitHub", "url": "https://github.blog/feed/"},
    {"name": "Cloudflare", "url": "https://blog.cloudflare.com/rss/"},
    {"name": "Astral", "url": "https://astral.sh/blog/rss.xml"},
    {"name": "Netflix TechBlog", "url": "https://netflixtechblog.com/feed"},
    {"name": "NVIDIA Technical Blog", "url": "https://developer.nvidia.com/blog/feed/"},
    {"name": "Waymo", "url": "https://waymo.com/blog/rss.xml"},
    {"name": "Wayve", "url": "https://wayve.ai/wp-content/themes/wayve/rss-feed.php"},
    {"name": "Meta Engineering", "url": "https://engineering.fb.com/feed/"},
    {"name": "Microsoft Research", "url": "https://www.microsoft.com/en-us/research/feed/"},
    {"name": "Stripe", "url": "https://stripe.com/blog/feed.rss"},
    {"name": "Airbnb", "url": "https://medium.com/feed/airbnb-engineering"},
    {"name": "Spotify", "url": "https://engineering.atspotify.com/feed/"},
    {"name": "Shopify", "url": "https://shopify.engineering/blog.atom"},
    {"name": "Dropbox", "url": "https://dropbox.tech/feed"},
    {"name": "Discord", "url": "https://discord.com/blog/rss.xml"},
    {"name": "Slack", "url": "https://slack.engineering/feed/"},
    {"name": "Pinterest", "url": "https://medium.com/feed/pinterest-engineering"},
    {"name": "Figma", "url": "https://www.figma.com/blog/feed/atom.xml"},
    {"name": "Vercel", "url": "https://vercel.com/atom"},
    {"name": "Datadog", "url": "https://www.datadoghq.com/blog/index.xml"}
  ]
}
```

- [ ] **Step 6: 実ネットワークで両方を1回動かす**

Run:

```bash
uv run .claude/skills/blog-digest/scripts/fetch_feeds.py --config .claude/skills/blog-digest/feeds.json --out-dir .cache/blogs-smoke --since $(date -u -v-3d +%F)
uv run .claude/skills/blog-digest/scripts/fetch_feeds.py --config .claude/skills/company-blog-digest/feeds.json --out-dir .cache/company-smoke --since $(date -u -v-3d +%F)
python3 -c "
import json,glob
for d in ['.cache/blogs-smoke','.cache/company-smoke']:
    m=json.load(open(d+'/manifest.json')); print(d, m['since'], [(f['name'],f['count']) for f in m['feeds']], m['errors'])
    print(' longest line:', max(len(l) for f in glob.glob(d+'/*') for l in open(f)))
"
```

Expected: 両方に `since` と、1件以上の記事を持つフィードが並ぶ。`errors` が空であること。空でなければ、そのフィードをブラウザや curl で確かめ、URL を直すか feeds.json から外してユーザーに報告する。最長行が2000未満。

- [ ] **Step 7: Commit**

```bash
git add .claude/skills/blog-digest .claude/skills/company-blog-digest
git commit -m "blog-digest: RSS/Atom フィードの取得スクリプトと個人・企業ブログのフィード一覧を追加"
```

---

### Task 5: trending-digest の取得スクリプト

**Files:**
- Create: `.claude/skills/trending-digest/scripts/fetch_trending.py`
- Test: `.claude/skills/trending-digest/tests/conftest.py`
- Test: `.claude/skills/trending-digest/tests/test_fetch_trending.py`

**Interfaces:**
- Produces: CLI `uv run fetch_trending.py [--out PATH]`。出力 JSON は `{since: "daily", repos: Repo[]}`、0件なら `{error, repos: []}` を書いて終了コード1。`Repo = {rank, repo, url, description, language, stars, forks, stars_today, readme_excerpt}`。

- [ ] **Step 1: 失敗するテストを書く**

`.claude/skills/trending-digest/tests/conftest.py`:

```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
```

`.claude/skills/trending-digest/tests/test_fetch_trending.py`:

```python
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
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run --with pytest --with beautifulsoup4 pytest .claude/skills/trending-digest/tests -q`
Expected: FAIL（`No module named 'fetch_trending'`）

- [ ] **Step 3: スクリプトを実装する**

`.claude/skills/trending-digest/scripts/fetch_trending.py`:

```python
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
    return result.stdout[:MAX_README_CHARS]


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
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run --with pytest --with beautifulsoup4 pytest .claude/skills/trending-digest/tests -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 実ネットワークで1回動かす**

Run: `uv run .claude/skills/trending-digest/scripts/fetch_trending.py --out .cache/trending-smoke.json && python3 -c "import json;d=json.load(open('.cache/trending-smoke.json'));r=d['repos'];print(len(r),sum(1 for x in r if x['readme_excerpt']),r[0]['repo'],r[0]['stars_today']);print(max(len(l) for l in open('.cache/trending-smoke.json')))"`
Expected: 1行目が `<10以上> <ほぼ同数> <owner/repo> <1以上>`。2行目が2000未満。

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/trending-digest
git commit -m "trending-digest: GitHub Trending の取得スクリプトを追加"
```

---

### Task 6: 5つの SKILL.md と権限設定

**Files:**
- Create: `.claude/skills/hackernews-digest/SKILL.md`
- Create: `.claude/skills/hf-papers-digest/SKILL.md`
- Create: `.claude/skills/blog-digest/SKILL.md`
- Create: `.claude/skills/company-blog-digest/SKILL.md`
- Create: `.claude/skills/trending-digest/SKILL.md`
- Modify: `.claude/settings.json`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: Task 2〜5 の CLI と出力形式。
- Produces: スキル名 `hackernews-digest`、`hf-papers-digest`、`blog-digest`、`company-blog-digest`、`trending-digest`。それぞれ `<dir>/YYYY-MM-DD.md` を書き、完了報告で件数を返す。

- [ ] **Step 1: `.gitignore` と `.claude/settings.json` を更新する**

`.gitignore` の末尾に追加する。

```
.cache/
```

`.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "Bash(uv run python */arxiv-digest/scripts/fetch_arxiv.py*)",
      "Bash(uv run python */github-digest/scripts/fetch_github.py*)",
      "Bash(uv run */hackernews-digest/scripts/fetch_hackernews.py*)",
      "Bash(uv run */hf-papers-digest/scripts/fetch_hf_papers.py*)",
      "Bash(uv run */blog-digest/scripts/fetch_feeds.py*)",
      "Bash(uv run */trending-digest/scripts/fetch_trending.py*)",
      "Bash(mkdir -p */arxiv)",
      "Bash(mkdir -p */github)",
      "Bash(mkdir -p */daily)",
      "Bash(npx textlint*)",
      "Bash(gh auth *)",
      "WebFetch(domain:export.arxiv.org)"
    ]
  }
}
```

- [ ] **Step 2: `hackernews-digest/SKILL.md` を書く**

````markdown
---
name: hackernews-digest
description: "Hacker News の直近24時間の上位記事と、関心キーワードに合う記事を取得し、日本語サマリーを Markdown に保存するスキル。「Hacker News」「HN」「ハッカーニュース」「HN ダイジェスト」などで発動する。"
allowed-tools:
  - "Bash(uv run */hackernews-digest/scripts/fetch_hackernews.py*)"
  - Read
  - Write
  - Edit
  - Skill
---

# Hacker News ダイジェスト

Hacker News の直近24時間の上位30件と、`keywords.json` のキーワードにタイトルが合う記事（最大20件）を取得し、日本語で要約して `hackernews/YYYY-MM-DD.md` に保存する。

## 設定ファイル

`<skill-dir>/keywords.json` にキーワードと最低ポイントを書く。

```json
{
  "keywords": ["LLM", "Neovim"],
  "min_points": 10
}
```

## ワークフロー

`YYYY-MM-DD` は今日の日付（ローカル時刻）とする。

### Step 1: データ取得

```bash
uv run <skill-dir>/scripts/fetch_hackernews.py --out .cache/hackernews-YYYY-MM-DD.json
```

- 上位記事の検索に失敗するとスクリプトは異常終了する。その場合は原因を報告して停止する。
- キーワード単位の失敗は `errors` に入る。

### Step 2: 読み込み

Read で `.cache/hackernews-YYYY-MM-DD.json` を読む。
1回で読み切れないときは `offset` と `limit` を使って分けて読む。

各記事は `title`、`url`、`hn_url`、`points`、`num_comments`、`comments`（HN の表示順で先頭の最大3件）を持つ。
`keyword_matches` の記事は、さらに `matched_keywords` を持つ。

### Step 3: サマリー生成・保存

要約の注意点:
- 記事本文は取得していない。「話題」はタイトル、URL、コメントから読み取れる範囲で書き、推測で補わない。
- コメントは日本語に要約する。原文をそのまま貼らない。
- `comments` が空なら「取得できたコメントなし」と書く。

ハイライトは上位記事とキーワード一致の両方から3〜5件選ぶ。選定基準:
- ポイントやコメント数が特に多い
- 技術的な発表（リリース、論文、ツール）で影響が大きい
- キーワード一致で、関心分野に直接関わる

```markdown
# Hacker News ダイジェスト — YYYY-MM-DD

## 本日のハイライト

1. **[{title}]({url})** ({points} points) — {選定理由(日本語)}
2. ...

---

## 上位記事

### [{title}]({url})
**{points} points** | **{num_comments} comments** | [HN スレッド]({hn_url})

**話題:** {何の話題か。1〜2文}

**HN での反応:** {コメントの要約。2〜3文}

---

## キーワード一致

### [{title}]({url})
**{points} points** | **{num_comments} comments** | **キーワード:** {matched_keywords をカンマ区切り} | [HN スレッド]({hn_url})

**話題:** {1〜2文}

**HN での反応:** {2〜3文}

---
```

キーワード一致が0件なら、その節に「該当する記事はありません」と書く。

保存先: `hackernews/YYYY-MM-DD.md`（同名ファイルがあれば上書き）

### Step 4: 文章校正

{共通ブロック A を `{出力パス}` = `hackernews/YYYY-MM-DD.md` で展開した本文}

### Step 5: 完了報告

- 保存したファイルパス
- 上位記事数とキーワード一致数
- `errors` に入ったキーワードがあればその旨
- 校正結果（規範修正件数、textlint の自動修正件数 / 手動対応が必要な件数）

## エラーハンドリング

- スクリプトが異常終了した場合は、標準エラーの内容を報告して停止する。
- コメント取得に失敗した記事（`error` フィールドあり）は、コメントなしとして扱う。
````

（`{共通ブロック A ...}` の行は、実際のファイルでは Global Constraints の「共通ブロック A」の本文に置き換える。以下の SKILL.md も同じ。）

- [ ] **Step 3: `hf-papers-digest/SKILL.md` を書く**

````markdown
---
name: hf-papers-digest
description: "Hugging Face Daily Papers（人が選んだ注目の arxiv 論文）を取得し、日本語サマリーを Markdown に保存するスキル。「HF Papers」「Daily Papers」「Hugging Face 論文」「注目論文」などで発動する。"
allowed-tools:
  - "Bash(uv run */hf-papers-digest/scripts/fetch_hf_papers.py*)"
  - Read
  - Write
  - Edit
  - Skill
---

# HF Daily Papers ダイジェスト

Hugging Face Daily Papers の掲載論文を upvote 順に取得し、日本語で要約して `hf-papers/YYYY-MM-DD.md` に保存する。

## ワークフロー

`YYYY-MM-DD` は今日の日付（ローカル時刻）とする。

### Step 1: データ取得

```bash
uv run <skill-dir>/scripts/fetch_hf_papers.py --out .cache/hf-papers-YYYY-MM-DD.json
```

対象日は UTC の今日で、掲載が0件なら UTC の前日分を取る。

### Step 2: 読み込み

Read で `.cache/hf-papers-YYYY-MM-DD.json` を読む。
`date` が実際の対象日、`fallback` が前日分に切り替えたかどうかを表す。
`papers` が空なら、Step 3 で「掲載された論文はありません」とだけ書く。

### Step 3: サマリー生成・保存

要約の注意点:
- `abstract` の内容に忠実に書く。`ai_summary` があれば参考にしてよい。
- 日本語タイトルは原題を訳したものにする。

ハイライトは3〜5件。選定基準:
- upvote が特に多い
- 実装（`github_url`）が公開されている
- 手法や結果が大きく新しい

```markdown
# HF Daily Papers — YYYY-MM-DD

> 対象日: {date}

## 本日のハイライト

1. **[{日本語タイトル}]({hf_url})** ({upvotes} upvotes) — {選定理由(日本語)}
2. ...

---

## 論文一覧

### [{日本語タイトル}]({hf_url})
**原題:** {title} | **upvotes:** {upvotes} | [arXiv]({arxiv_url}) | [GitHub]({github_url})

{要約。2〜3文}

---
```

- `github_url` が null なら `| [GitHub](...)` を省く。
- `fallback` が true なら、対象日の行を「対象日: {date}（{requested_date} の掲載がまだないため前日分）」にする。

保存先: `hf-papers/YYYY-MM-DD.md`（同名ファイルがあれば上書き）

### Step 4: 文章校正

{共通ブロック A を `{出力パス}` = `hf-papers/YYYY-MM-DD.md` で展開した本文}

### Step 5: 完了報告

- 保存したファイルパス
- 対象日と論文数（フォールバックしたかどうか）
- 校正結果

## エラーハンドリング

- スクリプトが異常終了した場合は、標準エラーの内容を報告して停止する。
````

- [ ] **Step 4: `blog-digest/SKILL.md` を書く**

````markdown
---
name: blog-digest
description: "登録した個人ブログ・ニュースレターの新着記事を RSS/Atom で取得し、本文を日本語で要約して Markdown に保存するスキル。「ブログダイジェスト」「個人ブログ」「ニュースレター」「blog digest」などで発動する。"
allowed-tools:
  - "Bash(uv run */blog-digest/scripts/fetch_feeds.py*)"
  - Read
  - Write
  - Edit
  - Skill
---

# ブログダイジェスト

`feeds.json` に登録した個人ブログの新着記事を取得し、本文を日本語で要約して `blogs/YYYY-MM-DD.md` に保存する。

## 設定ファイル

`<skill-dir>/feeds.json` にフィードを書く。追加・削除はこのファイルの編集だけでよい。

```json
{
  "max_items_per_feed": 5,
  "feeds": [
    {"name": "Simon Willison", "url": "https://simonwillison.net/atom/everything/"}
  ]
}
```

## ワークフロー

`YYYY-MM-DD` は今日の日付（ローカル時刻）とする。

### Step 1: データ取得

```bash
uv run <skill-dir>/scripts/fetch_feeds.py --config <skill-dir>/feeds.json --out-dir .cache/blogs-YYYY-MM-DD --state-dir blogs
```

対象期間は、`blogs/` にある今日より前の最新ファイルの日付以降（最大7日前まで）。

### Step 2: 読み込み

1. Read で `.cache/blogs-YYYY-MM-DD/manifest.json` を読む。`since` が対象期間の開始日、`feeds` が記事のあるフィード、`errors` が取得に失敗したフィード。
2. `feeds` の順に、`file` に書かれたファイルを1つずつ Read して要約する。読み終えたフィードの要約を書き出してから次に進む。

各記事には `Body-Source` がある。`summary` の記事は本文を取れずフィードの概要しかないので、要約の末尾に「（概要のみ）」と付ける。

### Step 3: サマリー生成・保存

要約の注意点:
- 本文に書かれていることだけで要約する。
- 「読む価値」は、どんな読者に何が得られるかを1文で書く。

ハイライトは3〜5件（記事がそれより少なければ全件）。選定基準:
- 独自の知見やデータがある
- 関心分野（AI/ML、開発ツール、エンジニアリング組織、生産性）に直接関わる
- 議論を呼びそうな主張がある

```markdown
# ブログダイジェスト — YYYY-MM-DD

> 対象期間: {since} 以降

## 本日のハイライト

1. **[{title}]({link})** ({フィード名}) — {選定理由(日本語)}
2. ...

---

## {フィード名}

### [{title}]({link})
**公開:** {published の日付部分} | **著者:** {author。空なら省く}

{要約。3〜5文}

**読む価値:** {1文}

---

## 取得に失敗したフィード

- {name}: {error}
```

- 記事が0件のフィードは節を作らない。
- `feeds` が空なら、ハイライトと本文の代わりに「対象期間に新着記事はありません」と書く。
- `errors` が空なら「取得に失敗したフィード」の節を省く。

保存先: `blogs/YYYY-MM-DD.md`（同名ファイルがあれば上書き）

### Step 4: 文章校正

{共通ブロック A を `{出力パス}` = `blogs/YYYY-MM-DD.md` で展開した本文}

### Step 5: 完了報告

- 保存したファイルパス
- 対象期間、フィードごとの記事数
- 取得に失敗したフィード
- 校正結果

## エラーハンドリング

- スクリプトが異常終了した場合（設定ファイルが読めないなど）は、標準エラーの内容を報告して停止する。
- フィード単位の失敗は `errors` に入るだけなので、残りで続行する。
````

- [ ] **Step 5: `company-blog-digest/SKILL.md` を書く**

````markdown
---
name: company-blog-digest
description: "登録した企業の技術ブログ（OpenAI、NVIDIA、Netflix など）の新着記事を RSS/Atom で取得し、本文を日本語で要約して Markdown に保存するスキル。「企業ブログ」「テックブログ」「company blog」「engineering blog」などで発動する。"
allowed-tools:
  - "Bash(uv run */blog-digest/scripts/fetch_feeds.py*)"
  - Read
  - Write
  - Edit
  - Skill
---

# 企業ブログダイジェスト

`feeds.json` に登録した企業の技術ブログの新着記事を取得し、本文を日本語で要約して `company-blogs/YYYY-MM-DD.md` に保存する。
取得スクリプトは `blog-digest` のものを共用する。

## 設定ファイル

`<skill-dir>/feeds.json`。形式は `blog-digest` と同じ。

## ワークフロー

`YYYY-MM-DD` は今日の日付（ローカル時刻）とする。

### Step 1: データ取得

`<skills-dir>` は `.claude/skills`（このスキルの親ディレクトリ）。

```bash
uv run <skills-dir>/blog-digest/scripts/fetch_feeds.py --config <skill-dir>/feeds.json --out-dir .cache/company-blogs-YYYY-MM-DD --state-dir company-blogs
```

### Step 2: 読み込み

1. Read で `.cache/company-blogs-YYYY-MM-DD/manifest.json` を読む。
2. `feeds` の順に `file` を1つずつ Read して要約する。読み終えたフィードの要約を書き出してから次に進む。

`Body-Source: summary` の記事は要約の末尾に「（概要のみ）」と付ける。

### Step 3: サマリー生成・保存

要約の注意点:
- 本文に書かれていることだけで要約する。製品発表の宣伝文句はそのまま繰り返さず、何が新しいのかを書く。
- 「読む価値」は1文で書く。

ハイライトは3〜5件（記事がそれより少なければ全件）。選定基準:
- 大規模システムの設計・運用の具体的な知見
- AI/ML のモデル・研究・インフラの発表
- 自動運転、開発ツールなど関心分野に直接関わる

```markdown
# 企業ブログダイジェスト — YYYY-MM-DD

> 対象期間: {since} 以降

## 本日のハイライト

1. **[{title}]({link})** ({フィード名}) — {選定理由(日本語)}
2. ...

---

## {フィード名}

### [{title}]({link})
**公開:** {published の日付部分} | **著者:** {author。空なら省く}

{要約。3〜5文}

**読む価値:** {1文}

---

## 取得に失敗したフィード

- {name}: {error}
```

- 記事が0件のフィードは節を作らない。
- `feeds` が空なら「対象期間に新着記事はありません」と書く。
- `errors` が空なら「取得に失敗したフィード」の節を省く。

保存先: `company-blogs/YYYY-MM-DD.md`（同名ファイルがあれば上書き）

### Step 4: 文章校正

{共通ブロック A を `{出力パス}` = `company-blogs/YYYY-MM-DD.md` で展開した本文}

### Step 5: 完了報告

- 保存したファイルパス
- 対象期間、フィードごとの記事数
- 取得に失敗したフィード
- 校正結果

## エラーハンドリング

- スクリプトが異常終了した場合は、標準エラーの内容を報告して停止する。
- フィード単位の失敗は `errors` に入るだけなので、残りで続行する。
````

- [ ] **Step 6: `trending-digest/SKILL.md` を書く**

````markdown
---
name: trending-digest
description: "GitHub Trending（全言語・デイリー）のリポジトリを取得し、日本語サマリーを Markdown に保存するスキル。「GitHub Trending」「トレンド」「trending」「話題のリポジトリ」などで発動する。"
allowed-tools:
  - "Bash(uv run */trending-digest/scripts/fetch_trending.py*)"
  - Read
  - Write
  - Edit
  - Skill
---

# GitHub Trending ダイジェスト

GitHub Trending（全言語・デイリー）に載ったリポジトリを取得し、日本語で紹介して `trending/YYYY-MM-DD.md` に保存する。

## ワークフロー

`YYYY-MM-DD` は今日の日付（ローカル時刻）とする。

### Step 1: データ取得

```bash
uv run <skill-dir>/scripts/fetch_trending.py --out .cache/trending-YYYY-MM-DD.json
```

- README の取得に `gh` CLI を使う。未認証なら `gh auth login` をユーザーに案内する（README なしでも続行できる）。
- 終了コード1は Trending ページを解析できなかったことを表す。原因（`error`）を報告して停止する。

### Step 2: 読み込み

Read で `.cache/trending-YYYY-MM-DD.json` を読む。
各リポジトリは `rank`、`repo`、`url`、`description`、`language`、`stars`、`forks`、`stars_today`、`readme_excerpt` を持つ。

### Step 3: サマリー生成・保存

要約の注意点:
- 「何をするものか」は `description` と `readme_excerpt` から書く。英語や中国語の説明は日本語に訳す。
- README から読み取れる特徴（対応環境、使い方の要点など）があれば1文足す。なければ書かない。

ハイライトは3〜5件。選定基準:
- 当日のスター数が特に多い
- 関心分野（AI/ML、開発ツール、ターミナル、エディタ、自動運転）に関わる
- 新しいカテゴリのツールである

```markdown
# GitHub Trending — YYYY-MM-DD

## 本日のハイライト

1. **[{repo}]({url})** (+{stars_today} stars) — {選定理由(日本語)}
2. ...

---

## リポジトリ一覧

### {rank}. [{repo}]({url})
**言語:** {language。空なら「不明」} | **スター:** {stars}（本日 +{stars_today}） | **フォーク:** {forks}

{何をするものか。1〜2文}{README からの特徴。1文}

---
```

保存先: `trending/YYYY-MM-DD.md`（同名ファイルがあれば上書き）

### Step 4: 文章校正

{共通ブロック A を `{出力パス}` = `trending/YYYY-MM-DD.md` で展開した本文}

### Step 5: 完了報告

- 保存したファイルパス
- リポジトリ数と README を取得できた数
- 校正結果

## エラーハンドリング

- 終了コード1（解析失敗）の場合は、GitHub の HTML 構造が変わった可能性があるとして報告し、停止する。
````

- [ ] **Step 7: 各スキルを1回ずつ単独で実行して確認する**

新しいセッション（またはこのセッション）で、次を1つずつ実行する。

- `Skill("hackernews-digest")`
- `Skill("hf-papers-digest")`
- `Skill("blog-digest")`
- `Skill("company-blog-digest")`
- `Skill("trending-digest")`

Expected: それぞれ `hackernews/`、`hf-papers/`、`blogs/`、`company-blogs/`、`trending/` に今日の `YYYY-MM-DD.md` ができる。フォーマットが SKILL.md のとおりで、要約が日本語になっている。

続けてサイトで表示を確かめる。

Run: `cd site && npm test`
Expected: PASS。`_site/<今日>/hackernews/index.html` など5ページがある。

- [ ] **Step 8: Commit**

```bash
git add .gitignore .claude/settings.json .claude/skills hackernews hf-papers blogs company-blogs trending
git commit -m "新しい情報源の digest スキル5つを追加"
```

---

### Task 7: daily-digest を7情報源に広げる

**Files:**
- Modify: `.claude/skills/daily-digest/SKILL.md`（全面書き換え）
- Modify: `README.md`
- Modify: `package.json`

**Interfaces:**
- Consumes: Task 6 のスキル名と出力パス。

- [ ] **Step 1: `.claude/skills/daily-digest/SKILL.md` を書き換える**

````markdown
---
name: daily-digest
description: "arxiv 新着論文、HF Daily Papers、Hacker News、GitHub リポジトリアクティビティ、GitHub Trending、個人ブログ、企業ブログを同時に取得し、個別ダイジェストに加えて横断的な統合サマリーを生成するスキル。「daily-digest」「今日のダイジェスト」「毎日のまとめ」「デイリーダイジェスト」などで発動する。"
allowed-tools:
  - "Bash(uv run python */arxiv-digest/scripts/fetch_arxiv.py*)"
  - "Bash(uv run python */github-digest/scripts/fetch_github.py*)"
  - "Bash(uv run */hackernews-digest/scripts/fetch_hackernews.py*)"
  - "Bash(uv run */hf-papers-digest/scripts/fetch_hf_papers.py*)"
  - "Bash(uv run */blog-digest/scripts/fetch_feeds.py*)"
  - "Bash(uv run */trending-digest/scripts/fetch_trending.py*)"
  - "Bash(git add *)"
  - "Bash(git commit -m *)"
  - "Bash(git push)"
  - "Bash(git status:*)"
  - Read
  - Write
  - Edit
  - Agent
  - Skill
---

# デイリーダイジェスト

7つの情報源のダイジェストを **並列** で生成し、それぞれの個別出力に加えて、全情報源を横断する統合サマリーを生成・保存する。

| 情報源 | スキル | 個別出力 |
|---|---|---|
| arxiv | `arxiv-digest` | `arxiv/YYYY-MM-DD.md` |
| HF Daily Papers | `hf-papers-digest` | `hf-papers/YYYY-MM-DD.md` |
| Hacker News | `hackernews-digest` | `hackernews/YYYY-MM-DD.md` |
| GitHub | `github-digest` | `github/YYYY-MM-DD.md` |
| GitHub Trending | `trending-digest` | `trending/YYYY-MM-DD.md` |
| 個人ブログ | `blog-digest` | `blogs/YYYY-MM-DD.md` |
| 企業ブログ | `company-blog-digest` | `company-blogs/YYYY-MM-DD.md` |

## ワークフロー

### Step 1: 各スキルの並列実行

7つの subagent を **並列に** 起動し、上の表のスキルをそれぞれ実行させる。

> **全ての subagent は `model: "opus"` を指定すること。**

各 subagent へのプロンプトは「{スキル名} スキルを実行してください。完了したら、保存したファイルパスと件数（{件数の内訳}）を報告してください。」とする。件数の内訳は次のとおり。

- `arxiv-digest`: カテゴリごとの論文数
- `hf-papers-digest`: 対象日と論文数
- `hackernews-digest`: 上位記事数とキーワード一致数
- `github-digest`: リポジトリごとの Issue/PR 数
- `trending-digest`: リポジトリ数
- `blog-digest`: 対象期間とフィードごとの記事数、失敗したフィード
- `company-blog-digest`: 対象期間とフィードごとの記事数、失敗したフィード

全エージェントの完了を待つ。失敗したものがあっても、残りの結果で続行する。

### Step 2: 統合サマリー生成

成功した情報源の個別ファイルを読み込み、横断的な統合サマリーを生成する。

#### 統合サマリーのフォーマット

```markdown
# デイリーダイジェスト — YYYY-MM-DD

## 本日のハイライト

全情報源から横断的に注目トピックを5〜8件選定する。

選定基準:
- 複数の情報源に同じ話題が現れている（例: HF Papers の論文が HN でも話題、企業ブログの発表したリポジトリが Trending に載っている、arxiv の手法が OSS で実装された）
- 大きなインパクトが見込まれる（画期的な手法、大規模な機能追加、重要なリリース）
- 複数の領域にまたがる影響がある

1. **[{タイトル}]({link})** ({情報源名。複数に出ていれば「HN / HF Papers」のように併記}) — {選定理由(日本語)}
2. ...

---

## arxiv 新着論文

> 詳細: [arxiv/YYYY-MM-DD.md](../arxiv/YYYY-MM-DD.md)

カテゴリを問わず注目論文を2〜3件。各1〜2文。

- **[{日本語タイトル}]({link})** ({カテゴリ}) — {1〜2文の要約}

---

## HF Daily Papers

> 詳細: [hf-papers/YYYY-MM-DD.md](../hf-papers/YYYY-MM-DD.md)

- **[{日本語タイトル}]({hf_url})** ({upvotes} upvotes) — {1〜2文の要約}

---

## Hacker News

> 詳細: [hackernews/YYYY-MM-DD.md](../hackernews/YYYY-MM-DD.md)

- **[{title}]({url})** ({points} points) — {話題と反応を1〜2文}

---

## GitHub アクティビティ

> 詳細: [github/YYYY-MM-DD.md](../github/YYYY-MM-DD.md)

- **[{タイトル}]({link})** ({owner/repo} `#{number}`) — {1〜2文の要約}

---

## GitHub Trending

> 詳細: [trending/YYYY-MM-DD.md](../trending/YYYY-MM-DD.md)

- **[{repo}]({url})** (+{stars_today} stars) — {1〜2文}

---

## 個人ブログ

> 詳細: [blogs/YYYY-MM-DD.md](../blogs/YYYY-MM-DD.md)

- **[{title}]({link})** ({フィード名}) — {1〜2文の要約}

---

## 企業ブログ

> 詳細: [company-blogs/YYYY-MM-DD.md](../company-blogs/YYYY-MM-DD.md)

- **[{title}]({link})** ({フィード名}) — {1〜2文の要約}
```

各情報源の節は2〜3件に絞る。

要約の注意点:
- 個別ファイルの内容に忠実に書く。新たな推測や外部知識で補わない
- ハイライトでは情報源どうしの関連を積極的に見つける
- 圧縮しても情報の正確さは維持する

#### 一部の情報源が失敗した場合

- 失敗した情報源の節には、詳細リンクを置かずに「取得に失敗しました」とだけ書く。
- ブログで新着記事がなかった場合は「対象期間に新着記事はありません」と書く（失敗ではない）。

### Step 3: 文章校正

生成した `daily/YYYY-MM-DD.md` を、次の2段階で校正・修正する。

1. **文章規範チェック（`japanese-tech-writing` スキル）**
   `Skill` ツールで `japanese-tech-writing` を呼び出し、対象ファイルを明示的に指定して、その文章規範に沿って推敲する。特に LLM が生成しがちな表現を重点的に直す。
   - ダッシュ（`—` `―` `——`）・中黒（・）の不使用
   - LLM っぽい空句（「重要なのは〜」「正面から」「多角的に」など）の排除
   - 冗長な言い換え・繰り返しの削除、一文一行の整形
   - ねじれ文・助詞の誤用の修正

2. **機械チェック（`textlint-proofreader` スキル）**
   `Skill` ツールで `textlint-proofreader` を呼び出し、同じファイルを指定して表記揺れ等を機械的に検出・修正する。
   - 表記揺れの統一
   - 読みやすさの最終確認

自動修正可能な指摘は適用し、残った手動対応分は完了報告に含める。

### Step 4: git コミットとプッシュ

生成できたファイルを git にコミットし、リモートへプッシュする。コミットメッセージは生成対象日（YYYY-MM-DD）。

```bash
git add arxiv/YYYY-MM-DD.md hf-papers/YYYY-MM-DD.md hackernews/YYYY-MM-DD.md github/YYYY-MM-DD.md trending/YYYY-MM-DD.md blogs/YYYY-MM-DD.md company-blogs/YYYY-MM-DD.md daily/YYYY-MM-DD.md
git commit -m "YYYY-MM-DD"
git push
```

注意点:

- `YYYY-MM-DD` はダイジェスト対象日（ファイル名と一致する日付）。当日生成なら今日の日付。
- Step 1 で失敗した情報源のファイルは `git add` に含めない（存在するファイルのみを指定する）。
- `.cache/` はコミットしない（`.gitignore` 済み）。
- コミット成功後に `git status` で結果を確認する。
- pre-commit フックなどで失敗した場合は、原因を報告して停止する（`--no-verify` は使わない）。
- コミット成功後に `git push` でリモートへ反映する。
- プッシュが失敗した場合（リモート拒否・認証エラー・upstream 未設定など）は、原因を報告して停止する。コミット自体は完了しているため、ファイルは失われない。

### Step 5: 完了報告

生成が完了したら、以下を報告する:

- 保存したファイルパス（統合サマリーと、成功した個別ダイジェスト）
- 情報源ごとの件数（Step 1 で各 subagent が報告したもの）
- 取得できなかった情報源があればその旨
- コミットハッシュ
- プッシュの結果（成功／失敗、失敗時はその原因）

## エラーハンドリング

- 一部の情報源が失敗しても、残りの結果で統合サマリーを生成する
- 全情報源が失敗した場合は、エラー内容をユーザーに報告する
- `daily/` ディレクトリが存在しない場合は作成する
````

- [ ] **Step 2: README.md を更新する**

```markdown
# briefing

arXiv 新着論文、HF Daily Papers、Hacker News、GitHub Issue/PR、GitHub Trending、技術ブログの日次ダイジェスト。
https://briefing.kamata.page/

- `daily/YYYY-MM-DD.md` 統合サマリー
- `arxiv/YYYY-MM-DD.md` arXiv 詳細
- `hf-papers/YYYY-MM-DD.md` HF Daily Papers 詳細
- `hackernews/YYYY-MM-DD.md` Hacker News 詳細
- `github/YYYY-MM-DD.md` GitHub 詳細
- `trending/YYYY-MM-DD.md` GitHub Trending 詳細
- `blogs/YYYY-MM-DD.md` 個人ブログ詳細
- `company-blogs/YYYY-MM-DD.md` 企業ブログ詳細
- `site/` Eleventy による静的サイト
- `.claude/skills/` 生成スキル（Claude Code）

## 生成

Claude Code で `daily-digest` スキルを実行する。
情報源ごとのスキル（`hackernews-digest` など）を単独で実行することもできる。
購読するブログは `.claude/skills/blog-digest/feeds.json` と `.claude/skills/company-blog-digest/feeds.json`、HN のキーワードは `.claude/skills/hackernews-digest/keywords.json` で変更する。

## サイト

```
cd site && npm ci && npm run build
```

## 検証

サイトの変更後は `cd site && npm test` を実行する（ユニットテスト、ビルド、スモークチェックを行う）。
取得スクリプトの変更後は、そのスキルの `tests/` を実行する（例: `uv run --with pytest --with feedparser --with trafilatura pytest .claude/skills/blog-digest/tests -q`）。
Markdown コンテンツの文章チェックはリポジトリルートで `npm run lint` を実行する（textlint）。
```

- [ ] **Step 3: package.json の lint 対象と説明を更新する**

`package.json` の `description` と `scripts.lint` を置き換える。

```json
  "description": "arXiv、HF Daily Papers、Hacker News、GitHub、GitHub Trending、技術ブログの日次ダイジェスト",
```

```json
    "lint": "textlint daily arxiv github hf-papers hackernews trending blogs company-blogs"
```

Run: `npm run lint`
Expected: 実行でき、存在しないディレクトリによるエラーが出ない（Task 6 Step 7 で5ディレクトリは作成済み）。文章の指摘が出る場合は既存ファイルと同程度であることを確認する。

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/daily-digest/SKILL.md README.md package.json
git commit -m "daily-digest: 7つの情報源を並列に実行し横断サマリーを作るよう拡張"
```

---

### Task 8: 通しの動作確認

**Files:** なし（確認のみ）

- [ ] **Step 1: 全 Python テストを一括で実行する**

Run: `uv run --with pytest --with feedparser --with trafilatura --with beautifulsoup4 pytest .claude/skills/hackernews-digest/tests .claude/skills/hf-papers-digest/tests .claude/skills/blog-digest/tests .claude/skills/trending-digest/tests -q`
Expected: PASS（30 passed）

- [ ] **Step 2: daily-digest を通しで実行する**

`/Users/kenshi.kamata/briefing` で Claude Code を開き、`daily-digest` を実行する。push まで行われるので、実行前にユーザーに確認する。

Expected:
- 7つの個別ファイルと `daily/<今日>.md` ができる
- 統合サマリーに7つの節があり、詳細リンクがすべて存在するファイルを指す
- コミットと push が成功する

- [ ] **Step 3: サイトを確認する**

Run: `cd site && npm test`
Expected: PASS。`_site/<今日>/` 配下に `arxiv`、`hf-papers`、`hackernews`、`github`、`trending`、`blogs`、`company-blogs` の7ページがある。

push 後、`https://briefing.kamata.page/latest/` が今日の日付へリダイレクトし、日付ナビに7種類のリンクが並ぶことをブラウザで確認する。
