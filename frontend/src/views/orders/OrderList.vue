<template>
  <div>
    <n-space justify="space-between" align="center" style="margin-bottom: 16px;">
      <n-select
        v-model:value="filterStatus"
        :options="statusOptions"
        clearable
        placeholder="筛选状态"
        style="width: 140px;"
        @update:value="load"
      />
      <n-button type="primary" @click="router.push('/orders/create')">新建订单</n-button>
    </n-space>
    <n-spin :show="loading">
      <n-data-table :columns="columns" :data="orders" :bordered="false" :row-props="rowProps" />
      <n-empty v-if="!loading && orders.length === 0" description="暂无订单" style="margin-top: 24px;" />
    </n-spin>
  </div>
</template>

<script setup>
import { ref, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { NSpace, NButton, NSelect, NDataTable, NSpin, NTag, NEmpty } from 'naive-ui'
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

const statusColor = { '待生产': 'default', '生产中': 'info', '已完成': 'success' }

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
    render: (r) => h(NTag, { type: statusColor[r.status] || 'default' }, () => r.status),
  },
  { title: '总金额', key: 'total_amount', render: (r) => r.total_amount?.toFixed(2) ?? '-' },
  { title: '创建时间', key: 'created_at', render: (r) => new Date(r.created_at).toLocaleString('zh-CN') },
]

onMounted(load)
</script>
