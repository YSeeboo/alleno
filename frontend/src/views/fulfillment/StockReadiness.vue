<template>
  <div class="fulfillment-page">
    <div class="page-header"><div class="page-breadcrumb">生产 / 库存备货</div><h2 class="page-title">库存备货</h2><div class="page-divider"></div></div>
    <div class="filter-bar">
      <n-input v-model:value="search" clearable placeholder="搜索客户、订单或商品" style="width:280px" :input-props="{ 'aria-label': '搜索备货明细' }" />
      <n-checkbox v-model:checked="onlyGap">只看待补齐</n-checkbox>
      <div class="filter-bar-end"><n-button :loading="loading" @click="load">刷新并核对</n-button></div>
    </div>
    <n-alert type="info" :bordered="false" class="wf-notice">预留库存不改变实物总量；取消预留不等于退料或退货。客户确认出货、材料发出及其他出库均不能占用这些待发预留。</n-alert>
    <n-alert v-if="error" type="error" class="wf-notice">{{ error }}</n-alert>
    <n-spin :show="loading">
      <n-data-table v-if="rows.length" :columns="columns" :data="rows" :bordered="false" :scroll-x="1050" />
      <n-empty v-else-if="!loading" description="暂无符合条件的备货明细" class="wf-empty" />
    </n-spin>
    <ReservationDialog v-model:show="showReservation" :order-id="selected?.order.order_id" :line="selected?.line" :release="release" @saved="load" />
  </div>
</template>
<script setup>
import { ref, computed, onMounted, h } from 'vue'
import { RouterLink } from 'vue-router'
import { NAlert, NButton, NCheckbox, NDataTable, NEmpty, NInput, NSpin } from 'naive-ui'
import { listOrders } from '@/api/orders'
import { getFulfillmentBatch } from '@/api/fulfillment'
import ProductCell from '@/components/fulfillment/ProductCell.vue'
import ReservationDialog from '@/components/fulfillment/ReservationDialog.vue'
const summaries = ref([]), loading = ref(false), search = ref(''), onlyGap = ref(false), error = ref('')
const selected = ref(null), release = ref(false), showReservation = ref(false)
const rows = computed(() => summaries.value.flatMap(order => order.lines.map(line => ({ order, line }))).filter(({ order, line }) => (!onlyGap.value || Number(line.gap) > 0) && `${order.order_id} ${order.customer_name} ${line.product_id} ${line.product_name}`.toLowerCase().includes(search.value.trim().toLowerCase())))
const columns = [
  { title: '订单 / 客户', key: 'order', render: row => h('div', null, [h(RouterLink, { to: `/orders/${row.order.order_id}` }, { default: () => row.order.order_id }), h('small', { class: 'wf-subtext' }, row.order.customer_name)]) },
  { title: '商品明细', key: 'line', render: row => h(ProductCell, { line: row.line }) },
  { title: '剩余待发', key: 'remaining', render: row => `${row.line.remaining ?? '未核实'} ${row.line.unit}` },
  { title: '本行预留', key: 'reserved', render: row => row.order.managed ? row.line.reserved : '待核对' },
  { title: '公共可用', key: 'public_available', render: row => `${row.line.public_available} ${row.line.unit}` },
  { title: '尚待备货', key: 'gap', render: row => h('span', { class: 'wf-amber' }, row.line.gap ?? '—') },
  { title: '操作', key: 'actions', render: row => row.order.editable ? h('div', { class: 'wf-actions' }, [
    h(NButton, { text: true, type: 'primary', onClick: () => edit(row, false) }, { default: () => '预留库存' }),
    Number(row.line.reserved) ? h(NButton, { text: true, type: 'primary', onClick: () => edit(row, true) }, { default: () => '取消预留' }) : null,
  ]) : h(RouterLink, { to: `/orders/${row.order.order_id}` }, { default: () => row.order.managed ? '查看订单' : '先核对历史' }) },
]
function edit(row, releasing) { selected.value = row; release.value = releasing; showReservation.value = true }
async function load() { loading.value = true; error.value = ''; try { const { data } = await listOrders(); const ids = data.filter(o => ['待生产', '生产中'].includes(o.status)).map(o => o.id); const results = []; for (let index = 0; index < ids.length; index += 100) results.push(...(await getFulfillmentBatch(ids.slice(index, index + 100))).data); summaries.value = results } catch (e) { error.value = e.response?.data?.detail || '加载失败' } finally { loading.value = false } }
onMounted(load)
</script>
