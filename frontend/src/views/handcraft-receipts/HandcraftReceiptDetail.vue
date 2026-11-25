<template>
  <div class="receipt-detail">
    <div class="page-breadcrumb">生产 / 手工回收 / {{ receipt?.id || route.params.id }}</div>
    <header class="rd-head">
      <div class="rd-title">
        <h2 class="page-title">手工回收单 {{ receipt?.id || route.params.id }}</h2>
        <n-popselect v-if="receipt" :value="receipt.status" :options="statusToggleOptions" trigger="click" @update:value="doChangeStatus">
          <button type="button" class="rd-status" :class="{ 'is-paid': isPaid() }" aria-label="切换回收单付款状态">{{ receipt.status }} ▾</button>
        </n-popselect>
      </div>
      <n-button text size="small" @click="goBack">← {{ summaryReturn?.path === '/handcraft-output' ? '返回产出总览' : summaryReturn ? '返回汇总' : '返回' }}</n-button>
    </header>

    <n-spin :show="loading">
      <n-empty v-if="!loading && !receipt" description="加载失败，请返回重试" style="margin-top: 24px;" />
      <template v-if="receipt">
        <section class="rd-stats" aria-label="回收单统计">
          <div class="rd-stat"><div class="rd-stat-label">回收明细</div><div class="rd-stat-value">{{ items.length }}<small>项</small></div><div class="rd-stat-note">产出 {{ detailSummary.outputCount }} 项 · 退料 {{ detailSummary.partCount }} 项</div></div>
          <div class="rd-stat"><div class="rd-stat-label">本单回收数量</div><div class="rd-stat-value rd-quantities"><span v-for="entry in detailSummary.quantities" :key="entry.unit">{{ entry.qty }}<small>{{ entry.unit }}</small></span><template v-if="!detailSummary.quantities.length">—</template></div><div class="rd-stat-note">不同单位分别汇总</div></div>
          <div class="rd-stat"><div class="rd-stat-label">回收总重量</div><div class="rd-stat-value">{{ detailSummary.weightKg ?? '—' }}<small v-if="detailSummary.weightKg != null">kg</small></div><div class="rd-stat-note">仅汇总已填写重量</div></div>
          <div class="rd-stat"><div class="rd-stat-label">已定价手工费</div><div class="rd-stat-value rd-total"><small v-if="receipt.total_amount != null">¥</small>{{ receipt.total_amount != null ? fmtMoney(receipt.total_amount) : '—' }}</div><div class="rd-stat-note">按本单已填写单价的明细汇总</div></div>
        </section>

        <dl class="rd-meta" aria-label="基本信息">
          <div><dt>手工商家</dt><dd>{{ receipt.supplier_name }}</dd></div>
          <div><dt>创建时间</dt><dd>
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
          </dd></div>
          <div><dt>付款时间</dt><dd>{{ receipt.paid_at ? fmt(receipt.paid_at) : '—' }}</dd></div>
          <div><dt>备注</dt><dd class="rd-note">{{ receipt.note || '—' }}</dd></div>
        </dl>

        <section class="rd-section" aria-labelledby="handcraft-receipt-items-title">
          <div class="rd-section-head">
            <div class="rd-section-title"><h3 id="handcraft-receipt-items-title">回收明细</h3><span class="rd-count">{{ items.length }} 项</span></div>
            <n-button v-if="!isPaid()" size="small" type="primary" @click="openAddItemsModal">＋ 添加回收项</n-button>
            <span v-else class="rd-hint">已付款 · 明细已锁定</span>
          </div>
          <n-data-table v-if="items.length" class="rd-table" :columns="itemColumns" :data="items" :bordered="false" :row-key="row => row.id" :scroll-x="1140" :row-props="summaryHighlight" />
          <n-empty v-else class="rd-empty" :description="isPaid() ? '暂无回收明细' : '暂无回收明细，可添加产出回收或配件退料'" />
          <p v-if="items.length" class="rd-hint rd-table-note">数量为本单实际回收数量；损耗针对来源手工单的差额，不计入本单回收数量。</p>
        </section>

        <section class="rd-section" aria-labelledby="handcraft-receipt-images-title">
          <div class="rd-section-head">
            <div class="rd-section-title"><h3 id="handcraft-receipt-images-title">单据与配件图片</h3><span class="rd-count">{{ totalDeliveryImageCount }} / 9</span></div>
            <span class="rd-hint">点击图片预览</span>
          </div>
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
            </div>
        </section>

        <footer class="rd-footer">
          <span class="rd-hint">{{ isPaid() ? '已付款后不可修改、添加或删除回收明细。' : '标记为已付款后将锁定回收明细。' }}</span>
          <n-button text size="small" type="error" :disabled="isPaid()" @click="doDeleteReceipt">删除回收单</n-button>
        </footer>
      </template>
    </n-spin>

    <!-- Edit Item Modal -->
    <n-modal v-model:show="editModalVisible" preset="card" title="修改明细" :style="{ width: isMobile ? '95vw' : '500px' }">
      <p>允许超过发出数量，库存及金额按实际回收数量调整；产出须为整数。</p>
      <form @submit.prevent="doEditItem">
      <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="90">
        <n-form-item label="数量">
          <n-input-number
            v-model:value="editForm.qty"
            :min="editForm.item_type === 'jewelry' ? 1 : 0.0001"
            :precision="editForm.item_type === 'jewelry' ? 0 : 4"
            :step="1"
            style="width: 100%;"
          />
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
      kind="handcraft-receipts"
      :entity-id="receipt?.id"
      suppress-success
      @uploaded="handleDeliveryImageUploaded"
    />

    <AddHandcraftReceiptItems
      v-if="addItemsModalVisible && receipt"
      :receipt="receipt"
      @close="addItemsModalVisible = false"
      @saved="onAddItemsSaved"
      @verified="onAddItemsVerified"
    />

    <!-- Cost Diff Modal (from add items) -->
    <n-modal v-model:show="addItemsCostDiffVisible" :mask-closable="false" :closable="!addItemsCostDiffUpdating" :close-on-esc="!addItemsCostDiffUpdating" preset="card" title="手工费成本变动确认" :style="{ width: isMobile ? '95vw' : '550px' }">
      <div style="margin-bottom: 12px; color: #333;">
        当前手工费与配件已有手工费金额不相同，是否更新手工费成本？
      </div>
      <n-data-table
        :columns="[
          { title: '配件编号', key: 'part_id', width: 160 },
          { title: '配件名称', key: 'part_name', minWidth: 120 },
          { title: '原手工费', key: 'current_value', width: 120, render: (r) => r.current_value != null ? `¥ ${fmtMoney(r.current_value)}` : '-' },
          { title: '更新手工费', key: 'new_value', width: 120, render: (r) => h('span', { style: 'color: #d03050; font-weight: 600;' }, `¥ ${fmtMoney(r.new_value)}`) },
        ]"
        :data="addItemsCostDiffs"
        :bordered="false"
        :scroll-x="520"
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
          <n-input-number v-model:value="lossForm.loss_qty" :min="lossTarget?.item_type === 'jewelry' ? 1 : 0.01" :precision="lossTarget?.item_type === 'jewelry' ? 0 : undefined" :max="lossTarget ? (lossTarget.source_qty || 0) - (lossTarget.source_received_qty || 0) : 0" style="width: 100%;" />
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
import { ref, computed, onMounted, h, nextTick } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useHandcraftSummaryReturn } from '@/composables/useHandcraftSummaryReturn'
import { useMessage, useDialog } from 'naive-ui'
import { useIsMobile } from '@/composables/useIsMobile'
import {
  NSpin, NDataTable, NSpace, NButton, NEmpty, NModal, NForm, NFormItem,
  NSelect, NInputNumber, NInput, NPopselect, NTooltip, NIcon, NImage, NDatePicker,
} from 'naive-ui'
import { CreateOutline } from '@vicons/ionicons5'
import {
  getHandcraftReceipt, updateHandcraftReceipt, updateHandcraftReceiptStatus,
  updateHandcraftReceiptDeliveryImages,
  updateHandcraftReceiptItem, deleteHandcraftReceiptItem,
  deleteHandcraftReceipt,
} from '@/api/handcraftReceipts'
import { tsToDateStr, isoToTs } from '@/utils/date'
import { batchUpdatePartCosts } from '@/api/parts'
import { confirmHandcraftLoss } from '@/api/productionLoss'
import { fmtMoney, fmtPrice, parseNum } from '@/utils/ui'
import { receiptSourceExcess } from '@/utils/receiptQuantity'
import { summarizeHandcraftReceiptDetail } from '@/utils/handcraftReceiptDetail'
import ImageUploadModal from '@/components/ImageUploadModal.vue'
import AddHandcraftReceiptItems from './AddHandcraftReceiptItems.vue'

const route = useRoute()
const router = useRouter()
const { summaryReturn, goBack } = useHandcraftSummaryReturn()
function summaryHighlight(row) {
  return summaryReturn.value && route.query.highlight === String(row.id)
    ? { style: 'outline: 2px solid #1e7a5a; outline-offset: -2px;', title: '汇总回收批次明细' } : {}
}
const message = useMessage()
const dialog = useDialog()
const { isMobile } = useIsMobile()

const loading = ref(true)
const receipt = ref(null)
const items = computed(() => receipt.value?.items || [])
const detailSummary = computed(() => summarizeHandcraftReceiptDetail(items.value))

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
    await updateHandcraftReceipt(route.params.id, { created_at: dateStr })
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
    const payload = {
      ...lossForm.value,
      item_type: lossTarget.value.item_type,
    }
    if (!payload.deduct_amount) payload.deduct_amount = null
    if (!payload.reason) payload.reason = null
    if (!payload.note) payload.note = null
    const itemId = lossTarget.value.item_type === 'part'
      ? lossTarget.value.handcraft_part_item_id
      : lossTarget.value.handcraft_jewelry_item_id
    await confirmHandcraftLoss(lossTarget.value.handcraft_order_id, itemId, payload)
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

// Cost diff modal (for add-items)
const addItemsCostDiffVisible = ref(false)
const addItemsCostDiffs = ref([])
const addItemsCostDiffUpdating = ref(false)

const applyReceipt = (data) => {
  receipt.value = data
  pendingDeliveryImages.value = pendingDeliveryImages.value.filter((image) => !(data.delivery_images || []).includes(image))
  if (isPaid()) {
    stopEditNote()
  }
}

const loadData = async () => {
  const { data } = await getHandcraftReceipt(route.params.id)
  applyReceipt(data)
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
        await updateHandcraftReceiptStatus(receipt.value.id, newStatus)
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
    item_type: row.item_type,
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
    const { id, item_type, ...body } = editForm.value
    await updateHandcraftReceiptItem(route.params.id, id, body)
    message.success('修改已保存')
    editModalVisible.value = false
    await loadData()
  } finally {
    editSubmitting.value = false
  }
}

const doDeleteItem = (row) => {
  dialog.warning({
    title: '确认删除',
    content: `确认删除 ${row.item_name || row.item_id} 的明细行？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteHandcraftReceiptItem(route.params.id, row.id)
        message.success('已删除')
        await loadData()
      } catch (_) {}
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
        await deleteHandcraftReceipt(route.params.id)
        message.success('回收单已删除')
        if (summaryReturn.value) goBack()
        else router.push('/handcraft-receipts')
      } catch (_) {}
    },
  })
}

// Delivery images
const mergeDeliveryImages = (...groups) => [...new Set(groups.flat().filter(Boolean))]

const persistDeliveryImages = async (nextImages, successText) => {
  if (!receipt.value) return
  deliveryImagesSaving.value = true
  try {
    const { data } = await updateHandcraftReceiptDeliveryImages(receipt.value.id, nextImages)
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
    const { data } = await updateHandcraftReceiptItem(route.params.id, itemId, { note: nextNote })
    row.note = data.note || ''
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
        !isPaid() ? 'cursor: pointer; color: #1e7a5a;' : '',
      ].join('; '),
      onClick: !isPaid() ? () => startEditNote(row) : undefined,
    },
    noteText,
  )
}

const itemColumns = [
  {
    title: '回收项',
    key: 'item_name',
    minWidth: 180,
    render: (row) => h('div', { class: 'rd-product' }, [
      h('strong', row.item_name || row.item_id),
      h('small', [row.item_id, row.color].filter(Boolean).join(' · ')),
    ]),
  },
  {
    title: '类型', key: 'item_type', width: 95,
    render: row => h('span', { class: ['rd-type', { 'is-output': row.handcraft_jewelry_item_id != null }] },
      row.handcraft_jewelry_item_id == null ? '配件退料' : row.is_composite ? '组合配件产出' : '产出回收'),
  },
  {
    title: '来源手工单',
    key: 'handcraft_order_id',
    width: 110,
    render: (row) => {
      if (!row.handcraft_order_id) return '-'
      return h(RouterLink, {
        class: 'rd-source-link',
        to: { path: `/handcraft/${row.handcraft_order_id}`, query: summaryReturn.value ? { from: 'handcraft-summary' } : {} },
      }, { default: () => row.handcraft_order_id })
    },
  },
  { title: '回收数量', key: 'qty', width: 110, render: (r) => h('div', [h('strong', { class: 'rd-qty' }, `${r.qty} ${r.unit || ''}`),
    receiptSourceExcess(r) ? h('small', { class: 'rd-source-excess' }, `结清超出 ${receiptSourceExcess(r)}`) : null,
  ]) },
  { title: '重量', key: 'weight', width: 90, render: (r) => r.weight != null ? `${r.weight} ${r.weight_unit || 'g'}` : '—' },
  { title: '手工单价', key: 'price', width: 105, render: (r) => r.price != null ? `¥ ${fmtPrice(r.price)}` : '—' },
  { title: '金额', key: 'amount', width: 95, render: (r) => r.amount != null ? `¥ ${fmtMoney(r.amount)}` : '—' },
  {
    title: '备注',
    key: 'note',
    minWidth: 165,
    render: (row) => renderNoteCell(row),
  },
  {
    title: '操作',
    key: 'actions',
    width: 190,
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
                disabled: !canEdit,
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
          type: 'warning',
          onClick: () => openLossModal(row),
        }, { default: () => '确认损耗' }))
      }
      return h(NSpace, { size: 6 }, { default: () => btns })
    },
  },
]

const openAddItemsModal = () => {
  if (receipt.value && !isPaid()) addItemsModalVisible.value = true
}

const onAddItemsSaved = (data, count) => {
  applyReceipt(data)
  addItemsModalVisible.value = false
  message.success(`已添加 ${count} 项回收明细`)
  if (data.cost_diffs?.length) {
    addItemsCostDiffs.value = data.cost_diffs
    addItemsCostDiffVisible.value = true
  }
}

const onAddItemsVerified = (data) => {
  applyReceipt(data)
  addItemsModalVisible.value = false
  message.warning('已刷新，请核对回收明细后再决定是否补录')
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
    message.success('配件手工费成本已更新')
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

onMounted(async () => {
  try {
    await loadData()
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.receipt-detail { min-width: 0; }
.rd-head, .rd-title, .rd-section-head, .rd-section-title, .rd-footer { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.rd-head, .rd-section-head, .rd-footer { justify-content: space-between; }
.rd-head { margin: 8px 0 20px; }
.rd-title .page-title { margin: 0; }
.rd-status { padding: 4px 11px; border: 0; border-radius: 20px; font: inherit; font-size: 12px; font-weight: 600; background: #fbf0dc; color: #875817; cursor: pointer; }
.rd-status.is-paid { background: #e6f2ec; color: #1e7a5a; }
.rd-status:focus-visible, .delivery-image-add:focus-visible { outline: 2px solid #1e7a5a; outline-offset: 3px; }
.rd-stats { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr) minmax(0, .9fr) minmax(0, 1.15fr); border: 1px solid #e8ecee; border-radius: 9px; background: #e8ecee; gap: 1px; overflow: hidden; }
.rd-stat { min-width: 0; background: #fff; padding: 14px 17px; }
.rd-stat-label, .rd-meta dt { font-size: 12px; color: #667179; margin-bottom: 4px; }
.rd-stat-value { font-size: 25px; font-weight: 700; line-height: 1.25; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.rd-stat-value small { font-size: 12px; color: #667179; font-weight: 500; margin: 0 4px; }
.rd-quantities { display: flex; flex-wrap: wrap; gap: 4px 10px; }
.rd-stat-note, .rd-hint { font-size: 12px; color: #667179; }
.rd-stat-note { margin-top: 4px; }
.rd-total { color: #1e7a5a; }
.rd-meta { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 18px; margin: 0; padding: 20px 0 26px; }
.rd-meta dd { font-size: 13px; min-height: 20px; margin: 0; overflow-wrap: anywhere; }
.rd-note { white-space: pre-wrap; }
.rd-section { margin-bottom: 24px; }
.rd-section-head { border-bottom: 1px solid #e8ecee; padding-bottom: 9px; margin-bottom: 12px; }
.rd-section-title h3 { margin: 0; font-size: 14px; }
.rd-count { font-size: 11px; border-radius: 4px; padding: 1px 6px; color: #52635b; background: #edf2ef; }
.rd-table-note { margin: 9px 0 0; }
.rd-empty { padding: 24px; }
.rd-table { border: 1px solid #e8ecee; border-radius: 9px; overflow: hidden; }
.rd-table :deep(th.n-data-table-th) { background: #fafbfb; color: #667179; font-size: 12px; font-weight: 600; }
.rd-table :deep(td.n-data-table-td) { padding: 12px 10px; font-size: 12px; }
.rd-table :deep(.rd-product) { display: grid; gap: 3px; overflow-wrap: anywhere; }
.rd-table :deep(.rd-product small) { color: #667179; font-size: 11px; }
.rd-table :deep(.rd-type) { font-size: 10px; border-radius: 4px; padding: 3px 5px; background: #eef1f3; color: #526169; white-space: nowrap; }
.rd-table :deep(.rd-type.is-output) { background: #e8f3ed; color: #1e7a5a; }
.rd-table :deep(.rd-qty), .rd-table :deep(.rd-source-link) { color: #1e7a5a; }
.rd-table :deep(.rd-source-link:hover) { text-decoration: underline; }
.rd-table :deep(.rd-source-excess) { display: block; color: #9c510d; }
.rd-footer { border-top: 1px solid #e8ecee; padding: 12px 0; }
@media (max-width: 900px) {
  .rd-stats, .rd-meta { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 560px) {
  .rd-stat { padding: 11px; }
  .rd-stat-value { font-size: 20px; }
  .rd-meta { gap: 12px; padding: 16px 0 20px; }
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
  border-radius: 9px;
  overflow: hidden;
  border: 1px solid #e5ece8;
  background: #f6f8f7;
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
  border: 1px dashed #a6c9b7;
  border-radius: 9px;
  background: #f1f7f4;
  color: #1e7a5a;
  font-size: 30px;
  line-height: 1;
  cursor: pointer;
}

.delivery-image-add:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

</style>
