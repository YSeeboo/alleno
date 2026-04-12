<template>
  <div>
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">回收单详情</n-h2>
    </n-space>

    <n-spin :show="loading">
      <n-empty v-if="!loading && !receipt" description="加载失败，请返回重试" style="margin-top: 24px;" />
      <n-card v-if="receipt" title="基本信息" style="margin-bottom: 16px;">
        <n-descriptions :column="3" bordered>
          <n-descriptions-item label="回收单号">{{ receipt.id }}</n-descriptions-item>
          <n-descriptions-item label="商家">{{ receipt.vendor_name }}</n-descriptions-item>
          <n-descriptions-item label="状态">
            <n-popselect
              :value="receipt?.status"
              :options="statusToggleOptions"
              trigger="click"
              @update:value="doChangeStatus"
            >
              <n-tag
                :type="statusType[receipt.status]"
                style="cursor: pointer;"
              >
                {{ receipt.status }} ▾
              </n-tag>
            </n-popselect>
          </n-descriptions-item>
          <n-descriptions-item label="总金额">{{ receipt.total_amount != null ? `¥ ${fmtMoney(receipt.total_amount)}` : '-' }}</n-descriptions-item>
          <n-descriptions-item label="创建时间">
            <template v-if="editingCreatedAt">
              <n-space align="center" size="small">
                <n-date-picker
                  v-model:value="editingCreatedAtTs"
                  type="date"
                  size="small"
                  style="width: 160px;"
                />
                <n-button size="small" type="primary" :loading="savingCreatedAt" @click="saveCreatedAt">确认</n-button>
                <n-button size="small" :disabled="savingCreatedAt" @click="editingCreatedAt = false">取消</n-button>
              </n-space>
            </template>
            <template v-else>
              {{ fmt(receipt.created_at) }}
              <n-button text type="primary" size="small" style="margin-left: 6px;" @click="startEditCreatedAt">
                <template #icon><n-icon :component="CreateOutline" /></template>
              </n-button>
            </template>
          </n-descriptions-item>
          <n-descriptions-item label="付款时间">{{ receipt.paid_at ? fmt(receipt.paid_at) : '-' }}</n-descriptions-item>
          <n-descriptions-item label="备注">{{ receipt.note || '-' }}</n-descriptions-item>
          <n-descriptions-item label="单据&配件图片" :span="2">
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
                  :disabled="deliveryImagesSaving"
                  @click="openDeliveryImageModal"
                >
                  +
                </button>
              </div>
              <button
                v-else
                class="delivery-image-add"
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
          </n-descriptions-item>
        </n-descriptions>
      </n-card>

      <n-card v-if="receipt">
        <template #header>
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span>回收明细</span>
            <n-button v-if="!isPaid()" size="small" type="primary" @click="openAddItemsModal">+ 增加配件</n-button>
          </div>
        </template>
        <n-data-table v-if="receipt.items?.length > 0" :columns="itemColumns" :data="receipt.items" :bordered="false" />
        <n-empty v-else description="暂无明细" style="margin-top: 16px;" />
      </n-card>

      <div v-if="receipt" style="margin-top: 16px;">
        <n-button type="error" :disabled="isPaid()" @click="doDeleteReceipt">删除回收单</n-button>
      </div>
    </n-spin>

    <!-- Edit Item Modal -->
    <n-modal v-model:show="editModalVisible" preset="card" title="修改明细" style="width: 500px;">
      <form @submit.prevent="doEditItem">
      <n-form label-placement="left" label-width="90">
        <n-form-item label="数量">
          <n-input-number v-model:value="editForm.qty" :min="0.0001" :precision="2" :step="1" style="width: 100%;" />
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
    <n-modal v-model:show="addItemsModalVisible" preset="card" :title="`增加回收配件（${receipt?.vendor_name}）`" style="width: 800px;">
      <div style="display: flex; gap: 12px; align-items: center; margin-bottom: 12px;">
        <n-input
          v-model:value="addItemsFilterKeyword"
          placeholder="编号/名称搜索"
          clearable
          style="width: 200px;"
          @update:value="onAddItemsFilterKeyword"
        />
        <span style="font-size: 13px; color: #666;">发出日期</span>
        <n-date-picker
          v-model:value="addItemsFilterDateOn"
          type="date"
          clearable
          style="width: 160px;"
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
    <n-modal v-model:show="addItemsCostDiffVisible" :mask-closable="false" preset="card" title="电镀成本变动确认" style="width: 550px;">
      <div style="margin-bottom: 12px; color: #333;">
        当前电镀成本与配件已有电镀成本金额不相同，是否更新电镀成本？
      </div>
      <n-data-table
        :columns="[
          { title: '配件编号', key: 'part_id', width: 130 },
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
    <n-modal v-model:show="showLossModal" preset="card" title="确认损耗" style="width: 420px;">
      <n-form label-placement="left" label-width="80">
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
import { ref, reactive, computed, onMounted, h, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NTag, NEmpty, NModal, NForm, NFormItem,
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

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()

const loading = ref(true)
const receipt = ref(null)

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

const statusType = { '已付款': 'success', '未付款': 'error' }
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
        !isPaid() ? 'cursor: pointer; color: #2080f0;' : '',
      ].join('; '),
      onClick: !isPaid() ? () => startEditNote(row) : undefined,
    },
    noteText,
  )
}

const itemColumns = [
  { title: '配件编号', key: 'part_id', width: 120 },
  {
    title: '配件',
    key: 'part_name',
    minWidth: 140,
    render: (row) => row.part_name || row.part_id,
  },
  {
    title: '电镀单号',
    key: 'plating_order_id',
    width: 110,
    render: (row) => {
      if (!row.plating_order_id) return '-'
      return h('a', {
        style: 'color: #2080f0; cursor: pointer;',
        onClick: (e) => { e.stopPropagation(); router.push(`/plating/${row.plating_order_id}`) },
      }, row.plating_order_id)
    },
  },
  { title: '电镀方式', key: 'plating_method', width: 90, render: (r) => r.plating_method || '-' },
  { title: '回收数量', key: 'qty' },
  { title: '单位', key: 'unit', render: (r) => r.unit || '-' },
  { title: '重量', key: 'weight', width: 100, render: (r) => r.weight != null ? `${r.weight} ${r.weight_unit || 'g'}` : '—' },
  { title: '单价', key: 'price', render: (r) => r.price != null ? `¥ ${fmtMoney(r.price)}` : '-' },
  { title: '金额', key: 'amount', render: (r) => r.amount != null ? `¥ ${fmtMoney(r.amount)}` : '-' },
  {
    title: '备注',
    key: 'note',
    minWidth: 240,
    render: (row) => renderNoteCell(row),
  },
  {
    title: '操作',
    key: 'actions',
    width: 140,
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
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name),
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
})
</script>

<style scoped>
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
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid #eadbc1;
  background: linear-gradient(180deg, #fffdf7, #f7f0e1);
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
  border: 1px dashed #d6b98d;
  border-radius: 14px;
  background: linear-gradient(180deg, #fffaf0, #f6eedc);
  color: #8a5a17;
  font-size: 30px;
  line-height: 1;
  cursor: pointer;
}

.delivery-image-add:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.delivery-images-meta {
  color: #8a6b39;
  font-size: 12px;
}
</style>
