<script setup lang="ts">
import { computed, ref } from "vue";
import type { HourlyUsage } from "../gatewayApi";

const props = defineProps<{
  hourly: HourlyUsage[];
}>();

// Internal coordinate system, fixed 4:1 aspect ratio. The SVG scales
// uniformly to the container's width (see the template's default
// preserveAspectRatio - deliberately not "none", which would stretch x
// and y independently and smear the bar radii the wider this renders).
const VIEW_W = 480;
const VIEW_H = 120;
const BASELINE = VIEW_H - 22; // room for x-axis labels below
const TOP_PAD = 10;
const BAR_RADIUS = 3;
const GAP = 3;

const slotWidth = computed(() => VIEW_W / props.hourly.length);
const barWidth = computed(() => Math.max(1, slotWidth.value - GAP));

const maxCount = computed(() =>
  Math.max(1, ...props.hourly.map((h) => h.count)),
);

function barHeight(count: number): number {
  const usable = BASELINE - TOP_PAD;
  return count === 0 ? 0 : Math.max(2, (count / maxCount.value) * usable);
}

// Rounded top, square at the baseline - marks-and-anatomy.md's bar spec.
// A zero-height bar draws nothing rather than a visible sliver at the
// baseline, so an empty hour reads as empty, not as "some" traffic.
function barPath(index: number, count: number): string {
  const height = barHeight(count);
  if (height <= 0) return "";
  const x = index * slotWidth.value + GAP / 2;
  const w = barWidth.value;
  const yTop = BASELINE - height;
  const r = Math.min(BAR_RADIUS, w / 2, height);
  return [
    `M ${x} ${BASELINE}`,
    `L ${x} ${yTop + r}`,
    `Q ${x} ${yTop} ${x + r} ${yTop}`,
    `L ${x + w - r} ${yTop}`,
    `Q ${x + w} ${yTop} ${x + w} ${yTop + r}`,
    `L ${x + w} ${BASELINE}`,
    "Z",
  ].join(" ");
}

function hourLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "numeric" });
}

function fullLabel(iso: string): string {
  return new Date(iso).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
  });
}

// Every 6th hour gets an axis label - 24 labels on a ~280px chart is
// unreadable clutter.
const tickIndices = computed(() =>
  props.hourly.map((_, i) => i).filter((i) => i % 6 === 0),
);

const activeIndex = ref<number | null>(null);
const active = computed(() =>
  activeIndex.value === null ? null : props.hourly[activeIndex.value],
);

const totalRequests = computed(() =>
  props.hourly.reduce((sum, h) => sum + h.count, 0),
);
</script>

<template>
  <div class="usage-chart">
    <div class="usage-chart-header">
      <span class="usage-chart-title">Requests per hour</span>
      <span class="usage-chart-subtitle">last 24 hours</span>
    </div>

    <div class="usage-chart-body">
      <svg
        :viewBox="`0 0 ${VIEW_W} ${VIEW_H}`"
        role="img"
        :aria-label="`${totalRequests} requests in the last 24 hours`"
        @mouseleave="activeIndex = null"
      >
        <line
          class="usage-chart-baseline"
          :x1="0"
          :x2="VIEW_W"
          :y1="BASELINE"
          :y2="BASELINE"
        />

        <template v-for="(point, i) in hourly" :key="point.hour">
          <path
            v-if="point.count > 0"
            :d="barPath(i, point.count)"
            class="usage-chart-bar"
            :class="{ 'is-active': activeIndex === i }"
          />
          <!-- Hit target wider than the painted bar (marks-and-anatomy.md /
               interaction.md): the full slot height, always present even
               for a zero-count hour, so every hour is reachable on
               hover/focus, not just the ones with visible bars. -->
          <rect
            :x="i * slotWidth"
            :y="0"
            :width="slotWidth"
            :height="BASELINE"
            class="usage-chart-hit"
            tabindex="0"
            :aria-label="`${fullLabel(point.hour)}: ${point.count} requests`"
            @mouseenter="activeIndex = i"
            @focus="activeIndex = i"
            @blur="activeIndex = null"
          />
        </template>

        <text
          v-for="i in tickIndices"
          :key="`tick-${i}`"
          :x="i * slotWidth + slotWidth / 2"
          :y="VIEW_H - 2"
          class="usage-chart-axis-label"
          text-anchor="middle"
        >
          {{ hourLabel(hourly[i].hour) }}
        </text>
      </svg>

      <div
        v-if="active"
        class="usage-chart-tooltip"
        :style="{
          left: `${((activeIndex! + 0.5) / hourly.length) * 100}%`,
        }"
      >
        <strong>{{ active.count }}</strong> requests
        <span class="usage-chart-tooltip-time">{{ fullLabel(active.hour) }}</span>
      </div>
    </div>

    <details class="usage-chart-table-toggle">
      <summary>View as table</summary>
      <table>
        <thead>
          <tr>
            <th>Hour</th>
            <th>Requests</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="point in hourly" :key="point.hour">
            <td>{{ fullLabel(point.hour) }}</td>
            <td>{{ point.count }}</td>
          </tr>
        </tbody>
      </table>
    </details>
  </div>
</template>

<style scoped>
.usage-chart {
  margin-top: 4px;
}

.usage-chart-header {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 4px;
}

.usage-chart-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--vp-c-text-2);
}

.usage-chart-subtitle {
  font-size: 11px;
  color: var(--vp-c-text-3);
}

.usage-chart-body {
  position: relative;
}

.usage-chart-body svg {
  width: 100%;
  aspect-ratio: 480 / 120;
  display: block;
  overflow: visible;
}

.usage-chart-baseline {
  stroke: var(--matchday-c-card-border);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.usage-chart-bar {
  fill: var(--vp-c-brand-1);
  transition: opacity 0.1s ease;
}

.usage-chart-bar.is-active {
  opacity: 0.75;
}

.usage-chart-hit {
  fill: transparent;
  cursor: pointer;
}

.usage-chart-hit:focus {
  outline: none;
}

.usage-chart-axis-label {
  font-size: 10px;
  fill: var(--vp-c-text-3);
}

.usage-chart-tooltip {
  position: absolute;
  bottom: 100%;
  transform: translateX(-50%);
  margin-bottom: 4px;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid var(--matchday-c-card-border);
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-size: 11px;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
}

.usage-chart-tooltip strong {
  color: var(--vp-c-text-1);
}

.usage-chart-tooltip-time {
  margin-left: 6px;
  color: var(--vp-c-text-3);
}

.usage-chart-table-toggle {
  margin-top: 6px;
}

.usage-chart-table-toggle summary {
  font-size: 11px;
  color: var(--vp-c-text-3);
  cursor: pointer;
}

.usage-chart-table-toggle table {
  margin-top: 6px;
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.usage-chart-table-toggle th,
.usage-chart-table-toggle td {
  text-align: left;
  padding: 2px 8px 2px 0;
  font-variant-numeric: tabular-nums;
}

.usage-chart-table-toggle th {
  color: var(--vp-c-text-3);
  font-weight: 500;
}
</style>
