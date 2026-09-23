import { defineConfig } from "vitepress";

export default defineConfig({
  title: "Matchday",
  description: "Self-hosted football data, served through one stable REST API.",

  themeConfig: {
    // No logo yet - docs/assets/banner.svg is a wide banner (1200x320),
    // not a square icon, and would look squished in the nav slot. A
    // proper small mark is future polish, not blocking.
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
