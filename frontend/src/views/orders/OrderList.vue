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
        :style="{ width: isMobile ? '100%' : '140px' }"
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
import { NButton, NSelect, NDataTable, NSpin, NEmpty, NTag, NTooltip, useDialog, useMessage } from 'naive-ui'
import { listOrders, batchGetProgress, deleteOrder, getOrderDeletePreview } from '@/api/orders'
import { fmtMoney } from '@/utils/ui'
import { useIsMobile } from '@/composables/useIsMobile'

const router = useRouter()
const { isMobile } = useIsMobile()
const dialog = useDialog()
const message = useMessage()

const confirmDelete = async (row) => {
  let parts = []
  try {
    const { data } = await getOrderDeletePreview(row.id)
    if (data.item_count) parts.push(`${data.item_count} 个明细`)
    if (data.batch_count) parts.push(`${data.batch_count} 个备货批次`)
    if (data.link_count) parts.push(`${data.link_count} 个生产单关联`)
  } catch (_) {
    return // 预览失败由拦截器提示，终止
  }
  const cascade = parts.length ? `，将一并删除：${parts.join('、')}` : ''
  dialog.warning({
    title: '确认删除订单',
    content: `确认删除订单 ${row.id}？此操作不可恢复${cascade}。`,
    positiveText: '确认删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      await deleteOrder(row.id)
      message.success('订单已删除')
      await load()
    },
  })
}

const loading = ref(true)
const orders = ref([])
const filterStatus = ref(null)
const statusOptions = [
  { label: '待生产', value: '待生产' },
  { label: '生产中', value: '生产中' },
  { label: '已完成', value: '已完成' },
]

const progressMap = ref({})

const load = async () => {
  loading.value = true
  try {
    const params = {}
    if (filterStatus.value) params.status = filterStatus.value
    const { data } = await listOrders(params)
    orders.value = data
    // Batch load progress for all orders in one request
    if (data.length) {
      const { data: progressResults } = await batchGetProgress(data.map((o) => o.id))
      const map = {}
      progressResults.forEach((p) => {
        if (p) map[p.order_id] = p
      })
      progressMap.value = map
    } else {
      progressMap.value = {}
    }
  } finally {
    loading.value = false
  }
}

const rowProps = (row) => ({ style: 'cursor: pointer;', onClick: () => router.push(`/orders/${row.id}`) })

const columns = [
  { title: '订单号', key: 'id' },
  {
    title: '客户名',
    key: 'customer_name',
    render: (r) => {
      if (!r.has_barcode) return r.customer_name
      return h('span', null, [
        r.customer_name,
        h(
          NTag,
          {
            size: 'small',
            bordered: false,
            color: { color: '#00A0E9', textColor: '#fff' },
            style: 'margin-left: 8px; font-weight: 600; letter-spacing: 0.5px;',
          },
          { default: () => '有条码' }
        ),
      ])
    },
  },
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
  {
    title: '备货进度',
    key: 'progress',
    width: 100,
    render: (r) => {
      const p = progressMap.value[r.id]
      if (!p || p.total === 0) return h('span', { style: 'color: #999;' }, '-')
      const color = p.completed === p.total ? '#18a058' : '#2080f0'
      return h('span', { style: `font-weight: 600; color: ${color};` }, `${p.completed}/${p.total}`)
    },
  },
  { title: '总金额', key: 'total_amount', render: (r) => r.total_amount != null ? fmtMoney(r.total_amount) : '-' },
  { title: '创建时间', key: 'created_at', render: (r) => new Date(r.created_at).toLocaleString('zh-CN') },
  {
    title: '操作',
    key: 'actions',
    width: 80,
    render: (r) => {
      const isPending = r.status === '待生产'
      const btn = h(
        NButton,
        {
          text: true,
          type: 'error',
          disabled: !isPending,
          onClick: (e) => { e.stopPropagation(); confirmDelete(r) },
        },
        { default: () => '删除' }
      )
      if (isPending) return btn
      return h(
        NTooltip,
        null,
        { trigger: () => btn, default: () => '只能删除待生产状态的订单' }
      )
    },
  },
]

onMounted(load)
</script>
