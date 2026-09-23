import DefaultTheme from "vitepress/theme";
import type { Theme } from "vitepress";

// Extended (not replaced) so the signup/dashboard pages - see
// site/account/*.md - can drop in interactive Vue components alongside
// VitePress's own default layout, without forking the whole theme.
export default {
  extends: DefaultTheme,
} satisfies Theme;
