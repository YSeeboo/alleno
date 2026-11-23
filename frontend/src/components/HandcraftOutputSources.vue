<template>
  <section class="hos-panel" :aria-label="`${item.output_name || item.output_id}的制作来源`">
    <div class="hos-heading"><strong>来源明细 · {{ total }} 条</strong><span>独立来源不合并，回收按来源核对</span></div>
    <div v-if="error" class="hos-error" role="alert">{{ error }} <n-button text size="small" @click="load">重试</n-button></div>
    <n-spin :show="loading">
      <article v-for="row in rows" :key="row.handcraft_jewelry_item_id" class="hos-source">
        <header><div><n-button text type="primary" size="small" @click="emit('open-page', `/handcraft/${encodeURIComponent(row.handcraft_order_id)}`, { highlight: String(row.handcraft_jewelry_item_id), item_type: 'jewelry' })">{{ row.handcraft_order_id }} ↗</n-button><small>独立来源 #{{ row.handcraft_jewelry_item_id }}</small><span v-if="row.archived_at" class="hos-archive">历史归档</span></div><span class="hos-status" :class="outputStatus(row)">{{ OUTPUT_STATUS[outputStatus(row)] }}</span></header>
        <p class="hos-date"><span :class="{ 'hos-reference': row.dispatch_date_basis !== 'actual' }">{{ row.dispatch_date_basis === 'actual' ? '实际发出日期' : '单据日期参考（非准确发出日）' }}</span> {{ row.dispatch_date || '日期缺失' }}</p>
        <div class="hos-quantities"><div v-for="metric in OUTPUT_METRICS" :key="metric.key"><small>{{ metric.label }}</small><strong :class="{ 'hos-outstanding': metric.key === 'unreceived_qty' && row.unreceived_qty > 0 }">{{ outputQuantity(row[metric.key]) }}<small>{{ outputUnit(row.unit) }}</small></strong></div></div>
        <p v-if="row.note || row.document_note" class="hos-notes"><span v-if="row.note">来源备注：{{ row.note }}</span><span v-if="row.document_note">单据备注：{{ row.document_note }}</span></p>
        <button class="hos-batch-toggle" :aria-expanded="!!batches[row.handcraft_jewelry_item_id]?.open" @click="toggleBatches(row)">{{ batches[row.handcraft_jewelry_item_id]?.open ? '收起' : '查看' }}回收批次 · {{ row.receipt_count }} 笔 <span>{{ batches[row.handcraft_jewelry_item_id]?.open ? '⌃' : '⌄' }}</span></button>
        <section v-if="batches[row.handcraft_jewelry_item_id]?.open" class="hos-batches" :aria-label="`${row.handcraft_order_id}来源${row.handcraft_jewelry_item_id}的回收批次`">
          <div v-if="batches[row.handcraft_jewelry_item_id].error" class="hos-error" role="alert">{{ batches[row.handcraft_jewelry_item_id].error }} <n-button text size="small" @click="loadBatches(row)">重试</n-button></div>
          <n-spin :show="batches[row.handcraft_jewelry_item_id].loading">
            <div v-for="batch in batches[row.handcraft_jewelry_item_id].items" :key="batch.receipt_item_id" class="hos-batch">
              <span>{{ batch.receipt_date }}</span><n-button text type="primary" size="tiny" @click="emit('open-page', `/handcraft-receipts/${encodeURIComponent(batch.receipt_id)}`, { highlight: String(batch.receipt_item_id) })">{{ batch.receipt_id }} ↗</n-button><strong>{{ outputQuantity(batch.qty) }} {{ outputUnit(batch.unit) }}</strong><span v-if="row.dispatch_date && batch.receipt_date.slice(0, 7) !== row.dispatch_date.slice(0, 7)" class="hos-cross-month">{{ row.dispatch_date_basis === 'actual' ? '跨月回收' : '跨参考月份' }}</span>
              <p v-if="batch.unit !== row.unit" class="hos-unit-warning">批次单位与来源不同，请核对原单；未做单位换算。</p>
              <p v-if="batch.note || batch.document_note" class="hos-batch-notes">{{ [batch.note && `明细备注：${batch.note}`, batch.document_note && `回收单备注：${batch.document_note}`].filter(Boolean).join(' · ') }}</p>
            </div>
            <p v-if="!batches[row.handcraft_jewelry_item_id].loading && !batches[row.handcraft_jewelry_item_id].error && !batches[row.handcraft_jewelry_item_id].items.length" class="hos-empty">尚无真实回收记录，制作任务仍保留在总览中。</p>
          </n-spin>
          <n-pagination v-if="batches[row.handcraft_jewelry_item_id].total > 20" :page="batches[row.handcraft_jewelry_item_id].page" :page-count="Math.ceil(batches[row.handcraft_jewelry_item_id].total / 20)" :page-slot="3" size="small" :disabled="batches[row.handcraft_jewelry_item_id].loading" @update:page="setBatchPage(row, $event)" />
        </section>
      </article>
      <p v-if="!loading && !error && !rows.length" class="hos-empty">当前条件下已无来源，请刷新总览核对。</p>
    </n-spin>
    <div v-if="total > 20" class="hos-pager"><n-pagination :page="page" :page-count="Math.ceil(total / 20)" :page-slot="3" :disabled="loading" size="small" @update:page="setPage" /></div>
  </section>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { NButton, NPagination, NSpin } from 'naive-ui'
import { getHandcraftOutputSources, getHandcraftOutputReceipts } from '@/api/handcraftOutput'
import { OUTPUT_METRICS, OUTPUT_STATUS, outputQuantity, outputStatus, outputUnit } from '@/utils/handcraftOutput'

const props = defineProps({ item: { type: Object, required: true }, filters: { type: Object, required: true } })
const emit = defineEmits(['open-page'])
const rows = ref([]), total = ref(props.item.source_count), page = ref(1), loading = ref(false), error = ref(''), batches = ref({})
let version = 0, disposed = false
async function load() {
  const current = ++version
  loading.value = true; error.value = ''; rows.value = []; batches.value = {}
  try {
    const { data } = await getHandcraftOutputSources({ ...props.filters, supplier_name: props.item.supplier_name, output_key: props.item.output_key, unit: props.item.unit, skip: (page.value - 1) * 20, limit: 20 })
    if (disposed || current !== version) return
    rows.value = data.items; total.value = data.total
    const lastPage = Math.max(1, Math.ceil(data.total / 20))
    if (page.value > lastPage) { page.value = lastPage; void load() }
  } catch (e) {
    if (!disposed && current === version) error.value = typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : '加载来源失败，请重试'
  } finally { if (!disposed && current === version) loading.value = false }
}
function setPage(value) { page.value = value; void load() }
function toggleBatches(row) {
  const id = row.handcraft_jewelry_item_id
  if (!batches.value[id]) {
    batches.value[id] = { open: true, loading: false, items: [], total: row.receipt_count, page: 1, error: '', version: 0 }
    void loadBatches(row)
  } else batches.value[id].open = !batches.value[id].open
}
async function loadBatches(row) {
  const entry = batches.value[row.handcraft_jewelry_item_id]
  const sourceVersion = version, current = ++entry.version
  entry.loading = true; entry.error = ''; entry.items = []
  try {
    const { data } = await getHandcraftOutputReceipts(row.handcraft_jewelry_item_id, { skip: (entry.page - 1) * 20, limit: 20 })
    if (disposed || sourceVersion !== version || current !== entry.version) return
    entry.items = data.items; entry.total = data.total
    const lastPage = Math.max(1, Math.ceil(data.total / 20))
    if (entry.page > lastPage) { entry.page = lastPage; void loadBatches(row) }
  } catch (e) {
    if (!disposed && sourceVersion === version && current === entry.version) entry.error = typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : '加载回收批次失败，请重试'
  } finally { if (!disposed && sourceVersion === version && current === entry.version) entry.loading = false }
}
function setBatchPage(row, value) { batches.value[row.handcraft_jewelry_item_id].page = value; void loadBatches(row) }
watch(() => JSON.stringify([props.item, props.filters]), () => { page.value = 1; void load() }, { immediate: true })
onBeforeUnmount(() => { disposed = true; version++ })
</script>

<style scoped>
.hos-panel { background: #f5f8f5; padding: 14px 18px 16px; color: #526f5b; }
.hos-heading { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; font-size: 11px; margin-bottom: 10px; }
.hos-heading strong { font-weight: 500; }.hos-heading > span { color: #9ca99f; font-size: 10px; }
.hos-source { background: white; border: 1px solid #e1e9e2; border-radius: 6px; padding: 10px 14px 0; margin-top: 9px; }
.hos-source header, .hos-source header > div { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.hos-source header { justify-content: space-between; }.hos-source header :deep(.n-button) { font-size: 11px; }
.hos-source header small { color: #9aa99e; font-size: 9px; }
.hos-archive { background: #f3f0ea; color: #9b9281; font-size: 9px; padding: 1px 5px; border-radius: 3px; }
.hos-status { font-size: 9px; border-radius: 3px; padding: 2px 6px; white-space: nowrap; }.hos-status.partial { background: #faf4e8; color: #a2854b; }.hos-status.unreceived { background: #eef2f5; color: #82919c; }.hos-status.settled { background: #e9f4ec; color: #59866b; }
.hos-date { font-size: 10px; color: #90a095; margin: 6px 0 12px; }.hos-reference { color: #b18a4b; }
.hos-quantities { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 10px; }
.hos-quantities > div > small { display: block; font-size: 10px; color: #98a69c; margin-bottom: 3px; }.hos-quantities strong { font-weight: 600; font-size: 13px; font-variant-numeric: tabular-nums; }.hos-quantities strong small { color: #9ba79e; font-size: 10px; margin-left: 4px; font-weight: 400; }.hos-outstanding { color: #a98147; }
.hos-notes, .hos-batch-notes { color: #97a49b; font-size: 10px; overflow-wrap: anywhere; }.hos-notes span { display: block; }
.hos-batch-toggle { display: flex; justify-content: space-between; align-items: center; width: 100%; padding: 9px 0; background: none; border: 0; border-top: 1px solid #eaf0eb; cursor: pointer; color: #64836c; font-size: 10px; }
.hos-batch-toggle:focus-visible { outline: 2px solid #1e7a5a; outline-offset: 2px; }
.hos-batches { padding: 3px 0 10px; border-top: 1px dashed #e4ebe5; }.hos-batch { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 15px; padding: 8px 0; color: #8fa094; font-size: 10px; }.hos-batch strong { margin-left: auto; font-size: 11px; color: #62826b; }.hos-batch :deep(.n-button) { font-size: 10px; }.hos-cross-month { color: #a08b5f; background: #faf5e9; padding: 1px 5px; border-radius: 3px; font-size: 9px; }
.hos-batch-notes, .hos-unit-warning { flex-basis: 100%; margin: 0; }.hos-unit-warning { color: #af8041; font-size: 10px; }.hos-error { color: #b5584a; padding: 8px 0; font-size: 11px; }.hos-empty { font-size: 11px; color: #99a79d; padding: 5px 0; }.hos-pager { display: flex; justify-content: flex-end; margin-top: 12px; overflow: auto; }
@media (max-width: 720px) { .hos-panel { padding: 12px 9px; }.hos-source { padding: 10px 9px 0; }.hos-quantities { gap: 6px; }.hos-quantities > div > small { font-size: 9px; }.hos-quantities strong { font-size: 12px; }.hos-quantities strong small { font-size: 9px; margin-left: 2px; }.hos-source header { gap: 5px; }.hos-source header small { font-size: 8px; }.hos-date { font-size: 9px; }.hos-batch { font-size: 9px; gap: 5px 8px; } }
</style>
