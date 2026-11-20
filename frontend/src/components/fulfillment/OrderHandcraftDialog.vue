<template>
  <n-modal :show="true" preset="card" title="为此明细安排手工制作" :mask-closable="!blocked" :closable="!blocked" :close-on-esc="!blocked" style="width:min(760px, calc(100vw - 24px))" @update:show="!$event && !blocked && $emit('close')">
    <div class="fulfillment-page">
      <n-alert type="info" :bordered="false" class="wf-notice">{{ orderId }} · 明细 #{{ line.id }} · {{ line.customer_code || line.product_name }}<br>只安排此明细，不改同款其他行。保存只建立制作计划和数量用途，不发料、不预留、不入库、不计客户出货。</n-alert>
      <p v-if="loading" role="status">正在读取商品、商家与当前 BOM…</p>
      <n-alert v-if="error" type="error" class="wf-notice">{{ error }}</n-alert>
      <n-form label-placement="top" :disabled="fieldsLocked">
        <n-form-item label="手工商家"><n-auto-complete v-model:value="supplier" :options="supplierOptions" :disabled="fieldsLocked" placeholder="选择或输入商家名称" :input-props="{ 'aria-label': '手工商家' }" /></n-form-item>
        <p class="wf-muted">可输入新商家名称；制作计划保存成功时会同时加入手工商家名录，失败不会留下空商家。</p>
        <HandcraftTargetPicker v-model="targetId" :supplier-name="supplier" :disabled="fieldsLocked" />
        <div class="quantity-fields">
          <n-form-item :label="`整条产出计划（${line.unit}）`"><n-input-number v-model:value="planned" :min="1" :precision="0" :disabled="fieldsLocked" :input-props="{ 'aria-label': '整条产出计划' }" style="width:100%" /></n-form-item>
          <n-form-item :label="`安排给本行（${line.unit}）`"><n-input-number v-model:value="allocated" :min="1" :max="remaining" :precision="0" :disabled="fieldsLocked" :input-props="{ 'aria-label': '安排给本行' }" style="width:100%" /></n-form-item>
        </div>
        <p class="wf-muted">本行尚可安排 {{ remaining }} {{ line.unit }}；新产出的公共备库存计划 {{ Math.max(0, Number(planned) - Number(allocated)) || 0 }} {{ line.unit }}。公共计划仍不是现货。</p>
        <h3 style="margin:16px 0 8px">计划投入配件</h3>
        <p class="wf-muted">{{ bomNote }} 以下数量可手动核对修改；保存不会扣库。当前尚未保存独立 BOM 需求快照，也不会自动关联上游电镀。</p>
        <div class="wf-table-wrap"><n-table :bordered="false" class="wf-table"><thead><tr><th>材料</th><th>计划数量</th><th>单位</th><th>操作</th></tr></thead><tbody>
          <tr v-for="(row, index) in materials" :key="row.key"><td><n-select v-model:value="row.part_id" :options="partOptions" filterable :disabled="fieldsLocked" placeholder="请选择配件" :aria-label="`材料 ${index + 1}`" style="min-width:210px" @update:value="row.unit = parts.find(p => p.id === row.part_id)?.unit || ''" /></td><td><n-input-number v-model:value="row.qty" :min="0.0001" :step="0.0001" :precision="4" :disabled="fieldsLocked" :input-props="{ 'aria-label': `材料 ${index + 1} 数量` }" style="width:140px" /></td><td>{{ row.unit || '待核对' }}</td><td><n-button text type="error" :disabled="fieldsLocked" @click="materials.splice(index, 1)">移除</n-button></td></tr>
        </tbody></n-table></div>
        <n-button :disabled="fieldsLocked" style="margin:12px 0 16px" @click="addMaterial">＋ 添加计划材料</n-button>
        <n-form-item label="制作备注"><n-input v-model:value="note" type="textarea" :rows="2" :disabled="fieldsLocked" placeholder="制作备注" :input-props="{ 'aria-label': '制作备注' }" /></n-form-item>
      </n-form>
      <div class="wf-actions" style="justify-content:flex-end;margin-top:20px">
        <n-button :disabled="blocked" @click="$emit('close')">返回</n-button>
        <n-button v-if="loadError" :disabled="blocked" @click="load">重新加载材料</n-button>
        <n-button type="primary" :loading="saving" :disabled="loading || !!loadError" @click="save">{{ uncertain ? '重试核对此次结果（不重复创建）' : targetId ? '追加新增产出并安排本行' : '新建制作单并安排本行' }}</n-button>
      </div>
    </div>
  </n-modal>
</template>
<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { NAlert, NAutoComplete, NButton, NForm, NFormItem, NInput, NInputNumber, NModal, NSelect, NTable } from 'naive-ui'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { listParts, getPartBom } from '@/api/parts'
import { listSuppliers } from '@/api/suppliers'
import { getBom } from '@/api/bom'
import { createOrderHandcraft } from '@/api/productionAllocation'
import { orderHandcraftPayload } from '@/utils/orderProductionCreation'
import HandcraftTargetPicker from './HandcraftTargetPicker.vue'

const props = defineProps({ orderId: { type: String, required: true }, line: { type: Object, required: true } })
const emit = defineEmits(['close', 'saved'])
const supplier = ref(''), suppliers = ref([]), parts = ref([])
const supplierOptions = computed(() => suppliers.value.map(s => s.name).filter(name => name.includes(supplier.value || '')))
const partOptions = computed(() => parts.value.map(part => ({ value: part.id, label: `${part.id} · ${part.name}` })))
const targetId = ref(null), planned = ref(1), allocated = ref(1), materials = ref([]), note = ref('')
const saving = ref(false), loading = ref(true), loadError = ref(''), error = ref(''), uncertain = ref(false), bomNote = ref('')
const remaining = computed(() => Math.max(0, Number(props.line.quantity) - Number(props.line.allocated)))
const blocked = computed(() => saving.value || uncertain.value)
const fieldsLocked = computed(() => blocked.value || loading.value || !!loadError.value)
onBeforeRouteLeave(() => !blocked.value)
onBeforeRouteUpdate(() => !blocked.value)
function beforeUnload(event) {
  if (blocked.value) { event.preventDefault(); event.returnValue = '' }
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
let materialKey = 0, attempt = null
function addMaterial() { materials.value.push({ key: ++materialKey, part_id: null, qty: null, unit: '' }) }
async function load() {
  loading.value = true; loadError.value = ''; error.value = ''
  try {
    const [p, s] = await Promise.all([listParts(), listSuppliers({ type: 'handcraft' })])
    parts.value = p.data; suppliers.value = s.data
    try {
      const { data } = await (props.line.product_type === 'jewelry' ? getBom(props.line.product_id) : getPartBom(props.line.product_id))
      materials.value = data.map(row => {
        const part = parts.value.find(p => p.id === (row.part_id || row.child_part_id))
        return { key: ++materialKey, part_id: part?.id || row.part_id || row.child_part_id, qty: Math.round(Number(row.qty_per_unit) * Number(planned.value) * 10000) / 10000, unit: part?.unit || '' }
      })
      bomNote.value = data.length ? '以下为打开页面时的 BOM × 整条产出计划；修改产出数量后请重新核对材料，不自动覆盖手填值。' : '该商品暂无 BOM，请手动填写计划投入材料。'
    } catch (_) { bomNote.value = 'BOM 读取失败，请手动核对材料；不能把空白当作无需用料。' }
    if (!materials.value.length) addMaterial()
  } catch (e) { loadError.value = '商品或商家加载失败，请重试'; error.value = loadError.value }
  finally { loading.value = false }
}
async function save() {
  if (saving.value || loading.value || loadError.value) return
  error.value = ''
  try {
    if (!attempt) {
      attempt = orderHandcraftPayload({ line: props.line, supplier: supplier.value, planned: planned.value,
        allocated: allocated.value, materials: materials.value, targetId: targetId.value,
        note: note.value, requestKey: crypto.randomUUID() })
    }
    saving.value = true
    const { data } = await createOrderHandcraft(props.orderId, attempt)
    uncertain.value = false
    emit('saved', data)
  } catch (e) {
    // Keep the exact payload/key on uncertain network/server outcomes. Retrying
    // checks the persisted receipt instead of creating another task/append.
    uncertain.value = !!attempt && (!e.response || e.response.status >= 500)
    if (!uncertain.value) attempt = null
    error.value = e.response?.data?.detail || e.message || '保存失败'
    if (uncertain.value) error.value += '；结果尚不确定，请重试核对此次结果，不要另建制作单。'
  } finally { saving.value = false }
}
onMounted(() => { planned.value = allocated.value = remaining.value || 1; load() })
</script>
<style scoped>
.quantity-fields { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
@media (max-width:540px) { .quantity-fields { grid-template-columns:1fr; gap:0; } }
</style>
