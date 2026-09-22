import { existsSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { DATE_RE } from "../lib/load.js";

const site = resolve(import.meta.dirname, "../_site");
const repoRoot = resolve(import.meta.dirname, "../..");
const failures = [];
const must = (cond, msg) => { if (!cond) failures.push(msg); };

const newestDate = (dir) =>
  readdirSync(resolve(repoRoot, dir))
    .map((n) => DATE_RE.exec(n)?.[1])
    .filter(Boolean)
    .sort()
    .at(-1);

const latest = ["daily", "arxiv", "github"]
  .map((dir) => newestDate(dir))
  .filter(Boolean)
  .sort()
  .at(-1);
must(latest, "daily/, arxiv/, github/ に日付ファイルがない");

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

for (const dir of ["arxiv", "github"]) {
  for (const name of readdirSync(resolve(repoRoot, dir))) {
    const date = DATE_RE.exec(name)?.[1];
    if (!date) continue;
    must(existsSync(resolve(site, date, dir, "index.html")), `_site/${date}/${dir}/index.html がない`);
  }
}

if (failures.length) {
  console.error(failures.map((f) => `✘ ${f}`).join("\n"));
  process.exit(1);
}
console.log(`✔ build ok (latest: ${latest}, latest daily: ${latestDaily})`);
