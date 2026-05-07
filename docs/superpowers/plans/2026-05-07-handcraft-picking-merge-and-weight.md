# Handcraft Picking — 合并 + 按 atom 称重 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge same-atom picking rows across `HandcraftPartItem` records into a single group, and add per-atom weight inputs (synced with the existing 配件明细 panel) via a new `HandcraftPickingWeight` table.

**Architecture:** Pure presentation reshape in the picking simulation service (no inventory mutation). The existing per-row PickingRecord granularity stays — only the GET response groups by `atom_part_id` instead of `HandcraftPartItem.id`. Weight tracking gets a new dedicated table that supports per-atom granularity (so composite-expanded atoms can be weighed independently).

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Pydantic V2, PostgreSQL, Vue 3.5 + Naive UI, ReportLab (PDF).

**Spec:** `docs/superpowers/specs/2026-05-07-handcraft-picking-merge-and-weight-design.md`

**Branch strategy:** Continue work on `feat/handcraft-picking-simulation` (the branch already contains the prior picking-sim commits and was deleted locally — re-checkout from origin first; or create `feat/handcraft-picking-merge` off main).

---

## File Map

**Backend (modify):**
- `models/handcraft_order.py` — add `HandcraftPickingWeight` class
- `database.py` — extend `ensure_schema_compat` to create the new table + idempotent backfill
- `schemas/handcraft.py` — refactor `HandcraftPicking*` schemas; add weight request schemas
- `services/handcraft_picking.py` — rebuild aggregation by `atom_part_id`
- `services/handcraft.py:393-411` — `update_handcraft_part`: route `weight` to new table for atomic, reject for composite
- `api/handcraft.py` — add `PUT/DELETE /picking/weight` endpoints
- `services/handcraft_picking_list_pdf.py` — render new grouped layout

**Backend (create):**
- `services/handcraft_picking_weight.py` — CRUD + bulk loaders for weight
- `tests/test_api_handcraft_picking_weight.py` — endpoint + service tests for weight

**Backend (modify tests):**
- `tests/test_api_handcraft_picking.py` — adapt assertions to new response shape; add merge-behavior tests

**Frontend (modify):**
- `frontend/src/api/handcraft.js` — add `upsertPickingWeight`, `deletePickingWeight`
- `frontend/src/components/handcraft/HandcraftPickingSimulationModal.vue` — rewrite table rendering for new shape
- `frontend/src/views/handcraft/HandcraftDetail.vue` — update parts table weight column to read/write new source

---

## Task 1: Add `HandcraftPickingWeight` model + ensure_schema_compat block

**Files:**
- Modify: `models/handcraft_order.py`
- Modify: `database.py`

- [ ] **Step 1.1: Add the new model class to `models/handcraft_order.py`**

Append at end of file (after `HandcraftJewelryItem`):

```python
from sqlalchemy import Index, UniqueConstraint  # if not already imported


class HandcraftPickingWeight(Base):
    """Per (part_item × atom_part_id) actual weight measured at picking time.

    For atomic part_items: one row, atom_part_id == part_item.part_id.
    For composite part_items: one row per atom expanded from the composite.
    """
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
    weight = Column(Numeric(10, 4), nullable=False)
    weight_unit = Column(String, nullable=False, default="kg")
    recorded_at = Column(DateTime, nullable=False, default=now_beijing)

    __table_args__ = (
        UniqueConstraint("part_item_id", "atom_part_id", name="uq_picking_weight_pa"),
    )
```

- [ ] **Step 1.2: Make sure the new model is imported by `models/__init__.py`**

Read `models/__init__.py`. If `HandcraftPartItem` is exported, add `HandcraftPickingWeight` to the same import line / `__all__`. Pattern to follow: same as how `HandcraftPickingRecord` is exported.

- [ ] **Step 1.3: Add `ensure_schema_compat` block for the new table in `database.py`**

In `ensure_schema_compat()`, after the existing `handcraft_picking_record` handling, add:

```python
if not inspector.has_table("handcraft_picking_weight"):
    HandcraftPickingWeight.__table__.create(bind=conn)
    logger.warning("Created missing handcraft_picking_weight table")
```

Add `from models.handcraft_order import HandcraftPickingWeight` at top of `database.py` if not already imported (or use `Base.metadata.tables["handcraft_picking_weight"].create(bind=conn)`).

- [ ] **Step 1.4: Run app startup to verify table creation**

```bash
.venv/bin/python -c "from database import engine, ensure_schema_compat, Base; from models import *; Base.metadata.create_all(bind=engine); ensure_schema_compat()"
```

Expected: no errors. The table is created. Verify with:

```bash
psql allen_shop -U allen -c "\d handcraft_picking_weight"
```

Expected: shows the table with the columns and unique constraint.

- [ ] **Step 1.5: Commit**

```bash
git add models/handcraft_order.py models/__init__.py database.py
git commit -m "feat(handcraft): add HandcraftPickingWeight model + auto schema migration"
```

---

## Task 2: Add Pydantic schemas for new picking response + weight requests

**Files:**
- Modify: `schemas/handcraft.py`

- [ ] **Step 2.1: Refactor picking response schemas**

Find the existing `HandcraftPickingVariant`, `HandcraftPickingGroup`, `HandcraftPickingResponse` block. Replace with:

```python
class PickingSourceRow(BaseModel):
    """One (part_item × atom_part_id) slice in the merged picking view."""
    part_item_id: int
    atom_part_id: str
    qty: float                          # atomic: pi.qty; composite: pi.qty × atom_ratio
    bom_qty: Optional[float] = None     # atomic: pi.bom_qty; composite: pi.bom_qty × atom_ratio
    is_composite_expansion: bool = False
    parent_composite_name: Optional[str] = None  # set when is_composite_expansion is True
    needed_qty: float                   # bom_qty (or qty fallback) used to compute suggested
    suggested_qty: Optional[int] = None
    weight: Optional[float] = None
    weight_unit: Optional[str] = None
    picked: bool


class PickingGroup(BaseModel):
    """All sub-rows for a single atomic part_id, across all part_items in the order."""
    atom_part_id: str
    atom_part_name: str
    atom_part_image: Optional[str] = None
    size_tier: SizeTier
    current_stock: float
    total_needed_qty: float
    total_suggested_qty: int
    rows: List[PickingSourceRow]


class HandcraftPickingProgress(BaseModel):
    total: int
    picked: int


class HandcraftPickingResponse(BaseModel):
    handcraft_order_id: str
    supplier_name: str
    status: str
    groups: List[PickingGroup]
    progress: HandcraftPickingProgress


class HandcraftPickingMarkRequest(BaseModel):
    part_item_id: int = Field(gt=0)
    part_id: str = Field(min_length=1)


class HandcraftPickingWeightUpsertRequest(BaseModel):
    part_item_id: int = Field(gt=0)
    atom_part_id: str = Field(min_length=1)
    weight: float = Field(gt=0)
    weight_unit: str = Field(default="kg", pattern="^(kg|g)$")


class HandcraftPickingWeightDeleteRequest(BaseModel):
    part_item_id: int = Field(gt=0)
    atom_part_id: str = Field(min_length=1)
```

Make sure `from typing import List, Optional` is at the top, and `SizeTier` is imported from wherever it currently lives.

- [ ] **Step 2.2: Verify nothing else still imports the removed classes**

```bash
grep -rn "HandcraftPickingVariant\|HandcraftPickingGroup" --include="*.py" .
```

The matches will be in `services/handcraft_picking.py` (will be rewritten in Task 5) and possibly tests. Note them — they'll be updated as the refactor proceeds. **Do not** silently keep the old classes around.

- [ ] **Step 2.3: Commit**

```bash
git add schemas/handcraft.py
git commit -m "feat(handcraft): refactor picking schemas — atom-grouped + weight requests"
```

(Test files and service files will fail to import at this point. Tasks 3–5 fix them.)

---

## Task 3: Implement `services/handcraft_picking_weight.py`

**Files:**
- Create: `services/handcraft_picking_weight.py`
- Create: `tests/test_api_handcraft_picking_weight.py`

- [ ] **Step 3.1: Write failing test for `upsert_weight` happy path + idempotency**

Create `tests/test_api_handcraft_picking_weight.py`:

```python
"""Tests for handcraft picking weight service + endpoints.

Domain: per-atom weight tracking for handcraft picking.
"""

from decimal import Decimal

from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftPickingWeight
from models.part import Part as PartModel
from services.handcraft_picking_weight import (
    upsert_weight, delete_weight, sum_weight_by_part_item, bulk_load_for_picking,
)


def _seed_atomic(db, order_id="HC-WT01", part_id="PJ-X-WT01", qty=200, bom_qty=200):
    db.add(PartModel(id=part_id, name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id=order_id, supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id=order_id, part_id=part_id, qty=qty, bom_qty=bom_qty)
    db.add(pi); db.flush()
    return order_id, pi


def test_upsert_weight_inserts_new_row(db):
    order_id, pi = _seed_atomic(db)
    row = upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")
    assert row.weight == Decimal("0.5000")
    assert row.weight_unit == "kg"


def test_upsert_weight_updates_existing(db):
    order_id, pi = _seed_atomic(db)
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.7, "kg")
    rows = db.query(HandcraftPickingWeight).filter_by(part_item_id=pi.id).all()
    assert len(rows) == 1
    assert rows[0].weight == Decimal("0.7000")


def test_upsert_weight_rejects_part_item_outside_order(db):
    _, pi = _seed_atomic(db, order_id="HC-WT02")
    db.add(HandcraftOrder(id="HC-OTHER", supplier_name="S", status="pending"))
    db.flush()
    import pytest
    with pytest.raises(ValueError, match="不属于"):
        upsert_weight(db, "HC-OTHER", pi.id, "PJ-X-WT01", 0.5, "kg")


def test_upsert_weight_rejects_bad_atom_part_id(db):
    order_id, pi = _seed_atomic(db, order_id="HC-WT03")
    import pytest
    with pytest.raises(ValueError, match="配件 .* 不存在"):
        upsert_weight(db, order_id, pi.id, "PJ-NOPE", 0.5, "kg")


def test_delete_weight(db):
    order_id, pi = _seed_atomic(db, order_id="HC-WT04")
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")
    assert delete_weight(db, pi.id, "PJ-X-WT01") is True
    assert delete_weight(db, pi.id, "PJ-X-WT01") is False  # second call: nothing to delete
```

- [ ] **Step 3.2: Run tests — expect ImportError**

```bash
.venv/bin/pytest tests/test_api_handcraft_picking_weight.py -x --tb=short
```

Expected: ImportError on `services.handcraft_picking_weight`.

- [ ] **Step 3.3: Implement `services/handcraft_picking_weight.py`**

Create the file:

```python
"""Picking weight (per atom) service.

Stores actual measured weights per (handcraft_part_item × atom_part_id),
which is the granularity exposed in the picking simulation. Atomic part_items
have one row; composite part_items can have multiple atom rows after expansion.

This module does NOT touch inventory_log. Weights are reference data for
records-keeping (UI, PDF, possibly later cost calculation).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from models.handcraft_order import (
    HandcraftPartItem,
    HandcraftPickingWeight,
)
from models.part import Part


_UNIT_TO_KG = {"kg": Decimal("1"), "g": Decimal("0.001")}


def _validate_part_item_in_order(db: Session, order_id: str, part_item_id: int) -> HandcraftPartItem:
    pi = db.query(HandcraftPartItem).filter_by(id=part_item_id).one_or_none()
    if pi is None or pi.handcraft_order_id != order_id:
        raise ValueError(f"part_item {part_item_id} 不属于手工单 {order_id}")
    return pi


def _validate_atom_part_id(db: Session, atom_part_id: str) -> None:
    if db.query(Part).filter_by(id=atom_part_id).count() == 0:
        raise ValueError(f"配件 {atom_part_id} 不存在")


def upsert_weight(
    db: Session,
    order_id: str,
    part_item_id: int,
    atom_part_id: str,
    weight: float,
    weight_unit: str = "kg",
) -> HandcraftPickingWeight:
    """Insert or update the (part_item, atom_part) weight record.

    Raises ValueError if part_item is not in the order or atom_part_id does
    not exist. Caller (API layer) must check order status separately.
    """
    _validate_part_item_in_order(db, order_id, part_item_id)
    _validate_atom_part_id(db, atom_part_id)
    if weight_unit not in _UNIT_TO_KG:
        raise ValueError(f"unsupported weight_unit: {weight_unit}")

    row = (
        db.query(HandcraftPickingWeight)
        .filter_by(part_item_id=part_item_id, atom_part_id=atom_part_id)
        .one_or_none()
    )
    weight_dec = Decimal(str(weight)).quantize(Decimal("0.0001"))
    if row is None:
        row = HandcraftPickingWeight(
            handcraft_order_id=order_id,
            part_item_id=part_item_id,
            atom_part_id=atom_part_id,
            weight=weight_dec,
            weight_unit=weight_unit,
        )
        db.add(row)
    else:
        row.weight = weight_dec
        row.weight_unit = weight_unit
    db.flush()
    return row


def delete_weight(db: Session, part_item_id: int, atom_part_id: str) -> bool:
    """Delete the (part_item, atom_part) weight record. Returns True if a row
    was deleted, False if no record existed."""
    row = (
        db.query(HandcraftPickingWeight)
        .filter_by(part_item_id=part_item_id, atom_part_id=atom_part_id)
        .one_or_none()
    )
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def bulk_load_for_picking(
    db: Session, order_id: str
) -> dict[tuple[int, str], HandcraftPickingWeight]:
    """Load all weight rows for a handcraft order, keyed by (part_item_id, atom_part_id).
    Used by the picking simulation service to populate weights in one query."""
    rows = (
        db.query(HandcraftPickingWeight)
        .filter_by(handcraft_order_id=order_id)
        .all()
    )
    return {(r.part_item_id, r.atom_part_id): r for r in rows}


def sum_weight_by_part_item(
    db: Session, part_item_id: int, target_unit: str = "kg"
) -> Optional[float]:
    """SUM all atom weights for a part_item, normalized to target_unit.

    Returns None if no weight rows exist (so the caller can show '—' instead
    of '0'). target_unit defaults to 'kg' to match the picking sim default.
    """
    if target_unit not in _UNIT_TO_KG:
        raise ValueError(f"unsupported target_unit: {target_unit}")
    rows = (
        db.query(HandcraftPickingWeight)
        .filter_by(part_item_id=part_item_id)
        .all()
    )
    if not rows:
        return None
    target_factor = _UNIT_TO_KG[target_unit]
    total_kg = sum(
        Decimal(str(r.weight)) * _UNIT_TO_KG[r.weight_unit]
        for r in rows
    )
    return float(total_kg / target_factor)
```

- [ ] **Step 3.4: Run tests — expect pass**

```bash
.venv/bin/pytest tests/test_api_handcraft_picking_weight.py -x --tb=short
```

Expected: 5 passed.

- [ ] **Step 3.5: Commit**

```bash
git add services/handcraft_picking_weight.py tests/test_api_handcraft_picking_weight.py
git commit -m "feat(handcraft): handcraft_picking_weight service (upsert/delete/bulk/sum)"
```

---

## Task 4: Add tests + impl for `bulk_load_for_picking` and `sum_weight_by_part_item` (mixed units)

**Files:**
- Modify: `tests/test_api_handcraft_picking_weight.py`

(`bulk_load_for_picking` and `sum_weight_by_part_item` were implemented in Task 3 — now add explicit tests for mixed-unit SUM + bulk-load shape.)

- [ ] **Step 4.1: Add tests for mixed-unit SUM and bulk loading**

Append to `tests/test_api_handcraft_picking_weight.py`:

```python
def test_sum_weight_handles_mixed_units(db):
    order_id, pi = _seed_atomic(db, order_id="HC-WT05")
    db.add(PartModel(id="PJ-X-WTB", name="扣环", category="小配件", size_tier="small"))
    db.flush()
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")     # 500 g
    upsert_weight(db, order_id, pi.id, "PJ-X-WTB", 300, "g")       # 300 g
    total_kg = sum_weight_by_part_item(db, pi.id, target_unit="kg")
    assert abs(total_kg - 0.8) < 1e-6


def test_sum_weight_returns_none_when_no_rows(db):
    _, pi = _seed_atomic(db, order_id="HC-WT06")
    assert sum_weight_by_part_item(db, pi.id) is None


def test_bulk_load_returns_keyed_dict(db):
    order_id, pi = _seed_atomic(db, order_id="HC-WT07")
    db.add(PartModel(id="PJ-X-WTB", name="扣环", category="小配件", size_tier="small"))
    db.flush()
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")
    upsert_weight(db, order_id, pi.id, "PJ-X-WTB", 0.3, "kg")
    loaded = bulk_load_for_picking(db, order_id)
    assert (pi.id, "PJ-X-WT01") in loaded
    assert (pi.id, "PJ-X-WTB") in loaded
    assert float(loaded[(pi.id, "PJ-X-WT01")].weight) == 0.5
```

- [ ] **Step 4.2: Run tests**

```bash
.venv/bin/pytest tests/test_api_handcraft_picking_weight.py -x --tb=short
```

Expected: 8 passed.

- [ ] **Step 4.3: Commit**

```bash
git add tests/test_api_handcraft_picking_weight.py
git commit -m "test(handcraft): mixed-unit weight SUM + bulk load coverage"
```

---

## Task 5: Rebuild `services/handcraft_picking.py` to aggregate by `atom_part_id`

**Files:**
- Modify: `services/handcraft_picking.py`
- Modify: `tests/test_api_handcraft_picking.py`

This is the largest task. Existing tests assert the old shape; we update them as we go.

- [ ] **Step 5.1: Write failing tests for the new merged shape**

In `tests/test_api_handcraft_picking.py`, add a new section near the top of the file (after imports). Adapt existing imports to add `PickingGroup`, `PickingSourceRow`. Locate any `HandcraftPickingGroup` / `HandcraftPickingVariant` references and update them to the new names — or update assertions to use the new dict shape directly.

Add new tests:

```python
def test_merge_same_atom_across_part_items_into_one_group(client, db):
    """Two part_items with the same part_id should produce ONE group with two rows."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem

    db.add(PartModel(id="PJ-X-LK", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-MG1", supplier_name="S", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-MG1", part_id="PJ-X-LK", qty=200, bom_qty=200))
    db.add(HandcraftPartItem(handcraft_order_id="HC-MG1", part_id="PJ-X-LK", qty=100, bom_qty=100))
    db.flush()

    resp = client.get("/api/handcraft/HC-MG1/picking")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["groups"]) == 1
    g = body["groups"][0]
    assert g["atom_part_id"] == "PJ-X-LK"
    assert g["total_needed_qty"] == 300
    assert len(g["rows"]) == 2
    assert g["rows"][0]["qty"] == 200
    assert g["rows"][1]["qty"] == 100


def test_total_suggested_is_sum_of_per_row_suggested(client, db):
    """Group total_suggested = sum(row.suggested), each row applies floor independently.
    Small tier: 200 → 250 (200+50); 100 → 150 (100+50). Sum = 400, NOT 350."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem

    db.add(PartModel(id="PJ-X-SM", name="链头小", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-MG2", supplier_name="S", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-MG2", part_id="PJ-X-SM", qty=200, bom_qty=200))
    db.add(HandcraftPartItem(handcraft_order_id="HC-MG2", part_id="PJ-X-SM", qty=100, bom_qty=100))
    db.flush()

    body = client.get("/api/handcraft/HC-MG2/picking").json()
    g = body["groups"][0]
    assert g["rows"][0]["suggested_qty"] == 250
    assert g["rows"][1]["suggested_qty"] == 150
    assert g["total_suggested_qty"] == 400


def test_composite_expansion_marks_is_composite_expansion(client, db):
    """A composite part_item expands into atoms; those rows should be flagged."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem
    from services.part_bom import set_part_bom

    db.add(PartModel(id="PJ-X-LK2", name="链头", category="小配件", size_tier="small"))
    db.add(PartModel(id="PJ-X-CL", name="扣环", category="小配件", size_tier="small"))
    db.add(PartModel(id="PJ-X-SET", name="套链", category="小配件", size_tier="small", is_composite=True))
    db.flush()
    set_part_bom(db, "PJ-X-SET", [
        {"part_id": "PJ-X-LK2", "qty_per_unit": 1},
        {"part_id": "PJ-X-CL",  "qty_per_unit": 1},
    ])
    db.add(HandcraftOrder(id="HC-MG3", supplier_name="S", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-MG3", part_id="PJ-X-SET", qty=10, bom_qty=10))
    db.flush()

    body = client.get("/api/handcraft/HC-MG3/picking").json()
    # Two groups: 链头 and 扣环, each with one row from the composite expansion
    atom_ids = sorted(g["atom_part_id"] for g in body["groups"])
    assert atom_ids == ["PJ-X-CL", "PJ-X-LK2"]
    for g in body["groups"]:
        assert len(g["rows"]) == 1
        row = g["rows"][0]
        assert row["is_composite_expansion"] is True
        assert row["parent_composite_name"] == "套链"


def test_groups_ordered_by_first_seen(client, db):
    """Group order = first appearance of each atom_part_id in part_items.id ASC."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem

    db.add(PartModel(id="PJ-X-A", name="A", category="小配件", size_tier="small"))
    db.add(PartModel(id="PJ-X-B", name="B", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-MG4", supplier_name="S", status="pending"))
    db.flush()
    # First B (id=1), then A (id=2), then B again (id=3): expected group order [B, A]
    db.add(HandcraftPartItem(handcraft_order_id="HC-MG4", part_id="PJ-X-B", qty=1, bom_qty=1))
    db.add(HandcraftPartItem(handcraft_order_id="HC-MG4", part_id="PJ-X-A", qty=1, bom_qty=1))
    db.add(HandcraftPartItem(handcraft_order_id="HC-MG4", part_id="PJ-X-B", qty=2, bom_qty=2))
    db.flush()

    body = client.get("/api/handcraft/HC-MG4/picking").json()
    assert [g["atom_part_id"] for g in body["groups"]] == ["PJ-X-B", "PJ-X-A"]
    # And inside group B, rows should be ordered by part_item.id ASC
    g_b = body["groups"][0]
    assert [r["qty"] for r in g_b["rows"]] == [1, 2]


def test_picking_includes_weight_when_recorded(client, db):
    """Recorded weight surfaces in the picking response."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem
    from services.handcraft_picking_weight import upsert_weight

    db.add(PartModel(id="PJ-X-WT", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-MG5", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-MG5", part_id="PJ-X-WT", qty=200, bom_qty=200)
    db.add(pi); db.flush()
    upsert_weight(db, "HC-MG5", pi.id, "PJ-X-WT", 0.5, "kg")

    body = client.get("/api/handcraft/HC-MG5/picking").json()
    row = body["groups"][0]["rows"][0]
    assert row["weight"] == 0.5
    assert row["weight_unit"] == "kg"
```

- [ ] **Step 5.2: Run new tests — expect failures**

```bash
.venv/bin/pytest tests/test_api_handcraft_picking.py -x --tb=short -k "merge_same_atom or total_suggested_is_sum or composite_expansion_marks or groups_ordered_by_first_seen or includes_weight"
```

Expected: failures (response shape doesn't match yet).

- [ ] **Step 5.3: Rewrite the aggregation in `services/handcraft_picking.py`**

**Keep** the existing `mark_picked`, `unmark_picked`, `reset_picking`, and their helpers `_validate_pair_in_order` / `_check_writable`. They already use the correct `part_id` column on `HandcraftPickingRecord` and don't need changes.

Replace **only** `get_handcraft_picking_simulation` and `_expand_part_items` (and `_compute_suggested_qty` stays). Adjust imports to reference the new schema names. Final shape:

```python
"""Handcraft picking simulation (手工单配货模拟) service.

Aggregates a handcraft order's part items into a picker-friendly grouped
structure: each ATOMIC PART_ID becomes one group with one or more rows.
Atomic part_items contribute one row; composite part_items expand to multiple
rows that land in different atom groups.

Picked state persists per (handcraft_part_item_id, atom_part_id) in
handcraft_picking_record. Per-atom weight persists in
handcraft_picking_weight. This module does NOT touch inventory_log or
order status — purely a UI helper.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.handcraft_order import (
    HandcraftOrder,
    HandcraftPartItem,
    HandcraftPickingRecord,
)
from models.inventory_log import InventoryLog
from models.part import Part
from schemas.handcraft import (
    HandcraftPickingProgress,
    HandcraftPickingResponse,
    PickingGroup,
    PickingSourceRow,
)
from services.handcraft import compute_suggested_qty
from services.handcraft_picking_weight import bulk_load_for_picking


def _compute_suggested_qty(theoretical: Optional[float], part: Optional[Part]) -> Optional[int]:
    if theoretical is None or theoretical <= 0 or part is None:
        return None
    theo = Decimal(str(theoretical)).quantize(Decimal("0.0001"))
    if theo <= 0:
        return None
    return compute_suggested_qty(part, theo)


def get_handcraft_picking_simulation(
    db: Session, handcraft_order_id: str
) -> HandcraftPickingResponse:
    order = db.query(HandcraftOrder).filter_by(id=handcraft_order_id).one_or_none()
    if order is None:
        raise ValueError(f"手工单 {handcraft_order_id} 不存在")

    part_items = (
        db.query(HandcraftPartItem)
        .filter_by(handcraft_order_id=handcraft_order_id)
        .order_by(HandcraftPartItem.id.asc())
        .all()
    )
    if not part_items:
        return HandcraftPickingResponse(
            handcraft_order_id=order.id,
            supplier_name=order.supplier_name,
            status=order.status,
            groups=[],
            progress=HandcraftPickingProgress(total=0, picked=0),
        )

    # `_expand_part_items` returns dict[part_item_id, list[(atom_id, needed_qty, atom_ratio)]]
    # where needed_qty = pi.qty * atom_ratio (ratio=1.0 for atomic, BOM ratio for composite).
    expanded = _expand_part_items(db, part_items)

    atom_ids = sorted({atom_id for rows in expanded.values() for atom_id, _, _ in rows})
    parent_part_ids = list({pi.part_id for pi in part_items})
    parts_by_id = _load_parts(db, atom_ids + parent_part_ids)
    stock_by_part = _load_stock(db, atom_ids)
    picked_keys = _load_picked_keys(db, handcraft_order_id)
    weights_by_key = bulk_load_for_picking(db, handcraft_order_id)

    # First-seen order for groups: when each atom_part_id first appears
    # while iterating part_items in id ASC order.
    atom_first_seen: dict[str, int] = {}
    rows_by_atom: dict[str, list[PickingSourceRow]] = defaultdict(list)
    total = 0
    picked_count = 0
    for pi in part_items:
        parent_part = parts_by_id.get(pi.part_id)
        is_composite = bool(parent_part and parent_part.is_composite)
        for atom_id, qty_for_row, atom_ratio in expanded[pi.id]:
            atom_part = parts_by_id[atom_id]
            ratio = atom_ratio if atom_ratio is not None else 1.0
            bom_qty_for_row = (
                float(pi.bom_qty) * ratio if pi.bom_qty is not None else None
            )
            # qty_for_row is pi.qty * ratio; needed_qty for suggested calc uses bom_qty if set.
            needed_qty = bom_qty_for_row if bom_qty_for_row is not None else qty_for_row
            suggested = _compute_suggested_qty(needed_qty, atom_part)
            is_picked = (pi.id, atom_id) in picked_keys
            weight_row = weights_by_key.get((pi.id, atom_id))
            row = PickingSourceRow(
                part_item_id=pi.id,
                atom_part_id=atom_id,
                qty=qty_for_row,
                bom_qty=bom_qty_for_row,
                is_composite_expansion=is_composite,
                parent_composite_name=(parent_part.name if (is_composite and parent_part) else None),
                needed_qty=needed_qty,
                suggested_qty=suggested,
                weight=(float(weight_row.weight) if weight_row else None),
                weight_unit=(weight_row.weight_unit if weight_row else None),
                picked=is_picked,
            )
            rows_by_atom[atom_id].append(row)
            atom_first_seen.setdefault(atom_id, pi.id)
            total += 1
            if is_picked:
                picked_count += 1

    ordered_atom_ids = sorted(rows_by_atom.keys(), key=lambda a: atom_first_seen[a])
    groups = []
    for atom_id in ordered_atom_ids:
        atom_part = parts_by_id[atom_id]
        rows = rows_by_atom[atom_id]
        groups.append(PickingGroup(
            atom_part_id=atom_id,
            atom_part_name=atom_part.name,
            atom_part_image=atom_part.image,
            size_tier=atom_part.size_tier or "small",
            current_stock=stock_by_part.get(atom_id, 0.0),
            total_needed_qty=sum(r.needed_qty for r in rows),
            total_suggested_qty=sum((r.suggested_qty or 0) for r in rows),
            rows=rows,
        ))

    return HandcraftPickingResponse(
        handcraft_order_id=order.id,
        supplier_name=order.supplier_name,
        status=order.status,
        groups=groups,
        progress=HandcraftPickingProgress(total=total, picked=picked_count),
    )


# mark_picked / unmark_picked / reset_picking and their helpers
# (_validate_pair_in_order, _check_writable) are unchanged — keep as-is.


# --- helpers ---

def _expand_part_items(
    db: Session, part_items: list[HandcraftPartItem]
) -> dict[int, list[tuple[str, float, Optional[float]]]]:
    """For each HandcraftPartItem, return list of (atom_part_id, needed_qty, atom_ratio)
    tuples. Atomic: (part_id, pi.qty, 1.0). Composite: each atom expanded with
    needed_qty = pi.qty × ratio. Ratio is the per-composite-unit BOM ratio.

    This is intentionally the same shape as the previous implementation —
    only the consumer (caller above) has changed, not this helper.
    """
    if not part_items:
        return {}
    parent_part_ids = list({pi.part_id for pi in part_items})
    parent_parts = db.query(Part).filter(Part.id.in_(parent_part_ids)).all()
    is_composite = {p.id: bool(p.is_composite) for p in parent_parts}

    out: dict[int, list[tuple[str, float, Optional[float]]]] = {}
    for pi in part_items:
        if is_composite.get(pi.part_id, False):
            from services.picking import _expand_to_atoms
            atoms_per_unit = _expand_to_atoms(db, pi.part_id, Decimal("1.0"))
            agg_ratio: dict[str, float] = defaultdict(float)
            for atom_id, ratio in atoms_per_unit:
                agg_ratio[atom_id] += ratio
            qty = float(pi.qty)
            out[pi.id] = [
                (aid, round(r * qty, 4), round(r, 4))
                for aid, r in agg_ratio.items()
            ]
        else:
            out[pi.id] = [(pi.part_id, float(pi.qty), 1.0)]
    return out


def _load_parts(db: Session, part_ids: list[str]) -> dict[str, Part]:
    if not part_ids:
        return {}
    rows = db.query(Part).filter(Part.id.in_(set(part_ids))).all()
    return {p.id: p for p in rows}


def _load_stock(db: Session, atom_ids: list[str]) -> dict[str, float]:
    if not atom_ids:
        return {}
    rows = (
        db.query(InventoryLog.item_id, func.coalesce(func.sum(InventoryLog.change_qty), 0))
        .filter(InventoryLog.item_type == "part", InventoryLog.item_id.in_(set(atom_ids)))
        .group_by(InventoryLog.item_id)
        .all()
    )
    return {pid: float(qty) for pid, qty in rows}


def _load_picked_keys(db: Session, order_id: str) -> set[tuple[int, str]]:
    """Existing PickingRecord uses `part_id` (the atom's id) as column name.
    We return (part_item_id, atom_part_id) for parity with the aggregator's keying."""
    rows = (
        db.query(HandcraftPickingRecord.handcraft_part_item_id, HandcraftPickingRecord.part_id)
        .filter_by(handcraft_order_id=order_id)
        .all()
    )
    return {(pi_id, atom_id) for pi_id, atom_id in rows}
```

> **NOTE:** `_expand_to_atoms` returns `[(atom_id, ratio_per_unit), ...]`. Verify by reading `services/picking.py` first; if the actual signature differs, adjust accordingly. The previous `services/handcraft_picking.py` already used a similar pattern — copy that.

- [ ] **Step 5.4: Run new tests + the existing picking tests**

```bash
.venv/bin/pytest tests/test_api_handcraft_picking.py -x --tb=short
```

Expected: most tests pass, but the OLD assertions in pre-existing tests still reference `parent_qty`, `parent_part_id`, `parent_part_name`, `parent_is_composite`, `parent_bom_qty`, `part_id`, `part_name`, `needed_qty`, `current_stock` etc. **Update each old test inline to use the new field names** as you encounter failures. Generic mapping:

| Old field (HandcraftPickingGroup.x) | New field (PickingGroup.x or row) |
|---|---|
| `g.parent_part_id` | `g.atom_part_id` (when atomic) — for composite tests, the SOURCE jewelry part disappears |
| `g.parent_part_name` | `g.atom_part_name` |
| `g.part_item_id` | `row.part_item_id` |
| `g.parent_qty` | sum of `row.qty` (or just look at row.qty) |
| `g.parent_bom_qty` | sum of `row.bom_qty` |
| `g.rows[i].part_id` | `g.rows[i].atom_part_id` |
| `g.rows[i].part_name` | `g.atom_part_name` (now group-level) |
| `g.rows[i].needed_qty` | `g.rows[i].needed_qty` (unchanged) |
| `g.rows[i].current_stock` | `g.current_stock` (now group-level) |

Run repeatedly, fixing each test in turn:

```bash
.venv/bin/pytest tests/test_api_handcraft_picking.py -x --tb=long
```

Until all green.

- [ ] **Step 5.5: Commit**

```bash
git add services/handcraft_picking.py tests/test_api_handcraft_picking.py
git commit -m "refactor(handcraft): aggregate picking by atom_part_id with weight"
```

---

## Task 6: Add `PUT/DELETE /picking/weight` endpoints

**Files:**
- Modify: `api/handcraft.py`
- Modify: `tests/test_api_handcraft_picking_weight.py`

- [ ] **Step 6.1: Write failing endpoint tests**

Append to `tests/test_api_handcraft_picking_weight.py`:

```python
def test_api_put_weight_upsert(client, db):
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem

    db.add(PartModel(id="PJ-X-EP1", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-EP1", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-EP1", part_id="PJ-X-EP1", qty=200, bom_qty=200)
    db.add(pi); db.flush()
    pi_id = pi.id

    r = client.put(f"/api/handcraft/HC-EP1/picking/weight", json={
        "part_item_id": pi_id, "atom_part_id": "PJ-X-EP1",
        "weight": 0.5, "weight_unit": "kg",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["weight"] == 0.5


def test_api_put_weight_blocked_when_status_not_pending(client, db):
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem

    db.add(PartModel(id="PJ-X-EP2", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-EP2", supplier_name="S", status="processing"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-EP2", part_id="PJ-X-EP2", qty=200, bom_qty=200)
    db.add(pi); db.flush()
    r = client.put(f"/api/handcraft/HC-EP2/picking/weight", json={
        "part_item_id": pi.id, "atom_part_id": "PJ-X-EP2",
        "weight": 0.5,
    })
    assert r.status_code == 400


def test_api_delete_weight(client, db):
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem
    from services.handcraft_picking_weight import upsert_weight

    db.add(PartModel(id="PJ-X-EP3", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-EP3", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-EP3", part_id="PJ-X-EP3", qty=200, bom_qty=200)
    db.add(pi); db.flush()
    upsert_weight(db, "HC-EP3", pi.id, "PJ-X-EP3", 0.5, "kg")

    r = client.request("DELETE", f"/api/handcraft/HC-EP3/picking/weight",
                       json={"part_item_id": pi.id, "atom_part_id": "PJ-X-EP3"})
    assert r.status_code == 200
    assert r.json()["deleted"] is True
```

- [ ] **Step 6.2: Run — expect 404 / route-not-found**

```bash
.venv/bin/pytest tests/test_api_handcraft_picking_weight.py -k "api_" -x --tb=short
```

- [ ] **Step 6.3: Add the endpoints in `api/handcraft.py`**

Imports at top:

```python
from schemas.handcraft import (
    # ... existing imports ...
    HandcraftPickingWeightUpsertRequest,
    HandcraftPickingWeightDeleteRequest,
)
from services.handcraft_picking_weight import (
    upsert_weight as upsert_picking_weight,
    delete_weight as delete_picking_weight,
)
from models.handcraft_order import HandcraftOrder
```

Append after the existing `picking/reset` endpoint:

```python
@router.put("/{order_id}/picking/weight")
def api_handcraft_picking_weight_upsert(
    order_id: str,
    body: HandcraftPickingWeightUpsertRequest,
    db: Session = Depends(get_db),
):
    """Upsert per-atom weight. Pending status only."""
    order = db.query(HandcraftOrder).filter_by(id=order_id).one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail=f"手工单 {order_id} 不存在")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail=f"手工单状态为 {order.status}，无法编辑重量")
    with service_errors():
        row = upsert_picking_weight(
            db, order_id, body.part_item_id, body.atom_part_id,
            body.weight, body.weight_unit,
        )
    return {
        "part_item_id": row.part_item_id,
        "atom_part_id": row.atom_part_id,
        "weight": float(row.weight),
        "weight_unit": row.weight_unit,
    }


@router.delete("/{order_id}/picking/weight")
def api_handcraft_picking_weight_delete(
    order_id: str,
    body: HandcraftPickingWeightDeleteRequest,
    db: Session = Depends(get_db),
):
    """Delete per-atom weight. Pending status only."""
    order = db.query(HandcraftOrder).filter_by(id=order_id).one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail=f"手工单 {order_id} 不存在")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail=f"手工单状态为 {order.status}，无法删除重量")
    with service_errors():
        deleted = delete_picking_weight(db, body.part_item_id, body.atom_part_id)
    return {"deleted": deleted}
```

- [ ] **Step 6.4: Run all picking-weight tests**

```bash
.venv/bin/pytest tests/test_api_handcraft_picking_weight.py -x --tb=short
```

Expected: all green.

- [ ] **Step 6.5: Commit**

```bash
git add api/handcraft.py tests/test_api_handcraft_picking_weight.py
git commit -m "feat(handcraft): PUT/DELETE /picking/weight endpoints"
```

---

## Task 7: Route weight in `update_handcraft_part` to new table; reject for composite

**Files:**
- Modify: `services/handcraft.py:393-411`
- Modify: `tests/test_api_handcraft_picking_weight.py` (or create a new test file for handcraft part editing)

- [ ] **Step 7.1: Write failing tests**

Append to `tests/test_api_handcraft_picking_weight.py`:

```python
def test_patch_atomic_part_weight_lands_in_new_table(client, db):
    """PATCH /handcraft/{id}/parts/{item_id} with weight on atomic part_item
    should write to handcraft_picking_weight, NOT handcraft_part_item.weight."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftPickingWeight

    db.add(PartModel(id="PJ-X-PT1", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-PT1", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-PT1", part_id="PJ-X-PT1", qty=200, bom_qty=200)
    db.add(pi); db.flush()

    r = client.patch(f"/api/handcraft/HC-PT1/parts/{pi.id}",
                     json={"weight": 0.5, "weight_unit": "kg"})
    assert r.status_code == 200

    # Old column NOT touched (still null)
    db.refresh(pi)
    assert pi.weight is None

    # New table HAS the row
    rows = db.query(HandcraftPickingWeight).filter_by(part_item_id=pi.id).all()
    assert len(rows) == 1
    assert float(rows[0].weight) == 0.5


def test_patch_composite_part_weight_rejected(client, db):
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem
    from services.part_bom import set_part_bom

    db.add(PartModel(id="PJ-X-A1", name="原A", category="小配件", size_tier="small"))
    db.add(PartModel(id="PJ-X-B1", name="原B", category="小配件", size_tier="small"))
    db.add(PartModel(id="PJ-X-CO1", name="组合", category="小配件", size_tier="small", is_composite=True))
    db.flush()
    set_part_bom(db, "PJ-X-CO1", [{"part_id": "PJ-X-A1", "qty_per_unit": 1}, {"part_id": "PJ-X-B1", "qty_per_unit": 1}])
    db.add(HandcraftOrder(id="HC-PT2", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-PT2", part_id="PJ-X-CO1", qty=10, bom_qty=10)
    db.add(pi); db.flush()

    r = client.patch(f"/api/handcraft/HC-PT2/parts/{pi.id}",
                     json={"weight": 0.5, "weight_unit": "kg"})
    assert r.status_code == 400


def test_patch_non_weight_fields_unchanged_for_both(client, db):
    """Non-weight fields still update normally for atomic and composite alike."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem

    db.add(PartModel(id="PJ-X-PT3", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-PT3", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-PT3", part_id="PJ-X-PT3", qty=200, bom_qty=200)
    db.add(pi); db.flush()

    r = client.patch(f"/api/handcraft/HC-PT3/parts/{pi.id}", json={"note": "hello"})
    assert r.status_code == 200
    db.refresh(pi)
    assert pi.note == "hello"
```

- [ ] **Step 7.2: Update `services/handcraft.py update_handcraft_part`**

Locate the function (around line 393). The current logic does `setattr(item, k, v)` for `(weight, weight_unit, ...)` fields. Change so that when `weight` or `weight_unit` is in the payload:

1. If part is composite → raise `ValueError("组合配件不支持直接编辑重量；请在配货模拟中按 atom 输入")`
2. If atomic → call `services.handcraft_picking_weight.upsert_weight(db, order_id, item.id, item.part_id, weight, weight_unit)` and pop `weight`/`weight_unit` from the data dict before the generic setattr loop runs.

Concrete patch (read the existing function first; this is illustrative):

```python
def update_handcraft_part(db: Session, order_id: str, item_id: int, data: dict) -> HandcraftPartItem:
    item = db.query(HandcraftPartItem).filter(
        HandcraftPartItem.id == item_id,
        HandcraftPartItem.handcraft_order_id == order_id,
    ).one_or_none()
    if item is None:
        raise ValueError(f"HandcraftPartItem {item_id} not found in order {order_id}")

    # Route weight to handcraft_picking_weight table.
    weight_keys = {"weight", "weight_unit"}
    if weight_keys & data.keys():
        from services.handcraft_picking_weight import upsert_weight, delete_weight
        from models.part import Part
        part = db.query(Part).filter_by(id=item.part_id).one_or_none()
        if part is None:
            raise ValueError(f"配件 {item.part_id} 不存在")
        if part.is_composite:
            raise ValueError("组合配件不支持直接编辑重量；请在配货模拟中按 atom 输入")
        weight_val = data.pop("weight", None)
        unit_val = data.pop("weight_unit", "kg") or "kg"
        if weight_val is None:
            delete_weight(db, item.id, item.part_id)
        else:
            upsert_weight(db, order_id, item.id, item.part_id, float(weight_val), unit_val)

    for wf in ("weight", "weight_unit"):
        data.pop(wf, None)  # safety — should already be popped
    for k, v in data.items():
        setattr(item, k, v)
    db.flush()
    return item
```

- [ ] **Step 7.3: Run new tests + existing handcraft tests**

```bash
.venv/bin/pytest tests/test_api_handcraft_picking_weight.py tests/test_api_handcraft.py -x --tb=short
```

Expected: green. If `test_api_handcraft.py` has tests that PATCH weight on atomic part_items and ASSERT on `HandcraftPartItem.weight` directly, update those assertions.

- [ ] **Step 7.4: Commit**

```bash
git add services/handcraft.py tests/test_api_handcraft_picking_weight.py tests/test_api_handcraft.py
git commit -m "feat(handcraft): route part weight edits to handcraft_picking_weight"
```

---

## Task 8: One-shot data migration in `ensure_schema_compat`

**Files:**
- Modify: `database.py`

- [ ] **Step 8.1: Write failing test**

Add to `tests/test_api_handcraft_picking_weight.py`:

```python
def test_ensure_schema_compat_backfills_existing_weights(db):
    """Existing HandcraftPartItem.weight values get migrated to handcraft_picking_weight."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftPickingWeight
    from database import ensure_schema_compat
    from sqlalchemy import text

    db.add(PartModel(id="PJ-X-MG1", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-MGR1", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-MGR1", part_id="PJ-X-MG1", qty=200, bom_qty=200,
                           weight=0.5, weight_unit="g")
    db.add(pi); db.flush()
    pi_id = pi.id

    # Clear any existing migration rows for clean test
    db.execute(text("DELETE FROM handcraft_picking_weight WHERE part_item_id = :pi"), {"pi": pi_id})
    db.commit()

    ensure_schema_compat(target_engine=db.bind)

    rows = db.query(HandcraftPickingWeight).filter_by(part_item_id=pi_id).all()
    assert len(rows) == 1
    assert float(rows[0].weight) == 0.5
    assert rows[0].weight_unit == "g"

    # Idempotent: run again should not duplicate
    ensure_schema_compat(target_engine=db.bind)
    rows = db.query(HandcraftPickingWeight).filter_by(part_item_id=pi_id).all()
    assert len(rows) == 1
```

- [ ] **Step 8.2: Run — expect failure (no migration yet)**

```bash
.venv/bin/pytest tests/test_api_handcraft_picking_weight.py::test_ensure_schema_compat_backfills_existing_weights -x --tb=short
```

- [ ] **Step 8.3: Add idempotent backfill in `database.py ensure_schema_compat`**

After the table-creation block from Task 1, add:

```python
# Backfill existing HandcraftPartItem.weight into handcraft_picking_weight (idempotent).
# Each part_item with a non-null weight gets one row keyed by (part_item.id, part_item.part_id).
# Composite part_items: the migrated row treats the weight as the parent's atomic-self weight,
# preserving display continuity. Users can split per-atom going forward.
conn.execute(text("""
    INSERT INTO handcraft_picking_weight
        (handcraft_order_id, part_item_id, atom_part_id, weight, weight_unit, recorded_at)
    SELECT
        hpi.handcraft_order_id, hpi.id, hpi.part_id,
        hpi.weight, COALESCE(hpi.weight_unit, 'g'),
        CURRENT_TIMESTAMP
    FROM handcraft_part_item hpi
    WHERE hpi.weight IS NOT NULL
    ON CONFLICT (part_item_id, atom_part_id) DO NOTHING
"""))
```

(Use `text()` for raw SQL. `CURRENT_TIMESTAMP` is fine — `recorded_at` only matters for sorting which we don't currently expose.)

- [ ] **Step 8.4: Run test — expect pass**

```bash
.venv/bin/pytest tests/test_api_handcraft_picking_weight.py::test_ensure_schema_compat_backfills_existing_weights -x --tb=short
```

- [ ] **Step 8.5: Commit**

```bash
git add database.py tests/test_api_handcraft_picking_weight.py
git commit -m "feat(handcraft): idempotent backfill HandcraftPartItem.weight to picking_weight"
```

---

## Task 9: Update PDF rendering to new grouped layout

> **⚠ Sequencing note:** `services/handcraft_picking_list_pdf.py` currently calls `get_handcraft_picking_simulation` and reads the OLD response shape (`parent_part_name`, etc.). After Task 5 commits, the PDF will be broken until this task lands. If you run the full test suite between Task 5 and Task 9, the picking PDF smoke test (added in Task 9.3) will fail. **Recommendation:** Do Task 5 → Task 9 → Task 6 → ... in immediate sequence, or skip PDF tests in the gap.

**Files:**
- Modify: `services/handcraft_picking_list_pdf.py`

- [ ] **Step 9.1: Read the existing PDF builder**

```bash
.venv/bin/python -c "import services.handcraft_picking_list_pdf; print(services.handcraft_picking_list_pdf.__file__)"
```

Read the file. Locate where it iterates over `groups` and `rows`. The shape it reads has changed (Task 5).

- [ ] **Step 9.2: Adapt PDF code to new shape**

For each `group` (now a `PickingGroup`):
- Header line: `{atom_part_name} {atom_part_id} · {size_tier_label} · 合计 {total_needed_qty} (库存 {current_stock})`
- For each `row` (now `PickingSourceRow`):
  - Skip if `row.picked` and `include_picked is False` (existing logic; just adapted to new field name)
  - Render: `qty {row.qty} · bom {row.bom_qty}` + composite tag if `row.is_composite_expansion` → `[来自 {parent_composite_name} atom]`
  - Weight column: `row.weight} {row.weight_unit}` if present, else `_ _ _`
  - Suggested column: `row.suggested_qty`
  - Picked checkbox

The file's table column ordering should be: `name | weight | qty | suggested | picked` (same as UI).

- [ ] **Step 9.3: Smoke-test PDF generation**

There's no existing PDF unit test (the function returns bytes). Smoke-test by hitting the endpoint:

```python
def test_pdf_endpoint_smoke(client, db):
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem

    db.add(PartModel(id="PJ-X-PDF", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-PDF1", supplier_name="S", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-PDF1", part_id="PJ-X-PDF", qty=200, bom_qty=200))
    db.flush()
    r = client.post("/api/handcraft/HC-PDF1/picking/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert len(r.content) > 1000  # PDF has some real bytes
```

Add this to `tests/test_api_handcraft_picking.py` and run:

```bash
.venv/bin/pytest tests/test_api_handcraft_picking.py::test_pdf_endpoint_smoke -x --tb=short
```

- [ ] **Step 9.4: Commit**

```bash
git add services/handcraft_picking_list_pdf.py tests/test_api_handcraft_picking.py
git commit -m "feat(handcraft): PDF picking list — atom-grouped layout"
```

---

## Task 10: Frontend API client — add weight functions

**Files:**
- Modify: `frontend/src/api/handcraft.js`

- [ ] **Step 10.1: Read current API client**

```bash
grep -n "getHandcraftPicking\|markHandcraftPicking\|unmarkHandcraftPicking\|axios" frontend/src/api/handcraft.js
```

- [ ] **Step 10.2: Add weight client functions**

Append:

```js
export const upsertHandcraftPickingWeight = (orderId, payload) =>
  http.put(`/api/handcraft/${orderId}/picking/weight`, payload)

export const deleteHandcraftPickingWeight = (orderId, payload) =>
  http.delete(`/api/handcraft/${orderId}/picking/weight`, { data: payload })
```

(Use whatever HTTP client is imported at the top of the file — `http`, `axios`, etc. Match the existing pattern.)

- [ ] **Step 10.3: Commit**

```bash
git add frontend/src/api/handcraft.js
git commit -m "feat(handcraft): frontend API — picking weight upsert/delete"
```

---

## Task 11: Rewrite `HandcraftPickingSimulationModal.vue`

**Files:**
- Modify: `frontend/src/components/handcraft/HandcraftPickingSimulationModal.vue`

This is a big component change. The new shape:

- Outer table renders `groups[]` with `<thead>`: `配件/来源 | 重量 | 理论 | 建议 | 库存 | 已配`
- Each group emits two kinds of rows:
  1. **Group row** (橙色/绿色/红色): atom_part_name + ID + size_tier + progress; `total_needed_qty`; `total_suggested_qty`; `current_stock`; progress text
  2. **Source rows** (one per `row` in `group.rows`): `qty XXX · bom XXX` + composite tag; weight input (kg/g); per-row qty/suggested; checkbox

- [ ] **Step 11.1: Update template to render new shape**

Replace the table rendering section. Pseudo-code:

```vue
<template>
  <n-modal v-model:show="visible" preset="card" :title="title" style="width: 920px">
    <div class="head-strip">…</div>
    <div class="summary-bar">…</div>
    <table class="pk-table">
      <thead>
        <tr><th>配件/来源</th><th>重量</th><th>理论</th><th>建议</th><th>库存</th><th>已配</th></tr>
      </thead>
      <tbody>
        <template v-for="g in groups" :key="g.atom_part_id">
          <!-- Group header row -->
          <tr class="group-row" :class="{ done: groupDone(g), warn: stockWarn(g) }">
            <td>{{ g.atom_part_name }} {{ g.atom_part_id }}<span class="tier">{{ tierLabel(g.size_tier) }}</span><span class="progress-text">· {{ pickedInGroup(g) }}/{{ g.rows.length }} 已配</span></td>
            <td>—</td>
            <td>{{ g.total_needed_qty }}</td>
            <td class="pk-suggest">{{ g.total_suggested_qty }}</td>
            <td>{{ g.current_stock }}</td>
            <td>—</td>
          </tr>
          <!-- Source rows -->
          <tr v-for="r in g.rows" :key="`${r.part_item_id}-${r.atom_part_id}`" class="src-row" :class="{ picked: r.picked }">
            <td class="src-name">qty {{ r.qty }} · bom {{ r.bom_qty ?? '—' }}<span v-if="r.is_composite_expansion" class="composite-tag">来自{{ r.parent_composite_name }} atom</span></td>
            <td class="weight-cell">
              <div class="weight-input" :class="{ 'has-value': r.weight != null }">
                <input
                  type="number" step="0.0001" min="0"
                  :value="r.weight"
                  :disabled="readOnly"
                  @blur="onWeightBlur(g, r, $event)"
                />
                <select :value="r.weight_unit || 'kg'" :disabled="readOnly" @change="onUnitChange(g, r, $event)">
                  <option value="kg">kg</option>
                  <option value="g">g</option>
                </select>
              </div>
            </td>
            <td>{{ r.qty }}</td>
            <td class="pk-suggest">{{ r.suggested_qty ?? '—' }}</td>
            <td>—</td>
            <td><input type="checkbox" :checked="r.picked" :disabled="readOnly" @change="onPickToggle(g, r)" /></td>
          </tr>
        </template>
      </tbody>
    </table>
  </n-modal>
</template>
```

- [ ] **Step 11.2: Implement script section helpers**

```js
import { upsertHandcraftPickingWeight, deleteHandcraftPickingWeight, markHandcraftPicking, unmarkHandcraftPicking } from '@/api/handcraft'

const readOnly = computed(() => props.status !== 'pending')
const groupDone = (g) => g.rows.every(r => r.picked)
const stockWarn = (g) => g.current_stock < g.total_suggested_qty
const pickedInGroup = (g) => g.rows.filter(r => r.picked).length
const tierLabel = (tier) => tier === 'small' ? '小件' : tier === 'medium' ? '中件' : tier

async function onWeightBlur(group, row, evt) {
  const val = evt.target.value
  if (val === '' || val === null || Number(val) <= 0) {
    if (row.weight != null) {
      await deleteHandcraftPickingWeight(props.orderId, {
        part_item_id: row.part_item_id, atom_part_id: row.atom_part_id,
      })
      row.weight = null
    }
    return
  }
  const unit = row.weight_unit || 'kg'
  const resp = await upsertHandcraftPickingWeight(props.orderId, {
    part_item_id: row.part_item_id, atom_part_id: row.atom_part_id,
    weight: Number(val), weight_unit: unit,
  })
  row.weight = resp.data.weight
  row.weight_unit = resp.data.weight_unit
}

async function onUnitChange(group, row, evt) {
  row.weight_unit = evt.target.value
  if (row.weight != null && row.weight > 0) {
    await upsertHandcraftPickingWeight(props.orderId, {
      part_item_id: row.part_item_id, atom_part_id: row.atom_part_id,
      weight: row.weight, weight_unit: row.weight_unit,
    })
  }
}

async function onPickToggle(group, row) {
  if (row.picked) {
    await unmarkHandcraftPicking(props.orderId, { part_item_id: row.part_item_id, part_id: row.atom_part_id })
    row.picked = false
  } else {
    await markHandcraftPicking(props.orderId, { part_item_id: row.part_item_id, part_id: row.atom_part_id })
    row.picked = true
  }
}
```

(Hook `mark/unmark` API — check the existing client for actual function names. The schema field for the legacy mark request is `part_id`, but on our side the data structure says `atom_part_id` — the API contract is unchanged so we pass the atom id under the `part_id` key.)

- [ ] **Step 11.3: Verify in browser**

Restart dev server (already running on http://localhost:5174/). Open a handcraft order, click 配货模拟, verify:
- Same atom across multiple part_items merges into one group
- Composite atom rows show `来自 X atom` label
- Weight inputs save on blur
- Status pending shows editable; processing/completed shows read-only

- [ ] **Step 11.4: Commit**

```bash
git add frontend/src/components/handcraft/HandcraftPickingSimulationModal.vue
git commit -m "feat(handcraft): picking modal — atom-grouped layout + weight inputs"
```

---

## Task 12: Update `HandcraftDetail.vue` parts table weight column

**Files:**
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue:1500-1517`
- Modify: `frontend/src/api/handcraft.js`

- [ ] **Step 12.1: Add a bulk weight loader endpoint or use the picking endpoint**

The picking simulation response already carries weights; for the parts table, simplest path: call `GET /api/handcraft/{id}/picking` to get `groups[].rows[].weight`, then build a per-part_item map: atomic = `row.weight`, composite = SUM (across all rows with same `part_item_id`, normalized to kg).

(No new endpoint needed.)

- [ ] **Step 12.2: Update the weight column render in `HandcraftDetail.vue`**

Locate the existing weight column (line 1500–1517 area). Replace with:

```js
{
  title: '重量',
  key: 'weight',
  render: (row) => {
    const parts = pickingPartsByItemId.value[row.id]  // computed from picking response
    if (!parts) return '—'
    if (row.is_composite) {
      const total = parts.reduce((s, r) => s + toKg(r.weight, r.weight_unit), 0)
      return parts.length === 0 ? '—' : `${total.toFixed(3)} kg（合计·只读）`
    }
    // atomic — single picking row
    const r = parts[0]
    return h(NInputNumber, {
      value: r.weight ?? null,
      precision: 4,
      min: 0,
      style: 'width: 110px',
      'onUpdate:value': (v) => { r.weight = v },
      onBlur: async () => {
        const orderId = route.params.id
        if (r.weight == null || r.weight <= 0) {
          await deleteHandcraftPickingWeight(orderId, {
            part_item_id: row.id, atom_part_id: row.part_id,
          })
        } else {
          await upsertHandcraftPickingWeight(orderId, {
            part_item_id: row.id, atom_part_id: row.part_id,
            weight: Number(r.weight), weight_unit: r.weight_unit || 'kg',
          })
        }
      },
    })
  },
}
```

Add a `pickingPartsByItemId` computed that reshapes the picking GET response into `{ part_item_id: [rows...] }`. Trigger a fetch of this on mount and after PATCH operations.

Helper:

```js
const toKg = (w, unit) => {
  if (w == null) return 0
  return unit === 'g' ? Number(w) / 1000 : Number(w)
}
```

- [ ] **Step 12.3: Verify in browser**

Open a handcraft order detail page:
- Atomic part_item: weight column shows input box, edits save, then the value also appears in 配货模拟
- Composite part_item: weight column shows `0.X kg（合计·只读）` and is not editable

- [ ] **Step 12.4: Commit**

```bash
git add frontend/src/views/handcraft/HandcraftDetail.vue frontend/src/api/handcraft.js
git commit -m "feat(handcraft): parts table weight column — read picking_weight, lock composite"
```

---

## Task 13: End-to-end manual verification

- [ ] **Step 13.1: Run full pytest**

```bash
.venv/bin/pytest --tb=short 2>&1 | tail -25
```

Expected: all originally-passing tests still pass + new ones pass. Note any pre-existing failures (from main branch state) and ignore them — verify they fail on the parent commit too.

- [ ] **Step 13.2: Frontend smoke checklist**

Open http://localhost:5174/ and walk through:

- [ ] Create handcraft order with 2 jewelries that share a part (same atom across multiple part_items)
- [ ] Open 配货模拟 → confirm same atom appears as ONE group with multiple sub-rows
- [ ] Type weight on a sub-row → tab away → reload page → weight persists
- [ ] Open the order's 配件明细 panel → confirm same weight value shows there
- [ ] Edit weight in 配件明细 panel → reopen 配货模拟 → confirm sync
- [ ] Add a composite part to the handcraft order
- [ ] In 配货模拟: composite atoms show `来自 X atom` tag; each weight input is independent
- [ ] In 配件明细: composite row weight shows SUM (read-only)
- [ ] Send order to processing (`POST /send`) → confirm 配货模拟 becomes read-only (no weight edits, no checkbox toggles)
- [ ] Export PDF → confirm grouped layout, composite rows have tag, picked rows excluded

- [ ] **Step 13.3: Final commit if any small fixes were made**

```bash
git add -A
git commit -m "chore(handcraft): post-verification fixes" || true
```

---

## Spec Coverage Self-Check

Mapping spec sections to plan tasks:

| Spec section | Tasks |
|---|---|
| §0 Pure presentation; no inventory writes | All — explicit constraint, no inventory_log writes anywhere |
| §1 Background / motivation | covered by goal |
| §2.1 Layout C | T11 |
| §2.2 Visual rules (color, progress, stock warn) | T11 |
| §2.3 Column order incl weight ← of theoretical | T11 |
| §2.4 No note in sub-row | T11 |
| §2.5 Status gating (pending only) | T6 (endpoint), T7 (PATCH), T11 (UI) |
| §2.6 Sort by first-seen | T5 |
| §3.1 New table | T1 |
| §3.2 Old field kept, not written | T7 |
| §3.3 配件明细 panel sync | T12 |
| §4.1 New schemas | T2 |
| §4.2 Suggested = sum | T5 |
| §4.3 First-seen ordering | T5 |
| §4.4 New endpoints | T6 |
| §4.5 Service module | T3, T4 |
| §5 Migration | T1 (table) + T8 (data) |
| §6 PDF | T9 |
| §7.1 Picking modal | T11 |
| §7.2 配件明细 panel | T12 |
| §7.3 API client | T10 |
| §8 Edge cases | covered piecemeal in T5/T7/T11 |
| §10 Verification checklist | T13 |
