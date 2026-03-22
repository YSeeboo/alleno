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
        <n-button @click="openReceiveModal">回收</n-button>
      </div>
    </div>
    <n-spin :show="loading">
      <n-data-table v-if="rows.length > 0" :columns="columns" :data="rows" :bordered="false" :row-props="rowProps" />
      <n-empty v-else-if="!loading" description="暂无电镀单" style="margin-top: 24px;" />
    </n-spin>

    <!-- Receive Modal -->
    <n-modal v-model:show="receiveModalVisible" preset="card" title="回收" style="width: 900px;">
      <n-input
        v-model:value="receiveKeyword"
        placeholder="搜索配件名称或编号"
        clearable
        style="margin-bottom: 12px;"
        @update:value="debouncedSearch"
      />
      <n-spin :show="receiveLoading">
        <n-data-table
          v-if="receiveItems.length > 0"
          :columns="receiveColumns"
          :data="receiveItems"
          :bordered="false"
          :max-height="400"
        />
        <n-empty v-else-if="!receiveLoading && receiveSearched" description="没有待回收的明细" style="margin-top: 16px;" />
      </n-spin>
    </n-modal>

    <!-- Partial Receive Modal -->
    <n-modal v-model:show="partialReceiveVisible" preset="card" title="部分回收" style="width: 400px;">
      <n-form label-placement="left" label-width="80">
        <n-form-item label="配件">{{ partialReceiveItem?.part_name }}</n-form-item>
        <n-form-item label="未收回">{{ partialReceiveRemaining }}</n-form-item>
        <n-form-item label="回收数量">
          <n-input-number
            v-model:value="partialReceiveQty"
            :min="0.0001"
            :max="partialReceiveRemaining"
            :precision="4"
            style="width: 100%;"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="partialReceiveVisible = false">取消</n-button>
          <n-button type="primary" :loading="receiveSubmitting" @click="doPartialReceive">确定</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { useDialog, useMessage, NButton, NSelect, NDataTable, NSpin, NEmpty, NModal, NInput, NInputNumber, NForm, NFormItem, NSpace, NImage } from 'naive-ui'
import { listPlating, deletePlating, receivePlating, listPendingReceiveItems } from '@/api/plating'
import { renderNamedImage } from '@/utils/ui'

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

// Receive modal state
const receiveModalVisible = ref(false)
const receiveKeyword = ref('')
const receiveLoading = ref(false)
const receiveSearched = ref(false)
const receiveItems = ref([])
const receiveSubmitting = ref(false)

// Partial receive modal state
const partialReceiveVisible = ref(false)
const partialReceiveItem = ref(null)
const partialReceiveQty = ref(0)
const partialReceiveRemaining = ref(0)

let searchTimer = null
let searchVersion = 0

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

// --- Receive modal logic ---

const openReceiveModal = () => {
  receiveModalVisible.value = true
  receiveKeyword.value = ''
  receiveItems.value = []
  receiveSearched.value = false
  searchReceiveItems()
}

const debouncedSearch = () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => searchReceiveItems(), 300)
}

const searchReceiveItems = async () => {
  const version = ++searchVersion
  receiveLoading.value = true
  receiveSearched.value = true
  try {
    const params = receiveKeyword.value ? { part_keyword: receiveKeyword.value } : {}
    const { data } = await listPendingReceiveItems(params)
    if (version !== searchVersion) return
    receiveItems.value = data
  } finally {
    if (version === searchVersion) receiveLoading.value = false
  }
}

const doFullReceiveItem = async (item) => {
  receiveSubmitting.value = true
  try {
    const remaining = item.qty - item.received_qty
    await receivePlating(item.plating_order_id, [{ plating_order_item_id: item.id, qty: remaining }])
    message.success('回收成功')
    await Promise.all([searchReceiveItems(), load()])
  } finally {
    receiveSubmitting.value = false
  }
}

const openPartialReceiveModal = (item) => {
  partialReceiveItem.value = item
  partialReceiveRemaining.value = item.qty - item.received_qty
  partialReceiveQty.value = null
  partialReceiveVisible.value = true
}

const doPartialReceive = async () => {
  if (!partialReceiveItem.value || !partialReceiveQty.value) return
  receiveSubmitting.value = true
  try {
    await receivePlating(partialReceiveItem.value.plating_order_id, [
      { plating_order_item_id: partialReceiveItem.value.id, qty: partialReceiveQty.value },
    ])
    message.success('回收成功')
    partialReceiveVisible.value = false
    await Promise.all([searchReceiveItems(), load()])
  } finally {
    receiveSubmitting.value = false
  }
}

const receiveColumns = [
  {
    title: '电镀单号',
    key: 'plating_order_id',
    width: 110,
    render: (row) => h(
      NButton,
      {
        text: true,
        type: 'primary',
        onClick: () => router.push(`/plating/${row.plating_order_id}`),
      },
      { default: () => row.plating_order_id },
    ),
  },
  { title: '厂家', key: 'supplier_name', width: 100 },
  {
    title: '发出配件',
    key: 'part_name',
    minWidth: 140,
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name),
  },
  {
    title: '收回配件',
    key: 'receive_part_name',
    width: 100,
    render: (row) => row.receive_part_name || '同发出配件',
  },
  { title: '电镀工艺', key: 'plating_method', width: 80 },
  { title: '发出', key: 'qty', width: 60 },
  { title: '已收', key: 'received_qty', width: 60 },
  {
    title: '未收',
    key: 'remaining',
    width: 60,
    render: (row) => row.qty - row.received_qty,
  },
  {
    title: '操作',
    key: 'actions',
    width: 160,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(NButton, {
          size: 'small',
          type: 'primary',
          loading: receiveSubmitting.value,
          onClick: () => doFullReceiveItem(row),
        }, { default: () => '全部回收' }),
        h(NButton, {
          size: 'small',
          onClick: () => openPartialReceiveModal(row),
        }, { default: () => '部分回收' }),
      ],
    }),
  },
]

onMounted(load)
</script>
