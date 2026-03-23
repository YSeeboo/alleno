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
          <n-descriptions-item label="单件成本">
            <template v-if="part.unit_cost != null">
              <span style="font-weight: 600;">¥ {{ fmtMoney(part.unit_cost) }}</span>
              <span v-if="costBreakdown" style="color: #999; font-size: 12px; margin-left: 8px;">
                ({{ costBreakdown }})
              </span>
              <n-popover
                v-if="costLogs.length > 0"
                trigger="hover"
                placement="bottom-start"
                :style="{ maxWidth: '520px' }"
              >
                <template #trigger>
                  <span
                    style="display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 6px; background: #f0f7ff; color: #1890ff; font-size: 13px; cursor: pointer; margin-left: 8px; border: 1px solid #d6e8fa; vertical-align: middle;"
                  >
                    &#x1F4CB;
                  </span>
                </template>
                <div style="min-width: 460px;">
                  <div style="font-weight: 600; font-size: 13px; margin-bottom: 8px; color: #333;">价格变动历史</div>
                  <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <thead>
                      <tr style="border-bottom: 1px solid #f0f0f0;">
                        <th style="padding: 6px 8px; text-align: left; font-weight: 500; color: #666;">时间</th>
                        <th style="padding: 6px 8px; text-align: left; font-weight: 500; color: #666;">当前价格</th>
                        <th style="padding: 6px 8px; text-align: left; font-weight: 500; color: #666;">变动</th>
                        <th style="padding: 6px 8px; text-align: left; font-weight: 500; color: #666;">原因</th>
                        <th style="padding: 6px 8px; text-align: left; font-weight: 500; color: #666;">来源</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="log in costLogs" :key="log.id" style="border-bottom: 1px solid #f5f5f5;">
                        <td style="padding: 6px 8px; color: #999; font-size: 12px;">
                          {{ new Date(log.created_at).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) }}
                          {{ new Date(log.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}
                        </td>
                        <td style="padding: 6px 8px; font-weight: 500;">
                          ¥ {{ fmtMoney(log.unit_cost_after) }}
                        </td>
                        <td style="padding: 6px 8px;">
                          <span
                            :style="{
                              color: (log.unit_cost_after - log.unit_cost_before) >= 0 ? '#18a058' : '#d03050',
                              fontWeight: 600,
                            }"
                          >
                            {{ (log.unit_cost_after - log.unit_cost_before) >= 0 ? '+' : '' }}{{ fmtMoney(log.unit_cost_after - log.unit_cost_before) }}
                          </span>
                        </td>
                        <td style="padding: 6px 8px;">
                          <span
                            style="background: #f5f5f5; padding: 2px 8px; border-radius: 4px; font-size: 11px; color: #666;"
                          >
                            {{ COST_FIELD_LABELS[log.field] || log.field }}
                          </span>
                        </td>
                        <td style="padding: 6px 8px;">
                          <router-link
                            v-if="sourceRoute(log.source_id)"
                            :to="sourceRoute(log.source_id)"
                            style="color: #1890ff; font-size: 12px;"
                          >
                            {{ log.source_id }}
                          </router-link>
                          <span v-else style="color: #999; font-size: 12px;">{{ log.source_id || '-' }}</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </n-popover>
            </template>
            <span v-else>-</span>
          </n-descriptions-item>
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
import { ref, h, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NText, NEmpty, NImage, NPopover,
} from 'naive-ui'
import { getPart, getPartCostLogs } from '@/api/parts'
import { getStock, getStockLog } from '@/api/inventory'
import { fmtMoney } from '@/utils/ui'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const part = ref(null)
const parentPartName = ref('')
const stock = ref(0)
const logs = ref([])
const costLogs = ref([])

const COST_FIELD_LABELS = {
  purchase_cost: '采购费用更新',
  bead_cost: '穿珠费用更新',
  plating_cost: '电镀费用更新',
}

const costBreakdown = computed(() => {
  if (!part.value) return null
  const { purchase_cost, bead_cost, plating_cost } = part.value
  if (purchase_cost == null && bead_cost == null && plating_cost == null) return null
  const parts = []
  if (purchase_cost != null && purchase_cost !== 0) parts.push(`采购 ${fmtMoney(purchase_cost)}`)
  if (bead_cost != null && bead_cost !== 0) parts.push(`穿珠 ${fmtMoney(bead_cost)}`)
  if (plating_cost != null && plating_cost !== 0) parts.push(`电镀 ${fmtMoney(plating_cost)}`)
  return parts.length > 0 ? parts.join(' + ') : null
})

const sourceRoute = (sourceId) => {
  if (!sourceId) return null
  if (sourceId.startsWith('CG-')) return `/purchase-orders/${sourceId}`
  if (sourceId.startsWith('ER-')) return `/plating-receipts/${sourceId}`
  return null
}

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
    getPartCostLogs(id).then(r => { costLogs.value = r.data }).catch(() => {})
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
