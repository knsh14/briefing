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

保存した `hackernews/YYYY-MM-DD.md` を、次の2段階で校正・修正する。

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

### Step 5: 完了報告

- 保存したファイルパス
- 上位記事数とキーワード一致数
- `errors` に入ったキーワードがあればその旨
- 校正結果（規範修正件数、textlint の自動修正件数 / 手動対応が必要な件数）

## エラーハンドリング

- スクリプトが異常終了した場合は、標準エラーの内容を報告して停止する。
- コメント取得に失敗した記事（`error` フィールドあり）は、コメントなしとして扱う。
