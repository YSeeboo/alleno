<template>
  <section class="ow-section" :class="{ 'ow-section-collapsed': collapsed }">
    <header v-if="title || $slots['header-extra']" class="ow-section-head">
      <div class="ow-section-title">
        <h3 v-if="canCollapse" class="ow-section-heading">
          <button type="button" class="ow-section-toggle" :aria-expanded="!collapsed" :aria-controls="bodyId" :title="collapsed ? '展开此模块' : '收起此模块'" @click="setCollapsed(!collapsed)">
            <span class="ow-section-chevron" aria-hidden="true"><svg viewBox="0 0 20 20" fill="none"><path d="m7.5 5 5 5-5 5" /></svg></span>
            <span>{{ title }}</span>
          </button>
        </h3>
        <h3 v-else>{{ title }}</h3>
        <span v-if="count != null" class="ow-count">{{ count }}</span><slot name="summary" />
      </div>
      <div v-if="$slots['header-extra']" class="wf-actions"><slot name="header-extra" /></div>
    </header>
    <div :id="bodyId" v-show="!collapsed"><slot />
    <div v-if="$slots.footer" class="ow-table-note"><slot name="footer" /></div></div>
  </section>
</template>
<script setup>
import { computed, inject, ref, useId } from 'vue'
const props = defineProps({ title: String, count: [String, Number], collapsible: Boolean })
const context = inject('order-production-sections', null), localCollapsed = ref(false), bodyId = useId()
const canCollapse = computed(() => props.collapsible || !!context)
const collapsed = computed(() => canCollapse.value && (context ? !!context.collapsed.value[props.title] : localCollapsed.value))
function setCollapsed(value) {
  if (context) context.setCollapsed(props.title, value)
  else localCollapsed.value = value
}
defineExpose({ expand: () => setCollapsed(false) })
</script>
<style scoped>
.ow-section-heading { min-width:0; }
.ow-section-toggle { display:inline-flex; align-items:center; gap:9px; min-height:32px; background:none; border:0; padding:0; color:inherit; font:inherit; cursor:pointer; text-align:left; border-radius:6px; transition:color .16s ease; }
.ow-section-chevron { display:grid; place-items:center; flex:0 0 24px; width:24px; height:24px; border:1px solid #E8ECE9; border-radius:7px; background:#F7F9F8; color:#7B8680; transition:background .16s ease, border-color .16s ease, color .16s ease; }
.ow-section-chevron svg { width:14px; height:14px; stroke:currentColor; stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round; transition:transform .18s ease; }
.ow-section-toggle[aria-expanded="true"] .ow-section-chevron svg { transform:rotate(90deg); }
.ow-section-toggle:hover { color:#1E7A5A; }
.ow-section-toggle:hover .ow-section-chevron { background:#EDF5F0; border-color:#D5E6DC; color:#1E7A5A; }
.ow-section-toggle:focus-visible { outline:2px solid #1E7A5A; outline-offset:4px; }
.ow-section-collapsed .ow-section-head { padding-bottom:0; margin-bottom:0; border-bottom-color:transparent; }
@media (prefers-reduced-motion:reduce) {
  .ow-section-toggle, .ow-section-chevron, .ow-section-chevron svg { transition:none; }
}
</style>
