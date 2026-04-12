<template>
  <div>
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">采购单详情</n-h2>
    </n-space>

    <n-spin :show="loading">
      <n-empty v-if="!loading && !order" description="加载失败，请返回重试" style="margin-top: 24px;" />
      <n-card v-if="order" title="基本信息" style="margin-bottom: 16px;">
        <n-descriptions :column="3" bordered>
          <n-descriptions-item label="购入单号">{{ order.id }}</n-descriptions-item>
          <n-descriptions-item label="商家">{{ order.vendor_name }}</n-descriptions-item>
          <n-descriptions-item label="状态">
            <n-popselect
              :value="order?.status"
              :options="statusToggleOptions"
              trigger="click"
              @update:value="doChangeStatus"
            >
              <n-tag
                :type="statusType[order.status]"
                style="cursor: pointer;"
              >
                {{ order.status }} ▾
              </n-tag>
            </n-popselect>
          </n-descriptions-item>
          <n-descriptions-item label="总金额">{{ order.total_amount != null ? `¥ ${fmtMoney(order.total_amount)}` : '-' }}</n-descriptions-item>
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
              {{ fmt(order.created_at) }}
              <n-button text type="primary" size="small" style="margin-left: 6px;" @click="startEditCreatedAt">
                <template #icon><n-icon :component="CreateOutline" /></template>
              </n-button>
            </template>
          </n-descriptions-item>
          <n-descriptions-item label="付款时间">{{ order.paid_at ? fmt(order.paid_at) : '-' }}</n-descriptions-item>
          <n-descriptions-item label="备注">{{ order.note || '-' }}</n-descriptions-item>
          <n-descriptions-item label="单据&配件图片" :span="2">
            <div class="delivery-images-block">
              <div v-if="pendingDeliveryImages.length > 0" class="delivery-images-warning">
                <div class="delivery-images-warning-title">
                  有 {{ pendingDeliveryImages.length }} 张图片已上传，但还没保存到采购单
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
                {{ totalDeliveryImageCount }}/4 张
                <span v-if="pendingDeliveryImages.length > 0">（待保存 {{ pendingDeliveryImages.length }} 张）</span>
              </div>
            </div>
          </n-descriptions-item>
        </n-descriptions>
      </n-card>

      <n-card v-if="order" title="购入明细">
        <template #header-extra>
          <n-space>
            <n-button
              v-if="!isPaid() && canAccessParts"
              size="small"
              type="primary"
              @click="openAddItemModal"
            >
              追加配件
            </n-button>
            <n-button
              v-if="order.items?.length > 0"
              size="small"
              @click="openBatchLinkModal"
            >
              批量关联订单
            </n-button>
          </n-space>
        </template>
        <n-data-table v-if="order.items?.length > 0" :columns="itemColumns" :data="tableData" :bordered="false" :row-class-name="rowClassName" />
        <n-empty v-else description="暂无明细" style="margin-top: 16px;" />
      </n-card>
    </n-spin>

    <!-- Edit Item Modal -->
    <n-modal v-model:show="editModalVisible" preset="card" title="修改明细" style="width: 500px;">
      <form @submit.prevent="doEditItem">
      <n-form label-placement="left" label-width="90">
        <n-form-item label="数量">
          <n-input-number v-model:value="editForm.qty" :min="1" :precision="0" :step="1" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="editForm.unit" :options="unitOptions" />
        </n-form-item>
        <n-form-item label="单价">
          <n-input-number v-model:value="editForm.price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" :step="0.1" style="width: 100%;" />
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

    <!-- Add Item Modal -->
    <n-modal v-model:show="addItemModalVisible" preset="card" title="追加配件" style="width: 500px;">
      <n-form label-placement="left" label-width="90">
        <n-form-item label="配件">
          <n-select
            v-model:value="addItemForm.part_id"
            :options="addItemPartOptions"
            :render-label="renderOptionWithImage"
            filterable
            clearable
            placeholder="选择配件"
          />
        </n-form-item>
        <n-form-item label="数量">
          <n-input-number v-model:value="addItemForm.qty" :min="1" :precision="0" :step="1" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="addItemForm.unit" :options="unitOptions" />
        </n-form-item>
        <n-form-item label="单价">
          <n-input-number v-model:value="addItemForm.price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" :step="0.1" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="addItemForm.note" placeholder="备注（可选）" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="addItemModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="addItemSubmitting" @click="doAddItem">确认添加</n-button>
        </n-space>
      </template>
    </n-modal>

    <ImageUploadModal
      v-model:show="showDeliveryImageModal"
      kind="purchase-orders"
      :entity-id="order?.id"
      suppress-success
      @uploaded="handleDeliveryImageUploaded"
    />

    <!-- Single Link Modal -->
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
          <n-button type="primary" :loading="linkSubmitting" :disabled="!linkForm.todoItemId" @click="doCreateLink">确认关联</n-button>
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
        <n-form-item label="勾选配件">
          <div v-if="unlinkableItems.length === 0" style="color: #999; font-size: 13px;">
            所有配件项已关联订单
          </div>
          <n-checkbox-group v-else v-model:value="batchLinkCheckedIds">
            <n-space vertical>
              <n-checkbox v-for="item in unlinkableItems" :key="item.id" :value="item.id">
                {{ partMap[item.part_id]?.name || item.part_id }} — {{ item.qty }}{{ item.unit || '个' }}
              </n-checkbox>
            </n-space>
          </n-checkbox-group>
        </n-form-item>
        <div style="color: #666; font-size: 13px; padding: 4px 0;">
          将自动按配件编号匹配该订单配件清单中的行
        </div>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="batchLinkModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="batchLinkSubmitting" :disabled="!batchLinkOrderId || batchLinkCheckedIds.length === 0" @click="doBatchLink">确认批量关联</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Addon Cost Diff Modal -->
    <n-modal v-model:show="addonCostDiffVisible" :mask-closable="false" preset="card" title="穿珠成本变动确认" style="width: 550px;">
      <div style="margin-bottom: 12px; color: #333;">
        当前穿珠成本与配件已有穿珠成本金额不相同，是否更新穿珠成本？
      </div>
      <n-data-table
        :columns="[
          { title: '配件编号', key: 'part_id', width: 130 },
          { title: '配件名称', key: 'part_name', minWidth: 120 },
          { title: '原穿珠费用', key: 'current_value', width: 120, render: (r) => r.current_value != null ? `¥ ${fmtMoney(r.current_value)}` : '-' },
          { title: '更新穿珠费用', key: 'new_value', width: 120, render: (r) => h('span', { style: 'color: #d03050; font-weight: 600;' }, `¥ ${fmtMoney(r.new_value)}`) },
        ]"
        :data="addonCostDiffs"
        :bordered="false"
        size="small"
      />
      <template #footer>
        <n-space justify="end">
          <n-button @click="skipAddonCostUpdate" :disabled="addonCostDiffUpdating">跳过</n-button>
          <n-button type="primary" :loading="addonCostDiffUpdating" @click="confirmAddonCostUpdate">确认更新</n-button>
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
  NPopover, NRadioGroup, NRadio, NCheckbox, NCheckboxGroup, NDatePicker,
} from 'naive-ui'
import { CreateOutline } from '@vicons/ionicons5'
import {
  getPurchaseOrder, updatePurchaseOrder, updatePurchaseOrderStatus,
  updatePurchaseOrderDeliveryImages,
  addPurchaseOrderItem, updatePurchaseOrderItem, deletePurchaseOrderItem,
  createPurchaseOrderItemAddon, updatePurchaseOrderItemAddon, deletePurchaseOrderItemAddon,
  getPurchaseItemOrders, deletePurchaseItemOrderLink,
} from '@/api/purchaseOrders'
import { tsToDateStr, isoToTs } from '@/utils/date'
import { listOrders, getTodo, createLink, batchLink } from '@/api/orders'
import { listParts, batchUpdatePartCosts } from '@/api/parts'
import { renderNamedImage, renderOptionWithImage, fmtMoney, fmtPrice, parseNum } from '@/utils/ui'
import ImageUploadModal from '@/components/ImageUploadModal.vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const authStore = useAuthStore()
const canAccessParts = authStore.hasPermission('parts')

const loading = ref(true)
const order = ref(null)

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
    await updatePurchaseOrder(route.params.id, { created_at: dateStr })
    await loadData()
    message.success('创建时间已更新')
    editingCreatedAt.value = false
  } catch (e) {
    message.error(e.response?.data?.detail || '更新失败')
  } finally {
    savingCreatedAt.value = false
  }
}

const partMap = ref({})
const showDeliveryImageModal = ref(false)
const deliveryImagesSaving = ref(false)
const pendingDeliveryImages = ref([])
const retryingPendingImage = ref('')

const statusType = { '已付款': 'success', '未付款': 'error' }
const statusToggleOptions = computed(() => {
  if (!order.value) return []
  if (order.value.status === '未付款') return [{ label: '已付款', value: '已付款' }]
  return [{ label: '未付款', value: '未付款' }]
})

const deliveryImages = computed(() => order.value?.delivery_images || [])
const totalDeliveryImageCount = computed(() => deliveryImages.value.length + pendingDeliveryImages.value.length)
const canAddDeliveryImage = computed(() => totalDeliveryImageCount.value < 4)
const fmt = (dt) => new Date(dt).toLocaleString('zh-CN')
const isPaid = () => order.value?.status === '已付款'

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
const editForm = ref({ id: null, qty: 1, unit: '个', price: 0, note: '' })

// Inline note editing
const editingNoteItemId = ref(null)
const editingNoteValue = ref('')
const savingNoteItemId = ref(null)
const noteInputRef = ref(null)

// Addon cost diff modal
const addonCostDiffVisible = ref(false)
const addonCostDiffs = ref([])
const addonCostDiffSourceId = ref('')
const addonCostDiffUpdating = ref(false)

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
const batchLinkCheckedIds = ref([])

// Items that don't yet have a link (available for batch linking)
const unlinkableItems = computed(() => {
  if (!order.value?.items) return []
  return order.value.items.filter((item) => {
    const links = itemOrderLinks.value[item.id] || []
    return links.length === 0
  })
})

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
  if (!order.value?.items) return
  const map = {}
  await Promise.all(order.value.items.map(async (item) => {
    try {
      const { data } = await getPurchaseItemOrders(route.params.id, item.id)
      map[item.id] = data
    } catch (_) {
      map[item.id] = []
    }
  }))
  itemOrderLinks.value = map
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

const doCreateLink = async () => {
  if (!linkForm.value.todoItemId) return
  linkSubmitting.value = true
  try {
    await createLink(linkForm.value.orderId, {
      order_todo_item_id: linkForm.value.todoItemId,
      purchase_order_item_id: linkForm.value.itemId,
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
  batchLinkCheckedIds.value = unlinkableItems.value.map((i) => i.id)
  batchLinkModalVisible.value = true
  loadOrderOptions()
}

const doBatchLink = async () => {
  if (!batchLinkOrderId.value || batchLinkCheckedIds.value.length === 0) return
  batchLinkSubmitting.value = true
  try {
    const { data } = await batchLink(batchLinkOrderId.value, {
      order_id: batchLinkOrderId.value,
      purchase_order_item_ids: batchLinkCheckedIds.value,
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

const doUnlinkPurchaseItem = (itemId, link) => {
  dialog.warning({
    title: '解除关联',
    content: `确认解除与订单「${link.order_id}」的关联？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deletePurchaseItemOrderLink(route.params.id, itemId, link.link_id)
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
  const children = links.map((link) => h('span', {
    style: 'display: inline-flex; align-items: center; gap: 2px; background: #f0f9eb; border: 1px solid #c2e7b0; border-radius: 4px; padding: 1px 6px; font-size: 12px;',
  }, [
    h('span', null, link.order_id),
    h(NButton, {
      size: 'tiny',
      quaternary: true,
      type: 'error',
      style: 'padding: 0 2px;',
      onClick: () => doUnlinkPurchaseItem(row.id, link),
    }, { default: () => '×' }),
  ]))
  // purchase_order_item_id has unique constraint — only show + if no link exists
  if (links.length === 0) {
    children.push(h(NButton, {
      size: 'tiny',
      text: true,
      type: 'primary',
      onClick: () => openLinkModal(row),
    }, { default: () => '+' }))
  }
  return h('div', { style: 'display: flex; flex-wrap: wrap; gap: 4px; align-items: center;' }, children)
}

// Addon (穿珠费用)
const addonEditing = ref({})   // { [itemId]: { qty: null, price: null, saving: false } }

const tableData = computed(() => {
  if (!order.value?.items) return []
  const rows = []
  for (const item of order.value.items) {
    rows.push({ ...item, _rowType: 'item' })
    for (const addon of (item.addons || [])) {
      rows.push({ ...addon, _rowType: 'addon', _parentItem: item })
    }
    if (addonEditing.value[item.id]) {
      rows.push({ _rowType: 'addon_new', _parentItem: item, id: `new-${item.id}` })
    }
  }
  return rows
})

const loadData = async () => {
  const id = route.params.id
  const { data } = await getPurchaseOrder(id)
  // Enrich items with part info
  data.items = (data.items || []).map((i) => ({
    ...i,
    part_name: partMap.value[i.part_id]?.name || i.part_id,
    part_image: partMap.value[i.part_id]?.image || '',
  }))
  order.value = data
  pendingDeliveryImages.value = pendingDeliveryImages.value.filter((image) => !data.delivery_images.includes(image))
  if (isPaid()) {
    stopEditNote()
    addonEditing.value = {}
    addonInlineEditing.value = {}
  }
}

const doChangeStatus = (newStatus) => {
  dialog.warning({
    title: '确认状态变更',
    content: `确认将采购单「${order.value?.id}」状态从「${order.value?.status}」切换为「${newStatus}」？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      const loadingMsg = message.loading('正在更新状态...', { duration: 0 })
      try {
        await updatePurchaseOrderStatus(order.value.id, newStatus)
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
    price: row.price || 0,
    note: row.note || '',
  }
  editModalVisible.value = true
}

const doEditItem = async () => {
  editSubmitting.value = true
  try {
    const { id, ...body } = editForm.value
    await updatePurchaseOrderItem(route.params.id, id, body)
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
        await deletePurchaseOrderItem(route.params.id, row.id)
        message.success('已删除')
        await loadData()
      } catch (_) {
        // error shown by axios interceptor
      }
    },
  })
}

// Add Item Modal
const addItemModalVisible = ref(false)
const addItemSubmitting = ref(false)
const addItemForm = ref({ part_id: null, qty: 1, unit: '个', price: null, note: '' })
const addItemPartOptions = computed(() =>
  Object.values(partMap.value).map((p) => ({
    label: `${p.id} ${p.name}`,
    value: p.id,
    code: p.id,
    name: p.name,
    image: p.image,
  }))
)

const openAddItemModal = () => {
  addItemForm.value = { part_id: null, qty: 1, unit: '个', price: null, note: '' }
  addItemModalVisible.value = true
}

const doAddItem = async () => {
  if (!addItemForm.value.part_id) { message.warning('请选择配件'); return }
  if (!addItemForm.value.qty || addItemForm.value.qty <= 0) { message.warning('请填写数量'); return }
  addItemSubmitting.value = true
  try {
    await addPurchaseOrderItem(route.params.id, addItemForm.value)
    message.success('配件已追加')
    addItemModalVisible.value = false
    await loadData()
    await loadItemOrderLinks()
  } finally {
    addItemSubmitting.value = false
  }
}

// Delivery images
const mergeDeliveryImages = (...groups) => [...new Set(groups.flat().filter(Boolean))]

const persistDeliveryImages = async (nextImages, successText) => {
  if (!order.value) return
  deliveryImagesSaving.value = true
  try {
    const { data } = await updatePurchaseOrderDeliveryImages(order.value.id, nextImages)
    order.value = { ...order.value, delivery_images: data.delivery_images }
    pendingDeliveryImages.value = pendingDeliveryImages.value.filter((image) => !data.delivery_images.includes(image))
    message.success(successText)
    return data
  } finally {
    deliveryImagesSaving.value = false
  }
}

const openDeliveryImageModal = () => {
  if (!canAddDeliveryImage.value) {
    message.warning('图片最多上传 4 张')
    return
  }
  showDeliveryImageModal.value = true
}

const handleDeliveryImageUploaded = async (url) => {
  if (!url) return
  if (!canAddDeliveryImage.value) {
    message.warning('图片最多上传 4 张')
    return
  }
  try {
    await persistDeliveryImages(mergeDeliveryImages(deliveryImages.value, [url]), '图片已上传')
  } catch (_) {
    if (!pendingDeliveryImages.value.includes(url)) {
      pendingDeliveryImages.value.push(url)
    }
    message.warning('图片已上传，但写入采购单失败，可点击"重试保存"继续')
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
      '待保存图片已写入采购单',
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
    const { data } = await updatePurchaseOrderItem(route.params.id, itemId, { note: nextNote })
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
        !isPaid() ? 'cursor: pointer; color: #2080f0;' : '',
      ].join('; '),
      onClick: !isPaid() ? () => startEditNote(row) : undefined,
    },
    noteText,
  )
}

const handleAddonCostDiffs = (data, orderId) => {
  if (data.cost_diffs && data.cost_diffs.length > 0) {
    addonCostDiffs.value = data.cost_diffs
    addonCostDiffSourceId.value = orderId
    addonCostDiffVisible.value = true
  }
}

const confirmAddonCostUpdate = async () => {
  addonCostDiffUpdating.value = true
  try {
    await batchUpdatePartCosts({
      updates: addonCostDiffs.value.map((d) => ({
        part_id: d.part_id,
        field: d.field,
        value: d.new_value,
        source_id: addonCostDiffSourceId.value,
      })),
    })
    message.success('配件穿珠成本已更新')
    addonCostDiffVisible.value = false
  } catch (_) {
    message.error('成本更新失败，请重试')
  } finally {
    addonCostDiffUpdating.value = false
  }
}

const skipAddonCostUpdate = () => {
  addonCostDiffVisible.value = false
}

// --- Addon (穿珠费用) ---
const startAddonEditing = (itemId) => {
  addonEditing.value[itemId] = { qty: null, price: null, saving: false }
}

const cancelAddonEditing = (itemId) => {
  delete addonEditing.value[itemId]
}

const saveAddon = async (itemId) => {
  const state = addonEditing.value[itemId]
  if (!state || state.saving) return
  if (!state.qty || state.qty <= 0) {
    message.warning('请填写穿珠数量')
    return
  }
  if (state.price == null || state.price < 0) {
    message.warning('请填写穿珠单价')
    return
  }
  state.saving = true
  try {
    const { data } = await createPurchaseOrderItemAddon(route.params.id, itemId, {
      type: 'bead_stringing',
      qty: state.qty,
      unit: '条',
      price: state.price,
    })
    message.success('穿珠费用已保存')
    handleAddonCostDiffs(data, route.params.id)
    delete addonEditing.value[itemId]
    await loadData()
  } finally {
    state.saving = false
  }
}

const doDeleteAddon = (itemId, addonId) => {
  dialog.warning({
    title: '确认移除',
    content: '确认移除该穿珠费用？',
    positiveText: '移除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deletePurchaseOrderItemAddon(route.params.id, itemId, addonId)
        message.success('已移除')
        await loadData()
      } catch (_) {}
    },
  })
}

// Inline addon editing (展示态双击编辑)
const addonInlineEditing = ref({})  // { [addonId]: { qty, price, saving } }

const startAddonInlineEdit = (addon) => {
  if (isPaid()) return
  addonInlineEditing.value[addon.id] = {
    qty: addon.qty,
    price: addon.price,
    saving: false,
  }
}

const cancelAddonInlineEdit = (addonId) => {
  delete addonInlineEditing.value[addonId]
}

const saveAddonInlineEdit = async (itemId, addonId) => {
  const state = addonInlineEditing.value[addonId]
  if (!state || state.saving) return
  if (!state.qty || state.qty <= 0) {
    message.warning('请填写穿珠数量')
    return
  }
  if (state.price == null || state.price < 0) {
    message.warning('请填写穿珠单价')
    return
  }
  state.saving = true
  try {
    const { data } = await updatePurchaseOrderItemAddon(route.params.id, itemId, addonId, {
      qty: state.qty,
      price: state.price,
    })
    message.success('穿珠费用已更新')
    handleAddonCostDiffs(data, route.params.id)
    delete addonInlineEditing.value[addonId]
    await loadData()
  } finally {
    state.saving = false
  }
}

const rowClassName = (row) => {
  if (row._rowType === 'addon' || row._rowType === 'addon_new') return 'addon-sub-row'
  return ''
}

// Format helper: keep precision constraints but strip trailing zeros
const fmtQty = (v) => v == null ? '' : parseFloat(Number(v).toFixed(4)).toString()

const ADDON_TYPE_LABELS = { bead_stringing: '穿珠子' }

const addonRowStyle = {
  fontSize: '13px',
  lineHeight: '1',
}

const itemColumns = [
  {
    title: '配件编号',
    key: 'part_id',
    width: 120,
    render: (row) => {
      if (row._rowType === 'addon' || row._rowType === 'addon_new') {
        return h('span', { style: { ...addonRowStyle, color: '#bbb', paddingLeft: '16px' } }, '└')
      }
      return row.part_id
    },
  },
  {
    title: '配件',
    key: 'part_name',
    minWidth: 180,
    render: (row) => {
      if (row._rowType === 'addon') {
        return h('span', { style: { ...addonRowStyle, color: '#1890ff', fontWeight: 500 } }, ADDON_TYPE_LABELS[row.type] || row.type)
      }
      if (row._rowType === 'addon_new') {
        return h('span', { style: { ...addonRowStyle, color: '#1890ff', fontWeight: 500 } }, '穿珠子')
      }
      return renderNamedImage(row.part_name, row.part_image, row.part_name)
    },
  },
  {
    title: '购入数量',
    key: 'qty',
    render: (row) => {
      if (row._rowType === 'addon') {
        const editing = addonInlineEditing.value[row.id]
        if (editing) {
          return h(NInputNumber, {
            value: editing.qty,
            size: 'small',
            min: 0.0001,
            precision: 4,
            format: fmtQty,
            parse: parseNum,
            style: 'width: 90px;',
            disabled: editing.saving,
            'onUpdate:value': (v) => { editing.qty = v },
          })
        }
        return h('span', {
          style: { ...addonRowStyle, cursor: isPaid() ? 'default' : 'pointer' },
          onDblclick: () => startAddonInlineEdit(row),
        }, row.qty)
      }
      if (row._rowType === 'addon_new') {
        const state = addonEditing.value[row._parentItem.id]
        return h(NInputNumber, {
          value: state?.qty,
          size: 'small',
          min: 0.0001,
          precision: 4,
          format: fmtQty,
          parse: parseNum,
          placeholder: '数量',
          style: 'width: 90px;',
          disabled: state?.saving,
          'onUpdate:value': (v) => { if (state) state.qty = v },
        })
      }
      return row.qty
    },
  },
  {
    title: '单位',
    key: 'unit',
    render: (row) => {
      if (row._rowType === 'addon' || row._rowType === 'addon_new') {
        return h('span', { style: addonRowStyle }, '条')
      }
      return row.unit || '-'
    },
  },
  {
    title: '单价',
    key: 'price',
    render: (row) => {
      if (row._rowType === 'addon') {
        const editing = addonInlineEditing.value[row.id]
        if (editing) {
          return h(NInputNumber, {
            value: editing.price,
            size: 'small',
            min: 0,
            precision: 7,
            format: fmtPrice,
            parse: parseNum,
            step: 0.1,
            style: 'width: 100px;',
            disabled: editing.saving,
            'onUpdate:value': (v) => { editing.price = v },
          })
        }
        return h('span', {
          style: { ...addonRowStyle, cursor: isPaid() ? 'default' : 'pointer' },
          onDblclick: () => startAddonInlineEdit(row),
        }, `¥ ${fmtMoney(row.price)}`)
      }
      if (row._rowType === 'addon_new') {
        const state = addonEditing.value[row._parentItem.id]
        return h(NInputNumber, {
          value: state?.price,
          size: 'small',
          min: 0,
          precision: 7,
          format: fmtPrice,
          parse: parseNum,
          step: 0.1,
          placeholder: '单价',
          style: 'width: 100px;',
          disabled: state?.saving,
          'onUpdate:value': (v) => { if (state) state.price = v },
        })
      }
      return row.price != null ? `¥ ${fmtMoney(row.price)}` : '-'
    },
  },
  {
    title: '金额',
    key: 'amount',
    render: (row) => {
      if (row._rowType === 'addon') {
        return h('span', { style: addonRowStyle }, `¥ ${fmtMoney(row.amount)}`)
      }
      if (row._rowType === 'addon_new') {
        const state = addonEditing.value[row._parentItem.id]
        const amt = (state?.qty && state?.price != null) ? state.qty * state.price : null
        return h('span', { style: addonRowStyle }, amt != null ? `¥ ${fmtMoney(amt)}` : '-')
      }
      return row.amount != null ? `¥ ${fmtMoney(row.amount)}` : '-'
    },
  },
  {
    title: '备注',
    key: 'note',
    minWidth: 240,
    render: (row) => {
      if (row._rowType === 'addon') {
        return h(
          'span',
          {
            style: {
              background: '#f0f7ff',
              border: '1px solid #d6e8fa',
              borderRadius: '4px',
              padding: '2px 8px',
              fontSize: '11px',
              color: '#4a90d9',
            },
          },
          `单配件穿珠成本: ¥ ${fmtMoney(row.unit_cost)}`,
        )
      }
      if (row._rowType === 'addon_new') {
        return h('span', { style: { ...addonRowStyle, color: '#999' } }, '-')
      }
      return renderNoteCell(row)
    },
  },
  {
    title: '关联订单',
    key: 'order_link',
    minWidth: 140,
    render: (row) => {
      if (row._rowType === 'addon' || row._rowType === 'addon_new') return null
      return renderOrderLinkCell(row)
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 180,
    render: (row) => {
      if (row._rowType === 'addon') {
        if (isPaid()) return h('span', { style: { ...addonRowStyle, color: '#999' } }, '-')
        const editing = addonInlineEditing.value[row.id]
        if (editing) {
          return h(NSpace, { size: 'small' }, { default: () => [
            h(NButton, { size: 'tiny', type: 'primary', loading: editing.saving, onClick: () => saveAddonInlineEdit(row._parentItem.id, row.id) }, { default: () => '保存' }),
            h(NButton, { size: 'tiny', disabled: editing.saving, onClick: () => cancelAddonInlineEdit(row.id) }, { default: () => '取消' }),
          ]})
        }
        return h(NButton, { size: 'tiny', type: 'error', onClick: () => doDeleteAddon(row._parentItem.id, row.id) }, { default: () => '移除' })
      }
      if (row._rowType === 'addon_new') {
        const state = addonEditing.value[row._parentItem.id]
        return h(NSpace, { size: 'small' }, { default: () => [
          h(NButton, { size: 'tiny', type: 'primary', loading: state?.saving, onClick: () => saveAddon(row._parentItem.id) }, { default: () => '保存' }),
          h(NButton, { size: 'tiny', disabled: state?.saving, onClick: () => cancelAddonEditing(row._parentItem.id) }, { default: () => '取消' }),
        ]})
      }

      // 配件行
      const canEdit = !isPaid()
      const hasBeadAddon = (row.addons || []).some((a) => a.type === 'bead_stringing')
      const isNewAddonEditing = !!addonEditing.value[row.id]

      const editBtn = h(
        NTooltip,
        { disabled: canEdit, trigger: 'hover' },
        {
          trigger: () => h(NButton, { size: 'small', disabled: !canEdit, style: 'margin-right: 6px;', onClick: canEdit ? () => openEditModal(row) : undefined }, { default: () => '修改' }),
          default: () => '已付款状态不允许修改',
        },
      )
      const deleteBtn = h(
        NTooltip,
        { disabled: canEdit, trigger: 'hover' },
        {
          trigger: () => h(NButton, { size: 'small', type: 'error', disabled: !canEdit, onClick: canEdit ? () => doDeleteItem(row) : undefined }, { default: () => '删除' }),
          default: () => '已付款状态不允许删除',
        },
      )

      const moreBtn = canEdit
        ? h(NPopover, { trigger: 'click', placement: 'bottom-start' }, {
            trigger: () => h(NButton, { size: 'small', style: 'letter-spacing: 2px; font-weight: bold;' }, { default: () => '···' }),
            default: () => h('div', { style: 'min-width: 100px;' }, [
              h(NButton, {
                text: true,
                block: true,
                disabled: hasBeadAddon || isNewAddonEditing,
                style: 'justify-content: flex-start; padding: 6px 12px;',
                onClick: () => startAddonEditing(row.id),
              }, { default: () => '穿珠费用' }),
            ]),
          })
        : null

      return h(NSpace, { size: 'small' }, { default: () => [editBtn, deleteBtn, moreBtn].filter(Boolean) })
    },
  },
]

onMounted(async () => {
  try {
    try {
      const { data: parts } = await listParts()
      parts.forEach((p) => { partMap.value[p.id] = p })
    } catch (_) {
      // parts list failure should not block order loading
    }
    await loadData()
    await loadItemOrderLinks()
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

:deep(.addon-sub-row td) {
  background: linear-gradient(90deg, #f0f7ff 0%, #fafcff 100%) !important;
  padding-top: 4px !important;
  padding-bottom: 4px !important;
}
</style>
