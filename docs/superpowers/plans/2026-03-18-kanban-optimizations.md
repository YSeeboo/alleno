# Kanban Optimizations Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix dropdown bugs in ReceiptModal and enable manual status changes on VendorDetailModal, PlatingDetail, and HandcraftDetail, including confirmation dialogs.

**Architecture:** All changes are frontend-only Vue 3 components. The backend `POST /kanban/order-status` endpoint already handles all required status transitions with correct inventory side effects. No backend changes needed. A new `changeOrderStatus` API helper is added to `kanban.js` and reused across three views.

**Tech Stack:** Vue 3 (Composition API), Naive UI (`NDropdown`, `NPopselect`, `NDialog`), Axios via project API wrapper.

---

## File Map

| File | Change |
|------|--------|
| `frontend/src/api/kanban.js` | Add `changeOrderStatus` export |
| `frontend/src/views/kanban/ReceiptModal.vue` | BUG-1: vendor dropdown auto-load on open; BUG-2: item dropdown auto-load on focus |
| `frontend/src/views/kanban/VendorDetailModal.vue` | 功能二: clickable status with confirmation; 功能三: close modal on navigate |
| `frontend/src/views/kanban/KanbanBoard.vue` | Propagate `@refresh` from VendorDetailModal |
| `frontend/src/views/plating/PlatingDetail.vue` | 功能四: status change dropdown + confirmation dialog |
| `frontend/src/views/handcraft/HandcraftDetail.vue` | 功能四: same as PlatingDetail but for handcraft |

---

## Task 1: Add `changeOrderStatus` API helper

**Files:**
- Modify: `frontend/src/api/kanban.js`

This function will be imported by VendorDetailModal, PlatingDetail, and HandcraftDetail. Add it once here so all three tasks can use it.

- [ ] **Step 1: Add the export to kanban.js**

Open `frontend/src/api/kanban.js` and append at the end:

```js
// 变更订单状态（看板双向流转）
export const changeOrderStatus = (data) =>
  api.post('/kanban/order-status', data)
  // data: { order_id: string, order_type: 'plating'|'handcraft', new_status: 'pending'|'processing'|'completed' }
```

- [ ] **Step 2: Verify the file looks correct**

The file should now export: `getKanban`, `getVendorDetail`, `submitReturn`, `searchVendors`, `getVendorOrders`, `getOrderItems`, `searchParts`, `searchJewelries`, `changeOrderStatus`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/kanban.js
git commit -m "feat: add changeOrderStatus API helper to kanban.js"
```

---

## Task 2: Fix ReceiptModal dropdown bugs

**Files:**
- Modify: `frontend/src/views/kanban/ReceiptModal.vue`

**Bug context:**
- BUG-1: The vendor `n-select` uses `remote` mode. On open without typing, `vendorOptions` is `[]` so nothing shows. Fix: load vendors when modal opens.
- BUG-2: Each item row's `n-select` also uses `remote` mode. On focus without typing, `row.options` is `[]`. Fix: trigger search on focus.
- BUG-3 is caused by the same root issue — once BUG-1/2 are fixed, search by ID also works (backend already does `id.ilike`).

- [ ] **Step 1: Fix BUG-1 — add `if (val)` branch to the show watcher**

Find the existing `watch(() => props.show, ...)` block near the bottom of the `<script setup>` (currently lines 286–299). It looks like this:

```js
watch(
  () => props.show,
  (val) => {
    if (!val) {
      _vendorSearchVersion++
      detailRows.value = [createRow()]
      form.vendor_name = null
      form.order_type = 'plating'
      form.order_id = null
      vendorOptions.value = []
      orderOptions.value = []
    }
  },
)
```

Change it to add a new `if (val)` branch BEFORE the existing `if (!val)` block:

```js
watch(
  () => props.show,
  (val) => {
    if (val) {
      handleVendorSearch('')
    } else {
      _vendorSearchVersion++
      detailRows.value = [createRow()]
      form.vendor_name = null
      form.order_type = 'plating'
      form.order_id = null
      vendorOptions.value = []
      orderOptions.value = []
    }
  },
)
```

- [ ] **Step 2: Fix BUG-2 — add `@focus` to item selector in detail rows**

Find the `n-select` inside the `v-for="(row, index) in detailRows"` loop (currently around line 59). It currently looks like:

```vue
<n-select
  v-model:value="row.selectorValue"
  filterable
  remote
  :options="row.options"
  :loading="row.searching"
  placeholder="搜索编号..."
  style="flex: 1; min-width: 0;"
  @search="(q) => handleItemSearch(q, index)"
/>
```

Add a `@focus` handler after `@search`:

```vue
<n-select
  v-model:value="row.selectorValue"
  filterable
  remote
  :options="row.options"
  :loading="row.searching"
  placeholder="搜索编号..."
  style="flex: 1; min-width: 0;"
  @search="(q) => handleItemSearch(q, index)"
  @focus="() => { if (!row.options.length && !row.selectorValue) handleItemSearch('', index) }"
/>
```

The guard `!row.options.length && !row.selectorValue` prevents a redundant refetch when the row already has options pre-filled from `loadOrderItems`.

- [ ] **Step 3: Manual verification checklist**

Open the kanban page and click "收回":
1. Vendor dropdown opens → options should populate immediately without typing ✓
2. Select a vendor → order dropdown populates ✓
3. Select an order → item rows pre-fill ✓
4. Add a new row → click item dropdown without typing → options load ✓
5. Type "SP-" in handcraft mode → jewelry results appear ✓
6. Type a part ID prefix like "PJ-" in plating mode → part results appear ✓

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/kanban/ReceiptModal.vue
git commit -m "fix: auto-load vendor and item dropdowns on open in ReceiptModal"
```

---

## Task 3: VendorDetailModal — 功能二 + 功能三

**Files:**
- Modify: `frontend/src/views/kanban/VendorDetailModal.vue`

**Changes needed:**
1. Add `NDropdown`, `useDialog` imports
2. Import `changeOrderStatus` from `@/api/kanban`
3. Add `'refresh'` to emits
4. Replace status column render with NDropdown-wrapped NTag
5. Add `handleOrderStatusChange` function
6. Close modal before navigation (功能三)

- [ ] **Step 1: Update imports in `<script setup>`**

Current import block (lines 40–44):
```js
import { ref, reactive, computed, watch, h } from 'vue'
import { useRouter } from 'vue-router'
import { NModal, NCard, NButton, NIcon, NSpin, NDataTable, NTag } from 'naive-ui'
import { CloseOutline } from '@vicons/ionicons5'
import { getVendorDetail } from '@/api/kanban'
```

Replace with:
```js
import { ref, reactive, computed, watch, h } from 'vue'
import { useRouter } from 'vue-router'
import { NModal, NCard, NButton, NIcon, NSpin, NDataTable, NTag, NDropdown, useDialog } from 'naive-ui'
import { CloseOutline } from '@vicons/ionicons5'
import { getVendorDetail, changeOrderStatus } from '@/api/kanban'
```

- [ ] **Step 2: Add `useDialog` instance and extend emits**

After `const emit = defineEmits(['update:show'])`, change to:
```js
const emit = defineEmits(['update:show', 'refresh'])
```

After the `const router = useRouter()` line, add:
```js
const dialog = useDialog()
```

- [ ] **Step 3: Add status helper data and `handleOrderStatusChange` function**

Add these after the existing `statusTypeMap` / `statusLabelMap` constants:

```js
const statusOptions = (currentStatus) => {
  if (currentStatus === 'pending') return [{ label: '进行中', key: 'processing' }]
  if (currentStatus === 'processing') return [
    { label: '待发出', key: 'pending' },
    { label: '已完成', key: 'completed' },
  ]
  if (currentStatus === 'completed') return [{ label: '进行中', key: 'processing' }]
  return []
}

const handleOrderStatusChange = (row, newStatus) => {
  const currentLabel = statusLabelMap[row.status] || row.status
  const newLabel = statusLabelMap[newStatus] || newStatus
  dialog.warning({
    title: '确认状态变更',
    content: `请确认将「${props.vendor.vendor_name}」的订单「${row.order_id}」状态从「${currentLabel}」转为「${newLabel}」`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await changeOrderStatus({
          order_id: row.order_id,
          order_type: row.order_type,
          new_status: newStatus,
        })
        await fetchDetail()
        emit('refresh')
      } catch (_) {
        // errors shown by axios interceptor
      }
    },
  })
}
```

- [ ] **Step 4: Update `orderColumns` — status column becomes NDropdown, and order_id closes modal before navigate (功能三)**

Find the `orderColumns` array (starts around line 88). It currently has two relevant renders to change.

**a. order_id column** — add `visible.value = false` before `router.push`:

```js
{
  title: '订单号',
  key: 'order_id',
  width: 140,
  render: (r) =>
    h(
      'span',
      {
        style: { color: '#C4952A', cursor: 'pointer', fontWeight: 500 },
        onClick: () => {
          visible.value = false
          router.push(`/${r.order_type}/${r.order_id}`)
        },
      },
      r.order_id,
    ),
},
```

**b. status column** — replace static NTag with NDropdown-wrapped NTag:

```js
{
  title: '状态',
  key: 'status',
  width: 110,
  render: (r) => {
    const opts = statusOptions(r.status)
    if (opts.length === 0) {
      return h(NTag, { type: statusTypeMap[r.status] || 'default', size: 'small' }, () => statusLabelMap[r.status] || r.status)
    }
    return h(
      NDropdown,
      {
        options: opts,
        trigger: 'click',
        onSelect: (key) => handleOrderStatusChange(r, key),
      },
      () => h(
        NTag,
        { type: statusTypeMap[r.status] || 'default', size: 'small', style: 'cursor: pointer;' },
        () => (statusLabelMap[r.status] || r.status) + ' ▾',
      ),
    )
  },
},
```

- [ ] **Step 5: Manual verification checklist**

1. Open kanban → click a vendor card in "待收回" lane → detail modal opens
2. In 关联订单 table, status tag for a `processing` order shows "进行中 ▾" and is clickable
3. Click it → dropdown shows "待发出" and "已完成"
4. Select "已完成" → confirmation dialog appears with correct text
5. Click 取消 → dialog closes, status unchanged
6. Select "已完成" again → confirm → status updates, table refreshes, kanban board refreshes
7. Click an order_id link → modal closes AND page navigates to that order detail
8. Navigate back → kanban still shows correct state

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/kanban/VendorDetailModal.vue
git commit -m "feat: add status change dropdown and close-on-navigate in VendorDetailModal"
```

---

## Task 4: KanbanBoard — listen for refresh from VendorDetailModal

**Files:**
- Modify: `frontend/src/views/kanban/KanbanBoard.vue`

- [ ] **Step 1: Add `@refresh="reloadAll"` to VendorDetailModal usage**

Find the `<VendorDetailModal>` tag (currently lines 54–57):

```vue
<VendorDetailModal
  v-model:show="detailVisible"
  :vendor="selectedVendor"
/>
```

Change to:

```vue
<VendorDetailModal
  v-model:show="detailVisible"
  :vendor="selectedVendor"
  @refresh="reloadAll"
/>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/kanban/KanbanBoard.vue
git commit -m "feat: reload kanban board on status change from VendorDetailModal"
```

---

## Task 5: PlatingDetail — 功能四 status change

**Files:**
- Modify: `frontend/src/views/plating/PlatingDetail.vue`

**Context:** The current `statusOptions = computed(() => [])` forces the popselect to always be disabled. `doChangeStatus` calls the old `updatePlatingStatus` (PATCH /plating/{id}/status) which the backend deliberately blocks. Both must be changed.

- [ ] **Step 1: Update imports**

Find the existing imports block (lines 118–121 — `import {` opens at 118):
```js
import {
  getPlating, getPlatingItems, sendPlating,
  addPlatingItem, updatePlatingItem, deletePlatingItem, updatePlatingStatus,
} from '@/api/plating'
```

Remove `updatePlatingStatus` from this import and add `changeOrderStatus` from `@/api/kanban`:

```js
import {
  getPlating, getPlatingItems, sendPlating,
  addPlatingItem, updatePlatingItem, deletePlatingItem,
} from '@/api/plating'
import { changeOrderStatus } from '@/api/kanban'
```

- [ ] **Step 2: Update `statusOptions` computed**

Find (currently line 139):
```js
const statusOptions = computed(() => [])
```

Replace with:
```js
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
```

- [ ] **Step 3: Change popselect binding from `v-model` to one-way `:value`**

Find in the template (line 15):
```vue
<n-popselect
  v-model:value="order.status"
```

Change to (prevents immediate UI mutation before API confirms):
```vue
<n-popselect
  :value="order?.status"
```

The `@update:value="doChangeStatus"` binding on the same tag stays unchanged.

- [ ] **Step 4: Rewrite `doChangeStatus` function body**

Find the existing function (lines 189–198):
```js
const doChangeStatus = async (newStatus) => {
  try {
    await updatePlatingStatus(route.params.id, newStatus)
    message.success('状态已更新')
    await loadData()
  } catch (_) {
    // error shown by axios interceptor; reload to restore displayed value
    await loadData()
  }
}
```

Replace the **entire function** with:
```js
const doChangeStatus = (newStatus) => {
  const currentLabel = statusLabel[order.value?.status] || order.value?.status
  const newLabel = statusLabel[newStatus] || newStatus
  dialog.warning({
    title: '确认状态变更',
    content: `请确认将「${order.value?.supplier_name}」的订单「${order.value?.id}」状态从「${currentLabel}」转为「${newLabel}」`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await changeOrderStatus({ order_id: order.value.id, order_type: 'plating', new_status: newStatus })
        message.success('状态已更新')
        await loadData()
      } catch (_) {
        // errors shown by axios interceptor
        await loadData()
      }
    },
  })
}
```

- [ ] **Step 5: Verify `useDialog` is already imported**

Check line 112: `import { useMessage, useDialog } from 'naive-ui'` — `useDialog` is already imported.
Check line 128: `const dialog = useDialog()` — already instantiated.
No import changes needed for dialog.

- [ ] **Step 6: Manual verification checklist**

1. Open a plating order in `待发出` state → status tag shows "待发出 ▾" and is clickable
2. Click → dropdown shows only "进行中"
3. Select "进行中" → confirmation dialog appears: `请确认将「{supplier}」的订单「EP-xxxx」状态从「待发出」转为「进行中」`
4. Cancel → no change
5. Confirm → status becomes 进行中, stock deducted (verify in inventory log)
6. With status 进行中 → dropdown shows "待发出" and "已完成"
7. Select "已完成" → confirm → order completes, inventory added back

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/plating/PlatingDetail.vue
git commit -m "feat: enable status change with confirmation dialog in PlatingDetail"
```

---

## Task 6: HandcraftDetail — 功能四 status change

**Files:**
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue`

Same pattern as Task 5. The only differences are: `order_type: 'handcraft'`, the supplier label is "手工商家", and `updateHandcraftStatus` is removed instead of `updatePlatingStatus`.

- [ ] **Step 1: Update imports**

Find (lines 183–188 — `import {` opens at 183):
```js
import {
  getHandcraft, getHandcraftParts, getHandcraftJewelries, sendHandcraft,
  addHandcraftPart, updateHandcraftPart, deleteHandcraftPart,
  addHandcraftJewelry, updateHandcraftJewelry, deleteHandcraftJewelry,
  updateHandcraftStatus,
} from '@/api/handcraft'
```

Remove `updateHandcraftStatus` and add `changeOrderStatus` from kanban:

```js
import {
  getHandcraft, getHandcraftParts, getHandcraftJewelries, sendHandcraft,
  addHandcraftPart, updateHandcraftPart, deleteHandcraftPart,
  addHandcraftJewelry, updateHandcraftJewelry, deleteHandcraftJewelry,
} from '@/api/handcraft'
import { changeOrderStatus } from '@/api/kanban'
```

- [ ] **Step 2: Update `statusOptions` computed**

Find (line 211):
```js
const statusOptions = computed(() => [])
```

Replace with:
```js
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
```

- [ ] **Step 3: Change popselect binding from `v-model` to one-way `:value`**

Find in the template (line 15):
```vue
<n-popselect
  v-model:value="order.status"
```

Change to:
```vue
<n-popselect
  :value="order?.status"
```

The `@update:value="doChangeStatus"` binding stays unchanged.

- [ ] **Step 4: Rewrite `doChangeStatus` function body**

Find the existing function (lines 277–286):
```js
const doChangeStatus = async (newStatus) => {
  try {
    await updateHandcraftStatus(route.params.id, newStatus)
    message.success('状态已更新')
    await loadData()
  } catch (_) {
    // error shown by axios interceptor; reload to restore displayed value
    await loadData()
  }
}
```

Replace the **entire function** with:
```js
const doChangeStatus = (newStatus) => {
  const currentLabel = statusLabel[order.value?.status] || order.value?.status
  const newLabel = statusLabel[newStatus] || newStatus
  dialog.warning({
    title: '确认状态变更',
    content: `请确认将「${order.value?.supplier_name}」的订单「${order.value?.id}」状态从「${currentLabel}」转为「${newLabel}」`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await changeOrderStatus({ order_id: order.value.id, order_type: 'handcraft', new_status: newStatus })
        message.success('状态已更新')
        await loadData()
      } catch (_) {
        // errors shown by axios interceptor
        await loadData()
      }
    },
  })
}
```

- [ ] **Step 5: Verify `useDialog` is already imported and instantiated, and remove stale comment**

Check line 177: `import { useMessage, useDialog } from 'naive-ui'` — already imported.
Check line 196: `const dialog = useDialog()` — already instantiated.

Also remove the stale comment at line 210 (immediately before `statusOptions`):
```js
// All status transitions go through dedicated endpoints (POST /send, POST /receive)
```
Delete this line — it is no longer accurate after enabling manual status changes.

- [ ] **Step 6: Manual verification checklist**

1. Open a handcraft order in `待发出` state → status shows "待发出 ▾"
2. Click → dropdown shows "进行中" only
3. Confirm → status becomes 进行中, parts stock deducted
4. With status 进行中, dropdown shows "待发出" and "已完成"
5. Force complete → confirm → remaining parts added back, jewelry stock added

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/handcraft/HandcraftDetail.vue
git commit -m "feat: enable status change with confirmation dialog in HandcraftDetail"
```

---

## Final Verification

After all tasks are done, run a full smoke test:

1. **ReceiptModal dropdown bug:** Open 收回 modal, vendor + item dropdowns load immediately without typing
2. **ReceiptModal search:** Type "SP-" in handcraft mode → jewelry results; type "PJ-" in plating mode → part results
3. **VendorDetailModal status:** Click vendor → detail shows orders with clickable status tags; changing status triggers dialog + refreshes both detail and kanban board
4. **VendorDetailModal navigate:** Clicking an order ID closes the modal and navigates correctly
5. **PlatingDetail status:** Status dropdown works, shows correct options per state, dialog has correct content
6. **HandcraftDetail status:** Same as above for handcraft

Start the dev server to test:
```bash
cd frontend && npm run dev
```
