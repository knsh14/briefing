---
name: daily-digest
description: "arxiv 新着論文と GitHub リポジトリアクティビティを同時に取得し、個別ダイジェストに加えて横断的な統合サマリーを生成するスキル。「daily-digest」「今日のダイジェスト」「毎日のまとめ」「デイリーダイジェスト」などで発動する。"
allowed-tools:
  - "Bash(uv run python */arxiv-digest/scripts/fetch_arxiv.py*)"
  - "Bash(uv run python */github-digest/scripts/fetch_github.py*)"
  - "Bash(git worktree list:*)"
  - "Bash(git -C * pull --ff-only)"
  - "Bash(git -C * add arxiv/* github/* daily/*)"
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

arxiv 新着論文ダイジェストと GitHub リポジトリダイジェストを **並列** で同時実行し、それぞれの個別出力に加えて、両ソースを横断する統合サマリーを生成・保存する。

## ワークフロー

### Step 1: 既存スキルの並列実行

2つの subagent を **並列に** 起動し、既存スキルをそれぞれ実行させる。

```
Agent(model=opus, name="arxiv-agent")  ──→ Skill("arxiv-digest")  ──→ arxiv/YYYY-MM-DD.md
Agent(model=opus, name="github-agent") ──→ Skill("github-digest") ──→ github/YYYY-MM-DD.md
```

> **全ての subagent は `model: "opus"` を指定すること。**

各 subagent へのプロンプト:

- **arxiv-agent**: 「arxiv-digest スキルを実行してください。完了したら、保存したファイルパスとカテゴリごとの論文数を報告してください。」
- **github-agent**: 「github-digest スキルを実行してください。完了したら、保存したファイルパスとリポジトリごとの Issue/PR 数を報告してください。」

両エージェントの完了を待つ。片方が失敗しても、もう片方の結果で続行する。

### Step 2: 統合サマリー生成

両方の個別ダイジェストファイルを読み込み、横断的な統合サマリーを生成する。

1. `arxiv/YYYY-MM-DD.md` を読み込む
2. `github/YYYY-MM-DD.md` を読み込む
3. 以下のフォーマットで統合サマリーを生成する

#### 統合サマリーのフォーマット

```markdown
# デイリーダイジェスト — YYYY-MM-DD

## 本日のハイライト

arxiv 論文と GitHub アクティビティから横断的に注目トピックを5〜8件選定する。

選定基準:
- arxiv 論文と GitHub の動向に関連性がある（例: 論文の手法が OSS で実装されている）
- 大きなインパクトが見込まれる（画期的な手法、大規模な機能追加）
- 複数の領域にまたがる影響がある

1. **[{タイトル}]({link})** ({arxiv/GitHub リポジトリ名}) — {選定理由(日本語)}
2. ...

---

## arxiv 新着論文

> 詳細: [arxiv/YYYY-MM-DD.md](../arxiv/YYYY-MM-DD.md)

カテゴリごとに注目論文を1〜2件ピックアップし、簡潔に紹介する。
個別ファイルの要約をさらに圧縮し、各論文1〜2文で記載する。

### {カテゴリ名}
- **[{日本語タイトル}]({link})** — {1〜2文の要約}
- ...

---

## GitHub アクティビティ

> 詳細: [github/YYYY-MM-DD.md](../github/YYYY-MM-DD.md)

リポジトリごとに主要な動きを簡潔に紹介する。
個別ファイルの要約をさらに圧縮し、各項目1〜2文で記載する。

### {owner/repo}
- **[{タイトル}]({link})** (`#{number}`) — {1〜2文の要約}
- ...
```

要約の注意点:
- 個別ファイルの内容に忠実に書く。新たな推測や外部知識で補わない
- ハイライトセクションでは arxiv と GitHub の関連性を積極的に見つける
- 圧縮しても情報の正確さは維持する

#### 片方のみ成功した場合

- arxiv のみ成功: GitHub セクションを「取得に失敗しました」と記載し、arxiv の内容で統合サマリーを生成する
- GitHub のみ成功: arxiv セクションを「取得に失敗しました」と記載し、GitHub の内容で統合サマリーを生成する

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

生成した3つのファイルを **main ブランチ** にコミットし、リモートの main へプッシュする。作業用ブランチや PR は作らない。コミットメッセージは生成対象日（YYYY-MM-DD）。

まず main をチェックアウトしているディレクトリ（`MAIN_DIR`）を特定する。通常は現在のディレクトリだが、セッションが別ブランチの worktree（`.claude/worktrees/...`）で動いている場合は元のリポジトリのルートになる。

```bash
MAIN_DIR=$(git worktree list --porcelain | awk '/^worktree /{p=$2} /^branch refs\/heads\/main$/{print p}')
git -C "$MAIN_DIR" pull --ff-only
# 現在のディレクトリが MAIN_DIR と異なる場合は、生成した3ファイルを MAIN_DIR の同じパスへコピーする
git -C "$MAIN_DIR" add arxiv/YYYY-MM-DD.md github/YYYY-MM-DD.md daily/YYYY-MM-DD.md
git -C "$MAIN_DIR" commit -m "YYYY-MM-DD"
git -C "$MAIN_DIR" push origin main
```

注意点:

- `MAIN_DIR` に今回の3ファイル以外の未コミット変更があっても、それらは `git add` しない（3ファイルだけを明示的に指定する）。
- `git pull --ff-only` が失敗した場合（main が分岐しているなど）は、原因を報告して停止する。
- `YYYY-MM-DD` はダイジェスト対象日（ファイル名と一致する日付）。当日生成なら今日の日付。
- Step 1 で片方が失敗していた場合、存在するファイルのみを `git add` する。
- コミット成功後に `git -C "$MAIN_DIR" status` で結果を確認する。
- pre-commit フックなどで失敗した場合は、原因を報告して停止する（`--no-verify` は使わない）。
- コミット成功後に `git push origin main` でリモートの main へ反映する。
- プッシュが失敗した場合（リモート拒否・認証エラー・upstream 未設定など）は、原因を報告して停止する。コミット自体は完了しているため、ファイルは失われない。

### Step 5: 完了報告

生成が完了したら、以下を報告する:

- 保存した3つのファイルパス:
  - `arxiv/YYYY-MM-DD.md`
  - `github/YYYY-MM-DD.md`
  - `daily/YYYY-MM-DD.md`
- カテゴリごとの論文数
- リポジトリごとの Issue/PR 数
- 取得できなかったソースがあればその旨
- コミットハッシュ
- プッシュの結果（成功／失敗、失敗時はその原因）

## エラーハンドリング

- 片方のスキルが失敗しても、もう片方の結果で統合サマリーを生成する
- 両方失敗した場合は、エラー内容をユーザーに報告する
- `daily/` ディレクトリが存在しない場合は作成する
