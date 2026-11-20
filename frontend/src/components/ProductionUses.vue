<template>
  <n-card title="生产计划用途与订单来源" size="small" style="margin: 16px 0;">
    <template #header-extra><n-button size="small" :loading="loading" @click="load">刷新用途</n-button></template>
    <n-alert type="info" :bordered="false">以下仅为直接产出的需求数量计划，不表示客户已预留库存、材料已发出或客户已出货。整批实收不自动分摊给各订单；未覆盖上游 BOM 备料。</n-alert>
    <n-button v-if="sourceOrder" text type="primary" style="margin-top: 12px;" @click="openOrder(sourceOrder)">← 返回 {{ sourceOrder }} 的生产需求</n-button>
    <p v-if="error" role="alert">{{ error }}</p>
    <section v-for="source in sources" :key="source.source_item_id" class="use-section">
      <strong>{{ source.product_name }} · {{ source.product_id }} · 产出明细 #{{ source.source_item_id }}</strong>
      <p>整批计划 {{ source.planned }} · 实收 {{ source.received }} · 损耗 {{ source.loss }} {{ source.unit }}<br>已安排 {{ source.allocated }} · 公共未安排 {{ source.public_unallocated ?? '旧归属待核对' }}</p>
      <p v-if="source.legacy_claim">存在旧关联／批次或手填客户归属，保留原入口查询，未自动生成明细份额。</p>
      <p v-if="source.unit_mismatch">产出单位与商品基本单位不一致，请核对；未自动换算。</p>
      <p v-if="source.risk">存在已确认损耗，需另行核对交付缺口；未自动减少原计划或分摊实收。</p>
      <p v-if="!source.legacy_claim && !source.allocations.length">暂无订单数量安排，保留公共备库存用途。</p>
      <div v-for="row in source.allocations" :key="row.order_item_id" class="use-row" :class="{ current: row.order_id === sourceOrder }">
        <n-button text type="primary" @click="openOrder(row.order_id)">{{ row.order_id }} · {{ row.customer_name }}</n-button>
        <span>明细 #{{ row.order_item_id }} · {{ row.customer_code || '未填客户货号' }} · 安排 <b>{{ row.quantity }} {{ source.unit }}</b></span>
      </div>
    </section>
  </n-card>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NCard } from 'naive-ui'
import { getProductionUses } from '@/api/productionAllocation'
const props = defineProps({ type: { type: String, required: true }, orderId: { type: String, required: true } })
const route = useRoute(), router = useRouter()
const sources = ref([]), loading = ref(false), error = ref('')
const sourceOrder = computed(() => typeof route.query.from_order === 'string' ? route.query.from_order : '')
let requestId = 0
async function load() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const response = await getProductionUses(props.type, props.orderId)
    if (id === requestId) sources.value = response.data
  } catch (e) { if (id === requestId) error.value = e.response?.data?.detail || '用途加载失败，请重试' }
  finally { if (id === requestId) loading.value = false }
}
const openOrder = id => router.push(`/orders/${encodeURIComponent(id)}/production`)
watch(() => [props.type, props.orderId], load, { immediate: true })
</script>

<style scoped>
.use-section { padding: 16px 0; border-bottom: 1px solid #eee; overflow-wrap: anywhere; }
.use-section:last-child { border: 0; }
.use-row { display: flex; flex-wrap: wrap; gap: 8px 20px; padding: 10px; }
.current { background: #edf8ef; border-radius: 6px; }
</style>
