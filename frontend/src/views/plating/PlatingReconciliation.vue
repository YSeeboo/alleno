<template>
  <div class="reconciliation">
    <header class="section-heading"><h2>电镀商家对账</h2><p>按回收明细核对加工报价，独立记录最终结算金额。</p></header>
    <div class="filter-panel">
      <div class="filters">
        <label>商家名称<n-select v-model:value="supplier" :options="vendorOptions" placeholder="全部商家" clearable filterable /></label>
        <div class="dates"><span>回收日期</span><div class="date-range"><input v-model="from" type="date" aria-label="开始日期"><span>至</span><input v-model="to" type="date" aria-label="结束日期"></div></div>
        <label>付款状态<n-select v-model:value="status" :options="statusOptions" placeholder="全部状态" clearable /></label>
        <div class="quick-dates"><n-button size="small" quaternary @click="setPeriod(0)">本月</n-button><n-button size="small" quaternary @click="setPeriod(-1)">上月</n-button><n-button size="small" quaternary @click="setPeriod(null)">不限日期</n-button></div>
        <n-button class="reset" text @click="resetFilters">重置筛选</n-button>
      </div>
      <p class="filter-note">按回收单创建时间统计 · 汇总、明细与导出使用相同筛选 · 已付款为所选回收单的结算金额，并非期间付款流水</p>
      <p v-if="invalidDates" class="error" role="alert">开始日期不能晚于结束日期，请调整日期范围。</p>
    </div>
    <div v-if="error" class="load-error" role="alert">{{ error }} <n-button size="small" @click="load">重新加载</n-button></div>
    <n-spin :show="loading">
      <div class="stats" aria-live="polite">
        <article v-for="stat in stats" :key="stat.key" class="stat" :class="stat.key"><span>{{ stat.label }}</span><strong :style="{ '--amount-length': money(data.totals[stat.key]).length + 1 }"><small>¥</small>{{ money(data.totals[stat.key]) }}</strong><p>{{ stat.note }}</p></article>
      </div>
      <p v-if="data.totals.unpriced_count" class="unpriced" role="status">另有 {{ data.totals.unpriced_count }} 条待定价明细，尚未计入金额合计，不按 0 元结算。</p>
      <section class="block"><div class="block-head"><h3>商家汇总 <small>{{ data.merchants.length }} 家</small></h3><span>点击商家名称查看该商家明细</span></div>
        <n-data-table :columns="merchantColumns" :data="data.merchants" :scroll-x="650" size="small" :summary="merchantSummary" />
      </section>
      <section class="block"><div class="block-head"><h3>回收明细 <small>{{ data.total }} 条</small></h3><span>金额单位：元 · 左右滑动查看完整明细</span></div>
        <div class="rule-strip">改价只影响对账，不修改原回收单。留空沿用原价，清空可恢复；已付款或历史归档明细不可改价。回车或移出输入框保存。</div>
        <n-data-table :columns="detailColumns" :data="data.items" :row-key="row => row.receipt_item_id" :scroll-x="1870" size="small" />
        <div class="table-footer"><span>共 {{ data.total }} 条明细，汇总和导出包含所有分页</span><span>{{ saveNote }} <n-button v-if="Object.keys(drafts).length" text size="tiny" :disabled="saving.size > 0" @click="discardDrafts">放弃未保存改价</n-button></span></div>
        <div class="pager"><n-pagination v-model:page="page" :page-count="pageCount" :page-size="pageSize" /></div>
      </section>
    </n-spin>
    <p class="bottom-note">已付款按结算时的对账金额锁定，历史已付款沿用原单金额。付款状态在原回收单维护；撤回为未付款后解除锁定，保留改价。<br>本页不包含部分付款、付款流水或损耗扣款抵扣。Excel 默认打开“回收明细”，“商家汇总”位于第二个工作表。</p>
    <FloatingActionBar aria-label="电镀商家对账操作"><FloatingActionButton variant="excel" :disabled="exportDisabled" :loading="exporting" @click="exportExcel"><template #icon><n-icon :component="DownloadOutline" /></template>导出 Excel</FloatingActionButton></FloatingActionBar>
  </div>
</template>

<script setup>
import { computed, h, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { NButton, NDataTable, NIcon, NPagination, NSelect, NSpin, NTag, useMessage } from 'naive-ui'
import { DownloadOutline, LockClosedOutline } from '@vicons/ionicons5'
import FloatingActionBar from '@/components/FloatingActionBar.vue'
import FloatingActionButton from '@/components/FloatingActionButton.vue'
import { usePlatingPageQuery } from '@/composables/usePlatingPageQuery'
import { useIsMobile } from '@/composables/useIsMobile'
import { getPlatingReceiptVendors } from '@/api/platingReceipts'
import { downloadReconciliationExcel, listReconciliation, updateReconciliationPrice } from '@/api/platingReconciliation'
import { monthBounds, reconciliationParams, validOverride } from '@/utils/platingReconciliation'

const router = useRouter()
const message = useMessage()
const { isMobile } = useIsMobile()
const { active, query, updateQuery, field } = usePlatingPageQuery('reconciliation')
const defaults = monthBounds()
const supplier = field('supplier')
const status = field('status')
const from = field('date_from', defaults.date_from)
const to = field('date_to', defaults.date_to)
const statusOptions = [{ label: '未付款', value: '未付款' }, { label: '已付款', value: '已付款' }]
const vendorOptions = ref([])
const pageSize = 30
const page = computed({ get: () => Number(query.value.page || 1), set: value => void updateQuery({ page: String(value) }, false) })
const emptyData = () => ({ totals: { due: '0', paid: '0', pending: '0', unpriced_count: 0 }, merchants: [], items: [], total: 0 })
const data = ref(emptyData())
const loading = ref(false)
const error = ref('')
const exporting = ref(false)
const drafts = reactive({})
const saving = reactive(new Set())
const saveNote = ref('改价独立保存于服务器，原回收单不变')
const invalidDates = computed(() => !!(from.value && to.value && from.value > to.value))
const pageCount = computed(() => Math.max(1, Math.ceil(data.value.total / pageSize)))
const exportDisabled = computed(() => loading.value || exporting.value || !!error.value || invalidDates.value || !data.value.total || saving.size > 0 || Object.keys(drafts).length > 0)
const stats = [
  { key: 'due', label: '应付款', note: '已付款 + 待付款' },
  { key: 'paid', label: '已付款', note: '已结算金额，价格已锁定' },
  { key: 'pending', label: '待付款', note: '按对账后的金额计算' },
]
const money = value => value == null ? '待定价' : Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const number = value => value == null ? '—' : String(value).replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '')
function setPeriod(offset) { void updateQuery(offset === null ? { date_from: '', date_to: '' } : monthBounds(offset)) }
function resetFilters() { void updateQuery({ supplier: null, status: null, ...monthBounds() }) }
function discardDrafts() { for (const key of Object.keys(drafts)) delete drafts[key] }
function params() { return reconciliationParams({ ...query.value, date_from: from.value, date_to: to.value }) }
let version = 0
let disposed = false
async function load() {
  if (!active.value || disposed) return
  const current = ++version
  if (invalidDates.value) { data.value = emptyData(); loading.value = false; return }
  loading.value = true
  error.value = ''
  try {
    const response = await listReconciliation({ ...params(), skip: (page.value - 1) * pageSize, limit: pageSize })
    if (current !== version || disposed) return
    data.value = response.data
    if (page.value > pageCount.value) void updateQuery({ page: String(pageCount.value) }, false)
  } catch (e) {
    if (current === version && !disposed) { data.value = emptyData(); error.value = e?.response?.data?.detail || '加载对账数据失败，请重试' }
  } finally { if (current === version) loading.value = false }
}
function link(text, path, highlight) {
  return h(NButton, { text: true, type: 'primary', size: 'small', onClick: () => router.push({ path, query: { highlight } }) }, { default: () => text })
}
const merchantColumns = [
  { title: '商家名称', key: 'vendor_name', width: 290, render: row => h('div', [h(NButton, { text: true, type: 'primary', onClick: () => { supplier.value = row.vendor_name } }, { default: () => row.vendor_name }), h('small', { class: 'merchant-meta' }, ` ${row.receipt_count} 张回收单${row.unpriced_count ? ` · ${row.unpriced_count} 条待定价` : ''}`)]) },
  ...[['due', '应付款'], ['paid', '已付款'], ['pending', '待付款']].map(([key, title]) => ({ title, key, align: 'right', render: row => `¥ ${money(row[key])}` })),
]
function merchantSummary() {
  return { vendor_name: { value: '合计' }, ...Object.fromEntries(['due', 'paid', 'pending'].map(key => [key, { value: `¥ ${money(data.value.totals[key])}` }])) }
}
async function savePrice(row) {
  const id = row.receipt_item_id
  if (!(id in drafts) || saving.has(id)) return
  const value = drafts[id].trim()
  if (!validOverride(value)) { message.error('改价须大于等于 0，最多 7 位小数；本次输入尚未保存'); return }
  if (value === number(row.override_price) || (value === '' && row.override_price == null)) { delete drafts[id]; return }
  saving.add(id)
  try {
    await updateReconciliationPrice(id, value === '' ? null : value)
    delete drafts[id]
    saveNote.value = '对账改价已保存 · 原回收单未修改'
    message.success(value === '' ? '已恢复原单价' : '对账改价已保存')
    await load()
  } catch (e) {
    message.error(e?.response?.data?.detail || '保存改价失败，输入已保留，请重试')
    await load()
  } finally { saving.delete(id) }
}
function renderOverride(row) {
  if (row.status === '已付款' || row.archived) return h('span', { class: 'locked', title: row.archived ? '历史归档，不可改价' : '已付款，结算金额已锁定' }, [h(NIcon, { component: LockClosedOutline }), ` ${number(row.override_price)}`])
  const id = row.receipt_item_id
  const value = drafts[id] ?? (row.override_price == null ? '' : number(row.override_price))
  return h('input', {
    class: ['price-input', { changed: row.override_price != null }], value, type: 'text', inputmode: 'decimal',
    'aria-label': `${row.receipt_id} ${row.part_name} 改价`, 'aria-invalid': !validOverride(value.trim()),
    placeholder: '填写改价', disabled: saving.has(id),
    onInput: event => { drafts[id] = event.target.value }, onBlur: () => savePrice(row),
    onKeydown: event => { if (event.key === 'Enter') { event.preventDefault(); event.target.blur() } if (event.key === 'Escape') { delete drafts[id]; event.target.value = row.override_price == null ? '' : number(row.override_price); event.target.blur() } },
  })
}
const detailColumns = computed(() => [
  { title: '回收时间 ↓', key: 'created_at', width: 150, render: row => row.created_at?.replace('T', ' ').slice(0, 19) || '—' },
  { title: '回收单号', key: 'receipt_id', width: 155, render: row => link(row.receipt_id, `/plating-receipts/${row.receipt_id}`, row.receipt_item_id) },
  { title: '商家名称', key: 'vendor_name', width: 130 },
  { title: '配件编号', key: 'part_id', width: 145 },
  { title: '配件', key: 'part_name', width: 170 },
  { title: '电镀单号', key: 'plating_order_id', width: 150, render: row => link(row.plating_order_id, `/plating/${row.plating_order_id}`, row.plating_order_item_id) },
  { title: '电镀方式', key: 'plating_method', width: 95 },
  { title: '回收数量', key: 'qty', width: 90, align: 'right', render: row => number(row.qty) },
  { title: '单位', key: 'unit', width: 60 },
  { title: '重量', key: 'weight', width: 95, align: 'right', render: row => row.weight == null ? '—' : `${number(row.weight)} ${row.weight_unit || 'g'}` },
  { title: '单价', key: 'price', width: 100, align: 'right', render: row => number(row.price) },
  { title: '改价', key: 'override_price', width: 115, align: 'right', render: renderOverride },
  { title: '金额', key: 'amount', width: 110, align: 'right', render: row => h('span', { class: row.amount == null ? 'unpriced' : row.override_price != null ? 'changed-amount' : '' }, money(row.amount)) },
  { title: '付款状态', key: 'status', width: 100, render: row => h(NTag, { size: 'small', round: true, type: row.status === '已付款' ? 'success' : 'warning' }, { default: () => row.status }) },
  { title: '备注', key: 'note', width: 170 },
].map(column => ({ ...column, fixed: isMobile.value ? undefined : column.key === 'created_at' ? 'left' : ['price', 'override_price', 'amount', 'status'].includes(column.key) ? 'right' : undefined })))
async function exportExcel() {
  if (exportDisabled.value) return
  exporting.value = true
  try {
    const response = await downloadReconciliationExcel(params())
    const url = URL.createObjectURL(response.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `电镀商家对账_${supplier.value || '全部商家'}_${from.value || '不限'}_${to.value || '不限'}.xlsx`
    document.body.append(a); a.click(); a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (_) { message.error('Excel 导出失败，请重试') } finally { exporting.value = false }
}
watch(query, () => { void load() }, { immediate: true })
getPlatingReceiptVendors().then(response => { vendorOptions.value = response.data.map(value => ({ label: value, value })) }).catch(() => { message.error('加载商家列表失败') })
function confirmNavigation() {
  if (saving.size) { message.warning('正在保存改价，请稍候'); return false }
  if (Object.keys(drafts).length && !window.confirm('有未保存的改价，离开将丢弃这些输入，是否继续？')) return false
  discardDrafts()
}
onBeforeRouteLeave(confirmNavigation)
onBeforeRouteUpdate(confirmNavigation)
function beforeUnload(event) { if (saving.size || Object.keys(drafts).length) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => { disposed = true; version++; window.removeEventListener('beforeunload', beforeUnload) })
</script>

<style scoped>
.reconciliation { min-width: 0; }
.section-heading h2 { margin: 0; font-size: 16px; font-weight: 650; }
.section-heading p { margin: 4px 0 17px; color: #8B9096; font-size: 12px; }
.filter-panel { padding: 16px; background: #fff; border: 1px solid #E8ECEB; border-radius: 9px; }
.filters { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 13px; }
.filters label, .dates { display: flex; flex-direction: column; gap: 6px; color: #8B9096; font-size: 11px; }
.filters label { width: 170px; }
.date-range { display: flex; align-items: center; gap: 8px; }
.date-range input { box-sizing: border-box; min-width: 0; height: 34px; width: 145px; padding: 0 9px; border: 1px solid #DFE5E1; border-radius: 5px; color: #536259; background: white; font: inherit; }
.quick-dates { display: flex; gap: 3px; }
.reset { margin-left: auto; min-height: 34px; font-size: 11px; }
.filter-note, .bottom-note { margin: 11px 0 0; font-size: 11px; color: #929D96; line-height: 1.8; }
.stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 13px; margin: 18px 0; }
.stat { background: white; padding: 17px 20px; border: 1px solid #E8ECEB; border-radius: 9px; }
.stat > span { font-size: 11px; color: #7E8C84; }
.stat strong { display: block; font-size: 29px; font-weight: 650; font-variant-numeric: tabular-nums; }
.stat small { margin-right: 7px; font-size: 16px; font-weight: 400; color: #8E9992; }
.stat p { margin: 4px 0 0; font-size: 10px; color: #9CA59F; }
.stat.paid strong, .stat.pending strong { color: #1E7A5A; }
.stat.pending { background: linear-gradient(115deg, #F0F7F2, #fff); }
.block { margin-top: 22px; }
.block-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
.block-head h3 { margin: 0; font-size: 13px; }
.block-head small { margin-left: 5px; padding: 2px 6px; background: #E9EDEB; color: #819088; border-radius: 4px; font-size: 10px; font-weight: 400; }
.block-head > span { color: #98A39B; font-size: 10px; }
.rule-strip { margin: 10px 0; padding: 9px 11px; background: #F0F5F1; border: 1px solid #E4EBE5; border-radius: 6px; color: #7D9081; font-size: 11px; }
.table-footer { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-top: 10px; color: #8C9D91; font-size: 10px; }
.pager { display: flex; justify-content: flex-end; margin-top: 16px; }
.bottom-note { margin-top: 24px; }
.error, .load-error { color: #BD5F50; }
.load-error { margin: 14px 0; }
.unpriced { color: #B37A2C; font-size: 11px; }
:deep(.merchant-meta) { color: #98A39B; font-size: 10px; }
:deep(.price-input) { box-sizing: border-box; width: 92px; height: 30px; padding: 0 7px; border: 1px solid #DBE6DD; border-radius: 5px; background: white; color: #2C7147; text-align: right; font: inherit; font-size: 11px; }
:deep(.price-input.changed) { border-color: #BCD6C3; }
:deep(.price-input[aria-invalid=true]) { border-color: #CD6F61; background: #FFF8F6; }
:deep(.price-input:focus-visible) { outline: 2px solid #1E7A5A; outline-offset: 1px; }
:deep(.locked) { display: inline-flex; align-items: center; gap: 4px; color: #9DA89F; font-size: 11px; }
:deep(.changed-amount) { color: #31754C; font-weight: 600; }
@media (max-width: 767px) {
  .filters { gap: 10px; }
  .filters label { flex: 1 1 calc(50% - 10px); min-width: 0; }
  .dates { flex-basis: 100%; order: 3; }
  .date-range input { flex: 1; width: 0; }
  .quick-dates { order: 4; }
  .reset { order: 5; }
  .stats { gap: 7px; }
  .stat { padding: 12px 9px; }
  .stat strong { font-size: clamp(10px, calc(140px / var(--amount-length)), 16px); white-space: nowrap; letter-spacing: -.3px; }
  .stat small { font-size: 10px; margin-right: 3px; }
  .stat p { font-size: 9px; }
}
</style>
