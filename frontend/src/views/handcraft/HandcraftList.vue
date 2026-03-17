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
import { NButton, NSelect, NDataTable, NSpin, NEmpty } from 'naive-ui'
import { listHandcraft } from '@/api/handcraft'

const router = useRouter()
const loading = ref(true)
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
    const { data } = await listHandcraft(params)
    rows.value = data
  } finally {
    loading.value = false
  }
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
]

onMounted(load)
</script>
