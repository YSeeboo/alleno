<template>
  <div class="fulfillment-page order-management">
    <div class="page-breadcrumb">生产 / <router-link to="/orders">订单管理</router-link> / 新建订单</div>
    <header class="om-head"><div><div class="om-title-line"><h2 class="page-title">新建订单</h2><span class="om-draft-tag">尚未创建</span></div><p class="om-description">录入客户与订购商品，创建后再安排制作或直接现货出货。</p></div><div class="om-actions"><n-button quaternary :disabled="submitting" @click="router.push('/orders')">← 返回列表</n-button><n-button type="primary" :loading="submitting" :disabled="editingDisabled" @click="submit">创建订单</n-button></div></header>
    <n-alert v-if="catalogError" type="error" class="wf-notice">{{ catalogError }} <n-button text type="primary" :disabled="catalogLoading" @click="loadCatalog">重新加载商品</n-button></n-alert>
    <n-alert v-if="submitError" type="error" class="wf-notice" role="alert">{{ submitError }}</n-alert>
    <n-spin :show="catalogLoading">
      <div class="om-create-layout">
        <div class="om-create-fields">
          <section class="om-section"><header class="om-section-head"><div><span class="om-section-number">01</span><h3>基本资料</h3></div><span class="om-muted">* 必填项</span></header>
            <div class="om-panel om-basic-panel"><n-form label-placement="top" :disabled="submitting" @submit.prevent="submit"><div class="om-basic-grid"><n-form-item label="客户名称" required><n-input v-model:value="customerName" placeholder="请输入客户名称" :input-props="{ 'aria-label': '客户名称' }" /></n-form-item><n-form-item label="创建日期"><div class="om-date-field"><n-date-picker v-model:value="createdAtTs" type="date" clearable placeholder="不填则使用当前时间" /><small class="om-subtext">留空则使用创建当天日期</small></div></n-form-item></div><div class="om-barcode-setting"><n-checkbox v-model:checked="hasBarcode">需要贴条码</n-checkbox><p>条码内容、唛头与参考图片可在创建后的「订单信息」中补充。</p></div></n-form></div>
          </section>
          <OrderCreateLines kind="jewelry" :items="jewelryItems" :options="jewelryOptions" :catalog="jewelryMap" :subtotal="totals.groups.jewelry" :disabled="editingDisabled" @add="addJewelryLine" @select="onJewelrySelect" @remove="key => removeLine(jewelryItems, key)" />
          <OrderCreateLines kind="part" :items="partItems" :options="partOptions" :catalog="partMap" :subtotal="totals.groups.part" :disabled="editingDisabled" @add="addPartLine" @select="onPartSelect" @remove="key => removeLine(partItems, key)" />
          <p class="om-table-note">同款商品可添加多行，各行独立保存；单价最多支持 7 位小数，数量按商品单位分别统计。明细表格可横向滚动。</p>
        </div>
        <aside class="om-create-summary" aria-label="订单汇总"><header><h3>本次订单</h3><span class="om-draft-tag">待创建</span></header><div class="om-summary-body">
          <dl class="om-summary-customer"><dt>客户</dt><dd>{{ customerName || '待填写客户名称' }}</dd></dl>
          <div class="om-summary-lines"><div><span>饰品 <small>{{ jewelryItems.length }} 项</small></span><strong>¥{{ formatOrderAmount(totals.groups.jewelry) }}</strong></div><div><span>配件 <small>{{ partItems.length }} 项</small></span><strong>¥{{ formatOrderAmount(totals.groups.part) }}</strong></div></div>
          <div class="om-grand-total"><span>商品合计</span><strong>{{ totals.invalid ? '待完善明细' : `¥${formatOrderAmount(totals.total)}` }}</strong><small>不含后续包装费用</small></div>
          <div class="om-summary-units"><span>订购数量</span><strong>{{ totals.units || '—' }}</strong><small>不同单位不混加</small></div>
          <p class="om-summary-notice">{{ totals.invalid ? '存在未选择的商品或无效数字；当前小计仅汇总有效明细，不能提交。' : '创建订单不扣料、不预留、不出货。' }}</p>
          <div class="om-next-steps"><h4>创建之后</h4><p><span>01</span>每条商品保留独立明细身份</p><p><span>02</span>按需安排制作，或直接使用现货</p><p><span>03</span>预留与实际出货分别记录</p></div>
        </div></aside>
      </div>
    </n-spin>
  </div>
</template>
<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter, onBeforeRouteLeave } from 'vue-router'
import { NAlert, NButton, NCheckbox, NDatePicker, NForm, NFormItem, NInput, NSpin, useMessage } from 'naive-ui'
import { listJewelries } from '@/api/jewelries'
import { listParts } from '@/api/parts'
import { createOrder } from '@/api/orders'
import { tsToDateStr } from '@/utils/date'
import { orderLineAmount, orderDraftTotals, formatOrderAmount } from '@/utils/orderManagement'
import OrderCreateLines from '@/components/fulfillment/OrderCreateLines.vue'
import '@/styles/order-management.css'

const router = useRouter(), message = useMessage()
const customerName = ref(''), createdAtTs = ref(null), hasBarcode = ref(false)
const jewelryItems = reactive([]), partItems = reactive([])
const submitting = ref(false), catalogLoading = ref(false), catalogError = ref(''), submitError = ref('')
const jewelryMap = ref({}), jewelryOptions = ref([]), partMap = ref({}), partOptions = ref([])
let nextKey = 1, navigatingAfterCreate = false
const editingDisabled = computed(() => submitting.value || catalogLoading.value || Boolean(catalogError.value))
const totals = computed(() => orderDraftTotals(jewelryItems, partItems, jewelryMap.value, partMap.value))
watch([customerName, createdAtTs, hasBarcode, jewelryItems, partItems], () => { submitError.value = '' }, { deep: true })
function addJewelryLine() { if (!editingDisabled.value) jewelryItems.push({ key: nextKey++, jewelry_id: null, quantity: 1, unit_price: 0, remarks: '' }) }
function addPartLine() { if (!editingDisabled.value) partItems.push({ key: nextKey++, part_id: null, quantity: 1, unit_price: 0, remarks: '' }) }
function removeLine(items, key) { if (!editingDisabled.value) { const index = items.findIndex(item => item.key === key); if (index >= 0) items.splice(index, 1) } }
function onJewelrySelect(item, id) { if (!editingDisabled.value) item.unit_price = jewelryMap.value[id]?.wholesale_price ?? 0 }
function onPartSelect(item, id) { if (!editingDisabled.value) item.unit_price = partMap.value[id]?.wholesale_price ?? 0 }
async function submit() {
  if (editingDisabled.value) return
  submitError.value = ''
  try {
    if (!customerName.value.trim()) throw Error('请输入客户名称')
    if (!jewelryItems.length && !partItems.length) throw Error('请添加订单明细')
    if (jewelryItems.some(item => !jewelryMap.value[item.jewelry_id])) throw Error('请选择饰品')
    if (partItems.some(item => !partMap.value[item.part_id])) throw Error('请选择配件')
    for (const item of [...jewelryItems, ...partItems]) orderLineAmount(item)
    if (createdAtTs.value != null && !Number.isFinite(createdAtTs.value)) throw Error('请填写有效创建日期')
  } catch (e) { submitError.value = e.message; message.warning(e.message); return }
  const items = [
    ...jewelryItems.map(item => ({ jewelry_id: item.jewelry_id, quantity: item.quantity, unit_price: item.unit_price, remarks: item.remarks })),
    ...partItems.map(item => ({ part_id: item.part_id, quantity: item.quantity, unit_price: item.unit_price, remarks: item.remarks })),
  ]
  submitting.value = true
  try {
    const payload = { customer_name: customerName.value, items, has_barcode: hasBarcode.value }
    const createdAt = tsToDateStr(createdAtTs.value)
    if (createdAt) payload.created_at = createdAt
    const { data } = await createOrder(payload)
    message.success('订单创建成功')
    navigatingAfterCreate = true
    await router.push(`/orders/${data.id}`)
  } catch (e) { submitError.value = e.response?.data?.detail || '创建失败，请检查后重试；表单内容已保留。' }
  finally { submitting.value = false; navigatingAfterCreate = false }
}
async function loadCatalog() {
  if (catalogLoading.value || submitting.value) return
  catalogLoading.value = true; catalogError.value = ''
  try {
    const [{ data: jData }, { data: pData }] = await Promise.all([listJewelries({ status: 'active' }), listParts({})])
    jewelryMap.value = Object.fromEntries(jData.map(item => [item.id, item]))
    partMap.value = Object.fromEntries(pData.map(item => [item.id, item]))
    const option = item => ({ label: `${item.id} ${item.name}`, value: item.id, code: item.id, name: item.name, image: item.image })
    jewelryOptions.value = jData.map(option); partOptions.value = pData.map(option)
  } catch { catalogError.value = '商品加载失败，暂不能创建订单。请重新加载，已填内容不会清空。' }
  finally { catalogLoading.value = false }
}
onBeforeRouteLeave(() => !submitting.value || navigatingAfterCreate)
onMounted(loadCatalog)
</script>
