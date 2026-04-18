<template>
  <div>
    <div class="page-header">
      <div class="page-breadcrumb">生产 / 电镀回收</div>
      <h2 class="page-title">电镀回收单</h2>
      <div class="page-divider"></div>
    </div>
    <div class="filter-bar">
      <n-select v-model:value="filterVendor" :options="vendorOptions" clearable placeholder="筛选商家"
        :style="{ width: isMobile ? '100%' : '160px' }" @update:value="load" />
      <div class="filter-bar-end">
        <n-button type="primary" @click="router.push('/plating-receipts/create')">新建回收单</n-button>
      </div>
    </div>
    <n-spin :show="loading">
      <n-data-table v-if="rows.length > 0" :columns="columns" :data="rows" :bordered="false" :row-props="rowProps" />
      <n-empty v-else-if="!loading && !loadError" description="暂无回收单" style="margin-top: 24px;" />
      <n-empty v-else-if="!loading && loadError" description="加载失败，请稍后重试" style="margin-top: 24px;" />
    </n-spin>
  </div>
</template>

<script setup>
import { ref, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { useDialog, useMessage, NButton, NSelect, NDataTable, NSpin, NEmpty } from 'naive-ui'
import { listPlatingReceipts, deletePlatingReceipt, getPlatingReceiptVendors } from '@/api/platingReceipts'
import { fmtMoney } from '@/utils/ui'
import { useIsMobile } from '@/composables/useIsMobile'

const router = useRouter()
const dialog = useDialog()
const message = useMessage()
const { isMobile } = useIsMobile()
const loading = ref(true)
const deletingId = ref(null)
const rows = ref([])
const filterVendor = ref(null)
const vendorOptions = ref([])
const loadError = ref(false)

const statusLabel = { '已付款': '已付款', '未付款': '未付款' }
const statusBadge = { '已付款': 'badge-green', '未付款': 'badge-red' }

const load = async () => {
  loading.value = true
  loadError.value = false
  try {
    const params = filterVendor.value ? { vendor_name: filterVendor.value } : {}
    const { data } = await listPlatingReceipts(params)
    rows.value = data
  } catch (_) {
    rows.value = []
    loadError.value = true
  } finally {
    loading.value = false
  }
}

const loadVendors = async () => {
  try {
    const { data } = await getPlatingReceiptVendors()
    vendorOptions.value = data.map((v) => ({ label: v, value: v }))
  } catch (_) {
    // error shown by axios interceptor
  }
}

const doDelete = (row) => {
  if (!row?.id || deletingId.value) return
  dialog.warning({
    title: '确认删除回收单',
    content: `确认删除回收单「${row.id}」吗？删除后不可恢复。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      deletingId.value = row.id
      try {
        await deletePlatingReceipt(row.id)
        rows.value = rows.value.filter((item) => item.id !== row.id)
        message.success('回收单已删除')
        await load()
      } finally {
        deletingId.value = null
      }
    },
  })
}

const rowProps = (row) => ({ style: 'cursor: pointer;', onClick: () => router.push(`/plating-receipts/${row.id}`) })

const formatAmount = (val) => val == null ? '-' : `¥ ${fmtMoney(val)}`

const columns = [
  { title: '回收单号', key: 'id' },
  { title: '商家', key: 'vendor_name' },
  {
    title: '总金额',
    key: 'total_amount',
    render: (r) => formatAmount(r.total_amount),
  },
  {
    title: '状态',
    key: 'status',
    render: (r) => h('span', { class: `badge ${statusBadge[r.status] || 'badge-gray'}` }, `• ${statusLabel[r.status] || r.status}`),
  },
  { title: '创建时间', key: 'created_at', render: (r) => new Date(r.created_at).toLocaleString('zh-CN') },
  {
    title: '',
    key: 'actions',
    width: 96,
    render: (row) => h(
      NButton,
      {
        size: 'small',
        type: 'error',
        disabled: row.status === '已付款',
        loading: deletingId.value === row.id,
        onClick: (event) => {
          event.stopPropagation()
          doDelete(row)
        },
      },
      { default: () => '删除' },
    ),
  },
]

onMounted(() => {
  loadVendors()
  load()
})
</script>
