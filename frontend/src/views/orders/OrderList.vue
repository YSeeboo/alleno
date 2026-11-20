<template>
  <div class="fulfillment-page order-management">
    <div class="page-breadcrumb">生产 / 订单管理</div>
    <header class="om-head">
      <div><h2 class="page-title">订单管理</h2><p class="om-description">从客户需求到实际交付，每一笔订单清晰可循。</p></div>
      <div class="om-actions"><n-button quaternary :loading="loading" :disabled="deleting" @click="load">刷新</n-button><n-button type="primary" :disabled="deleting" @click="router.push('/orders/create')">＋ 新建订单</n-button></div>
    </header>
    <section class="om-stats" aria-label="全部订单概况">
      <div v-for="stat in stats" :key="stat.label" class="om-stat"><div class="om-stat-label">{{ stat.label }}</div><div class="om-stat-value">{{ loaded ? stat.value : '—' }}<small>笔</small></div><div class="om-stat-note">{{ stat.note }}</div></div>
    </section>
    <n-alert v-if="error" type="error" class="wf-notice">{{ error }} <n-button text type="primary" :disabled="loading" @click="load">重新加载</n-button></n-alert>
    <section aria-label="订单列表">
      <div class="om-list-controls">
        <div class="om-status-filters" aria-label="筛选订单状态"><n-button v-for="entry in statusOptions" :key="entry.value" quaternary :class="{ 'is-selected': status === entry.value }" :aria-pressed="status === entry.value" @click="status = entry.value">{{ entry.label }}<span class="om-filter-count">{{ loaded ? countStatus(entry.value) : '—' }}</span></n-button></div>
        <n-input v-model:value="search" clearable class="om-search" placeholder="搜索订单号或客户" :input-props="{ 'aria-label': '搜索订单号或客户' }" />
      </div>
      <div class="om-filter-meta"><span><strong>{{ filtered.length }}</strong> 笔订单 <span class="om-meta-divider">/</span>生产回收不等于客户出货</span><div class="om-actions"><n-checkbox v-model:checked="historyOnly">仅历史待核对</n-checkbox><n-select v-model:value="sort" :options="sortOptions" class="om-sort" aria-label="订单排序" /></div></div>
      <n-spin :show="loading">
        <div class="om-register">
          <n-data-table v-if="filtered.length" :columns="columns" :data="pagedOrders" :bordered="false" :row-key="row => row.id" :row-props="rowProps" :scroll-x="1080" />
          <n-empty v-else-if="!loading" description="暂无符合条件的订单" class="wf-empty"><template #extra><n-button v-if="hasFilters" text type="primary" @click="clearFilters">清除筛选</n-button></template></n-empty>
          <div class="om-list-footer"><span>共 {{ filtered.length }} 笔 · 每页 {{ pageSize }} 笔</span><n-pagination v-model:page="page" :page-size="pageSize" :item-count="filtered.length" :page-slot="5" size="small" /></div>
        </div>
      </n-spin>
      <p class="om-table-note">足量交付按完整发完的订单明细统计；部分发货不计为完成项，历史订单不自动补记。生产计划、库存预留与实际出货分别核算，现货可直接出货。商品金额不含后续包装费。</p>
    </section>
  </div>
</template>
<script setup>
import { ref, computed, onMounted, h, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NAlert, NButton, NCheckbox, NDataTable, NEmpty, NInput, NPagination, NSelect, NSpin, useDialog, useMessage } from 'naive-ui'
import { listOrders, deleteOrder, getOrderDeletePreview } from '@/api/orders'
import { getFulfillmentBatch } from '@/api/fulfillment'
import { shipmentLabel } from '@/utils/fulfillment'
import { fmtMoney } from '@/utils/ui'
import { orderStatuses, filterOrderRows, reservedOrderText, canDeleteOrder } from '@/utils/orderManagement'
import '@/styles/order-management.css'

const dialog = useDialog(), message = useMessage(), router = useRouter()
const orders = ref([]), summaries = ref({}), loading = ref(false), loaded = ref(false), deleting = ref(false), error = ref('')
const search = ref(''), status = ref(''), historyOnly = ref(false), sort = ref('date'), page = ref(1), pageSize = 7
const statusOptions = [{ label: '全部订单', value: '' }, ...orderStatuses.map(value => ({ label: value, value }))]
const sortOptions = [{ label: '创建日期 · 最新优先', value: 'date' }, { label: '订单金额 · 从高到低', value: 'amount' }]
const countStatus = value => orders.value.filter(order => !value || order.status === value).length
const stats = computed(() => [
  { label: '订单总数', value: orders.value.length, note: '全部订单，含历史记录' },
  { label: '待生产', value: countStatus('待生产'), note: '等待安排与启动' },
  { label: '生产中', value: countStatus('生产中'), note: '制作计划与客户交付分别核算' },
  { label: '已完成', value: countStatus('已完成'), note: '历史订单的实发仍须单独核对' },
])
const filtered = computed(() => filterOrderRows(orders.value, summaries.value, { status: status.value, search: search.value, history: historyOnly.value, sort: sort.value }))
const pagedOrders = computed(() => filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize))
const hasFilters = computed(() => Boolean(status.value || search.value || historyOnly.value))
watch([status, search, historyOnly, sort], () => { page.value = 1 })
watch(() => filtered.value.length, length => { page.value = Math.min(page.value, Math.max(1, Math.ceil(length / pageSize))) })
function clearFilters() { status.value = ''; search.value = ''; historyOnly.value = false; sort.value = 'date'; page.value = 1 }
const rowProps = row => ({ style: 'cursor: pointer;', onClick: () => { if (!deleting.value) router.push(`/orders/${row.id}`) } })
const columns = [
  { title: '订单 / 客户', key: 'id', width: 210, fixed: 'left', render: row => h('div', null, [
    h(NButton, { text: true, class: 'om-order-id', disabled: deleting.value, onClick: event => { event.stopPropagation(); router.push(`/orders/${row.id}`) } }, { default: () => row.id }),
    h('div', { class: 'om-customer' }, [row.customer_name, row.has_barcode ? h('span', { class: 'om-barcode' }, '条码') : null]),
  ]) },
  { title: '订单状态', key: 'status', width: 110, render: row => h('span', { class: `om-status om-status-${orderStatuses.indexOf(row.status)}` }, row.status) },
  { title: '足量交付', key: 'progress', width: 185, render: row => {
    const summary = summaries.value[row.id]
    if (!summary) return h('span', { class: 'om-muted' }, loading.value ? '加载中…' : '加载失败，待重试')
    if (!summary.managed) return h('div', { class: 'om-history' }, ['历史待核对', h('small', { class: 'om-subtext' }, '不按旧状态补记实发')])
    return h('div', { title: shipmentLabel(summary) }, [h('div', { class: 'om-delivery' }, [String(summary.completed_items), h('span', null, ` / ${summary.total_items} 项`)]), h('progress', { class: 'om-progress', value: summary.completed_items, max: Math.max(1, summary.total_items), 'aria-label': `${row.id} 足量交付` })])
  } },
  { title: '待发预留', key: 'reserved', width: 160, render: row => loading.value && !summaries.value[row.id] ? '加载中…' : reservedOrderText(summaries.value[row.id]) },
  { title: '商品金额', key: 'total_amount', width: 170, align: 'right', render: row => h('div', { class: 'om-amount' }, [row.total_amount != null ? `¥${fmtMoney(row.total_amount)}` : '—', summaries.value[row.id] ? h('small', { class: 'om-subtext' }, `${summaries.value[row.id].total_items} 项商品`) : null]) },
  { title: '创建日期', key: 'created_at', width: 120, render: row => row.created_at ? String(row.created_at).slice(0, 10) : '—' },
  { title: '操作', key: 'actions', width: 130, render: row => h('div', { class: 'om-actions', onClick: event => event.stopPropagation() }, [
    h(NButton, { text: true, type: 'primary', size: 'small', disabled: deleting.value, onClick: () => router.push(`/orders/${row.id}`) }, { default: () => '查看 →' }),
    canDeleteOrder(row, summaries.value[row.id]) && !loading.value ? h(NButton, { text: true, type: 'error', size: 'small', disabled: deleting.value, onClick: () => confirmDelete(row) }, { default: () => '删除' }) : null,
  ]) },
]
async function load() {
  if (loading.value) return
  loading.value = true; error.value = ''; summaries.value = {}
  try {
    orders.value = (await listOrders()).data; loaded.value = true
    let failed = false
    for (let i = 0; i < orders.value.length; i += 100) {
      try {
        const { data } = await getFulfillmentBatch(orders.value.slice(i, i + 100).map(order => order.id))
        for (const summary of data) summaries.value[summary.order_id] = summary
      } catch { failed = true }
    }
    if (failed || orders.value.some(order => !summaries.value[order.id])) error.value = '部分订单出货摘要加载失败；未知进度不计为历史订单，请重新加载。'
  } catch (e) { orders.value = []; loaded.value = false; error.value = e.response?.data?.detail || '加载失败，请刷新后重试' }
  finally { loading.value = false }
}
async function confirmDelete(order) {
  if (loading.value || deleting.value || !canDeleteOrder(order, summaries.value[order.id])) return
  deleting.value = true
  try {
    const { data: preview } = await getOrderDeletePreview(order.id)
    dialog.warning({ title: '确认删除订单', content: `删除 ${order.id}，包括 ${preview.item_count} 个明细、${preview.batch_count} 个旧批次及 ${preview.link_count} 个旧生产关联。此操作不可恢复。`, positiveText: '确认删除', negativeText: '返回', onPositiveClick: async () => {
      if (deleting.value) return false
      deleting.value = true
      try { await deleteOrder(order.id); message.success('订单已删除'); await load() }
      catch (e) { message.error(e.response?.data?.detail || '删除失败，请重试'); return false }
      finally { deleting.value = false }
    } })
  } catch (e) { message.error(e.response?.data?.detail || '删除预检失败，请重试') }
  finally { deleting.value = false }
}
onMounted(load)
</script>
