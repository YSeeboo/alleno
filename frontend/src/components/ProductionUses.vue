<template>
  <section class="production-uses" aria-label="生产计划用途与订单来源" :aria-busy="loading">
    <header class="use-header">
      <button type="button" class="use-toggle" :aria-expanded="expanded" @click="expanded = !expanded">
        <span class="use-chevron" :class="{ expanded }" aria-hidden="true">›</span>
        <strong>生产计划用途与订单来源</strong>
        <span v-if="loaded" class="use-summary">{{ sources.length }} 项产出 · {{ orderCount }} 个订单</span>
        <span v-else class="use-summary">{{ loading ? '加载中…' : '暂未加载' }}</span>
        <span v-if="reviewCount" class="use-review">{{ reviewCount }} 项待核对</span>
        <span class="use-expand">{{ expanded ? '收起' : '展开' }}</span>
      </button>
      <div class="use-actions">
        <n-button v-if="sourceOrder" text size="tiny" type="primary" @click="openOrder(sourceOrder)">← 返回 {{ sourceOrder }}</n-button>
        <n-button text size="tiny" :loading="loading" @click="load">刷新用途</n-button>
      </div>
    </header>
    <p v-if="error" class="use-error" role="alert">{{ error }}{{ loaded ? '（当前显示上次加载结果）' : '' }}</p>
    <div v-if="expanded" class="use-body">
      <p class="use-note">仅为直接产出的需求计划，不代表库存预留、材料发出或客户出货。整批实收不自动分摊，未覆盖上游 BOM 备料。</p>
      <div class="use-sources">
        <p v-if="loaded && !sources.length" class="use-empty">暂无直接产出明细</p>
        <section v-for="source in sources" :key="source.source_item_id" class="use-source">
          <div class="use-source-head">
            <div class="use-product"><strong>{{ source.product_name }}</strong><small>{{ source.product_id }} · 产出 #{{ source.source_item_id }}</small></div>
            <dl class="use-quantities">
              <div><dt>计划</dt><dd>{{ source.planned }} <small>{{ source.unit }}</small></dd></div>
              <div><dt>实收</dt><dd>{{ source.received }} <small>{{ source.unit }}</small></dd></div>
              <div :class="{ 'has-loss': source.risk }"><dt>损耗</dt><dd>{{ source.loss }} <small>{{ source.unit }}</small></dd></div>
              <div><dt>已安排</dt><dd>{{ source.allocated }} <small>{{ source.unit }}</small></dd></div>
              <div><dt>公共未安排</dt><dd>{{ source.public_unallocated ?? '待核对' }} <small v-if="source.public_unallocated != null">{{ source.unit }}</small></dd></div>
            </dl>
          </div>
          <div v-if="source.legacy_claim || source.unit_mismatch || source.risk" class="use-flags">
            <span v-if="source.legacy_claim">旧归属待核对：存在旧关联／批次或手填客户，请从原入口查询；未生成明细份额。</span>
            <span v-if="source.unit_mismatch">产出与商品基本单位不一致，未自动换算。</span>
            <span v-if="source.risk">已有确认损耗，请核对交付缺口；未自动减少计划或分摊实收。</span>
          </div>
          <p v-if="!source.legacy_claim && !source.allocations.length" class="use-public">公共备库存 · 暂无订单安排</p>
          <div v-for="row in source.allocations" :key="row.order_item_id" class="use-row" :class="{ current: row.order_id === sourceOrder }">
            <button type="button" class="use-order" @click="openOrder(row.order_id)">{{ row.order_id }}<span>{{ row.customer_name }}</span></button>
            <span class="use-line">明细 #{{ row.order_item_id }} · {{ row.customer_code || '未填客户货号' }}</span>
            <span class="use-allocation">安排 <b>{{ row.quantity }}</b> {{ source.unit }}</span>
          </div>
        </section>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton } from 'naive-ui'
import { getProductionUses } from '@/api/productionAllocation'
const props = defineProps({ type: { type: String, required: true }, orderId: { type: String, required: true } })
const route = useRoute(), router = useRouter()
const sources = ref([]), loading = ref(false), error = ref('')
const expanded = ref(false), loaded = ref(false)
const sourceOrder = computed(() => typeof route.query.from_order === 'string' ? route.query.from_order : '')
// Count identities only: quantities in different product units must not be combined.
const orderCount = computed(() => new Set(sources.value.flatMap(source => source.allocations.map(row => row.order_id))).size)
const reviewCount = computed(() => sources.value.filter(source => source.legacy_claim || source.unit_mismatch || source.risk).length)
let requestId = 0
async function load() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const response = await getProductionUses(props.type, props.orderId)
    if (id === requestId) { sources.value = response.data; loaded.value = true }
  } catch (e) { if (id === requestId) error.value = e.response?.data?.detail || '用途加载失败，请重试' }
  finally { if (id === requestId) loading.value = false }
}
const openOrder = id => router.push(`/orders/${encodeURIComponent(id)}/production`)
watch(() => [props.type, props.orderId], () => {
  sources.value = []; loaded.value = false; expanded.value = false
  load()
}, { immediate: true })
</script>

<style scoped>
.production-uses { margin: 12px 0; border: 1px solid #ECEDEF; border-radius: 8px; background: #fff; color: #475569; font-size: 12px; overflow: hidden; }
.use-header { display: flex; align-items: center; gap: 12px; padding: 0 14px; min-height: 46px; }
.use-toggle { flex: 1; min-width: 0; display: flex; align-items: center; flex-wrap: wrap; gap: 6px 12px; padding: 12px 0; border: 0; background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.use-toggle strong { font-weight: 600; color: #1A1D21; }
.use-toggle:focus-visible, .use-order:focus-visible { outline: 2px solid #1E7A5A; outline-offset: 3px; border-radius: 3px; }
.use-chevron { color: #8B9096; font-size: 18px; line-height: 16px; transition: transform .15s; }
.use-chevron.expanded { transform: rotate(90deg); }
.use-summary, .use-expand, .use-line { color: #8B9096; }
.use-expand { margin-left: auto; font-size: 11px; }
.use-review { color: #9A681E; background: #FBF0DC; border-radius: 4px; padding: 1px 6px; font-size: 11px; }
.use-actions { display: flex; align-items: center; flex-wrap: wrap; justify-content: flex-end; gap: 6px 12px; }
.use-body { border-top: 1px solid #ECEDEF; }
.use-note { margin: 0; padding: 8px 14px; background: #FAFBFC; color: #7C858C; font-size: 11px; line-height: 1.6; }
.use-sources { max-height: 420px; overflow-y: auto; }
.use-source { padding: 10px 14px; border-top: 1px solid #F0F1F2; overflow-wrap: anywhere; }
.use-source-head { display: flex; align-items: center; gap: 12px 24px; flex-wrap: wrap; }
.use-product { flex: 1 1 180px; min-width: 0; }
.use-product strong { display: block; color: #1A1D21; font-weight: 600; }
.use-product small { display: block; color: #8B9096; font-size: 10px; margin-top: 2px; }
.use-quantities { display: flex; flex-wrap: wrap; gap: 6px 20px; margin: 0; font-variant-numeric: tabular-nums; }
.use-quantities>div { display: flex; align-items: baseline; gap: 6px; }
.use-quantities dt { color: #8B9096; font-size: 11px; }
.use-quantities dd { margin: 0; font-weight: 600; color: #475569; }
.use-quantities dd small { font-size: 10px; font-weight: 400; color: #8B9096; }
.use-quantities .has-loss dd { color: #9A681E; }
.use-flags { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 6px; color: #9A681E; font-size: 11px; }
.use-public, .use-empty { color: #8B9096; font-size: 11px; margin: 6px 0 0; }
.use-empty { margin: 0; padding: 12px 14px; }
.use-row { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr) auto; align-items: baseline; gap: 4px 16px; margin-top: 6px; padding: 5px 8px; background: #FAFBFC; border-radius: 4px; }
.use-order { display: flex; flex-wrap: wrap; gap: 2px 10px; min-width: 0; padding: 0; border: 0; background: none; color: #1E7A5A; font: inherit; text-align: left; overflow-wrap: anywhere; cursor: pointer; }
.use-order:hover { text-decoration: underline; }
.use-order span { color: #475569; }
.use-line { font-size: 11px; }
.use-allocation { text-align: right; font-variant-numeric: tabular-nums; }
.use-row.current { background: #EDF8EF; box-shadow: inset 2px 0 #1E7A5A; }
.use-error { margin: 0; padding: 0 14px 10px; color: #B45309; overflow-wrap: anywhere; }
@media (max-width: 600px) {
  .use-header { flex-wrap: wrap; gap: 0; padding: 0 10px; }
  .use-toggle { flex-basis: 100%; gap: 6px 8px; padding: 10px 0; }
  .use-toggle strong { font-size: 12px; }
  .use-summary { margin-left: 16px; }
  .use-actions { width: 100%; padding-bottom: 8px; }
  .use-source { padding: 10px; }
  .use-source-head { gap: 6px; }
  .use-product { flex-basis: 100%; }
  .use-quantities { gap: 4px 12px; }
  .use-row { grid-template-columns: minmax(0,1fr) auto; gap: 2px 8px; }
  .use-line { grid-column: 1; grid-row: 2; }
  .use-allocation { grid-column: 2; grid-row: 1 / 3; align-self: center; }
}
</style>
