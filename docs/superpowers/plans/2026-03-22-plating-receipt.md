# 电镀回收单 (Plating Receipt) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create an independent "plating receipt" (电镀回收单) document system that replaces the current inline plating receive flow, supporting cross-order partial receiving with price tracking and image uploads.

**Architecture:** New PlatingReceipt + PlatingReceiptItem models follow the PurchaseOrder pattern (create-on-submit with immediate stock effects). Each receipt item links to a PlatingOrderItem, updating its `received_qty` and triggering plating order status transitions. The old `POST /plating/{id}/receive` endpoint is removed.

**Tech Stack:** FastAPI + SQLAlchemy (backend), Vue 3 + Naive UI (frontend), PostgreSQL

---

## File Structure

### New files
| File | Responsibility |
|------|---------------|
| `models/plating_receipt.py` | PlatingReceipt + PlatingReceiptItem ORM models |
| `schemas/plating_receipt.py` | Pydantic request/response schemas |
| `services/plating_receipt.py` | Business logic: create, list, get, delete, update item, delete item, status toggle, images |
| `api/plating_receipt.py` | REST endpoints under `/api/plating-receipts` |
| `tests/test_api_plating_receipt.py` | API-level tests |
| `frontend/src/api/platingReceipts.js` | Axios API client |
| `frontend/src/views/plating-receipts/PlatingReceiptList.vue` | List page |
| `frontend/src/views/plating-receipts/PlatingReceiptCreate.vue` | Create page (select vendor → pick pending items → fill qty/price) |
| `frontend/src/views/plating-receipts/PlatingReceiptDetail.vue` | Detail page with status toggle, item edit/delete, image upload |

### Modified files
| File | Change |
|------|--------|
| `models/__init__.py` | Import and export PlatingReceipt, PlatingReceiptItem |
| `main.py` | Register plating_receipt_router with `require_permission("plating")` |
| `services/plating.py` | Add `supplier_name` param to `list_pending_receive_items()`; remove `receive_plating_items()` (dead code); update `delete_plating_order()` to also reverse PlatingReceiptItem stock |
| `api/plating.py` | Remove `POST /{order_id}/receive` endpoint; remove `ReceiptRequest` import; add `supplier_name` query param to pending-receive endpoint |
| `frontend/src/router/index.js` | Add plating-receipts routes (under `plating` perm) |
| `frontend/src/layouts/DefaultLayout.vue` | Convert 电镀单 to submenu with children: 电镀发出 + 电镀回收 |
| `frontend/src/api/plating.js` | Remove `receivePlating`; add `supplier_name` param to `listPendingReceiveItems` |
| `frontend/src/views/plating/PlatingDetail.vue` | Remove receive buttons (整单回收, 部分回收) |

---

## Task 1: Backend — Model

**Files:**
- Create: `models/plating_receipt.py`
- Modify: `models/__init__.py`

- [ ] **Step 1: Create PlatingReceipt and PlatingReceiptItem models**

```python
# models/plating_receipt.py
import json

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from database import Base
from time_utils import now_beijing


class PlatingReceipt(Base):
    __tablename__ = "plating_receipt"

    id = Column(String, primary_key=True)
    vendor_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="未付款")
    total_amount = Column(Numeric(12, 3), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
    paid_at = Column(DateTime, nullable=True)
    delivery_images_raw = Column("delivery_images", Text, nullable=True)

    items = relationship("PlatingReceiptItem", backref="plating_receipt", lazy="select")

    @property
    def delivery_images(self):
        if not self.delivery_images_raw:
            return []
        try:
            value = json.loads(self.delivery_images_raw)
        except (TypeError, ValueError):
            return []
        return value if isinstance(value, list) else []

    @delivery_images.setter
    def delivery_images(self, value):
        cleaned = [str(item).strip() for item in (value or []) if str(item).strip()]
        self.delivery_images_raw = json.dumps(cleaned, ensure_ascii=True) if cleaned else None


class PlatingReceiptItem(Base):
    __tablename__ = "plating_receipt_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plating_receipt_id = Column(String, ForeignKey("plating_receipt.id"), nullable=False)
    plating_order_item_id = Column(Integer, ForeignKey("plating_order_item.id"), nullable=False)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty = Column(Numeric(10, 4), nullable=False)
    unit = Column(String, nullable=True, default="个")
    price = Column(Numeric(12, 3), nullable=True)
    amount = Column(Numeric(12, 3), nullable=True)
    note = Column(Text, nullable=True)
```

- [ ] **Step 2: Register models in `models/__init__.py`**

Add to imports:
```python
from .plating_receipt import PlatingReceipt, PlatingReceiptItem
```
Add to `__all__`:
```python
"PlatingReceipt",
"PlatingReceiptItem",
```

- [ ] **Step 3: Verify models load**

Run: `python -c "import models; print([t.name for t in models.Base.metadata.sorted_tables if 'plating_receipt' in t.name])"`
Expected: `['plating_receipt', 'plating_receipt_item']`

- [ ] **Step 4: Commit**

```bash
git add models/plating_receipt.py models/__init__.py
git commit -m "feat: add PlatingReceipt and PlatingReceiptItem models"
```

---

## Task 2: Backend — Schemas

**Files:**
- Create: `schemas/plating_receipt.py`

- [ ] **Step 1: Create Pydantic schemas**

```python
# schemas/plating_receipt.py
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlatingReceiptItemCreate(BaseModel):
    plating_order_item_id: int
    part_id: str
    qty: float = Field(gt=0)
    unit: Optional[str] = "个"
    price: Optional[float] = Field(None, ge=0)
    note: Optional[str] = None


class PlatingReceiptCreate(BaseModel):
    vendor_name: str
    items: List[PlatingReceiptItemCreate] = Field(min_length=1)
    status: str = "未付款"
    note: Optional[str] = None

    @field_validator("vendor_name")
    @classmethod
    def vendor_name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("商家名称不能为空")
        return v


class PlatingReceiptItemUpdate(BaseModel):
    qty: float = Field(None, gt=0)
    unit: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    note: Optional[str] = None


class PlatingReceiptStatusUpdate(BaseModel):
    status: str


class PlatingReceiptDeliveryImagesUpdate(BaseModel):
    delivery_images: List[str] = Field(default_factory=list, max_length=9)


class PlatingReceiptItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plating_receipt_id: str
    plating_order_item_id: int
    part_id: str
    qty: float
    unit: Optional[str] = None
    price: Optional[float] = None
    amount: Optional[float] = None
    note: Optional[str] = None
    # Enriched fields (populated by service, not from ORM)
    part_name: Optional[str] = None
    plating_order_id: Optional[str] = None
    plating_method: Optional[str] = None


class PlatingReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    vendor_name: str
    status: str
    total_amount: Optional[float] = None
    note: Optional[str] = None
    created_at: datetime
    paid_at: Optional[datetime] = None
    delivery_images: list[str] = Field(default_factory=list)
    items: list[PlatingReceiptItemResponse] = Field(default_factory=list)
```

- [ ] **Step 2: Commit**

```bash
git add schemas/plating_receipt.py
git commit -m "feat: add PlatingReceipt Pydantic schemas"
```

---

## Task 3: Backend — Service (core CRUD)

**Files:**
- Create: `services/plating_receipt.py`
- Modify: `services/plating.py` (add `supplier_name` filter to `list_pending_receive_items`)

- [ ] **Step 1: Add `supplier_name` filter to `list_pending_receive_items` in `services/plating.py`**

In `list_pending_receive_items()`, add a `supplier_name` parameter:

```python
def list_pending_receive_items(db: Session, part_keyword: str = None, supplier_name: str = None) -> list:
```

Add filter before the `part_keyword` filter:
```python
    if supplier_name:
        q = q.filter(PlatingOrder.supplier_name == supplier_name)
```

- [ ] **Step 2: Update the API endpoint in `api/plating.py`**

```python
@router.get("/items/pending-receive", response_model=list[PendingReceiveItemResponse])
def api_list_pending_receive_items(part_keyword: str = None, supplier_name: str = None, db: Session = Depends(get_db)):
    with service_errors():
        return list_pending_receive_items(db, part_keyword, supplier_name=supplier_name)
```

- [ ] **Step 3: Create `services/plating_receipt.py`**

Core logic — follow PurchaseOrder service pattern closely. Key difference: creating a receipt also updates the linked PlatingOrderItem's `received_qty` and potentially completes the plating order.

```python
# services/plating_receipt.py
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.part import Part
from models.plating_order import PlatingOrder, PlatingOrderItem
from models.plating_receipt import PlatingReceipt, PlatingReceiptItem
from services._helpers import _next_id
from services.inventory import add_stock, deduct_stock
from time_utils import now_beijing


_VALID_STATUSES = {"未付款", "已付款"}


def _require_part(db: Session, part_id: str) -> None:
    if db.get(Part, part_id) is None:
        raise ValueError(f"Part not found: {part_id}")


def _normalize_delivery_images(delivery_images: Optional[list]) -> list[str]:
    cleaned = [str(item).strip() for item in (delivery_images or []) if str(item).strip()]
    if len(cleaned) > 9:
        raise ValueError("图片最多上传 9 张")
    return cleaned


def _recalc_total(db: Session, receipt: PlatingReceipt) -> None:
    items = get_plating_receipt_items(db, receipt.id)
    total = sum(float(item.amount or 0) for item in items)
    receipt.total_amount = total


def _check_plating_order_completion(db: Session, plating_order_id: str) -> None:
    """If all items of a plating order are fully received, mark it completed."""
    all_items = (
        db.query(PlatingOrderItem)
        .filter(PlatingOrderItem.plating_order_id == plating_order_id)
        .all()
    )
    if all(float(i.received_qty or 0) >= float(i.qty) for i in all_items):
        order = db.query(PlatingOrder).filter(PlatingOrder.id == plating_order_id).first()
        if order and order.status == "processing":
            order.status = "completed"
            order.completed_at = now_beijing()
    else:
        # If previously completed but now not all received (e.g. after item edit/delete),
        # revert to processing
        order = db.query(PlatingOrder).filter(PlatingOrder.id == plating_order_id).first()
        if order and order.status == "completed":
            order.status = "processing"
            order.completed_at = None


def _apply_receive(db: Session, plating_order_item: PlatingOrderItem, qty: float) -> None:
    """Add qty to received_qty, update item status, add stock."""
    plating_order_item.received_qty = float(plating_order_item.received_qty or 0) + qty
    receive_id = plating_order_item.receive_part_id or plating_order_item.part_id
    add_stock(db, "part", receive_id, qty, "电镀收回")
    if float(plating_order_item.received_qty) >= float(plating_order_item.qty):
        plating_order_item.status = "已收回"
    else:
        plating_order_item.status = "电镀中"


def _reverse_receive(db: Session, plating_order_item: PlatingOrderItem, qty: float) -> None:
    """Reverse qty from received_qty, update item status, deduct stock."""
    plating_order_item.received_qty = float(plating_order_item.received_qty or 0) - qty
    receive_id = plating_order_item.receive_part_id or plating_order_item.part_id
    deduct_stock(db, "part", receive_id, qty, "电镀收回撤回")
    if float(plating_order_item.received_qty) >= float(plating_order_item.qty):
        plating_order_item.status = "已收回"
    else:
        plating_order_item.status = "电镀中"


def create_plating_receipt(
    db: Session,
    vendor_name: str,
    items: list,
    status: str = "未付款",
    note: str = None,
) -> PlatingReceipt:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Valid: {', '.join(sorted(_VALID_STATUSES))}")

    receipt_id = _next_id(db, PlatingReceipt, "ER")
    receipt = PlatingReceipt(
        id=receipt_id,
        vendor_name=vendor_name,
        status=status,
        note=note,
    )
    if status == "已付款":
        receipt.paid_at = now_beijing()
    db.add(receipt)
    db.flush()

    affected_plating_orders = set()
    total = 0.0

    for item_data in items:
        poi = db.query(PlatingOrderItem).filter(
            PlatingOrderItem.id == item_data["plating_order_item_id"]
        ).first()
        if poi is None:
            raise ValueError(f"PlatingOrderItem not found: {item_data['plating_order_item_id']}")
        if poi.status not in ("电镀中", "已收回"):
            raise ValueError(f"PlatingOrderItem {poi.id} status is '{poi.status}', cannot receive")

        qty = item_data["qty"]
        remaining = float(poi.qty) - float(poi.received_qty or 0)
        if qty > remaining:
            raise ValueError(f"PlatingOrderItem {poi.id}: 最多可回收 {remaining}, 当前填写 {qty}")

        # Validate part_id matches
        expected_part_id = item_data["part_id"]
        receive_id = poi.receive_part_id or poi.part_id
        if expected_part_id != receive_id:
            raise ValueError(f"part_id mismatch for PlatingOrderItem {poi.id}")

        price = round(item_data["price"], 3) if item_data.get("price") is not None else None
        amount = round(qty * price, 3) if price is not None else None
        if amount is not None:
            total += amount

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

    receipt.total_amount = total
    db.flush()

    for po_id in affected_plating_orders:
        _check_plating_order_completion(db, po_id)
    db.flush()

    return receipt


def list_plating_receipts(db: Session, vendor_name: str = None) -> list:
    q = db.query(PlatingReceipt)
    if vendor_name is not None:
        q = q.filter(PlatingReceipt.vendor_name == vendor_name)
    return q.order_by(PlatingReceipt.created_at.desc()).all()


def get_plating_receipt(db: Session, receipt_id: str) -> Optional[PlatingReceipt]:
    return db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first()


def get_plating_receipt_items(db: Session, receipt_id: str) -> list:
    return (
        db.query(PlatingReceiptItem)
        .filter(PlatingReceiptItem.plating_receipt_id == receipt_id)
        .order_by(PlatingReceiptItem.id.asc())
        .all()
    )


def delete_plating_receipt(db: Session, receipt_id: str) -> None:
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise ValueError(f"PlatingReceipt not found: {receipt_id}")
    if receipt.status == "已付款":
        raise ValueError("已付款的回收单不能删除")

    items = get_plating_receipt_items(db, receipt_id)
    affected_plating_orders = set()

    for item in items:
        poi = db.query(PlatingOrderItem).filter(
            PlatingOrderItem.id == item.plating_order_item_id
        ).first()
        if poi:
            _reverse_receive(db, poi, float(item.qty))
            affected_plating_orders.add(poi.plating_order_id)

    db.query(PlatingReceiptItem).filter(
        PlatingReceiptItem.plating_receipt_id == receipt_id
    ).delete(synchronize_session=False)
    db.flush()
    db.delete(receipt)
    db.flush()

    for po_id in affected_plating_orders:
        _check_plating_order_completion(db, po_id)
    db.flush()


def update_plating_receipt_status(db: Session, receipt_id: str, status: str) -> PlatingReceipt:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Valid: {', '.join(sorted(_VALID_STATUSES))}")
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise ValueError(f"PlatingReceipt not found: {receipt_id}")
    if receipt.status == status:
        raise ValueError(f"回收单已经是「{status}」状态")
    if status == "已付款":
        receipt.paid_at = now_beijing()
    else:
        receipt.paid_at = None
    receipt.status = status
    db.flush()
    return receipt


def update_plating_receipt_images(db: Session, receipt_id: str, delivery_images: Optional[list]) -> PlatingReceipt:
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise ValueError(f"PlatingReceipt not found: {receipt_id}")
    receipt.delivery_images = _normalize_delivery_images(delivery_images)
    db.flush()
    return receipt


def update_plating_receipt_item(db: Session, receipt_id: str, item_id: int, data: dict) -> PlatingReceiptItem:
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise ValueError(f"PlatingReceipt not found: {receipt_id}")
    if receipt.status == "已付款":
        raise ValueError("已付款的回收单不能修改明细")

    item = db.query(PlatingReceiptItem).filter(
        PlatingReceiptItem.id == item_id,
        PlatingReceiptItem.plating_receipt_id == receipt_id,
    ).first()
    if item is None:
        raise ValueError(f"PlatingReceiptItem {item_id} not found in receipt {receipt_id}")

    poi = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.id == item.plating_order_item_id
    ).first()

    old_qty = float(item.qty)

    for field in ("unit", "note"):
        if field in data:
            setattr(item, field, data[field])
    if "price" in data:
        item.price = round(data["price"], 3) if data["price"] is not None else None
    if "qty" in data and data["qty"] is not None:
        new_qty = data["qty"]
        # Validate: new_qty must not exceed remaining + old_qty
        remaining = float(poi.qty) - float(poi.received_qty or 0) + old_qty
        if new_qty > remaining:
            raise ValueError(f"最多可回收 {remaining}, 当前填写 {new_qty}")
        item.qty = new_qty

    new_qty = float(item.qty)
    if new_qty != old_qty:
        diff = new_qty - old_qty
        if diff > 0:
            _apply_receive(db, poi, diff)
        else:
            _reverse_receive(db, poi, -diff)
        _check_plating_order_completion(db, poi.plating_order_id)

    if item.price is not None:
        item.amount = round(float(item.qty) * float(item.price), 3)
    else:
        item.amount = None

    _recalc_total(db, receipt)
    db.flush()
    return item


def delete_plating_receipt_item(db: Session, receipt_id: str, item_id: int) -> None:
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise ValueError(f"PlatingReceipt not found: {receipt_id}")
    if receipt.status == "已付款":
        raise ValueError("已付款的回收单不能删除明细")

    item = db.query(PlatingReceiptItem).filter(
        PlatingReceiptItem.id == item_id,
        PlatingReceiptItem.plating_receipt_id == receipt_id,
    ).first()
    if item is None:
        raise ValueError(f"PlatingReceiptItem {item_id} not found in receipt {receipt_id}")

    remaining_count = db.query(PlatingReceiptItem).filter(
        PlatingReceiptItem.plating_receipt_id == receipt_id,
        PlatingReceiptItem.id != item_id,
    ).count()
    if remaining_count == 0:
        raise ValueError("不能删除最后一条明细，请直接删除整个回收单")

    poi = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.id == item.plating_order_item_id
    ).first()
    if poi:
        _reverse_receive(db, poi, float(item.qty))
        affected_po_id = poi.plating_order_id
    else:
        affected_po_id = None

    db.delete(item)
    db.flush()
    _recalc_total(db, receipt)
    db.flush()

    if affected_po_id:
        _check_plating_order_completion(db, affected_po_id)
        db.flush()


def get_receipt_vendor_names(db: Session) -> list[str]:
    rows = db.query(PlatingReceipt.vendor_name).distinct().all()
    return [row[0] for row in rows]


def _enrich_receipt(db: Session, receipt: PlatingReceipt) -> PlatingReceipt:
    """Populate enriched fields (part_name, plating_order_id, plating_method) on receipt items."""
    for item in receipt.items:
        poi = db.query(PlatingOrderItem).filter(PlatingOrderItem.id == item.plating_order_item_id).first()
        if poi:
            item.plating_order_id = poi.plating_order_id
            item.plating_method = poi.plating_method
        part = db.get(Part, item.part_id)
        if part:
            item.part_name = part.name
    return receipt
```

**Important:** Call `_enrich_receipt(db, receipt)` in `get_plating_receipt()` and `create_plating_receipt()` before returning. The list endpoint can skip enrichment for performance (only IDs needed for list view).

- [ ] **Step 4: Commit**

```bash
git add services/plating_receipt.py services/plating.py api/plating.py
git commit -m "feat: add plating receipt service, extend pending-receive with supplier filter"
```

---

## Task 4: Backend — API Routes

**Files:**
- Create: `api/plating_receipt.py`
- Modify: `main.py`

- [ ] **Step 1: Create API router**

Follow `api/purchase_order.py` pattern exactly. Endpoints:

```python
# api/plating_receipt.py
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.plating_receipt import (
    PlatingReceiptCreate,
    PlatingReceiptDeliveryImagesUpdate,
    PlatingReceiptItemUpdate,
    PlatingReceiptItemResponse,
    PlatingReceiptResponse,
    PlatingReceiptStatusUpdate,
)
from services.plating_receipt import (
    create_plating_receipt,
    delete_plating_receipt,
    delete_plating_receipt_item,
    get_plating_receipt,
    get_receipt_vendor_names,
    list_plating_receipts,
    update_plating_receipt_images,
    update_plating_receipt_item,
    update_plating_receipt_status,
)

router = APIRouter(prefix="/api/plating-receipts", tags=["plating-receipts"])


@router.get("/", response_model=list[PlatingReceiptResponse])
def api_list_plating_receipts(vendor_name: Optional[str] = None, db: Session = Depends(get_db)):
    return list_plating_receipts(db, vendor_name=vendor_name)


@router.get("/vendors", response_model=list[str])
def api_get_receipt_vendor_names(db: Session = Depends(get_db)):
    return get_receipt_vendor_names(db)


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


@router.get("/{receipt_id}", response_model=PlatingReceiptResponse)
def api_get_plating_receipt(receipt_id: str, db: Session = Depends(get_db)):
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"PlatingReceipt {receipt_id} not found")
    return receipt


@router.delete("/{receipt_id}", status_code=204)
def api_delete_plating_receipt(receipt_id: str, db: Session = Depends(get_db)):
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"PlatingReceipt {receipt_id} not found")
    with service_errors():
        delete_plating_receipt(db, receipt_id)


@router.patch("/{receipt_id}/status", response_model=PlatingReceiptResponse)
def api_update_plating_receipt_status(receipt_id: str, body: PlatingReceiptStatusUpdate, db: Session = Depends(get_db)):
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"PlatingReceipt {receipt_id} not found")
    with service_errors():
        receipt = update_plating_receipt_status(db, receipt_id, body.status)
    return receipt


@router.patch("/{receipt_id}/delivery-images", response_model=PlatingReceiptResponse)
def api_update_plating_receipt_images(receipt_id: str, body: PlatingReceiptDeliveryImagesUpdate, db: Session = Depends(get_db)):
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"PlatingReceipt {receipt_id} not found")
    with service_errors():
        receipt = update_plating_receipt_images(db, receipt_id, body.delivery_images)
    return receipt


@router.put("/{receipt_id}/items/{item_id}", response_model=PlatingReceiptItemResponse)
def api_update_plating_receipt_item(receipt_id: str, item_id: int, body: PlatingReceiptItemUpdate, db: Session = Depends(get_db)):
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"PlatingReceipt {receipt_id} not found")
    with service_errors():
        item = update_plating_receipt_item(db, receipt_id, item_id, body.model_dump(exclude_unset=True))
    return item


@router.delete("/{receipt_id}/items/{item_id}", status_code=204)
def api_delete_plating_receipt_item(receipt_id: str, item_id: int, db: Session = Depends(get_db)):
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"PlatingReceipt {receipt_id} not found")
    with service_errors():
        delete_plating_receipt_item(db, receipt_id, item_id)
```

- [ ] **Step 2: Register router in `main.py`**

Add import:
```python
from api.plating_receipt import router as plating_receipt_router
```

Add after `plating_router` line:
```python
app.include_router(plating_receipt_router, dependencies=[require_permission("plating")])
```

- [ ] **Step 3: Commit**

```bash
git add api/plating_receipt.py main.py
git commit -m "feat: add plating receipt REST API endpoints"
```

---

## Task 5: Backend — Remove old receive endpoint + update delete_plating_order

**Files:**
- Modify: `api/plating.py`
- Modify: `services/plating.py`

- [ ] **Step 1: Remove `POST /{order_id}/receive` endpoint from `api/plating.py`**

Delete the `api_receive_plating_items` function (lines 147-158) and remove `ReceiptRequest` from the schema import and `receive_plating_items` from the service import.

- [ ] **Step 2: Remove `receive_plating_items` from `services/plating.py`**

This function is now dead code. Delete it entirely (lines 94-130).

- [ ] **Step 3: Update `delete_plating_order` in `services/plating.py`**

The existing `delete_plating_order` reverses stock from `VendorReceipt` records. It must also reverse stock from `PlatingReceiptItem` records and delete them.

Add to the function, after the VendorReceipt cleanup block:

```python
from models.plating_receipt import PlatingReceiptItem

# Reverse stock from PlatingReceiptItem records linked to this order's items
item_ids = [item.id for item in items]
receipt_items = db.query(PlatingReceiptItem).filter(
    PlatingReceiptItem.plating_order_item_id.in_(item_ids)
).all()
for ri in receipt_items:
    receive_id = ri.part_id  # part_id on receipt item is already the receive target
    deduct_stock(db, "part", receive_id, float(ri.qty), "电镀收回撤回")
    db.delete(ri)
```

Note: This handles the case where a plating order is deleted after some items have been received via plating receipts. The VendorReceipt logic remains for backward compatibility with the kanban system.

- [ ] **Step 4: Verify existing plating tests still pass**

Run: `pytest tests/test_api_plating.py tests/test_plating.py tests/test_plating_item_crud.py -v`

Note: Tests that call `POST /plating/{id}/receive` will need to be updated to use the new plating receipt flow instead. Check each test file and update accordingly.

- [ ] **Step 5: Commit**

```bash
git add api/plating.py services/plating.py
git commit -m "refactor: remove direct plating receive endpoint, update delete to handle receipt items"
```

---

## Task 6: Backend — Tests

**Files:**
- Create: `tests/test_api_plating_receipt.py`
- Modify: tests that use old receive endpoint

- [ ] **Step 1: Write tests for plating receipt CRUD**

Test file `tests/test_api_plating_receipt.py`. Key test cases:

1. `test_create_plating_receipt` — create receipt with items, verify stock added, verify plating order item received_qty updated
2. `test_create_receipt_completes_plating_order` — fully receive all items → plating order status becomes "completed"
3. `test_create_receipt_partial_receive` — partial receive, plating order stays "processing"
4. `test_create_receipt_exceeds_remaining` — should fail with 400
5. `test_delete_receipt_reverses_stock` — delete unpaid receipt, verify stock reversed and plating order received_qty reversed
6. `test_delete_paid_receipt_rejected` — should fail with 400
7. `test_update_receipt_item_qty` — change qty, verify stock diff applied
8. `test_delete_receipt_item` — delete item, verify stock reversed
9. `test_status_toggle` — toggle 未付款 ↔ 已付款
10. `test_delivery_images_max_9` — 9 images OK, 10 images rejected
11. `test_list_receipts` — list all, list by vendor_name
12. `test_receipt_with_receive_part_id` — plating order item with receive_part_id, verify stock goes to receive_part_id

Helper setup in each test: create part → create plating order → send plating order (to get items into 电镀中 status) → then create receipt.

```python
# tests/test_api_plating_receipt.py
import pytest

from services.part import create_part
from services.inventory import add_stock, get_stock
from services.plating import (
    create_plating_order, send_plating_order, get_plating_order, get_plating_items,
)


def _setup_processing_plating(db, part_name="P1", qty=10.0, supplier="Supplier A",
                               plating_method="金色", receive_part_id=None):
    """Helper: create a part with stock, create + send a plating order."""
    part = create_part(db, {"name": part_name, "category": "小配件"})
    add_stock(db, "part", part.id, qty + 10, "初始库存")

    items = [{"part_id": part.id, "qty": qty, "plating_method": plating_method}]
    if receive_part_id:
        items[0]["receive_part_id"] = receive_part_id
    order = create_plating_order(db, supplier, items)
    send_plating_order(db, order.id)
    db.flush()
    return part, order


def test_create_plating_receipt(client, db):
    part, order = _setup_processing_plating(db)
    poi_id = get_plating_items(db, order.id)[0].id

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Supplier A",
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 5.0, "price": 2.0}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("ER-")
    assert data["status"] == "未付款"
    assert data["total_amount"] == 10.0
    assert len(data["items"]) == 1
    assert data["items"][0]["qty"] == 5.0


def test_create_receipt_exceeds_remaining(client, db):
    part, order = _setup_processing_plating(db, qty=10.0)
    poi_id = get_plating_items(db, order.id)[0].id

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Supplier A",
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 15.0}],
    })
    assert resp.status_code == 400


def test_delete_paid_receipt_rejected(client, db):
    part, order = _setup_processing_plating(db)
    poi_id = get_plating_items(db, order.id)[0].id

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Supplier A",
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 5.0}],
        "status": "已付款",
    })
    receipt_id = resp.json()["id"]

    del_resp = client.delete(f"/api/plating-receipts/{receipt_id}")
    assert del_resp.status_code == 400


def test_delivery_images_max_9(client, db):
    part, order = _setup_processing_plating(db)
    poi_id = get_plating_items(db, order.id)[0].id

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Supplier A",
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 5.0}],
    })
    receipt_id = resp.json()["id"]

    # 9 images OK
    img_resp = client.patch(f"/api/plating-receipts/{receipt_id}/delivery-images", json={
        "delivery_images": [f"img{i}.jpg" for i in range(9)]
    })
    assert img_resp.status_code == 200

    # 10 images rejected
    img_resp2 = client.patch(f"/api/plating-receipts/{receipt_id}/delivery-images", json={
        "delivery_images": [f"img{i}.jpg" for i in range(10)]
    })
    assert img_resp2.status_code == 400
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/test_api_plating_receipt.py -v`
Expected: All pass

- [ ] **Step 3: Fix any existing plating tests that relied on old receive endpoint**

Run: `pytest tests/ -v`
Fix any failures.

- [ ] **Step 4: Commit**

```bash
git add tests/test_api_plating_receipt.py
git commit -m "test: add plating receipt API tests"
```

---

## Task 7: Frontend — API Client + Routes + Navigation

**Files:**
- Create: `frontend/src/api/platingReceipts.js`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/layouts/DefaultLayout.vue`
- Modify: `frontend/src/api/plating.js`

- [ ] **Step 1: Create `frontend/src/api/platingReceipts.js`**

```javascript
import api from './index'

export const listPlatingReceipts = (params) => api.get('/plating-receipts/', { params })
export const getPlatingReceiptVendors = () => api.get('/plating-receipts/vendors')
export const createPlatingReceipt = (data) => api.post('/plating-receipts/', data)
export const getPlatingReceipt = (id) => api.get(`/plating-receipts/${id}`)
export const deletePlatingReceipt = (id) => api.delete(`/plating-receipts/${id}`)
export const updatePlatingReceiptStatus = (id, status) => api.patch(`/plating-receipts/${id}/status`, { status })
export const updatePlatingReceiptDeliveryImages = (id, images) => api.patch(`/plating-receipts/${id}/delivery-images`, { delivery_images: images })
export const updatePlatingReceiptItem = (id, itemId, data) => api.put(`/plating-receipts/${id}/items/${itemId}`, data)
export const deletePlatingReceiptItem = (id, itemId) => api.delete(`/plating-receipts/${id}/items/${itemId}`)
```

- [ ] **Step 2: Add routes in `frontend/src/router/index.js`**

Add after plating routes (line 58):
```javascript
{ path: 'plating-receipts', component: () => import('@/views/plating-receipts/PlatingReceiptList.vue'), meta: { perm: 'plating' } },
{ path: 'plating-receipts/create', component: () => import('@/views/plating-receipts/PlatingReceiptCreate.vue'), meta: { perm: 'plating' } },
{ path: 'plating-receipts/:id', component: () => import('@/views/plating-receipts/PlatingReceiptDetail.vue'), meta: { perm: 'plating' } },
```

- [ ] **Step 3: Convert 电镀单 to submenu in `DefaultLayout.vue`**

In both `allFlatItems` and `allGroupedItems`, replace the flat 电镀单 entry with a submenu. For Naive UI `n-menu`, use `children` property:

In `allGroupedItems` → group-production children, replace:
```javascript
{ label: '电镀单', key: 'plating', icon: icon(ColorWandOutline), perm: 'plating' },
```
with:
```javascript
{
  label: '电镀管理', key: 'plating-group', icon: icon(ColorWandOutline), perm: 'plating',
  children: [
    { label: '电镀发出', key: 'plating', perm: 'plating' },
    { label: '电镀回收', key: 'plating-receipts', perm: 'plating' },
  ],
},
```

Similarly update `allFlatItems`.

Update `activeKey` computed to handle the submenu — currently it uses `route.path.split('/')[1]` which will return `plating-receipts` correctly.

- [ ] **Step 4: Remove `receivePlating` from `frontend/src/api/plating.js`**

Remove:
```javascript
export const receivePlating = (id, receipts) =>
  api.post(`/plating/${id}/receive`, { receipts })
```

Add `supplier_name` to `listPendingReceiveItems`:
```javascript
export const listPendingReceiveItems = (params) =>
  api.get('/plating/items/pending-receive', { params })
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/platingReceipts.js frontend/src/router/index.js frontend/src/layouts/DefaultLayout.vue frontend/src/api/plating.js
git commit -m "feat: add plating receipt routes, navigation submenu, API client"
```

---

## Task 8: Frontend — Create Page (PlatingReceiptCreate.vue)

**Files:**
- Create: `frontend/src/views/plating-receipts/PlatingReceiptCreate.vue`

- [ ] **Step 1: Build create page**

Follow `PurchaseOrderCreate.vue` as the template. Key differences:

1. **Vendor selection**: Autocomplete from plating order supplier names (use `listPendingReceiveItems` grouped by supplier, or add a vendor endpoint)
2. **Item selection**: After selecting vendor, call `listPendingReceiveItems({ supplier_name })` to show all pending items
3. **Item table**: Show plating_order_id, part_name, plating_method, total_qty, already_received_qty, remaining_qty — user fills in receive_qty and price
4. **Images**: Support up to 9 images (use same upload pattern as other pages)
5. **Submit**: POST to `/api/plating-receipts/`

This is the most complex frontend page. Refer to existing `PurchaseOrderCreate.vue` for form layout and `PlatingDetail.vue` for plating-specific patterns.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/plating-receipts/PlatingReceiptCreate.vue
git commit -m "feat: add plating receipt create page"
```

---

## Task 9: Frontend — List Page (PlatingReceiptList.vue)

**Files:**
- Create: `frontend/src/views/plating-receipts/PlatingReceiptList.vue`

- [ ] **Step 1: Build list page**

Follow `PurchaseOrderList.vue` pattern. Show: ID, vendor, status, total_amount, created_at. Filter by vendor. "新建回收单" button links to create page.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/plating-receipts/PlatingReceiptList.vue
git commit -m "feat: add plating receipt list page"
```

---

## Task 10: Frontend — Detail Page (PlatingReceiptDetail.vue)

**Files:**
- Create: `frontend/src/views/plating-receipts/PlatingReceiptDetail.vue`

- [ ] **Step 1: Build detail page**

Follow `PurchaseOrderDetail.vue` pattern. Features:
- Header: receipt ID, vendor, status toggle, total_amount, paid_at
- Items table: plating_order_item_id (show as EP-XXXX link), part_id, part_name, qty, unit, price, amount, note
- Edit/delete item buttons (disabled if 已付款)
- Delivery images section (max 9)
- Delete order button (disabled if 已付款)

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/plating-receipts/PlatingReceiptDetail.vue
git commit -m "feat: add plating receipt detail page"
```

---

## Task 11: Frontend — Remove receive buttons from PlatingDetail.vue

**Files:**
- Modify: `frontend/src/views/plating/PlatingDetail.vue`

- [ ] **Step 1: Remove receive-related UI**

Remove:
- "整单回收" button and its handler
- Per-item "回收" / "部分回收" buttons and their handlers/modals
- Any receive-related state/refs

Optionally: Add a link/button "查看回收记录" that navigates to the plating receipt list filtered by this supplier.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/plating/PlatingDetail.vue
git commit -m "refactor: remove inline receive UI from plating detail, replaced by plating receipts"
```

---

## Task 12: Final verification

- [ ] **Step 1: Run all backend tests**

Run: `pytest tests/ -v`
Expected: All pass

- [ ] **Step 2: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 3: Manual smoke test**

1. Create a plating order → send it
2. Create a plating receipt → verify stock updated
3. Edit receipt item qty → verify stock diff
4. Toggle receipt status
5. Delete receipt → verify stock reversed

- [ ] **Step 4: Final commit if any fixes needed**
