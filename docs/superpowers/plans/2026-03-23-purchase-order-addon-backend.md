# 采购单附加费用（后端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `purchase_order_item_addon` table and CRUD API for per-item addon costs (first type: bead stringing), with automatic total recalculation.

**Architecture:** New `PurchaseOrderItemAddon` model with FK to `PurchaseOrderItem`, cascade delete-orphan. Service functions follow existing stateless pattern (flush, no commit). `_recalc_total` extended to include addon amounts.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, Pydantic v2, pytest

**Spec:** `docs/superpowers/specs/2026-03-23-purchase-order-addon-cost-design.md`

---

### Task 1: Model — `PurchaseOrderItemAddon`

**Files:**
- Modify: `models/purchase_order.py:40-51` (add relationship to `PurchaseOrderItem`, add new class)
- Modify: `models/__init__.py` (add import + `__all__` entry)

- [ ] **Step 1: Add `PurchaseOrderItemAddon` model to `models/purchase_order.py`**

After the existing `PurchaseOrderItem` class, add:

```python
class PurchaseOrderItemAddon(Base):
    __tablename__ = "purchase_order_item_addon"
    __table_args__ = (
        UniqueConstraint("purchase_order_item_id", "type", name="uq_po_item_addon_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_order_item_id = Column(Integer, ForeignKey("purchase_order_item.id"), nullable=False)
    type = Column(String, nullable=False)
    qty = Column(Numeric(10, 4), nullable=False)
    unit = Column(String, nullable=True)
    price = Column(Numeric(18, 7), nullable=False)
    amount = Column(Numeric(18, 7), nullable=False)
    unit_cost = Column(Numeric(18, 7), nullable=False)
```

Add import for `UniqueConstraint` from `sqlalchemy`:

```python
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
```

Add relationship on `PurchaseOrderItem`:

```python
addons = relationship("PurchaseOrderItemAddon", backref="purchase_order_item", cascade="all, delete-orphan", lazy="select")
```

- [ ] **Step 2: Register in `models/__init__.py`**

Add `PurchaseOrderItemAddon` to the import line and `__all__` list:

```python
from .purchase_order import PurchaseOrder, PurchaseOrderItem, PurchaseOrderItemAddon
```

```python
__all__ = [
    ...
    "PurchaseOrderItemAddon",
]
```

- [ ] **Step 3: Verify table creation**

Run: `python -c "from models import *; print('OK')"`
Expected: `OK` (no import errors)

- [ ] **Step 4: Commit**

```bash
git add models/purchase_order.py models/__init__.py
git commit -m "feat: add PurchaseOrderItemAddon model"
```

---

### Task 2: Schemas — addon create/update/response

**Files:**
- Modify: `schemas/purchase_order.py`

- [ ] **Step 1: Add addon schemas to `schemas/purchase_order.py`**

Add before the response schemas:

```python
class PurchaseOrderItemAddonCreate(BaseModel):
    type: str
    qty: float = Field(gt=0)
    unit: Optional[str] = None
    price: float = Field(ge=0)


class PurchaseOrderItemAddonUpdate(BaseModel):
    qty: Optional[float] = Field(None, gt=0)
    price: Optional[float] = Field(None, ge=0)
```

Add response schema (before `PurchaseOrderItemResponse`):

```python
class PurchaseOrderItemAddonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purchase_order_item_id: int
    type: str
    qty: float
    unit: Optional[str] = None
    price: float
    amount: float
    unit_cost: float
```

Modify `PurchaseOrderItemResponse` to include `addons`:

```python
class PurchaseOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purchase_order_id: str
    part_id: str
    qty: float
    unit: Optional[str] = None
    price: Optional[float] = None
    amount: Optional[float] = None
    note: Optional[str] = None
    addons: list[PurchaseOrderItemAddonResponse] = Field(default_factory=list)
```

- [ ] **Step 2: Commit**

```bash
git add schemas/purchase_order.py
git commit -m "feat: add addon schemas for purchase order items"
```

---

### Task 3: Service — addon CRUD + recalc_total update

**Files:**
- Modify: `services/purchase_order.py:1-32` (imports, `_recalc_total`)
- Modify: `services/purchase_order.py` (add new functions at end)

- [ ] **Step 1: Write failing tests for addon CRUD**

Create tests in `tests/test_purchase_order_addon.py`:

```python
import pytest
from decimal import Decimal

from services.purchase_order import (
    create_purchase_order,
    create_purchase_item_addon,
    update_purchase_item_addon,
    delete_purchase_item_addon,
    get_purchase_order,
)


@pytest.fixture
def part(db):
    """Create a part for purchase order items to reference."""
    from models.part import Part
    p = Part(id="PJ-DZ-00001", name="测试配件", category="吊坠")
    db.add(p)
    db.flush()
    return p


@pytest.fixture
def order_and_item(db, part):
    order = create_purchase_order(
        db,
        vendor_name="测试商家",
        items=[{"part_id": part.id, "qty": 200, "unit": "条", "price": 5.0}],
    )
    return order, order.items[0]


def test_create_addon(db, order_and_item):
    order, item = order_and_item
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    assert addon.type == "bead_stringing"
    assert addon.qty == 10
    assert addon.price == Decimal("3")
    assert addon.amount == Decimal("30")
    # unit_cost = 30 / 200 = 0.15
    assert addon.unit_cost == Decimal("0.15")


def test_create_addon_updates_total(db, order_and_item):
    order, item = order_and_item
    original_total = float(order.total_amount)  # 200 * 5 = 1000
    create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    refreshed = get_purchase_order(db, order.id)
    assert float(refreshed.total_amount) == original_total + 30


def test_create_addon_duplicate_type_rejected(db, order_and_item):
    order, item = order_and_item
    create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    with pytest.raises(ValueError, match="已存在"):
        create_purchase_item_addon(
            db, order.id, item.id, type="bead_stringing", qty=5, unit="条", price=2.0,
        )


def test_create_addon_paid_order_rejected(db, order_and_item):
    order, item = order_and_item
    from services.purchase_order import update_purchase_order_status
    update_purchase_order_status(db, order.id, "已付款")
    with pytest.raises(ValueError, match="已付款"):
        create_purchase_item_addon(
            db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
        )


def test_update_addon(db, order_and_item):
    order, item = order_and_item
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    updated = update_purchase_item_addon(db, order.id, item.id, addon.id, qty=20, price=4.0)
    assert updated.qty == 20
    assert updated.price == Decimal("4")
    assert updated.amount == Decimal("80")
    # unit_cost = 80 / 200 = 0.4
    assert updated.unit_cost == Decimal("0.4")


def test_update_addon_updates_total(db, order_and_item):
    order, item = order_and_item
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    update_purchase_item_addon(db, order.id, item.id, addon.id, qty=20, price=4.0)
    refreshed = get_purchase_order(db, order.id)
    # item: 1000 + addon: 80 = 1080
    assert float(refreshed.total_amount) == 1080


def test_delete_addon(db, order_and_item):
    order, item = order_and_item
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    delete_purchase_item_addon(db, order.id, item.id, addon.id)
    refreshed = get_purchase_order(db, order.id)
    assert float(refreshed.total_amount) == 1000  # back to original
    assert len(refreshed.items[0].addons) == 0


def test_delete_addon_paid_rejected(db, order_and_item):
    order, item = order_and_item
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    from services.purchase_order import update_purchase_order_status
    update_purchase_order_status(db, order.id, "已付款")
    with pytest.raises(ValueError, match="已付款"):
        delete_purchase_item_addon(db, order.id, item.id, addon.id)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_purchase_order_addon.py -v`
Expected: FAIL (ImportError — functions don't exist yet)

- [ ] **Step 3: Update `_recalc_total` in `services/purchase_order.py`**

Change lines 29-32 from:

```python
def _recalc_total(db: Session, order: PurchaseOrder) -> None:
    items = get_purchase_items(db, order.id)
    total = sum(Decimal(str(item.amount or 0)) for item in items)
    order.total_amount = total
```

To:

```python
def _recalc_total(db: Session, order: PurchaseOrder) -> None:
    items = get_purchase_items(db, order.id)
    total = sum(Decimal(str(item.amount or 0)) for item in items)
    addon_total = sum(
        Decimal(str(a.amount or 0)) for item in items for a in item.addons
    )
    order.total_amount = total + addon_total
```

- [ ] **Step 4: Add addon CRUD functions to `services/purchase_order.py`**

Add import at top:

```python
from models.purchase_order import PurchaseOrder, PurchaseOrderItem, PurchaseOrderItemAddon
```

Add helper and CRUD functions at the end of the file:

```python
def _get_order_and_item(db: Session, order_id: str, item_id: int):
    """Validate order is not paid, return (order, item). Raises ValueError on failure."""
    order = get_purchase_order(db, order_id)
    if order is None:
        raise ValueError(f"采购单 {order_id} 不存在")
    if order.status == "已付款":
        raise ValueError("已付款状态不允许操作附加费用")
    item = db.get(PurchaseOrderItem, item_id)
    if item is None or item.purchase_order_id != order_id:
        raise ValueError(f"明细 {item_id} 不存在")
    return order, item


def create_purchase_item_addon(
    db: Session, order_id: str, item_id: int, *,
    type: str, qty: float, unit: str | None = None, price: float,
) -> PurchaseOrderItemAddon:
    order, item = _get_order_and_item(db, order_id, item_id)

    existing = db.query(PurchaseOrderItemAddon).filter_by(
        purchase_order_item_id=item_id, type=type
    ).first()
    if existing:
        raise ValueError(f"该配件已存在类型为 {type} 的附加费用")

    qty_d = Decimal(str(qty))
    price_d = Decimal(str(price)).quantize(_Q7, rounding=ROUND_HALF_UP)
    amount_d = (qty_d * price_d).quantize(_Q7, rounding=ROUND_HALF_UP)
    item_qty_d = Decimal(str(item.qty))
    unit_cost_d = (amount_d / item_qty_d).quantize(_Q7, rounding=ROUND_HALF_UP) if item_qty_d else Decimal("0")

    addon = PurchaseOrderItemAddon(
        purchase_order_item_id=item_id,
        type=type,
        qty=qty_d,
        unit=unit,
        price=price_d,
        amount=amount_d,
        unit_cost=unit_cost_d,
    )
    db.add(addon)
    db.flush()
    _recalc_total(db, order)
    db.flush()
    return addon


def update_purchase_item_addon(
    db: Session, order_id: str, item_id: int, addon_id: int, *,
    qty: float | None = None, price: float | None = None,
) -> PurchaseOrderItemAddon:
    order, item = _get_order_and_item(db, order_id, item_id)

    addon = db.get(PurchaseOrderItemAddon, addon_id)
    if addon is None or addon.purchase_order_item_id != item_id:
        raise ValueError(f"附加费用 {addon_id} 不存在")

    if qty is not None:
        addon.qty = Decimal(str(qty))
    if price is not None:
        addon.price = Decimal(str(price)).quantize(_Q7, rounding=ROUND_HALF_UP)

    addon.amount = (Decimal(str(addon.qty)) * Decimal(str(addon.price))).quantize(_Q7, rounding=ROUND_HALF_UP)
    item_qty_d = Decimal(str(item.qty))
    addon.unit_cost = (addon.amount / item_qty_d).quantize(_Q7, rounding=ROUND_HALF_UP) if item_qty_d else Decimal("0")

    db.flush()
    _recalc_total(db, order)
    db.flush()
    return addon


def delete_purchase_item_addon(
    db: Session, order_id: str, item_id: int, addon_id: int,
) -> None:
    order, item = _get_order_and_item(db, order_id, item_id)

    addon = db.get(PurchaseOrderItemAddon, addon_id)
    if addon is None or addon.purchase_order_item_id != item_id:
        raise ValueError(f"附加费用 {addon_id} 不存在")

    db.delete(addon)
    db.flush()
    _recalc_total(db, order)
    db.flush()
```

- [ ] **Step 5: Fix `delete_purchase_order` to cascade addon deletion**

The existing `delete_purchase_order` uses bulk SQL `db.query(...).delete()` which bypasses ORM cascade. Change `services/purchase_order.py` lines 115-117 from:

```python
    db.query(PurchaseOrderItem).filter(
        PurchaseOrderItem.purchase_order_id == order_id
    ).delete(synchronize_session=False)
```

To:

```python
    for item in items:
        db.delete(item)
```

This reuses the already-loaded `items` list (line 111) and triggers the ORM cascade to auto-delete addons.

- [ ] **Step 6: Fix `update_purchase_item` to recalc addon unit_cost when qty changes**

In `services/purchase_order.py`, in the `update_purchase_item` function, after the stock adjustment block (after line 179) and before the amount recalc (line 181), add addon unit_cost recalculation:

```python
    # Recalc addon unit_cost when item qty changes
    if new_qty != old_qty:
        new_qty_d = Decimal(str(item.qty))
        for addon in item.addons:
            addon.unit_cost = (Decimal(str(addon.amount)) / new_qty_d).quantize(
                _Q7, rounding=ROUND_HALF_UP
            ) if new_qty_d else Decimal("0")
```

- [ ] **Step 7: Add tests for cascade delete and unit_cost recalc**

Append to `tests/test_purchase_order_addon.py`:

```python
def test_delete_order_cascades_addons(db, part):
    """Deleting entire order should cascade-delete addon rows."""
    from services.purchase_order import delete_purchase_order
    order = create_purchase_order(
        db,
        vendor_name="测试商家",
        items=[{"part_id": part.id, "qty": 200, "unit": "条", "price": 5.0}],
    )
    item = order.items[0]
    create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    delete_purchase_order(db, order.id)
    from models.purchase_order import PurchaseOrderItemAddon
    remaining = db.query(PurchaseOrderItemAddon).all()
    assert len(remaining) == 0


def test_update_item_qty_recalcs_addon_unit_cost(db, order_and_item):
    """Changing item qty should recalculate addon unit_cost."""
    from services.purchase_order import update_purchase_item
    order, item = order_and_item
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    # Original: unit_cost = 30 / 200 = 0.15
    assert addon.unit_cost == Decimal("0.15")

    update_purchase_item(db, order.id, item.id, {"qty": 100})
    db.refresh(addon)
    # New: unit_cost = 30 / 100 = 0.3
    assert addon.unit_cost == Decimal("0.3")
```

- [ ] **Step 8: Run tests**

Run: `pytest tests/test_purchase_order_addon.py -v`
Expected: All 10 tests PASS

- [ ] **Step 9: Commit**

```bash
git add services/purchase_order.py tests/test_purchase_order_addon.py
git commit -m "feat: add addon CRUD service + tests, extend _recalc_total"
```

---

### Task 4: API — addon endpoints

**Files:**
- Modify: `api/purchase_order.py`

- [ ] **Step 1: Write API tests**

Append to `tests/test_purchase_order_addon.py`:

```python
# --- API Tests ---

def _create_part_via_db(db):
    from models.part import Part
    p = Part(id="PJ-DZ-00099", name="API测试配件", category="吊坠")
    db.add(p)
    db.flush()
    return p


def test_api_create_addon(client, db):
    part = _create_part_via_db(db)
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part.id, "qty": 100, "unit": "条", "price": 2.0}],
    }).json()
    item_id = po["items"][0]["id"]

    resp = client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 5, "unit": "条", "price": 1.0},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["type"] == "bead_stringing"
    assert data["amount"] == 5.0
    assert data["unit_cost"] == 0.05  # 5 / 100


def test_api_addon_in_order_response(client, db):
    part = _create_part_via_db(db)
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part.id, "qty": 100, "unit": "条", "price": 2.0}],
    }).json()
    item_id = po["items"][0]["id"]
    client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 5, "unit": "条", "price": 1.0},
    )

    resp = client.get(f"/api/purchase-orders/{po['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"][0]["addons"]) == 1
    assert data["total_amount"] == 205.0  # 200 + 5


def test_api_update_addon(client, db):
    part = _create_part_via_db(db)
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part.id, "qty": 100, "unit": "条", "price": 2.0}],
    }).json()
    item_id = po["items"][0]["id"]
    addon = client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 5, "unit": "条", "price": 1.0},
    ).json()

    resp = client.put(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons/{addon['id']}",
        json={"qty": 10, "price": 2.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["amount"] == 20.0
    assert data["unit_cost"] == 0.2


def test_api_delete_addon(client, db):
    part = _create_part_via_db(db)
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part.id, "qty": 100, "unit": "条", "price": 2.0}],
    }).json()
    item_id = po["items"][0]["id"]
    addon = client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 5, "unit": "条", "price": 1.0},
    ).json()

    resp = client.delete(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons/{addon['id']}",
    )
    assert resp.status_code == 204

    order = client.get(f"/api/purchase-orders/{po['id']}").json()
    assert order["total_amount"] == 200.0
    assert len(order["items"][0]["addons"]) == 0


def test_api_create_addon_paid_returns_400(client, db):
    part = _create_part_via_db(db)
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part.id, "qty": 100, "unit": "条", "price": 2.0}],
    }).json()
    item_id = po["items"][0]["id"]
    client.patch(f"/api/purchase-orders/{po['id']}/status", json={"status": "已付款"})

    resp = client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 5, "unit": "条", "price": 1.0},
    )
    assert resp.status_code == 400


def test_api_delete_item_cascades_addon(client, db):
    part = _create_part_via_db(db)
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [
            {"part_id": part.id, "qty": 100, "unit": "条", "price": 2.0},
            {"part_id": part.id, "qty": 50, "unit": "条", "price": 1.0},
        ],
    }).json()
    item_id = po["items"][0]["id"]
    client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 5, "unit": "条", "price": 1.0},
    )

    resp = client.delete(f"/api/purchase-orders/{po['id']}/items/{item_id}")
    assert resp.status_code == 204

    order = client.get(f"/api/purchase-orders/{po['id']}").json()
    # Only second item remains, no addons
    assert len(order["items"]) == 1
    assert order["total_amount"] == 50.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_purchase_order_addon.py::test_api_create_addon -v`
Expected: FAIL (404 — routes don't exist yet)

- [ ] **Step 3: Add API endpoints to `api/purchase_order.py`**

Add imports:

```python
from schemas.purchase_order import (
    PurchaseOrderCreate,
    PurchaseOrderDeliveryImagesUpdate,
    PurchaseOrderItemAddonCreate,
    PurchaseOrderItemAddonResponse,
    PurchaseOrderItemAddonUpdate,
    PurchaseOrderItemUpdate,
    PurchaseOrderItemResponse,
    PurchaseOrderResponse,
    PurchaseOrderStatusUpdate,
)
from services.purchase_order import (
    create_purchase_order,
    create_purchase_item_addon,
    delete_purchase_item,
    delete_purchase_item_addon,
    delete_purchase_order,
    get_purchase_order,
    get_vendor_names,
    list_purchase_orders,
    update_purchase_item,
    update_purchase_item_addon,
    update_purchase_order_images,
    update_purchase_order_status,
)
```

Add endpoints at the end of the file:

```python
@router.post("/{order_id}/items/{item_id}/addons", response_model=PurchaseOrderItemAddonResponse, status_code=201)
def api_create_addon(order_id: str, item_id: int, body: PurchaseOrderItemAddonCreate, db: Session = Depends(get_db)):
    order = get_purchase_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PurchaseOrder {order_id} not found")
    with service_errors():
        addon = create_purchase_item_addon(
            db, order_id, item_id,
            type=body.type, qty=body.qty, unit=body.unit, price=body.price,
        )
    return addon


@router.put("/{order_id}/items/{item_id}/addons/{addon_id}", response_model=PurchaseOrderItemAddonResponse)
def api_update_addon(order_id: str, item_id: int, addon_id: int, body: PurchaseOrderItemAddonUpdate, db: Session = Depends(get_db)):
    order = get_purchase_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PurchaseOrder {order_id} not found")
    with service_errors():
        addon = update_purchase_item_addon(
            db, order_id, item_id, addon_id,
            **body.model_dump(exclude_unset=True),
        )
    return addon


@router.delete("/{order_id}/items/{item_id}/addons/{addon_id}", status_code=204)
def api_delete_addon(order_id: str, item_id: int, addon_id: int, db: Session = Depends(get_db)):
    order = get_purchase_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PurchaseOrder {order_id} not found")
    with service_errors():
        delete_purchase_item_addon(db, order_id, item_id, addon_id)
```

- [ ] **Step 4: Run all tests**

Run: `pytest tests/test_purchase_order_addon.py -v`
Expected: All 14 tests PASS (8 service + 6 API)

- [ ] **Step 5: Run full test suite to check no regressions**

Run: `pytest --tb=short`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add api/purchase_order.py schemas/purchase_order.py tests/test_purchase_order_addon.py
git commit -m "feat: add addon API endpoints for purchase order items"
```
