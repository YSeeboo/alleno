<template>
  <div>
    <div v-if="embedded" class="plating-section-title"><h2>电镀发出</h2><span>管理发出单据与加工状态</span></div>
    <div v-else class="page-header">
      <div class="page-breadcrumb">生产 / 电镀单</div>
      <h2 class="page-title">电镀单</h2>
      <div class="page-divider"></div>
    </div>
    <div class="filter-bar">
      <n-select v-model:value="filterArchive" :options="archiveOptions"
        :style="{ width: isMobile ? '100%' : '150px' }" />
      <n-select v-model:value="filterStatus" :options="statusOptions" clearable placeholder="筛选状态"
        :style="{ width: isMobile ? '100%' : '140px' }" />
      <n-select v-model:value="filterSupplier" :options="supplierOptions" clearable placeholder="筛选厂家"
        :style="{ width: isMobile ? '100%' : '160px' }" />
      <div class="filter-bar-end">
        <n-button type="primary" @click="router.push('/plating/create')">新建电镀单</n-button>
      </div>
    </div>
    <n-spin :show="loading">
      <n-data-table v-if="rows.length > 0" :columns="columns" :data="rows" :bordered="false" :row-props="rowProps" :scroll-x="720" />
      <n-empty v-else-if="!loading" :description="loadError ? '加载失败，请稍后重试' : '暂无电镀单'" style="margin-top: 24px;" />
    </n-spin>

  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, h } from 'vue'
import { useRouter } from 'vue-router'
import { useDialog, useMessage, NButton, NSelect, NDataTable, NSpin, NEmpty } from 'naive-ui'
import { listPlating, deletePlating, getPlatingSuppliers } from '@/api/plating'
import { useIsMobile } from '@/composables/useIsMobile'
import { usePlatingPageQuery } from '@/composables/usePlatingPageQuery'

defineProps({ embedded: { type: Boolean, default: false } })

const router = useRouter()
const dialog = useDialog()
const message = useMessage()
const { isMobile } = useIsMobile()
const loading = ref(true)
const deletingId = ref(null)
const rows = ref([])
const loadError = ref(false)
const { route, active, field } = usePlatingPageQuery('dispatch')
const filterStatus = field('status')
const filterArchive = field('archive', 'active')
const archiveOptions = [
  { label: '正常单据', value: 'active' },
  { label: '历史归档', value: 'archived' },
  { label: '全部（含归档）', value: 'all' },
]
const filterSupplier = field('supplier')
const supplierOptions = ref([])
const statusOptions = [
  { label: '待发出', value: 'pending' },
  { label: '进行中', value: 'processing' },
  { label: '已完成', value: 'completed' },
]
const statusLabel = { pending: '待发出', processing: '进行中', completed: '已完成' }
const statusBadge = { pending: 'badge-amber', processing: 'badge-indigo', completed: 'badge-green' }

let loadVersion = 0
const load = async () => {
  if (!active.value) return
  const version = ++loadVersion
  loading.value = true
  loadError.value = false
  try {
    const params = { archive: filterArchive.value }
    if (filterStatus.value) params.status = filterStatus.value
    if (filterSupplier.value) params.supplier_name = filterSupplier.value
    const { data } = await listPlating(params)
    if (version === loadVersion) rows.value = data
  } catch (_) {
    if (version === loadVersion) {
      rows.value = []
      loadError.value = true
    }
  } finally {
    if (version === loadVersion) loading.value = false
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
  getPlatingSuppliers().then(({ data }) => {
    supplierOptions.value = data.map((v) => ({ label: v, value: v }))
  }).catch(() => {})
  await load()
})

watch(() => route.fullPath, () => { if (active.value) void load() })
onBeforeUnmount(() => { loadVersion++ })
</script>

<style scoped>
.plating-section-title { display: flex; align-items: center; flex-wrap: wrap; gap: 9px; margin-bottom: 14px; }
.plating-section-title h2 { margin: 0; font-size: 15px; font-weight: 650; }
.plating-section-title span { color: #9AA2A9; font-size: 11px; }
</style>
