<template>
  <div>
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">配件详情</n-h2>
    </n-space>

    <n-spin :show="loading">
      <n-card v-if="part" title="基本信息" style="margin-bottom: 16px;">
        <n-descriptions :column="3" bordered>
          <n-descriptions-item label="编号">{{ part.id }}</n-descriptions-item>
          <n-descriptions-item label="配件">{{ part.name }}</n-descriptions-item>
          <n-descriptions-item label="图片">
            <n-image
              v-if="part.image"
              :src="part.image"
              :alt="part.name"
              :width="48"
              :height="48"
              object-fit="cover"
              style="border-radius: 8px; border: 1px solid #ffd6d6; overflow: hidden; display: block; cursor: zoom-in;"
            />
            <span v-else>无图</span>
          </n-descriptions-item>
          <n-descriptions-item label="类目">{{ part.category || '-' }}</n-descriptions-item>
          <n-descriptions-item label="颜色">{{ part.color || '-' }}</n-descriptions-item>
          <n-descriptions-item label="单位">{{ part.unit || '-' }}</n-descriptions-item>
          <n-descriptions-item label="单件成本">{{ part.unit_cost?.toFixed(3) ?? '-' }}</n-descriptions-item>
          <n-descriptions-item label="默认电镀工艺">{{ part.plating_process || '-' }}</n-descriptions-item>
          <n-descriptions-item label="关联原色配件">
            <router-link v-if="part.parent_part_id" :to="`/parts/${part.parent_part_id}`" style="color: #2080f0;">
              {{ parentPartName || part.parent_part_id }}
            </router-link>
            <span v-else>-</span>
          </n-descriptions-item>
          <n-descriptions-item label="当前库存">
            <n-text :style="{ color: stock < 10 ? '#d03050' : '#18a058', fontWeight: 600 }">
              {{ stock }}
            </n-text>
          </n-descriptions-item>
        </n-descriptions>
      </n-card>

      <n-card title="库存流水">
        <n-data-table v-if="logs.length > 0" :columns="logColumns" :data="logs" :bordered="false" />
        <n-empty v-else description="暂无流水" style="margin-top: 16px;" />
      </n-card>
    </n-spin>
  </div>
</template>

<script setup>
import { ref, h, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NText, NEmpty, NImage,
} from 'naive-ui'
import { getPart } from '@/api/parts'
import { getStock, getStockLog } from '@/api/inventory'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const part = ref(null)
const parentPartName = ref('')
const stock = ref(0)
const logs = ref([])

const logColumns = [
  { title: '时间', key: 'created_at', render: (r) => new Date(r.created_at).toLocaleString('zh-CN') },
  {
    title: '变动数量',
    key: 'change_qty',
    render: (r) =>
      h('span', { style: { color: r.change_qty > 0 ? '#18a058' : '#d03050', fontWeight: 600 } },
        (r.change_qty > 0 ? '+' : '') + r.change_qty
      ),
  },
  { title: '原因', key: 'reason' },
  { title: '备注', key: 'note', render: (r) => r.note || '-' },
]

onMounted(async () => {
  const id = route.params.id
  try {
    const [pRes, sRes, lRes] = await Promise.all([
      getPart(id),
      getStock('part', id),
      getStockLog('part', id),
    ])
    part.value = pRes.data
    stock.value = sRes.data.current
    logs.value = lRes.data
  } finally {
    loading.value = false
  }
  if (part.value?.parent_part_id) {
    try {
      const ppRes = await getPart(part.value.parent_part_id)
      parentPartName.value = `${ppRes.data.id} ${ppRes.data.name}`
    } catch (_) {
      parentPartName.value = part.value.parent_part_id
    }
  }
})
</script>
