<template>
  <div class="handcraft-receipt-create">
    <div class="hcr-crumbs">生产管理 <span>/</span> 手工回收 <span>/</span> 新建</div>
    <header class="hcr-head">
      <div><n-h2>新建手工回收单</n-h2><n-tag size="small" :bordered="false" :type="createdReceiptId ? 'success' : 'default'">{{ createdReceiptId ? '已创建' : '录入中' }}</n-tag></div>
      <n-button :disabled="locked" @click="goBack">{{ backLabel }}</n-button>
    </header>
    <p class="hcr-intro">选择回收来源，按实际数量录入产出与退料，再核对手工费。</p>
    <n-alert v-if="createdReceiptId" type="success" class="hcr-alert" :show-icon="false">回收单 {{ createdReceiptId }} 已创建，无需重复提交。<n-button v-if="!costDiffVisible" text type="primary" @click="goToCreated">查看已创建回收单</n-button></n-alert>

    <div class="hcr-layout">
      <div class="hcr-main">
        <n-card title="回收信息" size="small">
          <n-form label-placement="top" :show-feedback="false" :disabled="locked || switchPending || reviewVisible" class="hcr-meta">
            <n-form-item label="手工商家" required>
              <n-select :value="supplierName" :options="supplierOptions" :loading="loadingSuppliers" :disabled="!!scopeCode || locked || switchPending || reviewVisible" filterable tag clearable placeholder="选择或输入商家名称" aria-label="手工商家" @update:value="onSupplierChange" />
            </n-form-item>
            <n-form-item label="回执编码（选填）">
              <div class="hcr-code-field"><n-input v-model:value="receiptCode" clearable placeholder="扫码或输入 5 位编码" :input-props="{ 'aria-label': '回执编码', maxlength: 5 }" @keyup.enter="applyReceiptCode"><template #prefix>⌗</template></n-input><n-button :loading="resolvingCode" :disabled="locked || switchPending || reviewVisible || !receiptCode.trim()" @click="applyReceiptCode">定位</n-button></div>
            </n-form-item>
            <n-form-item label="创建日期"><n-date-picker v-model:value="createdAtTs" type="date" clearable placeholder="留空使用当前时间" aria-label="回收单创建日期" /></n-form-item>
            <n-form-item label="备注"><n-input v-model:value="note" placeholder="本次回收说明（选填）" :input-props="{ 'aria-label': '回收备注' }" /></n-form-item>
          </n-form>
          <p class="hcr-hint">回执编码可自动定位商家；扫码后按回车，或点击“定位”。切换来源前会确认已填内容。</p>
          <div v-if="supplierLoadError" class="hcr-feedback" role="alert">商家列表加载失败，仍可输入名称。<n-button text type="primary" :disabled="locked" @click="loadSuppliers">重试</n-button></div>
          <div v-if="codeError" class="hcr-feedback is-error" role="alert">{{ codeError }}</div>
          <div v-if="scopeCode" class="hcr-scope"><span>已定位回执 <strong>{{ scopeCode }}</strong> · 仅显示该手工单的来源</span><n-button text type="primary" :disabled="busy || locked || reviewVisible" @click="clearReceiptScope">清除定位</n-button></div>
        </n-card>

        <n-card title="产出回收" size="small">
          <template #header-extra><n-space align="center" :size="8"><n-tag size="small" :bordered="false">{{ pendingOutputs.length }} 条来源</n-tag><n-button size="small" :disabled="!supplierName || busy || locked || reviewVisible" @click="fetchPendingItems">刷新</n-button></n-space></template>
          <p class="hcr-hint hcr-top-hint">包含饰品及产出配件，含已结清来源。数量为整数，允许按实际数量超收。</p>
          <div class="hcr-filters">
            <n-input v-model:value="filterKeyword" :disabled="locked || reviewVisible" clearable placeholder="产出名称 / 商品编号 / 手工单" :input-props="{ 'aria-label': '搜索产出来源' }"><template #prefix><SearchOutline class="hcr-icon" /></template></n-input>
            <div class="hcr-date-filter"><span>单据日期</span><n-date-picker v-model:value="filterDateOn" :disabled="locked || reviewVisible" type="date" clearable placeholder="全部日期" aria-label="筛选来源单据日期" /></div>
          </div>
          <div class="hcr-list-tools">
            <n-radio-group v-model:value="progressFilter" :disabled="locked || reviewVisible" size="small" aria-label="产出来源范围"><n-radio-button value="all">全部来源</n-radio-button><n-radio-button value="remaining">尚有未收</n-radio-button><n-radio-button value="selected">已选 {{ selectedOutputs.length }}</n-radio-button></n-radio-group>
            <n-checkbox :checked="allPageSelected" :indeterminate="somePageSelected && !allPageSelected" :disabled="!pageOutputs.length || busy || locked || reviewVisible" aria-label="选择本页来源" @update:checked="togglePage">选择本页</n-checkbox>
          </div>
          <p v-if="hiddenSelectedCount" class="hcr-hidden-note">另有 {{ hiddenSelectedCount }} 条已选来源未在当前筛选结果中显示，仍计入本次回收。<n-button text type="primary" size="small" :disabled="locked || reviewVisible" @click="showSelected">查看已选</n-button></p>
          <n-spin :show="loadingItems">
            <div v-if="fetchError" class="hcr-empty" role="alert"><p>回收来源加载失败，已填写的明细仍保留，暂不能提交。</p><n-button :disabled="locked || busy" @click="fetchPendingItems">重试加载</n-button></div>
            <div v-else-if="!pageOutputs.length" class="hcr-empty"><n-empty :description="!supplierName ? '请先选择商家或输入回执编码' : loadingItems ? '正在加载回收来源' : !pendingOutputs.length ? '该来源暂无产出，可检查配件退料' : '没有符合筛选条件的来源'" /><n-button v-if="supplierName && (filterKeyword || filterDateOn != null || progressFilter !== 'all')" text type="primary" @click="clearFilters">清除筛选</n-button></div>
            <div v-else class="hcr-sources">
              <article v-for="row in pageOutputs" :key="sourceKey(row)" class="hcr-source" :class="{ 'is-selected': selectedKeys.has(sourceKey(row)), 'is-unavailable': row._unavailable }">
                <div class="hcr-product-line">
                  <n-checkbox :checked="selectedKeys.has(sourceKey(row))" :disabled="locked || busy || reviewVisible" :aria-label="`选择 ${row.item_name} ${row.handcraft_order_id} 产出 ${row.id}`" @update:checked="value => toggleOutput(row, value)" />
                  <n-image v-if="row.item_image" :src="row.item_image" :alt="row.item_name" :width="44" :height="44" object-fit="cover" />
                  <div v-else class="hcr-image-placeholder"><CubeOutline /></div>
                  <div class="hcr-product-copy"><div class="hcr-product-name">{{ row.item_name }} <n-tag size="small" :bordered="false">{{ row.item_type === 'part' ? '产出配件' : '饰品' }}{{ row.is_composite ? ' · 组合' : '' }}</n-tag></div><div class="hcr-source-meta"><code>{{ row.item_id }}</code><n-button text type="primary" size="tiny" @click="openOrderPeek(row.handcraft_order_id)">{{ row.handcraft_order_id }} ↗</n-button><span>单据 {{ row.created_at?.slice(0, 10) || '—' }}</span></div></div>
                  <div class="hcr-balance"><small>{{ getRemaining(row) ? '尚未收回' : '来源已结清' }}</small><strong>{{ sourceBalance(row) }} <span>{{ row.unit || '个' }}</span></strong></div>
                </div>
                <div v-if="row._unavailable" class="hcr-feedback is-error">该来源已不可用，请取消勾选后重新选择。</div>
                <template v-if="selectedKeys.has(sourceKey(row))">
                  <div class="hcr-entry">
                    <div class="hcr-field"><span>本次回收 <em>*</em></span><div class="hcr-input-unit"><n-input-number v-model:value="itemInputs[sourceKey(row)].qty" :disabled="locked || reviewVisible || row._unavailable" :min="1" :precision="0" :step="1" :show-button="false" placeholder="实际数量" :input-props="{ 'aria-label': `产出 ${row.id} 本次回收数量` }" /><span>{{ row.unit || '个' }}</span></div></div>
                    <div class="hcr-field"><span>手工单价</span><n-input-number v-model:value="itemInputs[sourceKey(row)].price" :disabled="locked || reviewVisible || row._unavailable" :min="0" :precision="7" :step="0.1" :format="fmtPrice" :parse="parseNum" :show-button="false" placeholder="待定价" :input-props="{ 'aria-label': `产出 ${row.id} 手工单价` }"><template #prefix>¥</template></n-input-number><small>元 / {{ row.unit || '个' }}</small></div>
                    <div class="hcr-line-amount"><span>本行金额</span><strong>{{ lineAmount(row) == null ? '待定价' : `¥ ${fmtMoney(lineAmount(row))}` }}</strong></div>
                  </div>
                  <div class="hcr-entry-note"><span :class="{ 'hcr-over': isOver(row) }">{{ afterReceiptNote(row) }}</span><n-button text size="small" :disabled="locked || reviewVisible" :aria-expanded="!!weightExpanded[sourceKey(row)]" @click="weightExpanded[sourceKey(row)] = !weightExpanded[sourceKey(row)]">{{ weightExpanded[sourceKey(row)] ? '收起重量' : '记录重量（选填）' }}</n-button></div>
                  <div v-if="weightExpanded[sourceKey(row)]" class="hcr-weight"><span>本次重量</span><n-input-number v-model:value="itemInputs[sourceKey(row)].weight" :disabled="locked || reviewVisible || row._unavailable" :min="0" :show-button="false" placeholder="选填" :input-props="{ 'aria-label': `产出 ${row.id} 本次重量` }" /><n-select v-model:value="itemInputs[sourceKey(row)].weight_unit" :disabled="locked || reviewVisible" :options="weightUnits" :aria-label="`产出 ${row.id} 重量单位`" /><small>不按重量计算手工费</small></div>
                </template>
              </article>
            </div>
          </n-spin>
          <div class="hcr-list-footer"><span>同款不同来源分别核对 · 日期为单据创建日期</span><n-pagination v-if="filteredOutputs.length > pageSize" v-model:page="sourcePage" :page-size="pageSize" :item-count="filteredOutputs.length" :page-slot="isMobile ? 3 : 5" :disabled="locked || reviewVisible" size="small" /></div>
          <p class="hcr-hint">未收数取来源结清余额（实收与已确认损耗均会减少余额），不是只扣实收；未收差额不会自动记为损耗。</p>
        </n-card>

        <n-card size="small" class="hcr-materials"><div class="hcr-material-head"><div><h3>配件退料 <n-tag size="small" :bordered="false">选填</n-tag></h3><p>未用完的材料单独退回，不计入产出及手工费。</p></div><n-button :disabled="!supplierName || busy || locked || reviewVisible" @click="partModalShow = true">{{ selectedParts.length ? `编辑退料（${selectedParts.length}）` : '＋ 添加退料' }}</n-button></div><div v-if="selectedParts.length" class="hcr-return-list"><div v-for="part in selectedParts" :key="part.id"><span>{{ part.item_name }} <small>{{ part.handcraft_order_id }}</small></span><strong>{{ formatQty(partReturnSel[String(part.id)]) }} {{ part.unit || '个' }}</strong><span v-if="part._unavailable" class="hcr-over">来源已不可用</span><n-button text size="small" :disabled="locked || reviewVisible" :aria-label="`移除退料 ${part.item_name} ${part.id}`" @click="removePart(part)">移除</n-button></div></div></n-card>
      </div>

      <aside class="hcr-summary" aria-label="本次回收核对">
        <n-card title="本次回收" size="small">
          <p class="hcr-summary-supplier">{{ supplierName || '尚未选择商家' }}</p>
          <div class="hcr-summary-label"><span>产出回收</span><span>{{ selectedOutputs.length }} 条来源</span></div>
          <n-scrollbar style="max-height: 290px"><div v-for="row in selectedOutputs" :key="sourceKey(row)" class="hcr-summary-row"><div><strong>{{ row.item_name }}</strong><small>{{ row.handcraft_order_id }} · {{ formatQty(itemInputs[sourceKey(row)]?.qty) }} {{ row.unit || '个' }}</small><small v-if="row._unavailable" class="hcr-over">来源已不可用，请移除</small></div><span>{{ lineAmount(row) == null ? '待定价' : `¥ ${fmtMoney(lineAmount(row))}` }}</span></div><p v-if="!selectedOutputs.length" class="hcr-hint">尚未选择回收产出</p></n-scrollbar>
          <div v-if="draftSummary.quantities.length" class="hcr-quantities">回收数量：<span v-for="entry in draftSummary.quantities" :key="entry.unit">{{ formatQty(entry.qty) }} {{ entry.unit }}</span></div>
          <div class="hcr-summary-label hcr-summary-material"><span>配件退料</span><span>{{ selectedParts.length }} 项 · 不计费</span></div>
          <div class="hcr-total"><span>{{ draftSummary.unpricedCount ? '已定价手工费合计' : '手工费合计' }}</span><strong>¥ {{ fmtMoney(draftSummary.amount) }}</strong></div>
          <p class="hcr-hint">{{ draftSummary.unpricedCount ? `${draftSummary.unpricedCount} 条产出待定价；留空不表示免费。` : '按本次回收数量 × 手工单价计算。' }}</p>
          <div class="hcr-payment"><span>付款状态</span><n-radio-group v-model:value="status" :disabled="locked || reviewVisible" aria-label="付款状态"><n-radio value="未付款">未付款</n-radio><n-radio value="已付款">已付款</n-radio></n-radio-group><p v-if="status === '已付款'" class="hcr-hint">已付款单据创建后锁定明细，请仔细核对。</p></div>
          <n-alert v-if="draftSummary.overCount" type="warning" :show-icon="false" class="hcr-alert">{{ draftSummary.overCount }} 条产出超过尚未收回数量，允许实际超收，请核实数量。</n-alert>
          <n-alert v-if="unavailableCount" type="error" :show-icon="false" class="hcr-alert">{{ unavailableCount }} 条已选来源已不可用，请移除或重新选择。</n-alert>
          <n-button type="primary" block class="hcr-review-button" :disabled="!canReview" :loading="submitting" @click="review">核对回收单</n-button>
        </n-card>
        <p class="hcr-hint">创建后按现有规则入库、计费；若有配件不足或手工费成本变动，仍会单独提示。</p>
      </aside>
    </div>

    <div v-if="isMobile" class="hcr-mobile-bar"><div><small>已选 {{ selectedOutputs.length }} 条产出 / {{ selectedParts.length }} 项退料</small><strong>¥ {{ fmtMoney(draftSummary.amount) }}</strong><small v-if="draftSummary.unpricedCount">含 {{ draftSummary.unpricedCount }} 条待定价</small></div><n-button type="primary" :disabled="!canReview" :loading="submitting" @click="review">核对回收单</n-button></div>

    <part-return-modal :show="partModalShow" :parts="pendingParts" :selections="partReturnSel" :is-mobile="isMobile" @confirm="onPartConfirm" @cancel="partModalShow = false" @update:show="partModalShow = $event" />
    <handcraft-order-peek-modal :show="peekShow" :order-id="peekOrderId" @update:show="peekShow = $event" />

    <n-modal v-model:show="reviewVisible" preset="card" title="核对本次回收单" class="hcr-modal" :mask-closable="!submitting" :close-on-esc="!submitting" :closable="!submitting" :style="modalStyle" :content-style="modalContentStyle">
      <n-descriptions :column="isMobile ? 1 : 2" label-placement="left"><n-descriptions-item label="手工商家">{{ supplierName }}</n-descriptions-item><n-descriptions-item label="创建日期">{{ tsToDateStr(createdAtTs) || '使用当前时间' }}</n-descriptions-item><n-descriptions-item label="付款状态">{{ status }}</n-descriptions-item><n-descriptions-item v-if="scopeCode" label="定位回执">{{ scopeCode }}</n-descriptions-item><n-descriptions-item v-if="note" label="备注">{{ note }}</n-descriptions-item></n-descriptions>
      <h3 class="hcr-review-heading">产出回收 · {{ selectedOutputs.length }} 条来源</h3>
      <div v-for="row in selectedOutputs" :key="sourceKey(row)" class="hcr-review-row"><div><strong>{{ row.item_name }}</strong><small>{{ row.handcraft_order_id }} · {{ formatQty(itemInputs[sourceKey(row)].qty) }} {{ row.unit || '个' }} × {{ itemInputs[sourceKey(row)].price == null ? '单价未填' : `¥ ${fmtMoney(itemInputs[sourceKey(row)].price)}` }}</small><small v-if="itemInputs[sourceKey(row)].weight != null">重量 {{ formatQty(itemInputs[sourceKey(row)].weight) }} {{ itemInputs[sourceKey(row)].weight_unit }}</small><small v-if="isOver(row)" class="hcr-over">{{ afterReceiptNote(row) }}</small></div><strong>{{ lineAmount(row) == null ? '待定价' : `¥ ${fmtMoney(lineAmount(row))}` }}</strong></div>
      <h3 v-if="selectedParts.length" class="hcr-review-heading">配件退料 · 不计手工费</h3>
      <div v-for="part in selectedParts" :key="part.id" class="hcr-review-row"><div><strong>{{ part.item_name }}</strong><small>{{ part.handcraft_order_id }}</small><small v-if="partReturnSel[String(part.id)] > getRemaining(part)" class="hcr-over">超出未退 {{ formatQty(partReturnSel[String(part.id)] - getRemaining(part)) }} {{ part.unit || '个' }} · 允许实际超收</small></div><strong>{{ formatQty(partReturnSel[String(part.id)]) }} {{ part.unit || '个' }}</strong></div>
      <div class="hcr-review-total"><span>{{ draftSummary.unpricedCount ? '已定价手工费合计' : '手工费合计' }}</span><strong>¥ {{ fmtMoney(draftSummary.amount) }}</strong></div>
      <p v-if="draftSummary.unpricedCount" class="hcr-hint">{{ draftSummary.unpricedCount }} 条产出未填单价，可在回收后按现有规则补录。</p>
      <template #footer><n-space justify="end"><n-button :disabled="submitting" @click="reviewVisible = false">返回修改</n-button><n-button type="primary" :loading="submitting" :disabled="locked || busy || fetchError" @click="submit">确认创建回收单</n-button></n-space></template>
    </n-modal>

    <n-modal v-model:show="costDiffVisible" :mask-closable="false" :close-on-esc="false" :closable="false" preset="card" title="手工费成本变动确认" :style="modalStyle" :content-style="modalContentStyle">
      <p class="hcr-cost-created">回收单 {{ createdReceiptId }} 已创建，请选择是否同步配件成本，无需再次提交。</p><p>当前手工费与已有配件手工费不同，是否更新手工费成本？</p>
      <n-data-table :columns="costColumns" :data="costDiffs" :bordered="false" :scroll-x="480" size="small" />
      <template #footer><n-space justify="end"><n-button :disabled="costDiffUpdating" @click="skipCostUpdate">跳过</n-button><n-button type="primary" :loading="costDiffUpdating" @click="confirmCostUpdate">确认更新</n-button></n-space></template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, h } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useMessage, useDialog, NButton, NSelect, NInput, NInputNumber, NCard, NH2, NRadioGroup, NRadio, NRadioButton, NDataTable, NSpin, NEmpty, NImage, NModal, NDatePicker, NCheckbox, NForm, NFormItem, NTag, NSpace, NAlert, NScrollbar, NPagination, NDescriptions, NDescriptionsItem } from 'naive-ui'
import { SearchOutline, CubeOutline } from '@vicons/ionicons5'
import { useHandcraftSummaryReturn } from '@/composables/useHandcraftSummaryReturn'
import { listHandcraftPendingReceiveItems, createHandcraftReceipt } from '@/api/handcraftReceipts'
import { getHandcraftSuppliers, getHandcraftByReceiptCode } from '@/api/handcraft'
import { batchUpdatePartCosts } from '@/api/parts'
import HandcraftOrderPeekModal from '@/components/HandcraftOrderPeekModal.vue'
import PartReturnModal from './PartReturnModal.vue'
import { fmtMoney, fmtPrice, parseNum } from '@/utils/ui'
import { remainingQuantity as getRemaining, sourceBalance } from '@/utils/receiptQuantity'
import { tsToDateStr } from '@/utils/date'
import { useIsMobile } from '@/composables/useIsMobile'
import { handcraftSourceKey as sourceKey, createHandcraftReceiptInput, filterHandcraftReceiptSources, handcraftReceiptLineAmount, summarizeHandcraftReceipt, handcraftReceiptItemPayload } from '@/utils/handcraftReceiptCreate'

const { summaryReturn, goBack, openCreated } = useHandcraftSummaryReturn()
const backLabel = computed(() => summaryReturn.value?.path === '/handcraft-output' ? '返回产出总览' : summaryReturn.value ? '返回汇总' : '返回')
const message = useMessage()
const dialog = useDialog()
const { isMobile } = useIsMobile()
const supplierName = ref(null), receiptCode = ref(''), scopeCode = ref(null)
const note = ref(''), createdAtTs = ref(null), status = ref('未付款')
const loadingSuppliers = ref(false), supplierLoadError = ref(false), supplierOptions = ref([])
const loadingItems = ref(false), fetchError = ref(false), resolvingCode = ref(false), codeError = ref(''), switchPending = ref(false)
const pendingOutputs = ref([]), pendingParts = ref([]), selectedOutputs = ref([]), selectedParts = ref([])
const itemInputs = reactive({}), partReturnSel = reactive({}), weightExpanded = reactive({})
const filterKeyword = ref(''), filterDateOn = ref(null), progressFilter = ref('all'), sourcePage = ref(1)
const pageSize = 20
const partModalShow = ref(false), reviewVisible = ref(false), submitting = ref(false), createdReceiptId = ref(null)
const peekShow = ref(false), peekOrderId = ref(null)
const costDiffVisible = ref(false), costDiffs = ref([]), costDiffUpdating = ref(false)
const locked = computed(() => submitting.value || !!createdReceiptId.value)
const busy = computed(() => loadingItems.value || resolvingCode.value || switchPending.value)
const selectedKeys = computed(() => new Set(selectedOutputs.value.map(sourceKey)))
const allOutputSources = computed(() => [...pendingOutputs.value, ...selectedOutputs.value.filter(row => row._unavailable)])
const filteredOutputs = computed(() => filterHandcraftReceiptSources(allOutputSources.value, { keyword: filterKeyword.value, dateOn: tsToDateStr(filterDateOn.value), progress: progressFilter.value, selectedKeys: selectedKeys.value }))
const pageOutputs = computed(() => filteredOutputs.value.slice((sourcePage.value - 1) * pageSize, sourcePage.value * pageSize))
const allPageSelected = computed(() => !!pageOutputs.value.length && pageOutputs.value.every(row => selectedKeys.value.has(sourceKey(row))))
const somePageSelected = computed(() => pageOutputs.value.some(row => selectedKeys.value.has(sourceKey(row))))
const hiddenSelectedCount = computed(() => selectedOutputs.value.filter(row => !filteredOutputs.value.some(visible => sourceKey(visible) === sourceKey(row))).length)
const draftSummary = computed(() => summarizeHandcraftReceipt(selectedOutputs.value, itemInputs))
const unavailableCount = computed(() => [...selectedOutputs.value, ...selectedParts.value].filter(row => row._unavailable).length)
const canReview = computed(() => !!supplierName.value?.trim() && !!(selectedOutputs.value.length || selectedParts.value.length) && !locked.value && !busy.value && !fetchError.value && !unavailableCount.value)
const lineAmount = row => handcraftReceiptLineAmount(itemInputs[sourceKey(row)])
const isOver = row => Number(itemInputs[sourceKey(row)]?.qty || 0) > getRemaining(row)
const formatQty = value => value == null ? '—' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
const afterReceiptNote = row => {
  const qty = itemInputs[sourceKey(row)]?.qty
  if (qty == null || qty <= 0) return '请填写实际回收数量'
  const difference = Number(qty) - getRemaining(row)
  return difference > 0 ? `超出未收 ${formatQty(difference)} ${row.unit || '个'} · 允许实际超收` : `本次后尚未收回 ${formatQty(-difference)} ${row.unit || '个'}`
}
const weightUnits = [{ label: 'g', value: 'g' }, { label: 'kg', value: 'kg' }]
const modalStyle = { width: '640px', maxWidth: 'calc(100vw - 24px)', maxHeight: '90dvh', display: 'flex', flexDirection: 'column' }
const modalContentStyle = { overflow: 'auto', minHeight: '0', flex: '1' }
const costColumns = [
  { title: '配件编号', key: 'part_id', width: 140 }, { title: '配件名称', key: 'part_name', minWidth: 120 },
  { title: '原手工费', key: 'current_value', width: 110, render: row => row.current_value != null ? `¥ ${fmtMoney(row.current_value)}` : '—' },
  { title: '新手工费', key: 'new_value', width: 110, render: row => h('strong', `¥ ${fmtMoney(row.new_value)}`) },
]
let fetchSeq = 0, codeSeq = 0, sourceVersion = 0, alive = true
const clearFilters = () => { filterKeyword.value = ''; filterDateOn.value = null; progressFilter.value = 'all'; sourcePage.value = 1 }
const showSelected = () => { clearFilters(); progressFilter.value = 'selected' }
watch([filterKeyword, filterDateOn, progressFilter], () => { sourcePage.value = 1 })
watch(() => filteredOutputs.value.length, count => { sourcePage.value = Math.min(sourcePage.value, Math.max(1, Math.ceil(count / pageSize))) })
watch(receiptCode, () => { ++codeSeq; resolvingCode.value = false; codeError.value = '' }, { flush: 'sync' })

async function loadSuppliers() {
  if (loadingSuppliers.value) return
  loadingSuppliers.value = true; supplierLoadError.value = false
  try {
    const { data } = await getHandcraftSuppliers()
    if (alive) supplierOptions.value = data.map(value => ({ label: value, value }))
  } catch (_) { if (alive) supplierLoadError.value = true }
  finally { if (alive) loadingSuppliers.value = false }
}

async function fetchPendingItems() {
  if (locked.value || reviewVisible.value) return
  const seq = ++fetchSeq
  if (!supplierName.value) { pendingOutputs.value = []; pendingParts.value = []; loadingItems.value = false; fetchError.value = false; return }
  const params = { supplier_name: supplierName.value, include_settled: true }
  if (scopeCode.value) params.receipt_code = scopeCode.value
  loadingItems.value = true; fetchError.value = false
  try {
    // Fetch the whole source scope; local filters never discard selected inputs.
    const { data } = await listHandcraftPendingReceiveItems(params)
    if (!alive || seq !== fetchSeq) return
    pendingOutputs.value = data.filter(row => row.is_output)
    pendingParts.value = data.filter(row => !row.is_output)
    const byKey = new Map(data.map(row => [sourceKey(row), row]))
    const reconcile = row => {
      const current = byKey.get(sourceKey(row))
      const input = itemInputs[sourceKey(row)]
      if (current && input) input.unit = current.unit || '个'
      return current || { ...row, _unavailable: true }
    }
    selectedOutputs.value = selectedOutputs.value.map(reconcile)
    selectedParts.value = selectedParts.value.map(reconcile)
  } catch (_) {
    if (!alive || seq !== fetchSeq) return
    pendingOutputs.value = []; pendingParts.value = []; fetchError.value = true
  } finally { if (alive && seq === fetchSeq) loadingItems.value = false }
}

function requestSourceChange(supplier, code = null) {
  if (locked.value || reviewVisible.value || switchPending.value) return
  supplier = supplier?.trim() || null
  if (supplier === supplierName.value && code === scopeCode.value) { receiptCode.value = code || ''; return }
  const version = sourceVersion
  const apply = () => {
    if (!alive || locked.value || reviewVisible.value || version !== sourceVersion) return
    ++sourceVersion; ++fetchSeq; ++codeSeq
    resolvingCode.value = false; fetchError.value = false
    supplierName.value = supplier; scopeCode.value = code; receiptCode.value = code || ''
    pendingOutputs.value = []; pendingParts.value = []; selectedOutputs.value = []; selectedParts.value = []
    for (const store of [itemInputs, partReturnSel, weightExpanded]) for (const key of Object.keys(store)) delete store[key]
    clearFilters(); fetchPendingItems()
  }
  if (selectedOutputs.value.length || selectedParts.value.length) {
    switchPending.value = true
    const finish = () => { switchPending.value = false }
    dialog.warning({
      title: '切换回收来源', content: '切换后将清空已选产出、数量、价格、重量和配件退料；创建日期、备注及付款状态保留。', positiveText: '清空并切换', negativeText: '保留当前内容',
      onPositiveClick: () => { apply(); finish() },
      onNegativeClick: () => { receiptCode.value = scopeCode.value || ''; finish() },
      onClose: () => { receiptCode.value = scopeCode.value || ''; finish() },
      onMaskClick: () => { receiptCode.value = scopeCode.value || ''; finish() },
    })
  } else apply()
}
const onSupplierChange = value => requestSourceChange(value)
const clearReceiptScope = () => requestSourceChange(supplierName.value)

async function applyReceiptCode() {
  if (locked.value || reviewVisible.value || switchPending.value) return
  const code = receiptCode.value.trim().toUpperCase()
  if (!code || code === scopeCode.value) return
  if (code.length !== 5) { codeError.value = '请输入 5 位回执编码'; return }
  const seq = ++codeSeq, version = sourceVersion
  resolvingCode.value = true; codeError.value = ''
  try {
    const { data: order } = await getHandcraftByReceiptCode(code)
    if (!alive || seq !== codeSeq || version !== sourceVersion) return
    if (!order.supplier_name?.trim()) { codeError.value = '该回执没有可用的手工商家，请核对手工单'; return }
    resolvingCode.value = false
    requestSourceChange(order.supplier_name, code)
  } catch (_) {
    if (alive && seq === codeSeq && version === sourceVersion) codeError.value = `回执 ${code} 定位失败，请核对编码后重试`
  } finally { if (alive && seq === codeSeq) resolvingCode.value = false }
}

function toggleOutput(row, checked) {
  if (locked.value || busy.value || reviewVisible.value) return
  const key = sourceKey(row)
  if (checked && !selectedKeys.value.has(key) && !row._unavailable) {
    if (!itemInputs[key]) itemInputs[key] = createHandcraftReceiptInput(row)
    selectedOutputs.value.push(row)
  } else if (!checked) selectedOutputs.value = selectedOutputs.value.filter(item => sourceKey(item) !== key)
}
function togglePage(checked) { for (const row of pageOutputs.value) toggleOutput(row, checked) }
function onPartConfirm(selections) {
  if (locked.value || busy.value || reviewVisible.value) return
  const rows = pendingParts.value.filter(row => Object.hasOwn(selections, String(row.id)))
  if (rows.length !== Object.keys(selections).length) { message.warning('部分退料来源已不可用，请重新选择'); return }
  try { for (const row of rows) handcraftReceiptItemPayload(row, { qty: selections[String(row.id)] }, supplierName.value?.trim()) }
  catch (error) { message.warning(error.message); return }
  for (const key of Object.keys(partReturnSel)) delete partReturnSel[key]
  Object.assign(partReturnSel, selections); selectedParts.value = rows; partModalShow.value = false
}
function removePart(row) {
  if (locked.value || reviewVisible.value) return
  delete partReturnSel[String(row.id)]
  selectedParts.value = selectedParts.value.filter(part => part.id !== row.id)
}
function openOrderPeek(id) { peekOrderId.value = id; peekShow.value = true }

function buildPayload() {
  if (!supplierName.value?.trim()) throw new Error('请先选择手工商家')
  const supplier = supplierName.value.trim()
  const items = [
    ...selectedOutputs.value.map(row => handcraftReceiptItemPayload(row, itemInputs[sourceKey(row)], supplier)),
    ...selectedParts.value.map(row => handcraftReceiptItemPayload(row, { qty: partReturnSel[String(row.id)] }, supplier)),
  ]
  if (!items.length) throw new Error('请至少选择一条产出或一项配件退料')
  const date = tsToDateStr(createdAtTs.value)
  if (createdAtTs.value != null && !date) throw new Error('请核对回收单创建日期')
  return { supplier_name: supplier, items, status: status.value, note: note.value, ...(date ? { created_at: date } : {}) }
}
function review() {
  if (!canReview.value) return
  try { buildPayload(); reviewVisible.value = true }
  catch (error) { message.warning(error.message) }
}
async function goToCreated() {
  if (!createdReceiptId.value || costDiffVisible.value) return
  try { await openCreated(`/handcraft-receipts/${createdReceiptId.value}`) }
  catch (_) { message.warning('单据已创建，可点击“查看已创建回收单”继续') }
}
async function submit() {
  if (locked.value || busy.value || fetchError.value || !reviewVisible.value) return
  let payload
  try { payload = buildPayload() } catch (error) { message.warning(error.message); return }
  submitting.value = true
  try {
    const { data } = await createHandcraftReceipt(payload)
    createdReceiptId.value = data.id; reviewVisible.value = false
    if (data.parts_shortfall?.length) message.warning(`部分产出项所需配件不足：${data.parts_shortfall.map(part => `${part.part_name}：缺 ${part.shortfall_qty}`).join('；')}`, { duration: 8000 })
    message.success('创建成功')
    if (data.cost_diffs?.length) { costDiffs.value = data.cost_diffs; costDiffVisible.value = true }
    else await goToCreated()
  } catch (_) {
    // The API interceptor reports errors. Keep the review and complete draft.
  } finally { submitting.value = false }
}
async function confirmCostUpdate() {
  if (costDiffUpdating.value || !createdReceiptId.value) return
  costDiffUpdating.value = true
  try {
    await batchUpdatePartCosts({ updates: costDiffs.value.map(row => ({ part_id: row.part_id, field: row.field, value: row.new_value, source_id: createdReceiptId.value })) })
    message.success('配件手工费成本已更新'); costDiffVisible.value = false; await goToCreated()
  } catch (_) { message.error('成本更新失败，请重试，或跳过成本更新') }
  finally { costDiffUpdating.value = false }
}
function skipCostUpdate() { if (!costDiffUpdating.value) { costDiffVisible.value = false; goToCreated() } }

onBeforeRouteLeave(to => {
  if (createdReceiptId.value && !costDiffVisible.value && to.path === `/handcraft-receipts/${createdReceiptId.value}`) return true
  if (locked.value) { message.warning(costDiffVisible.value ? '回收单已创建，请先选择是否更新配件成本' : '正在提交或单据已创建，请勿重复操作'); return false }
})
const beforeUnload = event => { if (locked.value) { event.preventDefault(); event.returnValue = '' } }
onMounted(() => { loadSuppliers(); window.addEventListener('beforeunload', beforeUnload) })
onBeforeUnmount(() => { alive = false; ++fetchSeq; ++codeSeq; window.removeEventListener('beforeunload', beforeUnload) })
</script>

<style scoped>
.handcraft-receipt-create { --hcr-line: #ECEDEF; --hcr-muted: #8B9096; --hcr-primary: #1E7A5A; width: 100%; min-width: 0; max-width: 1440px; container-type: inline-size; color: #1A1D21; }
.hcr-crumbs { display: flex; gap: 9px; color: var(--hcr-muted); font-size: 12px; margin-bottom: 18px; }
.hcr-crumbs span { color: #B1B6BB; }
.hcr-head, .hcr-head > div { display: flex; align-items: center; gap: 12px; }
.hcr-head { justify-content: space-between; }
.hcr-head :deep(.n-h2) { margin: 0; font-size: 25px; }
.hcr-intro { color: var(--hcr-muted); font-size: 13px; margin: 8px 0 24px; }
.hcr-layout { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 20px; align-items: start; }
.hcr-main { min-width: 0; display: grid; gap: 18px; }
.hcr-summary { min-width: 0; position: sticky; top: 0; max-height: calc(100dvh - 32px); overflow-y: auto; overscroll-behavior: contain; }
.hcr-meta { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px 20px; }
.hcr-meta :deep(.n-form-item), .hcr-meta :deep(.n-form-item-blank) { min-width: 0; }
.hcr-meta :deep(.n-form-item-label) { font-size: 13px; }
.hcr-meta :deep(.n-date-picker) { width: 100%; }
.hcr-code-field { display: flex; gap: 8px; width: 100%; min-width: 0; }
.hcr-code-field > .n-input { min-width: 0; }
.hcr-hint { font-size: 12px; color: var(--hcr-muted); line-height: 1.7; margin: 12px 0 0; }
.hcr-top-hint { margin: 0 0 16px; }
.hcr-feedback { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 12px; margin-top: 12px; color: #9B7434; }
.hcr-feedback.is-error { color: #C85A54; }
.hcr-scope { padding: 9px 12px; background: #E6F2EC; color: var(--hcr-primary); border-radius: 8px; display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 14px; font-size: 12px; }
.hcr-filters { display: flex; gap: 12px; align-items: center; }
.hcr-filters > .n-input { flex: 1; min-width: 0; }
.hcr-date-filter { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #747C83; }
.hcr-date-filter :deep(.n-date-picker) { width: 155px; }
.hcr-icon { height: 16px; width: 16px; color: var(--hcr-muted); }
.hcr-list-tools { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin: 14px 0; flex-wrap: wrap; }
.hcr-list-tools :deep(.n-checkbox__label) { font-size: 12px; }
.hcr-hidden-note { font-size: 12px; color: #9B7434; background: #FFF8EB; padding: 8px 10px; border-radius: 6px; }
.hcr-sources { border: 1px solid var(--hcr-line); border-radius: 8px; overflow: hidden; }
.hcr-source { padding: 16px; border-bottom: 1px solid var(--hcr-line); }
.hcr-source:last-child { border-bottom: 0; }
.hcr-source.is-selected { background: #F1F8F4; }
.hcr-source.is-unavailable { background: #FFF8F4; }
.hcr-product-line { display: flex; gap: 12px; align-items: center; }
.hcr-product-line :deep(.n-image) { flex-shrink: 0; border-radius: 6px; overflow: hidden; }
.hcr-image-placeholder { width: 44px; height: 44px; display: grid; place-items: center; flex-shrink: 0; color: #AEB8B1; background: #F0F2F1; border-radius: 6px; }
.hcr-image-placeholder svg { width: 22px; height: 22px; }
.hcr-product-copy { min-width: 0; flex: 1; overflow-wrap: anywhere; }
.hcr-product-name { font-size: 14px; font-weight: 550; }
.hcr-product-name :deep(.n-tag) { font-size: 10px; margin-left: 4px; height: 19px; vertical-align: middle; }
.hcr-source-meta { display: flex; gap: 4px 9px; flex-wrap: wrap; align-items: center; color: var(--hcr-muted); font-size: 11px; margin-top: 5px; }
.hcr-source-meta code { font-family: inherit; overflow-wrap: anywhere; }
.hcr-source-meta :deep(.n-button) { font-size: 11px; height: auto; white-space: normal; text-align: left; }
.hcr-balance { text-align: right; max-width: 145px; overflow-wrap: anywhere; }
.hcr-balance small { display: block; font-size: 11px; color: var(--hcr-muted); }
.hcr-balance strong { display: block; font-size: 17px; color: var(--hcr-primary); font-weight: 600; font-variant-numeric: tabular-nums; }
.hcr-balance strong span { font-size: 11px; font-weight: 400; }
.hcr-entry { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(90px, .65fr); gap: 14px; margin: 15px 0 0 30px; padding-top: 14px; border-top: 1px dashed #DCE7E0; align-items: start; }
.hcr-field { min-width: 0; }
.hcr-field > span, .hcr-line-amount > span { display: block; font-size: 12px; color: #747C83; margin-bottom: 6px; }
.hcr-field em { font-style: normal; color: #C75B51; }
.hcr-field small { font-size: 11px; color: var(--hcr-muted); display: block; margin-top: 4px; }
.hcr-field :deep(.n-input-number) { width: 100%; min-width: 0; }
.hcr-input-unit { display: flex; align-items: center; gap: 7px; }
.hcr-input-unit > span { font-size: 12px; color: #747C83; flex-shrink: 0; }
.hcr-line-amount { text-align: right; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.hcr-line-amount strong { display: block; padding-top: 5px; font-size: 14px; font-weight: 550; color: #3E5548; }
.hcr-entry-note { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; margin: 10px 0 0 30px; color: var(--hcr-muted); font-size: 11px; }
.hcr-entry-note :deep(.n-button) { font-size: 11px; }
.hcr-over { color: #A57933 !important; }
.hcr-weight { margin: 10px 0 0 30px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 12px; color: #747C83; }
.hcr-weight > .n-input-number { width: 120px; }
.hcr-weight > .n-select { width: 80px; }
.hcr-weight small { font-size: 11px; color: var(--hcr-muted); }
.hcr-empty { padding: 32px 12px; text-align: center; color: var(--hcr-muted); font-size: 13px; }
.hcr-empty p { margin: 0 0 12px; }
.hcr-list-footer { display: flex; flex-wrap: wrap; gap: 12px; justify-content: space-between; align-items: center; color: var(--hcr-muted); font-size: 11px; margin-top: 14px; }
.hcr-material-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.hcr-material-head h3 { font-size: 15px; margin: 0; }
.hcr-material-head h3 :deep(.n-tag) { margin-left: 5px; }
.hcr-material-head p { margin: 6px 0 0; color: var(--hcr-muted); font-size: 12px; }
.hcr-return-list { display: grid; gap: 10px; margin-top: 16px; font-size: 13px; }
.hcr-return-list > div { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; border-top: 1px solid var(--hcr-line); padding-top: 10px; }
.hcr-return-list > div > span:first-child { flex: 1; min-width: 120px; overflow-wrap: anywhere; }
.hcr-return-list small { display: block; font-size: 11px; color: var(--hcr-muted); }
.hcr-return-list strong { font-size: 13px; font-weight: 500; }
.hcr-summary-supplier { color: #4C535A; margin: 0 0 18px; font-size: 14px; overflow-wrap: anywhere; }
.hcr-summary-label { display: flex; justify-content: space-between; gap: 10px; color: var(--hcr-muted); font-size: 12px; margin-bottom: 12px; }
.hcr-summary-row { display: flex; justify-content: space-between; gap: 8px; margin-bottom: 13px; font-size: 12px; }
.hcr-summary-row > div { min-width: 0; overflow-wrap: anywhere; }
.hcr-summary-row strong { font-weight: 500; }
.hcr-summary-row small { display: block; margin-top: 4px; color: var(--hcr-muted); font-size: 11px; }
.hcr-summary-row > span { flex-shrink: 0; font-variant-numeric: tabular-nums; }
.hcr-quantities { color: #747C83; font-size: 11px; line-height: 1.8; }
.hcr-quantities > span { display: inline-block; margin-right: 9px; }
.hcr-summary-material { border-top: 1px solid var(--hcr-line); margin-top: 16px; padding-top: 13px; }
.hcr-total { border-top: 1px solid var(--hcr-line); margin-top: 16px; padding-top: 16px; font-size: 12px; color: #747C83; }
.hcr-total strong { display: block; font-size: 27px; color: var(--hcr-primary); font-weight: 650; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; margin-top: 4px; }
.hcr-payment { padding-top: 16px; margin-top: 16px; border-top: 1px solid var(--hcr-line); }
.hcr-payment > span { display: block; color: #747C83; font-size: 12px; margin-bottom: 10px; }
.hcr-alert { margin-top: 14px; }
.hcr-review-button { margin-top: 20px; }
.hcr-mobile-bar { display: none; }
.hcr-review-heading { font-size: 14px; margin: 22px 0 10px; }
.hcr-review-row { display: flex; justify-content: space-between; gap: 14px; padding: 12px 0; border-bottom: 1px solid #ECEDEF; font-size: 13px; }
.hcr-review-row > div { min-width: 0; overflow-wrap: anywhere; }
.hcr-review-row strong { font-weight: 550; }
.hcr-review-row > strong { flex-shrink: 0; }
.hcr-review-row small { display: block; font-size: 12px; color: #8B9096; margin-top: 5px; }
.hcr-review-total { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-top: 20px; font-size: 13px; color: #747C83; }
.hcr-review-total strong { color: #1E7A5A; font-size: 23px; font-weight: 650; }
.hcr-cost-created { color: #1E7A5A; font-size: 13px; }
@container (max-width: 1060px) {
  .hcr-layout { grid-template-columns: minmax(0, 1fr) 270px; gap: 16px; }
  .hcr-filters { flex-wrap: wrap; }.hcr-filters > .n-input { flex-basis: 100%; }
  .hcr-source { padding: 14px 12px; }.hcr-product-line { gap: 9px; }
  .hcr-entry { margin-left: 0; gap: 10px; }.hcr-entry-note, .hcr-weight { margin-left: 0; }
}
@container (max-width: 850px) {
  .hcr-layout { grid-template-columns: minmax(0, 1fr); }.hcr-summary { position: static; max-height: none; overflow: visible; }
  .hcr-filters > .n-input { flex-basis: auto; }.hcr-summary-row { font-size: 13px; }
}
@container (max-width: 540px) {
  .hcr-head { align-items: flex-start; }.hcr-head > div { flex-wrap: wrap; gap: 6px; }.hcr-head :deep(.n-h2) { font-size: 21px; }.hcr-head > .n-button { font-size: 12px; }
  .hcr-meta { grid-template-columns: minmax(0, 1fr); gap: 14px; }.hcr-intro { font-size: 12px; }
  .hcr-main { gap: 14px; }.hcr-main :deep(.n-card-content), .hcr-summary :deep(.n-card-content) { padding-left: 14px; padding-right: 14px; }
  .hcr-main :deep(.n-card-header), .hcr-summary :deep(.n-card-header) { padding-left: 14px; padding-right: 14px; }
  .hcr-filters { flex-direction: column; align-items: stretch; }.hcr-date-filter { justify-content: space-between; }.hcr-date-filter :deep(.n-date-picker) { flex: 1; width: auto; max-width: 220px; }
  .hcr-list-tools { gap: 10px; }.hcr-list-tools :deep(.n-radio-button) { font-size: 12px; padding-left: 9px; padding-right: 9px; }
  .hcr-product-line { flex-wrap: wrap; align-items: flex-start; }.hcr-product-line > .n-checkbox { margin-top: 9px; }.hcr-product-copy { flex-basis: calc(100% - 85px); }.hcr-product-name { font-size: 13px; }
  .hcr-balance { max-width: 100%; flex-basis: 100%; display: flex; align-items: baseline; gap: 8px; text-align: left; margin-left: 28px; }.hcr-balance strong { font-size: 15px; }
  .hcr-entry { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }.hcr-line-amount { grid-column: 1 / -1; display: flex; align-items: center; justify-content: space-between; }.hcr-line-amount > span { margin: 0; }.hcr-line-amount strong { padding: 0; }
  .hcr-source-meta { gap: 5px 8px; }.hcr-material-head { align-items: flex-start; flex-wrap: wrap; }.hcr-scope { align-items: flex-start; flex-wrap: wrap; }
}
@media (max-width: 767px) {
  .handcraft-receipt-create { padding-bottom: 96px; }.hcr-crumbs { padding-left: 36px; }
  .hcr-mobile-bar { position: fixed; left: 0; right: 0; bottom: 0; z-index: 20; display: flex; justify-content: space-between; gap: 12px; align-items: center; background: #FFFFFFF5; backdrop-filter: blur(12px); border-top: 1px solid #ECEDEF; padding: 11px 16px calc(11px + env(safe-area-inset-bottom, 0px)); box-shadow: 0 -4px 16px #1A1D2106; }
  .hcr-mobile-bar > div { min-width: 0; }.hcr-mobile-bar small { display: block; font-size: 10px; color: #8B9096; }.hcr-mobile-bar strong { display: block; color: #1E7A5A; font-size: 22px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }.hcr-mobile-bar > .n-button { height: 42px; flex-shrink: 0; }
}
</style>
