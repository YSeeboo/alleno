# 电镀汇总 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-item "电镀汇总" page with two tabs (已发出 / 已收回) that flatten all `PlatingOrderItem` rows across orders, with filters, partition-by-completion sort, cross-jump highlight, and inline 确认损耗.

**Architecture:**
- Backend: new `services/plating_summary.py` does pure read-only aggregation (joins `plating_order_item` + `plating_order` + `part`, plus separate batch queries for `plating_receipt_item` and `production_loss`); new `api/plating_summary.py` exposes 2 GET endpoints. Reuses existing `keyword_filter()`, `getPlatingSuppliers()`, `confirm_plating_loss` (via `/plating-receipts/{receipt_id}/confirm-loss`).
- Frontend: single `PlatingSummary.vue` page with `NDataTable`, two column configs swapped by tab. Filter & tab state is mirrored to URL query for back-nav preservation. Highlight reuses `?highlight={item_id}` + `receipt-highlight-row` animation already in place.

**Tech Stack:** FastAPI + SQLAlchemy 2.x + Pydantic V2 backend; Vue 3.5 + Naive UI + Pinia + Vue Router 4 frontend. Tests use pytest with PostgreSQL test DB.

**Spec:** `docs/superpowers/specs/2026-04-23-plating-summary-design.md`

---

## File Structure

**New files:**
- `schemas/plating_summary.py` — Pydantic response models (DispatchedItem, ReceivedItem, ReceiptInfo, ListResponse)
- `services/plating_summary.py` — `list_dispatched()` and `list_received()` aggregation queries
- `api/plating_summary.py` — 2 GET endpoints
- `tests/test_api_plating_summary.py` — service + API tests
- `frontend/src/api/platingSummary.js` — API client wrappers
- `frontend/src/components/icons/PlatingSummaryIcon.vue` — wraps `汇总.svg`
- `frontend/src/views/plating/PlatingSummary.vue` — main page

**Modified files:**
- `main.py` — register new router with `plating` permission
- `frontend/src/layouts/DefaultLayout.vue` — group rename + new child
- `frontend/src/router/index.js` — new route + permission entry
- `frontend/src/views/plating/PlatingDetail.vue` — restore-summary on back nav
- `frontend/src/views/plating-receipts/PlatingReceiptDetail.vue` — same

---

## Phase 1 — Backend

### Task 1: Response schemas

**Files:**
- Create: `schemas/plating_summary.py`

- [ ] **Step 1: Write the schema file**

```python
# schemas/plating_summary.py
from datetime import date as date_type
from typing import Literal, Optional, List
from pydantic import BaseModel, ConfigDict


class ReceiptInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    receipt_id: str
    receipt_item_id: int
    receipt_date: date_type


class DispatchedItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    plating_order_item_id: int
    plating_order_id: str
    supplier_name: str
    part_id: str
    part_name: str
    part_image: Optional[str] = None
    plating_method: Optional[str] = None
    qty: float
    unit: Optional[str] = None
    weight: Optional[float] = None
    weight_unit: Optional[str] = None
    note: Optional[str] = None
    dispatch_date: date_type
    days_out: Optional[int] = None       # None when is_completed
    is_completed: bool
    receive_part_id: Optional[str] = None
    receive_part_name: Optional[str] = None
    receive_part_image: Optional[str] = None


class ReceivedItem(DispatchedItem):
    actual_received_qty: float
    unreceived_qty: float
    loss_total_qty: float
    loss_state: Literal["none", "pending", "confirmed"]
    receipts: List[ReceiptInfo]
    latest_receipt_id: Optional[str] = None


class DispatchedListResponse(BaseModel):
    items: List[DispatchedItem]
    total: int


class ReceivedListResponse(BaseModel):
    items: List[ReceivedItem]
    total: int
```

- [ ] **Step 2: Verify schemas import cleanly**

Run: `python -c "from schemas.plating_summary import DispatchedItem, ReceivedItem, DispatchedListResponse, ReceivedListResponse"`
Expected: no error.

- [ ] **Step 3: Commit**

```bash
git add schemas/plating_summary.py
git commit -m "feat: add plating summary response schemas"
```

---

### Task 2: Service `list_dispatched` — base behavior + partition

**Files:**
- Create: `services/plating_summary.py`
- Create: `tests/test_api_plating_summary.py`

This task wires up the service skeleton and covers default sort + partition (in-progress before completed). Filters and `days_out_desc` sort come in Task 3.

- [ ] **Step 1: Create empty service module so test imports work**

```python
# services/plating_summary.py
from datetime import date, timedelta
from typing import Literal, Optional

from sqlalchemy.orm import Session

from models.plating_order import PlatingOrder, PlatingOrderItem
from models.part import Part
from time_utils import now_beijing


def list_dispatched(
    db: Session,
    *,
    supplier_name: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    part_keyword: Optional[str] = None,
    sort: Literal["dispatch_date_desc", "days_out_desc"] = "dispatch_date_desc",
    skip: int = 0,
    limit: int = 30,
) -> tuple[list[dict], int]:
    raise NotImplementedError
```

- [ ] **Step 2: Write failing tests for default sort + partition**

Create `tests/test_api_plating_summary.py`:

```python
from datetime import date, timedelta
from decimal import Decimal

import pytest

from models.plating_order import PlatingOrder, PlatingOrderItem
from models.part import Part
from services.plating_summary import list_dispatched
from time_utils import now_beijing


def _make_part(db, pid: str, name: str = "测试配件"):
    p = Part(id=pid, name=name, category="吊坠", unit="件")
    db.add(p); db.flush()
    return p


def _make_order(db, oid: str, supplier: str, *, days_ago: int = 0):
    created = now_beijing() - timedelta(days=days_ago)
    o = PlatingOrder(id=oid, supplier_name=supplier, status="processing", created_at=created)
    db.add(o); db.flush()
    return o


def _make_item(db, *, order_id: str, part_id: str, qty: float, received: float = 0):
    it = PlatingOrderItem(
        plating_order_id=order_id, part_id=part_id,
        qty=Decimal(str(qty)), received_qty=Decimal(str(received)),
        status="电镀中" if received < qty else "已收回",
        plating_method="G", unit="件",
    )
    db.add(it); db.flush()
    return it


def test_list_dispatched_empty(db):
    items, total = list_dispatched(db)
    assert items == []
    assert total == 0


def test_list_dispatched_default_sort_partition(db):
    """Completed items sink to bottom; within each partition, dispatch date desc."""
    _make_part(db, "PJ-DZ-00001")
    _make_part(db, "PJ-DZ-00002")
    _make_part(db, "PJ-DZ-00003")

    # Order A: 10 days ago, in-progress (qty 10, received 5)
    _make_order(db, "EP-0001", "厂A", days_ago=10)
    _make_item(db, order_id="EP-0001", part_id="PJ-DZ-00001", qty=10, received=5)

    # Order B: 1 day ago, in-progress (qty 5, received 0)
    _make_order(db, "EP-0002", "厂B", days_ago=1)
    _make_item(db, order_id="EP-0002", part_id="PJ-DZ-00002", qty=5, received=0)

    # Order C: 5 days ago, completed (qty 8, received 8)
    _make_order(db, "EP-0003", "厂C", days_ago=5)
    _make_item(db, order_id="EP-0003", part_id="PJ-DZ-00003", qty=8, received=8)

    items, total = list_dispatched(db)
    assert total == 3
    # Order: in-progress B (newer) → in-progress A (older) → completed C
    assert [i["plating_order_id"] for i in items] == ["EP-0002", "EP-0001", "EP-0003"]
    assert [i["is_completed"] for i in items] == [False, False, True]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_api_plating_summary.py -v`
Expected: FAIL with `NotImplementedError`.

- [ ] **Step 4: Implement `list_dispatched` minimal default-sort version**

Replace the body in `services/plating_summary.py`:

```python
from datetime import date, timedelta
from typing import Literal, Optional

from sqlalchemy import case, desc, asc, func
from sqlalchemy.orm import Session, aliased

from models.plating_order import PlatingOrder, PlatingOrderItem
from models.part import Part
from time_utils import now_beijing


def _to_beijing_date(dt) -> date:
    """PlatingOrder.created_at is stored as naive Beijing time."""
    return dt.date() if dt is not None else None


def _serialize_dispatched(poi: PlatingOrderItem, po: PlatingOrder, part: Part,
                          recv_part: Optional[Part], today: date) -> dict:
    qty = float(poi.qty or 0)
    received = float(poi.received_qty or 0)
    is_completed = received >= qty
    dispatch_date = _to_beijing_date(po.created_at)
    days_out = None
    if not is_completed:
        days_out = max(0, (today - dispatch_date).days - 1)
    return {
        "plating_order_item_id": poi.id,
        "plating_order_id": po.id,
        "supplier_name": po.supplier_name,
        "part_id": part.id,
        "part_name": part.name,
        "part_image": part.image,
        "plating_method": poi.plating_method,
        "qty": qty,
        "unit": poi.unit,
        "weight": float(poi.weight) if poi.weight is not None else None,
        "weight_unit": poi.weight_unit,
        "note": poi.note,
        "dispatch_date": dispatch_date,
        "days_out": days_out,
        "is_completed": is_completed,
        "receive_part_id": recv_part.id if recv_part else None,
        "receive_part_name": recv_part.name if recv_part else None,
        "receive_part_image": recv_part.image if recv_part else None,
    }


def list_dispatched(
    db: Session,
    *,
    supplier_name: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    part_keyword: Optional[str] = None,
    sort: Literal["dispatch_date_desc", "days_out_desc"] = "dispatch_date_desc",
    skip: int = 0,
    limit: int = 30,
) -> tuple[list[dict], int]:
    today = now_beijing().date()

    is_completed_expr = (PlatingOrderItem.received_qty >= PlatingOrderItem.qty)

    q = (
        db.query(PlatingOrderItem, PlatingOrder)
        .join(PlatingOrder, PlatingOrderItem.plating_order_id == PlatingOrder.id)
    )

    total = q.count()

    # Default sort: completed flag asc (False=0 first), then dispatch date desc
    q = q.order_by(
        case((is_completed_expr, 1), else_=0),
        desc(PlatingOrder.created_at),
        desc(PlatingOrderItem.id),
    )

    rows = q.offset(skip).limit(limit).all()

    # Batch-load parts (original + receive)
    part_ids = {poi.part_id for poi, _ in rows} | {
        poi.receive_part_id for poi, _ in rows if poi.receive_part_id
    }
    parts = {p.id: p for p in db.query(Part).filter(Part.id.in_(part_ids)).all()} if part_ids else {}

    items = [
        _serialize_dispatched(poi, po, parts.get(poi.part_id),
                              parts.get(poi.receive_part_id) if poi.receive_part_id else None,
                              today)
        for poi, po in rows
    ]
    return items, total
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_api_plating_summary.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add services/plating_summary.py tests/test_api_plating_summary.py
git commit -m "feat: add list_dispatched service with partition sort"
```

---

### Task 3: Service `list_dispatched` — filters + days_out_desc sort

**Files:**
- Modify: `services/plating_summary.py`
- Modify: `tests/test_api_plating_summary.py`

- [ ] **Step 1: Add failing tests for filters and alternate sort**

Append to `tests/test_api_plating_summary.py`:

```python
from datetime import datetime
from services.plating_summary import list_dispatched


def test_list_dispatched_supplier_filter(db):
    _make_part(db, "PJ-DZ-A1")
    _make_part(db, "PJ-DZ-A2")
    _make_order(db, "EP-A1", "厂A", days_ago=2)
    _make_item(db, order_id="EP-A1", part_id="PJ-DZ-A1", qty=5)
    _make_order(db, "EP-A2", "厂B", days_ago=2)
    _make_item(db, order_id="EP-A2", part_id="PJ-DZ-A2", qty=5)

    items, total = list_dispatched(db, supplier_name="厂A")
    assert total == 1
    assert items[0]["supplier_name"] == "厂A"


def test_list_dispatched_date_range_filter(db):
    _make_part(db, "PJ-DZ-D1")
    _make_part(db, "PJ-DZ-D2")
    _make_order(db, "EP-D1", "厂", days_ago=10)
    _make_item(db, order_id="EP-D1", part_id="PJ-DZ-D1", qty=5)
    _make_order(db, "EP-D2", "厂", days_ago=2)
    _make_item(db, order_id="EP-D2", part_id="PJ-DZ-D2", qty=5)

    today = now_beijing().date()
    items, total = list_dispatched(db, date_from=today - timedelta(days=5))
    assert total == 1
    assert items[0]["plating_order_id"] == "EP-D2"


def test_list_dispatched_keyword_filter(db):
    _make_part(db, "PJ-DZ-K1", name="圆形吊坠")
    _make_part(db, "PJ-DZ-K2", name="椭圆吊坠")
    _make_order(db, "EP-K1", "厂", days_ago=2)
    _make_item(db, order_id="EP-K1", part_id="PJ-DZ-K1", qty=5)
    _make_order(db, "EP-K2", "厂", days_ago=2)
    _make_item(db, order_id="EP-K2", part_id="PJ-DZ-K2", qty=5)

    items, total = list_dispatched(db, part_keyword="圆形")
    assert total == 1
    assert items[0]["part_name"] == "圆形吊坠"


def test_list_dispatched_sort_days_out_flattens_partition(db):
    """When sort=days_out_desc, completed items are NOT pushed to bottom."""
    _make_part(db, "PJ-DZ-S1")
    _make_part(db, "PJ-DZ-S2")
    _make_part(db, "PJ-DZ-S3")
    # Completed item, but oldest (would have biggest days_out if it were tracked)
    _make_order(db, "EP-S1", "厂", days_ago=20)
    _make_item(db, order_id="EP-S1", part_id="PJ-DZ-S1", qty=5, received=5)
    # In-progress, 8 days
    _make_order(db, "EP-S2", "厂", days_ago=10)
    _make_item(db, order_id="EP-S2", part_id="PJ-DZ-S2", qty=5, received=0)
    # In-progress, 1 day
    _make_order(db, "EP-S3", "厂", days_ago=2)
    _make_item(db, order_id="EP-S3", part_id="PJ-DZ-S3", qty=5, received=0)

    items, total = list_dispatched(db, sort="days_out_desc")
    # In-progress sorted by days_out desc; completed item has days_out=0 → at the end
    assert [i["plating_order_id"] for i in items] == ["EP-S2", "EP-S3", "EP-S1"]


def test_list_dispatched_pagination(db):
    for i in range(5):
        pid = f"PJ-DZ-P{i}"
        _make_part(db, pid)
        _make_order(db, f"EP-P{i}", "厂", days_ago=i)
        _make_item(db, order_id=f"EP-P{i}", part_id=pid, qty=5)
    items, total = list_dispatched(db, skip=2, limit=2)
    assert total == 5
    assert len(items) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_plating_summary.py -v`
Expected: 4 new tests fail (date filter and keyword may pass trivially if no implementation rejects, but supplier/sort fail).

- [ ] **Step 3: Implement filters + alternate sort**

Edit `services/plating_summary.py` — replace `list_dispatched` body with:

```python
def list_dispatched(
    db: Session,
    *,
    supplier_name: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    part_keyword: Optional[str] = None,
    sort: Literal["dispatch_date_desc", "days_out_desc"] = "dispatch_date_desc",
    skip: int = 0,
    limit: int = 30,
) -> tuple[list[dict], int]:
    from services._helpers import keyword_filter

    today = now_beijing().date()
    is_completed_expr = (PlatingOrderItem.received_qty >= PlatingOrderItem.qty)

    q = (
        db.query(PlatingOrderItem, PlatingOrder)
        .join(PlatingOrder, PlatingOrderItem.plating_order_id == PlatingOrder.id)
    )

    if supplier_name:
        q = q.filter(PlatingOrder.supplier_name == supplier_name)
    if date_from is not None:
        q = q.filter(func.date(PlatingOrder.created_at) >= date_from)
    if date_to is not None:
        q = q.filter(func.date(PlatingOrder.created_at) <= date_to)

    if part_keyword:
        q = q.join(Part, PlatingOrderItem.part_id == Part.id)
        kw = keyword_filter(part_keyword, [Part.id, Part.name])
        if kw is not None:
            q = q.filter(kw)

    total = q.count()

    if sort == "days_out_desc":
        # days_out = max(0, today - dispatch - 1); completed → 0
        # Since SQL date arithmetic is awkward, fall back to ordering by dispatch asc (older first)
        # for in-progress items, then completed last.
        q = q.order_by(
            case((is_completed_expr, 1), else_=0),
            asc(PlatingOrder.created_at),
            desc(PlatingOrderItem.id),
        )
    else:
        q = q.order_by(
            case((is_completed_expr, 1), else_=0),
            desc(PlatingOrder.created_at),
            desc(PlatingOrderItem.id),
        )

    rows = q.offset(skip).limit(limit).all()

    part_ids = {poi.part_id for poi, _ in rows} | {
        poi.receive_part_id for poi, _ in rows if poi.receive_part_id
    }
    parts = {p.id: p for p in db.query(Part).filter(Part.id.in_(part_ids)).all()} if part_ids else {}

    items = [
        _serialize_dispatched(poi, po, parts.get(poi.part_id),
                              parts.get(poi.receive_part_id) if poi.receive_part_id else None,
                              today)
        for poi, po in rows
    ]
    return items, total
```

Note on `days_out_desc`: ordering by `created_at asc` produces the same ordering as ordering by `days_out desc` because `days_out = today - dispatch - 1` is monotonically decreasing in `dispatch`. This avoids portable date-diff SQL and keeps DB-side ordering exact.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_plating_summary.py -v`
Expected: 6 passed (2 from Task 2 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add services/plating_summary.py tests/test_api_plating_summary.py
git commit -m "feat: add filters and days_out_desc sort to list_dispatched"
```

---

### Task 4: Service `list_received` — inclusion + aggregation + loss state

**Files:**
- Modify: `services/plating_summary.py`
- Modify: `tests/test_api_plating_summary.py`

- [ ] **Step 1: Add failing tests for `list_received`**

Append to `tests/test_api_plating_summary.py`:

```python
from models.plating_receipt import PlatingReceipt, PlatingReceiptItem
from models.production_loss import ProductionLoss
from services.plating_summary import list_received


def _make_receipt(db, rid: str, vendor: str, *, days_ago: int = 0):
    created = now_beijing() - timedelta(days=days_ago)
    r = PlatingReceipt(id=rid, vendor_name=vendor, status="未付款", created_at=created)
    db.add(r); db.flush()
    return r


def _make_receipt_item(db, *, receipt_id: str, plating_order_item_id: int,
                       part_id: str, qty: float, price: float = 1.0):
    ri = PlatingReceiptItem(
        plating_receipt_id=receipt_id,
        plating_order_item_id=plating_order_item_id,
        part_id=part_id,
        qty=Decimal(str(qty)),
        price=Decimal(str(price)),
        amount=Decimal(str(qty * price)),
        unit="件",
    )
    db.add(ri); db.flush()
    return ri


def _make_loss(db, *, order_id: str, item_id: int, loss_qty: float, part_id: str):
    pl = ProductionLoss(
        order_type="plating", order_id=order_id, item_id=item_id,
        item_type="plating_item", part_id=part_id,
        loss_qty=Decimal(str(loss_qty)),
    )
    db.add(pl); db.flush()
    return pl


def test_list_received_inclusion_excludes_zero_received(db):
    _make_part(db, "PJ-DZ-R1")
    _make_part(db, "PJ-DZ-R2")
    _make_order(db, "EP-R1", "厂A", days_ago=2)
    _make_item(db, order_id="EP-R1", part_id="PJ-DZ-R1", qty=10, received=0)  # excluded
    _make_order(db, "EP-R2", "厂A", days_ago=2)
    it2 = _make_item(db, order_id="EP-R2", part_id="PJ-DZ-R2", qty=10, received=5)  # included

    items, total = list_received(db)
    assert total == 1
    assert items[0]["plating_order_item_id"] == it2.id


def test_list_received_actual_vs_loss_split(db):
    """received_qty bumps from real receipts AND loss; service must split correctly."""
    _make_part(db, "PJ-DZ-S1")
    _make_order(db, "EP-S1", "厂", days_ago=2)
    poi = _make_item(db, order_id="EP-S1", part_id="PJ-DZ-S1", qty=10, received=8)
    _make_receipt(db, "ER-S1", "厂", days_ago=1)
    _make_receipt_item(db, receipt_id="ER-S1", plating_order_item_id=poi.id,
                       part_id="PJ-DZ-S1", qty=5)
    _make_loss(db, order_id="EP-S1", item_id=poi.id, loss_qty=3, part_id="PJ-DZ-S1")

    items, _ = list_received(db)
    assert items[0]["actual_received_qty"] == 5
    assert items[0]["loss_total_qty"] == 3
    assert items[0]["unreceived_qty"] == 2  # qty - received_qty = 10 - 8


def test_list_received_loss_state(db):
    """Three loss states based on actual_received and loss_total."""
    # State 1: none — qty == actual_received, no loss
    _make_part(db, "PJ-DZ-N1")
    _make_order(db, "EP-N1", "厂", days_ago=2)
    poi1 = _make_item(db, order_id="EP-N1", part_id="PJ-DZ-N1", qty=5, received=5)
    _make_receipt(db, "ER-N1", "厂", days_ago=1)
    _make_receipt_item(db, receipt_id="ER-N1", plating_order_item_id=poi1.id,
                       part_id="PJ-DZ-N1", qty=5)

    # State 2: pending — qty > actual_received, no loss
    _make_part(db, "PJ-DZ-P1")
    _make_order(db, "EP-P1", "厂", days_ago=2)
    poi2 = _make_item(db, order_id="EP-P1", part_id="PJ-DZ-P1", qty=10, received=5)
    _make_receipt(db, "ER-P1", "厂", days_ago=1)
    _make_receipt_item(db, receipt_id="ER-P1", plating_order_item_id=poi2.id,
                       part_id="PJ-DZ-P1", qty=5)

    # State 3: confirmed — has loss
    _make_part(db, "PJ-DZ-C1")
    _make_order(db, "EP-C1", "厂", days_ago=2)
    poi3 = _make_item(db, order_id="EP-C1", part_id="PJ-DZ-C1", qty=10, received=10)
    _make_receipt(db, "ER-C1", "厂", days_ago=1)
    _make_receipt_item(db, receipt_id="ER-C1", plating_order_item_id=poi3.id,
                       part_id="PJ-DZ-C1", qty=8)
    _make_loss(db, order_id="EP-C1", item_id=poi3.id, loss_qty=2, part_id="PJ-DZ-C1")

    items, _ = list_received(db)
    by_id = {i["plating_order_item_id"]: i for i in items}
    assert by_id[poi1.id]["loss_state"] == "none"
    assert by_id[poi2.id]["loss_state"] == "pending"
    assert by_id[poi3.id]["loss_state"] == "confirmed"


def test_list_received_multi_receipt_aggregation(db):
    """Receipts list is sorted newest first, latest_receipt_id reflects newest."""
    _make_part(db, "PJ-DZ-M1")
    _make_order(db, "EP-M1", "厂", days_ago=10)
    poi = _make_item(db, order_id="EP-M1", part_id="PJ-DZ-M1", qty=10, received=8)
    _make_receipt(db, "ER-M1", "厂", days_ago=5)  # older
    _make_receipt_item(db, receipt_id="ER-M1", plating_order_item_id=poi.id,
                       part_id="PJ-DZ-M1", qty=3)
    _make_receipt(db, "ER-M2", "厂", days_ago=2)  # newer
    _make_receipt_item(db, receipt_id="ER-M2", plating_order_item_id=poi.id,
                       part_id="PJ-DZ-M1", qty=5)

    items, _ = list_received(db)
    item = items[0]
    assert [r["receipt_id"] for r in item["receipts"]] == ["ER-M2", "ER-M1"]
    assert item["latest_receipt_id"] == "ER-M2"
    assert item["actual_received_qty"] == 8


def test_list_received_full_loss_no_receipt_appears(db):
    """Per Q-E: 100% loss with 0 receipts still appears in 已收回."""
    _make_part(db, "PJ-DZ-F1")
    _make_order(db, "EP-F1", "厂", days_ago=2)
    poi = _make_item(db, order_id="EP-F1", part_id="PJ-DZ-F1", qty=10, received=10)
    _make_loss(db, order_id="EP-F1", item_id=poi.id, loss_qty=10, part_id="PJ-DZ-F1")

    items, total = list_received(db)
    assert total == 1
    assert items[0]["actual_received_qty"] == 0
    assert items[0]["loss_total_qty"] == 10
    assert items[0]["unreceived_qty"] == 0
    assert items[0]["loss_state"] == "confirmed"
    assert items[0]["receipts"] == []
    assert items[0]["latest_receipt_id"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_plating_summary.py -v -k "received"`
Expected: 5 fail with `cannot import name 'list_received'`.

- [ ] **Step 3: Implement `list_received`**

Append to `services/plating_summary.py`:

```python
from models.plating_receipt import PlatingReceipt, PlatingReceiptItem
from models.production_loss import ProductionLoss


def _serialize_received(poi: PlatingOrderItem, po: PlatingOrder, part: Part,
                        recv_part: Optional[Part], today: date,
                        receipts: list[dict], loss_total: float) -> dict:
    base = _serialize_dispatched(poi, po, part, recv_part, today)
    qty = base["qty"]
    received_qty = float(poi.received_qty or 0)
    actual_received = received_qty - loss_total

    if loss_total > 0:
        loss_state = "confirmed"
    elif qty > actual_received:
        loss_state = "pending"
    else:
        loss_state = "none"

    base.update({
        "actual_received_qty": actual_received,
        "unreceived_qty": qty - received_qty,
        "loss_total_qty": loss_total,
        "loss_state": loss_state,
        "receipts": receipts,
        "latest_receipt_id": receipts[0]["receipt_id"] if receipts else None,
    })
    return base


def list_received(
    db: Session,
    *,
    supplier_name: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    part_keyword: Optional[str] = None,
    skip: int = 0,
    limit: int = 30,
) -> tuple[list[dict], int]:
    from services._helpers import keyword_filter

    today = now_beijing().date()
    is_completed_expr = (PlatingOrderItem.received_qty >= PlatingOrderItem.qty)

    q = (
        db.query(PlatingOrderItem, PlatingOrder)
        .join(PlatingOrder, PlatingOrderItem.plating_order_id == PlatingOrder.id)
        .filter(PlatingOrderItem.received_qty > 0)
    )

    if supplier_name:
        q = q.filter(PlatingOrder.supplier_name == supplier_name)
    if part_keyword:
        q = q.join(Part, PlatingOrderItem.part_id == Part.id)
        kw = keyword_filter(part_keyword, [Part.id, Part.name])
        if kw is not None:
            q = q.filter(kw)

    # Date filter on receipt date — handled after pulling receipts (multi-row).
    # We fetch all matching items first, then post-filter in Python on receipts.

    q = q.order_by(
        case((is_completed_expr, 1), else_=0),
        desc(PlatingOrder.created_at),
        desc(PlatingOrderItem.id),
    )

    all_rows = q.all()  # date filter on receipts requires post-fetch filtering

    poi_ids = [poi.id for poi, _ in all_rows]
    if not poi_ids:
        return [], 0

    # Batch-load receipts
    receipt_rows = (
        db.query(PlatingReceiptItem, PlatingReceipt)
        .join(PlatingReceipt, PlatingReceiptItem.plating_receipt_id == PlatingReceipt.id)
        .filter(PlatingReceiptItem.plating_order_item_id.in_(poi_ids))
        .order_by(desc(PlatingReceipt.created_at), desc(PlatingReceiptItem.id))
        .all()
    )
    receipts_by_poi: dict[int, list[dict]] = {}
    for ri, rcpt in receipt_rows:
        receipts_by_poi.setdefault(ri.plating_order_item_id, []).append({
            "receipt_id": rcpt.id,
            "receipt_item_id": ri.id,
            "receipt_date": _to_beijing_date(rcpt.created_at),
        })

    # Batch-load losses
    loss_rows = (
        db.query(ProductionLoss.item_id, func.sum(ProductionLoss.loss_qty))
        .filter(
            ProductionLoss.order_type == "plating",
            ProductionLoss.item_type == "plating_item",
            ProductionLoss.item_id.in_(poi_ids),
        )
        .group_by(ProductionLoss.item_id)
        .all()
    )
    loss_by_poi = {item_id: float(total) for item_id, total in loss_rows}

    # Batch-load parts
    part_ids = {poi.part_id for poi, _ in all_rows} | {
        poi.receive_part_id for poi, _ in all_rows if poi.receive_part_id
    }
    parts = {p.id: p for p in db.query(Part).filter(Part.id.in_(part_ids)).all()} if part_ids else {}

    items = []
    for poi, po in all_rows:
        receipts = receipts_by_poi.get(poi.id, [])
        loss_total = loss_by_poi.get(poi.id, 0.0)

        # Date filter on receipt date (any receipt in range matches).
        # Items with NO receipts (full-loss case) match only when no date filter is set.
        if date_from is not None or date_to is not None:
            matched = False
            for r in receipts:
                d = r["receipt_date"]
                if date_from is not None and d < date_from:
                    continue
                if date_to is not None and d > date_to:
                    continue
                matched = True
                break
            if not matched:
                continue

        items.append(_serialize_received(
            poi, po,
            parts.get(poi.part_id),
            parts.get(poi.receive_part_id) if poi.receive_part_id else None,
            today, receipts, loss_total,
        ))

    total = len(items)
    paged = items[skip:skip + limit]
    return paged, total
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_plating_summary.py -v`
Expected: all tests pass (Tasks 2–4).

- [ ] **Step 5: Commit**

```bash
git add services/plating_summary.py tests/test_api_plating_summary.py
git commit -m "feat: add list_received service with loss aggregation"
```

---

### Task 5: Service `list_received` — date filter + pagination tests

**Files:**
- Modify: `tests/test_api_plating_summary.py`

This task adds tests for date filter (post-fetch by receipt date) and pagination, which are already implemented in Task 4. If a test fails, fix the implementation.

- [ ] **Step 1: Add tests**

Append to `tests/test_api_plating_summary.py`:

```python
def test_list_received_date_range_filter_on_receipt_date(db):
    _make_part(db, "PJ-DZ-DR1")
    _make_part(db, "PJ-DZ-DR2")
    _make_order(db, "EP-DR1", "厂", days_ago=20)
    poi1 = _make_item(db, order_id="EP-DR1", part_id="PJ-DZ-DR1", qty=5, received=5)
    _make_receipt(db, "ER-DR1", "厂", days_ago=15)  # old
    _make_receipt_item(db, receipt_id="ER-DR1", plating_order_item_id=poi1.id,
                       part_id="PJ-DZ-DR1", qty=5)

    _make_order(db, "EP-DR2", "厂", days_ago=10)
    poi2 = _make_item(db, order_id="EP-DR2", part_id="PJ-DZ-DR2", qty=5, received=5)
    _make_receipt(db, "ER-DR2", "厂", days_ago=2)   # recent
    _make_receipt_item(db, receipt_id="ER-DR2", plating_order_item_id=poi2.id,
                       part_id="PJ-DZ-DR2", qty=5)

    today = now_beijing().date()
    items, total = list_received(db, date_from=today - timedelta(days=5))
    assert total == 1
    assert items[0]["plating_order_item_id"] == poi2.id


def test_list_received_pagination(db):
    for i in range(5):
        pid = f"PJ-DZ-RP{i}"
        _make_part(db, pid)
        _make_order(db, f"EP-RP{i}", "厂", days_ago=i)
        poi = _make_item(db, order_id=f"EP-RP{i}", part_id=pid, qty=5, received=5)
        _make_receipt(db, f"ER-RP{i}", "厂", days_ago=i)
        _make_receipt_item(db, receipt_id=f"ER-RP{i}", plating_order_item_id=poi.id,
                           part_id=pid, qty=5)
    items, total = list_received(db, skip=2, limit=2)
    assert total == 5
    assert len(items) == 2
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_api_plating_summary.py -v`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_api_plating_summary.py
git commit -m "test: add date filter and pagination tests for list_received"
```

---

### Task 6: API endpoints

**Files:**
- Create: `api/plating_summary.py`
- Modify: `main.py`
- Modify: `tests/test_api_plating_summary.py`

- [ ] **Step 1: Add API smoke tests**

Append to `tests/test_api_plating_summary.py`:

```python
def test_api_dispatched_smoke(client, db):
    _make_part(db, "PJ-DZ-API1")
    _make_order(db, "EP-API1", "厂A", days_ago=2)
    _make_item(db, order_id="EP-API1", part_id="PJ-DZ-API1", qty=5)

    resp = client.get("/api/plating-summary/dispatched")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["plating_order_id"] == "EP-API1"
    assert body["items"][0]["is_completed"] is False


def test_api_dispatched_filters_pass_through(client, db):
    _make_part(db, "PJ-DZ-API2")
    _make_part(db, "PJ-DZ-API3")
    _make_order(db, "EP-API2", "厂A", days_ago=2)
    _make_item(db, order_id="EP-API2", part_id="PJ-DZ-API2", qty=5)
    _make_order(db, "EP-API3", "厂B", days_ago=2)
    _make_item(db, order_id="EP-API3", part_id="PJ-DZ-API3", qty=5)

    resp = client.get("/api/plating-summary/dispatched", params={"supplier_name": "厂A"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_api_received_smoke(client, db):
    _make_part(db, "PJ-DZ-RA1")
    _make_order(db, "EP-RA1", "厂", days_ago=2)
    poi = _make_item(db, order_id="EP-RA1", part_id="PJ-DZ-RA1", qty=5, received=5)
    _make_receipt(db, "ER-RA1", "厂", days_ago=1)
    _make_receipt_item(db, receipt_id="ER-RA1", plating_order_item_id=poi.id,
                       part_id="PJ-DZ-RA1", qty=5)

    resp = client.get("/api/plating-summary/received")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["loss_state"] == "none"
    assert body["items"][0]["latest_receipt_id"] == "ER-RA1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_plating_summary.py -v -k "api"`
Expected: 3 fail with 404.

- [ ] **Step 3: Create API module**

```python
# api/plating_summary.py
from datetime import date as date_type
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from schemas.plating_summary import DispatchedListResponse, ReceivedListResponse
from services.plating_summary import list_dispatched, list_received

router = APIRouter(prefix="/api/plating-summary", tags=["plating-summary"])


@router.get("/dispatched", response_model=DispatchedListResponse)
def api_list_dispatched(
    supplier_name: Optional[str] = Query(None),
    date_from: Optional[date_type] = Query(None),
    date_to: Optional[date_type] = Query(None),
    part_keyword: Optional[str] = Query(None),
    sort: Literal["dispatch_date_desc", "days_out_desc"] = Query("dispatch_date_desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    items, total = list_dispatched(
        db, supplier_name=supplier_name,
        date_from=date_from, date_to=date_to,
        part_keyword=part_keyword, sort=sort,
        skip=skip, limit=limit,
    )
    return {"items": items, "total": total}


@router.get("/received", response_model=ReceivedListResponse)
def api_list_received(
    supplier_name: Optional[str] = Query(None),
    date_from: Optional[date_type] = Query(None),
    date_to: Optional[date_type] = Query(None),
    part_keyword: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    items, total = list_received(
        db, supplier_name=supplier_name,
        date_from=date_from, date_to=date_to,
        part_keyword=part_keyword,
        skip=skip, limit=limit,
    )
    return {"items": items, "total": total}
```

- [ ] **Step 4: Register router in `main.py`**

Add to imports section (alongside `from api.plating_receipt import router as plating_receipt_router`):

```python
from api.plating_summary import router as plating_summary_router
```

Add to router registrations (next to `app.include_router(plating_router, ...)`):

```python
app.include_router(plating_summary_router, dependencies=[require_permission("plating")])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_api_plating_summary.py -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add api/plating_summary.py main.py tests/test_api_plating_summary.py
git commit -m "feat: add /api/plating-summary endpoints"
```

---

## Phase 2 — Frontend Foundation

### Task 7: Icon component

**Files:**
- Create: `frontend/src/components/icons/PlatingSummaryIcon.vue`

- [ ] **Step 1: Create the icon component**

```vue
<!-- frontend/src/components/icons/PlatingSummaryIcon.vue -->
<template>
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
    <path d="M821.6064 792.3712H215.04c-73.4208 0-133.12-59.6992-133.12-133.12V215.6544c0-73.4208 59.6992-133.12 133.12-133.12h606.5664c73.4208 0 133.12 59.6992 133.12 133.12v443.5968c0 73.3696-59.7504 133.12-133.12 133.12zM215.04 143.9744c-39.5264 0-71.68 32.1536-71.68 71.68v443.5968c0 39.5264 32.1536 71.68 71.68 71.68h606.5664c39.5264 0 71.68-32.1536 71.68-71.68V215.6544c0-39.5264-32.1536-71.68-71.68-71.68H215.04zM712.4992 942.4896H324.096c-16.9472 0-30.72-13.7728-30.72-30.72s13.7728-30.72 30.72-30.72h388.4032c16.9472 0 30.72 13.7728 30.72 30.72s-13.7216 30.72-30.72 30.72z" fill="currentColor" />
    <path d="M324.608 566.528c-16.9472 0-30.72-13.7728-30.72-30.72V444.6208c0-16.9472 13.7728-30.72 30.72-30.72s30.72 13.7728 30.72 30.72v91.1872c0 16.9472-13.7216 30.72-30.72 30.72zM514.3552 566.528c-16.9472 0-30.72-13.7728-30.72-30.72V319.6416c0-16.9472 13.7728-30.72 30.72-30.72s30.72 13.7728 30.72 30.72v216.1664c0 16.9472-13.7728 30.72-30.72 30.72zM705.9968 566.528c-16.9472 0-30.72-13.7728-30.72-30.72V388.7616c0-16.9472 13.7728-30.72 30.72-30.72s30.72 13.7728 30.72 30.72v147.0464c0 16.9472-13.7216 30.72-30.72 30.72z" fill="currentColor" />
  </svg>
</template>
```

(SVG path data is from `frontend/src/assets/icons/汇总.svg`, with `fill="currentColor"` so it inherits the menu color theme like other custom icons.)

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/icons/PlatingSummaryIcon.vue
git commit -m "feat: add PlatingSummaryIcon component"
```

---

### Task 8: Frontend API client

**Files:**
- Create: `frontend/src/api/platingSummary.js`

- [ ] **Step 1: Create the API client**

```js
// frontend/src/api/platingSummary.js
import api from './index'

export const listDispatchedSummary = (params) =>
  api.get('/plating-summary/dispatched', { params })

export const listReceivedSummary = (params) =>
  api.get('/plating-summary/received', { params })
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/platingSummary.js
git commit -m "feat: add plating summary API client"
```

---

### Task 9: Router + Permission map + Menu rename

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/layouts/DefaultLayout.vue`

- [ ] **Step 1: Add route to `frontend/src/router/index.js`**

In the `ROUTE_PERMISSION_MAP` object, add `'plating-summary': 'plating',` (next to `'plating': 'plating',`).

In `PERMISSION_ROUTE_ORDER`, no change required (the order is for first-permitted-route, not for menu).

In the `routes[].children` array, add (right after the existing `'plating-receipts/:id'` route):

```js
{ path: 'plating-summary', component: lazyLoad(() => import('@/views/plating/PlatingSummary.vue')), meta: { perm: 'plating' } },
```

- [ ] **Step 2: Update menu in `frontend/src/layouts/DefaultLayout.vue`**

Add icon import next to existing icon imports:

```js
import PlatingSummaryIcon from '@/components/icons/PlatingSummaryIcon.vue'
```

In `allFlatItems`, add (after the `'plating-receipts'` entry):

```js
{ label: '电镀汇总', key: 'plating-summary', icon: icon(PlatingSummaryIcon), perm: 'plating' },
```

In `allGroupedItems` → group `'group-production'`, locate the `'plating-group'` entry and:
1. Change `label: '电镀单'` → `label: '电镀'`
2. Add a third child after `'plating-receipts'`:

```js
{ label: '电镀汇总', key: 'plating-summary', icon: icon(PlatingSummaryIcon), perm: 'plating' },
```

- [ ] **Step 3: Smoke check the frontend builds**

Run: `cd frontend && npm run build`
Expected: build succeeds with no errors. (The route target file does not exist yet — `lazyLoad` is a runtime import, so build still succeeds.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/router/index.js frontend/src/layouts/DefaultLayout.vue
git commit -m "feat: rename plating menu group and add 电镀汇总 entry"
```

---

### Task 10: Skeleton page (renders with empty data)

**Files:**
- Create: `frontend/src/views/plating/PlatingSummary.vue`

- [ ] **Step 1: Create skeleton page**

```vue
<!-- frontend/src/views/plating/PlatingSummary.vue -->
<template>
  <div class="plating-summary">
    <div class="page-head">
      <h2 class="page-title">电镀汇总</h2>
    </div>

    <div class="toolbar">
      <n-button-group>
        <n-button :type="tab === 'out' ? 'primary' : 'default'" @click="setTab('out')">已发出</n-button>
        <n-button :type="tab === 'in' ? 'primary' : 'default'" @click="setTab('in')">已收回</n-button>
      </n-button-group>

      <div class="filters">
        <n-date-picker v-model:value="dateRangeRaw" type="daterange" clearable style="width: 240px" placeholder="日期范围" />
        <n-select v-model:value="supplier" :options="supplierOptions" placeholder="商家" clearable style="width: 160px" />
        <n-input v-model:value="qInput" placeholder="搜索 ID 或配件名" clearable style="width: 220px" />
      </div>
    </div>

    <n-spin :show="loading">
      <n-data-table
        :columns="columns"
        :data="rows"
        :row-class-name="rowClassName"
        :scroll-x="1400"
        size="small"
      />
    </n-spin>

    <div class="pager-wrap">
      <n-pagination v-model:page="page" :page-count="pageCount" :page-size="pageSize" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton, NButtonGroup, NDataTable, NDatePicker, NInput, NPagination, NSelect, NSpin,
} from 'naive-ui'
import { listDispatchedSummary, listReceivedSummary } from '@/api/platingSummary'
import { getPlatingSuppliers } from '@/api/plating'

const route = useRoute()
const router = useRouter()

const tab = ref('out')
const supplier = ref(null)
const dateRangeRaw = ref(null)  // [startMs, endMs] from NDatePicker
const qInput = ref('')
const page = ref(1)
const pageSize = 30

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const supplierOptions = ref([])

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const columns = computed(() => [])  // filled in next tasks
const rowClassName = () => ''

function setTab(t) { tab.value = t; page.value = 1 }

async function loadSuppliers() {
  const list = await getPlatingSuppliers()
  supplierOptions.value = list.map((s) => ({ label: s, value: s }))
}

async function load() { /* implemented in Task 11 */ }

onMounted(() => { loadSuppliers() })
watch([tab, supplier, dateRangeRaw, page], load)
</script>

<style scoped>
.plating-summary { padding: 4px 0; }
.page-head { margin-bottom: 12px; }
.page-title { font-size: 20px; font-weight: 700; margin: 0; }
.toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; gap: 12px; flex-wrap: wrap;
}
.filters { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.pager-wrap { display: flex; justify-content: flex-end; margin-top: 12px; }
</style>
```

- [ ] **Step 2: Manual smoke check**

Start the backend (`python main.py`) and frontend (`cd frontend && npm run dev`) in two terminals. Open the app, navigate to `/plating-summary`. Expected: page renders with title, two tab buttons, filter row, empty table, paginator. No console errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/plating/PlatingSummary.vue
git commit -m "feat: add PlatingSummary skeleton page"
```

---

## Phase 3 — Frontend Implementation

### Task 11: 已发出 tab — columns + data load + URL state

**Files:**
- Modify: `frontend/src/views/plating/PlatingSummary.vue`

- [ ] **Step 1: Replace script block with full data-load + URL sync logic**

Replace the entire `<script setup>` block of `PlatingSummary.vue` with:

```js
import { ref, computed, watch, onMounted, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton, NButtonGroup, NDataTable, NDatePicker, NInput, NPagination, NSelect, NSpin, NTag,
} from 'naive-ui'
import { listDispatchedSummary, listReceivedSummary } from '@/api/platingSummary'
import { getPlatingSuppliers } from '@/api/plating'
import { renderImageThumb } from '@/utils/ui'

const route = useRoute()
const router = useRouter()

const tab = ref('out')
const supplier = ref(null)
const dateRangeRaw = ref(null)   // [startMs, endMs]
const qInput = ref('')
const qDebounced = ref('')
const sortByDays = ref(false)    // user clicked 发出天数 column
const page = ref(1)
const pageSize = 30

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const supplierOptions = ref([])

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

// --- URL <-> state sync ---
function syncStateFromQuery() {
  const q = route.query
  tab.value = q.tab === 'in' ? 'in' : 'out'
  supplier.value = q.supplier || null
  if (q.date_from || q.date_to) {
    const from = q.date_from ? new Date(q.date_from).getTime() : null
    const to = q.date_to ? new Date(q.date_to).getTime() : null
    dateRangeRaw.value = (from && to) ? [from, to] : null
  } else {
    dateRangeRaw.value = null
  }
  qInput.value = q.q || ''
  qDebounced.value = q.q || ''
  sortByDays.value = q.sort === 'days'
  page.value = parseInt(q.page) || 1
}

function pushQuery() {
  const q = {}
  if (tab.value !== 'out') q.tab = tab.value
  if (supplier.value) q.supplier = supplier.value
  if (dateRangeRaw.value) {
    q.date_from = new Date(dateRangeRaw.value[0]).toISOString().slice(0, 10)
    q.date_to = new Date(dateRangeRaw.value[1]).toISOString().slice(0, 10)
  }
  if (qDebounced.value) q.q = qDebounced.value
  if (sortByDays.value) q.sort = 'days'
  if (page.value > 1) q.page = page.value
  router.replace({ query: q })
}

// 300ms debounce on search input
let qTimer = null
watch(qInput, (v) => {
  clearTimeout(qTimer)
  qTimer = setTimeout(() => { qDebounced.value = v; page.value = 1 }, 300)
})

function setTab(t) { tab.value = t; page.value = 1; sortByDays.value = false }
function toggleSortDays() { sortByDays.value = !sortByDays.value; page.value = 1 }

// --- Data loaders ---
async function loadSuppliers() {
  const list = await getPlatingSuppliers()
  supplierOptions.value = list.map((s) => ({ label: s, value: s }))
}

function buildParams() {
  const params = { skip: (page.value - 1) * pageSize, limit: pageSize }
  if (supplier.value) params.supplier_name = supplier.value
  if (dateRangeRaw.value) {
    params.date_from = new Date(dateRangeRaw.value[0]).toISOString().slice(0, 10)
    params.date_to = new Date(dateRangeRaw.value[1]).toISOString().slice(0, 10)
  }
  if (qDebounced.value) params.part_keyword = qDebounced.value
  if (tab.value === 'out' && sortByDays.value) params.sort = 'days_out_desc'
  return params
}

async function load() {
  loading.value = true
  try {
    const fn = tab.value === 'out' ? listDispatchedSummary : listReceivedSummary
    const data = await fn(buildParams())
    rows.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
  pushQuery()
}

// --- Cell renderers ---
const renderPart = (row) => h('span', { style: 'display:inline-flex;align-items:center;gap:8px;' }, [
  renderImageThumb(row.part_image, row.part_name, 32),
  h('span', row.part_name),
])

const renderReceivePart = (row) => row.receive_part_id
  ? h('span', { style: 'display:inline-flex;align-items:center;gap:8px;' }, [
      renderImageThumb(row.receive_part_image, row.receive_part_name, 32),
      h('span', row.receive_part_name),
    ])
  : h('span', { style: 'color:#94A3B8' }, '—')

const renderColor = (row) => row.plating_method
  ? h(NTag, { size: 'small', type: 'default', round: true }, { default: () => row.plating_method })
  : h('span', { style: 'color:#94A3B8' }, '—')

const renderOrderLink = (row) => h('span', {
  style: 'color:#6366F1;cursor:pointer;font-family:ui-monospace,monospace;',
  onClick: () => navigateToDetail('plating', row.plating_order_id, row.plating_order_item_id),
}, row.plating_order_id)

function navigateToDetail(kind, id, highlightId) {
  const path = kind === 'plating' ? `/plating/${id}` : `/plating-receipts/${id}`
  // store current summary state for back-nav (Task 18 reads it)
  sessionStorage.setItem('plating-summary-return', JSON.stringify(route.query))
  router.push({ path, query: { highlight: highlightId } })
}

const dispatchedColumns = computed(() => [
  { title: '商家', key: 'supplier_name' },
  {
    title: '发出天数',
    key: 'days_out',
    sorter: false,
    titleColSpan: 1,
    render: (row) => row.days_out == null
      ? h('span', { style: 'color:#94A3B8' }, '—')
      : h('span', { style: `font-weight:600;color:${dayColor(row.days_out)};` }, `${row.days_out} 天`),
    title: () => h('span', {
      style: 'cursor:pointer;user-select:none',
      onClick: toggleSortDays,
    }, ['发出天数', sortByDays.value ? ' ↓' : '']),
  },
  { title: 'ID', key: 'part_id' },
  { title: '配件', key: 'part_name', render: renderPart },
  { title: '电镀颜色', key: 'plating_method', render: renderColor },
  { title: '收回配件', key: 'receive_part_name', render: renderReceivePart },
  { title: '发出日期', key: 'dispatch_date' },
  { title: '发出数量', key: 'qty', align: 'right' },
  { title: '单位', key: 'unit' },
  { title: '重量', key: 'weight', render: (row) => row.weight == null ? '' : `${row.weight} ${row.weight_unit || ''}`.trim() },
  { title: '备注', key: 'note' },
  { title: '电镀单号', key: 'plating_order_id', render: renderOrderLink },
])

const columns = computed(() => tab.value === 'out' ? dispatchedColumns.value : [])

function dayColor(days) {
  if (days === 0) return '#10B981'
  if (days <= 7) return '#F59E0B'
  return '#EF4444'
}

const rowClassName = (row) => row.is_completed ? 'row-completed' : ''

onMounted(async () => {
  syncStateFromQuery()
  await loadSuppliers()
  await load()
})

watch([tab, supplier, dateRangeRaw, qDebounced, sortByDays, page], load)
```

- [ ] **Step 2: Add row-completed style**

In the `<style scoped>` block, append:

```css
:deep(.row-completed td) {
  background: #F1F5F9 !important;
  color: #94A3B8;
}
```

- [ ] **Step 3: Manual smoke check**

Reload the page. Create test data via existing UI (or inspect with seeded data). Expected: 已发出 tab shows rows with proper columns; completed rows are greyed; days color matches gradient; URL updates as filters change; clicking 发出天数 header toggles sort.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/plating/PlatingSummary.vue
git commit -m "feat: implement 已发出 tab with filters and URL sync"
```

---

### Task 12: 已收回 tab — columns + loss button

**Files:**
- Modify: `frontend/src/views/plating/PlatingSummary.vue`

- [ ] **Step 1: Add receipt-specific renderers and columns**

Inside `<script setup>`, add after `dispatchedColumns`:

```js
const renderReceiptDate = (row) => row.receipts.length === 0
  ? h('span', { style: 'color:#94A3B8' }, '—')
  : row.receipts.map((r) => r.receipt_date).join(', ')

const renderReceiptLinks = (row) => row.receipts.length === 0
  ? h('span', { style: 'color:#94A3B8' }, '—')
  : h('span', null, row.receipts.map((r, idx) => [
      h('span', {
        style: 'color:#6366F1;cursor:pointer;font-family:ui-monospace,monospace;',
        onClick: () => navigateToDetail('receipt', r.receipt_id, r.receipt_item_id),
      }, r.receipt_id),
      idx < row.receipts.length - 1 ? ', ' : '',
    ]))

const renderLoss = (row) => {
  if (row.loss_state === 'confirmed') {
    return h('span', { style: 'color:#EF4444;font-weight:600;' }, row.loss_total_qty)
  }
  if (row.loss_state === 'none') {
    return h('span', { style: 'color:#94A3B8' }, '—')
  }
  // pending
  return h(NButton, {
    size: 'tiny', type: 'error', ghost: true,
    onClick: () => openLossModal(row),
  }, { default: () => '确认损耗' })
}

const receivedColumns = computed(() => [
  { title: '商家', key: 'supplier_name' },
  { title: 'ID', key: 'part_id' },
  { title: '配件', key: 'part_name', render: renderPart },
  { title: '电镀颜色', key: 'plating_method', render: renderColor },
  { title: '收回配件', key: 'receive_part_name', render: renderReceivePart },
  { title: '发出日期', key: 'dispatch_date' },
  { title: '收回日期', key: 'receipt_dates', render: renderReceiptDate },
  { title: '发出数量', key: 'qty', align: 'right' },
  { title: '单位', key: 'unit' },
  { title: '重量', key: 'weight', render: (row) => row.weight == null ? '' : `${row.weight} ${row.weight_unit || ''}`.trim() },
  { title: '已回收', key: 'actual_received_qty', align: 'right' },
  { title: '未回收', key: 'unreceived_qty', align: 'right' },
  { title: '损耗', key: 'loss', render: renderLoss },
  { title: '备注', key: 'note' },
  { title: '电镀单号', key: 'plating_order_id', render: renderOrderLink },
  { title: '回收单号', key: 'receipt_ids', render: renderReceiptLinks },
])
```

Update the `columns` computed:

```js
const columns = computed(() => tab.value === 'out' ? dispatchedColumns.value : receivedColumns.value)
```

Add a stub `openLossModal` (filled in Task 13):

```js
function openLossModal(row) { console.log('TODO loss modal for', row) }
```

- [ ] **Step 2: Manual smoke check**

Switch to 已收回 tab. Expected: columns match spec; loss column shows `—` / 【确认损耗】 / red number based on `loss_state`; multi-receipt rows show comma-separated dates and clickable receipt IDs.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/plating/PlatingSummary.vue
git commit -m "feat: implement 已收回 tab columns with loss tri-state"
```

---

### Task 13: Confirm-loss modal

**Files:**
- Modify: `frontend/src/views/plating/PlatingSummary.vue`

The existing `PlatingReceiptDetail.vue` already implements a confirm-loss modal that hits `POST /plating-receipts/{receipt_id}/confirm-loss`. We reuse the endpoint with `latest_receipt_id` from the row.

- [ ] **Step 1: Inspect existing modal to mirror its UX**

Read `frontend/src/views/plating-receipts/PlatingReceiptDetail.vue` lines 273–298 to understand the loss modal structure (loss_qty / deduct_amount / reason / note inputs).

- [ ] **Step 2: Add modal state + UI to `PlatingSummary.vue`**

Add to `<script setup>`:

```js
import { NModal, NForm, NFormItem, NInputNumber, NInput as NInputText, useMessage } from 'naive-ui'
import api from '@/api/index'

const message = useMessage()
const lossModal = ref({ visible: false, row: null, loss_qty: null, deduct_amount: null, reason: '' })

function openLossModal(row) {
  lossModal.value = {
    visible: true, row,
    loss_qty: row.unreceived_qty,
    deduct_amount: null,
    reason: '',
  }
}

async function submitLoss() {
  const m = lossModal.value
  if (!m.row || !m.loss_qty || m.loss_qty <= 0) {
    message.error('请输入有效的损耗数量')
    return
  }
  try {
    await api.post(`/plating-receipts/${m.row.latest_receipt_id}/confirm-loss`, {
      items: [{
        plating_order_item_id: m.row.plating_order_item_id,
        loss_qty: m.loss_qty,
        deduct_amount: m.deduct_amount,
        reason: m.reason || null,
      }],
    })
    message.success('损耗已确认')
    lossModal.value.visible = false
    await load()
  } catch (e) {
    message.error(e?.response?.data?.detail || '确认损耗失败')
  }
}
```

Add to `<template>` (after `</n-spin>`):

```vue
<n-modal v-model:show="lossModal.visible" preset="card" title="确认损耗" style="width: 480px">
  <n-form label-placement="left" label-width="90">
    <n-form-item label="损耗数量">
      <n-input-number v-model:value="lossModal.loss_qty" :min="0.0001" :max="lossModal.row?.unreceived_qty" />
    </n-form-item>
    <n-form-item label="扣款金额">
      <n-input-number v-model:value="lossModal.deduct_amount" :min="0" />
    </n-form-item>
    <n-form-item label="原因">
      <n-input v-model:value="lossModal.reason" />
    </n-form-item>
  </n-form>
  <template #footer>
    <n-button @click="lossModal.visible = false" style="margin-right: 8px">取消</n-button>
    <n-button type="primary" @click="submitLoss">确认</n-button>
  </template>
</n-modal>
```

- [ ] **Step 3: Manual smoke check**

Trigger 【确认损耗】on a row. Expected: modal opens with `loss_qty` defaulted to `unreceived_qty`. On submit, the row updates (loss column becomes red number, in-progress → completed if applicable).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/plating/PlatingSummary.vue
git commit -m "feat: wire confirm-loss modal in plating summary"
```

---

### Task 14: Pagination wire-up

**Files:**
- Modify: `frontend/src/views/plating/PlatingSummary.vue`

Pagination is already partially wired (page state + `page-count`). Verify it triggers reload and resets on filter change.

- [ ] **Step 1: Verify watch covers page**

Confirm `watch([tab, supplier, dateRangeRaw, qDebounced, sortByDays, page], load)` includes `page`. (It does.)

- [ ] **Step 2: Reset page on tab/filter change**

Add to `setTab` (already done) and to filter watchers — wrap each filter watcher to reset page:

```js
watch([supplier, dateRangeRaw, qDebounced, sortByDays], () => { page.value = 1 })
```

(Place this BEFORE the existing `watch([tab, ...], load)` so the page reset propagates into the load.)

- [ ] **Step 3: Manual smoke check**

Apply a filter that reduces results, change page, then change filter again. Expected: filter change resets to page 1; pagination reflects total/30.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/plating/PlatingSummary.vue
git commit -m "feat: reset pagination on filter change"
```

---

## Phase 4 — Cross-page integration

### Task 15: Detail page back-nav preserves summary filters

**Files:**
- Modify: `frontend/src/views/plating/PlatingDetail.vue`
- Modify: `frontend/src/views/plating-receipts/PlatingReceiptDetail.vue`

The summary page stores its current `route.query` to `sessionStorage['plating-summary-return']` before navigating (already done in Task 11). The detail pages read it on mount and offer a "返回汇总" button.

- [ ] **Step 1: Add helper composable**

Create `frontend/src/composables/useSummaryReturn.js`:

```js
import { computed } from 'vue'
import { useRouter } from 'vue-router'

export function useSummaryReturn() {
  const router = useRouter()

  const returnQuery = computed(() => {
    const raw = sessionStorage.getItem('plating-summary-return')
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  })

  function back() {
    const q = returnQuery.value
    if (q) {
      sessionStorage.removeItem('plating-summary-return')
      router.push({ path: '/plating-summary', query: q })
    } else {
      router.back()
    }
  }

  return { returnQuery, back }
}
```

- [ ] **Step 2: Add "返回汇总" button to `PlatingDetail.vue`**

In `frontend/src/views/plating/PlatingDetail.vue`:

Add to the `<script setup>` imports section:

```js
import { useSummaryReturn } from '@/composables/useSummaryReturn'

const { returnQuery: summaryReturn, back: backToSummary } = useSummaryReturn()
```

Find the page header area (search for the existing "返回" button or breadcrumb near the top of `<template>`). Add adjacent to the existing nav controls:

```vue
<n-button v-if="summaryReturn" size="small" @click="backToSummary">← 返回汇总</n-button>
```

- [ ] **Step 3: Repeat for `PlatingReceiptDetail.vue`**

Apply the same `useSummaryReturn` import and the same button placement in `frontend/src/views/plating-receipts/PlatingReceiptDetail.vue`.

- [ ] **Step 4: Manual smoke check**

From summary, apply filters → click 电镀单号 → in detail, click 返回汇总. Expected: returns to summary with all filters preserved.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/composables/useSummaryReturn.js frontend/src/views/plating/PlatingDetail.vue frontend/src/views/plating-receipts/PlatingReceiptDetail.vue
git commit -m "feat: detail pages support 返回汇总 with preserved filters"
```

---

## Phase 5 — Smoke verification

### Task 16: End-to-end manual verification

**Files:** none

- [ ] **Step 1: Start backend + frontend**

Run in two terminals:
- `python main.py` (backend)
- `cd frontend && npm run dev` (frontend)

- [ ] **Step 2: Verify menu and navigation**

- Navigate to the app, sign in.
- Confirm the left menu shows the **电镀** group with three children: 电镀发出 / 电镀回收 / **电镀汇总** (with the 汇总 icon).
- Click 电镀汇总. Page loads at `/plating-summary` with default 已发出 tab.

- [ ] **Step 3: Verify 已发出 tab**

- Confirm columns match spec: 商家 / 发出天数 / ID / 配件 / 电镀颜色 / 收回配件 / 发出日期 / 发出数量 / 单位 / 重量 / 备注 / 电镀单号
- In-progress rows on top, completed rows greyed at bottom.
- Days color: 0=green, 1–7=yellow, ≥8=red.
- Click 发出天数 header → sort flips, partition collapses.

- [ ] **Step 4: Verify 已收回 tab**

- Switch to 已收回. Columns match spec including 收回日期 / 已回收 / 未回收 / 损耗 / 回收单号.
- Find a row with `loss_state=pending` → click 【确认损耗】 → modal opens → submit small loss → row updates.
- Verify multi-receipt row shows comma-separated dates and IDs.

- [ ] **Step 5: Verify filters and URL sync**

- Apply supplier / date range / search filters → URL updates (`?tab=&supplier=&date_from=&date_to=&q=&page=`).
- Reload page → state restored from URL.
- Switch tabs → filters preserved.

- [ ] **Step 6: Verify cross-jump and back-nav**

- Click an EP- link → lands on plating detail with target row highlighted (green flash).
- Click 返回汇总 → back to summary with prior filters intact.
- Same for ER- → plating receipt detail.

- [ ] **Step 7: Verify mobile horizontal scroll**

- Resize browser to mobile width or open devtools mobile emulator.
- Table should scroll horizontally; layout does not break.

- [ ] **Step 8: Run full backend test suite**

Run: `pytest tests/test_api_plating_summary.py -v && pytest -q`
Expected: new tests pass; no regressions in existing suite.

- [ ] **Step 9: Build frontend for production**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 10: No commit needed — verification only**

If any step revealed a bug, fix it in the relevant file with a focused commit. Otherwise, mark this task complete.

---

## Self-Review (already performed)

**Spec coverage check:**
- ✓ Menu rename + 电镀汇总 子项 (Task 9)
- ✓ Two tabs with default 已发出 (Task 10–11)
- ✓ Toolbar layout: tabs left, filters right (Task 10)
- ✓ Date filter single + range (Task 11 — NDatePicker daterange)
- ✓ Supplier filter, dropdown source = all-time suppliers (Task 11 — `getPlatingSuppliers`)
- ✓ Search by part ID + name, 300ms debounce (Task 11)
- ✓ 发出天数 column with color gradient + sort on click (Tasks 11, 4)
- ✓ Default sort partition (in-progress first, completed bottom) (Task 2)
- ✓ Manual sort 发出天数 ignores partition (Task 3)
- ✓ Already-received items: days_out shows `—` (Task 2 service, Task 11 render)
- ✓ Pagination 30/page (Task 14)
- ✓ Mobile horizontal scroll (Task 11 — `scroll-x`)
- ✓ 已收回 columns + loss tri-state (Task 12)
- ✓ Multi-receipt aggregation, latest first (Task 4)
- ✓ Confirm-loss reuses `/plating-receipts/{receipt_id}/confirm-loss` with `latest_receipt_id` (Task 13)
- ✓ 100% loss case appears in 已收回 (Task 4)
- ✓ Cross-jump highlight reuses existing `?highlight=` (Task 11 navigateToDetail)
- ✓ Back-nav preserves summary filters (Task 15)

**Type/name consistency:**
- DTO field names match between `schemas/plating_summary.py` and the service serializers (Tasks 1, 2, 4)
- Frontend uses `latest_receipt_id`, `loss_state`, `actual_received_qty`, `unreceived_qty`, `loss_total_qty`, `receipts[].receipt_id` etc. — all defined in the schema

**Placeholder scan:** clean — every code step has actual code; manual-test steps explicitly say "no commit / verification only".
