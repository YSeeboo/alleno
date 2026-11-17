<template>
  <div>
    <div v-if="embedded" class="handcraft-section-title"><h2>手工发出</h2><span>查看手工发出进度与回执</span></div>
    <div v-else class="page-header">
      <div class="page-breadcrumb">生产 / 手工单</div>
      <h2 class="page-title">手工单</h2>
      <div class="page-divider"></div>
    </div>
    <div class="filter-bar">
      <n-select v-model:value="filterArchive" :options="archiveOptions"
        :style="{ width: isMobile ? '100%' : '150px' }" />
      <n-select v-model:value="filterStatus" :options="statusOptions" clearable placeholder="筛选状态"
        :style="{ width: isMobile ? '100%' : '140px' }" />
      <n-select v-model:value="filterSupplier" :options="supplierOptions" clearable placeholder="筛选商家"
        :style="{ width: isMobile ? '100%' : '160px' }" />
      <n-input-group :style="{ width: isMobile ? '100%' : '240px' }">
        <n-input v-model:value="receiptCodeInput" placeholder="回执编号"
          maxlength="5" :input-props="{ style: 'text-transform: uppercase' }"
          @keyup.enter="jumpByReceiptCode" />
        <n-button type="primary" :loading="lookingUp" @click="jumpByReceiptCode">
          扫码跳转
        </n-button>
      </n-input-group>
      <div class="filter-bar-end">
        <n-button type="primary" @click="router.push('/handcraft/create')">新建手工单</n-button>
      </div>
    </div>
    <n-spin :show="loading">
      <n-data-table v-if="rows.length > 0" :columns="columns" :data="rows" :bordered="false" :row-props="rowProps" :scroll-x="800" />
      <n-empty v-else-if="!loading" :description="loadError ? '加载失败，请稍后重试' : '暂无手工单'" style="margin-top: 24px;" />
    </n-spin>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, h } from 'vue'
import { useRouter } from 'vue-router'
import { useDialog, useMessage, NButton, NSelect, NDataTable, NSpin, NEmpty, NInput, NInputGroup } from 'naive-ui'
import { listHandcraft, deleteHandcraft, getHandcraftSuppliers, getHandcraftByReceiptCode } from '@/api/handcraft'
import { useIsMobile } from '@/composables/useIsMobile'
import { useHandcraftPageQuery } from '@/composables/useHandcraftPageQuery'

defineProps({ embedded: Boolean })
const router = useRouter()
const { route, active, field } = useHandcraftPageQuery('dispatch')
const dialog = useDialog()
const message = useMessage()
const { isMobile } = useIsMobile()
const loading = ref(true)
const deletingId = ref(null)
const rows = ref([])
const loadError = ref(false)
const filterStatus = field('status')
const filterArchive = field('archive', 'active')
const archiveOptions = [
  { label: '正常单据', value: 'active' },
  { label: '历史归档', value: 'archived' },
  { label: '全部（含归档）', value: 'all' },
]
const filterSupplier = field('supplier_name')
const supplierOptions = ref([])
const receiptCodeInput = ref('')
const lookingUp = ref(false)
let disposed = false

async function jumpByReceiptCode() {
  if (lookingUp.value) return
  const code = receiptCodeInput.value.trim().toUpperCase()
  if (code.length !== 5) {
    message.warning('请输入 5 位回执编号')
    return
  }
  lookingUp.value = true
  try {
    const { data } = await getHandcraftByReceiptCode(code)
    if (disposed || !active.value) return
    router.push(`/handcraft/${data.id}`)
  } catch (err) {
    if (disposed || !active.value) return
    if (err?.response?.status === 404) {
      message.error(`无此回执编号：${code}`)
    } else {
      message.error('查询失败')
    }
  } finally {
    lookingUp.value = false
  }
}
const statusOptions = [
  { label: '待发出', value: 'pending' },
  { label: '进行中', value: 'processing' },
  { label: '已完成', value: 'completed' },
]
const statusLabel = { pending: '待发出', processing: '进行中', completed: '已完成' }
const statusBadge = { pending: 'badge-amber', processing: 'badge-indigo', completed: 'badge-green' }

let loadVersion = 0
const load = async () => {
  if (disposed || !active.value) return
  const version = ++loadVersion
  loading.value = true
  loadError.value = false
  try {
    const params = { archive: filterArchive.value }
    if (filterStatus.value) params.status = filterStatus.value
    if (filterSupplier.value) params.supplier_name = filterSupplier.value
    const { data } = await listHandcraft(params)
    if (disposed || version !== loadVersion || !active.value) return
    rows.value = data
  } catch (_) {
    if (disposed || version !== loadVersion || !active.value) return
    rows.value = []
    loadError.value = true
  } finally {
    if (!disposed && version === loadVersion && active.value) loading.value = false
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
  {
    title: '回执编号',
    key: 'receipt_code',
    width: 110,
    render: (r) => r.receipt_code
      ? h('span', { class: 'receipt-code-cell' }, r.receipt_code)
      : h('span', { style: 'color: rgba(0,0,0,.3)' }, '—'),
  },
  { title: '手工商家', key: 'supplier_name' },
  {
    title: '状态',
    key: 'status',
    render: (r) => h('span', { class: `badge ${r.archived_at ? 'badge-gray' : statusBadge[r.status] || 'badge-gray'}` }, `${r.archived_at ? '历史归档 · ' : '• '}${statusLabel[r.status] || r.status}`),
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
        disabled: !!row.archived_at,
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
    if (disposed) return
    supplierOptions.value = data.map((v) => ({ label: v, value: v }))
  }).catch(() => {})
  await load()
})
watch(() => route.fullPath, () => { if (active.value) void load() })
onBeforeUnmount(() => { disposed = true; loadVersion++ })
</script>

<style scoped>
.handcraft-section-title { display: flex; align-items: center; flex-wrap: wrap; gap: 9px; margin-bottom: 14px; }
.handcraft-section-title h2 { margin: 0; font-size: 15px; font-weight: 650; }
.handcraft-section-title span { color: #9AA2A9; font-size: 11px; }
.receipt-code-cell {
  font-family: "SF Mono", Menlo, monospace;
  font-weight: 500;
  letter-spacing: 0.08em;
  font-size: 13px;
  padding: 1px 6px;
  background: #f5f5f8;
  border-radius: 3px;
}
</style>
