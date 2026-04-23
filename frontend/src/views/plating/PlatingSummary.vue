<template>
  <div class="plating-summary">
    <div class="page-head">
      <h2 class="page-title">电镀汇总</h2>
    </div>

    <div class="toolbar">
      <n-button-group>
        <n-button :type="tab === 'out' ? 'primary' : 'default'" @click="setTab('out')">已发出</n-button>
        <n-button :type="tab === 'in' ? 'primary' : 'default'" @click="setTab('in')">已收回</n-button>
      </n-button-group>

      <div class="filters">
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

    <div class="pager-wrap">
      <n-pagination v-model:page="page" :page-count="pageCount" :page-size="pageSize" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton, NButtonGroup, NDataTable, NDatePicker, NInput, NPagination, NSelect, NSpin, NTag,
} from 'naive-ui'
import { listDispatchedSummary, listReceivedSummary } from '@/api/platingSummary'
import { getPlatingSuppliers } from '@/api/plating'
import { renderImageThumb } from '@/utils/ui'

const route = useRoute()
const router = useRouter()

const tab = ref('out')
const supplier = ref(null)
const dateRangeRaw = ref(null)
const qInput = ref('')
const qDebounced = ref('')
const sortByDays = ref(false)
const page = ref(1)
const pageSize = 30

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const supplierOptions = ref([])

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

function syncStateFromQuery() {
  const q = route.query
  tab.value = q.tab === 'in' ? 'in' : 'out'
  supplier.value = q.supplier || null
  if (q.date_from && q.date_to) {
    const from = new Date(q.date_from).getTime()
    const to = new Date(q.date_to).getTime()
    dateRangeRaw.value = [from, to]
  } else {
    dateRangeRaw.value = null
  }
  qInput.value = q.q || ''
  qDebounced.value = q.q || ''
  sortByDays.value = q.sort === 'days'
  page.value = parseInt(q.page) || 1
}

function pushQuery() {
  const q = {}
  if (tab.value !== 'out') q.tab = tab.value
  if (supplier.value) q.supplier = supplier.value
  if (dateRangeRaw.value) {
    q.date_from = new Date(dateRangeRaw.value[0]).toISOString().slice(0, 10)
    q.date_to = new Date(dateRangeRaw.value[1]).toISOString().slice(0, 10)
  }
  if (qDebounced.value) q.q = qDebounced.value
  if (sortByDays.value) q.sort = 'days'
  if (page.value > 1) q.page = page.value
  router.replace({ query: q })
}

let qTimer = null
watch(qInput, (v) => {
  clearTimeout(qTimer)
  qTimer = setTimeout(() => { qDebounced.value = v; page.value = 1 }, 300)
})

function setTab(t) { tab.value = t; page.value = 1; sortByDays.value = false }
function toggleSortDays() { sortByDays.value = !sortByDays.value; page.value = 1 }

async function loadSuppliers() {
  const list = await getPlatingSuppliers()
  supplierOptions.value = list.map((s) => ({ label: s, value: s }))
}

function buildParams() {
  const params = { skip: (page.value - 1) * pageSize, limit: pageSize }
  if (supplier.value) params.supplier_name = supplier.value
  if (dateRangeRaw.value) {
    params.date_from = new Date(dateRangeRaw.value[0]).toISOString().slice(0, 10)
    params.date_to = new Date(dateRangeRaw.value[1]).toISOString().slice(0, 10)
  }
  if (qDebounced.value) params.part_keyword = qDebounced.value
  if (tab.value === 'out' && sortByDays.value) params.sort = 'days_out_desc'
  return params
}

async function load() {
  loading.value = true
  try {
    const fn = tab.value === 'out' ? listDispatchedSummary : listReceivedSummary
    const data = await fn(buildParams())
    rows.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
  pushQuery()
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
}, row.plating_order_id)

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

const columns = computed(() => tab.value === 'out' ? dispatchedColumns.value : [])

const rowClassName = (row) => row.is_completed ? 'row-completed' : ''

onMounted(async () => {
  syncStateFromQuery()
  await loadSuppliers()
  await load()
})

watch([tab, supplier, dateRangeRaw, qDebounced, sortByDays, page], load)
</script>

<style scoped>
.plating-summary { padding: 4px 0; }
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
</style>
