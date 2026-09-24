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

保存した `hf-papers/YYYY-MM-DD.md` を、次の2段階で校正・修正する。

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
- 対象日と論文数（フォールバックしたかどうか）
- 校正結果

## エラーハンドリング

- スクリプトが異常終了した場合は、標準エラーの内容を報告して停止する。
