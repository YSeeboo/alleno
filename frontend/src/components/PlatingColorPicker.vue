<template>
  <div class="plating-color-picker" role="group" :aria-label="label">
    <button v-for="color in colors.filter(c => c.common)" :key="color.code" type="button" :disabled="disabled" :aria-pressed="modelValue === color.code" :title="color.label" :style="chipStyle(color)" @click="choose(color.code)">{{ color.code }}</button>
    <n-popover v-if="extraColors.length" trigger="click" :disabled="disabled" placement="bottom-end">
      <template #trigger><button type="button" class="more" :disabled="disabled" :title="extraColor?.label || '更多颜色'" :style="extraColor ? chipStyle(extraColor) : {}">{{ extraColor?.code || '更多' }} ▾</button></template>
      <div class="plating-color-picker"><button v-for="color in extraColors" :key="color.code" type="button" :disabled="disabled" :aria-pressed="modelValue === color.code" :style="chipStyle(color)" @click="choose(color.code)">{{ color.code }} · {{ color.label }}</button></div>
    </n-popover>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { NPopover } from 'naive-ui'
const props = defineProps({ modelValue: String, colors: { type: Array, default: () => [] }, disabled: Boolean, label: { type: String, default: '电镀颜色' } })
const emit = defineEmits(['update:modelValue'])
const extraColors = computed(() => props.colors.filter(c => !c.common))
const extraColor = computed(() => extraColors.value.find(c => c.code === props.modelValue))
const chipStyle = color => ({ color: props.modelValue === color.code ? '#fff' : color.badge, background: props.modelValue === color.code ? color.badge : '#f5f5f5', borderColor: color.badge })
function choose(code) { if (!props.disabled) emit('update:modelValue', props.modelValue === code ? null : code) }
</script>
<style scoped>
.plating-color-picker { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; min-height: 34px; }
button { font: inherit; font-size: 11px; font-weight: 600; padding: 3px 7px; border: 1px solid; border-radius: 4px; cursor: pointer; white-space: nowrap; }
button:disabled { cursor: not-allowed; opacity: .6; }
.more { border: 1px dashed #aaa; color: #666; background: #f5f5f5; }
@media (max-width: 600px) { button { font-size: 10px; padding: 3px 4px; } .plating-color-picker { gap: 3px; } }
</style>
