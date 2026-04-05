# 生产损耗确认 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to confirm production losses on plating/handcraft orders, enabling order completion when received quantity is less than sent quantity.

**Architecture:** New `production_loss` table for loss records. Confirming loss increments `received_qty` to trigger existing status/completion logic. Inventory log entry with `change_qty=0` for audit trail. Entry points on both order detail pages and receipt pages.

**Tech Stack:** FastAPI, SQLAlchemy, Vue 3 + Naive UI

**Spec:** `docs/superpowers/specs/2026-04-05-production-loss-design.md`

---

## File Structure

| File | Changes |
|------|---------|
| `models/production_loss.py` | New model: ProductionLoss |
| `models/__init__.py` | Import new model |
| `schemas/production_loss.py` | New schemas |
| `services/production_loss.py` | New service: confirm loss logic |
| `api/plating.py` | Add confirm-loss endpoint for plating items |
| `api/handcraft.py` | Add confirm-loss endpoint for handcraft items |
| `api/plating_receipt.py` | Add batch confirm-loss endpoint |
| `api/handcraft_receipt.py` | Add batch confirm-loss endpoint |
| `frontend/src/api/production_loss.js` | New API functions |
| `frontend/src/views/plating/PlatingDetail.vue` | Add loss UI on plating items |
| `frontend/src/views/handcraft/HandcraftDetail.vue` | Add loss UI on handcraft items |
| `tests/test_production_loss.py` | New test file |

---

## Task 1: Model — ProductionLoss Table

**Files:**
- Create: `models/production_loss.py`
- Modify: `models/__init__.py`

- [ ] **Step 1: Create ProductionLoss model**

Create `models/production_loss.py`:

```python
from sqlalchemy import Column, Integer, String, Numeric, Text, DateTime
from database import Base
from time_utils import now_beijing


class ProductionLoss(Base):
    __tablename__ = "production_loss"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_type = Column(String, nullable=False)          # "plating" or "handcraft"
    order_id = Column(String, nullable=False)             # EP-xxx or HC-xxx
    item_id = Column(Integer, nullable=False)             # PlatingOrderItem.id etc.
    item_type = Column(String, nullable=False)            # "plating_item", "handcraft_part", "handcraft_jewelry"
    part_id = Column(String, nullable=True)               # for part losses
    jewelry_id = Column(String, nullable=True)            # for jewelry losses
    loss_qty = Column(Numeric(10, 4), nullable=False)
    deduct_amount = Column(Numeric(18, 7), nullable=True)
    reason = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
```

- [ ] **Step 2: Add import to models/__init__.py**

Add to `models/__init__.py`:

```python
from models.production_loss import ProductionLoss
```

- [ ] **Step 3: Verify model loads**

Run: `python -c "from models.production_loss import ProductionLoss; print(ProductionLoss.__tablename__)"`
Expected: `production_loss`

- [ ] **Step 4: Commit**

```bash
git add models/production_loss.py models/__init__.py
git commit -m "feat: add ProductionLoss model"
```

---

## Task 2: Schemas

**Files:**
- Create: `schemas/production_loss.py`

- [ ] **Step 1: Create schemas**

Create `schemas/production_loss.py`:

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ConfirmLossRequest(BaseModel):
    loss_qty: float
    deduct_amount: float | None = None
    reason: str | None = None
    note: str | None = None


class ConfirmLossHandcraftRequest(ConfirmLossRequest):
    item_type: str  # "part" or "jewelry"


class BatchConfirmLossPlatingItem(BaseModel):
    plating_order_item_id: int
    loss_qty: float
    deduct_amount: float | None = None
    reason: str | None = None


class BatchConfirmLossPlatingRequest(BaseModel):
    items: list[BatchConfirmLossPlatingItem]


class BatchConfirmLossHandcraftItem(BaseModel):
    item_id: int
    item_type: str  # "part" or "jewelry"
    loss_qty: float
    deduct_amount: float | None = None
    reason: str | None = None


class BatchConfirmLossHandcraftRequest(BaseModel):
    items: list[BatchConfirmLossHandcraftItem]


class BatchConfirmLossResponse(BaseModel):
    confirmed_count: int


class ProductionLossResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_type: str
    order_id: str
    item_id: int
    item_type: str
    part_id: str | None = None
    jewelry_id: str | None = None
    loss_qty: float
    deduct_amount: float | None = None
    reason: str | None = None
    note: str | None = None
    created_at: datetime
```

- [ ] **Step 2: Verify import**

Run: `python -c "from schemas.production_loss import ConfirmLossRequest, ProductionLossResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add schemas/production_loss.py
git commit -m "feat: add production loss schemas"
```

---

## Task 3: Service — Confirm Loss Logic

**Files:**
- Create: `services/production_loss.py`
- Test: `tests/test_production_loss.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_production_loss.py`:

```python
import pytest
from decimal import Decimal
from models.part import Part
from models.plating_order import PlatingOrder, PlatingOrderItem
from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
from models.jewelry import Jewelry
from models.production_loss import ProductionLoss
from services.inventory import add_stock, get_stock


def _setup_plating_with_partial_receive(db):
    """Create plating order: sent 100, received 80, gap 20."""
    part = Part(id="PJ-X-LOSS1", name="损耗测试配件", category="小配件")
    db.add(part)
    db.flush()
    add_stock(db, "part", part.id, 100, "入库")
    db.flush()

    po = PlatingOrder(id="EP-LOSS1", supplier_name="电镀商", status="processing")
    db.add(po)
    db.flush()
    poi = PlatingOrderItem(
        plating_order_id=po.id,
        part_id=part.id,
        qty=100,
        received_qty=80,
        status="电镀中",
    )
    db.add(poi)
    db.flush()
    return part, po, poi


def _setup_handcraft_with_partial_receive(db):
    """Create handcraft order: part sent 50, received 40; jewelry sent 30, received 25."""
    part = Part(id="PJ-X-LOSS2", name="手工损耗配件", category="小配件")
    jewelry = Jewelry(id="SP-LOSS1", name="手工损耗饰品", category="项链")
    db.add_all([part, jewelry])
    db.flush()
    add_stock(db, "part", part.id, 50, "入库")
    db.flush()

    hc = HandcraftOrder(id="HC-LOSS1", supplier_name="手工商", status="processing")
    db.add(hc)
    db.flush()
    hc_part = HandcraftPartItem(
        handcraft_order_id=hc.id,
        part_id=part.id,
        qty=50,
        received_qty=40,
        status="制作中",
    )
    hc_jewelry = HandcraftJewelryItem(
        handcraft_order_id=hc.id,
        jewelry_id=jewelry.id,
        qty=30,
        received_qty=25,
        status="制作中",
    )
    db.add_all([hc_part, hc_jewelry])
    db.flush()
    return part, jewelry, hc, hc_part, hc_jewelry


def test_confirm_plating_loss(client, db):
    """Confirm loss on plating item: received_qty increases, loss record created."""
    part, po, poi = _setup_plating_with_partial_receive(db)
    resp = client.post(
        f"/api/plating/{po.id}/items/{poi.id}/confirm-loss",
        json={"loss_qty": 20, "reason": "电镀损耗"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["loss_qty"] == 20
    assert data["order_type"] == "plating"

    # Verify received_qty updated
    db.refresh(poi)
    assert float(poi.received_qty) == 100
    assert poi.status == "已收回"

    # Verify loss record exists
    loss = db.query(ProductionLoss).filter_by(item_id=poi.id).first()
    assert loss is not None
    assert float(loss.loss_qty) == 20


def test_confirm_plating_loss_completes_order(client, db):
    """After confirming loss on all items, plating order becomes completed."""
    part, po, poi = _setup_plating_with_partial_receive(db)
    client.post(
        f"/api/plating/{po.id}/items/{poi.id}/confirm-loss",
        json={"loss_qty": 20},
    )
    db.refresh(po)
    assert po.status == "completed"


def test_confirm_plating_loss_exceeds_gap(client, db):
    """Cannot confirm loss greater than gap."""
    part, po, poi = _setup_plating_with_partial_receive(db)
    resp = client.post(
        f"/api/plating/{po.id}/items/{poi.id}/confirm-loss",
        json={"loss_qty": 25},  # gap is only 20
    )
    assert resp.status_code == 400


def test_confirm_plating_loss_with_deduction(client, db):
    """Confirm loss with deduction amount."""
    part, po, poi = _setup_plating_with_partial_receive(db)
    resp = client.post(
        f"/api/plating/{po.id}/items/{poi.id}/confirm-loss",
        json={"loss_qty": 20, "deduct_amount": 50.0, "reason": "品质不良"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["deduct_amount"] == 50.0
    assert data["reason"] == "品质不良"


def test_confirm_handcraft_part_loss(client, db):
    """Confirm loss on handcraft part item."""
    part, jewelry, hc, hc_part, hc_jewelry = _setup_handcraft_with_partial_receive(db)
    resp = client.post(
        f"/api/handcraft/{hc.id}/items/{hc_part.id}/confirm-loss",
        json={"loss_qty": 10, "item_type": "part"},
    )
    assert resp.status_code == 200
    db.refresh(hc_part)
    assert float(hc_part.received_qty) == 50
    assert hc_part.status == "已收回"


def test_confirm_handcraft_jewelry_loss(client, db):
    """Confirm loss on handcraft jewelry item."""
    part, jewelry, hc, hc_part, hc_jewelry = _setup_handcraft_with_partial_receive(db)
    resp = client.post(
        f"/api/handcraft/{hc.id}/items/{hc_jewelry.id}/confirm-loss",
        json={"loss_qty": 5, "item_type": "jewelry"},
    )
    assert resp.status_code == 200
    db.refresh(hc_jewelry)
    assert hc_jewelry.received_qty == 30
    assert hc_jewelry.status == "已收回"


def test_confirm_loss_inventory_log(client, db):
    """Confirm loss writes inventory log with change_qty=0."""
    from models.inventory_log import InventoryLog
    part, po, poi = _setup_plating_with_partial_receive(db)
    client.post(
        f"/api/plating/{po.id}/items/{poi.id}/confirm-loss",
        json={"loss_qty": 20, "reason": "正常损耗"},
    )
    log = (
        db.query(InventoryLog)
        .filter_by(item_type="part", item_id=part.id, reason="电镀损耗")
        .first()
    )
    assert log is not None
    assert float(log.change_qty) == 0
    assert "损耗 20" in log.note
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_production_loss.py -v`
Expected: FAIL

- [ ] **Step 3: Implement service**

Create `services/production_loss.py`:

```python
from sqlalchemy.orm import Session
from decimal import Decimal
from models.production_loss import ProductionLoss
from models.plating_order import PlatingOrder, PlatingOrderItem
from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
from models.inventory_log import InventoryLog
from services.plating_receipt import _check_plating_order_completion
from services.handcraft_receipt import _check_handcraft_order_completion
from time_utils import now_beijing


def confirm_plating_loss(
    db: Session,
    order_id: str,
    item_id: int,
    loss_qty: float,
    deduct_amount: float | None = None,
    reason: str | None = None,
    note: str | None = None,
) -> ProductionLoss:
    po = db.query(PlatingOrder).filter_by(id=order_id).first()
    if not po:
        raise ValueError(f"电镀单 {order_id} 不存在")

    poi = db.query(PlatingOrderItem).filter_by(id=item_id, plating_order_id=order_id).first()
    if not poi:
        raise ValueError(f"电镀单项 {item_id} 不存在")

    gap = float(poi.qty) - float(poi.received_qty or 0)
    if loss_qty <= 0:
        raise ValueError("损耗数量必须大于 0")
    if loss_qty > gap:
        raise ValueError(f"损耗数量 {loss_qty} 超过差额 {gap}")

    # Create loss record
    loss = ProductionLoss(
        order_type="plating",
        order_id=order_id,
        item_id=item_id,
        item_type="plating_item",
        part_id=poi.part_id,
        loss_qty=loss_qty,
        deduct_amount=Decimal(str(deduct_amount)) if deduct_amount else None,
        reason=reason,
        note=note,
    )
    db.add(loss)

    # Write inventory log (change_qty=0 for audit)
    log = InventoryLog(
        item_type="part",
        item_id=poi.part_id,
        change_qty=0,
        reason="电镀损耗",
        note=f"损耗 {loss_qty}，电镀单 {order_id}" + (f"，原因：{reason}" if reason else ""),
    )
    db.add(log)

    # Increment received_qty to trigger existing status logic
    poi.received_qty = Decimal(str(float(poi.received_qty or 0) + loss_qty))
    if float(poi.received_qty) >= float(poi.qty):
        poi.status = "已收回"
    db.flush()

    # Check order completion
    _check_plating_order_completion(db, order_id)
    db.flush()

    return loss


def confirm_handcraft_loss(
    db: Session,
    order_id: str,
    item_id: int,
    item_type: str,
    loss_qty: float,
    deduct_amount: float | None = None,
    reason: str | None = None,
    note: str | None = None,
) -> ProductionLoss:
    hc = db.query(HandcraftOrder).filter_by(id=order_id).first()
    if not hc:
        raise ValueError(f"手工单 {order_id} 不存在")

    if item_type == "part":
        item = db.query(HandcraftPartItem).filter_by(id=item_id, handcraft_order_id=order_id).first()
        if not item:
            raise ValueError(f"手工单配件项 {item_id} 不存在")
        loss_item_type = "handcraft_part"
        part_id = item.part_id
        jewelry_id = None
        inv_item_type = "part"
        inv_item_id = item.part_id
    elif item_type == "jewelry":
        item = db.query(HandcraftJewelryItem).filter_by(id=item_id, handcraft_order_id=order_id).first()
        if not item:
            raise ValueError(f"手工单饰品项 {item_id} 不存在")
        loss_item_type = "handcraft_jewelry"
        part_id = None
        jewelry_id = item.jewelry_id
        inv_item_type = "jewelry"
        inv_item_id = item.jewelry_id
    else:
        raise ValueError(f"无效的 item_type: {item_type}")

    gap = float(item.qty) - float(item.received_qty or 0)
    if loss_qty <= 0:
        raise ValueError("损耗数量必须大于 0")
    if loss_qty > gap:
        raise ValueError(f"损耗数量 {loss_qty} 超过差额 {gap}")

    # Create loss record
    loss = ProductionLoss(
        order_type="handcraft",
        order_id=order_id,
        item_id=item_id,
        item_type=loss_item_type,
        part_id=part_id,
        jewelry_id=jewelry_id,
        loss_qty=loss_qty,
        deduct_amount=Decimal(str(deduct_amount)) if deduct_amount else None,
        reason=reason,
        note=note,
    )
    db.add(loss)

    # Write inventory log
    log = InventoryLog(
        item_type=inv_item_type,
        item_id=inv_item_id,
        change_qty=0,
        reason="手工损耗",
        note=f"损耗 {loss_qty}，手工单 {order_id}" + (f"，原因：{reason}" if reason else ""),
    )
    db.add(log)

    # Increment received_qty
    if item_type == "jewelry":
        item.received_qty = int(item.received_qty or 0) + int(loss_qty)
    else:
        item.received_qty = Decimal(str(float(item.received_qty or 0) + loss_qty))

    if float(item.received_qty) >= float(item.qty):
        item.status = "已收回"
    db.flush()

    # Check order completion
    _check_handcraft_order_completion(db, order_id)
    db.flush()

    return loss


def get_losses(
    db: Session,
    order_type: str | None = None,
    order_id: str | None = None,
) -> list[ProductionLoss]:
    q = db.query(ProductionLoss)
    if order_type:
        q = q.filter(ProductionLoss.order_type == order_type)
    if order_id:
        q = q.filter(ProductionLoss.order_id == order_id)
    return q.order_by(ProductionLoss.created_at.desc()).all()


def get_item_loss(db: Session, item_id: int, item_type: str) -> ProductionLoss | None:
    """Get loss record for a specific item, if any."""
    return (
        db.query(ProductionLoss)
        .filter_by(item_id=item_id, item_type=item_type)
        .first()
    )
```

- [ ] **Step 4: Add API endpoints**

In `api/plating.py`, add:

```python
from services.production_loss import confirm_plating_loss
from schemas.production_loss import ConfirmLossRequest, ProductionLossResponse

@router.post("/{order_id}/items/{item_id}/confirm-loss", response_model=ProductionLossResponse)
def api_confirm_plating_loss(order_id: str, item_id: int, body: ConfirmLossRequest, db: Session = Depends(get_db)):
    with service_errors():
        return confirm_plating_loss(
            db, order_id, item_id,
            loss_qty=body.loss_qty,
            deduct_amount=body.deduct_amount,
            reason=body.reason,
            note=body.note,
        )
```

In `api/handcraft.py`, add:

```python
from services.production_loss import confirm_handcraft_loss
from schemas.production_loss import ConfirmLossHandcraftRequest, ProductionLossResponse

@router.post("/{order_id}/items/{item_id}/confirm-loss", response_model=ProductionLossResponse)
def api_confirm_handcraft_loss(order_id: str, item_id: int, body: ConfirmLossHandcraftRequest, db: Session = Depends(get_db)):
    with service_errors():
        return confirm_handcraft_loss(
            db, order_id, item_id,
            item_type=body.item_type,
            loss_qty=body.loss_qty,
            deduct_amount=body.deduct_amount,
            reason=body.reason,
            note=body.note,
        )
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_production_loss.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add services/production_loss.py api/plating.py api/handcraft.py tests/test_production_loss.py
git commit -m "feat: add confirm-loss endpoints for plating and handcraft orders"
```

---

## Task 4: API — Batch Confirm Loss on Receipts

**Files:**
- Modify: `api/plating_receipt.py`
- Modify: `api/handcraft_receipt.py`
- Test: `tests/test_production_loss.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_production_loss.py`:

```python
def test_batch_confirm_plating_loss_via_receipt(client, db):
    """Batch confirm losses from receipt endpoint."""
    from models.plating_order import PlatingOrder, PlatingOrderItem
    # Create plating receipt scenario
    part = Part(id="PJ-X-LOSS3", name="批量损耗配件", category="小配件")
    db.add(part)
    db.flush()
    add_stock(db, "part", part.id, 200, "入库")
    db.flush()

    po = PlatingOrder(id="EP-LOSS2", supplier_name="电镀商B", status="processing")
    db.add(po)
    db.flush()
    poi1 = PlatingOrderItem(plating_order_id=po.id, part_id=part.id, qty=100, received_qty=90, status="电镀中")
    poi2 = PlatingOrderItem(plating_order_id=po.id, part_id=part.id, qty=50, received_qty=45, status="电镀中")
    db.add_all([poi1, poi2])
    db.flush()

    # Create a receipt to get receipt_id
    from services.plating_receipt import create_plating_receipt
    receipt = create_plating_receipt(db, vendor_name="电镀商B", items=[
        {"plating_order_item_id": poi1.id, "part_id": part.id, "qty": 90, "price": 1.0},
    ])
    db.flush()

    resp = client.post(
        f"/api/plating-receipts/{receipt['id']}/confirm-loss",
        json={
            "items": [
                {"plating_order_item_id": poi1.id, "loss_qty": 10},
                {"plating_order_item_id": poi2.id, "loss_qty": 5},
            ]
        },
    )
    assert resp.status_code == 200
    assert resp.json()["confirmed_count"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_production_loss.py::test_batch_confirm_plating_loss_via_receipt -v`
Expected: FAIL

- [ ] **Step 3: Add batch endpoints**

In `api/plating_receipt.py`, add:

```python
from services.production_loss import confirm_plating_loss
from schemas.production_loss import BatchConfirmLossPlatingRequest, BatchConfirmLossResponse

@router.post("/{receipt_id}/confirm-loss", response_model=BatchConfirmLossResponse)
def api_batch_confirm_plating_loss(receipt_id: str, body: BatchConfirmLossPlatingRequest, db: Session = Depends(get_db)):
    from services.plating_receipt import get_plating_receipt
    receipt = get_plating_receipt(db, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail=f"收回单 {receipt_id} 不存在")

    count = 0
    with service_errors():
        for item in body.items:
            # Look up the plating order via the order item
            poi = db.query(PlatingOrderItem).filter_by(id=item.plating_order_item_id).first()
            if poi and float(poi.qty) > float(poi.received_qty or 0):
                confirm_plating_loss(
                    db, poi.plating_order_id, item.plating_order_item_id,
                    loss_qty=item.loss_qty,
                    deduct_amount=item.deduct_amount,
                    reason=item.reason,
                )
                count += 1
    return {"confirmed_count": count}
```

In `api/handcraft_receipt.py`, add similarly:

```python
from services.production_loss import confirm_handcraft_loss
from schemas.production_loss import BatchConfirmLossHandcraftRequest, BatchConfirmLossResponse

@router.post("/{receipt_id}/confirm-loss", response_model=BatchConfirmLossResponse)
def api_batch_confirm_handcraft_loss(receipt_id: str, body: BatchConfirmLossHandcraftRequest, db: Session = Depends(get_db)):
    from services.handcraft_receipt import get_handcraft_receipt
    receipt = get_handcraft_receipt(db, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail=f"收回单 {receipt_id} 不存在")

    count = 0
    with service_errors():
        for item in body.items:
            if item.item_type == "part":
                hc_item = db.query(HandcraftPartItem).filter_by(id=item.item_id).first()
            else:
                hc_item = db.query(HandcraftJewelryItem).filter_by(id=item.item_id).first()
            if hc_item and float(hc_item.qty) > float(hc_item.received_qty or 0):
                confirm_handcraft_loss(
                    db, hc_item.handcraft_order_id, item.item_id,
                    item_type=item.item_type,
                    loss_qty=item.loss_qty,
                    deduct_amount=item.deduct_amount,
                    reason=item.reason,
                )
                count += 1
    return {"confirmed_count": count}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_production_loss.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add api/plating_receipt.py api/handcraft_receipt.py tests/test_production_loss.py
git commit -m "feat: add batch confirm-loss endpoints on receipt pages"
```

---

## Task 5: Frontend — Confirm Loss UI

**Files:**
- Create: `frontend/src/api/production_loss.js`
- Modify: `frontend/src/views/plating/PlatingDetail.vue`
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue`

- [ ] **Step 1: Add API functions**

Create `frontend/src/api/production_loss.js`:

```javascript
import request from './index'

export function confirmPlatingLoss(orderId, itemId, data) {
  return request.post(`/plating/${orderId}/items/${itemId}/confirm-loss`, data)
}

export function confirmHandcraftLoss(orderId, itemId, data) {
  return request.post(`/handcraft/${orderId}/items/${itemId}/confirm-loss`, data)
}

export function batchConfirmPlatingLoss(receiptId, data) {
  return request.post(`/plating-receipts/${receiptId}/confirm-loss`, data)
}

export function batchConfirmHandcraftLoss(receiptId, data) {
  return request.post(`/handcraft-receipts/${receiptId}/confirm-loss`, data)
}
```

- [ ] **Step 2: Add loss UI to PlatingDetail.vue**

In the plating order items table, for each item where `received_qty < qty` and status is "电镀中":

Add a column or inline display showing:
- `已收回 {received_qty} / 发出 {qty}，差额 {gap}`
- 【确认损耗】button

Add modal state and handler:

```javascript
import { confirmPlatingLoss } from '@/api/production_loss'

const showLossModal = ref(false)
const lossTarget = ref(null)
const lossForm = ref({ loss_qty: 0, deduct_amount: null, reason: '', note: '' })

function openLossModal(item) {
  lossTarget.value = item
  const gap = item.qty - (item.received_qty || 0)
  lossForm.value = { loss_qty: gap, deduct_amount: null, reason: '', note: '' }
  showLossModal.value = true
}

async function confirmLoss() {
  try {
    await confirmPlatingLoss(orderId.value, lossTarget.value.id, lossForm.value)
    showLossModal.value = false
    message.success('损耗已确认')
    await loadOrder()
  } catch (err) {
    message.error(err.response?.data?.detail || '确认失败')
  }
}
```

Modal template:

```html
<n-modal v-model:show="showLossModal" preset="card" title="确认损耗" style="width: 420px;">
  <n-form label-placement="left" label-width="80">
    <n-form-item label="损耗数量">
      <n-input-number v-model:value="lossForm.loss_qty" :min="0.01" :max="lossTarget?.qty - (lossTarget?.received_qty || 0)" />
    </n-form-item>
    <n-form-item label="扣款金额">
      <n-input-number v-model:value="lossForm.deduct_amount" :min="0" placeholder="不扣款留空" />
    </n-form-item>
    <n-form-item label="原因">
      <n-input v-model:value="lossForm.reason" placeholder="如：品质不良、加工损坏" />
    </n-form-item>
    <n-form-item label="备注">
      <n-input v-model:value="lossForm.note" type="textarea" :rows="2" />
    </n-form-item>
  </n-form>
  <template #footer>
    <n-space justify="end">
      <n-button @click="showLossModal = false">取消</n-button>
      <n-button type="warning" @click="confirmLoss">确认损耗</n-button>
    </n-space>
  </template>
</n-modal>
```

For items that already have a loss record, show a tag: `损耗 {loss_qty}` with a tooltip showing details.

- [ ] **Step 3: Add loss UI to HandcraftDetail.vue**

Same pattern as plating, but use `confirmHandcraftLoss` and include `item_type` ("part" or "jewelry") in the request.

Apply to both part items table and jewelry items table.

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/production_loss.js frontend/src/views/plating/PlatingDetail.vue frontend/src/views/handcraft/HandcraftDetail.vue
git commit -m "feat: add confirm-loss UI to plating and handcraft detail pages"
```

---

## Task 6: Frontend — Receipt Page Loss Entry

**Files:**
- Modify: Plating receipt detail page
- Modify: Handcraft receipt detail page

- [ ] **Step 1: Add loss button on receipt item rows**

On receipt detail pages, for each receipt item whose source order item has `received_qty < qty`, show the gap info and a 【确认损耗】button. Reuse the same modal pattern from Task 5.

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/plating/ frontend/src/views/handcraft/
git commit -m "feat: add confirm-loss entry on receipt detail pages"
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

Test scenarios:
- Create plating order, send, partially receive, confirm loss → order completes
- Create handcraft order, send, partially receive parts and jewelry, confirm losses → order completes
- Verify inventory log has loss audit entries
- Verify loss tag appears on confirmed items
- Verify receipt page also has confirm-loss entry
