import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DATE_RE, readSeries, buildDays } from "../lib/load.js";

const upper = (s) => s.toUpperCase();

test("DATE_RE matches only YYYY-MM-DD.md", () => {
  assert.ok(DATE_RE.test("2026-08-11.md"));
  assert.equal(DATE_RE.exec("2026-08-11.md")[1], "2026-08-11");
  assert.ok(!DATE_RE.test("SKILL.md"));
  assert.ok(!DATE_RE.test("2026-08-11.txt"));
  assert.ok(!DATE_RE.test("icons"));
});

test("readSeries returns only date files with their text", (t) => {
  const dir = mkdtempSync(join(tmpdir(), "briefing-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  writeFileSync(join(dir, "2026-08-11.md"), "# a");
  writeFileSync(join(dir, "2026-08-10.md"), "# b");
  writeFileSync(join(dir, "SKILL.md"), "skip");
  mkdirSync(join(dir, "icons"));
  const out = readSeries(dir).sort((x, y) => x.date.localeCompare(y.date));
  assert.deepEqual(out, [
    { date: "2026-08-10", text: "# b" },
    { date: "2026-08-11", text: "# a" },
  ]);
});

test("buildDays groups by date, newest first, with prev/next", () => {
  const days = buildDays(
    {
      daily: [{ date: "2026-08-11", text: "d11" }],
      arxiv: [{ date: "2026-08-11", text: "a11" }, { date: "2026-08-10", text: "a10" }],
      github: [{ date: "2026-08-09", text: "g09" }],
    },
    upper,
  );
  assert.deepEqual(days.map((d) => d.date), ["2026-08-11", "2026-08-10", "2026-08-09"]);
  assert.deepEqual(days[0], {
    date: "2026-08-11",
    daily: { html: "D11" },
    arxiv: { html: "A11" },
    github: null,
    prev: "2026-08-10",
    next: null,
  });
  assert.deepEqual(days[1], {
    date: "2026-08-10",
    daily: null,
    arxiv: { html: "A10" },
    github: null,
    prev: "2026-08-09",
    next: "2026-08-11",
  });
  assert.equal(days[2].prev, null);
  assert.equal(days[2].next, "2026-08-10");
});

test("buildDays returns [] when every series is empty", () => {
  assert.deepEqual(buildDays({ daily: [], arxiv: [], github: [] }, upper), []);
});
