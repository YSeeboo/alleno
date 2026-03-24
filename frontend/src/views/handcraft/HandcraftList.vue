<template>
  <div>
    <div class="page-header">
      <div class="page-breadcrumb">生产 / 手工单</div>
      <h2 class="page-title">手工单</h2>
      <div class="page-divider"></div>
    </div>
    <div class="filter-bar">
      <n-select v-model:value="filterStatus" :options="statusOptions" clearable placeholder="筛选状态"
        style="width: 140px;" @update:value="load" />
      <n-select v-model:value="filterSupplier" :options="supplierOptions" clearable placeholder="筛选商家"
        style="width: 160px;" @update:value="load" />
      <div class="filter-bar-end">
        <n-button type="primary" @click="router.push('/handcraft/create')">新建手工单</n-button>
      </div>
    </div>
    <n-spin :show="loading">
      <n-data-table v-if="rows.length > 0" :columns="columns" :data="rows" :bordered="false" :row-props="rowProps" />
      <n-empty v-else-if="!loading" description="暂无手工单" style="margin-top: 24px;" />
    </n-spin>
  </div>
</template>

<script setup>
import { ref, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { useDialog, useMessage, NButton, NSelect, NDataTable, NSpin, NEmpty } from 'naive-ui'
import { listHandcraft, deleteHandcraft, getHandcraftSuppliers } from '@/api/handcraft'

const router = useRouter()
const dialog = useDialog()
const message = useMessage()
const loading = ref(true)
const deletingId = ref(null)
const rows = ref([])
const filterStatus = ref(null)
const filterSupplier = ref(null)
const supplierOptions = ref([])
const statusOptions = [
  { label: '待发出', value: 'pending' },
  { label: '进行中', value: 'processing' },
  { label: '已完成', value: 'completed' },
]
const statusLabel = { pending: '待发出', processing: '进行中', completed: '已完成' }
const statusBadge = { pending: 'badge-amber', processing: 'badge-indigo', completed: 'badge-green' }

const load = async () => {
  loading.value = true
  try {
    const params = {}
    if (filterStatus.value) params.status = filterStatus.value
    if (filterSupplier.value) params.supplier_name = filterSupplier.value
    const { data } = await listHandcraft(params)
    rows.value = data
  } finally {
    loading.value = false
  }
}

const doDeleteOrder = (row) => {
  if (!row?.id || deletingId.value) return
  dialog.warning({
    title: '确认删除手工单',
    content: `确认删除手工单「${row.id}」吗？删除后不可恢复。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      deletingId.value = row.id
      try {
        await deleteHandcraft(row.id)
        rows.value = rows.value.filter((item) => item.id !== row.id)
        message.success('手工单已删除')
        await load()
      } finally {
        deletingId.value = null
      }
    },
  })
}

const rowProps = (row) => ({ style: 'cursor: pointer;', onClick: () => router.push(`/handcraft/${row.id}`) })

const columns = [
  { title: '手工单号', key: 'id' },
  { title: '手工商家', key: 'supplier_name' },
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
        loading: deletingId.value === row.id,
        onClick: (event) => {
          event.stopPropagation()
          doDeleteOrder(row)
        },
      },
      { default: () => '删除' },
    ),
  },
]

onMounted(async () => {
  getHandcraftSuppliers().then(({ data }) => {
    supplierOptions.value = data.map((v) => ({ label: v, value: v }))
  }).catch(() => {})
  await load()
})
</script>
