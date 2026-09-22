# briefing サイト設計

日付: 2026-09-22
対象リポジトリ: `knsh14/briefing`
配信ドメイン: `briefing.kamata.page`

## TL;DR

til リポジトリで運用してきた日次ダイジェスト（arXiv 新着論文、GitHub Issue/PR、両者の統合サマリー）の仕組みを `knsh14/briefing` に移設し、Eleventy で静的サイトを生成して Cloudflare Workers の静的アセット配信で公開する。
デプロイは Cloudflare Workers Builds が main への push を検知して行う。
URL は日付を先頭に置き、`/latest/` は最新日へリダイレクトする。

## 背景

- til リポジトリの `daily-digest` スキルが `arxiv/`、`github-digest/`、`daily-digest/` に `YYYY-MM-DD.md` を毎日生成し、git push まで自動化している。
- 生成物は GitHub 上の Markdown としてしか読めず、日付を指定してブラウザで開ける場所がない。
- til は調査レポート、音声、PDF 資料を含む雑多なリポジトリで、日次ダイジェストの仕組みを切り出したいという要望があった。

## ゴール

- `https://briefing.kamata.page/YYYY-MM-DD/` でその日の統合サマリーが読める。
- 日付ページから同日の arXiv 詳細と GitHub 詳細へサイト内で遷移できる。
- `https://briefing.kamata.page/latest/` が最新日へ飛ぶ。
- daily-digest スキルが push した数分後にサイトが更新される。
- ダイジェストの仕組み（スキル、取得スクリプト、出力 Markdown、サイト）が briefing リポジトリで完結する。

## 非ゴール

- 検索、タグ、フィルタなどの動的 UI。
- til の `doc/`（deep-research レポート）や `transcript/` の公開。
- 過去 Markdown の git 履歴の保持。ファイルのコピーで移す。
- 認証やアクセス制限。内容は既に公開リポジトリにある。

## 決定事項と根拠

| 論点 | 決定 | 根拠 |
|---|---|---|
| 公開対象 | daily、arxiv、github の 3 系列 | 統合サマリーが既に詳細ファイルへ相対リンクを張っている |
| URL 構造 | 日付を先頭に置く。`/latest/` を追加 | 「その日のところに飛べる」を URL に日付を打つだけで満たす |
| SSG | Eleventy | Markdown をそのまま扱え、依存が軽い。将来別の SSG へ移るのも容易 |
| デプロイ | Cloudflare Workers Builds | push 起点で自動化でき、GitHub 側にトークンを置かない |
| リポジトリ | 新規 `knsh14/briefing` に仕組みごと移設 | 内容と描画コードを同じコミットで揃え、til から分離する |
| 名前 | briefing | 「今日知っておくべきことを短く伝える」という形式に合う |
| 履歴 | コピーのみ | コミットメッセージが日付だけで、ファイル名にも日付があるため失う情報がない |

## リポジトリ構成

```
briefing/
├── .claude/
│   ├── settings.json                 fetch スクリプトの Bash 許可
│   └── skills/
│       ├── arxiv-digest/             SKILL.md, categories.json, scripts/fetch_arxiv.py
│       ├── github-digest/            SKILL.md, repos.json, scripts/fetch_github.py, icons/
│       └── daily-digest/             SKILL.md
├── .agents/
│   └── skills -> ../.claude/skills   シンボリックリンク
├── arxiv/YYYY-MM-DD.md
├── github/YYYY-MM-DD.md              til の github-digest/*.md
├── daily/YYYY-MM-DD.md               til の daily-digest/*.md
├── site/                             Eleventy プロジェクト（後述）
├── docs/superpowers/specs/           本書
├── package.json                      textlint 一式
├── .textlintrc.json
├── .gitignore
└── README.md
```

### 出力ディレクトリ名の変更

til の `github-digest/` を `github/`、`daily-digest/` を `daily/` に改名する。
URL のセグメント名と一致させるためである。
これに伴い次を書き換える。

- 3 つの SKILL.md 内の出力パスと `git add` 対象。
- daily-digest の統合サマリーテンプレートにある相対リンク `../github-digest/` を `../github/` に変更。
- 既存 Markdown 内の `](../github-digest/` を `](../github/` に一括置換。

### スキルの正本

til には各スキルの SKILL.md が 3 箇所（トップレベル、`.claude/skills/`、`.agents/skills/`）にあり内容が食い違っている。
トップレベル版（未コミットの変更を含む）が最新で、japanese-tech-writing による校正ステップを含む。
これを `.claude/skills/` に置き、`.agents/skills` はシンボリックリンクにする。
スクリプト、`categories.json`、`repos.json`（`sunnypilot/sunnypilot` 追加済みの未コミット版）、`icons/` もスキルディレクトリ配下に置く。

### 移さないもの

- `scripts/generate_rss.py`。フィードは Eleventy が生成する。
- deep-research、podcast-script のスキルと `doc/`、`transcript/`、`voice/`、`sources/`。

## サイト設計

### site/ の構成

```
site/
├── package.json          @11ty/eleventy のみ。scripts: build, dev, test
├── eleventy.config.js
├── wrangler.jsonc
├── .gitignore            node_modules/, _site/
├── src/
│   ├── _data/digests.js  3 ディレクトリを走査して日付ごとに束ねる
│   ├── _includes/base.njk
│   ├── index.njk         /
│   ├── date.njk          /{date}/
│   ├── arxiv.njk         /{date}/arxiv/
│   ├── github.njk        /{date}/github/
│   ├── redirects.njk     /_redirects
│   ├── feed.njk          /feed.xml
│   ├── 404.njk           /404.html
│   └── style.css
├── lib/
│   ├── load.js           ファイル走査と日付グルーピング（純粋関数）
│   └── render.js         markdown-it 設定とリンク書き換え
└── test/
    ├── load.test.js
    └── render.test.js
```

### データモデル

`_data/digests.js` は `lib/load.js` と `lib/render.js` を使い、次の配列を新しい日付順で返す。

```js
[
  {
    date: "2026-08-11",
    daily:  { html: "<h1>…</h1>…" } | null,
    arxiv:  { html: "…" } | null,
    github: { html: "…" } | null,
    prev: "2026-08-10" | null,   // 一つ古い日付
    next: "2026-08-12" | null,   // 一つ新しい日付
  },
  …
]
```

- 対象ファイルはファイル名が `^\d{4}-\d{2}-\d{2}\.md$` に一致するものだけ。それ以外は無視する。
- 3 系列のうち 1 つでも存在する日付はページを生成する。欠けている系列は `null`。
- Markdown 先頭の `# 見出し` はそのまま HTML にし、テンプレートは本文用の `<h1>` を別途出さない。ページの `<title>` は日付と系列名（例: `2026-08-11 arXiv | briefing`）から組む。

### リンクと画像の書き換え

`lib/render.js` は markdown-it の `link_open` と `image` レンダラーを差し替える。
正規表現による HTML 後処理は行わない。

| 元の記述 | 書き換え後 |
|---|---|
| `../arxiv/YYYY-MM-DD.md` | `/YYYY-MM-DD/arxiv/` |
| `../github/YYYY-MM-DD.md`、`../github-digest/YYYY-MM-DD.md` | `/YYYY-MM-DD/github/` |
| `icons/foo.svg` | `/icons/foo.svg` |
| `http://` または `https://` で始まる外部リンク | そのまま。`target="_blank"` と `rel="noopener"` を付与 |
| 上記以外の相対リンク | そのまま |

`github-digest` の `icons/` は passthrough copy で `_site/icons/` に配置する。

### ページ

| URL | テンプレート | 内容 |
|---|---|---|
| `/` | index.njk | 日付一覧。新しい日が先頭。各行に daily、arxiv、github へのリンク。欠けている系列はリンクを出さない |
| `/{date}/` | date.njk | 統合サマリー本文。上部に前日・翌日ナビと同日の arxiv、github へのリンク。daily が `null` なら「この日の統合サマリーはありません」と表示 |
| `/{date}/arxiv/` | arxiv.njk | arXiv 詳細。上部に `/{date}/` へ戻るリンクと前日・翌日ナビ |
| `/{date}/github/` | github.njk | GitHub 詳細。同上 |
| `/latest/`、`/latest` | redirects.njk | `_redirects` に 302 行を 2 本出す |
| `/feed.xml` | feed.njk | Atom。daily がある日を 1 エントリとし、本文は daily の HTML。最新 30 件 |
| `/404.html` | 404.njk | トップへ戻るリンクのみ |

`_redirects` の内容例:

```
/latest   /2026-08-11/  302
/latest/  /2026-08-11/  302
```

### 見た目

- CSS は `style.css` 1 ファイル。フレームワーク、JS なし。
- `prefers-color-scheme` でダーク対応。
- 本文幅は 44rem 程度、日本語向けフォントスタック。
- 外部リンクと内部リンクは見分けられる程度の最小限の装飾。

## Cloudflare 設定

### wrangler.jsonc

```jsonc
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

- `main` は assets 専用 Worker では省略可（公式ドキュメントで確認済み）。
- `html_handling` は既定の `auto-trailing-slash` を使う。`foo/index.html` を `/foo/` で配信するため Eleventy の出力と一致する。
- `_redirects` は assets ディレクトリ直下に置く。省略時のコードは 302。
- カスタムドメインはデプロイ時に DNS レコードと証明書が自動作成される。前提は `kamata.page` ゾーンが同一アカウントにあり、`briefing` に既存 CNAME がないこと。

### Workers Builds

ダッシュボードで 1 回だけ設定する。

| 項目 | 値 |
|---|---|
| リポジトリ | `knsh14/briefing` |
| 本番ブランチ | `main` |
| ルートディレクトリ | `site` |
| ビルドコマンド | `npm ci && npm run build` |
| デプロイコマンド | 既定の `npx wrangler deploy` |
| Node | 既定の 24 系 |

## 移行手順

1. briefing に上記構成でファイルをコピーする。Markdown 内リンクの一括置換、SKILL.md のパス修正、`.agents/skills` シンボリックリンク作成。
2. `site/` を実装し、`npm test` と `npm run build` をローカルで通す。`npx @11ty/eleventy --serve` で表示確認。
3. briefing を push する。
4. ユーザーが `npx wrangler login` を実行し、`site/` で `npx wrangler deploy` を一度手動実行する。Worker とカスタムドメインが作られ、`https://briefing.kamata.page/latest/` が 302 を返すことを確認する。
5. ダッシュボードで `briefing` Worker に Git 接続し、Workers Builds を設定する。空コミットを push して自動デプロイを確認する。
6. til から次を削除するコミットを 1 つ入れる。`arxiv/`、`github-digest/`、`daily-digest/`、`arxiv-digest/`、`.claude/skills/{arxiv-digest,github-digest,daily-digest}`、`.agents/skills/{同}`、`scripts/generate_rss.py`、`.claude/settings.json` の fetch スクリプト許可。til の AGENTS.md と doc、transcript の未コミット変更には触れない。

## テスト

- `test/load.test.js`: 日付ファイルのみ拾うこと、3 系列を日付で束ねること、片方欠けで `null` になること、prev/next の連結、新しい日付順のソート。
- `test/render.test.js`: 表の各書き換え規則、外部リンクへの属性付与、書き換え対象外の相対リンクが変わらないこと。
- ビルドスモーク（`npm run build` 後）: `_site/_redirects` に最新日付の行が 2 本あること、`_site/<最新日付>/index.html`、`_site/feed.xml`、`_site/404.html`、`_site/icons/git-pull-request.svg` が存在すること。
- デプロイ後: `curl -I https://briefing.kamata.page/latest/` が 302 で `Location: /<最新日付>/` を返すこと。

## 未確認事項

- `kamata.page` ゾーンが Cloudflare の同一アカウントにあること。手順 4 で判明する。
- Workers Builds の build watch paths の既定は全パスなので、README だけの変更でもビルドが走る。問題になれば `site/*`、`daily/*`、`arxiv/*`、`github/*` に絞る。
