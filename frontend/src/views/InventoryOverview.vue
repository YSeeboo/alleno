<template>
  <div>
    <div class="page-header">
      <div class="page-breadcrumb">库存 / 库存总表</div>
      <h2 class="page-title">库存总表</h2>
      <div class="page-divider"></div>
    </div>

    <div class="filter-bar">
      <n-select
        v-model:value="itemType"
        :options="itemTypeOptions"
        style="width: 140px;"
        placeholder="全部品类"
        clearable
      />
      <n-input
        v-model:value="searchName"
        placeholder="搜索编号或名称"
        clearable
        style="width: 220px;"
        @keydown.enter="load"
      />
      <n-switch v-model:value="inStockOnly" />
      <span style="line-height: 34px; color: #64748B; font-size: 13px;">仅看有库存</span>
      <div class="filter-bar-end">
        <n-button type="primary" :loading="loading" @click="load">查询</n-button>
      </div>
    </div>

    <n-spin :show="loading">
      <n-data-table v-if="rows.length > 0" :columns="columns" :data="rows" :bordered="false" />
      <n-empty v-else-if="!loading" description="暂无库存数据" style="margin-top: 24px;" />
    </n-spin>
  </div>
</template>

<script setup>
import { computed, h, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  NSelect, NInput, NSwitch, NButton,
  NSpin, NDataTable, NEmpty,
} from 'naive-ui'
import { getInventoryOverview } from '@/api/inventory'
import { renderNamedImage } from '@/utils/ui'

const router = useRouter()

const loading = ref(false)
const rows = ref([])
const itemType = ref(null)
const searchName = ref('')
const inStockOnly = ref(false)

const itemTypeOptions = [
  { label: '配件', value: 'part' },
  { label: '饰品', value: 'jewelry' },
]

const load = async () => {
  loading.value = true
  try {
    const params = {}
    if (itemType.value) params.item_type = itemType.value
    if (searchName.value) params.name = searchName.value
    if (inStockOnly.value) params.in_stock_only = true
    const { data } = await getInventoryOverview(params)
    rows.value = data
  } finally {
    loading.value = false
  }
}

const kindLabel = computed(() => ({
  part: '配件',
  jewelry: '饰品',
}))

const columns = [
  { title: '品类', key: 'item_type', width: 90, render: (row) => kindLabel.value[row.item_type] || row.item_type },
  { title: '编号', key: 'item_id', width: 130 },
  {
    title: '名称',
    key: 'name',
    minWidth: 220,
    render: (row) => renderNamedImage(row.name, row.image, row.name),
  },
  { title: '类目', key: 'category', width: 100, render: (row) => row.category || '-' },
  {
    title: '当前库存',
    key: 'current',
    width: 100,
    render: (row) => row.current <= 0
      ? h('span', { class: 'badge badge-red' }, `• ${row.current}`)
      : h('span', { style: { color: '#10B981', fontWeight: 700 } }, row.current),
  },
  {
    title: '最近更新',
    key: 'updated_at',
    width: 180,
    render: (row) => row.updated_at ? new Date(row.updated_at).toLocaleString('zh-CN') : '-',
  },
  {
    title: '操作',
    key: 'actions',
    width: 80,
    render: (row) =>
      h('button', {
        class: 'icon-btn',
        title: '详情',
        onClick: () => router.push(row.item_type === 'part' ? `/parts/${row.item_id}` : `/jewelries/${row.item_id}`),
      }, '→'),
  },
]

onMounted(load)
</script>
