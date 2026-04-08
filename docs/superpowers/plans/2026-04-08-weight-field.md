# 发出/收回重量字段 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add weight and weight_unit fields to plating/handcraft order items and receipt items. Include weight in PDF exports.

**Architecture:** Add 2 columns (weight, weight_unit) to 5 tables. Update schemas, PDF export, and frontend tables.

**Tech Stack:** FastAPI, SQLAlchemy, Vue 3 + Naive UI, ReportLab (PDF)

**Spec:** `docs/superpowers/specs/2026-04-08-weight-field-design.md`

---

## File Structure

| File | Changes |
|------|---------|
| `models/plating_order.py` | Add weight, weight_unit to PlatingOrderItem |
| `models/handcraft_order.py` | Add weight, weight_unit to HandcraftPartItem and HandcraftJewelryItem |
| `models/plating_receipt.py` | Add weight, weight_unit to PlatingReceiptItem |
| `models/handcraft_receipt.py` | Add weight, weight_unit to HandcraftReceiptItem |
| `database.py` | Schema compat for 10 new columns |
| `schemas/plating.py` | Add weight fields to create/response schemas |
| `schemas/handcraft.py` | Add weight fields to create/response schemas |
| `schemas/plating_receipt.py` | Add weight fields to create/response schemas |
| `schemas/handcraft_receipt.py` | Add weight fields to create/response schemas |
| `services/plating_export.py` | Add weight column to PDF |
| `services/handcraft_export.py` | Add weight column to PDF |
| `frontend/src/views/plating/PlatingDetail.vue` | Add weight column |
| `frontend/src/views/handcraft/HandcraftDetail.vue` | Add weight column |
| `frontend/src/views/plating/PlatingReceiptDetail.vue` | Add weight column |
| `frontend/src/views/handcraft/HandcraftReceiptDetail.vue` | Add weight column |
| `frontend/src/views/handcraft/HandcraftReceiptCreate.vue` | Add weight column |
| `tests/test_api_parts.py` or new test file | Weight field tests |

---

## Task 1: Backend — Models + Schema Compat

**Files:**
- Modify: `models/plating_order.py`
- Modify: `models/handcraft_order.py`
- Modify: `models/plating_receipt.py`
- Modify: `models/handcraft_receipt.py`
- Modify: `database.py`

- [ ] **Step 1: Add weight columns to all 5 models**

In `models/plating_order.py`, add to PlatingOrderItem after `qty`:

```python
    weight = Column(Numeric(10, 4), nullable=True)
    weight_unit = Column(String, nullable=True, default="g")
```

In `models/handcraft_order.py`, add same 2 fields to HandcraftPartItem (after `qty`) and HandcraftJewelryItem (after `qty`).

In `models/plating_receipt.py`, add same 2 fields to PlatingReceiptItem (after `qty`).

In `models/handcraft_receipt.py`, add same 2 fields to HandcraftReceiptItem (after `qty`).

- [ ] **Step 2: Add schema compat**

In `database.py`, add to `ensure_schema_compat()`:

```python
# --- weight fields ---
for table_name in [
    "plating_order_item",
    "handcraft_part_item",
    "handcraft_jewelry_item",
    "plating_receipt_item",
    "handcraft_receipt_item",
]:
    if inspector.has_table(table_name):
        cols = [c["name"] for c in inspector.get_columns(table_name)]
        if "weight" not in cols:
            conn.execute(text(
                f"ALTER TABLE {table_name} ADD COLUMN weight NUMERIC(10,4)"
            ))
        if "weight_unit" not in cols:
            conn.execute(text(
                f"ALTER TABLE {table_name} ADD COLUMN weight_unit VARCHAR DEFAULT 'g'"
            ))
```

- [ ] **Step 3: Verify models load**

Run: `python -c "from models.plating_order import PlatingOrderItem; print([c.name for c in PlatingOrderItem.__table__.columns])"`
Expected: includes `weight`, `weight_unit`

- [ ] **Step 4: Commit**

```bash
git add models/plating_order.py models/handcraft_order.py models/plating_receipt.py models/handcraft_receipt.py database.py
git commit -m "feat: add weight and weight_unit columns to order and receipt items"
```

---

## Task 2: Backend — Schemas

**Files:**
- Modify: `schemas/plating.py`
- Modify: `schemas/handcraft.py`
- Modify: `schemas/plating_receipt.py`
- Modify: `schemas/handcraft_receipt.py`

- [ ] **Step 1: Add weight fields to all schemas**

In `schemas/plating.py`:
- `PlatingItemCreate`: add `weight: float | None = None` and `weight_unit: str | None = None`
- `PlatingItemResponse`: add same 2 fields

In `schemas/handcraft.py`:
- `HandcraftPartIn`: add `weight: float | None = None` and `weight_unit: str | None = None`
- `HandcraftPartItemResponse`: add same 2 fields
- `HandcraftJewelryIn`: add same 2 fields
- `HandcraftJewelryItemResponse`: add same 2 fields

In `schemas/plating_receipt.py`:
- `PlatingReceiptItemCreate`: add same 2 fields
- `PlatingReceiptItemResponse`: add same 2 fields

In `schemas/handcraft_receipt.py`:
- `HandcraftReceiptItemCreate`: add same 2 fields
- `HandcraftReceiptItemResponse`: add same 2 fields

- [ ] **Step 2: Verify imports**

Run: `python -c "from schemas.plating import PlatingItemCreate; print(PlatingItemCreate.model_fields.keys())"`
Expected: includes `weight`, `weight_unit`

- [ ] **Step 3: Commit**

```bash
git add schemas/plating.py schemas/handcraft.py schemas/plating_receipt.py schemas/handcraft_receipt.py
git commit -m "feat: add weight fields to plating and handcraft schemas"
```

---

## Task 3: Backend — Tests + PDF Export

**Files:**
- Modify: `services/plating_export.py`
- Modify: `services/handcraft_export.py`
- Test: new or existing test file

- [ ] **Step 1: Write failing tests**

Add tests to verify weight is stored and returned:

```python
def test_plating_item_weight(client, db):
    """Plating order item stores and returns weight."""
    from models.part import Part
    part = Part(id="PJ-X-WT1", name="重量测试", category="小配件")
    db.add(part)
    db.flush()
    from services.inventory import add_stock
    add_stock(db, "part", part.id, 100, "入库")
    db.flush()

    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀商",
        "items": [{"part_id": part.id, "qty": 50, "weight": 150.5, "weight_unit": "g"}],
    })
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["weight"] == 150.5
    assert item["weight_unit"] == "g"


def test_handcraft_part_item_weight(client, db):
    """Handcraft part item stores and returns weight."""
    from models.part import Part
    part = Part(id="PJ-X-WT2", name="手工重量测试", category="小配件")
    db.add(part)
    db.flush()
    from services.inventory import add_stock
    add_stock(db, "part", part.id, 100, "入库")
    db.flush()

    resp = client.post("/api/handcraft/", json={
        "supplier_name": "手工商",
        "parts": [{"part_id": part.id, "qty": 30, "weight": 2.5, "weight_unit": "kg"}],
    })
    assert resp.status_code == 200
    item = resp.json()["part_items"][0]
    assert item["weight"] == 2.5
    assert item["weight_unit"] == "kg"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_weight.py -v` (or wherever you place the tests)
Expected: FAIL

- [ ] **Step 3: Update services to pass weight through**

The create/update functions in `services/plating.py` and `services/handcraft.py` should already pass through all fields from the schema to the model. Verify that `weight` and `weight_unit` are included when creating items. If the service uses explicit field assignment, add the two fields.

- [ ] **Step 4: Run tests**

Expected: PASS

- [ ] **Step 5: Update PDF exports**

In `services/plating_export.py`, modify `get_plating_export_payload()`:
- Add `weight` and `weight_unit` to the detail row dict
- In the PDF column layout, add "重量" column after 数量
- Display format: `f"{weight} {weight_unit}"` (e.g., "150 g")
- Reduce note column width to make room

In `services/handcraft_export.py`, same changes.

- [ ] **Step 6: Run full test suite**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add services/plating.py services/handcraft.py services/plating_export.py services/handcraft_export.py tests/
git commit -m "feat: support weight in plating/handcraft items and PDF export"
```

---

## Task 4: Frontend — Plating Detail Weight Column

**Files:**
- Modify: `frontend/src/views/plating/PlatingDetail.vue`

- [ ] **Step 1: Add weight column to items table**

In the plating order items table columns, after the qty column, add:

```javascript
{
  title: '重量',
  key: 'weight',
  width: 140,
  render(row) {
    if (!canEdit.value) {
      return row.weight ? `${row.weight} ${row.weight_unit || 'g'}` : '—'
    }
    return h('div', { style: 'display:flex;gap:4px;align-items:center' }, [
      h(NInputNumber, {
        value: row.weight,
        size: 'small',
        style: 'width:80px',
        min: 0,
        onUpdateValue: (v) => { row.weight = v },
        onBlur: () => saveItemWeight(row),
      }),
      h(NSelect, {
        value: row.weight_unit || 'g',
        size: 'small',
        style: 'width:55px',
        options: [{ label: 'g', value: 'g' }, { label: 'kg', value: 'kg' }],
        onUpdateValue: (v) => { row.weight_unit = v; saveItemWeight(row) },
      }),
    ])
  },
}
```

Add `saveItemWeight` function that calls the update item API.

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/plating/PlatingDetail.vue
git commit -m "feat: add weight column to plating order items table"
```

---

## Task 5: Frontend — Handcraft Detail Weight Column

**Files:**
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue`

- [ ] **Step 1: Add weight column to part items and jewelry/output items tables**

Same pattern as Task 4, add weight column after qty column in both tables (配件明细 and 产出明细).

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/handcraft/HandcraftDetail.vue
git commit -m "feat: add weight column to handcraft order items tables"
```

---

## Task 6: Frontend — Receipt Pages Weight Column

**Files:**
- Modify: Plating receipt detail/create pages
- Modify: Handcraft receipt detail/create pages

- [ ] **Step 1: Add weight column to receipt item tables**

In plating receipt and handcraft receipt detail/create pages, add weight column after qty column. Weight should be editable when creating/editing receipt items.

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/plating/ frontend/src/views/handcraft/
git commit -m "feat: add weight column to receipt pages"
```

---

## Task 7: Verify

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 2: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Manual verification**

- Create plating order with weight → verify stored and displayed
- Create handcraft order with weight → verify stored
- Create receipts with weight → verify stored
- Export plating/handcraft PDF → verify weight column appears
- Verify weight unit dropdown (g/kg) works
