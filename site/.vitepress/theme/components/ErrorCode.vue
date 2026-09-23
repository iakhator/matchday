<script setup lang="ts">
defineProps<{
  code: string;
  title: string;
}>();
</script>

<template>
  <div class="error-card">
    <span class="error-code" :class="{ ok: code.startsWith('2') }">{{ code }}</span>
    <div>
      <div class="error-title">{{ title }}</div>
      <p class="error-desc"><slot /></p>
    </div>
  </div>
</template>

<style scoped>
.error-card {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 12px 16px;
  margin: 10px 0;
  border-radius: 8px;
  background: var(--matchday-c-card-bg);
  border: 1px solid var(--matchday-c-card-border);
}

.error-code {
  flex-shrink: 0;
  min-width: 44px;
  text-align: center;
  font-family: var(--vp-font-family-mono);
  font-weight: 700;
  font-size: 13px;
  padding: 3px 8px;
  border-radius: 5px;
  color: var(--matchday-c-delete);
  background: color-mix(in srgb, var(--matchday-c-delete) 16%, transparent);
}

.error-code.ok {
  color: var(--matchday-c-get);
  background: color-mix(in srgb, var(--matchday-c-get) 16%, transparent);
}

.error-title {
  font-weight: 600;
  color: var(--vp-c-text-1);
}

.error-desc {
  margin: 2px 0 0;
  font-size: 14px;
  color: var(--vp-c-text-2);
}
</style>
