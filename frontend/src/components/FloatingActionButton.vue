<template>
  <n-button
    v-bind="$attrs"
    class="fab-action"
    :class="`fab-action--${variant}`"
    :bordered="false"
    :loading="loading"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
    :theme-overrides="buttonTheme"
  >
    <template v-if="$slots.icon" #icon><slot name="icon" /></template>
    <slot />
  </n-button>
</template>

<script setup>
import { computed } from 'vue'
import { NButton } from 'naive-ui'

defineOptions({ inheritAttrs: false })
const props = defineProps({
  variant: { type: String, default: 'secondary', validator: (value) => ['secondary', 'excel', 'pdf', 'primary'].includes(value) },
  loading: Boolean,
  disabled: Boolean,
})
const buttonTheme = computed(() => {
  const primary = props.variant === 'primary'
  const hover = { excel: '#1E7A5A', pdf: '#E5484D', primary: '#248D69' }[props.variant] || '#FFFFFF0D'
  return {
    color: primary ? '#1E7A5A' : 'transparent',
    colorHover: hover,
    colorPressed: hover,
    colorFocus: primary ? '#1E7A5A' : 'transparent',
    colorDisabled: primary ? '#1E7A5A' : 'transparent',
    textColor: primary ? '#fff' : '#C0C6CD',
    textColorHover: '#fff', textColorPressed: '#fff',
    textColorFocus: primary ? '#fff' : '#C0C6CD', textColorDisabled: '#C0C6CD',
    rippleColor: 'transparent', borderRadiusMedium: '7px',
  }
})
</script>

<style scoped>
.fab-action { --fab-interaction: #FFFFFF0D; height: 40px; padding: 9px 12px; font-size: 12px; transition: background-color .15s, color .15s, opacity .15s; }
.fab-action--excel { --fab-interaction: #1E7A5A; }
.fab-action--pdf { --fab-interaction: #E5484D; }
.fab-action--primary { --fab-interaction: #248D69; font-weight: 600; }
.fab-action:not(:disabled):focus-visible { background: var(--fab-interaction); color: #fff; outline: 2px solid #fff; outline-offset: 2px; }
.fab-action :deep(.n-button__content), .fab-action :deep(.n-button__icon) { color: inherit; }
@media (max-width: 480px) { .fab-action { min-height: 44px; font-size: 11px; padding: 9px 8px; } }
@media (prefers-reduced-motion: reduce) { .fab-action { transition: none; } }
</style>
