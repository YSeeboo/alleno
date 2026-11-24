<template>
  <n-modal :show="show" preset="card" title="配件退料" :style="modalStyle" :content-style="{ overflow: 'auto', minHeight: '0', flex: '1' }" :mask-closable="false" @update:show="onCancel">
    <p class="return-hint">未用完的材料单独退回，不计手工费。含已结清来源，按实际数量退料，允许超收。</p>
    <n-input v-model:value="filterText" clearable placeholder="配件名称 / 编号 / 手工单筛选" :input-props="{ 'aria-label': '搜索退料来源' }" />
    <div class="return-list">
      <article v-for="part in filteredParts" :key="part.id" class="return-source" :class="{ 'is-selected': isSelected(part) }">
        <div class="return-product">
          <n-checkbox :checked="isSelected(part)" :aria-label="`选择退料 ${part.item_name} ${part.handcraft_order_id} ${part.id}`" @update:checked="v => togglePart(part, v)" />
          <n-image v-if="part.item_image" :src="part.item_image" :alt="part.item_name" :width="38" :height="38" object-fit="cover" />
          <div class="return-copy"><strong>{{ part.item_name }}</strong><small>{{ part.item_id }}<span v-if="part.color"> · {{ part.color }}</span></small><small>{{ part.handcraft_order_id }} · 单据 {{ part.created_at?.slice(0, 10) || '—' }}</small></div>
          <div class="return-balance"><small>尚未退回</small><span>{{ getRemaining(part) }} {{ part.unit || '个' }}</span></div>
        </div>
        <div v-if="isSelected(part)" class="return-entry"><label :for="`return-qty-${part.id}`">本次退料</label><n-input-number :value="localSel[String(part.id)] ?? null" :min="0.0001" :precision="4" :step="1" :show-button="false" placeholder="实际数量" :input-props="{ id: `return-qty-${part.id}`, 'aria-label': `退料 ${part.id} 本次数量` }" @update:value="v => setQty(part, v)" /><span>{{ part.unit || '个' }}</span><small v-if="localSel[String(part.id)] > remainingQuantity(part)" class="return-over">超出未退 {{ Number((localSel[String(part.id)] - remainingQuantity(part)).toFixed(4)) }} · 允许实际超收</small></div>
      </article>
      <n-empty v-if="!filteredParts.length" description="没有符合条件的退料来源" class="return-empty" />
    </div>
    <p class="return-hint">筛选不清空已选退料；取消不修改主单。未退数为包含实收与已确认损耗的来源结清余额。</p>
    <template #footer><div class="return-footer"><span>已选 {{ selectedCount }} 项 · 不计费</span><n-button @click="onCancel">取消</n-button><n-button type="primary" @click="onConfirm">确定（{{ selectedCount }}）</n-button></div></template>
  </n-modal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { NModal, NInput, NInputNumber, NCheckbox, NImage, NButton, NEmpty, useMessage } from 'naive-ui'
import { sourceBalance, remainingQuantity } from '@/utils/receiptQuantity'

const message = useMessage()
const props = defineProps({
  show: { type: Boolean, required: true },
  parts: { type: Array, default: () => [] },
  selections: { type: Object, default: () => ({}) },
  isMobile: { type: Boolean, default: false },
})
const emit = defineEmits(['update:show', 'confirm', 'cancel'])
const filterText = ref('')
// Independent draft: cancelling must never mutate the receipt selections.
const localSel = ref({})
watch(() => props.show, val => {
  if (val) {
    filterText.value = ''
    localSel.value = { ...props.selections }
  }
}, { immediate: true })
const modalStyle = computed(() => ({ width: '640px', maxWidth: 'calc(100vw - 24px)', maxHeight: props.isMobile ? '86dvh' : '90dvh', display: 'flex', flexDirection: 'column' }))
const getRemaining = sourceBalance
const isSelected = part => Object.hasOwn(localSel.value, String(part.id))
const filteredParts = computed(() => {
  const tokens = filterText.value.trim().toLowerCase().split(/\s+/).filter(Boolean)
  return props.parts.filter(part => tokens.every(token => [part.item_name, part.item_id, part.handcraft_order_id, part.color].some(value => String(value || '').toLowerCase().includes(token))))
})
const selectedCount = computed(() => Object.keys(localSel.value).length)
const togglePart = (part, checked) => {
  const key = String(part.id)
  if (checked) localSel.value[key] = remainingQuantity(part) || null
  else delete localSel.value[key]
}
const setQty = (part, v) => {
  const key = String(part.id)
  if (isSelected(part)) localSel.value[key] = v
}
const onConfirm = () => {
  if (Object.values(localSel.value).some(v => !Number.isFinite(v) || v <= 0)) {
    message.warning('请为每项已选配件填写大于 0 的实际回收数量')
    return
  }
  if (Object.values(localSel.value).some(v => Math.abs(v * 10000 - Math.round(v * 10000)) > 0.000001)) {
    message.warning('退料数量最多保留 4 位小数')
    return
  }
  if (Object.keys(localSel.value).some(key => !props.parts.some(part => String(part.id) === key))) {
    message.warning('部分退料来源已不可用，请取消后刷新来源并移除失效退料')
    return
  }
  emit('confirm', { ...localSel.value })
}
const onCancel = () => {
  emit('cancel')
  emit('update:show', false)
}
</script>

<style scoped>
.return-hint { font-size: 12px; color: #8B9096; line-height: 1.7; margin: 0 0 14px; }
.return-list { margin: 14px 0; display: grid; gap: 10px; }
.return-source { border: 1px solid #ECEDEF; border-radius: 8px; padding: 13px; }
.return-source.is-selected { background: #F1F8F4; border-color: #DCE7E0; }
.return-product { display: flex; align-items: center; gap: 10px; }
.return-product :deep(.n-image) { flex-shrink: 0; border-radius: 6px; overflow: hidden; }
.return-copy { min-width: 0; flex: 1; overflow-wrap: anywhere; }
.return-copy strong { font-size: 13px; font-weight: 550; }
.return-copy small { display: block; margin-top: 3px; color: #8B9096; font-size: 11px; }
.return-balance { text-align: right; font-size: 12px; max-width: 150px; overflow-wrap: anywhere; }
.return-balance small { display: block; color: #8B9096; font-size: 11px; margin-bottom: 3px; }
.return-balance span { color: #1E7A5A; }
.return-entry { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 12px 0 0 26px; padding-top: 12px; border-top: 1px dashed #DCE7E0; font-size: 12px; color: #747C83; }
.return-entry :deep(.n-input-number) { width: 150px; }
.return-over { color: #A57933; font-size: 11px; }
.return-empty { padding: 24px 0; }
.return-footer { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.return-footer > span { flex: 1; font-size: 12px; color: #8B9096; }
@media (max-width: 540px) {
  .return-product { flex-wrap: wrap; }.return-copy { flex-basis: calc(100% - 80px); }.return-balance { max-width: none; text-align: left; margin-left: 26px; display: flex; gap: 8px; }
  .return-entry { margin-left: 0; }.return-entry :deep(.n-input-number) { flex: 1; min-width: 80px; width: auto; }.return-over { flex-basis: 100%; }.return-footer > span { flex-basis: 100%; }
}
</style>
