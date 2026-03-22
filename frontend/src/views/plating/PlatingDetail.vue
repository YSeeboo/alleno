<template>
  <div>
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">电镀单详情</n-h2>
    </n-space>

    <n-spin :show="loading">
      <n-card v-if="order" title="基本信息" style="margin-bottom: 16px;">
        <template #header-extra>
          <n-space size="small">
            <n-button
              :loading="downloadingExcel"
              class="export-excel-btn"
              @click="doDownloadExcel"
            >
              导出Excel
            </n-button>
            <n-button
              :loading="downloadingPdf"
              class="export-pdf-btn"
              @click="doDownloadPdf"
            >
              导出PDF
            </n-button>
          </n-space>
        </template>
        <n-descriptions :column="3" bordered>
          <n-descriptions-item label="电镀单号">{{ order.id }}</n-descriptions-item>
          <n-descriptions-item label="电镀厂">{{ order.supplier_name }}</n-descriptions-item>
          <n-descriptions-item label="状态">
            <n-popselect
              :value="order?.status"
              :options="statusOptions"
              trigger="click"
              :disabled="statusOptions.length === 0"
              @update:value="doChangeStatus"
            >
              <n-tag
                :type="statusType[order.status]"
                :style="statusOptions.length > 0 ? 'cursor: pointer;' : ''"
              >
                {{ statusLabel[order.status] }}{{ statusOptions.length > 0 ? ' ▾' : '' }}
              </n-tag>
            </n-popselect>
          </n-descriptions-item>
          <n-descriptions-item label="创建时间">{{ fmt(order.created_at) }}</n-descriptions-item>
          <n-descriptions-item label="完成时间">{{ order.completed_at ? fmt(order.completed_at) : '-' }}</n-descriptions-item>
          <n-descriptions-item label="备注">{{ order.note || '-' }}</n-descriptions-item>
          <n-descriptions-item label="发货图片" :span="2">
            <div class="delivery-images-block">
              <div v-if="pendingDeliveryImages.length > 0" class="delivery-images-warning">
                <div class="delivery-images-warning-title">
                  有 {{ pendingDeliveryImages.length }} 张图片已上传，但还没保存到电镀单
                </div>
                <div class="delivery-images-pending-list">
                  <div
                    v-for="image in pendingDeliveryImages"
                    :key="`pending-${image}`"
                    class="delivery-pending-item"
                  >
                    <n-image
                      :src="image"
                      alt="待保存发货图片"
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
                    alt="发货图片"
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
                {{ totalDeliveryImageCount }}/4 张
                <span v-if="pendingDeliveryImages.length > 0">（待保存 {{ pendingDeliveryImages.length }} 张）</span>
              </div>
            </div>
          </n-descriptions-item>
        </n-descriptions>
        <n-space style="margin-top: 12px;">
          <n-button v-if="order.status === 'pending'" type="primary" :loading="sending" @click="doSend">
            确认发出
          </n-button>
          <n-button v-if="order.status === 'processing'" type="warning" :loading="bulkReceiving" @click="doBulkReceive">
            整单回收
          </n-button>
        </n-space>
      </n-card>

      <n-card title="电镀明细">
        <n-data-table v-if="items.length > 0" :columns="itemColumns" :data="items" :bordered="false" />
        <n-empty v-else description="暂无明细" style="margin-top: 16px;" />
        <div v-if="order?.status === 'pending'" style="margin-top: 12px;">
          <n-button dashed style="width: 100%;" @click="openAddModal">+ 添加明细行</n-button>
        </div>
      </n-card>
    </n-spin>

    <!-- Add Item Modal -->
    <n-modal v-model:show="addModalVisible" preset="card" title="添加电镀明细" style="width: 500px;">
      <n-form label-placement="left" label-width="90">
        <n-form-item label="发出配件">
          <n-select
            v-model:value="addForm.part_id"
            :options="partOptions"
            :render-label="renderOptionWithImage"
            filterable
            placeholder="选择发出配件"
            @update:value="onAddPartSelect"
          />
        </n-form-item>
        <n-form-item label="收回配件">
          <n-select
            v-model:value="addForm.receive_part_id"
            :options="getReceivePartOptions(addForm.part_id)"
            :render-label="renderOptionWithImage"
            filterable
            clearable
            placeholder="默认同发出配件"
            @update:value="(v) => autoFillMethod(v, addForm)"
          />
        </n-form-item>
        <n-form-item label="数量">
          <n-input-number v-model:value="addForm.qty" :min="1" :precision="0" :step="1" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="addForm.unit" :options="unitOptions" />
        </n-form-item>
        <n-form-item label="电镀方式">
          <n-select v-model:value="addForm.plating_method" :options="platingMethodOptions" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="addForm.note" placeholder="备注（可选）" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="addModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="addSubmitting" @click="doAddItem">确认添加</n-button>
        </n-space>
      </template>
    </n-modal>


    <ImageUploadModal
      v-model:show="showDeliveryImageModal"
      kind="plating"
      :entity-id="order?.id"
      suppress-success
      @uploaded="handleDeliveryImageUploaded"
    />

    <!-- Partial Receive Modal -->
    <n-modal v-model:show="detailPartialReceiveVisible" preset="card" title="部分回收" style="width: 400px;">
      <n-form label-placement="left" label-width="80">
        <n-form-item label="配件">{{ detailPartialItem?.part_name }}</n-form-item>
        <n-form-item label="发出数量">{{ detailPartialItem?.qty }}</n-form-item>
        <n-form-item label="已收回">{{ detailPartialItem?.received_qty }}</n-form-item>
        <n-form-item label="未收回">{{ detailPartialRemaining }}</n-form-item>
        <n-form-item label="回收数量">
          <n-input-number
            v-model:value="detailPartialQty"
            :min="0.0001"
            :max="detailPartialRemaining"
            :precision="4"
            style="width: 100%;"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="detailPartialReceiveVisible = false">取消</n-button>
          <n-button type="primary" :loading="itemReceiving" @click="doDetailPartialReceive">确定</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, h, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NTag, NEmpty, NModal, NForm, NFormItem,
  NSelect, NInputNumber, NInput, NPopselect, NTooltip, NIcon, NImage,
} from 'naive-ui'
import { CreateOutline } from '@vicons/ionicons5'
import {
  getPlating, getPlatingItems, sendPlating, receivePlating,
  addPlatingItem, updatePlatingItem, deletePlatingItem,
  updatePlatingDeliveryImages, downloadPlatingExcel, downloadPlatingPdf,
} from '@/api/plating'
import { changeOrderStatus } from '@/api/kanban'
import { listParts } from '@/api/parts'
import { renderNamedImage, renderOptionWithImage } from '@/utils/ui'
import ImageUploadModal from '@/components/ImageUploadModal.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()

const loading = ref(true)
const sending = ref(false)
const downloadingExcel = ref(false)
const downloadingPdf = ref(false)
const order = ref(null)
const items = ref([])
const partMap = ref({})
const partOptions = ref([])
const allParts = ref([])
const showDeliveryImageModal = ref(false)
const deliveryImagesSaving = ref(false)
const pendingDeliveryImages = ref([])
const retryingPendingImage = ref('')

// Receive state
const bulkReceiving = ref(false)
const itemReceiving = ref(false)
const detailPartialReceiveVisible = ref(false)
const detailPartialItem = ref(null)
const detailPartialQty = ref(0)
const detailPartialRemaining = ref(0)

const statusType = { pending: 'default', processing: 'info', completed: 'success' }
const statusLabel = { pending: '待发出', processing: '进行中', completed: '已完成' }
const deliveryImages = computed(() => order.value?.delivery_images || [])
const totalDeliveryImageCount = computed(() => deliveryImages.value.length + pendingDeliveryImages.value.length)
const canAddDeliveryImage = computed(() => totalDeliveryImageCount.value < 4)
const statusOptions = computed(() => {
  if (!order.value) return []
  const s = order.value.status
  if (s === 'pending') return [{ label: '进行中', value: 'processing' }]
  if (s === 'processing') return [
    { label: '待发出', value: 'pending' },
    { label: '已完成', value: 'completed' },
  ]
  if (s === 'completed') return [{ label: '进行中', value: 'processing' }]
  return []
})
const fmt = (dt) => new Date(dt).toLocaleString('zh-CN')

const platingMethodOptions = [
  { label: '金', value: '金' },
  { label: '白K', value: '白K' },
  { label: '玫瑰金', value: '玫瑰金' },
]

const COLOR_TO_METHOD = { '金色': '金', '白K': '白K', '玫瑰金': '玫瑰金' }

const unitOptions = [
  { label: '个', value: '个' },
  { label: '条', value: '条' },
  { label: '米', value: '米' },
  { label: 'g', value: 'g' },
  { label: 'kg', value: 'kg' },
]

const COLOR_BADGE_MAP = { '金色': 'G', '白K': 'S', '玫瑰金': 'RG' }
const COLOR_BADGE_STYLE = { 'G': '#DAA520', 'S': '#C0C0C0', 'RG': '#B76E79' }

const getReceivePartOptions = (sendPartId) => {
  if (!sendPartId) return partOptions.value
  const sendPart = allParts.value.find((p) => p.id === sendPartId)
  if (!sendPart) return partOptions.value
  const rootId = sendPart.parent_part_id || sendPart.id
  const variantIds = new Set(
    allParts.value
      .filter((p) => p.id === rootId || p.parent_part_id === rootId)
      .map((p) => p.id)
  )
  if (variantIds.size <= 1) return []
  return partOptions.value
    .filter((opt) => variantIds.has(opt.value))
    .map((opt) => {
      const part = allParts.value.find((p) => p.id === opt.value)
      const badge = part?.color ? COLOR_BADGE_MAP[part.color] : null
      if (!badge) return opt
      return { ...opt, badge, badgeColor: COLOR_BADGE_STYLE[badge] || '#999' }
    })
}

// Inline editing
const inlineEditing = ref({}) // key: `${row.id}_${field}`, value: current editing value
const inlineSaving = ref({})

const inlineKey = (rowId, field) => `${rowId}_${field}`

const startInline = (row, field) => {
  if (!isPending()) return
  inlineEditing.value[inlineKey(row.id, field)] = row[field] ?? null
}

const cancelInline = (rowId, field) => {
  delete inlineEditing.value[inlineKey(rowId, field)]
}

const saveInline = async (row, field, value) => {
  const key = inlineKey(row.id, field)
  if (inlineSaving.value[key]) return
  const oldValue = row[field] ?? null
  if (value === oldValue) { cancelInline(row.id, field); return }
  inlineSaving.value[key] = true
  try {
    const body = { [field]: value }
    // Changing part_id invalidates receive_part_id — clear it
    if (field === 'part_id') {
      body.receive_part_id = null
    }
    // Auto-fill plating_method when changing receive_part_id
    if (field === 'receive_part_id' && value) {
      const part = allParts.value.find((p) => p.id === value)
      if (part?.color && COLOR_TO_METHOD[part.color]) {
        body.plating_method = COLOR_TO_METHOD[part.color]
      }
    }
    await updatePlatingItem(route.params.id, row.id, body)
    await loadData()
    message.success('已保存')
  } catch (e) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    delete inlineSaving.value[key]
    cancelInline(row.id, field)
  }
}

const renderInlineSelect = (row, field, options, { renderLabel, placeholder } = {}) => {
  const key = inlineKey(row.id, field)
  const isEditing = key in inlineEditing.value
  if (!isEditing) return null // caller handles display
  return h(NSelect, {
    value: inlineEditing.value[key],
    options,
    filterable: true,
    clearable: field === 'receive_part_id',
    placeholder: placeholder || '请选择',
    size: 'small',
    style: 'min-width: 140px;',
    defaultExpanded: true,
    renderLabel: renderLabel || undefined,
    'onUpdate:value': (v) => { saveInline(row, field, v) },
    onBlur: () => { cancelInline(row.id, field) },
  })
}

// Add Item Modal
const addModalVisible = ref(false)
const addSubmitting = ref(false)
const addForm = ref({ part_id: null, receive_part_id: null, qty: 1, unit: '个', plating_method: '金', note: '' })

const editingNoteItemId = ref(null)
const editingNoteValue = ref('')
const savingNoteItemId = ref(null)
const noteInputRef = ref(null)

const loadData = async () => {
  const id = route.params.id
  const [oRes, iRes] = await Promise.all([getPlating(id), getPlatingItems(id)])
  order.value = oRes.data
  items.value = iRes.data.map((i) => ({
    ...i,
    part_name: partMap.value[i.part_id]?.name || i.part_id,
    part_image: partMap.value[i.part_id]?.image || '',
    receive_part_name: i.receive_part_id ? (partMap.value[i.receive_part_id]?.name || i.receive_part_id) : null,
  }))
  pendingDeliveryImages.value = pendingDeliveryImages.value.filter((image) => !order.value.delivery_images.includes(image))
  if (!isPending()) {
    stopEditNote()
  }
}

const doSend = async () => {
  sending.value = true
  try {
    await sendPlating(route.params.id)
    message.success('已确认发出')
    await loadData()
  } finally {
    sending.value = false
  }
}

const doBulkReceive = () => {
  dialog.warning({
    title: '确认整单回收',
    content: '确认将该电镀单所有未收回配件全部回收？',
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      bulkReceiving.value = true
      try {
        const receipts = items.value
          .filter((item) => item.received_qty < item.qty)
          .map((item) => ({ plating_order_item_id: item.id, qty: item.qty - item.received_qty }))
        if (receipts.length === 0) {
          message.warning('没有需要回收的明细')
          return
        }
        await receivePlating(route.params.id, receipts)
        message.success('回收成功')
        await loadData()
      } finally {
        bulkReceiving.value = false
      }
    },
  })
}

const doFullReceiveRow = async (row) => {
  itemReceiving.value = true
  try {
    const remaining = row.qty - row.received_qty
    await receivePlating(route.params.id, [{ plating_order_item_id: row.id, qty: remaining }])
    message.success('回收成功')
    await loadData()
  } finally {
    itemReceiving.value = false
  }
}

const openDetailPartialReceive = (row) => {
  detailPartialItem.value = row
  detailPartialRemaining.value = row.qty - row.received_qty
  detailPartialQty.value = null
  detailPartialReceiveVisible.value = true
}

const doDetailPartialReceive = async () => {
  if (!detailPartialItem.value || !detailPartialQty.value) return
  itemReceiving.value = true
  try {
    await receivePlating(route.params.id, [
      { plating_order_item_id: detailPartialItem.value.id, qty: detailPartialQty.value },
    ])
    message.success('回收成功')
    detailPartialReceiveVisible.value = false
    await loadData()
  } finally {
    itemReceiving.value = false
  }
}

const doDownloadExcel = async () => {
  await downloadExportFile('xlsx', downloadingExcel, downloadPlatingExcel, 'Excel 下载失败')
}

const doDownloadPdf = async () => {
  await downloadExportFile('pdf', downloadingPdf, downloadPlatingPdf, 'PDF 下载失败')
}

const downloadExportFile = async (extension, loadingRef, request, errorText) => {
  if (!order.value) return
  loadingRef.value = true
  try {
    const { data, headers } = await request(order.value.id)
    const url = window.URL.createObjectURL(data)
    const link = document.createElement('a')
    link.href = url
    link.download = buildExportFilename(order.value, extension)
      || extractDownloadFilename(headers?.['content-disposition'])
      || `发出_${order.value.id}.${extension}`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (_) {
    message.error(errorText)
  } finally {
    loadingRef.value = false
  }
}

const extractDownloadFilename = (contentDisposition) => {
  if (!contentDisposition) return ''
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch {
      return utf8Match[1]
    }
  }
  const plainMatch = contentDisposition.match(/filename=\"?([^\";]+)\"?/i)
  return plainMatch?.[1] || ''
}

const buildExportFilename = (currentOrder, extension) => {
  if (!currentOrder) return ''
  const supplierName = sanitizeFilenamePart(currentOrder.supplier_name) || '未命名电镀厂'
  const shortDate = formatShortDate(currentOrder.created_at)
  return `发出_${supplierName}_${shortDate}.${extension}`
}

const sanitizeFilenamePart = (value) => {
  if (!value) return ''
  return String(value)
    .replace(/[\\/:*?"<>|]+/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[. ]+$/g, '')
}

const formatShortDate = (value) => {
  if (!value) return '000000'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '000000'
  const year = String(date.getFullYear() % 100).padStart(2, '0')
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}${month}${day}`
}

const doChangeStatus = (newStatus) => {
  const currentLabel = statusLabel[order.value?.status] || order.value?.status
  const newLabel = statusLabel[newStatus] || newStatus
  dialog.warning({
    title: '确认状态变更',
    content: `请确认将「${order.value?.supplier_name}」的订单「${order.value?.id}」状态从「${currentLabel}」转为「${newLabel}」`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      const loadingMsg = message.loading('正在更新状态...', { duration: 0 })
      try {
        await changeOrderStatus({ order_id: order.value.id, order_type: 'plating', new_status: newStatus })
        loadingMsg.destroy()
        message.success(`状态已更新为${newLabel}`)
        await loadData()
      } catch (_) {
        loadingMsg.destroy()
        // errors shown by axios interceptor
        await loadData()
      }
    },
  })
}

const openAddModal = () => {
  addForm.value = { part_id: null, receive_part_id: null, qty: 1, unit: '个', plating_method: '金', note: '' }
  addModalVisible.value = true
}

const autoFillMethod = (receivePartId, form) => {
  if (!receivePartId) return
  const part = allParts.value.find((p) => p.id === receivePartId)
  if (part?.color && COLOR_TO_METHOD[part.color]) {
    form.plating_method = COLOR_TO_METHOD[part.color]
  }
}

const onAddPartSelect = (val) => {
  const found = partOptions.value.find((p) => p.value === val)
  if (found && found.unit) {
    addForm.value.unit = found.unit
  } else {
    addForm.value.unit = '个'
  }
  addForm.value.receive_part_id = null
}

const doAddItem = async () => {
  if (!addForm.value.part_id) { message.warning('请选择配件'); return }
  if (!addForm.value.qty || addForm.value.qty < 1) { message.warning('数量不能小于 1'); return }
  addSubmitting.value = true
  try {
    await addPlatingItem(route.params.id, addForm.value)
    message.success('明细已添加')
    addModalVisible.value = false
    await loadData()
  } finally {
    addSubmitting.value = false
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
        await deletePlatingItem(route.params.id, row.id)
        message.success('已删除')
        await loadData()
      } catch (_) {
        // error shown by axios interceptor
      }
    },
  })
}

const isPending = () => order.value?.status === 'pending'
const normalizeNote = (value) => (value || '').trim()
const mergeDeliveryImages = (...groups) => [...new Set(groups.flat().filter(Boolean))]

const persistDeliveryImages = async (nextImages, successText) => {
  if (!order.value) return
  deliveryImagesSaving.value = true
  try {
    const { data } = await updatePlatingDeliveryImages(order.value.id, nextImages)
    order.value = data
    pendingDeliveryImages.value = pendingDeliveryImages.value.filter((image) => !data.delivery_images.includes(image))
    message.success(successText)
    return data
  } finally {
    deliveryImagesSaving.value = false
  }
}

const openDeliveryImageModal = () => {
  if (!canAddDeliveryImage.value) {
    message.warning('发货图片最多上传 4 张')
    return
  }
  showDeliveryImageModal.value = true
}

const handleDeliveryImageUploaded = async (url) => {
  if (!url) return
  if (!canAddDeliveryImage.value) {
    message.warning('发货图片最多上传 4 张')
    return
  }
  try {
    await persistDeliveryImages(mergeDeliveryImages(deliveryImages.value, [url]), '发货图片已上传')
  } catch (_) {
    if (!pendingDeliveryImages.value.includes(url)) {
      pendingDeliveryImages.value.push(url)
    }
    message.warning('图片已上传，但写入电镀单失败，可点击“重试保存”继续')
  }
}

const removeDeliveryImage = (index) => {
  if (!order.value) return
  dialog.warning({
    title: '确认删除图片',
    content: '删除后不可恢复，确认继续吗？',
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      const nextImages = deliveryImages.value.filter((_, currentIndex) => currentIndex !== index)
      await persistDeliveryImages(nextImages, '发货图片已删除')
    },
  })
}

const retryPendingDeliveryImage = async (image) => {
  if (!pendingDeliveryImages.value.includes(image)) return
  retryingPendingImage.value = image
  try {
    await persistDeliveryImages(
      mergeDeliveryImages(deliveryImages.value, pendingDeliveryImages.value),
      '待保存图片已写入电镀单',
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

const focusEditingNoteInput = () => {
  nextTick(() => {
    noteInputRef.value?.focus?.()
  })
}

const startEditNote = (row) => {
  if (!isPending()) return
  editingNoteItemId.value = row.id
  editingNoteValue.value = row.note || ''
  focusEditingNoteInput()
}

const stopEditNote = (itemId = null) => {
  if (itemId !== null && editingNoteItemId.value !== itemId) return
  editingNoteItemId.value = null
  editingNoteValue.value = ''
}

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
    const { data } = await updatePlatingItem(route.params.id, itemId, { note: nextNote })
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
    if (!isPending()) {
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
        isPending() ? 'cursor: pointer; color: #2080f0;' : '',
      ].join('; '),
      onClick: isPending() ? () => startEditNote(row) : undefined,
    },
    noteText,
  )
}

const itemColumns = [
  { title: '配件编号', key: 'part_id', width: 110 },
  {
    title: '发出配件',
    key: 'part_name',
    minWidth: 180,
    render: (row) => {
      const key = inlineKey(row.id, 'part_id')
      if (key in inlineEditing.value) {
        return renderInlineSelect(row, 'part_id', partOptions.value, { renderLabel: renderOptionWithImage, placeholder: '选择发出配件' })
      }
      const content = renderNamedImage(row.part_name, row.part_image, row.part_name)
      if (!isPending()) return content
      return h('div', { style: 'cursor: pointer;', onClick: () => startInline(row, 'part_id') }, [content])
    },
  },
  {
    title: '收回配件',
    key: 'receive_part_name',
    minWidth: 140,
    render: (row) => {
      const key = inlineKey(row.id, 'receive_part_id')
      if (key in inlineEditing.value) {
        return renderInlineSelect(row, 'receive_part_id', getReceivePartOptions(row.part_id), { renderLabel: renderOptionWithImage, placeholder: '默认同发出配件' })
      }
      let content
      if (!row.receive_part_name) {
        content = h('span', { style: 'color: #999;' }, '同发出配件')
      } else {
        const receivePart = allParts.value.find((p) => p.id === row.receive_part_id)
        const badge = receivePart?.color ? COLOR_BADGE_MAP[receivePart.color] : null
        if (!badge) {
          content = h('span', null, row.receive_part_name)
        } else {
          const badgeColor = COLOR_BADGE_STYLE[badge] || '#999'
          content = h('span', [
            row.receive_part_name,
            h('span', {
              style: `margin-left: 4px; font-size: 11px; font-weight: bold; color: #fff; background: ${badgeColor}; padding: 1px 5px; border-radius: 4px;`,
            }, badge),
          ])
        }
      }
      if (!isPending()) return content
      return h('div', { style: 'cursor: pointer;', onClick: () => startInline(row, 'receive_part_id') }, [content])
    },
  },
  {
    title: '发出数量',
    key: 'qty',
    width: 100,
    render: (row) => {
      const key = inlineKey(row.id, 'qty')
      if (key in inlineEditing.value) {
        return h(NInputNumber, {
          value: inlineEditing.value[key],
          min: 1,
          precision: 0,
          step: 1,
          size: 'small',
          style: 'width: 90px;',
          autofocus: true,
          'onUpdate:value': (v) => { inlineEditing.value[key] = v },
          onBlur: () => { saveInline(row, 'qty', inlineEditing.value[key]) },
          onKeydown: (e) => { if (e.key === 'Enter') saveInline(row, 'qty', inlineEditing.value[key]); if (e.key === 'Escape') cancelInline(row.id, 'qty') },
        })
      }
      if (!isPending()) return row.qty
      return h('span', { style: 'cursor: pointer; color: #2080f0;', onClick: () => startInline(row, 'qty') }, row.qty)
    },
  },
  { title: '已收回', key: 'received_qty', render: (r) => r.received_qty ?? 0 },
  {
    title: '未收回',
    key: 'remaining',
    render: (r) => r.qty - (r.received_qty ?? 0),
  },
  {
    title: '单位',
    key: 'unit',
    width: 80,
    render: (row) => {
      const key = inlineKey(row.id, 'unit')
      if (key in inlineEditing.value) {
        return renderInlineSelect(row, 'unit', unitOptions)
      }
      const text = row.unit || '-'
      if (!isPending()) return text
      return h('span', { style: 'cursor: pointer; color: #2080f0;', onClick: () => startInline(row, 'unit') }, text)
    },
  },
  {
    title: '电镀方式',
    key: 'plating_method',
    width: 100,
    render: (row) => {
      const key = inlineKey(row.id, 'plating_method')
      if (key in inlineEditing.value) {
        return renderInlineSelect(row, 'plating_method', platingMethodOptions)
      }
      const text = row.plating_method || '-'
      if (!isPending()) return text
      return h('span', { style: 'cursor: pointer; color: #2080f0;', onClick: () => startInline(row, 'plating_method') }, text)
    },
  },
  {
    title: '状态',
    key: 'item_status',
    render: (r) => h('span', r.status),
  },
  {
    title: '备注',
    key: 'note',
    minWidth: 240,
    render: (row) => renderNoteCell(row),
  },
  {
    title: '操作',
    key: 'actions',
    width: 200,
    render: (row) => {
      const pending = isPending()
      const isProcessing = order.value?.status === 'processing'
      const canReceive = isProcessing && row.status === '电镀中' && row.received_qty < row.qty
      const btns = []

      if (pending) {
        btns.push(h(NButton, {
          size: 'small',
          type: 'error',
          onClick: () => doDeleteItem(row),
        }, { default: () => '删除' }))
      }

      if (canReceive) {
        btns.push(h(NButton, {
          size: 'small',
          type: 'primary',
          loading: itemReceiving.value,
          onClick: () => doFullReceiveRow(row),
        }, { default: () => '全部回收' }))
        btns.push(h(NButton, {
          size: 'small',
          onClick: () => openDetailPartialReceive(row),
        }, { default: () => '部分回收' }))
      }

      if (!pending && !canReceive) {
        btns.push(h(
          NTooltip,
          { trigger: 'hover' },
          {
            trigger: () =>
              h(NButton, {
                size: 'small',
                type: 'error',
                disabled: true,
              }, { default: () => '删除' }),
            default: () => '当前单子进行中/已完成，不允许删除',
          },
        ))
      }

      return h(NSpace, { size: 'small' }, { default: () => btns })
    },
  },
]

onMounted(async () => {
  try {
    const { data: parts } = await listParts()
    allParts.value = parts
    parts.forEach((p) => { partMap.value[p.id] = p })
    partOptions.value = parts.map((p) => ({
      label: `${p.id} ${p.name}`,
      value: p.id,
      code: p.id,
      name: p.name,
      image: p.image,
      unit: p.unit,
    }))
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

.export-excel-btn {
  background: #469c66;
  color: #fff;
  border-color: #469c66;
}

.export-excel-btn:hover,
.export-excel-btn:focus {
  background: #3d8959;
  color: #fff;
  border-color: #3d8959;
}

.export-pdf-btn {
  background: #d84243;
  color: #fff;
  border-color: #d84243;
}

.export-pdf-btn:hover,
.export-pdf-btn:focus {
  background: #bf3a3b;
  color: #fff;
  border-color: #bf3a3b;
}
</style>
