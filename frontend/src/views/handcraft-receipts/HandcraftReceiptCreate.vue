<template>
  <div :style="{ maxWidth: isMobile ? '100%' : '1000px' }">
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">新建手工回收单</n-h2>
    </n-space>

    <!-- 头部双列布局：桌面 grid 2-col，移动端单列 -->
    <div
      :style="{
        display: 'grid',
        gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
        gap: '12px 18px',
        marginBottom: '16px',
      }"
    >
      <!-- 第一列：手工商家 -->
      <div>
        <div style="font-size: 12px; color: #6b7280; margin-bottom: 5px; font-weight: 500;">手工商家</div>
        <n-select
          v-model:value="supplierName"
          :options="supplierOptions"
          filterable
          tag
          placeholder="选择或输入商家名称"
          :disabled="supplierLocked"
          style="width: 100%;"
          @update:value="onSupplierChange"
        />
      </div>

      <!-- 第二列：回执编码 -->
      <div>
        <div style="font-size: 12px; color: #6b7280; margin-bottom: 5px; font-weight: 500;">回执编码</div>
        <n-input
          v-model:value="receiptCode"
          placeholder="扫码或输入 5 位编码"
          clearable
          style="width: 100%; --n-border: 1px solid #bcc0f3; --n-border-hover: 1px solid #6366F1; --n-border-focus: 1px solid #6366F1; --n-caret-color: #6366F1;"
          @keyup.enter="applyReceiptCode"
          @blur="applyReceiptCode"
        >
          <template #prefix>
            <span style="color: #6366F1;">⌗</span>
          </template>
        </n-input>
        <div style="font-size: 11px; color: #9ca3af; margin-top: 4px;">
          填入后仅展示该单待回收项；也可只填编码查询
        </div>
      </div>

      <!-- 第三列：创建时间 -->
      <div>
        <div style="font-size: 12px; color: #6b7280; margin-bottom: 5px; font-weight: 500;">创建时间</div>
        <n-date-picker
          v-model:value="createdAtTs"
          type="date"
          clearable
          placeholder="不填则使用当前时间"
          style="width: 100%;"
        />
      </div>

      <!-- 第四列：备注 -->
      <div>
        <div style="font-size: 12px; color: #6b7280; margin-bottom: 5px; font-weight: 500;">备注</div>
        <n-input v-model:value="note" placeholder="选填" style="width: 100%;" />
      </div>
    </div>

    <n-card style="margin-bottom: 16px;">
      <template #header>
        <span style="font-weight: 600;">待回收饰品</span>
        <span style="font-size: 12px; color: #9ca3af; margin-left: 8px; font-weight: 400;">该商家制作中的产出项</span>
      </template>
      <template #header-extra>
        <n-badge :value="partReturnCount" :max="99" :show="partReturnCount > 0">
          <n-button
            size="small"
            style="color: #6366F1; border-color: #c7cbf5; background: #fff;"
            @click="partModalShow = true"
          >
            ＋ 配件回收
          </n-button>
        </n-badge>
      </template>

      <!-- Scope banner：仅在回执码模式下显示 -->
      <div
        v-if="scopeCode"
        style="margin-bottom: 10px; background: #eef6ff; border: 1px solid #cfe3f7; border-radius: 7px; padding: 8px 12px; display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: #2a5d8f;"
      >
        <span>仅显示回执单 <strong>{{ scopeCode }}</strong> 的待回收项</span>
        <span
          style="margin-left: auto; cursor: pointer; opacity: 0.7;"
          @click="clearReceiptScope"
        >✕ 清除</span>
      </div>

      <!-- 配件回收回执条：常驻 -->
      <div
        :class="partReturnCount === 0 ? 'parts-recap parts-recap-empty' : 'parts-recap'"
        style="margin-bottom: 10px; background: #eef1fe; border: 1px solid #d6dafb; border-radius: 7px; padding: 9px 12px; display: flex; align-items: center; gap: 10px; font-size: 12.5px;"
      >
        <span style="color: #6366F1; font-weight: 600; white-space: nowrap;">
          {{ partReturnCount > 0 ? `配件回收 · ${partReturnCount} 项` : '配件回收' }}
        </span>
        <span :style="{ flex: 1, color: partReturnCount > 0 ? '#6b7280' : '#9ca3af' }">
          {{ partReturnCount > 0 ? partReturnSummary : '未选配件退料' }}
        </span>
        <span
          style="color: #6366F1; font-size: 12px; cursor: pointer; white-space: nowrap;"
          @click="partModalShow = true"
        >编辑</span>
      </div>

      <div v-if="supplierName || scopeCode" style="display: flex; gap: 12px; align-items: center; margin-bottom: 12px;">
        <n-input
          v-model:value="filterKeyword"
          placeholder="编号/名称搜索"
          clearable
          :style="{ width: isMobile ? '100%' : '200px' }"
          @update:value="onFilterKeywordChange"
        />
        <span style="font-size: 13px; color: #666;">发出日期</span>
        <n-date-picker
          v-model:value="filterDateOn"
          type="date"
          clearable
          :style="{ width: isMobile ? '100%' : '160px' }"
          @update:value="onFilterDateChange"
        />
      </div>
      <n-spin :show="loadingItems">
        <n-empty
          v-if="!loadingItems && pendingJewelryItems.length === 0"
          :description="fetchError ? '加载失败，请重试' : (supplierName || scopeCode) ? '该商家暂无待回收产出项' : '请先选择商家或输入回执编码'"
          style="margin-top: 16px;"
        />

        <!-- Mobile: card list -->
        <div
          v-if="isMobile && pendingJewelryItems.length > 0"
          style="max-height: 420px; overflow-y: auto;"
        >
          <div
            v-for="row in pendingJewelryItems"
            :key="rowKey(row)"
            :style="{
              border: '1px solid ' + (jewelryCheckedKeys.includes(rowKey(row)) ? '#c7cbf5' : '#e5e7eb'),
              background: jewelryCheckedKeys.includes(rowKey(row)) ? '#f3f4fe' : '#fff',
              borderRadius: '9px',
              padding: '11px',
              marginBottom: '9px',
            }"
          >
            <!-- top row: checkbox + thumbnail + name/id + 剩余 + 手工单 link -->
            <div style="display: flex; align-items: center; gap: 10px;">
              <n-checkbox
                :checked="jewelryCheckedKeys.includes(rowKey(row))"
                @update:checked="(v) => toggleMobileCard(rowKey(row), v)"
              />
              <n-image
                :src="row.item_image || ''"
                width="38"
                height="38"
                object-fit="cover"
                style="border-radius: 7px; flex: none; background: linear-gradient(135deg, #f3d9b1, #d9a441);"
                :fallback-src="''"
                :preview-disabled="!row.item_image"
              />
              <div style="flex: 1; min-width: 0;">
                <div style="font-size: 13.5px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                  {{ row.item_name }}
                  <span v-if="row.is_composite" style="font-size: 11px; padding: 1px 7px; border-radius: 4px; background: #fef3e8; color: #c2700d; font-weight: 500; margin-left: 4px;">组合</span>
                  <span v-else style="font-size: 11px; padding: 1px 7px; border-radius: 4px; background: #eef2ff; color: #4f5bd5; font-weight: 500; margin-left: 4px;">饰品</span>
                </div>
                <div style="font-size: 11px; color: #9ca3af; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                  <span>{{ row.item_id }}</span>
                  <span>· 剩余 {{ getRemaining(row) }}</span>
                  <span
                    style="color: #6366F1; font-weight: 600; cursor: pointer; border-bottom: 1px dashed #c7cbf5; padding-bottom: 1px;"
                    @click.stop="openOrderPeek(row.handcraft_order_id)"
                  >{{ row.handcraft_order_id }} 🗗</span>
                </div>
              </div>
            </div>

            <!-- inputs row: shown when checked -->
            <div
              v-if="jewelryCheckedKeys.includes(rowKey(row))"
              style="display: flex; gap: 8px; margin-top: 10px; padding-top: 10px; border-top: 1px dashed #e5e7eb;"
            >
              <div style="flex: 1;">
                <div style="font-size: 11px; color: #9ca3af; margin-bottom: 3px;">本次回收</div>
                <n-input-number
                  :value="getInput(rowKey(row)).qty"
                  :min="1"
                  :max="getRemaining(row)"
                  :precision="0"
                  :step="1"
                  style="width: 100%;"
                  @update:value="(v) => { getInput(rowKey(row)).qty = v }"
                />
              </div>
              <div style="flex: 1;">
                <div style="font-size: 11px; color: #9ca3af; margin-bottom: 3px;">单价</div>
                <n-input-number
                  :value="getInput(rowKey(row)).price"
                  :min="0"
                  :precision="7"
                  :format="fmtPrice"
                  :parse="parseNum"
                  :step="0.1"
                  style="width: 100%;"
                  @update:value="(v) => { getInput(rowKey(row)).price = v }"
                />
              </div>
              <div style="flex: 1;">
                <div style="font-size: 11px; color: #9ca3af; margin-bottom: 3px;">金额</div>
                <div style="height: 34px; display: flex; align-items: center; font-weight: 600; font-variant-numeric: tabular-nums; font-size: 13px;">
                  {{ fmtMoney((getInput(rowKey(row)).qty || 0) * (getInput(rowKey(row)).price || 0)) }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Desktop: data table -->
        <n-data-table
          v-if="!isMobile && pendingJewelryItems.length > 0"
          :columns="jewelryPendingColumns"
          :data="pendingJewelryItems"
          :bordered="false"
          :row-key="(row) => rowKey(row)"
          :checked-row-keys="jewelryCheckedKeys"
          :max-height="280"
          @update:checked-row-keys="onCheck"
        />
      </n-spin>
    </n-card>

    <!-- 底部常驻操作栏 -->
    <div
      :style="{
        position: 'sticky',
        bottom: 0,
        marginTop: '14px',
        background: '#fff',
        borderTop: '1px solid #e5e7eb',
        padding: isMobile ? '10px 14px calc(10px + env(safe-area-inset-bottom, 0px))' : '12px 18px',
        boxShadow: '0 -6px 16px rgba(0,0,0,.04)',
        zIndex: 10,
      }"
    >
      <!-- Mobile layout: row1 (total + payment), row2 (submit) -->
      <template v-if="isMobile">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 9px;">
          <div style="display: flex; flex-direction: column;">
            <span style="font-size: 11px; color: #9ca3af;">合计金额</span>
            <span style="font-size: 22px; font-weight: 700; color: #6366F1; font-variant-numeric: tabular-nums;">
              ¥ {{ totalAmount }}
            </span>
          </div>
          <n-radio-group v-model:value="status" size="small">
            <n-radio-button value="未付款">未付款</n-radio-button>
            <n-radio-button value="已付款">已付款</n-radio-button>
          </n-radio-group>
        </div>
        <n-button
          type="primary"
          :loading="submitting"
          style="width: 100%; height: 46px; font-size: 15.5px; font-weight: 600; border-radius: 10px; box-shadow: 0 4px 12px rgba(99,102,241,.3);"
          @click="submit"
        >
          提交回收单 →
        </n-button>
      </template>

      <!-- Desktop layout: flex row -->
      <template v-else>
        <div style="display: flex; align-items: center; gap: 16px;">
          <!-- 合计金额 -->
          <div style="display: flex; flex-direction: column;">
            <span style="font-size: 11px; color: #9ca3af;">合计金额</span>
            <span style="font-size: 26px; font-weight: 700; color: #6366F1; line-height: 1.1; font-variant-numeric: tabular-nums;">
              <small style="font-size: 14px; font-weight: 600; margin-right: 2px;">¥</small>{{ totalAmount }}
            </span>
          </div>
          <!-- 付款状态 -->
          <div style="display: flex; flex-direction: column; gap: 5px;">
            <span style="font-size: 11px; color: #9ca3af;">付款状态</span>
            <n-radio-group v-model:value="status" size="small">
              <n-radio-button value="未付款">未付款</n-radio-button>
              <n-radio-button value="已付款">已付款</n-radio-button>
            </n-radio-group>
          </div>
          <div style="flex: 1;" />
          <!-- 提交按钮 -->
          <n-button
            type="primary"
            :loading="submitting"
            style="height: 42px; padding: 0 30px; font-size: 15px; font-weight: 600; border-radius: 8px; box-shadow: 0 4px 12px rgba(99,102,241,.28);"
            @click="submit"
          >
            提交回收单 →
          </n-button>
        </div>
      </template>
    </div>

    <!-- Part Return Modal -->
    <part-return-modal
      :show="partModalShow"
      :parts="pendingPartItems"
      :selections="partReturnSel"
      :is-mobile="isMobile"
      @confirm="onPartConfirm"
      @cancel="partModalShow = false"
      @update:show="partModalShow = $event"
    />

    <!-- Handcraft Order Peek Modal -->
    <handcraft-order-peek-modal
      :show="peekShow"
      :order-id="peekOrderId"
      @update:show="peekShow = $event"
    />

    <!-- Cost Diff Modal -->
    <n-modal v-model:show="costDiffVisible" :mask-closable="false" preset="card" title="手工费成本变动确认" :style="{ width: isMobile ? '95vw' : '550px' }">
      <div style="margin-bottom: 12px; color: #333;">
        当前手工费与配件已有手工费金额不相同，是否更新手工费成本？
      </div>
      <div style="margin-bottom: 12px; color: #999; font-size: 12px;">来源：{{ costDiffSourceId }}</div>
      <n-data-table
        :columns="[
          { title: '配件编号', key: 'part_id', width: 160 },
          { title: '配件名称', key: 'part_name', minWidth: 120 },
          { title: '原手工费', key: 'current_value', width: 120, render: (r) => r.current_value != null ? `¥ ${fmtMoney(r.current_value)}` : '-' },
          { title: '更新手工费', key: 'new_value', width: 120, render: (r) => h('span', { style: 'color: #d03050; font-weight: 600;' }, `¥ ${fmtMoney(r.new_value)}`) },
        ]"
        :data="costDiffs"
        :bordered="false"
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
import { ref, reactive, computed, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem,
  NCard, NH2, NRadioGroup, NRadio, NRadioButton, NDataTable, NSpin, NEmpty, NImage, NModal, NDatePicker, NBadge, NCheckbox,
} from 'naive-ui'
import { listHandcraftPendingReceiveItems, createHandcraftReceipt } from '@/api/handcraftReceipts'
import { getHandcraftSuppliers, getHandcraftByReceiptCode } from '@/api/handcraft'
import HandcraftOrderPeekModal from '@/components/HandcraftOrderPeekModal.vue'
import { batchUpdatePartCosts } from '@/api/parts'
import { renderNamedImage, fmtMoney, fmtPrice, parseNum } from '@/utils/ui'
import { tsToDateStr } from '@/utils/date'
import { useIsMobile } from '@/composables/useIsMobile'
import PartReturnModal from './PartReturnModal.vue'

const router = useRouter()
const message = useMessage()
const { isMobile } = useIsMobile()
const supplierName = ref(null)
const note = ref('')
const status = ref('未付款')
const createdAtTs = ref(null)
const submitting = ref(false)
const loadingItems = ref(false)
const supplierOptions = ref([])
// Receipt code scoped query state
const receiptCode = ref('')
const scopeCode = ref(null)       // 已生效的回执码过滤；null = 商家模式
const supplierLocked = ref(false) // 回执码模式下锁定商家选择

// Pending items separated by type
const pendingPartItems = ref([])
const pendingJewelryItems = ref([])
const partCheckedKeys = ref([])
const jewelryCheckedKeys = ref([])

// Store user input for qty and price per item key
const itemInputs = reactive({})

// Filter state
const filterKeyword = ref('')
const filterDateOn = ref(null)
let debounceTimer = null
let fetchSeq = 0
const fetchError = ref(false)

// Part return modal
const partModalShow = ref(false)
const partReturnSel = reactive({})   // {partItemId (string): qty}
const partReturnCount = computed(() => Object.keys(partReturnSel).length)
const onPartConfirm = (sel) => {
  // Replace all with new selection
  Object.keys(partReturnSel).forEach((k) => delete partReturnSel[k])
  Object.entries(sel).forEach(([k, v]) => { if (v > 0) partReturnSel[k] = v })
  partModalShow.value = false
}

// Cost diff modal
const costDiffVisible = ref(false)
const costDiffs = ref([])
const costDiffSourceId = ref('')
const costDiffUpdating = ref(false)

const unitOptions = [
  { label: '个', value: '个' },
  { label: '条', value: '条' },
  { label: '米', value: '米' },
  { label: 'g', value: 'g' },
  { label: 'kg', value: 'kg' },
]

const rowKey = (row) => `${row.is_output ? 'output' : row.item_type}_${row.id}`
const getRemaining = (item) => item.qty - (item.received_qty || 0)

const getInput = (key) => {
  if (!itemInputs[key]) {
    itemInputs[key] = { qty: null, price: null, unit: '个', weight: null, weight_unit: 'g' }
  }
  return itemInputs[key]
}

const totalAmount = computed(() => {
  let sum = 0
  for (const key of jewelryCheckedKeys.value) {
    const input = itemInputs[key]
    if (input) sum += (input.qty || 0) * (input.price || 0)
  }
  return fmtMoney(sum)
})

// Recap chip: summarize selected part returns
const partReturnSummary = computed(() => {
  const entries = Object.entries(partReturnSel)
  if (entries.length === 0) return ''
  return entries.map(([id, qty]) => {
    const part = pendingPartItems.value.find((p) => String(p.id) === String(id))
    const name = part ? part.item_name : `ID:${id}`
    return `${name} ×${qty}`
  }).join('、')
})

const fetchPendingItems = async () => {
  const seq = ++fetchSeq
  if (!supplierName.value && !scopeCode.value) {
    pendingPartItems.value = []
    pendingJewelryItems.value = []
    loadingItems.value = false
    fetchError.value = false
    return
  }
  loadingItems.value = true
  fetchError.value = false
  try {
    const params = {}
    if (supplierName.value) params.supplier_name = supplierName.value
    if (scopeCode.value) params.receipt_code = scopeCode.value
    if (filterKeyword.value) params.keyword = filterKeyword.value
    if (filterDateOn.value) {
      const d = new Date(filterDateOn.value)
      params.date_on = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    }
    const { data } = await listHandcraftPendingReceiveItems(params)
    if (seq !== fetchSeq) return
    const parts = []
    const jewelries = []
    for (const item of data) {
      const key = `${item.is_output ? 'output' : item.item_type}_${item.id}`
      if (!itemInputs[key]) {
        itemInputs[key] = { qty: getRemaining(item), price: null, unit: item.unit || '个', weight: null, weight_unit: 'g' }
      }
      if (item.is_output) {
        jewelries.push(item)
      } else {
        parts.push(item)
      }
    }
    pendingPartItems.value = parts
    pendingJewelryItems.value = jewelries
  } catch (_) {
    if (seq !== fetchSeq) return
    pendingPartItems.value = []
    pendingJewelryItems.value = []
    partCheckedKeys.value = []
    jewelryCheckedKeys.value = []
    fetchError.value = true
    message.error('加载待回收项目失败')
  } finally {
    if (seq === fetchSeq) loadingItems.value = false
  }
}

// Receipt code query logic
const applyReceiptCode = async () => {
  const code = receiptCode.value.trim().toUpperCase()
  if (!code) return
  // Don't re-apply if already the active scope
  if (code === scopeCode.value) return
  if (code.length !== 5) { message.warning('请输入 5 位回执编号'); return }
  try {
    const { data: order } = await getHandcraftByReceiptCode(code)
    supplierName.value = order.supplier_name
    supplierLocked.value = true
    scopeCode.value = code
    partCheckedKeys.value = []
    jewelryCheckedKeys.value = []
    await fetchPendingItems()
  } catch (_) {
    message.error(`无此回执编号：${code}`)
  }
}

const clearReceiptScope = async () => {
  scopeCode.value = null
  supplierLocked.value = false
  receiptCode.value = ''
  await fetchPendingItems()
}

const onSupplierChange = async (val) => {
  supplierName.value = val
  partCheckedKeys.value = []
  jewelryCheckedKeys.value = []
  filterKeyword.value = ''
  filterDateOn.value = null
  await fetchPendingItems()
}

const onFilterKeywordChange = () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    partCheckedKeys.value = []
    jewelryCheckedKeys.value = []
    fetchPendingItems()
  }, 300)
}

const onFilterDateChange = () => {
  partCheckedKeys.value = []
  jewelryCheckedKeys.value = []
  fetchPendingItems()
}

const onCheck = (keys) => {
  jewelryCheckedKeys.value = keys
}

const toggleMobileCard = (key, checked) => {
  if (checked) {
    if (!jewelryCheckedKeys.value.includes(key)) jewelryCheckedKeys.value = [...jewelryCheckedKeys.value, key]
  } else {
    jewelryCheckedKeys.value = jewelryCheckedKeys.value.filter((k) => k !== key)
  }
}

const partPendingColumns = [
  { type: 'selection' },
  { title: '手工单号', key: 'handcraft_order_id', width: 110 },
  {
    title: '配件',
    key: 'item_name',
    minWidth: 160,
    render: (row) => renderNamedImage(row.item_name, row.item_image, row.item_name, 40, row.is_composite ? '组合' : null),
  },
  { title: '颜色', key: 'color', width: 80, render: (r) => r.color || '-' },
  {
    title: '发出日期',
    key: 'created_at',
    width: 100,
    render: (r) => r.created_at ? new Date(r.created_at).toLocaleDateString('zh-CN') : '-',
  },
  { title: '总数量', key: 'qty', width: 80 },
  { title: '已回收', key: 'received_qty', width: 80, render: (r) => r.received_qty ?? 0 },
  { title: '剩余', key: 'remaining', width: 80, render: (r) => getRemaining(r) },
  {
    title: '本次回收',
    key: 'input_qty',
    width: 120,
    render: (row) => {
      const input = getInput(rowKey(row))
      return h(NInputNumber, {
        value: input.qty,
        min: 0.0001,
        max: getRemaining(row),
        precision: 4,
        step: 1,
        size: 'small',
        style: 'width: 110px;',
        'onUpdate:value': (v) => { input.qty = v },
      })
    },
  },
  {
    title: '重量',
    key: 'input_weight',
    width: 140,
    render: (row) => {
      const input = getInput(rowKey(row))
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
    title: '手工费单价',
    key: 'input_price',
    width: 120,
    render: (row) => {
      const input = getInput(rowKey(row))
      return h(NInputNumber, {
        value: input.price,
        min: 0,
        precision: 7,
        format: fmtPrice,
        parse: parseNum,
        step: 0.1,
        size: 'small',
        style: 'width: 110px;',
        'onUpdate:value': (v) => { input.price = v },
      })
    },
  },
]

const peekShow = ref(false)
const peekOrderId = ref(null)
const openOrderPeek = (orderId) => { peekOrderId.value = orderId; peekShow.value = true }

const jewelryPendingColumns = [
  { type: 'selection' },
  {
    title: '产出项',
    key: 'item_name',
    minWidth: 160,
    render: (row) => renderNamedImage(row.item_name, row.item_image, row.item_name, 40, row.is_composite ? '组合' : null),
  },
  {
    title: '发出日期',
    key: 'created_at',
    width: 100,
    render: (r) => r.created_at ? new Date(r.created_at).toLocaleDateString('zh-CN') : '-',
  },
  { title: '总数量', key: 'qty', width: 80 },
  { title: '已回收', key: 'received_qty', width: 80, render: (r) => r.received_qty ?? 0 },
  { title: '剩余', key: 'remaining', width: 80, render: (r) => getRemaining(r) },
  {
    title: '本次回收',
    key: 'input_qty',
    width: 120,
    render: (row) => {
      const input = getInput(rowKey(row))
      return h(NInputNumber, {
        value: input.qty,
        min: 1,
        max: getRemaining(row),
        precision: 0,
        step: 1,
        size: 'small',
        style: 'width: 110px;',
        'onUpdate:value': (v) => { input.qty = v },
      })
    },
  },
  {
    title: '重量',
    key: 'input_weight',
    width: 140,
    render: (row) => {
      const input = getInput(rowKey(row))
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
    width: 120,
    render: (row) => {
      const input = getInput(rowKey(row))
      return h(NInputNumber, {
        value: input.price,
        min: 0,
        precision: 7,
        format: fmtPrice,
        parse: parseNum,
        step: 0.1,
        size: 'small',
        style: 'width: 110px;',
        'onUpdate:value': (v) => { input.price = v },
      })
    },
  },
  {
    title: '手工单',
    key: 'handcraft_order_id',
    width: 110,
    render: (row) => h('span', {
      style: 'color:#6366F1; font-weight:600; cursor:pointer; border-bottom:1px dashed #c7cbf5;',
      onClick: () => openOrderPeek(row.handcraft_order_id),
    }, [row.handcraft_order_id, ' 🗗']),
  },
]

const handleCostDiffs = (data) => {
  if (data.cost_diffs && data.cost_diffs.length > 0) {
    costDiffs.value = data.cost_diffs
    costDiffSourceId.value = data.id
    costDiffVisible.value = true
  } else {
    router.push(`/handcraft-receipts/${data.id}`)
  }
}

const confirmCostUpdate = async () => {
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
    message.success('配件手工费成本已更新')
    costDiffVisible.value = false
    router.push(`/handcraft-receipts/${costDiffSourceId.value}`)
  } catch (_) {
    message.error('成本更新失败，请重试')
  } finally {
    costDiffUpdating.value = false
  }
}

const skipCostUpdate = () => {
  costDiffVisible.value = false
  router.push(`/handcraft-receipts/${costDiffSourceId.value}`)
}

const submit = async () => {
  if (!supplierName.value?.trim()) { message.warning('请输入商家名称'); return }
  const items = []

  // 产出项（勾选的待回收饰品）
  for (const key of jewelryCheckedKeys.value) {
    const id = parseInt(key.split('_')[1], 10)
    const pending = pendingJewelryItems.value.find((p) => p.id === id)
    if (!pending) continue
    const input = itemInputs[key]
    if (!input?.qty || input.qty <= 0) {
      message.warning(`请填写「${pending.item_name}」的回收数量`)
      return
    }
    items.push({
      handcraft_jewelry_item_id: pending.id,
      qty: input.qty,
      weight: input.weight != null ? input.weight : null,
      weight_unit: input.weight != null ? (input.weight_unit || 'g') : null,
      price: input.price != null ? input.price : null,
      unit: input.unit || '个',
    })
  }

  // 配件退料（弹窗选择，无价格）
  for (const [pidStr, qty] of Object.entries(partReturnSel)) {
    if (!qty || qty <= 0) continue
    const pending = pendingPartItems.value.find((p) => String(p.id) === String(pidStr))
    items.push({
      handcraft_part_item_id: parseInt(pidStr, 10),
      qty,
      unit: pending?.unit || '个',
    })
  }

  if (items.length === 0) { message.warning('请至少选择一项待回收饰品或配件退料'); return }

  submitting.value = true
  try {
    const payload = {
      supplier_name: supplierName.value.trim(),
      items,
      status: status.value,
      note: note.value,
    }
    const createdAt = tsToDateStr(createdAtTs.value)
    if (createdAt) payload.created_at = createdAt
    const { data } = await createHandcraftReceipt(payload)
    // 配件不足提示
    if (Array.isArray(data.parts_shortfall) && data.parts_shortfall.length) {
      const lines = data.parts_shortfall.map((s) => `${s.part_name}：缺 ${s.shortfall_qty}`).join('；')
      message.warning(`部分产出项所需配件不足：${lines}`, { duration: 8000 })
    }
    message.success('创建成功')
    handleCostDiffs(data)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  try {
    const { data } = await getHandcraftSuppliers()
    supplierOptions.value = data.map((v) => ({ label: v, value: v }))
  } catch (_) {}
})
</script>
