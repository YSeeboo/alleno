<template>
  <n-modal :show="true" preset="card" title="从其他饰品复制用料" class="jbc-modal"
    style="width: min(920px, calc(100vw - 24px)); max-height: calc(100dvh - 24px)"
    :content-style="{ display: 'flex', flexDirection: 'column', minHeight: 0 }"
    :mask-closable="false" :close-on-esc="!busy" :closable="!busy"
    @update:show="show => { if (!show && !busy) emit('close') }">
    <div class="jbc-body">
      <p class="jbc-intro">选择来源饰品，核对配件和用量，再添加到当前 BOM。不复制售价、手工费或库存，也不会同步来源的后续改动。</p>
      <div class="jbc-target">
        <span class="jbc-tag is-green">复制到</span>
        <div><strong>{{ target.name }}</strong><small>{{ target.id }} · {{ unitBasis(targetUnit) }}</small></div>
        <span class="jbc-count">当前 BOM {{ targetRows.length }} 项</span>
      </div>

      <div class="jbc-panels">
        <section class="jbc-source" aria-labelledby="jbc-source-title">
          <header class="jbc-panel-head"><h3 id="jbc-source-title">选择来源饰品</h3></header>
          <n-input v-model:value="query" clearable autofocus :maxlength="120" :disabled="busy" placeholder="搜索饰品名称 / 编号" :input-props="{ 'aria-label': '搜索来源饰品' }" />
          <div ref="sourceList" class="jbc-source-list" :aria-busy="searchLoading">
            <p v-if="searchLoading" class="jbc-empty" role="status">正在加载来源饰品…</p>
            <n-alert v-else-if="searchError" type="error">来源饰品加载失败。<n-button text type="primary" :disabled="busy" @click="searchNow">重试</n-button></n-alert>
            <p v-else-if="!sources.length" class="jbc-empty">{{ query.trim() ? '没有匹配的饰品，试试其他名称或编号。' : '没有可选的来源饰品。' }}</p>
            <button v-for="source in sources" v-else :key="source.id" type="button" class="jbc-source-option"
              :aria-pressed="source.id === selectedId" :disabled="busy" @click="chooseSource(source.id)">
              <span><strong>{{ source.name }}</strong><small>{{ source.id }} · {{ unitBasis(source.unit) }}{{ source.status === 'inactive' ? ' · 已停用' : '' }}</small></span>
              <span class="jbc-tag">{{ source.part_count }} 项</span>
            </button>
          </div>
          <div v-if="offset || hasMore" class="jbc-pages"><n-button text :disabled="busy || searchLoading || !offset" @click="changePage(-1)">上一页</n-button><span>第 {{ offset / pageSize + 1 }} 页</span><n-button text :disabled="busy || searchLoading || !hasMore" @click="changePage(1)">下一页</n-button></div>
        </section>

        <section class="jbc-preview" aria-labelledby="jbc-preview-title" :aria-busy="previewLoading">
          <header class="jbc-panel-head"><h3 id="jbc-preview-title">核对待添加用料</h3><small v-if="preview">{{ preview.source.name }} · {{ unitBasis(preview.source.unit) }}</small></header>
          <p class="jbc-policy"><strong>已有配件不会覆盖</strong> 按配件编号判断重复，保留当前 BOM 的原用量。</p>
          <n-alert v-if="needsUnitCheck && draft.length > skipped" class="jbc-unit" type="warning" :show-icon="false">
            来源{{ unitBasis(preview.source.unit) }}，目标{{ unitBasis(preview.target_unit) }}。不会自动换算，请按目标饰品的计量基准核对用量。
            <n-checkbox v-model:checked="unitConfirmed" :disabled="busy">已逐项核对，用量按目标饰品填写</n-checkbox>
          </n-alert>
          <p v-if="previewLoading" class="jbc-empty" role="status">正在加载来源用料…</p>
          <n-alert v-else-if="previewError" type="error">{{ previewError }} <n-button text type="primary" :disabled="busy" @click="loadPreview(selectedId)">重新加载</n-button></n-alert>
          <p v-else-if="!preview" class="jbc-empty">请选择来源饰品，选中后会在这里预填配件与用量。</p>
          <p v-else-if="!draft.length" class="jbc-empty">该饰品还没有 BOM 用料，请选择另一款饰品。</p>
          <div v-else class="jbc-rows">
            <div v-for="row in draft" :key="row.partId" class="jbc-row">
              <label class="jbc-row-label">
                <input v-model="row.selected" type="checkbox" :disabled="busy || row.existing" :aria-label="`选择 ${row.partName} ${row.partId}`" />
                <span><strong>{{ row.partName }}</strong><small>{{ row.partId }}{{ row.color ? ` · ${row.color}` : '' }}</small></span>
              </label>
              <div v-if="row.existing" class="jbc-skip"><span class="jbc-tag">跳过</span><small>当前 {{ row.targetQty }}{{ row.partUnit }} · 来源 {{ row.sourceQty }}{{ row.partUnit }}</small></div>
              <label v-else class="jbc-qty">
                <input v-model="row.quantity" type="text" inputmode="decimal" :disabled="busy || !row.selected" :aria-label="`${row.partName} ${row.partId} 每单位用量`" :aria-invalid="row.selected && !validBomQuantity(row.quantity)" />
                <span>{{ row.partUnit || '—' }}</span>
              </label>
            </div>
          </div>
        </section>
      </div>
    </div>

    <div v-if="saveError" class="jbc-save-error"><n-alert type="error">{{ saveError }} <n-button text type="primary" :disabled="busy || previewLoading" @click="loadPreview(selectedId)">重新加载来源用料</n-button></n-alert></div>
    <footer class="jbc-footer">
      <div role="status"><strong>待添加 {{ selected.length }} 项{{ skipped ? ` · 跳过 ${skipped} 项` : '' }}</strong><small>{{ footerNote }}</small></div>
      <div class="jbc-actions">
        <n-button :disabled="busy" @click="emit('close')">取消</n-button>
        <n-button type="primary" :loading="busy" :disabled="!allowed || busy || !!saveError || !payload" @click="submit">添加到当前 BOM</n-button>
      </div>
    </footer>
  </n-modal>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { NAlert, NButton, NCheckbox, NInput, NModal } from 'naive-ui'
import { listBomCopySources, previewBomCopy } from '@/api/bom'
import { validBomQuantity } from '@/utils/jewelryDetail'
import { bomCopyNeedsUnitCheck, bomCopyPayload, makeBomCopyDraft } from '@/utils/jewelryBomCopy'

const props = defineProps({
  target: { type: Object, required: true }, targetRows: { type: Array, required: true },
  partMap: { type: Object, required: true }, allowed: Boolean, busy: Boolean, saveError: String,
})
const emit = defineEmits(['close', 'save', 'clear-error'])
const pageSize = 24
const query = ref(''), offset = ref(0), hasMore = ref(false), sourceList = ref(null)
const sources = ref([]), searchLoading = ref(true), searchError = ref(false)
const selectedId = ref(''), preview = ref(null), draft = ref([]), previewLoading = ref(false), previewError = ref('')
const unitConfirmed = ref(false)
let searchSeq = 0, previewSeq = 0
const targetUnit = computed(() => preview.value ? preview.value.target_unit : props.target.unit)
const unitBasis = unit => unit?.trim() ? `按每 1 ${unit}计量` : '计量单位未设置'
const needsUnitCheck = computed(() => preview.value && bomCopyNeedsUnitCheck(preview.value.source.unit, targetUnit.value))
const selected = computed(() => draft.value.filter(row => row.selected && !row.existing))
const skipped = computed(() => draft.value.filter(row => row.existing).length)
const payload = computed(() => bomCopyPayload(preview.value, draft.value, unitConfirmed.value))
const footerNote = computed(() => {
  if (!props.allowed && !props.busy) return '当前无法添加，请关闭后核对页面'
  if (previewLoading.value) return '正在加载来源用料'
  if (previewError.value) return '请重新加载来源用料'
  if (!preview.value) return '先选择来源饰品'
  if (!draft.value.length) return '来源暂无用料'
  if (skipped.value === draft.value.length) return '目标已包含全部配件，无需添加'
  if (!selected.value.length) return '请至少勾选 1 项'
  if (selected.value.some(row => !validBomQuantity(row.quantity))) return '用量须大于 0，最多 4 位小数且小于 1000000'
  if (needsUnitCheck.value && !unitConfirmed.value) return '请先核对计量单位'
  return targetUnit.value?.trim() ? `用量按目标每 1 ${targetUnit.value}填写` : '用量按目标饰品计量基准填写'
})

async function search(seq, keyword, start) {
  try {
    const { data } = await listBomCopySources(props.target.id, { q: keyword, offset: start, limit: pageSize })
    if (seq !== searchSeq) return
    sources.value = data.items
    hasMore.value = data.has_more
    if (sourceList.value) sourceList.value.scrollTop = 0
  } catch {
    if (seq === searchSeq) searchError.value = true
  } finally {
    if (seq === searchSeq) searchLoading.value = false
  }
}
function startSearch() {
  searchLoading.value = true; searchError.value = false
  return ++searchSeq
}
function searchNow() { return search(startSearch(), query.value.trim(), offset.value) }
watch(query, (keyword, _old, onCleanup) => {
  offset.value = 0; hasMore.value = false
  const seq = startSearch()
  const timer = setTimeout(() => search(seq, keyword.trim(), 0), 200)
  onCleanup(() => clearTimeout(timer))
})
function changePage(delta) {
  offset.value += delta * pageSize
  searchNow()
}

function chooseSource(id) {
  if (props.busy || (selectedId.value === id && !previewError.value)) return
  loadPreview(id)
}
async function loadPreview(id) {
  if (props.busy || !id) return
  const seq = ++previewSeq
  selectedId.value = id; preview.value = null; draft.value = []; unitConfirmed.value = false
  previewError.value = ''; previewLoading.value = true
  emit('clear-error')
  try {
    const { data } = await previewBomCopy(props.target.id, id)
    if (seq !== previewSeq) return
    preview.value = data
    draft.value = makeBomCopyDraft(data.rows, props.targetRows, props.partMap)
  } catch (error) {
    if (seq === previewSeq) previewError.value = error.response?.status === 404 ? '饰品不存在，请刷新或重新选择来源。' : '来源用料加载失败，未按空 BOM 处理。'
  } finally {
    if (seq === previewSeq) previewLoading.value = false
  }
}
function submit() {
  if (props.allowed && !props.busy && !props.saveError && payload.value) emit('save', payload.value, skipped.value)
}
searchNow()
onBeforeUnmount(() => { searchSeq++; previewSeq++ })
</script>

<style scoped>
.jbc-body { min-height: 0; overflow: auto; }
.jbc-intro { margin: 0 0 12px; color: #5e6b65; font-size: 13px; }
.jbc-target, .jbc-panel-head, .jbc-footer, .jbc-actions, .jbc-pages { display: flex; align-items: center; gap: 8px; }
.jbc-target { flex-wrap: wrap; margin-bottom: 12px; padding: 8px 11px; border: 1px solid #e3ebe7; border-radius: 6px; background: #f5f8f6; overflow-wrap: anywhere; }
.jbc-count { margin-left: auto; color: #5e6b65; font-size: 12px; }
.jbc-tag { display: inline-block; padding: 2px 6px; border-radius: 4px; background: #eef1f0; color: #53645c; font-size: 11px; white-space: nowrap; }
.jbc-tag.is-green { background: #e7f3ec; color: #166048; }
.jbc-panels { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.7fr); border: 1px solid #e6eaec; border-radius: 8px; }
.jbc-source, .jbc-preview { min-width: 0; padding: 12px; }
.jbc-preview { border-left: 1px solid #e6eaec; }
.jbc-panel-head { justify-content: space-between; min-height: 22px; margin-bottom: 8px; }
.jbc-panel-head h3 { flex: none; margin: 0; font-size: 13px; }
.jbc-panel-head small { text-align: right; overflow-wrap: anywhere; }
small { display: block; margin-top: 2px; color: #5e6b65; font-size: 11px; }
.jbc-source-list, .jbc-rows { max-height: 42vh; overflow: auto; }
.jbc-source-list { display: grid; gap: 5px; margin-top: 6px; padding: 2px; }
.jbc-source-option { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px; align-items: center; padding: 7px; border: 1px solid #e4e9e6; border-radius: 5px; background: #fff; color: inherit; font: inherit; font-size: 13px; text-align: left; cursor: pointer; overflow-wrap: anywhere; }
.jbc-source-option[aria-pressed=true] { background: #eff7f2; border-color: #86b29f; }
.jbc-source-option:hover:not(:disabled) { border-color: #86b29f; }
.jbc-source-option:disabled { cursor: default; }
.jbc-source-option:focus-visible { outline: 2px solid #1e7a5a; }
.jbc-pages { justify-content: space-between; margin: 6px 2px 0; color: #5e6b65; font-size: 11px; }
.jbc-policy { margin: 0 0 6px; padding: 6px 8px; border-radius: 5px; color: #166048; background: #edf6f1; font-size: 12px; }
.jbc-unit { margin-bottom: 6px; }
.jbc-unit :deep(.n-checkbox) { display: flex; margin-top: 4px; }
.jbc-empty { margin: 14px 0; padding: 8px; text-align: center; color: #5e6b65; font-size: 13px; }
.jbc-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 6px; padding: 7px 2px; border-bottom: 1px solid #edf0ee; font-size: 13px; }
.jbc-row:last-child { border-bottom: 0; }
.jbc-row-label, .jbc-qty { display: flex; gap: 5px; align-items: center; min-width: 0; overflow-wrap: anywhere; }
.jbc-row-label input { flex: none; accent-color: #1e7a5a; }
.jbc-qty { font-size: 11px; }
.jbc-qty input { width: 72px; padding: 5px; border: 1px solid #dce3df; border-radius: 5px; color: inherit; font: inherit; font-size: 13px; }
.jbc-qty input[aria-invalid=true] { border-color: #b53a33; }
.jbc-skip { text-align: right; max-width: 155px; overflow-wrap: anywhere; }
.jbc-save-error { margin-top: 8px; }
.jbc-footer { flex: none; justify-content: space-between; border-top: 1px solid #edf0ee; margin-top: 10px; padding-top: 10px; }
.jbc-footer strong { color: #166048; font-size: 13px; }
.jbc-actions { flex: none; margin-left: auto; }
@media (max-width: 680px) {
  .jbc-panels { grid-template-columns: minmax(0, 1fr); }
  .jbc-preview { border-left: 0; border-top: 1px solid #e6eaec; }
  .jbc-source-list { max-height: 230px; }
  .jbc-rows { max-height: none; overflow: visible; }
  .jbc-footer { flex-wrap: wrap; }
  .jbc-modal { --n-padding-left: 12px !important; --n-padding-right: 12px !important; }
}
</style>
