<template>
  <n-modal :show="true" preset="card" title="批量关联订单" :mask-closable="!saving" :closable="!saving" :close-on-esc="!saving" style="width:min(880px,calc(100vw - 24px))" @update:show="value => { if (!value && !saving) emit('close') }">
    <n-alert type="info" :bordered="false">按本手工单的产出匹配订单商品和 BOM 配件备料，无需先生成配件清单。确认前仅为预览；不会扣料、入库或出货。</n-alert>
    <n-select v-model:value="orderId" :options="orders" filterable clearable :loading="ordersLoading" :disabled="saving" placeholder="选择订单号或客户" style="margin:16px 0" @update:value="load" />
    <n-alert v-if="ordersError" type="error">{{ ordersError }} <n-button text @click="loadOrders">重试订单列表</n-button></n-alert>
    <n-spin :show="loading">
      <n-alert v-if="loadError || saveError" type="error">{{ loadError || saveError }} <n-button text :disabled="saving" @click="load">刷新并重新核对</n-button></n-alert>
      <template v-if="data && !loading">
        <n-alert v-if="!data.editable" type="warning">订单已完成或已取消，仅可查看，不可分配。</n-alert>
        <n-empty v-if="!sources.length" description="本手工单没有匹配该订单商品或 BOM 配件的活跃产出" />
        <section v-for="source in sources" :key="source.source_item_id" class="link-source">
          <strong>{{ source.product_name }} · 产出 #{{ source.source_item_id }}</strong>
          <p>计划 {{ source.planned }} {{ source.unit }} · 未分配 {{ source.public_unallocated ?? '待核对' }} · 本单已有 {{ ownQuantity(source, data.order_id) }}</p>
          <n-alert v-if="source.legacy_claim || source.unit_mismatch" type="warning">{{ source.legacy_claim ? '此产出有旧关联或手填客户，需先核对并解除旧归属。' : '产出与配件基本单位不一致，不自动换算。' }}</n-alert>
          <div v-for="line in matchingLines(demands, source)" :key="line.id" class="link-demand">
            <label :for="`batch-${source.source_item_id}-${line.id}`">
              <b>{{ line.material_part_id ? '配件备料' : '商品制作' }}</b> · {{ line.material_part_id ? line.parent_product_name : line.product_name }} · {{ line.customer_code || '未填货号' }} · 明细 #{{ line.order_item_id || line.id }}
              <small>需求 {{ line.quantity }} {{ line.unit }} · 已安排 {{ line.allocated }}<span v-if="line.legacy_claim"> · 旧归属待核对</span></small>
              <small v-if="line.demand_changed" class="warning">BOM／订购量已变化（原需求 {{ line.snapshot_quantity }}），请核对后确认新数量；填 0 可取消原份额。</small>
            </label>
            <n-input-number v-model:value="quantities[source.source_item_id][line.id]" :min="0" :max="Math.max(Number(line.quantity), quantities[source.source_item_id][line.id] || 0)" :precision="0" :disabled="saving || !data.editable || source.legacy_claim || ((source.unit_mismatch || line.legacy_claim) && !ownQuantity(source, data.order_id))" :input-props="{ id: `batch-${source.source_item_id}-${line.id}` }" />
          </div>
        </section>
      </template>
    </n-spin>
    <template #footer><n-space justify="end"><n-button :disabled="saving" @click="emit('close')">返回</n-button><n-button type="primary" :loading="saving" :disabled="loading || !data?.editable || !sources.length || !!loadError" @click="save">确认关联并分配</n-button></n-space></template>
  </n-modal>
</template>
<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { NAlert, NButton, NEmpty, NInputNumber, NModal, NSelect, NSpace, NSpin } from 'naive-ui'
import { listOrders } from '@/api/orders'
import { getOrderProduction, replaceOrderProductionBatch } from '@/api/productionAllocation'
import { productionDemandLines, matchingLines, ownQuantity, sourceQuantities, allocationPayload } from '@/utils/productionAllocation'
const props = defineProps({ productionOrderId: { type: String, required: true } })
const emit = defineEmits(['close', 'saved'])
const orders = ref([]), ordersLoading = ref(false), ordersError = ref(''), orderId = ref(null)
const data = ref(null), loading = ref(false), saving = ref(false), loadError = ref(''), saveError = ref(''), quantities = ref({})
const demands = computed(() => productionDemandLines(data.value))
const sources = computed(() => (data.value?.sources || []).filter(source => source.source_type === 'handcraft' && source.production_order_id === props.productionOrderId && !source.archived && ['pending', 'processing'].includes(source.status) && matchingLines(demands.value, source).length))
let request = 0
async function loadOrders() {
  ordersLoading.value = true; ordersError.value = ''
  try { const response = await listOrders(); orders.value = response.data.filter(order => ['待生产', '生产中'].includes(order.status)).map(order => ({ label: `${order.id} — ${order.customer_name}`, value: order.id })) }
  catch (_) { ordersError.value = '订单列表加载失败' }
  finally { ordersLoading.value = false }
}
async function load() {
  if (saving.value) return
  const id = ++request
  data.value = null; quantities.value = {}; loadError.value = ''; saveError.value = ''; loading.value = !!orderId.value
  if (!orderId.value) return
  try {
    const response = await getOrderProduction(orderId.value)
    if (id !== request) return
    data.value = response.data
    // Share one temporary capacity/demand ledger across outputs. Do not suggest
    // the whole outstanding demand again for every matching production row.
    const ledger = structuredClone(productionDemandLines(response.data))
    for (const source of sources.value) {
      const suggestion = sourceQuantities(ledger, source, !ownQuantity(source, response.data.order_id))
      quantities.value[source.source_item_id] = suggestion
      for (const line of matchingLines(ledger, source)) {
        const existing = sourceQuantities([line], source)[line.id]
        line.allocated = Number(line.allocated || 0) + Math.max(0, suggestion[line.id] - existing)
      }
    }
  } catch (e) { if (id === request) loadError.value = e.response?.data?.detail || '需求加载失败，不能当作无需求' }
  finally { if (id === request) loading.value = false }
}
async function save() {
  if (saving.value || loading.value || loadError.value || !data.value?.editable) return
  saveError.value = ''
  try {
    const payloads = sources.value.filter(source => !source.legacy_claim && (!source.unit_mismatch || ownQuantity(source, data.value.order_id))).map(source => allocationPayload(demands.value, source, quantities.value[source.source_item_id]))
    if (!payloads.some(source => source.allocations.some(row => row.quantity > 0)) && !sources.value.some(source => ownQuantity(source, data.value.order_id))) throw new Error('请填写大于 0 的分配数量')
    if (!payloads.length) throw new Error('没有可调整的产出，请先核对旧归属与单位')
    saving.value = true
    await replaceOrderProductionBatch(data.value.order_id, payloads)
    emit('saved')
  } catch (e) { saveError.value = e.response?.data?.detail || e.message || '保存失败' }
  finally { saving.value = false }
}
onBeforeRouteLeave(() => !saving.value)
onBeforeRouteUpdate(() => !saving.value)
const beforeUnload = event => { if (saving.value) { event.preventDefault(); event.returnValue = '' } }
onMounted(() => { loadOrders(); window.addEventListener('beforeunload', beforeUnload) })
onBeforeUnmount(() => { ++request; window.removeEventListener('beforeunload', beforeUnload) })
</script>
<style scoped>
.link-source { padding: 16px 0; border-bottom: 1px solid #eceef0; }
.link-source p, .link-demand small { color: #777; font-size: 12px; }
.link-demand { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 12px; }
.link-demand small { display: block; margin-top: 4px; }
.link-demand .n-input-number { width: 160px; flex-shrink: 0; }
.link-demand .warning { color: #a46613; }
@media (max-width: 560px) { .link-demand { flex-wrap: wrap; } }
</style>
