// site/eleventy.config.js
export default function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy({ "../github/icons": "icons" });
  eleventyConfig.addPassthroughCopy("src/style.css");

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
