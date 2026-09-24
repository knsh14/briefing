// site/eleventy.config.js
import { SERIES } from "./lib/load.js";

export default function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy({ "../github/icons": "icons" });
  eleventyConfig.addPassthroughCopy("src/style.css");

  for (const key of SERIES) eleventyConfig.addWatchTarget(`../${key}/`);
  eleventyConfig.addWatchTarget("./lib/");

  return {
    dir: {
      input: "src",
      output: "_site",
      includes: "_includes",
      data: "_data",
    },
    markdownTemplateEngine: false,
    htmlTemplateEngine: "njk",
  };
}
