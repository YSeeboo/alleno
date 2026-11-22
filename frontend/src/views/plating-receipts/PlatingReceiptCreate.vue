<template>
  <div class="receipt-create">
    <div class="rc-crumbs">生产 <span>/</span> 电镀回收 <span>/</span> 新建</div>
    <header class="rc-head">
      <div class="rc-title"><h1>新建电镀回收单</h1><span class="rc-badge">录入中</span></div>
      <button class="rc-btn" type="button" :disabled="locked" @click="backToList"><ArrowBackOutline />{{ summaryReturn ? '返回汇总' : '返回列表' }}</button>
    </header>
    <p class="rc-intro">选择电镀厂与尚未完全回收的配件，按实际回收数量入库、计价；允许超过发出数量。</p>
    <div v-if="createdReceiptId && !costDiffVisible" class="rc-created" role="status">回收单 {{ createdReceiptId }} 已创建。<n-button text type="primary" @click="goToReceipt">查看已创建回收单</n-button></div>

    <section aria-labelledby="rc-basic-title">
      <div class="rc-section-head"><h2 id="rc-basic-title">基本信息</h2><span class="rc-section-note">创建后按本次回收数量入库</span></div>
      <n-form label-placement="top" :show-feedback="false" :disabled="locked" class="rc-meta">
        <n-form-item label="商家 / 电镀厂" required>
          <n-select
            :value="vendorName" :options="vendorOptions" :loading="loadingVendors" filterable tag clearable
            placeholder="选择或输入电镀厂名称" aria-label="商家 / 电镀厂" @update:value="onVendorChange"
          />
        </n-form-item>
        <n-form-item label="备注" class="rc-meta-note"><n-input v-model:value="note" placeholder="填写本次回收说明（选填）" :input-props="{ 'aria-label': '回收备注' }" /></n-form-item>
        <n-form-item label="创建时间"><n-date-picker v-model:value="createdAtTs" type="date" clearable placeholder="不填则使用当前时间" aria-label="创建时间" /></n-form-item>
      </n-form>
      <div v-if="vendorLoadError" class="rc-error" role="alert">商家列表加载失败，仍可输入名称。<n-button text type="primary" :disabled="locked" @click="loadVendors">重试商家列表</n-button></div>
      <div class="rc-payment">
        <span class="rc-payment-label">付款状态</span>
        <n-radio-group v-model:value="status" :disabled="locked" aria-label="付款状态"><n-radio value="未付款">未付款</n-radio><n-radio value="已付款">已付款</n-radio></n-radio-group>
        <span class="rc-payment-note">{{ status === '已付款' ? '已付款单据创建后锁定明细，请核对数量与费用' : '费用可暂不填写，回收后继续补录' }}</span>
      </div>
    </section>

    <section class="rc-source-section" aria-labelledby="rc-source-title">
      <div class="rc-section-head">
        <div class="rc-section-label"><h2 id="rc-source-title">待回收配件</h2><span class="rc-count">{{ filteredItems.length }} 项</span></div>
        <button class="rc-btn" type="button" :disabled="!vendorName || loadingItems || locked" @click="fetchPendingItems"><RefreshOutline />刷新待回收</button>
      </div>
      <div v-if="vendorName" class="rc-filters">
        <n-input v-model:value="filterKeyword" :disabled="locked" placeholder="发出 / 回收配件编号、名称" clearable :input-props="{ 'aria-label': '搜索待回收配件' }"><template #prefix><SearchOutline class="rc-search-icon" /></template></n-input>
        <div class="rc-date-filter"><span>发出日期</span><n-date-picker v-model:value="filterDateOn" :disabled="locked" type="date" clearable placeholder="全部日期" aria-label="筛选发出日期" /></div>
        <button v-if="filterKeyword || filterDateOn != null" class="rc-text-btn" type="button" :disabled="locked" @click="clearFilters">清除筛选</button>
      </div>
      <n-spin :show="loadingItems">
        <div v-if="fetchError" class="rc-empty" role="alert"><p>待回收配件加载失败，已填写的明细仍保留。</p><n-button :disabled="locked" @click="fetchPendingItems">重试加载</n-button></div>
        <div v-else-if="!vendorName || !pendingItems.length || !filteredItems.length" class="rc-empty">
          <p>{{ !vendorName ? '请先选择商家 / 电镀厂' : loadingItems ? '正在加载待回收配件…' : !pendingItems.length ? '该商家暂无待回收配件' : '没有符合筛选条件的配件' }}</p>
          <span>{{ !vendorName ? '仅显示所选商家尚未完全回收的明细' : '筛选不会移除下方已选的回收明细' }}</span>
        </div>
        <div v-else class="rc-source-table" :aria-busy="loadingItems">
          <div class="rc-source-grid rc-source-head">
            <n-checkbox :checked="allVisibleSelected" :indeterminate="someVisibleSelected && !allVisibleSelected" :disabled="locked || loadingItems" aria-label="选择当前筛选的全部配件" @update:checked="toggleAllVisible" />
            <span>发出配件 / 回收配件</span><span>来源电镀单</span><span>电镀方式</span><span>发出 / 已结清</span><span>未收 / 超出</span><span>回收单价</span>
          </div>
          <div class="rc-source-scroll">
            <div v-for="item in filteredItems" :key="item.id" class="rc-source-grid rc-source-row" :class="{ 'is-selected': selectedIds.has(item.id) }">
              <n-checkbox :checked="selectedIds.has(item.id)" :disabled="locked || loadingItems" :aria-label="`选择 ${item.part_name} ${item.plating_order_id} 明细 ${item.id}`" @update:checked="(value) => toggleItem(item, value)" />
              <div class="rc-part">
                <n-image v-if="item.part_image" :src="item.part_image" :alt="item.part_name" :width="38" :height="38" object-fit="cover" />
                <div v-else class="rc-image-placeholder"><CubeOutline /></div>
                <div class="rc-part-text"><strong>{{ item.part_name }}</strong><code>{{ item.part_id }}<span v-if="item.part_is_composite" class="rc-composite">组合</span></code><small v-if="item.receive_part_id && item.receive_part_id !== item.part_id">回收 → {{ item.receive_part_name || item.receive_part_id }}</small></div>
              </div>
              <div class="rc-source-order"><code>{{ item.plating_order_id }}</code><small>{{ item.created_at?.slice(0, 10) || '—' }}</small></div>
              <span class="rc-method">{{ item.plating_method || '—' }}</span>
              <span class="rc-source-progress"><span class="rc-mobile-label">发出 / 已结清</span>{{ item.qty }} / {{ item.received_qty ?? 0 }} {{ item.unit || '个' }}</span>
              <strong class="rc-remaining"><span class="rc-mobile-label">未收 / 超出</span>{{ sourceBalance(item) }} <small>{{ item.unit || '个' }}</small></strong>
              <div class="rc-source-price">
                <span class="rc-mobile-label">回收单价</span>
                <n-input-number
                  :value="itemInputs[item.id]?.price ?? null"
                  :disabled="locked || loadingItems"
                  :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" :step="0.1"
                  :show-button="false" size="small" placeholder="待定价"
                  :input-props="{ 'aria-label': `${item.part_name} ${item.plating_order_id} 明细 ${item.id} 回收单价` }"
                  @update:value="(value) => updateSourcePrice(item, value)"
                ><template #prefix>¥</template></n-input-number>
                <small>元 / {{ itemInputs[item.id]?.unit || item.unit || '个' }}</small>
              </div>
            </div>
          </div>
        </div>
      </n-spin>
      <p class="rc-hint"><InformationCircleOutline />可直接填写每行回收单价，与下方明细同步；填写单价不会自动勾选，仅勾选的配件计入本次回收。</p>
    </section>

    <section class="rc-detail-section" aria-labelledby="rc-detail-title">
      <div class="rc-section-head">
        <div class="rc-section-label"><h2 id="rc-detail-title">本次回收明细</h2><span class="rc-count">{{ selectedItems.length }} 项</span></div>
        <button v-if="selectedItems.length" class="rc-text-btn" type="button" :disabled="locked" @click="confirmClearItems">清空已选</button>
      </div>
      <div class="rc-detail-table">
        <div class="rc-detail-grid rc-detail-head" aria-hidden="true"><span>回收配件 / 来源</span><span>本次回收数量</span><span>回收重量</span><span>回收单价</span><span>小计</span><span>移除</span></div>
        <article v-for="(item, index) in selectedItems" :key="item.id" class="rc-detail-grid rc-detail-row" :aria-label="`第 ${index + 1} 行回收明细`">
          <div class="rc-detail-part"><span class="rc-row-number">{{ String(index + 1).padStart(2, '0') }}</span><div><strong>{{ item.receive_part_name || item.part_name }}</strong><code>{{ item.receive_part_id || item.part_id }}</code><small>来源 {{ item.plating_order_id }} · {{ item.plating_method || '未标方式' }}</small><span v-if="item._unavailable" class="rc-invalid">已不在待回收列表，请移除</span></div></div>
          <div class="rc-field rc-qty-field"><span class="rc-mobile-label">本次回收数量</span><div class="rc-input-unit"><n-input-number v-model:value="itemInputs[item.id].qty" :disabled="locked || item._unavailable" :min="0.0001" :precision="4" :step="1" :show-button="false" placeholder="回收数量" :input-props="{ 'aria-label': `第 ${index + 1} 行回收数量` }" /><span>{{ itemInputs[item.id].unit }}</span></div><small>{{ itemInputs[item.id].qty > getRemaining(item) ? `本次超出未收数量 ${Number((itemInputs[item.id].qty - getRemaining(item)).toFixed(4))}` : '按实际数量填写，允许超收' }}</small></div>
          <div class="rc-field rc-weight-field"><span class="rc-mobile-label">回收重量</span><div class="rc-input-unit"><n-input-number v-model:value="itemInputs[item.id].weight" :disabled="locked" :min="0" :precision="4" :show-button="false" placeholder="选填" :input-props="{ 'aria-label': `第 ${index + 1} 行回收重量` }" /><span>{{ item.weight_unit || 'g' }}</span></div><small>{{ item.weight == null ? '按实际回收填写' : `发出 ${item.weight} ${item.weight_unit || 'g'}` }}</small></div>
          <div class="rc-field rc-price-field"><span class="rc-mobile-label">回收单价</span><n-input-number v-model:value="itemInputs[item.id].price" :disabled="locked" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" :step="0.1" :show-button="false" placeholder="待定价" :input-props="{ 'aria-label': `第 ${index + 1} 行回收单价` }"><template #prefix>¥</template></n-input-number><small>元 / {{ itemInputs[item.id].unit }}</small></div>
          <div class="rc-line-amount" :class="{ 'is-unpriced': lineAmount(item) == null }"><span class="rc-mobile-label">小计</span>{{ lineAmount(item) == null ? '待定价' : `¥ ${fmtMoney(lineAmount(item))}` }}</div>
          <button class="rc-remove" type="button" :disabled="locked" :aria-label="`移除第 ${index + 1} 行回收明细`" @click="toggleItem(item, false)"><TrashOutline /></button>
        </article>
        <div v-if="!selectedItems.length" class="rc-empty"><p>尚未选择回收配件</p><span>从上方待回收列表勾选，默认填入剩余可回收数量</span></div>
      </div>
      <p class="rc-hint"><InformationCircleOutline />单价留空表示待定价，填 0 表示免费；小计按回收数量 × 单价计算，不按重量计费。</p>
    </section>

    <footer class="rc-footer">
      <div class="rc-summary" aria-live="polite">
        <span>已选 <strong>{{ selectedItems.length }}</strong> 项</span>
        <span v-if="draftSummary.quantities.length" class="rc-summary-qty">回收 <template v-for="(entry, index) in draftSummary.quantities" :key="entry.unit"><span v-if="index"> / </span><strong>{{ entry.qty.toLocaleString('zh-CN') }}</strong> {{ entry.unit }}</template></span>
        <span v-if="draftSummary.unpricedCount" class="rc-unpriced">{{ draftSummary.unpricedCount }} 项待定价</span>
      </div>
      <div class="rc-footer-actions"><div class="rc-total"><span>{{ draftSummary.unpricedCount ? '已定价合计' : '预估总金额' }}</span><strong>¥ {{ fmtMoney(draftSummary.amount) }}</strong></div><button class="rc-btn" type="button" :disabled="locked" @click="backToList">取消</button><n-button type="primary" :loading="submitting" :disabled="locked || loadingItems || fetchError || !selectedItems.length" @click="submit"><template #icon><CheckmarkOutline /></template>创建回收单</n-button></div>
    </footer>
    <!-- Cost Diff Modal -->
    <n-modal v-model:show="costDiffVisible" :mask-closable="false" :close-on-esc="false" :closable="false" preset="card" title="电镀成本变动确认" :style="{ width: isMobile ? '95vw' : '650px' }">
      <p class="rc-cost-created">回收单 {{ costDiffSourceId }} 已创建，请选择是否同步配件成本，无需再次提交。</p>
      <div style="margin-bottom: 12px; color: #333;">
        当前电镀成本与配件已有电镀成本金额不相同，是否更新电镀成本？
      </div>
      <div style="margin-bottom: 12px; color: #999; font-size: 12px;">来源：{{ costDiffSourceId }}</div>
      <n-data-table
        :columns="[
          { title: '配件编号', key: 'part_id', width: 160 },
          { title: '配件名称', key: 'part_name', minWidth: 120 },
          { title: '原电镀费用', key: 'current_value', width: 120, render: (r) => r.current_value != null ? `¥ ${fmtMoney(r.current_value)}` : '-' },
          { title: '更新电镀费用', key: 'new_value', width: 120, render: (r) => h('span', { style: 'color: #d03050; font-weight: 600;' }, `¥ ${fmtMoney(r.new_value)}`) },
        ]"
        :data="costDiffs"
        :bordered="false"
        :scroll-x="520"
        size="small"
      />
      <template #footer>
        <n-space justify="end">
          <n-button @click="skipCostUpdate" :disabled="costDiffUpdating">跳过</n-button>
          <n-button type="primary" :loading="costDiffUpdating" @click="confirmCostUpdate">确认更新</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, h } from 'vue'
import { useRouter, useRoute, onBeforeRouteLeave } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import {
  NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem,
  NRadioGroup, NRadio, NDataTable, NSpin, NImage, NModal, NDatePicker, NCheckbox,
} from 'naive-ui'
import { ArrowBackOutline, RefreshOutline, SearchOutline, CubeOutline, InformationCircleOutline, TrashOutline, CheckmarkOutline } from '@vicons/ionicons5'
import { listPendingReceiveItems } from '@/api/plating'
import { createPlatingReceipt } from '@/api/platingReceipts'
import { batchUpdatePartCosts } from '@/api/parts'
import { fmtMoney, fmtPrice, parseNum } from '@/utils/ui'
import { sourceBalance } from '@/utils/receiptQuantity'
import { tsToDateStr } from '@/utils/date'
import { useIsMobile } from '@/composables/useIsMobile'
import { getPlatingLocation, getPlatingCreateReturnLocation } from '@/utils/platingNavigation'
import {
  remainingReceiptQuantity as getRemaining, createReceiptInput, filterPendingReceiptItems,
  receiptLineAmount, summarizeReceiptDraft, receiptItemPayload,
} from '@/utils/platingReceiptCreate'

const router = useRouter()
const route = useRoute()
const summaryReturn = computed(() => getPlatingCreateReturnLocation(route.query))
const message = useMessage()
const dialog = useDialog()
const { isMobile } = useIsMobile()
const vendorName = ref(null)
const note = ref('')
const status = ref('未付款')
const createdAtTs = ref(null)
const submitting = ref(false)
const loadingItems = ref(false)
const vendorOptions = ref([])
const loadingVendors = ref(false)
const vendorLoadError = ref(false)
const pendingItems = ref([])
const selectedItems = ref([])
// Source IDs, not part IDs: the same part can appear in multiple source orders.
const itemInputs = reactive({})

// Filter state
const filterKeyword = ref('')
const filterDateOn = ref(null)
let fetchSeq = 0
const fetchError = ref(false)

// Cost diff modal
const costDiffVisible = ref(false)
const costDiffs = ref([])
const costDiffSourceId = ref('')
const costDiffUpdating = ref(false)
const createdReceiptId = ref(null)
const locked = computed(() => submitting.value || !!createdReceiptId.value)
const filteredItems = computed(() => filterPendingReceiptItems(pendingItems.value, filterKeyword.value, tsToDateStr(filterDateOn.value)))
const selectedIds = computed(() => new Set(selectedItems.value.map((item) => item.id)))
const allVisibleSelected = computed(() => filteredItems.value.length > 0 && filteredItems.value.every((item) => selectedIds.value.has(item.id)))
const someVisibleSelected = computed(() => filteredItems.value.some((item) => selectedIds.value.has(item.id)))
const draftSummary = computed(() => summarizeReceiptDraft(selectedItems.value, itemInputs))
const lineAmount = (item) => receiptLineAmount(itemInputs[item.id])
const backToList = () => { if (!locked.value) router.push(summaryReturn.value || getPlatingLocation('receipt')) }
const clearFilters = () => { filterKeyword.value = ''; filterDateOn.value = null }

const fetchPendingItems = async () => {
  if (locked.value) return
  const seq = ++fetchSeq
  if (!vendorName.value) {
    pendingItems.value = []
    loadingItems.value = false
    fetchError.value = false
    return
  }
  loadingItems.value = true
  fetchError.value = false
  try {
    // Fetch the complete vendor list once; local filters never discard selection.
    const { data } = await listPendingReceiveItems({ supplier_name: vendorName.value })
    if (seq !== fetchSeq) return
    pendingItems.value = data
    const byId = new Map(data.map((item) => [item.id, item]))
    selectedItems.value = selectedItems.value.map((item) => byId.get(item.id) || { ...item, _unavailable: true })
  } catch (_) {
    if (seq !== fetchSeq) return
    pendingItems.value = []
    fetchError.value = true
  } finally {
    if (seq === fetchSeq) loadingItems.value = false
  }
}

const onVendorChange = async (val) => {
  if (locked.value || val === vendorName.value) return
  const changeVendor = () => {
    vendorName.value = val
    selectedItems.value = []
    pendingItems.value = []
    for (const key of Object.keys(itemInputs)) delete itemInputs[key]
    clearFilters()
    fetchPendingItems()
  }
  if (selectedItems.value.length) {
    dialog.warning({
      title: '切换电镀厂', content: '切换后将清空已选回收明细及其数量、单价，是否继续？',
      positiveText: '清空并切换', negativeText: '保留当前明细',
      onPositiveClick: () => { if (!locked.value) changeVendor() },
    })
  } else changeVendor()
}

const toggleItem = (item, checked) => {
  if (locked.value || loadingItems.value) return
  if (checked && !selectedIds.value.has(item.id)) {
    if (!itemInputs[item.id]) itemInputs[item.id] = createReceiptInput(item)
    selectedItems.value.push(item)
  } else if (!checked) {
    selectedItems.value = selectedItems.value.filter((row) => row.id !== item.id)
  }
}

const updateSourcePrice = (item, price) => {
  if (locked.value || loadingItems.value) return
  if (!itemInputs[item.id]) itemInputs[item.id] = createReceiptInput(item)
  itemInputs[item.id].price = price
}

const toggleAllVisible = (checked) => {
  for (const item of filteredItems.value) toggleItem(item, checked)
}

const confirmClearItems = () => {
  if (locked.value) return
  dialog.warning({
    title: '清空本次回收明细', content: '将清空所有已选明细及其已填写的数量、重量与单价。',
    positiveText: '确认清空', negativeText: '取消',
    onPositiveClick: () => {
      if (locked.value) return
      selectedItems.value = []
      for (const key of Object.keys(itemInputs)) delete itemInputs[key]
    },
  })
}

const handleCostDiffs = (data) => {
  createdReceiptId.value = data.id
  if (data.cost_diffs && data.cost_diffs.length > 0) {
    costDiffs.value = data.cost_diffs
    costDiffSourceId.value = data.id
    costDiffVisible.value = true
  } else {
    goToReceipt()
  }
}

const goToReceipt = () => router.replace(`/plating-receipts/${createdReceiptId.value}`)

const confirmCostUpdate = async () => {
  if (costDiffUpdating.value) return
  costDiffUpdating.value = true
  try {
    await batchUpdatePartCosts({
      updates: costDiffs.value.map((d) => ({
        part_id: d.part_id,
        field: d.field,
        value: d.new_value,
        source_id: costDiffSourceId.value,
      })),
    })
    message.success('配件电镀成本已更新')
    costDiffVisible.value = false
    goToReceipt()
  } catch (_) {
    message.error('成本更新失败，请重试')
  } finally {
    costDiffUpdating.value = false
  }
}

const skipCostUpdate = () => {
  if (costDiffUpdating.value) return
  costDiffVisible.value = false
  goToReceipt()
}

const submit = async () => {
  if (locked.value || loadingItems.value || fetchError.value) return
  if (!vendorName.value?.trim()) { message.warning('请输入商家名称'); return }
  if (selectedItems.value.length === 0) { message.warning('请至少勾选一条待回收配件'); return }

  let items
  try {
    items = selectedItems.value.map((item) => receiptItemPayload(item, itemInputs[item.id], vendorName.value.trim()))
  } catch (error) {
    message.warning(error.message)
    return
  }

  submitting.value = true
  try {
    const payload = {
      vendor_name: vendorName.value.trim(),
      items,
      status: status.value,
      note: note.value,
    }
    const createdAt = tsToDateStr(createdAtTs.value)
    if (createdAt) payload.created_at = createdAt
    const { data } = await createPlatingReceipt(payload)
    message.success('创建成功')
    handleCostDiffs(data)
  } catch (_) {
    // The API interceptor reports the error; preserve the draft for correction.
  } finally {
    submitting.value = false
  }
}

const loadVendors = async () => {
  if (loadingVendors.value) return
  loadingVendors.value = true
  vendorLoadError.value = false
  // Load supplier names from pending items
  try {
    const { data } = await listPendingReceiveItems()
    const suppliers = [...new Set(data.map((i) => i.supplier_name).filter(Boolean))]
    vendorOptions.value = suppliers.map((v) => ({ label: v, value: v }))
  } catch (_) {
    vendorLoadError.value = true
  } finally {
    loadingVendors.value = false
  }
}

onBeforeRouteLeave((to) => {
  if (createdReceiptId.value && !costDiffVisible.value && to.path === `/plating-receipts/${createdReceiptId.value}`) return true
  if (locked.value) {
    message.warning(costDiffVisible.value ? '回收单已创建，请先选择是否更新配件成本' : '正在提交，请稍候')
    return false
  }
})

const beforeUnload = (event) => {
  if (!locked.value) return
  event.preventDefault()
  event.returnValue = ''
}
onMounted(() => { loadVendors(); window.addEventListener('beforeunload', beforeUnload) })
onBeforeUnmount(() => { ++fetchSeq; window.removeEventListener('beforeunload', beforeUnload) })
</script>

<style scoped>
.receipt-create {
  --rc-ink: #1A1D21;
  --rc-green: #1E7A5A;
  --rc-line: #ECEDEF;
  --rc-muted: #8B9096;
  container-type: inline-size;
  width: 100%;
  min-width: 0;
  min-height: calc(100dvh - 56px);
  display: flex;
  flex-direction: column;
  color: var(--rc-ink);
}
.rc-crumbs { display: flex; gap: 9px; color: var(--rc-muted); font-size: 12px; margin-bottom: 18px; }
.rc-crumbs span { color: #B1B6BB; }
.rc-head, .rc-title, .rc-section-head, .rc-section-label { display: flex; align-items: center; gap: 12px; }
.rc-head, .rc-section-head { justify-content: space-between; }
.rc-title h1 { margin: 0; font-size: 25px; font-weight: 700; letter-spacing: -.6px; }
.rc-badge { padding: 3px 9px; border-radius: 20px; font-size: 11px; color: var(--rc-green); background: #E6F2EC; white-space: nowrap; }
.rc-intro { color: var(--rc-muted); margin: 7px 0 27px; font-size: 12px; }
.rc-btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 7px 12px; font: inherit; font-size: 13px; white-space: nowrap; border: 1px solid var(--rc-line); border-radius: 7px; color: #4C535A; background: #fff; cursor: pointer; }
.rc-btn:hover:not(:disabled) { background: #F6F7F8; border-color: #CAD0D4; }
.receipt-create button:focus-visible { outline: 2px solid var(--rc-green); outline-offset: 3px; }
.receipt-create button:disabled { opacity: .5; cursor: not-allowed; }
.rc-btn svg, .rc-remove svg, .rc-hint svg, .rc-search-icon { width: 16px; height: 16px; flex-shrink: 0; }
.rc-section-head { border-bottom: 1px solid var(--rc-line); padding-bottom: 10px; margin-bottom: 17px; }
.rc-section-head h2 { margin: 0; color: var(--rc-muted); font-size: 11px; letter-spacing: .8px; font-weight: 700; }
.rc-section-note { color: #9AA0A6; font-size: 11px; }
.rc-meta { display: grid; grid-template-columns: minmax(190px, 1fr) minmax(230px, 1.6fr) minmax(180px, .8fr); gap: 22px; }
.rc-meta :deep(.n-form-item) { min-width: 0; }
.rc-meta :deep(.n-form-item-label) { font-size: 12px; color: #656D74; padding-bottom: 7px; }
.rc-meta :deep(.n-date-picker) { width: 100%; }
.rc-payment { display: flex; align-items: center; flex-wrap: wrap; gap: 12px 20px; padding: 17px 0 25px; font-size: 12px; }
.rc-payment-label { color: #656D74; }
.rc-payment-note { font-size: 11px; color: var(--rc-muted); }
.rc-payment :deep(.n-radio__label) { font-size: 12px; }
.rc-count { font-size: 10px; font-weight: 600; color: #6F787F; background: #F0F2F3; border-radius: 4px; padding: 1px 6px; }
.rc-filters { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-bottom: 12px; }
.rc-filters > .n-input { width: 290px; max-width: 100%; }
.rc-date-filter { display: flex; align-items: center; gap: 9px; font-size: 12px; color: #747C83; }
.rc-date-filter :deep(.n-date-picker) { width: 165px; }
.rc-text-btn { font: inherit; font-size: 12px; color: var(--rc-green); border: 0; background: transparent; cursor: pointer; padding: 5px 0; }
.rc-text-btn:hover:not(:disabled) { text-decoration: underline; }
.rc-source-table, .rc-detail-table { border: 1px solid var(--rc-line); border-radius: 9px; background: #fff; overflow: hidden; }
.rc-source-grid { display: grid; grid-template-columns: 24px minmax(180px, 2fr) minmax(110px, 1fr) 75px minmax(110px, 1fr) minmax(90px, .8fr) minmax(125px, 1fr); align-items: center; gap: 14px; padding: 12px 16px; }
.rc-source-head, .rc-detail-head { background: #F8F9FA; color: var(--rc-muted); font-size: 11px; border-bottom: 1px solid var(--rc-line); }
.rc-source-scroll { max-height: 330px; overflow: auto; overscroll-behavior: contain; }
.rc-source-row { border-bottom: 1px solid var(--rc-line); font-size: 12px; }
.rc-source-row:last-child { border-bottom: 0; }
.rc-source-row.is-selected { background: #F1F8F4; }
.rc-part { display: flex; align-items: center; gap: 10px; min-width: 0; }
.rc-part :deep(.n-image) { flex-shrink: 0; border-radius: 6px; overflow: hidden; }
.rc-image-placeholder { display: grid; place-items: center; width: 38px; height: 38px; flex-shrink: 0; border-radius: 6px; background: #F3F5F4; color: #B1BCB5; }
.rc-image-placeholder svg { width: 19px; height: 19px; }
.rc-part-text, .rc-detail-part > div { min-width: 0; overflow-wrap: anywhere; }
.rc-part-text strong, .rc-detail-part strong { display: block; font-size: 12px; font-weight: 550; }
.rc-part-text code, .rc-detail-part code, .rc-source-order code { display: block; font-size: 10px; color: #89939A; overflow-wrap: anywhere; }
.rc-part-text small, .rc-detail-part small, .rc-source-order small { display: block; color: var(--rc-muted); font-size: 10px; margin-top: 3px; }
.rc-composite { font-family: inherit; padding: 1px 4px; margin-left: 5px; background: #E6ECE8; color: #637B6C; border-radius: 3px; }
.rc-source-order code { color: #566A5E; font-size: 11px; }
.rc-method { color: #65736A; }
.rc-source-progress { color: #7E878E; font-variant-numeric: tabular-nums; }
.rc-remaining { color: var(--rc-green); font-size: 14px; font-variant-numeric: tabular-nums; }
.rc-remaining small { font-size: 11px; font-weight: 400; }
.rc-source-price { min-width: 0; }
.rc-source-price :deep(.n-input-number) { width: 100%; min-width: 0; }
.rc-source-price small { display: block; margin-top: 4px; color: var(--rc-muted); font-size: 10px; }
.rc-hint { display: flex; align-items: flex-start; gap: 6px; color: #9AA1A7; font-size: 11px; margin: 12px 0 25px; }
.rc-hint svg { width: 13px; height: 13px; margin-top: 2px; }
.rc-detail-grid { display: grid; grid-template-columns: minmax(190px, 2fr) minmax(135px, 1.1fr) minmax(120px, 1fr) minmax(130px, 1fr) minmax(110px, 1fr) 30px; gap: 16px; align-items: start; padding: 13px 16px; }
.rc-detail-head { align-items: center; }
.rc-detail-head > span:last-child { text-align: center; }
.rc-detail-row { border-bottom: 1px solid var(--rc-line); padding-top: 18px; padding-bottom: 18px; }
.rc-detail-row:last-child { border-bottom: 0; }
.rc-detail-part { display: flex; align-items: flex-start; gap: 10px; padding-top: 3px; }
.rc-row-number { font-size: 10px; color: #ABB1B6; padding-top: 1px; font-variant-numeric: tabular-nums; }
.rc-field { min-width: 0; }
.rc-field :deep(.n-input-number) { width: 100%; min-width: 0; }
.rc-field small { display: block; font-size: 10px; color: #9AA1A7; margin-top: 5px; }
.rc-input-unit { display: flex; align-items: center; gap: 7px; }
.rc-input-unit > span { flex-shrink: 0; color: #7E878E; font-size: 11px; }
.rc-line-amount { padding-top: 7px; color: #3E5548; font-size: 13px; font-weight: 550; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.rc-line-amount.is-unpriced, .rc-unpriced { color: #A07B3C; }
.rc-remove { display: grid; place-items: center; color: #A0A7AD; border: 0; background: transparent; width: 30px; height: 34px; border-radius: 6px; cursor: pointer; }
.rc-remove:hover:not(:disabled) { background: #FFF0F0; color: #D94950; }
.rc-mobile-label { display: none; }
.rc-empty { text-align: center; color: var(--rc-muted); padding: 30px 16px; font-size: 13px; border-radius: 9px; background: #FAFBFB; }
.rc-empty p { margin: 0 0 6px; }
.rc-empty > span { display: block; font-size: 11px; }
.rc-error, .rc-created { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; padding: 10px 12px; border-radius: 7px; background: #FFF8EB; color: #9B7434; font-size: 12px; margin: 10px 0; }
.rc-created { background: #E6F2EC; color: var(--rc-green); }
.rc-detail-part .rc-invalid, .rc-field .rc-invalid { color: #C85A54; font-size: 11px; }
.rc-cost-created { color: #1E7A5A; font-size: 13px; }
.rc-footer { position: sticky; bottom: -28px; margin-top: auto; padding: 18px 0; border-top: 1px solid var(--rc-line); background: #F6F7F8F5; backdrop-filter: blur(12px); display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 16px; z-index: 2; }
.rc-summary { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; color: var(--rc-muted); font-size: 12px; }
.rc-summary > span + span { padding-left: 12px; border-left: 1px solid #E0E4E6; }
.rc-summary strong { color: var(--rc-ink); font-size: 15px; font-weight: 650; font-variant-numeric: tabular-nums; }
.rc-footer-actions { display: flex; align-items: center; gap: 10px; margin-left: auto; }
.rc-total { margin-right: 12px; text-align: right; }
.rc-total > span { display: block; color: var(--rc-muted); font-size: 10px; }
.rc-total strong { font-size: 21px; font-weight: 650; color: var(--rc-green); font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
@container (max-width: 1050px) {
  .rc-source-grid { grid-template-columns: 20px minmax(145px, 2fr) 100px 60px minmax(95px, 1fr) 80px minmax(120px, 1fr); gap: 10px; }
  .rc-detail-grid { grid-template-columns: minmax(150px, 1.5fr) minmax(112px, 1fr) minmax(95px, .8fr) minmax(112px, 1fr) minmax(85px, .8fr) 28px; gap: 10px; padding-left: 12px; padding-right: 12px; }
  .rc-meta { gap: 14px; }
}
@container (max-width: 820px) {
  .rc-meta { grid-template-columns: minmax(155px, 1fr) minmax(170px, 1.2fr) minmax(155px, 1fr); }
  .rc-source-head { display: flex; }
  .rc-source-head > span { display: none; }
  .rc-source-head::after { content: '选择当前筛选的全部配件'; }
  .rc-source-row { grid-template-columns: 22px minmax(0, 1fr) minmax(100px, .5fr); gap: 8px 12px; }
  .rc-source-row > .n-checkbox { grid-column: 1; grid-row: 1 / 3; }
  .rc-part { grid-column: 2; }
  .rc-source-order { grid-column: 3; grid-row: 1; }
  .rc-method { grid-column: 2; grid-row: 2; padding-left: 48px; font-size: 11px; }
  .rc-source-progress { grid-column: 2; font-size: 11px; }
  .rc-remaining { grid-column: 3; font-size: 13px; }
  .rc-source-price { grid-column: 2 / -1; width: 200px; max-width: 100%; }
  .rc-source-row .rc-mobile-label { display: block; font-size: 10px; color: var(--rc-muted); font-weight: 400; }
  .rc-detail-head { display: none; }
  .rc-detail-row { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr) 28px; gap: 14px; }
  .rc-detail-part { grid-column: 1 / 4; }
  .rc-remove { grid-column: 4; grid-row: 1; }
  .rc-qty-field { grid-column: 1; }
  .rc-field .rc-mobile-label, .rc-line-amount .rc-mobile-label { display: block; color: var(--rc-muted); font-size: 10px; font-weight: 400; margin-bottom: 5px; }
  .rc-line-amount { grid-column: 1 / -1; display: flex; align-items: center; gap: 10px; padding: 0; }
  .rc-line-amount .rc-mobile-label { margin: 0; }
}
@container (max-width: 580px) {
  .rc-head { align-items: flex-start; gap: 8px; }
  .rc-title { flex-wrap: wrap; gap: 6px; }
  .rc-title h1 { font-size: 21px; }
  .rc-head > .rc-btn { font-size: 11px; padding: 6px 8px; }
  .rc-head > .rc-btn svg { display: none; }
  .rc-badge { font-size: 10px; }
  .rc-intro { font-size: 11px; margin-bottom: 24px; }
  .rc-meta { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 15px 12px; }
  .rc-meta-note { grid-column: 1 / -1; grid-row: 2; }
  .rc-section-note { display: none; }
  .rc-payment { gap: 8px 12px; }
  .rc-payment-note { flex-basis: 100%; }
  .rc-filters { gap: 10px; }
  .rc-filters > .n-input { width: 100%; }
  .rc-source-scroll { max-height: 360px; }
  .rc-source-grid { padding-left: 12px; padding-right: 12px; }
  .rc-source-row { grid-template-columns: 20px minmax(0, 1fr); gap: 8px 10px; }
  .rc-source-order { grid-column: 2; grid-row: 2; display: flex; align-items: center; gap: 8px; }
  .rc-source-order small { margin: 0; }
  .rc-method { grid-column: 2; grid-row: 3; padding: 0; }
  .rc-source-progress { grid-column: 2; }
  .rc-remaining { grid-column: 2; }
  .rc-source-price { grid-column: 2; }
  .rc-source-row .rc-mobile-label { display: inline; margin-right: 8px; }
  .rc-source-row > .n-checkbox { align-self: start; padding-top: 9px; }
  .rc-detail-row { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 13px 12px; padding: 14px 12px; }
  .rc-detail-part { grid-column: 1 / -1; grid-row: 1; padding-right: 30px; }
  .rc-remove { grid-column: 2; grid-row: 1; justify-self: end; }
  .rc-qty-field { grid-column: 1; grid-row: 2; }
  .rc-weight-field { grid-column: 2; grid-row: 2; }
  .rc-line-amount { grid-column: 2; grid-row: 3; flex-direction: column; align-items: flex-end; justify-content: center; }
  .rc-price-field { grid-column: 1; grid-row: 3; }
  .rc-footer { padding: 13px 0; gap: 12px; }
  .rc-summary { font-size: 11px; gap: 8px; }
  .rc-summary > span + span { padding-left: 8px; }
  .rc-summary strong { font-size: 13px; }
  .rc-footer-actions { width: 100%; flex-wrap: wrap; gap: 8px; }
  .rc-total { flex: 1; min-width: 0; text-align: left; margin-right: 0; }
  .rc-total strong { font-size: 18px; }
  .rc-footer-actions > .rc-btn { font-size: 12px; padding: 7px 8px; }
  .rc-footer-actions :deep(.n-button) { font-size: 12px; padding-left: 10px; padding-right: 10px; }
}
@media (max-width: 767px) {
  .receipt-create { min-height: calc(100dvh - 32px); }
  .rc-crumbs { padding-left: 36px; }
  .rc-footer { bottom: -16px; }
}
</style>
