<template>
  <div style="max-width: 1000px;">
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">新建手工回收单</n-h2>
    </n-space>

    <n-form label-placement="left" label-width="100" style="margin-bottom: 16px;">
      <n-form-item label="手工商家">
        <n-select
          v-model:value="supplierName"
          :options="supplierOptions"
          filterable
          tag
          placeholder="选择或输入商家名称"
          style="width: 300px;"
          @update:value="onSupplierChange"
        />
      </n-form-item>
      <n-form-item label="备注">
        <n-input v-model:value="note" type="textarea" :rows="2" style="width: 300px;" />
      </n-form-item>
    </n-form>

    <n-card title="待回收项目" style="margin-bottom: 16px;">
      <template #header-extra>
        <n-radio-group v-model:value="activeTab" size="small">
          <n-radio-button value="part">配件</n-radio-button>
          <n-radio-button value="jewelry">饰品</n-radio-button>
        </n-radio-group>
      </template>
      <div v-if="supplierName" style="display: flex; gap: 12px; align-items: center; margin-bottom: 12px;">
        <n-input
          v-model:value="filterKeyword"
          placeholder="编号/名称搜索"
          clearable
          style="width: 200px;"
          @update:value="onFilterKeywordChange"
        />
        <span style="font-size: 13px; color: #666;">发出日期</span>
        <n-date-picker
          v-model:value="filterDateOn"
          type="date"
          clearable
          style="width: 160px;"
          @update:value="onFilterDateChange"
        />
      </div>
      <n-spin :show="loadingItems">
        <n-empty
          v-if="!loadingItems && currentPendingItems.length === 0"
          :description="fetchError ? '加载失败，请重试' : supplierName ? `该商家暂无待回收${activeTab === 'part' ? '配件' : '饰品'}` : '请先选择商家'"
          style="margin-top: 16px;"
        />
        <n-data-table
          v-if="currentPendingItems.length > 0"
          :columns="currentColumns"
          :data="currentPendingItems"
          :bordered="false"
          :row-key="(row) => rowKey(row)"
          :checked-row-keys="currentCheckedKeys"
          @update:checked-row-keys="onCheck"
        />
      </n-spin>
    </n-card>

    <div style="margin-bottom: 16px; font-size: 15px; font-weight: 600;">
      总金额：¥ {{ totalAmount }}
    </div>

    <n-form label-placement="left" label-width="100" style="margin-bottom: 16px;">
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
    <n-modal v-model:show="costDiffVisible" :mask-closable="false" preset="card" title="手工费成本变动确认" style="width: 550px;">
      <div style="margin-bottom: 12px; color: #333;">
        当前手工费与配件已有手工费金额不相同，是否更新手工费成本？
      </div>
      <div style="margin-bottom: 12px; color: #999; font-size: 12px;">来源：{{ costDiffSourceId }}</div>
      <n-data-table
        :columns="[
          { title: '配件编号', key: 'part_id', width: 130 },
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
  NCard, NH2, NRadioGroup, NRadio, NRadioButton, NDataTable, NSpin, NEmpty, NImage, NModal, NDatePicker,
} from 'naive-ui'
import { listHandcraftPendingReceiveItems, createHandcraftReceipt } from '@/api/handcraftReceipts'
import { getHandcraftSuppliers } from '@/api/handcraft'
import { batchUpdatePartCosts } from '@/api/parts'
import { renderNamedImage, fmtMoney, fmtPrice, parseNum } from '@/utils/ui'

const router = useRouter()
const message = useMessage()
const supplierName = ref(null)
const note = ref('')
const status = ref('未付款')
const submitting = ref(false)
const loadingItems = ref(false)
const supplierOptions = ref([])
const activeTab = ref('part')

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

const rowKey = (row) => `${row.item_type}_${row.id}`
const getRemaining = (item) => item.qty - (item.received_qty || 0)

const currentPendingItems = computed(() => activeTab.value === 'part' ? pendingPartItems.value : pendingJewelryItems.value)
const currentCheckedKeys = computed(() => activeTab.value === 'part' ? partCheckedKeys.value : jewelryCheckedKeys.value)
const currentColumns = computed(() => activeTab.value === 'part' ? partPendingColumns : jewelryPendingColumns)

const getInput = (key) => {
  if (!itemInputs[key]) {
    itemInputs[key] = { qty: null, price: null, unit: '个', weight: null, weight_unit: 'g' }
  }
  return itemInputs[key]
}

const totalAmount = computed(() => {
  let sum = 0
  for (const key of [...partCheckedKeys.value, ...jewelryCheckedKeys.value]) {
    const input = itemInputs[key]
    if (input) {
      sum += (input.qty || 0) * (input.price || 0)
    }
  }
  return fmtMoney(sum)
})

const fetchPendingItems = async () => {
  const seq = ++fetchSeq
  if (!supplierName.value) {
    pendingPartItems.value = []
    pendingJewelryItems.value = []
    loadingItems.value = false
    fetchError.value = false
    return
  }
  loadingItems.value = true
  fetchError.value = false
  try {
    const params = { supplier_name: supplierName.value }
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
  if (activeTab.value === 'part') {
    partCheckedKeys.value = keys
  } else {
    jewelryCheckedKeys.value = keys
  }
}

const partPendingColumns = [
  { type: 'selection' },
  { title: '手工单号', key: 'handcraft_order_id', width: 110 },
  {
    title: '配件',
    key: 'item_name',
    minWidth: 160,
    render: (row) => renderNamedImage(row.item_name, row.item_image, row.item_name),
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

const jewelryPendingColumns = [
  { type: 'selection' },
  { title: '手工单号', key: 'handcraft_order_id', width: 110 },
  {
    title: '饰品',
    key: 'item_name',
    minWidth: 160,
    render: (row) => renderNamedImage(row.item_name, row.item_image, row.item_name),
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
  const allCheckedKeys = [...partCheckedKeys.value, ...jewelryCheckedKeys.value]
  if (allCheckedKeys.length === 0) { message.warning('请至少勾选一条待回收项目'); return }

  const items = []
  for (const key of allCheckedKeys) {
    const [type, idStr] = key.split('_')
    const id = parseInt(idStr, 10)
    const allItems = type === 'part' ? pendingPartItems.value : pendingJewelryItems.value
    const pending = allItems.find((p) => p.id === id)
    if (!pending) continue
    const input = itemInputs[key]
    if (!input?.qty || input.qty <= 0) {
      message.warning(`请填写「${pending.item_name}」的回收数量`)
      return
    }

    const item = {
      qty: input.qty,
      weight: input.weight != null ? input.weight : null,
      weight_unit: input.weight != null ? (input.weight_unit || 'g') : null,
      price: input.price != null ? input.price : null,
      unit: input.unit || '个',
    }
    if (type === 'output') {
      // Output items (jewelry or part output) use handcraft_jewelry_item_id
      item.handcraft_jewelry_item_id = pending.id
    } else {
      // Regular part items
      item.handcraft_part_item_id = pending.id
    }
    items.push(item)
  }

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
