<template>
  <div>
    <div class="page-header">
      <h2 class="page-title">仪表盘</h2>
      <div class="page-divider"></div>
    </div>
    <n-grid :cols="isMobile ? 2 : 4" :x-gap="12" :y-gap="12">
      <n-gi v-for="card in cards" :key="card.key">
        <n-card
          hoverable
          style="cursor: pointer;"
          @click="router.push(card.route)"
        >
          <n-spin :show="card.loading">
            <div style="text-align: center; padding: 8px 0;">
              <n-text depth="3" style="font-size: 14px;">{{ card.title }}</n-text>
              <n-h1 :style="{ margin: '8px 0', color: card.color }">{{ card.value ?? '-' }}</n-h1>
            </div>
          </n-spin>
        </n-card>
      </n-gi>
    </n-grid>
  </div>
</template>

<script setup>
import { reactive, onMounted } from 'vue'
import { useIsMobile } from '@/composables/useIsMobile'
import { useRouter } from 'vue-router'
import { NGrid, NGi, NCard, NSpin, NH1, NText } from 'naive-ui'
import { listParts } from '@/api/parts'
import { batchGetStock } from '@/api/inventory'
import { listOrders } from '@/api/orders'
import { listPlating } from '@/api/plating'
import { listHandcraft } from '@/api/handcraft'

const router = useRouter()
const { isMobile } = useIsMobile()

const cards = reactive([
  { key: 'low-stock', title: '低库存配件（< 10）', value: null, loading: true, route: '/parts', color: '#F59E0B' },
  { key: 'pending-orders', title: '待处理订单', value: null, loading: true, route: '/orders', color: '#6366F1' },
  { key: 'plating', title: '进行中电镀单', value: null, loading: true, route: '/plating', color: '#8B5CF6' },
  { key: 'handcraft', title: '进行中手工单', value: null, loading: true, route: '/handcraft', color: '#10B981' },
])

const loadCard = (key, fn) => {
  const card = cards.find((c) => c.key === key)
  return fn()
    .then((res) => { card.value = res })
    .finally(() => { card.loading = false })
}

onMounted(async () => {
  // Low-stock parts: fetch all parts, then batch fetch stock
  loadCard('low-stock', async () => {
    const { data: parts } = await listParts()
    if (!parts.length) return 0
    const { data: stockMap } = await batchGetStock('part', parts.map((p) => p.id))
    return parts.filter((p) => (stockMap[p.id] ?? 0) < 10).length
  })

  loadCard('pending-orders', async () => {
    const { data } = await listOrders({ status: '待生产' })
    return data.length
  })

  loadCard('plating', async () => {
    const { data } = await listPlating({ status: 'processing' })
    return data.length
  })

  loadCard('handcraft', async () => {
    const { data } = await listHandcraft({ status: 'processing' })
    return data.length
  })
})
</script>
