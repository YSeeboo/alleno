<template>
  <div class="plating-summary">
    <div v-if="embedded" class="plating-section-title"><h2>电镀汇总</h2><span>按配件明细查看发出与收回</span></div>
    <div v-else class="page-head">
      <h2 class="page-title">电镀汇总</h2>
    </div>

    <div class="toolbar">
      <n-button-group>
        <n-button :type="tab === 'out' ? 'primary' : 'default'" @click="setTab('out')">已发出</n-button>
        <n-button :type="tab === 'in' ? 'primary' : 'default'" @click="setTab('in')">已收回</n-button>
      </n-button-group>

      <div class="filters">
        <n-select v-model:value="archive" :options="archiveOptions" style="width: 150px" />
        <n-date-picker v-model:value="dateRangeRaw" type="daterange" clearable style="width: 240px" placeholder="日期范围" />
        <n-select v-model:value="supplier" :options="supplierOptions" placeholder="商家" clearable style="width: 160px" />
        <n-input v-model:value="qInput" placeholder="搜索 ID 或配件名" clearable style="width: 220px" />
      </div>
    </div>

    <n-spin :show="loading">
      <n-data-table
        :columns="columns"
        :data="rows"
        :row-class-name="rowClassName"
        :scroll-x="1400"
        size="small"
      />
    </n-spin>

    <n-modal v-model:show="lossModal.visible" preset="card" title="确认损耗" style="width: 480px">
      <n-form label-placement="left" label-width="90">
        <n-form-item label="损耗数量">
          <n-input-number v-model:value="lossModal.loss_qty" :min="0.0001" :max="lossModal.row?.unreceived_qty" />
        </n-form-item>
        <n-form-item label="扣款金额">
          <n-input-number v-model:value="lossModal.deduct_amount" :min="0" />
        </n-form-item>
        <n-form-item label="原因">
          <n-input v-model:value="lossModal.reason" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-button @click="lossModal.visible = false" style="margin-right: 8px">取消</n-button>
        <n-button type="primary" @click="submitLoss">确认</n-button>
      </template>
    </n-modal>

    <div class="pager-wrap">
      <n-pagination v-model:page="page" :page-count="pageCount" :page-size="pageSize" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, h } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton, NButtonGroup, NDataTable, NDatePicker, NForm, NFormItem, NInput,
  NInputNumber, NModal, NPagination, NSelect, NSpin, NTag, useMessage,
} from 'naive-ui'
import api from '@/api/index'
import { listDispatchedSummary, listReceivedSummary } from '@/api/platingSummary'
import { getPlatingSuppliers } from '@/api/plating'
import { renderImageThumb } from '@/utils/ui'
import { usePlatingPageQuery } from '@/composables/usePlatingPageQuery'

defineProps({ embedded: { type: Boolean, default: false } })

const { route, active, query, updateQuery, field } = usePlatingPageQuery('summary')
const router = useRouter()

const tab = field('tab', 'out')
const archive = field('archive', 'active')
const archiveOptions = [
  { label: '正常单据', value: 'active' },
  { label: '历史归档', value: 'archived' },
  { label: '全部（含归档）', value: 'all' },
]
const supplier = field('supplier')
const dateRangeRaw = computed({
  get: () => query.value.date_from && query.value.date_to
    ? [new Date(`${query.value.date_from}T00:00:00`).getTime(), new Date(`${query.value.date_to}T00:00:00`).getTime()] : null,
  set: (value) => { void updateQuery({ date_from: value ? tsToLocalDate(value[0]) : null, date_to: value ? tsToLocalDate(value[1]) : null }) },
})
const qInput = ref(query.value.q || '')
const qDebounced = computed(() => query.value.q || '')
const sortByDays = computed(() => query.value.sort === 'days')
const page = computed({
  get: () => Number(query.value.page || 1),
  set: (value) => { void updateQuery({ page: String(value) }, false) },
})
const pageSize = 30

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const supplierOptions = ref([])

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

function tsToLocalDate(ms) {
  const d = new Date(ms)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

let qTimer = null
watch(qInput, (v) => {
  clearTimeout(qTimer)
  if (v === qDebounced.value) return
  qTimer = setTimeout(() => { void updateQuery({ q: v }) }, 300)
})
watch(qDebounced, (value) => { qInput.value = value })

function setTab(t) { void updateQuery({ tab: t, sort: null }) }
function toggleSortDays() { void updateQuery({ sort: sortByDays.value ? null : 'days' }) }

async function loadSuppliers() {
  try {
    const { data: list } = await getPlatingSuppliers()
    supplierOptions.value = list.map((s) => ({ label: s, value: s }))
  } catch (e) {
    message.error('加载商家列表失败')
  }
}

function buildParams() {
  const params = { skip: (page.value - 1) * pageSize, limit: pageSize, archive: archive.value }
  if (supplier.value) params.supplier_name = supplier.value
  if (dateRangeRaw.value) {
    params.date_from = tsToLocalDate(dateRangeRaw.value[0])
    params.date_to = tsToLocalDate(dateRangeRaw.value[1])
  }
  if (qDebounced.value) params.part_keyword = qDebounced.value
  if (tab.value === 'out' && sortByDays.value) params.sort = 'days_out_desc'
  return params
}

let loadVersion = 0
let disposed = false
async function load() {
  if (!active.value || disposed) return
  const version = ++loadVersion
  loading.value = true
  try {
    const fn = tab.value === 'out' ? listDispatchedSummary : listReceivedSummary
    const { data } = await fn(buildParams())
    if (version === loadVersion) {
      rows.value = data.items
      total.value = data.total
    }
  } catch (e) {
    if (version === loadVersion) message.error(e?.response?.data?.detail || '加载汇总数据失败')
  } finally {
    if (version === loadVersion) loading.value = false
  }
}

const renderPart = (row) => h('span', { style: 'display:inline-flex;align-items:center;gap:8px;' }, [
  renderImageThumb(row.part_image, row.part_name, 32),
  h('span', row.part_name),
])

const renderReceivePart = (row) => row.receive_part_id
  ? h('span', { style: 'display:inline-flex;align-items:center;gap:8px;' }, [
      renderImageThumb(row.receive_part_image, row.receive_part_name, 32),
      h('span', row.receive_part_name),
    ])
  : h('span', { style: 'color:#94A3B8' }, '—')

const renderColor = (row) => row.plating_method
  ? h(NTag, { size: 'small', type: 'default', round: true }, { default: () => row.plating_method })
  : h('span', { style: 'color:#94A3B8' }, '—')

function navigateToDetail(kind, id, highlightId) {
  const path = kind === 'plating' ? `/plating/${id}` : `/plating-receipts/${id}`
  sessionStorage.setItem('plating-summary-return', JSON.stringify(route.query))
  router.push({ path, query: { highlight: highlightId } })
}

const renderOrderLink = (row) => h('span', {
  style: 'color:#6366F1;cursor:pointer;font-family:ui-monospace,monospace;',
  onClick: () => navigateToDetail('plating', row.plating_order_id, row.plating_order_item_id),
}, `${row.archived_at ? '历史归档 · ' : ''}${row.plating_order_id}`)

function dayColor(days) {
  if (days === 0) return '#10B981'
  if (days <= 7) return '#F59E0B'
  return '#EF4444'
}

const dispatchedColumns = computed(() => [
  { title: '商家', key: 'supplier_name' },
  {
    key: 'days_out',
    title: () => h('span', {
      style: 'cursor:pointer;user-select:none',
      onClick: toggleSortDays,
    }, ['发出天数', sortByDays.value ? ' ↓' : '']),
    render: (row) => row.days_out == null
      ? h('span', { style: 'color:#94A3B8' }, '—')
      : h('span', { style: `font-weight:600;color:${dayColor(row.days_out)};` }, `${row.days_out} 天`),
  },
  { title: 'ID', key: 'part_id' },
  { title: '配件', key: 'part_name', render: renderPart },
  { title: '电镀颜色', key: 'plating_method', render: renderColor },
  { title: '收回配件', key: 'receive_part_name', render: renderReceivePart },
  { title: '发出日期', key: 'dispatch_date' },
  { title: '发出数量', key: 'qty', align: 'right' },
  { title: '单位', key: 'unit' },
  { title: '重量', key: 'weight', render: (row) => row.weight == null ? '' : `${row.weight} ${row.weight_unit || ''}`.trim() },
  { title: '备注', key: 'note' },
  { title: '电镀单号', key: 'plating_order_id', render: renderOrderLink },
])

const renderReceiptDate = (row) => row.receipts.length === 0
  ? h('span', { style: 'color:#94A3B8' }, '—')
  : row.receipts.map((r) => r.receipt_date).join(', ')

const renderReceiptLinks = (row) => row.receipts.length === 0
  ? h('span', { style: 'color:#94A3B8' }, '—')
  : h('span', null, row.receipts.flatMap((r, idx) => {
      const link = h('span', {
        style: 'color:#6366F1;cursor:pointer;font-family:ui-monospace,monospace;',
        onClick: () => navigateToDetail('receipt', r.receipt_id, r.receipt_item_id),
      }, r.receipt_id)
      return idx < row.receipts.length - 1 ? [link, ', '] : [link]
    }))

const renderLoss = (row) => {
  if (row.archived_at && row.loss_state === 'pending') {
    return h('span', { style: 'color:#94A3B8' }, '历史归档（未核销）')
  }
  if (row.loss_state === 'confirmed') {
    return h('span', { style: 'color:#EF4444;font-weight:600;' }, row.loss_total_qty)
  }
  if (row.loss_state === 'none') {
    return h('span', { style: 'color:#94A3B8' }, '—')
  }
  return h(NButton, {
    size: 'tiny', type: 'error', ghost: true,
    onClick: () => openLossModal(row),
  }, { default: () => '确认损耗' })
}

const receivedColumns = computed(() => [
  { title: '商家', key: 'supplier_name' },
  { title: 'ID', key: 'part_id' },
  { title: '配件', key: 'part_name', render: renderPart },
  { title: '电镀颜色', key: 'plating_method', render: renderColor },
  { title: '收回配件', key: 'receive_part_name', render: renderReceivePart },
  { title: '发出日期', key: 'dispatch_date' },
  { title: '收回日期', key: 'receipt_dates', render: renderReceiptDate },
  { title: '发出数量', key: 'qty', align: 'right' },
  { title: '单位', key: 'unit' },
  { title: '重量', key: 'weight', render: (row) => row.weight == null ? '' : `${row.weight} ${row.weight_unit || ''}`.trim() },
  { title: '已回收', key: 'actual_received_qty', align: 'right' },
  { title: '未回收', key: 'unreceived_qty', align: 'right' },
  { title: '损耗', key: 'loss', render: renderLoss },
  { title: '备注', key: 'note' },
  { title: '电镀单号', key: 'plating_order_id', render: renderOrderLink },
  { title: '回收单号', key: 'receipt_ids', render: renderReceiptLinks },
])

const message = useMessage()
const lossModal = ref({ visible: false, row: null, loss_qty: null, deduct_amount: null, reason: '' })

function openLossModal(row) {
  lossModal.value = {
    visible: true, row,
    loss_qty: row.unreceived_qty,
    deduct_amount: null,
    reason: '',
  }
}

async function submitLoss() {
  const m = lossModal.value
  if (!m.row || !m.loss_qty || m.loss_qty <= 0) {
    message.error('请输入有效的损耗数量')
    return
  }
  try {
    await api.post(`/plating-receipts/${m.row.latest_receipt_id}/confirm-loss`, {
      items: [{
        plating_order_item_id: m.row.plating_order_item_id,
        loss_qty: m.loss_qty,
        deduct_amount: m.deduct_amount,
        reason: m.reason || null,
      }],
    })
    message.success('损耗已确认')
    lossModal.value.visible = false
    await load()
  } catch (e) {
    message.error(e?.response?.data?.detail || '确认损耗失败')
  }
}

const columns = computed(() => tab.value === 'out' ? dispatchedColumns.value : receivedColumns.value)

const rowClassName = (row) => row.is_completed ? 'row-completed' : ''

onMounted(async () => {
  // Clear any stale return state from a prior summary visit so a future
  // direct visit to a detail page won't show a misleading 返回汇总 button.
  sessionStorage.removeItem('plating-summary-return')
  await loadSuppliers()
  await load()
})

watch(() => route.fullPath, () => { if (active.value) void load() })
onBeforeUnmount(() => {
  disposed = true
  clearTimeout(qTimer)
  loadVersion++
})
</script>

<style scoped>
.plating-summary { padding: 4px 0; }
.plating-section-title { display: flex; align-items: center; flex-wrap: wrap; gap: 9px; margin-bottom: 14px; }
.plating-section-title h2 { margin: 0; font-size: 15px; font-weight: 650; }
.plating-section-title span { color: #9AA2A9; font-size: 11px; }
.page-head { margin-bottom: 12px; }
.page-title { font-size: 20px; font-weight: 700; margin: 0; }
.toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; gap: 12px; flex-wrap: wrap;
}
.filters { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.pager-wrap { display: flex; justify-content: flex-end; margin-top: 12px; }
:deep(.row-completed td) {
  background: #F1F5F9 !important;
  color: #94A3B8;
}
@media (max-width: 767px) {
  .filters { width: 100%; }
  .filters > * { flex: 1 1 calc(50% - 4px); min-width: 0; }
  .filters > :deep(.n-date-picker) { flex-basis: 100%; }
  .pager-wrap { overflow-x: auto; }
}
</style>
