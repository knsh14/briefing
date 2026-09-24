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
