<script setup lang="ts">
const props = defineProps<{
  method: "GET" | "POST" | "DELETE" | "PATCH" | "PUT";
  path: string;
}>();
</script>

<template>
  <div class="endpoint-bar">
    <span class="method" :class="props.method.toLowerCase()">{{ props.method }}</span>
    <code class="path">{{ props.path }}</code>
  </div>
</template>

<style scoped>
.endpoint-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 14px;
  margin: 16px 0;
  border-radius: 8px;
  background: var(--matchday-c-card-bg);
  border: 1px solid var(--matchday-c-card-border);
}

.method {
  flex-shrink: 0;
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  font-weight: 700;
  padding: 3px 9px;
  border-radius: 5px;
  letter-spacing: 0.03em;
}

.method.get {
  color: var(--matchday-c-get);
  background: color-mix(in srgb, var(--matchday-c-get) 16%, transparent);
}
.method.post {
  color: var(--matchday-c-post);
  background: color-mix(in srgb, var(--matchday-c-post) 16%, transparent);
}
.method.delete {
  color: var(--matchday-c-delete);
  background: color-mix(in srgb, var(--matchday-c-delete) 16%, transparent);
}
.method.patch,
.method.put {
  color: var(--matchday-c-patch);
  background: color-mix(in srgb, var(--matchday-c-patch) 16%, transparent);
}

.path {
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  word-break: break-all;
  color: var(--vp-c-text-1);
  background: transparent;
  padding: 0;
}
</style>
