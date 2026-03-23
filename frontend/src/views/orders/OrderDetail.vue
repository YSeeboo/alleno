<template>
  <div>
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">订单详情</n-h2>
    </n-space>

    <n-spin :show="loading">
      <n-grid :cols="2" :x-gap="16" style="margin-bottom: 16px;">
        <!-- Basic info -->
        <n-gi>
          <n-card title="基本信息">
            <n-descriptions :column="2" bordered>
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
        </n-gi>

        <!-- Order items -->
        <n-gi>
          <n-card title="饰品清单">
            <n-data-table v-if="orderItems.length > 0" :columns="itemColumns" :data="orderItems" :bordered="false" size="small" />
            <n-empty v-else description="暂无饰品明细" style="margin-top: 16px;" />
          </n-card>
        </n-gi>
      </n-grid>

      <!-- Parts summary -->
      <n-card title="配件汇总">
        <n-data-table v-if="partsSummaryRows.length > 0" :columns="partsColumns" :data="partsSummaryRows" :bordered="false" size="small" />
        <n-empty v-else description="暂无配件汇总" style="margin-top: 16px;" />
      </n-card>
    </n-spin>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NTag, NGrid, NGi, NEmpty,
} from 'naive-ui'
import { getOrder, getOrderItems, getPartsSummary, updateOrderStatus } from '@/api/orders'
import { listParts } from '@/api/parts'
import { listJewelries } from '@/api/jewelries'
import { renderNamedImage, fmtMoney } from '@/utils/ui'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const loading = ref(true)
const updating = ref(false)
const order = ref(null)
const orderItems = ref([])
const partsSummaryRows = ref([])

const statusColor = { '待生产': 'default', '生产中': 'info', '已完成': 'success' }
const statusFlow = { '待生产': '生产中', '生产中': '已完成' }
const statusFlowLabel = { '待生产': '开始生产', '生产中': '标记完成' }

const nextStatus = computed(() => order.value ? statusFlow[order.value.status] : null)
const nextStatusLabel = computed(() => order.value ? statusFlowLabel[order.value.status] : null)

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

    const jewelryMap = {}
    jRes.data.forEach((j) => { jewelryMap[j.id] = j })
    orderItems.value = iRes.data.map((i) => ({
      ...i,
      jewelry_name: jewelryMap[i.jewelry_id]?.name || i.jewelry_id,
      jewelry_image: jewelryMap[i.jewelry_id]?.image || '',
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
  } finally {
    loading.value = false
  }
})
</script>
