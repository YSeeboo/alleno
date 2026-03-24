# Plating Receipt Optimizations — Frontend Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add filter controls (keyword search + date picker) to the pending-receive items table on the receipt create page; add an "add items" modal to the receipt detail page for appending items to unpaid receipts.

**Architecture:** Two independent UI changes: (1) enhance `PlatingReceiptCreate.vue` with filter inputs that call the existing `listPendingReceiveItems` API with new params, (2) enhance `PlatingReceiptDetail.vue` with an add-items button + modal that reuses the pending-receive list and calls a new API endpoint.

**Tech Stack:** Vue 3.5, Naive UI, Vite

**Spec:** `docs/superpowers/specs/2026-03-24-plating-receipt-optimizations-design.md`

**Dependency:** Backend plan must be deployed first — this plan uses the new `date_on`, `exclude_item_ids` query params on `GET /api/plating/items/pending-receive` and the new `POST /api/plating-receipts/{id}/items` endpoint.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `frontend/src/api/platingReceipts.js` | Modify | Add `addPlatingReceiptItems` API call |
| `frontend/src/views/plating-receipts/PlatingReceiptCreate.vue` | Modify | Add filter row (keyword + date) + "发出日期" column |
| `frontend/src/views/plating-receipts/PlatingReceiptDetail.vue` | Modify | Add "+ 增加配件" button + add-items modal + cost diff modal |

---

### Task 1: Add `addPlatingReceiptItems` API method

**Files:**
- Modify: `frontend/src/api/platingReceipts.js:12`

- [ ] **Step 1: Add the API method**

At the end of `frontend/src/api/platingReceipts.js` (after line 11), add:

```javascript
export const addPlatingReceiptItems = (id, data) => api.post(`/plating-receipts/${id}/items`, data)
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -20 || true`
(Or just verify the dev server still starts without errors)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/platingReceipts.js
git commit -m "feat: add addPlatingReceiptItems API method"
```

---

### Task 2: Add filter controls to PlatingReceiptCreate.vue

**Files:**
- Modify: `frontend/src/views/plating-receipts/PlatingReceiptCreate.vue`

This task adds:
- A keyword search input and date picker above the pending items table
- A "发出日期" column in the table
- Debounced re-fetch when filters change

- [ ] **Step 1: Add NDatePicker to Naive UI imports**

In `PlatingReceiptCreate.vue` line 88, add `NDatePicker` to the imports:

```javascript
import {
  NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem,
  NCard, NH2, NRadioGroup, NRadio, NDataTable, NSpin, NEmpty, NImage, NModal, NDatePicker,
} from 'naive-ui'
```

- [ ] **Step 2: Add filter state variables**

After line 107 (`const itemInputs = reactive({})`), add:

```javascript
// Filter state
const filterKeyword = ref('')
const filterDateOn = ref(null)
let debounceTimer = null
```

- [ ] **Step 3: Add fetchPendingItems and filter change handler**

Replace the `onVendorChange` function (lines 143-165) with:

```javascript
const fetchPendingItems = async () => {
  if (!vendorName.value) {
    pendingItems.value = []
    return
  }
  loadingItems.value = true
  try {
    const params = { supplier_name: vendorName.value }
    if (filterKeyword.value) params.part_keyword = filterKeyword.value
    if (filterDateOn.value) {
      const d = new Date(filterDateOn.value)
      params.date_on = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    }
    const { data } = await listPendingReceiveItems(params)
    pendingItems.value = data
    for (const item of data) {
      if (!itemInputs[item.id]) {
        itemInputs[item.id] = { qty: getRemaining(item), price: null, unit: item.unit || '个' }
      }
    }
  } catch (_) {
    pendingItems.value = []
  } finally {
    loadingItems.value = false
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
    checkedKeys.value = []
    fetchPendingItems()
  }, 300)
}

const onFilterDateChange = () => {
  checkedKeys.value = []
  fetchPendingItems()
}
```

- [ ] **Step 4: Add filter row in template**

In the template, inside the `<n-card title="待回收配件">` (after line 25, before `<n-spin>`), add a filter row:

Replace lines 25-37:

```html
    <n-card title="待回收配件" style="margin-bottom: 16px;">
      <div v-if="vendorName" style="display: flex; gap: 12px; align-items: center; margin-bottom: 12px;">
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
        <n-empty v-if="!loadingItems && pendingItems.length === 0" :description="vendorName ? '该商家暂无待回收配件' : '请先选择商家'" style="margin-top: 16px;" />
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
```

- [ ] **Step 5: Add "发出日期" column to pendingColumns**

In `pendingColumns` (after line 180, after the 电镀方式 column), add:

```javascript
  {
    title: '发出日期',
    key: 'created_at',
    width: 100,
    render: (r) => r.created_at ? new Date(r.created_at).toLocaleDateString('zh-CN') : '-',
  },
```

- [ ] **Step 6: Test in browser**

1. Run `cd frontend && npm run dev`
2. Navigate to the "新建电镀回收单" page
3. Select a vendor — verify the filter row appears
4. Type in the keyword search — verify debounced filtering works
5. Select a date — verify table filters to that date only
6. Clear both filters — verify table shows all items again
7. Verify the "发出日期" column shows dates

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/plating-receipts/PlatingReceiptCreate.vue
git commit -m "feat: add keyword search and date filter to pending receive items"
```

---

### Task 3: Add "+ 增加配件" button and modal to PlatingReceiptDetail.vue

**Files:**
- Modify: `frontend/src/views/plating-receipts/PlatingReceiptDetail.vue`

This is the largest task. It adds:
- An "+ 增加配件" button in the "回收明细" card header (hidden when paid)
- A modal with the pending-receive items table (with filters)
- Submit logic that calls `POST /api/plating-receipts/{id}/items`
- Cost diff handling after adding items

- [ ] **Step 1: Add new imports**

In `PlatingReceiptDetail.vue`, add to the imports section:

At line 172, add `reactive` to the vue import:

```javascript
import { ref, reactive, computed, onMounted, h, nextTick } from 'vue'
```

Add `NDatePicker` to the Naive UI import (line 177-178):

```javascript
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NTag, NEmpty, NModal, NForm, NFormItem,
  NSelect, NInputNumber, NInput, NPopselect, NTooltip, NIcon, NImage, NDatePicker,
} from 'naive-ui'
```

Add API imports (after line 186):

```javascript
import { listPendingReceiveItems } from '@/api/plating'
import { addPlatingReceiptItems } from '@/api/platingReceipts'
import { batchUpdatePartCosts } from '@/api/parts'
```

Update the platingReceipts import to include `addPlatingReceiptItems`:

```javascript
import {
  getPlatingReceipt, updatePlatingReceiptStatus,
  updatePlatingReceiptDeliveryImages,
  updatePlatingReceiptItem, deletePlatingReceiptItem,
  deletePlatingReceipt, addPlatingReceiptItems,
} from '@/api/platingReceipts'
```

- [ ] **Step 2: Add add-items state variables**

After the existing edit item modal state (after line 232, after `const noteInputRef = ref(null)`), add:

```javascript
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

// Cost diff modal (for add-items)
const addItemsCostDiffVisible = ref(false)
const addItemsCostDiffs = ref([])
const addItemsCostDiffUpdating = ref(false)
```

- [ ] **Step 3: Add add-items helper functions**

After the add-items state variables, add:

```javascript
const getAddRemaining = (item) => item.qty - (item.received_qty || 0)

const getAddInput = (id) => {
  if (!addItemsInputs[id]) {
    addItemsInputs[id] = { qty: null, price: null, unit: '个' }
  }
  return addItemsInputs[id]
}

const fetchAddItemsPending = async () => {
  if (!receipt.value) return
  addItemsLoading.value = true
  try {
    const existingPoiIds = receipt.value.items.map((i) => i.plating_order_item_id).filter(Boolean)
    const params = { supplier_name: receipt.value.vendor_name }
    if (existingPoiIds.length > 0) params.exclude_item_ids = existingPoiIds.join(',')
    if (addItemsFilterKeyword.value) params.part_keyword = addItemsFilterKeyword.value
    if (addItemsFilterDateOn.value) {
      const d = new Date(addItemsFilterDateOn.value)
      params.date_on = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    }
    const { data } = await listPendingReceiveItems(params)
    addItemsPendingItems.value = data
    for (const item of data) {
      if (!addItemsInputs[item.id]) {
        addItemsInputs[item.id] = { qty: getAddRemaining(item), price: null, unit: item.unit || '个' }
      }
    }
  } catch (_) {
    addItemsPendingItems.value = []
  } finally {
    addItemsLoading.value = false
  }
}

const openAddItemsModal = () => {
  addItemsCheckedKeys.value = []
  addItemsFilterKeyword.value = ''
  addItemsFilterDateOn.value = null
  // Clear old inputs
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
      price: input.price != null ? input.price : null,
      unit: input.unit || '个',
    })
  }

  addItemsSubmitting.value = true
  try {
    const { data } = await addPlatingReceiptItems(route.params.id, { items })
    message.success('配件已添加')
    addItemsModalVisible.value = false
    // Handle cost diffs
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
```

- [ ] **Step 4: Add pending items table columns for the modal**

After the helper functions, add:

```javascript
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
    title: '单价',
    key: 'input_price',
    width: 110,
    render: (row) => {
      const input = getAddInput(row.id)
      return h(NInputNumber, {
        value: input.price,
        min: 0,
        precision: 7,
        step: 0.1,
        size: 'small',
        style: 'width: 100px;',
        'onUpdate:value': (v) => { input.price = v },
      })
    },
  },
]
```

- [ ] **Step 5: Update template — add button to card header**

Replace the "回收明细" card (line 127-130):

```html
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
```

- [ ] **Step 6: Add modals to template**

Before the closing `</div>` of the root template (before line 168), add the add-items modal and cost diff modal:

```html
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
        <n-empty v-if="!addItemsLoading && addItemsPendingItems.length === 0" description="暂无可添加的待回收配件" style="margin: 16px 0;" />
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
```

- [ ] **Step 7: Test in browser**

1. Run `cd frontend && npm run dev`
2. Navigate to an **unpaid** receipt detail page
3. Verify "+ 增加配件" button is visible in the "回收明细" card header
4. Click the button — verify the modal opens with pending items (excluding existing ones)
5. Test keyword search and date filter in the modal
6. Select items, fill qty/price, click "确认添加" — verify items are added
7. Verify total_amount is updated
8. Navigate to a **paid** receipt — verify the button is NOT visible

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/plating-receipts/PlatingReceiptDetail.vue
git commit -m "feat: add items modal to plating receipt detail page"
```

---

### Task 4: Final integration test

- [ ] **Step 1: End-to-end flow test**

With both backend and frontend running:

1. Create a plating order with multiple parts, send it
2. Create a receipt from "新建电镀回收单" — verify keyword and date filters work
3. Go to the receipt detail page
4. Click "+ 增加配件", add more items from the same plating order
5. Verify the new items appear in the receipt with correct quantities
6. Verify stock is updated correctly
7. If cost diff modal appears, test both "跳过" and "确认更新"
8. Change receipt status to "已付款" — verify "+ 增加配件" button disappears

- [ ] **Step 2: Final commit if any fixups needed**

Fix and commit with `fix:` prefix if needed.
