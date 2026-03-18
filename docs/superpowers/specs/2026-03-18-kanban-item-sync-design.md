# Kanban Item Row Sync — Design Spec

**Date:** 2026-03-18
**Status:** Approved

---

## Problem

The kanban receipt/status-change code paths in `services/kanban.py` update `VendorReceipt` records and inventory logs, but do not sync the item-row columns (`received_qty`, `status`) on `PlatingOrderItem` and `HandcraftJewelryItem`. This causes the detail pages (`PlatingDetail`, `HandcraftDetail`) to display stale item states after any kanban operation.

### Affected Code Paths

| Function | What it does | What it misses |
|----------|-------------|---------------|
| `record_vendor_receipt()` | Writes VendorReceipt + inventory | Does not update `PlatingOrderItem.received_qty/status` or `HandcraftJewelryItem.received_qty/status` |
| `_force_complete_plating()` | Writes supplementary receipts, sets `order.status = completed` | Items still show `电镀中` |
| `_force_complete_handcraft()` | Writes supplementary receipts, sets `order.status = completed` | Items still show `制作中` |
| `change_order_status(processing→pending)` | Resets `item.status = "未送出"` | Does not reset `item.received_qty = 0` |
| `change_order_status(completed→processing)` | Undoes receipts, resets order status | Items still show `已收回` |

`HandcraftPartItem` has no `received_qty` or `status` columns (design gap, out of scope).

### Constraint

Only the kanban path (`POST /kanban/return`) is used for receipts going forward. The old `POST /plating/{id}/receive` and `POST /handcraft/{id}/receive` paths are deprecated. This means incremental sync (not recompute-from-VendorReceipts) is sufficient and correct.

---

## Scope

**Backend only.** Two files:
- `services/kanban.py` — sync logic
- `tests/test_kanban.py` — new test cases

No frontend changes. No model changes. No new API endpoints.

---

## Changes to `services/kanban.py`

### 1. `record_vendor_receipt()` — sync item rows after each receipt

After writing each `VendorReceipt` row and calling `add_stock`, additionally update the corresponding item rows:

- **`(order_type=plating, item_type=part)`**: query `PlatingOrderItem` rows where `plating_order_id=order_id` and `part_id=item_id`. Distribute the receipt qty FIFO across rows (fill each row up to its `qty`). Set `status = "已收回"` when `received_qty >= qty`.
- **`(order_type=handcraft, item_type=jewelry)`**: query `HandcraftJewelryItem` rows where `handcraft_order_id=order_id` and `jewelry_id=item_id`. Same distribution logic. Set `status = "已收回"` when `received_qty >= qty`.
- **`(order_type=handcraft, item_type=part)`**: no-op — `HandcraftPartItem` has no tracking columns.

This is implemented as a private helper `_sync_receipt_to_item_rows(db, order_id, order_type, item_id, item_type, qty)` called once per receipt in the loop.

### 2. `_force_complete_plating()` — mark all items fully received

After adding supplementary VendorReceipts:
```python
all_items = db.query(PlatingOrderItem).filter(PlatingOrderItem.plating_order_id == order.id).all()
for item in all_items:
    item.received_qty = float(item.qty)
    item.status = "已收回"
```

### 3. `_force_complete_handcraft()` — mark all jewelry items fully received

After adding supplementary VendorReceipts:
```python
all_jewelry = db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.handcraft_order_id == order.id).all()
for ji in all_jewelry:
    ji.received_qty = int(ji.qty)
    ji.status = "已收回"
```

### 4. `change_order_status(processing→pending)` — reset `received_qty = 0`

Currently the code already sets `item.status = "未送出"` for plating items and `ji.status = "未送出"` for handcraft jewelry items. Add `received_qty = 0` alongside each existing status reset:

- Plating: `item.received_qty = 0` (in the same loop that sets `item.status = "未送出"`)
- Handcraft jewelry: query `HandcraftJewelryItem` rows and set `ji.received_qty = 0` (current code only resets handcraft part items and jewelry item status)

### 5. `change_order_status(completed→processing)` — reset items to processing state

After `_undo_receipts_for_order()`, explicitly reset item rows:

- **Plating**: query all `PlatingOrderItem` rows for the order, set `received_qty = 0`, `status = "电镀中"`
- **Handcraft**: query all `HandcraftJewelryItem` rows for the order, set `received_qty = 0`, `status = "制作中"`

---

## New Tests in `tests/test_kanban.py`

### Group A — `POST /kanban/order-status` transitions (via `client` fixture)

| Test name | Transition | Assertions |
|-----------|-----------|-----------|
| `test_order_status_pending_to_processing_plating` | `pending→processing` | HTTP 200; `PlatingOrderItem.status = "电镀中"`; stock deducted |
| `test_order_status_processing_to_completed_plating` | `processing→completed` | HTTP 200; `PlatingOrderItem.received_qty = qty`, `status = "已收回"`; `order.status = "completed"` |
| `test_order_status_processing_to_pending_plating` | `processing→pending` | HTTP 200; `PlatingOrderItem.status = "未送出"`, `received_qty = 0`; stock restored |
| `test_order_status_completed_to_processing_plating` | `completed→processing` | HTTP 200; `PlatingOrderItem.status = "电镀中"`, `received_qty = 0`; `order.status = "processing"` |
| `test_order_status_pending_to_processing_handcraft` | `pending→processing` | HTTP 200; `HandcraftJewelryItem.status = "制作中"` |
| `test_order_status_processing_to_completed_handcraft` | `processing→completed` | HTTP 200; `HandcraftJewelryItem.received_qty = qty`, `status = "已收回"` |
| `test_order_status_processing_to_pending_handcraft` | `processing→pending` | HTTP 200; `HandcraftJewelryItem.status = "未送出"`, `received_qty = 0` |
| `test_order_status_completed_to_processing_handcraft` | `completed→processing` | HTTP 200; `HandcraftJewelryItem.status = "制作中"`, `received_qty = 0` |
| `test_order_status_invalid_transition` | `pending→completed` | HTTP 400 |
| `test_order_status_order_not_found` | non-existent order_id | HTTP 400 |

### Group B — `record_vendor_receipt()` item row sync (via `db` fixture)

| Test name | Scenario | Assertions |
|-----------|---------|-----------|
| `test_receipt_syncs_plating_item_received_qty` | Partial receipt (5 of 10) | `PlatingOrderItem.received_qty = 5`, `status = "电镀中"` |
| `test_receipt_full_receipt_marks_item_received` | Full receipt (10 of 10) | `PlatingOrderItem.received_qty = 10`, `status = "已收回"` |
| `test_receipt_syncs_handcraft_jewelry_received_qty` | Partial jewelry receipt | `HandcraftJewelryItem.received_qty` updated, `status = "制作中"` |
| `test_receipt_full_jewelry_receipt_marks_item_received` | Full jewelry receipt | `HandcraftJewelryItem.received_qty = qty`, `status = "已收回"` |

---

## What Does NOT Change

- Frontend — no changes needed; detail pages already read `received_qty` and `status` from API
- `HandcraftPartItem` — no columns to sync
- `receive_plating_items()` / `receive_handcraft_jewelries()` — deprecated paths, not removed yet but not changed
- All existing tests must continue to pass

---

## Files Changed

| File | Change |
|------|--------|
| `services/kanban.py` | Add `_sync_receipt_to_item_rows()` helper; call it in `record_vendor_receipt()`; update force-complete functions; fix `processing→pending` received_qty; add `completed→processing` item reset |
| `tests/test_kanban.py` | 14 new test cases in two groups |
