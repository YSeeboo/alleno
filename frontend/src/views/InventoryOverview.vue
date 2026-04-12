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

    <n-modal v-model:show="showStockModal" preset="card" :title="stockAction === 'add' ? '快速入库' : '快速出库'" style="width: 380px;">
      <form @submit.prevent="doStock">
      <n-form label-placement="left" label-width="80">
        <n-form-item label="对象">
          <div>{{ stockingRow ? `${kindLabel[stockingRow.item_type]} / ${stockingRow.item_id} ${stockingRow.name}` : '-' }}</div>
        </n-form-item>
        <n-form-item label="数量">
          <n-input-number
            v-model:value="stockQty"
            :min="1"
            :step="1"
            :precision="0"
            style="width: 100%;"
          />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="stockNote" placeholder="选填" />
        </n-form-item>
      </n-form>
      </form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showStockModal = false">取消</n-button>
          <n-button :type="stockAction === 'add' ? 'primary' : 'warning'" :loading="stocking" @click="doStock">
            {{ stockAction === 'add' ? '入库' : '出库' }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, h, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NSelect, NInput, NSwitch, NButton,
  NSpin, NDataTable, NEmpty, NModal, NForm, NFormItem, NInputNumber, NSpace,
} from 'naive-ui'
import { addStock, deductStock, getInventoryOverview } from '@/api/inventory'
import { renderNamedImage } from '@/utils/ui'

const router = useRouter()
const message = useMessage()

const loading = ref(false)
const rows = ref([])
const itemType = ref(null)
const searchName = ref('')
const inStockOnly = ref(false)
const showStockModal = ref(false)
const stocking = ref(false)
const stockingRow = ref(null)
const stockAction = ref('add')
const stockQty = ref(1)
const stockNote = ref('')

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

const openStock = (row, action = 'add') => {
  stockingRow.value = row
  stockAction.value = action
  stockQty.value = 1
  stockNote.value = ''
  showStockModal.value = true
}

const doStock = async () => {
  if (!stockingRow.value) return
  if (!Number.isInteger(stockQty.value) || stockQty.value <= 0) {
    message.warning(`${stockAction.value === 'add' ? '入库' : '出库'}数量必须为大于 0 的整数`)
    return
  }
  if (stockAction.value === 'deduct' && stockQty.value > Number(stockingRow.value.current || 0)) {
    message.warning('出库数量不能大于当前库存')
    return
  }
  stocking.value = true
  try {
    const request = stockAction.value === 'add' ? addStock : deductStock
    await request(stockingRow.value.item_type, stockingRow.value.item_id, {
      qty: stockQty.value,
      reason: stockAction.value === 'add' ? '手动入库' : '手动出库',
      note: stockNote.value,
    })
    message.success(stockAction.value === 'add' ? '入库成功' : '出库成功')
    showStockModal.value = false
    await load()
  } finally {
    stocking.value = false
  }
}

const columns = [
  { title: '品类', key: 'item_type', width: 90, render: (row) => kindLabel.value[row.item_type] || row.item_type },
  { title: '编号', key: 'item_id', width: 130 },
  {
    title: '名称',
    key: 'name',
    minWidth: 220,
    render: (row) => renderNamedImage(row.name, row.image, row.name, 40, row.is_composite ? '组合' : null),
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
    width: 210,
    render: (row) => h(NSpace, { size: 8 }, {
      default: () => [
        h(NButton, {
          size: 'small',
          onClick: () => openStock(row, 'add'),
        }, { default: () => '入库' }),
        h(NButton, {
          size: 'small',
          type: 'warning',
          disabled: Number(row.current || 0) <= 0,
          onClick: () => openStock(row, 'deduct'),
        }, { default: () => '出库' }),
        h('button', {
          class: 'icon-btn',
          title: '详情',
          onClick: () => router.push(row.item_type === 'part' ? `/parts/${row.item_id}` : `/jewelries/${row.item_id}`),
        }, '→'),
      ],
    }),
  },
]

onMounted(load)
</script>
