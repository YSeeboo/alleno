<template>
  <div>
    <div class="page-header">
      <h2 class="page-title">库存流水</h2>
      <div class="page-divider"></div>
    </div>
    <n-space style="margin-bottom: 16px;">
      <n-select
        v-model:value="filters.item_type"
        :options="[{ label: '全部', value: null }, { label: '配件', value: 'part' }, { label: '饰品', value: 'jewelry' }]"
        placeholder="品类"
        :style="{ width: isMobile ? '100%' : '100px' }"
        @update:value="resetAndLoad"
      />
      <n-input v-model:value="filters.item_id" placeholder="编号" :style="{ width: isMobile ? '100%' : '160px' }" clearable @clear="resetAndLoad" @keyup.enter="resetAndLoad" />
      <n-input v-model:value="filters.reason" placeholder="原因" :style="{ width: isMobile ? '100%' : '140px' }" clearable @clear="resetAndLoad" @keyup.enter="resetAndLoad" />
      <n-button type="primary" :loading="loading" @click="resetAndLoad">查询</n-button>
    </n-space>

    <n-spin :show="loading">
      <n-data-table :columns="columns" :data="logs" :bordered="false" :pagination="pagination" remote @update:page="onPageChange" />
    </n-spin>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, h } from 'vue'
import { useIsMobile } from '@/composables/useIsMobile'
import { NSpace, NButton, NSelect, NInput, NDataTable, NSpin } from 'naive-ui'
import { listStockLogs } from '@/api/inventory'

const { isMobile } = useIsMobile()
const PAGE_SIZE = 50

const filters = reactive({
  item_type: null,
  item_id: '',
  reason: '',
})

const logs = ref([])
const loading = ref(false)
const total = ref(0)
const currentPage = ref(1)

const pagination = reactive({
  page: 1,
  pageSize: PAGE_SIZE,
  pageCount: 1,
  itemCount: 0,
})

const load = async () => {
  loading.value = true
  try {
    const params = {
      limit: PAGE_SIZE,
      offset: (currentPage.value - 1) * PAGE_SIZE,
    }
    if (filters.item_type) params.item_type = filters.item_type
    if (filters.item_id) params.item_id = filters.item_id
    if (filters.reason) params.reason = filters.reason
    const res = await listStockLogs(params)
    logs.value = res.data.items
    total.value = res.data.total
    pagination.itemCount = res.data.total
    pagination.pageCount = Math.ceil(res.data.total / PAGE_SIZE) || 1
    pagination.page = currentPage.value
  } finally {
    loading.value = false
  }
}

const resetAndLoad = () => {
  currentPage.value = 1
  load()
}

const onPageChange = (page) => {
  currentPage.value = page
  load()
}

onMounted(load)

const columns = [
  { title: '时间', key: 'created_at', width: 170, render: (r) => new Date(r.created_at).toLocaleString('zh-CN') },
  { title: '品类', key: 'item_type', width: 60, render: (r) => r.item_type === 'part' ? '配件' : '饰品' },
  { title: '编号', key: 'item_id', width: 120 },
  {
    title: '变动数量',
    key: 'change_qty',
    width: 100,
    render: (r) =>
      h('span', { style: { color: r.change_qty > 0 ? '#18a058' : '#d03050', fontWeight: 600 } },
        (r.change_qty > 0 ? '+' : '') + r.change_qty
      ),
  },
  { title: '原因', key: 'reason' },
  { title: '备注', key: 'note', render: (r) => r.note || '-' },
]
</script>
