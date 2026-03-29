<template>
  <div>
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">订单详情</n-h2>
    </n-space>

    <n-spin :show="loading">
      <!-- Basic info — full width -->
      <n-card title="基本信息" style="margin-bottom: 16px;">
        <n-descriptions :column="3" bordered>
          <n-descriptions-item label="订单号">{{ order?.id }}</n-descriptions-item>
          <n-descriptions-item label="客户名">{{ order?.customer_name }}</n-descriptions-item>
          <n-descriptions-item label="状态">
            <n-tag :type="statusColor[order?.status]">{{ order?.status }}</n-tag>
          </n-descriptions-item>
          <n-descriptions-item label="总金额">{{ order?.total_amount != null ? fmtMoney(order.total_amount) : '-' }}</n-descriptions-item>
          <n-descriptions-item label="创建时间" :span="2">
            {{ order?.created_at ? new Date(order.created_at).toLocaleString('zh-CN') : '-' }}
          </n-descriptions-item>
        </n-descriptions>
        <n-space style="margin-top: 12px;">
          <n-button
            v-if="nextStatus"
            type="primary"
            :loading="updating"
            @click="advanceStatus"
          >
            {{ nextStatusLabel }}
          </n-button>
        </n-space>
      </n-card>

      <!-- Order items — full width -->
      <n-card title="饰品清单" style="margin-bottom: 16px;">
        <n-data-table v-if="orderItems.length > 0" :columns="itemColumns" :data="orderItems" :bordered="false" size="small" />
        <n-empty v-else description="暂无饰品明细" style="margin-top: 16px;" />

        <!-- Add item row -->
        <n-divider style="margin: 12px 0;" />
        <n-space align="center">
          <n-select
            v-model:value="newItem.jewelry_id"
            :options="jewelryOptions"
            :render-label="renderOptionWithImage"
            filterable
            placeholder="选择饰品"
            style="width: 220px;"
            @update:value="onNewJewelrySelect"
          />
          <n-input-number v-model:value="newItem.quantity" :min="1" placeholder="数量" style="width: 90px;" />
          <n-input-number
            v-model:value="newItem.unit_price"
            :min="0"
            :precision="7"
            :format="fmtPrice"
            :parse="parseNum"
            placeholder="单价"
            style="width: 120px;"
          />
          <n-input v-model:value="newItem.remarks" placeholder="备注" style="width: 160px;" />
          <n-button type="primary" size="small" :loading="addingItem" @click="doAddItem">添加</n-button>
        </n-space>
      </n-card>

      <!-- TodoList -->
      <n-card title="配件清单" style="margin-bottom: 16px;">
        <template #header-extra>
          <n-button
            type="primary"
            size="small"
            :loading="generatingTodo"
            @click="doGenerateTodo"
          >
            {{ todoItems.length > 0 ? '重新生成' : '生成配件清单' }}
          </n-button>
        </template>
        <n-data-table v-if="todoItems.length > 0" :columns="todoColumns" :data="todoItems" :bordered="false" size="small" />
        <n-empty v-else description="暂无配件清单，请点击「生成配件清单」" style="margin-top: 16px;" />
      </n-card>

      <!-- Parts summary -->
      <n-card title="配件汇总（BOM）">
        <n-data-table v-if="partsSummaryRows.length > 0" :columns="partsColumns" :data="partsSummaryRows" :bordered="false" size="small" />
        <n-empty v-else description="暂无配件汇总" style="margin-top: 16px;" />
      </n-card>
    </n-spin>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NTag, NEmpty, NSelect, NInputNumber, NInput, NDivider, NPopconfirm,
} from 'naive-ui'
import { getOrder, getOrderItems, getPartsSummary, updateOrderStatus, generateTodo, getTodo, deleteLink, addOrderItem, deleteOrderItem } from '@/api/orders'
import { listParts } from '@/api/parts'
import { listJewelries } from '@/api/jewelries'
import { renderNamedImage, renderOptionWithImage, fmtMoney, fmtPrice, parseNum } from '@/utils/ui'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()

const loading = ref(true)
const updating = ref(false)
const generatingTodo = ref(false)
const addingItem = ref(false)
const order = ref(null)
const orderItems = ref([])
const partsSummaryRows = ref([])
const todoItems = ref([])

const jewelryMap = ref({})
const jewelryOptions = ref([])

const newItem = reactive({ jewelry_id: null, quantity: 1, unit_price: 0, remarks: '' })

const statusColor = { '待生产': 'default', '生产中': 'info', '已完成': 'success' }
const statusFlow = { '待生产': '生产中', '生产中': '已完成' }
const statusFlowLabel = { '待生产': '开始生产', '生产中': '标记完成' }

const nextStatus = computed(() => order.value ? statusFlow[order.value.status] : null)
const nextStatusLabel = computed(() => order.value ? statusFlowLabel[order.value.status] : null)

const onNewJewelrySelect = (v) => {
  const j = jewelryMap.value[v]
  if (j) newItem.unit_price = j.wholesale_price ?? 0
}

const reloadOrder = async () => {
  const id = route.params.id
  const [oRes, iRes, sRes] = await Promise.all([
    getOrder(id),
    getOrderItems(id),
    getPartsSummary(id),
  ])
  order.value = oRes.data
  orderItems.value = iRes.data.map((i) => ({
    ...i,
    jewelry_name: jewelryMap.value[i.jewelry_id]?.name || i.jewelry_id,
    jewelry_image: jewelryMap.value[i.jewelry_id]?.image || '',
  }))
  const partMap = {}
  ;(await listParts()).data.forEach((p) => { partMap[p.id] = p })
  partsSummaryRows.value = Object.entries(sRes.data).map(([part_id, total_qty]) => ({
    part_id,
    part_name: partMap[part_id]?.name || part_id,
    part_image: partMap[part_id]?.image || '',
    total_qty,
  }))
}

const doAddItem = async () => {
  if (!newItem.jewelry_id) { message.warning('请选择饰品'); return }
  addingItem.value = true
  try {
    await addOrderItem(order.value.id, {
      jewelry_id: newItem.jewelry_id,
      quantity: newItem.quantity,
      unit_price: newItem.unit_price,
      remarks: newItem.remarks || undefined,
    })
    message.success('饰品已添加')
    newItem.jewelry_id = null
    newItem.quantity = 1
    newItem.unit_price = 0
    newItem.remarks = ''
    await reloadOrder()
  } finally {
    addingItem.value = false
  }
}

const doDeleteItem = (row) => {
  dialog.warning({
    title: '删除饰品',
    content: `确认删除「${row.jewelry_name || row.jewelry_id}」？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      await deleteOrderItem(order.value.id, row.id)
      message.success('已删除')
      await reloadOrder()
    },
  })
}

const advanceStatus = async () => {
  if (!nextStatus.value) return
  updating.value = true
  try {
    const { data } = await updateOrderStatus(order.value.id, nextStatus.value)
    order.value = data
    message.success('状态已更新')
  } finally {
    updating.value = false
  }
}

const doGenerateTodo = async () => {
  if (!order.value) return
  if (todoItems.value.length > 0) {
    dialog.warning({
      title: '重新生成配件清单',
      content: '重新生成会根据当前 BOM 更新清单，已有的订单关联会保留。确认继续？',
      positiveText: '确认',
      negativeText: '取消',
      onPositiveClick: async () => {
        await execGenerateTodo()
      },
    })
  } else {
    await execGenerateTodo()
  }
}

const execGenerateTodo = async () => {
  generatingTodo.value = true
  try {
    const { data } = await generateTodo(order.value.id)
    todoItems.value = data
    message.success('配件清单已生成')
  } finally {
    generatingTodo.value = false
  }
}

const loadTodo = async () => {
  if (!order.value) return
  try {
    const { data } = await getTodo(order.value.id)
    todoItems.value = data
  } catch (_) {
    todoItems.value = []
  }
}

const doDeleteTodoLink = (todoRow, prod) => {
  dialog.warning({
    title: '解除关联',
    content: `确认解除配件「${todoRow.part_name || todoRow.part_id}」与生产单「${prod.order_id}」的关联？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteLink(prod.link_id)
        message.success('已解除关联')
        await loadTodo()
      } catch (_) {}
    },
  })
}

const prodStatusLabel = {
  '未送出': '未送出',
  '制作中': '制作中',
  '已收回': '已收回',
}
const prodStatusBadge = {
  '未送出': 'badge-gray',
  '制作中': 'badge-blue',
  '已收回': 'badge-green',
}

const itemColumns = [
  { title: '饰品编号', key: 'jewelry_id', width: 110 },
  {
    title: '饰品',
    key: 'jewelry_name',
    minWidth: 180,
    render: (row) => renderNamedImage(row.jewelry_name, row.jewelry_image, row.jewelry_name),
  },
  { title: '数量', key: 'quantity' },
  { title: '单价', key: 'unit_price', render: (r) => r.unit_price != null ? fmtMoney(r.unit_price) : '-' },
  { title: '小计', key: 'subtotal', render: (r) => fmtMoney((r.quantity || 0) * (r.unit_price || 0)) },
  { title: '备注', key: 'remarks', render: (r) => r.remarks || '-' },
  {
    title: '操作',
    key: 'actions',
    width: 80,
    render: (row) =>
      h(NPopconfirm, { onPositiveClick: () => doDeleteItem(row) }, {
        trigger: () => h(NButton, { size: 'small', type: 'error' }, () => '删除'),
        default: () => `确认删除「${row.jewelry_name || row.jewelry_id}」？`,
      }),
  },
]

const todoColumns = [
  { title: '配件编号', key: 'part_id', width: 110 },
  {
    title: '配件',
    key: 'part_name',
    minWidth: 160,
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name),
  },
  { title: '需要数量', key: 'required_qty', width: 100 },
  {
    title: '库存数量',
    key: 'stock_qty',
    width: 100,
    render: (r) => r.stock_qty != null ? r.stock_qty : '-',
  },
  {
    title: '缺口',
    key: 'gap',
    width: 80,
    render: (r) => {
      if (r.gap == null) return '-'
      if (r.gap > 0) return h('span', { style: 'color: #d03050; font-weight: 600;' }, r.gap)
      return h('span', { style: 'color: #18a058;' }, '0')
    },
  },
  {
    title: '生产单状态',
    key: 'linked_production',
    minWidth: 200,
    render: (row) => {
      const prods = row.linked_production || []
      if (prods.length === 0) return h('span', { style: 'color: #999;' }, '-')
      return h('div', { style: 'display: flex; flex-wrap: wrap; gap: 4px;' },
        prods.map((p) => h('span', {
          style: 'display: inline-flex; align-items: center; gap: 4px;',
        }, [
          h('span', {
            class: `badge ${prodStatusBadge[p.status] || 'badge-gray'}`,
            style: 'font-size: 12px;',
          }, `${p.type === 'plating' ? 'EP' : 'HC'}:${p.order_id} ${p.status || ''}`),
          h(NButton, {
            size: 'tiny',
            quaternary: true,
            type: 'error',
            onClick: () => doDeleteTodoLink(row, { ...p, link_id: p.link_id }),
          }, { default: () => '×' }),
        ])),
      )
    },
  },
  {
    title: '完成',
    key: 'is_complete',
    width: 70,
    render: (r) => {
      if (r.is_complete) return h('span', { style: 'color: #18a058; font-weight: 600;' }, 'Yes')
      return h('span', { style: 'color: #d03050;' }, 'No')
    },
  },
]

const partsColumns = [
  { title: '配件编号', key: 'part_id' },
  {
    title: '配件',
    key: 'part_name',
    minWidth: 180,
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name),
  },
  { title: '所需总量', key: 'total_qty', render: (r) => r.total_qty },
]

onMounted(async () => {
  const id = route.params.id
  try {
    const [oRes, iRes, sRes, pRes, jRes] = await Promise.all([
      getOrder(id),
      getOrderItems(id),
      getPartsSummary(id),
      listParts(),
      listJewelries(),
    ])
    order.value = oRes.data

    jRes.data.forEach((j) => { jewelryMap.value[j.id] = j })
    jewelryOptions.value = jRes.data
      .filter((j) => j.status === 'active')
      .map((j) => ({
        label: `${j.id} ${j.name}`,
        value: j.id,
        code: j.id,
        name: j.name,
        image: j.image,
      }))

    orderItems.value = iRes.data.map((i) => ({
      ...i,
      jewelry_name: jewelryMap.value[i.jewelry_id]?.name || i.jewelry_id,
      jewelry_image: jewelryMap.value[i.jewelry_id]?.image || '',
    }))

    const partMap = {}
    pRes.data.forEach((p) => { partMap[p.id] = p })

    // parts-summary returns dict {part_id: qty}
    partsSummaryRows.value = Object.entries(sRes.data).map(([part_id, total_qty]) => ({
      part_id,
      part_name: partMap[part_id]?.name || part_id,
      part_image: partMap[part_id]?.image || '',
      total_qty,
    }))

    await loadTodo()
  } finally {
    loading.value = false
  }
})
</script>
