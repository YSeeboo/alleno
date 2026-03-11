<template>
  <div>
    <n-space justify="space-between" align="center" style="margin-bottom: 16px;">
      <n-select v-model:value="filterStatus" :options="statusOptions" clearable placeholder="筛选状态"
        style="width: 140px;" @update:value="load" />
      <n-button type="primary" @click="router.push('/plating/create')">新建电镀单</n-button>
    </n-space>
    <n-spin :show="loading">
      <n-data-table :columns="columns" :data="rows" :bordered="false" :row-props="rowProps" />
      <n-empty v-if="!loading && rows.length === 0" description="暂无电镀单" style="margin-top: 24px;" />
    </n-spin>
  </div>
</template>

<script setup>
import { ref, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { NSpace, NButton, NSelect, NDataTable, NSpin, NTag, NEmpty } from 'naive-ui'
import { listPlating } from '@/api/plating'

const router = useRouter()
const loading = ref(true)
const rows = ref([])
const filterStatus = ref(null)
const statusOptions = [
  { label: '待发出', value: 'pending' },
  { label: '进行中', value: 'processing' },
  { label: '已完成', value: 'completed' },
]
const statusType = { pending: 'default', processing: 'info', completed: 'success' }
const statusLabel = { pending: '待发出', processing: '进行中', completed: '已完成' }

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

const rowProps = (row) => ({ style: 'cursor: pointer;', onClick: () => router.push(`/plating/${row.id}`) })

const columns = [
  { title: '电镀单号', key: 'id' },
  { title: '电镀厂', key: 'supplier_name' },
  {
    title: '状态',
    key: 'status',
    render: (r) => h(NTag, { type: statusType[r.status] || 'default' }, () => statusLabel[r.status] || r.status),
  },
  { title: '创建时间', key: 'created_at', render: (r) => new Date(r.created_at).toLocaleString('zh-CN') },
]

onMounted(load)
</script>
