<template>
  <div class="receipt-detail">
    <div class="page-breadcrumb">生产 / 电镀回收 / {{ receipt?.id || '…' }}</div>
    <header class="rd-head">
      <div class="rd-title">
        <h2 class="page-title">电镀回收单 {{ receipt?.id || '…' }}</h2>
        <n-popselect v-if="receipt" :value="receipt.status" :options="statusToggleOptions" trigger="click" @update:value="doChangeStatus">
          <button type="button" class="rd-status" :class="{ 'is-paid': isPaid() }" aria-label="切换回收单付款状态">{{ receipt.status }} ▾</button>
        </n-popselect>
      </div>
      <n-space size="small">
        <n-button v-if="summaryReturn" text size="small" @click="backToSummary">返回汇总</n-button>
        <n-button text size="small" @click="router.back()">← 返回</n-button>
      </n-space>
    </header>

    <n-spin :show="loading">
      <n-empty v-if="!loading && !receipt" description="加载失败，请返回重试" style="margin-top: 24px;" />
      <template v-if="receipt">
        <section class="rd-stats" aria-label="回收单统计">
          <div class="rd-stat"><div class="rd-stat-label">回收明细</div><div class="rd-stat-value">{{ items.length }}<small>项</small></div><div class="rd-stat-note">{{ detailSummary.partCount }} 种配件</div></div>
          <div class="rd-stat"><div class="rd-stat-label">本单回收数量</div><div class="rd-stat-value rd-quantities"><span v-for="quantity in detailSummary.quantities" :key="quantity.unit">{{ quantity.qty }}<small>{{ quantity.unit }}</small></span><template v-if="!detailSummary.quantities.length">—</template></div><div class="rd-stat-note">不同单位分别汇总</div></div>
          <div class="rd-stat"><div class="rd-stat-label">回收总重量</div><div class="rd-stat-value">{{ detailSummary.weightKg ?? '—' }}<small v-if="detailSummary.weightKg != null">kg</small></div><div class="rd-stat-note">{{ detailSummary.weightKg == null ? '暂无填写重量' : '按填写重量换算汇总' }}</div></div>
          <div class="rd-stat"><div class="rd-stat-label">待定价明细</div><div class="rd-stat-value" :class="{ 'is-amber': detailSummary.unpricedCount > 0 }">{{ detailSummary.unpricedCount }}<small>项</small></div><div class="rd-stat-note">{{ detailSummary.unpricedCount ? '未定价不视为免费' : '全部明细已定价' }}</div></div>
          <div class="rd-stat"><div class="rd-stat-label">原单总金额</div><div class="rd-stat-value is-green"><small v-if="receipt.total_amount != null">¥</small>{{ receipt.total_amount != null ? fmtMoney(receipt.total_amount) : '待定价' }}</div><div class="rd-stat-note">不含商家对账独立改价</div></div>
        </section>
        <section class="rd-meta" aria-label="基本信息">
          <div class="rd-meta-item"><div class="rd-meta-label">商家 / 电镀厂</div><div class="rd-meta-value">{{ receipt.vendor_name }}</div></div>
          <div class="rd-meta-item"><div class="rd-meta-label">创建时间</div><div class="rd-meta-value">
            <template v-if="editingCreatedAt">
              <n-space align="center" size="small">
                <n-date-picker
                  v-model:value="editingCreatedAtTs"
                  type="date"
                  size="small"
                  :style="{ width: isMobile ? '100%' : '160px' }"
                />
                <n-button size="small" type="primary" :loading="savingCreatedAt" @click="saveCreatedAt">确认</n-button>
                <n-button size="small" :disabled="savingCreatedAt" @click="editingCreatedAt = false">取消</n-button>
              </n-space>
            </template>
            <template v-else>
              {{ fmt(receipt.created_at) }}
              <n-button text type="primary" size="small" style="margin-left: 6px;" aria-label="修改创建时间" @click="startEditCreatedAt">
                <template #icon><n-icon :component="CreateOutline" /></template>
              </n-button>
            </template>
          </div></div>
          <div class="rd-meta-item"><div class="rd-meta-label">付款时间</div><div class="rd-meta-value">{{ receipt.paid_at ? fmt(receipt.paid_at) : '—' }}</div></div>
          <div class="rd-meta-item rd-meta-note"><div class="rd-meta-label">备注</div><div class="rd-meta-value rd-note-text">{{ receipt.note || '—' }}</div></div>
        </section>

        <section class="rd-section" aria-labelledby="receipt-items-title">
          <div class="rd-section-head">
            <div class="rd-section-title"><h3 id="receipt-items-title">回收明细</h3><span class="rd-count">{{ items.length }} 项</span></div>
            <n-space size="small" align="center">
              <span class="rd-hint">{{ isPaid() ? '已付款 · 明细及备注已锁定' : '可修改明细，点击备注直接编辑' }}</span>
              <n-button v-if="!isPaid()" size="small" type="primary" secondary @click="openAddItemsModal">+ 增加配件</n-button>
            </n-space>
          </div>
          <n-data-table
            v-if="items.length"
            class="rd-table"
            :columns="itemColumns"
            :data="items"
            :bordered="false"
            :row-key="(row) => row.id"
            :scroll-x="1330"
            :row-class-name="(row) => row.id === highlightItemId ? 'receipt-highlight-row' : ''"
          />
          <n-empty v-else description="暂无明细" style="padding: 24px;" />
          <p class="rd-table-note">数量为本单实际回收数量；损耗操作针对来源电镀单的剩余差额，不计入本单回收数量。</p>
        </section>

        <section class="rd-section" aria-labelledby="receipt-images-title">
          <div class="rd-section-head"><div class="rd-section-title"><h3 id="receipt-images-title">单据与配件图片</h3><span class="rd-count">{{ totalDeliveryImageCount }} / 9</span></div><span class="rd-hint">回收凭证与配件照片 · 点击图片可预览</span></div>
            <div class="delivery-images-block">
              <div v-if="pendingDeliveryImages.length > 0" class="delivery-images-warning">
                <div class="delivery-images-warning-title">
                  有 {{ pendingDeliveryImages.length }} 张图片已上传，但还没保存到回收单
                </div>
                <div class="delivery-images-pending-list">
                  <div
                    v-for="image in pendingDeliveryImages"
                    :key="`pending-${image}`"
                    class="delivery-pending-item"
                  >
                    <n-image
                      :src="image"
                      alt="待保存图片"
                      :width="56"
                      :height="56"
                      object-fit="cover"
                      class="delivery-pending-preview"
                    />
                    <div class="delivery-pending-actions">
                      <n-button
                        size="tiny"
                        type="warning"
                        ghost
                        :loading="retryingPendingImage === image"
                        :disabled="deliveryImagesSaving"
                        @click="retryPendingDeliveryImage(image)"
                      >
                        重试保存
                      </n-button>
                      <n-button
                        size="tiny"
                        quaternary
                        :disabled="deliveryImagesSaving || retryingPendingImage === image"
                        @click="dropPendingDeliveryImage(image)"
                      >
                        移除记录
                      </n-button>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="deliveryImages.length > 0" class="delivery-images-grid">
                <div
                  v-for="(image, index) in deliveryImages"
                  :key="`${image}-${index}`"
                  class="delivery-image-card"
                >
                  <n-image
                    :src="image"
                    alt="单据图片"
                    :width="88"
                    :height="88"
                    object-fit="cover"
                    class="delivery-image-preview"
                  />
                  <n-button
                    class="delivery-image-delete"
                    :aria-label="`删除第 ${index + 1} 张图片`"
                    size="tiny"
                    type="error"
                    circle
                    :disabled="deliveryImagesSaving"
                    @click="removeDeliveryImage(index)"
                  >
                    ×
                  </n-button>
                </div>
                <button
                  v-if="canAddDeliveryImage"
                  class="delivery-image-add"
                  aria-label="上传单据或配件图片"
                  :disabled="deliveryImagesSaving"
                  @click="openDeliveryImageModal"
                >
                  +
                </button>
              </div>
              <button
                v-else-if="canAddDeliveryImage"
                class="delivery-image-add"
                aria-label="上传单据或配件图片"
                :disabled="deliveryImagesSaving"
                @click="openDeliveryImageModal"
              >
                +
              </button>
              <div class="delivery-images-meta">
                {{ totalDeliveryImageCount }}/9 张
                <span v-if="pendingDeliveryImages.length > 0">（待保存 {{ pendingDeliveryImages.length }} 张）</span>
              </div>
            </div>
        </section>
        <div class="rd-footer">
          <p class="rd-footer-note">{{ isPaid() ? '已付款后不可增删改明细；创建时间和图片仍可维护。' : '确认付款后将锁定明细；付款状态可在页头切换。' }}</p>
          <n-button text type="error" size="small" :disabled="isPaid()" @click="doDeleteReceipt">删除回收单</n-button>
        </div>
      </template>
    </n-spin>

    <!-- Edit Item Modal -->
    <n-modal v-model:show="editModalVisible" preset="card" title="修改明细" :style="{ width: isMobile ? '95vw' : '500px' }">
      <form @submit.prevent="doEditItem">
      <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="90">
        <n-form-item label="数量">
          <n-input-number v-model:value="editForm.qty" :min="0.0001" :precision="4" :step="1" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="editForm.unit" :options="unitOptions" />
        </n-form-item>
        <n-form-item label="单价">
          <n-input-number v-model:value="editForm.price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" :step="0.1" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="重量">
          <div style="display:flex;gap:8px;align-items:center;width:100%">
            <n-input-number v-model:value="editForm.weight" :min="0" placeholder="重量" style="flex:1" />
            <n-select v-model:value="editForm.weight_unit" :options="[{label:'g',value:'g'},{label:'kg',value:'kg'}]" style="width:80px" />
          </div>
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="editForm.note" placeholder="备注（可选）" />
        </n-form-item>
      </n-form>
      </form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="editModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="editSubmitting" @click="doEditItem">保存修改</n-button>
        </n-space>
      </template>
    </n-modal>

    <ImageUploadModal
      v-model:show="showDeliveryImageModal"
      kind="plating-receipts"
      :entity-id="receipt?.id"
      suppress-success
      @uploaded="handleDeliveryImageUploaded"
    />

    <!-- Add Items Modal -->
    <n-modal v-model:show="addItemsModalVisible" preset="card" :title="`增加回收配件（${receipt?.vendor_name}）`" :style="{ width: isMobile ? '95vw' : '800px' }">
      <div class="rd-add-filters">
        <n-input
          v-model:value="addItemsFilterKeyword"
          placeholder="编号/名称搜索"
          clearable
          :style="{ width: isMobile ? '100%' : '200px' }"
          @update:value="onAddItemsFilterKeyword"
        />
        <span style="font-size: 13px; color: #666;">发出日期</span>
        <n-date-picker
          v-model:value="addItemsFilterDateOn"
          type="date"
          clearable
          :style="{ width: isMobile ? '100%' : '160px' }"
          @update:value="onAddItemsFilterDate"
        />
      </div>
      <n-spin :show="addItemsLoading">
        <n-empty v-if="!addItemsLoading && addItemsPendingItems.length === 0" :description="addItemsFetchError ? '加载失败，请重试' : '暂无可添加的待回收配件'" style="margin: 16px 0;" />
        <n-data-table
          v-if="addItemsPendingItems.length > 0"
          :columns="addItemsColumns"
          :data="addItemsPendingItems"
          :bordered="false"
          :row-key="(row) => row.id"
          :scroll-x="1050"
          :checked-row-keys="addItemsCheckedKeys"
          @update:checked-row-keys="(keys) => { addItemsCheckedKeys = keys }"
          size="small"
          :max-height="400"
        />
      </n-spin>
      <template #footer>
        <n-space justify="end">
          <n-button @click="addItemsModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="addItemsSubmitting" :disabled="addItemsCheckedKeys.length === 0" @click="submitAddItems">确认添加</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Cost Diff Modal (from add items) -->
    <n-modal v-model:show="addItemsCostDiffVisible" :mask-closable="false" preset="card" title="电镀成本变动确认" :style="{ width: isMobile ? '95vw' : '550px' }">
      <div style="margin-bottom: 12px; color: #333;">
        当前电镀成本与配件已有电镀成本金额不相同，是否更新电镀成本？
      </div>
      <n-data-table
        :columns="[
          { title: '配件编号', key: 'part_id', width: 160 },
          { title: '配件名称', key: 'part_name', minWidth: 120 },
          { title: '原电镀费用', key: 'current_value', width: 120, render: (r) => r.current_value != null ? `¥ ${fmtMoney(r.current_value)}` : '-' },
          { title: '更新电镀费用', key: 'new_value', width: 120, render: (r) => h('span', { style: 'color: #d03050; font-weight: 600;' }, `¥ ${fmtMoney(r.new_value)}`) },
        ]"
        :data="addItemsCostDiffs"
        :bordered="false"
        size="small"
      />
      <template #footer>
        <n-space justify="end">
          <n-button @click="skipAddItemsCostUpdate" :disabled="addItemsCostDiffUpdating">跳过</n-button>
          <n-button type="primary" :loading="addItemsCostDiffUpdating" @click="confirmAddItemsCostUpdate">确认更新</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Confirm Loss Modal -->
    <n-modal v-model:show="showLossModal" preset="card" title="确认损耗" :style="{ width: isMobile ? '95vw' : '420px' }">
      <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="80">
        <n-form-item label="差额信息">
          <span v-if="lossTarget">已收回 {{ lossTarget.source_received_qty || 0 }} / 发出 {{ lossTarget.source_qty || 0 }}，差额 {{ (lossTarget.source_qty || 0) - (lossTarget.source_received_qty || 0) }}</span>
        </n-form-item>
        <n-form-item label="损耗数量">
          <n-input-number v-model:value="lossForm.loss_qty" :min="0.01" :max="lossTarget ? (lossTarget.source_qty || 0) - (lossTarget.source_received_qty || 0) : 0" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="扣款金额">
          <n-input-number v-model:value="lossForm.deduct_amount" :min="0" placeholder="不扣款留空" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="原因">
          <n-input v-model:value="lossForm.reason" placeholder="如：品质不良、加工损坏" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="lossForm.note" type="textarea" :rows="2" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showLossModal = false">取消</n-button>
          <n-button type="warning" :loading="lossSubmitting" @click="doConfirmLoss">确认损耗</n-button>
        </n-space>
      </template>
    </n-modal>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, h, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { useIsMobile } from '@/composables/useIsMobile'
import { useSummaryReturn } from '@/composables/useSummaryReturn'
import {
  NSpin, NDataTable,
  NSpace, NButton, NEmpty, NModal, NForm, NFormItem,
  NSelect, NInputNumber, NInput, NPopselect, NTooltip, NIcon, NImage, NDatePicker,
} from 'naive-ui'
import { CreateOutline } from '@vicons/ionicons5'
import {
  getPlatingReceipt, updatePlatingReceipt, updatePlatingReceiptStatus,
  updatePlatingReceiptDeliveryImages,
  updatePlatingReceiptItem, deletePlatingReceiptItem,
  deletePlatingReceipt, addPlatingReceiptItems,
} from '@/api/platingReceipts'
import { tsToDateStr, isoToTs } from '@/utils/date'
import { listPendingReceiveItems } from '@/api/plating'
import { batchUpdatePartCosts } from '@/api/parts'
import { confirmPlatingLoss } from '@/api/productionLoss'
import { renderNamedImage, fmtMoney, fmtPrice, parseNum } from '@/utils/ui'
import ImageUploadModal from '@/components/ImageUploadModal.vue'
import { summarizePlatingReceipt } from '@/utils/platingReceiptDetail'

const route = useRoute()
const router = useRouter()
const { returnQuery: summaryReturn, back: backToSummary } = useSummaryReturn()

const highlightItemId = computed(() => {
  const val = route.query.highlight
  return val ? Number(val) : null
})

const scrollToHighlight = async () => {
  if (!highlightItemId.value) return
  await nextTick()
  const row = document.querySelector('.receipt-highlight-row')
  if (row) {
    row.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

watch(highlightItemId, scrollToHighlight)

const message = useMessage()
const dialog = useDialog()
const { isMobile } = useIsMobile()

const loading = ref(true)
const receipt = ref(null)
const items = computed(() => receipt.value?.items || [])
const detailSummary = computed(() => summarizePlatingReceipt(items.value))

const editingCreatedAt = ref(false)
const editingCreatedAtTs = ref(null)
const savingCreatedAt = ref(false)

const startEditCreatedAt = () => {
  editingCreatedAtTs.value = isoToTs(receipt.value?.created_at)
  editingCreatedAt.value = true
}

const saveCreatedAt = async () => {
  const dateStr = tsToDateStr(editingCreatedAtTs.value)
  if (!dateStr) { message.warning('请选择日期'); return }
  savingCreatedAt.value = true
  try {
    await updatePlatingReceipt(route.params.id, { created_at: dateStr })
    await loadData()
    message.success('创建时间已更新')
    editingCreatedAt.value = false
  } catch (e) {
    message.error(e.response?.data?.detail || '更新失败')
  } finally {
    savingCreatedAt.value = false
  }
}

// Confirm loss modal
const showLossModal = ref(false)
const lossTarget = ref(null)
const lossForm = ref({ loss_qty: 0, deduct_amount: null, reason: '', note: '' })
const lossSubmitting = ref(false)

const openLossModal = (item) => {
  lossTarget.value = item
  const gap = (item.source_qty || 0) - (item.source_received_qty || 0)
  lossForm.value = { loss_qty: gap, deduct_amount: null, reason: '', note: '' }
  showLossModal.value = true
}

const doConfirmLoss = async () => {
  lossSubmitting.value = true
  try {
    const payload = { ...lossForm.value }
    if (!payload.deduct_amount) payload.deduct_amount = null
    if (!payload.reason) payload.reason = null
    if (!payload.note) payload.note = null
    await confirmPlatingLoss(lossTarget.value.plating_order_id, lossTarget.value.plating_order_item_id, payload)
    showLossModal.value = false
    message.success('损耗已确认')
    await loadData()
  } catch (err) {
    // error handled by interceptor
  } finally {
    lossSubmitting.value = false
  }
}

const showDeliveryImageModal = ref(false)
const deliveryImagesSaving = ref(false)
const pendingDeliveryImages = ref([])
const retryingPendingImage = ref('')

const statusToggleOptions = computed(() => {
  if (!receipt.value) return []
  if (receipt.value.status === '未付款') return [{ label: '已付款', value: '已付款' }]
  return [{ label: '未付款', value: '未付款' }]
})

const deliveryImages = computed(() => receipt.value?.delivery_images || [])
const totalDeliveryImageCount = computed(() => deliveryImages.value.length + pendingDeliveryImages.value.length)
const canAddDeliveryImage = computed(() => totalDeliveryImageCount.value < 9)
const fmt = (dt) => new Date(dt).toLocaleString('zh-CN')
const isPaid = () => receipt.value?.status === '已付款'

const unitOptions = [
  { label: '个', value: '个' },
  { label: '条', value: '条' },
  { label: '米', value: '米' },
  { label: 'g', value: 'g' },
  { label: 'kg', value: 'kg' },
]

// Edit Item Modal
const editModalVisible = ref(false)
const editSubmitting = ref(false)
const editForm = ref({ id: null, qty: 1, unit: '个', price: 0, note: '', weight: null, weight_unit: 'g' })

// Inline note editing
const editingNoteItemId = ref(null)
const editingNoteValue = ref('')
const savingNoteItemId = ref(null)
const noteInputRef = ref(null)

// Add items modal
const addItemsModalVisible = ref(false)
const addItemsLoading = ref(false)
const addItemsSubmitting = ref(false)
const addItemsPendingItems = ref([])
const addItemsCheckedKeys = ref([])
const addItemsInputs = reactive({})
const addItemsFilterKeyword = ref('')
const addItemsFilterDateOn = ref(null)
let addItemsDebounceTimer = null
let addItemsFetchSeq = 0
const addItemsFetchError = ref(false)

// Cost diff modal (shared for edit-item and add-items)
const addItemsCostDiffVisible = ref(false)
const addItemsCostDiffs = ref([])
const addItemsCostDiffUpdating = ref(false)

const loadData = async () => {
  const id = route.params.id
  const { data } = await getPlatingReceipt(id)
  receipt.value = data
  pendingDeliveryImages.value = pendingDeliveryImages.value.filter((image) => !data.delivery_images.includes(image))
  if (isPaid()) {
    stopEditNote()
  }
}

const doChangeStatus = (newStatus) => {
  dialog.warning({
    title: '确认状态变更',
    content: `确认将回收单「${receipt.value?.id}」状态从「${receipt.value?.status}」切换为「${newStatus}」？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      const loadingMsg = message.loading('正在更新状态...', { duration: 0 })
      try {
        await updatePlatingReceiptStatus(receipt.value.id, newStatus)
        loadingMsg.destroy()
        message.success(`状态已更新为${newStatus}`)
        await loadData()
      } catch (_) {
        loadingMsg.destroy()
        await loadData()
      }
    },
  })
}

const openEditModal = (row) => {
  editForm.value = {
    id: row.id,
    qty: row.qty,
    unit: row.unit || '个',
    price: row.price ?? null,
    note: row.note || '',
    weight: row.weight ?? null,
    weight_unit: row.weight_unit || 'g',
  }
  editModalVisible.value = true
}

const doEditItem = async () => {
  editSubmitting.value = true
  try {
    const { id, ...body } = editForm.value
    const { data } = await updatePlatingReceiptItem(route.params.id, id, body)
    message.success('修改已保存')
    editModalVisible.value = false
    if (data.cost_diffs && data.cost_diffs.length > 0) {
      addItemsCostDiffs.value = data.cost_diffs
      addItemsCostDiffVisible.value = true
    }
    await loadData()
  } finally {
    editSubmitting.value = false
  }
}

const doDeleteItem = (row) => {
  dialog.warning({
    title: '确认删除',
    content: `确认删除配件 ${row.part_name || row.part_id} 的明细行？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deletePlatingReceiptItem(route.params.id, row.id)
        message.success('已删除')
        await loadData()
      } catch (_) {
        // error shown by axios interceptor
      }
    },
  })
}

const doDeleteReceipt = () => {
  dialog.warning({
    title: '确认删除回收单',
    content: `确认删除回收单「${receipt.value?.id}」吗？删除后不可恢复。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deletePlatingReceipt(route.params.id)
        message.success('回收单已删除')
        router.push('/plating-receipts')
      } catch (_) {
        // error shown by axios interceptor
      }
    },
  })
}

// Delivery images
const mergeDeliveryImages = (...groups) => [...new Set(groups.flat().filter(Boolean))]

const persistDeliveryImages = async (nextImages, successText) => {
  if (!receipt.value) return
  deliveryImagesSaving.value = true
  try {
    const { data } = await updatePlatingReceiptDeliveryImages(receipt.value.id, nextImages)
    receipt.value = { ...receipt.value, delivery_images: data.delivery_images }
    pendingDeliveryImages.value = pendingDeliveryImages.value.filter((image) => !data.delivery_images.includes(image))
    message.success(successText)
    return data
  } finally {
    deliveryImagesSaving.value = false
  }
}

const openDeliveryImageModal = () => {
  if (!canAddDeliveryImage.value) {
    message.warning('图片最多上传 9 张')
    return
  }
  showDeliveryImageModal.value = true
}

const handleDeliveryImageUploaded = async (url) => {
  if (!url) return
  if (!canAddDeliveryImage.value) {
    message.warning('图片最多上传 9 张')
    return
  }
  try {
    await persistDeliveryImages(mergeDeliveryImages(deliveryImages.value, [url]), '图片已上传')
  } catch (_) {
    if (!pendingDeliveryImages.value.includes(url)) {
      pendingDeliveryImages.value.push(url)
    }
    message.warning('图片已上传，但写入回收单失败，可点击"重试保存"继续')
  }
}

const removeDeliveryImage = (index) => {
  if (!receipt.value) return
  dialog.warning({
    title: '确认删除图片',
    content: '删除后不可恢复，确认继续吗？',
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      const nextImages = deliveryImages.value.filter((_, currentIndex) => currentIndex !== index)
      await persistDeliveryImages(nextImages, '图片已删除')
    },
  })
}

const retryPendingDeliveryImage = async (image) => {
  if (!pendingDeliveryImages.value.includes(image)) return
  retryingPendingImage.value = image
  try {
    await persistDeliveryImages(
      mergeDeliveryImages(deliveryImages.value, pendingDeliveryImages.value),
      '待保存图片已写入回收单',
    )
  } catch (_) {
    message.warning('重试保存失败，请稍后再试')
  } finally {
    retryingPendingImage.value = ''
  }
}

const dropPendingDeliveryImage = (image) => {
  pendingDeliveryImages.value = pendingDeliveryImages.value.filter((item) => item !== image)
  message.success('已移除待保存记录')
}

// Inline note editing
const focusEditingNoteInput = () => {
  nextTick(() => {
    noteInputRef.value?.focus?.()
  })
}

const startEditNote = (row) => {
  if (isPaid()) return
  editingNoteItemId.value = row.id
  editingNoteValue.value = row.note || ''
  focusEditingNoteInput()
}

const stopEditNote = (itemId = null) => {
  if (itemId !== null && editingNoteItemId.value !== itemId) return
  editingNoteItemId.value = null
  editingNoteValue.value = ''
}

const normalizeNote = (value) => (value || '').trim()

const saveNote = async (row) => {
  if (editingNoteItemId.value !== row.id || savingNoteItemId.value === row.id) return

  const itemId = row.id
  const nextNote = normalizeNote(editingNoteValue.value)
  const currentNote = normalizeNote(row.note)
  if (nextNote === currentNote) {
    stopEditNote(itemId)
    return
  }

  savingNoteItemId.value = itemId
  try {
    await updatePlatingReceiptItem(route.params.id, itemId, { note: nextNote })
    row.note = nextNote
    message.success(nextNote ? '备注已保存' : '备注已清空')
    stopEditNote(itemId)
  } finally {
    if (savingNoteItemId.value === itemId) {
      savingNoteItemId.value = null
    }
  }
}

const onNoteInputKeydown = (event, row) => {
  if (event.key !== 'Enter') return
  if (event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  void saveNote(row)
}

const renderNoteCell = (row) => {
  const isEditing = editingNoteItemId.value === row.id
  const isSaving = savingNoteItemId.value === row.id
  const noteText = row.note || ''

  if (isEditing) {
    return h(NInput, {
      ref: noteInputRef,
      value: editingNoteValue.value,
      size: 'small',
      placeholder: '输入备注后按回车或点击空白处保存',
      disabled: isSaving,
      autofocus: true,
      'onUpdate:value': (value) => { editingNoteValue.value = value },
      onBlur: () => { void saveNote(row) },
      onKeydown: (event) => onNoteInputKeydown(event, row),
    })
  }

  if (!noteText) {
    if (isPaid()) {
      return h('span', { style: 'color: #999;' }, '-')
    }
    return h(
      NButton,
      {
        text: true,
        type: 'primary',
        size: 'small',
        onClick: () => startEditNote(row),
      },
      {
        icon: () => h(NIcon, null, { default: () => h(CreateOutline) }),
        default: () => '添加备注',
      },
    )
  }

  return h(
    'span',
    {
      title: noteText,
      style: [
        'display: inline-block',
        'max-width: 220px',
        'overflow: hidden',
        'text-overflow: ellipsis',
        'white-space: nowrap',
        'vertical-align: bottom',
        !isPaid() ? 'cursor: pointer; color: #1E7A5A;' : '',
      ].join('; '),
      onClick: !isPaid() ? () => startEditNote(row) : undefined,
    },
    noteText,
  )
}

const itemColumns = [
  {
    title: '配件',
    key: 'part_name',
    width: 210,
    render: (row) => h('div', { class: 'rd-part' }, [
      h('div', { class: 'rd-part-name' }, [row.part_name || row.part_id,
        row.part_is_composite ? h('span', { class: 'rd-composite' }, '组合') : null]),
      h('div', { class: 'rd-part-code' }, row.part_id),
    ]),
  },
  {
    title: '电镀单号',
    key: 'plating_order_id',
    width: 120,
    render: (row) => {
      if (!row.plating_order_id) return '-'
      return h('a', {
        class: 'rd-source-link',
        href: `/plating/${row.plating_order_id}`,
        onClick: (e) => { if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return; e.preventDefault(); e.stopPropagation(); router.push(`/plating/${row.plating_order_id}`) },
      }, row.plating_order_id)
    },
  },
  { title: '电镀方式', key: 'plating_method', width: 90, render: (r) => r.plating_method || '-' },
  { title: '回收数量', key: 'qty', width: 120, render: (r) => h('span', { class: 'rd-qty' }, [String(r.qty), h('small', null, r.unit || '未标单位')]) },
  { title: '重量', key: 'weight', width: 120, render: (r) => r.weight != null ? `${r.weight} ${r.weight_unit || 'g'}` : '—' },
  { title: '单价', key: 'price', width: 120, render: (r) => r.price != null ? `¥ ${fmtMoney(r.price)}` : h('span', { class: 'rd-unpriced' }, '待定价') },
  { title: '金额', key: 'amount', width: 130, render: (r) => r.amount != null ? h('span', { class: 'rd-amount' }, `¥ ${fmtMoney(r.amount)}`) : h('span', { class: 'rd-unpriced' }, '待定价') },
  {
    title: '备注',
    key: 'note',
    minWidth: 220,
    render: (row) => renderNoteCell(row),
  },
  {
    title: '操作',
    key: 'actions',
    width: 200,
    render: (row) => {
      const canEdit = !isPaid()
      const editBtn = h(
        NTooltip,
        { disabled: canEdit, trigger: 'hover' },
        {
          trigger: () =>
            h(
              NButton,
              {
                size: 'small',
                text: true,
                type: 'primary',
                disabled: !canEdit,
                style: 'margin-right: 6px;',
                onClick: canEdit ? () => openEditModal(row) : undefined,
              },
              { default: () => '修改' },
            ),
          default: () => '已付款状态不允许修改',
        },
      )
      const deleteBtn = h(
        NTooltip,
        { disabled: canEdit, trigger: 'hover' },
        {
          trigger: () =>
            h(
              NButton,
              {
                size: 'small',
                text: true,
                type: 'error',
                disabled: !canEdit,
                onClick: canEdit ? () => doDeleteItem(row) : undefined,
              },
              { default: () => '删除' },
            ),
          default: () => '已付款状态不允许删除',
        },
      )
      const btns = [editBtn, deleteBtn]
      // Confirm loss button: show when source item has a gap
      const sourceGap = (row.source_qty || 0) - (row.source_received_qty || 0)
      if (sourceGap > 0) {
        btns.push(h(NButton, {
          size: 'small',
          text: true,
          type: 'warning',
          onClick: () => openLossModal(row),
        }, { default: () => '确认损耗' }))
      }
      return h(NSpace, { size: 'small' }, { default: () => btns })
    },
  },
]

// Add items helpers
const getAddRemaining = (item) => item.qty - (item.received_qty || 0)

const getAddInput = (id) => {
  if (!addItemsInputs[id]) {
    addItemsInputs[id] = { qty: null, price: null, unit: '个', weight: null, weight_unit: 'g' }
  }
  return addItemsInputs[id]
}

const fetchAddItemsPending = async () => {
  if (!receipt.value) return
  const seq = ++addItemsFetchSeq
  addItemsLoading.value = true
  addItemsFetchError.value = false
  try {
    const existingPoiIds = receipt.value.items.map((i) => i.plating_order_item_id).filter(Boolean)
    const params = { supplier_name: receipt.value.vendor_name }
    if (existingPoiIds.length > 0) params.exclude_item_ids = existingPoiIds
    if (addItemsFilterKeyword.value) params.part_keyword = addItemsFilterKeyword.value
    if (addItemsFilterDateOn.value) {
      const d = new Date(addItemsFilterDateOn.value)
      params.date_on = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    }
    const { data } = await listPendingReceiveItems(params)
    if (seq !== addItemsFetchSeq) return
    addItemsPendingItems.value = data
    for (const item of data) {
      if (!addItemsInputs[item.id]) {
        addItemsInputs[item.id] = { qty: getAddRemaining(item), price: null, unit: item.unit || '个' }
      }
    }
  } catch (_) {
    if (seq !== addItemsFetchSeq) return
    addItemsPendingItems.value = []
    addItemsCheckedKeys.value = []
    addItemsFetchError.value = true
    message.error('加载待回收配件失败')
  } finally {
    if (seq === addItemsFetchSeq) addItemsLoading.value = false
  }
}

const openAddItemsModal = () => {
  addItemsCheckedKeys.value = []
  addItemsFilterKeyword.value = ''
  addItemsFilterDateOn.value = null
  Object.keys(addItemsInputs).forEach((k) => delete addItemsInputs[k])
  addItemsModalVisible.value = true
  fetchAddItemsPending()
}

const onAddItemsFilterKeyword = () => {
  clearTimeout(addItemsDebounceTimer)
  addItemsDebounceTimer = setTimeout(() => {
    addItemsCheckedKeys.value = []
    fetchAddItemsPending()
  }, 300)
}

const onAddItemsFilterDate = () => {
  addItemsCheckedKeys.value = []
  fetchAddItemsPending()
}

const submitAddItems = async () => {
  if (addItemsCheckedKeys.value.length === 0) {
    message.warning('请至少勾选一条待回收配件')
    return
  }
  const items = []
  for (const id of addItemsCheckedKeys.value) {
    const pending = addItemsPendingItems.value.find((p) => p.id === id)
    if (!pending) continue
    const input = addItemsInputs[id]
    if (!input?.qty || input.qty <= 0) {
      message.warning(`请填写「${pending.part_name}」的回收数量`)
      return
    }
    items.push({
      plating_order_item_id: pending.id,
      part_id: pending.receive_part_id || pending.part_id,
      qty: input.qty,
      weight: input.weight != null ? input.weight : null,
      weight_unit: input.weight != null ? (input.weight_unit || 'g') : null,
      price: input.price != null ? input.price : null,
      unit: input.unit || '个',
    })
  }

  addItemsSubmitting.value = true
  try {
    const { data } = await addPlatingReceiptItems(route.params.id, { items })
    message.success('配件已添加')
    addItemsModalVisible.value = false
    if (data.cost_diffs && data.cost_diffs.length > 0) {
      addItemsCostDiffs.value = data.cost_diffs
      addItemsCostDiffVisible.value = true
    }
    await loadData()
  } finally {
    addItemsSubmitting.value = false
  }
}

const confirmAddItemsCostUpdate = async () => {
  addItemsCostDiffUpdating.value = true
  try {
    await batchUpdatePartCosts({
      updates: addItemsCostDiffs.value.map((d) => ({
        part_id: d.part_id,
        field: d.field,
        value: d.new_value,
        source_id: receipt.value.id,
      })),
    })
    message.success('配件电镀成本已更新')
    addItemsCostDiffVisible.value = false
  } catch (_) {
    message.error('成本更新失败，请重试')
  } finally {
    addItemsCostDiffUpdating.value = false
  }
}

const skipAddItemsCostUpdate = () => {
  addItemsCostDiffVisible.value = false
}

const addItemsColumns = [
  { type: 'selection' },
  { title: '电镀单号', key: 'plating_order_id', width: 100 },
  {
    title: '配件',
    key: 'part_name',
    minWidth: 140,
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name, 40, row.part_is_composite ? '组合' : null),
  },
  { title: '电镀方式', key: 'plating_method', width: 80, render: (r) => r.plating_method || '-' },
  {
    title: '发出日期',
    key: 'created_at',
    width: 100,
    render: (r) => r.created_at ? new Date(r.created_at).toLocaleDateString('zh-CN') : '-',
  },
  { title: '剩余', key: 'remaining', width: 70, render: (r) => getAddRemaining(r) },
  {
    title: '本次回收',
    key: 'input_qty',
    width: 110,
    render: (row) => {
      const input = getAddInput(row.id)
      return h(NInputNumber, {
        value: input.qty,
        min: 0.0001,
        max: getAddRemaining(row),
        precision: 4,
        step: 1,
        size: 'small',
        style: 'width: 100px;',
        'onUpdate:value': (v) => { input.qty = v },
      })
    },
  },
  {
    title: '重量',
    key: 'input_weight',
    width: 140,
    render: (row) => {
      const input = getAddInput(row.id)
      return h('div', { style: 'display:flex;gap:4px;align-items:center' }, [
        h(NInputNumber, {
          value: input.weight,
          size: 'small',
          style: 'width:80px',
          min: 0,
          placeholder: '重量',
          'onUpdate:value': (v) => { input.weight = v },
        }),
        h(NSelect, {
          value: input.weight_unit || 'g',
          size: 'small',
          style: 'width:55px',
          options: [{ label: 'g', value: 'g' }, { label: 'kg', value: 'kg' }],
          'onUpdate:value': (v) => { input.weight_unit = v },
        }),
      ])
    },
  },
  {
    title: '单价',
    key: 'input_price',
    width: 110,
    render: (row) => {
      const input = getAddInput(row.id)
      return h(NInputNumber, {
        value: input.price,
        min: 0,
        precision: 7,
        format: fmtPrice,
        parse: parseNum,
        step: 0.1,
        size: 'small',
        style: 'width: 100px;',
        'onUpdate:value': (v) => { input.price = v },
      })
    },
  },
]

onMounted(async () => {
  try {
    await loadData()
  } finally {
    loading.value = false
  }
  await scrollToHighlight()
})
</script>

<style scoped>
.receipt-detail { min-width: 0; }
.rd-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin: 8px 0 20px; }
.rd-title { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.rd-title .page-title { margin: 0; }
.rd-status { border: 0; border-radius: 20px; padding: 4px 11px; font: inherit; font-size: 11px; font-weight: 600; background: #FBF0DC; color: #B7791F; cursor: pointer; }
.rd-status.is-paid { background: #E6F2EC; color: #1E7A5A; }
.rd-status:focus-visible, .delivery-image-add:focus-visible { outline: 2px solid #1E7A5A; outline-offset: 3px; }
.rd-stats { display: grid; grid-template-columns: .85fr 1.15fr 1fr .9fr 1.3fr; background: #fff; border: 1px solid #ECEDEF; border-radius: 9px; overflow: hidden; }
.rd-stat { min-width: 0; padding: 14px 17px; border-right: 1px solid #ECEDEF; }
.rd-stat:last-child { border-right: 0; }
.rd-stat-label, .rd-meta-label { font-size: 10px; color: #8B9096; margin-bottom: 4px; }
.rd-stat-value { font-size: 25px; font-weight: 700; line-height: 1.25; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.rd-stat-value small { font-size: 12px; color: #8B9096; font-weight: 500; margin: 0 4px; }
.rd-quantities { display: flex; flex-wrap: wrap; gap: 4px 10px; }
.rd-quantities span { white-space: nowrap; }
.rd-stat-note { font-size: 10px; color: #A4ABB1; margin-top: 4px; }
.rd-stat-value.is-green { color: #1E7A5A; }
.rd-stat-value.is-amber { color: #B7791F; }
.rd-meta { display: grid; grid-template-columns: minmax(140px, 1.1fr) minmax(170px, 1fr) minmax(130px, .9fr) minmax(160px, 1.5fr); gap: 18px; padding: 20px 0 26px; }
.rd-meta-item { min-width: 0; }
.rd-meta-value { font-size: 12px; min-height: 20px; overflow-wrap: anywhere; }
.rd-meta-value :deep(.n-space) { max-width: 100%; }
.rd-note-text { white-space: pre-wrap; }
.rd-section { margin-bottom: 24px; }
.rd-section-head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; border-bottom: 1px solid #ECEDEF; padding-bottom: 9px; margin-bottom: 12px; }
.rd-section-title { display: flex; align-items: center; gap: 8px; }
.rd-section-title h3 { margin: 0; font-size: 11px; color: #8B9096; letter-spacing: .8px; font-weight: 700; }
.rd-count { font-size: 10px; border-radius: 4px; padding: 1px 6px; color: #879199; background: #E9ECEF; }
.rd-hint, .rd-table-note { font-size: 10px; color: #939DA5; }
.rd-table-note { margin: 9px 0 0; }
.rd-table { border: 1px solid #ECEDEF; border-radius: 9px; overflow: hidden; }
.rd-table :deep(th.n-data-table-th) { background: #FAFBFB; color: #8B9096; font-size: 10px; font-weight: 600; }
.rd-table :deep(td.n-data-table-td) { padding: 14px 12px; font-size: 12px; }
.rd-table :deep(.rd-part-name) { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; font-weight: 600; }
.rd-table :deep(.rd-part-code) { color: #A5ADB4; font-size: 10px; margin-top: 2px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.rd-table :deep(.rd-composite) { font-size: 9px; font-weight: 400; border-radius: 3px; padding: 1px 5px; background: #F0F2F4; color: #879199; }
.rd-table :deep(.rd-source-link) { color: #718278; text-decoration: none; }
.rd-table :deep(.rd-source-link:hover) { color: #1E7A5A; text-decoration: underline; }
.rd-table :deep(.rd-qty), .rd-table :deep(.rd-amount) { font-weight: 600; font-variant-numeric: tabular-nums; }
.rd-table :deep(.rd-qty) { color: #1E7A5A; white-space: nowrap; }
.rd-table :deep(.rd-qty small) { color: #A4ACB3; font-size: 10px; font-weight: 400; margin-left: 4px; }
.rd-table :deep(.rd-unpriced) { color: #B7791F; font-size: 11px; }
.rd-footer { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.rd-footer-note { margin: 0; color: #939EA5; font-size: 11px; }
.rd-add-filters { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 12px; }
@media (max-width: 1200px) {
  .rd-meta { grid-template-columns: 1fr 1fr; }
  .rd-stat { padding: 12px; }
}
@media (max-width: 760px) {
  .receipt-detail > .page-breadcrumb { padding-left: 32px; }
  .rd-title .page-title { font-size: 22px; }
  .rd-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .rd-stat { border-bottom: 1px solid #ECEDEF; }
  .rd-stat:nth-child(2n) { border-right: 0; }
  .rd-stat:last-child { grid-column: 1 / -1; border-bottom: 0; }
  .rd-stat-value { font-size: 22px; }
  .rd-meta { gap: 14px; }
  .rd-meta-note { grid-column: 1 / -1; }
}
.delivery-images-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.delivery-images-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.delivery-images-warning {
  padding: 12px;
  border-radius: 12px;
  border: 1px solid #f3d08a;
  background: #fff8e8;
}

.delivery-images-warning-title {
  color: #8a5a17;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}

.delivery-images-pending-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.delivery-pending-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.delivery-pending-preview {
  display: block;
  border-radius: 10px;
  overflow: hidden;
}

.delivery-pending-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.delivery-image-card {
  position: relative;
  width: 88px;
  height: 88px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #E0E4E7;
  background: #F6F7F8;
}

.delivery-image-preview {
  display: block;
}

.delivery-image-delete {
  position: absolute;
  top: 6px;
  right: 6px;
}

.delivery-image-add {
  width: 88px;
  height: 88px;
  border: 1px dashed #D1D9D4;
  border-radius: 8px;
  background: #F7FAF8;
  color: #98AA9F;
  font-size: 30px;
  line-height: 1;
  cursor: pointer;
}

.delivery-image-add:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.delivery-images-meta {
  color: #939DA5;
  font-size: 12px;
}

@keyframes receipt-highlight-flash {
  0%, 100% { background-color: transparent; }
  50% { background-color: #c8e6c9; }
}
:deep(.receipt-highlight-row td) {
  animation: receipt-highlight-flash 1.6s ease-in-out 3;
  position: relative;
}
:deep(.receipt-highlight-row td:first-child)::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: #18a058;
  border-radius: 2px;
}
</style>
