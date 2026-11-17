<template>
  <div class="handcraft-summary">
    <header class="summary-head">
      <div class="section-title"><h2>手工汇总</h2><span>按来源明细查看发出与产出回收</span></div>
      <div class="summary-actions" role="group" aria-label="新建手工单据">
        <n-button type="primary" :disabled="opening" @click="openPage('/handcraft/create')"><template #icon><AddOutline /></template>新建手工单</n-button>
        <n-button type="primary" :disabled="opening" @click="openPage('/handcraft-receipts/create')"><template #icon><AddOutline /></template>新建回收单</n-button>
      </div>
    </header>
    <div class="toolbar">
      <n-button-group aria-label="汇总方向">
        <n-button :type="tab === 'out' ? 'primary' : 'default'" :aria-pressed="tab === 'out'" @click="setTab('out')">已发出</n-button>
        <n-button :type="tab === 'in' ? 'primary' : 'default'" :aria-pressed="tab === 'in'" @click="setTab('in')">已回收</n-button>
      </n-button-group>
      <n-button text size="small" @click="showRules = true">查看统计口径</n-button>
    </div>
    <div class="filters primary-filters">
      <label><span>单据范围</span><n-select :value="filter('archive') || 'active'" :options="archiveOptions" aria-label="单据范围" @update:value="setFilter('archive', $event)" /></label>
      <label><span>商家</span><n-select :value="filter('supplier_name')" :options="suppliers" clearable filterable placeholder="全部商家" aria-label="商家" @update:value="setFilter('supplier_name', $event)" /></label>
      <label class="date-filter"><span>{{ tab === 'out' ? '发出' : '回收' }}日期范围</span><n-date-picker :value="dateRange" type="daterange" clearable start-placeholder="开始日期" end-placeholder="结束日期" aria-label="日期范围" @update:value="setDateRange" /></label>
    </div>
    <div class="filters secondary-filters">
      <label><span>配件 ID</span><n-input v-model:value="inputs.part_id" clearable placeholder="配件 ID 或名称" aria-label="配件 ID" /></label>
      <label><span>产出 ID</span><n-input v-model:value="inputs.output_id" clearable placeholder="产出 ID 或名称" aria-label="产出 ID" /></label>
      <label><span>订单 ID</span><n-input v-model:value="inputs.order_id" clearable placeholder="关联订单 ID" aria-label="订单 ID" /></label>
      <n-button @click="clearFilters">清空筛选</n-button>
    </div>
    <div class="rule" role="note">{{ tab === 'out'
      ? '按发出材料来源分行；只展示同单当前 BOM 中使用该材料的产出，并标注推导关系。多产出共用材料不重复计算发出数量。'
      : '仅统计产出回收，不含剩余材料退回。主行始终为累计真实回收量；日期筛选定位来源，展开可核对范围内外的批次。' }}</div>
    <div class="result-line"><span role="status">共 {{ total }} 条来源明细</span><span>左右滑动查看完整列</span></div>
    <div v-if="error" class="error" role="alert">{{ error }} <n-button size="small" @click="load">重试</n-button></div>
    <n-spin :show="loading">
      <n-data-table :key="tab" :columns="columns" :data="rows" :row-key="rowKey" :scroll-x="tableWidth" :row-class-name="rowClass"
        :expanded-row-keys="expanded" size="small" @update:expanded-row-keys="expanded = $event">
        <template #empty>暂无符合条件的来源明细</template>
      </n-data-table>
    </n-spin>
    <div class="pager"><n-pagination :page="page" :page-count="pageCount" :page-size="30" @update:page="setPage" /></div>

    <n-modal v-model:show="loss.show" preset="card" title="确认损耗" class="summary-modal" :mask-closable="!savingLoss" :closable="!savingLoss">
      <p>{{ loss.row?.output_name }} · {{ loss.row?.handcraft_order_id }} · 产出明细 #{{ loss.row?.handcraft_jewelry_item_id }}</p>
      <p class="loss-context">预期 {{ loss.row?.expected_qty }} · 累计实收 {{ loss.row?.actual_received_qty }} · 已确认损耗 {{ loss.row?.loss_total_qty }} {{ loss.row?.unit }}</p>
      <n-form label-placement="top">
        <n-form-item :label="`损耗数量（${loss.row?.unit || '原明细单位'}）`"><n-input-number v-model:value="loss.qty" :min="1" :max="Math.floor(loss.row?.max_loss_qty || 0)" :precision="0" :disabled="savingLoss" /></n-form-item>
        <n-form-item label="扣款金额（元，可选）"><n-input-number v-model:value="loss.deduct" :min="0" :precision="2" :disabled="savingLoss" /></n-form-item>
        <n-form-item label="原因（可选）"><n-input v-model:value="loss.reason" :disabled="savingLoss" /></n-form-item>
      </n-form>
      <p class="rule">仅确认当前产出来源的损耗；未回收差额不会自动计入损耗。沿用现有业务规则，不支持超量回收。</p>
      <template #footer><div class="modal-actions"><n-button :disabled="savingLoss" @click="loss.show = false">取消</n-button><n-button type="primary" :loading="savingLoss" @click="submitLoss">确认损耗</n-button></div></template>
    </n-modal>
    <n-modal v-model:show="showRules" preset="card" title="统计口径" class="summary-modal">
      <div class="rules-copy">
        <p><b>来源明细：</b>已发出按材料明细，已回收按产出明细分行，不跨手工单合并。同商品多条来源保持独立；待发出草稿不纳入。</p>
        <p><b>材料与产出：</b>按同单当前正数 BOM（含组合配件下级）推导，不是历史绑定。无依据显示“未能匹配产出”，不会猜测或修改历史。</p>
        <p><b>日期与批次：</b>发出使用手工单日期；回收日期筛选命中任一真实回收批次即选中来源。主行保持全部批次累计实收，展开逐批核对日期、数量、单位、单号与备注。</p>
        <p><b>数量与损耗：</b>未回收＝预期－累计真实回收－已确认损耗（最低为零）。不使用包含损耗的旧回收计数作为实收，也不含剩余材料退回或自动耗料。无回收批次的产出也保留，可处理全损。</p>
        <p><b>单位与重量：</b>数量和单位取业务明细，不跨单位相加。发出数量沿用有效实配规则；重量取配货记录，组合材料按详情规则折算 kg 合计。</p>
        <p><b>关联订单：</b>只显示当前来源直接关联的订单，不把同手工单其他来源的订单混入。两个方向的筛选、页码分别记忆；归档单据不可确认损耗。</p>
      </div>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NButtonGroup, NDataTable, NDatePicker, NForm, NFormItem, NInput, NInputNumber, NModal, NPagination, NSelect, NSpin, useMessage } from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'
import api from '@/api/index'
import { getHandcraftSuppliers } from '@/api/handcraft'
import { listHandcraftDispatchedSummary, listHandcraftReceivedSummary } from '@/api/handcraftSummary'
import { useHandcraftPageQuery } from '@/composables/useHandcraftPageQuery'
import { rememberHandcraftSummaryReturn } from '@/utils/handcraftNavigation'
import { renderImageThumb } from '@/utils/ui'

defineProps({ embedded: { type: Boolean, default: false } })
const { route, active, query, updateQuery } = useHandcraftPageQuery('summary')
const router = useRouter(), message = useMessage()
const tab = computed(() => query.value.tab || 'out')
const prefix = computed(() => tab.value === 'in' ? 'in_' : '')
const filter = (name) => query.value[prefix.value + name] || null
const names = ['archive', 'supplier_name', 'date_from', 'date_to', 'part_id', 'output_id', 'order_id', 'page']
const textNames = ['part_id', 'output_id', 'order_id']
const inputs = ref({ part_id: filter('part_id') || '', output_id: filter('output_id') || '', order_id: filter('order_id') || '' })
const archiveOptions = [{ label: '正常单据', value: 'active' }, { label: '历史归档', value: 'archived' }, { label: '全部（含归档）', value: 'all' }]
const suppliers = ref([]), rows = ref([]), total = ref(0), loading = ref(false), error = ref(''), expanded = ref([])
const showRules = ref(false), opening = ref(false), savingLoss = ref(false)
const loss = ref({ show: false, row: null, qty: null, deduct: null, reason: '' })
const page = computed(() => Number(filter('page') || 1))
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / 30)))
const dateRange = computed(() => filter('date_from') && filter('date_to')
  ? [new Date(`${filter('date_from')}T00:00:00`).getTime(), new Date(`${filter('date_to')}T00:00:00`).getTime()] : null)
function localDate(ts) { const d = new Date(ts); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
let timer, version = 0, disposed = false
function pendingText() { return Object.fromEntries(textNames.map(name => [prefix.value + name, inputs.value[name]])) }
async function flush() {
  clearTimeout(timer)
  const patch = pendingText()
  if (textNames.some(name => (inputs.value[name] || '').trim() !== (filter(name) || ''))) await updateQuery(patch)
}
watch(inputs, () => { clearTimeout(timer); timer = setTimeout(() => { void flush() }, 300) }, { deep: true })
function syncInputs() {
  clearTimeout(timer)
  inputs.value = Object.fromEntries(textNames.map(name => [name, filter(name) || '']))
}
async function setFilter(name, value) { await updateQuery({ ...pendingText(), [prefix.value + name]: value }) }
async function setDateRange(value) { await updateQuery({ ...pendingText(), [prefix.value + 'date_from']: value ? localDate(value[0]) : null, [prefix.value + 'date_to']: value ? localDate(value[1]) : null }) }
async function setTab(value) { await flush(); await updateQuery({ tab: value }, false) }
async function setPage(value) { await flush(); await updateQuery({ [prefix.value + 'page']: String(value) }, false) }
function clearFilters() { clearTimeout(timer); inputs.value = { part_id: '', output_id: '', order_id: '' }; void updateQuery(Object.fromEntries([...names.map(name => [prefix.value + name, null]), ...(tab.value === 'out' ? [['sort', null]] : [])])) }
async function openPage(path, detail = {}) {
  if (opening.value) return
  opening.value = true
  try {
    await flush()
    if (disposed || !active.value) return
    rememberHandcraftSummaryReturn(route.query)
    await router.push({ path, query: { from: 'handcraft-summary', ...detail } })
  } finally { opening.value = false }
}
async function load() {
  if (disposed || !active.value) return
  const current = ++version
  loading.value = true; error.value = ''; rows.value = []; total.value = 0
  const params = Object.fromEntries(names.filter(name => name !== 'page' && filter(name)).map(name => [name, filter(name)]))
  params.skip = (page.value - 1) * 30; params.limit = 30
  if (tab.value === 'out' && query.value.sort === 'days') params.sort = 'days_out_desc'
  try {
    const { data } = await (tab.value === 'out' ? listHandcraftDispatchedSummary : listHandcraftReceivedSummary)(params)
    if (current !== version || disposed || !active.value) return
    rows.value = data.items; total.value = data.total
    if (page.value > pageCount.value) await updateQuery({ [prefix.value + 'page']: String(pageCount.value) }, false)
  } catch (e) {
    if (current === version && !disposed && active.value) error.value = e?.response?.data?.detail || '加载手工汇总失败'
  } finally { if (current === version && !disposed) loading.value = false }
}
const small = (text) => h('div', { class: 'cell-sub' }, text)
const stack = (children) => h('div', { class: 'cell-stack' }, children)
const documentLink = (text, path, detail = {}) => h(NButton, { text: true, type: 'info', size: 'small', class: 'document-link', onClick: () => openPage(path, detail) }, { default: () => text })
const sourceLink = row => stack([documentLink(row.handcraft_order_id, `/handcraft/${encodeURIComponent(row.handcraft_order_id)}`, {
  highlight: String(tab.value === 'out' ? row.handcraft_part_item_id : row.handcraft_jewelry_item_id), item_type: tab.value === 'out' ? 'part' : 'jewelry',
}), row.archived_at ? small('历史归档') : null])
const receiptLinks = row => row.receipts.length ? (tab.value === 'out'
  ? stack([...new Set(row.receipts.map(batch => batch.receipt_id))].map(id => documentLink(id, `/handcraft-receipts/${encodeURIComponent(id)}`)))
  : stack(row.receipts.map(batch => stack([
  documentLink(batch.receipt_id, `/handcraft-receipts/${encodeURIComponent(batch.receipt_id)}`, { highlight: String(batch.receipt_item_id) }),
  small(`${batch.receipt_date} · ${batch.qty} ${batch.unit || ''}`),
])))) : '—'
const orderLinks = row => row.order_ids.length ? stack(row.order_ids.map(id => documentLink(id, `/orders/${encodeURIComponent(id)}`))) : '—'
function product(name, image, id) { return h('div', { class: 'product' }, [renderImageThumb(image, name, 32), h('div', [h('div', name || '—'), id ? small(id) : null])]) }
const remarks = row => stack([h('div', `明细备注：${row.note || '—'}`), row.document_note ? small(`单据备注：${row.document_note}`) : null, tab.value === 'in' ? small('回收备注见对应批次') : null])
function batchHit(batch) { return (!filter('date_from') || batch.receipt_date >= filter('date_from')) && (!filter('date_to') || batch.receipt_date <= filter('date_to')) }
function renderBatches(row) {
  return h('section', { class: 'batch-panel', 'aria-label': `${row.output_name}的回收批次` }, [
    h('b', `回收批次 · ${row.output_name || row.output_id} · ${row.handcraft_order_id} · 产出明细 #${row.handcraft_jewelry_item_id}`),
    ...row.receipts.map(batch => h('div', { class: 'batch' }, [h('span', batch.receipt_date),
      documentLink(batch.receipt_id, `/handcraft-receipts/${encodeURIComponent(batch.receipt_id)}`, { highlight: String(batch.receipt_item_id) }),
      h('b', `${batch.qty} ${batch.unit || ''}`), stack([h('div', `明细备注：${batch.note || '—'}`), small(`单据备注：${batch.document_note || '—'}`)]),
      small(filter('date_from') || filter('date_to') ? batchHit(batch) ? '范围内' : '范围外' : '全部批次'),
    ])), row.receipts.length ? small('主行始终显示该来源全部批次累计真实回收，已确认损耗不计入实收。') : small('尚无真实回收批次。'),
  ])
}
function renderLoss(row) {
  return stack([row.loss_total_qty ? h('span', { class: 'loss-number' }, `${row.loss_total_qty}（已确认）`) : null,
    row.archived_at ? small('历史归档，不可核销') : row.max_loss_qty >= 1 ? h(NButton, { size: 'tiny', type: 'error', ghost: true, onClick: () => {
      loss.value = { show: true, row, qty: Math.floor(row.max_loss_qty), deduct: null, reason: '' }
    } }, { default: () => row.loss_total_qty ? '继续确认' : '确认损耗' }) : row.unreceived_qty > 0 ? small('计数差异，请核对来源明细') : !row.loss_total_qty ? '—' : null])
}
const merchant = { title: '商家', key: 'supplier_name', width: 160, fixed: 'left' }
const tail = [
  { title: '备注', key: 'note', width: 240, render: remarks },
  { title: '手工单号', key: 'handcraft_order_id', width: 170, render: sourceLink },
  { title: '回收单号', key: 'receipts', width: 190, render: receiptLinks },
  { title: '关联订单号', key: 'order_ids', width: 170, render: orderLinks },
]
const dispatchedColumns = computed(() => [merchant,
  { title: () => h(NButton, { text: true, size: 'small', onClick: async () => { await flush(); await updateQuery({ sort: query.value.sort === 'days' ? null : 'days' }) } }, { default: () => `发出天数 ${query.value.sort === 'days' ? '↓' : '↕'}` }), key: 'days_out', width: 110, render: row => row.days_out == null ? '—' : h('span', { class: row.days_out > 7 ? 'late' : 'days' }, `${row.days_out} 天`) },
  { title: 'ID', key: 'part_id', width: 150 },
  { title: '配件', key: 'part_name', width: 200, render: row => product(row.part_name, row.part_image) },
  { title: '发出数量', key: 'qty', width: 100, align: 'right' }, { title: '单位', key: 'unit', width: 65 },
  { title: '重量', key: 'weight', width: 115, render: row => row.weight == null ? '—' : `${Number(row.weight.toFixed(4))} ${row.weight_unit || ''}` },
  { title: '产出', key: 'outputs', width: 245, render: row => row.outputs.length ? stack([
    ...row.outputs.map(output => product(output.output_name, output.output_image, output.output_id)), small('同单当前 BOM 关系推导'),
  ]) : stack(['未能匹配产出', small('缺少依据，不推测历史用途')]) },
  { title: '发出日期', key: 'dispatch_date', width: 115 }, ...tail,
])
const receivedColumns = computed(() => [merchant,
  { title: 'ID', key: 'output_id', width: 150 },
  { title: '产出', key: 'output_name', width: 220, render: row => stack([product(row.output_name, row.output_image), small(`产出明细 #${row.handcraft_jewelry_item_id}`)]) },
  { title: '预期回收数量', key: 'expected_qty', width: 120, align: 'right' },
  { title: '实际回收数量', key: 'actual_received_qty', width: 120, align: 'right', render: row => stack([String(row.actual_received_qty), small('累计真实回收')]) },
  { title: '单位', key: 'unit', width: 65 }, { title: '未回收数量', key: 'unreceived_qty', width: 110, align: 'right' },
  { title: '损耗', key: 'loss', width: 160, render: renderLoss }, { title: '发出日期', key: 'dispatch_date', width: 115 },
  { title: '回收日期', key: 'receipt_dates', width: 150, render: row => stack([
    ...row.receipts.map(batch => h('span', batch.receipt_date)),
    h(NButton, { text: true, type: 'info', size: 'small', 'aria-expanded': expanded.value.includes(rowKey(row)), onClick: () => {
      const key = rowKey(row); expanded.value = expanded.value.includes(key) ? expanded.value.filter(value => value !== key) : [...expanded.value, key]
    } }, { default: () => `${row.receipts.length} 批 · ${expanded.value.includes(rowKey(row)) ? '收起' : '展开'}` }),
  ]) }, ...tail,
  // Hide the library's extra expand column: the date cell is the accessible trigger.
  { type: 'expand', width: 0, className: 'summary-expand-control', renderExpand: renderBatches },
])
const columns = computed(() => tab.value === 'out' ? dispatchedColumns.value : receivedColumns.value)
const tableWidth = computed(() => columns.value.reduce((sum, column) => sum + column.width, 0))
const rowKey = row => tab.value === 'out' ? `material-${row.handcraft_part_item_id}` : `output-${row.handcraft_jewelry_item_id}`
const rowClass = row => row.is_completed ? 'row-completed' : ''
async function submitLoss() {
  if (savingLoss.value) return
  const { row, qty, deduct, reason } = loss.value
  if (!row || row.archived_at || !Number.isInteger(qty) || qty < 1 || qty > row.max_loss_qty || (deduct != null && (!Number.isFinite(deduct) || deduct < 0))) {
    message.error('请检查损耗数量与扣款金额，产出损耗须为差额内的正整数'); return
  }
  savingLoss.value = true
  try {
    await api.post(`/handcraft/${encodeURIComponent(row.handcraft_order_id)}/items/${row.handcraft_jewelry_item_id}/confirm-loss`, { item_type: 'jewelry', loss_qty: qty, deduct_amount: deduct, reason: reason || null })
    if (disposed) return
    loss.value.show = false; message.success('损耗已确认'); await load()
  } catch (e) { if (!disposed) message.error(e?.response?.data?.detail || '确认损耗失败') }
  finally { savingLoss.value = false }
}
watch(() => route.fullPath, () => { if (active.value) { syncInputs(); expanded.value = []; void load() } })
onMounted(() => {
  void load()
  getHandcraftSuppliers().then(({ data }) => { if (!disposed) suppliers.value = data.map(value => ({ label: value, value })) }).catch(() => { if (!disposed) message.error('加载商家列表失败') })
})
onBeforeUnmount(() => { disposed = true; version++; clearTimeout(timer) })
</script>

<style scoped>
.handcraft-summary { min-width: 0; padding: 4px 0; container-type: inline-size; }
.summary-head, .toolbar, .result-line { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 16px; }
.section-title { display: flex; align-items: center; flex-wrap: wrap; gap: 9px; }
.section-title h2 { margin: 0; font-size: 15px; font-weight: 650; }
.section-title span { color: #9aa2a9; font-size: 11px; }
.summary-actions { display: flex; gap: 9px; flex-shrink: 0; }
.filters { display: grid; gap: 10px; margin-bottom: 12px; }
.primary-filters { grid-template-columns: 150px 180px minmax(240px, 1fr); }
.secondary-filters { grid-template-columns: repeat(3, minmax(0, 1fr)) auto; align-items: end; }
.filters label { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.filters label > span { color: #7d878f; font-size: 11px; }
.rule { color: #79878d; font-size: 11px; background: #eef2f3; padding: 9px 11px; border-radius: 6px; margin: 4px 0 15px; }
.result-line { color: #8d969e; font-size: 11px; margin-bottom: 9px; }
.pager { display: flex; justify-content: flex-end; overflow: auto; margin-top: 15px; }
.error { padding: 12px; color: #b34343; }
:deep(.cell-stack) { display: flex; flex-direction: column; align-items: flex-start; gap: 7px; }
:deep(.cell-sub) { color: #94a3ab; font-size: 10px; line-height: 1.6; white-space: normal; overflow-wrap: anywhere; }
:deep(.document-link) { max-width: 100%; font-family: ui-monospace, monospace; font-size: 11px; }
:deep(.document-link .n-button__content) { white-space: normal; overflow-wrap: anywhere; }
:deep(.product) { display: flex; align-items: center; gap: 8px; }
:deep(.summary-expand-control) { display: none; padding: 0 !important; width: 0; }
:deep(.summary-expand-control > *) { display: none; }
:deep(.row-completed td) { background: #f1f5f9 !important; color: #94a3b8; }
:deep(.days) { color: #d68722; font-weight: 600; }
:deep(.late), :deep(.loss-number) { color: #c35757; font-weight: 600; }
:deep(.batch-panel) { position: sticky; left: 0; width: min(100cqw - 36px, 1100px); box-sizing: border-box; padding: 10px; color: #587166; white-space: normal; overflow-wrap: anywhere; }
:deep(.batch) { display: grid; grid-template-columns: 100px 160px 85px minmax(130px, 1fr) 65px; gap: 12px; align-items: start; border-top: 1px solid #e2eae4; margin-top: 9px; padding: 10px 0; font-size: 12px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
.loss-context { color: #79878d; font-size: 12px; }
.rules-copy { line-height: 1.9; font-size: 13px; }
@container (max-width: 720px) {
  .summary-head { flex-wrap: wrap; gap: 14px; }
  .summary-actions { width: 100%; }
  .summary-actions > .n-button { flex: 1; min-width: 0; padding: 0 9px; font-size: 12px; }
  .primary-filters, .secondary-filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .date-filter { grid-column: 1 / -1; }
  :deep(.batch) { grid-template-columns: minmax(0, 1fr) auto; gap: 7px; }
  :deep(.batch > :nth-child(4)) { grid-column: 1 / -1; }
}
</style>
<style>
.summary-modal.n-card { width: min(520px, calc(100vw - 32px)); max-height: calc(100dvh - 40px); overflow: auto; }
</style>
