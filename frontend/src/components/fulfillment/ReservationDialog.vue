<template>
  <n-modal :show="show" preset="card" :title="release ? '取消预留' : '预留库存'" :mask-closable="!saving" :closable="!saving" style="width:min(500px,calc(100vw - 24px))" @update:show="$emit('update:show', $event)">
    <div v-if="line" class="wf-dialog">
      <n-alert type="info" :bordered="false" class="wf-notice">{{ release ? '只释放待发预留，恢复公共可用量。不改变实物库存、生产安排或已出货。' : '从公共可用库存中为当前明细留货，不代表出货，也不改变实物总量。' }}</n-alert>
      <ProductCell :line="line" />
      <p style="margin:16px 0">本行待发 {{ line.remaining }} · 已预留 {{ line.reserved }} · 公共可用 {{ line.public_available }} {{ line.unit }}</p>
      <div class="wf-field"><label for="reservation-quantity">{{ release ? '本次取消数量' : '本次新增预留' }}</label><n-input-number v-model:value="quantity" :input-props="{ id: 'reservation-quantity' }" :min="1" :precision="0" :disabled="saving" placeholder="填写实际数量" /></div>
      <p v-if="error" role="alert" class="wf-amber">{{ error }}</p>
      <div class="wf-dialog-footer"><n-button :disabled="saving" @click="$emit('update:show', false)">取消</n-button><n-button type="primary" :loading="saving" :disabled="!quantity" @click="save">{{ release ? '确认取消预留' : '确认预留' }}</n-button></div>
    </div>
  </n-modal>
</template>
<script setup>
import { ref, watch } from 'vue'
import { NAlert, NButton, NModal, NInputNumber } from 'naive-ui'
import { updateReservation } from '@/api/fulfillment'
import ProductCell from './ProductCell.vue'
const props = defineProps({ show: Boolean, orderId: String, line: Object, release: Boolean })
const emit = defineEmits(['update:show', 'saved', 'busy'])
const quantity = ref(null), saving = ref(false), error = ref('')
watch(() => props.show, () => { quantity.value = null; error.value = '' })
async function save() {
  if (saving.value || !Number.isSafeInteger(quantity.value) || quantity.value <= 0) return
  const target = Number(props.line.reserved) + (props.release ? -quantity.value : quantity.value)
  if (target < 0) { error.value = '取消数量不能超过本行预留'; return }
  saving.value = true; emit('busy', true)
  try {
    await updateReservation(props.orderId, props.line.id, { quantity: target, expected_quantity: props.line.reserved })
    emit('update:show', false); emit('saved')
  } catch (e) { error.value = e.response?.data?.detail || '保存失败' }
  finally { saving.value = false; emit('busy', false) }
}
</script>
