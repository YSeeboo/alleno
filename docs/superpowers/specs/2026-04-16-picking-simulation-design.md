# Picking Simulation (配货模拟) — Design

**Date:** 2026-04-16
**Status:** Draft
**Area:** Order detail · 配件汇总(BOM) section

## Problem

The current 配件汇总(BOM) section on the order detail page has an "导出 PDF"
button that generates a summary of parts with stock information. In practice,
when warehouse staff pick parts for an order, this view gives limited help:

- It shows aggregated totals per part, but not the breakdown that explains
  *why* a part is needed at that quantity (i.e., which jewelries and at
  what `qty_per_unit` each contributed).
- Composite parts (组合配件) are not expanded, so their atomic children
  don't appear in the summary — the picker has to look up the composite's
  BOM manually.
- There is no way to mark a part as "已配货" and track picking progress.

Staff want a dedicated view that is purpose-built for the picking workflow:
**here is exactly what to pull from shelves, broken down so I can double-check,
and let me mark each one done as I go.**

## Goal

Replace the "导出 PDF" button on the order detail 配件汇总 card with a
**配货模拟** button. Clicking it opens a modal that shows a picking-oriented
view of all parts needed for the order (composite parts expanded to atoms),
grouped by part with variant rows for distinct `qty_per_unit` values. Picking
state (which rows are already picked) is persisted server-side per order.
A new "导出 PDF" button inside the modal generates a printable picking list
containing only the still-unpicked items, with an empty "完成" column for
manual checking.

## Non-Goals (YAGNI)

Explicitly excluded:

- Multi-user concurrent picking UX (real-time sync, WebSocket, optimistic-lock
  conflict resolution). Simultaneous picking on two devices can occasionally
  produce stale UI, which is acceptable for current usage.
- Historical audit trail (who picked, when, with log of un-pick events).
  The picking table only stores current state; no history.
- Inventory movement. Marking a row as picked does NOT touch `inventory_log`
  or change stock. 配货模拟 is a UI helper, not a stock transition.
- Extending this feature to handcraft orders (HC-) or plating orders (EP-).
  This spec covers customer orders (OR-) only.
- Relevance-sorting, filters, or search inside the picking modal beyond the
  single "只看未完成" toggle.
- "Assign picker / approve" workflow.

## Design

### Data model

New table `order_picking_record`:

| column         | type         | notes                                        |
|----------------|--------------|----------------------------------------------|
| `id`           | Integer PK   | auto                                         |
| `order_id`     | String(20)   | FK → `order.id`, indexed                     |
| `part_id`      | String(30)   | FK → `part.id`                               |
| `qty_per_unit` | Numeric(10,4)| matches `bom.qty_per_unit`                   |
| `picked_at`    | DateTime     | default `now_beijing()`                      |

Unique constraint: `(order_id, part_id, qty_per_unit)`.

Semantics: **row exists = picked**. Unpick = delete the row. No `picked`
boolean column (avoids two-way state sync with the row's existence).

Migration: follow the project's additive-migration pattern via
`Base.metadata.create_all()` on FastAPI startup. No Alembic step required.

### Aggregation logic

New service `get_picking_simulation(db, order_id) -> list[PickingPartRow]`
in a new file `services/picking.py`.

Algorithm:

1. Load all `OrderItem` rows for `order_id` (regardless of item status —
   matches the existing `get_parts_summary` behavior).
2. For each `(jewelry_id, units_count)`, load the jewelry's BOM.
3. For each BOM row whose part is composite (`part.is_composite == True`),
   recursively expand using the existing helper
   `services.cutting_stats._expand_composite_part()`. The composite part
   itself does NOT appear in the output; only its atomic children do.
   Track per-triple whether it originated from a composite expansion.
4. Collect triples `(part_id, qty_per_unit, units_count)`.
5. Group by `(part_id, qty_per_unit)`; sum `units_count`. Each resulting
   entry becomes a *variant*.
6. Group variants by `part_id` into part rows. Attach `part_name`,
   `part_image`, and `current_stock` (via the existing
   `SUM(change_qty) FROM inventory_log` pattern) at the part level.
   Set `is_composite_child = True` on a part if **any** of the contributing
   triples came from a composite expansion (so a part that appears both
   directly and via a composite still gets the badge — it tells the picker
   "this part is needed at least partly because of a composite parent").
7. Join against `order_picking_record` for this `order_id` to set each
   variant's `picked` flag.
8. Compute `total_required = sum(v.subtotal for v in variants)` per part.
9. Return in a stable order: by `part_id` ascending.

The helpers `_expand_composite_part` and the BOM batch-load pattern in
`services/order.py::get_parts_summary` are reused where possible.

### API endpoints

All handlers live in `api/orders.py` under `/orders/{order_id}/picking`:

| Method | Path                                   | Body                              | Response                                   | Purpose                                   |
|--------|----------------------------------------|-----------------------------------|--------------------------------------------|-------------------------------------------|
| GET    | `/orders/{id}/picking`                 | —                                 | `PickingSimulationResponse`                | Fetch data for the modal                  |
| POST   | `/orders/{id}/picking/mark`            | `{part_id, qty_per_unit}`         | `{picked: true, picked_at}`                | Mark a variant as picked (idempotent)     |
| POST   | `/orders/{id}/picking/unmark`          | `{part_id, qty_per_unit}`         | `{picked: false}`                          | Unmark a variant (idempotent)             |
| DELETE | `/orders/{id}/picking/reset`           | —                                 | `{deleted: <int>}`                         | Clear all picking records for this order  |
| POST   | `/orders/{id}/picking/pdf`             | `{include_picked?: false}`        | `application/pdf` blob                     | Export picking list PDF                   |

Note: `mark` and `unmark` use POST (not DELETE) because some HTTP proxies
strip request bodies from DELETE; POST is portable and the semantic pair
is clear.

Validation rules:

- Order must exist → else 404.
- For `POST /mark` and `POST /unmark`: `(part_id, qty_per_unit)` must match
  an existing variant in the order's picking-simulation result → else 400
  `"该配件/变体不在此订单配货范围内"`.
- For `POST /pdf`: if no parts remain to pick (empty result after applying
  `include_picked` filter) → 400 `"没有需要配货的配件"`.
- All business errors bubble through the existing `service_errors()`
  context manager.

### Pydantic schemas

Added to `schemas/order.py`:

```python
class PickingVariant(BaseModel):
    qty_per_unit: float
    units_count: int
    subtotal: float
    picked: bool

class PickingPartRow(BaseModel):
    part_id: str
    part_name: str
    part_image: str | None
    current_stock: float
    is_composite_child: bool
    variants: list[PickingVariant]
    total_required: float

class PickingProgress(BaseModel):
    total: int     # total number of variant rows
    picked: int    # number of variant rows currently marked picked

class PickingSimulationResponse(BaseModel):
    order_id: str
    customer_name: str
    rows: list[PickingPartRow]
    progress: PickingProgress

class PickingMarkRequest(BaseModel):
    part_id: str
    qty_per_unit: float

class PickingPdfRequest(BaseModel):
    include_picked: bool = False
```

### Frontend

Component `frontend/src/components/picking/PickingSimulationModal.vue` (new).

Props: `orderId: string`, `customerName: string`. Emits: `close`.

Structure:

```
┌─────────────────────────────────────────────────────────┐
│ 配货模拟 · 订单 OR-0123                             [ × ]│
├─────────────────────────────────────────────────────────┤
│ 客户：张女士    进度：3 / 12 已完成   [□ 只看未完成]    │
│                          [ 导出 PDF ]  [ 重置勾选 ]    │
├─────────────────────────────────────────────────────────┤
│ 配件编号 │ 配件             │ 单份 │ 份数 │ 总数 │ 库存 │ ✓ │
├─────────────────────────────────────────────────────────┤
│ PJ-X-001 │ [img] 小珠子     │  2   │  18  │ 36   │  45  │ □ │
│          │                  │  3   │  5   │ 15   │      │ □ │
│ PJ-X-002 │ [img] 金属扣     │  1   │  10  │ 10   │   8  │ ☑ │
│ PJ-X-003 │ [img] 焊接片 [组合] │  2   │  10  │ 20   │  60  │ □ │
│ ...                                                      │
└─────────────────────────────────────────────────────────┘
```

UI behavior:

- Table uses Naive UI's `n-data-table` with manual rowspan for the
  part-level columns (`配件编号`, `配件`, `库存`); variant rows share these.
- Variant rows alternate with a subtle dashed internal border
  (separator between `qty_per_unit` variants of the same part).
- Completed rows render at `opacity: 0.5` with `text-decoration: line-through`
  on the numeric columns; the checkbox shows checked.
- Checkbox clicks optimistically update local state, then call
  `POST/DELETE /picking/mark`. On failure, revert and show a toast.
- "只看未完成" toggle filters client-side: a part is hidden if *all* its
  variants are picked.
- "重置勾选" opens an `n-popconfirm`; on confirm, calls
  `DELETE /picking/reset` and refreshes the modal data.
- Composite-expanded parts show the existing "组合" tag badge
  (same style as commit `b13af0c`, which added this tag across jewelry/handcraft
  pages) next to the part name.
- Progress indicator in the header counts picked variants vs total variants.

`OrderDetail.vue` changes:

- Replace the "导出 PDF" button in the 配件汇总 card header with a
  "配货模拟" button that opens the new modal.
- Delete the `doPartsSummaryPdfExport()` function and related imports.

`frontend/src/services/orders.js`:

- Remove `downloadPartsSummaryPdf()`.
- Add `getPickingSimulation(orderId)`,
  `markPicked(orderId, partId, qtyPerUnit)`,
  `unmarkPicked(orderId, partId, qtyPerUnit)`,
  `resetPicking(orderId)`,
  `downloadPickingListPdf(orderId, { includePicked })`.

### PDF generation

New file `services/picking_list_pdf.py` — around 200 lines, independent
of the old `parts_summary_pdf.py` (which is deleted entirely).

Layout parameters:

- A4 595×842pt, margins 40pt → usable 515×762pt.
- Image cell: 45×45pt (≈1.6cm), chosen so ~12 single-variant rows fit per
  page (row height ≈ 55pt).
- Column widths (7 columns, sum = 515pt):

| 配件编号 | 配件   | 单份 | 份数 | 总数量 | 库存 | 完成 |
|----------|--------|------|------|--------|------|------|
| 55pt     | 185pt  | 45pt | 45pt | 60pt   | 55pt | 70pt |

Data flow:

1. Handler invokes `get_picking_simulation(db, order_id)`.
2. If `include_picked == False` (default), drop variants with `picked=True`;
   drop parts whose variants are all picked.
3. Concurrently prefetch part images via a shared helper
   `services/_pdf_helpers.py::_prefetch_images()` (extracted from the old
   `parts_summary_pdf.py`).
4. Build a ReportLab `Table` with row spans matching the modal layout.
5. Header includes order ID, customer name, date.
6. Footer shows `第 N / M 页` and `Allen Shop · 饰品店管理系统`.
7. Return `bytes`.

Edge cases:

- Empty after filtering → service raises `ValueError` (handler returns 400).
- Image download fails → render as grey placeholder box (same behavior as
  existing PDF generator).
- Long part names → wrap within the cell; if still too tall, truncate with `…`.

### Shared PDF helper

To keep the cleanup surface small:

- Move `_fit_image()` and `_prefetch_images()` out of
  `services/parts_summary_pdf.py` into new `services/_pdf_helpers.py`.
- Delete `services/parts_summary_pdf.py` and its `build_parts_summary_pdf()`.
- The shared helpers now serve `picking_list_pdf.py` and any future PDF
  generators.

### Old endpoint removal

Delete all of the following in the same change:

- `POST /orders/{order_id}/parts-summary/pdf` route in `api/orders.py`.
- `PartsSummaryPdfRequest` schema.
- `build_parts_summary_pdf()` and `services/parts_summary_pdf.py`.
- Frontend `downloadPartsSummaryPdf()` helper.
- The "导出 PDF" button wiring in `OrderDetail.vue`.

No deprecation / compatibility shim — the old PDF is replaced by the new
picking list and has no other callers.

## Testing

### Service tests — `tests/test_service_picking.py`

- Basic aggregation: order with 2 jewelries, each using 2 parts → variants
  match expected totals.
- Composite expansion: a jewelry BOM contains a composite part → output
  contains only the atomic children with `is_composite_child=True`, and
  the composite itself does not appear.
- Multi-variant aggregation: one part used at two distinct `qty_per_unit`
  across three jewelries → produces two variants, `units_count` correctly
  summed within each variant.
- Empty order → `rows=[]`, `progress={"total": 0, "picked": 0}`.
- `mark_picked` idempotency: calling twice creates only one record.
- `mark_picked` validation: `(part_id, qty_per_unit)` outside the
  aggregation result → raises `ValueError`.
- `unmark_picked` idempotency: calling on a non-existent record is silent.
- `reset_picking`: clears all records for the order, returns the deleted count.
- Stock is computed correctly via inventory_log sum.

### API tests — `tests/test_api_picking.py`

- `GET /orders/{id}/picking` → 200 with expected shape.
- `GET` 404 for unknown order.
- `POST /picking/mark` → 200, idempotent.
- `POST /picking/mark` → 400 when body references an invalid variant.
- `DELETE /picking/mark` → 200, idempotent.
- `DELETE /picking/reset` → 200.
- `POST /picking/pdf` → 200, `Content-Type: application/pdf`,
  `Content-Disposition` filename includes `配货清单_{order_id}.pdf`
  (UTF-8 encoded per existing pattern).
- `POST /picking/pdf` → 400 when no parts remain to pick.

PDF rendering is not asserted cell-by-cell; tests only verify a non-empty
`bytes` response and correct content-type. Visual correctness is reviewed
manually against the mockup.

### Frontend

No automated tests (project does not run frontend unit tests). Manual QA
against the mockups at `frontend/mockup_picking_variants.html` and
`frontend/mockup_picking_pdf.html`.

## Deployment

- `deploy_aliyun_update.sh` unchanged.
- Release order: backend first (triggers `create_all()` to create the new
  table), then frontend (so new requests land on the updated backend).
- No data backfill — existing orders start with zero picking records,
  which correctly means "nothing picked yet".

## References

- Mockup A: `frontend/mockup_picking_variants.html` — modal variant-row UI
  options (selected: rowspan merge, no subtotal row).
- Mockup B: `frontend/mockup_picking_pdf.html` — PDF image size comparison
  (selected: 45pt image for ~12 rows per A4 page).
- Prior art for composite expansion: `services/cutting_stats.py`
  `_expand_composite_part()`.
- Prior art for additive migrations: `database.py::ensure_schema_compat()`
  pattern.
- Existing parts summary aggregation being retained:
  `services/order.py::get_parts_summary()` (unchanged by this spec).
