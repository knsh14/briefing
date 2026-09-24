// site/src/_data/digests.js
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { KINDS, SERIES, readSeries, buildDays, buildPages } from "../../lib/load.js";
import { renderMarkdown } from "../../lib/render.js";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");

export default function () {
  const days = buildDays(
    Object.fromEntries(SERIES.map((key) => [key, readSeries(resolve(repoRoot, key))])),
    renderMarkdown,
  );
  return {
    days,
    kinds: KINDS,
    pages: buildPages(days),
    latest: days[0]?.date ?? null,
    feed: days.filter((d) => d.daily).slice(0, 30),
  };
}
