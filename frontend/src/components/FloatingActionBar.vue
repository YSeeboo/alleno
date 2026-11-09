<template>
  <div class="fab-spacer" :style="{ height: `${barHeight}px` }" aria-hidden="true"></div>
  <div ref="bar" class="fab-bar" role="group" v-bind="$attrs">
    <div class="fab-pill"><slot /></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

defineOptions({ inheritAttrs: false })
const bar = ref(null)
const barHeight = ref(64)
let observer
onMounted(() => {
  observer = new ResizeObserver(() => { barHeight.value = Math.ceil(bar.value?.getBoundingClientRect().height || 64) })
  observer.observe(bar.value)
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<style scoped>
/* reserve space so page content isn't hidden behind the sticky bar */
.fab-spacer { flex-shrink: 0; }
.fab-bar {
  position: sticky;
  bottom: 0;
  display: flex;
  justify-content: center;
  padding: 14px 0 calc(14px + env(safe-area-inset-bottom));
  pointer-events: none;
  z-index: 20;
  max-width: 100%;
}
.fab-pill {
  pointer-events: auto;
  background: #1A1D21;
  border-radius: 14px;
  padding: 8px 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  box-sizing: border-box;
  box-shadow: 0 14px 34px rgba(16, 20, 26, 0.30);
}
@media (max-width: 480px) {
  .fab-pill { width: 100%; flex-wrap: wrap; gap: 4px; }
  .fab-pill :deep(> .n-button) { flex: 1 1 calc(50% - 4px); min-height: 44px; }
}
</style>
