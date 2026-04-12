<template>
  <div>
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">订单详情</n-h2>
    </n-space>

    <n-spin :show="loading">
      <!-- Basic info — full width -->
      <n-card title="基本信息" style="margin-bottom: 16px;">
        <n-descriptions :column="3" bordered>
          <n-descriptions-item label="订单号">{{ order?.id }}</n-descriptions-item>
          <n-descriptions-item label="客户名">{{ order?.customer_name }}</n-descriptions-item>
          <n-descriptions-item label="状态">
            <n-tag :type="statusColor[order?.status]">{{ order?.status }}</n-tag>
          </n-descriptions-item>
          <n-descriptions-item label="总金额">{{ order?.total_amount != null ? fmtMoney(order.total_amount) : '-' }}</n-descriptions-item>
          <n-descriptions-item label="创建时间" :span="2">
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
              {{ order?.created_at ? new Date(order.created_at).toLocaleString('zh-CN') : '-' }}
              <n-button text type="primary" size="small" style="margin-left: 6px;" @click="startEditCreatedAt">
                <template #icon><n-icon :component="CreateOutline" /></template>
              </n-button>
            </template>
          </n-descriptions-item>
        </n-descriptions>
        <n-space style="margin-top: 12px;">
          <n-button
            v-if="nextStatus"
            type="primary"
            :loading="updating"
            @click="advanceStatus"
          >
            {{ nextStatusLabel }}
          </n-button>
        </n-space>
      </n-card>

      <!-- 附加信息 (collapsible, default collapsed) -->
      <n-card style="margin-bottom: 16px;">
        <n-collapse>
          <n-collapse-item title="附加信息" name="extra-info">
            <!-- 条码要求 -->
            <div style="margin-bottom: 20px;">
              <div style="font-weight: 500; margin-bottom: 8px;">条码要求</div>
              <div style="display: flex; gap: 16px;">
                <n-input
                  v-model:value="extraInfo.barcode_text"
                  type="textarea"
                  :rows="3"
                  placeholder="条码要求说明..."
                  style="flex: 1;"
                />
                <div style="width: 100px;">
                  <div v-if="extraInfo.barcode_image" style="position: relative; display: inline-block;">
                    <n-image :src="extraInfo.barcode_image" width="100" height="80" object-fit="cover" style="border-radius: 4px;" />
                    <n-button circle size="tiny" type="error" style="position: absolute; top: -6px; right: -6px;" @click="clearImage('barcode')">
                      <template #icon><n-icon :component="CloseIcon" /></template>
                    </n-button>
                  </div>
                  <n-button v-else dashed style="width: 100px; height: 80px;" @click="openImageUpload('barcode')">
                    上传图片
                  </n-button>
                </div>
              </div>
            </div>

            <!-- 唛头要求 -->
            <div style="margin-bottom: 20px;">
              <div style="font-weight: 500; margin-bottom: 8px;">唛头要求</div>
              <div style="display: flex; gap: 16px;">
                <n-input
                  v-model:value="extraInfo.mark_text"
                  type="textarea"
                  :rows="3"
                  placeholder="唛头要求说明..."
                  style="flex: 1;"
                />
                <div style="width: 100px;">
                  <div v-if="extraInfo.mark_image" style="position: relative; display: inline-block;">
                    <n-image :src="extraInfo.mark_image" width="100" height="80" object-fit="cover" style="border-radius: 4px;" />
                    <n-button circle size="tiny" type="error" style="position: absolute; top: -6px; right: -6px;" @click="clearImage('mark')">
                      <template #icon><n-icon :component="CloseIcon" /></template>
                    </n-button>
                  </div>
                  <n-button v-else dashed style="width: 100px; height: 80px;" @click="openImageUpload('mark')">
                    上传图片
                  </n-button>
                </div>
              </div>
            </div>

            <!-- 总备注 -->
            <div style="margin-bottom: 16px;">
              <div style="font-weight: 500; margin-bottom: 8px;">总备注</div>
              <n-input
                v-model:value="extraInfo.note"
                type="textarea"
                :rows="3"
                placeholder="其他注意事项..."
              />
            </div>

            <n-button type="primary" :loading="savingExtraInfo" @click="saveExtraInfo">保存</n-button>

            <!-- Image upload modal (reused) -->
            <ImageUploadModal
              v-model:show="showImageUpload"
              kind="order"
              :entity-id="order?.id"
              :suppress-success="true"
              @uploaded="onImageUploaded"
            />
          </n-collapse-item>
        </n-collapse>
      </n-card>

      <!-- Packaging cost -->
      <n-card title="包装费" style="margin-bottom: 16px;">
        <n-space align="center">
          <n-input-number
            v-model:value="packagingCost"
            :min="0"
            :precision="2"
            placeholder="包装费"
            style="width: 180px;"
          />
          <n-button type="primary" size="small" :loading="savingPkg" @click="savePackagingCost">保存</n-button>
        </n-space>
      </n-card>

      <!-- Order items — full width -->
      <n-card style="margin-bottom: 16px;">
        <n-collapse :default-expanded-names="['jewelry-list']">
          <n-collapse-item title="饰品清单" name="jewelry-list">
        <n-button
          v-if="canEditCustomerCode && checkedItemIds.length > 0"
          size="small"
          type="primary"
          style="margin-bottom: 8px;"
          @click="showBatchCodeModal = true"
        >
          批量填入客户货号 ({{ checkedItemIds.length }})
        </n-button>
        <n-data-table v-if="orderItems.length > 0" :columns="itemColumns" :data="orderItems" :bordered="false" size="small" :row-key="row => row.id" v-model:checked-row-keys="checkedItemIds" />
        <n-empty v-else description="暂无饰品明细" style="margin-top: 16px;" />

        <!-- Add item row -->
        <template v-if="canEditItems">
        <n-divider style="margin: 12px 0;" />
        <n-space align="center">
          <n-select
            v-model:value="newItem.jewelry_id"
            :options="jewelryOptions"
            :render-label="renderOptionWithImage"
            filterable
            clearable
            placeholder="选择饰品"
            style="width: 220px;"
            @update:value="onNewJewelrySelect"
          />
          <n-input-number v-model:value="newItem.quantity" :min="1" placeholder="数量" style="width: 90px;" />
          <n-input-number
            v-model:value="newItem.unit_price"
            :min="0"
            :precision="7"
            :format="fmtPrice"
            :parse="parseNum"
            placeholder="单价"
            style="width: 120px;"
          />
          <n-input v-model:value="newItem.remarks" placeholder="备注" style="width: 160px;" />
          <n-button type="primary" size="small" :loading="addingItem" @click="doAddItem">添加</n-button>
        </n-space>
        </template>
          </n-collapse-item>
        </n-collapse>
      </n-card>

      <!-- Cost Snapshot -->
      <n-card v-if="snapshot" title="成本快照" style="margin-bottom: 16px;">
        <n-alert v-if="snapshot.has_incomplete_cost" type="warning" style="margin-bottom: 12px;">
          部分配件缺少成本数据，成本可能不完整
        </n-alert>
        <n-descriptions :column="4" bordered style="margin-bottom: 16px;">
          <n-descriptions-item label="订单总成本">{{ fmtMoney(snapshot.total_cost) }}</n-descriptions-item>
          <n-descriptions-item label="包装费">{{ snapshot.packaging_cost != null ? fmtMoney(snapshot.packaging_cost) : '-' }}</n-descriptions-item>
          <n-descriptions-item label="售价总额">{{ snapshot.total_amount != null ? fmtMoney(snapshot.total_amount) : '-' }}</n-descriptions-item>
          <n-descriptions-item label="利润">
            <span :style="{ color: snapshot.profit >= 0 ? '#18a058' : '#d03050', fontWeight: 600 }">
              {{ fmtMoney(snapshot.profit) }}
            </span>
          </n-descriptions-item>
        </n-descriptions>

        <n-data-table
          :columns="snapshotColumns"
          :data="snapshot.items"
          :bordered="false"
          size="small"
          :row-key="(r) => r.id"
          :expanded-row-keys="expandedKeys"
          @update:expanded-row-keys="(keys) => expandedKeys = keys"
        />
      </n-card>

      <!-- TodoList — Batch-based collapsible structure -->
      <n-card title="配件清单" style="margin-bottom: 16px;">
        <template #header-extra>
          <n-button
            type="primary"
            size="small"
            @click="openBatchModal"
          >
            生成指定配件清单
          </n-button>
        </template>

        <!-- Batch-based collapsible list -->
        <div v-if="batches.length > 0" style="margin-bottom: 16px;">
          <div v-for="(batch, batchIndex) in batches" :key="batch.id" class="batch-row">
            <!-- Big row (header) -->
            <div class="batch-header" @click="toggleBatch(batch.id)">
              <div class="batch-header-left">
                <span class="batch-chevron">{{ expandedBatchIds.has(batch.id) ? '▾' : '▸' }}</span>
                <span class="batch-title">批次 {{ batchIndex + 1 }}</span>
                <span class="batch-date">{{ formatBatchDate(batch.created_at) }}</span>
              </div>
              <div class="batch-header-right" @click.stop>
                <n-button size="small" class="export-pdf-btn" @click="doBatchPdfExport(batch, batchIndex)">导出 PDF</n-button>
                <template v-if="batch.supplier_name">
                  <n-tag type="success" :bordered="false" strong>✓ 已分配给：{{ batch.supplier_name }}</n-tag>
                </template>
                <template v-else>
                  <n-button size="small" type="primary" @click="openSupplierModal(batch)">关联手工商家</n-button>
                </template>
                <n-popconfirm @positive-click="doDeleteBatch(batch)">
                  <template #trigger>
                    <n-button size="small" type="error" ghost>删除</n-button>
                  </template>
                  确定删除该批次？关联的手工单也会一并删除。
                </n-popconfirm>
              </div>
            </div>

            <!-- Small row (detail), with transition -->
            <div v-show="expandedBatchIds.has(batch.id)" class="batch-detail">
              <!-- Jewelry header row -->
              <div class="batch-jewelry-row">
                <div
                  v-for="j in batch.jewelries"
                  :key="j.jewelry_id"
                  class="jewelry-card"
                  @mouseenter="startHover(j, batch, $event)"
                  @mouseleave="cancelHover()"
                >
                  <n-image
                    v-if="j.jewelry_image"
                    :src="j.jewelry_image"
                    :width="64"
                    :height="64"
                    object-fit="cover"
                    preview-disabled
                  />
                  <div v-else class="jewelry-card-placeholder">{{ j.jewelry_name?.charAt(0) || '?' }}</div>
                  <div class="jewelry-card-label">{{ j.jewelry_id }}</div>
                </div>
              </div>
              <!-- Parts detail table -->
              <n-data-table :columns="batchItemColumns" :data="batch.items" :bordered="false" size="small" />
            </div>
          </div>
        </div>

        <!-- Legacy flat todo list (for orders without batches) -->
        <n-data-table v-if="todoItems.length > 0 && batches.length === 0" :columns="todoColumns" :data="todoItems" :bordered="false" size="small" />
        <n-empty v-if="todoItems.length === 0 && batches.length === 0" description="暂无配件清单，请点击「生成指定配件清单」" style="margin-top: 16px;" />
      </n-card>

      <!-- Parts summary -->
      <n-card title="配件汇总（BOM）">
        <template #header-extra>
          <div v-if="partsSummaryRows.length > 0" class="parts-header-extra">
            <n-button
              size="small"
              class="export-pdf-btn"
              :loading="exportingPartsPdf"
              @click="doPartsSummaryPdfExport"
            >
              导出 PDF
            </n-button>
            <div class="parts-filter">
              <button
                v-for="opt in partsFilterOptions"
                :key="opt.value"
                type="button"
                class="parts-filter-item"
                :class="{ 'parts-filter-item--active': partsFilter === opt.value }"
                @click="partsFilter = opt.value"
              >
                <n-icon
                  :component="partsFilter === opt.value ? opt.iconFilled : opt.iconOutline"
                  :size="16"
                />
                <span>{{ opt.label }}</span>
                <span class="parts-filter-item-count">{{ partsFilterCounts[opt.value] }}</span>
              </button>
            </div>
          </div>
        </template>
        <n-data-table v-if="filteredPartsRows.length > 0" :columns="partsColumns" :data="filteredPartsRows" :bordered="false" size="small" />
        <n-empty
          v-else-if="partsSummaryRows.length === 0"
          description="暂无配件汇总"
          style="margin-top: 16px;"
        />
        <n-empty
          v-else
          :description="partsFilter === 'attention' ? '所有配件均已充足' : '当前筛选下暂无配件'"
          style="margin-top: 16px;"
        />
      </n-card>
    </n-spin>

    <!-- Hover tooltip for jewelry cards -->
    <teleport to="body">
      <div
        v-if="hoverJewelry"
        class="jewelry-hover-tooltip"
        :style="{ left: hoverPosition.x + 'px', top: hoverPosition.y + 'px' }"
      >
        <div style="font-weight: 600; margin-bottom: 6px;">{{ hoverJewelry.jewelry_name }}</div>
        <div v-for="item in hoverParts" :key="item.part_id" class="hover-part-row">
          <span>{{ item._label || item.part_name }}</span>
          <span>需要: {{ item.required_qty }}</span>
          <span>库存: {{ item.stock_qty }}</span>
          <span :style="{ color: item.gap > 0 ? '#d03050' : '#18a058' }">缺口: {{ item.gap }}</span>
        </div>
      </div>
    </teleport>

    <!-- Batch select modal -->
    <n-modal v-model:show="showBatchModal" preset="card" title="选择饰品生成配件清单" style="width: 620px;">
      <n-data-table
        :columns="batchSelectColumns"
        :data="batchJewelryList"
        :row-key="row => row.jewelry_id"
        :row-class-name="row => row.selectable ? '' : 'row-disabled'"
        v-model:checked-row-keys="selectedJewelryIds"
        size="small"
      />
      <template #footer>
        <n-space justify="end">
          <n-button @click="showBatchModal = false">取消</n-button>
          <n-button type="primary" :loading="batchGenerating" :disabled="selectedJewelryIds.length === 0" @click="confirmCreateBatch">
            生成配件清单
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Supplier modal -->
    <n-modal v-model:show="showSupplierModal" preset="card" title="关联手工商家" style="width: 440px;">
      <n-auto-complete
        v-model:value="supplierName"
        :options="supplierOptions"
        placeholder="输入商家名称"
        clearable
      />
      <div style="font-size: 12px; color: #999; margin-top: 6px;">输入商家名称，可选择已有商家或自动新建</div>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showSupplierModal = false">取消</n-button>
          <n-button type="primary" :loading="linkingSupplier" :disabled="!supplierName.trim()" @click="confirmLinkSupplier">
            确定
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Batch customer code modal -->
    <n-modal v-model:show="showBatchCodeModal" preset="card" title="批量填入客户货号" style="width: 420px;">
      <n-form label-placement="left" label-width="80">
        <n-form-item label="前缀">
          <n-input v-model:value="batchCodeForm.prefix" placeholder="如 MG-" />
        </n-form-item>
        <n-form-item label="起始号">
          <n-input-number v-model:value="batchCodeForm.start_number" :min="0" />
        </n-form-item>
        <n-form-item label="位数">
          <n-input-number v-model:value="batchCodeForm.padding" :min="1" :max="6" />
        </n-form-item>
      </n-form>
      <div v-if="batchCodePreview()" style="margin-top: 8px; color: #666; font-size: 12px;">
        预览：{{ batchCodePreview() }}
      </div>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showBatchCodeModal = false">取消</n-button>
          <n-button type="primary" :loading="batchCodeFilling" :disabled="!batchCodeForm.prefix" @click="confirmBatchCode">确定</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NTag, NEmpty, NSelect, NInputNumber, NInput, NDivider, NPopconfirm, NAlert,
  NModal, NImage, NAutoComplete, NIcon, NCollapse, NCollapseItem, NForm, NFormItem, NDatePicker,
} from 'naive-ui'
import {
  Close as CloseIcon, CreateOutline,
  Apps, AppsOutline,
  Warning, WarningOutline,
  CheckmarkCircle, CheckmarkCircleOutline,
} from '@vicons/ionicons5'
import { tsToDateStr, isoToTs } from '@/utils/date'
import ImageUploadModal from '@/components/ImageUploadModal.vue'
import {
  getOrder, getOrderItems, getPartsSummary, updateOrderStatus,
  getTodo, deleteLink, addOrderItem, deleteOrderItem,
  getCostSnapshot, updatePackagingCost, updateExtraInfo,
  getJewelryStatus, getJewelryForBatch, createTodoBatch, getTodoBatches,
  linkBatchSupplier, downloadBatchPdf, downloadPartsSummaryPdf, deleteTodoBatch,
  updateOrderItem, batchFillCustomerCode,
} from '@/api/orders'
import { listParts } from '@/api/parts'
import { listJewelries } from '@/api/jewelries'
import { listSuppliers } from '@/api/suppliers'
import { renderNamedImage, renderOptionWithImage, fmtMoney, fmtPrice, parseNum } from '@/utils/ui'
import { sortPartsSummary, classifyPartRow } from '@/utils/partsSummarySort'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()

const loading = ref(true)
const updating = ref(false)
const addingItem = ref(false)
const savingPkg = ref(false)
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
    await updateExtraInfo(order.value.id, { created_at: dateStr })
    await reloadOrder()
    message.success('创建时间已更新')
    editingCreatedAt.value = false
  } catch (e) {
    message.error(e.response?.data?.detail || '更新失败')
  } finally {
    savingCreatedAt.value = false
  }
}

const orderItems = ref([])
const partsSummaryRows = ref([])
// Parts summary filter: 'all' | 'attention' | 'sufficient' (B 口径: 全局视角)
// 需关注 = 本单不够 (red) 或 本单够但全局紧张 (orange)
// 充足 = 全局都够 (green)
// classifyPartRow is imported from @/utils/partsSummarySort.
const partsFilter = ref('all')
const partsFilterOptions = [
  { value: 'all', label: '全部', iconFilled: Apps, iconOutline: AppsOutline },
  { value: 'attention', label: '需关注', iconFilled: Warning, iconOutline: WarningOutline },
  { value: 'sufficient', label: '充足', iconFilled: CheckmarkCircle, iconOutline: CheckmarkCircleOutline },
]
const partsFilterCounts = computed(() => {
  let attention = 0
  let sufficient = 0
  for (const row of partsSummaryRows.value) {
    const c = classifyPartRow(row)
    if (c === 'attention') attention++
    else if (c === 'sufficient') sufficient++
  }
  return { all: partsSummaryRows.value.length, attention, sufficient }
})
const filteredPartsRows = computed(() => {
  if (partsFilter.value === 'all') return partsSummaryRows.value
  return partsSummaryRows.value.filter((row) => classifyPartRow(row) === partsFilter.value)
})
// Sort priority: red (insufficient) → orange (global contention) → green (all ok)
// sortPartsSummary / classifyPartRow live in @/utils/partsSummarySort
// (pure functions, unit-tested). Imported at the top of this file.
const todoItems = ref([])
const snapshot = ref(null)
const expandedKeys = ref([])
const packagingCost = ref(null)

// --- Extra Info ---
const extraInfo = ref({
  barcode_text: '',
  barcode_image: null,
  mark_text: '',
  mark_image: null,
  note: '',
})
const savingExtraInfo = ref(false)
const showImageUpload = ref(false)
const imageUploadTarget = ref('')

function initExtraInfo(o) {
  extraInfo.value = {
    barcode_text: o.barcode_text || '',
    barcode_image: o.barcode_image || null,
    mark_text: o.mark_text || '',
    mark_image: o.mark_image || null,
    note: o.note || '',
  }
}

async function saveExtraInfo() {
  savingExtraInfo.value = true
  try {
    await updateExtraInfo(order.value.id, extraInfo.value)
    message.success('附加信息已保存')
  } catch (err) {
    message.error('保存失败')
  } finally {
    savingExtraInfo.value = false
  }
}

function openImageUpload(target) {
  imageUploadTarget.value = target
  showImageUpload.value = true
}

function onImageUploaded(url) {
  if (imageUploadTarget.value === 'barcode') {
    extraInfo.value.barcode_image = url
  } else {
    extraInfo.value.mark_image = url
  }
}

function clearImage(target) {
  if (target === 'barcode') {
    extraInfo.value.barcode_image = null
  } else {
    extraInfo.value.mark_image = null
  }
}

// --- Customer Code inline edit + batch fill ---
const editingCustomerCode = ref(null)
const editingCodeValue = ref('')
const checkedItemIds = ref([])
const showBatchCodeModal = ref(false)
const batchCodeForm = ref({ prefix: '', start_number: 1, padding: 2 })
const batchCodeFilling = ref(false)

function startEditCode(item) {
  editingCustomerCode.value = item.id
  editingCodeValue.value = item.customer_code || ''
}

async function saveCustomerCode(item) {
  const value = editingCodeValue.value.trim() || null
  try {
    await updateOrderItem(order.value.id, item.id, { customer_code: value })
    item.customer_code = value
  } catch (err) {
    message.error('保存失败')
  }
  editingCustomerCode.value = null
}

function batchCodePreview() {
  const { prefix, start_number, padding } = batchCodeForm.value
  const count = checkedItemIds.value.length
  if (count === 0 || !prefix) return ''
  const codes = []
  for (let i = 0; i < Math.min(count, 5); i++) {
    codes.push(prefix + String(start_number + i).padStart(padding, '0'))
  }
  if (count > 5) codes.push('...')
  return codes.join(', ')
}

async function confirmBatchCode() {
  batchCodeFilling.value = true
  try {
    await batchFillCustomerCode(order.value.id, {
      item_ids: checkedItemIds.value,
      ...batchCodeForm.value,
    })
    showBatchCodeModal.value = false
    checkedItemIds.value = []
    await reloadOrder()
    message.success('批量填入成功')
  } catch (err) {
    message.error('批量填入失败')
  } finally {
    batchCodeFilling.value = false
  }
}

const jewelryMap = ref({})
const jewelryOptions = ref([])

const newItem = reactive({ jewelry_id: null, quantity: 1, unit_price: 0, remarks: '' })

const statusColor = { '待生产': 'default', '生产中': 'info', '已完成': 'success', '已取消': 'error' }
const statusFlow = { '待生产': '生产中', '生产中': '已完成' }
const statusFlowLabel = { '待生产': '开始生产', '生产中': '标记完成' }

const nextStatus = computed(() => order.value ? statusFlow[order.value.status] : null)
const nextStatusLabel = computed(() => order.value ? statusFlowLabel[order.value.status] : null)
const canEditItems = computed(() => order.value?.status === '待生产')
const canInlineEdit = computed(() => ['待生产', '生产中'].includes(order.value?.status))
const canEditCustomerCode = computed(() => order.value?.status !== '已取消')

// Inline editing for quantity / unit_price
const inlineEditing = ref({})
const inlineSaving = ref({})
const inlineKey = (rowId, field) => `${rowId}_${field}`

const startInline = (row, field) => {
  if (!canInlineEdit.value) return
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
    await updateOrderItem(order.value.id, row.id, { [field]: value })
    message.success('已保存')
    await reloadOrder()
  } catch (e) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    delete inlineSaving.value[key]
    cancelInline(row.id, field)
  }
}

// --- Jewelry status ---
const jewelryStatusMap = ref({})

async function loadJewelryStatus() {
  try {
    const { data } = await getJewelryStatus(route.params.id)
    // Use array to support duplicate jewelry_id across order items
    jewelryStatusMap.value = data
  } catch (_) {
    jewelryStatusMap.value = {}
  }
}

// --- Batch state ---
const batches = ref([])
const expandedBatchIds = ref(new Set())
const showBatchModal = ref(false)
const batchJewelryList = ref([])
const selectedJewelryIds = ref([])
const batchQuantities = ref({})  // jewelry_id → user-specified quantity
const batchGenerating = ref(false)

async function loadBatches() {
  try {
    const { data } = await getTodoBatches(route.params.id)
    batches.value = data.batches
  } catch (_) {
    batches.value = []
  }
}

async function loadJewelryForBatch() {
  try {
    const { data } = await getJewelryForBatch(route.params.id)
    batchJewelryList.value = data
  } catch (_) {
    batchJewelryList.value = []
  }
}

function toggleBatch(batchId) {
  const s = new Set(expandedBatchIds.value)
  if (s.has(batchId)) {
    s.delete(batchId)
  } else {
    s.add(batchId)
  }
  expandedBatchIds.value = s
}

function formatBatchDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleString('zh-CN')
}

async function openBatchModal() {
  selectedJewelryIds.value = []
  batchQuantities.value = {}
  await loadJewelryForBatch()
  // Initialize quantities to remaining_quantity
  for (const item of batchJewelryList.value) {
    if (item.selectable) {
      batchQuantities.value[item.jewelry_id] = item.remaining_quantity
    }
  }
  showBatchModal.value = true
}

async function confirmCreateBatch() {
  // Build items with quantities
  const items = selectedJewelryIds.value.map(jid => ({
    jewelry_id: jid,
    quantity: batchQuantities.value[jid] || 0,
  }))
  // Validate
  for (const item of items) {
    if (!item.quantity || item.quantity <= 0) {
      message.warning('请为所有已选饰品填写数量')
      return
    }
  }
  dialog.warning({
    title: '确认',
    content: '会根据已选择的饰品生成指定的配件清单，确定要生成吗？',
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      batchGenerating.value = true
      try {
        await createTodoBatch(route.params.id, items)
        showBatchModal.value = false
        message.success('配件清单已生成')
        await loadBatches()
        await loadJewelryStatus()
      } catch (e) {
        message.error(e.response?.data?.detail || '生成失败')
      } finally {
        batchGenerating.value = false
      }
    },
  })
}

// --- Batch PDF export ---
async function doBatchPdfExport(batch, index) {
  try {
    const { data } = await downloadBatchPdf(route.params.id, batch.id)
    const url = window.URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = `配件清单_${route.params.id}_批次${index + 1}.pdf`
    a.click()
    window.URL.revokeObjectURL(url)
  } catch (_) {
    message.error('PDF 下载失败')
  }
}

const exportingPartsPdf = ref(false)
async function doPartsSummaryPdfExport() {
  const partIds = filteredPartsRows.value.map((r) => r.part_id)
  if (partIds.length === 0) {
    message.warning('当前筛选下无配件可导出')
    return
  }
  exportingPartsPdf.value = true
  try {
    const { data } = await downloadPartsSummaryPdf(route.params.id, partIds)
    const url = window.URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = `配件汇总_${route.params.id}.pdf`
    a.click()
    window.URL.revokeObjectURL(url)
  } catch (_) {
    message.error('PDF 下载失败')
  } finally {
    exportingPartsPdf.value = false
  }
}

// --- Hover tooltip for jewelry cards ---
const hoverTimer = ref(null)
const hoverJewelry = ref(null)
const hoverParts = ref([])
const hoverPosition = ref({ x: 0, y: 0 })

function startHover(jewelry, batch, event) {
  cancelHover()
  hoverTimer.value = setTimeout(() => {
    hoverJewelry.value = jewelry
    // Show batch-level part info (items include stock_qty, required_qty, gap)
    // If batch has only one jewelry, these are exactly its parts.
    // For multi-jewelry batches, label accordingly.
    const isSingleJewelry = batch.jewelries.length === 1
    hoverParts.value = (batch.items || []).map((item) => ({
      ...item,
      _label: isSingleJewelry ? item.part_name : `${item.part_name} (批次合计)`,
    }))
    hoverPosition.value = { x: event.clientX + 12, y: event.clientY + 12 }
  }, 1000)
}

function cancelHover() {
  if (hoverTimer.value) clearTimeout(hoverTimer.value)
  hoverTimer.value = null
  hoverJewelry.value = null
  hoverParts.value = []
}

onBeforeUnmount(() => {
  cancelHover()
})

// --- Supplier modal state ---
const showSupplierModal = ref(false)
const supplierBatchId = ref(null)
const supplierName = ref('')
const supplierOptions = ref([])
const linkingSupplier = ref(false)

function openSupplierModal(batch) {
  supplierBatchId.value = batch.id
  supplierName.value = ''
  showSupplierModal.value = true
  loadSuppliers()
}

async function loadSuppliers() {
  try {
    const { data } = await listSuppliers({ type: 'handcraft' })
    supplierOptions.value = data.map((s) => ({ label: s.name, value: s.name }))
  } catch (_) {
    supplierOptions.value = []
  }
}

async function confirmLinkSupplier() {
  if (!supplierName.value.trim()) return
  linkingSupplier.value = true
  try {
    const { data } = await linkBatchSupplier(route.params.id, supplierBatchId.value, supplierName.value.trim())
    showSupplierModal.value = false
    message.success('已关联手工商家')
    router.push(`/handcraft/${data.handcraft_order_id}`)
  } catch (e) {
    message.error(e.response?.data?.detail || '关联失败')
  } finally {
    linkingSupplier.value = false
  }
}

const doDeleteBatch = async (batch) => {
  try {
    await deleteTodoBatch(route.params.id, batch.id)
    message.success('批次已删除')
    await reloadOrder()
  } catch (e) {
    message.error(e.response?.data?.detail || '删除失败')
  }
}

// --- Existing functions ---
const onNewJewelrySelect = (v) => {
  if (!v) { newItem.unit_price = 0; return }
  const j = jewelryMap.value[v]
  newItem.unit_price = j?.wholesale_price ?? 0
}

const savePackagingCost = async () => {
  if (!order.value) return
  savingPkg.value = true
  try {
    await updatePackagingCost(order.value.id, { packaging_cost: packagingCost.value || 0 })
    message.success('包装费已保存')
    await reloadOrder()
  } finally {
    savingPkg.value = false
  }
}

const loadSnapshot = async () => {
  try {
    const { data } = await getCostSnapshot(route.params.id)
    snapshot.value = data
  } catch (_) {
    snapshot.value = null
  }
}

const reloadOrder = async () => {
  const id = route.params.id
  const [oRes, iRes, sRes] = await Promise.all([
    getOrder(id),
    getOrderItems(id),
    getPartsSummary(id),
  ])
  order.value = oRes.data
  packagingCost.value = oRes.data.packaging_cost ?? null
  initExtraInfo(oRes.data)
  orderItems.value = iRes.data.map((i) => ({
    ...i,
    jewelry_name: jewelryMap.value[i.jewelry_id]?.name || i.jewelry_id,
    jewelry_image: jewelryMap.value[i.jewelry_id]?.image || '',
  }))

  // parts-summary now returns list[dict] with part_id, part_name, part_image, total_qty, remaining_qty
  partsSummaryRows.value = sortPartsSummary(Array.isArray(sRes.data)
    ? sRes.data
    : Object.entries(sRes.data).map(([part_id, total_qty]) => ({
        part_id,
        part_name: part_id,
        part_image: null,
        total_qty,
        current_stock: 0,
        reserved_qty: 0,
        global_demand: 0,
        remaining_qty: total_qty,
      })))

  await loadTodo()
  await loadBatches()
  await loadJewelryStatus()
  await loadSnapshot()
}

const doAddItem = async () => {
  if (!newItem.jewelry_id) { message.warning('请选择饰品'); return }
  addingItem.value = true
  try {
    await addOrderItem(order.value.id, {
      jewelry_id: newItem.jewelry_id,
      quantity: newItem.quantity,
      unit_price: newItem.unit_price,
      remarks: newItem.remarks || undefined,
    })
    message.success('饰品已添加')
    newItem.jewelry_id = null
    newItem.quantity = 1
    newItem.unit_price = 0
    newItem.remarks = ''
    await reloadOrder()
  } finally {
    addingItem.value = false
  }
}

const doDeleteItem = async (row) => {
  await deleteOrderItem(order.value.id, row.id)
  message.success('已删除')
  await reloadOrder()
}

const advanceStatus = async () => {
  if (!nextStatus.value) return
  updating.value = true
  try {
    const { data } = await updateOrderStatus(order.value.id, nextStatus.value)
    order.value = data
    packagingCost.value = data.packaging_cost ?? null
    message.success('状态已更新')
    await reloadOrder()
  } finally {
    updating.value = false
  }
}

const loadTodo = async () => {
  if (!order.value) return
  try {
    const { data } = await getTodo(order.value.id)
    todoItems.value = data
  } catch (_) {
    todoItems.value = []
  }
}

const doDeleteTodoLink = (todoRow, prod) => {
  dialog.warning({
    title: '解除关联',
    content: `确认解除配件「${todoRow.part_name || todoRow.part_id}」与生产单「${prod.order_id}」的关联？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteLink(prod.link_id)
        message.success('已解除关联')
        await loadTodo()
      } catch (_) {}
    },
  })
}

const prodStatusLabel = {
  '未送出': '未送出',
  '制作中': '制作中',
  '已收回': '已收回',
}
const prodStatusBadge = {
  '未送出': 'badge-gray',
  '制作中': 'badge-blue',
  '已收回': 'badge-green',
  '已采购': 'badge-green',
}

const jewelryStatusColorMap = {
  '等待配件备齐': { color: '#fa8c16', bg: '#fff7e6' },
  '等待发往手工': { color: '#13c2c2', bg: '#e6fffb' },
  '等待手工返回': { color: '#1890ff', bg: '#e6f7ff' },
  '完成备货': { color: '#52c41a', bg: '#f6ffed' },
}

const itemColumns = computed(() => {
  const cols = []
  if (canEditCustomerCode.value) {
    cols.push({ type: 'selection', width: 40 })
  }
  cols.push(
    { title: '饰品编号', key: 'jewelry_id', width: 110 },
    {
      title: '客户货号',
      key: 'customer_code',
      width: 120,
      render(row) {
        if (canEditCustomerCode.value && editingCustomerCode.value === row.id) {
          return h(NInput, {
            value: editingCodeValue.value,
            size: 'small',
            autofocus: true,
            onUpdateValue: (v) => { editingCodeValue.value = v },
            onBlur: () => saveCustomerCode(row),
            onKeydown: (e) => { if (e.key === 'Enter') saveCustomerCode(row) },
          })
        }
        if (!canEditCustomerCode.value) {
          return h('span', { style: { color: row.customer_code ? '#333' : '#ccc' } }, row.customer_code || '—')
        }
        return h('span', {
          style: {
            cursor: 'pointer',
            color: row.customer_code ? '#333' : '#ccc',
          },
          onClick: () => startEditCode(row),
        }, row.customer_code || '—')
      },
    },
    {
      title: '饰品',
      key: 'jewelry_name',
      minWidth: 180,
      render: (row) => renderNamedImage(row.jewelry_name, row.jewelry_image, row.jewelry_name),
    },
    {
      title: '数量', key: 'quantity',
      render(row) {
        const key = inlineKey(row.id, 'quantity')
        if (key in inlineEditing.value) {
          return h(NInputNumber, {
            value: inlineEditing.value[key],
            min: 1,
            size: 'small',
            style: 'width: 90px;',
            autofocus: true,
            'onUpdate:value': (v) => { inlineEditing.value[key] = v },
            onBlur: () => { if (key in inlineEditing.value) saveInline(row, 'quantity', inlineEditing.value[key]) },
            onKeydown: (e) => {
              if (e.key === 'Enter') saveInline(row, 'quantity', inlineEditing.value[key])
              if (e.key === 'Escape') { e.preventDefault(); cancelInline(row.id, 'quantity') }
            },
          })
        }
        if (!canInlineEdit.value) return row.quantity
        return h('span', { class: 'editable-cell', onClick: () => startInline(row, 'quantity') }, row.quantity)
      },
    },
    {
      title: '单价', key: 'unit_price',
      render(row) {
        const key = inlineKey(row.id, 'unit_price')
        if (key in inlineEditing.value) {
          return h(NInputNumber, {
            value: inlineEditing.value[key],
            min: 0,
            precision: 7,
            format: fmtPrice,
            parse: parseNum,
            size: 'small',
            style: 'width: 120px;',
            autofocus: true,
            'onUpdate:value': (v) => { inlineEditing.value[key] = v },
            onBlur: () => { if (key in inlineEditing.value) saveInline(row, 'unit_price', inlineEditing.value[key]) },
            onKeydown: (e) => {
              if (e.key === 'Enter') saveInline(row, 'unit_price', inlineEditing.value[key])
              if (e.key === 'Escape') { e.preventDefault(); cancelInline(row.id, 'unit_price') }
            },
          })
        }
        const display = row.unit_price != null ? fmtMoney(row.unit_price) : '-'
        if (!canInlineEdit.value) return display
        return h('span', { class: 'editable-cell', onClick: () => startInline(row, 'unit_price') }, display)
      },
    },
    { title: '小计', key: 'subtotal', render: (r) => fmtMoney((r.quantity || 0) * (r.unit_price || 0)) },
    {
      title: '状态',
      key: 'status',
      align: 'center',
      width: 140,
      render(row) {
        // Match by order_item id to handle duplicate jewelry_id
        const statusList = jewelryStatusMap.value
        const match = Array.isArray(statusList)
          ? statusList.find((s) => s.jewelry_id === row.jewelry_id)
          : null
        const status = match?.status
        const c = jewelryStatusColorMap[status] || { color: '#999', bg: '#f5f5f5' }
        return h(NTag, {
          size: 'small',
          bordered: false,
          style: { color: c.color, backgroundColor: c.bg },
        }, { default: () => status || '—' })
      },
    },
    { title: '备注', key: 'remarks', render: (r) => r.remarks || '-' },
  )
  if (canEditItems.value) {
    cols.push({
      title: '操作',
      key: 'actions',
      width: 80,
      render: (row) =>
        h(NPopconfirm, { onPositiveClick: () => doDeleteItem(row) }, {
          trigger: () => h(NButton, { size: 'small', type: 'error' }, () => '删除'),
          default: () => `确认删除「${row.jewelry_name || row.jewelry_id}」？`,
        }),
    })
  }
  return cols
})

const snapshotColumns = [
  {
    type: 'expand',
    renderExpand: (row) => {
      return h('div', { style: 'padding: 8px 0 8px 32px;' }, [
        h(NDataTable, {
          columns: bomDetailColumns,
          data: row.bom_details || [],
          bordered: false,
          size: 'small',
        }),
      ])
    },
  },
  { title: '饰品', key: 'jewelry_name', minWidth: 160 },
  { title: '数量', key: 'quantity', width: 80 },
  { title: '售价单价', key: 'unit_price', width: 100, render: (r) => r.unit_price != null ? fmtMoney(r.unit_price) : '-' },
  { title: '手工费', key: 'handcraft_cost', width: 100, render: (r) => r.handcraft_cost != null ? fmtMoney(r.handcraft_cost) : '-' },
  { title: '饰品单位成本', key: 'jewelry_unit_cost', width: 120, render: (r) => fmtMoney(r.jewelry_unit_cost) },
  { title: '饰品总成本', key: 'jewelry_total_cost', width: 120, render: (r) => fmtMoney(r.jewelry_total_cost) },
]

const bomDetailColumns = [
  { title: '配件', key: 'part_name', minWidth: 140, render: (r) => r.part_name || r.part_id },
  { title: '配件单位成本', key: 'unit_cost', width: 120, render: (r) => r.unit_cost != null ? fmtMoney(r.unit_cost) : '-' },
  { title: 'BOM 用量', key: 'qty_per_unit', width: 100 },
  { title: '小计', key: 'subtotal', width: 100, render: (r) => r.subtotal != null ? fmtMoney(r.subtotal) : '-' },
]

const todoColumns = [
  { title: '配件编号', key: 'part_id', width: 110 },
  {
    title: '配件',
    key: 'part_name',
    minWidth: 160,
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name),
  },
  { title: '需要数量', key: 'required_qty', width: 100 },
  {
    title: '库存数量',
    key: 'stock_qty',
    width: 100,
    render: (r) => r.stock_qty != null ? r.stock_qty : '-',
  },
  {
    title: '缺口',
    key: 'gap',
    width: 80,
    render: (r) => {
      if (r.gap == null) return '-'
      if (r.gap > 0) return h('span', { style: 'color: #d03050; font-weight: 600;' }, r.gap)
      return h('span', { style: 'color: #18a058;' }, '0')
    },
  },
  {
    title: '生产单状态',
    key: 'linked_production',
    minWidth: 200,
    render: (row) => {
      const prods = row.linked_production || []
      if (prods.length === 0) return h('span', { style: 'color: #999;' }, '-')
      return h('div', { style: 'display: flex; flex-wrap: wrap; gap: 4px;' },
        prods.map((p) => h('span', {
          style: 'display: inline-flex; align-items: center; gap: 4px;',
        }, [
          h('span', {
            class: `badge ${prodStatusBadge[p.status] || 'badge-gray'}`,
            style: 'font-size: 12px;',
          }, `${p.type === 'plating' ? 'EP' : p.type === 'purchase' ? 'PO' : 'HC'}:${p.order_id} ${p.status || ''}`),
          h(NButton, {
            size: 'tiny',
            quaternary: true,
            type: 'error',
            onClick: () => doDeleteTodoLink(row, { ...p, link_id: p.link_id }),
          }, { default: () => '×' }),
        ])),
      )
    },
  },
  {
    title: '完成',
    key: 'is_complete',
    width: 70,
    render: (r) => {
      if (r.is_complete) return h('span', { style: 'color: #18a058; font-weight: 600;' }, 'Yes')
      return h('span', { style: 'color: #d03050;' }, 'No')
    },
  },
]

// --- Batch item columns (used in expanded batch detail) ---
const batchItemColumns = [
  { title: '配件编号', key: 'part_id', width: 110 },
  {
    title: '配件',
    key: 'part_name',
    minWidth: 160,
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name),
  },
  { title: '需要数量', key: 'required_qty', width: 100 },
  {
    title: '库存数量',
    key: 'stock_qty',
    width: 100,
    render: (r) => r.stock_qty != null ? r.stock_qty : '-',
  },
  {
    title: '缺口',
    key: 'gap',
    width: 80,
    render: (r) => {
      if (r.gap == null) return '-'
      if (r.gap > 0) return h('span', { style: 'color: #d03050; font-weight: 600;' }, r.gap)
      return h('span', { style: 'color: #18a058;' }, '0')
    },
  },
  {
    title: '生产单状态',
    key: 'linked_production',
    minWidth: 200,
    render: (row) => {
      const prods = row.linked_production || []
      if (prods.length === 0) return h('span', { style: 'color: #999;' }, '-')
      return h('div', { style: 'display: flex; flex-wrap: wrap; gap: 4px;' },
        prods.map((p) => {
          const prefix = p.type === 'plating' ? 'EP' : p.type === 'purchase' ? 'PO' : 'HC'
          const routePath = p.type === 'plating' ? `/plating/${p.order_id}`
            : p.type === 'purchase' ? `/purchase-orders/${p.order_id}`
            : `/handcraft/${p.order_id}`
          return h('span', {
            class: `badge ${prodStatusBadge[p.status] || 'badge-gray'}`,
            style: 'font-size: 12px; display: inline-flex; align-items: center; gap: 4px;',
          }, [
            h('span', {
              style: 'color: rgb(100,101,232); cursor: pointer; font-size: 12px;',
              onClick: () => router.push(routePath),
            }, `${prefix}:${p.order_id}`),
            p.status || '',
          ])
        }),
      )
    },
  },
  {
    title: '配货状态',
    key: 'is_allocated',
    width: 90,
    render: (r) => {
      if (r.is_allocated) return h('span', { style: 'background: #18a058; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 12px;' }, '已分配')
      return h('span', { style: 'background: #d03050; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 12px;' }, '未分配')
    },
  },
]

// --- Batch select modal columns ---
const batchSelectColumns = [
  {
    type: 'selection',
    disabled(row) { return !row.selectable },
  },
  { title: '饰品编号', key: 'jewelry_id', width: 110 },
  {
    title: '饰品',
    key: 'jewelry_name',
    minWidth: 180,
    render(row) {
      return h('div', { style: 'display:flex;align-items:center;gap:6px' }, [
        row.jewelry_image
          ? h(NImage, { src: row.jewelry_image, width: 28, height: 28, objectFit: 'cover', previewDisabled: true })
          : null,
        row.jewelry_name,
      ])
    },
  },
  {
    title: '数量',
    key: 'remaining_quantity',
    width: 160,
    render(row) {
      if (!row.selectable) {
        return h('span', { style: 'color: #999;' }, row.remaining_quantity)
      }
      const maxQty = row.remaining_quantity
      return h('div', { style: 'display:flex;align-items:center;gap:4px' }, [
        h(NInputNumber, {
          value: batchQuantities.value[row.jewelry_id],
          onUpdateValue: (v) => { batchQuantities.value[row.jewelry_id] = v },
          min: 1,
          max: maxQty,
          precision: 0,
          size: 'small',
          style: 'width: 90px;',
        }),
        h('span', { style: 'color: #999; font-size: 12px;' }, `/ ${maxQty}`),
      ])
    },
  },
  {
    title: '原因',
    key: 'disabled_reason',
    width: 120,
    render(row) {
      if (!row.selectable && row.disabled_reason) {
        return h('span', { style: 'color: #999; font-size: 12px;' }, row.disabled_reason)
      }
      return ''
    },
  },
]

// --- Parts summary columns (updated with remaining_qty) ---
const partsColumns = [
  { title: '配件编号', key: 'part_id' },
  {
    title: '配件',
    key: 'part_name',
    minWidth: 180,
    render(row) {
      return h('div', { style: 'display:flex;align-items:center;gap:6px' }, [
        row.part_image
          ? h(NImage, {
              src: row.part_image,
              width: 28,
              height: 28,
              objectFit: 'cover',
              style: 'cursor: zoom-in; border-radius: 2px;',
            })
          : null,
        row.part_name,
      ])
    },
  },
  { title: '总需求量', key: 'total_qty', align: 'center' },
  { title: '全局总需求', key: 'global_demand', align: 'center' },
  { title: '当前库存', key: 'current_stock', align: 'center' },
  { title: '他人预留', key: 'reserved_qty', align: 'center' },
  {
    title: '剩余需求量',
    key: 'remaining_qty',
    align: 'center',
    render(row) {
      if (row.remaining_qty == null) return '-'
      // Color uses the backend's raw-math globally_sufficient flag so we
      // don't reconstruct (stock - reserved) from ceiled components, which
      // can misclassify around fractional meter boundaries.
      let color = '#52c41a' // green
      if (row.remaining_qty > 0) {
        color = '#ff4d4f' // red
      } else if (row.globally_sufficient === false) {
        color = '#fa8c16' // orange
      }
      return h('span', { style: { color, fontWeight: '500' } }, row.remaining_qty)
    },
  },
]

onMounted(async () => {
  const id = route.params.id
  try {
    // Core data: order, items, parts-summary load first
    // Jewelries load in parallel but non-blocking for items table
    const [oRes, iRes, sRes, jRes] = await Promise.all([
      getOrder(id),
      getOrderItems(id),
      getPartsSummary(id),
      listJewelries(),
    ])
    order.value = oRes.data
    packagingCost.value = oRes.data.packaging_cost ?? null
    initExtraInfo(oRes.data)

    jRes.data.forEach((j) => { jewelryMap.value[j.id] = j })
    jewelryOptions.value = jRes.data
      .filter((j) => j.status === 'active')
      .map((j) => ({
        label: `${j.id} ${j.name}`,
        value: j.id,
        code: j.id,
        name: j.name,
        image: j.image,
      }))

    orderItems.value = iRes.data.map((i) => ({
      ...i,
      jewelry_name: jewelryMap.value[i.jewelry_id]?.name || i.jewelry_id,
      jewelry_image: jewelryMap.value[i.jewelry_id]?.image || '',
    }))

    // parts-summary: support both new list format and legacy dict format
    partsSummaryRows.value = sortPartsSummary(Array.isArray(sRes.data)
      ? sRes.data
      : Object.entries(sRes.data).map(([part_id, total_qty]) => ({
          part_id,
          part_name: part_id,
          part_image: null,
          total_qty,
          current_stock: 0,
          reserved_qty: 0,
          global_demand: 0,
          remaining_qty: total_qty,
        })))

    await Promise.all([
      loadTodo(),
      loadBatches(),
      loadJewelryStatus(),
    ])
    await loadSnapshot()
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
/* Parts summary header-extra: [导出 PDF]  (10px gap)  [filter group] */
.parts-header-extra {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

/* Parts summary filter — icon + text, gray pill when active */
.parts-filter {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.parts-filter-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: none;
  background: transparent;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.6);
  font-family: inherit;
  line-height: 1;
  transition: background 0.15s ease, color 0.15s ease;
}
.parts-filter-item:hover {
  background: rgba(0, 0, 0, 0.04);
  color: rgba(0, 0, 0, 0.85);
}
.parts-filter-item--active {
  background: rgba(0, 0, 0, 0.07);
  color: rgba(0, 0, 0, 0.9);
  font-weight: 600;
}
.parts-filter-item-count {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.38);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.parts-filter-item--active .parts-filter-item-count {
  color: rgba(0, 0, 0, 0.5);
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

/* Batch structure styles */
.batch-row {
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  margin-bottom: 8px;
  overflow: hidden;
}
.batch-header {
  padding: 12px 16px;
  background: #fafafa;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  user-select: none;
}
.batch-header:hover {
  background: #f0f0f0;
}
.batch-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.batch-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.batch-chevron {
  font-size: 14px;
  color: #666;
  width: 14px;
}
.batch-title {
  font-weight: 600;
  font-size: 14px;
}
.batch-date {
  font-size: 12px;
  color: #999;
}
.batch-detail {
  padding: 16px;
  border-top: 1px solid #e8e8e8;
}
.batch-jewelry-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.jewelry-card {
  text-align: center;
  cursor: pointer;
}
.jewelry-card-label {
  font-size: 11px;
  color: #666;
  margin-top: 4px;
}
.jewelry-card-placeholder {
  width: 64px;
  height: 64px;
  background: #f0f0f0;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #999;
  font-size: 18px;
}

/* Hover tooltip */
.jewelry-hover-tooltip {
  position: fixed;
  z-index: 9999;
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  padding: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  max-width: 320px;
  font-size: 13px;
}
.hover-part-row {
  display: flex;
  gap: 12px;
  padding: 2px 0;
  font-size: 12px;
}

/* Disabled rows in batch select modal */
:deep(.row-disabled) {
  opacity: 0.45;
  pointer-events: none;
}
</style>
