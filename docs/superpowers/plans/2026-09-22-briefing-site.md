# briefing サイト実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** til の日次ダイジェストの仕組みを `knsh14/briefing` に移設し、Eleventy で生成した静的サイトを Cloudflare Workers から `briefing.kamata.page` で配信する。

**Architecture:** リポジトリ直下の `daily/`、`arxiv/`、`github/` に置いた `YYYY-MM-DD.md` を、`site/` の Eleventy プロジェクトがビルド時に走査して日付ごとのページに変換する。走査（`lib/load.js`）と描画（`lib/render.js`）は純粋関数として分離し `node:test` で検証する。Cloudflare Workers Builds が main への push を検知してビルドとデプロイを行う。

**Tech Stack:** Node 24、@11ty/eleventy 3.1、markdown-it 15、Nunjucks、wrangler 4、Cloudflare Workers 静的アセット

**Spec:** `docs/superpowers/specs/2026-09-22-briefing-site-design.md`

## Global Constraints

- 作業ディレクトリは `/Users/kenshi.kamata/briefing`。til は `/Users/kenshi.kamata/til`（コピー元。Task 11 まで変更しない）。
- コミットの author/committer は `kenshi.kamata@gmail.com`（リポジトリローカルに設定済み）。
- 既存の Markdown 本文は、`](../github-digest/` → `](../github/` の一括置換以外、一切変更しない。
- Python の実行は `uv run python`。`python` の直接呼び出しは禁止。
- スキルの `allowed-tools` の Bash 許可は特定スクリプトに限定し、広範なパターンを書かない。
- `site/package.json` は `"type": "module"`。設定、データ、テストはすべて ESM。
- HTML の後処理に正規表現を使わない。リンク書き換えは markdown-it のレンダラー差し替えで行う。
- 出力ディレクトリ名は `daily`、`arxiv`、`github`。URL のセグメントと一致させる。
- スキル名 `arxiv-digest`、`github-digest`、`daily-digest` は変更しない。変えるのは出力パスだけ。

---

## ファイル構成

| パス | 責務 |
|---|---|
| `daily/`, `arxiv/`, `github/` | 生成済み Markdown。`github/icons/` に Octicons SVG |
| `.claude/skills/{arxiv-digest,github-digest,daily-digest}/` | スキル定義、取得スクリプト、設定 JSON |
| `.agents/skills` | `../.claude/skills` へのシンボリックリンク |
| `.claude/settings.json` | fetch スクリプト等の許可 |
| `package.json`, `.textlintrc.json` | textlint（daily-digest Step 3 用） |
| `site/package.json` | Eleventy 依存とスクリプト |
| `site/eleventy.config.js` | 入出力ディレクトリ、passthrough copy |
| `site/wrangler.jsonc` | Workers 静的アセット設定 |
| `site/lib/load.js` | 系列ディレクトリの走査と日付グルーピング |
| `site/lib/render.js` | markdown-it 設定とリンク・画像書き換え |
| `site/src/_data/digests.js` | `lib/` を使って全ページ共通データを組む |
| `site/src/_includes/base.njk` | HTML 骨格 |
| `site/src/{index,date,arxiv,github,redirects,feed,404}.njk` | 各ページ |
| `site/src/style.css` | スタイル |
| `site/scripts/check-build.mjs` | ビルド出力のスモークチェック |
| `site/test/{load,render}.test.js` | ユニットテスト |

---

### Task 1: リポジトリ骨格と Markdown の移設

**Files:**
- Create: `.gitignore`, `README.md`, `package.json`, `.textlintrc.json`
- Create: `daily/*.md`, `arxiv/*.md`, `github/*.md`, `github/icons/*.svg`

**Interfaces:**
- Produces: `daily/`, `arxiv/`, `github/` の 3 ディレクトリ。ファイル名は `YYYY-MM-DD.md`。`github/icons/{git-pull-request,issue-opened}.svg`。

- [ ] **Step 1: ルートファイルを作る**

```bash
cd /Users/kenshi.kamata/briefing
cat > .gitignore <<'EOF'
node_modules/
.DS_Store
site/_site/
EOF
cat > README.md <<'EOF'
# briefing

arXiv 新着論文と GitHub Issue/PR の日次ダイジェスト。
https://briefing.kamata.page/

- `daily/YYYY-MM-DD.md` 統合サマリー
- `arxiv/YYYY-MM-DD.md` arXiv 詳細
- `github/YYYY-MM-DD.md` GitHub 詳細
- `site/` Eleventy による静的サイト
- `.claude/skills/` 生成スキル（Claude Code）

## 生成

Claude Code で `daily-digest` スキルを実行する。

## サイト

```
cd site && npm ci && npm run build
```
EOF
cp /Users/kenshi.kamata/til/.textlintrc.json .textlintrc.json
```

- [ ] **Step 2: textlint 用 package.json を作る**

```bash
cd /Users/kenshi.kamata/briefing
cat > package.json <<'EOF'
{
  "name": "briefing",
  "private": true,
  "version": "1.0.0",
  "description": "arXiv と GitHub の日次ダイジェスト",
  "type": "commonjs",
  "scripts": {
    "lint": "textlint daily arxiv github"
  },
  "repository": {
    "type": "git",
    "url": "git+https://github.com/knsh14/briefing.git"
  },
  "license": "ISC",
  "devDependencies": {
    "textlint": "^15.5.4",
    "textlint-rule-preset-ja-spacing": "^2.4.3",
    "textlint-rule-preset-ja-technical-writing": "^12.0.2",
    "textlint-rule-prh": "^6.1.0"
  }
}
EOF
npm install
```

Expected: `package-lock.json` と `node_modules/` が生成される。

- [ ] **Step 3: Markdown をコピーし、リンクを置換する**

```bash
cd /Users/kenshi.kamata/briefing
mkdir -p daily arxiv github/icons
cp /Users/kenshi.kamata/til/daily-digest/*.md daily/
cp /Users/kenshi.kamata/til/arxiv/*.md arxiv/
find /Users/kenshi.kamata/til/github-digest -maxdepth 1 -name '20??-??-??.md' -exec cp {} github/ \;
cp /Users/kenshi.kamata/til/github-digest/icons/*.svg github/icons/
sed -i '' 's#](\.\./github-digest/#](../github/#g' daily/*.md
```

- [ ] **Step 4: 件数とリンク置換を検証する**

```bash
cd /Users/kenshi.kamata/briefing
ls daily | wc -l; ls arxiv | wc -l; ls github/*.md | wc -l; ls github/icons
grep -l 'github-digest/' daily/*.md | wc -l
grep -ho '](\.\./[a-z-]*/' daily/*.md | sort | uniq -c
```

Expected: daily 31、arxiv 33、github 32、icons に svg 2 つ。`github-digest/` を含む daily は 0。uniq の結果は `](../arxiv/` と `](../github/` の 2 行のみ。

- [ ] **Step 5: textlint が動くことを確認する**

```bash
cd /Users/kenshi.kamata/briefing && npx textlint daily/2026-08-11.md; echo "exit=$?"
```

Expected: 指摘が出ても出なくてもよい。「設定が見つからない」「ルールが見つからない」系のエラーが出ないこと。

- [ ] **Step 6: コミット**

```bash
cd /Users/kenshi.kamata/briefing
git add .gitignore README.md package.json package-lock.json .textlintrc.json daily arxiv github
git commit -m "$(cat <<'EOF'
Import digests and textlint config from til

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: スキルの移設とパス修正

**Files:**
- Create: `.claude/skills/arxiv-digest/{SKILL.md,categories.json,scripts/fetch_arxiv.py}`
- Create: `.claude/skills/github-digest/{SKILL.md,repos.json,scripts/fetch_github.py}`
- Create: `.claude/skills/daily-digest/SKILL.md`
- Create: `.claude/settings.json`
- Create: `.agents/skills` (symlink)

**Interfaces:**
- Consumes: Task 1 の `daily/`, `arxiv/`, `github/`。
- Produces: スキルが `daily/YYYY-MM-DD.md`、`arxiv/YYYY-MM-DD.md`、`github/YYYY-MM-DD.md` に書き出す。

- [ ] **Step 1: 最新版の SKILL.md とスクリプトをコピーする**

til のトップレベル版（未コミット変更込み）が正本。daily-digest は `.claude/skills/` 版が唯一の版。

```bash
cd /Users/kenshi.kamata/briefing
T=/Users/kenshi.kamata/til
mkdir -p .claude/skills/arxiv-digest/scripts .claude/skills/github-digest/scripts .claude/skills/daily-digest .agents
cp $T/arxiv-digest/SKILL.md            .claude/skills/arxiv-digest/SKILL.md
cp $T/arxiv-digest/categories.json     .claude/skills/arxiv-digest/categories.json
cp $T/arxiv-digest/scripts/fetch_arxiv.py .claude/skills/arxiv-digest/scripts/
cp $T/github-digest/SKILL.md           .claude/skills/github-digest/SKILL.md
cp $T/github-digest/repos.json         .claude/skills/github-digest/repos.json
cp $T/github-digest/scripts/fetch_github.py .claude/skills/github-digest/scripts/
cp $T/.claude/skills/daily-digest/SKILL.md .claude/skills/daily-digest/SKILL.md
ln -s ../.claude/skills .agents/skills
grep -c sunnypilot .claude/skills/github-digest/repos.json
```

Expected: 最後の grep が `1`（未コミット版が取れている）。

- [ ] **Step 2: arxiv-digest の設定パスを直す**

```bash
cd /Users/kenshi.kamata/briefing
sed -i '' 's#`arxiv-digest/categories.json`#`<skill-dir>/categories.json`#g' .claude/skills/arxiv-digest/SKILL.md
grep -n 'categories.json' .claude/skills/arxiv-digest/SKILL.md
```

Expected: `arxiv-digest/categories.json` という記述が残っていない。

- [ ] **Step 3: github-digest の設定パスと出力パスを直す**

```bash
cd /Users/kenshi.kamata/briefing
F=.claude/skills/github-digest/SKILL.md
sed -i '' \
  -e 's#`github-digest/repos.json`#`<skill-dir>/repos.json`#g' \
  -e 's#`github-digest/icons/`#`github/icons/`#g' \
  -e 's#`github-digest/YYYY-MM-DD.md`#`github/YYYY-MM-DD.md`#g' \
  "$F"
grep -n 'github-digest/' "$F"
```

Expected: 残るのは `Bash(uv run python */github-digest/scripts/fetch_github.py*)` の 1 行だけ（スキルディレクトリ名なので正しい）。

- [ ] **Step 4: daily-digest の出力パスと相互リンクを直す**

```bash
cd /Users/kenshi.kamata/briefing
F=.claude/skills/daily-digest/SKILL.md
sed -i '' \
  -e 's#git add arxiv/\* github-digest/\* daily-digest/\*#git add arxiv/* github/* daily/*#' \
  -e 's#github-digest/YYYY-MM-DD\.md#github/YYYY-MM-DD.md#g' \
  -e 's#daily-digest/YYYY-MM-DD\.md#daily/YYYY-MM-DD.md#g' \
  -e 's#\.\./github-digest/#../github/#g' \
  -e 's#`daily-digest/` ディレクトリ#`daily/` ディレクトリ#' \
  "$F"
grep -n 'github-digest\|daily-digest' "$F"
```

Expected: 残る行はスキル名としての `github-digest`、`daily-digest`（`Skill("github-digest")`、`name: daily-digest`、「github-digest スキルを実行してください」など）だけ。パスとしての `github-digest/`、`daily-digest/` は残っていない。

- [ ] **Step 5: .claude/settings.json を作る**

```bash
cd /Users/kenshi.kamata/briefing
cat > .claude/settings.json <<'EOF'
{
  "permissions": {
    "allow": [
      "Bash(uv run python */arxiv-digest/scripts/fetch_arxiv.py*)",
      "Bash(uv run python */github-digest/scripts/fetch_github.py*)",
      "Bash(mkdir -p */arxiv)",
      "Bash(mkdir -p */github)",
      "Bash(mkdir -p */daily)",
      "Bash(npx textlint*)",
      "Bash(gh auth *)",
      "WebFetch(domain:export.arxiv.org)"
    ]
  }
}
EOF
```

- [ ] **Step 6: スクリプトが設定ファイルを見つけることを確認する**

```bash
cd /Users/kenshi.kamata/briefing
uv run python .claude/skills/arxiv-digest/scripts/fetch_arxiv.py --help 2>&1 | head -5
grep -n 'os.path.join(os.path.dirname(__file__), "..", "categories.json")' .claude/skills/arxiv-digest/scripts/fetch_arxiv.py
grep -n 'os.path.join(os.path.dirname(__file__), "..", "repos.json")' .claude/skills/github-digest/scripts/fetch_github.py
```

Expected: 両 grep が 1 行ずつ一致する（スクリプトは `scripts/../categories.json` を既定で読むため、配置がそのまま使える）。

- [ ] **Step 7: コミット**

```bash
cd /Users/kenshi.kamata/briefing
git add .claude .agents
git commit -m "$(cat <<'EOF'
Import digest skills from til and point them at daily/arxiv/github

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: site/ の骨格と Eleventy 設定

**Files:**
- Create: `site/package.json`, `site/eleventy.config.js`, `site/.gitignore`, `site/wrangler.jsonc`, `site/src/.gitkeep`

**Interfaces:**
- Produces: `npm run build` が `site/_site/` を出力する。入力は `site/src/`。`../github/icons` が `_site/icons/` に、`src/style.css` が `_site/style.css` にコピーされる。

- [ ] **Step 1: package.json を作り依存を入れる**

```bash
mkdir -p /Users/kenshi.kamata/briefing/site/src && cd /Users/kenshi.kamata/briefing/site
cat > package.json <<'EOF'
{
  "name": "briefing-site",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "eleventy",
    "dev": "eleventy --serve",
    "test": "node --test",
    "check": "node scripts/check-build.mjs"
  }
}
EOF
cat > .gitignore <<'EOF'
node_modules/
_site/
EOF
npm install --save-dev @11ty/eleventy@^3.1.6 wrangler@^4.136.1
npm install markdown-it@^15.0.2
```

- [ ] **Step 2: eleventy.config.js を書く**

```js
// site/eleventy.config.js
export default function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy({ "../github/icons": "icons" });
  eleventyConfig.addPassthroughCopy("src/style.css");

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

- [ ] **Step 3: wrangler.jsonc を書く**

```jsonc
// site/wrangler.jsonc
{
  "$schema": "./node_modules/wrangler/config-schema.json",
  "name": "briefing",
  "compatibility_date": "2026-09-22",
  "assets": {
    "directory": "./_site",
    "not_found_handling": "404-page"
  },
  "routes": [
    { "pattern": "briefing.kamata.page", "custom_domain": true }
  ]
}
```

- [ ] **Step 4: 空ビルドが通ることを確認する**

```bash
cd /Users/kenshi.kamata/briefing/site
printf '/* placeholder */\n' > src/style.css
npm run build && ls _site _site/icons
```

Expected: `_site/style.css` と `_site/icons/git-pull-request.svg`、`_site/icons/issue-opened.svg` がある。

- [ ] **Step 5: コミット**

```bash
cd /Users/kenshi.kamata/briefing
git add site/package.json site/package-lock.json site/.gitignore site/eleventy.config.js site/wrangler.jsonc site/src/style.css
git commit -m "$(cat <<'EOF'
Scaffold Eleventy site with Workers static assets config

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: lib/load.js（走査と日付グルーピング）

**Files:**
- Create: `site/lib/load.js`
- Test: `site/test/load.test.js`

**Interfaces:**
- Produces:
  - `DATE_RE: RegExp` — `^(\d{4}-\d{2}-\d{2})\.md$`
  - `readSeries(dir: string): Array<{date: string, text: string}>` — `dir` 直下の日付ファイルだけを読む。順不同。
  - `buildDays(series: {daily: Entry[], arxiv: Entry[], github: Entry[]}, render: (text: string) => string): Day[]`
    - `Day = { date: string, daily: {html}|null, arxiv: {html}|null, github: {html}|null, prev: string|null, next: string|null }`
    - 新しい日付順。`prev` は一つ古い日付、`next` は一つ新しい日付。

- [ ] **Step 1: 失敗するテストを書く**

```js
// site/test/load.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DATE_RE, readSeries, buildDays } from "../lib/load.js";

const upper = (s) => s.toUpperCase();

test("DATE_RE matches only YYYY-MM-DD.md", () => {
  assert.ok(DATE_RE.test("2026-08-11.md"));
  assert.equal(DATE_RE.exec("2026-08-11.md")[1], "2026-08-11");
  assert.ok(!DATE_RE.test("SKILL.md"));
  assert.ok(!DATE_RE.test("2026-08-11.txt"));
  assert.ok(!DATE_RE.test("icons"));
});

test("readSeries returns only date files with their text", () => {
  const dir = mkdtempSync(join(tmpdir(), "briefing-"));
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

test("buildDays groups by date, newest first, with prev/next", () => {
  const days = buildDays(
    {
      daily: [{ date: "2026-08-11", text: "d11" }],
      arxiv: [{ date: "2026-08-11", text: "a11" }, { date: "2026-08-10", text: "a10" }],
      github: [{ date: "2026-08-09", text: "g09" }],
    },
    upper,
  );
  assert.deepEqual(days.map((d) => d.date), ["2026-08-11", "2026-08-10", "2026-08-09"]);
  assert.deepEqual(days[0], {
    date: "2026-08-11",
    daily: { html: "D11" },
    arxiv: { html: "A11" },
    github: null,
    prev: "2026-08-10",
    next: null,
  });
  assert.deepEqual(days[1], {
    date: "2026-08-10",
    daily: null,
    arxiv: { html: "A10" },
    github: null,
    prev: "2026-08-09",
    next: "2026-08-11",
  });
  assert.equal(days[2].prev, null);
  assert.equal(days[2].next, "2026-08-10");
});

test("buildDays returns [] when every series is empty", () => {
  assert.deepEqual(buildDays({ daily: [], arxiv: [], github: [] }, upper), []);
});
```

- [ ] **Step 2: テストが失敗することを確認する**

```bash
cd /Users/kenshi.kamata/briefing/site && npm test
```

Expected: FAIL。`Cannot find module '../lib/load.js'`。

- [ ] **Step 3: 実装する**

```js
// site/lib/load.js
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

export const DATE_RE = /^(\d{4}-\d{2}-\d{2})\.md$/;

export function readSeries(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const m = DATE_RE.exec(name);
    if (!m) continue;
    out.push({ date: m[1], text: readFileSync(join(dir, name), "utf8") });
  }
  return out;
}

const SERIES = ["daily", "arxiv", "github"];

export function buildDays(series, render) {
  const byDate = new Map();
  for (const key of SERIES) {
    for (const { date, text } of series[key] ?? []) {
      if (!byDate.has(date)) {
        byDate.set(date, { date, daily: null, arxiv: null, github: null });
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
```

- [ ] **Step 4: テストが通ることを確認する**

```bash
cd /Users/kenshi.kamata/briefing/site && npm test
```

Expected: 4 tests pass。

- [ ] **Step 5: コミット**

```bash
cd /Users/kenshi.kamata/briefing
git add site/lib/load.js site/test/load.test.js
git commit -m "$(cat <<'EOF'
Add digest loader that groups daily/arxiv/github by date

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: lib/render.js（markdown-it とリンク書き換え）

**Files:**
- Create: `site/lib/render.js`
- Test: `site/test/render.test.js`

**Interfaces:**
- Produces:
  - `rewriteHref(href: string): string` — 純粋関数。表の規則で書き換える。
  - `rewriteSrc(src: string): string` — `icons/x.svg` → `/icons/x.svg`。それ以外はそのまま。
  - `isExternal(href: string): boolean` — `http://` または `https://` で始まる。
  - `createMarkdown(): MarkdownIt` — レンダラーを差し替えた markdown-it インスタンス。
  - `renderMarkdown(text: string): string` — 上記で HTML 化。

- [ ] **Step 1: 失敗するテストを書く**

```js
// site/test/render.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { rewriteHref, rewriteSrc, isExternal, renderMarkdown } from "../lib/render.js";

test("rewriteHref maps sibling digest links to site URLs", () => {
  assert.equal(rewriteHref("../arxiv/2026-08-11.md"), "/2026-08-11/arxiv/");
  assert.equal(rewriteHref("../github/2026-08-11.md"), "/2026-08-11/github/");
  assert.equal(rewriteHref("../github-digest/2026-08-11.md"), "/2026-08-11/github/");
});

test("rewriteHref leaves other links alone", () => {
  assert.equal(rewriteHref("https://arxiv.org/abs/2608.07776"), "https://arxiv.org/abs/2608.07776");
  assert.equal(rewriteHref("#section"), "#section");
  assert.equal(rewriteHref("../doc/foo.md"), "../doc/foo.md");
  assert.equal(rewriteHref("../arxiv/notes.md"), "../arxiv/notes.md");
});

test("rewriteSrc maps icons/ to /icons/", () => {
  assert.equal(rewriteSrc("icons/git-pull-request.svg"), "/icons/git-pull-request.svg");
  assert.equal(rewriteSrc("https://example.com/a.png"), "https://example.com/a.png");
});

test("isExternal detects http(s) links", () => {
  assert.ok(isExternal("https://github.com/x"));
  assert.ok(isExternal("http://example.com"));
  assert.ok(!isExternal("/2026-08-11/"));
  assert.ok(!isExternal("mailto:a@b"));
});

test("renderMarkdown rewrites links, adds attributes to external links, rewrites images", () => {
  const html = renderMarkdown(
    [
      "[詳細](../github-digest/2026-08-11.md)",
      "",
      "[GH](https://github.com/neovim/neovim/pull/40924)",
      "",
      "![PR](icons/git-pull-request.svg) title",
    ].join("\n"),
  );
  assert.match(html, /<a href="\/2026-08-11\/github\/">詳細<\/a>/);
  assert.match(html, /<a href="https:\/\/github.com\/neovim\/neovim\/pull\/40924" target="_blank" rel="noopener">GH<\/a>/);
  assert.match(html, /<img src="\/icons\/git-pull-request.svg" alt="PR">/);
  assert.doesNotMatch(html, /target="_blank"[^>]*href="\/2026/);
});

test("renderMarkdown keeps raw HTML disabled and renders headings", () => {
  const html = renderMarkdown("# タイトル\n\n<script>x</script>");
  assert.match(html, /<h1>タイトル<\/h1>/);
  assert.match(html, /&lt;script&gt;/);
});
```

- [ ] **Step 2: テストが失敗することを確認する**

```bash
cd /Users/kenshi.kamata/briefing/site && npm test
```

Expected: FAIL。`Cannot find module '../lib/render.js'`。

- [ ] **Step 3: 実装する**

```js
// site/lib/render.js
import MarkdownIt from "markdown-it";

const SIBLING_RE = /^\.\.\/(arxiv|github|github-digest)\/(\d{4}-\d{2}-\d{2})\.md$/;
const ICON_RE = /^icons\/(.+)$/;

export function rewriteHref(href) {
  const m = SIBLING_RE.exec(href);
  if (!m) return href;
  const kind = m[1] === "arxiv" ? "arxiv" : "github";
  return `/${m[2]}/${kind}/`;
}

export function rewriteSrc(src) {
  const m = ICON_RE.exec(src);
  return m ? `/icons/${m[1]}` : src;
}

export function isExternal(href) {
  return /^https?:\/\//.test(href);
}

export function createMarkdown() {
  const md = new MarkdownIt({ html: false, linkify: false, typographer: false });

  const defaultLinkOpen =
    md.renderer.rules.link_open ??
    ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options));
  md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    const token = tokens[idx];
    const hrefIdx = token.attrIndex("href");
    if (hrefIdx >= 0) {
      const href = rewriteHref(token.attrs[hrefIdx][1]);
      token.attrs[hrefIdx][1] = href;
      if (isExternal(href)) {
        token.attrSet("target", "_blank");
        token.attrSet("rel", "noopener");
      }
    }
    return defaultLinkOpen(tokens, idx, options, env, self);
  };

  const defaultImage = md.renderer.rules.image;
  md.renderer.rules.image = (tokens, idx, options, env, self) => {
    const token = tokens[idx];
    const srcIdx = token.attrIndex("src");
    if (srcIdx >= 0) token.attrs[srcIdx][1] = rewriteSrc(token.attrs[srcIdx][1]);
    return defaultImage(tokens, idx, options, env, self);
  };

  return md;
}

const shared = createMarkdown();

export function renderMarkdown(text) {
  return shared.render(text);
}
```

- [ ] **Step 4: テストが通ることを確認する**

```bash
cd /Users/kenshi.kamata/briefing/site && npm test
```

Expected: load 4 件、render 6 件、すべて pass。

- [ ] **Step 5: コミット**

```bash
cd /Users/kenshi.kamata/briefing
git add site/lib/render.js site/test/render.test.js
git commit -m "$(cat <<'EOF'
Add markdown renderer that rewrites digest links and icon paths

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: データファイルと日付ページ

**Files:**
- Create: `site/src/_data/digests.js`
- Create: `site/src/_includes/base.njk`, `site/src/_includes/daynav.njk`
- Create: `site/src/index.njk`, `site/src/date.njk`, `site/src/arxiv.njk`, `site/src/github.njk`

**Interfaces:**
- Consumes: Task 4 の `readSeries`, `buildDays`、Task 5 の `renderMarkdown`。
- Produces: グローバルデータ `digests`:
  - `digests.days: Day[]` — 全日付、新しい順
  - `digests.latest: string|null` — 最新日付
  - `digests.arxiv: Day[]` — `arxiv` が非 null の日
  - `digests.github: Day[]` — `github` が非 null の日
  - `digests.feed: Day[]` — `daily` が非 null の日、最新 30 件
- Produces: レイアウト `base.njk` は `title`（文字列）と `content` を受け取る。

- [ ] **Step 1: データファイルを書く**

```js
// site/src/_data/digests.js
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { readSeries, buildDays } from "../../lib/load.js";
import { renderMarkdown } from "../../lib/render.js";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");

export default function () {
  const days = buildDays(
    {
      daily: readSeries(resolve(repoRoot, "daily")),
      arxiv: readSeries(resolve(repoRoot, "arxiv")),
      github: readSeries(resolve(repoRoot, "github")),
    },
    renderMarkdown,
  );
  return {
    days,
    latest: days[0]?.date ?? null,
    arxiv: days.filter((d) => d.arxiv),
    github: days.filter((d) => d.github),
    feed: days.filter((d) => d.daily).slice(0, 30),
  };
}
```

- [ ] **Step 2: レイアウトを書く**

```njk
{# site/src/_includes/base.njk #}
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <link rel="stylesheet" href="/style.css">
  <link rel="alternate" type="application/atom+xml" title="briefing" href="/feed.xml">
</head>
<body>
  <header class="site-header">
    <a class="site-name" href="/">briefing</a>
    <nav>
      <a href="/latest/">最新</a>
      <a href="/feed.xml">Feed</a>
    </nav>
  </header>
  <main>
    {{ content | safe }}
  </main>
  <footer class="site-footer">
    <a href="https://github.com/knsh14/briefing" target="_blank" rel="noopener">knsh14/briefing</a>
  </footer>
</body>
</html>
```

- [ ] **Step 3: 日付ナビの部品を書く**

```njk
{# site/src/_includes/daynav.njk #}
{# 期待する変数: day, current ("daily" | "arxiv" | "github") #}
<nav class="daynav">
  <div class="daynav-dates">
    {% if day.prev %}<a href="/{{ day.prev }}/">← {{ day.prev }}</a>{% else %}<span></span>{% endif %}
    <strong>{{ day.date }}</strong>
    {% if day.next %}<a href="/{{ day.next }}/">{{ day.next }} →</a>{% else %}<span></span>{% endif %}
  </div>
  <div class="daynav-kinds">
    <a href="/{{ day.date }}/" {% if current == "daily" %}aria-current="page"{% endif %}>統合</a>
    {% if day.arxiv %}<a href="/{{ day.date }}/arxiv/" {% if current == "arxiv" %}aria-current="page"{% endif %}>arXiv</a>{% endif %}
    {% if day.github %}<a href="/{{ day.date }}/github/" {% if current == "github" %}aria-current="page"{% endif %}>GitHub</a>{% endif %}
  </div>
</nav>
```

- [ ] **Step 4: 日付ページ 3 種を書く**

```njk
{# site/src/date.njk #}
---
pagination:
  data: digests.days
  size: 1
  alias: day
permalink: "/{{ day.date }}/"
layout: base.njk
eleventyComputed:
  title: "{{ day.date }} | briefing"
---
{% set current = "daily" %}
{% include "daynav.njk" %}
<article class="digest">
{% if day.daily %}
  {{ day.daily.html | safe }}
{% else %}
  <h1>{{ day.date }}</h1>
  <p>この日の統合サマリーはありません。</p>
{% endif %}
</article>
```

```njk
{# site/src/arxiv.njk #}
---
pagination:
  data: digests.arxiv
  size: 1
  alias: day
permalink: "/{{ day.date }}/arxiv/"
layout: base.njk
eleventyComputed:
  title: "{{ day.date }} arXiv | briefing"
---
{% set current = "arxiv" %}
{% include "daynav.njk" %}
<article class="digest">
  {{ day.arxiv.html | safe }}
</article>
```

```njk
{# site/src/github.njk #}
---
pagination:
  data: digests.github
  size: 1
  alias: day
permalink: "/{{ day.date }}/github/"
layout: base.njk
eleventyComputed:
  title: "{{ day.date }} GitHub | briefing"
---
{% set current = "github" %}
{% include "daynav.njk" %}
<article class="digest">
  {{ day.github.html | safe }}
</article>
```

- [ ] **Step 5: トップページを書く**

```njk
{# site/src/index.njk #}
---
permalink: "/"
layout: base.njk
title: "briefing"
---
<h1>briefing</h1>
<p>arXiv 新着論文と GitHub Issue/PR の日次ダイジェスト。</p>
<ul class="daylist">
{% for day in digests.days %}
  <li>
    <a class="daylist-date" href="/{{ day.date }}/">{{ day.date }}</a>
    <span class="daylist-kinds">
      {% if day.daily %}<a href="/{{ day.date }}/">統合</a>{% endif %}
      {% if day.arxiv %}<a href="/{{ day.date }}/arxiv/">arXiv</a>{% endif %}
      {% if day.github %}<a href="/{{ day.date }}/github/">GitHub</a>{% endif %}
    </span>
  </li>
{% endfor %}
</ul>
```

- [ ] **Step 6: ビルドして出力を確認する**

```bash
cd /Users/kenshi.kamata/briefing/site
npm run build
ls _site | head; ls _site/2026-08-11 _site/2026-04-07
grep -c 'href="/2026-08-11/github/"' _site/2026-08-11/index.html
grep -o 'この日の統合サマリーはありません' _site/2026-04-07/index.html
grep -o 'src="/icons/git-pull-request.svg"' _site/2026-08-11/github/index.html | head -1
grep -c 'href="/latest/"' _site/index.html
```

Expected: `_site/2026-08-11/` に `index.html`、`arxiv/`、`github/`。2026-04-07 は GitHub のみなので「ありません」の文言が出る。アイコンの src が `/icons/` に書き換わっている。`_site/2026-04-07/arxiv/` は存在しない。

- [ ] **Step 7: ブラウザで確認する**

```bash
cd /Users/kenshi.kamata/briefing/site && npm run dev
```

`http://localhost:8080/2026-08-11/` を開き、前日・翌日ナビ、統合/arXiv/GitHub の切り替え、外部リンクが新しいタブで開くことを確認する。確認後に停止する。

- [ ] **Step 8: コミット**

```bash
cd /Users/kenshi.kamata/briefing
git add site/src
git commit -m "$(cat <<'EOF'
Add date, arxiv, github pages and index

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: リダイレクト、404、Atom フィード

**Files:**
- Create: `site/src/redirects.njk`, `site/src/404.njk`, `site/src/feed.njk`

**Interfaces:**
- Consumes: `digests.latest`, `digests.feed`（Task 6）。
- Produces: `_site/_redirects`、`_site/404.html`、`_site/feed.xml`。

- [ ] **Step 1: _redirects を生成するテンプレートを書く**

```njk
{# site/src/redirects.njk #}
---
permalink: "/_redirects"
eleventyExcludeFromCollections: true
---
{% if digests.latest %}
/latest   /{{ digests.latest }}/  302
/latest/  /{{ digests.latest }}/  302
{% endif %}
```

- [ ] **Step 2: 404 ページを書く**

```njk
{# site/src/404.njk #}
---
permalink: "/404.html"
layout: base.njk
title: "見つかりません | briefing"
eleventyExcludeFromCollections: true
---
<h1>ページが見つかりません</h1>
<p><a href="/">日付一覧へ戻る</a>{% if digests.latest %}、または <a href="/{{ digests.latest }}/">最新のダイジェスト</a>{% endif %}</p>
```

- [ ] **Step 3: Atom フィードを書く**

Nunjucks の autoescape が有効なので、`{{ day.daily.html }}` は HTML エスケープされて `type="html"` の content として正しく出る。`| safe` を付けないこと。

```njk
{# site/src/feed.njk #}
---
permalink: "/feed.xml"
eleventyExcludeFromCollections: true
---
<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>briefing</title>
  <subtitle>arXiv 新着論文と GitHub Issue/PR の日次ダイジェスト</subtitle>
  <id>https://briefing.kamata.page/</id>
  <link href="https://briefing.kamata.page/"/>
  <link rel="self" type="application/atom+xml" href="https://briefing.kamata.page/feed.xml"/>
  <updated>{{ digests.latest }}T00:00:00+09:00</updated>
  <author><name>kenshi kamata</name></author>
{% for day in digests.feed %}
  <entry>
    <title>デイリーダイジェスト {{ day.date }}</title>
    <id>https://briefing.kamata.page/{{ day.date }}/</id>
    <link href="https://briefing.kamata.page/{{ day.date }}/"/>
    <updated>{{ day.date }}T00:00:00+09:00</updated>
    <content type="html">{{ day.daily.html }}</content>
  </entry>
{% endfor %}
</feed>
```

- [ ] **Step 4: ビルドして確認する**

```bash
cd /Users/kenshi.kamata/briefing/site
npm run build
cat _site/_redirects
head -12 _site/feed.xml
grep -c '<entry>' _site/feed.xml
xmllint --noout _site/feed.xml && echo "feed: well-formed"
grep -o '<h1>ページが見つかりません</h1>' _site/404.html
```

Expected: `_redirects` に `/latest` と `/latest/` の 2 行（先頭の空行は許容）。`<entry>` が 30。`xmllint` がエラーなし。

- [ ] **Step 5: コミット**

```bash
cd /Users/kenshi.kamata/briefing
git add site/src/redirects.njk site/src/404.njk site/src/feed.njk
git commit -m "$(cat <<'EOF'
Add latest redirect, 404 page and Atom feed

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: スタイル

**Files:**
- Modify: `site/src/style.css`

**Interfaces:**
- Consumes: Task 6、7 のクラス名 `site-header`, `site-name`, `site-footer`, `daynav`, `daynav-dates`, `daynav-kinds`, `digest`, `daylist`, `daylist-date`, `daylist-kinds`。

- [ ] **Step 1: style.css を書く**

```css
/* site/src/style.css */
:root {
  color-scheme: light dark;
  --bg: #fff;
  --fg: #1f2328;
  --muted: #59636e;
  --line: #d1d9e0;
  --link: #0969da;
  --accent-bg: #f6f8fa;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117;
    --fg: #e6edf3;
    --muted: #9198a1;
    --line: #3d444d;
    --link: #4493f8;
    --accent-bg: #161b22;
  }
}

* { box-sizing: border-box; }
html { font-size: 16px; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Noto Sans JP", Meiryo, sans-serif;
  line-height: 1.75;
  padding: 0 1rem;
}
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }
a[target="_blank"]::after { content: "↗"; font-size: 0.75em; margin-left: 0.15em; opacity: 0.7; }

.site-header, .site-footer, main {
  max-width: 44rem;
  margin: 0 auto;
}
.site-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 1rem 0;
  border-bottom: 1px solid var(--line);
}
.site-name { font-weight: 700; font-size: 1.25rem; color: var(--fg); }
.site-header nav a { margin-left: 1rem; }
.site-footer {
  padding: 2rem 0 3rem;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 0.875rem;
}

main { padding: 1.5rem 0; }
h1 { font-size: 1.75rem; line-height: 1.3; margin: 1rem 0; }
h2 { font-size: 1.35rem; margin: 2.5rem 0 0.75rem; padding-bottom: 0.25rem; border-bottom: 1px solid var(--line); }
h3 { font-size: 1.1rem; margin: 1.75rem 0 0.5rem; }
hr { border: 0; border-top: 1px solid var(--line); margin: 2rem 0; }
blockquote { margin: 1rem 0; padding: 0.25rem 1rem; border-left: 4px solid var(--line); color: var(--muted); }
code { background: var(--accent-bg); padding: 0.1em 0.35em; border-radius: 4px; font-size: 0.9em; }
img { vertical-align: -0.15em; }
ol, ul { padding-left: 1.5rem; }
li + li { margin-top: 0.4rem; }

.daynav {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  padding: 0.75rem 1rem;
  background: var(--accent-bg);
  border-radius: 8px;
  font-size: 0.95rem;
}
.daynav-dates { display: flex; gap: 1rem; align-items: baseline; }
.daynav-kinds a { margin-left: 0.75rem; }
.daynav-kinds a[aria-current="page"] { font-weight: 700; color: var(--fg); }

.daylist { list-style: none; padding: 0; }
.daylist li {
  display: flex;
  justify-content: space-between;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--line);
}
.daylist-date { font-variant-numeric: tabular-nums; font-weight: 600; }
.daylist-kinds a { margin-left: 0.75rem; color: var(--muted); }
```

- [ ] **Step 2: ビルドしてブラウザで確認する**

```bash
cd /Users/kenshi.kamata/briefing/site && npm run build && npm run dev
```

`http://localhost:8080/`、`/2026-08-11/`、`/2026-08-11/github/` をライトとダークの両方で確認する。アイコン SVG が行内に収まっていること、幅 400px でも横スクロールが出ないこと。確認後に停止する。

- [ ] **Step 3: コミット**

```bash
cd /Users/kenshi.kamata/briefing
git add site/src/style.css
git commit -m "$(cat <<'EOF'
Style the briefing site

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: ビルド出力のスモークチェック

**Files:**
- Create: `site/scripts/check-build.mjs`
- Modify: `site/package.json`（`test` スクリプト）

**Interfaces:**
- Consumes: `_site/` の出力、`digests.js` と同じ走査ロジック（`lib/load.js`）。
- Produces: `npm run check` が失敗時に非ゼロで終了する。`npm test` はユニットテストの後に build と check を実行する。

- [ ] **Step 1: チェックスクリプトを書く**

```js
// site/scripts/check-build.mjs
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { DATE_RE } from "../lib/load.js";

const site = resolve(import.meta.dirname, "../_site");
const repoRoot = resolve(import.meta.dirname, "../..");
const failures = [];
const must = (cond, msg) => { if (!cond) failures.push(msg); };

const latest = readdirSync(resolve(repoRoot, "daily"))
  .map((n) => DATE_RE.exec(n)?.[1])
  .filter(Boolean)
  .sort()
  .at(-1);
must(latest, "daily/ に日付ファイルがない");

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
  must(feed.includes(`<id>https://briefing.kamata.page/${latest}/</id>`), "feed.xml に最新日のエントリがない");
}

for (const dir of ["arxiv", "github"]) {
  for (const name of readdirSync(resolve(repoRoot, dir))) {
    const date = DATE_RE.exec(name)?.[1];
    if (!date) continue;
    must(existsSync(resolve(site, date, dir, "index.html")), `_site/${date}/${dir}/index.html がない`);
  }
}

if (failures.length) {
  console.error(failures.map((f) => `✘ ${f}`).join("\n"));
  process.exit(1);
}
console.log(`✔ build ok (latest: ${latest})`);
```

- [ ] **Step 2: package.json の test を拡張する**

`site/package.json` の `scripts` を次に置き換える。

```json
"scripts": {
  "build": "eleventy",
  "dev": "eleventy --serve",
  "test": "node --test && npm run build && npm run check",
  "check": "node scripts/check-build.mjs"
}
```

- [ ] **Step 3: 実行して通ることを確認する**

```bash
cd /Users/kenshi.kamata/briefing/site && npm test
```

Expected: ユニットテスト 10 件 pass、ビルド成功、`✔ build ok (latest: 2026-08-11)`。

- [ ] **Step 4: 壊して失敗することを確認する**

```bash
cd /Users/kenshi.kamata/briefing/site
rm _site/_redirects && npm run check; echo "exit=$?"
npm run build >/dev/null && npm run check
```

Expected: 1 回目は `✘ _site/_redirects がない` で exit=1。再ビルド後は成功。

- [ ] **Step 5: コミット**

```bash
cd /Users/kenshi.kamata/briefing
git add site/scripts/check-build.mjs site/package.json
git commit -m "$(cat <<'EOF'
Add build smoke check and wire it into npm test

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: push、初回デプロイ、Workers Builds 接続

このタスクはユーザーの操作を含む。エージェントはコマンドを提示し、結果を待って検証する。

**Files:** なし（設定はすべて Cloudflare 側）

**Interfaces:**
- Consumes: Task 3 の `site/wrangler.jsonc`。
- Produces: `https://briefing.kamata.page/` が配信され、main への push で自動デプロイされる。

- [ ] **Step 1: push する**

```bash
cd /Users/kenshi.kamata/briefing && git push -u origin main
```

- [ ] **Step 2: ユーザーが wrangler にログインする**

ユーザーに次を実行してもらう（ブラウザ認証）。

```bash
cd /Users/kenshi.kamata/briefing/site && npx wrangler login
```

確認:

```bash
cd /Users/kenshi.kamata/briefing/site && npx wrangler whoami
```

Expected: アカウント名が表示される。

- [ ] **Step 3: 初回デプロイ**

```bash
cd /Users/kenshi.kamata/briefing/site && npm run build && npx wrangler deploy
```

Expected: `Deployed briefing` と `briefing.kamata.page (custom domain)` が出力される。

失敗時の切り分け:
- `zone not found` 系: `kamata.page` が別アカウントか Cloudflare 外。ユーザーに確認。
- `conflicts with an existing DNS record`: `briefing` サブドメインに既存レコードがある。ダッシュボードで削除してもらう。

- [ ] **Step 4: 配信を確認する**

```bash
curl -sI https://briefing.kamata.page/latest/ | head -5
curl -sI https://briefing.kamata.page/latest | head -5
curl -s -o /dev/null -w '%{http_code}\n' https://briefing.kamata.page/2026-08-11/
curl -s -o /dev/null -w '%{http_code}\n' https://briefing.kamata.page/nope/
curl -sI https://briefing.kamata.page/feed.xml | grep -i content-type
```

Expected: 先頭 2 つが `302` で `location: /2026-08-11/`。日付ページ 200。存在しないパス 404。feed は `application/atom+xml` または `application/xml`。DNS 伝播直後は数分待つ。

- [ ] **Step 5: ユーザーが Workers Builds を接続する**

ユーザーに Cloudflare ダッシュボードで次を行ってもらう。

1. Workers & Pages → `briefing` → Settings → Build → Connect to Git。
2. GitHub App を許可し `knsh14/briefing` を選ぶ。
3. Production branch `main`、Root directory `site`、Build command `npm ci && npm run build`、Deploy command は既定の `npx wrangler deploy` のまま。
4. 保存。

- [ ] **Step 6: 自動デプロイを確認する**

```bash
cd /Users/kenshi.kamata/briefing
git commit --allow-empty -m "Trigger Workers Builds" && git push
```

ダッシュボードの Builds でビルドが成功することを確認し、`curl -sI https://briefing.kamata.page/latest/` が引き続き 302 を返すことを確認する。

---

### Task 11: til からの撤去

**Files (til):**
- Delete: `arxiv/`, `github-digest/`, `daily-digest/`, `arxiv-digest/`
- Delete: `.claude/skills/{arxiv-digest,github-digest,daily-digest}`, `.agents/skills/{arxiv-digest,github-digest,daily-digest}`
- Delete: `scripts/generate_rss.py`
- Modify: `.claude/settings.json`（fetch スクリプトの許可を削除）

**Interfaces:**
- Consumes: Task 10 が完了し、briefing が配信されていること。

- [ ] **Step 1: til の未コミット状態を確認する**

```bash
cd /Users/kenshi.kamata/til && git status --short | grep -v '^??'
```

Expected: `AGENTS.md`、`arxiv-digest/SKILL.md`、`github-digest/SKILL.md`、`github-digest/repos.json`、`doc/…`、`transcript/…` の変更。arxiv-digest と github-digest の未コミット変更は briefing に取り込み済みなので、ディレクトリごと削除して問題ない。

- [ ] **Step 2: 削除する**

```bash
cd /Users/kenshi.kamata/til
git rm -r -q arxiv github-digest daily-digest arxiv-digest scripts/generate_rss.py \
  .claude/skills/arxiv-digest .claude/skills/github-digest .claude/skills/daily-digest \
  .agents/skills/arxiv-digest .agents/skills/github-digest .agents/skills/daily-digest
git status --short | grep -c '^D '
```

Expected: 削除数が 100 を超える（Markdown 約 96 件 + スキル、スクリプト）。

- [ ] **Step 3: settings.json から許可を外す**

`.claude/settings.json` を次に置き換える。

```json
{
  "permissions": {
    "allow": [
      "Bash(mkdir -p:*)",
      "Bash(wc -l:*)"
    ]
  }
}
```

- [ ] **Step 4: AGENTS.md や doc の未コミット変更を巻き込んでいないことを確認する**

```bash
cd /Users/kenshi.kamata/til && git diff --cached --stat | tail -3 && git diff --stat | tail -5
```

Expected: staged はすべて削除と `.claude/settings.json`。unstaged に `AGENTS.md`、`doc/`、`transcript/` の変更が残っている。

- [ ] **Step 5: コミットして push**

```bash
cd /Users/kenshi.kamata/til
git add .claude/settings.json
git commit -m "$(cat <<'EOF'
Move daily digest pipeline to knsh14/briefing

The arxiv/github/daily digests, their skills, fetch scripts and the
Atom feed generator now live in https://github.com/knsh14/briefing
and are published at https://briefing.kamata.page/.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
git push
```

- [ ] **Step 6: briefing 側で daily-digest スキルを一度実行して確認する**

ユーザーが `/Users/kenshi.kamata/briefing` で Claude Code を開き `daily-digest` を実行する。`daily/<今日>.md`、`arxiv/<今日>.md`、`github/<今日>.md` が生成され、push 後に `https://briefing.kamata.page/latest/` が今日の日付へ飛ぶことを確認する。

---

## Self-Review

- **Spec coverage:** 3 系列の公開（Task 1、6）、URL 構造と `/latest/`（Task 6、7）、Eleventy（Task 3）、Workers Builds（Task 10）、briefing への移設（Task 1、2）、ディレクトリ改名とリンク置換（Task 1、2）、スキル正本の整理とシンボリックリンク（Task 2）、フィード（Task 7）、404（Task 7）、CSS とダーク対応（Task 8）、wrangler.jsonc（Task 3）、テスト 3 種（Task 4、5、9）、デプロイ後 curl（Task 10）、til 撤去（Task 11）。すべて対応するタスクがある。
- **Spec からの変更:** `icons/` を `.claude/skills/github-digest/icons/` ではなく `github/icons/` に置く。GitHub 上で Markdown を開いたときの相対参照 `icons/x.svg` を切らないため。Task 2 Step 3 の SKILL.md 書き換えと Task 3 の passthrough がこれに従う。
- **Type consistency:** `Day` の形（`date`, `daily|arxiv|github: {html}|null`, `prev`, `next`）は Task 4 の実装、Task 6 のテンプレート、Task 9 で一致。`digests.{days,latest,arxiv,github,feed}` は Task 6 で定義し Task 7、9 で使用。`renderMarkdown(text): string` は Task 5 で定義し Task 6 が `buildDays` の `render` に渡す。
