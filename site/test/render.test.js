import { test } from "node:test";
import assert from "node:assert/strict";
import { rewriteHref, rewriteSrc, isExternal, renderMarkdown } from "../lib/render.js";

test("rewriteHref maps sibling digest links to site URLs", () => {
  assert.equal(rewriteHref("../arxiv/2026-08-11.md"), "/2026-08-11/arxiv/");
  assert.equal(rewriteHref("../github/2026-08-11.md"), "/2026-08-11/github/");
  assert.equal(rewriteHref("../github-digest/2026-08-11.md"), "/2026-08-11/github/");
});

test("rewriteHref leaves other links alone", () => {
  assert.equal(rewriteHref("https://arxiv.org/abs/2608.07776"), "https://arxiv.org/abs/2608.07776");
  assert.equal(rewriteHref("#section"), "#section");
  assert.equal(rewriteHref("../doc/foo.md"), "../doc/foo.md");
  assert.equal(rewriteHref("../arxiv/notes.md"), "../arxiv/notes.md");
});

test("rewriteSrc maps icons/ to /icons/", () => {
  assert.equal(rewriteSrc("icons/git-pull-request.svg"), "/icons/git-pull-request.svg");
  assert.equal(rewriteSrc("https://example.com/a.png"), "https://example.com/a.png");
});

test("isExternal detects http(s) links", () => {
  assert.ok(isExternal("https://github.com/x"));
  assert.ok(isExternal("http://example.com"));
  assert.ok(!isExternal("/2026-08-11/"));
  assert.ok(!isExternal("mailto:a@b"));
});

test("renderMarkdown rewrites links, adds attributes to external links, rewrites images", () => {
  const html = renderMarkdown(
    [
      "[詳細](../github-digest/2026-08-11.md)",
      "",
      "[GH](https://github.com/neovim/neovim/pull/40924)",
      "",
      "![PR](icons/git-pull-request.svg) title",
    ].join("\n"),
  );
  assert.match(html, /<a href="\/2026-08-11\/github\/">詳細<\/a>/);
  assert.match(html, /<a href="https:\/\/github.com\/neovim\/neovim\/pull\/40924" target="_blank" rel="noopener">GH<\/a>/);
  assert.match(html, /<img src="\/icons\/git-pull-request.svg" alt="PR">/);
  assert.doesNotMatch(html, /target="_blank"[^>]*href="\/2026/);
});

test("renderMarkdown keeps raw HTML disabled and renders headings", () => {
  const html = renderMarkdown("# タイトル\n\n<script>x</script>");
  assert.match(html, /<h1>タイトル<\/h1>/);
  assert.match(html, /&lt;script&gt;/);
});
