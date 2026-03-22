# Kanban Optimizations Design

**Date:** 2026-03-18
**Status:** Approved

---

## Scope

Frontend-only changes (6 files) plus one API helper addition. No backend service changes required — `POST /kanban/order-status` already handles all needed transitions.

---

## Already Implemented (confirmed, no changes needed)

- **功能零** – Receipt modal order field: `ReceiptModal.vue` already has order selector + auto-fill from order items.
- **功能一** – 进度看板 sidebar position: `DefaultLayout.vue` already places 进度看板 first in the 工作台 group.

---

## Bug Fixes

### BUG-1 & BUG-2: Dropdowns show no options on open

**Root cause:** `n-select` with `remote` only loads options on `@search` (user typing). On open without typing, `options` array is empty.

**Fix – Vendor dropdown (`ReceiptModal.vue`):**
The existing `watch(() => props.show)` only has an `if (!val)` reset branch. A new `if (val)` branch must be added before the reset branch to call `handleVendorSearch('')` and pre-load vendors when the modal opens.

**Fix – Item dropdown (`ReceiptModal.vue`):**
Add `@focus="() => handleItemSearch('', index)"` on each row's item selector, so opening the dropdown triggers a full search with empty query.

**BUG-3 (SP-0001 search):** Root cause is BUG-1/2 — no auto-trigger. Backend already searches both by name and ID (`Part.id.ilike`, `Jewelry.id.ilike`). Fixed by same solution.

---

## 功能二: VendorDetailModal – Status Change

**File:** `VendorDetailModal.vue`

**Change:** Convert status column from static `NTag` to `NDropdown`-wrapped clickable tag.

**Available transitions (per current status):**

| Current | Options shown |
|---------|--------------|
| `pending` | `processing` (进行中) |
| `processing` | `pending` (待发出), `completed` (已完成) |
| `completed` | `processing` (进行中) |

(Note: `completed → processing` is not in the original requirements but is supported by the backend. It is included as a useful correction flow. Same applies to 功能四.)

**Confirmation dialog content:**
`请确认将「{vendor_name}」的订单「{order_id}」状态从「{currentLabel}」转为「{newLabel}」`

(Note: requirements specified `{supplier_name}` as variable name; in VendorDetailModal the vendor comes from `props.vendor.vendor_name`. The wording adds `将` and uses 「」 brackets for clarity — acceptable UI polish.)

**After confirm:** Call `POST /kanban/order-status`, then `fetchDetail()` to refresh, then `emit('refresh')` so parent KanbanBoard calls `reloadAll()`.

**New emit:** `'refresh'` added to VendorDetailModal emits.

---

## 功能三: Click Order ID to Navigate + Close Modal

**File:** `VendorDetailModal.vue`

**Change:** In the `onClick` handler for order_id column, add `visible.value = false` before `router.push(...)`. The modal closes before navigation.

---

## 功能四: PlatingDetail / HandcraftDetail – Status Change

**Files:** `PlatingDetail.vue`, `HandcraftDetail.vue`

**Changes:**

1. `statusOptions` computed — change from always-empty `[]` to status-aware transitions:
   - `pending` → `[{ label: '进行中', value: 'processing' }]`
   - `processing` → `[{ label: '待发出', value: 'pending' }, { label: '已完成', value: 'completed' }]`
   - `completed` → `[{ label: '进行中', value: 'processing' }]`

2. Popselect binding — change `v-model:value="order.status"` to `:value="order?.status"` (one-way only). This prevents premature UI mutation before the API call confirms.

3. **Remove old imports:** Remove `updatePlatingStatus` import from `@/api/plating` in PlatingDetail; remove `updateHandcraftStatus` import from `@/api/handcraft` in HandcraftDetail. Add `changeOrderStatus` import from `@/api/kanban` in both files.

4. `doChangeStatus(newStatus)` — keep the `@update:value="doChangeStatus"` binding on `n-popselect` (not removed). Rewrite the **entire function body** (replacing the existing `updatePlatingStatus`/`updateHandcraftStatus` call inside the body — not only the import line, otherwise a ReferenceError occurs at runtime): show `dialog.warning` confirmation (same format as 功能二), then on confirm call `changeOrderStatus({ order_id: order.value.id, order_type: 'plating'|'handcraft', new_status: newStatus })`, then `loadData()`.

5. `order_type` values: `'plating'` for PlatingDetail, `'handcraft'` for HandcraftDetail.

---

## API Helper

**File:** `frontend/src/api/kanban.js`

**Add:**
```js
export const changeOrderStatus = (data) =>
  api.post('/kanban/order-status', data)
  // data: { order_id, order_type, new_status }
```

---

## KanbanBoard Update

**File:** `KanbanBoard.vue`

**Change:** Add `@refresh="reloadAll"` to `<VendorDetailModal>` so status changes from the detail modal are reflected in the kanban lanes.

---

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/api/kanban.js` | Add `changeOrderStatus` |
| `frontend/src/views/kanban/ReceiptModal.vue` | Fix vendor + item dropdown auto-load |
| `frontend/src/views/kanban/VendorDetailModal.vue` | Status change (功能二) + nav close (功能三) |
| `frontend/src/views/kanban/KanbanBoard.vue` | Listen `@refresh` |
| `frontend/src/views/plating/PlatingDetail.vue` | Enable status change with dialog (功能四) |
| `frontend/src/views/handcraft/HandcraftDetail.vue` | Enable status change with dialog (功能四) |
