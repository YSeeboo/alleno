<template>
  <div class="handcraft-output">
    <header class="ho-head"><div><div class="ho-eyebrow">OUTPUT OVERVIEW</div><h2>产出总览</h2><p>交给谁做了什么，收回多少，还差多少。</p></div><n-button size="small" @click="showRules = true">ⓘ 统计口径</n-button></header>
    <section class="ho-filters" aria-label="产出查询条件">
      <div class="ho-filter-grid">
        <div class="ho-filter-field"><span>手工商家 <small>可多选</small></span><n-select :value="query.suppliers || []" :options="supplierOptions" multiple filterable clearable :max-tag-count="1" :loading="optionsLoading" placeholder="全部商家" aria-label="手工商家" @update:value="setSelection('suppliers', $event)" /></div>
        <div class="ho-filter-field"><span>产出商品 <small>可多选</small></span><n-select :value="query.outputs || []" :options="productOptions" multiple filterable remote clearable :max-tag-count="1" :loading="optionsLoading" placeholder="搜索名称 / 商品编号" aria-label="产出商品" @search="searchProducts" @update:value="setSelection('outputs', $event)" /></div>
        <div class="ho-filter-field"><span>回收进度</span><n-select :value="query.progress || 'all'" :options="progressOptions" aria-label="回收进度" @update:value="setFilter('progress', $event)" /></div>
        <div class="ho-filter-field"><span>单据范围</span><n-select :value="query.archive || 'active'" :options="archiveOptions" aria-label="单据范围" @update:value="setFilter('archive', $event)" /></div>
      </div>
      <div v-if="optionsError" class="ho-option-error" role="alert">{{ optionsError }} <n-button text size="tiny" @click="loadOptions">重新加载选项</n-button></div>
      <p v-else-if="hasMoreOptions" class="ho-option-hint">产出选项仅显示前 50 款，请输入名称或编号缩小范围；已选项始终保留。</p>
      <div class="ho-dates"><span>发出日期</span><div class="ho-presets" role="group" aria-label="发出日期快捷范围"><button v-for="preset in presets" :key="preset.value" :aria-pressed="(query.date_preset || 'all') === preset.value" @click="setPreset(preset.value)">{{ preset.label }}</button></div><small v-if="query.date_preset && query.date_preset !== 'custom'">{{ filters.date_from }} — {{ filters.date_to }}</small><n-button text size="tiny" @click="reset">重置筛选</n-button></div>
      <n-date-picker v-if="query.date_preset === 'custom'" :formatted-value="dateRange" value-format="yyyy-MM-dd" type="daterange" clearable start-placeholder="开始发出日期" end-placeholder="结束发出日期" aria-label="自定义发出日期范围" class="ho-date-picker" @update:formatted-value="setDateRange" />
      <p v-if="dateError" class="ho-error" role="alert">{{ dateError }}</p>
      <div v-if="query.suppliers?.length || query.outputs?.length" class="ho-chips"><span>已选条件</span><button v-for="name in query.suppliers || []" :key="`supplier:${name}`" :aria-label="`移除商家${name}筛选`" @click="removeSelection('suppliers', name)">{{ name }} ×</button><button v-for="key in query.outputs || []" :key="key" :aria-label="`移除产出${productLabel(key)}筛选`" @click="removeSelection('outputs', key)">{{ productLabel(key) }} ×</button></div>
    </section>
    <p class="ho-scope">ⓘ 按发出日期选取制作任务，<strong>累计实收包含这些任务截至当前的全部回收</strong>，不受回收月份限制。</p>
    <p class="ho-date-caveat">历史记录缺少实际发出时间时，使用并标注「单据日期参考」，不视为准确发出日，不回填历史。</p>
    <n-alert v-if="data?.reference_date_count" type="warning" :show-icon="false" class="ho-reference-alert">当前筛选含 {{ data.reference_date_count }} 条日期参考来源，日期范围也会按其手工单日期筛选；请展开核对。</n-alert>
    <section class="ho-metrics" aria-label="当前筛选数量汇总"><article v-for="metric in OUTPUT_METRICS" :key="metric.key" :class="{ 'ho-remaining': metric.key === 'unreceived_qty' }"><span class="ho-metric-label">{{ metric.label }}</span><div class="ho-metric-values"><template v-if="data?.totals.length"><strong v-for="total in data.totals" :key="total.unit">{{ outputQuantity(total[metric.key]) }}<small>{{ outputUnit(total.unit) }}</small></strong></template><strong v-else>{{ data ? '0' : '—' }}</strong></div><p>{{ metric.note }}</p></article></section>
    <section class="ho-results" aria-label="产出查询结果">
      <header class="ho-result-head"><div><h3>产出明细 <span v-if="data">{{ data.total }} {{ view === 'merchant' ? '位商家' : '款产出' }}</span></h3><p role="status" aria-live="polite">{{ loading ? '正在查询…' : data ? `${data.supplier_count} 位商家 · ${data.output_count} 款产出 · ${data.source_count} 条制作来源，数量按单位分开统计` : '查询未完成，不展示旧数据。' }}</p></div><div class="ho-view" role="group" aria-label="结果视角"><button :aria-pressed="view === 'merchant'" @click="setFilter('view', 'merchant')">按商家看</button><button :aria-pressed="view === 'product'" @click="setFilter('view', 'product')">按产出看</button></div></header>
      <div class="ho-result-tools"><span>同款按商家、单位汇总 · 展开追溯独立来源</span><div><n-button text size="tiny" :disabled="!data || pageItemCount > 20" @click="toggleAllSources">{{ allExpanded ? '收起本页来源' : '展开本页来源' }}</n-button><n-button text size="tiny" :disabled="loading" @click="refresh">刷新</n-button></div></div>
      <p v-if="data && pageItemCount > 20" class="ho-option-hint">本页产出较多，请逐行展开，或先筛选至 20 行以内再批量展开。</p>
      <div v-if="error" class="ho-error" role="alert">{{ error }} <n-button size="small" @click="load">重试</n-button></div>
      <n-spin :show="loading">
        <section v-for="group in data?.groups || []" :key="group.key" class="ho-group">
          <button class="ho-group-head" :aria-expanded="!collapsed[group.key]" @click="collapsed[group.key] = !collapsed[group.key]"><span class="ho-group-title"><span class="ho-avatar">{{ groupTitle(group).slice(0, 1) }}</span><span><strong>{{ groupTitle(group) }}</strong><small>{{ view === 'merchant' ? `${new Set(group.items.map(item => item.output_key)).size} 款产出` : `${new Set(group.items.map(item => item.supplier_name)).size} 位商家` }} · {{ group.source_count }} 条来源</small></span></span><span class="ho-group-state">{{ group.pending_source_count ? `${group.pending_source_count} 条来源待收齐` : '所有来源已结清' }} <span>{{ collapsed[group.key] ? '⌄' : '⌃' }}</span></span></button>
          <table v-if="!collapsed[group.key]" class="ho-table"><caption class="ho-sr-only">{{ groupTitle(group) }}产出与回收进度</caption><thead><tr><th>{{ view === 'merchant' ? '产出商品 / 来源' : '制作商家 / 来源' }}</th><th>已发出制作</th><th>累计实收</th><th>已确认损耗</th><th>尚未收回</th><th>回收进度</th></tr></thead><tbody><template v-for="item in group.items" :key="outputItemKey(item)">
            <tr class="ho-item"><td><button class="ho-item-toggle" :aria-expanded="!!expanded[outputItemKey(item)]" @click="toggleItem(item)"><span class="ho-chevron">{{ expanded[outputItemKey(item)] ? '⌄' : '›' }}</span><span v-if="view === 'merchant'" class="ho-image"><n-image v-if="item.output_image" :src="item.output_image" :alt="item.output_name || item.output_id" :width="32" :height="32" object-fit="contain" preview-disabled /><span v-else>◇</span></span><span class="ho-item-name"><strong>{{ view === 'merchant' ? item.output_name || item.output_id : item.supplier_name }}</strong><small>{{ view === 'merchant' ? `${item.output_id} · ${item.output_type === 'part' ? '产出配件' : '饰品'}` : item.output_id }} · {{ item.source_count }} 条来源<span v-if="item.reference_date_count"> · 含日期参考</span></small></span></button></td>
            <td v-for="metric in OUTPUT_METRICS" :key="metric.key" :data-label="metric.label"><span class="ho-quantity" :class="{ 'ho-outstanding': metric.key === 'unreceived_qty' && item.unreceived_qty > 0 }">{{ outputQuantity(item[metric.key]) }}<small>{{ outputUnit(item.unit) }}</small></span></td>
            <td class="ho-progress-cell" data-label="回收进度"><div class="ho-progress"><div><span class="ho-status" :class="outputStatus(item)">{{ OUTPUT_STATUS[outputStatus(item)] }}</span><small>实收 {{ outputPercent(item) }}%</small></div><progress :max="item.expected_qty || 1" :value="item.actual_received_qty" :aria-label="`实收比例 ${outputPercent(item)}%`"></progress></div></td></tr>
            <tr v-if="expanded[outputItemKey(item)]" class="ho-sources"><td colspan="6"><HandcraftOutputSources :item="item" :filters="filters" @open-page="openPage" /></td></tr>
          </template></tbody></table>
        </section>
        <div v-if="!loading && data && !data.groups.length" class="ho-empty"><span>⌕</span><h3>没有符合条件的产出</h3><p>可以清除商品选择，或扩大日期、单据范围。</p><n-button size="small" @click="reset">重置全部筛选</n-button></div>
      </n-spin>
      <div v-if="data && data.total > 10" class="ho-pager"><span>按{{ view === 'merchant' ? '商家' : '产出' }}分组分页 · 上方数量为全部筛选结果</span><n-pagination :page="page" :page-count="Math.max(1, Math.ceil(data.total / 10))" :page-slot="3" :disabled="loading" @update:page="updateQuery({ page: String($event) }, false)" /></div>
    </section>
    <footer class="ho-foot"><span>只读查询 · 待发出草稿不纳入</span><span>数量沿用来源单位，不同单位分别统计，不做换算。</span></footer>
    <n-modal v-model:show="showRules" preset="card" title="统计口径" class="handcraft-output-rules"><div class="ho-rules-copy"><h3>看发出任务的当前进度</h3><p>仅纳入已发出的制作任务，不含待发出草稿。日期只限定任务发出范围；累计实收包含任务截至当前的全部真实回收，包括其他月份的回收。</p><dl><template v-for="metric in OUTPUT_METRICS" :key="metric.key"><dt>{{ metric.label }}</dt><dd>{{ metric.note }}</dd></template></dl><p>尚未收回逐来源计算 max(预期产出 − 累计实收 − 已确认损耗, 0)，再按相同单位汇总。旧回收计数、材料退回和自动耗料均不充当真实实收。</p><h3>筛选与汇总</h3><p>商家、产出不选即全部；同类多选取并集，商家与产出之间取交集。回收进度先筛来源，再汇总结果。</p><p>尚未收回：实收为 0 且仍有余量；部分收回：已有实收且仍有余量；已结清：实收加损耗覆盖预期，不代表全部实收。</p><p>同款只汇总展示，底层来源保持独立；同款不同单位分行，不跨单位计算总数量或总进度。数量按来源单位记录，展开保留回收批次原单位；如单位不同应核对原单，页面不推测换算。</p><h3>日期依据</h3><p>新发出的产出记录实际发出时间；制作中追加的产出从追加时计入制作任务。历史来源没有可靠发出时间时，使用手工单日期参考并明确标注，不猜测回填。</p><p>本周从北京时间周一开始；本月、上月按北京时间自然月。默认全部时间。历史缺失日期仅在全部时间可见。</p><h3>分页与来源核对</h3><p>主列表按商家或产出分组分页，上方数量始终统计全部筛选结果，不是本页小计。来源和回收批次独立分页；来源可跳转到手工单、回收单，并返回保留条件的产出总览。</p></div></n-modal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NAlert, NButton, NDatePicker, NImage, NModal, NPagination, NSelect, NSpin } from 'naive-ui'
import HandcraftOutputSources from '@/components/HandcraftOutputSources.vue'
import { getHandcraftOutputOverview, getHandcraftOutputOptions } from '@/api/handcraftOutput'
import { useHandcraftPageQuery } from '@/composables/useHandcraftPageQuery'
import { rememberHandcraftLocation } from '@/utils/handcraftNavigation'
import { OUTPUT_METRICS, OUTPUT_STATUS, beijingToday, outputDateError, outputDateRange, outputFilters, outputItemKey, outputPercent, outputQuantity, outputStatus, outputUnit } from '@/utils/handcraftOutput'

defineProps({ embedded: { type: Boolean, default: false } })
const { route, active, query, updateQuery } = useHandcraftPageQuery('output')
const router = useRouter()
const today = ref(beijingToday()), data = ref(null), loading = ref(false), error = ref(''), showRules = ref(false)
const optionsLoading = ref(false), optionsError = ref(''), suppliers = ref([]), outputs = ref([]), hasMoreOptions = ref(false)
const productNames = ref({}), expanded = ref({}), collapsed = ref({})
const view = computed(() => query.value.view || 'merchant'), page = computed(() => Number(query.value.page || 1))
const filters = computed(() => outputFilters(query.value, today.value))
const dateError = computed(() => outputDateError(query.value))
const dateRange = computed(() => query.value.date_from && query.value.date_to ? [query.value.date_from, query.value.date_to] : null)
const supplierOptions = computed(() => [...new Set([...suppliers.value, ...(query.value.suppliers || [])])].map(value => ({ label: value, value })))
const productOptions = computed(() => [...new Set([...outputs.value.map(item => item.output_key), ...(query.value.outputs || [])])].map(value => ({ label: productLabel(value), value })))
const pageItems = computed(() => data.value?.groups.flatMap(group => group.items) || [])
const pageItemCount = computed(() => pageItems.value.length)
const allExpanded = computed(() => !!pageItems.value.length && pageItems.value.every(item => expanded.value[outputItemKey(item)]))
const progressOptions = [{ value: 'all', label: '全部进度' }, { value: 'unreceived', label: '尚未收回（实收为 0）' }, { value: 'partial', label: '部分收回' }, { value: 'settled', label: '已结清' }]
const archiveOptions = [{ value: 'active', label: '正常单据' }, { value: 'archived', label: '历史归档' }, { value: 'all', label: '全部（含归档）' }]
const presets = [{ value: 'all', label: '全部时间' }, { value: 'week', label: '本周' }, { value: 'month', label: '本月' }, { value: 'lastMonth', label: '上月' }, { value: 'custom', label: '自定义' }]
let disposed = false, version = 0, optionsVersion = 0, searchTimer, search = ''
function productLabel(key) { const item = productNames.value[key]; return item ? `${item.output_name || item.output_id} · ${item.output_id}（${item.output_type === 'jewelry' ? '饰品' : '配件'}）` : key }
function groupTitle(group) { return view.value === 'merchant' ? group.key : group.items[0]?.output_name || group.items[0]?.output_id || group.key }
function setFilter(key, value) { void updateQuery({ [key]: value }) }
function setSelection(key, values) { void updateQuery({ [key]: (values || []).slice(0, 100) }) }
function removeSelection(key, value) { void updateQuery({ [key]: query.value[key].filter(item => item !== value) }) }
function setPreset(value) {
  if (value === 'custom') {
    void updateQuery({ date_preset: 'custom', ...(query.value.date_from && query.value.date_to ? {} : outputDateRange('month', today.value)) })
  } else void updateQuery({ date_preset: value === 'all' ? null : value, date_from: null, date_to: null })
}
function setDateRange(value) { void updateQuery({ date_preset: value ? 'custom' : null, date_from: value?.[0] || null, date_to: value?.[1] || null }) }
function reset() { search = ''; clearTimeout(searchTimer); void updateQuery({ suppliers: null, outputs: null, progress: null, archive: null, date_preset: null, date_from: null, date_to: null, page: null }); void loadOptions() }
function toggleItem(item) { const key = outputItemKey(item); expanded.value[key] = !expanded.value[key] }
function toggleAllSources() { const open = !allExpanded.value; collapsed.value = {}; expanded.value = Object.fromEntries(pageItems.value.map(item => [outputItemKey(item), open])) }
async function openPage(path, detail = {}) {
  if (disposed || !active.value) return
  rememberHandcraftLocation({ path: route.path, query: route.query })
  await router.push({ path, query: { from: 'handcraft-output', ...detail } })
}
async function load() {
  const current = ++version
  data.value = null; error.value = ''; expanded.value = {}; collapsed.value = {}
  if (disposed || !active.value || dateError.value) { loading.value = false; return }
  loading.value = true
  try {
    const { data: result } = await getHandcraftOutputOverview({ ...filters.value, view: view.value, skip: (page.value - 1) * 10, limit: 10 })
    if (disposed || current !== version || !active.value) return
    const lastPage = Math.max(1, Math.ceil(result.total / 10))
    if (page.value > lastPage) { await updateQuery({ page: String(lastPage) }, false); return }
    data.value = result
  } catch (e) {
    if (!disposed && current === version && active.value) error.value = typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : '加载产出总览失败，请重试'
  } finally { if (!disposed && current === version) loading.value = false }
}
async function loadOptions() {
  const current = ++optionsVersion
  optionsLoading.value = true; optionsError.value = ''
  try {
    const { data: result } = await getHandcraftOutputOptions({ q: search, selected_keys: query.value.outputs || [] })
    if (disposed || current !== optionsVersion || !active.value) return
    suppliers.value = result.suppliers; outputs.value = result.outputs; hasMoreOptions.value = result.has_more
    result.outputs.forEach(item => { productNames.value[item.output_key] = item })
  } catch (e) {
    if (!disposed && current === optionsVersion && active.value) optionsError.value = '加载筛选选项失败，已选条件仍保留，可重试'
  } finally { if (!disposed && current === optionsVersion) optionsLoading.value = false }
}
function searchProducts(value) { search = value; optionsVersion++; clearTimeout(searchTimer); searchTimer = setTimeout(() => { void loadOptions() }, 250) }
function refresh() { today.value = beijingToday(); void load() }
function onFocus() { const date = beijingToday(); if (date !== today.value) { today.value = date; void load() } }
watch(() => route.fullPath, () => { if (active.value) void load() }, { flush: 'sync' })
watch(() => JSON.stringify(query.value.outputs || []), () => { clearTimeout(searchTimer); void loadOptions() })
onMounted(() => { void load(); void loadOptions(); window.addEventListener('focus', onFocus) })
onBeforeUnmount(() => { disposed = true; version++; optionsVersion++; clearTimeout(searchTimer); window.removeEventListener('focus', onFocus) })
</script>

<style scoped src="@/styles/handcraft-output.css"></style>
<style>
.handcraft-output-rules.n-card { width: min(620px, calc(100vw - 28px)); max-height: calc(100dvh - 32px); }
.handcraft-output-rules.n-card > .n-card__content, .handcraft-output-rules.n-card > .n-card-content { min-height: 0; overflow-y: auto; }
</style>
