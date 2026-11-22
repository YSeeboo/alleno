<template>
  <div class="fulfillment-page order-workspace">
    <OrderWorkspaceHeader :order-id="orderId" :customer-name="data?.customer_name" :status="data?.status" :created-at="order?.created_at" active="fulfillment">
      <n-button v-if="data?.editable && !loading && !error" type="primary" :disabled="busy" @click="router.push({ path: '/shipments/create', query: { order_id: orderId } })">新建出货单</n-button>
    </OrderWorkspaceHeader>
    <n-alert v-if="error" type="error" class="wf-notice">{{ error }} <n-button text type="primary" @click="load">重新加载</n-button></n-alert>
    <n-spin :show="loading">
      <template v-if="data && !error">
        <n-alert v-if="!data.managed" type="warning" class="wf-notice">
          <strong>本单历史实发数量待核对</strong><br>不根据订单状态或生产回收推算已出货量。只有确认本单没有历史实发，才能从 0 开始记录；已有实发或无法确认时请继续核对原始凭据。
          <div><n-button v-if="canEdit" text type="primary" @click="showActivation = true">核对历史实发</n-button></div>
        </n-alert>
        <section class="ow-stats" aria-label="订单概况">
          <div class="ow-stat"><div class="ow-stat-label">订单总额</div><div class="ow-stat-value wf-green">¥{{ fmtMoney(orderTotal) }}</div><div class="ow-stat-note">含包装费 ¥{{ fmtMoney(Number(order?.packaging_cost || 0)) }}</div></div>
          <div class="ow-stat"><div class="ow-stat-label">商品明细</div><div class="ow-stat-value">{{ data.total_items }}<small>项</small></div><div class="ow-stat-note">同款不同货号独立记录</div></div>
          <div class="ow-stat"><div class="ow-stat-label">足量交付</div><div class="ow-stat-value">{{ data.managed ? data.completed_items : '待核对' }}<small v-if="data.managed">/ {{ data.total_items }} 项</small></div><div class="ow-stat-note">{{ data.managed ? `已全部发货 ${data.completed_items} / ${data.total_items} 项` : '历史待核对，不虚构实发数量' }}</div></div>
          <div class="ow-stat"><div class="ow-stat-label">备货状态</div><div class="ow-stat-value">{{ !data.managed ? '待核对' : data.lines.every(l => Number(l.gap) === 0) ? '已备齐' : '待补齐' }}</div><div class="ow-stat-note">仅核算剩余待发的库存预留</div></div>
          <div class="ow-stat"><div class="ow-stat-label">已确认出货</div><div class="ow-stat-value">{{ shipments.filter(s => s.status === 'confirmed').length }}<small>笔</small></div><div class="ow-stat-note">{{ data.managed ? '支持按明细分批出货' : '仅统计可核实凭据' }}</div></div>
        </section>
        <OrderSection title="商品明细" :count="`${data.total_items} 项`">
          <template #header-extra>
            <n-button text type="primary" size="small" class="ow-secondary-action" :disabled="busy" @click="openProduction">查看生产安排 →</n-button>
            <n-button text type="primary" size="small" :disabled="busy" @click="showMaterials = true">物料工具</n-button>
            <n-button v-if="canEdit" text type="primary" size="small" :disabled="busy" @click="showBatchCode = true">客户货号</n-button>
            <n-button v-if="canEdit" size="small" type="primary" secondary :disabled="busy" @click="openLineEditor()">＋ 添加商品</n-button>
          </template>
          <div class="ow-table-panel"><div class="wf-table-wrap" role="region" aria-label="商品明细，可横向滚动" tabindex="0"><n-table :bordered="false" class="wf-table ow-product-table"><thead><tr><th>商品 / 客户货号</th><th class="ow-num">单价 / 金额</th><th class="ow-num">订购数量</th><th class="ow-num">生产安排</th><th class="ow-num">已预留待发</th><th class="ow-num">已出货</th><th class="ow-num">尚待备货</th><th>操作</th></tr></thead><tbody>
            <tr v-for="line in data.lines" :key="line.id">
              <td><ProductCell :line="line" interactive @inspect="selectedProduct = $event" /><small v-if="line.remarks" class="wf-subtext ow-line-remarks">{{ line.remarks }}</small></td>
              <td class="ow-num">¥{{ fmtPrice(Number(line.unit_price)) }}<small class="wf-subtext">小计 ¥{{ fmtMoney(line.quantity * Number(line.unit_price)) }}</small></td>
              <td class="ow-num"><strong>{{ line.quantity }}</strong> <small class="wf-muted">{{ line.unit }}</small></td>
              <td class="ow-num"><n-button text type="primary" size="small" :disabled="busy" @click="openProduction">{{ line.planned }}</n-button><small class="wf-subtext">计划，不代表库存</small></td>
              <td class="ow-num">{{ data.managed ? line.reserved : '待核对' }}<small class="wf-subtext">公共可用 {{ line.public_available }} {{ line.unit }}</small><div v-if="data.editable" class="wf-actions ow-reservation-actions"><n-button text type="primary" size="small" :disabled="busy" @click="editReservation(line, false)">预留库存</n-button><n-button v-if="Number(line.reserved)" text size="small" :disabled="busy" @click="editReservation(line, true)">取消预留</n-button></div></td>
              <td class="ow-num"><strong :class="{ 'wf-green': data.managed }">{{ line.shipped ?? '未核实' }}</strong><progress v-if="data.managed" class="ow-progress" :value="Number(line.shipped)" :max="line.quantity" :aria-label="`${line.customer_code || line.product_name} 实发进度`" /><small class="wf-subtext">{{ data.managed ? `待发 ${line.remaining} ${line.unit || ''}` : '不自动补记' }}</small></td>
              <td class="ow-num wf-amber">{{ line.gap ?? '—' }}</td>
              <td><div v-if="canEdit" class="wf-actions ow-row-actions"><n-button text type="primary" size="small" :disabled="busy" @click="openLineEditor(line)">编辑</n-button><n-popconfirm :disabled="busy || !canDeleteLine" @positive-click="removeLine(line)"><template #trigger><n-button text type="error" size="small" :loading="deletingLineId === line.id" :disabled="busy || !canDeleteLine" :title="!canDeleteLine ? '订单至少保留一条商品明细' : undefined">删除</n-button></template>仅无业务关联的明细可删除，确定删除 {{ line.customer_code || line.product_name }}？</n-popconfirm></div></td>
            </tr>
          </tbody></n-table></div>
          <div class="ow-table-total"><span>商品金额<strong>¥{{ fmtMoney(Number(order?.total_amount || 0)) }}</strong></span><span>包装费<strong>¥{{ fmtMoney(Number(order?.packaging_cost || 0)) }}</strong></span><span>合计<strong>¥{{ fmtMoney(orderTotal) }}</strong></span></div></div>
          <template #footer>尚待备货 = 订购 − 已出货 − 待发预留；生产计划不与现货相加。现货可直接出货，无需关联生产或 BOM；每条明细足量出货后订单才会完成。表格可横向滚动。</template>
        </OrderSection>
        <div class="ow-bottom-grid">
          <OrderSection title="出货记录" :count="shipments.length"><template #header-extra><n-button v-if="data.editable" text type="primary" size="small" :disabled="busy" @click="router.push({ path: '/shipments/create', query: { order_id: orderId } })">新建出货单</n-button><n-button text size="small" :disabled="busy" @click="router.push('/shipments')">查看全部</n-button></template><div class="ow-panel"><ShipmentTable :shipments="shipments" compact /></div><template #footer>只展示实际单据，不把加工回收当成客户出货。</template></OrderSection>
          <OrderCosts v-if="order" :order="order" :editable="canEdit" @saved="load" @busy="costBusy = $event" />
        </div>
      </template>
    </n-spin>
    <n-modal v-model:show="showMaterials" preset="card" title="物料工具" class="order-workspace" style="width:min(1100px,calc(100vw - 24px))"><OrderMaterials v-if="data && showMaterials" :order-id="orderId" :lines="data.lines" :editable="canEdit" /></n-modal>
    <n-modal :show="!!selectedProduct" preset="card" title="商品详情" class="order-workspace" style="width:min(660px,calc(100vw - 24px))" @update:show="value => { if (!value) selectedProduct = null }">
      <template v-if="selectedProduct"><ProductCell :line="selectedProduct" /><div class="ow-product-metrics"><div><span>订购数量</span><strong>{{ selectedProduct.quantity }} {{ selectedProduct.unit }}</strong></div><div><span>已预留待发</span><strong>{{ data.managed ? selectedProduct.reserved : '未核实' }}</strong></div><div><span>已实际出货</span><strong>{{ selectedProduct.shipped ?? '未核实' }}</strong></div></div><p>单价 ¥{{ fmtPrice(Number(selectedProduct.unit_price)) }} · 小计 ¥{{ fmtMoney(selectedProduct.quantity * Number(selectedProduct.unit_price)) }}</p><p v-if="selectedProduct.remarks" class="ow-prewrap">{{ selectedProduct.remarks }}</p><p class="ow-table-note">本行生产计划 {{ selectedProduct.planned }} {{ selectedProduct.unit }}，不代表已经入库或预留。</p><div class="wf-dialog-footer"><n-button @click="openProduction">查看生产安排</n-button><n-button v-if="canEdit" type="primary" :disabled="busy" @click="openLineEditor(selectedProduct)">编辑商品明细</n-button></div></template>
    </n-modal>
    <ReservationDialog v-model:show="showReservation" :order-id="orderId" :line="selectedLine" :release="release" @saved="load" @busy="reservationBusy = $event" />
    <OrderLineEditor v-if="showLineEditor" :order-id="orderId" :line="selectedEdit" :can-delete="canDeleteLine" :allowed="canEdit" :refresh="load" @close="showLineEditor = false" @saved="showLineEditor = false; load()" @busy="lineBusy = $event" />
    <n-modal v-model:show="showBatchCode" preset="card" title="批量填写客户货号" class="customer-code-dialog" :mask-closable="!batchSaving" :closable="!batchSaving" :close-on-esc="!batchSaving" style="width:min(620px,calc(100vw - 24px))">
      <p class="cc-intro">为所选饰品明细连续编号，不影响商品、数量和生产安排。</p>
      <section class="cc-section" aria-label="选择编号明细">
        <div class="cc-section-head"><h3><span>01</span>选择明细</h3><small>已选 <b>{{ batchIds.length }}</b> / {{ customerCodeLines.length }} 项</small></div>
        <div class="cc-line-list">
          <n-checkbox-group v-model:value="batchIds" :disabled="batchSaving">
            <div v-for="line in customerCodeLines" :key="line.id" class="cc-line" :class="{ 'is-selected': batchIds.includes(line.id) }">
              <n-checkbox :value="line.id">
                <div class="cc-line-content">
                  <div class="cc-product"><strong>{{ line.product_name }}</strong><small>{{ line.product_id }} · 明细 #{{ line.id }}</small></div>
                  <div class="cc-current"><small>当前货号</small><span :class="{ 'is-empty': !line.customer_code }">{{ line.customer_code || '未填写' }}</span></div>
                </div>
              </n-checkbox>
            </div>
          </n-checkbox-group>
          <p v-if="!customerCodeLines.length" class="cc-empty">暂无可编号的饰品明细，配件不支持客户货号。</p>
        </div>
      </section>
      <section class="cc-section" aria-label="设置连续编号">
        <div class="cc-section-head"><h3><span>02</span>编号规则</h3><small>前缀 + 连续数字</small></div>
        <n-form label-placement="top" class="cc-fields" :show-feedback="false">
          <n-form-item label="前缀"><n-input v-model:value="batchPrefix" placeholder="如 KH-" :input-props="{ 'aria-label': '货号前缀' }" :disabled="batchSaving" /></n-form-item>
          <n-form-item label="起始号"><n-input-number v-model:value="batchStart" :input-props="{ 'aria-label': '起始号' }" :min="0" :precision="0" :show-button="false" :disabled="batchSaving" /></n-form-item>
          <n-form-item label="数字位数"><n-input-number v-model:value="batchPadding" :input-props="{ 'aria-label': '数字位数' }" :min="1" :max="6" :precision="0" :show-button="false" :disabled="batchSaving" /></n-form-item>
        </n-form>
        <p class="cc-example">例如：前缀 KH-，起始号 5，位数 3 → KH-005、KH-006…</p>
      </section>
      <div class="cc-notice"><span aria-hidden="true">!</span><p>按明细编号从小到大生成，不按勾选顺序；数字位数不足时补零。<strong>所选明细已有货号会被覆盖，未选明细不变。</strong></p></div>
      <template #footer>
        <div class="cc-footer"><span>将为 <b>{{ batchIds.length }}</b> 项明细生成货号</span><div><n-button :disabled="batchSaving" @click="showBatchCode = false">取消</n-button><n-button type="primary" :loading="batchSaving" :disabled="!canEdit || !batchIds.length" @click="saveBatchCode">生成并保存</n-button></div></div>
      </template>
    </n-modal>
    <n-modal v-model:show="showActivation" preset="card" title="核对历史并启用逐笔履约" :mask-closable="!activating" :closable="!activating" style="width:min(540px,calc(100vw - 24px))">
      <n-alert type="warning" class="wf-notice">启用后，订单只能通过真实出货单完成，不再使用旧“改为完成”按钮扣库。系统不会生成任何历史出货或调整库存。已有历史实发的订单请勿启用。</n-alert>
      <n-checkbox v-model:checked="activationChecked" :disabled="activating">已核实本单没有历史实发，可以从 0 开始记录</n-checkbox>
      <div class="wf-dialog-footer"><n-button :disabled="activating" @click="showActivation = false">返回</n-button><n-button type="primary" :loading="activating" :disabled="!activationChecked" @click="activate">确认启用</n-button></div>
    </n-modal>
  </div>
</template>
<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { NAlert, NButton, NCheckbox, NCheckboxGroup, NForm, NFormItem, NInput, NInputNumber, NModal, NPopconfirm, NSpin, NTable, useMessage } from 'naive-ui'
import OrderWorkspaceHeader from '@/components/fulfillment/OrderWorkspaceHeader.vue'
import OrderSection from '@/components/fulfillment/OrderSection.vue'
import OrderMaterials from '@/components/fulfillment/OrderMaterials.vue'
import ProductCell from '@/components/fulfillment/ProductCell.vue'
import ReservationDialog from '@/components/fulfillment/ReservationDialog.vue'
import ShipmentTable from '@/components/fulfillment/ShipmentTable.vue'
import { getFulfillment, activateFulfillment, listShipments } from '@/api/fulfillment'
import OrderCosts from '@/components/fulfillment/OrderCosts.vue'
import OrderLineEditor from '@/components/fulfillment/OrderLineEditor.vue'
import { getOrder, batchFillCustomerCode, deleteOrderItem } from '@/api/orders'
import { fmtMoney, fmtPrice } from '@/utils/ui'
const route = useRoute(), message = useMessage()
const router = useRouter()
const orderId = computed(() => String(route.params.id))
const data = ref(null), order = ref(null), shipments = ref([]), loading = ref(false), error = ref('')
const showReservation = ref(false), selectedLine = ref(null), release = ref(false)
const showActivation = ref(false), activating = ref(false), activationChecked = ref(false)
const canEdit = computed(() => !loading.value && !error.value && ['待生产', '生产中'].includes(data.value?.status))
const canDeleteLine = computed(() => canEdit.value && data.value.lines.length > 1)
const selectedEdit = ref(null), showLineEditor = ref(false), costBusy = ref(false), lineBusy = ref(false)
const showBatchCode = ref(false), batchIds = ref([]), batchPrefix = ref(''), batchStart = ref(1), batchPadding = ref(2), batchSaving = ref(false)
const customerCodeLines = computed(() => data.value?.lines.filter(line => line.product_type === 'jewelry') || [])
const reservationBusy = ref(false)
const deletingLineId = ref(null)
const busy = computed(() => activating.value || costBusy.value || lineBusy.value || batchSaving.value || reservationBusy.value || deletingLineId.value !== null)
const showMaterials = ref(false), selectedProduct = ref(null)
const orderTotal = computed(() => Number(order.value?.total_amount || 0) + Number(order.value?.packaging_cost || 0))
function openLineEditor(line = null) {
  if (!canEdit.value || busy.value) return
  selectedEdit.value = line
  selectedProduct.value = null
  showLineEditor.value = true
}
function openProduction() { if (!busy.value) router.push({ path: `/orders/${orderId.value}/production`, query: route.query }) }
async function removeLine(line) {
  if (busy.value || !canDeleteLine.value || !data.value.lines.some(item => item.id === line?.id)) return
  deletingLineId.value = line.id
  try {
    await deleteOrderItem(orderId.value, line.id)
    if (selectedProduct.value?.id === line.id) selectedProduct.value = null
    await load()
    message.success('商品明细已删除')
  } catch (_) { /* API interceptor displays failure. */ }
  finally { deletingLineId.value = null }
}
onBeforeRouteLeave(() => !busy.value)
onBeforeRouteUpdate(() => !busy.value)
let requestId = 0
async function load() {
  const request = ++requestId
  loading.value = true; error.value = ''
  try {
    const [summary, info, records] = await Promise.all([getFulfillment(orderId.value), getOrder(orderId.value), listShipments(orderId.value)])
    if (request !== requestId) return
    data.value = summary.data; order.value = info.data; shipments.value = records.data
    return true
  } catch (e) { if (request === requestId) error.value = e.response?.data?.detail || '加载失败'; return false }
  finally { if (request === requestId) loading.value = false }
}
function editReservation(line, releasing) {
  if (busy.value || loading.value || error.value || !data.value?.editable) return
  selectedLine.value = line; release.value = releasing; showReservation.value = true
}
async function saveBatchCode() {
  if (batchSaving.value || !canEdit.value) return
  if (!batchIds.value.length || !batchPrefix.value.trim() || !Number.isInteger(batchStart.value) || !Number.isInteger(batchPadding.value)) return message.warning('请选择明细并填写前缀和编号')
  batchSaving.value = true
  try { await batchFillCustomerCode(orderId.value, { item_ids: batchIds.value, prefix: batchPrefix.value.trim(), start_number: batchStart.value, padding: batchPadding.value }); showBatchCode.value = false; await load() }
  catch (_) { /* API interceptor displays failure. */ }
  finally { batchSaving.value = false }
}
async function activate() {
  if (activating.value || !activationChecked.value) return
  activating.value = true
  try { await activateFulfillment(orderId.value); showActivation.value = false; await load(); message.success('已启用逐笔履约，未修改库存') }
  catch (_) { /* API interceptor displays failure. */ }
  finally { activating.value = false }
}
watch(orderId, () => { data.value = null; order.value = null; batchIds.value = []; showBatchCode.value = false; showLineEditor.value = false; activationChecked.value = false; showActivation.value = false; showReservation.value = false; showMaterials.value = false; selectedProduct.value = null; load() }, { immediate: true })
</script>

<style scoped>
/* NModal teleports its card without this component's scoped attribute. */
:global(.customer-code-dialog) { max-height: calc(100dvh - 32px); }
:global(.customer-code-dialog .n-card-header) { padding-bottom: 8px; }
:global(.customer-code-dialog .n-card-content) { min-height: 0; overflow-y: auto; }
:global(.customer-code-dialog .n-card__footer) { border-top: 1px solid #ECEDEF; padding-top: 14px; }
.cc-intro { margin: 0 0 20px; color: #8B9096; font-size: 12px; line-height: 1.6; }
.cc-section + .cc-section { margin-top: 20px; }
.cc-section-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 10px; }
.cc-section-head h3 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 13px; font-weight: 600; color: #475569; }
.cc-section-head h3>span { color: #A1AAA5; font-size: 10px; font-weight: 500; }
.cc-section-head>small { color: #8B9096; font-size: 11px; }
.cc-section-head b, .cc-footer b { color: #1E7A5A; font-weight: 600; }
.cc-line-list { max-height: clamp(100px, 28dvh, 240px); overflow-y: auto; border: 1px solid #E7EAED; border-radius: 7px; }
.cc-line { padding: 10px 12px; background: #fff; }
.cc-line + .cc-line { border-top: 1px solid #F0F1F2; }
.cc-line.is-selected { background: #F0F8F4; }
.cc-line :deep(.n-checkbox) { width: 100%; align-items: center; }
.cc-line :deep(.n-checkbox__label) { flex: 1; min-width: 0; padding-right: 0; }
.cc-line-content { display: grid; grid-template-columns: minmax(0,1.5fr) minmax(0,1fr); gap: 8px 16px; align-items: center; }
.cc-product, .cc-current { min-width: 0; overflow-wrap: anywhere; }
.cc-product strong { display: block; color: #3D454B; font-size: 12px; font-weight: 600; line-height: 1.5; }
.cc-product small, .cc-current small { display: block; color: #8B9096; font-size: 10px; line-height: 1.5; }
.cc-product small { margin-top: 3px; }
.cc-current { text-align: right; }
.cc-current>span { display: block; color: #475569; font-size: 12px; line-height: 1.5; }
.cc-current>span.is-empty { color: #A0A8AF; }
.cc-empty { margin: 0; padding: 24px 12px; text-align: center; color: #8B9096; font-size: 12px; }
.cc-fields { display: grid; grid-template-columns: minmax(0,1.4fr) repeat(2,minmax(0,1fr)); gap: 12px; }
.cc-fields :deep(.n-form-item), .cc-fields :deep(.n-input-number) { min-width: 0; width: 100%; }
.cc-fields :deep(.n-form-item-label) { color: #7C858C; font-size: 11px; padding-bottom: 6px; }
.cc-example { margin: 8px 0 0; color: #8B9096; font-size: 11px; line-height: 1.7; }
.cc-notice { display: flex; gap: 8px; margin-top: 18px; padding: 10px 12px; background: #FCF8EF; border-radius: 6px; font-size: 11px; color: #9A753C; }
.cc-notice>span { flex-shrink: 0; display: grid; place-items: center; width: 14px; height: 14px; margin-top: 2px; border: 1px solid #C7AB7D; border-radius: 50%; font-size: 10px; }
.cc-notice p { margin: 0; line-height: 1.7; }
.cc-notice strong { display: block; font-weight: 500; }
.cc-footer { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
.cc-footer>span { color: #8B9096; font-size: 11px; }
.cc-footer>div { display: flex; gap: 8px; margin-left: auto; }
@media (max-width: 600px) {
  .cc-intro { margin-bottom: 16px; }
  .cc-fields { gap: 8px; }
  .cc-line { padding: 9px 10px; }
  .cc-line-content { grid-template-columns: minmax(0,1.3fr) minmax(0,1fr); gap: 8px; }
  .cc-current>span { font-size: 11px; }
}
</style>
