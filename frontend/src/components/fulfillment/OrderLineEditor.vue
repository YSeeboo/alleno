<template>
  <BatchAddDialog v-if="!line" scene="order" :entity-id="orderId" :allowed="allowed" :refresh="refresh" @close="emit('close')" @saved="emit('saved')" @busy="emit('busy', $event)" />
  <n-modal v-else :show="true" preset="card" title="编辑商品明细" :mask-closable="!saving" :closable="!saving" :close-on-esc="!saving" style="width:min(560px,calc(100vw - 24px))" @update:show="value => { if (!value) emit('close') }">
    <n-alert type="info" :bordered="false" class="wf-notice">保留明细 #{{ line.id }} 的商品身份；数量变更会核对生产安排、预留和出货凭据。</n-alert>
    <n-form label-placement="top">
      <n-form-item label="订购数量"><n-input-number v-model:value="values.quantity" :min="1" :precision="0" :disabled="saving" /></n-form-item>
      <n-form-item label="单价（最多 7 位小数）"><n-input-number v-model:value="values.unit_price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" :disabled="saving" /></n-form-item>
      <n-form-item v-if="kind === 'jewelry'" label="客户货号"><n-input v-model:value="values.customer_code" :disabled="saving" /></n-form-item>
      <n-form-item label="备注"><n-input v-model:value="values.remarks" type="textarea" :disabled="saving" /></n-form-item>
    </n-form>
    <div class="wf-dialog-footer"><n-popconfirm v-if="canDelete" @positive-click="remove"><template #trigger><n-button type="error" ghost :disabled="saving">删除明细</n-button></template>仅无业务关联的明细可删除，确定继续？</n-popconfirm><n-button :disabled="saving" @click="emit('close')">取消</n-button><n-button type="primary" :loading="saving" :disabled="!allowed" @click="save">保存明细</n-button></div>
  </n-modal>
</template>
<script setup>
import { reactive, ref } from 'vue'
import { NAlert, NButton, NForm, NFormItem, NInput, NInputNumber, NModal, NPopconfirm, useMessage } from 'naive-ui'
import { deleteOrderItem, updateOrderItem } from '@/api/orders'
import { fmtPrice, parseNum } from '@/utils/ui'
import BatchAddDialog from '@/components/BatchAddDialog.vue'
const props = defineProps({ orderId: String, line: Object, canDelete: Boolean, allowed: { type: Boolean, default: true }, refresh: Function })
const emit = defineEmits(['close', 'saved', 'busy']), message = useMessage()
const saving = ref(false)
const kind = ref(props.line?.product_type || 'jewelry')
const values = reactive({ quantity: props.line?.quantity ?? 1, unit_price: props.line ? Number(props.line.unit_price) : 0, customer_code: props.line?.customer_code || '', remarks: props.line?.remarks || '', product_id: null })
async function mutate(action) {
  if (saving.value) return
  saving.value = true; emit('busy', true)
  try { await action(); emit('saved'); message.success('商品明细已保存') }
  catch (_) { /* API interceptor displays failure. */ }
  finally { saving.value = false; emit('busy', false) }
}
function save() {
  if (saving.value || !props.line || props.allowed === false) return
  if (!Number.isInteger(values.quantity) || values.quantity <= 0 || values.unit_price == null || !Number.isFinite(values.unit_price) || values.unit_price < 0) return message.warning('请填写有效数量和单价')
  const fields = { quantity: values.quantity, unit_price: values.unit_price, remarks: values.remarks }
  if (kind.value === 'jewelry') fields.customer_code = values.customer_code || null
  return mutate(() => updateOrderItem(props.orderId, props.line.id, fields))
}
function remove() {
  if (!props.line || !props.canDelete) return
  return mutate(() => deleteOrderItem(props.orderId, props.line.id))
}
</script>
