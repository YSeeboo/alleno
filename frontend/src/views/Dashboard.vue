<template>
  <div>
    <n-h2>仪表盘</n-h2>
    <n-grid :cols="4" :x-gap="16" :y-gap="16">
      <n-gi v-for="card in cards" :key="card.key">
        <n-card
          hoverable
          style="cursor: pointer;"
          @click="router.push(card.route)"
        >
          <n-spin :show="card.loading">
            <div style="text-align: center; padding: 8px 0;">
              <n-text depth="3" style="font-size: 14px;">{{ card.title }}</n-text>
              <n-h1 style="margin: 8px 0; color: #18a058;">{{ card.value ?? '-' }}</n-h1>
            </div>
          </n-spin>
        </n-card>
      </n-gi>
    </n-grid>
  </div>
</template>

<script setup>
import { reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NGrid, NGi, NCard, NSpin, NH2, NH1, NText } from 'naive-ui'
import { listParts } from '@/api/parts'
import { getStock } from '@/api/inventory'
import { listOrders } from '@/api/orders'
import { listPlating } from '@/api/plating'
import { listHandcraft } from '@/api/handcraft'

const router = useRouter()

const cards = reactive([
  { key: 'low-stock', title: '低库存配件（< 10）', value: null, loading: true, route: '/parts' },
  { key: 'pending-orders', title: '待处理订单', value: null, loading: true, route: '/orders' },
  { key: 'plating', title: '进行中电镀单', value: null, loading: true, route: '/plating' },
  { key: 'handcraft', title: '进行中手工单', value: null, loading: true, route: '/handcraft' },
])

const loadCard = (key, fn) => {
  const card = cards.find((c) => c.key === key)
  return fn()
    .then((res) => { card.value = res })
    .finally(() => { card.loading = false })
}

onMounted(async () => {
  // Low-stock parts: fetch all parts, then fetch stock for each in parallel
  loadCard('low-stock', async () => {
    const { data: parts } = await listParts()
    const stocks = await Promise.all(
      parts.map((p) => getStock('part', p.id).then((r) => r.data.current).catch(() => 0))
    )
    return stocks.filter((s) => s < 10).length
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
