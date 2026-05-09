# Handcraft Picking — 子行「实际」列可编辑 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the picking simulation sub-row 「理论」 column to 「实际」, make the cell click-editable so users can record actual picked quantity per (part_item × atom), persisted in `handcraft_picking_weight.actual_qty` (new nullable column).

**Architecture:** Extend the existing `handcraft_picking_weight` table with `actual_qty Numeric(10,4) NULL`. `weight` and `weight_unit` become nullable too — a row may now hold weight only, actual_qty only, or both. The picking simulation response surfaces `actual_qty` per row. Two new endpoints (`PUT/DELETE /picking/actual_qty`) parallel the weight endpoints with the same status gating + order scoping. Frontend reuses the focus/blur snapshot pattern from the weight column. The 建议 column and `total_suggested_qty` stay BOM-derived (do NOT recompute from `actual_qty`); only the group header 合计 sums actuals.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Pydantic V2, PostgreSQL, Vue 3.5 + Naive UI, ReportLab.

**Spec:** `docs/superpowers/specs/2026-05-09-handcraft-picking-actual-qty-design.md`

**Branch:** Already on `feat/picking-actual-qty` off `main`. Spec commit `9192c38` is on this branch.

---

## File Map

**Backend (modify):**
- `models/handcraft_order.py` — add `actual_qty` column to `HandcraftPickingWeight`; relax `weight` and `weight_unit` to nullable
- `database.py` — extend `ensure_schema_compat` to ALTER COLUMN for the new column + nullability changes
- `schemas/handcraft.py` — add `actual_qty: Optional[float]` to `PickingSourceRow`; add request schemas for actual_qty endpoints
- `services/handcraft_picking_weight.py` — add `upsert_actual_qty`, `clear_actual_qty`; relax existing `upsert_weight`/`delete_weight` to coexist with actual_qty rows (don't blow away rows that still hold an actual_qty when weight is cleared)
- `services/handcraft_picking.py` — surface `actual_qty` in `PickingSourceRow`; recompute `total_needed_qty` from `(actual_qty ?? needed_qty)`
- `api/handcraft.py` — add `PUT/DELETE /picking/actual_qty` endpoints
- `services/handcraft_picking_list_pdf.py` — header column rename; row value uses `(actual_qty ?? needed_qty)`; group header sum follows

**Backend (modify tests):**
- `tests/test_api_handcraft_picking_weight.py` — append actual_qty tests (service + endpoints + cross-order rejection + nullable-weight coexistence)
- `tests/test_api_handcraft_picking.py` — adapt assertions on `total_needed_qty`; add tests verifying `actual_qty` surfaces in response and group sum reflects it

**Frontend (modify):**
- `frontend/src/api/handcraft.js` — add `upsertHandcraftPickingActualQty`, `deleteHandcraftPickingActualQty`
- `frontend/src/components/picking/HandcraftPickingSimulationModal.vue` — column header rename; new editable cell with focus/blur snapshot; group header 合计 uses local helper

---

## Task 1: Add `actual_qty` column + nullability migration

**Files:**
- Modify: `models/handcraft_order.py`
- Modify: `database.py`

- [ ] **Step 1.1: Read the current model**

```bash
grep -n "class HandcraftPickingWeight" -A 25 models/handcraft_order.py
```

Expected: shows `weight = Column(Numeric(10, 4), nullable=False)`, `weight_unit = Column(String, nullable=False, default="kg")`, and 4 other columns + UniqueConstraint.

- [ ] **Step 1.2: Update the model**

In `models/handcraft_order.py`, replace the `HandcraftPickingWeight` class column block. Change `weight` and `weight_unit` to `nullable=True`, and append `actual_qty`:

```python
class HandcraftPickingWeight(Base):
    """Per (part_item × atom_part_id) measurements at picking time:
    actual weight and/or actual picked qty. Either may be null; uniqueness
    is on (part_item_id, atom_part_id)."""
    __tablename__ = "handcraft_picking_weight"

    id = Column(Integer, primary_key=True, autoincrement=True)
    handcraft_order_id = Column(
        String,
        ForeignKey("handcraft_order.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    part_item_id = Column(
        Integer,
        ForeignKey("handcraft_part_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    atom_part_id = Column(String, ForeignKey("part.id"), nullable=False)
    weight = Column(Numeric(10, 4), nullable=True)
    weight_unit = Column(String, nullable=True, default="kg")
    actual_qty = Column(Numeric(10, 4), nullable=True)
    recorded_at = Column(DateTime, nullable=False, default=now_beijing)

    __table_args__ = (
        UniqueConstraint("part_item_id", "atom_part_id", name="uq_picking_weight_pa"),
    )
```

- [ ] **Step 1.3: Add ALTER blocks in `ensure_schema_compat`**

In `database.py`, find the existing `if not inspector.has_table("handcraft_picking_weight"):` block and add additive migration AFTER the create-if-missing block:

```python
if inspector.has_table("handcraft_picking_weight"):
    cols = {c["name"]: c for c in inspector.get_columns("handcraft_picking_weight")}
    if "actual_qty" not in cols:
        conn.execute(text(
            "ALTER TABLE handcraft_picking_weight ADD COLUMN actual_qty NUMERIC(10,4) NULL"
        ))
        logger.warning("Added missing handcraft_picking_weight.actual_qty column")
    if cols.get("weight", {}).get("nullable") is False:
        conn.execute(text(
            "ALTER TABLE handcraft_picking_weight ALTER COLUMN weight DROP NOT NULL"
        ))
        logger.warning("Relaxed handcraft_picking_weight.weight to NULLABLE")
    if cols.get("weight_unit", {}).get("nullable") is False:
        conn.execute(text(
            "ALTER TABLE handcraft_picking_weight ALTER COLUMN weight_unit DROP NOT NULL"
        ))
        logger.warning("Relaxed handcraft_picking_weight.weight_unit to NULLABLE")
```

(`text` is already imported in `database.py`. Inspect the file to confirm.)

- [ ] **Step 1.4: Verify migration runs cleanly**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/python -c "from database import engine, ensure_schema_compat, Base; from models import *; Base.metadata.create_all(bind=engine); ensure_schema_compat()"
```

Expected: no errors. Then verify columns:

```bash
psql -h localhost -U allen -d allen_shop -c "\d handcraft_picking_weight"
```

Expected: `actual_qty` column present; `weight` and `weight_unit` nullable.

- [ ] **Step 1.5: Run unrelated tests to ensure no regression**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft_picking.py tests/test_api_handcraft_picking_weight.py --tb=short 2>&1 | tail -10
```

Expected: tests still pass with the schema change (existing rows unaffected; new column is nullable).

- [ ] **Step 1.6: Commit**

```bash
git add models/handcraft_order.py database.py
git commit -m "feat(handcraft): add actual_qty column to handcraft_picking_weight"
```

---

## Task 2: Relax existing weight service to coexist with actual_qty

**Files:**
- Modify: `services/handcraft_picking_weight.py`
- Modify: `tests/test_api_handcraft_picking_weight.py`

Currently `delete_weight()` deletes the entire row. After this task, a row may hold an `actual_qty` even when weight is cleared — we must NOT delete the row in that case. Same logic in mirror direction for the upcoming `clear_actual_qty`.

- [ ] **Step 2.1: Write failing test**

Append to `tests/test_api_handcraft_picking_weight.py`:

```python
def test_delete_weight_keeps_row_when_actual_qty_present(db):
    """Clearing weight on a row that also holds actual_qty should NOT delete
    the row. Only the weight fields are cleared."""
    from sqlalchemy import update
    order_id, pi = _seed_atomic(db, order_id="HC-WTKEEP")
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")
    # Simulate actual_qty being set (we'll formally test upsert_actual_qty later).
    db.execute(update(HandcraftPickingWeight)
               .where(HandcraftPickingWeight.part_item_id == pi.id,
                      HandcraftPickingWeight.atom_part_id == "PJ-X-WT01")
               .values(actual_qty=Decimal("123.4567")))
    db.flush()

    deleted = delete_weight(db, order_id, pi.id, "PJ-X-WT01")
    assert deleted is True

    row = (db.query(HandcraftPickingWeight)
           .filter_by(part_item_id=pi.id, atom_part_id="PJ-X-WT01")
           .one_or_none())
    assert row is not None, "row should remain because actual_qty is set"
    assert row.weight is None
    assert row.weight_unit is None
    assert row.actual_qty == Decimal("123.4567")


def test_delete_weight_removes_row_when_actual_qty_null(db):
    """Existing behavior: when only weight is set (no actual_qty), clearing
    weight deletes the entire row."""
    order_id, pi = _seed_atomic(db, order_id="HC-WTDROP")
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")

    deleted = delete_weight(db, order_id, pi.id, "PJ-X-WT01")
    assert deleted is True
    assert db.query(HandcraftPickingWeight).filter_by(
        part_item_id=pi.id, atom_part_id="PJ-X-WT01"
    ).count() == 0
```

- [ ] **Step 2.2: Run, expect failure**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft_picking_weight.py::test_delete_weight_keeps_row_when_actual_qty_present -x --tb=short
```

Expected: FAIL — current `delete_weight` always deletes the row.

- [ ] **Step 2.3: Update `delete_weight` to preserve rows with actual_qty**

Edit `services/handcraft_picking_weight.py`. Replace the body of `delete_weight`:

```python
def delete_weight(db: Session, order_id: str, part_item_id: int, atom_part_id: str) -> bool:
    """Clear the weight fields on a (part_item, atom_part) row.
    If actual_qty is also null after clearing, the whole row is removed.
    Otherwise the row stays so actual_qty is preserved.
    Returns True if the row existed (whether removed or just cleared)."""
    _validate_part_item_in_order(db, order_id, part_item_id)
    row = (
        db.query(HandcraftPickingWeight)
        .filter_by(part_item_id=part_item_id, atom_part_id=atom_part_id)
        .one_or_none()
    )
    if row is None:
        return False
    if row.actual_qty is None:
        db.delete(row)
    else:
        row.weight = None
        row.weight_unit = None
    db.flush()
    return True
```

(The `_validate_part_item_in_order` call is already part of this function from earlier work — confirm.)

- [ ] **Step 2.4: Update `upsert_weight` so it doesn't reset existing actual_qty**

Read the current `upsert_weight`. The existing code sets `row.weight = ...` and `row.weight_unit = ...` on update — it does NOT touch `actual_qty`, so the upsert side is already safe. Just verify; no edit needed unless the existing code resets unrelated fields.

- [ ] **Step 2.5: Run tests**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft_picking_weight.py --tb=short 2>&1 | tail -10
```

Expected: all weight tests still pass + 2 new ones.

- [ ] **Step 2.6: Commit**

```bash
git add services/handcraft_picking_weight.py tests/test_api_handcraft_picking_weight.py
git commit -m "refactor(handcraft): delete_weight preserves row when actual_qty is set"
```

---

## Task 3: Add `upsert_actual_qty` / `clear_actual_qty` services

**Files:**
- Modify: `services/handcraft_picking_weight.py`
- Modify: `tests/test_api_handcraft_picking_weight.py`

- [ ] **Step 3.1: Write failing tests**

Append to `tests/test_api_handcraft_picking_weight.py`:

```python
def test_upsert_actual_qty_inserts_new_row(db):
    from services.handcraft_picking_weight import upsert_actual_qty
    order_id, pi = _seed_atomic(db, order_id="HC-AQ01")
    row = upsert_actual_qty(db, order_id, pi.id, "PJ-X-WT01", 250.5)
    assert row.actual_qty == Decimal("250.5000")
    assert row.weight is None
    assert row.weight_unit is None


def test_upsert_actual_qty_updates_existing_weight_row(db):
    """A row that has weight gets actual_qty appended without losing weight."""
    from services.handcraft_picking_weight import upsert_actual_qty
    order_id, pi = _seed_atomic(db, order_id="HC-AQ02")
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")
    upsert_actual_qty(db, order_id, pi.id, "PJ-X-WT01", 250)

    row = db.query(HandcraftPickingWeight).filter_by(part_item_id=pi.id).one()
    assert row.weight == Decimal("0.5000")
    assert row.weight_unit == "kg"
    assert row.actual_qty == Decimal("250.0000")


def test_upsert_actual_qty_rejects_part_item_outside_order(db):
    from services.handcraft_picking_weight import upsert_actual_qty
    import pytest
    _, pi = _seed_atomic(db, order_id="HC-AQ03")
    db.add(HandcraftOrder(id="HC-OTHER-AQ", supplier_name="S", status="pending"))
    db.flush()
    with pytest.raises(ValueError, match="不属于"):
        upsert_actual_qty(db, "HC-OTHER-AQ", pi.id, "PJ-X-WT01", 100)


def test_clear_actual_qty_removes_row_when_weight_null(db):
    from services.handcraft_picking_weight import upsert_actual_qty, clear_actual_qty
    order_id, pi = _seed_atomic(db, order_id="HC-AQ04")
    upsert_actual_qty(db, order_id, pi.id, "PJ-X-WT01", 250)
    deleted = clear_actual_qty(db, order_id, pi.id, "PJ-X-WT01")
    assert deleted is True
    assert db.query(HandcraftPickingWeight).filter_by(part_item_id=pi.id).count() == 0


def test_clear_actual_qty_keeps_row_when_weight_present(db):
    from services.handcraft_picking_weight import upsert_actual_qty, clear_actual_qty
    order_id, pi = _seed_atomic(db, order_id="HC-AQ05")
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")
    upsert_actual_qty(db, order_id, pi.id, "PJ-X-WT01", 250)

    deleted = clear_actual_qty(db, order_id, pi.id, "PJ-X-WT01")
    assert deleted is True
    row = db.query(HandcraftPickingWeight).filter_by(part_item_id=pi.id).one()
    assert row.actual_qty is None
    assert row.weight == Decimal("0.5000")


def test_clear_actual_qty_returns_false_when_no_row(db):
    from services.handcraft_picking_weight import clear_actual_qty
    order_id, pi = _seed_atomic(db, order_id="HC-AQ06")
    assert clear_actual_qty(db, order_id, pi.id, "PJ-X-WT01") is False
```

- [ ] **Step 3.2: Run, expect ImportError**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft_picking_weight.py -k "actual_qty" --tb=short
```

Expected: ImportError on `upsert_actual_qty`/`clear_actual_qty`.

- [ ] **Step 3.3: Implement the new functions**

Append to `services/handcraft_picking_weight.py`:

```python
def upsert_actual_qty(
    db: Session,
    order_id: str,
    part_item_id: int,
    atom_part_id: str,
    qty: float,
) -> HandcraftPickingWeight:
    """Set the actual picked quantity for a (part_item × atom) slice. Creates
    a row if none exists; updates only `actual_qty` on existing rows
    (preserves weight)."""
    _validate_part_item_in_order(db, order_id, part_item_id)
    _validate_atom_part_id(db, atom_part_id)
    qty_dec = Decimal(str(qty)).quantize(Decimal("0.0001"))
    row = (
        db.query(HandcraftPickingWeight)
        .filter_by(part_item_id=part_item_id, atom_part_id=atom_part_id)
        .one_or_none()
    )
    if row is None:
        row = HandcraftPickingWeight(
            handcraft_order_id=order_id,
            part_item_id=part_item_id,
            atom_part_id=atom_part_id,
            weight=None,
            weight_unit=None,
            actual_qty=qty_dec,
        )
        db.add(row)
    else:
        row.actual_qty = qty_dec
    db.flush()
    return row


def clear_actual_qty(
    db: Session,
    order_id: str,
    part_item_id: int,
    atom_part_id: str,
) -> bool:
    """Clear `actual_qty` on a (part_item × atom) row. If the row has no
    weight either, the row is deleted. Returns True if a row was found."""
    _validate_part_item_in_order(db, order_id, part_item_id)
    row = (
        db.query(HandcraftPickingWeight)
        .filter_by(part_item_id=part_item_id, atom_part_id=atom_part_id)
        .one_or_none()
    )
    if row is None:
        return False
    if row.weight is None:
        db.delete(row)
    else:
        row.actual_qty = None
    db.flush()
    return True
```

- [ ] **Step 3.4: Run tests**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft_picking_weight.py --tb=short 2>&1 | tail -10
```

Expected: all green (existing + 6 new).

- [ ] **Step 3.5: Commit**

```bash
git add services/handcraft_picking_weight.py tests/test_api_handcraft_picking_weight.py
git commit -m "feat(handcraft): upsert_actual_qty / clear_actual_qty services"
```

---

## Task 4: Surface `actual_qty` on `PickingSourceRow` + group sum

**Files:**
- Modify: `schemas/handcraft.py`
- Modify: `services/handcraft_picking.py`
- Modify: `tests/test_api_handcraft_picking.py`

- [ ] **Step 4.1: Write failing test for actual_qty surfacing**

Append to `tests/test_api_handcraft_picking.py`:

```python
def test_picking_includes_actual_qty_when_recorded(client, db):
    """Recorded actual_qty surfaces in the picking response and the group
    total_needed_qty reflects (actual_qty ?? needed_qty) per row."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem
    from services.handcraft_picking_weight import upsert_actual_qty

    db.add(PartModel(id="PJ-X-AQ", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-AQ-T1", supplier_name="S", status="pending"))
    db.flush()
    pi1 = HandcraftPartItem(handcraft_order_id="HC-AQ-T1", part_id="PJ-X-AQ", qty=200, bom_qty=200)
    pi2 = HandcraftPartItem(handcraft_order_id="HC-AQ-T1", part_id="PJ-X-AQ", qty=100, bom_qty=100)
    db.add(pi1); db.add(pi2); db.flush()
    upsert_actual_qty(db, "HC-AQ-T1", pi1.id, "PJ-X-AQ", 210)
    # pi2 left without actual_qty, so it falls back to needed_qty = 100

    body = client.get("/api/handcraft/HC-AQ-T1/picking").json()
    g = body["groups"][0]
    rows = sorted(g["rows"], key=lambda r: r["part_item_id"])
    assert rows[0]["actual_qty"] == 210
    assert rows[1]["actual_qty"] is None
    assert g["total_needed_qty"] == 310  # 210 + 100 (actual ?? needed)
    # 建议 unchanged: still computed from needed_qty (200 → 250) + (100 → 150) = 400
    assert g["total_suggested_qty"] == 400
```

- [ ] **Step 4.2: Run, expect failure**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft_picking.py::test_picking_includes_actual_qty_when_recorded -x --tb=short
```

Expected: FAIL — response has no `actual_qty` field.

- [ ] **Step 4.3: Add field to schema**

In `schemas/handcraft.py`, find the `PickingSourceRow` class and add `actual_qty`:

```python
class PickingSourceRow(BaseModel):
    """One (part_item × atom_part_id) slice in the merged picking view."""
    part_item_id: int
    atom_part_id: str
    qty: float
    bom_qty: Optional[float] = None
    is_composite_expansion: bool = False
    parent_composite_name: Optional[str] = None
    needed_qty: float
    suggested_qty: Optional[int] = None
    weight: Optional[float] = None
    weight_unit: Optional[str] = None
    actual_qty: Optional[float] = None
    picked: bool
```

- [ ] **Step 4.4: Surface actual_qty in the picking simulation builder**

In `services/handcraft_picking.py`, find the loop where `PickingSourceRow(...)` is constructed (look for `weight=(float(weight_row.weight) if weight_row else None)`). Add `actual_qty`:

```python
            row = PickingSourceRow(
                part_item_id=pi.id,
                atom_part_id=atom_id,
                qty=qty_for_row,
                bom_qty=bom_qty_for_row,
                is_composite_expansion=is_composite,
                parent_composite_name=(parent_part.name if (is_composite and parent_part) else None),
                needed_qty=needed_qty,
                suggested_qty=suggested,
                weight=(float(weight_row.weight) if weight_row and weight_row.weight is not None else None),
                weight_unit=(weight_row.weight_unit if weight_row and weight_row.weight is not None else None),
                actual_qty=(float(weight_row.actual_qty) if weight_row and weight_row.actual_qty is not None else None),
                picked=is_picked,
            )
```

(Note the `weight_row.weight is not None` guards on the existing weight/weight_unit fields — necessary now that those columns are nullable.)

- [ ] **Step 4.5: Update `total_needed_qty` to use (actual ?? needed)**

In the same file, find the loop that builds `groups`. Replace the `total_needed_qty=sum(...)` line:

```python
        groups.append(PickingGroup(
            atom_part_id=atom_id,
            atom_part_name=atom_part.name,
            atom_part_image=atom_part.image,
            size_tier=atom_part.size_tier or "small",
            current_stock=stock_by_part.get(atom_id, 0.0),
            total_needed_qty=sum(
                (r.actual_qty if r.actual_qty is not None else r.needed_qty)
                for r in rows
            ),
            total_suggested_qty=sum((r.suggested_qty or 0) for r in rows),
            rows=rows,
        ))
```

- [ ] **Step 4.6: Run the new test + the merge tests**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft_picking.py --tb=short 2>&1 | tail -10
```

Expected: all picking tests pass. The existing `test_merge_same_atom_across_part_items_into_one_group` and `test_total_suggested_is_sum_of_per_row_suggested` still hold (no actual_qty set → falls back to needed_qty).

- [ ] **Step 4.7: Commit**

```bash
git add schemas/handcraft.py services/handcraft_picking.py tests/test_api_handcraft_picking.py
git commit -m "feat(handcraft): surface actual_qty on picking response, group sum honors override"
```

---

## Task 5: PUT/DELETE `/picking/actual_qty` endpoints

**Files:**
- Modify: `schemas/handcraft.py`
- Modify: `api/handcraft.py`
- Modify: `tests/test_api_handcraft_picking_weight.py`

- [ ] **Step 5.1: Add request schemas**

In `schemas/handcraft.py`, near the existing `HandcraftPickingWeight*Request` classes, append:

```python
class HandcraftPickingActualQtyUpsertRequest(BaseModel):
    part_item_id: int = Field(gt=0)
    atom_part_id: str = Field(min_length=1)
    qty: float = Field(gt=0)


class HandcraftPickingActualQtyDeleteRequest(BaseModel):
    part_item_id: int = Field(gt=0)
    atom_part_id: str = Field(min_length=1)
```

- [ ] **Step 5.2: Write failing endpoint tests**

Append to `tests/test_api_handcraft_picking_weight.py`:

```python
def test_api_put_actual_qty_upsert(client, db):
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem

    db.add(PartModel(id="PJ-X-EAQ1", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-EAQ1", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-EAQ1", part_id="PJ-X-EAQ1", qty=200, bom_qty=200)
    db.add(pi); db.flush()
    pi_id = pi.id

    r = client.put(f"/api/handcraft/HC-EAQ1/picking/actual_qty", json={
        "part_item_id": pi_id, "atom_part_id": "PJ-X-EAQ1", "qty": 250,
    })
    assert r.status_code == 200, r.text
    assert r.json()["actual_qty"] == 250


def test_api_put_actual_qty_blocked_when_status_not_pending(client, db):
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem

    db.add(PartModel(id="PJ-X-EAQ2", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-EAQ2", supplier_name="S", status="processing"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-EAQ2", part_id="PJ-X-EAQ2", qty=200, bom_qty=200)
    db.add(pi); db.flush()
    r = client.put(f"/api/handcraft/HC-EAQ2/picking/actual_qty", json={
        "part_item_id": pi.id, "atom_part_id": "PJ-X-EAQ2", "qty": 250,
    })
    assert r.status_code == 400


def test_api_delete_actual_qty(client, db):
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem
    from services.handcraft_picking_weight import upsert_actual_qty

    db.add(PartModel(id="PJ-X-EAQ3", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-EAQ3", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-EAQ3", part_id="PJ-X-EAQ3", qty=200, bom_qty=200)
    db.add(pi); db.flush()
    upsert_actual_qty(db, "HC-EAQ3", pi.id, "PJ-X-EAQ3", 250)

    r = client.request("DELETE", f"/api/handcraft/HC-EAQ3/picking/actual_qty",
                       json={"part_item_id": pi.id, "atom_part_id": "PJ-X-EAQ3"})
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_api_delete_actual_qty_rejects_cross_order(client, db):
    """Issue #8 mirror: cross-order DELETE must be rejected (4xx), not silently
    delete another order's row."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftPickingWeight
    from services.handcraft_picking_weight import upsert_actual_qty

    db.add(PartModel(id="PJ-X-EAQX", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-A-AQ", supplier_name="S", status="pending"))
    db.add(HandcraftOrder(id="HC-B-AQ", supplier_name="S", status="pending"))
    db.flush()
    pi_b = HandcraftPartItem(handcraft_order_id="HC-B-AQ", part_id="PJ-X-EAQX", qty=200, bom_qty=200)
    db.add(pi_b); db.flush()
    upsert_actual_qty(db, "HC-B-AQ", pi_b.id, "PJ-X-EAQX", 250)

    r = client.request("DELETE", f"/api/handcraft/HC-A-AQ/picking/actual_qty",
                       json={"part_item_id": pi_b.id, "atom_part_id": "PJ-X-EAQX"})
    assert r.status_code == 400
    # Order B's actual_qty must still be present.
    row = db.query(HandcraftPickingWeight).filter_by(part_item_id=pi_b.id).one()
    assert row.actual_qty == Decimal("250.0000")
```

- [ ] **Step 5.3: Run, expect 404 / route-not-found**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft_picking_weight.py -k "actual_qty" -x --tb=short
```

- [ ] **Step 5.4: Add endpoints in `api/handcraft.py`**

Find the existing `picking/weight` endpoints. Mirror the same structure for `actual_qty`. First update imports (near existing schema imports):

```python
from schemas.handcraft import (
    # ... existing imports ...
    HandcraftPickingActualQtyUpsertRequest,
    HandcraftPickingActualQtyDeleteRequest,
)
from services.handcraft_picking_weight import (
    upsert_weight as upsert_picking_weight,
    delete_weight as delete_picking_weight,
    upsert_actual_qty as upsert_picking_actual_qty,
    clear_actual_qty as clear_picking_actual_qty,
)
```

Append after the existing `picking/weight` endpoints:

```python
@router.put("/{order_id}/picking/actual_qty")
def api_handcraft_picking_actual_qty_upsert(
    order_id: str,
    body: HandcraftPickingActualQtyUpsertRequest,
    db: Session = Depends(get_db),
):
    """Upsert per-atom actual picked qty. Pending status only."""
    order = db.query(HandcraftOrder).filter_by(id=order_id).one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail=f"手工单 {order_id} 不存在")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail=f"手工单状态为 {order.status}，无法编辑实际数量")
    with service_errors():
        row = upsert_picking_actual_qty(
            db, order_id, body.part_item_id, body.atom_part_id, body.qty,
        )
    return {
        "part_item_id": row.part_item_id,
        "atom_part_id": row.atom_part_id,
        "actual_qty": float(row.actual_qty) if row.actual_qty is not None else None,
    }


@router.delete("/{order_id}/picking/actual_qty")
def api_handcraft_picking_actual_qty_delete(
    order_id: str,
    body: HandcraftPickingActualQtyDeleteRequest,
    db: Session = Depends(get_db),
):
    """Clear per-atom actual picked qty. Pending status only."""
    order = db.query(HandcraftOrder).filter_by(id=order_id).one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail=f"手工单 {order_id} 不存在")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail=f"手工单状态为 {order.status}，无法删除实际数量")
    with service_errors():
        deleted = clear_picking_actual_qty(db, order_id, body.part_item_id, body.atom_part_id)
    return {"deleted": deleted}
```

- [ ] **Step 5.5: Run all picking-weight tests**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft_picking_weight.py --tb=short 2>&1 | tail -10
```

Expected: all green (existing + 4 new).

- [ ] **Step 5.6: Commit**

```bash
git add schemas/handcraft.py api/handcraft.py tests/test_api_handcraft_picking_weight.py
git commit -m "feat(handcraft): PUT/DELETE /picking/actual_qty endpoints"
```

---

## Task 6: PDF — column rename + group sum reflects actual

**Files:**
- Modify: `services/handcraft_picking_list_pdf.py`

- [ ] **Step 6.1: Read current PDF builder**

```bash
grep -n "_HEADERS\|total_needed_qty\|needed_qty\|理论\|实际" services/handcraft_picking_list_pdf.py
```

Locate the `_HEADERS` list and the row-render block for 需要 column.

- [ ] **Step 6.2: Rename column header**

In `services/handcraft_picking_list_pdf.py`, change `_HEADERS`:

```python
_HEADERS = ["配件编号", "配件", "重量", "实际", "建议", "库存", "完成"]
```

(Was: `... "重量", "需要", ...`.)

- [ ] **Step 6.3: Use (actual_qty ?? needed_qty) in the row 实际 cell**

Find the col-3 (was 需要) draw block. Replace `_fmt_qty(r.needed_qty)` with the override:

```python
            actual_or_needed = r.actual_qty if r.actual_qty is not None else r.needed_qty
            qty_label = _fmt_qty(actual_or_needed)
            c.drawString(x + (_COL_W[3] - stringWidth(qty_label, _FONT, 9)) / 2,
                         y - _ROW_H / 2 - 3, qty_label)
```

- [ ] **Step 6.4: Group header `合计` reflects new sum**

If the PDF group header currently displays `合计需要 {total_needed_qty}`, no changes needed: Task 4 already updated `total_needed_qty` to honor `actual_qty`. The PDF reads it directly. Just verify the label text still makes sense (`合计需要` → `合计`).

In the group-header draw block, change `f"合计需要 {_fmt_qty(g.total_needed_qty)}"` to `f"合计 {_fmt_qty(g.total_needed_qty)}"` for clarity.

- [ ] **Step 6.5: Run smoke test**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft_picking.py::test_pdf_endpoint_smoke -x --tb=short
```

Expected: PASS.

- [ ] **Step 6.6: Commit**

```bash
git add services/handcraft_picking_list_pdf.py
git commit -m "feat(handcraft): PDF picking list — rename 需要 to 实际, header 合计"
```

---

## Task 7: Frontend API client

**Files:**
- Modify: `frontend/src/api/handcraft.js`

- [ ] **Step 7.1: Append client functions**

After the existing `upsertHandcraftPickingWeight` / `deleteHandcraftPickingWeight` exports, append:

```js
export const upsertHandcraftPickingActualQty = (id, partItemId, atomPartId, qty) =>
  api.put(`/handcraft/${id}/picking/actual_qty`, {
    part_item_id: partItemId,
    atom_part_id: atomPartId,
    qty,
  })

export const deleteHandcraftPickingActualQty = (id, partItemId, atomPartId) =>
  api.delete(`/handcraft/${id}/picking/actual_qty`, {
    data: { part_item_id: partItemId, atom_part_id: atomPartId },
  })
```

- [ ] **Step 7.2: Commit**

```bash
git add frontend/src/api/handcraft.js
git commit -m "feat(handcraft): frontend API — picking actual_qty upsert/delete"
```

---

## Task 8: Picking modal — column rename + editable cell

**Files:**
- Modify: `frontend/src/components/picking/HandcraftPickingSimulationModal.vue`

- [ ] **Step 8.1: Read the current modal**

```bash
grep -n "理论\|needed_qty\|onWeightBlur\|onWeightFocus" frontend/src/components/picking/HandcraftPickingSimulationModal.vue
```

Identify: the column header text, the sub-row 理论 cell, and the existing focus/blur snapshot pattern (if present).

- [ ] **Step 8.2: Rename column header**

Find the `<th>理论</th>` cell in the table header (or the literal string in the template) and change to `<th>实际</th>`. If both modal table header and group-header summary mention 「合计 N」, leave the group label as 「合计」 (the value already reflects actuals after Task 4).

- [ ] **Step 8.3: Add the editable input**

In the sub-row block, replace the static 理论 cell with an `<n-input-number>`:

```vue
<td class="num">
  <n-input-number
    :value="r.actual_qty ?? r.needed_qty"
    :precision="4"
    :show-button="false"
    :min="0"
    :disabled="readonly"
    style="width: 80px"
    @focus="onActualQtyFocus(r)"
    @blur="onActualQtyBlur(g, r, $event)"
    @update:value="(v) => { r._localActualQty = v }"
  />
</td>
```

(`r._localActualQty` is a transient draft so we don't mutate `r.actual_qty` until persistence succeeds.)

Add the imports / helpers in `<script setup>` (after the existing weight handlers):

```js
import {
  upsertHandcraftPickingActualQty,
  deleteHandcraftPickingActualQty,
} from '@/api/handcraft'

function onActualQtyFocus(row) {
  row._actualAtFocus = row.actual_qty
}

async function onActualQtyBlur(group, row, evt) {
  if (readonly.value) return
  const fresh = row._localActualQty
  const prev = row._actualAtFocus
  const isClear =
    fresh == null ||
    fresh === '' ||
    Number(fresh) <= 0 ||
    Number(fresh) === Number(row.needed_qty)

  try {
    if (isClear) {
      if (prev != null) {
        await deleteHandcraftPickingActualQty(props.orderId, row.part_item_id, row.atom_part_id)
      }
      row.actual_qty = null
    } else {
      const resp = await upsertHandcraftPickingActualQty(
        props.orderId, row.part_item_id, row.atom_part_id, Number(fresh),
      )
      row.actual_qty = resp.data.actual_qty
    }
    // Recompute group total (rows are reactive, but total_needed_qty is server-sent
    // — we patch it locally to match)
    group.total_needed_qty = group.rows.reduce(
      (s, x) => s + (x.actual_qty != null ? Number(x.actual_qty) : Number(x.needed_qty)),
      0,
    )
  } catch (err) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    row._localActualQty = undefined
  }
}
```

(`message` and `props.orderId` are already in scope from the existing component; verify and reuse.)

- [ ] **Step 8.4: Verify build**

```bash
cd /Users/ycb/workspace/allen_shop/frontend && node_modules/.bin/vite build 2>&1 | tail -5; rm -rf dist
```

Expected: build succeeds, no syntax errors.

- [ ] **Step 8.5: Manual UI smoke**

Start dev server (`npm run dev`), open a pending handcraft order's 配货模拟:
- Column header reads 「实际」
- Default value matches the previous 「理论」
- Click a cell, change to a different value, blur → value persists, group 合计 updates
- Set value back to default → row reverts to default display
- Switch order to processing → cells become read-only

(Manual; not test-automated.)

- [ ] **Step 8.6: Commit**

```bash
git add frontend/src/components/picking/HandcraftPickingSimulationModal.vue
git commit -m "feat(handcraft): picking modal — 实际 column editable"
```

---

## Task 9: Final verification

- [ ] **Step 9.1: Targeted test pass**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft_picking.py tests/test_api_handcraft_picking_weight.py tests/test_api_handcraft.py tests/test_handcraft_item_crud.py --tb=line 2>&1 | tail -10
```

Expected: all green.

- [ ] **Step 9.2: Frontend build**

```bash
cd /Users/ycb/workspace/allen_shop/frontend && node_modules/.bin/vite build 2>&1 | tail -5; rm -rf dist
```

Expected: clean build.

- [ ] **Step 9.3: Manual UX smoke**

In the picking modal, set actual_qty on multiple rows of a group; verify group 合计 sums them correctly and 建议 stays unchanged. Confirm cascade: deleting a part_item also removes the actual_qty row (existing FK CASCADE — already covered by `test_delete_part_item_cascades_picking_weight`).

- [ ] **Step 9.4: No new commit needed if everything works**

If post-verification fixes are needed, commit them with a clear message; otherwise the feature is complete.

---

## Spec Coverage Self-Check

| Spec section | Tasks |
|---|---|
| §0 No inventory side-effects | All — only `actual_qty` writes; nothing in inventory_log |
| §2.1 Column rename + sum behavior | T8 (UI) + T4 (server) + T6 (PDF) |
| §2.2 Editable input + onBlur logic | T8 |
| §2.3 Status gating | T5 (endpoint) + T8 (frontend `readonly` reuse) |
| §2.4 Independent from picked checkbox | No code change needed; covered by spec narrative |
| §3 建议 unchanged | T4 (kept `total_suggested_qty` formula intact) |
| §4.1 New column on existing table | T1 |
| §4.2 schema migration | T1 |
| §5.1 Schema field on PickingSourceRow | T4 |
| §5.2 New endpoints | T5 |
| §5.3 Service functions | T3 + T2 (delete_weight coexistence) |
| §6 PDF | T6 |
| §7.1 Picking modal | T8 |
| §7.2 Frontend API client | T7 |
| §8 Edge cases (input == default → DELETE; weight + actual coexist; cascade) | T2, T3, T8 |

No gaps.
