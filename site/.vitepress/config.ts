import { defineConfig } from "vitepress";

// Sidebar/nav item `text` is rendered via v-html by VitePress's own
// VPSidebarItem/VPNavBarMenuLink components (not escaped interpolation),
// which is what makes this possible without patching the theme - see
// node_modules/vitepress/dist/client/theme-default/components/
// VPSidebarItem.vue. Inline SVG (not <img src="...">) is deliberate:
// stroke="currentColor" only inherits the surrounding link's color, and
// therefore themes correctly with light/dark mode, when the SVG is part
// of the same DOM/CSS tree - an <img>-loaded SVG is an isolated document
// and currentColor inside it would just resolve to black.
//
// Path data below is copied as-is from lucide-static (ISC licensed),
// not hand-drawn - see site/public/icons/*.svg for the source files
// these came from.
const ICONS: Record<string, string> = {
  rocket:
    '<path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" /><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09" /><path d="M9 12a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.4 22.4 0 0 1-4 2z" /><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 .05 5 .05" />',
  shieldCheck:
    '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" /><path d="m9 12 2 2 4-4" />',
  gitBranch:
    '<path d="M15 6a9 9 0 0 0-9 9V3" /><circle cx="18" cy="6" r="3" /><circle cx="6" cy="18" r="3" />',
  activity:
    '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2" />',
  scale:
    '<path d="M12 3v18" /><path d="m19 8 3 8a5 5 0 0 1-6 0zV7" /><path d="M3 7h1a17 17 0 0 0 8-2 17 17 0 0 0 8 2h1" /><path d="m5 8 3 8a5 5 0 0 1-6 0zV7" /><path d="M7 21h10" />',
  trophy:
    '<path d="M10 14.66V17a1 1 0 0 1-1 1 2 2 0 0 0-2 2v2" /><path d="M14 14.66V17a1 1 0 0 0 1 1 2 2 0 0 1 2 2v2" /><path d="M17.916 10H19.5A2.5 2.5 0 0 0 22 7.5V5a1 1 0 0 0-1-1h-3" /><path d="M4 22h16" /><path d="M6 9a6 6 0 0 0 12 0V3a1 1 0 0 0-1-1H7a1 1 0 0 0-1 1z" /><path d="M6.084 10H4.5A2.5 2.5 0 0 1 2 7.5V5a1 1 0 0 1 1-1h3" />',
  users:
    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><path d="M16 3.128a4 4 0 0 1 0 7.744" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><circle cx="9" cy="7" r="4" />',
  calendar:
    '<path d="M8 2v3" /><path d="M16 2v3" /><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18" />',
  listOrdered:
    '<path d="M11 5h10" /><path d="M11 12h10" /><path d="M11 19h10" /><path d="M4 4h1v5" /><path d="M4 9h2" /><path d="M6.5 20H3.4c0-1 2.6-1.925 2.6-3.5a1.5 1.5 0 0 0-2.6-1.02" />',
  star: '<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z" />',
  target:
    '<circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" />',
  percent:
    '<line x1="19" x2="5" y1="5" y2="19" /><circle cx="6.5" cy="6.5" r="2.5" /><circle cx="17.5" cy="17.5" r="2.5" />',
  search: '<path d="m21 21-4.34-4.34" /><circle cx="11" cy="11" r="8" />',
  keyRound:
    '<path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z" /><circle cx="16.5" cy="7.5" r=".5" fill="currentColor" />',
  heartPulse:
    '<path d="M2 9.5a5.5 5.5 0 0 1 9.591-3.676.56.56 0 0 0 .818 0A5.49 5.49 0 0 1 22 9.5c0 2.29-1.5 4-3 5.5l-5.492 5.313a2 2 0 0 1-3 .019L5 15c-1.5-1.5-3-3.2-3-5.5" /><path d="M3.22 13H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27" />',
  logIn:
    '<path d="m10 17 5-5-5-5" /><path d="M15 12H3" /><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />',
  layoutDashboard:
    '<rect width="7" height="9" x="3" y="3" rx="1" /><rect width="7" height="5" x="14" y="3" rx="1" /><rect width="7" height="9" x="14" y="12" rx="1" /><rect width="7" height="5" x="3" y="16" rx="1" />',
};

function withIcon(name: keyof typeof ICONS, label: string): string {
  return (
    `<svg class="vp-sidebar-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" ` +
    `viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ` +
    `stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>${label}`
  );
}

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

  vite: {
    server: {
      // Without this, an occupied 5173 makes Vite silently drift to
      // 5174/5175/... - which then no longer matches GATEWAY_CORS_ORIGINS
      // and every /account/* API call fails with an opaque CORS error
      // that looks nothing like "wrong port". Fail loudly instead.
      strictPort: true,
      headers: {
        // The documented fix for Firebase Auth's "Cross-Origin-Opener-
        // Policy policy would block the window.closed call" warning on
        // signInWithPopup - without it the popup-closed poll can't check
        // window.closed. Harmless without this (sign-in still completes),
        // but noisy and worth silencing properly rather than ignoring.
        "Cross-Origin-Opener-Policy": "same-origin-allow-popups",
      },
    },
  },

  themeConfig: {
    // Square crop of the ball mark from docs/assets/banner.svg (which is
    // a 1200x320 wide banner, wrong aspect ratio for a nav slot) -
    // see site/public/icon.svg.
    logo: "/icon.svg",

    nav: [
      { text: "Guide", link: "/guide/getting-started" },
      { text: "Reference", link: "/reference/" },
      { text: "Get an API key", link: "/account/signup" },
    ],

    sidebar: [
      {
        text: "Guide",
        items: [
          { text: withIcon("rocket", "Getting started"), link: "/guide/getting-started" },
          {
            text: withIcon("shieldCheck", "Authentication & rate limits"),
            link: "/guide/authentication",
          },
          {
            text: withIcon("gitBranch", "API versioning & stability"),
            link: "/guide/versioning",
          },
          {
            text: withIcon("activity", "How fresh is the data?"),
            link: "/guide/data-freshness",
          },
          {
            text: withIcon("scale", "Data licensing & attribution"),
            link: "/guide/licensing",
          },
        ],
      },
      {
        // One page per endpoint (its own URL, deep-linkable) rather than
        // one long page for the whole API - matches how the request to
        // restructure this section specifically asked for it.
        text: "Football Data",
        items: [
          { text: withIcon("trophy", "Leagues"), link: "/reference/leagues" },
          { text: withIcon("users", "Teams"), link: "/reference/teams" },
          { text: withIcon("calendar", "Fixtures"), link: "/reference/fixtures" },
          { text: withIcon("listOrdered", "Standings"), link: "/reference/standings" },
          { text: withIcon("star", "Season scorers"), link: "/reference/season-scorers" },
          {
            text: withIcon("activity", "Advanced match stats"),
            link: "/reference/advanced-stats",
          },
          { text: withIcon("target", "Goal events"), link: "/reference/goals" },
          { text: withIcon("percent", "Odds"), link: "/reference/odds" },
          { text: withIcon("search", "Lookup"), link: "/reference/lookup" },
          { text: withIcon("keyRound", "Account"), link: "/reference/account" },
          { text: withIcon("heartPulse", "Health"), link: "/reference/health" },
        ],
      },
      {
        text: "Account",
        items: [
          { text: withIcon("logIn", "Sign up"), link: "/account/signup" },
          { text: withIcon("layoutDashboard", "Dashboard"), link: "/account/dashboard" },
        ],
      },
    ],

    socialLinks: [{ icon: "github", link: "https://github.com/iakhator/matchday" }],
  },
});
