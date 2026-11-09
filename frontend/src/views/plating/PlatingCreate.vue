<template>
  <div ref="pageEl" class="plating-create">
    <div class="pc-crumbs">生产 <span>/</span> 电镀发出 <span>/</span> 新建</div>
    <header class="pc-head">
      <div class="pc-title"><h1>新建电镀单</h1><span class="pc-badge">录入中</span></div>
      <button class="pc-btn" type="button" @click="router.back()"><ArrowBackOutline />返回列表</button>
    </header>
    <p class="pc-intro">填写电镀信息，添加本次发出的配件与电镀颜色。</p>

    <section aria-labelledby="pc-basic-title">
      <div class="pc-section-head">
        <h2 id="pc-basic-title">基本信息</h2>
        <span class="pc-section-note">创建后为待发出状态，可继续编辑</span>
      </div>
      <n-form label-placement="top" :show-feedback="false" class="pc-meta">
        <n-form-item label="电镀厂名称" required>
          <n-select
            v-model:value="supplierName" :options="supplierOptions" filterable tag
            placeholder="选择或输入电镀厂名称" @update:value="checkSameDayOrder"
          />
        </n-form-item>
        <n-form-item label="备注" class="pc-meta-note">
          <n-input v-model:value="note" placeholder="填写本次电镀要求、交期等（选填）" />
        </n-form-item>
        <n-form-item label="创建时间">
          <n-date-picker
            v-model:value="createdAtTs" type="date" clearable placeholder="不填则使用当前时间"
            @update:value="() => checkSameDayOrder(supplierName)"
          />
        </n-form-item>
      </n-form>
    </section>

    <n-alert
      v-if="mergeCandidate"
      type="warning"
      style="margin-bottom: 16px;"
      :title="`该厂家同日已有电镀单`"
    >
      <div style="margin-bottom: 8px;">
        <strong>{{ mergeCandidate.supplier_name }}</strong> 在 {{ mergeCandidate.created_at?.slice(0, 10) }} 已有电镀单
        <strong>{{ mergeCandidate.id }}</strong>（待发出）。是否将当前配件合并到该电镀单？
      </div>
      <n-space size="small">
        <n-button type="primary" size="small" :loading="merging" @click="doMerge">
          合并到 {{ mergeCandidate.id }}
        </n-button>
        <n-button size="small" @click="mergeCandidate = null">仍然新建</n-button>
      </n-space>
    </n-alert>

    <section aria-labelledby="pc-detail-title">
      <div class="pc-section-head pc-details-head">
        <div class="pc-details-label"><h2 id="pc-detail-title">电镀明细</h2><span class="pc-count">{{ items.length }} 项</span></div>
        <button class="pc-btn pc-btn--green" type="button" @click="addItem"><AddOutline />添加明细</button>
      </div>
      <div class="pc-table">
        <div class="pc-grid pc-table-head" aria-hidden="true">
          <span>行操作</span><span>发出配件</span><span>发出数量</span><span>单位</span>
          <span>重量</span><span>重量单位</span><span>明细备注</span><span>删除</span>
        </div>
        <article
          v-for="(item, idx) in items" :key="item._key" :data-row-key="item._key"
          class="pc-item" :class="{ 'pc-item--fresh': freshRowKey === item._key }"
          :aria-label="`第 ${idx + 1} 行电镀明细`"
        >
          <div class="pc-grid pc-line-main">
            <div class="pc-copy-cell">
              <span class="pc-row-number">{{ String(idx + 1).padStart(2, '0') }}</span>
              <button
                type="button" class="pc-copy" :aria-label="`复制第 ${idx + 1} 行`"
                :disabled="item._variantLoading || item._creatingVariant"
                :title="item._variantLoading || item._creatingVariant ? '颜色变体处理中，请稍候再复制' : '复制当前行并插入下方'"
                @click="copyItem(idx)"
              ><CopyOutline />复制</button>
            </div>
            <div class="pc-field pc-part-field">
              <span class="pc-mobile-label">发出配件</span>
              <n-select
                v-model:value="item.part_id" :options="partOptions" :render-label="renderOptionWithImage"
                filterable clearable placeholder="选择发出配件" :aria-label="`第 ${idx + 1} 行发出配件`"
                @update:value="(val) => onPartSelect(item, val)"
              />
            </div>
            <div class="pc-field">
              <span class="pc-mobile-label">发出数量</span>
              <n-input-number v-model:value="item.qty" :min="1" :precision="0" :step="1" :show-button="false" placeholder="发出数量" :input-props="{ 'aria-label': `第 ${idx + 1} 行发出数量` }" />
            </div>
            <div class="pc-field">
              <span class="pc-mobile-label">单位</span>
              <n-select v-model:value="item.unit" :options="unitOptions" :aria-label="`第 ${idx + 1} 行单位`" />
            </div>
            <div class="pc-field">
              <span class="pc-mobile-label">重量</span>
              <n-input-number v-model:value="item.weight" :min="0" :precision="4" :step="0.1" :show-button="false" placeholder="选填" :input-props="{ 'aria-label': `第 ${idx + 1} 行重量` }" />
            </div>
            <div class="pc-field">
              <span class="pc-mobile-label">重量单位</span>
              <n-select v-model:value="item.weight_unit" :options="weightUnitOptions" :aria-label="`第 ${idx + 1} 行重量单位`" />
            </div>
            <div class="pc-field pc-row-note">
              <span class="pc-mobile-label">明细备注</span>
              <n-input v-model:value="item.note" placeholder="备注（选填）" :input-props="{ 'aria-label': `第 ${idx + 1} 行备注` }" />
            </div>
            <button type="button" class="pc-delete" :aria-label="`删除第 ${idx + 1} 行`" title="删除当前行" @click="items.splice(idx, 1)"><TrashOutline /></button>
          </div>
          <div v-if="item.part_id" class="pc-line-extra">
            <span class="pc-color-label">电镀颜色</span>
            <div class="pc-colors">
              <button
                v-for="cv in (item._showMore ? [...commonColors, ...moreColors] : commonColors)" :key="cv.code"
                type="button" class="pc-color" :class="{ 'pc-color--selected': item._selectedColor === cv.code }"
                :style="{ '--badge-color': cv.badge || '#8B9096' }"
                :aria-pressed="item._selectedColor === cv.code" :title="cv.label"
                @click="toggleColor(item, cv.code)"
              >{{ cv.code }}</button>
              <button v-if="moreColors.length" type="button" class="pc-color pc-color--more" :aria-expanded="item._showMore" @click="item._showMore = !item._showMore">
                {{ item._showMore ? '收起 ▴' : '更多 ▾' }}
              </button>
            </div>
            <div v-if="item._selectedColor && item._variantInfo" class="pc-target">
              <template v-if="item._variantInfo.part">
                对应配件：<strong>{{ item._variantInfo.part.name }}</strong><code>{{ item._variantInfo.part.id }}</code>
              </template>
              <template v-else-if="item._variantInfo.suggested_name">
                对应配件：{{ item._variantInfo.suggested_name }}
                <n-button size="tiny" type="primary" :loading="item._creatingVariant" @click="doCreateVariantForItem(item)">新建</n-button>
              </template>
            </div>
            <span v-if="item._selectedColor && item._variantLoading" class="pc-target">查询中...</span>
          </div>
        </article>
        <div v-if="!items.length" class="pc-empty">暂无明细，点击下方按钮添加发出配件。</div>
      </div>
      <button class="pc-add-line" type="button" @click="addItem"><AddOutline />添加一行电镀明细</button>
      <p class="pc-hint"><InformationCircleOutline />同款不同色？点击行首「复制」，再修改电镀颜色即可，无需重复填写。</p>
    </section>

    <footer class="pc-footer">
      <div class="pc-summary" aria-live="polite">
        <span>共 <strong>{{ items.length }}</strong> 项明细</span>
        <span v-if="summary.quantities.length" class="pc-summary-quantity">发出 <template v-for="(entry, idx) in summary.quantities" :key="entry.unit"><span v-if="idx"> / </span><strong>{{ entry.qty.toLocaleString('zh-CN') }}</strong> {{ entry.unit }}</template></span>
        <span>总重量 <strong>{{ summary.weightKg.toLocaleString('zh-CN') }}</strong> kg</span>
      </div>
      <div class="pc-footer-actions">
        <button class="pc-btn" type="button" @click="router.back()">取消</button>
        <n-button type="primary" :loading="submitting" :disabled="merging" @click="submit"><template #icon><CheckmarkOutline /></template>创建电镀单</n-button>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, nextTick, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem, NDatePicker, NAlert } from 'naive-ui'
import { AddOutline, ArrowBackOutline, CopyOutline, TrashOutline, InformationCircleOutline, CheckmarkOutline } from '@vicons/ionicons5'
import { listParts, findOrCreateVariant, createPartVariant, getColorVariants } from '@/api/parts'
import { createPlating, listPlating, addPlatingItem } from '@/api/plating'
import { listSuppliers, createSupplier } from '@/api/suppliers'
import { renderOptionWithImage } from '@/utils/ui'
import { tsToDateStr } from '@/utils/date'
import { createPlatingItem, copyPlatingItem, platingItemPayload, summarizePlatingItems } from '@/utils/platingCreate'

const router = useRouter()
const route = useRoute()
const message = useMessage()
const dialog = useDialog()
const supplierName = ref(null)
const supplierOptions = ref([])
const note = ref('')
const createdAtTs = ref(null)
const items = reactive([createPlatingItem()])
const summary = computed(() => summarizePlatingItems(items))
const pageEl = ref(null)
const freshRowKey = ref(null)
let highlightTimer
onBeforeUnmount(() => clearTimeout(highlightTimer))
const submitting = ref(false)
const partOptions = ref([])
const allParts = ref([])
const colorVariants = ref([])

const mergeCandidate = ref(null)
const checkingMerge = ref(false)
const merging = ref(false)
let mergeSeq = 0

const beijingToday = () => {
  const d = new Date(Date.now() + 8 * 3600_000)
  return d.toISOString().slice(0, 10)
}

const checkSameDayOrder = async (supplier) => {
  const trimmed = supplier?.trim()
  if (!trimmed) {
    mergeCandidate.value = null
    return
  }
  const seq = ++mergeSeq
  checkingMerge.value = true
  try {
    const { data: orders } = await listPlating({ supplier_name: trimmed, status: 'pending' })
    if (seq !== mergeSeq) return
    const targetDate = createdAtTs.value ? tsToDateStr(createdAtTs.value) : beijingToday()
    const match = orders.find((o) => o.supplier_name === trimmed && o.created_at?.slice(0, 10) === targetDate)
    if (match) {
      mergeCandidate.value = {
        id: match.id,
        supplier_name: match.supplier_name,
        created_at: match.created_at,
      }
    } else {
      mergeCandidate.value = null
    }
  } catch (_) {
    if (seq === mergeSeq) mergeCandidate.value = null
  } finally {
    if (seq === mergeSeq) checkingMerge.value = false
  }
}

const doMerge = async () => {
  if (!mergeCandidate.value) return
  const validItems = items.filter((i) => i.part_id)
  if (validItems.length === 0) {
    message.warning('请至少有一条有效明细')
    return
  }
  if (validItems.some((i) => i._variantLoading || i._creatingVariant)) { message.warning('颜色变体处理中，请稍候'); return }
  merging.value = true
  const orderId = mergeCandidate.value.id
  let added = 0
  try {
    for (const item of validItems) {
      await addPlatingItem(orderId, platingItemPayload(item))
      added++
    }
    message.success(`已合并 ${added} 项配件到 ${orderId}`)
    router.push(`/plating/${orderId}`)
  } catch (e) {
    if (added > 0) {
      message.warning(`已合并 ${added}/${validItems.length} 项，部分失败: ${e.response?.data?.detail || '未知错误'}`)
      router.push(`/plating/${orderId}`)
    } else {
      message.error(e.response?.data?.detail || '合并失败')
    }
  } finally {
    merging.value = false
  }
}

const methodOf     = computed(() => Object.fromEntries(colorVariants.value.map(c => [c.code, c.method])))
const codeOfLabel  = computed(() => Object.fromEntries(colorVariants.value.map(c => [c.label, c.code])))
const codeOfSuffix = computed(() => Object.fromEntries(colorVariants.value.map(c => ['_' + c.label, c.code])))
const commonColors = computed(() => colorVariants.value.filter(c => c.common))
const moreColors   = computed(() => colorVariants.value.filter(c => !c.common))

const unitOptions = [
  { label: '个', value: '个' },
  { label: '条', value: '条' },
  { label: '米', value: '米' },
  { label: '包', value: '包' },
  { label: 'g', value: 'g' },
  { label: 'kg', value: 'kg' },
]

const weightUnitOptions = [
  { label: 'kg', value: 'kg' },
  { label: 'g', value: 'g' },
]

const getPartColorCode = (part) => {
  if (!part) return null
  // Prefer the color field (authoritative)
  if (part.color && codeOfLabel.value[part.color]) return codeOfLabel.value[part.color]
  // Fallback: parse name suffix
  for (const [suffix, code] of Object.entries(codeOfSuffix.value)) {
    if (part.name?.endsWith(suffix)) return code
  }
  return null
}

const onPartSelect = (item, val) => {
  const found = partOptions.value.find((p) => p.value === val)
  item.unit = found?.unit || '个'
  item.receive_part_id = null
  item._selectedColor = null
  item._variantInfo = null
  item._variantLoading = false
  ++item._reqSeq
  if (val) {
    const part = allParts.value.find((p) => p.id === val)
    const existingCode = getPartColorCode(part)
    // Default: use existing color if variant, otherwise G
    toggleColor(item, existingCode || 'G')
  }
}

const toggleColor = async (item, code) => {
  if (item._selectedColor === code) {
    // Deselect
    ++item._reqSeq
    item._selectedColor = null
    item._variantInfo = null
    item._variantLoading = false
    item.receive_part_id = null
    item.plating_method = '金'
    return
  }
  item._selectedColor = code
  item.plating_method = methodOf.value[code] || '金'
  item.receive_part_id = null
  item._variantInfo = null
  item._variantLoading = true
  const seq = ++item._reqSeq
  try {
    const { data } = await findOrCreateVariant(item.part_id, { color_code: code })
    if (item._reqSeq !== seq) return // stale
    item._variantInfo = data
    item.receive_part_id = data.part?.id || null
  } catch (e) {
    if (item._reqSeq === seq) {
      message.error(e.response?.data?.detail || '查询变体失败')
    }
  } finally {
    if (item._reqSeq === seq) {
      item._variantLoading = false
    }
  }
}

const doCreateVariantForItem = (item) => {
  const suggestedName = item._variantInfo?.suggested_name
  dialog.info({
    title: '确认新建',
    content: `当前没有 ${suggestedName}，确定新建吗？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      item._creatingVariant = true
      try {
        const { data: newPart } = await createPartVariant(item.part_id, { color_code: item._selectedColor })
        item.receive_part_id = newPart.id
        item._variantInfo = { part: newPart, created: true }
        // Refresh parts list
        const { data: parts } = await listParts()
        allParts.value = parts
        partOptions.value = parts.map((p) => ({
          label: `${p.id} ${p.name}`,
          value: p.id,
          code: p.id,
          name: p.name,
          image: p.image,
          unit: p.unit,
        }))
        message.success('变体创建成功')
      } catch (e) {
        message.error(e.response?.data?.detail || '创建变体失败')
      } finally {
        item._creatingVariant = false
      }
    },
  })
}

const highlightRow = async (item) => {
  freshRowKey.value = item._key
  clearTimeout(highlightTimer)
  highlightTimer = setTimeout(() => { freshRowKey.value = null }, 2000)
  await nextTick()
  const row = pageEl.value?.querySelector(`[data-row-key="${item._key}"]`)
  row?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'nearest' })
  row?.querySelector('.pc-copy')?.focus({ preventScroll: true })
}

const addItem = () => {
  items.push(createPlatingItem())
  highlightRow(items[items.length - 1])
}

const copyItem = (idx) => {
  const source = items[idx]
  if (source._variantLoading || source._creatingVariant) return
  items.splice(idx + 1, 0, copyPlatingItem(source))
  highlightRow(items[idx + 1])
  message.success(`已复制第 ${idx + 1} 行，可在下方独立修改`)
}

const submit = async () => {
  const trimmedSupplier = supplierName.value?.trim()
  if (!trimmedSupplier) { message.warning('请输入电镀厂名称'); return }
  if (items.length === 0) { message.warning('请至少添加一条明细'); return }
  if (items.some((i) => !i.part_id)) { message.warning('请选择配件'); return }
  if (items.some((i) => i._variantLoading || i._creatingVariant)) { message.warning('颜色变体处理中，请稍候'); return }
  submitting.value = true
  try {
    // Auto-create supplier if new (swallow duplicate 400, rethrow others)
    const isNew = !supplierOptions.value.some((o) => o.value === trimmedSupplier)
    if (isNew) {
      try { await createSupplier({ name: trimmedSupplier, type: 'plating' }) } catch (e) { if (e.response?.status !== 400) throw e }
    }
    // Strip internal fields before submit
    const cleanItems = items.map(platingItemPayload)
    const payload = { supplier_name: trimmedSupplier, items: cleanItems, note: note.value }
    const createdAt = tsToDateStr(createdAtTs.value)
    if (createdAt) payload.created_at = createdAt
    const { data } = await createPlating(payload)
    message.success('创建成功')
    router.push(`/plating/${data.id}`)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  try {
    const [partsRes, colorsRes, suppliersRes] = await Promise.all([
      listParts(), getColorVariants(), listSuppliers({ type: 'plating' }),
    ])
    allParts.value = partsRes.data
    partOptions.value = partsRes.data.map((p) => ({
      label: `${p.id} ${p.name}`,
      value: p.id,
      code: p.id,
      name: p.name,
      image: p.image,
      unit: p.unit,
    }))
    colorVariants.value = colorsRes.data
    supplierOptions.value = suppliersRes.data.map((s) => ({ label: s.name, value: s.name }))
    // Prefill from purchase order
    if (route.query.prefill) {
      try {
        const prefillItems = JSON.parse(route.query.prefill)
        if (Array.isArray(prefillItems) && prefillItems.length > 0) {
          items.splice(0, items.length)
          for (const pi of prefillItems) {
            const item = createPlatingItem()
            item.part_id = pi.part_id
            item.qty = pi.qty
            item.unit = pi.unit || '个'
            items.push(item)
          }
          // Trigger color variant lookup for each prefilled item
          for (const item of items) {
            if (item.part_id) {
              const part = allParts.value.find((p) => p.id === item.part_id)
              const existingCode = getPartColorCode(part)
              toggleColor(item, existingCode || 'G')
            }
          }
        }
      } catch (_) {
        // Invalid prefill JSON, ignore
      }
    }
  } catch (_) {
    // error already shown by axios interceptor
  }
})
</script>

<style scoped>
.plating-create {
  --pc-ink: #1A1D21;
  --pc-green: #1E7A5A;
  --pc-line: #ECEDEF;
  --pc-muted: #8B9096;
  /* Respond to the actual content width, including an expanded sidebar. */
  container-type: inline-size;
  width: 100%;
  min-width: 0;
  min-height: calc(100dvh - 56px);
  display: flex;
  flex-direction: column;
  color: var(--pc-ink);
}
.pc-crumbs { display: flex; gap: 9px; align-items: center; color: var(--pc-muted); font-size: 12px; margin-bottom: 18px; }
.pc-crumbs span { color: #B1B6BB; }
.pc-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.pc-title { display: flex; align-items: center; gap: 12px; }
.pc-title h1 { margin: 0; font-size: 25px; font-weight: 700; letter-spacing: -.6px; }
.pc-badge { padding: 3px 9px; border-radius: 20px; font-size: 11px; color: var(--pc-green); background: #E6F2EC; white-space: nowrap; }
.pc-intro { color: var(--pc-muted); margin: 7px 0 27px; font-size: 12px; }
.pc-btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 7px 12px; font: inherit; font-size: 13px; white-space: nowrap; border: 1px solid var(--pc-line); border-radius: 7px; color: #4C535A; background: #fff; cursor: pointer; transition: background .15s, border-color .15s; }
.pc-btn:hover { background: #F6F7F8; border-color: #CAD0D4; }
.pc-btn--green { color: var(--pc-green); background: #E6F2EC; border-color: #C5E0D3; }
.pc-btn--green:hover { background: #D6EBE0; }
.plating-create button:focus-visible { outline: 2px solid var(--pc-green); outline-offset: 3px; }
.pc-btn svg, .pc-copy svg, .pc-delete svg, .pc-add-line svg, .pc-hint svg { width: 16px; height: 16px; flex-shrink: 0; }
.pc-section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; border-bottom: 1px solid var(--pc-line); padding-bottom: 10px; margin-bottom: 17px; }
.pc-section-head h2 { margin: 0; color: var(--pc-muted); font-size: 11px; letter-spacing: .8px; font-weight: 700; }
.pc-section-note { color: #9AA0A6; font-size: 11px; }
.pc-meta { display: grid; grid-template-columns: minmax(190px, 1fr) minmax(230px, 1.6fr) minmax(180px, .8fr); gap: 22px; margin-bottom: 30px; }
.pc-meta :deep(.n-form-item) { min-width: 0; }
.pc-meta :deep(.n-form-item-label) { font-size: 12px; color: #656D74; padding-bottom: 7px; }
.pc-meta :deep(.n-date-picker) { width: 100%; }
.pc-details-head { margin-bottom: 12px; }
.pc-details-label { display: flex; align-items: center; gap: 9px; }
.pc-count { font-size: 10px; font-weight: 600; color: #6F787F; background: #F0F2F3; border-radius: 4px; padding: 1px 6px; }
.pc-table { border: 1px solid var(--pc-line); border-radius: 9px; background: #fff; overflow: hidden; }
.pc-grid { display: grid; grid-template-columns: 72px minmax(190px, 2fr) minmax(84px, .7fr) 68px minmax(80px, .65fr) 72px minmax(115px, 1fr) 34px; gap: 12px; align-items: center; }
.pc-table-head { padding: 11px 16px; background: #F8F9FA; border-bottom: 1px solid var(--pc-line); color: var(--pc-muted); font-size: 11px; }
.pc-table-head span:last-child { text-align: center; }
.pc-item { padding: 17px 16px 14px; border-bottom: 1px solid var(--pc-line); }
.pc-item:last-child { border-bottom: 0; }
.pc-item--fresh { animation: pc-highlight 2s ease-out; }
@keyframes pc-highlight { 0%, 30% { background: #E6F2EC; } 100% { background: #fff; } }
.pc-copy-cell { display: flex; align-items: center; gap: 8px; }
.pc-row-number { font-size: 11px; color: #ABB1B6; font-variant-numeric: tabular-nums; }
.pc-copy { display: inline-flex; align-items: center; gap: 3px; border: 0; background: transparent; color: var(--pc-green); font: inherit; font-size: 12px; padding: 5px 0; cursor: pointer; white-space: nowrap; }
.pc-copy svg { width: 13px; height: 13px; }
.pc-copy:hover:not(:disabled) { color: #104E37; text-decoration: underline; }
.pc-copy:disabled { opacity: .45; cursor: wait; }
.pc-delete { display: grid; place-items: center; color: #A0A7AD; border: 0; background: transparent; width: 34px; height: 34px; border-radius: 6px; cursor: pointer; }
.pc-delete:hover { background: #FFF0F0; color: #D94950; }
.pc-field { min-width: 0; }
.pc-field :deep(.n-input-number), .pc-field :deep(.n-select) { width: 100%; min-width: 0; }
.pc-mobile-label { display: none; }
.pc-line-extra { margin: 10px 0 0 84px; display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.pc-color-label { font-size: 11px; color: var(--pc-muted); }
.pc-colors { display: flex; flex-wrap: wrap; gap: 5px; }
.pc-color { font: inherit; font-size: 10px; font-weight: 600; padding: 3px 8px; line-height: 1.4; border-radius: 4px; border: 1px solid #E3E5E7; color: #747C83; background: #fff; min-width: 28px; cursor: pointer; }
.pc-color--selected { border-color: var(--badge-color); color: var(--badge-color); background: color-mix(in srgb, var(--badge-color) 12%, white); }
.pc-color--more { border-style: dashed; font-weight: 400; }
.pc-target { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 4px; color: #8C949A; font-size: 11px; overflow-wrap: anywhere; }
.pc-target strong { font-weight: 400; color: #57675E; }
.pc-target code { color: #9DA5AA; font-size: 10px; }
.pc-add-line { display: flex; align-items: center; justify-content: center; gap: 7px; width: 100%; margin-top: 11px; padding: 11px; font: inherit; font-size: 12px; border: 1px dashed #D7DFDA; color: var(--pc-green); border-radius: 7px; background: #FCFDFC; cursor: pointer; }
.pc-add-line:hover { background: #F1F8F4; border-color: #7EAF97; }
.pc-hint { display: flex; align-items: center; gap: 6px; color: #9AA1A7; font-size: 11px; margin: 12px 0 24px; }
.pc-hint svg { width: 13px; height: 13px; }
.pc-empty { color: var(--pc-muted); text-align: center; padding: 35px; font-size: 13px; }
.pc-footer { position: sticky; bottom: -28px; margin-top: auto; padding: 18px 0; border-top: 1px solid var(--pc-line); background: #F6F7F8F5; backdrop-filter: blur(12px); display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 16px; z-index: 2; }
.pc-summary { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; font-size: 12px; color: var(--pc-muted); }
.pc-summary > span + span { padding-left: 16px; border-left: 1px solid #E0E4E6; }
.pc-summary strong { font-weight: 650; font-size: 15px; color: var(--pc-ink); font-variant-numeric: tabular-nums; }
.pc-footer-actions { display: flex; align-items: center; gap: 10px; margin-left: auto; }
@container (max-width: 1050px) {
  .pc-grid { grid-template-columns: 65px minmax(150px, 2fr) 74px 60px 70px 66px minmax(90px, 1fr) 30px; gap: 8px; }
  .pc-delete { width: 30px; }
  .pc-table-head, .pc-item { padding-left: 12px; padding-right: 12px; }
  .pc-line-extra { margin-left: 73px; }
}
@container (max-width: 820px) {
  .pc-meta { gap: 12px; grid-template-columns: minmax(160px, 1fr) minmax(180px, 1.3fr) minmax(155px, .9fr); }
  .pc-table-head { display: none; }
  .pc-line-main { grid-template-columns: 60px minmax(140px, 2fr) minmax(80px, 1fr) minmax(66px, .7fr) 30px; gap: 10px; }
  .pc-line-main > .pc-field:nth-child(5) { grid-column: 3; grid-row: 2; }
  .pc-line-main > .pc-field:nth-child(6) { grid-column: 4; grid-row: 2; }
  .pc-row-note { grid-column: 2; grid-row: 2; }
  .pc-delete { grid-column: 5; grid-row: 1; }
  .pc-mobile-label { display: block; color: var(--pc-muted); font-size: 10px; margin-bottom: 5px; }
  .pc-copy-cell, .pc-delete { align-self: end; }
  .pc-line-extra { margin-left: 70px; }
}
@container (max-width: 580px) {
  .pc-title h1 { font-size: 22px; }
  .pc-head > .pc-btn { font-size: 12px; padding: 6px 9px; }
  .pc-title { gap: 8px; }
  .pc-intro { font-size: 11px; margin-bottom: 24px; }
  .pc-meta { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 15px 12px; margin-bottom: 25px; }
  .pc-meta-note { grid-column: 1 / -1; grid-row: 2; }
  .pc-section-note { display: none; }
  .pc-line-main { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 11px; }
  .pc-copy-cell { grid-column: 1; }
  .pc-delete { grid-column: 2; grid-row: 1; justify-self: end; width: 30px; height: 28px; }
  .pc-part-field { grid-column: 1 / -1; }
  .pc-line-main > .pc-field:nth-child(5), .pc-line-main > .pc-field:nth-child(6) { grid-column: auto; grid-row: auto; }
  .pc-row-note { grid-column: 1 / -1; grid-row: auto; }
  .pc-line-extra { margin: 14px 0 0; gap: 8px; }
  .pc-target { flex-basis: 100%; }
  .pc-item { padding: 10px 13px 16px; }
  .pc-footer { padding: 13px 0; gap: 10px; }
  .pc-summary { font-size: 11px; gap: 10px; }
  .pc-summary > span + span { padding-left: 10px; }
  .pc-summary strong { font-size: 13px; }
  .pc-hint { align-items: flex-start; }
  .pc-hint svg { margin-top: 2px; }
}
@media (max-width: 767px) {
  .plating-create { min-height: calc(100dvh - 32px); }
  .pc-crumbs { padding-left: 36px; }
  .pc-footer { bottom: -16px; }
}
@media (prefers-reduced-motion: reduce) {
  .pc-item--fresh { animation: none; background: #E6F2EC; }
}
</style>
