<script setup lang="ts">
defineProps<{
  name: string;
  type: string;
  required?: boolean;
  enumValues?: string[];
  default?: string;
}>();
</script>

<template>
  <div class="param-card">
    <div class="param-head">
      <code class="param-name">{{ name }}</code>
      <span class="param-type">{{ type }}</span>
      <span class="param-badge" :class="required ? 'required' : 'optional'">
        {{ required ? "Required" : "Optional" }}
      </span>
    </div>
    <p class="param-desc"><slot /></p>
    <div class="param-enum" v-if="enumValues?.length">
      <span
        v-for="v in enumValues"
        :key="v"
        class="enum-chip"
        :class="{ active: v === $props.default }"
      >
        {{ v }}{{ v === $props.default ? " (default)" : "" }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.param-card {
  padding: 14px 16px;
  margin: 12px 0;
  border-radius: 8px;
  background: var(--matchday-c-card-bg);
  border: 1px solid var(--matchday-c-card-border);
}

.param-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}

.param-name {
  font-weight: 700;
  color: var(--vp-c-brand-1);
  background: transparent;
  padding: 0;
}

.param-type {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.param-badge {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.param-badge.required {
  color: var(--matchday-c-patch);
  background: color-mix(in srgb, var(--matchday-c-patch) 16%, transparent);
}
.param-badge.optional {
  color: var(--vp-c-text-3);
  background: var(--vp-c-bg-alt);
}

.param-desc {
  margin: 4px 0 0;
  font-size: 14px;
  color: var(--vp-c-text-2);
}

.param-enum {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.enum-chip {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 5px;
  background: var(--vp-c-bg-alt);
  color: var(--vp-c-text-2);
}

.enum-chip.active {
  background: color-mix(in srgb, var(--vp-c-brand-1) 18%, transparent);
  color: var(--vp-c-brand-1);
}
</style>
