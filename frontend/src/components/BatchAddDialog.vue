<template>
  <n-modal :show="true" preset="card" :title="config.title" class="batch-add-dialog" style="width:min(1120px,calc(100vw - 24px))" :mask-closable="false" :closable="!busy" :close-on-esc="!busy" @update:show="value => { if (!value) requestClose() }">
    <p class="batch-note">{{ config.note }}</p>
    <n-alert v-if="loadError" type="error">{{ loadError }} <n-button text @click="loadCatalog">重新加载</n-button></n-alert>
    <n-alert v-if="uncertain || refreshError" type="warning" class="batch-warning">
      {{ uncertain ? '部分保存结果未能确认，已暂停提交。请刷新核对明细，不要直接重试这些行。' : '明细已保存，但最新资料未加载完整。请刷新核对，不要重复添加。' }}
      <n-button text :loading="busy" @click="refreshOnly">刷新核对</n-button>
    </n-alert>
    <n-alert v-if="!allowed" type="warning">当前单据状态或权限不允许继续添加，请关闭后核对。</n-alert>
    <n-tabs v-if="$slots.recent" v-model:value="tab" type="line" :disabled="busy">
      <n-tab name="catalog" :disabled="busy">配件库多选</n-tab><n-tab name="recent" :disabled="busy || rows.length > 0">最近导入{{ rows.length ? '（请先清空待添加清单）' : '' }}</n-tab>
    </n-tabs>
    <div v-show="tab === 'recent'"><slot name="recent" :close="requestClose" /></div>
    <template v-if="tab === 'catalog'">
      <div class="batch-split">
        <section class="batch-catalog" aria-label="商品库">
          <div class="batch-search"><n-input v-model:value="query" clearable placeholder="搜索商品名称 / 编号" aria-label="搜索商品名称或编号" :disabled="busy" /><n-checkbox v-model:checked="selectedOnly" :disabled="busy">只看已选</n-checkbox></div>
          <n-tabs v-if="config.kinds.length > 1" v-model:value="kind" type="line" size="small"><n-tab name="all" :disabled="busy">全部</n-tab><n-tab v-for="value in config.kinds" :key="value" :name="value" :disabled="busy">{{ kindLabel(value) }}</n-tab></n-tabs>
          <div class="batch-catalog-meta"><n-checkbox :checked="allSelected" :indeterminate="someSelected && !allSelected" :disabled="busy || !selectable.length || uncertain" @update:checked="selectAll">全选当前筛选</n-checkbox><span>{{ filtered.length }} 款</span></div>
          <n-spin :show="loading"><div class="batch-catalog-scroll">
            <label v-for="product in filtered" :key="product.key" class="batch-product" :class="{ selected: isSelected(product), unavailable: unavailable(product) }">
              <input type="checkbox" :checked="isSelected(product)" :disabled="busy || unavailable(product) || uncertain" :aria-label="`选择 ${product.name} ${product.id}`" @change="toggleProduct(product, $event.target.checked)" />
              <img v-if="product.image" :src="product.image" :alt="product.name" loading="lazy" /><span v-else class="batch-no-image">无图</span>
              <span class="batch-product-name"><strong>{{ product.name }}</strong><small>{{ product.id }} · {{ kindLabel(product.kind) }} · {{ product.unit || '个' }}</small><small v-if="unavailable(product)">{{ scene === 'bom' && existingPartIds.includes(product.id) ? '已在 BOM 中' : '本次已保存' }}</small></span>
            </label>
            <n-empty v-if="!loading && !filtered.length" description="没有匹配的商品" />
          </div></n-spin>
        </section>
        <section class="batch-drafts" aria-label="待添加清单">
          <div class="batch-draft-head"><strong>待添加清单 <small>{{ rows.length }} 行</small></strong><n-button text size="small" :disabled="busy || uncertain || !pending.length" @click="clearDrafts">清空未保存</n-button></div>
          <div class="batch-tools"><span>统一{{ scene === 'bom' ? '用量' : '数量' }}</span><n-input-number v-model:value="batchQty" size="small" :min="scene === 'bom' ? 0.0001 : 1" :precision="scene === 'bom' ? 4 : 0" :disabled="busy || uncertain" :show-button="false" aria-label="统一数量" /><n-button text size="small" :disabled="busy || uncertain || !pending.length" @click="applyQuantity">应用</n-button>
            <template v-if="scene === 'plating'"><PlatingColorPicker v-model="batchColor" :colors="colors" :disabled="busy || uncertain" label="统一电镀颜色" /><n-button text size="small" :disabled="busy || uncertain || !pending.length" @click="applyColor">应用颜色</n-button></template>
          </div>
          <div class="batch-draft-scroll">
            <n-empty v-if="!rows.length" description="从左侧勾选商品，再在这里完善明细" />
            <article v-for="row in rows" :key="row.key" class="batch-row" :class="{ 'is-error': row.error, 'is-saved': row.status === 'saved' }" :data-row="row.key">
              <header><div class="batch-product-name"><strong>{{ row.product.name }}</strong><small>{{ row.product.id }} · {{ kindLabel(row.product.kind) }}</small></div><span v-if="row.status === 'saved'" class="batch-saved">已保存 ✓</span><template v-else><n-button v-if="scene === 'order'" text size="tiny" :disabled="rowLocked(row)" @click="duplicate(row)">再加一行</n-button><n-button text size="small" :disabled="rowLocked(row)" :aria-label="`移除 ${row.product.name}`" @click="removeRow(row)">×</n-button></template></header>
              <div class="batch-fields" :class="{ 'three-fields': config.price || scene === 'plating', 'plating-fields': scene === 'plating' }">
                <div><label :for="`batch-qty-${row.key}`">{{ scene === 'bom' ? '每 1 单位用量' : scene === 'order' ? '订购数量' : scene === 'plating' ? '发出数量' : '数量' }}</label><n-input-number v-model:value="row.qty" :input-props="{ id: `batch-qty-${row.key}` }" size="small" :min="scene === 'bom' ? 0.0001 : 1" :max="scene === 'bom' ? 999999.9999 : undefined" :precision="scene === 'bom' ? 4 : 0" :show-button="false" :disabled="rowLocked(row)" /></div>
                <div><label :for="`batch-unit-${row.key}`">单位</label><n-input v-model:value="row.unit" :input-props="{ id: `batch-unit-${row.key}` }" size="small" :disabled="rowLocked(row) || ['order', 'bom'].includes(scene)" /></div>
                <div v-if="config.price"><label :for="`batch-price-${row.key}`">单价（元）</label><n-input-number v-model:value="row.price" :input-props="{ id: `batch-price-${row.key}` }" size="small" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" :show-button="false" :disabled="rowLocked(row)" :placeholder="scene === 'purchase' ? '可选' : '必填'" /></div>
                <div v-if="scene === 'plating'"><label>电镀颜色</label><PlatingColorPicker :model-value="row.color" :colors="colors" :disabled="rowLocked(row)" :label="`${row.product.name} 电镀颜色`" @update:model-value="code => selectColor(row, code)" /></div>
              </div>
              <div v-if="scene === 'plating'" class="batch-variant">
                <span v-if="row.variantBusy">正在查询对应配件…</span><span v-else-if="!row.color">未选颜色，沿用原页面的无对应配件模式</span><span v-else-if="row.variant?.part">对应配件：{{ row.variant.part.name }}（{{ row.variant.part.id }}）</span>
                <template v-else-if="row.variant?.suggested_name">缺少对应配件：{{ row.variant.suggested_name }} <n-button text type="primary" size="tiny" :disabled="rowLocked(row)" @click="confirmVariant(row)">确认新建</n-button></template><n-button v-else text size="tiny" :disabled="rowLocked(row)" @click="selectColor(row, row.color)">重新查询对应配件</n-button>
              </div>
              <n-button v-if="scene !== 'bom'" text size="tiny" :disabled="busy" @click="row.details = !row.details">{{ row.details ? '收起' : '展开' }}{{ config.weight ? '重量 / ' : '' }}备注</n-button>
              <div v-if="row.details && scene !== 'bom'" class="batch-details">
                <div v-if="config.weight" class="batch-weight"><span>重量（可选）</span><n-input-number v-model:value="row.weight" size="small" :min="0" :precision="2" :show-button="false" :disabled="rowLocked(row)" /><n-select v-model:value="row.weightUnit" size="small" :options="weightUnits" :disabled="rowLocked(row)" /></div>
                <n-input v-model:value="row.note" size="small" placeholder="备注（可选）" :disabled="rowLocked(row)" />
              </div>
              <p v-if="row.error" class="batch-row-error" role="alert">{{ row.error }}</p>
            </article>
          </div>
        </section>
      </div>
      <div class="batch-footer"><span>已保存 {{ savedCount }} 行 · 待处理 {{ pending.length }} 行</span><div><n-button :disabled="busy" @click="requestClose">{{ savedCount || uncertain ? '关闭' : '取消' }}</n-button><n-button type="primary" :loading="busy" :disabled="!allowed || loading || !!loadError || uncertain || refreshError || !pending.length || rows.some(r => r.variantBusy)" @click="submit">{{ savedCount ? '添加剩余' : '统一添加' }} {{ pending.length }} 行</n-button></div></div>
    </template>
  </n-modal>
</template>

<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { NAlert, NButton, NCheckbox, NEmpty, NInput, NInputNumber, NModal, NSelect, NSpin, NTab, NTabs, useDialog, useMessage } from 'naive-ui'
import { loadBatchCatalog, saveBatchRow } from '@/api/batchAdd'
import { findOrCreateVariant, createPartVariant, getPart } from '@/api/parts'
import { batchScenes, makeBatchRow, batchRowError, batchPayload, submitBatchRows } from '@/utils/batchAdd'
import { fmtPrice, parseNum } from '@/utils/ui'
import PlatingColorPicker from './PlatingColorPicker.vue'

const props = defineProps({ scene: { type: String, required: true }, entityId: { type: String, required: true }, allowed: { type: Boolean, default: true }, externalBusy: Boolean, existingPartIds: { type: Array, default: () => [] }, refresh: Function })
const emit = defineEmits(['close', 'saved', 'busy', 'uncertain'])
const message = useMessage(), dialog = useDialog()
const config = computed(() => batchScenes[props.scene])
const products = ref([]), colors = ref([]), rows = ref([]), query = ref(''), kind = ref('all'), selectedOnly = ref(false), tab = ref('catalog')
const loading = ref(false), loadError = ref(''), internalBusy = ref(false), refreshError = ref(false), batchQty = ref(1), batchColor = ref('G')
const busy = computed(() => internalBusy.value || props.externalBusy)
const weightUnits = [{ label: 'kg', value: 'kg' }, { label: 'g', value: 'g' }]
let serial = 0, active = true, catalogSeq = 0
const pending = computed(() => rows.value.filter(row => ['draft', 'failed'].includes(row.status)))
const savedCount = computed(() => rows.value.filter(row => row.status === 'saved').length)
const uncertain = computed(() => rows.value.some(row => row.status === 'uncertain'))
const kindLabel = value => value === 'jewelry' ? '饰品' : props.scene === 'output' ? '组合配件' : '配件'
const isSelected = product => rows.value.some(row => row.product.key === product.key)
const unavailable = product => (props.scene === 'bom' && props.existingPartIds.includes(product.id)) || rows.value.some(row => row.product.key === product.key && ['saved', 'uncertain'].includes(row.status))
const filtered = computed(() => {
  const text = query.value.trim().toLowerCase()
  return products.value.filter(p => (kind.value === 'all' || kind.value === p.kind) && (!selectedOnly.value || isSelected(p)) && (!text || `${p.id} ${p.name}`.toLowerCase().includes(text)))
})
const selectable = computed(() => filtered.value.filter(p => !unavailable(p)))
const allSelected = computed(() => selectable.value.length > 0 && selectable.value.every(isSelected))
const someSelected = computed(() => selectable.value.some(isSelected))
const rowLocked = row => busy.value || uncertain.value || !['draft', 'failed'].includes(row.status)
function setBusy(value) { internalBusy.value = value; emit('busy', value) }
async function loadCatalog() {
  const seq = ++catalogSeq
  loading.value = true; loadError.value = ''
  try {
    const data = await loadBatchCatalog(props.scene)
    if (!active || seq !== catalogSeq) return
    products.value = data.products; colors.value = data.colors
  } catch { if (active && seq === catalogSeq) loadError.value = '商品资料加载失败，不能按空商品库处理。' }
  finally { if (active && seq === catalogSeq) loading.value = false }
}
function toggleProduct(product, checked) {
  if (busy.value || uncertain.value || unavailable(product)) return
  if (!checked) { rows.value = rows.value.filter(row => row.product.key !== product.key || rowLocked(row)); return }
  if (isSelected(product)) return
  const row = makeBatchRow(props.scene, product, String(++serial), colors.value)
  rows.value.push(row)
  const draft = rows.value[rows.value.length - 1]
  // Refresh the default without replacing a unit the user has already edited.
  if (product.kind === 'part' && !['bom', 'order'].includes(props.scene)) {
    const initial = draft.unit
    getPart(product.id).then(({ data }) => {
      if (active && rows.value.includes(draft) && !rowLocked(draft) && draft.unit === initial) draft.unit = data.unit || initial
    }).catch(() => {})
  }
  if (props.scene === 'plating') selectColor(draft, draft.color)
}
function selectAll(checked) { for (const product of selectable.value) toggleProduct(product, checked) }
function removeRow(row) { if (!rowLocked(row)) rows.value = rows.value.filter(item => item.key !== row.key) }
function clearDrafts() { if (!busy.value && !uncertain.value) rows.value = rows.value.filter(row => !['draft', 'failed'].includes(row.status)) }
function duplicate(row) {
  if (rowLocked(row)) return
  rows.value.push({ ...row, key: String(++serial), status: 'draft', error: '', product: row.product })
}
function applyQuantity() {
  if (busy.value || uncertain.value) return
  if (batchQty.value == null || batchQty.value <= 0) return message.warning('请填写有效数量')
  for (const row of pending.value) row.qty = batchQty.value
}
async function selectColor(row, code) {
  if (rowLocked(row)) return
  row.color = code; row.variant = null; row.error = ''
  const seq = ++row.variantSeq
  row.variantBusy = !!code
  if (!code) return
  try {
    const { data } = await findOrCreateVariant(row.product.id, { color_code: code })
    if (active && rows.value.includes(row) && row.variantSeq === seq) row.variant = data
  } catch { if (active && row.variantSeq === seq) row.error = '对应配件查询失败，请重新查询' }
  finally { if (active && row.variantSeq === seq) row.variantBusy = false }
}
function applyColor() { if (!busy.value && !uncertain.value) for (const row of pending.value) selectColor(row, batchColor.value) }
function confirmVariant(row) {
  if (rowLocked(row) || row.variantBusy || !props.allowed) return
  const code = row.color, seq = row.variantSeq
  dialog.warning({ title: '确认新建对应配件', content: `当前没有 ${row.variant?.suggested_name}，确定新建吗？`, positiveText: '确认新建', negativeText: '取消', onPositiveClick: async () => {
    if (!active || rowLocked(row) || row.variantSeq !== seq || !props.allowed || !rows.value.includes(row)) return
    setBusy(true)
    try {
      const { data } = await createPartVariant(row.product.id, { color_code: code })
      row.variant = { part: data, created: true }
      message.success('对应配件已新建')
    } catch { row.error = '新建结果未能确认，请重新查询对应配件后再操作。'; row.variant = null }
    finally { setBusy(false) }
  } })
}
async function refreshPage() {
  if (!props.refresh) return true
  try { const result = await props.refresh(); return result !== false } catch { return false }
}
async function refreshOnly() {
  if (busy.value) return
  setBusy(true)
  try { refreshError.value = !(await refreshPage()) } finally { setBusy(false) }
}
async function submit() {
  if (busy.value || !props.allowed || loading.value || loadError.value || uncertain.value || refreshError.value || !pending.value.length || rows.value.some(r => r.variantBusy)) return
  let invalid = false
  for (const row of pending.value) { row.error = batchRowError(props.scene, row, props.existingPartIds); invalid ||= !!row.error }
  if (invalid) return message.warning('请先修正待添加清单中的提示')
  const id = props.entityId, scene = props.scene
  setBusy(true)
  try {
    await submitBatchRows(rows.value, row => saveBatchRow(scene, id, batchPayload(scene, row, colors.value)), () => active && props.entityId === id && props.allowed)
    if (uncertain.value) emit('uncertain', '保存结果未能确认。请先刷新核对，再决定是否重试。')
    if (savedCount.value || uncertain.value) refreshError.value = !(await refreshPage())
    if (rows.value.every(row => row.status === 'saved') && !refreshError.value) {
      message.success(`已添加 ${savedCount.value} 行`); emit('saved'); emit('close')
    }
  } finally { setBusy(false) }
}
function requestClose() {
  if (busy.value) return
  if (pending.value.length && !uncertain.value) dialog.warning({ title: '关闭添加？', content: `还有 ${pending.value.length} 行未保存，关闭将丢弃这些草稿。已保存的行不会撤销。`, positiveText: '关闭', negativeText: '继续填写', onPositiveClick: () => { if (!busy.value) emit('close') } })
  else emit('close')
}
function allowNavigation() { if (busy.value) { message.warning('正在保存，请稍候'); return false } }
function beforeUnload(event) { if (busy.value) { event.preventDefault(); event.returnValue = '' } }
onBeforeRouteLeave(allowNavigation)
onBeforeRouteUpdate(allowNavigation)
onMounted(() => { loadCatalog(); window.addEventListener('beforeunload', beforeUnload) })
onBeforeUnmount(() => { active = false; ++catalogSeq; window.removeEventListener('beforeunload', beforeUnload) })
</script>

<style scoped>
.batch-add-dialog { max-height: calc(100dvh - 24px); }
.batch-add-dialog :deep(.n-card__content) { min-height: 0; overflow-y: auto; }
.batch-note { color: #7C858C; font-size: 12px; margin: 0 0 16px; }
.batch-warning { margin-bottom: 12px; }
.batch-split { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr); border: 1px solid #ECEDEF; border-radius: 8px; overflow: hidden; }
.batch-catalog, .batch-drafts { min-width: 0; }
.batch-catalog { border-right: 1px solid #ECEDEF; }
.batch-search { padding: 14px; display: flex; align-items: center; gap: 10px; }
.batch-search :deep(.n-checkbox) { white-space: nowrap; font-size: 12px; }
.batch-catalog :deep(.n-tabs) { padding: 0 14px; }
.batch-catalog-meta, .batch-draft-head { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; background: #FAFBFC; font-size: 12px; border-bottom: 1px solid #ECEDEF; }
.batch-catalog-meta { color: #8B9096; }
.batch-catalog-scroll { height: clamp(180px, calc(100dvh - 360px), 440px); overflow-y: auto; }
.batch-product { display: flex; align-items: center; gap: 10px; padding: 12px 14px; border-bottom: 1px solid #F0F1F2; cursor: pointer; }
.batch-product.selected { background: #F0F8F4; }
.batch-product.unavailable { opacity: .65; cursor: not-allowed; }
.batch-product img, .batch-no-image { width: 42px; height: 42px; border-radius: 5px; object-fit: contain; flex-shrink: 0; }
.batch-no-image { display: grid; place-items: center; background: #F3F4F5; color: #A0A5AA; font-size: 10px; }
.batch-product-name { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.batch-product-name strong { display: block; font-size: 12px; font-weight: 600; }
.batch-product-name small { display: block; color: #8B9096; font-size: 10px; margin-top: 3px; }
.batch-tools { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding: 10px 14px; font-size: 11px; border-bottom: 1px solid #ECEDEF; }
.batch-tools :deep(.n-input-number) { width: 90px; }
.batch-draft-scroll { height: clamp(180px, calc(100dvh - 360px), 440px); overflow-y: auto; padding: 12px; background: #FAFBFC; }
.batch-row { background: white; border: 1px solid #E7EAED; border-radius: 7px; padding: 12px; margin-bottom: 10px; }
.batch-row header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.batch-fields { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 10px; align-items: start; }
.batch-fields.three-fields { grid-template-columns: repeat(3,minmax(0,1fr)); }
.batch-fields.plating-fields { grid-template-columns: minmax(0,1fr) 60px minmax(0,1.8fr); }
.batch-fields>div { min-width: 0; }
.batch-fields label { display: block; font-size: 11px; color: #7C858C; margin-bottom: 5px; }
.batch-variant { font-size: 11px; color: #7C858C; margin: 8px 0; overflow-wrap: anywhere; }
.batch-details { display: grid; gap: 8px; margin-top: 8px; }
.batch-weight { display: grid; align-items: center; grid-template-columns: auto minmax(0,1fr) 70px; gap: 8px; font-size: 11px; }
.batch-row.is-error { border-color: #D0A14C; }
.batch-row-error { color: #B36B15; font-size: 11px; margin: 8px 0 0; }
.batch-row.is-saved { background: #F5FAF7; }
.batch-saved { color: #1E7A5A; font-size: 11px; }
.batch-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 16px 0 4px; font-size: 12px; color: #7C858C; background: white; position: sticky; bottom: 0; z-index: 1; }
.batch-footer>div { display: flex; gap: 8px; }
.batch-catalog-scroll :deep(.n-empty), .batch-draft-scroll :deep(.n-empty) { padding: 60px 10px; }
@media (max-width: 720px) {
  .batch-split { grid-template-columns: minmax(0,1fr); }
  .batch-catalog { border-right: 0; border-bottom: 1px solid #ECEDEF; }
  .batch-catalog-scroll { height: 215px; }
  .batch-draft-scroll { height: 300px; padding: 8px; }
  .batch-row { padding: 10px; }
  .batch-fields { gap: 7px; }
  .batch-fields.plating-fields { grid-template-columns: minmax(0,1fr) 42px minmax(0,2fr); }
  .batch-search { padding: 10px; }
  .batch-footer { flex-wrap: wrap; }
}
</style>
