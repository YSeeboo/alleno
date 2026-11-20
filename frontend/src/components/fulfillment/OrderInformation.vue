<template>
  <OrderSection title="基本信息">
    <template #header-extra><n-button v-if="editable" text type="primary" @click="openInfo">编辑资料</n-button></template>
    <div class="ow-information-grid ow-panel">
      <dl><dt>订单编号</dt><dd>{{ order.id }}</dd></dl><dl><dt>客户名称</dt><dd>{{ order.customer_name }}</dd></dl><dl><dt>创建时间</dt><dd>{{ order.created_at ? new Date(order.created_at).toLocaleString('zh-CN') : '—' }}</dd></dl>
      <dl><dt>订单状态</dt><dd>{{ order.status }}</dd></dl><dl><dt>订单金额（含包装费）</dt><dd class="wf-green">¥{{ fmtMoney(Number(order.total_amount || 0) + Number(order.packaging_cost || 0)) }}</dd></dl><dl><dt>资料说明</dt><dd>资料修改不改变生产、库存或出货</dd></dl>
      <div class="ow-information-note"><slot /></div>
    </div>
  </OrderSection>
  <OrderSection title="订单要求"><template #header-extra><n-button v-if="editable" text type="primary" @click="openRequirements">编辑订单要求</n-button></template>
    <div class="ow-panel ow-requirements">
      <div v-for="entry in requirementFields.filter(field => field.image)" :key="entry.key" class="ow-requirement-row"><div><div class="wf-actions"><h4>{{ entry.label }}</h4><span v-if="entry.key === 'barcode_text'" class="ow-count">{{ order.has_barcode ? '需要贴条码' : '无需条码' }}</span></div><p class="ow-prewrap">{{ order[entry.key] || '未填写' }}</p></div><n-image v-if="order[entry.image]" :src="order[entry.image]" :alt="`${entry.label}参考图`" width="112" height="86" object-fit="contain" /></div>
    </div>
  </OrderSection>
  <OrderSection title="订单备注"><template #header-extra><n-button v-if="editable" text type="primary" @click="openRequirements">编辑备注</n-button></template><div class="ow-panel ow-order-note ow-prewrap">{{ order.note || '未填写订单备注' }}</div></OrderSection>
  <p class="ow-table-note">本页集中维护订单资料与要求；商品数量和价格在「商品详情」中管理，制作计划在「生产安排」中管理。</p>
  <n-modal v-model:show="showRequirements" preset="card" title="编辑订单要求" :mask-closable="!saving" :closable="!saving" :close-on-esc="!saving" style="width:min(720px,calc(100vw - 24px))">
    <n-checkbox v-model:checked="requirements.has_barcode" :disabled="!editable || saving">需要贴条码</n-checkbox>
    <div v-for="entry in requirementFields" :key="entry.key" class="requirement-row">
      <label class="requirement-text">{{ entry.label }}<n-input v-model:value="requirements[entry.key]" type="textarea" :rows="3" :disabled="!editable || saving" /></label>
      <div v-if="entry.image" class="requirement-image">
        <n-image v-if="requirements[entry.image]" :src="requirements[entry.image]" width="90" height="75" object-fit="cover" />
        <n-button v-if="editable" size="small" :disabled="saving" @click="imageField = entry.image; showUpload = true">{{ requirements[entry.image] ? '更换图片' : '上传图片' }}</n-button>
        <n-button v-if="editable && requirements[entry.image]" text size="small" :disabled="saving" @click="requirements[entry.image] = null">移除图片</n-button>
      </div>
    </div>
    <n-button v-if="editable" type="primary" :loading="saving" @click="saveRequirements">保存订单要求</n-button>
  </n-modal>
  <n-modal v-model:show="showInfo" preset="card" title="编辑订单资料" :mask-closable="!saving" :closable="!saving" :close-on-esc="!saving" style="width:min(520px,calc(100vw - 24px))">
    <n-form label-placement="top"><n-form-item label="客户名"><n-input v-model:value="info.customer_name" :disabled="saving" /></n-form-item><n-form-item label="创建日期"><n-date-picker v-model:value="info.date" type="date" :disabled="saving" /></n-form-item></n-form>
    <div class="wf-dialog-footer"><n-button :disabled="saving" @click="showInfo = false">取消</n-button><n-button type="primary" :loading="saving" @click="saveInfo">保存资料</n-button></div>
  </n-modal>
  <ImageUploadModal v-model:show="showUpload" kind="order" :entity-id="order.id" suppress-success @uploaded="url => requirements[imageField] = url" />
</template>
<script setup>
import { reactive, ref, watch } from 'vue'
import { NButton, NCheckbox, NDatePicker, NForm, NFormItem, NImage, NInput, NModal, useMessage } from 'naive-ui'
import OrderSection from '@/components/fulfillment/OrderSection.vue'
import ImageUploadModal from '@/components/ImageUploadModal.vue'
import { updateExtraInfo } from '@/api/orders'
import { isoToTs, tsToDateStr } from '@/utils/date'
import { fmtMoney } from '@/utils/ui'
const props = defineProps({ order: { type: Object, required: true }, editable: Boolean })
const emit = defineEmits(['saved', 'busy'])
const message = useMessage()
const requirements = reactive({}), info = reactive({}), saving = ref(false), showInfo = ref(false), showUpload = ref(false), imageField = ref('')
const requirementFields = [{ key: 'barcode_text', label: '条码要求', image: 'barcode_image' }, { key: 'mark_text', label: '唛头要求', image: 'mark_image' }, { key: 'note', label: '订单备注' }]
const showRequirements = ref(false)
function openRequirements() {
  if (!props.editable || saving.value) return
  for (const key of ['has_barcode', 'barcode_text', 'barcode_image', 'mark_text', 'mark_image', 'note']) requirements[key] = props.order[key]
  showRequirements.value = true
}
watch(() => props.order, value => {
  for (const key of ['has_barcode', 'barcode_text', 'barcode_image', 'mark_text', 'mark_image', 'note']) requirements[key] = value[key]
}, { immediate: true })
function openInfo() { Object.assign(info, { customer_name: props.order.customer_name, date: isoToTs(props.order.created_at) }); showInfo.value = true }
async function persist(values) {
  if (saving.value || !props.editable) return
  saving.value = true; emit('busy', true)
  try { await updateExtraInfo(props.order.id, values); showInfo.value = false; showRequirements.value = false; emit('saved'); message.success('订单资料已保存') }
  catch (_) { /* Interceptor displays API errors. */ }
  finally { saving.value = false; emit('busy', false) }
}
function saveInfo() {
  const name = info.customer_name?.trim(), date = tsToDateStr(info.date)
  if (!name || !date) return message.warning('请填写客户名与创建日期')
  return persist({ customer_name: name, created_at: date })
}
function saveRequirements() { return persist({ ...requirements }) }
</script>
<style scoped>
.requirement-row { display:flex; gap:16px; margin:16px 0; }
.requirement-text { flex:1; min-width:0; display:grid; gap:8px; }
.requirement-image { width:100px; display:flex; flex-direction:column; gap:8px; }
@media(max-width:540px) { .requirement-row { flex-wrap:wrap; } .requirement-text { flex-basis:100%; } }
</style>
