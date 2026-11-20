<template>
  <OrderSection title="配件备料与 BOM">
    <template #header-extra><div class="wf-actions"><n-button size="small" :type="accentActions ? 'primary' : 'default'" :secondary="accentActions" @click="openCutting">裁剪统计</n-button><n-button size="small" :type="accentActions ? 'primary' : 'default'" :secondary="accentActions" @click="showPicking = true">配货模拟 / PDF</n-button></div></template>
    <n-alert type="info" :bordered="false" class="wf-notice">理论用量来自当前 BOM，不是生产时点快照，也不代表已备料、已发料或成品库存。实际物料、发出、回收、损耗与付款仍在对应加工单处理。</n-alert>
    <n-spin :show="loading">
      <n-alert v-if="error" type="error">{{ error }} <n-button text @click="load">重新加载</n-button></n-alert>
      <template v-else>
        <n-empty v-if="!bomRows.length" description="无饰品 BOM；直接销售的配件无需 BOM 即可出货" class="wf-empty" />
        <div v-else class="wf-table-wrap"><n-data-table :columns="bomColumns" :data="bomRows" :bordered="false" :row-key="row => row.key" /></div>
        <n-collapse style="margin-top:16px"><n-collapse-item title="原备料估算参考" name="estimate">
          <p class="wf-section-description">保留原汇总算法（可能扣减整库成品、合并原批次）。这里的“原他单需求估计”不是当前库存预留台账，估算缺口不是精确制作需求，不用于客户交付判断。</p>
          <div class="wf-table-wrap"><n-data-table :columns="estimateColumns" :data="estimates" :bordered="false" :row-key="row => row.part_id" /></div>
        </n-collapse-item></n-collapse>
      </template>
    </n-spin>
  </OrderSection>
  <OrderSection v-if="historyError || batches.length || todos.length"><n-collapse><n-collapse-item title="已有批次与生产关联记录" name="history">
    <n-alert v-if="historyError" type="error">{{ historyError }} <n-button text @click="loadHistory">重新加载记录</n-button></n-alert>
    <p class="wf-section-description">按原始记录保留，不推算为本单当前明细的生产份额，不自动预留或补记出货。后续新增制作统一使用上方逐明细安排。</p>
    <n-collapse>
      <n-collapse-item v-for="batch in batches" :key="batch.id" :name="batch.id" :title="`批次 #${batch.id} · ${batch.created_at?.slice(0,10) || ''} · ${batch.supplier_name || '尚未关联商家'}`">
        <n-alert v-if="batch.missing_source" type="warning" class="wf-notice">原加工单已不存在，保留原关联编号供核对，不自动清除或重新分配。</n-alert>
        <div class="wf-actions" style="margin-bottom:12px"><n-button size="small" @click="exportBatch(batch)">导出批次 PDF</n-button><router-link v-if="batch.handcraft_order_id" :to="{ path: `/handcraft/${batch.handcraft_order_id}`, query: { from_order: orderId } }">{{ batch.handcraft_order_id }} → 查看原加工单</router-link></div>
        <p v-for="j in batch.jewelries" :key="j.jewelry_id">{{ j.jewelry_id }} · {{ j.jewelry_name }} × {{ j.quantity }}</p>
        <div class="wf-table-wrap"><n-data-table :columns="historyColumns" :data="batch.items" :bordered="false" /></div>
      </n-collapse-item>
    </n-collapse>
    <div v-if="unbatched.length" class="wf-table-wrap" style="margin-top:16px"><n-data-table :columns="historyColumns" :data="unbatched" :bordered="false" /></div>
  </n-collapse-item></n-collapse></OrderSection>
  <n-modal v-model:show="showCutting" preset="card" title="裁剪统计（原备料口径）" style="width:min(850px,calc(100vw - 24px))">
    <p class="wf-section-description">裁剪备料参考，不是实际发料凭据或客户出货数量。</p><n-button size="small" :loading="exporting" @click="exportCutting">导出裁剪 PDF</n-button>
    <n-spin :show="cuttingLoading"><n-alert v-if="cuttingError" type="error">{{ cuttingError }}</n-alert><div v-else class="wf-table-wrap"><n-data-table :columns="cuttingColumns" :data="cutting" :bordered="false" /></div></n-spin>
  </n-modal>
  <n-modal v-model:show="showBom" preset="card" title="组合配件 BOM" style="width:min(700px,calc(100vw - 24px))"><n-spin :show="childLoading"><n-alert v-if="childError" type="error">{{ childError }}</n-alert><div v-else class="wf-table-wrap"><n-data-table :columns="childColumns" :data="children" :bordered="false" /></div></n-spin></n-modal>
  <PickingSimulationModal v-model:show="showPicking" :order-id="orderId" :readonly="!editable" />
</template>
<script setup>
import { computed, h, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { NAlert, NButton, NCollapse, NCollapseItem, NDataTable, NEmpty, NModal, NSpin, useMessage } from 'naive-ui'
import OrderSection from '@/components/fulfillment/OrderSection.vue'
import PickingSimulationModal from '@/components/picking/PickingSimulationModal.vue'
import { getPartsSummary, getTodo, getTodoBatches, getCuttingStats, downloadCuttingStatsPdf, downloadBatchPdf } from '@/api/orders'
import { getBom } from '@/api/bom'
import { getPartBom, listParts } from '@/api/parts'
import { renderNamedImage } from '@/utils/ui'
const props = defineProps({ orderId: { type: String, required: true }, lines: { type: Array, required: true }, editable: Boolean, accentActions: Boolean })
const message = useMessage(), loading = ref(false), error = ref(''), estimates = ref([]), boms = ref({}), parts = ref({})
const batches = ref([]), todos = ref([]), historyError = ref('')
const showPicking = ref(false), showCutting = ref(false), cuttingLoading = ref(false), cuttingError = ref(''), cutting = ref([]), exporting = ref(false)
const showBom = ref(false), children = ref([]), childLoading = ref(false), childError = ref('')
const unbatched = computed(() => todos.value.filter(t => !batches.value.some(b => b.items.some(i => i.id === t.id))))
const bomRows = computed(() => props.lines.filter(l => l.product_type === 'jewelry').flatMap(line => {
  const rows = boms.value[line.product_id] || []
  if (!rows.length) return [{ key:`${line.id}:missing`, line, missing:true }]
  return rows.map(row => ({ ...row, key:`${line.id}:${row.part_id}`, line, part:parts.value[row.part_id] }))
}))
function partCell(row) {
  const p = parts.value[row.part_id], node = renderNamedImage(p?.name || row.part_name || row.part_id, p?.image || row.part_image, p?.name || row.part_name || row.part_id, 32)
  return p?.is_composite || row.part_is_composite ? h(NButton, { text:true, type:'primary', onClick:() => openChildren(row.part_id) }, () => node) : node
}
const bomColumns = [
  { title:'订单明细', key:'line', render:r => `${r.line.product_name} · #${r.line.id}${r.line.customer_code ? ` · ${r.line.customer_code}` : ''}` },
  { title:'所需配件', key:'part_id', render:r => r.missing ? '尚未维护 BOM（不阻止现货出货）' : partCell(r) },
  { title:'单件用量', key:'qty_per_unit' }, { title:'订购', key:'quantity', render:r => r.line.quantity },
  { title:'整单理论用量', key:'total', render:r => r.missing ? '—' : `${Number((r.qty_per_unit * r.line.quantity).toFixed(7))} ${r.part?.unit || ''}` },
]
const estimateColumns = [ { title:'配件', key:'part_id', render:partCell }, { title:'原估算需求', key:'total_qty' }, { title:'整库账面量', key:'current_stock' }, { title:'原他单需求估计', key:'reserved_qty' }, { title:'原估算缺口', key:'remaining_qty' },
  { type:'expand', renderExpand:r => h('div', { style:'padding:12px' }, (r.source_jewelries || []).map(s => h('p', s.source_type === 'direct' ? `客户直购 × ${s.order_qty} = ${s.subtotal}` : `${s.jewelry_id} · ${s.jewelry_name}：${s.qty_per_unit} × ${s.order_qty} = ${s.subtotal}`))) },
]
const historyColumns = [ { title:'配件', key:'part_id', render:partCell }, { title:'原清单数量', key:'required_qty' }, { title:'原生产关联', key:'linked_production', render:r => h('div', { class:'wf-actions' }, (r.linked_production || []).map(p => h(RouterLink, { to:{ path:`/${{ plating:'plating', purchase:'purchase-orders', handcraft:'handcraft' }[p.type]}/${p.order_id}`, query:{ from_order:props.orderId } } }, () => `${p.order_id} · ${p.status || ''}`))) } ]
const cuttingColumns = [ { title:'配件编号', key:'part_id' }, { title:'配件', key:'part_name' }, { title:'裁剪长度（cm）', key:'cut_length_cm' }, { title:'裁剪数量', key:'qty' }, { title:'总长度（m）', key:'total', render:r => Math.ceil((r.cut_length_cm * r.qty / 100) * 10 - 1e-8) / 10 } ]
const childColumns = [ { title:'子配件', key:'child_part_name' }, { title:'编号', key:'child_part_id' }, { title:'单件用量', key:'qty_per_unit' }, { title:'单位', key:'child_part_unit' } ]
let request = 0, historyRequest = 0, childRequest = 0, cuttingRequest = 0
async function load() {
  const id = ++request; loading.value = true; error.value = ''
  boms.value = {}; parts.value = {}; estimates.value = []
  try {
    const ids = [...new Set(props.lines.filter(l => l.product_type === 'jewelry').map(l => l.product_id))]
    const [summary, catalog, ...bom] = await Promise.all([getPartsSummary(props.orderId), listParts({}), ...ids.map(getBom)])
    if (id !== request) return
    estimates.value = summary.data; parts.value = Object.fromEntries(catalog.data.map(p => [p.id, p])); boms.value = Object.fromEntries(ids.map((key, index) => [key, bom[index].data]))
  } catch (_) { if (id === request) error.value = 'BOM 与备料参考加载失败，不能当作没有需求' }
  finally { if (id === request) loading.value = false }
}
async function loadHistory() {
  const id = ++historyRequest; historyError.value = ''
  batches.value = []; todos.value = []
  try { const [b, t] = await Promise.all([getTodoBatches(props.orderId), getTodo(props.orderId)]); if (id === historyRequest) { batches.value = b.data.batches || []; todos.value = t.data || [] } }
  catch (_) { if (id === historyRequest) historyError.value = '已有批次记录加载失败' }
}
async function openChildren(partId) {
  const id = ++childRequest; showBom.value = true; children.value = []; childLoading.value = true; childError.value = ''
  try { const response = await getPartBom(partId); if (id === childRequest) children.value = response.data }
  catch (_) { if (id === childRequest) childError.value = '组合配件 BOM 加载失败' }
  finally { if (id === childRequest) childLoading.value = false }
}
async function openCutting() {
  const id = ++cuttingRequest
  showCutting.value = true; cuttingLoading.value = true; cuttingError.value = ''; cutting.value = []
  try { const response = await getCuttingStats(props.orderId); if (id === cuttingRequest) cutting.value = response.data.items || [] }
  catch (_) { if (id === cuttingRequest) cuttingError.value = '裁剪统计加载失败' }
  finally { if (id === cuttingRequest) cuttingLoading.value = false }
}
function download(response, filename) { const url = URL.createObjectURL(response.data), link = document.createElement('a'); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url) }
async function exportBatch(batch) { try { download(await downloadBatchPdf(props.orderId, batch.id), `配件清单_${props.orderId}_批次${batch.id}.pdf`) } catch (_) { message.error('批次 PDF 导出失败') } }
async function exportCutting() { if (exporting.value) return; exporting.value = true; try { download(await downloadCuttingStatsPdf(props.orderId), `裁剪统计_${props.orderId}.pdf`) } catch (_) { message.error('裁剪 PDF 导出失败') } finally { exporting.value = false } }
watch(() => [props.orderId, props.lines], () => { ++childRequest; ++cuttingRequest; showPicking.value = false; showBom.value = false; showCutting.value = false; load(); loadHistory() }, { immediate:true })
</script>
