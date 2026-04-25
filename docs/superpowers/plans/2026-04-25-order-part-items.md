# 订单支持购买配件 (Order Part Items) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow `OrderItem` rows to reference either a `jewelry_id` or a `part_id` (XOR), so customers can purchase parts directly within an order. Direct-purchase parts join existing TodoList / picking flows but do not trigger handcraft / plating; their stock is deducted at order completion.

**Architecture:** Single `order_item` table with nullable FKs and a DB CHECK constraint enforcing XOR. Service layer adds direct-part contributions to `get_parts_summary`, picking, and global demand; a new branch in `update_order_status` deducts/restores `part` stock on completion / un-completion. Frontend splits jewelry vs. part sections into two cards on order create/detail pages. `part.wholesale_price` is the default unit price; user-entered prices write back.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Pydantic V2, PostgreSQL, Vue 3 + Naive UI, pytest.

**Spec:** `docs/superpowers/specs/2026-04-25-order-part-items-design.md`

---

## Task 1: DB schema migration (additive)

Add `part.wholesale_price`, make `order_item.jewelry_id` nullable, add `order_item.part_id` + CHECK constraint via `ensure_schema_compat()`.

**Files:**
- Modify: `database.py` — add migrations to `ensure_schema_compat()`
- Modify: `models/part.py` — add `wholesale_price` column
- Modify: `models/order.py` — `OrderItem`: `jewelry_id` nullable, add `part_id`, add `CheckConstraint`
- Test: `tests/test_db_migration_part_items.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_migration_part_items.py
"""Verify ensure_schema_compat() adds part.wholesale_price, order_item.part_id,
makes order_item.jewelry_id nullable, and adds the XOR CHECK constraint."""
from sqlalchemy import inspect, text


def test_part_has_wholesale_price_column(engine):
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("part")}
    assert "wholesale_price" in cols


def test_order_item_has_part_id_column(engine):
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("order_item")}
    assert "part_id" in cols


def test_order_item_jewelry_id_is_nullable(engine):
    insp = inspect(engine)
    cols = {c["name"]: c for c in insp.get_columns("order_item")}
    assert cols["jewelry_id"]["nullable"] is True


def test_xor_check_constraint_rejects_both_null(engine):
    # Direct INSERT bypassing ORM — both NULL must violate CHECK
    from sqlalchemy.exc import IntegrityError
    with engine.begin() as conn:
        conn.execute(text(
            'INSERT INTO "order" (id, customer_name, status) '
            "VALUES ('OR-CK1', 'check-test', '待生产')"
        ))
        try:
            conn.execute(text(
                "INSERT INTO order_item (order_id, jewelry_id, part_id, quantity, unit_price) "
                "VALUES ('OR-CK1', NULL, NULL, 1, 0)"
            ))
            assert False, "expected IntegrityError"
        except IntegrityError:
            pass


def test_xor_check_constraint_rejects_both_set(engine):
    from sqlalchemy.exc import IntegrityError
    with engine.begin() as conn:
        conn.execute(text(
            'INSERT INTO "order" (id, customer_name, status) '
            "VALUES ('OR-CK2', 'check-test', '待生产')"
        ))
        # Need real jewelry + part FKs
        conn.execute(text(
            "INSERT INTO jewelry (id, name, status) VALUES ('SP-CK', 'j', 'active')"
        ))
        conn.execute(text(
            "INSERT INTO part (id, name) VALUES ('PJ-CK', 'p')"
        ))
        try:
            conn.execute(text(
                "INSERT INTO order_item (order_id, jewelry_id, part_id, quantity, unit_price) "
                "VALUES ('OR-CK2', 'SP-CK', 'PJ-CK', 1, 0)"
            ))
            assert False, "expected IntegrityError"
        except IntegrityError:
            pass
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_db_migration_part_items.py -v
```
Expected: FAIL — columns/constraint missing.

- [ ] **Step 3: Update `models/part.py`**

```python
# models/part.py — add the column to Part class
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String

class Part(Base):
    __tablename__ = "part"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    image = Column(String, nullable=True)
    category = Column(String, nullable=True)
    color = Column(String, nullable=True)
    unit = Column(String, nullable=True)
    unit_cost = Column(Numeric(18, 7), nullable=True)
    wholesale_price = Column(Numeric(18, 7), nullable=True)   # <-- NEW
    purchase_cost = Column(Numeric(18, 7), nullable=True)
    bead_cost = Column(Numeric(18, 7), nullable=True)
    plating_cost = Column(Numeric(18, 7), nullable=True)
    plating_process = Column(String, nullable=True)
    assembly_cost = Column(Numeric(18, 7), nullable=True)
    spec = Column(String, nullable=True)
    parent_part_id = Column(String, ForeignKey("part.id"), nullable=True)
    is_composite = Column(Boolean, nullable=False, server_default="false")
```

- [ ] **Step 4: Update `models/order.py` `OrderItem`**

```python
# models/order.py — replace OrderItem definition
from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint,
)


class OrderItem(Base):
    __tablename__ = "order_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("order.id"), nullable=False, index=True)
    jewelry_id = Column(String, ForeignKey("jewelry.id"), nullable=True)
    part_id = Column(String, ForeignKey("part.id"), nullable=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(18, 7), nullable=False)
    remarks = Column(Text, nullable=True)
    customer_code = Column(String, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "(jewelry_id IS NULL) <> (part_id IS NULL)",
            name="ck_order_item_jewelry_xor_part",
        ),
    )
```

- [ ] **Step 5: Add migration block to `database.py` `ensure_schema_compat()`**

Insert after the existing `if inspector.has_table("order_item")` block (around line 206):

```python
        # --- part.wholesale_price ---
        if inspector.has_table("part"):
            cols = {c["name"] for c in inspector.get_columns("part")}
            if "wholesale_price" not in cols:
                conn.execute(text(
                    "ALTER TABLE part ADD COLUMN wholesale_price NUMERIC(18,7) NULL"
                ))
                logger.warning("Added missing part.wholesale_price column")

        # --- order_item: part_id + nullable jewelry_id + XOR CHECK ---
        if inspector.has_table("order_item"):
            cols = {c["name"]: c for c in inspector.get_columns("order_item")}
            if "part_id" not in cols:
                conn.execute(text(
                    "ALTER TABLE order_item ADD COLUMN part_id VARCHAR NULL "
                    "REFERENCES part(id)"
                ))
                logger.warning("Added missing order_item.part_id column")
            if cols.get("jewelry_id") and cols["jewelry_id"]["nullable"] is False:
                conn.execute(text(
                    "ALTER TABLE order_item ALTER COLUMN jewelry_id DROP NOT NULL"
                ))
                logger.warning("Made order_item.jewelry_id nullable")
            existing_constraints = {
                c["name"] for c in inspector.get_check_constraints("order_item")
            }
            if "ck_order_item_jewelry_xor_part" not in existing_constraints:
                conn.execute(text(
                    "ALTER TABLE order_item ADD CONSTRAINT "
                    "ck_order_item_jewelry_xor_part "
                    "CHECK ((jewelry_id IS NULL) <> (part_id IS NULL))"
                ))
                logger.warning("Added missing order_item XOR CHECK constraint")
```

- [ ] **Step 6: Run test to verify it passes**

```bash
pytest tests/test_db_migration_part_items.py -v
```
Expected: PASS (4 tests).

- [ ] **Step 7: Run existing test suite to confirm no regressions**

```bash
pytest tests/ -x -q
```
Expected: all existing tests pass. If any fail because they create `OrderItem` rows without `jewelry_id` (impossible before this change), update them in this same task.

- [ ] **Step 8: Commit**

```bash
git add models/part.py models/order.py database.py tests/test_db_migration_part_items.py
git commit -m "feat: order_item supports part_id (XOR with jewelry_id) + part.wholesale_price"
```

---

## Task 2: Part schema — expose wholesale_price

**Files:**
- Modify: `schemas/part.py` — add `wholesale_price` to `PartCreate`, `PartUpdate`, `PartResponse`
- Test: `tests/test_api_parts.py` — extend with wholesale_price round-trip

- [ ] **Step 1: Inspect existing schemas/part.py to find Create/Update/Response classes**

```bash
grep -n "class Part" schemas/part.py
```

- [ ] **Step 2: Write the failing test (append to `tests/test_api_parts.py`)**

```python
def test_part_wholesale_price_round_trip(client):
    # Create a part with wholesale_price
    r = client.post("/api/parts/", json={
        "name": "测试链条",
        "category": "链条",
        "wholesale_price": 15.0,
    })
    assert r.status_code == 201
    part_id = r.json()["id"]
    assert r.json()["wholesale_price"] == 15.0

    # Update it
    r = client.patch(f"/api/parts/{part_id}", json={"wholesale_price": 18.5})
    assert r.status_code == 200
    assert r.json()["wholesale_price"] == 18.5

    # Get it
    r = client.get(f"/api/parts/{part_id}")
    assert r.json()["wholesale_price"] == 18.5
```

- [ ] **Step 3: Run test to verify failure**

```bash
pytest tests/test_api_parts.py::test_part_wholesale_price_round_trip -v
```
Expected: FAIL — schema rejects `wholesale_price`.

- [ ] **Step 4: Add field to schemas in `schemas/part.py`**

Find `PartCreate`, `PartUpdate`, `PartResponse`, add `wholesale_price: Optional[float] = None` to each.

- [ ] **Step 5: Run test to verify pass**

```bash
pytest tests/test_api_parts.py::test_part_wholesale_price_round_trip -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add schemas/part.py tests/test_api_parts.py
git commit -m "feat: part schemas expose wholesale_price"
```

---

## Task 3: Pydantic XOR validator on `OrderItemCreate`

**Files:**
- Modify: `schemas/order.py` — `OrderItemCreate` becomes XOR (`jewelry_id` OR `part_id`); `OrderItemResponse` adds `part_id` + enriched fields
- Test: `tests/test_api_orders.py` — add XOR validation tests

- [ ] **Step 1: Write the failing tests (append to `tests/test_api_orders.py`)**

```python
def test_order_create_rejects_both_null_in_item(client):
    r = client.post("/api/orders/", json={
        "customer_name": "x",
        "items": [{"quantity": 1, "unit_price": 0}],
    })
    assert r.status_code == 422


def test_order_create_rejects_both_set_in_item(client, db):
    # Need valid jewelry & part to make pydantic ID checks pass
    db.execute(text(
        "INSERT INTO jewelry (id, name, status) VALUES ('SP-T1', 'j', 'active')"
    ))
    db.execute(text("INSERT INTO part (id, name) VALUES ('PJ-T1', 'p')"))
    db.commit()
    r = client.post("/api/orders/", json={
        "customer_name": "x",
        "items": [{
            "jewelry_id": "SP-T1",
            "part_id": "PJ-T1",
            "quantity": 1,
            "unit_price": 0,
        }],
    })
    assert r.status_code == 422
```

(Add `from sqlalchemy import text` at the top if not present.)

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_api_orders.py::test_order_create_rejects_both_null_in_item tests/test_api_orders.py::test_order_create_rejects_both_set_in_item -v
```
Expected: FAIL — schema accepts both.

- [ ] **Step 3: Update `OrderItemCreate` and `OrderItemResponse` in `schemas/order.py`**

Replace the existing `OrderItemCreate` and `OrderItemResponse`:

```python
from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrderItemCreate(BaseModel):
    jewelry_id: Optional[str] = None
    part_id: Optional[str] = None
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    remarks: Optional[str] = None

    @model_validator(mode="after")
    def _xor(self):
        if (self.jewelry_id is None) == (self.part_id is None):
            raise ValueError("jewelry_id 和 part_id 必须且只能填一个")
        return self


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: str
    jewelry_id: Optional[str] = None
    part_id: Optional[str] = None
    quantity: int
    unit_price: float
    remarks: Optional[str] = None
    customer_code: str | None = None
    # Enriched (populated by service layer at response time)
    part_name: Optional[str] = None
    part_image: Optional[str] = None
    part_unit: Optional[str] = None
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_api_orders.py::test_order_create_rejects_both_null_in_item tests/test_api_orders.py::test_order_create_rejects_both_set_in_item -v
```
Expected: PASS.

- [ ] **Step 5: Run full orders test file to catch regressions**

```bash
pytest tests/test_api_orders.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add schemas/order.py tests/test_api_orders.py
git commit -m "feat: OrderItemCreate XOR jewelry_id/part_id; response carries part_id"
```

---

## Task 4: Service layer — create/add part items + wholesale_price write-back

**Files:**
- Modify: `services/order.py` — `create_order`, `add_order_item`, `update_order_item`
- Test: `tests/test_service_order_part_items.py` (new)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_service_order_part_items.py
import pytest
from decimal import Decimal
from models.order import Order, OrderItem
from models.part import Part
from services.order import create_order, add_order_item, update_order_item


@pytest.fixture
def part_chain(db):
    p = Part(id="PJ-LT-T01", name="链 1.5mm", category="链条",
             unit="米", wholesale_price=Decimal("15"), unit_cost=Decimal("8"))
    db.add(p)
    db.flush()
    return p


def test_create_order_with_part_only(db, part_chain):
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id,
        "quantity": 5,
        "unit_price": 15,
        "remarks": None,
    }])
    items = db.query(OrderItem).filter_by(order_id=order.id).all()
    assert len(items) == 1
    assert items[0].part_id == part_chain.id
    assert items[0].jewelry_id is None
    assert order.total_amount == Decimal("75.0000000")


def test_create_order_writes_back_wholesale_price(db, part_chain):
    create_order(db, "客户A", [{
        "part_id": part_chain.id,
        "quantity": 1,
        "unit_price": 22,
        "remarks": None,
    }])
    db.refresh(part_chain)
    assert part_chain.wholesale_price == Decimal("22")


def test_create_order_does_not_write_back_when_price_matches(db, part_chain):
    create_order(db, "客户A", [{
        "part_id": part_chain.id,
        "quantity": 1,
        "unit_price": 15,  # same as default
        "remarks": None,
    }])
    db.refresh(part_chain)
    assert part_chain.wholesale_price == Decimal("15")


def test_add_part_item_to_existing_order(db, part_chain):
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id,
        "quantity": 1,
        "unit_price": 15,
        "remarks": None,
    }])
    add_order_item(db, order.id, {
        "part_id": part_chain.id,
        "quantity": 2,
        "unit_price": 16,
    })
    items = db.query(OrderItem).filter_by(order_id=order.id).all()
    assert len(items) == 2
    db.refresh(part_chain)
    assert part_chain.wholesale_price == Decimal("16")


def test_update_part_item_unit_price_writes_back(db, part_chain):
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id,
        "quantity": 1,
        "unit_price": 15,
        "remarks": None,
    }])
    item = db.query(OrderItem).filter_by(order_id=order.id).first()
    update_order_item(db, order.id, item.id, {"unit_price": 19.5})
    db.refresh(part_chain)
    assert part_chain.wholesale_price == Decimal("19.5")
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_service_order_part_items.py -v
```
Expected: FAIL — `create_order` does not handle `part_id`.

- [ ] **Step 3: Update `create_order` in `services/order.py`**

Replace the `for item in items:` loop inside `create_order`:

```python
    for item in items:
        unit_price = Decimal(str(item["unit_price"])).quantize(_Q7, rounding=ROUND_HALF_UP)
        subtotal = (Decimal(str(item["quantity"])) * unit_price).quantize(_Q7, rounding=ROUND_HALF_UP)
        total += subtotal
        db.add(OrderItem(
            order_id=order_id,
            jewelry_id=item.get("jewelry_id"),
            part_id=item.get("part_id"),
            quantity=item["quantity"],
            unit_price=unit_price,
            remarks=item.get("remarks"),
        ))
        if item.get("part_id"):
            _writeback_part_wholesale_price(db, item["part_id"], unit_price)
```

Add helper at module top (after imports):

```python
from models.part import Part  # add to existing imports


def _writeback_part_wholesale_price(db: Session, part_id: str, new_price: Decimal) -> None:
    """If part.wholesale_price differs from new_price, overwrite it."""
    part = db.query(Part).filter(Part.id == part_id).first()
    if part is None:
        return
    if part.wholesale_price != new_price:
        part.wholesale_price = new_price
        db.flush()
```

- [ ] **Step 4: Update `add_order_item` similarly**

Replace its body:

```python
def add_order_item(db: Session, order_id: str, data: dict) -> OrderItem:
    order = get_order(db, order_id)
    if order is None:
        raise ValueError(f"Order not found: {order_id}")
    if order.status != "待生产":
        raise ValueError(f"订单状态为「{order.status}」，只有「待生产」状态可以修改饰品明细")
    if (data.get("jewelry_id") is None) == (data.get("part_id") is None):
        raise ValueError("jewelry_id 和 part_id 必须且只能填一个")
    unit_price = Decimal(str(data["unit_price"])).quantize(_Q7, rounding=ROUND_HALF_UP)
    item = OrderItem(
        order_id=order_id,
        jewelry_id=data.get("jewelry_id"),
        part_id=data.get("part_id"),
        quantity=data["quantity"],
        unit_price=unit_price,
        remarks=data.get("remarks"),
    )
    db.add(item)
    db.flush()
    if data.get("part_id"):
        _writeback_part_wholesale_price(db, data["part_id"], unit_price)
    _recalc_total(db, order)
    return item
```

- [ ] **Step 5: Update `update_order_item` to write back on price change**

Inside `update_order_item`, after the existing `for key, value in fields.items(): setattr(...)` loop, before the `if price_fields & fields.keys(): _recalc_total(db, order)` line, add:

```python
    if "unit_price" in fields and item.part_id is not None:
        new_price = Decimal(str(fields["unit_price"])).quantize(_Q7, rounding=ROUND_HALF_UP)
        _writeback_part_wholesale_price(db, item.part_id, new_price)
```

Also: the existing logic in `update_order_item` checks `jewelry_id` for handcraft allocation. Wrap that block with `if item.jewelry_id is not None:` so it skips for part items:

```python
    if "quantity" in fields:
        new_qty = fields["quantity"]
        if item.jewelry_id is not None:    # <-- skip allocation check for part items
            jewelry_id = item.jewelry_id
            # ... existing batch_allocated / legacy_allocated / new_total check ...
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_service_order_part_items.py -v
```
Expected: PASS (5 tests).

- [ ] **Step 7: Run all order tests for regressions**

```bash
pytest tests/test_api_orders.py tests/test_service_order_part_items.py -v
```
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add services/order.py tests/test_service_order_part_items.py
git commit -m "feat: order service supports part items with wholesale_price write-back"
```

---

## Task 5: Stock deduction at "已完成" + rollback

**Files:**
- Modify: `services/order.py` — extend `update_order_status`
- Test: `tests/test_service_order_part_items.py` — append cases

- [ ] **Step 1: Append failing tests**

```python
# tests/test_service_order_part_items.py — append
from services.inventory import add_stock, get_stock
from services.order import update_order_status


def test_complete_order_deducts_part_stock(db, part_chain):
    add_stock(db, "part", part_chain.id, 100, "测试入库")
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id, "quantity": 5, "unit_price": 15, "remarks": None,
    }])
    update_order_status(db, order.id, "已完成")
    assert get_stock(db, "part", part_chain.id) == 95


def test_complete_order_rejects_when_part_stock_insufficient(db, part_chain):
    add_stock(db, "part", part_chain.id, 3, "测试入库")
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id, "quantity": 5, "unit_price": 15, "remarks": None,
    }])
    with pytest.raises(ValueError, match="配件库存不足"):
        update_order_status(db, order.id, "已完成")
    db.refresh(order)
    assert order.status == "待生产"
    assert get_stock(db, "part", part_chain.id) == 3  # untouched


def test_uncomplete_restores_part_stock(db, part_chain):
    add_stock(db, "part", part_chain.id, 100, "测试入库")
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id, "quantity": 5, "unit_price": 15, "remarks": None,
    }])
    update_order_status(db, order.id, "已完成")
    update_order_status(db, order.id, "已取消")
    assert get_stock(db, "part", part_chain.id) == 100


def test_complete_aggregates_same_part_across_items(db, part_chain):
    add_stock(db, "part", part_chain.id, 10, "测试入库")
    order = create_order(db, "客户A", [
        {"part_id": part_chain.id, "quantity": 4, "unit_price": 15, "remarks": None},
        {"part_id": part_chain.id, "quantity": 4, "unit_price": 15, "remarks": None},
    ])
    update_order_status(db, order.id, "已完成")
    assert get_stock(db, "part", part_chain.id) == 2


def test_complete_order_jewelry_only_does_not_touch_stock(db):
    # ensure no regression to existing jewelry-only behavior
    from models.jewelry import Jewelry
    from models.bom import Bom
    from sqlalchemy import text as sa_text
    db.add(Jewelry(id="SP-T2", name="j", status="active",
                   handcraft_cost=0, wholesale_price=100))
    db.add(Part(id="PJ-T2", name="p", unit_cost=10))
    db.flush()
    db.add(Bom(jewelry_id="SP-T2", part_id="PJ-T2", qty_per_unit=1))
    db.flush()
    order = create_order(db, "客户A", [{
        "jewelry_id": "SP-T2", "quantity": 1, "unit_price": 100, "remarks": None,
    }])
    # No part stock; jewelry-only completion does not need it.
    update_order_status(db, order.id, "已完成")
    db.refresh(order)
    assert order.status == "已完成"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_service_order_part_items.py -v -k "complete or uncomplete or aggregates"
```
Expected: FAIL — stock deduction not implemented.

- [ ] **Step 3: Modify `update_order_status` in `services/order.py`**

Replace the existing function:

```python
def update_order_status(db: Session, order_id: str, status: str) -> Order:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {_VALID_STATUSES}")
    order = get_order(db, order_id)
    if order is None:
        raise ValueError(f"Order not found: {order_id}")
    if order.status == status:
        return order  # no-op, avoids duplicate snapshot generation

    items = get_order_items(db, order_id)
    part_qty_map: dict[str, int] = {}
    for it in items:
        if it.part_id is not None:
            part_qty_map[it.part_id] = part_qty_map.get(it.part_id, 0) + it.quantity

    # Transition INTO "已完成" — pre-check then deduct part stock
    if status == "已完成" and order.status != "已完成":
        if part_qty_map:
            from services.inventory import batch_get_stock, deduct_stock
            stocks = batch_get_stock(db, "part", list(part_qty_map.keys()))
            insufficient = [
                f"{pid} 需要 {qty}，仅有 {stocks.get(pid, 0):.2f}"
                for pid, qty in part_qty_map.items()
                if stocks.get(pid, 0) < qty
            ]
            if insufficient:
                raise ValueError("配件库存不足：" + "；".join(insufficient))
            for pid, qty in part_qty_map.items():
                deduct_stock(db, "part", pid, qty, "订单出货")
        from services.order_cost_snapshot import generate_cost_snapshot
        generate_cost_snapshot(db, order_id)

    # Transition OUT of "已完成" — restore part stock
    elif order.status == "已完成" and status != "已完成":
        if part_qty_map:
            from services.inventory import add_stock
            for pid, qty in part_qty_map.items():
                add_stock(db, "part", pid, qty, "订单出货撤回")

    order.status = status
    db.flush()
    return order
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_service_order_part_items.py -v
```
Expected: PASS.

- [ ] **Step 5: Run jewelry-only regression suite**

```bash
pytest tests/test_api_orders.py tests/test_api_cost_snapshot.py -v
```
Expected: all pass. Cost snapshot tests use jewelry items only — should still work.

- [ ] **Step 6: Commit**

```bash
git add services/order.py tests/test_service_order_part_items.py
git commit -m "feat: deduct/restore part stock on order 已完成 transitions"
```

---

## Task 6: Reject `customer_code` on part items

**Files:**
- Modify: `services/order.py` — `update_order_item`, `batch_fill_customer_code`
- Test: `tests/test_service_order_part_items.py` — append

- [ ] **Step 1: Append failing tests**

```python
# tests/test_service_order_part_items.py — append
from services.order import update_order_item_customer_code, batch_fill_customer_code


def test_reject_customer_code_on_part_item(db, part_chain):
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id, "quantity": 1, "unit_price": 15, "remarks": None,
    }])
    item = db.query(OrderItem).filter_by(order_id=order.id).first()
    with pytest.raises(ValueError, match="配件项不允许设置客户货号"):
        update_order_item_customer_code(db, order.id, item.id, "C001")


def test_reject_batch_customer_code_with_part_item(db, part_chain):
    from models.jewelry import Jewelry
    db.add(Jewelry(id="SP-T3", name="j", status="active", wholesale_price=100))
    db.flush()
    order = create_order(db, "客户A", [
        {"jewelry_id": "SP-T3", "quantity": 1, "unit_price": 100, "remarks": None},
        {"part_id": part_chain.id, "quantity": 1, "unit_price": 15, "remarks": None},
    ])
    items = db.query(OrderItem).filter_by(order_id=order.id).all()
    item_ids = [i.id for i in items]
    with pytest.raises(ValueError, match="配件项不允许设置客户货号"):
        batch_fill_customer_code(db, order.id, item_ids, "C", 0, 2)
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_service_order_part_items.py -v -k "customer_code"
```
Expected: FAIL.

- [ ] **Step 3: Update `update_order_item` to reject customer_code on part items**

Inside `update_order_item`, before applying any field, add:

```python
    if "customer_code" in fields and item.part_id is not None:
        raise ValueError("配件项不允许设置客户货号")
```

- [ ] **Step 4: Update `batch_fill_customer_code`**

Inside `batch_fill_customer_code`, after loading `items`, before the renaming loop:

```python
    if any(it.part_id is not None for it in items):
        raise ValueError("配件项不允许设置客户货号")
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_service_order_part_items.py -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/order.py tests/test_service_order_part_items.py
git commit -m "feat: reject customer_code on part order items"
```

---

## Task 7: TodoList aggregation includes direct part contributions

**Files:**
- Modify: `services/order.py` — `get_parts_summary`, `_calc_global_part_demand`
- Modify: `schemas/order.py` — `SourceJewelryItem` adds `source_type`, makes `jewelry_id` / `qty_per_unit` Optional
- Test: `tests/test_service_order_part_items.py` — append

- [ ] **Step 1: Append failing test**

```python
# tests/test_service_order_part_items.py — append
from services.order import get_parts_summary


def test_parts_summary_merges_bom_and_direct(db, part_chain):
    from models.jewelry import Jewelry
    from models.bom import Bom
    db.add(Jewelry(id="SP-T4", name="j", status="active",
                   handcraft_cost=0, wholesale_price=200))
    db.flush()
    db.add(Bom(jewelry_id="SP-T4", part_id=part_chain.id, qty_per_unit=3))
    db.flush()
    order = create_order(db, "客户A", [
        {"jewelry_id": "SP-T4", "quantity": 1, "unit_price": 200, "remarks": None},
        {"part_id": part_chain.id, "quantity": 5, "unit_price": 15, "remarks": None},
    ])
    summary = get_parts_summary(db, order.id)
    row = next(r for r in summary if r["part_id"] == part_chain.id)
    assert row["total_qty"] == 8  # 3 BOM + 5 direct (ceil)
    sources = row["source_jewelries"]
    types = {s.get("source_type", "jewelry") for s in sources}
    assert "direct" in types
    assert "jewelry" in types
    direct = next(s for s in sources if s.get("source_type") == "direct")
    assert direct["order_qty"] == 5


def test_parts_summary_direct_only_order(db, part_chain):
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id, "quantity": 7, "unit_price": 15, "remarks": None,
    }])
    summary = get_parts_summary(db, order.id)
    assert len(summary) == 1
    row = summary[0]
    assert row["part_id"] == part_chain.id
    assert row["total_qty"] == 7
    assert row["source_jewelries"][0].get("source_type") == "direct"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_service_order_part_items.py -v -k "summary"
```
Expected: FAIL.

- [ ] **Step 3: Update `SourceJewelryItem` in `schemas/order.py`**

```python
from typing import Literal


class SourceJewelryItem(BaseModel):
    source_type: Literal["jewelry", "direct"] = "jewelry"
    jewelry_id: Optional[str] = None
    jewelry_name: str = ""
    qty_per_unit: Optional[float] = None
    order_qty: int
    subtotal: float
```

- [ ] **Step 4: Update `get_parts_summary` in `services/order.py`**

In `get_parts_summary`, after the existing BOM aggregation loops, before the final `result = []` build, add direct part contributions. Locate the block that filters items by `oi.jewelry_id` for BOM expansion — change to filter `if oi.jewelry_id is not None`. Then add a new aggregation pass:

After this existing line:
```python
    items = get_order_items(db, order_id)
    if not items:
        return []
```

Filter jewelry vs. part items:
```python
    jewelry_items = [oi for oi in items if oi.jewelry_id is not None]
    part_items = [oi for oi in items if oi.part_id is not None]
```

Replace all subsequent uses of `items` (where it iterates jewelry items only — for BOM expansion, agg_qty, jewelry_stocks deduction, source_map) with `jewelry_items`. Keep the same logic.

After the existing `source_map` enrichment with jewelry names, add direct contributions:

```python
    # Add direct part contributions (customer-purchased parts)
    direct_part_qty: dict[str, int] = {}
    for pi in part_items:
        direct_part_qty[pi.part_id] = direct_part_qty.get(pi.part_id, 0) + pi.quantity
    for pid, dq in direct_part_qty.items():
        total_map[pid] = total_map.get(pid, 0) + dq
        source_map.setdefault(pid, []).append({
            "source_type": "direct",
            "jewelry_id": None,
            "jewelry_name": "",
            "qty_per_unit": None,
            "order_qty": dq,
            "subtotal": float(dq),
        })
    # Tag existing BOM-derived sources with source_type="jewelry"
    for entries in source_map.values():
        for entry in entries:
            entry.setdefault("source_type", "jewelry")
```

- [ ] **Step 5: Update `_calc_global_part_demand` in `services/order.py`**

Inside `_calc_global_part_demand`, after the `for jid, total in agg_qty.items():` loop that sums BOM demand, append:

```python
    # Add direct part purchases from active orders
    direct_rows = (
        db.query(OrderItem.part_id, sa_func.sum(OrderItem.quantity))
        .join(Order, OrderItem.order_id == Order.id)
        .filter(
            Order.status.notin_(["已完成", "已取消"]),
            OrderItem.part_id.in_(part_ids),
        )
        .group_by(OrderItem.part_id)
        .all()
    )
    for pid, qty in direct_rows:
        global_map[pid] = global_map.get(pid, 0) + float(qty)
```

`sa_func` is already imported at the top of the file.

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_service_order_part_items.py -v -k "summary"
```
Expected: PASS.

- [ ] **Step 7: Run TodoList regression suite**

```bash
pytest tests/test_api_order_todo.py -v
```
Expected: all pass — direct contributions don't affect jewelry-only orders.

- [ ] **Step 8: Commit**

```bash
git add services/order.py schemas/order.py tests/test_service_order_part_items.py
git commit -m "feat: TodoList aggregates direct part purchases alongside BOM demand"
```

---

## Task 8: Picking simulation includes direct part variants

**Files:**
- Modify: `services/picking.py` — `_collect_triples` to add direct part triples
- Test: `tests/test_api_picking.py` — append

- [ ] **Step 1: Append failing test**

```python
# tests/test_api_picking.py — append (use existing client/db fixtures style)
from sqlalchemy import text


def test_picking_includes_direct_part_variant(client, db):
    db.execute(text(
        "INSERT INTO part (id, name, unit, wholesale_price) "
        "VALUES ('PJ-PK1', 'chain', '米', 15)"
    ))
    db.commit()
    r = client.post("/api/orders/", json={
        "customer_name": "P",
        "items": [{"part_id": "PJ-PK1", "quantity": 7, "unit_price": 15}],
    })
    order_id = r.json()["id"]
    r = client.get(f"/api/orders/{order_id}/picking")
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert any(row["part_id"] == "PJ-PK1" for row in rows)
    row = next(r for r in rows if r["part_id"] == "PJ-PK1")
    assert row["is_composite_child"] is False
    assert any(v["qty_per_unit"] == 7.0 and v["units_count"] == 1 for v in row["variants"])
```

- [ ] **Step 2: Run test to verify failure**

```bash
pytest tests/test_api_picking.py::test_picking_includes_direct_part_variant -v
```
Expected: FAIL.

- [ ] **Step 3: Modify `_collect_triples` in `services/picking.py`**

Replace its body:

```python
def _collect_triples(db: Session, order_items: list[OrderItem]) -> list[_Triple]:
    """Return list of _Triple. Composite parts in a jewelry's BOM are expanded;
    direct part purchases are added as a single triple per part item with
    qty_per_unit=quantity, units_count=1, from_composite=False."""
    jewelry_items = [oi for oi in order_items if oi.jewelry_id is not None]
    part_items = [oi for oi in order_items if oi.part_id is not None]

    out: list[_Triple] = []

    # Direct part purchases — one variant per item
    for oi in part_items:
        out.append(_Triple(
            part_id=oi.part_id,
            qty_per_unit=float(oi.quantity),
            units_count=1,
            from_composite=False,
        ))

    if not jewelry_items:
        return out

    jewelry_ids = list({oi.jewelry_id for oi in jewelry_items})
    boms = db.query(Bom).filter(Bom.jewelry_id.in_(jewelry_ids)).all()
    bom_by_jewelry: dict[str, list[Bom]] = defaultdict(list)
    for b in boms:
        bom_by_jewelry[b.jewelry_id].append(b)

    direct_part_ids = list({b.part_id for bs in bom_by_jewelry.values() for b in bs})
    direct_parts = db.query(Part).filter(Part.id.in_(direct_part_ids)).all() if direct_part_ids else []
    is_composite = {p.id: p.is_composite for p in direct_parts}

    for oi in jewelry_items:
        for b in bom_by_jewelry.get(oi.jewelry_id, []):
            qpu_root = float(b.qty_per_unit)
            if is_composite.get(b.part_id):
                atoms = _expand_to_atoms(db, b.part_id, Decimal(str(b.qty_per_unit)))
                for atom_id, atom_qpu in atoms:
                    out.append(_Triple(
                        part_id=atom_id,
                        qty_per_unit=atom_qpu,
                        units_count=oi.quantity,
                        from_composite=True,
                    ))
            else:
                out.append(_Triple(
                    part_id=b.part_id,
                    qty_per_unit=qpu_root,
                    units_count=oi.quantity,
                    from_composite=False,
                ))
    return out
```

- [ ] **Step 4: Update `get_picking_simulation` empty-check**

Replace:
```python
    order_items = db.query(OrderItem).filter_by(order_id=order_id).all()
    if not order_items:
        return PickingSimulationResponse(...)
```

The empty check is fine — `_collect_triples` and `_build_rows` handle empty `triples` list. No change needed.

- [ ] **Step 5: Run test**

```bash
pytest tests/test_api_picking.py::test_picking_includes_direct_part_variant -v
```
Expected: PASS.

- [ ] **Step 6: Run picking regression suite**

```bash
pytest tests/test_api_picking.py -v
```
Expected: all pass — `_validate_variant_in_order` reuses `_collect_triples`, so it transparently accepts direct part variants for `mark_picked` / `unmark_picked`.

- [ ] **Step 7: Commit**

```bash
git add services/picking.py tests/test_api_picking.py
git commit -m "feat: picking simulation surfaces direct part purchases as variants"
```

---

## Task 9: Cost snapshot includes part items

**Files:**
- Modify: `models/order_cost_snapshot.py` — `OrderCostSnapshotItem` adds `part_id` (nullable), `jewelry_id` becomes nullable
- Modify: `database.py` — additive migration: drop NOT NULL on `jewelry_id`, add `part_id`
- Modify: `services/order_cost_snapshot.py` — `generate_cost_snapshot` handles part items
- Test: `tests/test_api_cost_snapshot.py` — append

- [ ] **Step 1: Inspect existing cost snapshot tests for fixtures**

```bash
grep -n "def test_" tests/test_api_cost_snapshot.py | head
```

- [ ] **Step 2: Append failing test**

```python
# tests/test_api_cost_snapshot.py — append
def test_cost_snapshot_includes_part_items(client, db):
    from sqlalchemy import text
    db.execute(text(
        "INSERT INTO part (id, name, unit_cost, wholesale_price) "
        "VALUES ('PJ-CS1', 'chain', 8, 15)"
    ))
    db.commit()
    # Stock the part so completion succeeds
    r = client.post("/api/inventory/", json={
        "item_type": "part", "item_id": "PJ-CS1",
        "change_qty": 100, "reason": "test",
    })
    assert r.status_code == 201
    r = client.post("/api/orders/", json={
        "customer_name": "X",
        "items": [{"part_id": "PJ-CS1", "quantity": 5, "unit_price": 15}],
    })
    order_id = r.json()["id"]
    r = client.patch(f"/api/orders/{order_id}/status", json={"status": "已完成"})
    assert r.status_code == 200
    r = client.get(f"/api/orders/{order_id}/cost-snapshot")
    snap = r.json()
    # 5 × 15 (price) - 5 × 8 (cost) = 35 profit
    assert snap is not None
    assert float(snap["total_amount"]) == 75.0
    assert float(snap["total_cost"]) == 40.0
    assert float(snap["profit"]) == 35.0
```

(Adjust `/api/inventory/` to actual endpoint; check existing test_api_inventory.py for the correct path.)

- [ ] **Step 3: Run test to verify failure**

```bash
pytest tests/test_api_cost_snapshot.py::test_cost_snapshot_includes_part_items -v
```
Expected: FAIL — `generate_cost_snapshot` raises `没有饰品明细` for part-only orders.

- [ ] **Step 4: Update `OrderCostSnapshotItem` model**

```python
# models/order_cost_snapshot.py — modify OrderCostSnapshotItem
class OrderCostSnapshotItem(Base):
    __tablename__ = "order_cost_snapshot_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(Integer, ForeignKey("order_cost_snapshot.id"), nullable=False)
    jewelry_id = Column(String, nullable=True)              # was nullable=False
    jewelry_name = Column(String, nullable=True)
    part_id = Column(String, nullable=True)                 # NEW
    part_name = Column(String, nullable=True)               # NEW
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(18, 7), nullable=True)
    handcraft_cost = Column(Numeric(18, 7), nullable=True)
    jewelry_unit_cost = Column(Numeric(18, 7), nullable=True)   # was nullable=False
    jewelry_total_cost = Column(Numeric(18, 7), nullable=True)  # was nullable=False
    bom_details_raw = Column("bom_details", Text, nullable=True)
    # ... existing bom_details property/setter unchanged
```

- [ ] **Step 5: Add migration block to `database.py`**

Insert into `ensure_schema_compat()`:

```python
        # --- order_cost_snapshot_item: part_id columns + nullability ---
        if inspector.has_table("order_cost_snapshot_item"):
            cols = {c["name"]: c for c in inspector.get_columns("order_cost_snapshot_item")}
            if "part_id" not in cols:
                conn.execute(text(
                    "ALTER TABLE order_cost_snapshot_item ADD COLUMN part_id VARCHAR NULL"
                ))
                logger.warning("Added missing order_cost_snapshot_item.part_id column")
            if "part_name" not in cols:
                conn.execute(text(
                    "ALTER TABLE order_cost_snapshot_item ADD COLUMN part_name VARCHAR NULL"
                ))
                logger.warning("Added missing order_cost_snapshot_item.part_name column")
            for col_name in ("jewelry_id", "jewelry_unit_cost", "jewelry_total_cost"):
                if cols.get(col_name) and cols[col_name]["nullable"] is False:
                    conn.execute(text(
                        f"ALTER TABLE order_cost_snapshot_item "
                        f"ALTER COLUMN {col_name} DROP NOT NULL"
                    ))
                    logger.warning("Made order_cost_snapshot_item.%s nullable", col_name)
```

- [ ] **Step 6: Update `generate_cost_snapshot`**

Replace function body:

```python
def generate_cost_snapshot(db: Session, order_id: str) -> OrderCostSnapshot:
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None:
        raise ValueError(f"Order not found: {order_id}")

    items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
    if not items:
        raise ValueError(f"订单 {order_id} 没有任何明细")

    jewelry_items = [i for i in items if i.jewelry_id is not None]
    part_items = [i for i in items if i.part_id is not None]

    # --- Jewelry section: existing behavior ---
    jewelry_ids = list({i.jewelry_id for i in jewelry_items})
    jewelries = db.query(Jewelry).filter(Jewelry.id.in_(jewelry_ids)).all() if jewelry_ids else []
    jewelry_map = {j.id: j for j in jewelries}
    all_bom = db.query(Bom).filter(Bom.jewelry_id.in_(jewelry_ids)).all() if jewelry_ids else []
    bom_by_jewelry: dict[str, list] = {}
    bom_part_ids = set()
    for b in all_bom:
        bom_by_jewelry.setdefault(b.jewelry_id, []).append(b)
        bom_part_ids.add(b.part_id)

    # --- Part section: load part details ---
    direct_part_ids = list({i.part_id for i in part_items})
    all_part_ids = bom_part_ids | set(direct_part_ids)
    part_map = {}
    if all_part_ids:
        for p in db.query(Part).filter(Part.id.in_(list(all_part_ids))).all():
            part_map[p.id] = p

    for item in jewelry_items:
        if not bom_by_jewelry.get(item.jewelry_id):
            jewelry = jewelry_map.get(item.jewelry_id)
            name = jewelry.name if jewelry else item.jewelry_id
            raise ValueError(f"饰品「{name}」({item.jewelry_id}) 没有 BOM，无法生成成本快照")

    has_incomplete = False
    total_cost = Decimal(0)
    snapshot_items: list[dict] = []

    # Jewelry rows
    for item in jewelry_items:
        jewelry = jewelry_map.get(item.jewelry_id)
        bom_rows = bom_by_jewelry.get(item.jewelry_id, [])
        bom_cost = Decimal(0)
        bom_details = []
        for row in bom_rows:
            part = part_map.get(row.part_id)
            part_unit_cost = Decimal(str(part.unit_cost or 0)) if part else Decimal(0)
            if part and part.unit_cost is None:
                has_incomplete = True
            qty_per_unit = Decimal(str(row.qty_per_unit))
            subtotal = (part_unit_cost * qty_per_unit).quantize(_Q7, rounding=ROUND_HALF_UP)
            bom_cost += subtotal
            bom_details.append({
                "part_id": row.part_id,
                "part_name": part.name if part else None,
                "unit_cost": float(part_unit_cost),
                "qty_per_unit": float(qty_per_unit),
                "subtotal": float(subtotal),
            })
        hc_cost = Decimal(str(jewelry.handcraft_cost or 0)) if jewelry else Decimal(0)
        jewelry_unit_cost = (bom_cost + hc_cost).quantize(_Q7, rounding=ROUND_HALF_UP)
        jewelry_total_cost = (jewelry_unit_cost * item.quantity).quantize(_Q7, rounding=ROUND_HALF_UP)
        total_cost += jewelry_total_cost
        snapshot_items.append({
            "jewelry_id": item.jewelry_id,
            "jewelry_name": jewelry.name if jewelry else None,
            "part_id": None,
            "part_name": None,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price) if item.unit_price is not None else None,
            "handcraft_cost": float(hc_cost),
            "jewelry_unit_cost": float(jewelry_unit_cost),
            "jewelry_total_cost": float(jewelry_total_cost),
            "bom_details": bom_details,
        })

    # Part rows
    for item in part_items:
        part = part_map.get(item.part_id)
        unit_cost = Decimal(str(part.unit_cost or 0)) if part else Decimal(0)
        if part and part.unit_cost is None:
            has_incomplete = True
        line_cost = (unit_cost * item.quantity).quantize(_Q7, rounding=ROUND_HALF_UP)
        total_cost += line_cost
        snapshot_items.append({
            "jewelry_id": None,
            "jewelry_name": None,
            "part_id": item.part_id,
            "part_name": part.name if part else None,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price) if item.unit_price is not None else None,
            "handcraft_cost": 0.0,
            "jewelry_unit_cost": float(unit_cost),
            "jewelry_total_cost": float(line_cost),
            "bom_details": [],
        })

    pkg_cost = Decimal(str(order.packaging_cost or 0))
    total_cost = (total_cost + pkg_cost).quantize(_Q7, rounding=ROUND_HALF_UP)
    total_amount = Decimal(str(order.total_amount or 0))
    profit = (total_amount - total_cost).quantize(_Q7, rounding=ROUND_HALF_UP)

    snapshot = OrderCostSnapshot(
        order_id=order_id,
        total_cost=total_cost,
        packaging_cost=pkg_cost if order.packaging_cost is not None else None,
        total_amount=order.total_amount,
        profit=profit,
        has_incomplete_cost=1 if has_incomplete else 0,
    )
    db.add(snapshot)
    db.flush()
    for si in snapshot_items:
        bom_details = si.pop("bom_details")
        item_obj = OrderCostSnapshotItem(snapshot_id=snapshot.id, **si)
        item_obj.bom_details = bom_details
        db.add(item_obj)
    db.flush()
    return snapshot
```

- [ ] **Step 7: Update `OrderCostSnapshotResponse` schema if it strictly types `jewelry_id`**

Inspect `schemas/order_cost_snapshot.py`:

```bash
grep -n "jewelry" schemas/order_cost_snapshot.py
```

If it has non-Optional `jewelry_id` / `jewelry_unit_cost` etc. on item response, change to `Optional[...]`. Add `part_id: Optional[str] = None`, `part_name: Optional[str] = None`.

- [ ] **Step 8: Run tests**

```bash
pytest tests/test_api_cost_snapshot.py -v
```
Expected: PASS (new test + existing).

- [ ] **Step 9: Commit**

```bash
git add models/order_cost_snapshot.py database.py services/order_cost_snapshot.py schemas/order_cost_snapshot.py tests/test_api_cost_snapshot.py
git commit -m "feat: cost snapshot includes part-item rows"
```

---

## Task 10: API enrichment — return part_name / part_image / part_unit on OrderItem responses

**Files:**
- Modify: `api/orders.py` — `api_get_order_items` and `api_add_order_item` and `api_update_order_item` enrich part items
- Test: `tests/test_api_orders.py` — verify enrichment

- [ ] **Step 1: Append failing test**

```python
# tests/test_api_orders.py — append
def test_get_order_items_enriches_part_info(client, db):
    from sqlalchemy import text
    db.execute(text(
        "INSERT INTO part (id, name, unit, image, wholesale_price) "
        "VALUES ('PJ-EN1', '玫瑰金链', '米', '/images/chain.png', 15)"
    ))
    db.commit()
    r = client.post("/api/orders/", json={
        "customer_name": "E",
        "items": [{"part_id": "PJ-EN1", "quantity": 3, "unit_price": 15}],
    })
    order_id = r.json()["id"]
    r = client.get(f"/api/orders/{order_id}/items")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    item = items[0]
    assert item["part_id"] == "PJ-EN1"
    assert item["jewelry_id"] is None
    assert item["part_name"] == "玫瑰金链"
    assert item["part_unit"] == "米"
    assert item["part_image"] == "/images/chain.png"
```

- [ ] **Step 2: Run test to verify failure**

```bash
pytest tests/test_api_orders.py::test_get_order_items_enriches_part_info -v
```
Expected: FAIL — fields are `None`.

- [ ] **Step 3: Add enrichment helper in `api/orders.py`**

After imports, add:

```python
def _enrich_items(db: Session, items: list) -> list:
    """Attach part_name / part_image / part_unit for part-typed items."""
    from models.part import Part
    part_ids = [i.part_id for i in items if i.part_id is not None]
    if not part_ids:
        return items
    parts = {p.id: p for p in db.query(Part).filter(Part.id.in_(part_ids)).all()}
    enriched = []
    for it in items:
        if it.part_id is None:
            enriched.append(it)
            continue
        p = parts.get(it.part_id)
        # Build dict with all OrderItem fields + enrichment
        d = {
            "id": it.id, "order_id": it.order_id,
            "jewelry_id": it.jewelry_id, "part_id": it.part_id,
            "quantity": it.quantity, "unit_price": float(it.unit_price),
            "remarks": it.remarks, "customer_code": it.customer_code,
            "part_name": p.name if p else None,
            "part_image": p.image if p else None,
            "part_unit": p.unit if p else None,
        }
        enriched.append(d)
    return enriched
```

- [ ] **Step 4: Wrap response in the three endpoints**

Update `api_get_order_items`, `api_add_order_item`, `api_update_order_item` to enrich:

```python
@router.get("/{order_id}/items", response_model=list[OrderItemResponse])
def api_get_order_items(order_id: str, db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    items = get_order_items(db, order_id)
    return _enrich_items(db, items)


@router.post("/{order_id}/items", response_model=OrderItemResponse, status_code=201)
def api_add_order_item(order_id: str, body: OrderItemCreate, db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        item = add_order_item(db, order_id, body.model_dump())
    return _enrich_items(db, [item])[0]


@router.patch("/{order_id}/items/{item_id}", response_model=OrderItemResponse)
def api_update_order_item(order_id: str, item_id: int, body: OrderItemUpdate, db: Session = Depends(get_db)):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="请提供至少一个要修改的字段")
    with service_errors():
        item = update_order_item(db, order_id, item_id, fields)
    return _enrich_items(db, [item])[0]
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_api_orders.py::test_get_order_items_enriches_part_info -v
```
Expected: PASS.

- [ ] **Step 6: Run regression suite**

```bash
pytest tests/test_api_orders.py -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add api/orders.py tests/test_api_orders.py
git commit -m "feat: enrich part fields on OrderItem API responses"
```

---

## Task 11: Frontend — `OrderCreate.vue` split jewelry / parts cards

**Files:**
- Modify: `frontend/src/views/orders/OrderCreate.vue` — split into two cards
- Modify or Create: `frontend/src/api/parts.js` — ensure `listParts({ status })` exists (likely already does)

- [ ] **Step 1: Verify part list API helper exists**

```bash
grep -n "listParts\|export" frontend/src/api/parts.js | head -5
```

If `listParts` is missing, add:

```js
// frontend/src/api/parts.js — append if missing
export const listParts = (params) => http.get('/parts', { params })
```

- [ ] **Step 2: Replace `frontend/src/views/orders/OrderCreate.vue`**

```vue
<template>
  <div :style="{ maxWidth: isMobile ? '100%' : '900px' }">
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">新建订单</n-h2>
    </n-space>

    <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="90" style="margin-bottom: 16px;">
      <n-form-item label="客户名">
        <n-input v-model:value="customerName" placeholder="请输入客户名称" :style="{ width: isMobile ? '100%' : '300px' }" />
      </n-form-item>
      <n-form-item label="创建时间">
        <n-date-picker
          v-model:value="createdAtTs"
          type="date"
          clearable
          placeholder="不填则使用当前时间"
          :style="{ width: isMobile ? '100%' : '300px' }"
        />
      </n-form-item>
    </n-form>

    <!-- Jewelry section -->
    <n-card style="margin-bottom: 16px;">
      <template #header>
        <n-space justify="space-between" align="center" style="width: 100%;">
          <span>💎 饰品明细 <n-text depth="3" style="font-size: 13px;">({{ jewelryItems.length }} 项)</n-text></span>
          <n-space align="center">
            <n-text depth="3" style="font-size: 13px;">小计 ¥{{ fmtMoney(jewelrySubtotal) }}</n-text>
            <n-button type="primary" size="small" @click="addJewelryLine">+ 添加饰品</n-button>
          </n-space>
        </n-space>
      </template>
      <div v-for="(item, idx) in jewelryItems" :key="`j-${idx}`" style="margin-bottom: 12px;">
        <n-space align="center">
          <n-select
            v-model:value="item.jewelry_id"
            :options="jewelryOptions"
            :render-label="renderOptionWithImage"
            filterable clearable
            placeholder="选择饰品"
            :style="{ width: isMobile ? '100%' : '220px' }"
            @update:value="(v) => onJewelrySelect(idx, v)"
          />
          <n-input-number v-model:value="item.quantity" :min="1" placeholder="数量" style="width: 90px;" />
          <n-input-number v-model:value="item.unit_price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" placeholder="单价" style="width: 120px;" />
          <n-input v-model:value="item.remarks" placeholder="备注" style="width: 160px;" />
          <n-button type="error" size="small" @click="jewelryItems.splice(idx, 1)">删除</n-button>
        </n-space>
      </div>
      <n-text v-if="jewelryItems.length === 0" depth="3">点击右上角 "+ 添加饰品" 开始</n-text>
    </n-card>

    <!-- Parts section -->
    <n-card style="margin-bottom: 16px;">
      <template #header>
        <n-space justify="space-between" align="center" style="width: 100%;">
          <span>🔧 配件明细 <n-text depth="3" style="font-size: 13px;">({{ partItems.length }} 项)</n-text></span>
          <n-space align="center">
            <n-text depth="3" style="font-size: 13px;">小计 ¥{{ fmtMoney(partSubtotal) }}</n-text>
            <n-button type="primary" size="small" @click="addPartLine">+ 添加配件</n-button>
          </n-space>
        </n-space>
      </template>
      <div v-for="(item, idx) in partItems" :key="`p-${idx}`" style="margin-bottom: 12px;">
        <n-space align="center">
          <n-select
            v-model:value="item.part_id"
            :options="partOptions"
            :render-label="renderOptionWithImage"
            filterable clearable
            placeholder="选择配件"
            :style="{ width: isMobile ? '100%' : '220px' }"
            @update:value="(v) => onPartSelect(idx, v)"
          />
          <n-input-number v-model:value="item.quantity" :min="1" placeholder="数量" style="width: 90px;" />
          <n-input-number v-model:value="item.unit_price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" placeholder="单价" style="width: 120px;" />
          <n-input v-model:value="item.remarks" placeholder="备注" style="width: 160px;" />
          <n-button type="error" size="small" @click="partItems.splice(idx, 1)">删除</n-button>
        </n-space>
      </div>
      <n-text v-if="partItems.length === 0" depth="3">点击右上角 "+ 添加配件" 开始</n-text>
    </n-card>

    <n-space justify="space-between" align="center">
      <n-text>合计：<n-text style="font-size: 18px; font-weight: 600; color: #FF0000;">
        ¥{{ fmtMoney(total) }}
      </n-text></n-text>
      <n-button type="primary" :loading="submitting" @click="submit">提交订单</n-button>
    </n-space>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem, NCard, NText, NH2, NDatePicker } from 'naive-ui'
import { listJewelries } from '@/api/jewelries'
import { listParts } from '@/api/parts'
import { createOrder } from '@/api/orders'
import { renderOptionWithImage, fmtMoney, fmtPrice, parseNum } from '@/utils/ui'
import { tsToDateStr } from '@/utils/date'
import { useIsMobile } from '@/composables/useIsMobile'

const router = useRouter()
const message = useMessage()
const { isMobile } = useIsMobile()

const customerName = ref('')
const createdAtTs = ref(null)
const jewelryItems = reactive([])
const partItems = reactive([])
const submitting = ref(false)

const jewelryMap = ref({})
const jewelryOptions = ref([])
const partMap = ref({})
const partOptions = ref([])

const addJewelryLine = () =>
  jewelryItems.push({ jewelry_id: null, quantity: 1, unit_price: 0, remarks: '' })

const addPartLine = () =>
  partItems.push({ part_id: null, quantity: 1, unit_price: 0, remarks: '' })

const onJewelrySelect = (idx, jewelryId) => {
  if (!jewelryId) { jewelryItems[idx].unit_price = 0; return }
  jewelryItems[idx].unit_price = jewelryMap.value[jewelryId]?.wholesale_price ?? 0
}

const onPartSelect = (idx, partId) => {
  if (!partId) { partItems[idx].unit_price = 0; return }
  partItems[idx].unit_price = partMap.value[partId]?.wholesale_price ?? 0
}

const jewelrySubtotal = computed(() =>
  jewelryItems.reduce((s, i) => s + (i.quantity || 0) * (i.unit_price || 0), 0)
)
const partSubtotal = computed(() =>
  partItems.reduce((s, i) => s + (i.quantity || 0) * (i.unit_price || 0), 0)
)
const total = computed(() => jewelrySubtotal.value + partSubtotal.value)

const submit = async () => {
  if (!customerName.value) { message.warning('请输入客户名称'); return }
  if (jewelryItems.length === 0 && partItems.length === 0) {
    message.warning('请添加订单明细'); return
  }
  if (jewelryItems.some((i) => !i.jewelry_id)) { message.warning('请选择饰品'); return }
  if (partItems.some((i) => !i.part_id)) { message.warning('请选择配件'); return }

  const items = [
    ...jewelryItems.map(i => ({ jewelry_id: i.jewelry_id, quantity: i.quantity, unit_price: i.unit_price, remarks: i.remarks })),
    ...partItems.map(i => ({ part_id: i.part_id, quantity: i.quantity, unit_price: i.unit_price, remarks: i.remarks })),
  ]
  submitting.value = true
  try {
    const payload = { customer_name: customerName.value, items }
    const createdAt = tsToDateStr(createdAtTs.value)
    if (createdAt) payload.created_at = createdAt
    const { data } = await createOrder(payload)
    message.success('订单创建成功')
    router.push(`/orders/${data.id}`)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  const [{ data: jData }, { data: pData }] = await Promise.all([
    listJewelries({ status: 'active' }),
    listParts({}),
  ])
  jData.forEach((j) => { jewelryMap.value[j.id] = j })
  jewelryOptions.value = jData.map((j) => ({
    label: `${j.id} ${j.name}`, value: j.id, code: j.id, name: j.name, image: j.image,
  }))
  pData.forEach((p) => { partMap.value[p.id] = p })
  partOptions.value = pData.map((p) => ({
    label: `${p.id} ${p.name}`, value: p.id, code: p.id, name: p.name, image: p.image,
  }))
})
</script>
```

- [ ] **Step 3: Run dev server and visually verify**

```bash
# Terminal 1
python main.py
# Terminal 2
cd frontend && npm run dev
```

Open `http://localhost:5173/orders/new`. Verify:
- Two cards visible (饰品 / 配件)
- "+ 添加" buttons in upper-right of each card
- Adding only parts works
- Adding mixed works
- Submitting creates order

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/orders/OrderCreate.vue frontend/src/api/parts.js
git commit -m "feat: OrderCreate splits jewelry / parts into separate cards"
```

---

## Task 12: Frontend — `OrderDetail.vue` split jewelry / parts cards

**Files:**
- Modify: `frontend/src/views/orders/OrderDetail.vue`

- [ ] **Step 1: Inspect existing OrderDetail.vue**

```bash
wc -l frontend/src/views/orders/OrderDetail.vue
grep -n "items\|customer_code\|jewelry_id" frontend/src/views/orders/OrderDetail.vue | head -30
```

- [ ] **Step 2: Modify the items rendering**

In OrderDetail.vue, locate the section where `items` are rendered (typically a `<n-data-table>` or v-for). Split into two computed lists:

```js
const jewelryItems = computed(() => items.value.filter(i => i.jewelry_id !== null))
const partItems = computed(() => items.value.filter(i => i.part_id !== null))
```

Render two cards mirroring OrderCreate.vue layout:
- Jewelry card: keep existing customer_code column, batch-fill button, all current behavior
- Part card: NO customer_code column; columns are 配件 (id + name + image) / 数量 / 单价 / 小计 / 备注 / 操作

For the part card "+ 添加配件" button, reuse the same picker pattern from OrderCreate.vue, then call `POST /orders/{id}/items` with `{ part_id, quantity, unit_price, remarks }`.

For unit_price PATCH: existing PATCH endpoint works for both — server writes back `part.wholesale_price` automatically.

- [ ] **Step 3: Manual verification**

Open existing order with mixed items in browser. Verify:
- Both cards display correctly
- Editing jewelry item quantity/price works as before
- Adding a part to existing order works
- Editing part unit_price persists and reflects new wholesale_price next time the part is loaded
- Customer code batch-fill button only operates on jewelry items (server now enforces this; UI should not present it for parts)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/orders/OrderDetail.vue
git commit -m "feat: OrderDetail splits jewelry / parts into separate cards"
```

---

## Task 13: Frontend — TodoList view shows direct part source

**Files:**
- Modify: frontend view that renders `parts-summary` (likely `frontend/src/views/orders/OrderDetail.vue` or a child component, possibly `OrderTodoList.vue`)

- [ ] **Step 1: Locate the source_jewelries renderer**

```bash
grep -rn "source_jewelries\|source_type" frontend/src/views/orders/ frontend/src/components/ | head
```

- [ ] **Step 2: Update rendering**

Wherever the source list is rendered, add a branch on `source_type`:

```vue
<template v-for="src in row.source_jewelries" :key="src.jewelry_id ?? 'direct'">
  <div v-if="src.source_type === 'direct'">
    客户直购 × {{ src.order_qty }}
  </div>
  <div v-else>
    {{ src.jewelry_name }} ({{ src.qty_per_unit }} × {{ src.order_qty }})
  </div>
</template>
```

Adjust to actual existing markup style.

- [ ] **Step 3: Manual verification**

Create a mixed order; open TodoList; verify a part appearing in both BOM and direct shows two source rows.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/  # specific path(s)
git commit -m "feat: TodoList shows 客户直购 source rows"
```

---

## Task 14: Frontend — Verify picking simulation handles direct part variants

**Files:**
- Verify only — no code change expected unless visual gap appears

- [ ] **Step 1: Manual verification**

Create part-only order; open `/orders/{id}/picking`; verify the part appears as a row with one variant (`qty_per_unit` = ordered qty, `units_count` = 1). Marking and unmarking should work via existing UI.

- [ ] **Step 2: If UI hides rows where `is_composite_child=false` and no BOM context, add explicit handling**

Otherwise no commit needed for this task.

---

## Task 15: End-to-end smoke + final regression

- [ ] **Step 1: Run full backend test suite**

```bash
pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 2: Manual end-to-end smoke**

In dev environment:
1. Create part `PJ-LT-99` with `wholesale_price=15`, stock 100 via 入库.
2. Create jewelry `SP-99` with BOM containing `PJ-LT-99 × 3`, stock 0.
3. Create order: 1 × `SP-99` + 5 × `PJ-LT-99` directly. Verify total = jewelry price + 75.
4. Open TodoList — verify `PJ-LT-99` shows demand 8 with two sources (BOM 3 + direct 5).
5. Open picking simulation — verify two variants under `PJ-LT-99`.
6. Create handcraft order from batch (only jewelry section participates) — direct part 5 should NOT appear in handcraft.
7. Receive jewelry back from handcraft.
8. Mark order 已完成 — verify `PJ-LT-99` stock decreases by 5 (just direct; BOM portion already consumed via handcraft).
9. Cost snapshot — verify it includes one part item line.
10. Mark order 已取消 — verify `PJ-LT-99` stock restored.

- [ ] **Step 3: Final commit (only if any fix-up needed)**

If any fix was made during smoke test, commit it:

```bash
git add -p
git commit -m "fix: <specific issue found in smoke test>"
```

---

## Self-Review Checklist (run before handing off)

- [x] Spec section 1 (需求总览) — all 8 decisions wired into tasks 1, 4, 5, 7, 11
- [x] Spec section 2 (数据模型) — Task 1
- [x] Spec section 3 (Service 层) — Tasks 4, 5, 6, 7, 8, 9
- [x] Spec section 4 (API + Schema) — Tasks 2, 3, 10
- [x] Spec section 5 (前端) — Tasks 11, 12, 13, 14
- [x] Spec section 6 (边界情况 & 错误处理) — covered by Tasks 5 (stock), 6 (customer_code), 7 (TodoList merge), 1 (DB CHECK)
- [x] Spec section 7 (测试) — every code task includes tests; Task 15 runs final regression
