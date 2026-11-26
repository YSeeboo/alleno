<template>
  <OrderSection title="配件备料" :count="mergeSameMaterials ? `${materialGroups.filter(r => !r.missing).length} 类 / ${bomRows.filter(r => !r.missing).length} 项来源` : `${bomRows.filter(r => !r.missing).length} 项`">
    <template #summary><span v-if="loading">读取中</span><span v-if="error" class="wf-amber">BOM／材料加载失败</span><span v-if="(materials || (!loading && !error)) && bomRows.some(r => r.missing)" class="wf-amber">有商品尚未维护 BOM</span><span v-if="bomRows.some(r => r.demand_changed || r.legacy_claim)" class="wf-amber">BOM／旧归属待核对</span><span v-if="estimateError" class="wf-amber">旧估算加载失败</span></template>
    <template #header-extra><div class="wf-actions"><n-button size="small" :type="mergeSameMaterials ? 'primary' : 'default'" :secondary="mergeSameMaterials" :aria-pressed="mergeSameMaterials" title="按相同配件编号和单位汇总，仅合并显示" @click="mergeSameMaterials = !mergeSameMaterials">{{ mergeSameMaterials ? '按商品明细' : '合并同类型' }}</n-button><n-button size="small" :type="accentActions ? 'primary' : 'default'" :secondary="accentActions" @click="openCutting">裁剪统计</n-button><n-button size="small" :type="accentActions ? 'primary' : 'default'" :secondary="accentActions" @click="showPicking = true">配货模拟 / PDF</n-button></div></template>
    <n-alert type="info" :bordered="false" class="wf-notice">理论需求按具体订单商品行的当前 BOM 计算，不扣减公共库存，不是生产时点快照。已安排仅代表配件制作计划，不代表已备料、已发料、成品完成或客户出货；实际发出、回收、损耗与付款仍在对应加工单处理。组合配件可行内展开 BOM。</n-alert>
    <n-spin :show="loading">
      <n-alert v-if="error" type="error">{{ error }} <n-button text @click="load">重新加载</n-button></n-alert>
      <template v-if="!error || materials">
        <n-empty v-if="!bomRows.length" description="无饰品 BOM；直接销售的配件无需 BOM 即可出货" class="wf-empty" />
        <template v-else>
          <p v-if="mergeSameMaterials" class="wf-section-description">同一配件编号、同一单位合并显示；点击配件行展开商品来源。来源需求已包含在汇总中，不另行相加，不改变原生产份额。</p>
          <div v-show="mergeSameMaterials" class="wf-table-wrap"><n-data-table :columns="materialGroupColumns" :data="materialGroups" :bordered="false" :scroll-x="740" :row-key="row => row.key" :row-props="materialGroupRowProps" v-model:expanded-row-keys="expandedMaterialGroups" /></div>
          <div v-show="!mergeSameMaterials" class="wf-table-wrap"><n-data-table :columns="bomColumns" :data="bomRows" :bordered="false" :scroll-x="1040" :row-key="row => row.key" v-model:expanded-row-keys="expandedBomRows" @update:expanded-row-keys="expandBomRows" /></div>
        </template>
        <p v-if="!materials" class="wf-section-description">此处仅查看 BOM 理论用量；已安排制作量与变更核对请前往「生产安排」，未知量不按 0 处理。</p>
      </template>
      <n-collapse style="margin-top:16px"><n-collapse-item title="原备料估算参考" name="estimate">
          <p class="wf-section-description">保留原汇总算法（可能扣减整库成品、合并原批次）。这里的“原他单需求估计”不是当前库存预留台账，估算缺口不是精确制作需求，不用于客户交付判断。</p>
          <n-alert v-if="estimateError" type="error">{{ estimateError }} <n-button text @click="loadEstimates">重新加载估算</n-button></n-alert>
          <n-spin :show="estimateLoading"><div v-if="!estimateError" class="wf-table-wrap"><n-data-table :columns="estimateColumns" :data="estimates" :bordered="false" :row-key="row => row.part_id" /></div></n-spin>
        </n-collapse-item></n-collapse>
    </n-spin>
  </OrderSection>
  <OrderSection v-if="historyError || batches.length || todos.length || historyExpanded.length" title="已有批次与生产关联记录" ref="historySection" tabindex="-1"><template #summary><span v-if="historyError" class="wf-amber">历史加载失败</span><span v-else-if="batches.some(b => b.missing_source)" class="wf-amber">原加工单缺失，待核对</span></template><n-collapse v-model:expanded-names="historyExpanded"><n-collapse-item title="查看原始记录（不计生产份额）" name="history">
    <n-alert v-if="historyError" type="error">{{ historyError }} <n-button text @click="loadHistory">重新加载记录</n-button></n-alert>
    <p class="wf-section-description">按原始记录保留，不推算为本单当前明细的生产份额，不自动预留或补记出货。后续新增制作统一使用上方逐明细安排。</p>
    <n-collapse>
      <n-collapse-item v-for="batch in batches" :key="batch.id" :name="batch.id" :title="`批次 #${batch.id} · ${batch.created_at?.slice(0,10) || ''} · ${batch.supplier_name || '尚未关联商家'}`">
        <n-alert v-if="batch.missing_source" type="warning" class="wf-notice">原加工单已不存在，保留原关联编号供核对，不自动清除或重新分配。</n-alert>
        <div class="wf-actions" style="margin-bottom:12px"><n-button size="small" @click="exportBatch(batch)">导出批次 PDF</n-button><router-link v-if="batch.handcraft_order_id" :to="{ path: `/handcraft/${batch.handcraft_order_id}`, query: { from_order: orderId } }">{{ batch.handcraft_order_id }} → 查看原加工单</router-link></div>
        <p v-for="j in batch.jewelries" :key="j.jewelry_id">{{ j.jewelry_id }} · {{ j.jewelry_name }} × {{ j.quantity }}</p>
        <div class="wf-table-wrap"><n-data-table :columns="historyColumns" :data="batch.items" :bordered="false" /></div>
      </n-collapse-item>
    </n-collapse>
    <div v-if="unbatched.length" class="wf-table-wrap" style="margin-top:16px"><n-data-table :columns="historyColumns" :data="unbatched" :bordered="false" /></div>
  </n-collapse-item></n-collapse></OrderSection>
  <n-modal v-model:show="showCutting" preset="card" title="裁剪统计（原备料口径）" style="width:min(850px,calc(100vw - 24px))">
    <p class="wf-section-description">裁剪备料参考，不是实际发料凭据或客户出货数量。</p><n-button size="small" :loading="exporting" @click="exportCutting">导出裁剪 PDF</n-button>
    <n-spin :show="cuttingLoading"><n-alert v-if="cuttingError" type="error">{{ cuttingError }}</n-alert><div v-else class="wf-table-wrap"><n-data-table :columns="cuttingColumns" :data="cutting" :bordered="false" /></div></n-spin>
  </n-modal>
  <PickingSimulationModal v-model:show="showPicking" :order-id="orderId" :readonly="!editable" />
</template>
<script setup>
import { computed, h, nextTick, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { NAlert, NButton, NCollapse, NCollapseItem, NDataTable, NEmpty, NModal, NSpin, useMessage } from 'naive-ui'
import OrderSection from '@/components/fulfillment/OrderSection.vue'
import PickingSimulationModal from '@/components/picking/PickingSimulationModal.vue'
import { getPartsSummary, getTodo, getTodoBatches, getCuttingStats, downloadCuttingStatsPdf, downloadBatchPdf } from '@/api/orders'
import { getBom } from '@/api/bom'
import { getPartBom, listParts } from '@/api/parts'
import { renderNamedImage } from '@/utils/ui'
import { groupMaterialRows } from '@/utils/orderMaterialGroups'
const props = defineProps({ orderId: { type: String, required: true }, lines: { type: Array, required: true }, materials: Array, editable: Boolean, accentActions: Boolean })
const message = useMessage(), loading = ref(false), error = ref(''), estimates = ref([]), boms = ref({}), parts = ref({})
const estimateError = ref(''), estimateLoading = ref(false)
const batches = ref([]), todos = ref([]), historyError = ref('')
const historyExpanded = ref([]), historySection = ref(null)
async function openHistory() {
  historyExpanded.value = ['history']
  await nextTick()
  historySection.value?.expand?.()
  await nextTick()
  historySection.value?.$el?.scrollIntoView({ block:'start', behavior:'auto' })
  historySection.value?.$el?.focus({ preventScroll:true })
}
defineExpose({ openHistory })
const showPicking = ref(false), showCutting = ref(false), cuttingLoading = ref(false), cuttingError = ref(''), cutting = ref([]), exporting = ref(false)
const expandedBomRows = ref([]), childBoms = ref({})
const mergeSameMaterials = ref(false), expandedMaterialGroups = ref([])
const unbatched = computed(() => todos.value.filter(t => !batches.value.some(b => b.items.some(i => i.id === t.id))))
const bomRows = computed(() => props.lines.filter(l => l.product_type === 'jewelry').flatMap(line => {
  if (props.materials) {
    const demands = props.materials.filter(row => row.order_item_id === line.id)
    const rows = demands.map(row => ({ ...row, key:row.id, line, part_id:row.material_part_id, part:parts.value[row.material_part_id] }))
    // Deleted BOM entries with saved allocations remain visible for review.
    if (!demands.some(row => Number(row.qty_per_unit) > 0)) rows.push({ key:`${line.id}:missing`, line, missing:true })
    return rows
  }
  const rows = boms.value[line.product_id] || []
  if (!rows.length) return [{ key:`${line.id}:missing`, line, missing:true }]
  return rows.map(row => ({ ...row, key:`${line.id}:${row.part_id}`, line, part:parts.value[row.part_id], quantity:Number((row.qty_per_unit * line.quantity).toFixed(7)), allocated:null }))
}))
const materialGroups = computed(() => groupMaterialRows(bomRows.value))
function partCell(row) {
  const p = parts.value[row.part_id], name = row.product_name || p?.name || row.part_name || row.part_id
  return renderNamedImage(name, row.image || p?.image || row.part_image, name, 32)
}
const isComposite = row => !row.missing && !!(parts.value[row.part_id]?.is_composite || row.part_is_composite)
function reviewText(row) {
  if (row.missing) return '尚未维护 BOM（不阻止现货出货）'
  if (!props.materials) return '请在生产安排中核对'
  return [row.demand_changed ? `BOM／订购量已变化，原需求 ${row.snapshot_quantity}；请重新核对安排` : '', row.legacy_claim ? '旧归属待核对' : ''].filter(Boolean).join('；') || '无冲突'
}
const bomColumns = [
  { type:'expand', width:40, expandable:isComposite, renderExpand:renderChildBom },
  { title:'订单明细 / 客户货号', key:'line', width:200, render:r => `${r.line.product_name} · #${r.line.id}${r.line.customer_code ? ` · ${r.line.customer_code}` : ''}` },
  { title:'所需配件', key:'part_id', width:170, render:r => r.missing ? '—' : partCell(r) },
  { title:'单件用量', key:'qty_per_unit', width:90, render:r => r.missing ? '—' : r.qty_per_unit }, { title:'订购', key:'quantity', width:70, render:r => r.line.quantity },
  { title:'理论需求', key:'total', width:110, render:r => r.missing ? '—' : `${props.materials ? r.quantity : Number((r.qty_per_unit * r.line.quantity).toFixed(7))} ${r.unit || r.part?.unit || ''}` },
  { title:'已安排', key:'allocated', width:110, render:r => r.missing || !props.materials ? '—' : `${r.allocated} ${r.unit || ''}` },
  { title:'核对', key:'review', width:250, render:r => h('span', { class:r.missing || r.demand_changed || r.legacy_claim ? 'wf-amber' : '' }, reviewText(r)) },
]
function toggleMaterialGroup(row) {
  if (row.missing) return
  expandedMaterialGroups.value = expandedMaterialGroups.value.includes(row.key) ? expandedMaterialGroups.value.filter(key => key !== row.key) : [...expandedMaterialGroups.value, row.key]
}
function materialGroupRowProps(row) {
  return row.missing ? {} : { class:'material-group-row', onClick:event => {
    if (!event.target.closest('button, a, .n-data-table-expand-trigger')) toggleMaterialGroup(row)
  } }
}
function materialGroupReview(row) {
  if (row.missing) return reviewText(row)
  const notices = []
  const changed = row.sources.filter(source => source.demand_changed).length, legacy = row.sources.filter(source => source.legacy_claim).length
  if (changed) notices.push(`${changed} 项 BOM／订购量已变化`)
  if (legacy) notices.push(`${legacy} 项旧归属待核对`)
  if (row.quantity === null) notices.push('需求量未知')
  if (!props.materials) notices.push('制作量请在生产安排中核对')
  else if (row.allocated === null) notices.push('已安排量未知')
  return notices.length ? `${notices.join('；')}，展开核对来源` : '无冲突'
}
function renderMaterialSources(row) {
  const columns = bomColumns.filter(column => column.key !== 'part_id').map(column => column.key === 'line' ? { ...column, render:source => h('div', [column.render(source), h('small', { class:'material-compact-quantity' }, source.quantity == null ? '需求待核对' : `需求 × ${source.quantity} ${row.unit}`)]) } : column)
  return h('div', { class:'material-group-sources' }, [
    h('p', { class:'wf-section-description' }, `来源明细 · ${row.sources.length} 条（已计入上方汇总）`),
    h(NDataTable, { columns, data:row.sources, bordered:false, scrollX:830, rowKey:source => source.key, expandedRowKeys:expandedBomRows.value, 'onUpdate:expandedRowKeys':keys => { expandedBomRows.value = keys; expandBomRows(keys) } }),
  ])
}
const materialGroupColumns = [
  { type:'expand', width:40, expandable:row => !row.missing, renderExpand:renderMaterialSources },
  { title:'所需配件 / 来源', key:'part_id', width:260, render:row => row.missing ? `${row.line.product_name || row.line.product_id} · #${row.line.id}` : h('div', [
    h(NButton, { text:true, type:'primary', 'aria-expanded':expandedMaterialGroups.value.includes(row.key), 'aria-label':`${expandedMaterialGroups.value.includes(row.key) ? '收起' : '展开'} ${row.product_name || row.part?.name || row.part_name || row.part_id} 的来源明细`, onClick:() => toggleMaterialGroup(row) }, () => partCell(row)),
    h('strong', { class:'material-compact-quantity' }, row.quantity === null ? '需求待核对' : `× ${row.quantity} ${row.unit}`),
    h('small', { class:'wf-subtext' }, `${row.part_id} · ${row.sources.length} 条商品来源`),
  ]) },
  { title:'理论需求合计', key:'quantity', width:140, render:row => row.missing || row.quantity === null ? '—' : `× ${row.quantity} ${row.unit}` },
  { title:'已安排合计', key:'allocated', width:120, render:row => row.missing || row.allocated === null ? '—' : `${row.allocated} ${row.unit}` },
  { title:'核对', key:'review', width:220, render:row => h('span', { class:row.missing || row.demand_changed || row.legacy_claim || row.quantity === null || (props.materials && row.allocated === null) ? 'wf-amber' : '' }, materialGroupReview(row)) },
]
const estimateColumns = [ { title:'配件', key:'part_id', render:partCell }, { title:'原估算需求', key:'total_qty' }, { title:'整库账面量', key:'current_stock' }, { title:'原他单需求估计', key:'reserved_qty' }, { title:'原估算缺口', key:'remaining_qty' },
  { type:'expand', renderExpand:r => h('div', { style:'padding:12px' }, (r.source_jewelries || []).map(s => h('p', s.source_type === 'direct' ? `客户直购 × ${s.order_qty} = ${s.subtotal}` : `${s.jewelry_id} · ${s.jewelry_name}：${s.qty_per_unit} × ${s.order_qty} = ${s.subtotal}`))) },
]
const historyColumns = [ { title:'配件', key:'part_id', render:partCell }, { title:'原清单数量', key:'required_qty' }, { title:'原生产关联', key:'linked_production', render:r => h('div', { class:'wf-actions' }, (r.linked_production || []).map(p => h(RouterLink, { to:{ path:`/${{ plating:'plating', purchase:'purchase-orders', handcraft:'handcraft' }[p.type]}/${p.order_id}`, query:{ from_order:props.orderId } } }, () => `${p.order_id} · ${p.status || ''}`))) } ]
const cuttingColumns = [ { title:'配件编号', key:'part_id' }, { title:'配件', key:'part_name' }, { title:'裁剪长度（cm）', key:'cut_length_cm' }, { title:'裁剪数量', key:'qty' }, { title:'总长度（m）', key:'total', render:r => Math.ceil((r.cut_length_cm * r.qty / 100) * 10 - 1e-8) / 10 } ]
const childColumns = [ { title:'子配件', key:'child_part_name' }, { title:'编号', key:'child_part_id' }, { title:'单件用量', key:'qty_per_unit' }, { title:'单位', key:'child_part_unit' } ]
function renderChildBom(row) {
  const state = childBoms.value[row.part_id]
  if (!state || state.loading) return h('p', '组合配件 BOM 读取中…')
  if (state.error) return h(NAlert, { type:'error' }, { default:() => [state.error, h(NButton, { text:true, onClick:() => openChildren(row.part_id) }, () => '重新加载 BOM')] })
  return h('div', { class:'wf-table-wrap', style:'padding:12px' }, [h('p', '组合配件 BOM（单件参考，不另计当前需求）'), h(NDataTable, { columns:childColumns, data:state.rows, bordered:false })])
}
function expandBomRows(keys) {
  for (const row of bomRows.value) if (keys.includes(row.key) && isComposite(row) && !childBoms.value[row.part_id]) openChildren(row.part_id)
}
let request = 0, estimateRequest = 0, historyRequest = 0, childRequest = 0, cuttingRequest = 0
async function load() {
  const id = ++request; loading.value = true; error.value = ''
  boms.value = {}; parts.value = {}
  try {
    const ids = props.materials ? [] : [...new Set(props.lines.filter(l => l.product_type === 'jewelry').map(l => l.product_id))]
    const [catalog, ...bom] = await Promise.all([listParts({}), ...ids.map(getBom)])
    if (id !== request) return
    parts.value = Object.fromEntries(catalog.data.map(p => [p.id, p])); boms.value = Object.fromEntries(ids.map((key, index) => [key, bom[index].data]))
  } catch (_) { if (id === request) error.value = 'BOM 与备料参考加载失败，不能当作没有需求' }
  finally { if (id === request) loading.value = false }
}
async function loadEstimates() {
  const id = ++estimateRequest; estimateLoading.value = true; estimateError.value = ''; estimates.value = []
  try { const response = await getPartsSummary(props.orderId); if (id === estimateRequest) estimates.value = response.data }
  catch (_) { if (id === estimateRequest) estimateError.value = '原备料估算加载失败，不影响当前生产需求与已安排量' }
  finally { if (id === estimateRequest) estimateLoading.value = false }
}
async function loadHistory() {
  const id = ++historyRequest; historyError.value = ''
  batches.value = []; todos.value = []
  try { const [b, t] = await Promise.all([getTodoBatches(props.orderId), getTodo(props.orderId)]); if (id === historyRequest) { batches.value = b.data.batches || []; todos.value = t.data || [] } }
  catch (_) { if (id === historyRequest) historyError.value = '已有批次记录加载失败' }
}
async function openChildren(partId) {
  if (childBoms.value[partId]?.loading) return
  const generation = childRequest, state = { loading:true, error:'', rows:[] }
  childBoms.value[partId] = state
  try { const response = await getPartBom(partId); if (generation === childRequest) childBoms.value[partId] = { loading:false, error:'', rows:response.data } }
  catch (_) { if (generation === childRequest) childBoms.value[partId] = { loading:false, error:'组合配件 BOM 加载失败', rows:[] } }
}
async function openCutting() {
  const id = ++cuttingRequest
  showCutting.value = true; cuttingLoading.value = true; cuttingError.value = ''; cutting.value = []
  try { const response = await getCuttingStats(props.orderId); if (id === cuttingRequest) cutting.value = response.data.items || [] }
  catch (_) { if (id === cuttingRequest) cuttingError.value = '裁剪统计加载失败' }
  finally { if (id === cuttingRequest) cuttingLoading.value = false }
}
function download(response, filename) { const url = URL.createObjectURL(response.data), link = document.createElement('a'); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url) }
async function exportBatch(batch) { try { download(await downloadBatchPdf(props.orderId, batch.id), `配件清单_${props.orderId}_批次${batch.id}.pdf`) } catch (_) { message.error('批次 PDF 导出失败') } }
async function exportCutting() { if (exporting.value) return; exporting.value = true; try { download(await downloadCuttingStatsPdf(props.orderId), `裁剪统计_${props.orderId}.pdf`) } catch (_) { message.error('裁剪 PDF 导出失败') } finally { exporting.value = false } }
let materialOrderId = props.orderId
watch(() => [props.orderId, props.lines, props.materials], () => { if (materialOrderId !== props.orderId) { mergeSameMaterials.value = false; materialOrderId = props.orderId } ++childRequest; ++cuttingRequest; expandedBomRows.value = []; expandedMaterialGroups.value = []; childBoms.value = {}; showPicking.value = false; showCutting.value = false; load(); loadEstimates(); loadHistory() }, { immediate:true })
</script>
<style scoped>
:deep(.ow-section-title) { flex-wrap:wrap; min-width:0; }
:deep(.material-group-row) { cursor:pointer; }
:deep(.material-group-sources) { padding:12px 16px; border-left:3px solid #D5E6DC; background:#F7FAF8; }
:deep(.material-compact-quantity) { display:none; }
@media (max-width:540px) {
  :deep(.material-compact-quantity) { display:block; margin-top:6px; color:#2F5B44; font-size:12px; }
}
</style>
