<template>
  <button
    v-if="childCount > 0"
    type="button"
    class="part-group-toggle"
    :class="{ 'is-expanded': expanded }"
    :aria-expanded="expanded"
    :aria-label="`${expanded ? '收起' : '展开'} ${partName || partId} 的 ${childCount} 个子配件`"
    :title="`${expanded ? '收起' : '展开'}子配件`"
    @click.stop="$emit('toggle')"
  >
    <span class="part-group-arrow" aria-hidden="true">
      <svg viewBox="0 0 16 16" fill="none">
        <path d="m6 4 4 4-4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </span>
    <span>{{ partId }}</span>
  </button>
  <span v-else class="part-group-id">
    <span class="part-group-spacer" aria-hidden="true"></span>
    <span>{{ partId }}</span>
  </span>
</template>

<script setup>
defineProps({
  partId: { type: String, required: true },
  partName: { type: String, default: '' },
  childCount: { type: Number, default: 0 },
  expanded: { type: Boolean, default: false },
})

defineEmits(['toggle'])
</script>

<style scoped>
.part-group-toggle,
.part-group-id {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 44px;
  padding: 0 6px;
  font: inherit;
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
  color: #6b7280;
  white-space: nowrap;
  vertical-align: middle;
}

.part-group-toggle {
  width: 100%;
  border: 0;
  border-radius: 6px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  touch-action: manipulation;
  transition: background 0.12s, color 0.12s;
}

.part-group-toggle:hover {
  background: #EEF1F4;
  color: #1A1D21;
}

.part-group-toggle:active {
  background: #E2E7EC;
}

.part-group-toggle:focus-visible {
  outline: 2px solid #1E7A5A;
  outline-offset: 2px;
}

.part-group-arrow,
.part-group-spacer {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 28px;
  flex-shrink: 0;
}

.part-group-arrow svg {
  width: 16px;
  height: 16px;
  transition: transform 0.15s;
}

.is-expanded .part-group-arrow svg {
  transform: rotate(90deg);
}

@media (prefers-reduced-motion: reduce) {
  .part-group-toggle,
  .part-group-arrow svg {
    transition: none;
  }
}
</style>
