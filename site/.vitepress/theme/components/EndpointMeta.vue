<script setup lang="ts">
defineProps<{
  stats: { label: string; value: string }[];
}>();
</script>

<template>
  <div class="meta-grid">
    <div class="meta-card" v-for="s in stats" :key="s.label">
      <div class="meta-label">{{ s.label }}</div>
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
