<template>
  <n-modal
    :show="true" preset="card" title="添加回收项" class="receipt-picker"
    :mask-closable="false" :close-on-esc="!busy && !uncertain" :closable="!busy && !uncertain"
    @update:show="value => { if (!value) requestClose() }"
  >
    <p class="rp-intro"><strong>{{ receipt.supplier_name }}</strong> · 选择来源后，填写本次实际收回的数量。含已结清来源，允许超收；本单已有的来源请修改原明细。</p>
    <n-alert v-if="loadError" type="error" class="rp-alert">回收来源加载失败。<n-button text type="primary" @click="loadSources">重试加载</n-button></n-alert>

    <div class="rp-split">
      <section class="rp-catalog" aria-labelledby="receipt-source-heading">
        <div class="rp-panel-head"><h3 id="receipt-source-heading">可选来源</h3><span>{{ filtered.length }} 条</span></div>
        <div class="rp-filters">
          <n-input v-model:value="keyword" clearable placeholder="搜索名称 / 编号 / 手工单" :input-props="{ 'aria-label': '搜索回收来源' }" :disabled="locked"><template #prefix><n-icon :component="SearchOutline" /></template></n-input>
          <n-date-picker v-model:value="dateOn" type="date" clearable placeholder="手工单日期" aria-label="筛选手工单日期" :disabled="locked" />
        </div>
        <div class="rp-types" role="group" aria-label="回收来源类型">
          <button v-for="option in kinds" :key="option.value" type="button" :aria-pressed="kind === option.value" :disabled="locked" @click="kind = option.value">{{ option.label }}</button>
        </div>
        <div class="rp-list-tools">
          <n-checkbox :checked="allPageSelected" :indeterminate="somePageSelected && !allPageSelected" :disabled="locked || loading || !pageRows.length" @update:checked="togglePage">选择本页</n-checkbox>
          <n-checkbox v-model:checked="selectedOnly" :disabled="locked">只看已选</n-checkbox>
        </div>
        <n-spin :show="loading">
          <div class="rp-source-list">
            <label v-for="row in pageRows" :key="sourceKey(row)" class="rp-source" :class="{ 'is-selected': selectedKeys.has(sourceKey(row)) }">
              <input type="checkbox" :checked="selectedKeys.has(sourceKey(row))" :disabled="locked" :aria-label="`选择 ${row.item_name} ${row.handcraft_order_id} ${kindLabel(row)}`" @change="toggle(row, $event.target.checked)" />
              <img v-if="row.item_image" :src="row.item_image" :alt="row.item_name" loading="lazy" />
              <span v-else class="rp-image-placeholder" aria-hidden="true"><n-icon :component="CubeOutline" /></span>
              <span class="rp-source-copy">
                <strong>{{ row.item_name || row.item_id }}</strong>
                <small>{{ row.item_id }} · {{ kindLabel(row) }}<template v-if="row.color"> · {{ row.color }}</template></small>
                <small>{{ row.handcraft_order_id }} · {{ row.created_at?.slice(0, 10) || '—' }}</small>
              </span>
              <span class="rp-balance"><small>{{ remainingQuantity(row) ? '尚未收回' : '来源已结清' }}</small><strong>{{ sourceBalance(row) }} {{ row.unit || '个' }}</strong></span>
            </label>
            <n-empty v-if="!loading && !loadError && !pageRows.length" :description="sources.length ? '没有符合筛选条件的来源' : '该商家暂无可添加的回收来源'">
              <template v-if="sources.length" #extra><n-button text type="primary" :disabled="locked" @click="clearFilters">清除筛选</n-button></template>
            </n-empty>
          </div>
        </n-spin>
        <div v-if="filtered.length > pageSize" class="rp-pagination"><n-pagination v-model:page="page" :page-size="pageSize" :item-count="filtered.length" :page-slot="3" size="small" :disabled="locked" /></div>
      </section>

      <section class="rp-drafts" aria-labelledby="receipt-draft-heading">
        <div class="rp-panel-head"><h3 id="receipt-draft-heading">待添加清单 <span>{{ selected.length }} 项</span></h3><n-button text size="small" :disabled="locked || !selected.length" @click="clearSelection">清空</n-button></div>
        <div class="rp-draft-list">
          <n-empty v-if="!selected.length" description="勾选来源后，在这里填写回收明细" />
          <article v-for="row in selected" :key="sourceKey(row)" class="rp-draft">
            <header>
              <div class="rp-source-copy"><strong>{{ row.item_name || row.item_id }}</strong><small>{{ row.handcraft_order_id }} · {{ row.item_id }} · {{ kindLabel(row) }}</small></div>
              <n-button text size="small" :disabled="locked" :aria-label="`移除 ${row.item_name} ${row.handcraft_order_id}`" @click="toggle(row, false)">移除</n-button>
            </header>
            <div class="rp-fields">
              <label><span>本次回收（{{ inputs[sourceKey(row)].unit }}）</span><n-input-number v-model:value="inputs[sourceKey(row)].qty" :min="row.is_output ? 1 : 0.0001" :precision="row.is_output ? 0 : 4" :disabled="locked" :show-button="false" size="small" placeholder="实际数量" :input-props="{ 'aria-label': `本次回收数量 ${row.item_name}` }" /></label>
              <label><span>手工单价（元）</span><n-input-number v-model:value="inputs[sourceKey(row)].price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" :disabled="locked" :show-button="false" size="small" placeholder="选填" :input-props="{ 'aria-label': `手工单价 ${row.item_name}` }" /></label>
              <div class="rp-amount"><span>本行金额</span><strong>{{ lineAmount(row) == null ? '待定价' : `¥ ${fmtMoney(lineAmount(row))}` }}</strong></div>
            </div>
            <div class="rp-row-tools">
              <span :class="{ 'rp-over': overBy(row) > 0 }">{{ overBy(row) > 0 ? `超出未收 ${overBy(row)} ${inputs[sourceKey(row)].unit}` : `未收：${sourceBalance(row)} ${inputs[sourceKey(row)].unit}` }}</span>
              <n-button text size="small" :disabled="locked" :aria-expanded="!!inputs[sourceKey(row)].showWeight" @click="inputs[sourceKey(row)].showWeight = !inputs[sourceKey(row)].showWeight">{{ inputs[sourceKey(row)].showWeight ? '收起重量' : '重量（选填）' }}</n-button>
            </div>
            <div v-if="inputs[sourceKey(row)].showWeight" class="rp-weight">
              <n-input-number v-model:value="inputs[sourceKey(row)].weight" :min="0" :disabled="locked" :show-button="false" size="small" placeholder="本次重量" :input-props="{ 'aria-label': `本次重量 ${row.item_name}` }" />
              <n-select v-model:value="inputs[sourceKey(row)].weight_unit" :options="weightUnits" :disabled="locked" size="small" :aria-label="`重量单位 ${row.item_name}`" />
            </div>
          </article>
        </div>
      </section>
    </div>

    <template #footer>
      <n-alert v-if="uncertain" type="warning" class="rp-alert">未能确认是否已保存。请刷新回收明细核对，避免重复回收。<n-button text type="primary" :loading="busy" @click="verify">刷新明细</n-button></n-alert>
      <n-alert v-if="submitError" type="error" class="rp-alert">{{ submitError }}</n-alert>
      <div class="rp-footer">
        <div><strong>已选 {{ selected.length }} 项</strong><span v-if="selected.length"> · 已定价金额 ¥ {{ fmtMoney(summary.amount) }}<template v-if="summary.unpricedCount"> · {{ summary.unpricedCount }} 项待定价</template></span></div>
        <n-space size="small" justify="end">
          <n-button v-if="!uncertain" :disabled="busy" @click="requestClose">取消</n-button>
          <n-button type="primary" :loading="busy && !uncertain" :disabled="locked || loading || loadError || !selected.length" @click="submit">添加 {{ selected.length }} 项</n-button>
        </n-space>
      </div>
    </template>
  </n-modal>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { NAlert, NButton, NCheckbox, NDatePicker, NEmpty, NIcon, NInput, NInputNumber, NModal, NPagination, NSelect, NSpace, NSpin, useDialog, useMessage } from 'naive-ui'
import { CubeOutline, SearchOutline } from '@vicons/ionicons5'
import { addHandcraftReceiptItems, getHandcraftReceipt, listHandcraftPendingReceiveItems } from '@/api/handcraftReceipts'
import { createHandcraftReceiptInput, handcraftReceiptLineAmount, handcraftSourceKey as sourceKey, summarizeHandcraftReceipt } from '@/utils/handcraftReceiptCreate'
import { additionalReceiptPayload, filterAddReceiptSources, handcraftReceiptSourceParams } from '@/utils/handcraftReceiptDetail'
import { remainingQuantity, sourceBalance } from '@/utils/receiptQuantity'
import { tsToDateStr } from '@/utils/date'
import { fmtMoney, fmtPrice, parseNum } from '@/utils/ui'

const props = defineProps({ receipt: { type: Object, required: true } })
const emit = defineEmits(['close', 'saved', 'verified'])
const dialog = useDialog()
const message = useMessage()
const sources = ref([]), selected = ref([]), inputs = reactive({})
const kind = ref('all'), keyword = ref(''), dateOn = ref(null), selectedOnly = ref(false), page = ref(1)
const loading = ref(false), loadError = ref(false), busy = ref(false), uncertain = ref(false), submitError = ref('')
const locked = computed(() => busy.value || uncertain.value || props.receipt.status === '已付款')
const pageSize = 12
const kinds = [{ label: '全部', value: 'all' }, { label: '产出回收', value: 'output' }, { label: '配件退料', value: 'material' }]
const weightUnits = [{ label: 'g', value: 'g' }, { label: 'kg', value: 'kg' }]
const kindLabel = row => !row.is_output ? '配件退料' : row.item_type !== 'part' ? '饰品产出' : row.is_composite ? '组合配件产出' : '配件产出'
const selectedKeys = computed(() => new Set(selected.value.map(sourceKey)))
const filtered = computed(() => filterAddReceiptSources(sources.value, {
  kind: kind.value, keyword: keyword.value, dateOn: tsToDateStr(dateOn.value), selectedOnly: selectedOnly.value, selectedKeys: selectedKeys.value,
}))
const pageRows = computed(() => filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize))
const allPageSelected = computed(() => pageRows.value.length > 0 && pageRows.value.every(row => selectedKeys.value.has(sourceKey(row))))
const somePageSelected = computed(() => pageRows.value.some(row => selectedKeys.value.has(sourceKey(row))))
const summary = computed(() => summarizeHandcraftReceipt(selected.value, inputs))
const lineAmount = row => handcraftReceiptLineAmount(inputs[sourceKey(row)])
const overBy = row => Math.max(0, Number(((inputs[sourceKey(row)].qty || 0) - remainingQuantity(row)).toFixed(4)))
watch([kind, keyword, dateOn, selectedOnly], () => { page.value = 1 })
watch(() => filtered.value.length, count => { page.value = Math.min(page.value, Math.max(1, Math.ceil(count / pageSize))) })

let active = true
async function loadSources() {
  if (loading.value) return
  loading.value = true
  loadError.value = false
  try {
    const { data } = await listHandcraftPendingReceiveItems(handcraftReceiptSourceParams(props.receipt))
    if (active) sources.value = data
  } catch {
    if (active) loadError.value = true
  } finally {
    if (active) loading.value = false
  }
}

function toggle(row, checked) {
  if (locked.value) return
  const key = sourceKey(row)
  if (checked && !selectedKeys.value.has(key)) {
    inputs[key] = createHandcraftReceiptInput(row)
    selected.value.push(row)
  } else if (!checked) {
    selected.value = selected.value.filter(item => sourceKey(item) !== key)
    delete inputs[key]
  }
  submitError.value = ''
}
function togglePage(checked) {
  for (const row of pageRows.value) toggle(row, checked)
}
function clearSelection() {
  for (const row of selected.value) toggle(row, false)
}
function clearFilters() {
  keyword.value = ''; dateOn.value = null; kind.value = 'all'; selectedOnly.value = false
}
function requestClose() {
  if (busy.value || uncertain.value) return
  if (!selected.value.length) return emit('close')
  dialog.warning({ title: '放弃本次添加？', content: '已选回收项尚未保存，关闭后将清空待添加清单。', positiveText: '放弃添加', negativeText: '继续填写', onPositiveClick: () => emit('close') })
}

async function submit() {
  if (locked.value || loading.value || loadError.value || !selected.value.length) return
  submitError.value = ''
  let payload
  try {
    payload = additionalReceiptPayload(selected.value, inputs)
  } catch (error) {
    submitError.value = error.message
    return
  }
  busy.value = true
  try {
    const { data } = await addHandcraftReceiptItems(props.receipt.id, payload)
    if (active) emit('saved', data, selected.value.length)
  } catch (error) {
    if (!active) return
    const status = error?.response?.status
    if ([400, 401, 403, 404, 409, 422].includes(status)) {
      const detail = error.response.data?.detail
      submitError.value = typeof detail === 'string' ? detail : '添加失败，请核对来源及填写的明细。'
    } else {
      uncertain.value = true
    }
  } finally {
    busy.value = false
  }
}

async function verify() {
  if (busy.value || !uncertain.value) return
  busy.value = true
  try {
    const { data } = await getHandcraftReceipt(props.receipt.id)
    if (active) emit('verified', data)
  } catch {
    if (active) submitError.value = '刷新明细失败，请稍后重试。'
  } finally {
    busy.value = false
  }
}

function guardNavigation() {
  if (busy.value) { message.warning('正在处理回收项，请稍候'); return false }
}
onBeforeRouteLeave(guardNavigation)
onBeforeRouteUpdate(guardNavigation)
onMounted(loadSources)
onBeforeUnmount(() => { active = false })
</script>

<style scoped>
.receipt-picker { width: min(1100px, calc(100vw - 24px)); max-height: calc(100dvh - 24px); }
.receipt-picker :deep(.n-card__content) { min-height: 0; overflow-y: auto; }
.rp-intro { margin: 0 0 16px; font-size: 13px; color: #616b72; }
.rp-intro strong { color: #1e7a5a; }
.rp-alert { margin-bottom: 12px; }
.rp-split { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr); border: 1px solid #e6ebed; border-radius: 9px; overflow: hidden; }
.rp-catalog, .rp-drafts { min-width: 0; padding: 14px; }
.rp-drafts { border-left: 1px solid #e6ebed; background: #f8faf9; }
.rp-panel-head, .rp-list-tools, .rp-draft header, .rp-row-tools, .rp-footer { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.rp-panel-head { min-height: 26px; margin-bottom: 10px; }
.rp-panel-head h3 { margin: 0; font-size: 14px; }
.rp-panel-head span { font-size: 12px; color: #626d74; font-weight: normal; }
.rp-filters { display: grid; grid-template-columns: minmax(0, 1fr) minmax(120px, .58fr); gap: 8px; margin-bottom: 6px; }
.rp-types { display: flex; gap: 14px; border-bottom: 1px solid #e6ebed; }
.rp-types button { margin-bottom: -1px; padding: 7px 2px; border: 0; border-bottom: 2px solid transparent; color: #626d74; background: none; font: inherit; font-size: 13px; cursor: pointer; }
.rp-types button[aria-pressed='true'] { color: #1e7a5a; border-bottom-color: #1e7a5a; font-weight: 600; }
.rp-types button:disabled { cursor: default; opacity: .6; }
.rp-types button:focus-visible { outline: 2px solid #1e7a5a; outline-offset: -2px; }
.rp-list-tools { margin: 10px 0 8px; font-size: 12px; }
.rp-source-list, .rp-draft-list { max-height: min(46vh, 500px); overflow-y: auto; }
.rp-source-list :deep(.n-empty), .rp-draft-list :deep(.n-empty) { padding: 26px 8px; }
.rp-source { display: grid; grid-template-columns: auto 42px minmax(0, 1fr) minmax(0, auto); align-items: center; gap: 9px; padding: 9px 7px; border: 1px solid transparent; border-bottom-color: #eef1f0; cursor: pointer; }
.rp-source:hover { background: #f5f9f7; }
.rp-source.is-selected { background: #eaf5ef; border-color: #cde3d8; border-radius: 6px; }
.rp-source input { margin: 0; accent-color: #1e7a5a; width: 16px; height: 16px; }
.rp-source img, .rp-image-placeholder { width: 42px; height: 42px; object-fit: cover; border-radius: 6px; }
.rp-image-placeholder { display: grid; place-items: center; background: #eef1f0; color: #6b7b74; }
.rp-source-copy, .rp-balance { display: grid; gap: 2px; min-width: 0; overflow-wrap: anywhere; }
.rp-source-copy small, .rp-balance small, .rp-row-tools { font-size: 11px; color: #626d74; }
.rp-balance { text-align: right; max-width: 102px; }
.rp-balance strong { color: #1e7a5a; font-size: 12px; font-variant-numeric: tabular-nums; }
.rp-pagination { display: flex; justify-content: flex-end; margin-top: 9px; }
.rp-draft { padding: 12px; border: 1px solid #e6ebed; border-radius: 8px; background: #fff; margin-bottom: 8px; }
.rp-draft header { flex-wrap: nowrap; }
.rp-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 10px; }
.rp-fields > * { display: grid; gap: 4px; align-content: start; min-width: 0; }
.rp-fields span { font-size: 11px; color: #626d74; }
.rp-amount strong { color: #1e7a5a; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.rp-row-tools { margin-top: 7px; }
.rp-row-tools .rp-over { color: #9c510d; }
.rp-weight { display: grid; grid-template-columns: minmax(0, 140px) 74px; gap: 8px; margin-top: 6px; }
.rp-footer { font-size: 12px; }
.rp-footer span { color: #626d74; }
@media (max-width: 760px) {
  .receipt-picker :deep(.n-card__content), .receipt-picker :deep(.n-card__footer) { padding-left: 12px; padding-right: 12px; }
  .rp-split { grid-template-columns: minmax(0, 1fr); }
  .rp-catalog, .rp-drafts { padding: 10px; }
  .rp-drafts { border-left: 0; border-top: 1px solid #e6ebed; }
  .rp-source-list { max-height: 250px; }
  .rp-draft-list { max-height: none; overflow: visible; }
  .rp-source { grid-template-columns: auto 32px minmax(0, 1fr) minmax(0, auto); gap: 6px; padding-inline: 2px; }
  .rp-source img, .rp-image-placeholder { width: 32px; height: 32px; }
  .rp-balance { max-width: 74px; }
  .rp-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .rp-amount { grid-column: 1 / -1; grid-template-columns: auto 1fr; align-items: baseline; }
  .rp-footer > :last-child { margin-left: auto; }
}
</style>
