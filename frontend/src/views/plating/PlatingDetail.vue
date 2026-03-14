<template>
  <div>
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">电镀单详情</n-h2>
    </n-space>

    <n-spin :show="loading">
      <n-card v-if="order" title="基本信息" style="margin-bottom: 16px;">
        <n-descriptions :column="3" bordered>
          <n-descriptions-item label="电镀单号">{{ order.id }}</n-descriptions-item>
          <n-descriptions-item label="电镀厂">{{ order.supplier_name }}</n-descriptions-item>
          <n-descriptions-item label="状态">
            <n-tag :type="statusType[order.status]">{{ statusLabel[order.status] }}</n-tag>
          </n-descriptions-item>
          <n-descriptions-item label="创建时间">{{ fmt(order.created_at) }}</n-descriptions-item>
          <n-descriptions-item label="完成时间">{{ order.completed_at ? fmt(order.completed_at) : '-' }}</n-descriptions-item>
          <n-descriptions-item label="备注">{{ order.note || '-' }}</n-descriptions-item>
        </n-descriptions>
        <n-space style="margin-top: 12px;">
          <n-button v-if="order.status === 'pending'" type="primary" :loading="sending" @click="doSend">
            确认发出
          </n-button>
        </n-space>
      </n-card>

      <n-card title="电镀明细">
        <n-data-table v-if="items.length > 0" :columns="itemColumns" :data="items" :bordered="false" />
        <n-empty v-else description="暂无明细" style="margin-top: 16px;" />
      </n-card>
    </n-spin>
  </div>
</template>

<script setup>
import { ref, onMounted, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NTag, NEmpty,
} from 'naive-ui'
import { getPlating, getPlatingItems, sendPlating } from '@/api/plating'
import { listParts } from '@/api/parts'
import { renderNamedImage } from '@/utils/ui'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const loading = ref(true)
const sending = ref(false)
const order = ref(null)
const items = ref([])
const partMap = ref({})

const statusType = { pending: 'default', processing: 'info', completed: 'success' }
const statusLabel = { pending: '待发出', processing: '进行中', completed: '已完成' }
const fmt = (dt) => new Date(dt).toLocaleString('zh-CN')

const loadData = async () => {
  const id = route.params.id
  const [oRes, iRes] = await Promise.all([getPlating(id), getPlatingItems(id)])
  order.value = oRes.data
  items.value = iRes.data.map((i) => ({
    ...i,
    part_name: partMap.value[i.part_id]?.name || i.part_id,
    part_image: partMap.value[i.part_id]?.image || '',
  }))
}

const doSend = async () => {
  sending.value = true
  try {
    await sendPlating(route.params.id)
    message.success('已确认发出')
    await loadData()
  } finally {
    sending.value = false
  }
}

const itemColumns = [
  { title: '配件编号', key: 'part_id', width: 110 },
  {
    title: '配件',
    key: 'part_name',
    minWidth: 180,
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name),
  },
  { title: '发出数量', key: 'qty' },
  { title: '电镀方式', key: 'plating_method', render: (r) => r.plating_method || '-' },
  {
    title: '状态',
    key: 'item_status',
    render: (r) => h('span', r.status),
  },
]

onMounted(async () => {
  try {
    const { data: parts } = await listParts()
    parts.forEach((p) => { partMap.value[p.id] = p })
    await loadData()
  } finally {
    loading.value = false
  }
})
</script>
