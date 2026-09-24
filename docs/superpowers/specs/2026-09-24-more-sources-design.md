# 情報源の追加 設計

## TL;DR

daily-digest に5つの情報源を加える。
Hacker News、Hugging Face Daily Papers、個人ブログ、企業ブログ、GitHub Trending である。
情報源ごとに `*-digest` スキルを1つ作り、取得は Python スクリプト、要約は Claude が担う。
daily-digest は7本の subagent を並列に走らせ、横断ハイライトと情報源ごとの短い紹介からなる統合サマリーを作る。
サイトには情報源ごとの詳細ページを5種類足す。

## 背景

現状の daily-digest は arxiv 新着論文と、指定した GitHub リポジトリの Issue/PR だけを扱う。
arxiv は量が多いわりに注目度の情報がなく、GitHub は監視対象の外で起きた話題が入らない。
海外のエンジニアがよく使う情報源を足して、「コミュニティが何に注目しているか」を日々の情報収集に混ぜたい。

## ゴール

- 5つの情報源を、既存スキルと同じ「取得スクリプト＋設定 JSON＋SKILL.md」の形で追加する。
- 各情報源の詳細ダイジェストを `<dir>/YYYY-MM-DD.md` に日本語で保存する。
- daily-digest の統合サマリーで、全情報源を横断したハイライトを出す。
- サイトで各詳細ページを閲覧できる。
- フィードやキーワードは設定ファイルの編集だけで増減できる。

## 非ゴール

- X / Bluesky / Reddit / Podcast の取得。
- RSS を持たないサイトの HTML スクレイピング（GitHub Trending を除く）。
- 既存スキル名の変更（`daily-digest` はそのまま）。
- 統合サマリーのテーマ別再編成。

## 設計

### スキルと出力

| スキル | 出力 | 設定ファイル | 取得スクリプト |
|---|---|---|---|
| `hackernews-digest` | `hackernews/YYYY-MM-DD.md` | `keywords.json` | `fetch_hackernews.py` |
| `hf-papers-digest` | `hf-papers/YYYY-MM-DD.md` | なし | `fetch_hf_papers.py` |
| `blog-digest` | `blogs/YYYY-MM-DD.md` | `feeds.json` | `fetch_feeds.py` |
| `company-blog-digest` | `company-blogs/YYYY-MM-DD.md` | `feeds.json` | `blog-digest` の `fetch_feeds.py` を共用 |
| `trending-digest` | `trending/YYYY-MM-DD.md` | なし | `fetch_trending.py` |

スキルは `.claude/skills/<name>/` に置く。
`.agents/skills` は `.claude/skills` へのシンボリックリンクなので追加作業はない。

`company-blog-digest` は `../blog-digest/scripts/fetch_feeds.py --config <自分の feeds.json>` を実行する。
フィード取得の実装を1本に保つためである。

### 取得期間

| 情報源 | 期間 |
|---|---|
| Hacker News | 実行時点から直近24時間 |
| GitHub Trending | GitHub の `since=daily` に従う |
| HF Daily Papers | 実行日の Daily Papers。空なら前日分にフォールバックし、その旨を JSON に記録する |
| 個人ブログ・企業ブログ | 出力ディレクトリ内の、今日より前の最新ファイルの日付のローカル時刻 0:00 以降。ファイルがなければ直近7日。遡る上限は7日 |

ブログの期間を前回出力基準にするのは、実行しなかった日の記事を取りこぼさないためである。
スクリプトは `--state-dir <出力ディレクトリ>` を受け取り、そこにある今日より前の最新ファイルの日付 D を探す。
期間の開始は D のローカル時刻 0:00 とし、7日前より古ければ7日前に切り上げる。
ファイル名の日付と今日の日付はどちらもローカル時刻の日付なので、期間の開始もローカル時刻にそろえる。
D 当日の記事は前回と重複しうるが、取りこぼしよりましとする。
`--since YYYY-MM-DD` を渡したときはそれを優先する。

### スクリプト共通の約束

- 結果は JSON で出す。`--out <path>` を渡せばそのファイルに書き、省略時は標準出力に出す。進捗とエラーは標準エラーに出す。
  SKILL.md からは `--out .cache/<name>-YYYY-MM-DD.json` を使い、Read で読む。Bash の出力上限に収まらない量になるためである。`.cache/` は `.gitignore` に入れる。
- JSON は `indent=2` で書き、1つの文字列値が2,000字を超えないようにする。Read ツールは2,000字を超える行を切り詰めるためである。
  本文のように長いテキストは JSON に入れず、`fetch_feeds.py` のように行を折り返したテキストファイルに出す。
- 1件の失敗で全体を止めない。失敗は `error` または `errors` フィールドに記録する。
- 外部パッケージが要るものは PEP 723 のインライン依存で宣言し、`uv run <script>.py` で実行する。
  既存の `uv run python <script>.py` 形式ではインライン依存が読まれないためである。
- HTTP には User-Agent を付け、タイムアウトとリトライ（最大3回、指数バックオフ）を入れる。
- パース処理は純粋関数に分け、ネットワーク取得と切り離してテストできるようにする。

### fetch_hackernews.py

- Algolia HN Search API（`https://hn.algolia.com/api/v1/search`）を使う。
- `tags=story` と `numericFilters=created_at_i>{24時間前}` で取得し、ポイント降順で上位30件を選ぶ。
- `keywords.json` の各キーワードについて同じ期間で検索し、10ポイント以上の記事を拾う。
  上位30件と重複するものは除き、どのキーワードに一致したかを記録する。
- 各記事について HN 公式 Firebase API（`https://hacker-news.firebaseio.com/v0/item/{id}.json`）の `kids` を取り、表示順で先頭のトップレベルコメントを最大3件付ける。`kids` は HN での表示順（ランク順）に並んでいる。削除済み・dead のコメントは飛ばす。各コメントは500字で切る。
- キーワード一致は合計20件までとし、ポイント降順で残す。
- キーワード検索は `restrictSearchableAttributes=title` と `typoTolerance=false` を付け、タイトルへの完全一致に絞る。
- 各記事のフィールドは `id`、`title`、`url`、`hn_url`、`points`、`num_comments`、`author`、`created_at`、`comments`、`matched_keywords`。

`keywords.json` の初期値:

```json
{
  "keywords": ["LLM", "Claude", "Anthropic", "openpilot", "comma.ai", "self-driving", "autonomous driving", "robotics", "Neovim", "Vim", "Ghostty", "terminal", "uv", "Python", "Rust", "QMK", "mechanical keyboard"],
  "min_points": 10
}
```

### fetch_hf_papers.py

- `https://huggingface.co/api/daily_papers?date=YYYY-MM-DD` を使う。
- 日付の既定値は UTC の今日。空なら UTC の前日にフォールバックする。
- 各論文のフィールドは `arxiv_id`、`title`、`abstract`（1,700字で切る）、`upvotes`、`num_comments`、`hf_url`、`arxiv_url`、`github_url`（あれば）、`ai_summary`（あれば）。
- upvote 降順で並べる。

### fetch_feeds.py

- 引数は `--config <feeds.json>`（必須）、`--out-dir <dir>`（必須）、`--state-dir <dir>`、`--since YYYY-MM-DD`。
- `feedparser` で RSS / Atom を読み、公開日時（なければ更新日時）が期間内の記事を取り出す。
  日時が取れない記事は除く。
- 本文はフィードの全文（`content`）が十分な長さ（目安 1,500 字以上）ならそれを使う。
  足りなければ記事ページを取得し、`trafilatura` で本文を抽出する。
  抽出にも失敗したらフィードの概要で代替し、`body_source` に `feed` / `page` / `summary` を記録する。
- 本文は8,000字で切り詰め、200字ごとに折り返す。
- 1フィードあたりの記事数は `feeds.json` の `max_items_per_feed`（既定5）までとし、新しい順に残す。
- 出力は `--out-dir` に書く。
  - 記事が1件以上あるフィードごとに `NN-<slug>.txt`（`NN` は feeds.json での順番）。中身はフィード名、URL、記事ごとのタイトル・リンク・公開日時・著者・`body_source`・本文。
  - `manifest.json` に `{since, feeds: [{name, url, file, count}], errors: [{name, url, error}]}`。
- 既存の `--out-dir` の中身は実行開始時に消す。ただし `manifest.json` がない空でないディレクトリは消さず、標準エラーに理由を出して終了コード 1 で止まる。パスの指定を誤って無関係なファイルを消さないためである。

`feeds.json` の形:

```json
{
  "max_items_per_feed": 5,
  "feeds": [
    {"name": "Simon Willison", "url": "https://simonwillison.net/atom/everything/"}
  ]
}
```

各フィードには任意で `include_links_from`（ページURLの配列）を指定できる。指定した場合、そのページ群を取得してリンクを抽出し、フィードの記事のうちリンクがいずれかと一致するものだけを残す（本文取得や `max_items_per_feed` の適用より前に絞り込む）。ページの取得に一つでも失敗した場合は、全件を含める形にフォールバックせず、フィード全体を失敗として `manifest.json` の `errors` に記録する。

### fetch_trending.py

- `https://github.com/trending?since=daily` の HTML を `beautifulsoup4` で解析し、最大25件を取る（実際の掲載数は日によって十数件）。
- 各リポジトリのフィールドは `repo`、`url`、`description`、`language`、`stars`、`forks`、`stars_today`、`readme_excerpt`。
- `readme_excerpt` は `gh api repos/{repo}/readme` の先頭1,200字。JSON エスケープ後の長さが1,900字に達する場合は、その手前で切る。取れなければ空文字。
- HTML 構造が変わって0件になったら、`error` を立てて終了コード 1 を返す。

### フィード初期リスト

2026-09-24 に全 URL を取得し、`feedparser` で記事を読めることを確かめた。

個人ブログ（`blog-digest/feeds.json`）:

| 名前 | URL |
|---|---|
| Simon Willison | https://simonwillison.net/atom/everything/ |
| The Pragmatic Engineer | https://newsletter.pragmaticengineer.com/feed |
| Import AI | https://importai.substack.com/feed |
| Latent Space | https://www.latent.space/feed |
| Ahead of AI | https://magazine.sebastianraschka.com/feed |
| Lilian Weng | https://lilianweng.github.io/index.xml |
| Mitchell Hashimoto | https://mitchellh.com/feed.xml |
| Julia Evans | https://jvns.ca/atom.xml |
| Will Larson | https://lethain.com/feeds/ |
| Cal Newport | https://calnewport.com/feed/ |
| Kent Beck (Tidy First?) | https://tidyfirst.substack.com/feed |
| Martin Fowler | https://martinfowler.com/feed.atom |
| Charity Majors | https://charity.wtf/feed/ |
| Camille Fournier (Elided Branches) | https://www.elidedbranches.com/feeds/posts/default |
| Paul Graham（非公式） | http://www.aaronsw.com/2002/feeds/pgessays.rss |
| Dan Luu | https://danluu.com/atom.xml |
| Addy Osmani | https://addyo.substack.com/feed |
| Eugene Yan | https://eugeneyan.com/rss/ |
| Hamel Husain | https://hamel.dev/index.xml |

企業ブログ（`company-blog-digest/feeds.json`）:

| 名前 | URL |
|---|---|
| OpenAI | https://openai.com/news/rss.xml |
| Google DeepMind | https://deepmind.google/blog/feed/basic/ |
| Hugging Face | https://huggingface.co/blog/feed.xml |
| comma.ai | https://blog.comma.ai/feed.xml |
| GitHub | https://github.blog/feed/ |
| Cloudflare | https://blog.cloudflare.com/rss/ |
| Astral | https://astral.sh/blog/rss.xml |
| Netflix TechBlog | https://netflixtechblog.com/feed |
| NVIDIA Technical Blog | https://developer.nvidia.com/blog/feed/ |
| Waymo | https://waymo.com/blog/rss.xml |
| Wayve | https://wayve.ai/wp-content/themes/wayve/rss-feed.php（`include_links_from` で `thinking/category/engineering/` と `research/` に絞り込む） |
| Meta Engineering | https://engineering.fb.com/feed/ |
| Microsoft Research | https://www.microsoft.com/en-us/research/feed/ |
| Stripe | https://stripe.com/blog/feed.rss |
| Airbnb | https://medium.com/feed/airbnb-engineering |
| Spotify | https://engineering.atspotify.com/feed/ |
| Shopify | https://shopify.engineering/blog.atom |
| Dropbox | https://dropbox.tech/feed |
| Discord | https://discord.com/blog/rss.xml |
| Slack | https://slack.engineering/feed/ |
| Pinterest | https://medium.com/feed/pinterest-engineering |
| Figma | https://www.figma.com/blog/feed/atom.xml |
| Vercel | https://vercel.com/atom |
| Datadog | https://www.datadoghq.com/blog/index.xml |

公式フィードが見つからず除外したもの: Anthropic、Uber Engineering、LinkedIn Engineering。

### 各スキルの出力フォーマット

どのスキルも既存の `github-digest` にならい、先頭に「ハイライト」（3〜5件）、続いて本体を置く。
要約は取得データに忠実に書き、外部知識で補わない。
タイトルは原語のまま、説明は日本語で書く。

- **hackernews-digest**: 「上位記事」と「キーワード一致」の2節。各記事にポイント、コメント数、何の話題か（1〜2文）、HN での反応（2〜3文）を書く。記事本文は取得しないので、話題の説明はタイトルとコメントから読み取れる範囲にとどめる。記事へのリンクと HN スレッドへのリンクを両方置く。
- **hf-papers-digest**: upvote 順に論文を並べ、日本語タイトル、要約（2〜3文）、upvote 数、arxiv / HF / GitHub へのリンクを書く。前日分へのフォールバックが起きたら冒頭に明記する。
- **blog-digest / company-blog-digest**: フィードごとに節を立て、記事ごとに要約（3〜5文）と「なぜ読む価値があるか」（1文）を書く。記事が0件のフィードは省く。取得に失敗したフィードは末尾に一覧で出す。記事が1件もない日は「対象期間に新着記事はありません」と書く。
  要約は `manifest.json` を読んだあと、フィードのファイルを1つずつ Read して進める。subagent の中からさらに subagent を起動できるとは限らないので、並列化には頼らない。
- **trending-digest**: 順位順にリポジトリを並べ、何をするものか（1〜2文）、言語、スター総数と当日のスター数を書く。README から読み取れる特徴があれば1文足す。

### daily-digest の変更

Step 1 は7本の subagent を並列に起動する。
全 subagent に `model: "opus"` を指定する既存の約束は維持する。
失敗した情報源があっても残りで続行し、全部が失敗したときだけ停止して報告する。

統合サマリー（`daily/YYYY-MM-DD.md`）の構成:

1. **本日のハイライト**（5〜8件）。全情報源を横断して選ぶ。複数の情報源に同じ話題が現れたら優先し、どの情報源に出たかを併記する。
2. **情報源ごとの節**。arxiv → HF Papers → Hacker News → GitHub → Trending → 個人ブログ → 企業ブログの順。各節は2〜3件と詳細ページへの相対リンク（`../<dir>/YYYY-MM-DD.md`）。
3. 失敗した情報源の節には「取得に失敗しました」と書く。

Step 3（校正）は変更しない。
Step 4 の `git add` は生成できたファイルだけを対象にする。
Step 5 の完了報告に新しい情報源の件数を加える。

`allowed-tools` と `.claude/settings.json` の `permissions.allow` に `Bash(uv run */hackernews-digest/scripts/fetch_hackernews.py*)` ほか新スクリプト4本分を足す。
新出力ディレクトリ用の `mkdir -p` の許可は足さない。出力ディレクトリは Write ツールがファイルを書くときに作るためである。
`allowed-tools` の `git add` は `Bash(git add *)` に広げる。生成できたファイルだけを指定するので、対象の組み合わせが実行ごとに変わるためである。

### サイトの変更

- `lib/load.js` の `SERIES` に `hackernews`、`hf-papers`、`trending`、`blogs`、`company-blogs` を足す。1日分のオブジェクトは全キーを `null` で初期化する。
- `src/_data/digests.js` で新ディレクトリを読み込み、キーごとの配列を返す。
- 種類ごとのページテンプレート（現状 `arxiv.njk`、`github.njk`）を1つの `kind.njk` にまとめる。`(日付, 種類)` の組を平たく並べたデータを `digests.js` で作り、それをページ分割して `/{date}/{kind}/` を出す。
- 種類のラベルと順序は `lib/load.js` に `KINDS` として1か所で定義し、`daynav.njk` と `index.njk` はそれをループする。ラベルは「arXiv」「HF Papers」「HN」「GitHub」「Trending」「Blogs」「企業ブログ」。
- `eleventy.config.js` の watch 対象に新ディレクトリを足す。
- トップページの説明文と README を更新する。
- 既存の URL（`/{date}/arxiv/`、`/{date}/github/`）は変えない。

## テスト

- サイト: `test/load.test.js` に、新シリーズを含む日と一部の種類だけがある日のケースを足す。`cd site && npm test` でユニットテスト、ビルド、スモークチェックが通ること。
- スクリプト: 各スクリプトのパース関数に pytest を書く。テストは `.claude/skills/<skill>/tests/` に置き、入力は実レスポンスを縮めたサンプルをテスト内に埋め込む。pytest は `uv run --with pytest ... pytest <dir>` で実行する。
- 手動確認: 実装の最後に各スクリプトを実ネットワークで1回ずつ実行し、件数とエラーを確認する。その後 daily-digest を1回通しで実行し、サイトのビルドで7種類のページが出ることを確かめる。

## 代替案

- **1つの `news-digest` にまとめる**: スキルとページが少なく済む。情報源を個別に実行したり外したりしにくいため採らなかった。
- **WebFetch に任せる（スクリプトなし）**: すぐ作れる。フィード約45本と本文の取得が遅くトークンも多く、期間判定もぶれるため採らなかった。

## 懸念点

- **実行時間とトークン**: ブログ本文の要約は記事数に比例する。フィード43本で普段は1日数件だが、初回や期間が7日に広がった日は数十件になる。フィードあたり5件の上限で抑えるが、それでも多い日は要約が長時間かかる。
- **GitHub Trending の HTML 変更**: 公式 API がなく、構造が変わると壊れる。0件なら失敗として扱い、黙って空のページを出さない。
- **非公式フィード**: Paul Graham のフィードは第三者が運用しており、止まる可能性がある。
- **HF Daily Papers の反映タイミング**: 実行時刻によっては当日分が空である。前日分へのフォールバックで対応するが、前日の daily-digest と同じ論文が出ることがある。

## 未決定事項

- RSS を持たない企業ブログ（Anthropic、Uber、LinkedIn）の扱い。今回は除外し、必要なら別途検討する。
