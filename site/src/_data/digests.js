// site/src/_data/digests.js
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { readSeries, buildDays } from "../../lib/load.js";
import { renderMarkdown } from "../../lib/render.js";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");

export default function () {
  const days = buildDays(
    {
      daily: readSeries(resolve(repoRoot, "daily")),
      arxiv: readSeries(resolve(repoRoot, "arxiv")),
      github: readSeries(resolve(repoRoot, "github")),
    },
    renderMarkdown,
  );
  return {
    days,
    latest: days[0]?.date ?? null,
    arxiv: days.filter((d) => d.arxiv),
    github: days.filter((d) => d.github),
    feed: days.filter((d) => d.daily).slice(0, 30),
  };
}
