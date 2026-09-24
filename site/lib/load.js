import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

export const DATE_RE = /^(\d{4}-\d{2}-\d{2})\.md$/;

// 詳細ページの種類。並び順がナビゲーションとトップページの表示順になる。
export const KINDS = [
  { key: "arxiv", label: "arXiv" },
  { key: "hf-papers", label: "HF Papers" },
  { key: "hackernews", label: "HN" },
  { key: "github", label: "GitHub" },
  { key: "trending", label: "Trending" },
  { key: "blogs", label: "Blogs" },
  { key: "company-blogs", label: "企業ブログ" },
];

// リポジトリ直下のディレクトリ名と一致する。
export const SERIES = ["daily", ...KINDS.map((k) => k.key)];

export function readSeries(dir) {
  if (!existsSync(dir)) return [];
  const out = [];
  for (const name of readdirSync(dir)) {
    const m = DATE_RE.exec(name);
    if (!m) continue;
    out.push({ date: m[1], text: readFileSync(join(dir, name), "utf8") });
  }
  return out;
}

export function buildDays(series, render) {
  const byDate = new Map();
  for (const key of SERIES) {
    for (const { date, text } of series[key] ?? []) {
      if (!byDate.has(date)) {
        byDate.set(date, { date, ...Object.fromEntries(SERIES.map((k) => [k, null])) });
      }
      byDate.get(date)[key] = { html: render(text) };
    }
  }
  const days = [...byDate.values()].sort((a, b) => b.date.localeCompare(a.date));
  days.forEach((day, i) => {
    day.next = i > 0 ? days[i - 1].date : null;
    day.prev = i < days.length - 1 ? days[i + 1].date : null;
  });
  return days;
}

export function buildPages(days) {
  return days.flatMap((day) =>
    KINDS.filter((kind) => day[kind.key]).map((kind) => ({ day, kind })),
  );
}
