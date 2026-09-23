import { defineConfig } from "vitepress";

export default defineConfig({
  title: "Matchday",
  description: "Self-hosted football data, served through one stable REST API.",

  head: [
    ["link", { rel: "icon", type: "image/svg+xml", href: "/icon.svg" }],
    ["link", { rel: "preconnect", href: "https://fonts.googleapis.com" }],
    [
      "link",
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossorigin: "" },
    ],
    [
      "link",
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap",
      },
    ],
  ],

  themeConfig: {
    // Square crop of the ball mark from docs/assets/banner.svg (which is
    // a 1200x320 wide banner, wrong aspect ratio for a nav slot) -
    // see site/public/icon.svg.
    logo: "/icon.svg",

    nav: [
      { text: "Guide", link: "/guide/getting-started" },
      { text: "Reference", link: "/reference/endpoints" },
      { text: "Get an API key", link: "/account/signup" },
    ],

    sidebar: [
      {
        text: "Guide",
        items: [
          { text: "Getting started", link: "/guide/getting-started" },
          { text: "Authentication & rate limits", link: "/guide/authentication" },
          { text: "API versioning & stability", link: "/guide/versioning" },
          { text: "How fresh is the data?", link: "/guide/data-freshness" },
          { text: "Data licensing & attribution", link: "/guide/licensing" },
        ],
      },
      {
        text: "Reference",
        items: [{ text: "Endpoints", link: "/reference/endpoints" }],
      },
      {
        text: "Account",
        items: [
          { text: "Sign up", link: "/account/signup" },
          { text: "Dashboard", link: "/account/dashboard" },
        ],
      },
    ],

    socialLinks: [{ icon: "github", link: "https://github.com/iakhator/matchday" }],
  },
});
