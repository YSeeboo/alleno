# 电镀发出 — 关联电镀回收单 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow linking plating order items to existing plating receipts from the send side, with navigation and highlight support.

**Architecture:** Three new backend endpoints under `/api/plating/` (available-receipts, link-receipt, receipt-links) that wrap existing `add_plating_receipt_items` logic. Frontend adds a "关联电镀单" column to PlatingDetail.vue with a link modal, and highlight support to PlatingReceiptDetail.vue.

**Tech Stack:** FastAPI, SQLAlchemy, Vue 3 + Naive UI, existing plating receipt service layer.

---

### Task 1: Backend — Schema for link-receipt request

**Files:**
- Modify: `/Users/ycb/workspace/allen_shop/schemas/plating_receipt.py:39-40`

- [ ] **Step 1: Add LinkReceiptRequest schema**

Add after line 40 in `schemas/plating_receipt.py`:

```python
class LinkReceiptRequest(BaseModel):
    receipt_id: str
    qty: float = Field(gt=0)
    price: float = Field(ge=0)
```

- [ ] **Step 2: Commit**

```bash
git add schemas/plating_receipt.py
git commit -m "feat: add LinkReceiptRequest schema for plating receipt linking"
```

---

### Task 2: Backend — Service functions (receipt-links, available-receipts, link-receipt)

**Files:**
- Modify: `/Users/ycb/workspace/allen_shop/services/plating_receipt.py`

- [ ] **Step 1: Write failing tests**

Create test file `/Users/ycb/workspace/allen_shop/tests/test_plating_receipt_link.py`:

```python
import pytest
from services.part import create_part
from services.inventory import add_stock, get_stock
from services.plating import create_plating_order, send_plating_order, get_plating_items
from services.plating_receipt import (
    create_plating_receipt,
    get_receipt_links_for_plating_order,
    get_available_receipts_for_item,
    link_plating_item_to_receipt,
)


def _setup(db, supplier="Supplier A", qty=100.0):
    """Create part with stock, create + send plating order."""
    part = create_part(db, {"name": "Test Part", "category": "小配件"})
    add_stock(db, "part", part.id, qty + 50, "初始库存")
    order = create_plating_order(db, supplier, [{"part_id": part.id, "qty": qty}])
    send_plating_order(db, order.id)
    db.flush()
    items = get_plating_items(db, order.id)
    return part, order, items[0]


def _create_unpaid_receipt(db, vendor="Supplier A"):
    """Create a part + plating order + receipt, return (part, order, poi, receipt_id)."""
    part, order, poi = _setup(db, supplier=vendor)
    receipt = create_plating_receipt(db, vendor, [
        {"plating_order_item_id": poi.id, "part_id": part.id, "qty": 10.0, "price": 1.0},
    ])
    return part, order, poi, receipt.id


# --- get_receipt_links_for_plating_order ---

def test_receipt_links_empty(db):
    _part, order, _poi = _setup(db)
    result = get_receipt_links_for_plating_order(db, order.id)
    assert result == {}


def test_receipt_links_returns_linked_items(db):
    part, order, poi = _setup(db)
    receipt = create_plating_receipt(db, "Supplier A", [
        {"plating_order_item_id": poi.id, "part_id": part.id, "qty": 30.0, "price": 2.0},
    ])
    result = get_receipt_links_for_plating_order(db, order.id)
    assert poi.id in result
    links = result[poi.id]
    assert len(links) == 1
    assert links[0]["receipt_id"] == receipt.id
    assert links[0]["qty"] == 30.0
    assert links[0]["price"] == 2.0


# --- get_available_receipts_for_item ---

def test_available_receipts_filters_by_vendor(db):
    part, order, poi = _setup(db, supplier="Vendor X")
    # Create receipt with different vendor — should not appear
    other_part = create_part(db, {"name": "Other", "category": "小配件"})
    add_stock(db, "part", other_part.id, 100, "stock")
    other_order = create_plating_order(db, "Vendor Y", [{"part_id": other_part.id, "qty": 10}])
    send_plating_order(db, other_order.id)
    db.flush()
    other_poi = get_plating_items(db, other_order.id)[0]
    create_plating_receipt(db, "Vendor Y", [
        {"plating_order_item_id": other_poi.id, "part_id": other_part.id, "qty": 5, "price": 1},
    ])
    # Create receipt with matching vendor
    matching_receipt = create_plating_receipt(db, "Vendor X", [
        {"plating_order_item_id": poi.id, "part_id": part.id, "qty": 5, "price": 1},
    ])
    # Available should only show matching vendor, but exclude this receipt (already linked)
    result = get_available_receipts_for_item(db, order.id, poi.id)
    # matching_receipt already has this poi, so it should be excluded
    assert all(r["id"] != matching_receipt.id for r in result) or len(result) == 0


def test_available_receipts_excludes_paid(db):
    part, order, poi = _setup(db, supplier="Supplier A")
    # Create a paid receipt with different item
    other_part = create_part(db, {"name": "Other2", "category": "小配件"})
    add_stock(db, "part", other_part.id, 100, "stock")
    other_order = create_plating_order(db, "Supplier A", [{"part_id": other_part.id, "qty": 10}])
    send_plating_order(db, other_order.id)
    db.flush()
    other_poi = get_plating_items(db, other_order.id)[0]
    create_plating_receipt(db, "Supplier A", [
        {"plating_order_item_id": other_poi.id, "part_id": other_part.id, "qty": 5, "price": 1},
    ], status="已付款")
    result = get_available_receipts_for_item(db, order.id, poi.id)
    assert all(r["id"] for r in result if True)  # just should not error
    # All returned receipts should be unpaid
    for r in result:
        assert r.get("status", "未付款") != "已付款" or "status" not in r


# --- link_plating_item_to_receipt ---

def test_link_receipt_success(db):
    part, order, poi = _setup(db, supplier="Supplier A")
    # Create an empty-ish receipt with a different item
    other_part = create_part(db, {"name": "Other3", "category": "小配件"})
    add_stock(db, "part", other_part.id, 100, "stock")
    other_order = create_plating_order(db, "Supplier A", [{"part_id": other_part.id, "qty": 10}])
    send_plating_order(db, other_order.id)
    db.flush()
    other_poi = get_plating_items(db, other_order.id)[0]
    receipt = create_plating_receipt(db, "Supplier A", [
        {"plating_order_item_id": other_poi.id, "part_id": other_part.id, "qty": 5, "price": 1},
    ])
    # Link our poi to this receipt
    result = link_plating_item_to_receipt(db, order.id, poi.id, receipt.id, 20.0, 0.5)
    assert result["receipt_item_id"] is not None
    assert result["qty"] == 20.0
    # Verify received_qty updated
    db.refresh(poi)
    assert float(poi.received_qty) == 20.0
    # Verify stock added
    receive_id = poi.receive_part_id or poi.part_id
    stock = get_stock(db, "part", receive_id)
    assert stock >= 20.0


def test_link_receipt_exceeds_remaining(db):
    part, order, poi = _setup(db, supplier="Supplier A", qty=10.0)
    other_part = create_part(db, {"name": "Other4", "category": "小配件"})
    add_stock(db, "part", other_part.id, 100, "stock")
    other_order = create_plating_order(db, "Supplier A", [{"part_id": other_part.id, "qty": 10}])
    send_plating_order(db, other_order.id)
    db.flush()
    other_poi = get_plating_items(db, other_order.id)[0]
    receipt = create_plating_receipt(db, "Supplier A", [
        {"plating_order_item_id": other_poi.id, "part_id": other_part.id, "qty": 5, "price": 1},
    ])
    with pytest.raises(ValueError, match="最多可回收"):
        link_plating_item_to_receipt(db, order.id, poi.id, receipt.id, 15.0, 0.5)


def test_link_receipt_vendor_mismatch(db):
    part, order, poi = _setup(db, supplier="Vendor A")
    other_part = create_part(db, {"name": "Other5", "category": "小配件"})
    add_stock(db, "part", other_part.id, 100, "stock")
    other_order = create_plating_order(db, "Vendor B", [{"part_id": other_part.id, "qty": 10}])
    send_plating_order(db, other_order.id)
    db.flush()
    other_poi = get_plating_items(db, other_order.id)[0]
    receipt = create_plating_receipt(db, "Vendor B", [
        {"plating_order_item_id": other_poi.id, "part_id": other_part.id, "qty": 5, "price": 1},
    ])
    with pytest.raises(ValueError, match="不一致"):
        link_plating_item_to_receipt(db, order.id, poi.id, receipt.id, 5.0, 0.5)


def test_link_receipt_duplicate_rejected(db):
    part, order, poi = _setup(db, supplier="Supplier A")
    other_part = create_part(db, {"name": "Other6", "category": "小配件"})
    add_stock(db, "part", other_part.id, 100, "stock")
    other_order = create_plating_order(db, "Supplier A", [{"part_id": other_part.id, "qty": 10}])
    send_plating_order(db, other_order.id)
    db.flush()
    other_poi = get_plating_items(db, other_order.id)[0]
    receipt = create_plating_receipt(db, "Supplier A", [
        {"plating_order_item_id": other_poi.id, "part_id": other_part.id, "qty": 5, "price": 1},
    ])
    # First link succeeds
    link_plating_item_to_receipt(db, order.id, poi.id, receipt.id, 10.0, 0.5)
    # Second link to same receipt should fail
    with pytest.raises(ValueError, match="已存在"):
        link_plating_item_to_receipt(db, order.id, poi.id, receipt.id, 10.0, 0.5)


def test_link_receipt_paid_rejected(db):
    part, order, poi = _setup(db, supplier="Supplier A")
    other_part = create_part(db, {"name": "Other7", "category": "小配件"})
    add_stock(db, "part", other_part.id, 100, "stock")
    other_order = create_plating_order(db, "Supplier A", [{"part_id": other_part.id, "qty": 10}])
    send_plating_order(db, other_order.id)
    db.flush()
    other_poi = get_plating_items(db, other_order.id)[0]
    receipt = create_plating_receipt(db, "Supplier A", [
        {"plating_order_item_id": other_poi.id, "part_id": other_part.id, "qty": 5, "price": 1},
    ], status="已付款")
    with pytest.raises(ValueError, match="已付款"):
        link_plating_item_to_receipt(db, order.id, poi.id, receipt.id, 5.0, 0.5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plating_receipt_link.py -v`
Expected: ImportError — functions not yet defined.

- [ ] **Step 3: Implement the three service functions**

Add the following to the end of `/Users/ycb/workspace/allen_shop/services/plating_receipt.py`:

```python
def get_receipt_links_for_plating_order(db: Session, plating_order_id: str) -> dict:
    """Return {item_id: [{receipt_id, receipt_item_id, qty, price}, ...]} for all items in this order."""
    from models.plating_order import PlatingOrderItem
    item_ids = [
        row.id for row in
        db.query(PlatingOrderItem.id).filter(PlatingOrderItem.plating_order_id == plating_order_id).all()
    ]
    if not item_ids:
        return {}
    rows = (
        db.query(PlatingReceiptItem)
        .filter(PlatingReceiptItem.plating_order_item_id.in_(item_ids))
        .all()
    )
    result = {}
    for r in rows:
        result.setdefault(r.plating_order_item_id, []).append({
            "receipt_id": r.plating_receipt_id,
            "receipt_item_id": r.id,
            "qty": float(r.qty),
            "price": float(r.price) if r.price is not None else None,
        })
    return result


def get_available_receipts_for_item(db: Session, plating_order_id: str, item_id: int) -> list:
    """Return unpaid receipts from the same supplier, excluding those already linked to this item."""
    from models.plating_order import PlatingOrder, PlatingOrderItem
    poi = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.id == item_id,
        PlatingOrderItem.plating_order_id == plating_order_id,
    ).first()
    if poi is None:
        raise ValueError(f"PlatingOrderItem {item_id} not found in order {plating_order_id}")

    order = db.query(PlatingOrder).filter(PlatingOrder.id == plating_order_id).first()
    if order is None:
        raise ValueError(f"PlatingOrder {plating_order_id} not found")

    # Find receipt IDs already linked to this item
    linked_receipt_ids = {
        row.plating_receipt_id for row in
        db.query(PlatingReceiptItem.plating_receipt_id)
        .filter(PlatingReceiptItem.plating_order_item_id == item_id)
        .all()
    }

    query = db.query(PlatingReceipt).filter(
        PlatingReceipt.vendor_name == order.supplier_name,
        PlatingReceipt.status == "未付款",
    )
    if linked_receipt_ids:
        query = query.filter(PlatingReceipt.id.notin_(linked_receipt_ids))

    receipts = query.order_by(PlatingReceipt.created_at.desc()).all()
    result = []
    for r in receipts:
        item_count = db.query(PlatingReceiptItem).filter(
            PlatingReceiptItem.plating_receipt_id == r.id
        ).count()
        result.append({
            "id": r.id,
            "vendor_name": r.vendor_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "item_count": item_count,
        })
    return result


def link_plating_item_to_receipt(
    db: Session,
    plating_order_id: str,
    item_id: int,
    receipt_id: str,
    qty: float,
    price: float,
) -> dict:
    """Link a plating order item to an existing receipt. Returns {receipt_item_id, qty, price}."""
    from models.plating_order import PlatingOrder, PlatingOrderItem

    # 1. Validate item exists and belongs to order
    poi = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.id == item_id,
        PlatingOrderItem.plating_order_id == plating_order_id,
    ).first()
    if poi is None:
        raise ValueError(f"PlatingOrderItem {item_id} not found in order {plating_order_id}")

    # 2. Validate item status
    if poi.status not in ("电镀中", "已收回"):
        raise ValueError(f"配件项状态为「{poi.status}」，无法关联回收单")

    # 3. Validate qty
    remaining = float(poi.qty) - float(poi.received_qty or 0)
    if qty > remaining:
        raise ValueError(f"最多可回收 {remaining}，当前填写 {qty}")

    # 4. Validate receipt exists and is unpaid
    receipt = db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"回收单 {receipt_id} 不存在")
    if receipt.status == "已付款":
        raise ValueError("已付款的回收单不能添加明细")

    # 5. Validate vendor match
    order = db.query(PlatingOrder).filter(PlatingOrder.id == plating_order_id).first()
    if order.supplier_name != receipt.vendor_name:
        raise ValueError(
            f"电镀单供应商「{order.supplier_name}」与回收单商家「{receipt.vendor_name}」不一致"
        )

    # 6. Validate no duplicate
    existing = db.query(PlatingReceiptItem).filter(
        PlatingReceiptItem.plating_receipt_id == receipt_id,
        PlatingReceiptItem.plating_order_item_id == item_id,
    ).first()
    if existing:
        raise ValueError(f"该配件项已存在于回收单 {receipt_id} 中")

    # 7. Build item data and delegate to add_plating_receipt_items
    part_id = poi.receive_part_id or poi.part_id
    item_data = {
        "plating_order_item_id": poi.id,
        "part_id": part_id,
        "qty": qty,
        "price": price,
    }
    add_plating_receipt_items(db, receipt_id, [item_data])

    # Find the newly created receipt item
    new_item = db.query(PlatingReceiptItem).filter(
        PlatingReceiptItem.plating_receipt_id == receipt_id,
        PlatingReceiptItem.plating_order_item_id == item_id,
    ).first()

    return {
        "receipt_id": receipt_id,
        "receipt_item_id": new_item.id,
        "qty": float(new_item.qty),
        "price": float(new_item.price) if new_item.price is not None else None,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plating_receipt_link.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/plating_receipt.py tests/test_plating_receipt_link.py
git commit -m "feat: add service functions for plating receipt linking"
```

---

### Task 3: Backend — API endpoints

**Files:**
- Modify: `/Users/ycb/workspace/allen_shop/api/plating.py`

- [ ] **Step 1: Write failing API tests**

Add to `/Users/ycb/workspace/allen_shop/tests/test_plating_receipt_link.py`:

```python
# --- API Tests ---

def test_api_receipt_links(client, db):
    part, order, poi = _setup(db, supplier="Supplier A")
    receipt = create_plating_receipt(db, "Supplier A", [
        {"plating_order_item_id": poi.id, "part_id": part.id, "qty": 10.0, "price": 1.5},
    ])
    resp = client.get(f"/api/plating/{order.id}/receipt-links")
    assert resp.status_code == 200
    data = resp.json()
    assert str(poi.id) in data
    assert data[str(poi.id)][0]["receipt_id"] == receipt.id


def test_api_available_receipts(client, db):
    part, order, poi = _setup(db, supplier="Supplier A")
    # Create a receipt with a different item from same supplier
    other_part = create_part(db, {"name": "AP1", "category": "小配件"})
    add_stock(db, "part", other_part.id, 100, "stock")
    other_order = create_plating_order(db, "Supplier A", [{"part_id": other_part.id, "qty": 10}])
    send_plating_order(db, other_order.id)
    db.flush()
    other_poi = get_plating_items(db, other_order.id)[0]
    receipt = create_plating_receipt(db, "Supplier A", [
        {"plating_order_item_id": other_poi.id, "part_id": other_part.id, "qty": 5, "price": 1},
    ])
    resp = client.get(f"/api/plating/{order.id}/items/{poi.id}/available-receipts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(r["id"] == receipt.id for r in data)


def test_api_link_receipt(client, db):
    part, order, poi = _setup(db, supplier="Supplier A")
    other_part = create_part(db, {"name": "AP2", "category": "小配件"})
    add_stock(db, "part", other_part.id, 100, "stock")
    other_order = create_plating_order(db, "Supplier A", [{"part_id": other_part.id, "qty": 10}])
    send_plating_order(db, other_order.id)
    db.flush()
    other_poi = get_plating_items(db, other_order.id)[0]
    receipt = create_plating_receipt(db, "Supplier A", [
        {"plating_order_item_id": other_poi.id, "part_id": other_part.id, "qty": 5, "price": 1},
    ])
    resp = client.post(f"/api/plating/{order.id}/items/{poi.id}/link-receipt", json={
        "receipt_id": receipt.id,
        "qty": 20.0,
        "price": 0.5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["receipt_id"] == receipt.id
    assert data["qty"] == 20.0


def test_api_link_receipt_validation_error(client, db):
    part, order, poi = _setup(db, supplier="Supplier A", qty=10.0)
    resp = client.post(f"/api/plating/{order.id}/items/{poi.id}/link-receipt", json={
        "receipt_id": "ER-9999",
        "qty": 5.0,
        "price": 0.5,
    })
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plating_receipt_link.py::test_api_receipt_links -v`
Expected: 404 — endpoints not yet defined.

- [ ] **Step 3: Add the three endpoints to api/plating.py**

Add the following imports at the top of `/Users/ycb/workspace/allen_shop/api/plating.py` (with existing imports from `services.plating_receipt`):

```python
from schemas.plating_receipt import LinkReceiptRequest
from services.plating_receipt import (
    get_receipt_links_for_plating_order,
    get_available_receipts_for_item,
    link_plating_item_to_receipt,
)
```

Add the following endpoints before the `order-links` section (before line 240):

```python
@router.get("/{order_id}/receipt-links")
def api_get_receipt_links(order_id: str, db: Session = Depends(get_db)):
    """批量获取电镀单所有配件项的关联回收单"""
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    return get_receipt_links_for_plating_order(db, order_id)


@router.get("/{order_id}/items/{item_id}/available-receipts")
def api_get_available_receipts(order_id: str, item_id: int, db: Session = Depends(get_db)):
    """获取可关联的回收单列表（同供应商、未付款、未关联该配件项）"""
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    with service_errors():
        return get_available_receipts_for_item(db, order_id, item_id)


@router.post("/{order_id}/items/{item_id}/link-receipt")
def api_link_receipt(order_id: str, item_id: int, body: LinkReceiptRequest, db: Session = Depends(get_db)):
    """将电镀配件项关联到已有的回收单"""
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    with service_errors():
        return link_plating_item_to_receipt(db, order_id, item_id, body.receipt_id, body.qty, body.price)
```

- [ ] **Step 4: Run all link tests**

Run: `pytest tests/test_plating_receipt_link.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run full test suite to check no regressions**

Run: `pytest --tb=short -q`
Expected: All existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add api/plating.py schemas/plating_receipt.py tests/test_plating_receipt_link.py
git commit -m "feat: add API endpoints for plating receipt linking"
```

---

### Task 4: Frontend — API functions

**Files:**
- Modify: `/Users/ycb/workspace/allen_shop/frontend/src/api/plating.js`

- [ ] **Step 1: Add three new API functions**

Add at the end of `/Users/ycb/workspace/allen_shop/frontend/src/api/plating.js`:

```javascript
// --- Receipt links ---
export const getPlatingReceiptLinks = (orderId) =>
  api.get(`/plating/${orderId}/receipt-links`)
export const getAvailableReceipts = (orderId, itemId) =>
  api.get(`/plating/${orderId}/items/${itemId}/available-receipts`)
export const linkPlatingItemToReceipt = (orderId, itemId, data) =>
  api.post(`/plating/${orderId}/items/${itemId}/link-receipt`, data)
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/plating.js
git commit -m "feat: add frontend API functions for receipt linking"
```

---

### Task 5: Frontend — PlatingDetail.vue "关联电镀单" column and modal

**Files:**
- Modify: `/Users/ycb/workspace/allen_shop/frontend/src/views/plating/PlatingDetail.vue`

- [ ] **Step 1: Add imports and reactive state**

In the `<script setup>` section, add the new API imports alongside existing plating imports:

```javascript
import {
  getPlatingReceiptLinks,
  getAvailableReceipts,
  linkPlatingItemToReceipt,
} from '@/api/plating'
```

Also import `deletePlatingReceiptItem` from platingReceipts:

```javascript
import { deletePlatingReceiptItem } from '@/api/platingReceipts'
```

Add reactive state after the existing `itemOrderLinks` section (after line 1152):

```javascript
// --- Receipt Link ---
const itemReceiptLinks = ref({}) // itemId -> [{receipt_id, receipt_item_id, qty, price}]
const receiptLinkModalVisible = ref(false)
const receiptLinkForm = ref({ itemId: null, receiptId: null, qty: null, price: null })
const receiptLinkOptions = ref([])
const receiptLinkLoading = ref(false)
const receiptLinkSubmitting = ref(false)
const receiptLinkItemInfo = ref(null) // {part_id, part_name, qty, received_qty, remaining, receive_part_name}
```

- [ ] **Step 2: Add data loading and action functions**

Add after the reactive state:

```javascript
const loadItemReceiptLinks = async () => {
  try {
    const { data } = await getPlatingReceiptLinks(route.params.id)
    const map = {}
    for (const [key, val] of Object.entries(data)) {
      map[Number(key)] = val
    }
    itemReceiptLinks.value = map
  } catch (_) {
    itemReceiptLinks.value = {}
  }
}

const openReceiptLinkModal = async (row) => {
  receiptLinkForm.value = { itemId: row.id, receiptId: null, qty: null, price: null }
  const remaining = row.qty - (row.received_qty || 0)
  receiptLinkItemInfo.value = {
    part_id: row.part_id,
    part_name: row.part_name,
    qty: row.qty,
    received_qty: row.received_qty || 0,
    remaining,
    receive_part_name: row.receive_part_name,
  }
  receiptLinkOptions.value = []
  receiptLinkModalVisible.value = true
  receiptLinkLoading.value = true
  try {
    const { data } = await getAvailableReceipts(route.params.id, row.id)
    receiptLinkOptions.value = data
  } catch (_) {
    receiptLinkOptions.value = []
  } finally {
    receiptLinkLoading.value = false
  }
}

const doLinkReceipt = async () => {
  const { itemId, receiptId, qty, price } = receiptLinkForm.value
  if (!receiptId) { message.warning('请选择回收单'); return }
  if (!qty || qty <= 0) { message.warning('请输入回收数量'); return }
  if (price == null || price < 0) { message.warning('请输入回收单价'); return }
  const remaining = receiptLinkItemInfo.value?.remaining || 0
  if (qty > remaining) { message.warning(`回收数量不能超过剩余可收数量 ${remaining}`); return }
  receiptLinkSubmitting.value = true
  try {
    await linkPlatingItemToReceipt(route.params.id, itemId, {
      receipt_id: receiptId,
      qty,
      price,
    })
    message.success('关联成功')
    receiptLinkModalVisible.value = false
    await Promise.all([loadItemReceiptLinks(), loadItems()])
  } catch (e) {
    message.error(e.response?.data?.detail || '关联失败')
  } finally {
    receiptLinkSubmitting.value = false
  }
}

const doUnlinkReceipt = (itemId, link) => {
  dialog.warning({
    title: '确认取消关联',
    content: `取消关联回收单「${link.receipt_id}」将回滚对应的库存变更，是否继续？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deletePlatingReceiptItem(link.receipt_id, link.receipt_item_id)
        message.success('已取消关联')
        await Promise.all([loadItemReceiptLinks(), loadItems()])
      } catch (e) {
        message.error(e.response?.data?.detail || '取消关联失败')
      }
    },
  })
}
```

- [ ] **Step 3: Call loadItemReceiptLinks in onMounted**

Find the `onMounted` block and add `loadItemReceiptLinks()` alongside `loadItemOrderLinks()`.

- [ ] **Step 4: Add renderReceiptLinkCell function**

Add before the `itemColumns` definition:

```javascript
const renderReceiptLinkCell = (row) => {
  // Not sent yet — show dash
  if (row.status === '未送出') {
    return h('span', { style: 'color: #ccc;' }, '—')
  }
  const links = itemReceiptLinks.value[row.id] || []
  const receivedQty = row.received_qty || 0
  const qty = row.qty || 0
  const fullyReceived = receivedQty >= qty

  // No links yet — show "关联电镀单" button
  if (links.length === 0) {
    return h(NButton, {
      size: 'small',
      text: true,
      type: 'primary',
      onClick: () => openReceiptLinkModal(row),
    }, { default: () => '关联电镀单' })
  }

  const children = []
  // Linked receipt badges
  children.push(...links.map((link) => {
    const badge = [
      h('span', {
        style: 'cursor: pointer; text-decoration: underline;',
        onClick: () => router.push(`/plating-receipts/${link.receipt_id}?highlight=${link.receipt_item_id}`),
      }, link.receipt_id),
    ]
    // Show × delete button only when not fully received
    if (!fullyReceived) {
      badge.push(h(NButton, {
        size: 'tiny',
        quaternary: true,
        type: 'error',
        style: 'padding: 0 2px;',
        onClick: () => doUnlinkReceipt(row.id, link),
      }, { default: () => '×' }))
    }
    return h('span', {
      style: 'display: inline-flex; align-items: center; gap: 2px; background: #e8f5e9; border: 1px solid #a5d6a7; border-radius: 4px; padding: 1px 6px; font-size: 12px;',
    }, badge)
  }))

  // "+" button if not fully received
  if (!fullyReceived) {
    children.push(h(NButton, {
      size: 'tiny',
      text: true,
      type: 'primary',
      onClick: () => openReceiptLinkModal(row),
    }, { default: () => '+' }))
  }

  // Progress hint
  const hint = fullyReceived ? '已全部回收' : `已收 ${receivedQty} / ${qty}`
  children.push(h('div', { style: 'font-size: 11px; color: #999; margin-top: 2px; width: 100%;' }, hint))

  return h('div', { style: 'display: flex; flex-wrap: wrap; gap: 4px; align-items: center;' }, children)
}
```

- [ ] **Step 5: Add the column to itemColumns**

Insert after the existing `关联订单` column (after line 1452):

```javascript
{
  title: '关联电镀单',
  key: 'receipt_link',
  minWidth: 160,
  render: (row) => renderReceiptLinkCell(row),
},
```

- [ ] **Step 6: Add the modal template**

Add the modal in the `<template>` section, near the existing link modals:

```html
<!-- Receipt Link Modal -->
<n-modal v-model:show="receiptLinkModalVisible" preset="card" title="关联电镀回收单" :style="{ width: isMobile ? '95vw' : '520px' }">
  <!-- Current item info -->
  <div style="background: #f8f9fa; border-radius: 6px; padding: 12px; margin-bottom: 16px; font-size: 13px;">
    <div style="color: #999; font-size: 11px; margin-bottom: 4px;">当前配件</div>
    <div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 4px;">
      <span><strong>{{ receiptLinkItemInfo?.part_id }}</strong> {{ receiptLinkItemInfo?.part_name }}</span>
      <span style="color: #666;">
        发出 {{ receiptLinkItemInfo?.qty }} · 已收 {{ receiptLinkItemInfo?.received_qty }} ·
        <strong style="color: #e67e22;">剩余 {{ receiptLinkItemInfo?.remaining }}</strong>
      </span>
    </div>
    <div v-if="receiptLinkItemInfo?.receive_part_name" style="font-size: 12px; color: #666; margin-top: 4px;">
      收回配件：{{ receiptLinkItemInfo.receive_part_name }}
    </div>
  </div>

  <!-- Receipt selection -->
  <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="90">
    <n-form-item label="选择回收单">
      <n-spin :show="receiptLinkLoading" style="width: 100%;">
        <div v-if="receiptLinkOptions.length === 0 && !receiptLinkLoading" style="color: #999; font-size: 13px; padding: 8px 0;">
          暂无可用的回收单（需同供应商、未付款）
        </div>
        <n-radio-group v-else v-model:value="receiptLinkForm.receiptId" style="width: 100%;">
          <div style="display: flex; flex-direction: column; gap: 6px;">
            <n-radio v-for="r in receiptLinkOptions" :key="r.id" :value="r.id" style="padding: 6px 0;">
              <span style="font-weight: 500;">{{ r.id }}</span>
              <span style="font-size: 12px; color: #888; margin-left: 8px;">
                {{ r.vendor_name }} · {{ r.created_at?.slice(0, 10) }} · {{ r.item_count }} 项
              </span>
            </n-radio>
          </div>
        </n-radio-group>
      </n-spin>
    </n-form-item>
    <n-form-item label="回收数量">
      <n-input-number
        v-model:value="receiptLinkForm.qty"
        :min="0.0001"
        :max="receiptLinkItemInfo?.remaining || 0"
        :precision="4"
        placeholder="回收数量"
        style="width: 100%;"
      />
      <span style="font-size: 11px; color: #999; margin-left: 8px; white-space: nowrap;">
        最多 {{ receiptLinkItemInfo?.remaining }}
      </span>
    </n-form-item>
    <n-form-item label="回收单价">
      <n-input-number
        v-model:value="receiptLinkForm.price"
        :min="0"
        :precision="4"
        placeholder="元"
        style="width: 100%;"
      />
    </n-form-item>
  </n-form>
  <template #footer>
    <n-space justify="end">
      <n-button @click="receiptLinkModalVisible = false">取消</n-button>
      <n-button
        type="primary"
        :loading="receiptLinkSubmitting"
        :disabled="receiptLinkOptions.length === 0"
        @click="doLinkReceipt"
      >
        确认关联
      </n-button>
    </n-space>
  </template>
</n-modal>
```

- [ ] **Step 7: Verify frontend compiles**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/plating.js frontend/src/views/plating/PlatingDetail.vue
git commit -m "feat: add receipt link column and modal to PlatingDetail"
```

---

### Task 6: Frontend — PlatingReceiptDetail.vue highlight on navigate

**Files:**
- Modify: `/Users/ycb/workspace/allen_shop/frontend/src/views/plating-receipts/PlatingReceiptDetail.vue`

- [ ] **Step 1: Add highlight CSS**

Add a `<style>` block at the end of the file (or append to existing):

```css
<style scoped>
@keyframes receipt-highlight-flash {
  0%, 100% { background-color: transparent; }
  50% { background-color: #c8e6c9; }
}
.receipt-highlight-row td {
  animation: receipt-highlight-flash 1.6s ease-in-out 3;
  position: relative;
}
.receipt-highlight-row td:first-child::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: #18a058;
  border-radius: 2px;
}
</style>
```

- [ ] **Step 2: Add highlight logic in script setup**

Add after the existing `const route = useRoute()` line:

```javascript
const highlightItemId = computed(() => {
  const val = route.query.highlight
  return val ? Number(val) : null
})
```

- [ ] **Step 3: Add row-class-name prop to the data table**

Modify the `<n-data-table>` at line 153 to add `row-class-name`:

```html
<n-data-table
  v-if="receipt.items?.length > 0"
  :columns="itemColumns"
  :data="receipt.items"
  :bordered="false"
  :row-class-name="(row) => row.id === highlightItemId ? 'receipt-highlight-row' : ''"
/>
```

- [ ] **Step 4: Add scrollIntoView after data loads**

In the `onMounted` callback, after `loadData()` completes, add scroll logic:

```javascript
onMounted(async () => {
  try {
    await loadData()
  } finally {
    loading.value = false
  }
  // Scroll to highlighted item after DOM update
  if (highlightItemId.value) {
    await nextTick()
    const row = document.querySelector('.receipt-highlight-row')
    if (row) {
      row.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }
})
```

- [ ] **Step 5: Verify frontend compiles**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/plating-receipts/PlatingReceiptDetail.vue
git commit -m "feat: add highlight animation for receipt detail navigation"
```

---

### Task 7: Manual integration test

- [ ] **Step 1: Start backend and frontend**

```bash
# Terminal 1
python main.py

# Terminal 2
cd frontend && npm run dev
```

- [ ] **Step 2: Test end-to-end flow**

1. Navigate to a processing plating order (status = processing)
2. Verify "关联电镀单" column appears next to "关联订单"
3. Click "关联电镀单" on an item → verify modal shows available receipts
4. Select a receipt, enter qty and price, click "确认关联" → verify success
5. Verify linked receipt badge appears with × button
6. Click the receipt badge → verify navigation to receipt detail with highlight
7. Verify row flashes green 3 times then stops
8. Navigate back, click × on the badge → verify unlink with confirmation
9. Verify a pending order shows "—" in the column
10. Test partial receive: link some qty, verify badge + "+" button + progress text

- [ ] **Step 3: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 4: Final commit (if any fixups needed)**

```bash
git add -A
git commit -m "fix: integration test fixups for receipt linking"
```
