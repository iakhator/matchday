<script setup lang="ts">
import Icon from "./Icon.vue";

defineProps<{
  stats: { label: string; value: string }[];
}>();

// Derived from the label rather than requiring every call site (11
// endpoint pages) to also specify an icon name - "Auth" always means
// the same icon everywhere on this site, so it isn't really per-call-site
// data.
function iconFor(label: string) {
  const l = label.toLowerCase();
  if (l.includes("auth")) return "key";
  if (l.includes("update")) return "clock";
  if (l.includes("source") || l.includes("cap")) return "database";
  return "zap";
}
</script>

<template>
  <div class="meta-grid">
    <div class="meta-card" v-for="s in stats" :key="s.label">
      <div class="meta-label"><Icon :name="iconFor(s.label)" /> {{ s.label }}</div>
      <div class="meta-value">{{ s.value }}</div>
    </div>
  </div>
</template>

<style scoped>
.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  margin: 16px 0;
}

.meta-card {
  padding: 10px 14px;
  border-radius: 8px;
  background: var(--matchday-c-card-bg);
  border: 1px solid var(--matchday-c-card-border);
}

.meta-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--vp-c-text-3);
  margin-bottom: 4px;
}

.meta-value {
  font-family: var(--vp-font-family-mono);
  font-size: 14px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
  word-break: break-word;
}
</style>
