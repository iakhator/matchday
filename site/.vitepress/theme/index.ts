import DefaultTheme from "vitepress/theme";
import type { Theme } from "vitepress";
import "./custom.css";

import Icon from "./components/Icon.vue";
import MethodBadge from "./components/MethodBadge.vue";
import EndpointMeta from "./components/EndpointMeta.vue";
import ParamCard from "./components/ParamCard.vue";
import ErrorCode from "./components/ErrorCode.vue";

// Extended (not replaced) so the signup/dashboard pages - see
// site/account/*.md - can drop in interactive Vue components alongside
// VitePress's own default layout, without forking the whole theme.
export default {
  extends: DefaultTheme,
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
  },
} satisfies Theme;
