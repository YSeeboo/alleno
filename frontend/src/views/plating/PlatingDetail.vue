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
        <n-descriptions :column="isMobile ? 1 : 3" bordered>
          <n-descriptions-item label="电镀单号">{{ order.id }}</n-descriptions-item>
          <n-descriptions-item label="电镀厂">
            <template v-if="editingSupplier && order.status === 'pending'">
              <n-space align="center" size="small">
                <n-select
                  v-model:value="editingSupplierValue"
                  :options="supplierSelectOptions"
                  filterable
                  tag
                  size="small"
                  placeholder="选择或输入电镀厂"
                  :style="{ width: isMobile ? '100%' : '200px' }"
                />
                <n-button size="small" type="primary" :loading="savingSupplier" @click="saveSupplierName">确认</n-button>
                <n-button size="small" :disabled="savingSupplier" @click="editingSupplier = false">取消</n-button>
              </n-space>
            </template>
            <template v-else>
              {{ order.supplier_name }}
              <n-button v-if="order.status === 'pending'" text type="primary" size="small" style="margin-left: 6px;" @click="startEditSupplier">
                <template #icon><n-icon :component="CreateOutline" /></template>
              </n-button>
            </template>
          </n-descriptions-item>
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
          <n-descriptions-item label="创建时间">
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
              {{ fmt(order.created_at) }}
              <n-button text type="primary" size="small" style="margin-left: 6px;" @click="startEditCreatedAt">
                <template #icon><n-icon :component="CreateOutline" /></template>
              </n-button>
            </template>
          </n-descriptions-item>
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
                {{ totalDeliveryImageCount }}/10 张
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

      <n-card title="电镀明细">
        <template #header-extra>
          <n-button
            v-if="items.length > 0"
            size="small"
            @click="openBatchLinkModal"
          >
            批量关联订单
          </n-button>
        </template>
        <n-data-table v-if="items.length > 0" :columns="itemColumns" :data="items" :bordered="false" :row-key="(r) => r.id" />
        <n-empty v-else description="暂无明细" style="margin-top: 16px;" />
        <div v-if="order?.status === 'pending'" style="margin-top: 12px;">
          <n-button dashed style="width: 100%;" @click="openAddModal">+ 添加明细行</n-button>
        </div>
      </n-card>
    </n-spin>

    <!-- Add Item Modal -->
    <n-modal v-model:show="addModalVisible" preset="card" title="添加电镀明细" :style="{ width: isMobile ? '95vw' : '500px' }">
      <form @submit.prevent="doAddItem">
      <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="90">
        <n-form-item label="发出配件">
          <n-select
            v-model:value="addForm.part_id"
            :options="partOptions"
            :render-label="renderOptionWithImage"
            filterable
            clearable
            placeholder="选择发出配件"
            @update:value="onAddPartSelect"
          />
        </n-form-item>
        <n-form-item v-if="addForm.part_id" label="电镀颜色">
          <div>
            <n-space size="small" style="margin-bottom: 6px;">
              <span
                v-for="cv in colorVariantList"
                :key="cv.code"
                :style="{
                  display: 'inline-block',
                  fontSize: '11px',
                  fontWeight: 'bold',
                  color: addFormColor === cv.code ? '#fff' : BADGE_COLORS[cv.code],
                  background: addFormColor === cv.code ? BADGE_COLORS[cv.code] : '#f5f5f5',
                  padding: '2px 10px',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  border: `1px solid ${BADGE_COLORS[cv.code]}`,
                }"
                @click="toggleAddColor(cv.code)"
              >{{ cv.code }}</span>
            </n-space>
            <div v-if="addFormColor && addVariantInfo" style="font-size: 13px; color: #333;">
              <template v-if="addVariantInfo.part">
                <span>对应配件：{{ addVariantInfo.part.name }} ({{ addVariantInfo.part.id }})</span>
              </template>
              <template v-else-if="addVariantInfo.suggested_name">
                <span style="color: #999;">对应配件：{{ addVariantInfo.suggested_name }}</span>
                <n-button
                  size="tiny"
                  type="primary"
                  style="margin-left: 8px;"
                  :loading="addCreatingVariant"
                  @click="doCreateVariantInAdd"
                >新建</n-button>
              </template>
            </div>
            <div v-if="addFormColor && addVariantLoading" style="font-size: 13px; color: #999;">查询中...</div>
          </div>
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


    <ImageUploadModal
      v-model:show="showDeliveryImageModal"
      kind="plating"
      :entity-id="order?.id"
      suppress-success
      @uploaded="handleDeliveryImageUploaded"
    />

    <!-- Single Link Modal: select order → select matching todo item → confirm -->
    <n-modal v-model:show="linkModalVisible" preset="card" title="关联订单" :style="{ width: isMobile ? '95vw' : '600px' }">
      <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="80">
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
          <n-button type="primary" :loading="linkSubmitting" :disabled="!linkForm.todoItemId" @click="doCreateLink">确认关联</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Batch Link Modal: select order → auto-match by part_id -->
    <n-modal v-model:show="batchLinkModalVisible" preset="card" title="批量关联订单" :style="{ width: isMobile ? '95vw' : '500px' }">
      <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="80">
        <n-form-item label="选择订单">
          <n-select
            v-model:value="batchLinkOrderId"
            :options="orderOptions"
            filterable
            placeholder="搜索订单号或客户名"
          />
        </n-form-item>
        <div style="color: #666; font-size: 13px; padding: 4px 0;">
          将自动按配件编号匹配该订单配件清单中的行，所有明细项都会参与匹配
        </div>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="batchLinkModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="batchLinkSubmitting" :disabled="!batchLinkOrderId" @click="doBatchLink">确认批量关联</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Receipt Link Modal -->
    <n-modal v-model:show="receiptLinkModalVisible" preset="card" title="关联电镀回收单" :style="{ width: isMobile ? '95vw' : '520px' }">
      <div style="background: #f8f9fa; border-radius: 6px; padding: 12px; margin-bottom: 16px; font-size: 13px;">
        <div style="color: #999; font-size: 11px; margin-bottom: 4px;">当前配件</div>
        <div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 4px;">
          <span><strong>{{ receiptLinkItemInfo?.part_id }}</strong> {{ receiptLinkItemInfo?.part_name }}</span>
          <span style="color: #666;">
            发出 {{ receiptLinkItemInfo?.qty }} · 已收 {{ receiptLinkItemInfo?.received_qty }} ·
            <strong style="color: #e67e22;">剩余 {{ receiptLinkItemInfo?.remaining }}</strong>
          </span>
        </div>
        <div v-if="receiptLinkItemInfo?.receive_part_name" style="font-size: 12px; color: #666; margin-top: 4px;">
          收回配件：{{ receiptLinkItemInfo.receive_part_name }}
        </div>
      </div>
      <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="90">
        <n-form-item label="选择回收单">
          <n-spin :show="receiptLinkLoading" style="width: 100%;">
            <div v-if="receiptLinkOptions.length === 0 && !receiptLinkLoading" style="color: #999; font-size: 13px; padding: 8px 0;">
              暂无可用的回收单（需同供应商、未付款）
            </div>
            <n-radio-group v-else v-model:value="receiptLinkForm.receiptId" style="width: 100%;">
              <div style="display: flex; flex-direction: column; gap: 6px;">
                <n-radio v-for="r in receiptLinkOptions" :key="r.id" :value="r.id" style="padding: 6px 0;">
                  <span style="font-weight: 500;">{{ r.id }}</span>
                  <span style="font-size: 12px; color: #888; margin-left: 8px;">
                    {{ r.vendor_name }} · {{ r.created_at?.slice(0, 10) }} · {{ r.item_count }} 项
                  </span>
                </n-radio>
              </div>
            </n-radio-group>
          </n-spin>
        </n-form-item>
        <n-form-item label="回收数量">
          <n-input-number
            v-model:value="receiptLinkForm.qty"
            :min="0.0001"
            :max="receiptLinkItemInfo?.remaining || 0"
            :precision="4"
            placeholder="回收数量"
            style="width: 100%;"
          />
          <span style="font-size: 11px; color: #999; margin-left: 8px; white-space: nowrap;">
            最多 {{ receiptLinkItemInfo?.remaining }}
          </span>
        </n-form-item>
        <n-form-item label="回收单价">
          <n-input-number
            v-model:value="receiptLinkForm.price"
            :min="0"
            :precision="7"
            placeholder="元"
            style="width: 100%;"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="receiptLinkModalVisible = false">取消</n-button>
          <n-button
            type="primary"
            :loading="receiptLinkSubmitting"
            :disabled="receiptLinkOptions.length === 0"
            @click="doLinkReceipt"
          >
            确认关联
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Confirm Loss Modal -->
    <n-modal v-model:show="showLossModal" preset="card" title="确认损耗" :style="{ width: isMobile ? '95vw' : '420px' }">
      <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="80">
        <n-form-item label="差额信息">
          <span v-if="lossTarget">已收回 {{ lossTarget.received_qty || 0 }} / 发出 {{ lossTarget.qty }}，差额 {{ lossTarget.qty - (lossTarget.received_qty || 0) }}</span>
        </n-form-item>
        <n-form-item label="损耗数量">
          <n-input-number v-model:value="lossForm.loss_qty" :min="0.01" :max="lossTarget ? lossTarget.qty - (lossTarget.received_qty || 0) : 0" style="width: 100%;" />
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
import { useRoute, useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { useIsMobile } from '@/composables/useIsMobile'
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NTag, NEmpty, NModal, NForm, NFormItem,
  NSelect, NInputNumber, NInput, NPopselect, NTooltip, NIcon, NImage,
  NRadioGroup, NRadio, NDatePicker,
} from 'naive-ui'
import { tsToDateStr, isoToTs } from '@/utils/date'
import { CreateOutline } from '@vicons/ionicons5'
import {
  getPlating, getPlatingItems, sendPlating,
  addPlatingItem, updatePlatingItem, deletePlatingItem,
  updatePlatingDeliveryImages, updatePlatingOrder,
  downloadPlatingExcel, downloadPlatingPdf,
  getPlatingAllItemOrders, getPlatingItemOrders, deletePlatingItemOrderLink,
  getPlatingReceiptLinks, getAvailableReceipts, linkPlatingItemToReceipt,
} from '@/api/plating'
import { deletePlatingReceiptItem } from '@/api/platingReceipts'
import { confirmPlatingLoss } from '@/api/productionLoss'
import { listSuppliers, createSupplier } from '@/api/suppliers'
import { changeOrderStatus } from '@/api/kanban'
import { listParts, findOrCreateVariant, createPartVariant, getColorVariants } from '@/api/parts'
import { listOrders, getTodo, createLink, batchLink } from '@/api/orders'
import { renderNamedImage, renderOptionWithImage } from '@/utils/ui'
import ImageUploadModal from '@/components/ImageUploadModal.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const { isMobile } = useIsMobile()

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

// Confirm loss modal
const showLossModal = ref(false)
const lossTarget = ref(null)
const lossForm = ref({ loss_qty: 0, deduct_amount: null, reason: '', note: '' })
const lossSubmitting = ref(false)

const openLossModal = (item) => {
  lossTarget.value = item
  const gap = item.qty - (item.received_qty || 0)
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
    await confirmPlatingLoss(route.params.id, lossTarget.value.id, payload)
    showLossModal.value = false
    message.success('损耗已确认')
    await loadData()
  } catch (err) {
    // error handled by interceptor
  } finally {
    lossSubmitting.value = false
  }
}

const editingSupplier = ref(false)
const editingSupplierValue = ref('')
const savingSupplier = ref(false)
const supplierSelectOptions = ref([])

const editingCreatedAt = ref(false)
const editingCreatedAtTs = ref(null)
const savingCreatedAt = ref(false)

const startEditCreatedAt = () => {
  editingCreatedAtTs.value = isoToTs(order.value?.created_at)
  editingCreatedAt.value = true
}

const saveCreatedAt = async () => {
  const dateStr = tsToDateStr(editingCreatedAtTs.value)
  if (!dateStr) { message.warning('请选择日期'); return }
  savingCreatedAt.value = true
  try {
    await updatePlatingOrder(route.params.id, { created_at: dateStr })
    await loadData()
    message.success('创建时间已更新')
    editingCreatedAt.value = false
  } catch (e) {
    message.error(e.response?.data?.detail || '更新失败')
  } finally {
    savingCreatedAt.value = false
  }
}

const loadSupplierOptions = async () => {
  try {
    const { data } = await listSuppliers({ type: 'plating' })
    supplierSelectOptions.value = data.map((s) => ({ label: s.name, value: s.name }))
  } catch (_) {}
}

const startEditSupplier = () => {
  editingSupplierValue.value = order.value?.supplier_name || ''
  editingSupplier.value = true
  loadSupplierOptions()
}

const saveSupplierName = async () => {
  const trimmed = (editingSupplierValue.value || '').trim()
  if (!trimmed) { message.warning('电镀厂名称不能为空'); return }
  if (trimmed === order.value?.supplier_name) { editingSupplier.value = false; return }
  savingSupplier.value = true
  try {
    // Auto-create supplier if new (swallow duplicate 400, rethrow others)
    const isNew = !supplierSelectOptions.value.some((o) => o.value === trimmed)
    if (isNew) {
      try { await createSupplier({ name: trimmed, type: 'plating' }) } catch (e) { if (e.response?.status !== 400) throw e }
    }
    await updatePlatingOrder(route.params.id, { supplier_name: trimmed })
    await loadData()
    message.success('电镀厂名称已更新')
    editingSupplier.value = false
  } catch (e) {
    message.error(e.response?.data?.detail || '更新失败')
  } finally {
    savingSupplier.value = false
  }
}

const statusType = { pending: 'default', processing: 'info', completed: 'success' }
const statusLabel = { pending: '待发出', processing: '进行中', completed: '已完成' }
const deliveryImages = computed(() => order.value?.delivery_images || [])
const totalDeliveryImageCount = computed(() => deliveryImages.value.length + pendingDeliveryImages.value.length)
const canAddDeliveryImage = computed(() => totalDeliveryImageCount.value < 10)
const statusOptions = computed(() => {
  if (!order.value) return []
  const s = order.value.status
  if (s === 'pending') return [{ label: '进行中', value: 'processing' }]
  if (s === 'processing') return [
    { label: '待发出', value: 'pending' },
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

const BADGE_COLORS = { G: '#DAA520', S: '#C0C0C0', RG: '#B76E79' }
const COLOR_SUFFIX_MAP = { '_金色': 'G', '_白K': 'S', '_玫瑰金': 'RG' }
const COLOR_CODE_TO_METHOD = { G: '金', S: '白K', RG: '玫瑰金' }
const METHOD_TO_CODE = { '金': 'G', '白K': 'S', '玫瑰金': 'RG' }

const colorVariantList = ref([])
let addVariantRequestSeq = 0

const COLOR_LABEL_TO_CODE = { '金色': 'G', '白K': 'S', '玫瑰金': 'RG' }

const getPartColorCode = (part) => {
  if (!part) return null
  if (part.color && COLOR_LABEL_TO_CODE[part.color]) return COLOR_LABEL_TO_CODE[part.color]
  for (const [suffix, code] of Object.entries(COLOR_SUFFIX_MAP)) {
    if (part.name?.endsWith(suffix)) return code
  }
  return null
}

const getColorBadge = (partName) => {
  if (!partName) return null
  for (const [suffix, code] of Object.entries(COLOR_SUFFIX_MAP)) {
    if (partName.endsWith(suffix)) return code
  }
  return null
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
const addFormColor = ref(null)
const addVariantInfo = ref(null)
const addVariantLoading = ref(false)
const addCreatingVariant = ref(false)

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
  } catch (e) {
    const detail = e.response?.data?.detail || ''
    if (detail.includes('库存不足')) {
      const items = detail.replace(/^库存不足[：:]?\s*/, '').split('；').filter(Boolean)
      dialog.warning({
        title: '库存不足',
        content: () => h('ul', { style: 'padding-left: 20px; margin: 0;' }, items.map(t => h('li', { style: 'margin: 4px 0;' }, t))),
        positiveText: '知道了',
      })
    } else {
      message.error(detail || '发出失败')
    }
  } finally {
    sending.value = false
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
  addFormColor.value = null
  addVariantInfo.value = null
  addVariantLoading.value = false
  addCreatingVariant.value = false
  addModalVisible.value = true
}

const onAddPartSelect = (val) => {
  const found = partOptions.value.find((p) => p.value === val)
  addForm.value.unit = found?.unit || '个'
  addForm.value.receive_part_id = null
  addFormColor.value = null
  addVariantInfo.value = null
  addVariantLoading.value = false
  ++addVariantRequestSeq
  if (val) {
    const part = allParts.value.find((p) => p.id === val)
    const existingCode = getPartColorCode(part)
    // Default: use existing color if variant, otherwise G
    toggleAddColor(existingCode || 'G')
  }
}

const toggleAddColor = async (code) => {
  if (addFormColor.value === code) {
    addFormColor.value = null
    addVariantInfo.value = null
    addForm.value.receive_part_id = null
    addForm.value.plating_method = '金'
    return
  }
  addFormColor.value = code
  addForm.value.plating_method = COLOR_CODE_TO_METHOD[code] || '金'
  addForm.value.receive_part_id = null
  addVariantInfo.value = null
  addVariantLoading.value = true
  const seq = ++addVariantRequestSeq
  try {
    const { data } = await findOrCreateVariant(addForm.value.part_id, { color_code: code })
    if (addFormColor.value !== code || addVariantRequestSeq !== seq) return // stale
    addVariantInfo.value = data
    addForm.value.receive_part_id = data.part?.id || null
  } catch (e) {
    if (addFormColor.value === code && addVariantRequestSeq === seq) {
      message.error(e.response?.data?.detail || '查询变体失败')
    }
  } finally {
    if (addFormColor.value === code && addVariantRequestSeq === seq) {
      addVariantLoading.value = false
    }
  }
}

const doCreateVariantInAdd = () => {
  const suggestedName = addVariantInfo.value?.suggested_name
  dialog.info({
    title: '确认新建',
    content: `当前没有 ${suggestedName}，确定新建吗？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      addCreatingVariant.value = true
      try {
        const { data: newPart } = await createPartVariant(addForm.value.part_id, { color_code: addFormColor.value })
        addForm.value.receive_part_id = newPart.id
        addVariantInfo.value = { part: newPart, created: true }
        // Refresh parts list
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
        message.success('变体创建成功')
      } catch (e) {
        message.error(e.response?.data?.detail || '创建变体失败')
      } finally {
        addCreatingVariant.value = false
      }
    },
  })
}

const inlineColorSeq = ref({}) // key: row.id, value: request sequence number

const toggleInlineColor = async (row, code) => {
  const currentBadge = getColorBadge(row.receive_part_name) || METHOD_TO_CODE[row.plating_method] || null
  if (currentBadge === code) {
    // Deselect: clear receive_part_id
    try {
      await updatePlatingItem(route.params.id, row.id, { receive_part_id: null, plating_method: null })
      await loadData()
    } catch (e) {
      message.error(e.response?.data?.detail || '更新失败')
    }
    return
  }
  // Find or create variant with stale-response protection
  const seq = (inlineColorSeq.value[row.id] || 0) + 1
  inlineColorSeq.value[row.id] = seq
  const isStale = () => inlineColorSeq.value[row.id] !== seq
  try {
    const { data } = await findOrCreateVariant(row.part_id, { color_code: code })
    if (isStale()) return
    if (data.part) {
      // Variant exists, update directly
      await updatePlatingItem(route.params.id, row.id, {
        receive_part_id: data.part.id,
        plating_method: COLOR_CODE_TO_METHOD[code] || '金',
      })
      if (!isStale()) await loadData()
    } else {
      if (isStale()) return
      // Variant doesn't exist, confirm creation
      dialog.info({
        title: '确认新建',
        content: `当前没有 ${data.suggested_name}，确定新建吗？`,
        positiveText: '确认',
        negativeText: '取消',
        onPositiveClick: async () => {
          if (isStale()) return
          try {
            const { data: newPart } = await createPartVariant(row.part_id, { color_code: code })
            await updatePlatingItem(route.params.id, row.id, {
              receive_part_id: newPart.id,
              plating_method: COLOR_CODE_TO_METHOD[code] || '金',
            })
            // Refresh parts list and table
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
            message.success('变体创建成功')
          } catch (e) {
            message.error(e.response?.data?.detail || '创建变体失败')
          }
        },
      })
    }
  } catch (e) {
    if (!isStale()) message.error(e.response?.data?.detail || '查询变体失败')
  }
}

const doAddItem = async () => {
  if (!addForm.value.part_id) { message.warning('请选择配件'); return }
  if (!addForm.value.qty || addForm.value.qty < 1) { message.warning('数量不能小于 1'); return }
  if (addVariantLoading.value) { message.warning('正在查询变体，请稍候'); return }
  if (addFormColor.value && !addForm.value.receive_part_id) { message.warning('变体配件未就绪，请重新选择颜色'); return }
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
    message.warning('发货图片最多上传 10 张')
    return
  }
  showDeliveryImageModal.value = true
}

const handleDeliveryImageUploaded = async (url) => {
  if (!url) return
  if (!canAddDeliveryImage.value) {
    message.warning('发货图片最多上传 10 张')
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

// --- Receipt Link ---
const itemReceiptLinks = ref({}) // itemId -> [{receipt_id, receipt_item_id, qty, price}]
const receiptLinkModalVisible = ref(false)
const receiptLinkForm = ref({ itemId: null, receiptId: null, qty: null, price: null })
const receiptLinkOptions = ref([])
const receiptLinkLoading = ref(false)
const receiptLinkSubmitting = ref(false)
const receiptLinkItemInfo = ref(null)

const loadItemReceiptLinks = async () => {
  try {
    const { data } = await getPlatingReceiptLinks(route.params.id)
    const map = {}
    for (const [key, val] of Object.entries(data)) {
      map[Number(key)] = val
    }
    itemReceiptLinks.value = map
  } catch (_) {
    itemReceiptLinks.value = {}
  }
}

const openReceiptLinkModal = async (row) => {
  receiptLinkForm.value = { itemId: row.id, receiptId: null, qty: null, price: null }
  const remaining = row.qty - (row.received_qty || 0)
  receiptLinkItemInfo.value = {
    part_id: row.part_id,
    part_name: row.part_name,
    qty: row.qty,
    received_qty: row.received_qty || 0,
    remaining,
    receive_part_name: row.receive_part_name,
  }
  receiptLinkOptions.value = []
  receiptLinkModalVisible.value = true
  receiptLinkLoading.value = true
  try {
    const { data } = await getAvailableReceipts(route.params.id, row.id)
    receiptLinkOptions.value = data
  } catch (_) {
    receiptLinkOptions.value = []
  } finally {
    receiptLinkLoading.value = false
  }
}

const doLinkReceipt = async () => {
  const { itemId, receiptId, qty, price } = receiptLinkForm.value
  if (!receiptId) { message.warning('请选择回收单'); return }
  if (!qty || qty <= 0) { message.warning('请输入回收数量'); return }
  if (price == null || price < 0) { message.warning('请输入回收单价'); return }
  const remaining = receiptLinkItemInfo.value?.remaining || 0
  if (qty > remaining) { message.warning(`回收数量不能超过剩余可收数量 ${remaining}`); return }
  receiptLinkSubmitting.value = true
  try {
    await linkPlatingItemToReceipt(route.params.id, itemId, {
      receipt_id: receiptId,
      qty,
      price,
    })
    message.success('关联成功')
    receiptLinkModalVisible.value = false
    await Promise.all([loadItemReceiptLinks(), loadData()])
  } catch (e) {
    message.error(e.response?.data?.detail || '关联失败')
  } finally {
    receiptLinkSubmitting.value = false
  }
}

const doUnlinkReceipt = (itemId, link) => {
  dialog.warning({
    title: '确认取消关联',
    content: `取消关联回收单「${link.receipt_id}」将回滚对应的库存变更，是否继续？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deletePlatingReceiptItem(link.receipt_id, link.receipt_item_id)
        message.success('已取消关联')
        await Promise.all([loadItemReceiptLinks(), loadData()])
      } catch (e) {
        message.error(e.response?.data?.detail || '取消关联失败')
      }
    },
  })
}

// --- Order Link ---
const orderOptions = ref([])
const itemOrderLinks = ref({}) // itemId -> [{order_id, customer_name, link_id}]

const linkModalVisible = ref(false)
const linkForm = ref({ itemId: null, partId: null, orderId: null, todoItemId: null })
const linkTodoItems = ref([])
const linkTodoLoading = ref(false)
const linkSubmitting = ref(false)

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

const loadItemOrderLinks = async () => {
  try {
    const { data } = await getPlatingAllItemOrders(route.params.id)
    // data is {item_id: [...]} with integer keys serialized as strings
    const map = {}
    for (const [key, val] of Object.entries(data)) {
      map[Number(key)] = val
    }
    itemOrderLinks.value = map
  } catch (_) {
    itemOrderLinks.value = {}
  }
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
    // Filter to matching part_id
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

const doCreateLink = async () => {
  if (!linkForm.value.todoItemId) return
  linkSubmitting.value = true
  try {
    await createLink(linkForm.value.orderId, {
      order_todo_item_id: linkForm.value.todoItemId,
      plating_order_item_id: linkForm.value.itemId,
    })
    message.success('关联成功')
    linkModalVisible.value = false
    await loadItemOrderLinks()
  } catch (e) {
    message.error(e.response?.data?.detail || '关联失败')
  } finally {
    linkSubmitting.value = false
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
      plating_order_item_ids: allItemIds,
    })
    const msg = [`成功关联 ${data.linked} 项`]
    if (data.skipped.length > 0) {
      msg.push(`跳过: ${data.skipped.join(', ')}`)
    }
    message.success(msg.join('，'))
    batchLinkModalVisible.value = false
    await loadItemOrderLinks()
  } catch (e) {
    message.error(e.response?.data?.detail || '批量关联失败')
  } finally {
    batchLinkSubmitting.value = false
  }
}

const doUnlinkPlatingItem = (itemId, link) => {
  dialog.warning({
    title: '解除关联',
    content: `确认解除与订单「${link.order_id}」的关联？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deletePlatingItemOrderLink(route.params.id, itemId, link.link_id)
        message.success('已解除关联')
        await loadItemOrderLinks()
      } catch (_) {}
    },
  })
}

const renderOrderLinkCell = (row) => {
  const links = itemOrderLinks.value[row.id] || []
  if (links.length === 0) {
    return h(NButton, {
      size: 'small',
      text: true,
      type: 'primary',
      onClick: () => openLinkModal(row),
    }, { default: () => '关联订单' })
  }
  return h('div', { style: 'display: flex; flex-wrap: wrap; gap: 4px; align-items: center;' }, [
    ...links.map((link) => h('span', {
      style: 'display: inline-flex; align-items: center; gap: 2px; background: #f0f9eb; border: 1px solid #c2e7b0; border-radius: 4px; padding: 1px 6px; font-size: 12px;',
    }, [
      h('span', null, link.order_id),
      h(NButton, {
        size: 'tiny',
        quaternary: true,
        type: 'error',
        style: 'padding: 0 2px;',
        onClick: () => doUnlinkPlatingItem(row.id, link),
      }, { default: () => '×' }),
    ])),
    h(NButton, {
      size: 'tiny',
      text: true,
      type: 'primary',
      onClick: () => openLinkModal(row),
    }, { default: () => '+' }),
  ])
}

const renderReceiptLinkCell = (row) => {
  if (row.status === '未送出') {
    return h('span', { style: 'color: #ccc;' }, '—')
  }
  const links = itemReceiptLinks.value[row.id] || []
  const receivedQty = row.received_qty || 0
  const qty = row.qty || 0
  const fullyReceived = receivedQty >= qty

  if (links.length === 0) {
    return h(NButton, {
      size: 'small',
      text: true,
      type: 'primary',
      onClick: () => openReceiptLinkModal(row),
    }, { default: () => '关联电镀单' })
  }

  const children = []
  children.push(...links.map((link) => {
    const badge = [
      h('span', {
        style: 'cursor: pointer; text-decoration: underline;',
        onClick: () => router.push(`/plating-receipts/${link.receipt_id}?highlight=${link.receipt_item_id}`),
      }, link.receipt_id),
    ]
    if (!fullyReceived) {
      badge.push(h(NButton, {
        size: 'tiny',
        quaternary: true,
        type: 'error',
        style: 'padding: 0 2px;',
        onClick: () => doUnlinkReceipt(row.id, link),
      }, { default: () => '×' }))
    }
    return h('span', {
      style: 'display: inline-flex; align-items: center; gap: 2px; background: #e8f5e9; border: 1px solid #a5d6a7; border-radius: 4px; padding: 1px 6px; font-size: 12px;',
    }, badge)
  }))

  if (!fullyReceived) {
    children.push(h(NButton, {
      size: 'tiny',
      text: true,
      type: 'primary',
      onClick: () => openReceiptLinkModal(row),
    }, { default: () => '+' }))
  }

  const hint = fullyReceived ? '已全部回收' : `已收 ${receivedQty} / ${qty}`
  children.push(h('div', { style: 'font-size: 11px; color: #999; margin-top: 2px; width: 100%;' }, hint))

  return h('div', { style: 'display: flex; flex-wrap: wrap; gap: 4px; align-items: center;' }, children)
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
      const content = renderNamedImage(row.part_name, row.part_image, row.part_name, 40, partMap.value[row.part_id]?.is_composite ? '组合' : null)
      if (!isPending()) return content
      return h('div', { style: 'cursor: pointer;', onClick: () => startInline(row, 'part_id') }, [content])
    },
  },
  {
    title: '电镀颜色',
    key: 'plating_color_inline',
    width: 120,
    render: (row) => {
      const currentBadge = getColorBadge(row.receive_part_name) || METHOD_TO_CODE[row.plating_method] || null
      const pending = isPending()
      return h('div', { style: 'display: flex; gap: 4px; align-items: center;' },
        colorVariantList.value.map((cv) => {
          const isActive = currentBadge === cv.code
          return h('span', {
            style: {
              display: 'inline-block',
              fontSize: '11px',
              fontWeight: 'bold',
              color: isActive ? '#fff' : BADGE_COLORS[cv.code],
              background: isActive ? BADGE_COLORS[cv.code] : '#f5f5f5',
              padding: '2px 8px',
              borderRadius: '4px',
              cursor: pending ? 'pointer' : 'default',
              opacity: pending ? 1 : 0.5,
              border: `1px solid ${BADGE_COLORS[cv.code]}`,
            },
            onClick: pending ? () => toggleInlineColor(row, cv.code) : undefined,
          }, cv.code)
        }),
      )
    },
  },
  {
    title: '收回配件',
    key: 'receive_part_name',
    minWidth: 140,
    render: (row) => {
      if (!row.receive_part_name) {
        return h('span', { style: 'color: #999;' }, '同发出配件')
      }
      return h('span', null, row.receive_part_name)
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
  { title: '已收回', key: 'received_qty', render: (r) => (r.received_qty ?? 0) - (r.loss_qty ?? 0) },
  {
    title: '损耗',
    key: 'loss_qty',
    width: 60,
    render: (r) => r.loss_qty ? h(NTag, { type: 'warning', size: 'small' }, { default: () => r.loss_qty }) : null,
  },
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
    title: '重量',
    key: 'weight',
    width: 140,
    render: (row) => {
      if (!isPending()) {
        return row.weight != null ? `${row.weight} ${row.weight_unit || 'g'}` : '—'
      }
      const weightKey = inlineKey(row.id, 'weight')
      const unitKey = inlineKey(row.id, 'weight_unit')
      return h('div', { style: 'display:flex;gap:4px;align-items:center' }, [
        h(NInputNumber, {
          value: weightKey in inlineEditing.value ? inlineEditing.value[weightKey] : (row.weight ?? null),
          size: 'small',
          style: 'width:80px',
          min: 0,
          placeholder: '重量',
          onFocus: () => { if (!(weightKey in inlineEditing.value)) inlineEditing.value[weightKey] = row.weight ?? null },
          'onUpdate:value': (v) => { inlineEditing.value[weightKey] = v },
          onBlur: () => { saveInline(row, 'weight', inlineEditing.value[weightKey]) },
        }),
        h(NSelect, {
          value: row.weight_unit || 'g',
          size: 'small',
          style: 'width:55px',
          options: [{ label: 'g', value: 'g' }, { label: 'kg', value: 'kg' }],
          'onUpdate:value': (v) => { saveInline(row, 'weight_unit', v) },
        }),
      ])
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
    title: '关联订单',
    key: 'order_link',
    minWidth: 140,
    render: (row) => renderOrderLinkCell(row),
  },
  {
    title: '关联电镀单',
    key: 'receipt_link',
    minWidth: 160,
    render: (row) => renderReceiptLinkCell(row),
  },
  {
    title: '操作',
    key: 'actions',
    width: 100,
    render: (row) => {
      const pending = isPending()
      const btns = []

      if (pending) {
        btns.push(h(NButton, {
          size: 'small',
          type: 'error',
          onClick: () => doDeleteItem(row),
        }, { default: () => '删除' }))
      }

      if (!pending) {
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

      // Confirm loss button: show when item has gap and status is "电镀中"
      const gap = row.qty - (row.received_qty || 0)
      if (gap > 0 && row.status === '电镀中') {
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

onMounted(async () => {
  try {
    // Load parts/colors and data in parallel; order links also in parallel with loadData
    const [{ data: parts }, colorsRes] = await Promise.all([listParts(), getColorVariants()])
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
    colorVariantList.value = colorsRes.data
    await Promise.all([loadData(), loadItemOrderLinks(), loadItemReceiptLinks()])
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
