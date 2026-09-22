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
