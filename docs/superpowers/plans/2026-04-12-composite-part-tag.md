# Composite Part Tag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small blue "组合" NTag badge next to part names everywhere they appear in the UI, for parts that have part_bom children.

**Architecture:** Add `is_composite` boolean column to the Part model, maintained automatically by `set_part_bom` and `delete_part_bom_item`. Propagate this flag through all service responses that include part info. On the frontend, extend `renderNamedImage` with an optional `tag` parameter and pass it from every part-rendering call site.

**Tech Stack:** FastAPI + SQLAlchemy (backend), Vue 3 + Naive UI (frontend)

---

## File Structure

**Backend changes:**
- Modify: `models/part.py` — add `is_composite` column
- Modify: `database.py` — add migration for `is_composite` + data backfill
- Modify: `services/part_bom.py` — maintain `is_composite` on set/delete
- Modify: `schemas/part.py` — add `is_composite` to `PartResponse`
- Modify: `services/order.py` — add `part_is_composite` to `get_parts_summary()`
- Modify: `services/order_todo.py` — add `part_is_composite` to `get_todo()`
- Modify: `services/plating.py` — add `part_is_composite` to `list_pending_receive_items()`
- Modify: `services/plating_receipt.py` — add `part_is_composite` to `_enrich_receipt()`
- Modify: `services/handcraft.py` — add `is_composite` to `list_handcraft_pending_receive_items()`
- Modify: `services/handcraft_receipt.py` — add `is_composite` to `_enrich_receipt()`
- Modify: `services/inventory.py` — add `is_composite` to `get_inventory_overview()`
- Modify: `services/part_bom.py` — add `child_is_composite` to `get_part_bom()`
- Modify: `services/jewelry_template.py` — add `part_is_composite` to `_enrich_items()`
- Modify: corresponding schemas in `schemas/`

**Frontend changes:**
- Modify: `frontend/src/utils/ui.js` — add `tag` parameter to `renderNamedImage`
- Modify: 11 Vue files that render part names with `renderNamedImage`

**Test file:**
- Modify: `tests/test_part_bom.py` — add `is_composite` flag tests

---

### Task 1: Add `is_composite` column to Part model + migration

**Files:**
- Modify: `models/part.py:23` (after `parent_part_id`)
- Modify: `database.py:57-68` (part migration block)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_part_bom.py`:

```python
def test_is_composite_flag_set_on_bom_create(client, db):
    """is_composite should be True after adding a BOM child."""
    parent, children = _setup_parts(db)
    # Before BOM: not composite
    assert parent.is_composite is False

    client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[0].id, "qty_per_unit": 2.0},
    )
    db.refresh(parent)
    assert parent.is_composite is True


def test_is_composite_flag_cleared_on_last_bom_delete(client, db):
    """is_composite should revert to False when all BOM children are removed."""
    parent, children = _setup_parts(db)
    resp = client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[0].id, "qty_per_unit": 2.0},
    )
    bom_id = resp.json()["id"]
    db.refresh(parent)
    assert parent.is_composite is True

    client.delete(f"/api/parts/bom/{bom_id}")
    db.refresh(parent)
    assert parent.is_composite is False


def test_is_composite_stays_true_when_one_bom_deleted(client, db):
    """is_composite should stay True if other BOM children remain."""
    parent, children = _setup_parts(db)
    resp1 = client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[0].id, "qty_per_unit": 2.0},
    )
    client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[1].id, "qty_per_unit": 1.0},
    )
    bom_id = resp1.json()["id"]

    client.delete(f"/api/parts/bom/{bom_id}")
    db.refresh(parent)
    assert parent.is_composite is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_part_bom.py::test_is_composite_flag_set_on_bom_create tests/test_part_bom.py::test_is_composite_flag_cleared_on_last_bom_delete tests/test_part_bom.py::test_is_composite_stays_true_when_one_bom_deleted -v`
Expected: FAIL with `AttributeError: 'Part' object has no attribute 'is_composite'`

- [ ] **Step 3: Add `is_composite` column to Part model**

In `models/part.py`, add after line 23 (`parent_part_id`):

```python
    is_composite = Column(Boolean, nullable=False, server_default="false")
```

Also add `Boolean` to the import on line 1:

```python
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String
```

- [ ] **Step 4: Add migration in `database.py`**

In `database.py`, inside the `if inspector.has_table("part"):` block (after the `assembly_cost` loop around line 68), add:

```python
            if "is_composite" not in columns:
                conn.execute(text("ALTER TABLE part ADD COLUMN is_composite BOOLEAN NOT NULL DEFAULT false"))
                # Backfill: set is_composite=true for parts that have part_bom children
                conn.execute(text(
                    "UPDATE part SET is_composite = true "
                    "WHERE id IN (SELECT DISTINCT parent_part_id FROM part_bom)"
                ))
                logger.warning("Added missing part.is_composite column (backfilled from part_bom)")
```

- [ ] **Step 5: Maintain `is_composite` in `set_part_bom`**

In `services/part_bom.py`, in the `set_part_bom` function, add after `db.flush()` (line 57, just before `recalc_part_unit_cost`):

```python
    parent.is_composite = True
```

This works because `parent` was already loaded on line 28.

- [ ] **Step 6: Maintain `is_composite` in `delete_part_bom_item`**

In `services/part_bom.py`, in the `delete_part_bom_item` function, after `db.flush()` (line 85), add:

```python
    # Check if parent still has any BOM children
    remaining = db.query(PartBom).filter_by(parent_part_id=parent_id).count()
    if remaining == 0:
        part = db.query(Part).filter_by(id=parent_id).first()
        if part:
            part.is_composite = False
            db.flush()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_part_bom.py::test_is_composite_flag_set_on_bom_create tests/test_part_bom.py::test_is_composite_flag_cleared_on_last_bom_delete tests/test_part_bom.py::test_is_composite_stays_true_when_one_bom_deleted -v`
Expected: All 3 PASS

- [ ] **Step 8: Commit**

```bash
git add models/part.py database.py services/part_bom.py tests/test_part_bom.py
git commit -m "feat: add is_composite flag to Part model with auto-maintenance"
```

---

### Task 2: Add `is_composite` to PartResponse schema + API test

**Files:**
- Modify: `schemas/part.py:45` (after `parent_part_id`)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_part_bom.py`:

```python
def test_part_response_includes_is_composite(client, db):
    """GET /api/parts/{id} should include is_composite field."""
    parent, children = _setup_parts(db)
    resp = client.get(f"/api/parts/{parent.id}")
    assert resp.status_code == 200
    assert resp.json()["is_composite"] is False

    client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[0].id, "qty_per_unit": 2.0},
    )
    resp = client.get(f"/api/parts/{parent.id}")
    assert resp.json()["is_composite"] is True


def test_list_parts_includes_is_composite(client, db):
    """GET /api/parts/ should include is_composite for each part."""
    parent, children = _setup_parts(db)
    client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[0].id, "qty_per_unit": 2.0},
    )
    resp = client.get("/api/parts/")
    assert resp.status_code == 200
    parts_map = {p["id"]: p for p in resp.json()}
    assert parts_map[parent.id]["is_composite"] is True
    assert parts_map[children[0].id]["is_composite"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_part_bom.py::test_part_response_includes_is_composite tests/test_part_bom.py::test_list_parts_includes_is_composite -v`
Expected: FAIL — `is_composite` key missing from response JSON

- [ ] **Step 3: Add `is_composite` to `PartResponse`**

In `schemas/part.py`, in the `PartResponse` class, add after line 45 (`parent_part_id`):

```python
    is_composite: bool = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_part_bom.py::test_part_response_includes_is_composite tests/test_part_bom.py::test_list_parts_includes_is_composite -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add schemas/part.py tests/test_part_bom.py
git commit -m "feat: expose is_composite in PartResponse schema"
```

---

### Task 3: Add `is_composite` to all service responses that return part info

This task adds the `is_composite` field to every service function and schema that returns part information displayed via `renderNamedImage`. The Part object is already loaded in each of these services, so we just need to include the field.

**Files:**
- Modify: `services/order.py:265` — `get_parts_summary()` dict
- Modify: `services/order_todo.py:95-98` — `get_todo()` dict
- Modify: `services/plating.py:395-398` — `list_pending_receive_items()` dict
- Modify: `services/plating_receipt.py:461-463` — `_enrich_receipt()`
- Modify: `services/handcraft.py:561-564` — `list_handcraft_pending_receive_items()` part items
- Modify: `services/handcraft.py:623-629` — `list_handcraft_pending_receive_items()` jewelry items
- Modify: `services/handcraft_receipt.py:310-312` — `_enrich_receipt()` part items
- Modify: `services/inventory.py:116-124` — `get_inventory_overview()` part items
- Modify: `services/part_bom.py:67-74` — `get_part_bom()` child part info
- Modify: `services/jewelry_template.py:20-27` — `_enrich_items()`
- Modify: `schemas/order.py:202-203` — `PartsSummaryItemResponse`
- Modify: `schemas/order.py:87-88` — `OrderTodoItemResponse`
- Modify: `schemas/plating.py:94-96` — `PendingReceiveItemResponse`
- Modify: `schemas/plating_receipt.py:75` — `PlatingReceiptItemResponse`
- Modify: `schemas/handcraft_receipt.py:88` — `HandcraftReceiptItemResponse`
- Modify: `schemas/inventory.py:23-24` — `InventoryOverviewItem`
- Modify: `schemas/part_bom.py:18-19` — `PartBomResponse`
- Modify: `schemas/jewelry_template.py:33-34` — `JewelryTemplateItemResponse`
- Modify: `schemas/handcraft.py` — `HandcraftPartItemResponse` (for plating/handcraft detail pages that build from partMap)

Note: `PlatingDetail.vue`, `HandcraftDetail.vue`, and `PurchaseOrderDetail.vue` build part info from `partMap` loaded via `listParts()` → `PartResponse`, so they are already covered by Task 2. These pages enrich their items client-side using `partMap.value[i.part_id]`. The frontend task (Task 4) will read `is_composite` from `partMap`.

- [ ] **Step 1: Add `is_composite` / `part_is_composite` to all schemas**

In `schemas/order.py`, `PartsSummaryItemResponse` class, add after `part_image`:

```python
    part_is_composite: bool = False
```

In `schemas/order.py`, `OrderTodoItemResponse` class, add after `part_image`:

```python
    part_is_composite: Optional[bool] = None
```

In `schemas/plating.py`, `PendingReceiveItemResponse` class, add after `part_image`:

```python
    part_is_composite: bool = False
```

In `schemas/plating_receipt.py`, `PlatingReceiptItemResponse` class, add after `part_name`:

```python
    part_is_composite: Optional[bool] = None
```

In `schemas/handcraft_receipt.py`, `HandcraftReceiptItemResponse` class, add after `item_name`:

```python
    is_composite: Optional[bool] = None
```

In `schemas/inventory.py`, `InventoryOverviewItem` class, add after `image`:

```python
    is_composite: Optional[bool] = None
```

In `schemas/part_bom.py`, `PartBomResponse` class, add after `child_part_image`:

```python
    child_is_composite: Optional[bool] = None
```

In `schemas/jewelry_template.py`, `JewelryTemplateItemResponse` class, add after `part_image`:

```python
    part_is_composite: Optional[bool] = None
```

- [ ] **Step 2: Add `is_composite` to `get_parts_summary()` in `services/order.py`**

In the result dict around line 265, add after the `"part_image"` line:

```python
            "part_is_composite": p.is_composite if p else False,
```

- [ ] **Step 3: Add `part_is_composite` to `get_todo()` in `services/order_todo.py`**

In the result dict around line 97-98, add after `"part_image"`:

```python
            "part_is_composite": part.is_composite if part else None,
```

- [ ] **Step 4: Add `part_is_composite` to `list_pending_receive_items()` in `services/plating.py`**

This function uses a SQL query with `.label()` for columns. The `Part` object is aliased as `SendPart`. We need to add the `is_composite` column to the query.

In the query select list (around line 356-357), after `SendPart.image.label("part_image")`, add:

```python
            SendPart.is_composite.label("part_is_composite"),
```

In the result dict (around line 397-398), after `"part_image"`, add:

```python
            "part_is_composite": row.part_is_composite,
```

- [ ] **Step 5: Add `part_is_composite` to `_enrich_receipt()` in `services/plating_receipt.py`**

Around line 461-463, after `item.part_name = part.name`, add:

```python
            item.part_is_composite = part.is_composite
```

- [ ] **Step 6: Add `is_composite` to `list_handcraft_pending_receive_items()` in `services/handcraft.py`**

For part items query (around line 531-532), after `Part.image.label("item_image")`, add:

```python
            Part.is_composite.label("is_composite"),
```

In the part items result dict (around line 563-564), after `"item_image"`, add:

```python
            "is_composite": row.is_composite,
```

For jewelry output items (around line 623-629), these can be jewelry or parts. Add `is_composite: False` since output items are jewelry (not composite parts):

```python
            "is_composite": False,
```

- [ ] **Step 7: Add `is_composite` to `_enrich_receipt()` in `services/handcraft_receipt.py`**

For part items (around line 310-312), after `item.item_name = part.name`, add:

```python
                item.is_composite = part.is_composite
```

For jewelry items, set `item.is_composite = False` (jewelry items are not composite parts).

- [ ] **Step 8: Add `is_composite` to `get_inventory_overview()` in `services/inventory.py`**

In the part items result dict (around line 116-124), after `"image"`, add:

```python
                "is_composite": part.is_composite,
```

In the jewelry items result dict (around line 138-146), add:

```python
                "is_composite": False,
```

- [ ] **Step 9: Add `child_is_composite` to `get_part_bom()` in `services/part_bom.py`**

In the result dict (around line 67-74), after `"child_part_image"`, add:

```python
            "child_is_composite": child.is_composite if child else None,
```

- [ ] **Step 10: Add `part_is_composite` to `_enrich_items()` in `services/jewelry_template.py`**

In the result dict (around line 20-27), after `"part_image"`, add:

```python
            "part_is_composite": part.is_composite if part else None,
```

- [ ] **Step 11: Run full test suite**

Run: `pytest -x -q`
Expected: All tests pass. No existing tests should break since all new fields have default values.

- [ ] **Step 12: Commit**

```bash
git add schemas/ services/
git commit -m "feat: propagate is_composite through all part-related service responses"
```

---

### Task 4: Frontend — add composite tag to `renderNamedImage` and all call sites

**Files:**
- Modify: `frontend/src/utils/ui.js:71-86` — add `tag` parameter
- Modify: `frontend/src/views/parts/PartList.vue:587`
- Modify: `frontend/src/views/parts/PartDetail.vue:265`
- Modify: `frontend/src/views/orders/OrderDetail.vue:1210,1272`
- Modify: `frontend/src/views/plating/PlatingDetail.vue:1308`
- Modify: `frontend/src/views/plating-receipts/PlatingReceiptDetail.vue:946`
- Modify: `frontend/src/views/plating-receipts/PlatingReceiptCreate.vue:248`
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue:1176,1308`
- Modify: `frontend/src/views/handcraft-receipts/HandcraftReceiptCreate.vue:287,370`
- Modify: `frontend/src/views/handcraft-receipts/HandcraftReceiptDetail.vue:1009,1090`
- Modify: `frontend/src/views/jewelries/JewelryDetail.vue:274`
- Modify: `frontend/src/views/InventoryOverview.vue:159`
- Modify: `frontend/src/views/purchase-orders/PurchaseOrderDetail.vue:1091`

- [ ] **Step 1: Add `tag` parameter to `renderNamedImage` in `ui.js`**

Replace the `renderNamedImage` function (lines 71-86) with:

```javascript
export function renderNamedImage(name, image, fallback, size = 40, tag = null) {
  const children = [
    renderImageThumb(image, name || fallback || '图片', size),
    h('span', fallback || name || '-'),
  ]
  if (tag) {
    children.push(
      h('span', {
        style: {
          fontSize: '11px',
          lineHeight: '1',
          padding: '2px 6px',
          borderRadius: '3px',
          whiteSpace: 'nowrap',
          fontWeight: '500',
          background: '#e8f4ff',
          color: '#2080f0',
          border: '1px solid #b8deff',
          flexShrink: '0',
        },
      }, tag)
    )
  }
  return h(
    'div',
    {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
      },
    },
    children,
  )
}
```

- [ ] **Step 2: Update `PartList.vue`**

Line 587 — data comes from `listParts()` → `PartResponse`, row has `is_composite`:

```javascript
    render: (row) => renderNamedImage(row.name, row.image, row.name, 40, row.is_composite ? '组合' : null),
```

- [ ] **Step 3: Update `PartDetail.vue`**

Line 265 — data comes from `getPartBom()`, row has `child_is_composite`:

```javascript
    render: (row) => renderNamedImage(row.child_part_name, row.child_part_image, row.child_part_name, 40, row.child_is_composite ? '组合' : null),
```

- [ ] **Step 4: Update `InventoryOverview.vue`**

Line 159 — data comes from `getInventoryOverview()`, row has `is_composite`:

```javascript
    render: (row) => renderNamedImage(row.name, row.image, row.name, 40, row.is_composite ? '组合' : null),
```

- [ ] **Step 5: Update `OrderDetail.vue`**

Line 1210 — parts-summary table, data from `get_parts_summary()`, row has `part_is_composite`:

```javascript
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name, 40, row.part_is_composite ? '组合' : null),
```

Line 1272 — todo parts table, data from `get_todo()`, row has `part_is_composite`:

```javascript
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name, 40, row.part_is_composite ? '组合' : null),
```

- [ ] **Step 6: Update `PlatingDetail.vue`**

Line 1308 — items enriched from `partMap`, row has `part_id`. Read `is_composite` from partMap:

Change the render to:

```javascript
      const content = renderNamedImage(row.part_name, row.part_image, row.part_name, 40, partMap.value[row.part_id]?.is_composite ? '组合' : null)
```

- [ ] **Step 7: Update `PlatingReceiptDetail.vue`**

Line 946 — data from `_enrich_receipt()`, row has `part_is_composite`:

```javascript
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name, 40, row.part_is_composite ? '组合' : null),
```

- [ ] **Step 8: Update `PlatingReceiptCreate.vue`**

Line 248 — data from `list_pending_receive_items()`, row has `part_is_composite`:

```javascript
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name, 40, row.part_is_composite ? '组合' : null),
```

- [ ] **Step 9: Update `HandcraftDetail.vue`**

Line 1176 — part items enriched from `partMap`:

```javascript
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name, 40, partMap.value[row.part_id]?.is_composite ? '组合' : null),
```

Line 1308 — jewelry output items (display_name). These can be jewelry or parts. Check output_type:

```javascript
    render: (row) => renderNamedImage(row.display_name, row.display_image, row.display_name, 40, row.output_type === '配件' && partMap.value[row.part_id]?.is_composite ? '组合' : null),
```

- [ ] **Step 10: Update `HandcraftReceiptCreate.vue`**

Lines 287 and 370 — data from `list_handcraft_pending_receive_items()`, row has `is_composite`:

```javascript
    render: (row) => renderNamedImage(row.item_name, row.item_image, row.item_name, 40, row.is_composite ? '组合' : null),
```

Apply to both lines (287 and 370).

- [ ] **Step 11: Update `HandcraftReceiptDetail.vue`**

Lines 1009 and 1090 — data from `_enrich_receipt()`, row has `is_composite`:

```javascript
    render: (row) => renderNamedImage(row.item_name, row.item_image, row.item_name, 40, row.is_composite ? '组合' : null),
```

Apply to both lines (1009 and 1090).

- [ ] **Step 12: Update `JewelryDetail.vue`**

Line 274 — data from `_enrich_items()` in jewelry_template, row has `part_is_composite`:

```javascript
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name, 40, row.part_is_composite ? '组合' : null),
```

- [ ] **Step 13: Update `PurchaseOrderDetail.vue`**

Line 1091 — items enriched from `partMap`:

```javascript
      return renderNamedImage(row.part_name, row.part_image, row.part_name, 40, partMap.value[row.part_id]?.is_composite ? '组合' : null)
```

- [ ] **Step 14: Commit**

```bash
git add frontend/src/utils/ui.js frontend/src/views/
git commit -m "feat: show 组合 tag badge on composite parts across all pages"
```

---

### Task 5: Cleanup mockup file

- [ ] **Step 1: Remove mockup file**

```bash
rm mockup_composite_tag.html
```

- [ ] **Step 2: Run full test suite to confirm nothing is broken**

Run: `pytest -x -q`
Expected: All tests pass

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: remove composite tag mockup file"
```
