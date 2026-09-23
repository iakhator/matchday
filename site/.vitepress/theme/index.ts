import { h } from "vue";
import DefaultTheme from "vitepress/theme";
import type { Theme } from "vitepress";
import "./custom.css";

import Icon from "./components/Icon.vue";
import MethodBadge from "./components/MethodBadge.vue";
import EndpointMeta from "./components/EndpointMeta.vue";
import ParamCard from "./components/ParamCard.vue";
import ErrorCode from "./components/ErrorCode.vue";
import AuthPanel from "./components/AuthPanel.vue";
import Dashboard from "./components/Dashboard.vue";
import UserNavStatus from "./components/UserNavStatus.vue";

// Extended (not replaced) so the signup/dashboard pages - see
// site/account/*.md - can drop in interactive Vue components alongside
// VitePress's own default layout, without forking the whole theme.
export default {
  extends: DefaultTheme,
  Layout: () =>
    h(DefaultTheme.Layout, null, {
      // Mounted in both slots, not one: VitePress hides the desktop nav
      // bar below 768px and the mobile menu screen above it, so exactly
      // one of these two is ever visible - but which one depends on
      // viewport, not on anything this component controls itself.
      "nav-bar-content-after": () => h(UserNavStatus),
      "nav-screen-content-after": () => h(UserNavStatus),
    }),
  enhanceApp({ app }) {
    // Registered globally rather than imported per-page: these are the
    // API-reference building blocks (endpoint header, param cards, error
    // codes) used repeatedly across reference/*.md, and a per-file
    // <script setup> import block on every endpoint page would just be
    // the same five lines copy-pasted everywhere.
    app.component("Icon", Icon);
    app.component("MethodBadge", MethodBadge);
    app.component("EndpointMeta", EndpointMeta);
    app.component("ParamCard", ParamCard);
    app.component("ErrorCode", ErrorCode);
    app.component("AuthPanel", AuthPanel);
    app.component("Dashboard", Dashboard);
  },
} satisfies Theme;
