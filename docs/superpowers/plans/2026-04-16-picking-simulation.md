# Picking Simulation (配货模拟) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 配件汇总 card's "导出 PDF" button with a "配货模拟" modal that shows variant-grouped parts, persists picking state server-side, and exports a printable picking list.

**Architecture:** New `order_picking_record` table stores per-variant picked state. A new `services/picking.py` aggregates order parts with composite-expansion via existing `_expand_composite_part()`. 5 new API endpoints under `/orders/{id}/picking`. New Vue modal component replaces the old PDF button. Old `parts_summary_pdf` code is deleted.

**Tech Stack:** FastAPI + SQLAlchemy (PostgreSQL), Pydantic V2, Vue 3 + Naive UI, ReportLab (PDF), pytest.

**Spec:** `docs/superpowers/specs/2026-04-16-picking-simulation-design.md`

---

## File Structure

**New files:**
- `services/picking.py` — aggregation + state mutation services
- `services/_pdf_helpers.py` — shared PDF utilities (extracted)
- `services/picking_list_pdf.py` — picking list PDF generator
- `tests/test_service_picking.py`
- `tests/test_api_picking.py`
- `frontend/src/components/picking/PickingSimulationModal.vue`

**Modified files:**
- `models/order.py` — add `OrderPickingRecord`
- `models/__init__.py` — export new model
- `schemas/order.py` — add picking schemas
- `api/orders.py` — add 5 endpoints, delete 1 endpoint
- `frontend/src/api/orders.js` — add picking functions, remove old
- `frontend/src/views/orders/OrderDetail.vue` — replace button + mount modal

**Deleted files:**
- `services/parts_summary_pdf.py`

**Deleted code** (in modified files):
- `api/orders.py`: `PartsSummaryPdfRequest` class, `api_download_parts_summary_pdf` handler
- `tests/test_api_order_todo.py`: 6 tests for `parts-summary/pdf` endpoint (lines 1237-1341)
- `frontend/src/api/orders.js`: `downloadPartsSummaryPdf` function

---

## Task 1: Add `OrderPickingRecord` model

**Files:**
- Modify: `models/order.py`
- Modify: `models/__init__.py`
- Test: `tests/test_service_picking.py` (new file, will grow across tasks)

- [ ] **Step 1: Create the test file with a model smoke test**

Create `tests/test_service_picking.py`:

```python
"""Tests for services/picking.py — picking simulation aggregation and state."""

from decimal import Decimal
from sqlalchemy import inspect

from models.order import Order, OrderPickingRecord


def test_order_picking_record_table_exists(db):
    """The OrderPickingRecord table is registered with SQLAlchemy and create_all()
    made it. Basic smoke test for the model wiring."""
    insp = inspect(db.get_bind())
    assert "order_picking_record" in insp.get_table_names()


def test_order_picking_record_insert_and_read(db):
    """Insert a picking record and read it back. Verifies columns exist,
    defaults work, and unique key isn't fighting normal inserts."""
    order = Order(id="OR-PICK-1", customer_name="Test")
    db.add(order)
    db.flush()

    rec = OrderPickingRecord(
        order_id="OR-PICK-1",
        part_id="PJ-X-00001",
        qty_per_unit=Decimal("2.0000"),
    )
    db.add(rec)
    db.flush()

    row = db.query(OrderPickingRecord).filter_by(order_id="OR-PICK-1").one()
    assert row.part_id == "PJ-X-00001"
    assert float(row.qty_per_unit) == 2.0
    assert row.picked_at is not None  # default populated
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_service_picking.py -v`
Expected: FAIL with `ImportError: cannot import name 'OrderPickingRecord' from 'models.order'`

- [ ] **Step 3: Add `OrderPickingRecord` to `models/order.py`**

Append to `models/order.py` (after `OrderItemLink`):

```python
class OrderPickingRecord(Base):
    """Per-variant picking state for the 配货模拟 (picking simulation) feature.
    Row exists = picked; no row = not picked. No boolean column — presence IS
    the state. Does not affect inventory or order status; purely a UI helper."""

    __tablename__ = "order_picking_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("order.id"), nullable=False, index=True)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty_per_unit = Column(Numeric(10, 4), nullable=False)
    picked_at = Column(DateTime, default=now_beijing, nullable=False)

    __table_args__ = (
        UniqueConstraint("order_id", "part_id", "qty_per_unit",
                         name="uq_order_picking_record_order_part_qty"),
    )
```

Update the imports at the top of `models/order.py` to include `UniqueConstraint`:

```python
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
```

- [ ] **Step 4: Export new model from `models/__init__.py`**

In `models/__init__.py`:

- Change the order import line from:
  ```python
  from .order import Order, OrderItem, OrderTodoItem, OrderItemLink
  ```
  to:
  ```python
  from .order import Order, OrderItem, OrderTodoItem, OrderItemLink, OrderPickingRecord
  ```
- Add `"OrderPickingRecord",` to the `__all__` list (alphabetically near other Order types).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_service_picking.py -v`
Expected: PASS (both tests)

- [ ] **Step 6: Commit**

```bash
git add models/order.py models/__init__.py tests/test_service_picking.py
git commit -m "feat(picking): add OrderPickingRecord model

New table order_picking_record stores per-variant picking state for the
配货模拟 feature. Presence of a row = picked; no row = not picked. No
boolean column — unique constraint on (order_id, part_id, qty_per_unit)
enforces one row per variant."
```

---

## Task 2: Add Pydantic schemas for picking

**Files:**
- Modify: `schemas/order.py`
- Test: `tests/test_service_picking.py`

- [ ] **Step 1: Write a smoke test for schema validation**

Append to `tests/test_service_picking.py`:

```python
# --- Schema smoke tests ---

def test_picking_simulation_response_schema():
    from schemas.order import (
        PickingVariant, PickingPartRow, PickingProgress,
        PickingSimulationResponse,
    )
    resp = PickingSimulationResponse(
        order_id="OR-1",
        customer_name="客户 A",
        rows=[
            PickingPartRow(
                part_id="PJ-X-001",
                part_name="小珠子",
                part_image="https://example/x.png",
                current_stock=45.0,
                is_composite_child=False,
                variants=[
                    PickingVariant(qty_per_unit=2.0, units_count=10,
                                   subtotal=20.0, picked=False),
                ],
                total_required=20.0,
            ),
        ],
        progress=PickingProgress(total=1, picked=0),
    )
    assert resp.rows[0].variants[0].qty_per_unit == 2.0


def test_picking_mark_request_schema():
    from schemas.order import PickingMarkRequest
    req = PickingMarkRequest(part_id="PJ-X-001", qty_per_unit=3.0)
    assert req.qty_per_unit == 3.0


def test_picking_pdf_request_defaults_include_picked_false():
    from schemas.order import PickingPdfRequest
    req = PickingPdfRequest()
    assert req.include_picked is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_service_picking.py -v -k picking_`
Expected: FAIL with `ImportError: cannot import name 'PickingVariant' ...`

- [ ] **Step 3: Append schemas to `schemas/order.py`**

Append at the end of `schemas/order.py`:

```python
# --- Picking Simulation (配货模拟) ---


class PickingVariant(BaseModel):
    """One (qty_per_unit, units_count) row under a part."""
    qty_per_unit: float
    units_count: int
    subtotal: float
    picked: bool


class PickingPartRow(BaseModel):
    """One part with its variants. `is_composite_child=True` means this part
    appears — at least partly — because of a composite parent in some
    jewelry's BOM."""
    part_id: str
    part_name: str
    part_image: Optional[str] = None
    current_stock: float
    is_composite_child: bool
    variants: List[PickingVariant]
    total_required: float


class PickingProgress(BaseModel):
    total: int    # total number of variant rows
    picked: int   # number of variant rows currently marked picked


class PickingSimulationResponse(BaseModel):
    order_id: str
    customer_name: str
    rows: List[PickingPartRow]
    progress: PickingProgress


class PickingMarkRequest(BaseModel):
    part_id: str
    qty_per_unit: float


class PickingPdfRequest(BaseModel):
    include_picked: bool = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_service_picking.py -v -k picking_`
Expected: PASS (all 3 schema tests)

- [ ] **Step 5: Commit**

```bash
git add schemas/order.py tests/test_service_picking.py
git commit -m "feat(picking): add Pydantic schemas for picking simulation"
```

---

## Task 3: Aggregation service — core (BOM × order_items → variants)

Implements `get_picking_simulation()` for the base case: atomic parts,
no composite expansion yet, no stock/picked join yet.

**Files:**
- Create: `services/picking.py`
- Test: `tests/test_service_picking.py`

- [ ] **Step 1: Write the failing aggregation test**

Append to `tests/test_service_picking.py`:

```python
# --- Aggregation: core ---


def _make_part(db, pid: str, name: str, image: str = None, is_composite: bool = False):
    from models.part import Part
    p = Part(id=pid, name=name, category="吊坠", image=image, is_composite=is_composite)
    db.add(p)
    db.flush()
    return p


def _make_jewelry(db, jid: str, name: str):
    from models.jewelry import Jewelry
    j = Jewelry(id=jid, name=name, category="戒指")
    db.add(j)
    db.flush()
    return j


def _make_bom(db, jewelry_id: str, part_id: str, qty_per_unit: float):
    from models.bom import Bom
    from decimal import Decimal
    b = Bom(jewelry_id=jewelry_id, part_id=part_id,
            qty_per_unit=Decimal(str(qty_per_unit)))
    db.add(b)
    db.flush()
    return b


def _make_order(db, oid: str, items: list):
    """items: list of (jewelry_id, quantity)."""
    from models.order import Order, OrderItem
    from decimal import Decimal
    order = Order(id=oid, customer_name="客户测试")
    db.add(order)
    db.flush()
    for jid, qty in items:
        db.add(OrderItem(order_id=oid, jewelry_id=jid, quantity=qty,
                         unit_price=Decimal("1.0")))
    db.flush()
    return order


def test_picking_simulation_single_jewelry_single_part(db):
    """Order with 1 jewelry (quantity=10) → 1 part at qty_per_unit=2 → subtotal=20."""
    from services.picking import get_picking_simulation

    _make_part(db, "PJ-X-00001", "小珠子")
    _make_jewelry(db, "SP-0001", "项链 A")
    _make_bom(db, "SP-0001", "PJ-X-00001", 2.0)
    _make_order(db, "OR-0001", [("SP-0001", 10)])

    result = get_picking_simulation(db, "OR-0001")

    assert result.order_id == "OR-0001"
    assert result.customer_name == "客户测试"
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.part_id == "PJ-X-00001"
    assert row.part_name == "小珠子"
    assert row.is_composite_child is False
    assert len(row.variants) == 1
    v = row.variants[0]
    assert v.qty_per_unit == 2.0
    assert v.units_count == 10
    assert v.subtotal == 20.0
    assert v.picked is False
    assert row.total_required == 20.0
    assert result.progress.total == 1
    assert result.progress.picked == 0


def test_picking_simulation_empty_order(db):
    """Order with no items → empty rows, progress 0/0."""
    from services.picking import get_picking_simulation

    _make_order(db, "OR-EMPTY", [])
    result = get_picking_simulation(db, "OR-EMPTY")
    assert result.rows == []
    assert result.progress.total == 0
    assert result.progress.picked == 0


def test_picking_simulation_order_not_found(db):
    """Unknown order id → ValueError."""
    from services.picking import get_picking_simulation
    import pytest
    with pytest.raises(ValueError, match="OR-NOPE"):
        get_picking_simulation(db, "OR-NOPE")


def test_picking_simulation_two_parts_same_jewelry(db):
    """Jewelry with 2 parts in BOM → 2 rows sorted by part_id."""
    from services.picking import get_picking_simulation

    _make_part(db, "PJ-X-00001", "珠子")
    _make_part(db, "PJ-X-00002", "扣子")
    _make_jewelry(db, "SP-0001", "项链")
    _make_bom(db, "SP-0001", "PJ-X-00002", 1.0)  # insert out of order
    _make_bom(db, "SP-0001", "PJ-X-00001", 3.0)
    _make_order(db, "OR-0001", [("SP-0001", 5)])

    result = get_picking_simulation(db, "OR-0001")
    assert [r.part_id for r in result.rows] == ["PJ-X-00001", "PJ-X-00002"]
    assert result.rows[0].variants[0].subtotal == 15.0  # 3 × 5
    assert result.rows[1].variants[0].subtotal == 5.0   # 1 × 5


def test_picking_simulation_same_part_two_jewelries_same_qty(db):
    """Two jewelries using the same part at the same qty_per_unit →
    one row, one variant, units_count summed."""
    from services.picking import get_picking_simulation

    _make_part(db, "PJ-X-00001", "珠子")
    _make_jewelry(db, "SP-0001", "项链 A")
    _make_jewelry(db, "SP-0002", "项链 B")
    _make_bom(db, "SP-0001", "PJ-X-00001", 2.0)
    _make_bom(db, "SP-0002", "PJ-X-00001", 2.0)
    _make_order(db, "OR-0001", [("SP-0001", 10), ("SP-0002", 5)])

    result = get_picking_simulation(db, "OR-0001")
    assert len(result.rows) == 1
    row = result.rows[0]
    assert len(row.variants) == 1
    assert row.variants[0].units_count == 15  # 10 + 5
    assert row.variants[0].subtotal == 30.0   # 2 × 15


def test_picking_simulation_same_part_two_jewelries_different_qty(db):
    """Same part used at two distinct qty_per_unit → 1 row, 2 variants."""
    from services.picking import get_picking_simulation

    _make_part(db, "PJ-X-00001", "珠子")
    _make_jewelry(db, "SP-0001", "A")
    _make_jewelry(db, "SP-0002", "B")
    _make_bom(db, "SP-0001", "PJ-X-00001", 2.0)
    _make_bom(db, "SP-0002", "PJ-X-00001", 3.0)
    _make_order(db, "OR-0001", [("SP-0001", 10), ("SP-0002", 5)])

    result = get_picking_simulation(db, "OR-0001")
    assert len(result.rows) == 1
    row = result.rows[0]
    variants_by_qty = {v.qty_per_unit: v for v in row.variants}
    assert 2.0 in variants_by_qty
    assert 3.0 in variants_by_qty
    assert variants_by_qty[2.0].units_count == 10
    assert variants_by_qty[2.0].subtotal == 20.0
    assert variants_by_qty[3.0].units_count == 5
    assert variants_by_qty[3.0].subtotal == 15.0
    assert row.total_required == 35.0  # 20 + 15
    assert result.progress.total == 2  # 2 variants
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_service_picking.py -v -k simulation`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.picking'`

- [ ] **Step 3: Create `services/picking.py` with base aggregation**

Create `services/picking.py`:

```python
"""Picking simulation (配货模拟) service.

Aggregates an order's parts into a picker-friendly structure: each part may
have multiple variants distinguished by qty_per_unit. Composite parts are
expanded to atomic children (handled in a later task). Picked state is
joined in (handled in a later task).

This service is read-only aggregation + small CRUD on OrderPickingRecord.
It does NOT affect inventory_log, order status, or any stock computation.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from models.bom import Bom
from models.jewelry import Jewelry
from models.order import Order, OrderItem, OrderPickingRecord
from models.part import Part
from schemas.order import (
    PickingPartRow,
    PickingProgress,
    PickingSimulationResponse,
    PickingVariant,
)


def get_picking_simulation(db: Session, order_id: str) -> PickingSimulationResponse:
    """Aggregate all parts needed for `order_id` into a picking-oriented
    structure. Raises ValueError if the order does not exist."""
    order = db.query(Order).filter_by(id=order_id).one_or_none()
    if order is None:
        raise ValueError(f"订单 {order_id} 不存在")

    order_items = db.query(OrderItem).filter_by(order_id=order_id).all()
    if not order_items:
        return PickingSimulationResponse(
            order_id=order.id,
            customer_name=order.customer_name,
            rows=[],
            progress=PickingProgress(total=0, picked=0),
        )

    # Step 1: collect (part_id, qty_per_unit, units_count, from_composite) triples.
    triples = _collect_triples(db, order_items)

    # Step 2: aggregate into parts → variants.
    rows = _build_rows(db, triples)

    # Step 3: progress counts (picked join happens in a later task; for now
    # all picked=False, so picked count = 0).
    total_variants = sum(len(r.variants) for r in rows)
    picked_count = sum(1 for r in rows for v in r.variants if v.picked)

    return PickingSimulationResponse(
        order_id=order.id,
        customer_name=order.customer_name,
        rows=rows,
        progress=PickingProgress(total=total_variants, picked=picked_count),
    )


def _collect_triples(db: Session, order_items: list[OrderItem]) -> list[dict]:
    """Return list of {part_id, qty_per_unit, units_count, from_composite}.

    Composite expansion is wired in Task 4 — this base version only reads
    direct BOM rows."""
    # Batch-load BOM for all jewelries in the order.
    jewelry_ids = list({oi.jewelry_id for oi in order_items})
    boms = db.query(Bom).filter(Bom.jewelry_id.in_(jewelry_ids)).all()
    bom_by_jewelry: dict[str, list[Bom]] = defaultdict(list)
    for b in boms:
        bom_by_jewelry[b.jewelry_id].append(b)

    out: list[dict] = []
    for oi in order_items:
        for b in bom_by_jewelry.get(oi.jewelry_id, []):
            out.append({
                "part_id": b.part_id,
                "qty_per_unit": float(b.qty_per_unit),
                "units_count": oi.quantity,
                "from_composite": False,
            })
    return out


def _build_rows(db: Session, triples: list[dict]) -> list[PickingPartRow]:
    """Group triples by (part_id, qty_per_unit) → variants, then by part_id
    → rows. Part metadata batch-loaded."""
    if not triples:
        return []

    # Aggregate units_count by (part_id, qty_per_unit).
    grouped: dict[tuple[str, float], dict] = {}
    for t in triples:
        key = (t["part_id"], t["qty_per_unit"])
        entry = grouped.get(key)
        if entry is None:
            grouped[key] = {"units_count": 0, "from_composite": False}
            entry = grouped[key]
        entry["units_count"] += t["units_count"]
        if t["from_composite"]:
            entry["from_composite"] = True

    # Collect all part ids, batch-load parts.
    part_ids = sorted({k[0] for k in grouped.keys()})
    parts = db.query(Part).filter(Part.id.in_(part_ids)).all()
    part_by_id = {p.id: p for p in parts}

    # Assemble variants per part.
    variants_by_part: dict[str, list[PickingVariant]] = defaultdict(list)
    composite_flag: dict[str, bool] = defaultdict(bool)
    for (pid, qpu), entry in grouped.items():
        units = entry["units_count"]
        variants_by_part[pid].append(
            PickingVariant(
                qty_per_unit=qpu,
                units_count=units,
                subtotal=qpu * units,
                picked=False,  # joined in Task 5
            )
        )
        if entry["from_composite"]:
            composite_flag[pid] = True

    rows: list[PickingPartRow] = []
    for pid in part_ids:
        part = part_by_id.get(pid)
        if part is None:
            continue  # defensive — shouldn't happen given FK
        variants = sorted(variants_by_part[pid], key=lambda v: v.qty_per_unit)
        total_required = sum(v.subtotal for v in variants)
        rows.append(
            PickingPartRow(
                part_id=pid,
                part_name=part.name,
                part_image=part.image,
                current_stock=0.0,  # joined in Task 5
                is_composite_child=composite_flag[pid],
                variants=variants,
                total_required=total_required,
            )
        )
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_service_picking.py -v -k simulation`
Expected: PASS (all 6 aggregation tests)

- [ ] **Step 5: Commit**

```bash
git add services/picking.py tests/test_service_picking.py
git commit -m "feat(picking): aggregate order BOM into variant-grouped picking rows

services/picking.py :: get_picking_simulation() reads an order's
order_items × BOM, aggregates by (part_id, qty_per_unit) into variants,
groups by part. Composite expansion, current_stock, and picked state are
wired in subsequent commits."
```

---

## Task 4: Aggregation service — composite expansion

Reuses the existing `_expand_composite_part()` helper from `services/cutting_stats.py`.
After this task, a jewelry BOM that references a composite part contributes
the composite's atomic children to the picking rows (not the composite itself).

**Files:**
- Modify: `services/picking.py`
- Test: `tests/test_service_picking.py`

- [ ] **Step 1: Inspect the existing composite helper**

Open `services/cutting_stats.py` and read `_expand_composite_part()` (around
line 46). Key facts to re-use:
- Signature: `_expand_composite_part(db, parent_part_id, parent_part_name, parent_total_qty, source_label_suffix, _ancestors=frozenset())`
- It uses `services.part_bom.get_part_bom(db, parent_part_id)` internally to
  fetch a composite's immediate children.
- Its return shape is tuned to cutting stats (filters for "cm" patterns in
  part names). We CANNOT reuse its return value directly — we need a new
  helper that walks `get_part_bom()` recursively but returns ALL atomic
  descendants, regardless of name pattern.

We add a new helper `_expand_to_atoms()` in `services/picking.py` that
recursively walks composite BOMs and yields atomic (non-composite) leaves.

- [ ] **Step 2: Write failing composite expansion tests**

Append to `tests/test_service_picking.py`:

```python
# --- Aggregation: composite expansion ---


def _make_part_bom(db, parent_part_id: str, child_part_id: str, qty_per_unit: float):
    from models.part_bom import PartBom
    from decimal import Decimal
    pb = PartBom(parent_part_id=parent_part_id, child_part_id=child_part_id,
                 qty_per_unit=Decimal(str(qty_per_unit)))
    db.add(pb)
    db.flush()
    return pb


def test_picking_simulation_composite_expanded_to_atoms(db):
    """Jewelry BOM references a composite part → output contains atomic
    children only, with is_composite_child=True; composite itself is absent."""
    from services.picking import get_picking_simulation

    # Composite "金属底托" has 2 atomic children: 焊接片 × 2, 链扣 × 1
    composite = _make_part(db, "PJ-X-00010", "金属底托", is_composite=True)
    atom_a = _make_part(db, "PJ-X-00011", "焊接片")
    atom_b = _make_part(db, "PJ-X-00012", "链扣")
    _make_part_bom(db, "PJ-X-00010", "PJ-X-00011", 2.0)
    _make_part_bom(db, "PJ-X-00010", "PJ-X-00012", 1.0)

    _make_jewelry(db, "SP-0001", "戒指")
    _make_bom(db, "SP-0001", "PJ-X-00010", 1.0)  # 1 composite per unit
    _make_order(db, "OR-0001", [("SP-0001", 5)])  # 5 units

    result = get_picking_simulation(db, "OR-0001")
    part_ids = [r.part_id for r in result.rows]
    assert "PJ-X-00010" not in part_ids  # composite itself absent
    assert "PJ-X-00011" in part_ids
    assert "PJ-X-00012" in part_ids

    row_a = next(r for r in result.rows if r.part_id == "PJ-X-00011")
    assert row_a.is_composite_child is True
    # Each unit → 1 composite → 2 焊接片. 5 units → 10 焊接片.
    # qty_per_unit at leaf = jewelry.qty_per_unit × composite_qty_per_unit = 1 × 2 = 2
    assert len(row_a.variants) == 1
    v = row_a.variants[0]
    assert v.qty_per_unit == 2.0
    assert v.units_count == 5
    assert v.subtotal == 10.0


def test_picking_simulation_nested_composite(db):
    """Composite A → composite B → atom C. Output contains only C with
    is_composite_child=True."""
    from services.picking import get_picking_simulation

    _make_part(db, "PJ-X-00020", "外组合 A", is_composite=True)
    _make_part(db, "PJ-X-00021", "内组合 B", is_composite=True)
    _make_part(db, "PJ-X-00022", "原子 C")
    _make_part_bom(db, "PJ-X-00020", "PJ-X-00021", 2.0)
    _make_part_bom(db, "PJ-X-00021", "PJ-X-00022", 3.0)

    _make_jewelry(db, "SP-0001", "J")
    _make_bom(db, "SP-0001", "PJ-X-00020", 1.0)
    _make_order(db, "OR-0001", [("SP-0001", 4)])

    result = get_picking_simulation(db, "OR-0001")
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.part_id == "PJ-X-00022"
    assert row.is_composite_child is True
    # 1 A = 2 B = 6 C per jewelry unit. qty_per_unit=6, units=4, subtotal=24.
    v = row.variants[0]
    assert v.qty_per_unit == 6.0
    assert v.units_count == 4
    assert v.subtotal == 24.0


def test_picking_simulation_atom_appears_both_direct_and_via_composite(db):
    """An atom used both directly in a jewelry BOM and indirectly via a
    composite → single row; is_composite_child=True (because at least one
    occurrence came from composite expansion)."""
    from services.picking import get_picking_simulation

    # Composite "支架" expands to atom "螺丝" × 2.
    _make_part(db, "PJ-X-00030", "支架", is_composite=True)
    _make_part(db, "PJ-X-00031", "螺丝")
    _make_part_bom(db, "PJ-X-00030", "PJ-X-00031", 2.0)

    # Jewelry uses BOTH the composite (1 per unit) AND the atom directly (1 per unit).
    _make_jewelry(db, "SP-0001", "J")
    _make_bom(db, "SP-0001", "PJ-X-00030", 1.0)  # via composite → 螺丝 × 2
    _make_bom(db, "SP-0001", "PJ-X-00031", 1.0)  # direct → 螺丝 × 1
    _make_order(db, "OR-0001", [("SP-0001", 10)])

    result = get_picking_simulation(db, "OR-0001")
    row = next(r for r in result.rows if r.part_id == "PJ-X-00031")
    assert row.is_composite_child is True  # set because of the composite path
    # Two variants expected: qty_per_unit 1.0 (direct) and qty_per_unit 2.0 (via composite).
    qtys = sorted(v.qty_per_unit for v in row.variants)
    assert qtys == [1.0, 2.0]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_service_picking.py -v -k composite`
Expected: FAIL — composite parts currently propagate as-is (qty_per_unit 1.0 of the composite appears in output, and atomic children don't).

- [ ] **Step 4: Add `_expand_to_atoms` helper and wire into `_collect_triples`**

In `services/picking.py`, **add** the following helper (above `_collect_triples`):

```python
def _expand_to_atoms(
    db: Session,
    composite_part_id: str,
    multiplier: float,
    _ancestors: frozenset[str] = frozenset(),
) -> list[tuple[str, float]]:
    """Recursively walk a composite part's BOM. Return a list of
    (atom_part_id, effective_qty_per_unit) tuples for every non-composite
    descendant. `multiplier` is the running product of qty_per_unit along
    the path from the jewelry BOM root.

    Uses `services.part_bom.get_part_bom()` just like
    `services.cutting_stats._expand_composite_part` does, but does NOT
    filter by name pattern — we want ALL atoms. _ancestors guards against
    cycles, matching the existing helper's semantics."""
    from services.part_bom import get_part_bom

    if composite_part_id in _ancestors:
        return []
    path = _ancestors | {composite_part_id}

    children = get_part_bom(db, composite_part_id)
    out: list[tuple[str, float]] = []
    for child in children:
        child_id = child["child_part_id"]
        child_qty = multiplier * float(child["qty_per_unit"])
        if child.get("child_is_composite"):
            out.extend(_expand_to_atoms(db, child_id, child_qty, path))
        else:
            out.append((child_id, child_qty))
    return out
```

**Replace** the body of `_collect_triples` with the composite-aware version:

```python
def _collect_triples(db: Session, order_items: list[OrderItem]) -> list[dict]:
    """Return list of {part_id, qty_per_unit, units_count, from_composite}.

    Composite parts in a jewelry's BOM are expanded to their atomic descendants
    via _expand_to_atoms(). The composite itself never appears in the output;
    each atomic descendant inherits from_composite=True."""
    jewelry_ids = list({oi.jewelry_id for oi in order_items})
    boms = db.query(Bom).filter(Bom.jewelry_id.in_(jewelry_ids)).all()
    bom_by_jewelry: dict[str, list[Bom]] = defaultdict(list)
    for b in boms:
        bom_by_jewelry[b.jewelry_id].append(b)

    # Batch-load part.is_composite for every part that appears directly in
    # any BOM row. (Composite descendants are discovered via _expand_to_atoms.)
    direct_part_ids = list({b.part_id for bs in bom_by_jewelry.values() for b in bs})
    direct_parts = db.query(Part).filter(Part.id.in_(direct_part_ids)).all() if direct_part_ids else []
    is_composite = {p.id: p.is_composite for p in direct_parts}

    out: list[dict] = []
    for oi in order_items:
        for b in bom_by_jewelry.get(oi.jewelry_id, []):
            qpu_root = float(b.qty_per_unit)
            if is_composite.get(b.part_id):
                # Expand: each atom contributes qty_per_unit = qpu_root × child_qty.
                atoms = _expand_to_atoms(db, b.part_id, qpu_root)
                for atom_id, atom_qpu in atoms:
                    out.append({
                        "part_id": atom_id,
                        "qty_per_unit": atom_qpu,
                        "units_count": oi.quantity,
                        "from_composite": True,
                    })
            else:
                out.append({
                    "part_id": b.part_id,
                    "qty_per_unit": qpu_root,
                    "units_count": oi.quantity,
                    "from_composite": False,
                })
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_service_picking.py -v`
Expected: PASS (all prior + 3 new composite tests)

- [ ] **Step 6: Commit**

```bash
git add services/picking.py tests/test_service_picking.py
git commit -m "feat(picking): expand composite parts to atomic descendants

Uses services.part_bom.get_part_bom() recursively (same data source as
services.cutting_stats._expand_composite_part) but returns every atom,
not just cm-pattern rows. Composite parts never appear in picking rows;
their atomic descendants inherit is_composite_child=True."
```

---

## Task 5: Aggregation service — current_stock and picked state

Attaches `current_stock` (via inventory_log SUM) and joins `picked` state
from `order_picking_record`.

**Files:**
- Modify: `services/picking.py`
- Test: `tests/test_service_picking.py`

- [ ] **Step 1: Look up the existing stock query pattern**

Run: `rg -n "change_qty" services/ --type py -l`

Open the first matching service and find the idiom used to compute current
stock from `inventory_log`. We will reuse the same aggregation pattern for
consistency. Typical form:

```python
from sqlalchemy import func
from models.inventory_log import InventoryLog

stock = (
    db.query(InventoryLog.item_id, func.coalesce(func.sum(InventoryLog.change_qty), 0))
    .filter(InventoryLog.item_type == "part", InventoryLog.item_id.in_(part_ids))
    .group_by(InventoryLog.item_id)
    .all()
)
```

(The exact `item_type` value for parts — likely `"part"` — should match what
`services/order.py::get_parts_summary()` uses. Check that file and copy the
value.)

- [ ] **Step 2: Write failing stock + picked tests**

Append to `tests/test_service_picking.py`:

```python
# --- Aggregation: stock and picked state ---


def _add_stock(db, part_id: str, qty: float, reason: str = "入库"):
    from models.inventory_log import InventoryLog
    from decimal import Decimal
    db.add(InventoryLog(
        item_type="part", item_id=part_id,
        change_qty=Decimal(str(qty)), reason=reason,
    ))
    db.flush()


def test_picking_simulation_current_stock(db):
    """current_stock is computed from inventory_log SUM for each part."""
    from services.picking import get_picking_simulation

    _make_part(db, "PJ-X-00001", "珠子")
    _make_jewelry(db, "SP-0001", "J")
    _make_bom(db, "SP-0001", "PJ-X-00001", 1.0)
    _make_order(db, "OR-0001", [("SP-0001", 3)])

    _add_stock(db, "PJ-X-00001", 20.0)
    _add_stock(db, "PJ-X-00001", -5.0, reason="出库")

    result = get_picking_simulation(db, "OR-0001")
    assert result.rows[0].current_stock == 15.0


def test_picking_simulation_no_stock_is_zero(db):
    """Part with no inventory_log entries → current_stock = 0."""
    from services.picking import get_picking_simulation

    _make_part(db, "PJ-X-00001", "珠子")
    _make_jewelry(db, "SP-0001", "J")
    _make_bom(db, "SP-0001", "PJ-X-00001", 1.0)
    _make_order(db, "OR-0001", [("SP-0001", 1)])

    result = get_picking_simulation(db, "OR-0001")
    assert result.rows[0].current_stock == 0.0


def test_picking_simulation_picked_state_reflected(db):
    """An OrderPickingRecord sets the matching variant's picked=True and
    bumps progress.picked."""
    from services.picking import get_picking_simulation
    from models.order import OrderPickingRecord
    from decimal import Decimal

    _make_part(db, "PJ-X-00001", "珠子")
    _make_jewelry(db, "SP-0001", "A")
    _make_jewelry(db, "SP-0002", "B")
    _make_bom(db, "SP-0001", "PJ-X-00001", 2.0)
    _make_bom(db, "SP-0002", "PJ-X-00001", 3.0)
    _make_order(db, "OR-0001", [("SP-0001", 10), ("SP-0002", 5)])

    # Mark only the qty=2 variant.
    db.add(OrderPickingRecord(
        order_id="OR-0001", part_id="PJ-X-00001",
        qty_per_unit=Decimal("2.0"),
    ))
    db.flush()

    result = get_picking_simulation(db, "OR-0001")
    row = result.rows[0]
    picked = {v.qty_per_unit: v.picked for v in row.variants}
    assert picked[2.0] is True
    assert picked[3.0] is False
    assert result.progress.total == 2
    assert result.progress.picked == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_service_picking.py -v -k "stock or picked_state"`
Expected: FAIL — current_stock always 0; picked always False.

- [ ] **Step 4: Wire stock and picked into `_build_rows`**

At the top of `services/picking.py`, add imports:

```python
from sqlalchemy import func

from models.inventory_log import InventoryLog
```

Modify `get_picking_simulation` to pass `order_id` down to `_build_rows` (we
need it to query picking records scoped to this order). Replace the existing
call `rows = _build_rows(db, triples)` with `rows = _build_rows(db, triples, order.id)`.

Replace the body of `_build_rows` with:

```python
def _build_rows(db: Session, triples: list[dict], order_id: str) -> list[PickingPartRow]:
    """Group triples by (part_id, qty_per_unit) → variants, then by part_id.
    Attach current_stock (from inventory_log) and picked (from
    order_picking_record)."""
    if not triples:
        return []

    grouped: dict[tuple[str, float], dict] = {}
    for t in triples:
        key = (t["part_id"], t["qty_per_unit"])
        entry = grouped.get(key)
        if entry is None:
            grouped[key] = {"units_count": 0, "from_composite": False}
            entry = grouped[key]
        entry["units_count"] += t["units_count"]
        if t["from_composite"]:
            entry["from_composite"] = True

    part_ids = sorted({k[0] for k in grouped.keys()})
    parts = db.query(Part).filter(Part.id.in_(part_ids)).all()
    part_by_id = {p.id: p for p in parts}

    # Batch-load current_stock per part.
    stock_rows = (
        db.query(InventoryLog.item_id,
                 func.coalesce(func.sum(InventoryLog.change_qty), 0))
        .filter(InventoryLog.item_type == "part",
                InventoryLog.item_id.in_(part_ids))
        .group_by(InventoryLog.item_id)
        .all()
    )
    stock_by_part: dict[str, float] = {pid: float(q) for pid, q in stock_rows}

    # Batch-load picked records for this order, keyed by (part_id, qty_per_unit).
    picked_records = (
        db.query(OrderPickingRecord)
        .filter(OrderPickingRecord.order_id == order_id,
                OrderPickingRecord.part_id.in_(part_ids))
        .all()
    )
    picked_keys = {(r.part_id, float(r.qty_per_unit)) for r in picked_records}

    variants_by_part: dict[str, list[PickingVariant]] = defaultdict(list)
    composite_flag: dict[str, bool] = defaultdict(bool)
    for (pid, qpu), entry in grouped.items():
        units = entry["units_count"]
        variants_by_part[pid].append(
            PickingVariant(
                qty_per_unit=qpu,
                units_count=units,
                subtotal=qpu * units,
                picked=(pid, qpu) in picked_keys,
            )
        )
        if entry["from_composite"]:
            composite_flag[pid] = True

    rows: list[PickingPartRow] = []
    for pid in part_ids:
        part = part_by_id.get(pid)
        if part is None:
            continue
        variants = sorted(variants_by_part[pid], key=lambda v: v.qty_per_unit)
        total_required = sum(v.subtotal for v in variants)
        rows.append(
            PickingPartRow(
                part_id=pid,
                part_name=part.name,
                part_image=part.image,
                current_stock=stock_by_part.get(pid, 0.0),
                is_composite_child=composite_flag[pid],
                variants=variants,
                total_required=total_required,
            )
        )
    return rows
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_service_picking.py -v`
Expected: PASS (all prior + 3 new)

- [ ] **Step 6: Commit**

```bash
git add services/picking.py tests/test_service_picking.py
git commit -m "feat(picking): attach current_stock and picked state

current_stock computed from SUM(inventory_log.change_qty) matching the
project's no-stock-column pattern. Variant picked flag joined from
order_picking_record. Progress counts reflect actual picked variants."
```

---

## Task 6: State mutation services — mark / unmark / reset

**Files:**
- Modify: `services/picking.py`
- Test: `tests/test_service_picking.py`

- [ ] **Step 1: Write failing state-mutation tests**

Append to `tests/test_service_picking.py`:

```python
# --- State mutations: mark / unmark / reset ---


def _setup_single_variant_order(db):
    """Common setup: order with one part/one variant."""
    _make_part(db, "PJ-X-00001", "珠子")
    _make_jewelry(db, "SP-0001", "J")
    _make_bom(db, "SP-0001", "PJ-X-00001", 2.0)
    _make_order(db, "OR-0001", [("SP-0001", 3)])


def test_mark_picked_creates_record(db):
    from services.picking import mark_picked, get_picking_simulation
    _setup_single_variant_order(db)

    result = mark_picked(db, "OR-0001", "PJ-X-00001", 2.0)
    assert result.picked is True
    assert result.picked_at is not None

    sim = get_picking_simulation(db, "OR-0001")
    assert sim.rows[0].variants[0].picked is True


def test_mark_picked_idempotent(db):
    """Calling mark_picked twice is a no-op on the second call."""
    from services.picking import mark_picked
    from models.order import OrderPickingRecord
    _setup_single_variant_order(db)

    mark_picked(db, "OR-0001", "PJ-X-00001", 2.0)
    mark_picked(db, "OR-0001", "PJ-X-00001", 2.0)  # second call must not raise

    count = db.query(OrderPickingRecord).filter_by(order_id="OR-0001").count()
    assert count == 1


def test_mark_picked_rejects_unknown_variant(db):
    """Variant not in the order's aggregation → ValueError."""
    from services.picking import mark_picked
    import pytest
    _setup_single_variant_order(db)

    with pytest.raises(ValueError, match="配货范围"):
        mark_picked(db, "OR-0001", "PJ-X-00001", 999.0)  # wrong qty_per_unit
    with pytest.raises(ValueError, match="配货范围"):
        mark_picked(db, "OR-0001", "PJ-NOPE", 2.0)        # wrong part_id


def test_mark_picked_order_not_found(db):
    from services.picking import mark_picked
    import pytest
    with pytest.raises(ValueError, match="OR-NOPE"):
        mark_picked(db, "OR-NOPE", "PJ-X-00001", 2.0)


def test_unmark_picked_removes_record(db):
    from services.picking import mark_picked, unmark_picked
    from models.order import OrderPickingRecord
    _setup_single_variant_order(db)

    mark_picked(db, "OR-0001", "PJ-X-00001", 2.0)
    result = unmark_picked(db, "OR-0001", "PJ-X-00001", 2.0)
    assert result.picked is False

    count = db.query(OrderPickingRecord).filter_by(order_id="OR-0001").count()
    assert count == 0


def test_unmark_picked_idempotent(db):
    """Unmark when no record exists is silent."""
    from services.picking import unmark_picked
    _setup_single_variant_order(db)

    result = unmark_picked(db, "OR-0001", "PJ-X-00001", 2.0)
    assert result.picked is False  # not raised


def test_reset_picking_clears_all(db):
    from services.picking import mark_picked, reset_picking, get_picking_simulation
    _make_part(db, "PJ-X-00001", "A")
    _make_part(db, "PJ-X-00002", "B")
    _make_jewelry(db, "SP-0001", "J")
    _make_bom(db, "SP-0001", "PJ-X-00001", 1.0)
    _make_bom(db, "SP-0001", "PJ-X-00002", 1.0)
    _make_order(db, "OR-0001", [("SP-0001", 5)])

    mark_picked(db, "OR-0001", "PJ-X-00001", 1.0)
    mark_picked(db, "OR-0001", "PJ-X-00002", 1.0)

    deleted = reset_picking(db, "OR-0001")
    assert deleted == 2

    sim = get_picking_simulation(db, "OR-0001")
    assert all(not v.picked for r in sim.rows for v in r.variants)


def test_reset_picking_unknown_order(db):
    from services.picking import reset_picking
    import pytest
    with pytest.raises(ValueError, match="OR-NOPE"):
        reset_picking(db, "OR-NOPE")


def test_reset_picking_no_records_returns_zero(db):
    from services.picking import reset_picking
    _setup_single_variant_order(db)
    assert reset_picking(db, "OR-0001") == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_service_picking.py -v -k "mark_picked or unmark or reset"`
Expected: FAIL — functions don't exist yet.

- [ ] **Step 3: Add the mutation functions to `services/picking.py`**

Add a small Pydantic-ish return type and the three functions at the end of `services/picking.py`:

```python
# --- State mutations ---


from dataclasses import dataclass
from datetime import datetime


@dataclass
class PickingMarkResult:
    picked: bool
    picked_at: Optional[datetime] = None


def _validate_variant_in_order(
    db: Session, order_id: str, part_id: str, qty_per_unit: float
) -> None:
    """Raise ValueError unless (part_id, qty_per_unit) is a real variant of
    the picking simulation for this order."""
    sim = get_picking_simulation(db, order_id)  # raises if order missing
    valid_keys = {
        (r.part_id, v.qty_per_unit)
        for r in sim.rows for v in r.variants
    }
    if (part_id, qty_per_unit) not in valid_keys:
        raise ValueError("该配件/变体不在此订单配货范围内")


def mark_picked(
    db: Session, order_id: str, part_id: str, qty_per_unit: float
) -> PickingMarkResult:
    """Mark a variant as picked. Idempotent — calling twice produces one row."""
    _validate_variant_in_order(db, order_id, part_id, qty_per_unit)

    existing = (
        db.query(OrderPickingRecord)
        .filter_by(order_id=order_id, part_id=part_id,
                   qty_per_unit=Decimal(str(qty_per_unit)))
        .one_or_none()
    )
    if existing is not None:
        return PickingMarkResult(picked=True, picked_at=existing.picked_at)

    rec = OrderPickingRecord(
        order_id=order_id,
        part_id=part_id,
        qty_per_unit=Decimal(str(qty_per_unit)),
    )
    db.add(rec)
    db.flush()
    return PickingMarkResult(picked=True, picked_at=rec.picked_at)


def unmark_picked(
    db: Session, order_id: str, part_id: str, qty_per_unit: float
) -> PickingMarkResult:
    """Unmark a variant. Idempotent — unmarking a non-existent record is silent."""
    _validate_variant_in_order(db, order_id, part_id, qty_per_unit)

    (
        db.query(OrderPickingRecord)
        .filter_by(order_id=order_id, part_id=part_id,
                   qty_per_unit=Decimal(str(qty_per_unit)))
        .delete(synchronize_session=False)
    )
    db.flush()
    return PickingMarkResult(picked=False)


def reset_picking(db: Session, order_id: str) -> int:
    """Delete all picking records for the order. Returns the delete count.
    Raises ValueError if the order does not exist."""
    order = db.query(Order).filter_by(id=order_id).one_or_none()
    if order is None:
        raise ValueError(f"订单 {order_id} 不存在")

    deleted = (
        db.query(OrderPickingRecord)
        .filter_by(order_id=order_id)
        .delete(synchronize_session=False)
    )
    db.flush()
    return deleted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_service_picking.py -v`
Expected: PASS (all prior + 9 new)

- [ ] **Step 5: Commit**

```bash
git add services/picking.py tests/test_service_picking.py
git commit -m "feat(picking): mark/unmark/reset services with validation and idempotency

mark_picked and unmark_picked validate that (part_id, qty_per_unit) is a
variant in the order's current aggregation before mutating. Both are
idempotent. reset_picking returns the delete count."
```

---

## Task 7: API — GET /picking endpoint

**Files:**
- Modify: `api/orders.py`
- Create: `tests/test_api_picking.py`

- [ ] **Step 1: Create the test file with GET happy path + 404**

Create `tests/test_api_picking.py`:

```python
"""API tests for /api/orders/{id}/picking/... endpoints."""

from decimal import Decimal

from models.bom import Bom
from models.jewelry import Jewelry
from models.order import Order, OrderItem, OrderPickingRecord
from models.part import Part


def _setup(db):
    """Minimal fixture: 1 order, 1 jewelry, 1 part."""
    db.add(Part(id="PJ-X-00001", name="珠子", category="吊坠"))
    db.add(Jewelry(id="SP-0001", name="J", category="戒指"))
    db.flush()
    db.add(Bom(jewelry_id="SP-0001", part_id="PJ-X-00001",
               qty_per_unit=Decimal("2.0")))
    db.add(Order(id="OR-TEST-1", customer_name="张三"))
    db.flush()
    db.add(OrderItem(order_id="OR-TEST-1", jewelry_id="SP-0001",
                     quantity=5, unit_price=Decimal("1.0")))
    db.flush()


def test_get_picking_returns_aggregated_structure(client, db):
    _setup(db)
    resp = client.get("/api/orders/OR-TEST-1/picking")
    assert resp.status_code == 200
    body = resp.json()
    assert body["order_id"] == "OR-TEST-1"
    assert body["customer_name"] == "张三"
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["part_id"] == "PJ-X-00001"
    assert row["variants"][0]["qty_per_unit"] == 2.0
    assert row["variants"][0]["subtotal"] == 10.0
    assert body["progress"] == {"total": 1, "picked": 0}


def test_get_picking_order_not_found(client, db):
    resp = client.get("/api/orders/OR-NOPE/picking")
    assert resp.status_code == 400  # bubbles as ValueError → 400 via service_errors
    assert "OR-NOPE" in resp.json()["detail"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_picking.py -v`
Expected: FAIL with 404 (route not defined).

- [ ] **Step 3: Add GET handler to `api/orders.py`**

Near the top of `api/orders.py`, add to the existing `schemas.order` import block:

```python
from schemas.order import (
    OrderCreate, OrderResponse, OrderItemResponse, StatusUpdate,
    OrderTodoItemResponse, LinkCreateRequest, LinkResponse,
    BatchLinkRequest, BatchLinkResponse, OrderProgressResponse,
    OrderItemUpdate, BatchCustomerCodeRequest, PartsSummaryItemResponse,
    PickingSimulationResponse, PickingMarkRequest, PickingPdfRequest,
)
```

Add to the `services.picking` import block (create new):

```python
from services.picking import (
    get_picking_simulation, mark_picked, unmark_picked, reset_picking,
)
```

Append the new handler at the end of `api/orders.py`:

```python
# --- Picking simulation (配货模拟) ---


@router.get("/{order_id}/picking", response_model=PickingSimulationResponse)
def api_get_picking(order_id: str, db: Session = Depends(get_db)):
    """Aggregate order parts into a picking-oriented structure, join picked state."""
    with service_errors():
        return get_picking_simulation(db, order_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_picking.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add api/orders.py tests/test_api_picking.py
git commit -m "feat(picking): GET /orders/{id}/picking endpoint"
```

---

## Task 8: API — POST /mark, POST /unmark, DELETE /reset

**Files:**
- Modify: `api/orders.py`
- Modify: `tests/test_api_picking.py`

- [ ] **Step 1: Write failing tests for the three state endpoints**

Append to `tests/test_api_picking.py`:

```python
def test_post_mark_marks_variant(client, db):
    _setup(db)
    resp = client.post(
        "/api/orders/OR-TEST-1/picking/mark",
        json={"part_id": "PJ-X-00001", "qty_per_unit": 2.0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["picked"] is True
    assert body["picked_at"] is not None

    # Confirm it sticks on the next GET.
    g = client.get("/api/orders/OR-TEST-1/picking").json()
    assert g["rows"][0]["variants"][0]["picked"] is True
    assert g["progress"]["picked"] == 1


def test_post_mark_idempotent(client, db):
    _setup(db)
    for _ in range(3):
        r = client.post(
            "/api/orders/OR-TEST-1/picking/mark",
            json={"part_id": "PJ-X-00001", "qty_per_unit": 2.0},
        )
        assert r.status_code == 200
    count = db.query(OrderPickingRecord).filter_by(order_id="OR-TEST-1").count()
    assert count == 1


def test_post_mark_invalid_variant_rejected(client, db):
    _setup(db)
    resp = client.post(
        "/api/orders/OR-TEST-1/picking/mark",
        json={"part_id": "PJ-X-00001", "qty_per_unit": 999.0},  # wrong qty
    )
    assert resp.status_code == 400
    assert "配货范围" in resp.json()["detail"]


def test_post_unmark_removes_record(client, db):
    _setup(db)
    client.post(
        "/api/orders/OR-TEST-1/picking/mark",
        json={"part_id": "PJ-X-00001", "qty_per_unit": 2.0},
    )
    resp = client.post(
        "/api/orders/OR-TEST-1/picking/unmark",
        json={"part_id": "PJ-X-00001", "qty_per_unit": 2.0},
    )
    assert resp.status_code == 200
    assert resp.json()["picked"] is False

    g = client.get("/api/orders/OR-TEST-1/picking").json()
    assert g["rows"][0]["variants"][0]["picked"] is False


def test_post_unmark_idempotent(client, db):
    _setup(db)
    resp = client.post(
        "/api/orders/OR-TEST-1/picking/unmark",
        json={"part_id": "PJ-X-00001", "qty_per_unit": 2.0},
    )
    assert resp.status_code == 200  # no error when nothing to delete


def test_delete_reset_clears_all(client, db):
    _setup(db)
    # Add a second part and variant for realism.
    db.add(Part(id="PJ-X-00002", name="链扣", category="吊坠"))
    db.flush()
    db.add(Bom(jewelry_id="SP-0001", part_id="PJ-X-00002",
               qty_per_unit=Decimal("1.0")))
    db.flush()
    client.post("/api/orders/OR-TEST-1/picking/mark",
                json={"part_id": "PJ-X-00001", "qty_per_unit": 2.0})
    client.post("/api/orders/OR-TEST-1/picking/mark",
                json={"part_id": "PJ-X-00002", "qty_per_unit": 1.0})

    resp = client.delete("/api/orders/OR-TEST-1/picking/reset")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 2}

    count = db.query(OrderPickingRecord).filter_by(order_id="OR-TEST-1").count()
    assert count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_picking.py -v -k "mark or unmark or reset"`
Expected: FAIL — handlers not defined (404).

- [ ] **Step 3: Add the three handlers to `api/orders.py`**

Append after `api_get_picking`:

```python
@router.post("/{order_id}/picking/mark")
def api_picking_mark(
    order_id: str,
    body: PickingMarkRequest,
    db: Session = Depends(get_db),
):
    """Mark a variant as picked. Idempotent."""
    with service_errors():
        result = mark_picked(db, order_id, body.part_id, body.qty_per_unit)
    return {"picked": result.picked, "picked_at": result.picked_at}


@router.post("/{order_id}/picking/unmark")
def api_picking_unmark(
    order_id: str,
    body: PickingMarkRequest,
    db: Session = Depends(get_db),
):
    """Unmark a variant. Idempotent."""
    with service_errors():
        result = unmark_picked(db, order_id, body.part_id, body.qty_per_unit)
    return {"picked": result.picked}


@router.delete("/{order_id}/picking/reset")
def api_picking_reset(order_id: str, db: Session = Depends(get_db)):
    """Clear all picking records for this order."""
    with service_errors():
        deleted = reset_picking(db, order_id)
    return {"deleted": deleted}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_picking.py -v`
Expected: PASS (all tests incl. prior GET tests)

- [ ] **Step 5: Commit**

```bash
git add api/orders.py tests/test_api_picking.py
git commit -m "feat(picking): POST mark/unmark, DELETE reset endpoints

mark/unmark use POST (not DELETE with body) for proxy portability.
reset returns the deleted row count."
```

---

## Task 9: Extract shared PDF helpers

**Files:**
- Create: `services/_pdf_helpers.py`
- Modify: `services/parts_summary_pdf.py` (temporary — will be deleted in Task 13)
- Test: run existing `test_api_order_todo.py` parts-summary tests to confirm no regression

- [ ] **Step 1: Create `services/_pdf_helpers.py` with extracted utilities**

Create `services/_pdf_helpers.py`:

```python
"""Shared helpers for PDF generators that render part images."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from PIL import Image as PILImage, UnidentifiedImageError
from reportlab.lib.utils import ImageReader

from services.plating_export import download_pdf_image_bytes


def prefetch_images(image_urls) -> dict[str, bytes]:
    """Download the given image URLs concurrently, deduped. Returns {url: bytes}.
    Failed downloads map to empty bytes (caller renders as missing image)."""
    urls = {u for u in image_urls if u}
    if not urls:
        return {}
    cache: dict[str, bytes] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(urls))) as pool:
        for url, data in zip(urls, pool.map(_safe_download, urls)):
            cache[url] = data or b""
    return cache


def _safe_download(url: str) -> bytes | None:
    try:
        return download_pdf_image_bytes(url)
    except Exception:
        return None


def fit_image(image_bytes: bytes, max_w: float, max_h: float):
    """Return (ImageReader, draw_w, draw_h) that fits inside the box while
    preserving aspect ratio. Returns None if the image is invalid."""
    try:
        with PILImage.open(BytesIO(image_bytes)) as raw:
            raw.copy()
    except (UnidentifiedImageError, OSError):
        return None
    reader = ImageReader(BytesIO(image_bytes))
    img_w, img_h = reader.getSize()
    if img_w <= 0 or img_h <= 0:
        return None
    scale = min(max_w / img_w, max_h / img_h)
    return reader, max(1, img_w * scale), max(1, img_h * scale)
```

- [ ] **Step 2: Update `services/parts_summary_pdf.py` to use the shared helpers**

In `services/parts_summary_pdf.py`:

- At the top, remove these imports (they are now in the shared module):
  ```python
  from concurrent.futures import ThreadPoolExecutor
  from functools import lru_cache
  from PIL import Image as PILImage, UnidentifiedImageError
  from reportlab.lib.utils import ImageReader, simpleSplit
  ```
  …and keep `simpleSplit` since it's still used by `_centered_wrap`. So update to:
  ```python
  from functools import lru_cache
  from reportlab.lib.utils import simpleSplit
  ```
- Remove the private functions `_prefetch_images`, `_safe_download`, `_fit_image` (they've moved to `_pdf_helpers.py`).
- Add:
  ```python
  from services._pdf_helpers import prefetch_images, fit_image
  ```
- Replace the single call site `image_cache = _prefetch_images(rows)` with:
  ```python
  image_cache = prefetch_images(r.get("part_image") for r in rows)
  ```
- Replace `_fit_image(...)` inside `_draw_image_in_box` with `fit_image(...)`.
- Keep the `download_pdf_image_bytes` import removed if it isn't used anywhere
  else in the file (it isn't — only inside the moved `_safe_download`).

- [ ] **Step 3: Run the existing PDF tests to ensure no regression**

Run: `pytest tests/test_api_order_todo.py -v -k parts_summary`
Expected: PASS (all 6 existing parts-summary tests still green)

- [ ] **Step 4: Commit**

```bash
git add services/_pdf_helpers.py services/parts_summary_pdf.py
git commit -m "refactor(pdf): extract shared image helpers to services/_pdf_helpers.py

Moves prefetch_images and fit_image out of parts_summary_pdf.py so the
new picking_list_pdf.py (next commit) can reuse them. parts_summary_pdf
will be deleted in a later commit once the new PDF replaces it."
```

---

## Task 10: Build picking_list_pdf.py

**Files:**
- Create: `services/picking_list_pdf.py`
- Modify: `tests/test_api_picking.py`

- [ ] **Step 1: Write failing PDF generation test**

Append to `tests/test_api_picking.py`:

```python
# --- PDF generation ---


def test_build_picking_list_pdf_returns_bytes(db):
    from services.picking_list_pdf import build_picking_list_pdf
    _setup(db)
    file_bytes, filename = build_picking_list_pdf(db, "OR-TEST-1", "张三", include_picked=False)
    assert isinstance(file_bytes, bytes)
    assert file_bytes.startswith(b"%PDF")
    assert filename == "配货清单_OR-TEST-1.pdf"


def test_build_picking_list_pdf_empty_raises(db):
    """Order with no items (or all picked and include_picked=False) → ValueError."""
    from services.picking_list_pdf import build_picking_list_pdf
    import pytest
    db.add(Order(id="OR-EMPTY", customer_name="X"))
    db.flush()
    with pytest.raises(ValueError, match="没有需要配货"):
        build_picking_list_pdf(db, "OR-EMPTY", "X", include_picked=False)


def test_build_picking_list_pdf_filters_picked_by_default(db):
    """When include_picked=False (default), rows with all variants picked
    are omitted; partially picked rows keep only unpicked variants."""
    from services.picking_list_pdf import build_picking_list_pdf
    from services.picking import mark_picked
    _setup(db)
    mark_picked(db, "OR-TEST-1", "PJ-X-00001", 2.0)
    # Only variant → now fully picked → PDF should raise "nothing to pick".
    import pytest
    with pytest.raises(ValueError, match="没有需要配货"):
        build_picking_list_pdf(db, "OR-TEST-1", "张三", include_picked=False)


def test_build_picking_list_pdf_include_picked_flag(db):
    """include_picked=True renders picked rows too, so the PDF is non-empty."""
    from services.picking_list_pdf import build_picking_list_pdf
    from services.picking import mark_picked
    _setup(db)
    mark_picked(db, "OR-TEST-1", "PJ-X-00001", 2.0)
    file_bytes, _ = build_picking_list_pdf(db, "OR-TEST-1", "张三", include_picked=True)
    assert file_bytes.startswith(b"%PDF")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_picking.py -v -k "picking_list_pdf"`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Create `services/picking_list_pdf.py`**

Create `services/picking_list_pdf.py`:

```python
"""Generate a printable picking list PDF for 配货模拟.

Layout: A4, 45×45pt images, 7 columns (配件编号 / 配件 / 单份 / 份数 /
总数量 / 库存 / 完成). Part rows with multiple variants use ReportLab row
spans. By default, already-picked rows are filtered out — the PDF is a
to-do list."""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFont, stringWidth
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from schemas.order import PickingPartRow
from services._pdf_helpers import prefetch_images, fit_image
from services.picking import get_picking_simulation
from time_utils import now_beijing

_PAGE_WIDTH, _PAGE_HEIGHT = A4
_MARGIN_X = 40
_MARGIN_TOP = 36
_MARGIN_BOTTOM = 30
_CONTENT_WIDTH = _PAGE_WIDTH - _MARGIN_X * 2  # 515pt
_IMAGE_SIZE = 45
_ROW_MIN_H = 55
_VARIANT_ROW_H = 20  # inner row under a part when it has >1 variant
_HEADER_ROW_H = 24
_FONT = "STSong-Light"

# Column widths (7 columns), sum = 515pt
_COL_W = [55, 185, 45, 45, 60, 55, 70]
_HEADERS = ["配件编号", "配件", "单份", "份数", "总数量", "库存", "完成"]


@lru_cache(maxsize=1)
def _register_fonts() -> bool:
    registerFont(UnicodeCIDFont(_FONT))
    return True


def build_picking_list_pdf(
    db: Session,
    order_id: str,
    customer_name: str,
    include_picked: bool = False,
) -> tuple[bytes, str]:
    """Build the picking list PDF. Raises ValueError when there is nothing
    to pick (empty order, or all variants picked and include_picked=False)."""
    _register_fonts()

    sim = get_picking_simulation(db, order_id)
    rows = _filter_rows(sim.rows, include_picked=include_picked)
    if not rows:
        raise ValueError("没有需要配货的配件")

    image_cache = prefetch_images(r.part_image for r in rows)

    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    filename = f"配货清单_{order_id}.pdf"
    pdf.setTitle(filename)

    _render(pdf, rows, order_id, customer_name, image_cache)

    pdf.save()
    return buf.getvalue(), filename


def _filter_rows(
    rows: list[PickingPartRow], include_picked: bool
) -> list[PickingPartRow]:
    """When include_picked=False: drop variants that are picked; drop parts
    with no variants left."""
    if include_picked:
        return list(rows)

    out: list[PickingPartRow] = []
    for r in rows:
        remaining = [v for v in r.variants if not v.picked]
        if not remaining:
            continue
        out.append(
            PickingPartRow(
                part_id=r.part_id,
                part_name=r.part_name,
                part_image=r.part_image,
                current_stock=r.current_stock,
                is_composite_child=r.is_composite_child,
                variants=remaining,
                total_required=sum(v.subtotal for v in remaining),
            )
        )
    return out


def _render(pdf, rows, order_id, customer_name, image_cache):
    """Draw the title block, table header, and each part's row(s). Handles
    page breaks when the next part won't fit."""
    y = _PAGE_HEIGHT - _MARGIN_TOP
    y = _draw_title_block(pdf, y, order_id, customer_name, len(rows))
    y = _draw_table_header(pdf, y)

    for row in rows:
        needed = _row_height(row)
        if y - needed < _MARGIN_BOTTOM:
            pdf.showPage()
            y = _PAGE_HEIGHT - _MARGIN_TOP
            y = _draw_table_header(pdf, y)
        _draw_part_row(pdf, row, y, image_cache)
        y -= needed


def _row_height(row: PickingPartRow) -> float:
    n = len(row.variants)
    if n <= 1:
        return _ROW_MIN_H
    # First variant shares the image row; each extra variant adds a thin row.
    return _ROW_MIN_H + (n - 1) * _VARIANT_ROW_H


def _draw_title_block(pdf, y, order_id, customer_name, part_count) -> float:
    pdf.setFont(_FONT, 14)
    pdf.setFillColor(colors.black)
    title = f"配货清单 · 订单 {order_id}"
    pdf.drawString(_MARGIN_X, y - 12, title)
    pdf.setFont(_FONT, 9)
    date_str = now_beijing().strftime("%Y-%m-%d %H:%M")
    pdf.drawString(_MARGIN_X, y - 28,
                   f"客户: {customer_name or '-'}    生成时间: {date_str}    共 {part_count} 配件")
    return y - 40


def _draw_table_header(pdf, y) -> float:
    x = _MARGIN_X
    pdf.setStrokeColor(colors.black)
    pdf.setLineWidth(0.5)
    for w, hdr in zip(_COL_W, _HEADERS):
        pdf.setFillColor(colors.HexColor("#e8e8e8"))
        pdf.rect(x, y - _HEADER_ROW_H, w, _HEADER_ROW_H, stroke=1, fill=1)
        pdf.setFillColor(colors.black)
        pdf.setFont(_FONT, 9)
        tw = stringWidth(hdr, _FONT, 9)
        pdf.drawString(x + (w - tw) / 2, y - _HEADER_ROW_H + 8, hdr)
        x += w
    return y - _HEADER_ROW_H


def _draw_part_row(pdf, row: PickingPartRow, top_y: float, image_cache: dict[str, bytes]) -> None:
    """Draw a part spanning 1+ variant rows. part_id / part / stock / (first
    variant's completion box) sit in the top row; extra variants add thin
    rows with their own 单份/份数/总数 + empty 完成 box."""
    height = _row_height(row)
    x = _MARGIN_X

    # Draw the outer cell borders for the FIRST row of the part (spans full image).
    # For spanned columns (配件编号, 配件, 库存), draw as a single tall cell.
    col_xs = []
    cx = x
    for w in _COL_W:
        col_xs.append(cx)
        cx += w

    # Column 0 (配件编号), col 1 (配件), col 5 (库存) span the whole part height.
    for col_idx in (0, 1, 5):
        pdf.setStrokeColor(colors.black)
        pdf.setLineWidth(0.5)
        pdf.rect(col_xs[col_idx], top_y - height, _COL_W[col_idx], height,
                 stroke=1, fill=0)

    # For columns 2, 3, 4, 6 — each variant gets its own cell (variant slice).
    # First variant sits at the top of the part (height = _ROW_MIN_H); extra
    # variants sit below with _VARIANT_ROW_H each.
    variant_y = top_y
    for i, v in enumerate(row.variants):
        slice_h = _ROW_MIN_H if i == 0 else _VARIANT_ROW_H
        for col_idx in (2, 3, 4, 6):
            pdf.rect(col_xs[col_idx], variant_y - slice_h, _COL_W[col_idx],
                     slice_h, stroke=1, fill=0)
        _draw_variant_values(pdf, v, col_xs, variant_y, slice_h)
        variant_y -= slice_h

    # Fill the spanning columns' text + image.
    _draw_spanning_values(pdf, row, col_xs, top_y, height, image_cache)


def _draw_variant_values(pdf, v, col_xs, variant_top_y, h):
    """单份, 份数, 总数量, 完成(empty)."""
    pdf.setFillColor(colors.black)
    _centered(pdf, _fmt_qty(v.qty_per_unit), col_xs[2], variant_top_y - h,
              _COL_W[2], h, size=10)
    _centered(pdf, str(v.units_count), col_xs[3], variant_top_y - h,
              _COL_W[3], h, size=10)
    _centered(pdf, _fmt_qty(v.subtotal), col_xs[4], variant_top_y - h,
              _COL_W[4], h, size=10, bold=True)
    # Empty checkbox in the 完成 column.
    box_size = 12
    cx = col_xs[6] + (_COL_W[6] - box_size) / 2
    cy = variant_top_y - h + (h - box_size) / 2
    pdf.rect(cx, cy, box_size, box_size, stroke=1, fill=0)


def _draw_spanning_values(pdf, row, col_xs, top_y, height, image_cache):
    # 配件编号 (col 0)
    _centered(pdf, row.part_id, col_xs[0], top_y - height, _COL_W[0], height, size=9)
    # 配件 (col 1): image + name
    img_bytes = image_cache.get(row.part_image or "") if row.part_image else None
    _draw_image_in_cell(pdf, img_bytes, col_xs[1], top_y - height, _COL_W[1], height)
    _draw_name_in_cell(pdf, row, col_xs[1], top_y - height, _COL_W[1], height)
    # 库存 (col 5)
    _centered(pdf, _fmt_qty(row.current_stock), col_xs[5], top_y - height,
              _COL_W[5], height, size=10)


def _draw_image_in_cell(pdf, image_bytes, x, y, w, h):
    if not image_bytes:
        return
    placement = fit_image(image_bytes, _IMAGE_SIZE, _IMAGE_SIZE)
    if placement is None:
        return
    reader, draw_w, draw_h = placement
    # Place image on the left; name wraps on the right.
    offset_x = x + 4
    offset_y = y + (h - draw_h) / 2
    pdf.drawImage(reader, offset_x, offset_y, width=draw_w, height=draw_h,
                  preserveAspectRatio=True, mask="auto")


def _draw_name_in_cell(pdf, row, x, y, w, h):
    text_x = x + _IMAGE_SIZE + 10
    text_w = w - _IMAGE_SIZE - 14
    pdf.setFont(_FONT, 10)
    name = row.part_name
    if row.is_composite_child:
        name = f"{name} [组合]"
    lines = simpleSplit(name, _FONT, 10, max(text_w, 1))[:3]
    if not lines:
        return
    line_h = 13
    total_h = len(lines) * line_h
    cy = y + (h + total_h) / 2 - 10
    for line in lines:
        pdf.drawString(text_x, cy, line)
        cy -= line_h


def _centered(pdf, text, x, y, w, h, size=10, bold=False):
    pdf.setFont(_FONT, size)
    s = text or ""
    tw = stringWidth(s, _FONT, size)
    pdf.drawString(x + (w - tw) / 2, y + h / 2 - size / 2 + 1, s)


def _fmt_qty(v) -> str:
    if v is None:
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f == int(f):
        return str(int(f))
    return f"{f:g}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_picking.py -v -k "picking_list_pdf"`
Expected: PASS (all 4 new tests)

- [ ] **Step 5: Commit**

```bash
git add services/picking_list_pdf.py tests/test_api_picking.py
git commit -m "feat(picking): picking list PDF generator

A4 layout, 45×45pt images targeting ~12 rows per page in the
single-variant case. Row-spans for parts with multiple variants.
include_picked=False (default) filters out already-picked rows so the
PDF is a to-do list, not an audit trail."
```

---

## Task 11: API — POST /picking/pdf endpoint

**Files:**
- Modify: `api/orders.py`
- Modify: `tests/test_api_picking.py`

- [ ] **Step 1: Write failing PDF endpoint tests**

Append to `tests/test_api_picking.py`:

```python
def test_post_picking_pdf_returns_pdf(client, db):
    _setup(db)
    resp = client.post("/api/orders/OR-TEST-1/picking/pdf", json={})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    disp = resp.headers["content-disposition"]
    assert "配货清单_OR-TEST-1.pdf" in disp or "picking-list-OR-TEST-1.pdf" in disp


def test_post_picking_pdf_400_when_nothing_to_pick(client, db):
    db.add(Order(id="OR-EMPTY", customer_name="X"))
    db.flush()
    resp = client.post("/api/orders/OR-EMPTY/picking/pdf", json={})
    assert resp.status_code == 400
    assert "没有需要配货" in resp.json()["detail"]


def test_post_picking_pdf_include_picked_flag(client, db):
    _setup(db)
    client.post("/api/orders/OR-TEST-1/picking/mark",
                json={"part_id": "PJ-X-00001", "qty_per_unit": 2.0})
    # Default (include_picked=False) → 400 (everything picked).
    r1 = client.post("/api/orders/OR-TEST-1/picking/pdf", json={})
    assert r1.status_code == 400
    # include_picked=True → 200 PDF.
    r2 = client.post("/api/orders/OR-TEST-1/picking/pdf",
                     json={"include_picked": True})
    assert r2.status_code == 200
    assert r2.content.startswith(b"%PDF")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_picking.py -v -k "picking_pdf"`
Expected: FAIL — 404.

- [ ] **Step 3: Add PDF handler**

In `api/orders.py`, add to the top imports:

```python
from services.picking_list_pdf import build_picking_list_pdf
```

Append the handler:

```python
@router.post("/{order_id}/picking/pdf")
def api_picking_pdf(
    order_id: str,
    body: PickingPdfRequest,
    db: Session = Depends(get_db),
):
    """Export the picking list PDF. By default, only unpicked rows appear."""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        file_bytes, filename = build_picking_list_pdf(
            db, order_id, order.customer_name, include_picked=body.include_picked,
        )
    return Response(
        content=file_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="picking-list-{order_id}.pdf"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_picking.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add api/orders.py tests/test_api_picking.py
git commit -m "feat(picking): POST /orders/{id}/picking/pdf endpoint"
```

---

## Task 12: Frontend — API client functions

**Files:**
- Modify: `frontend/src/api/orders.js`

- [ ] **Step 1: Add new picking API functions and remove the old PDF helper**

Open `frontend/src/api/orders.js`.

Delete lines 33-38 (`downloadPartsSummaryPdf`):

```javascript
export const downloadPartsSummaryPdf = (orderId, partIds) =>
  api.post(
    `/orders/${orderId}/parts-summary/pdf`,
    { part_ids: partIds },
    { responseType: 'blob' },
  )
```

Append at the end of the file:

```javascript
// --- Picking Simulation (配货模拟) ---
export const getPicking = (orderId) => api.get(`/orders/${orderId}/picking`)
export const markPicked = (orderId, partId, qtyPerUnit) =>
  api.post(`/orders/${orderId}/picking/mark`, {
    part_id: partId,
    qty_per_unit: qtyPerUnit,
  })
export const unmarkPicked = (orderId, partId, qtyPerUnit) =>
  api.post(`/orders/${orderId}/picking/unmark`, {
    part_id: partId,
    qty_per_unit: qtyPerUnit,
  })
export const resetPicking = (orderId) =>
  api.delete(`/orders/${orderId}/picking/reset`)
export const downloadPickingListPdf = (orderId, includePicked = false) =>
  api.post(
    `/orders/${orderId}/picking/pdf`,
    { include_picked: includePicked },
    { responseType: 'blob' },
  )
```

- [ ] **Step 2: Smoke-check the frontend still builds**

Run from `frontend/`:
```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds. (There will be a reference error from `OrderDetail.vue` still importing `downloadPartsSummaryPdf`. Fix that in Task 14, OR temporarily `// @ts-expect-error` if needed. Since OrderDetail.vue is JS not TS, Vite may only warn or fail at runtime; build may still succeed. If build fails due to this import, proceed directly to Task 14 before committing.)

- [ ] **Step 3: Commit only if the build is clean OR fold into Task 14 if not**

If build passes cleanly:
```bash
git add frontend/src/api/orders.js
git commit -m "feat(picking): frontend API client functions"
```

Otherwise: skip committing here and include this change in Task 14's commit.

---

## Task 13: Frontend — PickingSimulationModal.vue component

**Files:**
- Create: `frontend/src/components/picking/PickingSimulationModal.vue`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/picking/PickingSimulationModal.vue`:

```vue
<script setup>
import { ref, computed, watch } from 'vue'
import {
  NModal, NCard, NButton, NCheckbox, NSwitch, NTag, NSpace, NPopconfirm,
  NSpin, useMessage,
} from 'naive-ui'
import {
  getPicking, markPicked, unmarkPicked, resetPicking, downloadPickingListPdf,
} from '@/api/orders'

const props = defineProps({
  show: { type: Boolean, required: true },
  orderId: { type: String, required: true },
})
const emit = defineEmits(['update:show'])

const message = useMessage()
const loading = ref(false)
const data = ref(null)
const onlyUnpicked = ref(false)
const exporting = ref(false)

const displayRows = computed(() => {
  if (!data.value) return []
  if (!onlyUnpicked.value) return data.value.rows
  return data.value.rows
    .map((r) => ({
      ...r,
      variants: r.variants.filter((v) => !v.picked),
    }))
    .filter((r) => r.variants.length > 0)
})

async function load() {
  loading.value = true
  try {
    const resp = await getPicking(props.orderId)
    data.value = resp.data
  } catch (err) {
    message.error(err.response?.data?.detail || '加载配货数据失败')
    emit('update:show', false)
  } finally {
    loading.value = false
  }
}

watch(() => props.show, (v) => {
  if (v) {
    data.value = null
    onlyUnpicked.value = false
    load()
  }
})

async function toggleVariant(row, variant) {
  const prev = variant.picked
  variant.picked = !prev
  data.value.progress.picked += variant.picked ? 1 : -1
  try {
    const fn = variant.picked ? markPicked : unmarkPicked
    await fn(props.orderId, row.part_id, variant.qty_per_unit)
  } catch (err) {
    // rollback
    variant.picked = prev
    data.value.progress.picked += prev ? 1 : -1
    message.error(err.response?.data?.detail || '操作失败')
  }
}

async function doReset() {
  try {
    await resetPicking(props.orderId)
    await load()
    message.success('已重置所有勾选')
  } catch (err) {
    message.error(err.response?.data?.detail || '重置失败')
  }
}

async function doExport() {
  exporting.value = true
  try {
    const resp = await downloadPickingListPdf(props.orderId, false)
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `配货清单_${props.orderId}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    // err.response.data is a Blob when responseType=blob — read it.
    let detail = '导出失败'
    if (err.response?.data instanceof Blob) {
      try {
        const text = await err.response.data.text()
        const parsed = JSON.parse(text)
        detail = parsed.detail || detail
      } catch {
        // fallthrough
      }
    } else {
      detail = err.response?.data?.detail || detail
    }
    message.error(detail)
  } finally {
    exporting.value = false
  }
}

function fmtQty(v) {
  if (v == null) return '-'
  const f = Number(v)
  if (Number.isNaN(f)) return String(v)
  if (f === Math.trunc(f)) return String(Math.trunc(f))
  return f.toString()
}
</script>

<template>
  <n-modal :show="show" @update:show="(v) => emit('update:show', v)"
           preset="card" style="width: 960px; max-width: 95vw"
           :title="`配货模拟 · 订单 ${orderId}`">
    <n-spin :show="loading">
      <div v-if="data">
        <div class="header-row">
          <div>
            客户：<b>{{ data.customer_name }}</b>
            <span class="progress">
              进度：{{ data.progress.picked }} / {{ data.progress.total }} 已完成
            </span>
          </div>
          <n-space>
            <span>
              只看未完成
              <n-switch v-model:value="onlyUnpicked" size="small" />
            </span>
            <n-button type="primary" :loading="exporting" @click="doExport">
              导出 PDF
            </n-button>
            <n-popconfirm @positive-click="doReset">
              <template #trigger>
                <n-button>重置勾选</n-button>
              </template>
              确认清空本订单的所有勾选记录？
            </n-popconfirm>
          </n-space>
        </div>

        <table class="picking-table">
          <thead>
            <tr>
              <th>配件编号</th>
              <th>配件</th>
              <th>单份</th>
              <th>份数</th>
              <th>需要总数量</th>
              <th>当前库存</th>
              <th>完成</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in displayRows" :key="row.part_id">
              <tr v-for="(v, vi) in row.variants"
                  :key="`${row.part_id}-${v.qty_per_unit}`"
                  :class="{ 'row-picked': v.picked, 'variant-inner': vi > 0 }">
                <td v-if="vi === 0" :rowspan="row.variants.length" class="merged">
                  {{ row.part_id }}
                </td>
                <td v-if="vi === 0" :rowspan="row.variants.length" class="merged">
                  <div class="part-cell">
                    <img v-if="row.part_image" :src="row.part_image" class="part-img" />
                    <div v-else class="part-img placeholder" />
                    <div class="part-name">
                      {{ row.part_name }}
                      <n-tag v-if="row.is_composite_child" size="small"
                             type="info" :bordered="false">
                        组合
                      </n-tag>
                    </div>
                  </div>
                </td>
                <td class="num">{{ fmtQty(v.qty_per_unit) }}</td>
                <td class="num">{{ v.units_count }}</td>
                <td class="num total">{{ fmtQty(v.subtotal) }}</td>
                <td v-if="vi === 0" :rowspan="row.variants.length" class="merged num">
                  {{ fmtQty(row.current_stock) }}
                </td>
                <td class="num">
                  <n-checkbox :checked="v.picked"
                              @update:checked="toggleVariant(row, v)" />
                </td>
              </tr>
            </template>
            <tr v-if="displayRows.length === 0">
              <td colspan="7" class="empty">没有数据</td>
            </tr>
          </tbody>
        </table>
      </div>
    </n-spin>
  </n-modal>
</template>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.progress {
  margin-left: 20px;
  color: #4361ee;
  font-weight: 500;
}
.picking-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.picking-table th,
.picking-table td {
  border: 1px solid #eee;
  padding: 8px;
  vertical-align: middle;
}
.picking-table thead th {
  background: #fafbfc;
  font-weight: 600;
}
.picking-table .merged {
  background: #fafbfc;
}
.picking-table .num {
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.picking-table .total {
  font-weight: 600;
}
.picking-table .variant-inner td:not(.merged) {
  border-top: 1px dashed #e5e5e5;
}
.picking-table .row-picked td:not(.merged) {
  opacity: 0.5;
  text-decoration: line-through;
}
.part-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.part-img {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 4px;
  flex-shrink: 0;
}
.part-img.placeholder {
  background: #f0f0f0;
}
.part-name {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.empty {
  text-align: center;
  color: #999;
  padding: 24px !important;
}
</style>
```

- [ ] **Step 2: Smoke-check the frontend build**

Run from `frontend/`:
```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds (the modal is not mounted anywhere yet, so it's
pure additive code and should compile).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/picking/PickingSimulationModal.vue
git commit -m "feat(picking): PickingSimulationModal.vue component

Modal table with rowspan for multi-variant parts, inline checkboxes
(optimistic update + rollback on failure), '只看未完成' filter, progress
indicator, reset popconfirm, and PDF export button. Matches the mockup
at frontend/mockup_picking_variants.html."
```

---

## Task 14: Frontend — wire button in OrderDetail.vue

**Files:**
- Modify: `frontend/src/views/orders/OrderDetail.vue`

- [ ] **Step 1: Replace button + mount modal**

Open `frontend/src/views/orders/OrderDetail.vue`.

a) Remove the old import. Find the import line for `downloadPartsSummaryPdf`
   (around the top) and remove it. If it's in a multi-import:

```javascript
// before
import { ..., downloadPartsSummaryPdf, ... } from '@/api/orders'

// after
import { ... } from '@/api/orders'
```

b) Add the modal import in the `<script setup>` block:

```javascript
import PickingSimulationModal from '@/components/picking/PickingSimulationModal.vue'
```

c) Add a ref for the modal's show state near the other refs:

```javascript
const pickingModalShow = ref(false)
```

d) Find `doPartsSummaryPdfExport()` (around line 955-975). Delete the entire
   function body. Replace call sites with:

```javascript
function openPickingSimulation() {
  pickingModalShow.value = true
}
```

e) In the template, find the `<n-button ...>导出 PDF</n-button>` in the
   配件汇总 card (around line 950-960). Replace the button's text and click
   handler:

```vue
<!-- before -->
<n-button @click="doPartsSummaryPdfExport" :loading="partsPdfLoading">
  导出 PDF
</n-button>

<!-- after -->
<n-button type="primary" @click="openPickingSimulation">
  配货模拟
</n-button>
```

f) Mount the modal near the end of the template (before the closing
   template root tag):

```vue
<PickingSimulationModal
  v-model:show="pickingModalShow"
  :order-id="orderId"
/>
```

Use whatever variable the page uses for the order id (`id`, `route.params.id`,
`orderId`, etc. — check the current file's pattern).

g) Remove any remaining `partsPdfLoading` ref and its usages if they exist
   — the old PDF flow is gone.

- [ ] **Step 2: Smoke-check build**

```bash
cd frontend && npm run build 2>&1 | tail -30
```

Expected: build succeeds.

- [ ] **Step 3: Manual smoke test**

Start the backend and frontend:

```bash
# Terminal 1
python main.py

# Terminal 2
cd frontend && npm run dev
```

1. Navigate to an existing order detail page.
2. Find the 配件汇总 card.
3. Click "配货模拟" → modal opens and shows aggregated parts.
4. Tick a checkbox → row greys out; refresh the modal → tick persists.
5. Toggle "只看未完成" → completed rows hide.
6. Click "导出 PDF" → file downloads; contains only unchecked variants.
7. Click "重置勾选" → all tick marks clear.
8. Close and re-open the modal → data is fresh.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/orders.js frontend/src/views/orders/OrderDetail.vue
git commit -m "feat(picking): wire 配货模拟 button into OrderDetail

Replaces the 配件汇总 card's 导出 PDF button with a new 配货模拟 button
that opens PickingSimulationModal. Old doPartsSummaryPdfExport() removed.

The old backend /parts-summary/pdf endpoint is still present but no
longer used; it is removed in the next commit."
```

---

## Task 15: Delete old parts_summary PDF code + tests

**Files:**
- Delete: `services/parts_summary_pdf.py`
- Modify: `api/orders.py` (remove endpoint + schema + imports)
- Modify: `tests/test_api_order_todo.py` (remove 6 obsolete tests)

- [ ] **Step 1: Delete the service file**

```bash
git rm services/parts_summary_pdf.py
```

- [ ] **Step 2: Remove the old endpoint and schema from `api/orders.py`**

In `api/orders.py`:

a) Delete the `PartsSummaryPdfRequest` class (around line 52-53):

```python
class PartsSummaryPdfRequest(_BaseModel):
    part_ids: list[str] = _Field(default_factory=list)
```

b) Delete the handler `api_download_parts_summary_pdf` and its route
   decorator (around lines 190-215):

```python
@router.post("/{order_id}/parts-summary/pdf")
def api_download_parts_summary_pdf(...):
    ...
```

c) Remove the import of `build_parts_summary_pdf`:

```python
from services.parts_summary_pdf import build_parts_summary_pdf
```

d) If `_BaseModel` / `_Field` are no longer referenced elsewhere in the
   file (there is still `PackagingCostUpdate` using `_BaseModel` — keep
   the import), leave the aliased imports as-is. Just verify:
   ```
   rg "_BaseModel|_Field" api/orders.py
   ```
   If only `PackagingCostUpdate` uses them, the import stays.

- [ ] **Step 3: Remove the 6 obsolete tests from `tests/test_api_order_todo.py`**

In `tests/test_api_order_todo.py`, delete lines ~1237-1342 — the entire
`# --- Parts Summary PDF Export ---` section and its 6 tests:

- `test_download_parts_summary_pdf_happy`
- `test_download_parts_summary_pdf_subset`
- `test_build_parts_summary_pdf_preserves_input_order`
- `test_download_parts_summary_pdf_empty_list_rejected`
- `test_download_parts_summary_pdf_all_ids_unmatched_rejected`
- `test_download_parts_summary_pdf_partial_mismatch_rejected`
- `test_download_parts_summary_pdf_order_not_found`

The section ends just before `# --- Bug fix: create_batch must reject
non-selectable jewelry ---`.

- [ ] **Step 4: Run the full test suite to confirm nothing else regressed**

```bash
pytest -q
```

Expected: PASS (everything; the deleted tests no longer exist and the new
picking tests cover the picking feature).

- [ ] **Step 5: Grep for any remaining dead references**

Run:
```bash
rg -n "parts_summary_pdf|parts-summary/pdf|PartsSummaryPdfRequest|downloadPartsSummaryPdf|build_parts_summary_pdf|doPartsSummaryPdfExport" --glob '!docs/**'
```

Expected output: empty (no matches outside the design spec).

If matches appear, trace each and delete.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(picking): delete old parts-summary PDF code

Removed in favor of the new 配货模拟 PDF:
- services/parts_summary_pdf.py (entire file)
- api/orders.py: PartsSummaryPdfRequest, api_download_parts_summary_pdf
- tests/test_api_order_todo.py: 6 tests for the removed endpoint

The old endpoint had no remaining callers after the frontend was switched
to the picking modal in the previous commit."
```

---

## Task 16: End-to-end verification

- [ ] **Step 1: Run the full test suite**

```bash
pytest -q
```

Expected: all green.

- [ ] **Step 2: Lint / format per project conventions**

Run whatever the project uses (project has no ruff/black config visible,
so skip unless a lint step surfaces in CI later).

- [ ] **Step 3: Build frontend in production mode**

```bash
cd frontend && npm run build
```

Expected: clean build with no warnings about the removed code.

- [ ] **Step 4: Manual end-to-end QA (see Task 14 Step 3 checklist)**

Re-run the smoke-test sequence from Task 14 Step 3 to confirm the
integrated feature behaves as designed.

- [ ] **Step 5: Final review before handing off**

- [ ] Spec coverage: walk through `docs/superpowers/specs/2026-04-16-picking-simulation-design.md` section by section and confirm every design decision is implemented.
- [ ] No leftover dead code (grep for old names per Task 15 Step 5).
- [ ] Git log is clean: each task = one commit with a descriptive message.

If everything passes, this feature is done. Tag the release or notify the
stakeholder.
