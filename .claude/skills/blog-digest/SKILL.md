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

保存した `blogs/YYYY-MM-DD.md` を、次の2段階で校正・修正する。

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
- 対象期間、フィードごとの記事数
- 取得に失敗したフィード
- 校正結果

## エラーハンドリング

- スクリプトが異常終了した場合（設定ファイルが読めないなど）は、標準エラーの内容を報告して停止する。
- フィード単位の失敗は `errors` に入るだけなので、残りで続行する。
