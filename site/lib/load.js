import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

export const DATE_RE = /^(\d{4}-\d{2}-\d{2})\.md$/;

export function readSeries(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const m = DATE_RE.exec(name);
    if (!m) continue;
    out.push({ date: m[1], text: readFileSync(join(dir, name), "utf8") });
  }
  return out;
}

const SERIES = ["daily", "arxiv", "github"];

export function buildDays(series, render) {
  const byDate = new Map();
  for (const key of SERIES) {
    for (const { date, text } of series[key] ?? []) {
      if (!byDate.has(date)) {
        byDate.set(date, { date, daily: null, arxiv: null, github: null });
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
