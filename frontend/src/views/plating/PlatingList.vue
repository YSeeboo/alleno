<template>
  <div>
    <div class="page-header">
      <div class="page-breadcrumb">生产 / 电镀单</div>
      <h2 class="page-title">电镀单</h2>
      <div class="page-divider"></div>
    </div>
    <div class="filter-bar">
      <n-select v-model:value="filterStatus" :options="statusOptions" clearable placeholder="筛选状态"
        style="width: 140px;" @update:value="load" />
      <div class="filter-bar-end">
        <n-button type="primary" @click="router.push('/plating/create')">新建电镀单</n-button>
      </div>
    </div>
    <n-spin :show="loading">
      <n-data-table v-if="rows.length > 0" :columns="columns" :data="rows" :bordered="false" :row-props="rowProps" />
      <n-empty v-else-if="!loading" description="暂无电镀单" style="margin-top: 24px;" />
    </n-spin>
  </div>
</template>

<script setup>
import { ref, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { useDialog, useMessage, NButton, NSelect, NDataTable, NSpin, NEmpty } from 'naive-ui'
import { listPlating, deletePlating } from '@/api/plating'

const router = useRouter()
const dialog = useDialog()
const message = useMessage()
const loading = ref(true)
const deletingId = ref(null)
const rows = ref([])
const filterStatus = ref(null)
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
    const params = filterStatus.value ? { status: filterStatus.value } : {}
    const { data } = await listPlating(params)
    rows.value = data
  } finally {
    loading.value = false
  }
}

const doDeleteOrder = (row) => {
  if (!row?.id || deletingId.value) return
  dialog.warning({
    title: '确认删除电镀单',
    content: `确认删除电镀单「${row.id}」吗？删除后不可恢复。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      deletingId.value = row.id
      try {
        await deletePlating(row.id)
        rows.value = rows.value.filter((item) => item.id !== row.id)
        message.success('电镀单已删除')
        await load()
      } finally {
        deletingId.value = null
      }
    },
  })
}

const rowProps = (row) => ({ style: 'cursor: pointer;', onClick: () => router.push(`/plating/${row.id}`) })

const columns = [
  { title: '电镀单号', key: 'id' },
  { title: '电镀厂', key: 'supplier_name' },
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

onMounted(load)
</script>
