<template>
  <n-modal :show="true" preset="card" :title="line ? '编辑商品明细' : '添加商品'" :mask-closable="!saving" :closable="!saving" :close-on-esc="!saving" style="width:min(560px,calc(100vw - 24px))" @update:show="value => { if (!value) emit('close') }">
    <n-alert type="info" :bordered="false" class="wf-notice">{{ line ? `保留明细 #${line.id} 的商品身份；数量变更会核对生产安排、预留和出货凭据。` : '同款商品也新增独立行，不合并原有客户货号或生产份额。' }}</n-alert>
    <n-alert v-if="loadError" type="error">{{ loadError }} <n-button text @click="loadProducts">重试</n-button></n-alert>
    <n-form label-placement="top">
      <template v-if="!line"><n-form-item label="商品类型"><n-select v-model:value="kind" :options="[{ label:'饰品', value:'jewelry' }, { label:'配件', value:'part' }]" :disabled="saving" @update:value="values.product_id = null" /></n-form-item><n-form-item label="商品"><n-select v-model:value="values.product_id" :options="options" :render-label="renderOptionWithImage" filterable :loading="loading" :disabled="saving" @update:value="setPrice" /></n-form-item></template>
      <n-form-item label="订购数量"><n-input-number v-model:value="values.quantity" :min="1" :precision="0" :disabled="saving" /></n-form-item>
      <n-form-item label="单价（最多 7 位小数）"><n-input-number v-model:value="values.unit_price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" :disabled="saving" /></n-form-item>
      <n-form-item v-if="kind === 'jewelry'" label="客户货号"><n-input v-model:value="values.customer_code" :disabled="saving" /></n-form-item>
      <n-form-item label="备注"><n-input v-model:value="values.remarks" type="textarea" :disabled="saving" /></n-form-item>
    </n-form>
    <div class="wf-dialog-footer"><n-popconfirm v-if="line && canDelete" @positive-click="remove"><template #trigger><n-button type="error" ghost :disabled="saving">删除明细</n-button></template>仅无业务关联的明细可删除，确定继续？</n-popconfirm><n-button :disabled="saving" @click="emit('close')">取消</n-button><n-button type="primary" :loading="saving" :disabled="loading || !!loadError" @click="save">保存明细</n-button></div>
  </n-modal>
</template>
<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import { NAlert, NButton, NForm, NFormItem, NInput, NInputNumber, NModal, NPopconfirm, NSelect, useMessage } from 'naive-ui'
import { addOrderItem, deleteOrderItem, updateOrderItem } from '@/api/orders'
import { listParts } from '@/api/parts'
import { listJewelries } from '@/api/jewelries'
import { fmtPrice, parseNum, renderOptionWithImage } from '@/utils/ui'
const props = defineProps({ orderId: String, line: Object, canDelete: Boolean })
const emit = defineEmits(['close', 'saved', 'busy']), message = useMessage()
const saving = ref(false), loading = ref(false), loadError = ref(''), products = ref({ jewelry: [], part: [] })
const kind = ref(props.line?.product_type || 'jewelry')
const values = reactive({ quantity: props.line?.quantity ?? 1, unit_price: props.line ? Number(props.line.unit_price) : 0, customer_code: props.line?.customer_code || '', remarks: props.line?.remarks || '', product_id: null })
const options = computed(() => products.value[kind.value].map(p => ({ value:p.id, label:`${p.id} ${p.name}`, code:p.id, name:p.name, image:p.image })))
async function loadProducts() {
  if (props.line) return
  loading.value = true; loadError.value = ''
  try { const [j, p] = await Promise.all([listJewelries(), listParts({})]); products.value = { jewelry:j.data.filter(row => row.status === 'active'), part:p.data } }
  catch (_) { loadError.value = '商品资料加载失败' }
  finally { loading.value = false }
}
function setPrice(id) { values.unit_price = Number(products.value[kind.value].find(p => p.id === id)?.wholesale_price || 0) }
async function mutate(action) {
  if (saving.value) return
  saving.value = true; emit('busy', true)
  try { await action(); emit('saved'); message.success('商品明细已保存') }
  catch (_) { /* API interceptor displays failure. */ }
  finally { saving.value = false; emit('busy', false) }
}
function save() {
  if (saving.value || loading.value || loadError.value) return
  if (!Number.isInteger(values.quantity) || values.quantity <= 0 || values.unit_price == null || !Number.isFinite(values.unit_price) || values.unit_price < 0) return message.warning('请填写有效数量和单价')
  const fields = { quantity: values.quantity, unit_price: values.unit_price, remarks: values.remarks }
  if (kind.value === 'jewelry') fields.customer_code = values.customer_code || null
  if (props.line) return mutate(() => updateOrderItem(props.orderId, props.line.id, fields))
  if (!values.product_id) return message.warning('请选择商品')
  fields[kind.value === 'jewelry' ? 'jewelry_id' : 'part_id'] = values.product_id
  return mutate(() => addOrderItem(props.orderId, fields))
}
function remove() {
  if (!props.line || !props.canDelete) return
  return mutate(() => deleteOrderItem(props.orderId, props.line.id))
}
onMounted(loadProducts)
</script>
