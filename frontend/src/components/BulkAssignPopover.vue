<template>
  <div class="bap">
    <h4 class="bap__title">⚡ 把剩余数量分给某位客户</h4>
    <div class="bap__preview">
      <div class="bap__preview-head">将填入(基于当前矩阵):</div>
      <ul class="bap__preview-list">
        <li v-for="it in previewItems" :key="it.jewelry_id">
          {{ it.jewelry_name }} <span class="qty">+{{ it.delta }}</span>
        </li>
      </ul>
      <div v-if="totalText" class="bap__preview-foot">{{ totalText }}</div>
    </div>

    <div class="bap__label">选客户(从历史选或输新名)</div>
    <CustomerNameSelect v-model:value="picked" placeholder="客户名" />

    <div class="bap__footer">
      <n-button size="small" @click="$emit('cancel')">取消</n-button>
      <n-button size="small" type="primary" :disabled="!canConfirm" @click="onConfirm">
        填入
      </n-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { NButton } from 'naive-ui'
import CustomerNameSelect from './CustomerNameSelect.vue'

const props = defineProps({
  previewItems: { type: Array, required: true },
  hasLocked: { type: Boolean, default: false },
  hasPartialManual: { type: Boolean, default: false },
})
const emit = defineEmits(['confirm', 'cancel'])

const picked = ref(null)

const totalSum = computed(() =>
  props.previewItems.reduce((s, it) => s + Number(it.delta || 0), 0),
)

const totalText = computed(() => {
  const hints = []
  if (!props.hasLocked && !props.hasPartialManual) {
    hints.push(`✓ 整单全部 ${totalSum.value} 套`)
  } else {
    if (props.hasLocked) hints.push('不会动 🔒 锁定行')
    if (props.hasPartialManual) hints.push('其他客户已填的部分不变')
  }
  return hints.join(' · ')
})

const canConfirm = computed(
  () => !!(picked.value && String(picked.value).trim()),
)

function onConfirm() {
  if (canConfirm.value) emit('confirm', String(picked.value).trim())
}
</script>

<style scoped>
.bap { width: 260px; font-size: 12px; }
.bap__title { margin: 0 0 10px; font-size: 13px; font-weight: 600; }
.bap__preview {
  background: #f9f9fc; border-radius: 3px; padding: 8px 10px;
  margin-bottom: 10px; font-size: 11px; color: #555; line-height: 1.7;
}
.bap__preview-head { color: #666; margin-bottom: 4px; }
.bap__preview-list { list-style: none; margin: 0; padding: 0; }
.bap__preview-list li { padding: 1px 0; }
.bap__preview-list .qty { color: #4338ca; font-family: "SF Mono", Menlo, monospace; }
.bap__preview-foot { color: #18a058; margin-top: 4px; font-size: 11px; }
.bap__label { color: #666; margin-bottom: 4px; }
.bap__footer { display: flex; gap: 6px; justify-content: flex-end; margin-top: 10px; }
</style>
