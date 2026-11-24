<template>
  <n-modal :show="true" preset="card" title="批量选择产出" class="hc-output-picker" :style="modalStyle" :content-style="contentStyle" :mask-closable="!busy" :close-on-esc="!busy" :closable="!busy" @update:show="value => { if (!value && !busy) emit('close') }">
    <p class="hop-note">从商品库多选，再集中填写数量。这里只编辑草稿，确认后才更新主单；取消不会改动主单。</p>
    <div v-if="isMobile" class="hop-mobile-tabs" role="group" aria-label="选品工作区"><button :aria-pressed="tab === 'catalog'" :disabled="busy" @click="tab = 'catalog'">商品库</button><button :aria-pressed="tab === 'drafts'" :disabled="busy" @click="tab = 'drafts'">已选清单 {{ rows.length }}</button></div>
    <div class="hop-split" :data-tab="tab">
      <section class="hop-catalog" aria-label="产出商品库">
        <n-input v-model:value="query" :disabled="busy" clearable placeholder="搜索商品名称 / 编号" :input-props="{ 'aria-label': '搜索产出商品' }" />
        <div class="hop-filters"><div class="hop-segments" role="group" aria-label="产出类型"><button v-for="filter in kinds" :key="filter.value" :disabled="busy" :aria-pressed="kind === filter.value" @click="kind = filter.value">{{ filter.label }}</button></div><n-checkbox v-model:checked="selectedOnly" :disabled="busy">只看已选</n-checkbox></div>
        <div class="hop-meta"><n-checkbox :checked="allSelected" :indeterminate="someSelected && !allSelected" :disabled="busy || !selectable.length" @update:checked="selectAll">全选当前筛选</n-checkbox><span>{{ filtered.length }} 款商品</span></div>
        <div class="hop-scroll">
          <label v-for="product in filtered" :key="product.key" class="hop-product" :class="{ selected: selected(product), existing: existingKeys.has(product.key) }">
            <input type="checkbox" :checked="selected(product)" :disabled="busy || existingKeys.has(product.key)" :aria-label="`选择 ${product.name} ${product.id}`" @change="toggle(product, $event.target.checked)">
            <img v-if="product.image" :src="product.image" :alt="product.name" loading="lazy"><span v-else class="hop-no-image" aria-hidden="true">◇</span>
            <span class="hop-product-copy"><strong>{{ product.name }}</strong><small>{{ product.id }} · {{ product.kind === 'part' ? '组合配件' : '饰品' }} · {{ product.unit || '个' }}</small></span><small v-if="existingKeys.has(product.key)" class="hop-existing-label">主单已有</small>
          </label>
          <n-empty v-if="!filtered.length" description="没有匹配的商品" />
        </div>
      </section>
      <section class="hop-drafts" aria-label="产出待选清单">
        <header class="hop-draft-head"><strong>本次产出清单 <small>{{ rows.length }} 款</small></strong><n-button text size="small" :disabled="busy || !rows.some(row => !existingKeys.has(row.product.key))" @click="clearNew">清除新增</n-button></header>
        <div class="hop-batch"><label for="hc-batch-quantity">统一数量</label><input id="hc-batch-quantity" v-model="batchQty" type="number" min="1" step="1" :disabled="busy" placeholder="如 100"><n-button text size="small" :disabled="busy || !rows.length" @click="applyQuantity">应用到已选</n-button></div>
        <div class="hop-scroll">
          <article v-for="row in rows" :key="row.product.key" class="hop-row" :data-output-draft="row.product.key">
            <header><div><strong>{{ row.product.name }}</strong><small>{{ row.product.id }} · {{ existingKeys.has(row.product.key) ? '主单已有，移除请在主单操作' : '待加入制作单' }}</small></div><n-button v-if="!existingKeys.has(row.product.key)" text :disabled="busy" :aria-label="`取消选择 ${row.product.name}`" @click="toggle(row.product, false)">×</n-button></header>
            <div class="hop-fields"><label>预期数量<input v-model="row.qty" type="number" min="1" step="1" :disabled="busy" :aria-label="`${row.product.name} 待选数量`" :aria-invalid="!handcraftInteger(row.qty)"></label><label>单位<input v-model="row.unit" :disabled="busy" :aria-label="`${row.product.name} 待选单位`" maxlength="20"></label></div>
            <input v-model="row.note" class="hop-note-input" :disabled="busy" :aria-label="`${row.product.name} 制作备注`" placeholder="制作备注（选填）" maxlength="500">
          </article>
          <n-empty v-if="!rows.length" description="从商品库勾选产出，再完善数量" />
        </div>
      </section>
    </div>
    <p v-if="error || applyError" class="hop-error" role="alert">{{ error || applyError }}</p>
    <template #footer><div class="hop-footer"><span>已选 {{ rows.length }} 款 · 新增 {{ newCount }} 款</span><div><n-button :disabled="busy" @click="emit('close')">取消</n-button><n-button type="primary" :disabled="!rows.length" :loading="busy" @click="confirm">{{ initial.length ? '更新制作清单' : '加入制作清单' }}</n-button></div></div></template>
  </n-modal>
</template>

<script setup>
import { computed, ref } from 'vue'
import { NButton, NCheckbox, NEmpty, NInput, NModal } from 'naive-ui'
import { useIsMobile } from '@/composables/useIsMobile'
import { handcraftOutputKey, handcraftInteger } from '@/utils/handcraftCreate'

const props = defineProps({ products: { type: Array, required: true }, initial: { type: Array, default: () => [] }, busy: Boolean, applyError: String })
const emit = defineEmits(['close', 'confirm'])
const { isMobile } = useIsMobile()
const rows = ref(props.initial.map(group => ({ product: props.products.find(product => product.key === handcraftOutputKey(group)) || { key: handcraftOutputKey(group), id: group.jewelry_id || group.part_id, name: '商品已不可用，请返回主单核对' }, qty: group.qty, unit: group.unit, note: group.note || '' })))
const query = ref(''), kind = ref('all'), selectedOnly = ref(false), tab = ref('catalog'), batchQty = ref(''), error = ref('')
const kinds = [{ value: 'all', label: '全部' }, { value: 'jewelry', label: '饰品' }, { value: 'part', label: '组合配件' }]
const existingKeys = computed(() => new Set(props.initial.map(handcraftOutputKey)))
const selected = product => rows.value.some(row => row.product.key === product.key)
const filtered = computed(() => {
  const text = query.value.trim().toLocaleLowerCase()
  return props.products.filter(product => (kind.value === 'all' || product.kind === kind.value) && (!selectedOnly.value || selected(product)) && (!text || `${product.id} ${product.name}`.toLocaleLowerCase().includes(text)))
})
const selectable = computed(() => filtered.value.filter(product => !existingKeys.value.has(product.key)))
const allSelected = computed(() => !!selectable.value.length && selectable.value.every(selected))
const someSelected = computed(() => selectable.value.some(selected))
const newCount = computed(() => rows.value.filter(row => !existingKeys.value.has(row.product.key)).length)
const modalStyle = { width: '1100px', maxWidth: 'calc(100vw - 24px)', maxHeight: 'calc(100dvh - 24px)', display: 'flex', flexDirection: 'column' }
const contentStyle = { minHeight: '0', overflow: 'auto' }
function toggle(product, checked) {
  if (props.busy || existingKeys.value.has(product.key)) return
  error.value = ''
  if (!checked) rows.value = rows.value.filter(row => row.product.key !== product.key)
  else if (!selected(product)) rows.value.push({ product, qty: 1, unit: product.unit || '个', note: '' })
}
function selectAll(checked) { for (const product of selectable.value) toggle(product, checked) }
function clearNew() { if (!props.busy) rows.value = rows.value.filter(row => existingKeys.value.has(row.product.key)) }
function applyQuantity() {
  if (props.busy) return
  if (!handcraftInteger(batchQty.value)) { error.value = '统一数量必须为正整数'; return }
  for (const row of rows.value) row.qty = Number(batchQty.value)
  error.value = ''
}
function confirm() {
  if (props.busy) return
  if (!rows.value.length || rows.value.some(row => !handcraftInteger(row.qty) || !row.unit.trim())) {
    error.value = '请检查已选清单，数量必须为正整数，单位不能为空'
    tab.value = 'drafts'
    return
  }
  error.value = ''
  emit('confirm', rows.value.map(row => ({ product: row.product, qty: Number(row.qty), unit: row.unit.trim(), note: row.note })))
}
</script>

<style scoped>
.hop-note { color:#829080; font-size:12px; margin:0 0 17px; line-height:1.8; }
.hop-split { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,.9fr); border:1px solid #e2e9df; border-radius:8px; overflow:hidden; }
.hop-catalog,.hop-drafts { min-width:0; display:flex; flex-direction:column; padding:16px; }
.hop-drafts { border-left:1px solid #e2e9df; background:#f8faf6; }
.hop-filters,.hop-meta,.hop-draft-head,.hop-batch,.hop-footer,.hop-footer>div { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.hop-filters { margin:14px 0 12px; }.hop-meta { font-size:11px; color:#84947c; padding-bottom:10px; }
.hop-filters :deep(.n-checkbox),.hop-meta :deep(.n-checkbox) { font-size:11px; white-space:nowrap; }
.hop-segments { display:flex; padding:3px; border-radius:5px; background:#eff4eb; }
.hop-segments button { border:0; border-radius:4px; padding:5px 10px; background:transparent; font:inherit; font-size:11px; color:#7e9071; cursor:pointer; }
.hop-segments button[aria-pressed=true] { background:white; color:#1e7a5a; box-shadow:0 1px 4px #304b1e0e; }
.hop-scroll { height:clamp(130px,calc(100dvh - 385px),430px); overflow-y:auto; scrollbar-width:thin; }
.hop-catalog .hop-scroll { flex:1; min-height:130px; max-height:430px; }
.hop-product { display:flex; align-items:center; gap:10px; border:1px solid #e1e8db; border-radius:6px; padding:12px 10px; margin-bottom:8px; cursor:pointer; }
.hop-product.selected { background:#f2f8ee; border-color:#afc8a2; }.hop-product.existing { cursor:default; }
.hop-product input { accent-color:#1e7a5a; width:15px; height:15px; flex-shrink:0; }
.hop-product img,.hop-no-image { width:43px; height:43px; object-fit:cover; border-radius:6px; flex-shrink:0; }
.hop-no-image { display:grid; place-items:center; background:#f0f3eb; color:#a1b28f; font-size:24px; }
.hop-product-copy { min-width:0; flex:1; overflow-wrap:anywhere; }.hop-product-copy strong { display:block; font-size:12px; font-weight:600; }
.hop-product-copy small,.hop-existing-label { color:#8d9c80; font-size:10px; }.hop-existing-label { white-space:nowrap; }
.hop-draft-head { font-size:12px; margin-bottom:10px; }.hop-draft-head small { color:#8c9c7d; font-weight:400; }
.hop-batch { font-size:11px; color:#829476; margin:3px 0 16px; }.hop-batch input { width:80px; }.hop-batch :deep(.n-button) { margin-left:auto; }
.hop-row { padding:13px; background:white; border:1px solid #e0e8d9; border-radius:6px; margin-bottom:10px; }
.hop-row header { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; }.hop-row strong { font-size:12px; font-weight:600; }
.hop-row header small { display:block; color:#8c9a80; font-size:10px; margin-top:4px; }
.hop-fields { display:grid; grid-template-columns:minmax(0,1fr) 75px; gap:12px; margin-top:12px; }.hop-fields label { font-size:10px; color:#849478; }
.hop-fields input,.hop-batch input { display:block; box-sizing:border-box; width:100%; min-width:0; background:white; border:1px solid #dce5d4; padding:7px 9px; border-radius:5px; font:inherit; color:#354832; margin-top:5px; }
.hop-batch input { width:80px; margin:0; }.hop-fields input[aria-invalid=true] { border-color:#bc7655; }
.hop-note-input { width:100%; box-sizing:border-box; margin-top:10px; border:0; background:transparent; font:inherit; font-size:11px; color:#829672; padding:6px 0; }
input:focus-visible,button:focus-visible { outline:2px solid #1e7a5a; outline-offset:2px; }
.hop-error { color:#ac7044; font-size:12px; padding:10px 0 0; margin:0; }.hop-footer { font-size:11px; color:#8c9c80; }.hop-scroll :deep(.n-empty) { padding:45px 10px; }
.hop-mobile-tabs { display:none; }
@media(max-width:768px) {
  .hop-note { font-size:11px; margin-bottom:12px; }.hop-mobile-tabs { display:flex; border-bottom:1px solid #dce5d5; margin-bottom:12px; }
  .hop-mobile-tabs button { flex:1; padding:10px; background:white; border:0; border-bottom:2px solid transparent; color:#8a9a7e; font:inherit; font-size:12px; cursor:pointer; }
  .hop-mobile-tabs button[aria-pressed=true] { border-color:#1e7a5a; color:#1e7a5a; }
  .hop-split { display:block; }.hop-catalog,.hop-drafts { padding:12px; }.hop-drafts { border:0; }
  .hop-split[data-tab=catalog] .hop-drafts,.hop-split[data-tab=drafts] .hop-catalog { display:none; }
  .hop-scroll { height:clamp(100px,calc(100dvh - 400px),340px); }.hop-catalog .hop-scroll { flex:initial; min-height:100px; max-height:none; }
  .hop-product { padding:10px 8px; gap:8px; }.hop-product img,.hop-no-image { width:38px; height:38px; }
  .hop-product-copy strong { font-size:12px; }.hop-product-copy small { font-size:9px; }.hop-existing-label { font-size:9px; }
  .hop-segments button { font-size:10px; padding:5px 8px; }.hop-filters { gap:5px; }
  .hop-fields input { min-height:40px; font-size:14px; }.hop-footer { gap:8px; font-size:10px; }.hop-footer>div { gap:7px; }
  .hop-footer :deep(.n-button) { min-height:40px; font-size:12px; }
}
</style>
