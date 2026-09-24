import { existsSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { DATE_RE, KINDS, SERIES } from "../lib/load.js";

const site = resolve(import.meta.dirname, "../_site");
const repoRoot = resolve(import.meta.dirname, "../..");
const failures = [];
const must = (cond, msg) => { if (!cond) failures.push(msg); };

const datesIn = (dir) => {
  const path = resolve(repoRoot, dir);
  if (!existsSync(path)) return [];
  return readdirSync(path).map((n) => DATE_RE.exec(n)?.[1]).filter(Boolean);
};
const newestDate = (dir) => datesIn(dir).sort().at(-1);

const latest = SERIES.map((dir) => newestDate(dir)).filter(Boolean).sort().at(-1);
must(latest, `${SERIES.map((s) => `${s}/`).join(", ")} のどれにも日付ファイルがない`);

const latestDaily = newestDate("daily");
must(latestDaily, "daily/ に日付ファイルがない");

for (const p of ["index.html", "404.html", "feed.xml", "_redirects", "style.css", "icons/git-pull-request.svg", "icons/issue-opened.svg", `${latest}/index.html`]) {
  must(existsSync(resolve(site, p)), `_site/${p} がない`);
}

if (existsSync(resolve(site, "_redirects"))) {
  const redirects = readFileSync(resolve(site, "_redirects"), "utf8");
  must(redirects.includes(`/latest   /${latest}/  302`), `_redirects に /latest → /${latest}/ がない`);
  must(redirects.includes(`/latest/  /${latest}/  302`), `_redirects に /latest/ → /${latest}/ がない`);
}

if (existsSync(resolve(site, "feed.xml"))) {
  const feed = readFileSync(resolve(site, "feed.xml"), "utf8");
  must(feed.includes(`<id>https://briefing.kamata.page/${latestDaily}/</id>`), "feed.xml に最新日のエントリがない");
}

for (const { key } of KINDS) {
  for (const date of datesIn(key)) {
    must(existsSync(resolve(site, date, key, "index.html")), `_site/${date}/${key}/index.html がない`);
  }
}

// Markdown の相対リンク（../<kind>/YYYY-MM-DD.md など）が書き換えられずに残るとサイト上で 404 になる。
// feed.xml の本文は HTML エスケープされているので、両方の表記を探す。
const LEAKED_HREF_RE = /href=(?:"|&quot;)\.\.\//;
const builtFiles = existsSync(site)
  ? readdirSync(site, { recursive: true }).filter((p) => p.endsWith(".html") || p === "feed.xml")
  : [];
for (const p of builtFiles) {
  must(!LEAKED_HREF_RE.test(readFileSync(resolve(site, p), "utf8")), `_site/${p} に書き換えられていない href="../ が残っている`);
}

if (failures.length) {
  console.error(failures.map((f) => `✘ ${f}`).join("\n"));
  process.exit(1);
}
console.log(`✔ build ok (latest: ${latest}, latest daily: ${latestDaily})`);
