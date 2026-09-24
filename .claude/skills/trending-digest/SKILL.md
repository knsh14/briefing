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
- 終了コードが0以外で `--out` のファイルが書かれていない場合は、Trending ページ自体を取得できなかったことを表す。標準エラーの内容を報告して停止する。

### Step 2: 読み込み

Read で `.cache/trending-YYYY-MM-DD.json` を読む。
`repos` の各リポジトリは `rank`、`repo`、`url`、`description`、`language`、`stars`、`forks`、`stars_today`、`readme_excerpt` を持つ。

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

保存した `trending/YYYY-MM-DD.md` を、次の2段階で校正・修正する。

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
- リポジトリ数と README を取得できた数
- 校正結果

## エラーハンドリング

- 終了コード1で `--out` のファイルに `error` がある場合（解析失敗）は、GitHub の HTML 構造が変わった可能性があるとして報告し、停止する。
- 終了コードが0以外で `--out` のファイルが書かれていない場合は、Trending ページ自体を取得できなかったとして標準エラーの内容を報告し、停止する。
