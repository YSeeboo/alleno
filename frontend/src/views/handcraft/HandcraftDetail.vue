<template>
  <div>
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">手工单详情</n-h2>
    </n-space>

    <n-spin :show="loading">
      <n-card v-if="order" title="基本信息" style="margin-bottom: 16px;">
        <template #header-extra>
          <n-space size="small">
            <n-button
              @click="router.push(`/handcraft-receipts?supplier_name=${encodeURIComponent(order.supplier_name)}`)"
            >
              查看回收单
            </n-button>
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
          <n-descriptions-item label="手工单号">{{ order.id }}</n-descriptions-item>
          <n-descriptions-item label="手工商家">{{ order.supplier_name }}</n-descriptions-item>
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
                  有 {{ pendingDeliveryImages.length }} 张图片已上传，但还没保存到手工单
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
        </n-space>
      </n-card>

      <n-card title="配件明细" style="margin-bottom: 16px;">
        <template #header-extra>
          <n-button
            v-if="items.length > 0"
            size="small"
            @click="openBatchLinkModal"
          >
            批量关联订单
          </n-button>
        </template>
        <n-data-table v-if="items.length > 0" :columns="itemColumns" :data="items" :bordered="false" />
        <n-empty v-else description="暂无明细" style="margin-top: 16px;" />
        <div v-if="order?.status === 'pending'" style="margin-top: 12px;">
          <n-button dashed style="width: 100%;" @click="openAddModal">+ 添加明细行</n-button>
        </div>
      </n-card>

      <n-card v-if="jewelryItems.length > 0" title="饰品明细">
        <n-data-table :columns="jewelryColumns" :data="jewelryItems" :bordered="false" />
      </n-card>
    </n-spin>

    <n-modal v-model:show="addModalVisible" preset="card" title="添加配件明细" style="width: 500px;">
      <form @submit.prevent="doAddItem">
      <n-form label-placement="left" label-width="90">
        <n-form-item label="配件">
          <n-select
            v-model:value="addForm.part_id"
            :options="partOptions"
            :render-label="renderOptionWithImage"
            filterable
            placeholder="选择配件"
            @update:value="onAddPartSelect"
          />
        </n-form-item>
        <n-form-item label="数量">
          <n-input-number v-model:value="addForm.qty" :min="1" :precision="0" :step="1" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="addForm.unit" :options="unitOptions" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="addForm.note" placeholder="备注（可选）" />
        </n-form-item>
      </n-form>
      </form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="addModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="addSubmitting" @click="doAddItem">确认添加</n-button>
        </n-space>
      </template>
    </n-modal>

    <n-modal v-model:show="editModalVisible" preset="card" title="修改配件明细" style="width: 500px;">
      <form @submit.prevent="doEditItem">
      <n-form label-placement="left" label-width="90">
        <n-form-item label="数量">
          <n-input-number v-model:value="editForm.qty" :min="1" :precision="0" :step="1" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="editForm.unit" :options="unitOptions" />
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
      kind="handcraft"
      :entity-id="order?.id"
      suppress-success
      @uploaded="handleDeliveryImageUploaded"
    />

    <!-- Single Link Modal for part items -->
    <n-modal v-model:show="linkModalVisible" preset="card" title="关联订单" style="width: 600px;">
      <n-form label-placement="left" label-width="80">
        <n-form-item label="选择订单">
          <n-select
            v-model:value="linkForm.orderId"
            :options="orderOptions"
            filterable
            placeholder="搜索订单号或客户名"
            @update:value="onLinkOrderSelect"
          />
        </n-form-item>
        <n-form-item v-if="linkTodoItems.length > 0" label="匹配配件">
          <n-radio-group v-model:value="linkForm.todoItemId">
            <n-space vertical>
              <n-radio v-for="t in linkTodoItems" :key="t.id" :value="t.id">
                {{ t.part_name || t.part_id }} — 需要 {{ t.required_qty }}
              </n-radio>
            </n-space>
          </n-radio-group>
        </n-form-item>
        <div v-if="linkForm.orderId && linkTodoItems.length === 0 && !linkTodoLoading" style="color: #999; padding: 8px 0;">
          该订单配件清单中没有匹配的配件
        </div>
        <n-spin v-if="linkTodoLoading" size="small" />
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="linkModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="linkSubmitting" :disabled="!linkForm.todoItemId" @click="doCreatePartLink">确认关联</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Jewelry Link Modal: just select order -->
    <n-modal v-model:show="jewelryLinkModalVisible" preset="card" title="关联订单（饰品）" style="width: 500px;">
      <n-form label-placement="left" label-width="80">
        <n-form-item label="选择订单">
          <n-select
            v-model:value="jewelryLinkOrderId"
            :options="orderOptions"
            filterable
            placeholder="搜索订单号或客户名"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="jewelryLinkModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="jewelryLinkSubmitting" :disabled="!jewelryLinkOrderId" @click="doCreateJewelryLink">确认关联</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Batch Link Modal -->
    <n-modal v-model:show="batchLinkModalVisible" preset="card" title="批量关联订单" style="width: 500px;">
      <n-form label-placement="left" label-width="80">
        <n-form-item label="选择订单">
          <n-select
            v-model:value="batchLinkOrderId"
            :options="orderOptions"
            filterable
            placeholder="搜索订单号或客户名"
          />
        </n-form-item>
        <div style="color: #666; font-size: 13px; padding: 4px 0;">
          将自动按配件编号匹配该订单配件清单中的行
        </div>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="batchLinkModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="batchLinkSubmitting" :disabled="!batchLinkOrderId" @click="doBatchLink">确认批量关联</n-button>
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
  NRadioGroup, NRadio,
} from 'naive-ui'
import { CreateOutline } from '@vicons/ionicons5'
import {
  getHandcraft, getHandcraftParts, getHandcraftJewelries, sendHandcraft,
  addHandcraftPart, updateHandcraftPart, deleteHandcraftPart,
  updateHandcraftDeliveryImages, downloadHandcraftExcel, downloadHandcraftPdf,
  getHandcraftPartOrders, deleteHandcraftPartOrderLink,
  getHandcraftJewelryOrders, deleteHandcraftJewelryOrderLink,
} from '@/api/handcraft'
import { changeOrderStatus } from '@/api/kanban'
import { listParts, updatePart } from '@/api/parts'
import { listJewelries } from '@/api/jewelries'
import { listOrders, getTodo, createLink, batchLink } from '@/api/orders'
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
const showDeliveryImageModal = ref(false)
const deliveryImagesSaving = ref(false)
const pendingDeliveryImages = ref([])
const retryingPendingImage = ref('')

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

const unitOptions = [
  { label: '个', value: '个' },
  { label: '条', value: '条' },
  { label: '米', value: '米' },
  { label: 'g', value: 'g' },
  { label: 'kg', value: 'kg' },
]

const addModalVisible = ref(false)
const addSubmitting = ref(false)
const addForm = ref({ part_id: null, qty: 1, unit: '个', note: '' })

const editModalVisible = ref(false)
const editSubmitting = ref(false)
const editForm = ref({ id: null, qty: 1, unit: '个' })
const editingCellKey = ref('')
const editingCellValue = ref('')
const savingCellKey = ref('')
const cellInputRef = ref(null)

const loadParts = async () => {
  const { data: parts } = await listParts()
  partMap.value = Object.fromEntries(parts.map((part) => [part.id, part]))
  partOptions.value = parts.map((p) => ({
    label: `${p.id} ${p.name}`,
    value: p.id,
    code: p.id,
    name: p.name,
    image: p.image,
    unit: p.unit,
  }))
}

const loadData = async () => {
  const id = route.params.id
  const results = await Promise.all([loadParts(), getHandcraft(id), getHandcraftParts(id)])
  const oRes = results[1]
  const iRes = results[2]
  order.value = oRes.data
  items.value = iRes.data.map((i) => ({
    ...i,
    part_name: partMap.value[i.part_id]?.name || i.part_id,
    part_image: partMap.value[i.part_id]?.image || '',
    color: partMap.value[i.part_id]?.color || '',
  }))
  pendingDeliveryImages.value = pendingDeliveryImages.value.filter((image) => !order.value.delivery_images.includes(image))
  if (!isPending()) {
    stopEditingCell()
  }
}

const doSend = async () => {
  sending.value = true
  try {
    await sendHandcraft(route.params.id)
    message.success('已确认发出')
    await loadData()
  } finally {
    sending.value = false
  }
}

const doDownloadExcel = async () => {
  await downloadExportFile('xlsx', downloadingExcel, downloadHandcraftExcel, 'Excel 下载失败')
}

const doDownloadPdf = async () => {
  await downloadExportFile('pdf', downloadingPdf, downloadHandcraftPdf, 'PDF 下载失败')
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
  const supplierName = sanitizeFilenamePart(currentOrder.supplier_name) || '未命名手工厂'
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
        await changeOrderStatus({ order_id: order.value.id, order_type: 'handcraft', new_status: newStatus })
        loadingMsg.destroy()
        message.success(`状态已更新为${newLabel}`)
        await loadData()
      } catch (_) {
        loadingMsg.destroy()
        await loadData()
      }
    },
  })
}

const openAddModal = () => {
  addForm.value = { part_id: null, qty: 1, unit: '个', note: '' }
  addModalVisible.value = true
}

const onAddPartSelect = (val) => {
  const found = partOptions.value.find((p) => p.value === val)
  if (found && found.unit) {
    addForm.value.unit = found.unit
  } else {
    addForm.value.unit = '个'
  }
}

const doAddItem = async () => {
  if (!addForm.value.part_id) { message.warning('请选择配件'); return }
  if (!addForm.value.qty || addForm.value.qty < 1) { message.warning('数量不能小于 1'); return }
  addSubmitting.value = true
  try {
    await addHandcraftPart(route.params.id, addForm.value)
    message.success('明细已添加')
    addModalVisible.value = false
    await loadData()
  } finally {
    addSubmitting.value = false
  }
}

const openEditModal = (row) => {
  editForm.value = {
    id: row.id,
    qty: row.qty,
    unit: row.unit || '个',
  }
  editModalVisible.value = true
}

const doEditItem = async () => {
  editSubmitting.value = true
  try {
    const { id, ...body } = editForm.value
    await updateHandcraftPart(route.params.id, id, body)
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
    content: `确认删除配件 ${row.part_name || row.part_id} 的明细行？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteHandcraftPart(route.params.id, row.id)
        message.success('已删除')
        await loadData()
      } catch (_) {
      }
    },
  })
}

const isPending = () => order.value?.status === 'pending'
const normalizeEditableValue = (value) => (value || '').trim()
const mergeDeliveryImages = (...groups) => [...new Set(groups.flat().filter(Boolean))]

const persistDeliveryImages = async (nextImages, successText) => {
  if (!order.value) return
  deliveryImagesSaving.value = true
  try {
    const { data } = await updateHandcraftDeliveryImages(order.value.id, nextImages)
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
    message.warning('图片已上传，但写入手工单失败，可点击“重试保存”继续')
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
      '待保存图片已写入手工单',
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

const cellKeyOf = (field, row) => `${field}:${row.id}`

const focusEditingCellInput = () => {
  nextTick(() => {
    cellInputRef.value?.focus?.()
  })
}

const startEditCell = (field, row) => {
  if (!isPending()) return
  editingCellKey.value = cellKeyOf(field, row)
  editingCellValue.value = row[field] || ''
  focusEditingCellInput()
}

const stopEditingCell = (field = null, row = null) => {
  if (field && row && editingCellKey.value !== cellKeyOf(field, row)) return
  editingCellKey.value = ''
  editingCellValue.value = ''
}

const saveCell = async (field, row) => {
  const currentCellKey = cellKeyOf(field, row)
  if (editingCellKey.value !== currentCellKey || savingCellKey.value === currentCellKey) return

  const nextValue = normalizeEditableValue(editingCellValue.value)
  const currentValue = normalizeEditableValue(row[field])
  if (nextValue === currentValue) {
    stopEditingCell(field, row)
    return
  }

  savingCellKey.value = currentCellKey
  try {
    if (field === 'color') {
      const { data } = await updatePart(row.part_id, { color: nextValue || null })
      partMap.value = {
        ...partMap.value,
        [row.part_id]: data,
      }
      items.value.forEach((item) => {
        if (item.part_id === row.part_id) {
          item.color = data.color || ''
        }
      })
    } else {
      const { data } = await updateHandcraftPart(route.params.id, row.id, { [field]: nextValue })
      row[field] = data[field] || ''
    }
    message.success(nextValue ? `${field === 'color' ? '颜色' : '备注'}已保存` : `${field === 'color' ? '颜色' : '备注'}已清空`)
    stopEditingCell(field, row)
  } finally {
    if (savingCellKey.value === currentCellKey) {
      savingCellKey.value = ''
    }
  }
}

const onCellInputKeydown = (event, field, row) => {
  if (event.key !== 'Enter') return
  if (event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  void saveCell(field, row)
}

const renderEditableCell = (field, row, emptyLabel) => {
  const currentCellKey = cellKeyOf(field, row)
  const isEditing = editingCellKey.value === currentCellKey
  const isSaving = savingCellKey.value === currentCellKey
  const text = row[field] || ''

  if (isEditing) {
    return h(NInput, {
      ref: cellInputRef,
      value: editingCellValue.value,
      size: 'small',
      placeholder: '输入内容后按回车或点击空白处保存',
      disabled: isSaving,
      autofocus: true,
      'onUpdate:value': (value) => { editingCellValue.value = value },
      onBlur: () => { void saveCell(field, row) },
      onKeydown: (event) => onCellInputKeydown(event, field, row),
    })
  }

  if (!text) {
    if (!isPending()) {
      return h('span', { style: 'color: #999;' }, '-')
    }
    return h(
      NButton,
      {
        text: true,
        type: 'primary',
        size: 'small',
        onClick: () => startEditCell(field, row),
      },
      {
        icon: () => h(NIcon, null, { default: () => h(CreateOutline) }),
        default: () => emptyLabel,
      },
    )
  }

  return h(
    'span',
    {
      title: text,
      style: [
        'display: inline-block',
        'max-width: 220px',
        'overflow: hidden',
        'text-overflow: ellipsis',
        'white-space: nowrap',
        'vertical-align: bottom',
        isPending() ? 'cursor: pointer; color: #2080f0;' : '',
      ].join('; '),
      onClick: isPending() ? () => startEditCell(field, row) : undefined,
    },
    text,
  )
}

// --- Jewelry items ---
const jewelryItems = ref([])
const jewelryMap = ref({})

const loadJewelries = async () => {
  try {
    const { data } = await getHandcraftJewelries(route.params.id)
    jewelryItems.value = data.map((j) => ({
      ...j,
      jewelry_name: jewelryMap.value[j.jewelry_id]?.name || j.jewelry_id,
      jewelry_image: jewelryMap.value[j.jewelry_id]?.image || '',
    }))
  } catch (_) {
    jewelryItems.value = []
  }
}

// --- Order Link (parts) ---
const orderOptions = ref([])
const partItemOrderLinks = ref({}) // itemId -> [{order_id, customer_name, link_id}]
const jewelryItemOrderLinks = ref({}) // itemId -> [{order_id, customer_name, link_id}]

const linkModalVisible = ref(false)
const linkForm = ref({ itemId: null, partId: null, orderId: null, todoItemId: null })
const linkTodoItems = ref([])
const linkTodoLoading = ref(false)
const linkSubmitting = ref(false)

const jewelryLinkModalVisible = ref(false)
const jewelryLinkItemId = ref(null)
const jewelryLinkOrderId = ref(null)
const jewelryLinkSubmitting = ref(false)

const batchLinkModalVisible = ref(false)
const batchLinkOrderId = ref(null)
const batchLinkSubmitting = ref(false)

const loadOrderOptions = async () => {
  try {
    const { data } = await listOrders()
    orderOptions.value = data.map((o) => ({
      label: `${o.id} — ${o.customer_name}`,
      value: o.id,
    }))
  } catch (_) {}
}

const loadPartItemOrderLinks = async () => {
  const map = {}
  await Promise.all(items.value.map(async (item) => {
    try {
      const { data } = await getHandcraftPartOrders(route.params.id, item.id)
      map[item.id] = data
    } catch (_) {
      map[item.id] = []
    }
  }))
  partItemOrderLinks.value = map
}

const loadJewelryItemOrderLinks = async () => {
  const map = {}
  await Promise.all(jewelryItems.value.map(async (item) => {
    try {
      const { data } = await getHandcraftJewelryOrders(route.params.id, item.id)
      map[item.id] = data
    } catch (_) {
      map[item.id] = []
    }
  }))
  jewelryItemOrderLinks.value = map
}

const openLinkModal = (row) => {
  linkForm.value = { itemId: row.id, partId: row.part_id, orderId: null, todoItemId: null }
  linkTodoItems.value = []
  linkModalVisible.value = true
  loadOrderOptions()
}

const onLinkOrderSelect = async (orderId) => {
  linkForm.value.todoItemId = null
  linkTodoItems.value = []
  if (!orderId) return
  linkTodoLoading.value = true
  try {
    const { data } = await getTodo(orderId)
    linkTodoItems.value = data.filter((t) => t.part_id === linkForm.value.partId)
    if (linkTodoItems.value.length === 1) {
      linkForm.value.todoItemId = linkTodoItems.value[0].id
    }
  } catch (_) {
    linkTodoItems.value = []
  } finally {
    linkTodoLoading.value = false
  }
}

const doCreatePartLink = async () => {
  if (!linkForm.value.todoItemId) return
  linkSubmitting.value = true
  try {
    await createLink(linkForm.value.orderId, {
      order_todo_item_id: linkForm.value.todoItemId,
      handcraft_part_item_id: linkForm.value.itemId,
    })
    message.success('关联成功')
    linkModalVisible.value = false
    await loadPartItemOrderLinks()
  } catch (e) {
    message.error(e.response?.data?.detail || '关联失败')
  } finally {
    linkSubmitting.value = false
  }
}

const openJewelryLinkModal = (row) => {
  jewelryLinkItemId.value = row.id
  jewelryLinkOrderId.value = null
  jewelryLinkModalVisible.value = true
  loadOrderOptions()
}

const doCreateJewelryLink = async () => {
  if (!jewelryLinkOrderId.value || !jewelryLinkItemId.value) return
  jewelryLinkSubmitting.value = true
  try {
    await createLink(jewelryLinkOrderId.value, {
      order_id: jewelryLinkOrderId.value,
      handcraft_jewelry_item_id: jewelryLinkItemId.value,
    })
    message.success('关联成功')
    jewelryLinkModalVisible.value = false
    await loadJewelryItemOrderLinks()
  } catch (e) {
    message.error(e.response?.data?.detail || '关联失败')
  } finally {
    jewelryLinkSubmitting.value = false
  }
}

const openBatchLinkModal = () => {
  batchLinkOrderId.value = null
  batchLinkModalVisible.value = true
  loadOrderOptions()
}

const doBatchLink = async () => {
  if (!batchLinkOrderId.value) return
  batchLinkSubmitting.value = true
  try {
    const allItemIds = items.value.map((i) => i.id)
    const { data } = await batchLink(batchLinkOrderId.value, {
      order_id: batchLinkOrderId.value,
      handcraft_part_item_ids: allItemIds,
    })
    const msg = [`成功关联 ${data.linked} 项`]
    if (data.skipped.length > 0) {
      msg.push(`跳过: ${data.skipped.join(', ')}`)
    }
    message.success(msg.join('，'))
    batchLinkModalVisible.value = false
    await loadPartItemOrderLinks()
  } catch (e) {
    message.error(e.response?.data?.detail || '批量关联失败')
  } finally {
    batchLinkSubmitting.value = false
  }
}

const doUnlinkPartItem = (itemId, link) => {
  dialog.warning({
    title: '解除关联',
    content: `确认解除与订单「${link.order_id}」的关联？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteHandcraftPartOrderLink(route.params.id, itemId, link.link_id)
        message.success('已解除关联')
        await loadPartItemOrderLinks()
      } catch (_) {}
    },
  })
}

const doUnlinkJewelryItem = (itemId, link) => {
  dialog.warning({
    title: '解除关联',
    content: `确认解除与订单「${link.order_id}」的关联？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteHandcraftJewelryOrderLink(route.params.id, itemId, link.link_id)
        message.success('已解除关联')
        await loadJewelryItemOrderLinks()
      } catch (_) {}
    },
  })
}

const renderPartOrderLinkCell = (row) => {
  const links = partItemOrderLinks.value[row.id] || []
  if (links.length === 0) {
    return h(NButton, {
      size: 'small', text: true, type: 'primary',
      onClick: () => openLinkModal(row),
    }, { default: () => '关联订单' })
  }
  return h('div', { style: 'display: flex; flex-wrap: wrap; gap: 4px; align-items: center;' }, [
    ...links.map((link) => h('span', {
      style: 'display: inline-flex; align-items: center; gap: 2px; background: #f0f9eb; border: 1px solid #c2e7b0; border-radius: 4px; padding: 1px 6px; font-size: 12px;',
    }, [
      h('span', null, link.order_id),
      h(NButton, {
        size: 'tiny', quaternary: true, type: 'error', style: 'padding: 0 2px;',
        onClick: () => doUnlinkPartItem(row.id, link),
      }, { default: () => '×' }),
    ])),
    h(NButton, { size: 'tiny', text: true, type: 'primary', onClick: () => openLinkModal(row) }, { default: () => '+' }),
  ])
}

const renderJewelryOrderLinkCell = (row) => {
  const links = jewelryItemOrderLinks.value[row.id] || []
  if (links.length === 0) {
    return h(NButton, {
      size: 'small', text: true, type: 'primary',
      onClick: () => openJewelryLinkModal(row),
    }, { default: () => '关联订单' })
  }
  return h('div', { style: 'display: flex; flex-wrap: wrap; gap: 4px; align-items: center;' }, [
    ...links.map((link) => h('span', {
      style: 'display: inline-flex; align-items: center; gap: 2px; background: #f0f9eb; border: 1px solid #c2e7b0; border-radius: 4px; padding: 1px 6px; font-size: 12px;',
    }, [
      h('span', null, link.order_id),
      h(NButton, {
        size: 'tiny', quaternary: true, type: 'error', style: 'padding: 0 2px;',
        onClick: () => doUnlinkJewelryItem(row.id, link),
      }, { default: () => '×' }),
    ])),
    h(NButton, { size: 'tiny', text: true, type: 'primary', onClick: () => openJewelryLinkModal(row) }, { default: () => '+' }),
  ])
}

const partStatusLabel = { '未送出': '未送出', '制作中': '制作中', '已收回': '已收回' }
const partStatusBadge = { '未送出': 'badge-gray', '制作中': 'badge-blue', '已收回': 'badge-green' }

const itemColumns = [
  { title: '配件编号', key: 'part_id', width: 110 },
  {
    title: '配件',
    key: 'part_name',
    minWidth: 180,
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name),
  },
  {
    title: '颜色',
    key: 'color',
    minWidth: 140,
    render: (row) => renderEditableCell('color', row, '添加颜色'),
  },
  { title: '发出数量', key: 'qty' },
  { title: '已回收', key: 'received_qty', width: 80, render: (r) => r.received_qty ?? 0 },
  {
    title: '状态',
    key: 'status',
    width: 80,
    render: (r) => h('span', { class: `badge ${partStatusBadge[r.status] || 'badge-gray'}` }, `• ${partStatusLabel[r.status] || r.status || '未送出'}`),
  },
  { title: '单位', key: 'unit', render: (r) => r.unit || '-' },
  {
    title: '备注',
    key: 'note',
    minWidth: 240,
    render: (row) => renderEditableCell('note', row, '添加备注'),
  },
  {
    title: '关联订单',
    key: 'order_link',
    minWidth: 140,
    render: (row) => renderPartOrderLinkCell(row),
  },
  {
    title: '操作',
    key: 'actions',
    width: 140,
    render: (row) => {
      const pending = isPending()
      const editBtn = h(
        NTooltip,
        { disabled: pending, trigger: 'hover' },
        {
          trigger: () =>
            h(
              NButton,
              {
                size: 'small',
                disabled: !pending,
                style: 'margin-right: 6px;',
                onClick: pending ? () => openEditModal(row) : undefined,
              },
              { default: () => '修改' },
            ),
          default: () => '当前单子进行中/已完成，不允许修改',
        },
      )
      const deleteBtn = h(
        NTooltip,
        { disabled: pending, trigger: 'hover' },
        {
          trigger: () =>
            h(
              NButton,
              {
                size: 'small',
                type: 'error',
                disabled: !pending,
                onClick: pending ? () => doDeleteItem(row) : undefined,
              },
              { default: () => '删除' },
            ),
          default: () => '当前单子进行中/已完成，不允许删除',
        },
      )
      return h(NSpace, { size: 'small' }, { default: () => [editBtn, deleteBtn] })
    },
  },
]

const jewelryColumns = [
  { title: '饰品编号', key: 'jewelry_id', width: 110 },
  {
    title: '饰品',
    key: 'jewelry_name',
    minWidth: 180,
    render: (row) => renderNamedImage(row.jewelry_name, row.jewelry_image, row.jewelry_name),
  },
  { title: '数量', key: 'qty' },
  { title: '已回收', key: 'received_qty', width: 80, render: (r) => r.received_qty ?? 0 },
  {
    title: '状态',
    key: 'status',
    width: 80,
    render: (r) => h('span', { class: `badge ${partStatusBadge[r.status] || 'badge-gray'}` }, `• ${partStatusLabel[r.status] || r.status || '未送出'}`),
  },
  {
    title: '关联订单',
    key: 'order_link',
    minWidth: 140,
    render: (row) => renderJewelryOrderLinkCell(row),
  },
]

onMounted(async () => {
  try {
    const { data: jewels } = await listJewelries()
    jewels.forEach((j) => { jewelryMap.value[j.id] = j })
    await loadData()
    await Promise.all([loadJewelries(), loadPartItemOrderLinks()])
    await loadJewelryItemOrderLinks()
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
