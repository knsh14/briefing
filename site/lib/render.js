import MarkdownIt from "markdown-it";
import { KINDS } from "./load.js";

// 旧ディレクトリ名 → サイト上の種類。既存の daily/*.md が ../github-digest/ を参照している。
const KIND_ALIASES = { "github-digest": "github" };
const SIBLING_DIRS = [...KINDS.map((k) => k.key), ...Object.keys(KIND_ALIASES)];
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const SIBLING_RE = new RegExp(
  `^\\.\\./(${SIBLING_DIRS.map(escapeRe).join("|")})/(\\d{4}-\\d{2}-\\d{2})\\.md(#.*)?$`,
);
const ICON_RE = /^icons\/([\w.-]+\.svg)$/;

export function rewriteHref(href) {
  const m = SIBLING_RE.exec(href);
  if (!m) return href;
  const kind = KIND_ALIASES[m[1]] ?? m[1];
  return `/${m[2]}/${kind}/${m[3] ?? ""}`;
}

export function rewriteSrc(src) {
  const m = ICON_RE.exec(src);
  return m ? `/icons/${m[1]}` : src;
}

export function isExternal(href) {
  return /^https?:\/\//i.test(href);
}

export function createMarkdown() {
  const md = new MarkdownIt({ html: false, linkify: false, typographer: false });

  const defaultLinkOpen =
    md.renderer.rules.link_open ??
    ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options));
  md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    const token = tokens[idx];
    const hrefIdx = token.attrIndex("href");
    if (hrefIdx >= 0) {
      const href = rewriteHref(token.attrs[hrefIdx][1]);
      token.attrs[hrefIdx][1] = href;
      if (isExternal(href)) {
        token.attrSet("target", "_blank");
        token.attrSet("rel", "noopener");
      }
    }
    return defaultLinkOpen(tokens, idx, options, env, self);
  };

  const defaultImage = md.renderer.rules.image;
  md.renderer.rules.image = (tokens, idx, options, env, self) => {
    const token = tokens[idx];
    const srcIdx = token.attrIndex("src");
    if (srcIdx >= 0) token.attrs[srcIdx][1] = rewriteSrc(token.attrs[srcIdx][1]);
    return defaultImage(tokens, idx, options, env, self);
  };

  return md;
}

const shared = createMarkdown();

export function renderMarkdown(text) {
  return shared.render(text);
}
