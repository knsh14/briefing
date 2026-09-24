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
  - "Bash(git worktree list:*)"
  - "Bash(git -C * pull --ff-only)"
  - "Bash(git -C * add *)"
  - "Bash(git -C * commit -m *)"
  - "Bash(git -C * push origin main)"
  - "Bash(git -C * status:*)"
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

生成できたファイルを **main ブランチ** にコミットし、リモートの main へプッシュする。作業用ブランチや PR は作らない。コミットメッセージは生成対象日（YYYY-MM-DD）。

まず main をチェックアウトしているディレクトリ（`MAIN_DIR`）を特定する。通常は現在のディレクトリだが、セッションが別ブランチの worktree（`.claude/worktrees/...`）で動いている場合は元のリポジトリのルートになる。

```bash
MAIN_DIR=$(git worktree list --porcelain | awk '/^worktree /{p=$2} /^branch refs\/heads\/main$/{print p}')
git -C "$MAIN_DIR" pull --ff-only
# 現在のディレクトリが MAIN_DIR と異なる場合は、生成したファイルを MAIN_DIR の同じパスへコピーする
git -C "$MAIN_DIR" add arxiv/YYYY-MM-DD.md hf-papers/YYYY-MM-DD.md hackernews/YYYY-MM-DD.md github/YYYY-MM-DD.md trending/YYYY-MM-DD.md blogs/YYYY-MM-DD.md company-blogs/YYYY-MM-DD.md daily/YYYY-MM-DD.md
git -C "$MAIN_DIR" commit -m "YYYY-MM-DD"
git -C "$MAIN_DIR" push origin main
```

注意点:

- `MAIN_DIR` に今回生成したファイル以外の未コミット変更があっても、それらは `git add` しない（生成したファイルだけを明示的に指定する）。
- `git pull --ff-only` が失敗した場合（main が分岐しているなど）は、原因を報告して停止する。
- `YYYY-MM-DD` はダイジェスト対象日（ファイル名と一致する日付）。当日生成なら今日の日付。
- Step 1 で失敗した情報源のファイルは `git add` に含めない（存在するファイルのみを指定する）。
- `.cache/` はコミットしない（`.gitignore` 済み）。
- コミット成功後に `git -C "$MAIN_DIR" status` で結果を確認する。
- pre-commit フックなどで失敗した場合は、原因を報告して停止する（`--no-verify` は使わない）。
- コミット成功後に `git push origin main` でリモートの main へ反映する。
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
