# Plating Receipt Optimizations — Backend Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance `list_pending_receive_items` with `date_on`, `exclude_item_ids`, and `created_at` return; add `POST /api/plating-receipts/{id}/items` endpoint for adding items to existing receipts.

**Architecture:** Two independent changes to the plating backend: (1) extend the pending-receive query with new filter params and return field, (2) add a new service function + API endpoint for adding items to an existing receipt, reusing validation logic from `create_plating_receipt`.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, pytest

**Spec:** `docs/superpowers/specs/2026-03-24-plating-receipt-optimizations-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `services/plating.py` | Modify | Add `date_on`, `exclude_item_ids` params + `created_at` to `list_pending_receive_items` |
| `api/plating.py` | Modify | Add `date_on`, `exclude_item_ids` query params to endpoint |
| `schemas/plating.py` | Modify | Add `created_at` field to `PendingReceiveItemResponse` |
| `services/plating_receipt.py` | Modify | Add `add_plating_receipt_items()` function |
| `api/plating_receipt.py` | Modify | Add `POST /{receipt_id}/items` endpoint |
| `schemas/plating_receipt.py` | Modify | Add `PlatingReceiptAddItemsRequest` schema |
| `tests/test_api_plating.py` | Modify | Add tests for new pending-receive filters |
| `tests/test_api_plating_receipt.py` | Modify | Add tests for add-items endpoint |

---

### Task 1: Add `created_at` to pending-receive response

**Files:**
- Modify: `schemas/plating.py:61-73`
- Modify: `services/plating.py:304-360`
- Modify: `tests/test_api_plating.py`

- [ ] **Step 1: Write failing test — `created_at` returned in pending-receive items**

In `tests/test_api_plating.py`, add:

```python
from services.plating import list_pending_receive_items


def test_pending_receive_items_include_created_at(client, db):
    """GET /api/plating/items/pending-receive returns created_at field."""
    from services.part import create_part
    from services.inventory import add_stock
    from services.plating import create_plating_order, send_plating_order

    part = create_part(db, {"name": "测试扣", "category": "小配件"})
    add_stock(db, "part", part.id, 100, "初始")
    order = create_plating_order(db, "厂A", [{"part_id": part.id, "qty": 50, "plating_method": "金色"}])
    send_plating_order(db, order.id)
    db.flush()

    resp = client.get("/api/plating/items/pending-receive")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    assert "created_at" in items[0]
    assert items[0]["created_at"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_plating.py::test_pending_receive_items_include_created_at -v`
Expected: FAIL — `created_at` not in response

- [ ] **Step 3: Add `created_at` to schema and service**

In `schemas/plating.py`, add to `PendingReceiveItemResponse` (after line 73):

```python
    created_at: Optional[datetime] = None
```

In `services/plating.py`, add `PlatingOrder.created_at` to the query SELECT list (after line 320, inside `db.query(...)`):

```python
            PlatingOrderItem.unit,
            PlatingOrder.created_at,
```

And add to the return dict (after line 357, inside the dict comprehension):

```python
            "unit": row.unit,
            "created_at": row.created_at,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_plating.py::test_pending_receive_items_include_created_at -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add schemas/plating.py services/plating.py tests/test_api_plating.py
git commit -m "feat: add created_at to pending-receive items response"
```

---

### Task 2: Add `date_on` filter to pending-receive

**Files:**
- Modify: `services/plating.py:304-360`
- Modify: `api/plating.py:70-73`
- Modify: `tests/test_api_plating.py`

- [ ] **Step 1: Write failing test — `date_on` filters by exact date**

In `tests/test_api_plating.py`, add:

```python
def test_pending_receive_items_filter_date_on(client, db):
    """GET /api/plating/items/pending-receive?date_on=YYYY-MM-DD filters by created_at date."""
    from services.part import create_part
    from services.inventory import add_stock
    from services.plating import create_plating_order, send_plating_order
    from models.plating_order import PlatingOrder
    from datetime import datetime

    part = create_part(db, {"name": "扣A", "category": "小配件"})
    add_stock(db, "part", part.id, 200, "初始")

    # Order 1 — today
    o1 = create_plating_order(db, "厂A", [{"part_id": part.id, "qty": 10, "plating_method": "金色"}])
    send_plating_order(db, o1.id)

    # Order 2 — force to a different date
    o2 = create_plating_order(db, "厂A", [{"part_id": part.id, "qty": 20, "plating_method": "银色"}])
    send_plating_order(db, o2.id)
    db.query(PlatingOrder).filter(PlatingOrder.id == o2.id).update(
        {"created_at": datetime(2025, 1, 15, 10, 0, 0)}
    )
    db.flush()

    # Filter by o2's date — should only return o2's item
    resp = client.get("/api/plating/items/pending-receive", params={"date_on": "2025-01-15"})
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["plating_order_id"] == o2.id

    # Filter by today — should only return o1's item
    from time_utils import now_beijing
    today_str = now_beijing().strftime("%Y-%m-%d")
    resp2 = client.get("/api/plating/items/pending-receive", params={"date_on": today_str})
    items2 = resp2.json()
    assert len(items2) == 1
    assert items2[0]["plating_order_id"] == o1.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_plating.py::test_pending_receive_items_filter_date_on -v`
Expected: FAIL — `date_on` param ignored, both items returned

- [ ] **Step 3: Implement `date_on` filter**

In `services/plating.py`, update the function signature (line 304):

```python
def list_pending_receive_items(db: Session, part_keyword: str = None, supplier_name: str = None, date_on: date_type = None, exclude_item_ids: list[int] = None) -> list:
```

Add the import at top of file (line 1):

```python
from datetime import datetime, timezone, date as date_type
```

And add `Date` to the sqlalchemy import (line 4):

```python
from sqlalchemy import func, or_, Date
```

Add the filter after the `supplier_name` filter (after line 331):

```python
    if date_on:
        q = q.filter(func.cast(PlatingOrder.created_at, Date) == date_on)
```

In `api/plating.py`, update the endpoint signature (line 71). First add the import at top:

```python
from datetime import date as date_type
```

Then update the endpoint:

```python
@router.get("/items/pending-receive", response_model=list[PendingReceiveItemResponse])
def api_list_pending_receive_items(
    part_keyword: str = None,
    supplier_name: str = None,
    date_on: date_type = None,
    db: Session = Depends(get_db),
):
    with service_errors():
        return list_pending_receive_items(db, part_keyword, supplier_name=supplier_name, date_on=date_on)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_plating.py::test_pending_receive_items_filter_date_on -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/plating.py api/plating.py tests/test_api_plating.py
git commit -m "feat: add date_on filter to pending-receive items endpoint"
```

---

### Task 3: Add `exclude_item_ids` filter to pending-receive

**Files:**
- Modify: `services/plating.py:304-360`
- Modify: `api/plating.py:70-73`
- Modify: `tests/test_api_plating.py`

- [ ] **Step 1: Write failing test — `exclude_item_ids` excludes specified items**

In `tests/test_api_plating.py`, add:

```python
def test_pending_receive_items_exclude_item_ids(client, db):
    """GET /api/plating/items/pending-receive?exclude_item_ids=1,2 excludes those items."""
    from services.part import create_part
    from services.inventory import add_stock
    from services.plating import create_plating_order, send_plating_order, get_plating_items

    p1 = create_part(db, {"name": "扣X", "category": "小配件"})
    p2 = create_part(db, {"name": "扣Y", "category": "小配件"})
    add_stock(db, "part", p1.id, 100, "初始")
    add_stock(db, "part", p2.id, 100, "初始")

    order = create_plating_order(db, "厂B", [
        {"part_id": p1.id, "qty": 10, "plating_method": "金色"},
        {"part_id": p2.id, "qty": 20, "plating_method": "银色"},
    ])
    send_plating_order(db, order.id)
    db.flush()

    items = get_plating_items(db, order.id)
    exclude_id = items[0].id

    # Without exclusion — both items
    resp_all = client.get("/api/plating/items/pending-receive", params={"supplier_name": "厂B"})
    assert len(resp_all.json()) == 2

    # With exclusion — only the non-excluded item
    resp_excl = client.get("/api/plating/items/pending-receive", params={
        "supplier_name": "厂B",
        "exclude_item_ids": str(exclude_id),
    })
    items_excl = resp_excl.json()
    assert len(items_excl) == 1
    assert items_excl[0]["id"] != exclude_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_plating.py::test_pending_receive_items_exclude_item_ids -v`
Expected: FAIL — `exclude_item_ids` param ignored, both items returned

- [ ] **Step 3: Implement `exclude_item_ids` filter**

In `services/plating.py`, add the filter inside `list_pending_receive_items` (after the `date_on` filter):

```python
    if exclude_item_ids:
        q = q.filter(PlatingOrderItem.id.notin_(exclude_item_ids))
```

In `api/plating.py`, update the endpoint to accept and parse `exclude_item_ids`:

```python
@router.get("/items/pending-receive", response_model=list[PendingReceiveItemResponse])
def api_list_pending_receive_items(
    part_keyword: str = None,
    supplier_name: str = None,
    date_on: date_type = None,
    exclude_item_ids: str = None,
    db: Session = Depends(get_db),
):
    parsed_exclude = None
    if exclude_item_ids:
        try:
            parsed_exclude = [int(x.strip()) for x in exclude_item_ids.split(",") if x.strip()]
        except ValueError:
            parsed_exclude = None
    with service_errors():
        return list_pending_receive_items(
            db, part_keyword, supplier_name=supplier_name,
            date_on=date_on, exclude_item_ids=parsed_exclude,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_plating.py::test_pending_receive_items_exclude_item_ids -v`
Expected: PASS

- [ ] **Step 5: Run all pending-receive tests together**

Run: `pytest tests/test_api_plating.py -k "pending_receive" -v`
Expected: All 3 new tests PASS

- [ ] **Step 6: Commit**

```bash
git add services/plating.py api/plating.py tests/test_api_plating.py
git commit -m "feat: add exclude_item_ids filter to pending-receive items endpoint"
```

---

### Task 4: Add `PlatingReceiptAddItemsRequest` schema

**Files:**
- Modify: `schemas/plating_receipt.py`

- [ ] **Step 1: Add the schema**

In `schemas/plating_receipt.py`, add after `PlatingReceiptCreate` (after line 30):

```python
class PlatingReceiptAddItemsRequest(BaseModel):
    items: List[PlatingReceiptItemCreate] = Field(min_length=1)
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from schemas.plating_receipt import PlatingReceiptAddItemsRequest; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add schemas/plating_receipt.py
git commit -m "feat: add PlatingReceiptAddItemsRequest schema"
```

---

### Task 5: Add `add_plating_receipt_items` service function

**Files:**
- Modify: `services/plating_receipt.py`
- Modify: `tests/test_api_plating_receipt.py`

- [ ] **Step 1: Write failing test — add items to unpaid receipt**

In `tests/test_api_plating_receipt.py`, add:

```python
def test_add_items_to_existing_receipt(client, db):
    """POST /api/plating-receipts/{id}/items adds new items to an unpaid receipt."""
    from services.part import create_part
    from services.inventory import add_stock, get_stock
    from services.plating import create_plating_order, send_plating_order, get_plating_items

    p1 = create_part(db, {"name": "扣1", "category": "小配件"})
    p2 = create_part(db, {"name": "扣2", "category": "小配件"})
    add_stock(db, "part", p1.id, 100, "初始")
    add_stock(db, "part", p2.id, 100, "初始")

    order = create_plating_order(db, "厂C", [
        {"part_id": p1.id, "qty": 50, "plating_method": "金色"},
        {"part_id": p2.id, "qty": 30, "plating_method": "银色"},
    ])
    send_plating_order(db, order.id)
    db.flush()
    items = get_plating_items(db, order.id)
    poi1_id, poi2_id = items[0].id, items[1].id

    # Create receipt with only p1
    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "厂C",
        "items": [{"plating_order_item_id": poi1_id, "part_id": p1.id, "qty": 10, "price": 1.0}],
    })
    assert resp.status_code == 201
    receipt_id = resp.json()["id"]
    assert len(resp.json()["items"]) == 1

    # Add p2
    add_resp = client.post(f"/api/plating-receipts/{receipt_id}/items", json={
        "items": [{"plating_order_item_id": poi2_id, "part_id": p2.id, "qty": 15, "price": 2.0}],
    })
    assert add_resp.status_code == 201
    data = add_resp.json()
    assert len(data["items"]) == 2
    assert data["total_amount"] == 40.0  # 10*1.0 + 15*2.0

    # Stock updated
    assert get_stock(db, "part", p2.id) == 100 - 30 + 15  # sent 30, received 15
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_plating_receipt.py::test_add_items_to_existing_receipt -v`
Expected: FAIL — 404 or 405 (endpoint doesn't exist)

- [ ] **Step 3: Write the service function**

In `services/plating_receipt.py`, add after `create_plating_receipt` (after line 159):

```python
def add_plating_receipt_items(
    db: Session,
    receipt_id: str,
    items: list,
) -> PlatingReceipt:
    receipt = db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"PlatingReceipt not found: {receipt_id}")
    if receipt.status == "已付款":
        raise ValueError("已付款的回收单不能添加明细")

    # Gather existing plating_order_item_ids to prevent duplicates
    existing_poi_ids = {
        ri.plating_order_item_id
        for ri in get_plating_receipt_items(db, receipt_id)
    }

    affected_plating_orders = set()

    for item_data in items:
        poi_id = item_data["plating_order_item_id"]
        if poi_id in existing_poi_ids:
            raise ValueError(f"PlatingOrderItem {poi_id} 已在该回收单中，不能重复添加")

        poi = db.query(PlatingOrderItem).filter(
            PlatingOrderItem.id == poi_id
        ).first()
        if poi is None:
            raise ValueError(f"PlatingOrderItem not found: {poi_id}")
        if poi.status not in ("电镀中", "已收回"):
            raise ValueError(f"PlatingOrderItem {poi.id} status is '{poi.status}', cannot receive")

        # Validate vendor consistency
        plating_order = db.query(PlatingOrder).filter(PlatingOrder.id == poi.plating_order_id).first()
        if plating_order and plating_order.supplier_name != receipt.vendor_name:
            raise ValueError(
                f"PlatingOrderItem {poi.id} 属于供应商「{plating_order.supplier_name}」，"
                f"与回收单商家「{receipt.vendor_name}」不一致"
            )

        qty = item_data["qty"]
        remaining = float(poi.qty) - float(poi.received_qty or 0)
        if qty > remaining:
            raise ValueError(f"PlatingOrderItem {poi.id}: 最多可回收 {remaining}, 当前填写 {qty}")

        expected_part_id = item_data["part_id"]
        receive_id = poi.receive_part_id or poi.part_id
        if expected_part_id != receive_id:
            raise ValueError(f"part_id mismatch for PlatingOrderItem {poi.id}")

        price = Decimal(str(item_data["price"])).quantize(_Q7, rounding=ROUND_HALF_UP) if item_data.get("price") is not None else None
        amount = (Decimal(str(qty)) * price).quantize(_Q7, rounding=ROUND_HALF_UP) if price is not None else None

        db.add(PlatingReceiptItem(
            plating_receipt_id=receipt_id,
            plating_order_item_id=poi.id,
            part_id=expected_part_id,
            qty=qty,
            unit=item_data.get("unit", "个"),
            price=price,
            amount=amount,
            note=item_data.get("note"),
        ))

        _apply_receive(db, poi, qty)
        affected_plating_orders.add(poi.plating_order_id)
        existing_poi_ids.add(poi_id)

    _recalc_total(db, receipt)
    db.flush()

    for po_id in affected_plating_orders:
        _check_plating_order_completion(db, po_id)
    db.flush()

    _enrich_receipt(db, receipt)
    return receipt
```

- [ ] **Step 4: Write the API endpoint**

In `api/plating_receipt.py`, add the import for the new schema and service function.

Add to the schema import block:

```python
from schemas.plating_receipt import (
    PlatingReceiptAddItemsRequest,
    ...existing imports...
)
```

Add to the service import block:

```python
from services.plating_receipt import (
    add_plating_receipt_items,
    ...existing imports...
)
```

Add the endpoint after `api_create_plating_receipt` (after line 57):

```python
@router.post("/{receipt_id}/items", response_model=PlatingReceiptResponse, status_code=201)
def api_add_plating_receipt_items(receipt_id: str, body: PlatingReceiptAddItemsRequest, db: Session = Depends(get_db)):
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"PlatingReceipt {receipt_id} not found")
    with service_errors():
        receipt = add_plating_receipt_items(
            db,
            receipt_id=receipt_id,
            items=[item.model_dump() for item in body.items],
        )
    cost_diffs = detect_plating_cost_diffs(db, receipt)
    resp = PlatingReceiptResponse.model_validate(receipt)
    resp.cost_diffs = [CostDiffItem(**d) for d in cost_diffs]
    return resp
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_api_plating_receipt.py::test_add_items_to_existing_receipt -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/plating_receipt.py api/plating_receipt.py schemas/plating_receipt.py tests/test_api_plating_receipt.py
git commit -m "feat: add POST /plating-receipts/{id}/items endpoint for adding items"
```

---

### Task 6: Add validation tests for add-items edge cases

**Files:**
- Modify: `tests/test_api_plating_receipt.py`

- [ ] **Step 1: Write test — reject adding to paid receipt**

```python
def test_add_items_to_paid_receipt_rejected(client, db):
    """Cannot add items to a paid receipt."""
    from services.part import create_part
    from services.inventory import add_stock
    from services.plating import create_plating_order, send_plating_order, get_plating_items

    p1 = create_part(db, {"name": "扣P", "category": "小配件"})
    p2 = create_part(db, {"name": "扣Q", "category": "小配件"})
    add_stock(db, "part", p1.id, 100, "初始")
    add_stock(db, "part", p2.id, 100, "初始")

    order = create_plating_order(db, "厂D", [
        {"part_id": p1.id, "qty": 50, "plating_method": "金色"},
        {"part_id": p2.id, "qty": 30, "plating_method": "银色"},
    ])
    send_plating_order(db, order.id)
    db.flush()
    items = get_plating_items(db, order.id)

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "厂D",
        "items": [{"plating_order_item_id": items[0].id, "part_id": p1.id, "qty": 10}],
        "status": "已付款",
    })
    receipt_id = resp.json()["id"]

    add_resp = client.post(f"/api/plating-receipts/{receipt_id}/items", json={
        "items": [{"plating_order_item_id": items[1].id, "part_id": p2.id, "qty": 5}],
    })
    assert add_resp.status_code == 400
```

- [ ] **Step 2: Write test — reject duplicate plating_order_item_id**

```python
def test_add_items_duplicate_poi_rejected(client, db):
    """Cannot add a plating_order_item that is already in the receipt."""
    from services.part import create_part
    from services.inventory import add_stock
    from services.plating import create_plating_order, send_plating_order, get_plating_items

    part = create_part(db, {"name": "扣R", "category": "小配件"})
    add_stock(db, "part", part.id, 100, "初始")

    order = create_plating_order(db, "厂E", [
        {"part_id": part.id, "qty": 50, "plating_method": "金色"},
    ])
    send_plating_order(db, order.id)
    db.flush()
    poi_id = get_plating_items(db, order.id)[0].id

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "厂E",
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 10}],
    })
    receipt_id = resp.json()["id"]

    # Try to add the same poi again
    add_resp = client.post(f"/api/plating-receipts/{receipt_id}/items", json={
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 5}],
    })
    assert add_resp.status_code == 400
```

- [ ] **Step 3: Write test — reject exceeding remaining qty**

```python
def test_add_items_exceeds_remaining_rejected(client, db):
    """Cannot add more qty than remaining for a plating order item."""
    from services.part import create_part
    from services.inventory import add_stock
    from services.plating import create_plating_order, send_plating_order, get_plating_items

    p1 = create_part(db, {"name": "扣S", "category": "小配件"})
    p2 = create_part(db, {"name": "扣T", "category": "小配件"})
    add_stock(db, "part", p1.id, 100, "初始")
    add_stock(db, "part", p2.id, 100, "初始")

    order = create_plating_order(db, "厂F", [
        {"part_id": p1.id, "qty": 50, "plating_method": "金色"},
        {"part_id": p2.id, "qty": 10, "plating_method": "银色"},
    ])
    send_plating_order(db, order.id)
    db.flush()
    items = get_plating_items(db, order.id)

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "厂F",
        "items": [{"plating_order_item_id": items[0].id, "part_id": p1.id, "qty": 10}],
    })
    receipt_id = resp.json()["id"]

    # Try to add p2 with qty exceeding what was sent
    add_resp = client.post(f"/api/plating-receipts/{receipt_id}/items", json={
        "items": [{"plating_order_item_id": items[1].id, "part_id": p2.id, "qty": 999}],
    })
    assert add_resp.status_code == 400
```

- [ ] **Step 4: Write test — reject vendor mismatch**

```python
def test_add_items_vendor_mismatch_rejected(client, db):
    """Cannot add items from a different vendor's plating order."""
    from services.part import create_part
    from services.inventory import add_stock
    from services.plating import create_plating_order, send_plating_order, get_plating_items

    part = create_part(db, {"name": "扣V", "category": "小配件"})
    add_stock(db, "part", part.id, 200, "初始")

    order_a = create_plating_order(db, "厂G", [{"part_id": part.id, "qty": 50, "plating_method": "金色"}])
    send_plating_order(db, order_a.id)

    order_b = create_plating_order(db, "厂H", [{"part_id": part.id, "qty": 50, "plating_method": "银色"}])
    send_plating_order(db, order_b.id)
    db.flush()

    poi_a = get_plating_items(db, order_a.id)[0].id
    poi_b = get_plating_items(db, order_b.id)[0].id

    # Create receipt for 厂G
    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "厂G",
        "items": [{"plating_order_item_id": poi_a, "part_id": part.id, "qty": 10}],
    })
    receipt_id = resp.json()["id"]

    # Try to add item from 厂H's order
    add_resp = client.post(f"/api/plating-receipts/{receipt_id}/items", json={
        "items": [{"plating_order_item_id": poi_b, "part_id": part.id, "qty": 10}],
    })
    assert add_resp.status_code == 400
```

- [ ] **Step 5: Run all new tests**

Run: `pytest tests/test_api_plating_receipt.py -k "add_items" -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_api_plating_receipt.py
git commit -m "test: add edge case tests for add-items endpoint"
```

---

### Task 7: Run full test suite

- [ ] **Step 1: Run all tests**

Run: `pytest -v`
Expected: All tests PASS, no regressions

- [ ] **Step 2: Final commit if any fixups needed**

If any tests broke, fix and commit with `fix:` prefix.
