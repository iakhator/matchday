<script setup lang="ts">
// Hand-drawn, not an icon-library dependency - a handful of simple
// stroke icons doesn't justify a new package for a docs site.
defineProps<{ name: string }>();
</script>

<template>
  <svg
    class="md-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
  >
    <template v-if="name === 'shield'">
      <path d="M12 2.5 4.5 5.5v5.6c0 5.1 3.3 8.9 7.5 10.4 4.2-1.5 7.5-5.3 7.5-10.4V5.5L12 2.5Z" />
    </template>

    <template v-else-if="name === 'sliders'">
      <line x1="4" y1="6" x2="20" y2="6" />
      <circle cx="9" cy="6" r="2" fill="var(--vp-c-bg)" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <circle cx="15" cy="12" r="2" fill="var(--vp-c-bg)" />
      <line x1="4" y1="18" x2="20" y2="18" />
      <circle cx="11" cy="18" r="2" fill="var(--vp-c-bg)" />
    </template>

    <template v-else-if="name === 'grid'">
      <rect x="3.5" y="3.5" width="7" height="7" rx="1" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1" />
    </template>

    <template v-else-if="name === 'alert'">
      <path d="M12 3 2.5 20h19L12 3Z" />
      <line x1="12" y1="9.5" x2="12" y2="14" />
      <circle cx="12" cy="17" r="0.9" fill="currentColor" stroke="none" />
    </template>

    <template v-else-if="name === 'key'">
      <circle cx="8" cy="15" r="4.5" />
      <line x1="11.2" y1="11.8" x2="20" y2="3" />
      <line x1="16" y1="7" x2="19" y2="10" />
      <line x1="19" y1="4" x2="21" y2="6" />
    </template>

    <template v-else-if="name === 'zap'">
      <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z" />
    </template>
  </svg>
</template>

<style scoped>
.md-icon {
  width: 1.15em;
  height: 1.15em;
  flex-shrink: 0;
  vertical-align: -0.2em;
}
</style>
