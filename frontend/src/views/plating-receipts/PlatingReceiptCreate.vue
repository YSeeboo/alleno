<template>
  <div :style="{ maxWidth: isMobile ? '100%' : '1000px' }">
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">新建电镀回收单</n-h2>
    </n-space>

    <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="100" style="margin-bottom: 16px;">
      <n-form-item label="商家名称">
        <n-select
          v-model:value="vendorName"
          :options="vendorOptions"
          filterable
          tag
          placeholder="选择或输入商家名称"
          :style="{ width: isMobile ? '100%' : '300px' }"
          @update:value="onVendorChange"
        />
      </n-form-item>
      <n-form-item label="备注">
        <n-input v-model:value="note" type="textarea" :rows="2" :style="{ width: isMobile ? '100%' : '300px' }" />
      </n-form-item>
      <n-form-item label="创建时间">
        <n-date-picker
          v-model:value="createdAtTs"
          type="date"
          clearable
          placeholder="不填则使用当前时间"
          :style="{ width: isMobile ? '100%' : '300px' }"
        />
      </n-form-item>
    </n-form>

    <n-card title="待回收配件" style="margin-bottom: 16px;">
      <div v-if="vendorName" style="display: flex; gap: 12px; align-items: center; margin-bottom: 12px;">
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
        <n-empty v-if="!loadingItems && pendingItems.length === 0" :description="fetchError ? '加载失败，请重试' : vendorName ? '该商家暂无待回收配件' : '请先选择商家'" style="margin-top: 16px;" />
        <n-data-table
          v-if="pendingItems.length > 0"
          :columns="pendingColumns"
          :data="pendingItems"
          :bordered="false"
          :row-key="(row) => row.id"
          :checked-row-keys="checkedKeys"
          @update:checked-row-keys="onCheck"
        />
      </n-spin>
    </n-card>

    <div style="margin-bottom: 16px; font-size: 15px; font-weight: 600;">
      总金额：¥ {{ totalAmount }}
    </div>

    <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="100" style="margin-bottom: 16px;">
      <n-form-item label="付款状态">
        <n-radio-group v-model:value="status">
          <n-radio value="未付款">未付款</n-radio>
          <n-radio value="已付款">已付款</n-radio>
        </n-radio-group>
      </n-form-item>
    </n-form>

    <n-space justify="end">
      <n-button type="primary" :loading="submitting" @click="submit">提交</n-button>
    </n-space>
    <!-- Cost Diff Modal -->
    <n-modal v-model:show="costDiffVisible" :mask-closable="false" preset="card" title="电镀成本变动确认" :style="{ width: isMobile ? '95vw' : '550px' }">
      <div style="margin-bottom: 12px; color: #333;">
        当前电镀成本与配件已有电镀成本金额不相同，是否更新电镀成本？
      </div>
      <div style="margin-bottom: 12px; color: #999; font-size: 12px;">来源：{{ costDiffSourceId }}</div>
      <n-data-table
        :columns="[
          { title: '配件编号', key: 'part_id', width: 130 },
          { title: '配件名称', key: 'part_name', minWidth: 120 },
          { title: '原电镀费用', key: 'current_value', width: 120, render: (r) => r.current_value != null ? `¥ ${fmtMoney(r.current_value)}` : '-' },
          { title: '更新电镀费用', key: 'new_value', width: 120, render: (r) => h('span', { style: 'color: #d03050; font-weight: 600;' }, `¥ ${fmtMoney(r.new_value)}`) },
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
  NCard, NH2, NRadioGroup, NRadio, NDataTable, NSpin, NEmpty, NImage, NModal, NDatePicker,
} from 'naive-ui'
import { listPendingReceiveItems } from '@/api/plating'
import { createPlatingReceipt } from '@/api/platingReceipts'
import { batchUpdatePartCosts } from '@/api/parts'
import { renderNamedImage, fmtMoney, fmtPrice, parseNum } from '@/utils/ui'
import { tsToDateStr } from '@/utils/date'
import { useIsMobile } from '@/composables/useIsMobile'

const router = useRouter()
const message = useMessage()
const { isMobile } = useIsMobile()
const vendorName = ref(null)
const note = ref('')
const status = ref('未付款')
const createdAtTs = ref(null)
const submitting = ref(false)
const loadingItems = ref(false)
const vendorOptions = ref([])
const pendingItems = ref([])
const checkedKeys = ref([])
// Store user input for qty and price per item id
const itemInputs = reactive({})

// Filter state
const filterKeyword = ref('')
const filterDateOn = ref(null)
let debounceTimer = null
let fetchSeq = 0
const fetchError = ref(false)

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

const getRemaining = (item) => item.qty - (item.received_qty || 0)

const getInput = (id) => {
  if (!itemInputs[id]) {
    itemInputs[id] = { qty: null, price: null, unit: '个', weight: null }
  }
  return itemInputs[id]
}

const pendingIdSet = computed(() => new Set(pendingItems.value.map((p) => p.id)))

const visibleCheckedKeys = computed(() => checkedKeys.value.filter((id) => pendingIdSet.value.has(id)))

const totalAmount = computed(() => {
  let sum = 0
  for (const id of visibleCheckedKeys.value) {
    const input = itemInputs[id]
    if (input) {
      sum += (input.qty || 0) * (input.price || 0)
    }
  }
  return fmtMoney(sum)
})

const fetchPendingItems = async () => {
  const seq = ++fetchSeq
  if (!vendorName.value) {
    pendingItems.value = []
    loadingItems.value = false
    fetchError.value = false
    return
  }
  loadingItems.value = true
  fetchError.value = false
  try {
    const params = { supplier_name: vendorName.value }
    if (filterKeyword.value) params.part_keyword = filterKeyword.value
    if (filterDateOn.value) {
      const d = new Date(filterDateOn.value)
      params.date_on = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    }
    const { data } = await listPendingReceiveItems(params)
    if (seq !== fetchSeq) return
    pendingItems.value = data
    for (const item of data) {
      if (!itemInputs[item.id]) {
        itemInputs[item.id] = { qty: getRemaining(item), price: null, unit: item.unit || '个' }
      }
    }
  } catch (_) {
    if (seq !== fetchSeq) return
    pendingItems.value = []
    checkedKeys.value = []
    fetchError.value = true
    message.error('加载待回收配件失败')
  } finally {
    if (seq === fetchSeq) loadingItems.value = false
  }
}

const onVendorChange = async (val) => {
  vendorName.value = val
  checkedKeys.value = []
  filterKeyword.value = ''
  filterDateOn.value = null
  await fetchPendingItems()
}

const onFilterKeywordChange = () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    fetchPendingItems()
  }, 300)
}

const onFilterDateChange = () => {
  fetchPendingItems()
}

const onCheck = (keys) => {
  checkedKeys.value = keys
}

const pendingColumns = [
  { type: 'selection' },
  { title: '电镀单号', key: 'plating_order_id', width: 110 },
  {
    title: '配件',
    key: 'part_name',
    minWidth: 160,
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name, 40, row.part_is_composite ? '组合' : null),
  },
  { title: '电镀方式', key: 'plating_method', width: 90, render: (r) => r.plating_method || '-' },
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
      const input = getInput(row.id)
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
      const input = getInput(row.id)
      const wu = row.weight_unit || 'g'
      const children = []
      if (row.weight != null) {
        children.push(h('div', { style: 'color:#999;font-size:11px;margin-bottom:2px' }, `发出: ${row.weight}${wu}`))
      }
      children.push(
        h('div', { style: 'display:flex;gap:4px;align-items:center' }, [
          h(NInputNumber, {
            value: input.weight,
            size: 'small',
            style: 'width:80px',
            min: 0,
            placeholder: '重量',
            'onUpdate:value': (v) => { input.weight = v },
          }),
          h('span', { style: 'font-size:12px;color:#666' }, wu),
        ]),
      )
      return h('div', null, children)
    },
  },
  {
    title: '单价',
    key: 'input_price',
    width: 120,
    render: (row) => {
      const input = getInput(row.id)
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

const handleCostDiffs = (data) => {
  if (data.cost_diffs && data.cost_diffs.length > 0) {
    costDiffs.value = data.cost_diffs
    costDiffSourceId.value = data.id
    costDiffVisible.value = true
  } else {
    router.push(`/plating-receipts/${data.id}`)
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
    message.success('配件电镀成本已更新')
    costDiffVisible.value = false
    router.push(`/plating-receipts/${costDiffSourceId.value}`)
  } catch (_) {
    message.error('成本更新失败，请重试')
  } finally {
    costDiffUpdating.value = false
  }
}

const skipCostUpdate = () => {
  costDiffVisible.value = false
  router.push(`/plating-receipts/${costDiffSourceId.value}`)
}

const submit = async () => {
  if (!vendorName.value?.trim()) { message.warning('请输入商家名称'); return }
  if (visibleCheckedKeys.value.length === 0) { message.warning('请至少勾选一条待回收配件'); return }

  const items = []
  for (const id of visibleCheckedKeys.value) {
    const pending = pendingItems.value.find((p) => p.id === id)
    const input = itemInputs[id]
    if (!input?.qty || input.qty <= 0) { message.warning(`请填写「${pending.part_name}」的回收数量`); return }

    items.push({
      plating_order_item_id: pending.id,
      part_id: pending.receive_part_id || pending.part_id,
      qty: input.qty,
      weight: input.weight != null ? input.weight : null,
      weight_unit: input.weight != null ? (pending.weight_unit || 'g') : null,
      price: input.price != null ? input.price : null,
      unit: input.unit || '个',
    })
  }

  submitting.value = true
  try {
    const payload = {
      vendor_name: vendorName.value.trim(),
      items,
      status: status.value,
      note: note.value,
    }
    const createdAt = tsToDateStr(createdAtTs.value)
    if (createdAt) payload.created_at = createdAt
    const { data } = await createPlatingReceipt(payload)
    message.success('创建成功')
    handleCostDiffs(data)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  // Load supplier names from pending items
  try {
    const { data } = await listPendingReceiveItems({})
    const suppliers = [...new Set(data.map((i) => i.supplier_name).filter(Boolean))]
    vendorOptions.value = suppliers.map((v) => ({ label: v, value: v }))
  } catch (_) {}
})
</script>
