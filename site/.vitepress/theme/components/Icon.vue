<script setup lang="ts">
// Real Lucide icons (@lucide/vue), not hand-drawn paths - matches
// site/.vitepress/config.ts's sidebar icons, which come from the same
// icon set (lucide-static) for visual consistency across the site.
import {
  ShieldCheck,
  SlidersHorizontal,
  LayoutGrid,
  AlertTriangle,
  KeyRound,
  Zap,
  Clock,
  Database,
} from "@lucide/vue";

const ICONS = {
  shield: ShieldCheck,
  sliders: SlidersHorizontal,
  grid: LayoutGrid,
  alert: AlertTriangle,
  key: KeyRound,
  zap: Zap,
  clock: Clock,
  database: Database,
} as const;

defineProps<{ name: keyof typeof ICONS }>();
</script>

<template>
  <component :is="ICONS[name]" class="md-icon" :stroke-width="2" />
</template>

<style scoped>
.md-icon {
  width: 1.1em;
  height: 1.1em;
  flex-shrink: 0;
  vertical-align: -0.2em;
}
</style>
