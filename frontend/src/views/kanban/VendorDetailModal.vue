<template>
  <n-modal v-model:show="visible" :mask-closable="true">
    <n-card
      :title="vendor?.vendor_name || '厂家详情'"
      style="width: 720px; max-width: 95vw;"
      :bordered="false"
      role="dialog"
    >
      <template #header-extra>
        <n-button text @click="visible = false">
          <template #icon><n-icon :component="CloseOutline" /></template>
        </n-button>
      </template>

      <n-spin :show="loading">
        <!-- 配件/饰品汇总表 -->
        <div class="section-label">发出明细</div>
        <n-data-table
          :columns="itemColumns"
          :data="detail.items"
          :bordered="false"
          size="small"
          style="margin-bottom: 24px;"
        />

        <!-- 关联订单列表 -->
        <div class="section-label">关联订单</div>
        <n-data-table
          :columns="orderColumns"
          :data="detail.orders"
          :bordered="false"
          size="small"
        />
      </n-spin>
    </n-card>
  </n-modal>
</template>

<script setup>
import { ref, reactive, computed, watch, h } from 'vue'
import { useRouter } from 'vue-router'
import { NModal, NCard, NButton, NIcon, NSpin, NDataTable, NTag, NDropdown, useDialog } from 'naive-ui'
import { CloseOutline } from '@vicons/ionicons5'
import { getVendorDetail, changeOrderStatus } from '@/api/kanban'

const props = defineProps({
  show: Boolean,
  vendor: Object, // { vendor_name, order_type }
})
const emit = defineEmits(['update:show', 'refresh'])

const visible = computed({
  get: () => props.show,
  set: (val) => emit('update:show', val),
})

const router = useRouter()
const dialog = useDialog()
const loading = ref(false)
const detail = reactive({ items: [], orders: [] })

const statusTypeMap = { pending: 'default', processing: 'info', completed: 'success' }
const statusLabelMap = { pending: '待发出', processing: '进行中', completed: '已完成' }

const statusOptions = (currentStatus) => {
  if (currentStatus === 'pending') return [{ label: '进行中', key: 'processing' }]
  if (currentStatus === 'processing') return [
    { label: '待发出', key: 'pending' },
    { label: '已完成', key: 'completed' },
  ]
  if (currentStatus === 'completed') return [{ label: '进行中', key: 'processing' }]
  return []
}

const handleOrderStatusChange = (row, newStatus) => {
  const currentLabel = statusLabelMap[row.status] || row.status
  const newLabel = statusLabelMap[newStatus] || newStatus
  dialog.warning({
    title: '确认状态变更',
    content: `请确认将「${props.vendor.vendor_name}」的订单「${row.order_id}」状态从「${currentLabel}」转为「${newLabel}」`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await changeOrderStatus({
          order_id: row.order_id,
          order_type: row.order_type,
          new_status: newStatus,
        })
        await fetchDetail()
        emit('refresh')
      } catch (_) {
        // errors shown by axios interceptor
      }
    },
  })
}

const itemColumns = computed(() => {
  const cols = [
    { title: '编号', key: 'item_id', width: 120 },
    { title: '类型', key: 'item_type', width: 80, render: (r) => r.item_type === 'part' ? '配件' : '饰品' },
  ]
  if (props.vendor?.order_type === 'plating') {
    cols.push({ title: '电镀工艺', key: 'plating_method', width: 100 })
  }
  cols.push(
    { title: '已发出', key: 'dispatched_qty', width: 80 },
    { title: '已收回', key: 'received_qty', width: 80 },
    {
      title: '剩余',
      key: 'remaining',
      width: 80,
      render: (r) => {
        const rem = (r.dispatched_qty || 0) - (r.received_qty || 0)
        return h('span', { style: { color: rem > 0 ? '#D62828' : 'inherit', fontWeight: rem > 0 ? 600 : 400 } }, rem)
      },
    },
  )
  return cols
})

const orderColumns = [
  {
    title: '订单号',
    key: 'order_id',
    width: 140,
    render: (r) =>
      h(
        'span',
        {
          style: { color: '#C4952A', cursor: 'pointer', fontWeight: 500 },
          onClick: () => {
            visible.value = false
            router.push(`/${r.order_type}/${r.order_id}`)
          },
        },
        r.order_id,
      ),
  },
  {
    title: '类型',
    key: 'order_type',
    width: 80,
    render: (r) => r.order_type === 'plating' ? '电镀' : '手工',
  },
  {
    title: '状态',
    key: 'status',
    width: 110,
    render: (r) => {
      const opts = statusOptions(r.status)
      if (opts.length === 0) {
        return h(NTag, { type: statusTypeMap[r.status] || 'default', size: 'small' }, () => statusLabelMap[r.status] || r.status)
      }
      return h(
        NDropdown,
        {
          options: opts,
          trigger: 'click',
          onSelect: (key) => handleOrderStatusChange(r, key),
        },
        () => h(
          NTag,
          { type: statusTypeMap[r.status] || 'default', size: 'small', style: 'cursor: pointer;' },
          () => (statusLabelMap[r.status] || r.status) + ' ▾',
        ),
      )
    },
  },
  {
    title: '创建时间',
    key: 'created_at',
    render: (r) => new Date(r.created_at).toLocaleString('zh-CN'),
  },
]

let _detailVersion = 0

const fetchDetail = async () => {
  if (!props.vendor) return
  _detailVersion++
  const myVersion = _detailVersion
  loading.value = true
  detail.items = []
  detail.orders = []
  try {
    const { data } = await getVendorDetail(props.vendor.vendor_name, props.vendor.order_type)
    if (myVersion !== _detailVersion) return
    detail.items = data.items || []
    detail.orders = data.orders || []
  } finally {
    if (myVersion === _detailVersion) loading.value = false
  }
}

watch(
  () => [props.show, props.vendor],
  ([show]) => {
    if (show) fetchDetail()
  },
)
</script>

<style scoped>
.section-label {
  font-size: 12px;
  font-weight: 600;
  color: #8A8880;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  margin-bottom: 8px;
}
</style>
