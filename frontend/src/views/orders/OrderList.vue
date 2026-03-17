<template>
  <div>
    <div class="page-header">
      <div class="page-breadcrumb">生产 / 订单管理</div>
      <h2 class="page-title">订单管理</h2>
      <div class="page-divider"></div>
    </div>
    <div class="filter-bar">
      <n-select
        v-model:value="filterStatus"
        :options="statusOptions"
        clearable
        placeholder="筛选状态"
        style="width: 140px;"
        @update:value="load"
      />
      <div class="filter-bar-end">
        <n-button type="primary" @click="router.push('/orders/create')">新建订单</n-button>
      </div>
    </div>
    <n-spin :show="loading">
      <n-data-table v-if="orders.length > 0" :columns="columns" :data="orders" :bordered="false" :row-props="rowProps" />
      <n-empty v-else-if="!loading" description="暂无订单" style="margin-top: 24px;" />
    </n-spin>
  </div>
</template>

<script setup>
import { ref, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NSelect, NDataTable, NSpin, NEmpty } from 'naive-ui'
import { listOrders } from '@/api/orders'

const router = useRouter()
const loading = ref(true)
const orders = ref([])
const filterStatus = ref(null)
const statusOptions = [
  { label: '待生产', value: '待生产' },
  { label: '生产中', value: '生产中' },
  { label: '已完成', value: '已完成' },
]

const load = async () => {
  loading.value = true
  try {
    const params = {}
    if (filterStatus.value) params.status = filterStatus.value
    const { data } = await listOrders(params)
    orders.value = data
  } finally {
    loading.value = false
  }
}

const rowProps = (row) => ({ style: 'cursor: pointer;', onClick: () => router.push(`/orders/${row.id}`) })

const columns = [
  { title: '订单号', key: 'id' },
  { title: '客户名', key: 'customer_name' },
  {
    title: '状态',
    key: 'status',
    render: (r) => {
      const map = {
        '待生产': 'badge-amber',
        '生产中': 'badge-indigo',
        '已完成': 'badge-green',
      }
      const cls = map[r.status] || 'badge-gray'
      return h('span', { class: `badge ${cls}` }, `• ${r.status}`)
    },
  },
  { title: '总金额', key: 'total_amount', render: (r) => r.total_amount?.toFixed(2) ?? '-' },
  { title: '创建时间', key: 'created_at', render: (r) => new Date(r.created_at).toLocaleString('zh-CN') },
]

onMounted(load)
</script>
