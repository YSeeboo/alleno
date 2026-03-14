<template>
  <div>
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">手工单详情</n-h2>
    </n-space>

    <n-spin :show="loading">
      <n-card v-if="order" title="基本信息" style="margin-bottom: 16px;">
        <n-descriptions :column="3" bordered>
          <n-descriptions-item label="手工单号">{{ order.id }}</n-descriptions-item>
          <n-descriptions-item label="手工商家">{{ order.supplier_name }}</n-descriptions-item>
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

      <n-grid :cols="2" :x-gap="16">
        <n-gi>
          <n-card title="配件明细">
            <n-data-table v-if="partItems.length > 0" :columns="partColumns" :data="partItems" :bordered="false" size="small" />
            <n-empty v-else description="暂无配件明细" style="margin-top: 16px;" />
          </n-card>
        </n-gi>
        <n-gi>
          <n-card title="成品明细">
            <n-data-table v-if="jewelryItems.length > 0" :columns="jewelryColumns" :data="jewelryItems" :bordered="false" size="small" />
            <n-empty v-else description="暂无成品明细" style="margin-top: 16px;" />
          </n-card>
        </n-gi>
      </n-grid>
    </n-spin>
  </div>
</template>

<script setup>
import { ref, onMounted, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NTag, NGrid, NGi, NEmpty,
} from 'naive-ui'
import { getHandcraft, getHandcraftParts, getHandcraftJewelries, sendHandcraft } from '@/api/handcraft'
import { listParts } from '@/api/parts'
import { listJewelries } from '@/api/jewelries'
import { renderNamedImage } from '@/utils/ui'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const loading = ref(true)
const sending = ref(false)
const order = ref(null)
const partItems = ref([])
const jewelryItems = ref([])
const partMap = ref({})
const jewelryMap = ref({})

const statusType = { pending: 'default', processing: 'info', completed: 'success' }
const statusLabel = { pending: '待发出', processing: '进行中', completed: '已完成' }
const fmt = (dt) => new Date(dt).toLocaleString('zh-CN')

const loadData = async () => {
  const id = route.params.id
  const [oRes, pRes, jRes] = await Promise.all([
    getHandcraft(id), getHandcraftParts(id), getHandcraftJewelries(id),
  ])
  order.value = oRes.data
  partItems.value = pRes.data.map((p) => ({
    ...p,
    part_name: partMap.value[p.part_id]?.name || p.part_id,
    part_image: partMap.value[p.part_id]?.image || '',
  }))
  jewelryItems.value = jRes.data.map((j) => ({
    ...j,
    jewelry_name: jewelryMap.value[j.jewelry_id]?.name || j.jewelry_id,
    jewelry_image: jewelryMap.value[j.jewelry_id]?.image || '',
  }))
}

const doSend = async () => {
  sending.value = true
  try {
    await sendHandcraft(route.params.id)
    message.success('已确认发出')
    await loadData()
  } finally {
    sending.value = false
  }
}

const partColumns = [
  { title: '配件编号', key: 'part_id', width: 110 },
  {
    title: '配件',
    key: 'part_name',
    minWidth: 180,
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name),
  },
  { title: '实际发出', key: 'qty' },
  { title: 'BOM理论', key: 'bom_qty', render: (r) => r.bom_qty ?? '-' },
  {
    title: '差异',
    key: 'diff',
    render: (r) => {
      if (r.bom_qty == null) return '-'
      const diff = r.qty - r.bom_qty
      return h('span', { style: { color: diff > 0 ? '#d03050' : diff < 0 ? '#18a058' : undefined } },
        (diff > 0 ? '+' : '') + diff
      )
    },
  },
]

const jewelryColumns = [
  { title: '饰品编号', key: 'jewelry_id', width: 110 },
  {
    title: '饰品',
    key: 'jewelry_name',
    minWidth: 180,
    render: (row) => renderNamedImage(row.jewelry_name, row.jewelry_image, row.jewelry_name),
  },
  { title: '预期数量', key: 'qty' },
  { title: '状态', key: 'status' },
]

onMounted(async () => {
  try {
    const [pRes, jRes] = await Promise.all([listParts(), listJewelries()])
    pRes.data.forEach((p) => { partMap.value[p.id] = p })
    jRes.data.forEach((j) => { jewelryMap.value[j.id] = j })
    await loadData()
  } finally {
    loading.value = false
  }
})
</script>
