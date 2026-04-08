# 配件级 BOM（子装配件）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support part-level BOM (sub-assembly) so composite parts can be sent to handcraft workers for assembly. Handcraft orders support "send child parts, receive assembled parent part" with auto-consumption of child parts on receive.

**Architecture:** New `part_bom` table mirrors existing `bom` table. `HandcraftJewelryItem` (renamed to "output item") gains a `part_id` field. Handcraft receipt `_apply_receive` extended to handle part output with auto-consumption via `part_bom`.

**Tech Stack:** FastAPI, SQLAlchemy, Vue 3 + Naive UI

**Spec:** `docs/superpowers/specs/2026-04-08-part-sub-assembly-design.md`

---

## File Structure

| File | Changes |
|------|---------|
| `models/part_bom.py` | New model: PartBom |
| `models/__init__.py` | Import new model |
| `models/handcraft_order.py` | Add `part_id` to HandcraftJewelryItem |
| `database.py` | Schema compat for new table/column |
| `schemas/part_bom.py` | New schemas |
| `schemas/handcraft.py` | Update output item schemas |
| `services/part_bom.py` | New service: CRUD for part BOM |
| `services/handcraft.py` | Support part_id in output items |
| `services/handcraft_receipt.py` | Extend _apply_receive for part outputs |
| `services/cost_sync.py` | Add assembly_cost sync for part output receipts |
| `models/part.py` | Add `assembly_cost` field |
| `api/parts.py` | Add part BOM endpoints |
| `api/handcraft.py` | Adapt for output items |
| `frontend/src/api/parts.js` | Add part BOM API functions |
| `frontend/src/views/parts/PartDetail.vue` | Add sub-parts BOM section |
| `frontend/src/views/handcraft/HandcraftDetail.vue` | Rename to "产出明细", support parts |
| `tests/test_part_bom.py` | New test file |
| `tests/test_handcraft_item_crud.py` | Update for part output |

---

## Task 1: Model — PartBom Table

**Files:**
- Create: `models/part_bom.py`
- Modify: `models/__init__.py`

- [ ] **Step 1: Create PartBom model**

Create `models/part_bom.py`:

```python
from sqlalchemy import Column, String, Numeric, ForeignKey
from database import Base


class PartBom(Base):
    __tablename__ = "part_bom"

    id = Column(String, primary_key=True)
    parent_part_id = Column(String, ForeignKey("part.id"), nullable=False, index=True)
    child_part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty_per_unit = Column(Numeric(10, 4), nullable=False)
```

- [ ] **Step 2: Add import to models/__init__.py**

```python
from models.part_bom import PartBom
```

- [ ] **Step 3: Verify**

Run: `python -c "from models.part_bom import PartBom; print(PartBom.__tablename__)"`
Expected: `part_bom`

- [ ] **Step 4: Commit**

```bash
git add models/part_bom.py models/__init__.py
git commit -m "feat: add PartBom model for part sub-assembly"
```

---

## Task 2: Model — Add part_id to HandcraftJewelryItem + Schema Compat

**Files:**
- Modify: `models/handcraft_order.py` (HandcraftJewelryItem, line 50-61)
- Modify: `database.py`

- [ ] **Step 1: Add part_id column**

In `models/handcraft_order.py`, add to HandcraftJewelryItem after `jewelry_id`:

```python
    part_id = Column(String, ForeignKey("part.id"), nullable=True)
```

The existing `jewelry_id` should also become nullable:

```python
    jewelry_id = Column(String, ForeignKey("jewelry.id"), nullable=True)
```

Constraint: exactly one of `jewelry_id` or `part_id` must be non-null (enforced in service layer).

- [ ] **Step 2: Add schema compat**

In `database.py`, add to `ensure_schema_compat()`:

```python
# --- handcraft_jewelry_item.part_id ---
if inspector.has_table("handcraft_jewelry_item"):
    cols = [c["name"] for c in inspector.get_columns("handcraft_jewelry_item")]
    if "part_id" not in cols:
        conn.execute(text(
            "ALTER TABLE handcraft_jewelry_item ADD COLUMN part_id VARCHAR REFERENCES part(id)"
        ))
```

Also handle making `jewelry_id` nullable if needed:

```python
    # Make jewelry_id nullable (for part output items)
    # PostgreSQL: ALTER COLUMN ... DROP NOT NULL
    if "jewelry_id" in cols:
        conn.execute(text(
            "ALTER TABLE handcraft_jewelry_item ALTER COLUMN jewelry_id DROP NOT NULL"
        ))
```

- [ ] **Step 3: Verify**

Run: `python -c "from models.handcraft_order import HandcraftJewelryItem; print([c.name for c in HandcraftJewelryItem.__table__.columns])"`
Expected: includes `part_id`

- [ ] **Step 4: Commit**

```bash
git add models/handcraft_order.py database.py
git commit -m "feat: add part_id to HandcraftJewelryItem for part output"
```

---

## Task 3: Schemas — PartBom + Handcraft Output

**Files:**
- Create: `schemas/part_bom.py`
- Modify: `schemas/handcraft.py`

- [ ] **Step 1: Create part BOM schemas**

Create `schemas/part_bom.py`:

```python
from pydantic import BaseModel, ConfigDict


class PartBomSet(BaseModel):
    child_part_id: str
    qty_per_unit: float


class PartBomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_part_id: str
    child_part_id: str
    qty_per_unit: float
    child_part_name: str | None = None
    child_part_image: str | None = None
```

- [ ] **Step 2: Update handcraft schemas**

In `schemas/handcraft.py`, find the handcraft create schema's jewelry item definition and add `part_id`:

```python
# In the jewelry/output item create schema:
    jewelry_id: str | None = None
    part_id: str | None = None
```

Add validation: exactly one of `jewelry_id` or `part_id` must be set.

In the response schema for handcraft jewelry items, add:

```python
    part_id: str | None = None
    part_name: str | None = None
    part_image: str | None = None
```

- [ ] **Step 3: Verify imports**

Run: `python -c "from schemas.part_bom import PartBomSet, PartBomResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add schemas/part_bom.py schemas/handcraft.py
git commit -m "feat: add part BOM schemas, update handcraft output schemas"
```

---

## Task 4: Service — Part BOM CRUD

**Files:**
- Create: `services/part_bom.py`
- Create: `tests/test_part_bom.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_part_bom.py`:

```python
from models.part import Part


def _setup_parts(db):
    """Create parent part c and child parts e, f, g."""
    parent = Part(id="PJ-X-PARENT", name="组合配件C", category="小配件")
    children = [
        Part(id="PJ-X-CHILD-E", name="子配件E", category="小配件"),
        Part(id="PJ-X-CHILD-F", name="子配件F", category="小配件"),
        Part(id="PJ-X-CHILD-G", name="子配件G", category="小配件"),
    ]
    db.add(parent)
    db.add_all(children)
    db.flush()
    return parent, children


def test_set_part_bom(client, db):
    """Create part BOM entries."""
    parent, children = _setup_parts(db)
    for child in children:
        resp = client.post(
            f"/api/parts/{parent.id}/bom",
            json={"child_part_id": child.id, "qty_per_unit": 2.0},
        )
        assert resp.status_code == 200

    resp = client.get(f"/api/parts/{parent.id}/bom")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_update_part_bom_qty(client, db):
    """Update existing part BOM qty."""
    parent, children = _setup_parts(db)
    client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[0].id, "qty_per_unit": 2.0},
    )
    # Update qty
    resp = client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[0].id, "qty_per_unit": 5.0},
    )
    assert resp.status_code == 200
    bom_list = client.get(f"/api/parts/{parent.id}/bom").json()
    assert len(bom_list) == 1
    assert bom_list[0]["qty_per_unit"] == 5.0


def test_delete_part_bom(client, db):
    """Delete a part BOM entry."""
    parent, children = _setup_parts(db)
    resp = client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[0].id, "qty_per_unit": 2.0},
    )
    bom_id = resp.json()["id"]
    del_resp = client.delete(f"/api/parts/bom/{bom_id}")
    assert del_resp.status_code == 204

    bom_list = client.get(f"/api/parts/{parent.id}/bom").json()
    assert len(bom_list) == 0


def test_self_reference_rejected(client, db):
    """Cannot add a part as its own child."""
    parent, _ = _setup_parts(db)
    resp = client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": parent.id, "qty_per_unit": 1.0},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_part_bom.py -v`
Expected: FAIL

- [ ] **Step 3: Implement service**

Create `services/part_bom.py`:

```python
from sqlalchemy.orm import Session
from models.part_bom import PartBom
from models.part import Part
from services._helpers import _next_id


def set_part_bom(db: Session, parent_part_id: str, child_part_id: str, qty_per_unit: float) -> PartBom:
    if parent_part_id == child_part_id:
        raise ValueError("配件不能引用自身作为子配件")

    parent = db.query(Part).filter_by(id=parent_part_id).first()
    if not parent:
        raise ValueError(f"配件 {parent_part_id} 不存在")
    child = db.query(Part).filter_by(id=child_part_id).first()
    if not child:
        raise ValueError(f"配件 {child_part_id} 不存在")

    existing = (
        db.query(PartBom)
        .filter_by(parent_part_id=parent_part_id, child_part_id=child_part_id)
        .first()
    )
    if existing:
        existing.qty_per_unit = qty_per_unit
        db.flush()
        return existing

    bom = PartBom(
        id=_next_id(db, PartBom, "PB"),
        parent_part_id=parent_part_id,
        child_part_id=child_part_id,
        qty_per_unit=qty_per_unit,
    )
    db.add(bom)
    db.flush()
    return bom


def get_part_bom(db: Session, parent_part_id: str) -> list[dict]:
    rows = db.query(PartBom).filter_by(parent_part_id=parent_part_id).all()
    result = []
    for row in rows:
        child = db.query(Part).filter_by(id=row.child_part_id).first()
        result.append({
            "id": row.id,
            "parent_part_id": row.parent_part_id,
            "child_part_id": row.child_part_id,
            "qty_per_unit": float(row.qty_per_unit),
            "child_part_name": child.name if child else "",
            "child_part_image": child.image if child else None,
        })
    return result


def delete_part_bom_item(db: Session, bom_id: str) -> None:
    row = db.query(PartBom).filter_by(id=bom_id).first()
    if not row:
        raise ValueError(f"配件 BOM {bom_id} 不存在")
    db.delete(row)
    db.flush()


def calculate_child_parts_needed(db: Session, parent_part_id: str, qty: float) -> dict[str, float]:
    rows = db.query(PartBom).filter_by(parent_part_id=parent_part_id).all()
    return {row.child_part_id: float(row.qty_per_unit) * qty for row in rows}
```

- [ ] **Step 4: Add API endpoints**

In `api/parts.py`, add:

```python
from services.part_bom import set_part_bom, get_part_bom, delete_part_bom_item
from schemas.part_bom import PartBomSet

@router.get("/{part_id}/bom")
def api_get_part_bom(part_id: str, db: Session = Depends(get_db)):
    return get_part_bom(db, part_id)


@router.post("/{part_id}/bom")
def api_set_part_bom(part_id: str, body: PartBomSet, db: Session = Depends(get_db)):
    with service_errors():
        return set_part_bom(db, part_id, body.child_part_id, body.qty_per_unit)


@router.delete("/bom/{bom_id}", status_code=204)
def api_delete_part_bom(bom_id: str, db: Session = Depends(get_db)):
    with service_errors():
        delete_part_bom_item(db, bom_id)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_part_bom.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add services/part_bom.py api/parts.py tests/test_part_bom.py
git commit -m "feat: add part BOM CRUD service and API"
```

---

## Task 5: Service — Handcraft Output Item Support Part

**Files:**
- Modify: `services/handcraft.py`
- Modify: `services/handcraft_receipt.py`
- Test: `tests/test_handcraft_item_crud.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_handcraft_item_crud.py`:

```python
def test_create_handcraft_with_part_output(client, db):
    """Create handcraft order with a part as output item."""
    from models.part import Part
    parent = Part(id="PJ-X-OUT1", name="组合配件", category="小配件")
    child1 = Part(id="PJ-X-CH1", name="子配件1", category="小配件")
    child2 = Part(id="PJ-X-CH2", name="子配件2", category="小配件")
    db.add_all([parent, child1, child2])
    db.flush()

    from services.part_bom import set_part_bom
    set_part_bom(db, parent.id, child1.id, 2.0)
    set_part_bom(db, parent.id, child2.id, 3.0)
    db.flush()

    from services.inventory import add_stock
    add_stock(db, "part", child1.id, 100, "入库")
    add_stock(db, "part", child2.id, 100, "入库")
    db.flush()

    resp = client.post("/api/handcraft/", json={
        "supplier_name": "测试手工商",
        "parts": [
            {"part_id": child1.id, "qty": 20},
            {"part_id": child2.id, "qty": 30},
        ],
        "jewelries": [
            {"part_id": parent.id, "qty": 10},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()
    # Verify output item has part_id
    output_items = [i for i in data.get("jewelry_items", data.get("output_items", [])) if i.get("part_id")]
    assert len(output_items) == 1
    assert output_items[0]["part_id"] == parent.id


def test_receive_part_output_adds_stock_and_consumes(client, db):
    """Receiving a part output adds parent stock and auto-consumes child parts."""
    from models.part import Part
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
    from services.part_bom import set_part_bom
    from services.inventory import add_stock, get_stock

    parent = Part(id="PJ-X-RCV1", name="组合配件R", category="小配件")
    child1 = Part(id="PJ-X-RC1", name="子配件R1", category="小配件")
    child2 = Part(id="PJ-X-RC2", name="子配件R2", category="小配件")
    db.add_all([parent, child1, child2])
    db.flush()

    set_part_bom(db, parent.id, child1.id, 2.0)
    set_part_bom(db, parent.id, child2.id, 3.0)
    db.flush()

    # Create handcraft order manually
    hc = HandcraftOrder(id="HC-PARTOUT1", supplier_name="手工商", status="processing")
    db.add(hc)
    db.flush()

    hp1 = HandcraftPartItem(handcraft_order_id=hc.id, part_id=child1.id, qty=20, status="制作中")
    hp2 = HandcraftPartItem(handcraft_order_id=hc.id, part_id=child2.id, qty=30, status="制作中")
    hj = HandcraftJewelryItem(handcraft_order_id=hc.id, part_id=parent.id, qty=10, status="制作中")
    db.add_all([hp1, hp2, hj])
    db.flush()

    # Create receipt to receive parent part
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "手工商",
        "items": [{
            "handcraft_jewelry_item_id": hj.id,
            "qty": 10,
            "price": 5.0,
        }],
    })
    assert resp.status_code == 200

    # Verify parent stock increased
    assert get_stock(db, "part", parent.id) == 10

    # Verify child parts auto-consumed
    db.refresh(hp1)
    db.refresh(hp2)
    assert float(hp1.received_qty) == 20  # 10 * 2.0
    assert float(hp2.received_qty) == 30  # 10 * 3.0
    assert hp1.status == "已收回"
    assert hp2.status == "已收回"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handcraft_item_crud.py::test_create_handcraft_with_part_output tests/test_handcraft_item_crud.py::test_receive_part_output_adds_stock_and_consumes -v`
Expected: FAIL

- [ ] **Step 3: Update handcraft service to support part_id in output items**

In `services/handcraft.py`, modify `create_handcraft_order` to accept `part_id` in jewelry items:

```python
# In the jewelry items creation loop, support part_id:
for j_data in (jewelries or []):
    jewelry_id = j_data.get("jewelry_id")
    part_id = j_data.get("part_id")
    if not jewelry_id and not part_id:
        raise ValueError("产出项必须指定 jewelry_id 或 part_id")
    if jewelry_id and part_id:
        raise ValueError("产出项不能同时指定 jewelry_id 和 part_id")

    if jewelry_id:
        # existing validation for jewelry
        ...
    elif part_id:
        part = db.query(Part).filter_by(id=part_id).first()
        if not part:
            raise ValueError(f"配件 {part_id} 不存在")

    hj = HandcraftJewelryItem(
        handcraft_order_id=hc.id,
        jewelry_id=jewelry_id,
        part_id=part_id,
        qty=j_data["qty"],
        unit=j_data.get("unit", "套" if jewelry_id else "个"),
        note=j_data.get("note"),
    )
    db.add(hj)
```

- [ ] **Step 4: Update handcraft receipt to handle part output**

In `services/handcraft_receipt.py`, modify `_apply_receive` for the jewelry/output item branch:

```python
def _apply_receive(db, order_item, item_type, qty):
    order_item.received_qty = (order_item.received_qty or 0) + qty

    if item_type == "jewelry":
        if order_item.jewelry_id:
            # Existing: receive jewelry, add jewelry stock, auto-consume parts via bom
            add_stock(db, "jewelry", order_item.jewelry_id, qty, "手工收回")
            _auto_consume_parts(db, order_item.handcraft_order_id, order_item.jewelry_id, qty)
        elif order_item.part_id:
            # New: receive part output, add part stock, auto-consume child parts via part_bom
            add_stock(db, "part", order_item.part_id, qty, "手工收回")
            _auto_consume_child_parts(db, order_item.handcraft_order_id, order_item.part_id, qty)

    elif item_type == "part":
        add_stock(db, "part", order_item.part_id, qty, "手工收回")

    if float(order_item.received_qty) >= float(order_item.qty):
        order_item.status = "已收回"
    else:
        order_item.status = "制作中"
    db.flush()
```

Add `_auto_consume_child_parts` function (mirrors `_auto_consume_parts` but uses `part_bom`):

```python
def _auto_consume_child_parts(db: Session, handcraft_order_id: str, parent_part_id: str, parent_qty: float):
    """When a composite part is received, auto-consume child parts based on part_bom."""
    from models.part_bom import PartBom
    bom_rows = db.query(PartBom).filter_by(parent_part_id=parent_part_id).all()

    for bom in bom_rows:
        consume_qty = float(bom.qty_per_unit) * parent_qty
        # Distribute across HandcraftPartItem rows with matching child part_id
        part_items = (
            db.query(HandcraftPartItem)
            .filter_by(handcraft_order_id=handcraft_order_id, part_id=bom.child_part_id)
            .order_by(HandcraftPartItem.id)
            .all()
        )
        remaining = consume_qty
        for pi in part_items:
            if remaining <= 0:
                break
            capacity = float(pi.qty) - float(pi.received_qty or 0)
            if capacity <= 0:
                continue
            take = min(remaining, capacity)
            pi.received_qty = float(pi.received_qty or 0) + take
            if float(pi.received_qty) >= float(pi.qty):
                pi.status = "已收回"
            else:
                pi.status = "制作中"
            remaining -= take
        db.flush()
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_handcraft_item_crud.py::test_create_handcraft_with_part_output tests/test_handcraft_item_crud.py::test_receive_part_output_adds_stock_and_consumes -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add services/handcraft.py services/handcraft_receipt.py tests/test_handcraft_item_crud.py
git commit -m "feat: support part output in handcraft orders with auto-consume"
```

---

## Task 6: Backend — Assembly Cost + Auto Unit Cost Calculation

**Files:**
- Modify: `models/part.py` (add `assembly_cost` field)
- Modify: `database.py` (schema compat)
- Create or modify: `services/part_bom.py` (add `recalc_part_unit_cost`)
- Modify: `services/part_bom.py` (trigger recalc on BOM change)
- Modify: `services/part.py` (trigger recalc on child part unit_cost change)
- Modify: `services/cost_sync.py` (sync assembly_cost from handcraft receipt)
- Test: `tests/test_part_bom.py`

- [ ] **Step 1: Add `assembly_cost` to Part model**

In `models/part.py`, add after existing cost fields:

```python
    assembly_cost = Column(Numeric(18, 7), nullable=True)
```

In `database.py`, add schema compat:

```python
# --- part.assembly_cost ---
if inspector.has_table("part"):
    cols = [c["name"] for c in inspector.get_columns("part")]
    if "assembly_cost" not in cols:
        conn.execute(text(
            "ALTER TABLE part ADD COLUMN assembly_cost NUMERIC(18,7)"
        ))
```

- [ ] **Step 2: Write failing tests**

Add to `tests/test_part_bom.py`:

```python
def test_recalc_unit_cost_on_bom_change(client, db):
    """Setting part BOM auto-recalculates parent unit_cost."""
    parent, children = _setup_parts(db)
    # Set child costs
    children[0].unit_cost = 10.0
    children[1].unit_cost = 20.0
    children[2].unit_cost = 5.0
    db.flush()

    # Add BOM: e*2 + f*1 + g*3
    client.post(f"/api/parts/{parent.id}/bom", json={"child_part_id": children[0].id, "qty_per_unit": 2.0})
    client.post(f"/api/parts/{parent.id}/bom", json={"child_part_id": children[1].id, "qty_per_unit": 1.0})
    client.post(f"/api/parts/{parent.id}/bom", json={"child_part_id": children[2].id, "qty_per_unit": 3.0})

    db.refresh(parent)
    # Expected: 10*2 + 20*1 + 5*3 = 55, no assembly_cost yet
    assert float(parent.unit_cost) == 55.0


def test_recalc_includes_assembly_cost(client, db):
    """unit_cost includes assembly_cost."""
    parent, children = _setup_parts(db)
    children[0].unit_cost = 10.0
    parent.assembly_cost = 8.0
    db.flush()

    client.post(f"/api/parts/{parent.id}/bom", json={"child_part_id": children[0].id, "qty_per_unit": 2.0})

    db.refresh(parent)
    # Expected: 10*2 + 8 = 28
    assert float(parent.unit_cost) == 28.0


def test_recalc_on_child_cost_change(client, db):
    """Updating child part unit_cost triggers parent recalc."""
    parent, children = _setup_parts(db)
    children[0].unit_cost = 10.0
    db.flush()

    client.post(f"/api/parts/{parent.id}/bom", json={"child_part_id": children[0].id, "qty_per_unit": 2.0})
    db.refresh(parent)
    assert float(parent.unit_cost) == 20.0

    # Update child cost
    client.patch(f"/api/parts/{children[0].id}", json={"unit_cost": 15.0})
    db.refresh(parent)
    assert float(parent.unit_cost) == 30.0


def test_recalc_on_bom_delete(client, db):
    """Deleting a BOM row recalculates parent unit_cost."""
    parent, children = _setup_parts(db)
    children[0].unit_cost = 10.0
    children[1].unit_cost = 20.0
    db.flush()

    resp1 = client.post(f"/api/parts/{parent.id}/bom", json={"child_part_id": children[0].id, "qty_per_unit": 1.0})
    resp2 = client.post(f"/api/parts/{parent.id}/bom", json={"child_part_id": children[1].id, "qty_per_unit": 1.0})
    db.refresh(parent)
    assert float(parent.unit_cost) == 30.0

    # Delete one BOM row
    bom_id = resp2.json()["id"]
    client.delete(f"/api/parts/bom/{bom_id}")
    db.refresh(parent)
    assert float(parent.unit_cost) == 10.0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_part_bom.py -v -k "recalc"`
Expected: FAIL

- [ ] **Step 4: Implement `recalc_part_unit_cost`**

In `services/part_bom.py`, add:

```python
from decimal import Decimal

def recalc_part_unit_cost(db: Session, part_id: str) -> None:
    """Recalculate unit_cost for a composite part based on its part_bom.

    unit_cost = Σ(child.unit_cost × qty_per_unit) + assembly_cost
    Only applies if the part has part_bom rows.
    """
    rows = db.query(PartBom).filter_by(parent_part_id=part_id).all()
    if not rows:
        return  # Not a composite part, don't touch unit_cost

    part = db.query(Part).filter_by(id=part_id).first()
    if not part:
        return

    total = Decimal("0")
    for row in rows:
        child = db.query(Part).filter_by(id=row.child_part_id).first()
        child_cost = Decimal(str(child.unit_cost or 0)) if child else Decimal("0")
        total += child_cost * row.qty_per_unit

    assembly = Decimal(str(part.assembly_cost or 0))
    part.unit_cost = total + assembly
    db.flush()


def recalc_parents_of_child(db: Session, child_part_id: str) -> None:
    """Find all parent parts that use this child and recalculate their unit_cost."""
    parent_boms = db.query(PartBom).filter_by(child_part_id=child_part_id).all()
    for bom in parent_boms:
        recalc_part_unit_cost(db, bom.parent_part_id)
```

- [ ] **Step 5: Trigger recalc in BOM CRUD**

Update `set_part_bom` and `delete_part_bom_item` in `services/part_bom.py` to call `recalc_part_unit_cost` after changes:

```python
def set_part_bom(...):
    # ... existing logic ...
    db.flush()
    recalc_part_unit_cost(db, parent_part_id)
    return bom

def delete_part_bom_item(...):
    parent_id = row.parent_part_id
    # ... existing delete ...
    db.flush()
    recalc_part_unit_cost(db, parent_id)
```

- [ ] **Step 6: Trigger recalc on child part cost change**

In `services/part.py`, find the `update_part` function. After updating `unit_cost`, trigger parent recalc:

```python
from services.part_bom import recalc_parents_of_child

def update_part(db, part_id, data):
    # ... existing logic ...
    if "unit_cost" in data:
        recalc_parents_of_child(db, part_id)
    # Also recalc self if assembly_cost changed
    if "assembly_cost" in data:
        from services.part_bom import recalc_part_unit_cost
        recalc_part_unit_cost(db, part_id)
```

- [ ] **Step 7: Sync assembly_cost from handcraft receipt**

In `services/cost_sync.py` (or the handcraft receipt service where cost diffs are detected), add logic:

When a handcraft receipt receives a part output item (HandcraftJewelryItem with `part_id` set), detect if `price` differs from `Part.assembly_cost` and sync:

```python
# In the cost_sync / receipt creation flow:
if output_item.part_id:
    part = db.query(Part).filter_by(id=output_item.part_id).first()
    if part and receipt_item_price is not None:
        part.assembly_cost = receipt_item_price
        recalc_part_unit_cost(db, part.id)
        db.flush()
```

- [ ] **Step 8: Run tests**

Run: `pytest tests/test_part_bom.py -v`
Expected: All PASS

- [ ] **Step 9: Run full test suite**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add models/part.py database.py services/part_bom.py services/part.py services/cost_sync.py tests/test_part_bom.py
git commit -m "feat: auto-calculate composite part unit_cost from part_bom + assembly_cost"
```

---

## Task 7: Frontend — Part BOM Section on PartDetail

**Files:**
- Modify: `frontend/src/api/parts.js`
- Modify: `frontend/src/views/parts/PartDetail.vue`

- [ ] **Step 1: Add API functions**

In `frontend/src/api/parts.js`, add:

```javascript
export function getPartBom(partId) {
  return request.get(`/parts/${partId}/bom`)
}

export function setPartBom(partId, data) {
  return request.post(`/parts/${partId}/bom`, data)
}

export function deletePartBom(bomId) {
  return request.delete(`/parts/bom/${bomId}`)
}
```

- [ ] **Step 2: Add sub-parts BOM section to PartDetail.vue**

Add a "子配件" card section below the existing part info. Mirror the BOM management pattern from `JewelryDetail.vue`:

- Table columns: 子配件编号, 子配件（图片+名称）, 每单位用量（inline edit）, 操作（删除）
- Add row: select part + input qty + confirm button
- Inline edit qty on blur → `setPartBom()`
- Delete with popconfirm → `deletePartBom()`

```javascript
import { getPartBom, setPartBom, deletePartBom } from '@/api/parts'

const partBomList = ref([])
const newChildPartId = ref(null)
const newChildQty = ref(1)

async function loadPartBom() {
  const { data } = await getPartBom(partId.value)
  partBomList.value = data
}

async function addPartBom() {
  if (!newChildPartId.value) return
  await setPartBom(partId.value, {
    child_part_id: newChildPartId.value,
    qty_per_unit: newChildQty.value,
  })
  newChildPartId.value = null
  newChildQty.value = 1
  await loadPartBom()
}

async function savePartBomQty(row) {
  await setPartBom(partId.value, {
    child_part_id: row.child_part_id,
    qty_per_unit: row.qty_per_unit,
  })
}

async function doDeletePartBom(bomId) {
  await deletePartBom(bomId)
  await loadPartBom()
}
```

- [ ] **Step 3: Add cost display for composite parts**

When the part has sub-parts BOM, the `unit_cost` is auto-calculated. In PartDetail.vue:
- Show `unit_cost` as read-only with label "自动计算"
- Show cost breakdown: each child part cost contribution + assembly_cost = total
- `assembly_cost` field: editable input (also auto-synced from handcraft receipts)

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/parts.js frontend/src/views/parts/PartDetail.vue
git commit -m "feat: add sub-parts BOM management and cost display on PartDetail"
```

---

## Task 8: Frontend — Handcraft Detail Output Items

**Files:**
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue`

- [ ] **Step 1: Rename "饰品明细" to "产出明细"**

Find the section title "饰品明细" and change to "产出明细".

- [ ] **Step 2: Update output items table to show both jewelry and part**

In the table columns, update the name/image column to display:
- If `jewelry_id`: show jewelry name + image (existing)
- If `part_id`: show part name + image (new)

Add a type indicator column or tag to distinguish "饰品" vs "配件".

- [ ] **Step 3: Update add output item modal**

Add a toggle or select for "产出类型": 饰品 / 配件.
- When "饰品" selected: show jewelry selector (existing)
- When "配件" selected: show part selector (new), filter to parts that have sub-parts BOM

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/handcraft/HandcraftDetail.vue
git commit -m "feat: rename to 产出明细, support part output in handcraft detail"
```

---

## Task 9: Frontend — Receipt Support for Part Output

**Files:**
- Modify: Handcraft receipt create/detail pages

- [ ] **Step 1: Update pending receive list**

The pending receive endpoint should now return part output items alongside jewelry items. Update the receipt creation UI to show both types.

- [ ] **Step 2: Update receipt detail display**

In receipt detail, show item_type as "配件" when the output is a part (instead of "饰品").

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/handcraft/
git commit -m "feat: support part output items in handcraft receipt pages"
```

---

## Task 10: Verify

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 2: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Manual verification**

Test the full sub-assembly flow:
1. Create part c with sub-parts BOM (e, f, g) on PartDetail page
2. Create handcraft order: send e, f, g → output part c
3. Send the handcraft order (deducts e, f, g stock)
4. Create receipt: receive part c
5. Verify: c stock increased, e/f/g auto-consumed (received_qty updated)
6. Verify: handcraft order auto-completes when all items received
