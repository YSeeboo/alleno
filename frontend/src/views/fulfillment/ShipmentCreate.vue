<template>
  <div class="fulfillment-page">
    <div class="page-header"><div class="page-breadcrumb">生产 / <router-link to="/shipments">出货管理</router-link> / 新建出货</div><h2 class="page-title">新建出货单</h2><div class="page-divider"></div></div>
    <div class="filter-bar"><n-button text @click="router.push('/shipments')">← 返回出货列表</n-button><span v-if="draft" class="wf-muted">已保存草稿 {{ draft.id }}</span></div>
    <n-steps :current="step" size="small" class="wf-section"><n-step title="选择订单与明细" /><n-step title="核对并确认实发" /></n-steps>
    <n-alert v-if="error" type="error" class="wf-notice">{{ error }}</n-alert>
    <n-spin :show="loading">
      <n-card v-if="step === 1" title="选择实际出货明细" class="wf-section">
        <p class="wf-section-description">不自动勾选、不预填出货量，不要求生产关联。草稿和核对均不扣库存。</p>
        <n-form label-placement="top" :disabled="saving || !!draft">
          <n-form-item label="客户订单"><n-select v-model:value="orderId" :options="orderOptions" filterable placeholder="请选择客户订单" aria-label="客户订单" @update:value="loadOrder" /></n-form-item>
        </n-form>
        <template v-if="summary && !summary.managed"><n-alert type="warning" class="wf-notice">此订单尚未核对历史出货，不能直接从 0 记账。请先到订单详情核对并启用。</n-alert><router-link :to="`/orders/${orderId}`">打开订单核对 →</router-link></template>
        <div v-else-if="summary" class="wf-table-wrap"><n-table :bordered="false" class="wf-table wf-shipment-entry"><thead><tr><th>选择</th><th>产品 / 客户货号</th><th>剩余待发</th><th>本行预留 / 公共可用</th><th>本次实发</th></tr></thead><tbody><tr v-for="line in summary.lines" :key="line.id"><td><n-checkbox v-model:checked="selected[line.id]" :disabled="saving || Number(line.remaining) <= 0" :aria-label="`选择 ${line.product_name} 明细 ${line.id}`">实际发货项</n-checkbox></td><td><ProductCell :line="line" /></td><td>待发 {{ line.remaining }} {{ line.unit }}</td><td>预留 {{ line.reserved }} / 公共 {{ line.public_available }}</td><td><n-input-number v-model:value="quantities[line.id]" :input-props="{ 'aria-label': `明细 ${line.id} 本次实发` }" :disabled="!selected[line.id] || saving" :min="1" :precision="0" placeholder="实际数量" style="width:145px" /></td></tr></tbody></n-table></div>
        <n-form label-placement="top" :disabled="saving" style="margin-top:16px">
          <n-form-item label="物流信息（可选）"><n-input v-model:value="tracking" :maxlength="2000" placeholder="物流公司及单号" :input-props="{ 'aria-label': '物流信息' }" /></n-form-item>
          <n-form-item label="出货备注（可选）"><n-input v-model:value="note" type="textarea" :maxlength="5000" :rows="3" placeholder="出货备注" :input-props="{ 'aria-label': '出货备注' }" /></n-form-item>
        </n-form>
        <div class="wf-dialog-footer"><n-button :disabled="saving || !summary?.editable" @click="save(false)">保存草稿</n-button><n-button type="primary" :disabled="saving || !summary?.editable" @click="review">下一步，核对实物</n-button></div>
      </n-card>
      <template v-else>
        <n-alert type="info" :bordered="false" class="wf-notice">确认才会扣库，优先消耗当前所选明细的预留，其余使用公共现货。未选中同款明细的预留也不可挪用。</n-alert>
        <n-card title="核对本次实际出货" class="wf-section">
          <template #header-extra><n-button text type="primary" :disabled="saving" @click="refreshReview">刷新库存与剩余待发</n-button></template>
          <p class="wf-section-description">{{ orderId }} · {{ summary?.customer_name }} · 不要求加工关联</p>
          <div class="wf-table-wrap"><n-table :bordered="false" class="wf-table"><thead><tr><th>实际出货商品</th><th>本次实发</th><th>本行预留</th><th>公共可用</th></tr></thead><tbody><tr v-for="entry in entries" :key="entry.order_item_id"><td><ProductCell :line="lineFor(entry)" /></td><td><strong>{{ entry.quantity }} {{ lineFor(entry).unit }}</strong></td><td>{{ lineFor(entry).reserved }}</td><td>{{ lineFor(entry).public_available }}</td></tr></tbody></n-table></div>
          <n-alert v-for="warning in warnings" :key="warning" type="warning" class="wf-notice">{{ warning }}</n-alert>
          <n-alert v-if="!warnings.length" type="success" :bordered="false" class="wf-notice">当前数量与库存校验通过。最终确认仍以服务器实时校验为准。</n-alert>
          <p class="wf-muted">实际有货但尚未入账？<router-link to="/inventory" target="_blank" rel="noopener">在新窗口登记真实入库 →</router-link> 然后刷新本页核对。系统不会按缺口自动造库存。</p>
          <n-descriptions :column="1" label-placement="left" style="margin:16px 0"><n-descriptions-item label="物流">{{ tracking || '未填写' }}</n-descriptions-item><n-descriptions-item label="备注">{{ note || '无' }}</n-descriptions-item></n-descriptions>
          <n-checkbox v-model:checked="actualChecked" :disabled="saving">我已核对实际货物与本次数量，确认将扣减库存并计入订单出货进度。</n-checkbox>
          <div class="wf-dialog-footer"><n-button v-if="!draft" :disabled="saving" @click="step = 1; actualChecked = false">返回修改</n-button><n-button v-else :disabled="saving" @click="router.push(`/shipments/${draft.id}`)">查看已保存草稿</n-button><n-button :disabled="saving" @click="save(false)">保存草稿</n-button><n-button type="primary" :loading="saving" :disabled="!actualChecked || warnings.length > 0" @click="save(true)">确认实际出货</n-button></div>
        </n-card>
      </template>
    </n-spin>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { NAlert, NButton, NCard, NCheckbox, NDescriptions, NDescriptionsItem, NForm, NFormItem, NInput, NInputNumber, NSelect, NSpin, NStep, NSteps, NTable, useMessage } from 'naive-ui'
import { listOrders } from '@/api/orders'
import { getFulfillment, createShipment, confirmShipment } from '@/api/fulfillment'
import { shipmentEntries, stockWarnings } from '@/utils/fulfillment'
import ProductCell from '@/components/fulfillment/ProductCell.vue'
const route = useRoute(), router = useRouter(), message = useMessage()
const orders = ref([]), orderId = ref(typeof route.query.order_id === 'string' ? route.query.order_id : ''), summary = ref(null)
const orderOptions = computed(() => orders.value.map(order => ({ value: order.id, label: `${order.id} · ${order.customer_name}` })))
const selected = ref({}), quantities = ref({}), entries = ref([]), step = ref(1), tracking = ref(''), note = ref(''), actualChecked = ref(false)
const loading = ref(false), saving = ref(false), error = ref(''), draft = ref(null)
let requestKey = crypto.randomUUID(), requestId = 0
const warnings = computed(() => summary.value ? stockWarnings(summary.value.lines, entries.value) : ['订单数据未加载'])
const lineFor = entry => summary.value?.lines.find(line => line.id === entry.order_item_id) || { id: entry.order_item_id, product_name: '明细待重新核对' }
async function loadOrder() {
  const request = ++requestId
  selected.value = {}; quantities.value = {}; summary.value = null; actualChecked.value = false; error.value = ''; requestKey = crypto.randomUUID()
  if (!orderId.value) return
  loading.value = true
  try { const response = await getFulfillment(orderId.value); if (request === requestId) summary.value = response.data }
  catch (e) { if (request === requestId) error.value = e.response?.data?.detail || '加载订单失败' }
  finally { if (request === requestId) loading.value = false }
}
async function review() {
  error.value = ''
  try { entries.value = shipmentEntries(summary.value.lines, selected.value, quantities.value); if (await refreshReview()) step.value = 2 }
  catch (e) { error.value = e.message }
}
async function refreshReview() {
  actualChecked.value = false
  loading.value = true; error.value = ''
  try { summary.value = (await getFulfillment(orderId.value)).data; return true }
  catch (e) { summary.value = null; error.value = e.response?.data?.detail || '重新核对失败，请刷新后再确认'; return false }
  finally { loading.value = false }
}
async function save(confirm) {
  if (saving.value || (confirm && !actualChecked.value)) return
  saving.value = true; error.value = ''
  try {
    if (!draft.value) {
      const lines = step.value === 1 ? shipmentEntries(summary.value.lines, selected.value, quantities.value) : entries.value
      draft.value = (await createShipment({ order_id: orderId.value, request_key: requestKey, lines, tracking: tracking.value, note: note.value })).data
    }
    if (confirm) { await confirmShipment(draft.value.id); message.success('实际出货已确认，库存仅扣减一次') }
    else message.success('草稿已保存，未占库或扣库')
    saving.value = false
    router.push(`/shipments/${draft.value.id}`)
  } catch (e) { error.value = e.response?.data?.detail || e.message || '提交失败'; actualChecked.value = false }
  finally { saving.value = false }
}
onBeforeRouteLeave(() => !saving.value)
onMounted(async () => { try { orders.value = (await listOrders()).data.filter(o => ['待生产', '生产中'].includes(o.status)); await loadOrder() } catch (e) { error.value = e.response?.data?.detail || '加载失败' } })
</script>
