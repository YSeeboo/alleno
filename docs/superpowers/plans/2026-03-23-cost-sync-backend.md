# 成本同步（后端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect cost diffs when creating purchase orders, addon fees, and plating receipts; provide a batch cost update API.

**Architecture:** New `services/cost_sync.py` with diff detection functions. API layer calls detect functions after creation, injects `cost_diffs` into response. New batch update endpoint in `api/parts.py`. Schemas for CostDiffItem and BatchCostUpdate in `schemas/part.py`.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, Pydantic v2, pytest

**Spec:** `docs/superpowers/specs/2026-03-23-cost-sync-design.md`

---

### Task 1: Schemas — CostDiffItem + BatchCostUpdate + response extensions

**Files:**
- Modify: `schemas/part.py` (add batch update schemas)
- Modify: `schemas/purchase_order.py` (add cost_diffs to responses)
- Modify: `schemas/plating_receipt.py` (add cost_diffs to response)

- [ ] **Step 1: Add shared CostDiffItem and batch update schemas to `schemas/part.py`**

At the end of `schemas/part.py`, add:

```python
class CostDiffItem(BaseModel):
    part_id: str
    part_name: str
    field: str
    current_value: Optional[float] = None
    new_value: float


class BatchCostUpdateItem(BaseModel):
    part_id: str
    field: str
    value: float = Field(ge=0)
    source_id: Optional[str] = None


class BatchCostUpdateRequest(BaseModel):
    updates: list[BatchCostUpdateItem] = Field(min_length=1)


class BatchCostUpdateResultItem(BaseModel):
    part_id: str
    field: str
    updated: bool


class BatchCostUpdateResponse(BaseModel):
    updated_count: int
    results: list[BatchCostUpdateResultItem]
```

- [ ] **Step 2: Add `cost_diffs` to `PurchaseOrderResponse` in `schemas/purchase_order.py`**

Add import at top:
```python
from schemas.part import CostDiffItem
```

Add field to `PurchaseOrderResponse` (after `items`):
```python
    cost_diffs: list[CostDiffItem] = Field(default_factory=list)
```

Add field to `PurchaseOrderItemAddonResponse` (after `unit_cost`):
```python
    cost_diffs: list[CostDiffItem] = Field(default_factory=list)
```

- [ ] **Step 3: Add `cost_diffs` to `PlatingReceiptResponse` in `schemas/plating_receipt.py`**

Add import at top:
```python
from schemas.part import CostDiffItem
```

Add field to `PlatingReceiptResponse` (after `items`):
```python
    cost_diffs: list[CostDiffItem] = Field(default_factory=list)
```

- [ ] **Step 4: Commit**

```bash
git add schemas/part.py schemas/purchase_order.py schemas/plating_receipt.py
git commit -m "feat: add CostDiffItem and batch cost update schemas"
```

---

### Task 2: Service — cost diff detection functions

**Files:**
- Create: `services/cost_sync.py`
- Create: `tests/test_cost_sync.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cost_sync.py`:

```python
import pytest
from decimal import Decimal

from models.part import Part
from services.part import create_part, update_part_cost
from services.purchase_order import create_purchase_order, create_purchase_item_addon


@pytest.fixture
def part_a(db):
    return create_part(db, {"name": "配件A", "category": "吊坠"})


@pytest.fixture
def part_b(db):
    return create_part(db, {"name": "配件B", "category": "链条"})


def test_detect_purchase_cost_diffs_no_existing(db, part_a):
    """Part has no purchase_cost, order item has price → diff detected."""
    from services.cost_sync import detect_purchase_cost_diffs
    order = create_purchase_order(
        db, vendor_name="商家", items=[{"part_id": part_a.id, "qty": 100, "price": 2.5}],
    )
    diffs = detect_purchase_cost_diffs(db, order)
    assert len(diffs) == 1
    assert diffs[0]["part_id"] == part_a.id
    assert diffs[0]["field"] == "purchase_cost"
    assert diffs[0]["current_value"] is None
    assert diffs[0]["new_value"] == float(Decimal("2.5"))


def test_detect_purchase_cost_diffs_same_value(db, part_a):
    """Part already has matching purchase_cost → no diff."""
    from services.cost_sync import detect_purchase_cost_diffs
    update_part_cost(db, part_a.id, "purchase_cost", 2.5)
    order = create_purchase_order(
        db, vendor_name="商家", items=[{"part_id": part_a.id, "qty": 100, "price": 2.5}],
    )
    diffs = detect_purchase_cost_diffs(db, order)
    assert len(diffs) == 0


def test_detect_purchase_cost_diffs_different_value(db, part_a):
    """Part has different purchase_cost → diff detected."""
    from services.cost_sync import detect_purchase_cost_diffs
    update_part_cost(db, part_a.id, "purchase_cost", 2.0)
    order = create_purchase_order(
        db, vendor_name="商家", items=[{"part_id": part_a.id, "qty": 100, "price": 3.0}],
    )
    diffs = detect_purchase_cost_diffs(db, order)
    assert len(diffs) == 1
    assert diffs[0]["current_value"] == 2.0
    assert diffs[0]["new_value"] == 3.0


def test_detect_purchase_cost_diffs_no_price(db, part_a):
    """Item has no price → no diff for that item."""
    from services.cost_sync import detect_purchase_cost_diffs
    order = create_purchase_order(
        db, vendor_name="商家", items=[{"part_id": part_a.id, "qty": 100}],
    )
    diffs = detect_purchase_cost_diffs(db, order)
    assert len(diffs) == 0


def test_detect_purchase_cost_diffs_multiple_items_same_part(db, part_a):
    """Same part_id appears twice → use last item's price."""
    from services.cost_sync import detect_purchase_cost_diffs
    order = create_purchase_order(
        db, vendor_name="商家",
        items=[
            {"part_id": part_a.id, "qty": 50, "price": 2.0},
            {"part_id": part_a.id, "qty": 50, "price": 3.0},
        ],
    )
    diffs = detect_purchase_cost_diffs(db, order)
    assert len(diffs) == 1
    assert diffs[0]["new_value"] == 3.0


def test_detect_addon_cost_diffs_bead(db, part_a):
    """Addon bead_stringing unit_cost differs from part.bead_cost → diff detected."""
    from services.cost_sync import detect_addon_cost_diffs
    order = create_purchase_order(
        db, vendor_name="商家", items=[{"part_id": part_a.id, "qty": 200, "price": 5.0}],
    )
    item = order.items[0]
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    diffs = detect_addon_cost_diffs(db, item, addon)
    assert len(diffs) == 1
    assert diffs[0]["field"] == "bead_cost"
    assert diffs[0]["current_value"] is None
    # unit_cost = 30/200 = 0.15
    assert diffs[0]["new_value"] == 0.15


def test_detect_addon_cost_diffs_same_value(db, part_a):
    """Part already has matching bead_cost → no diff."""
    from services.cost_sync import detect_addon_cost_diffs
    update_part_cost(db, part_a.id, "bead_cost", 0.15)
    order = create_purchase_order(
        db, vendor_name="商家", items=[{"part_id": part_a.id, "qty": 200, "price": 5.0}],
    )
    item = order.items[0]
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    diffs = detect_addon_cost_diffs(db, item, addon)
    assert len(diffs) == 0


def test_detect_addon_cost_diffs_non_bead_type(db, part_a):
    """Non-bead_stringing addon → no diff detection."""
    from services.cost_sync import detect_addon_cost_diffs
    order = create_purchase_order(
        db, vendor_name="商家", items=[{"part_id": part_a.id, "qty": 200, "price": 5.0}],
    )
    item = order.items[0]
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="plating_cost", qty=10, unit="条", price=3.0,
    )
    diffs = detect_addon_cost_diffs(db, item, addon)
    assert len(diffs) == 0


# --- Plating receipt cost diff tests ---

def _setup_plating_scenario(db, part):
    """Helper: create part variant, plating order, send it → returns (variant, poi)."""
    from services.part import create_part_variant
    from services.plating import create_plating_order, send_plating_order
    from services.inventory import add_stock

    variant = create_part_variant(db, part.id, "G")
    # Need stock to send
    add_stock(db, "part", part.id, 100, "测试入库")
    order = create_plating_order(db, supplier_name="电镀商", items=[{
        "part_id": part.id,
        "qty": 50,
        "receive_part_id": variant.id,
    }])
    send_plating_order(db, order.id)
    poi = order.items[0]
    return variant, poi


def test_detect_plating_cost_diffs_no_existing(db, part_a):
    """Part has no plating_cost, receipt item has price → diff detected."""
    from services.cost_sync import detect_plating_cost_diffs
    from services.plating_receipt import create_plating_receipt

    variant, poi = _setup_plating_scenario(db, part_a)
    receipt = create_plating_receipt(
        db, vendor_name="电镀商",
        items=[{"plating_order_item_id": poi.id, "part_id": variant.id, "qty": 10, "price": 1.5}],
    )
    diffs = detect_plating_cost_diffs(db, receipt)
    assert len(diffs) == 1
    assert diffs[0]["part_id"] == variant.id
    assert diffs[0]["field"] == "plating_cost"
    assert diffs[0]["new_value"] == 1.5


def test_detect_plating_cost_diffs_same_value(db, part_a):
    """Part already has matching plating_cost → no diff."""
    from services.cost_sync import detect_plating_cost_diffs
    from services.plating_receipt import create_plating_receipt

    variant, poi = _setup_plating_scenario(db, part_a)
    update_part_cost(db, variant.id, "plating_cost", 1.5)
    receipt = create_plating_receipt(
        db, vendor_name="电镀商",
        items=[{"plating_order_item_id": poi.id, "part_id": variant.id, "qty": 10, "price": 1.5}],
    )
    diffs = detect_plating_cost_diffs(db, receipt)
    assert len(diffs) == 0


def test_detect_plating_cost_diffs_different_value(db, part_a):
    """Part has different plating_cost → diff detected."""
    from services.cost_sync import detect_plating_cost_diffs
    from services.plating_receipt import create_plating_receipt

    variant, poi = _setup_plating_scenario(db, part_a)
    update_part_cost(db, variant.id, "plating_cost", 2.0)
    receipt = create_plating_receipt(
        db, vendor_name="电镀商",
        items=[{"plating_order_item_id": poi.id, "part_id": variant.id, "qty": 10, "price": 1.5}],
    )
    diffs = detect_plating_cost_diffs(db, receipt)
    assert len(diffs) == 1
    assert diffs[0]["current_value"] == 2.0
    assert diffs[0]["new_value"] == 1.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cost_sync.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement `services/cost_sync.py`**

```python
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from models.part import Part
from models.purchase_order import PurchaseOrder, PurchaseOrderItem, PurchaseOrderItemAddon

_Q7 = Decimal("0.0000001")


def _compare(current_value, new_value) -> bool:
    """Return True if values differ. None vs 0 counts as different."""
    if current_value is None and new_value is None:
        return False
    if current_value is None or new_value is None:
        return True
    cur = Decimal(str(current_value)).quantize(_Q7, rounding=ROUND_HALF_UP)
    new = Decimal(str(new_value)).quantize(_Q7, rounding=ROUND_HALF_UP)
    return cur != new


def detect_purchase_cost_diffs(db: Session, order: PurchaseOrder) -> list[dict]:
    """Detect purchase_cost diffs between order items and parts."""
    # Build map: part_id → last item price (last wins for duplicates)
    price_map = {}
    for item in order.items:
        if item.price is not None:
            price_map[item.part_id] = float(item.price)

    diffs = []
    for part_id, new_price in price_map.items():
        part = db.get(Part, part_id)
        if part is None:
            continue
        current = float(part.purchase_cost) if part.purchase_cost is not None else None
        if _compare(current, new_price):
            diffs.append({
                "part_id": part_id,
                "part_name": part.name,
                "field": "purchase_cost",
                "current_value": current,
                "new_value": new_price,
            })
    return diffs


def detect_addon_cost_diffs(
    db: Session, item: PurchaseOrderItem, addon: PurchaseOrderItemAddon,
) -> list[dict]:
    """Detect bead_cost diff for a bead_stringing addon."""
    if addon.type != "bead_stringing":
        return []

    part = db.get(Part, item.part_id)
    if part is None:
        return []

    new_value = float(addon.unit_cost)
    current = float(part.bead_cost) if part.bead_cost is not None else None

    if _compare(current, new_value):
        return [{
            "part_id": item.part_id,
            "part_name": part.name,
            "field": "bead_cost",
            "current_value": current,
            "new_value": new_value,
        }]
    return []


def detect_plating_cost_diffs(db: Session, receipt) -> list[dict]:
    """Detect plating_cost diffs between receipt items and parts."""
    from models.plating_order import PlatingOrderItem

    # Build map: receive_part_id → last item price
    price_map = {}
    for ri in receipt.items:
        if ri.price is None:
            continue
        poi = db.get(PlatingOrderItem, ri.plating_order_item_id)
        if poi is None:
            continue
        receive_id = poi.receive_part_id or poi.part_id
        price_map[receive_id] = float(ri.price)

    diffs = []
    for part_id, new_price in price_map.items():
        part = db.get(Part, part_id)
        if part is None:
            continue
        current = float(part.plating_cost) if part.plating_cost is not None else None
        if _compare(current, new_price):
            diffs.append({
                "part_id": part_id,
                "part_name": part.name,
                "field": "plating_cost",
                "current_value": current,
                "new_value": new_price,
            })
    return diffs
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_cost_sync.py -v`
Expected: All 11 tests PASS (5 purchase + 3 addon + 3 plating)

- [ ] **Step 5: Commit**

```bash
git add services/cost_sync.py tests/test_cost_sync.py
git commit -m "feat: add cost diff detection service functions"
```

---

### Task 3: API — inject cost_diffs into create responses + batch update endpoint

**Files:**
- Modify: `api/purchase_order.py` (inject diffs in create + addon endpoints)
- Modify: `api/plating_receipt.py` (inject diffs in create endpoint)
- Modify: `api/parts.py` (add batch update endpoint)
- Append: `tests/test_cost_sync.py` (API tests)

- [ ] **Step 1: Write API tests**

Append to `tests/test_cost_sync.py`:

```python
# --- API Tests ---

def test_api_create_purchase_order_returns_cost_diffs(client, db, part_a):
    resp = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part_a.id, "qty": 100, "price": 2.5}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "cost_diffs" in data
    assert len(data["cost_diffs"]) == 1
    assert data["cost_diffs"][0]["field"] == "purchase_cost"
    assert data["cost_diffs"][0]["new_value"] == 2.5


def test_api_create_purchase_order_no_diffs(client, db, part_a):
    update_part_cost(db, part_a.id, "purchase_cost", 2.5)
    resp = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part_a.id, "qty": 100, "price": 2.5}],
    })
    assert resp.status_code == 201
    assert resp.json()["cost_diffs"] == []


def test_api_get_purchase_order_cost_diffs_empty(client, db, part_a):
    """GET should always return empty cost_diffs."""
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part_a.id, "qty": 100, "price": 2.5}],
    }).json()
    resp = client.get(f"/api/purchase-orders/{po['id']}")
    assert resp.json()["cost_diffs"] == []


def test_api_create_addon_returns_cost_diffs(client, db, part_a):
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part_a.id, "qty": 200, "price": 5.0}],
    }).json()
    item_id = po["items"][0]["id"]
    resp = client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 10, "unit": "条", "price": 3.0},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "cost_diffs" in data
    assert len(data["cost_diffs"]) == 1
    assert data["cost_diffs"][0]["field"] == "bead_cost"


def test_api_update_addon_returns_cost_diffs(client, db, part_a):
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part_a.id, "qty": 200, "price": 5.0}],
    }).json()
    item_id = po["items"][0]["id"]
    addon = client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 10, "unit": "条", "price": 3.0},
    ).json()
    # Update addon price
    resp = client.put(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons/{addon['id']}",
        json={"price": 4.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "cost_diffs" in data


def test_api_batch_update_costs(client, db, part_a, part_b):
    resp = client.post("/api/parts/batch-update-costs", json={
        "updates": [
            {"part_id": part_a.id, "field": "purchase_cost", "value": 3.0, "source_id": "CG-0001"},
            {"part_id": part_b.id, "field": "purchase_cost", "value": 5.0, "source_id": "CG-0001"},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated_count"] == 2
    assert len(data["results"]) == 2
    assert all(r["updated"] for r in data["results"])

    # Verify parts were updated
    p_a = client.get(f"/api/parts/{part_a.id}").json()
    assert p_a["purchase_cost"] == 3.0


def test_api_batch_update_costs_no_change(client, db, part_a):
    update_part_cost(db, part_a.id, "purchase_cost", 3.0)
    resp = client.post("/api/parts/batch-update-costs", json={
        "updates": [
            {"part_id": part_a.id, "field": "purchase_cost", "value": 3.0, "source_id": "CG-0001"},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated_count"] == 0
    assert data["results"][0]["updated"] is False


def test_api_batch_update_costs_invalid_field(client, db, part_a):
    resp = client.post("/api/parts/batch-update-costs", json={
        "updates": [
            {"part_id": part_a.id, "field": "invalid", "value": 3.0},
        ],
    })
    assert resp.status_code == 400


def test_api_create_plating_receipt_returns_cost_diffs(client, db, part_a):
    """Plating receipt create should return cost_diffs."""
    from services.part import create_part_variant
    from services.plating import create_plating_order, send_plating_order
    from services.inventory import add_stock

    variant = create_part_variant(db, part_a.id, "G")
    add_stock(db, "part", part_a.id, 100, "测试入库")
    order = create_plating_order(db, supplier_name="电镀商", items=[{
        "part_id": part_a.id, "qty": 50, "receive_part_id": variant.id,
    }])
    send_plating_order(db, order.id)
    poi = order.items[0]

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "电镀商",
        "items": [{"plating_order_item_id": poi.id, "part_id": variant.id, "qty": 10, "price": 1.5}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "cost_diffs" in data
    assert len(data["cost_diffs"]) == 1
    assert data["cost_diffs"][0]["field"] == "plating_cost"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cost_sync.py::test_api_create_purchase_order_returns_cost_diffs -v`
Expected: FAIL (cost_diffs not in response)

- [ ] **Step 3: Modify `api/purchase_order.py` — inject cost_diffs in create and addon endpoints**

Add import:
```python
from services.cost_sync import detect_purchase_cost_diffs, detect_addon_cost_diffs
```

Change the create endpoint (around line 47-57) from:

```python
@router.post("/", response_model=PurchaseOrderResponse, status_code=201)
def api_create_purchase_order(body: PurchaseOrderCreate, db: Session = Depends(get_db)):
    with service_errors():
        order = create_purchase_order(
            db,
            vendor_name=body.vendor_name,
            items=[item.model_dump() for item in body.items],
            status=body.status,
            note=body.note,
        )
    return order
```

To:

```python
@router.post("/", response_model=PurchaseOrderResponse, status_code=201)
def api_create_purchase_order(body: PurchaseOrderCreate, db: Session = Depends(get_db)):
    with service_errors():
        order = create_purchase_order(
            db,
            vendor_name=body.vendor_name,
            items=[item.model_dump() for item in body.items],
            status=body.status,
            note=body.note,
        )
    cost_diffs = detect_purchase_cost_diffs(db, order)
    resp = PurchaseOrderResponse.model_validate(order)
    resp.cost_diffs = [CostDiffItem(**d) for d in cost_diffs]
    return resp
```

Add import for schemas:
```python
from schemas.part import CostDiffItem
from schemas.purchase_order import (
    ...,
    PurchaseOrderItemAddonResponse,
)
```

Change the addon create endpoint to:

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
    item = db.get(PurchaseOrderItem, item_id)
    cost_diffs = detect_addon_cost_diffs(db, item, addon)
    resp = PurchaseOrderItemAddonResponse.model_validate(addon)
    resp.cost_diffs = [CostDiffItem(**d) for d in cost_diffs]
    return resp
```

Add import for `PurchaseOrderItem`:
```python
from models.purchase_order import PurchaseOrderItem
```

Change the addon update endpoint similarly:

```python
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
    item = db.get(PurchaseOrderItem, item_id)
    cost_diffs = detect_addon_cost_diffs(db, item, addon)
    resp = PurchaseOrderItemAddonResponse.model_validate(addon)
    resp.cost_diffs = [CostDiffItem(**d) for d in cost_diffs]
    return resp
```

- [ ] **Step 4: Modify `api/plating_receipt.py` — inject cost_diffs in create endpoint**

Add imports:
```python
from services.cost_sync import detect_plating_cost_diffs
from schemas.part import CostDiffItem
from schemas.plating_receipt import PlatingReceiptResponse
```

Change the create endpoint from:

```python
@router.post("/", response_model=PlatingReceiptResponse, status_code=201)
def api_create_plating_receipt(body: PlatingReceiptCreate, db: Session = Depends(get_db)):
    with service_errors():
        receipt = create_plating_receipt(
            db,
            vendor_name=body.vendor_name,
            items=[item.model_dump() for item in body.items],
            status=body.status,
            note=body.note,
        )
    return receipt
```

To:

```python
@router.post("/", response_model=PlatingReceiptResponse, status_code=201)
def api_create_plating_receipt(body: PlatingReceiptCreate, db: Session = Depends(get_db)):
    with service_errors():
        receipt = create_plating_receipt(
            db,
            vendor_name=body.vendor_name,
            items=[item.model_dump() for item in body.items],
            status=body.status,
            note=body.note,
        )
    cost_diffs = detect_plating_cost_diffs(db, receipt)
    resp = PlatingReceiptResponse.model_validate(receipt)
    resp.cost_diffs = [CostDiffItem(**d) for d in cost_diffs]
    return resp
```

- [ ] **Step 5: Add batch update endpoint to `api/parts.py`**

Add imports:
```python
from schemas.part import PartCreate, FindOrCreateVariantResponse, PartCostLogResponse, PartImportResponse, PartResponse, PartUpdate, PartVariantCreate, BatchCostUpdateRequest, BatchCostUpdateResponse, BatchCostUpdateResultItem
from services.part import COLOR_VARIANTS, create_part, create_part_variant, find_or_create_variant, get_part, list_part_cost_logs, list_part_variants, list_parts, update_part, update_part_cost, delete_part
```

Add endpoint (before the `/{part_id}` routes):

```python
@router.post("/batch-update-costs", response_model=BatchCostUpdateResponse)
def api_batch_update_costs(body: BatchCostUpdateRequest, db: Session = Depends(get_db)):
    results = []
    updated_count = 0
    with service_errors():
        for item in body.updates:
            log = update_part_cost(db, item.part_id, item.field, item.value, source_id=item.source_id)
            updated = log is not None
            if updated:
                updated_count += 1
            results.append(BatchCostUpdateResultItem(
                part_id=item.part_id,
                field=item.field,
                updated=updated,
            ))
    return BatchCostUpdateResponse(updated_count=updated_count, results=results)
```

- [ ] **Step 6: Run all tests**

Run: `pytest tests/test_cost_sync.py -v`
Expected: All 21 tests PASS (11 service + 10 API)

- [ ] **Step 7: Run full test suite**

Run: `pytest --tb=short`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add api/purchase_order.py api/plating_receipt.py api/parts.py tests/test_cost_sync.py
git commit -m "feat: inject cost_diffs in create responses, add batch update API"
```
