<template>
  <n-modal :show="true" preset="card" title="批量安排手工制作" :mask-closable="!blocked" :closable="!blocked" :close-on-esc="!blocked" style="width:min(1020px,calc(100vw - 24px))" @update:show="!$event && !blocked && $emit('close')">
    <div class="fulfillment-page">
      <n-alert type="info" :bordered="false" class="wf-notice">{{ orderId }} · {{ rows.length }} 条明细，同一商家新建到一张手工单，或明确追加到已有单。各行产出独立，不合并同款行；保存不发料、不预留、不入库、不记出货。</n-alert>
      <n-alert v-if="error" type="error" class="wf-notice">{{ error }}</n-alert>
      <p v-if="loading" role="status">正在读取商家、材料与各商品 BOM…</p>
      <n-form label-placement="top" :disabled="fieldsLocked">
        <n-form-item label="统一手工商家"><n-auto-complete v-model:value="supplier" :options="supplierOptions" :disabled="fieldsLocked" placeholder="选择或输入商家" :input-props="{ 'aria-label': '统一手工商家' }" /></n-form-item>
        <HandcraftTargetPicker v-model="targetId" :supplier-name="supplier" :disabled="fieldsLocked" />
        <div class="wf-table-wrap"><n-table :bordered="false" class="wf-table"><thead><tr><th>商品 / 客户货号</th><th>未安排</th><th>整条制作数量</th><th>其中本单份额</th></tr></thead><tbody>
          <tr v-for="row in rows" :key="row.line.id"><td><ProductCell :line="row.line" /></td><td>{{ remaining(row.line) }} {{ row.line.unit }}</td><td><n-input-number v-model:value="row.planned" :min="1" :max="999999999" :precision="0" :disabled="fieldsLocked" :input-props="{ 'aria-label': `明细 ${row.line.id} 整条制作数量` }" style="width:150px" /></td><td><n-input-number v-model:value="row.allocated" :min="1" :max="remaining(row.line)" :precision="0" :disabled="fieldsLocked" :input-props="{ 'aria-label': `明细 ${row.line.id} 本单份额` }" style="width:150px" /></td></tr>
        </tbody></n-table></div>
        <p class="wf-muted">默认值仅参考「订购 − 已有生产份额」，不是尚待备货量。改制作数量后请重新核对材料，不自动覆盖手填值。</p>
        <n-alert v-if="hasLegacy" type="warning" class="wf-notice">所选商品有旧批次参考，未自动计入新安排。请先核对历史加工及现有库存，再填写实际仍需制作量。<br><n-checkbox v-model:checked="reviewed" :disabled="fieldsLocked">我已核对旧加工记录和现有库存</n-checkbox></n-alert>
        <h3>逐行核对计划材料</h3>
        <n-collapse :default-expanded-names="rows.map(r => r.line.id)">
          <n-collapse-item v-for="row in rows" :key="row.line.id" :name="row.line.id" :title="`${row.line.customer_code || row.line.product_name} · 明细 #${row.line.id}`">
            <p class="wf-muted">{{ row.bomNote }}</p>
            <div class="wf-table-wrap"><n-table :bordered="false" class="wf-table"><thead><tr><th>材料</th><th>计划数量</th><th>单位</th><th>操作</th></tr></thead><tbody>
              <tr v-for="(material, index) in row.materials" :key="material.key"><td><n-select v-model:value="material.part_id" :options="partOptions" filterable :disabled="fieldsLocked" placeholder="选择配件" :aria-label="`明细 ${row.line.id} 材料 ${index + 1}`" style="min-width:220px" @update:value="material.unit = parts.find(p => p.id === material.part_id)?.unit || ''" /></td><td><n-input-number v-model:value="material.qty" :min="0.0001" :max="999999.9999" :precision="4" :disabled="fieldsLocked" :input-props="{ 'aria-label': `明细 ${row.line.id} 材料 ${index + 1} 数量` }" style="width:150px" /></td><td>{{ material.unit || '待核对' }}</td><td><n-button text type="error" :disabled="fieldsLocked" @click="row.materials.splice(index, 1)">移除</n-button></td></tr>
            </tbody></n-table></div>
            <n-button size="small" :disabled="fieldsLocked" @click="addMaterial(row)">添加本行计划材料</n-button>
          </n-collapse-item>
        </n-collapse>
        <p class="wf-muted">材料按行保留，不自动合并原手工单的配件行。BOM 只是理论参考；无 BOM 或读取失败时请手填核对，不把空白当作无需用料。</p>
        <n-form-item label="制作备注"><n-input v-model:value="note" type="textarea" :disabled="fieldsLocked" /></n-form-item>
      </n-form>
      <div class="wf-dialog-footer"><n-button :disabled="blocked" @click="$emit('close')">取消</n-button><n-button v-if="loadError" :disabled="blocked" @click="load">重新加载材料</n-button><n-button type="primary" :loading="saving" :disabled="loading || !!loadError" @click="save">{{ uncertain ? '重试核对此次结果（不重复创建）' : '确认整批安排' }}</n-button></div>
    </div>
  </n-modal>
</template>
<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { NAlert, NAutoComplete, NButton, NCheckbox, NCollapse, NCollapseItem, NForm, NFormItem, NInput, NInputNumber, NModal, NSelect, NTable } from 'naive-ui'
import { listParts, getPartBom } from '@/api/parts'
import { listSuppliers } from '@/api/suppliers'
import { getBom } from '@/api/bom'
import { createOrderHandcraftBatch } from '@/api/productionAllocation'
import { orderHandcraftBatchPayload } from '@/utils/orderProductionCreation'
import HandcraftTargetPicker from './HandcraftTargetPicker.vue'
import ProductCell from './ProductCell.vue'
const props = defineProps({ orderId: { type: String, required: true }, lines: { type: Array, required: true } })
const emit = defineEmits(['close', 'saved', 'busy'])
const remaining = line => Math.max(0, Number(line.quantity) - Number(line.allocated))
const rows = ref(props.lines.map(line => ({ line, planned: remaining(line), allocated: remaining(line), materials: [], bomNote: '' })))
const supplier = ref(''), suppliers = ref([]), parts = ref([]), targetId = ref(null), note = ref(''), reviewed = ref(false)
const loading = ref(true), saving = ref(false), uncertain = ref(false), loadError = ref(''), error = ref('')
const blocked = computed(() => saving.value || uncertain.value)
const fieldsLocked = computed(() => blocked.value || loading.value || !!loadError.value)
const hasLegacy = computed(() => props.lines.some(l => l.legacy_batches?.length))
const supplierOptions = computed(() => suppliers.value.map(s => s.name).filter(s => s.includes(supplier.value || '')))
const partOptions = computed(() => parts.value.map(p => ({ value: p.id, label: `${p.id} · ${p.name}` })))
let key = 0, attempt = null, active = true
function addMaterial(row) { row.materials.push({ key: ++key, part_id: null, unit: '', qty: null }) }
async function load() {
  if (blocked.value) return
  loading.value = true; loadError.value = ''; error.value = ''
  try {
    const [p, s] = await Promise.all([listParts(), listSuppliers({ type: 'handcraft' })])
    if (!active) return
    parts.value = p.data; suppliers.value = s.data
    const boms = new Map()
    await Promise.all(rows.value.map(async row => {
      const id = `${row.line.product_type}:${row.line.product_id}`
      if (!boms.has(id)) boms.set(id, (row.line.product_type === 'jewelry' ? getBom(row.line.product_id) : getPartBom(row.line.product_id)).then(r => r.data).catch(() => null))
      const bom = await boms.get(id)
      if (!active) return
      row.materials = (bom || []).map(r => {
        const partId = r.part_id || r.child_part_id, part = parts.value.find(p => p.id === partId)
        return { key: ++key, part_id: partId, unit: part?.unit || '', qty: Math.round(Number(r.qty_per_unit) * Number(row.planned) * 10000) / 10000 }
      })
      row.bomNote = bom === null ? 'BOM 读取失败，请手动核对材料。' : bom.length ? '打开弹窗时 BOM × 本行整条计划；改数量后请重新核对材料。' : '该商品暂无 BOM，请手动核对计划材料。'
      if (!row.materials.length) addMaterial(row)
    }))
  } catch (_) { if (active) { loadError.value = '商家或材料加载失败，请重试'; error.value = loadError.value } }
  finally { if (active) loading.value = false }
}
async function save() {
  if (saving.value || loading.value || loadError.value) return
  error.value = ''
  try {
    if (!attempt) attempt = orderHandcraftBatchPayload({ rows: rows.value, supplier: supplier.value, targetId: targetId.value, note: note.value, reviewed: reviewed.value, requestKey: crypto.randomUUID() })
    saving.value = true; emit('busy', true)
    const { data } = await createOrderHandcraftBatch(props.orderId, attempt)
    uncertain.value = false; emit('saved', data)
  } catch (e) {
    uncertain.value = !!attempt && (!e.response || e.response.status >= 500)
    if (!uncertain.value) attempt = null
    error.value = e.response?.data?.detail || e.message || '整批保存失败'
    if (uncertain.value) error.value += '；结果不确定，请用原请求重试核对，不要重新建单。'
  } finally { saving.value = false; emit('busy', uncertain.value) }
}
onBeforeRouteLeave(() => !blocked.value)
onBeforeRouteUpdate(() => !blocked.value)
function beforeUnload(event) { if (blocked.value) { event.preventDefault(); event.returnValue = '' } }
onMounted(() => { window.addEventListener('beforeunload', beforeUnload); load() })
onBeforeUnmount(() => { active = false; window.removeEventListener('beforeunload', beforeUnload) })
</script>
