# Handcraft Restock Reminder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a per-(part, handcraft_order) "to-restock" todo list with three UI entry points (picking modal one-click, handcraft detail manual entry, global aggregated list page).

**Architecture:** New `restock_request` table (one row per `(part_id, handcraft_order_id)` pair, status `pending` or `done`, single forward transition). A new `services/restock.py` exposes idempotent create / mark-done / mark-part-done / delete-pending / aggregated-summary queries. Backend API adds `/api/restock-requests` router. Frontend adds a column to the picking modal, a card to the handcraft detail page, and a new `/restock` page under "生产" sidebar group. No coupling to inventory log or purchase orders. No quantities recorded.

**Tech Stack:** SQLAlchemy 2.x, FastAPI, pydantic v2, pytest, Vue 3.5 + Naive UI + Pinia, axios.

**Spec:** `docs/superpowers/specs/2026-05-07-handcraft-restock-design.md`

---

## File Structure

**New backend files:**
- `models/restock_request.py` — `RestockRequest` ORM model
- `schemas/restock.py` — Pydantic request/response models
- `services/restock.py` — service functions (create, transition, query)
- `api/restock.py` — `/api/restock-requests` router
- `tests/test_services_restock.py` — service-layer tests
- `tests/test_api_restock.py` — API tests

**Modified backend files:**
- `models/__init__.py` — register `RestockRequest`
- `services/handcraft.py:delete_handcraft_order` — cascade delete restock requests
- `services/handcraft_picking.py:get_handcraft_picking_simulation` — embed `restock_status` / `restock_request_id` on picking rows
- `schemas/handcraft.py:HandcraftPickingVariant` — add `restock_status`, `restock_request_id` fields
- `api/handcraft.py` — add `GET /{order_id}/restock-requests` endpoint
- `main.py` — register restock router
- `tests/test_api_handcraft.py` — cascade test
- `tests/test_api_handcraft_picking.py` — restock_status field test

**New frontend files:**
- `frontend/src/api/restock.js` — API client
- `frontend/src/views/restock/RestockList.vue` — global page

**Modified frontend files:**
- `frontend/src/components/picking/HandcraftPickingSimulationModal.vue` — new "需补货" column
- `frontend/src/views/handcraft/HandcraftDetail.vue` — restock card + manual add modal
- `frontend/src/router/index.js` — `/restock` route + permission map
- `frontend/src/layouts/DefaultLayout.vue` — "待补货清单" sidebar item

---

## Task 1: RestockRequest model + Pydantic schemas

**Files:**
- Create: `models/restock_request.py`
- Modify: `models/__init__.py`
- Create: `schemas/restock.py`

- [ ] **Step 1.1: Write the model**

Create `models/restock_request.py`:

```python
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from database import Base
from time_utils import now_beijing


class RestockRequest(Base):
    """A pending or completed restock request, scoped to a (part, handcraft_order)
    pair. Pure 'todo list' — does not affect inventory or order status.
    Status flows pending -> done (one-way). One row per pair, ever."""

    __tablename__ = "restock_request"

    id = Column(Integer, primary_key=True, autoincrement=True)
    part_id = Column(String, ForeignKey("part.id"), nullable=False, index=True)
    handcraft_order_id = Column(
        String, ForeignKey("handcraft_order.id"), nullable=True, index=True
    )
    source = Column(String, nullable=False)  # "picking" | "manual"
    status = Column(String, nullable=False, default="pending")  # "pending" | "done"
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_beijing, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("part_id", "handcraft_order_id", name="uq_restock_part_order"),
    )
```

- [ ] **Step 1.2: Register the model**

Modify `models/__init__.py`. Add the import and the `__all__` entry alongside the others (alphabetical-ish ordering not enforced — match project style by adding after `ProductionLoss`):

```python
# at top, with the other imports
from .restock_request import RestockRequest
```

Add `"RestockRequest"` to the `__all__` list.

- [ ] **Step 1.3: Write the Pydantic schemas**

Create `schemas/restock.py`:

```python
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class RestockRequestCreate(BaseModel):
    part_id: str = Field(min_length=1)
    handcraft_order_id: Optional[str] = None
    source: Literal["picking", "manual"]
    note: Optional[str] = None


class RestockRequestPatch(BaseModel):
    status: Literal["done"]


class RestockRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    part_id: str
    handcraft_order_id: Optional[str]
    source: str
    status: str
    note: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]


class RestockSourceItem(BaseModel):
    request_id: int
    handcraft_order_id: str
    supplier_name: str
    created_at: datetime


class RestockSummaryItem(BaseModel):
    part_id: str
    part_name: str
    part_image: Optional[str] = None
    current_stock: float
    source_count: int
    sources: List[RestockSourceItem]


class RestockMarkPartDoneRequest(BaseModel):
    part_id: str = Field(min_length=1)


class RestockMarkPartDoneResponse(BaseModel):
    updated: int


class RestockHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    part_id: str
    part_name: str
    handcraft_order_id: Optional[str]
    supplier_name: Optional[str]
    source: str
    note: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
```

- [ ] **Step 1.4: Verify the model loads without error**

Run: `python -c "import models; print('ok')"`
Expected: `ok`

- [ ] **Step 1.5: Run the existing test suite to confirm nothing broke**

Run: `pytest tests/test_api_smoke.py -v`
Expected: PASS (no schema/migration errors).

- [ ] **Step 1.6: Commit**

```bash
git add models/restock_request.py models/__init__.py schemas/restock.py
git commit -m "feat(restock): add RestockRequest model and pydantic schemas"
```

---

## Task 2: services/restock.py — create_from_picking + create_manual

**Files:**
- Create: `services/restock.py`
- Create: `tests/test_services_restock.py`

- [ ] **Step 2.1: Write the failing test for create_from_picking (new request)**

Create `tests/test_services_restock.py`:

```python
import pytest

from models.handcraft_order import HandcraftOrder
from models.part import Part
from services.restock import create_from_picking, create_manual


def _seed_part(db, part_id="PJ-X-00001", name="小圆环", category="小配件"):
    p = Part(id=part_id, name=name, category=category)
    db.add(p)
    db.flush()
    return p


def _seed_handcraft(db, hc_id="HC-0001", supplier="王师傅"):
    o = HandcraftOrder(id=hc_id, supplier_name=supplier, status="pending")
    db.add(o)
    db.flush()
    return o


def test_create_from_picking_inserts_pending_with_picking_source(db):
    _seed_part(db)
    _seed_handcraft(db)

    rec = create_from_picking(db, part_id="PJ-X-00001", handcraft_order_id="HC-0001")

    assert rec.id is not None
    assert rec.part_id == "PJ-X-00001"
    assert rec.handcraft_order_id == "HC-0001"
    assert rec.source == "picking"
    assert rec.status == "pending"
    assert rec.completed_at is None
```

- [ ] **Step 2.2: Run it — fails because services/restock.py does not exist**

Run: `pytest tests/test_services_restock.py::test_create_from_picking_inserts_pending_with_picking_source -v`
Expected: FAIL (`ModuleNotFoundError: services.restock`)

- [ ] **Step 2.3: Write the minimal service**

Create `services/restock.py`:

```python
"""Restock request service. A pure 'todo list' for parts that need to be
restocked, scoped per handcraft order. No coupling to inventory_log or
purchase orders."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.handcraft_order import HandcraftOrder
from models.part import Part
from models.restock_request import RestockRequest
from time_utils import now_beijing


def _get_existing(db: Session, part_id: str, handcraft_order_id: Optional[str]) -> Optional[RestockRequest]:
    return (
        db.query(RestockRequest)
        .filter_by(part_id=part_id, handcraft_order_id=handcraft_order_id)
        .one_or_none()
    )


def _validate_part(db: Session, part_id: str) -> None:
    if db.query(Part).filter_by(id=part_id).one_or_none() is None:
        raise ValueError("配件不存在")


def _validate_handcraft(db: Session, hc_id: Optional[str]) -> None:
    if hc_id is None:
        return
    if db.query(HandcraftOrder).filter_by(id=hc_id).one_or_none() is None:
        raise ValueError("手工单不存在")


def _create(db: Session, *, part_id: str, handcraft_order_id: Optional[str], source: str, note: Optional[str]) -> RestockRequest:
    _validate_part(db, part_id)
    _validate_handcraft(db, handcraft_order_id)

    existing = _get_existing(db, part_id, handcraft_order_id)
    if existing is not None:
        if existing.status == "done":
            raise ValueError("该配件已为此手工单补过货")
        return existing

    rec = RestockRequest(
        part_id=part_id,
        handcraft_order_id=handcraft_order_id,
        source=source,
        status="pending",
        note=note,
    )
    db.add(rec)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = _get_existing(db, part_id, handcraft_order_id)
        if existing is None:
            raise
        if existing.status == "done":
            raise ValueError("该配件已为此手工单补过货")
        return existing
    return rec


def create_from_picking(db: Session, part_id: str, handcraft_order_id: str) -> RestockRequest:
    """Add a restock request from the picking modal. Idempotent: re-adding
    an already-pending pair returns the existing record. Already-done pair
    raises ValueError."""
    return _create(db, part_id=part_id, handcraft_order_id=handcraft_order_id,
                   source="picking", note=None)


def create_manual(db: Session, part_id: str, handcraft_order_id: str, note: Optional[str] = None) -> RestockRequest:
    """Add a manually-typed restock request (from the handcraft detail page).
    Idempotent like create_from_picking. Note is preserved on insert; for an
    already-pending pair the existing note is NOT overwritten."""
    return _create(db, part_id=part_id, handcraft_order_id=handcraft_order_id,
                   source="manual", note=note)
```

- [ ] **Step 2.4: Run the test — passes**

Run: `pytest tests/test_services_restock.py::test_create_from_picking_inserts_pending_with_picking_source -v`
Expected: PASS

- [ ] **Step 2.5: Add tests for idempotency, already-done, missing part/order, and create_manual**

Append to `tests/test_services_restock.py`:

```python
def test_create_from_picking_is_idempotent_for_pending(db):
    _seed_part(db)
    _seed_handcraft(db)

    rec1 = create_from_picking(db, "PJ-X-00001", "HC-0001")
    rec2 = create_from_picking(db, "PJ-X-00001", "HC-0001")

    assert rec1.id == rec2.id


def test_create_from_picking_raises_when_already_done(db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")
    rec.status = "done"
    db.flush()

    with pytest.raises(ValueError, match="已为此手工单补过货"):
        create_from_picking(db, "PJ-X-00001", "HC-0001")


def test_create_from_picking_raises_for_missing_part(db):
    _seed_handcraft(db)
    with pytest.raises(ValueError, match="配件不存在"):
        create_from_picking(db, "PJ-X-99999", "HC-0001")


def test_create_from_picking_raises_for_missing_handcraft(db):
    _seed_part(db)
    with pytest.raises(ValueError, match="手工单不存在"):
        create_from_picking(db, "PJ-X-00001", "HC-9999")


def test_create_manual_persists_note_and_source(db):
    _seed_part(db)
    _seed_handcraft(db)

    rec = create_manual(db, "PJ-X-00001", "HC-0001", note="实物找不到")

    assert rec.source == "manual"
    assert rec.note == "实物找不到"
    assert rec.status == "pending"


def test_create_manual_does_not_overwrite_existing_note(db):
    _seed_part(db)
    _seed_handcraft(db)
    create_manual(db, "PJ-X-00001", "HC-0001", note="第一次")

    rec = create_manual(db, "PJ-X-00001", "HC-0001", note="第二次")

    assert rec.note == "第一次"
```

- [ ] **Step 2.6: Run all tests for this task**

Run: `pytest tests/test_services_restock.py -v`
Expected: 6 PASS

- [ ] **Step 2.7: Commit**

```bash
git add services/restock.py tests/test_services_restock.py
git commit -m "feat(restock): create_from_picking and create_manual services"
```

---

## Task 3: services/restock.py — mark_done, mark_part_done, delete_pending

**Files:**
- Modify: `services/restock.py`
- Modify: `tests/test_services_restock.py`

- [ ] **Step 3.1: Write failing tests for mark_done**

Append to `tests/test_services_restock.py`:

```python
from services.restock import mark_done


def test_mark_done_transitions_pending_to_done(db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")

    updated = mark_done(db, rec.id)

    assert updated.status == "done"
    assert updated.completed_at is not None


def test_mark_done_raises_when_already_done(db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")
    mark_done(db, rec.id)

    with pytest.raises(ValueError, match="已完成"):
        mark_done(db, rec.id)


def test_mark_done_raises_for_unknown_id(db):
    with pytest.raises(ValueError, match="补货记录不存在"):
        mark_done(db, 99999)
```

- [ ] **Step 3.2: Implement mark_done**

Append to `services/restock.py`:

```python
def mark_done(db: Session, request_id: int) -> RestockRequest:
    """pending -> done. Raises ValueError if record does not exist or
    is already done. Single-direction transition."""
    rec = db.query(RestockRequest).filter_by(id=request_id).one_or_none()
    if rec is None:
        raise ValueError("补货记录不存在")
    if rec.status == "done":
        raise ValueError("补货记录已完成，不可重置")
    rec.status = "done"
    rec.completed_at = now_beijing()
    db.flush()
    return rec
```

- [ ] **Step 3.3: Run mark_done tests**

Run: `pytest tests/test_services_restock.py -k mark_done -v`
Expected: 3 PASS

- [ ] **Step 3.4: Write failing tests for mark_part_done**

Append to `tests/test_services_restock.py`:

```python
from services.restock import mark_part_done


def test_mark_part_done_updates_only_pending_for_that_part(db):
    _seed_part(db, "PJ-X-00001")
    _seed_part(db, "PJ-X-00002")
    _seed_handcraft(db, "HC-0001")
    _seed_handcraft(db, "HC-0002")

    a = create_from_picking(db, "PJ-X-00001", "HC-0001")
    b = create_from_picking(db, "PJ-X-00001", "HC-0002")
    other = create_from_picking(db, "PJ-X-00002", "HC-0001")
    # mark `other` done so it is excluded from the update
    mark_done(db, other.id)
    # also pre-mark one of the same-part records done — should NOT be touched
    pre_done = create_from_picking(db, "PJ-X-00001", "HC-0001")  # idempotent, returns a
    assert pre_done.id == a.id

    count = mark_part_done(db, "PJ-X-00001")
    db.refresh(a)
    db.refresh(b)
    db.refresh(other)

    assert count == 2
    assert a.status == "done" and a.completed_at is not None
    assert b.status == "done" and b.completed_at is not None
    assert other.status == "done"  # was already done, untouched but still done


def test_mark_part_done_returns_zero_when_no_pending(db):
    _seed_part(db, "PJ-X-00001")

    count = mark_part_done(db, "PJ-X-00001")

    assert count == 0
```

- [ ] **Step 3.5: Implement mark_part_done**

Append to `services/restock.py`:

```python
def mark_part_done(db: Session, part_id: str) -> int:
    """Bulk-transition all pending restock requests for `part_id` to done.
    Returns the number of rows updated. No-op if no pending exists."""
    now = now_beijing()
    count = (
        db.query(RestockRequest)
        .filter(RestockRequest.part_id == part_id, RestockRequest.status == "pending")
        .update({"status": "done", "completed_at": now}, synchronize_session=False)
    )
    db.flush()
    return count
```

- [ ] **Step 3.6: Run mark_part_done tests**

Run: `pytest tests/test_services_restock.py -k mark_part_done -v`
Expected: 2 PASS

- [ ] **Step 3.7: Write failing tests for delete_pending**

Append to `tests/test_services_restock.py`:

```python
from services.restock import delete_pending


def test_delete_pending_removes_pending_record(db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")

    delete_pending(db, rec.id)

    from models.restock_request import RestockRequest as R
    assert db.query(R).filter_by(id=rec.id).one_or_none() is None


def test_delete_pending_raises_when_done(db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")
    mark_done(db, rec.id)

    with pytest.raises(ValueError, match="已补货的记录不可删除"):
        delete_pending(db, rec.id)


def test_delete_pending_raises_for_unknown_id(db):
    with pytest.raises(ValueError, match="补货记录不存在"):
        delete_pending(db, 99999)
```

- [ ] **Step 3.8: Implement delete_pending**

Append to `services/restock.py`:

```python
def delete_pending(db: Session, request_id: int) -> None:
    """Cancel a pending restock request. Done records cannot be deleted
    via this path (they are kept as history). Raises ValueError otherwise."""
    rec = db.query(RestockRequest).filter_by(id=request_id).one_or_none()
    if rec is None:
        raise ValueError("补货记录不存在")
    if rec.status == "done":
        raise ValueError("已补货的记录不可删除")
    db.delete(rec)
    db.flush()
```

- [ ] **Step 3.9: Run all task 3 tests**

Run: `pytest tests/test_services_restock.py -v`
Expected: 11 PASS (6 from task 2 + 5 new)

- [ ] **Step 3.10: Commit**

```bash
git add services/restock.py tests/test_services_restock.py
git commit -m "feat(restock): mark_done / mark_part_done / delete_pending services"
```

---

## Task 4: services/restock.py — list queries (handcraft / summary / history)

**Files:**
- Modify: `services/restock.py`
- Modify: `tests/test_services_restock.py`

- [ ] **Step 4.1: Write failing test for list_for_handcraft**

Append to `tests/test_services_restock.py`:

```python
from services.restock import list_for_handcraft


def test_list_for_handcraft_returns_pending_and_done_newest_first(db):
    _seed_part(db, "PJ-X-00001")
    _seed_part(db, "PJ-X-00002")
    _seed_handcraft(db)

    rec1 = create_from_picking(db, "PJ-X-00001", "HC-0001")
    rec2 = create_manual(db, "PJ-X-00002", "HC-0001", note="实物找不到")
    mark_done(db, rec1.id)

    rows = list_for_handcraft(db, "HC-0001")

    assert len(rows) == 2
    assert {r.id for r in rows} == {rec1.id, rec2.id}


def test_list_for_handcraft_excludes_other_orders(db):
    _seed_part(db)
    _seed_handcraft(db, "HC-0001")
    _seed_handcraft(db, "HC-0002")
    create_from_picking(db, "PJ-X-00001", "HC-0001")
    create_from_picking(db, "PJ-X-00001", "HC-0002")

    rows = list_for_handcraft(db, "HC-0001")
    assert len(rows) == 1
    assert rows[0].handcraft_order_id == "HC-0001"
```

- [ ] **Step 4.2: Implement list_for_handcraft**

Append to `services/restock.py`:

```python
def list_for_handcraft(db: Session, handcraft_order_id: str) -> list[RestockRequest]:
    """All restock requests (pending + done) for a single handcraft order,
    newest first."""
    return (
        db.query(RestockRequest)
        .filter_by(handcraft_order_id=handcraft_order_id)
        .order_by(RestockRequest.created_at.desc(), RestockRequest.id.desc())
        .all()
    )
```

- [ ] **Step 4.3: Run those tests**

Run: `pytest tests/test_services_restock.py -k list_for_handcraft -v`
Expected: 2 PASS

- [ ] **Step 4.4: Write failing test for list_pending_summary**

Append to `tests/test_services_restock.py`:

```python
from services.restock import list_pending_summary
from services.inventory import add_stock


def test_list_pending_summary_aggregates_by_part(db):
    _seed_part(db, "PJ-X-00001", name="小圆环")
    _seed_part(db, "PJ-X-00002", name="银扣头")
    _seed_handcraft(db, "HC-0001", supplier="王师傅")
    _seed_handcraft(db, "HC-0002", supplier="李姐")

    add_stock(db, "part", "PJ-X-00001", 5.0, "测试入库")

    create_from_picking(db, "PJ-X-00001", "HC-0001")
    create_from_picking(db, "PJ-X-00001", "HC-0002")
    create_from_picking(db, "PJ-X-00002", "HC-0001")

    summary = list_pending_summary(db)
    summary_by_part = {row["part_id"]: row for row in summary}

    assert set(summary_by_part) == {"PJ-X-00001", "PJ-X-00002"}
    a = summary_by_part["PJ-X-00001"]
    assert a["part_name"] == "小圆环"
    assert a["current_stock"] == 5.0
    assert a["source_count"] == 2
    assert {s["handcraft_order_id"] for s in a["sources"]} == {"HC-0001", "HC-0002"}
    assert {s["supplier_name"] for s in a["sources"]} == {"王师傅", "李姐"}


def test_list_pending_summary_excludes_done(db):
    _seed_part(db, "PJ-X-00001")
    _seed_handcraft(db, "HC-0001")
    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")
    mark_done(db, rec.id)

    summary = list_pending_summary(db)
    assert summary == []
```

- [ ] **Step 4.5: Implement list_pending_summary**

Append to `services/restock.py`:

```python
from collections import defaultdict

from sqlalchemy import func

from models.inventory_log import InventoryLog


def list_pending_summary(db: Session) -> list[dict]:
    """Aggregate pending restock requests by part. Each row carries
    the part metadata, current stock, source handcraft orders, and count."""
    rows = (
        db.query(
            RestockRequest.id,
            RestockRequest.part_id,
            RestockRequest.handcraft_order_id,
            RestockRequest.created_at,
            Part.name,
            Part.image,
            HandcraftOrder.supplier_name,
        )
        .join(Part, Part.id == RestockRequest.part_id)
        .outerjoin(HandcraftOrder, HandcraftOrder.id == RestockRequest.handcraft_order_id)
        .filter(RestockRequest.status == "pending")
        .order_by(RestockRequest.created_at.asc())
        .all()
    )
    if not rows:
        return []

    part_ids = sorted({r.part_id for r in rows})
    stock_rows = (
        db.query(InventoryLog.item_id, func.coalesce(func.sum(InventoryLog.change_qty), 0))
        .filter(InventoryLog.item_type == "part", InventoryLog.item_id.in_(part_ids))
        .group_by(InventoryLog.item_id)
        .all()
    )
    stock_by_part = {pid: float(qty) for pid, qty in stock_rows}

    by_part: dict[str, dict] = {}
    for r in rows:
        bucket = by_part.setdefault(r.part_id, {
            "part_id": r.part_id,
            "part_name": r.name,
            "part_image": r.image,
            "current_stock": stock_by_part.get(r.part_id, 0.0),
            "sources": [],
        })
        bucket["sources"].append({
            "request_id": r.id,
            "handcraft_order_id": r.handcraft_order_id,
            "supplier_name": r.supplier_name or "",
            "created_at": r.created_at,
        })

    out = []
    for part_id in part_ids:
        bucket = by_part[part_id]
        bucket["source_count"] = len(bucket["sources"])
        out.append(bucket)
    return out
```

- [ ] **Step 4.6: Run summary tests**

Run: `pytest tests/test_services_restock.py -k list_pending_summary -v`
Expected: 2 PASS

- [ ] **Step 4.7: Write failing test for list_history**

Append to `tests/test_services_restock.py`:

```python
from services.restock import list_history


def test_list_history_returns_done_records_with_part_and_supplier(db):
    _seed_part(db, "PJ-X-00001", name="小圆环")
    _seed_handcraft(db, "HC-0001", supplier="王师傅")

    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")
    mark_done(db, rec.id)
    create_from_picking(db, "PJ-X-00001", "HC-0001")  # try (already done -> raises)
    # but a new pending should not appear in history
    _seed_part(db, "PJ-X-00002")
    create_from_picking(db, "PJ-X-00002", "HC-0001")

    rows = list_history(db)

    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == rec.id
    assert row["part_id"] == "PJ-X-00001"
    assert row["part_name"] == "小圆环"
    assert row["handcraft_order_id"] == "HC-0001"
    assert row["supplier_name"] == "王师傅"
    assert row["completed_at"] is not None
```

The test references the unique-key conflict — a follow-up `create_from_picking` call on an already-done pair raises. Wrap that line:

Replace the test body with this corrected version:

```python
def test_list_history_returns_done_records_with_part_and_supplier(db):
    _seed_part(db, "PJ-X-00001", name="小圆环")
    _seed_part(db, "PJ-X-00002")
    _seed_handcraft(db, "HC-0001", supplier="王师傅")

    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")
    mark_done(db, rec.id)
    # an unrelated pending record — should NOT appear in history
    create_from_picking(db, "PJ-X-00002", "HC-0001")

    rows = list_history(db)

    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == rec.id
    assert row["part_id"] == "PJ-X-00001"
    assert row["part_name"] == "小圆环"
    assert row["handcraft_order_id"] == "HC-0001"
    assert row["supplier_name"] == "王师傅"
    assert row["completed_at"] is not None


def test_list_history_filter_by_part_and_handcraft(db):
    _seed_part(db, "PJ-X-00001")
    _seed_part(db, "PJ-X-00002")
    _seed_handcraft(db, "HC-0001")
    _seed_handcraft(db, "HC-0002")

    a = create_from_picking(db, "PJ-X-00001", "HC-0001"); mark_done(db, a.id)
    b = create_from_picking(db, "PJ-X-00002", "HC-0001"); mark_done(db, b.id)
    c = create_from_picking(db, "PJ-X-00001", "HC-0002"); mark_done(db, c.id)

    rows = list_history(db, part_id="PJ-X-00001")
    assert {r["id"] for r in rows} == {a.id, c.id}

    rows = list_history(db, handcraft_order_id="HC-0001")
    assert {r["id"] for r in rows} == {a.id, b.id}
```

- [ ] **Step 4.8: Implement list_history**

Append to `services/restock.py`:

```python
def list_history(
    db: Session,
    part_id: Optional[str] = None,
    handcraft_order_id: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """List done restock requests, newest completion first. Optional filters
    by part / handcraft order. limit caps result size."""
    q = (
        db.query(
            RestockRequest.id,
            RestockRequest.part_id,
            RestockRequest.handcraft_order_id,
            RestockRequest.source,
            RestockRequest.note,
            RestockRequest.created_at,
            RestockRequest.completed_at,
            Part.name.label("part_name"),
            HandcraftOrder.supplier_name,
        )
        .join(Part, Part.id == RestockRequest.part_id)
        .outerjoin(HandcraftOrder, HandcraftOrder.id == RestockRequest.handcraft_order_id)
        .filter(RestockRequest.status == "done")
    )
    if part_id:
        q = q.filter(RestockRequest.part_id == part_id)
    if handcraft_order_id:
        q = q.filter(RestockRequest.handcraft_order_id == handcraft_order_id)
    q = q.order_by(RestockRequest.completed_at.desc(), RestockRequest.id.desc()).limit(limit)

    return [
        {
            "id": r.id,
            "part_id": r.part_id,
            "part_name": r.part_name,
            "handcraft_order_id": r.handcraft_order_id,
            "supplier_name": r.supplier_name,
            "source": r.source,
            "note": r.note,
            "created_at": r.created_at,
            "completed_at": r.completed_at,
        }
        for r in q.all()
    ]
```

- [ ] **Step 4.9: Run all task 4 tests**

Run: `pytest tests/test_services_restock.py -v`
Expected: 15 PASS (11 prior + 4 new)

- [ ] **Step 4.10: Commit**

```bash
git add services/restock.py tests/test_services_restock.py
git commit -m "feat(restock): list_for_handcraft / list_pending_summary / list_history queries"
```

---

## Task 5: API router + tests

**Files:**
- Create: `api/restock.py`
- Modify: `main.py`
- Create: `tests/test_api_restock.py`

- [ ] **Step 5.1: Write failing test for POST endpoint**

Create `tests/test_api_restock.py`:

```python
from models.handcraft_order import HandcraftOrder
from models.part import Part


def _seed_part(db, part_id="PJ-X-00001", name="小圆环"):
    db.add(Part(id=part_id, name=name, category="小配件"))
    db.flush()


def _seed_handcraft(db, hc_id="HC-0001", supplier="王师傅"):
    db.add(HandcraftOrder(id=hc_id, supplier_name=supplier, status="pending"))
    db.flush()


def test_post_restock_request_creates_pending(client, db):
    _seed_part(db)
    _seed_handcraft(db)

    resp = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001",
        "handcraft_order_id": "HC-0001",
        "source": "picking",
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["source"] == "picking"
    assert body["part_id"] == "PJ-X-00001"
    assert body["handcraft_order_id"] == "HC-0001"
```

- [ ] **Step 5.2: Run it — fails (router not registered)**

Run: `pytest tests/test_api_restock.py::test_post_restock_request_creates_pending -v`
Expected: FAIL (404)

- [ ] **Step 5.3: Implement the router**

Create `api/restock.py`:

```python
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.restock import (
    RestockHistoryItem,
    RestockMarkPartDoneRequest,
    RestockMarkPartDoneResponse,
    RestockRequestCreate,
    RestockRequestPatch,
    RestockRequestRead,
    RestockSummaryItem,
)
from services.restock import (
    create_from_picking,
    create_manual,
    delete_pending,
    list_history,
    list_pending_summary,
    mark_done,
    mark_part_done,
)

router = APIRouter(prefix="/api/restock-requests", tags=["restock"])


@router.post("", response_model=RestockRequestRead)
def api_create_restock(payload: RestockRequestCreate, db: Session = Depends(get_db)):
    if payload.handcraft_order_id is None:
        # First version: handcraft_order_id is required from the UI even though
        # the schema permits null (reserved for future use).
        with service_errors():
            raise ValueError("handcraft_order_id 不能为空")
    with service_errors():
        if payload.source == "picking":
            return create_from_picking(db, payload.part_id, payload.handcraft_order_id)
        return create_manual(db, payload.part_id, payload.handcraft_order_id, payload.note)


@router.patch("/{request_id}", response_model=RestockRequestRead)
def api_mark_done(request_id: int, payload: RestockRequestPatch, db: Session = Depends(get_db)):
    # The schema fixes status to literal "done" so we don't need to branch.
    with service_errors():
        return mark_done(db, request_id)


@router.delete("/{request_id}", status_code=204)
def api_delete_pending(request_id: int, db: Session = Depends(get_db)):
    with service_errors():
        delete_pending(db, request_id)


@router.post("/mark-part-done", response_model=RestockMarkPartDoneResponse)
def api_mark_part_done(payload: RestockMarkPartDoneRequest, db: Session = Depends(get_db)):
    with service_errors():
        count = mark_part_done(db, payload.part_id)
    return RestockMarkPartDoneResponse(updated=count)


@router.get("/summary", response_model=list[RestockSummaryItem])
def api_list_summary(db: Session = Depends(get_db)):
    return list_pending_summary(db)


@router.get("/history", response_model=list[RestockHistoryItem])
def api_list_history(
    part_id: Optional[str] = None,
    handcraft_order_id: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    return list_history(db, part_id=part_id, handcraft_order_id=handcraft_order_id, limit=limit)
```

- [ ] **Step 5.4: Register the router in main.py**

Modify `main.py`. Add the import alongside the others (after `from api.plating_summary import router as plating_summary_router`):

```python
from api.restock import router as restock_router
```

Then add the include line near the other routers (under `handcraft_router`):

```python
app.include_router(restock_router, dependencies=[require_permission("handcraft")])
```

- [ ] **Step 5.5: Run the POST test**

Run: `pytest tests/test_api_restock.py::test_post_restock_request_creates_pending -v`
Expected: PASS

- [ ] **Step 5.6: Add tests for the rest of the endpoints**

Append to `tests/test_api_restock.py`:

```python
def test_post_restock_idempotent(client, db):
    _seed_part(db)
    _seed_handcraft(db)
    payload = {"part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking"}

    r1 = client.post("/api/restock-requests", json=payload).json()
    r2 = client.post("/api/restock-requests", json=payload).json()

    assert r1["id"] == r2["id"]


def test_post_restock_already_done_returns_400(client, db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    }).json()
    client.patch(f"/api/restock-requests/{rec['id']}", json={"status": "done"})

    resp = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    })
    assert resp.status_code == 400
    assert "已为此手工单补过货" in resp.json()["detail"]


def test_post_restock_manual_persists_note(client, db):
    _seed_part(db)
    _seed_handcraft(db)
    resp = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001",
        "source": "manual", "note": "实物找不到",
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "manual"
    assert body["note"] == "实物找不到"


def test_patch_marks_done_and_404_for_unknown(client, db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    }).json()

    resp = client.patch(f"/api/restock-requests/{rec['id']}", json={"status": "done"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"
    assert resp.json()["completed_at"] is not None

    again = client.patch(f"/api/restock-requests/{rec['id']}", json={"status": "done"})
    assert again.status_code == 400


def test_delete_only_works_on_pending(client, db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    }).json()

    resp = client.delete(f"/api/restock-requests/{rec['id']}")
    assert resp.status_code == 204

    rec2 = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    }).json()
    client.patch(f"/api/restock-requests/{rec2['id']}", json={"status": "done"})
    resp = client.delete(f"/api/restock-requests/{rec2['id']}")
    assert resp.status_code == 400
    assert "已补货" in resp.json()["detail"]


def test_mark_part_done_endpoint(client, db):
    _seed_part(db, "PJ-X-00001")
    _seed_handcraft(db, "HC-0001")
    _seed_handcraft(db, "HC-0002")
    client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    })
    client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0002", "source": "picking",
    })

    resp = client.post("/api/restock-requests/mark-part-done", json={"part_id": "PJ-X-00001"})
    assert resp.status_code == 200
    assert resp.json() == {"updated": 2}


def test_summary_endpoint_aggregates_by_part(client, db):
    _seed_part(db, "PJ-X-00001", name="小圆环")
    _seed_part(db, "PJ-X-00002", name="银扣头")
    _seed_handcraft(db, "HC-0001")
    _seed_handcraft(db, "HC-0002")
    client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    })
    client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0002", "source": "picking",
    })
    client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00002", "handcraft_order_id": "HC-0001", "source": "picking",
    })

    body = client.get("/api/restock-requests/summary").json()
    by_part = {row["part_id"]: row for row in body}
    assert by_part["PJ-X-00001"]["source_count"] == 2
    assert by_part["PJ-X-00002"]["source_count"] == 1


def test_history_endpoint_lists_done(client, db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    }).json()
    client.patch(f"/api/restock-requests/{rec['id']}", json={"status": "done"})

    body = client.get("/api/restock-requests/history").json()
    assert len(body) == 1
    assert body[0]["id"] == rec["id"]
    assert body[0]["completed_at"] is not None
```

- [ ] **Step 5.7: Run all API tests**

Run: `pytest tests/test_api_restock.py -v`
Expected: 9 PASS

- [ ] **Step 5.8: Commit**

```bash
git add api/restock.py main.py tests/test_api_restock.py
git commit -m "feat(restock): /api/restock-requests router and endpoints"
```

---

## Task 6: handcraft order delete cascade

**Files:**
- Modify: `services/handcraft.py`
- Modify: `tests/test_api_handcraft.py` (or write a service-layer test)

- [ ] **Step 6.1: Write a failing cascade test**

Append to `tests/test_services_restock.py`:

```python
from services.handcraft import delete_handcraft_order


def test_delete_handcraft_order_cascades_restock_requests(db):
    _seed_part(db, "PJ-X-00001")
    _seed_handcraft(db, "HC-0001")
    rec_pending = create_from_picking(db, "PJ-X-00001", "HC-0001")

    _seed_part(db, "PJ-X-00002")
    rec_done = create_manual(db, "PJ-X-00002", "HC-0001")
    mark_done(db, rec_done.id)

    delete_handcraft_order(db, "HC-0001")

    from models.restock_request import RestockRequest as R
    remaining = db.query(R).filter_by(handcraft_order_id="HC-0001").all()
    assert remaining == []
```

- [ ] **Step 6.2: Run it — fails (cascade not implemented)**

Run: `pytest tests/test_services_restock.py::test_delete_handcraft_order_cascades_restock_requests -v`
Expected: FAIL (likely an `IntegrityError` from FK constraint, or remaining rows assertion)

- [ ] **Step 6.3: Add the cascade**

Modify `services/handcraft.py`. Find `delete_handcraft_order` (line 536) and locate the existing block that deletes `HandcraftPickingRecord` (around line 609). Add a new block immediately above it:

```python
    from models.restock_request import RestockRequest
    db.query(RestockRequest).filter(
        RestockRequest.handcraft_order_id == order_id
    ).delete(synchronize_session=False)
    db.flush()
```

The result should look like:

```python
    from models.restock_request import RestockRequest
    db.query(RestockRequest).filter(
        RestockRequest.handcraft_order_id == order_id
    ).delete(synchronize_session=False)
    db.flush()

    db.query(HandcraftPickingRecord).filter(
        HandcraftPickingRecord.handcraft_order_id == order_id
    ).delete(synchronize_session=False)
    db.flush()
```

- [ ] **Step 6.4: Run the cascade test**

Run: `pytest tests/test_services_restock.py::test_delete_handcraft_order_cascades_restock_requests -v`
Expected: PASS

- [ ] **Step 6.5: Run the full restock test file to confirm nothing else broke**

Run: `pytest tests/test_services_restock.py tests/test_api_restock.py tests/test_api_handcraft.py -v`
Expected: all PASS

- [ ] **Step 6.6: Commit**

```bash
git add services/handcraft.py tests/test_services_restock.py
git commit -m "feat(restock): cascade delete restock requests on handcraft order delete"
```

---

## Task 7: extend handcraft picking response with restock_status

**Files:**
- Modify: `schemas/handcraft.py` (HandcraftPickingVariant)
- Modify: `services/handcraft_picking.py`
- Modify: `tests/test_api_handcraft_picking.py`

- [ ] **Step 7.1: Write a failing test asserting the new fields appear**

Append to `tests/test_api_handcraft_picking.py` a fresh test (use the existing seed helpers in that file as a guide; below assumes the file already has fixtures for creating a handcraft order with a part item):

```python
def test_picking_simulation_exposes_restock_status_on_each_row(client, db):
    # Reuse whatever existing helper sets up a handcraft order with one
    # atomic part_item. Adjust the helper name to whatever the file uses.
    from models.part import Part
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem
    from models.restock_request import RestockRequest

    db.add(Part(id="PJ-X-00001", name="小圆环", category="小配件"))
    db.add(HandcraftOrder(id="HC-0001", supplier_name="王", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-0001", part_id="PJ-X-00001", qty=1))
    db.flush()

    body = client.get("/api/handcraft/HC-0001/picking-simulation").json()
    row = body["groups"][0]["rows"][0]
    assert row["restock_status"] is None
    assert row["restock_request_id"] is None

    db.add(RestockRequest(part_id="PJ-X-00001", handcraft_order_id="HC-0001",
                          source="picking", status="pending"))
    db.flush()

    body = client.get("/api/handcraft/HC-0001/picking-simulation").json()
    row = body["groups"][0]["rows"][0]
    assert row["restock_status"] == "pending"
    assert row["restock_request_id"] is not None
```

- [ ] **Step 7.2: Run it — fails (fields missing on response)**

Run: `pytest tests/test_api_handcraft_picking.py::test_picking_simulation_exposes_restock_status_on_each_row -v`
Expected: FAIL (`KeyError`, missing field, or attribute access error)

- [ ] **Step 7.3: Add fields to the schema**

Modify `schemas/handcraft.py`. Find `class HandcraftPickingVariant(BaseModel):` (line 130) and add two fields after `picked: bool`:

```python
    picked: bool
    restock_status: Optional[str] = None  # None | "pending" | "done"
    restock_request_id: Optional[int] = None
```

- [ ] **Step 7.4: Embed the data in the service**

Modify `services/handcraft_picking.py`. Find `get_handcraft_picking_simulation` (line 58) and after `picked_keys = _load_picked_keys(...)` add a parallel loader:

```python
    restock_by_part = _load_restock_by_part(db, handcraft_order_id, atom_ids)
```

Add the helper function near the bottom of the file (next to `_load_picked_keys`):

```python
def _load_restock_by_part(
    db: Session, handcraft_order_id: str, part_ids: list[str]
) -> dict[str, tuple[str, int]]:
    """Map part_id -> (status, request_id) for any restock_request rows that
    reference this handcraft order. None entries are simply absent from the dict."""
    if not part_ids:
        return {}
    from models.restock_request import RestockRequest
    rows = (
        db.query(RestockRequest.part_id, RestockRequest.status, RestockRequest.id)
        .filter(
            RestockRequest.handcraft_order_id == handcraft_order_id,
            RestockRequest.part_id.in_(part_ids),
        )
        .all()
    )
    return {pid: (status, rid) for pid, status, rid in rows}
```

In the row construction loop (where `HandcraftPickingVariant(...)` is built), add the two fields:

```python
            restock = restock_by_part.get(atom_id)
            rows.append(HandcraftPickingVariant(
                part_id=atom_id,
                part_name=atom_part.name,
                part_image=atom_part.image,
                size_tier=atom_part.size_tier or "small",
                needed_qty=needed_qty,
                suggested_qty=suggested,
                current_stock=stock_by_part.get(atom_id, 0.0),
                picked=is_picked,
                restock_status=restock[0] if restock else None,
                restock_request_id=restock[1] if restock else None,
            ))
```

- [ ] **Step 7.5: Run the picking test**

Run: `pytest tests/test_api_handcraft_picking.py::test_picking_simulation_exposes_restock_status_on_each_row -v`
Expected: PASS

- [ ] **Step 7.6: Run the full picking test suite**

Run: `pytest tests/test_api_handcraft_picking.py -v`
Expected: all PASS (no regressions)

- [ ] **Step 7.7: Commit**

```bash
git add schemas/handcraft.py services/handcraft_picking.py tests/test_api_handcraft_picking.py
git commit -m "feat(restock): expose restock_status on handcraft picking variants"
```

---

## Task 8: add `GET /api/handcraft/{order_id}/restock-requests`

**Files:**
- Modify: `api/handcraft.py`
- Create: schema response is already `RestockRequestRead` from task 1
- Modify: `tests/test_api_restock.py`

- [ ] **Step 8.1: Write a failing test**

Append to `tests/test_api_restock.py`:

```python
def test_list_restock_for_handcraft_endpoint(client, db):
    _seed_part(db, "PJ-X-00001")
    _seed_part(db, "PJ-X-00002")
    _seed_handcraft(db, "HC-0001")
    _seed_handcraft(db, "HC-0002")

    client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    })
    client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00002", "handcraft_order_id": "HC-0001", "source": "manual", "note": "x",
    })
    client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0002", "source": "picking",
    })

    body = client.get("/api/handcraft/HC-0001/restock-requests").json()
    assert len(body) == 2
    assert {r["part_id"] for r in body} == {"PJ-X-00001", "PJ-X-00002"}
    for row in body:
        assert row["handcraft_order_id"] == "HC-0001"
```

- [ ] **Step 8.2: Run it — fails (404)**

Run: `pytest tests/test_api_restock.py::test_list_restock_for_handcraft_endpoint -v`
Expected: FAIL (404)

- [ ] **Step 8.3: Add the endpoint**

Modify `api/handcraft.py`. At the top imports, add:

```python
from schemas.restock import RestockRequestRead
from services.restock import list_for_handcraft
```

Then add a new endpoint near the existing `GET /{order_id}` (after the line that defines `api_get_handcraft`, around line 148):

```python
@router.get("/{order_id}/restock-requests", response_model=list[RestockRequestRead])
def api_list_handcraft_restock_requests(order_id: str, db: Session = Depends(get_db)):
    return list_for_handcraft(db, order_id)
```

- [ ] **Step 8.4: Run the test**

Run: `pytest tests/test_api_restock.py::test_list_restock_for_handcraft_endpoint -v`
Expected: PASS

- [ ] **Step 8.5: Commit**

```bash
git add api/handcraft.py tests/test_api_restock.py
git commit -m "feat(restock): GET /api/handcraft/{id}/restock-requests endpoint"
```

---

## Task 9: frontend API client

**Files:**
- Create: `frontend/src/api/restock.js`

- [ ] **Step 9.1: Write the API client**

Create `frontend/src/api/restock.js`:

```javascript
import http from './index'

export const listRestockSummary = () =>
  http.get('/restock-requests/summary')

export const listRestockHistory = (params) =>
  http.get('/restock-requests/history', { params })

export const listHandcraftRestock = (handcraftOrderId) =>
  http.get(`/handcraft/${encodeURIComponent(handcraftOrderId)}/restock-requests`)

export const createRestock = (payload) =>
  http.post('/restock-requests', payload)

export const markRestockDone = (id) =>
  http.patch(`/restock-requests/${id}`, { status: 'done' })

export const deleteRestock = (id) =>
  http.delete(`/restock-requests/${id}`)

export const markPartRestockDone = (partId) =>
  http.post('/restock-requests/mark-part-done', { part_id: partId })
```

- [ ] **Step 9.2: Smoke-check via build**

Run: `cd frontend && npm run build`
Expected: build succeeds (validates the file parses and imports resolve).

- [ ] **Step 9.3: Commit**

```bash
git add frontend/src/api/restock.js
git commit -m "feat(restock): frontend API client"
```

---

## Task 10: add the「需补货」column to the picking modal

**Files:**
- Modify: `frontend/src/components/picking/HandcraftPickingSimulationModal.vue`

The modal currently has columns: 配件ID / 配件 / 需求量 / 建议量 / 当前库存 / 已选择. Add 需补货 as the last column. Render based on row state.

- [ ] **Step 10.1: Add the new column header**

Modify `HandcraftPickingSimulationModal.vue`. Find the `<thead>` block (search for "已选择" — it's a `<th>` near line 230 or so). Add a new `<th>` immediately after the 已选择 column header:

```html
<th class="th-restock">需补货</th>
```

(Match styling of the surrounding `<th>` cells.)

- [ ] **Step 10.2: Add the new column body cell**

Find the `<tr v-for="r in g.rows"` block (around line 211). After the 已选择 `<td>` (`<td class="num"><n-checkbox ...></n-checkbox></td>`), add a new `<td>` rendering one of three states:

```html
<td class="num restock-cell">
  <span
    v-if="r.restock_status === 'done'"
    class="restock-tag restock-done"
    title="已补过"
  >✓ 已补过</span>
  <n-checkbox
    v-else
    :checked="r.restock_status === 'pending'"
    :disabled="readonly || r.current_stock >= r.needed_qty"
    @update:checked="(v) => toggleRestock(g, r, v)"
  />
  <div
    v-if="r.restock_status === 'pending'"
    class="restock-hint pending"
  >⏳ 待补货</div>
  <div
    v-else-if="r.restock_status !== 'done' && r.current_stock < r.needed_qty"
    class="restock-hint"
  >未标记</div>
  <div
    v-else-if="r.restock_status !== 'done'"
    class="restock-hint dim"
  >库存充足</div>
</td>
```

- [ ] **Step 10.3: Wire the toggleRestock handler**

In the `<script setup>` block, add the handler near the existing `toggleRow` function (search for `function toggleRow`):

```javascript
import { createRestock, deleteRestock } from '@/api/restock'

async function toggleRestock(group, row, value) {
  if (props.readonly) return
  try {
    if (value) {
      const { data } = await createRestock({
        part_id: row.part_id,
        handcraft_order_id: props.handcraftOrderId,
        source: 'picking',
      })
      row.restock_status = data.status
      row.restock_request_id = data.id
    } else {
      if (!row.restock_request_id) return
      await deleteRestock(row.restock_request_id)
      row.restock_status = null
      row.restock_request_id = null
    }
  } catch (err) {
    const detail = err?.response?.data?.detail
    window.$message?.error(detail || '操作失败')
    // Reload picking data so the UI reflects server state
    refresh && refresh()
  }
}
```

(If the component already has a `refresh()` function, call it on error; if not, set `row.restock_status` back to its previous value.)

- [ ] **Step 10.4: Add CSS**

Append to the `<style scoped>` block of the modal:

```css
.restock-cell {
  background: #fff8e1;
  text-align: center;
}
.restock-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
}
.restock-done {
  background: #4caf50;
  color: #fff;
}
.restock-hint {
  font-size: 11px;
  color: #999;
  margin-top: 2px;
}
.restock-hint.pending {
  color: #f57c00;
  font-weight: 500;
}
.restock-hint.dim {
  color: #bbb;
}
```

- [ ] **Step 10.5: Smoke-check via dev build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 10.6: Manual UI test**

Start dev server (`cd frontend && npm run dev` in another terminal; backend `python main.py`). Open a `pending` handcraft order, open 配货模拟. Verify:
- Each row shows a 需补货 column.
- Stock-low rows show an enabled checkbox + "未标记".
- Stock-sufficient rows show a disabled checkbox + "库存充足".
- Click a checkbox; the row re-renders to "⏳ 待补货".
- Uncheck; reverts to "未标记".

- [ ] **Step 10.7: Commit**

```bash
git add frontend/src/components/picking/HandcraftPickingSimulationModal.vue
git commit -m "feat(restock): 配货模拟弹窗 add 需补货 column"
```

---

## Task 11: handcraft detail — restock card with manual add

**Files:**
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue`

- [ ] **Step 11.1: Add the card markup at the bottom of the detail page**

Find the closing `</n-spin>` near the bottom of the template (after the existing detail cards). Insert before it a new card:

```html
<n-card v-if="order" title="补货清单" style="margin-top: 16px;">
  <template #header-extra>
    <n-space size="small">
      <n-tag size="small" type="warning" :bordered="false">
        待补 {{ pendingRestockCount }}
      </n-tag>
      <n-tag size="small" type="default" :bordered="false">
        已补 {{ doneRestockCount }}
      </n-tag>
      <n-button size="small" type="primary" @click="openManualRestockModal">+ 手动添加</n-button>
    </n-space>
  </template>
  <n-data-table
    :columns="restockColumns"
    :data="restockRows"
    :loading="restockLoading"
    :bordered="false"
    size="small"
    :row-class-name="restockRowClass"
  />
</n-card>

<n-modal v-model:show="manualRestockShow" preset="card" title="手动添加补货项" style="max-width: 480px;">
  <n-form>
    <n-form-item label="配件" required>
      <n-select
        v-model:value="manualRestockPartId"
        :options="partOptions"
        filterable
        remote
        :loading="partOptionsLoading"
        placeholder="搜索配件 ID 或名称"
        @search="onPartSearch"
      />
    </n-form-item>
    <n-form-item label="备注">
      <n-input v-model:value="manualRestockNote" type="textarea" :rows="2" placeholder="选填" />
    </n-form-item>
  </n-form>
  <template #footer>
    <n-space justify="end">
      <n-button @click="manualRestockShow = false">取消</n-button>
      <n-button type="primary" :loading="manualRestockSaving" @click="saveManualRestock">提交</n-button>
    </n-space>
  </template>
</n-modal>
```

- [ ] **Step 11.2: Add the script logic**

In the `<script setup>` block of `HandcraftDetail.vue`, add the imports:

```javascript
import { listHandcraftRestock, createRestock, markRestockDone, deleteRestock } from '@/api/restock'
import { listParts } from '@/api/parts'
import { h } from 'vue'
import { NButton, NTag, NSpace } from 'naive-ui'
```

(Check if `listParts` exists in `frontend/src/api/parts.js`; use the actual exported name. If it differs, search there first.)

Add reactive state and lifecycle hooks (place after the existing data refs, near the order load logic):

```javascript
const restockRows = ref([])
const restockLoading = ref(false)

async function loadRestock() {
  if (!order.value?.id) return
  restockLoading.value = true
  try {
    const { data } = await listHandcraftRestock(order.value.id)
    restockRows.value = data
  } finally {
    restockLoading.value = false
  }
}

const pendingRestockCount = computed(() =>
  restockRows.value.filter((r) => r.status === 'pending').length
)
const doneRestockCount = computed(() =>
  restockRows.value.filter((r) => r.status === 'done').length
)

function restockRowClass(row) {
  return row.status === 'done' ? 'restock-row-done' : ''
}

const restockColumns = computed(() => [
  { title: '配件', key: 'part_id', render: (row) => row.part_id },
  {
    title: '来源',
    key: 'source',
    render: (row) => (row.source === 'picking' ? '配货模拟' : '手动添加')
      + ' · ' + new Date(row.created_at).toLocaleDateString(),
  },
  {
    title: '状态',
    key: 'status',
    render: (row) => h(
      NTag,
      { size: 'small', type: row.status === 'done' ? 'success' : 'warning', bordered: false },
      { default: () => row.status === 'done' ? '✓ 已补过' : '⏳ 待补货' },
    ),
  },
  { title: '备注', key: 'note', render: (row) => row.note || '—' },
  {
    title: '操作',
    key: 'actions',
    render: (row) => row.status === 'done'
      ? `${new Date(row.completed_at).toLocaleDateString()} 完成`
      : h(NSpace, { size: 'small' }, {
        default: () => [
          h(NButton, { size: 'tiny', onClick: () => markDoneRow(row) }, { default: () => '已补货' }),
          h(NButton, { size: 'tiny', text: true, onClick: () => cancelRow(row) }, { default: () => '取消' }),
        ],
      }),
  },
])

async function markDoneRow(row) {
  try {
    await markRestockDone(row.id)
    await loadRestock()
  } catch (err) {
    window.$message?.error(err?.response?.data?.detail || '操作失败')
  }
}

async function cancelRow(row) {
  try {
    await deleteRestock(row.id)
    await loadRestock()
  } catch (err) {
    window.$message?.error(err?.response?.data?.detail || '操作失败')
  }
}

const manualRestockShow = ref(false)
const manualRestockPartId = ref(null)
const manualRestockNote = ref('')
const manualRestockSaving = ref(false)
const partOptions = ref([])
const partOptionsLoading = ref(false)

function openManualRestockModal() {
  manualRestockPartId.value = null
  manualRestockNote.value = ''
  manualRestockShow.value = true
}

async function onPartSearch(query) {
  if (!query) {
    partOptions.value = []
    return
  }
  partOptionsLoading.value = true
  try {
    const { data } = await listParts({ keyword: query, limit: 30 })
    partOptions.value = (data?.items || data || []).map((p) => ({
      label: `${p.id} · ${p.name}`,
      value: p.id,
    }))
  } finally {
    partOptionsLoading.value = false
  }
}

async function saveManualRestock() {
  if (!manualRestockPartId.value) {
    window.$message?.warning('请选择配件')
    return
  }
  manualRestockSaving.value = true
  try {
    await createRestock({
      part_id: manualRestockPartId.value,
      handcraft_order_id: order.value.id,
      source: 'manual',
      note: manualRestockNote.value || null,
    })
    manualRestockShow.value = false
    await loadRestock()
  } catch (err) {
    window.$message?.error(err?.response?.data?.detail || '添加失败')
  } finally {
    manualRestockSaving.value = false
  }
}
```

Add `loadRestock()` to the order-load callback. Find where the page loads `order.value` (search `loadOrder` or similar). After it succeeds, call `await loadRestock()`.

- [ ] **Step 11.3: Add CSS for the done row**

Append to the `<style scoped>` block:

```css
:deep(.restock-row-done) {
  opacity: 0.6;
  background: #fafafa;
}
```

- [ ] **Step 11.4: Verify the parts API**

Open `frontend/src/api/parts.js` and confirm there is a function that searches parts by keyword (named `listParts` or similar). If the exact import name in step 11.2 is wrong, replace with the correct one. Run `grep "export" frontend/src/api/parts.js` to list available exports.

- [ ] **Step 11.5: Smoke-check via build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 11.6: Manual UI test**

In the dev environment, open a handcraft detail page. Verify:
- 补货清单 card appears at the bottom.
- Card shows pending and done rows from the picking modal (if you marked some).
- "+ 手动添加" opens the modal; selecting a part + saving inserts a row with source = 手动添加.
- "已补货" button transitions a row to done (浅灰 + "X/Y 完成"); "取消" deletes the row.

- [ ] **Step 11.7: Commit**

```bash
git add frontend/src/views/handcraft/HandcraftDetail.vue
git commit -m "feat(restock): handcraft detail 补货清单 card with manual add"
```

---

## Task 12: global「待补货清单」page (待补货 tab) + sidebar + routing

**Files:**
- Create: `frontend/src/views/restock/RestockList.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/layouts/DefaultLayout.vue`

- [ ] **Step 12.1: Create the page (待补货 tab only first)**

Create `frontend/src/views/restock/RestockList.vue`:

```vue
<template>
  <div>
    <h2 style="margin-top: 0;">待补货清单</h2>

    <n-tabs v-model:value="activeTab" type="line" animated>
      <n-tab-pane name="pending" :tab="`待补货 (${summaryRows.length})`">
        <div style="display:flex;gap:12px;align-items:center;margin:8px 0 12px;">
          <n-input v-model:value="searchQuery" placeholder="搜索配件 ID / 名称" clearable style="width:280px;" />
          <n-checkbox v-model:checked="onlyZeroStock">仅看库存为 0</n-checkbox>
          <span style="margin-left:auto;color:#888;font-size:13px;">
            共 {{ filteredRows.length }} 个配件 · {{ totalSourceCount }} 条来源
          </span>
        </div>

        <n-spin :show="summaryLoading">
          <n-empty v-if="!summaryLoading && filteredRows.length === 0" description="暂无待补货" />
          <n-collapse v-else accordion arrow-placement="left" :default-expanded-names="[]">
            <n-collapse-item
              v-for="row in filteredRows"
              :key="row.part_id"
              :name="row.part_id"
            >
              <template #header>
                <div style="display:flex;align-items:center;gap:12px;flex:1;">
                  <img v-if="row.part_image" :src="row.part_image" class="part-img" />
                  <div v-else class="part-img placeholder" />
                  <div style="flex:1;">
                    <div style="font-weight:500;">{{ row.part_id }} · {{ row.part_name }}</div>
                  </div>
                  <div :class="{ 'stock-low': row.current_stock < row.source_count }" style="text-align:right;">
                    <div style="font-size:11px;color:#888;">当前库存</div>
                    <div style="font-size:16px;font-weight:500;">{{ row.current_stock }}</div>
                  </div>
                  <div style="text-align:right;min-width:60px;">
                    <div style="font-size:11px;color:#888;">来源</div>
                    <div style="font-size:16px;font-weight:500;">{{ row.source_count }} 单</div>
                  </div>
                </div>
              </template>
              <template #header-extra>
                <n-button size="small" type="success" @click.stop="markPartDone(row)">
                  全部已补货
                </n-button>
              </template>
              <div>
                <div
                  v-for="src in row.sources"
                  :key="src.request_id"
                  class="source-row"
                >
                  <a class="hc-link" @click="goToHandcraft(src.handcraft_order_id)">
                    {{ src.handcraft_order_id }}
                  </a>
                  <span class="supplier">{{ src.supplier_name }}</span>
                  <span class="ts">{{ formatDate(src.created_at) }} 标记</span>
                  <n-button size="tiny" @click="markOneDone(src)">已补货</n-button>
                </div>
              </div>
            </n-collapse-item>
          </n-collapse>
        </n-spin>
      </n-tab-pane>

      <n-tab-pane name="history" tab="历史">
        <p style="color:#888;">历史记录将在 Task 13 中实现。</p>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useDialog, useMessage } from 'naive-ui'
import {
  listRestockSummary,
  markRestockDone,
  markPartRestockDone,
} from '@/api/restock'

const router = useRouter()
const dialog = useDialog()
const message = useMessage()

const activeTab = ref('pending')
const summaryRows = ref([])
const summaryLoading = ref(false)
const searchQuery = ref('')
const onlyZeroStock = ref(false)

const totalSourceCount = computed(() =>
  filteredRows.value.reduce((acc, r) => acc + r.source_count, 0),
)

const filteredRows = computed(() => {
  let rows = summaryRows.value
  if (onlyZeroStock.value) {
    rows = rows.filter((r) => r.current_stock <= 0)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    rows = rows.filter((r) =>
      r.part_id.toLowerCase().includes(q) || r.part_name.toLowerCase().includes(q)
    )
  }
  return rows
})

async function loadSummary() {
  summaryLoading.value = true
  try {
    const { data } = await listRestockSummary()
    summaryRows.value = data
  } finally {
    summaryLoading.value = false
  }
}

function formatDate(ts) {
  return new Date(ts).toLocaleDateString()
}

function goToHandcraft(hcId) {
  router.push(`/handcraft/${hcId}`)
}

async function markOneDone(src) {
  try {
    await markRestockDone(src.request_id)
    await loadSummary()
  } catch (err) {
    message.error(err?.response?.data?.detail || '操作失败')
  }
}

function markPartDone(row) {
  dialog.warning({
    title: '确认全部已补货',
    content: `把「${row.part_id} · ${row.part_name}」的所有 ${row.source_count} 条记录都标为已补货？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await markPartRestockDone(row.part_id)
        await loadSummary()
      } catch (err) {
        message.error(err?.response?.data?.detail || '操作失败')
      }
    },
  })
}

onMounted(loadSummary)
</script>

<style scoped>
.part-img {
  width: 48px;
  height: 48px;
  border-radius: 4px;
  background: #eee;
  object-fit: cover;
}
.part-img.placeholder { background: #fafafa; }
.stock-low > div:last-child { color: #d32f2f; }
.source-row {
  display: grid;
  grid-template-columns: 120px 1fr 140px 80px;
  align-items: center;
  padding: 8px 12px;
  border-top: 1px solid #f5f5f5;
  font-size: 13px;
}
.hc-link { color: #4361ee; cursor: pointer; }
.supplier { color: #666; }
.ts { color: #888; font-size: 12px; }
</style>
```

- [ ] **Step 12.2: Add the route**

Modify `frontend/src/router/index.js`. Add to the `ROUTE_PERMISSION_MAP`:

```javascript
const ROUTE_PERMISSION_MAP = {
  // ...existing entries...
  restock: 'handcraft',
}
```

Add to `PERMISSION_ROUTE_ORDER` (somewhere reasonable, e.g. between `'handcraft'` and `'inventory'`):

```javascript
const PERMISSION_ROUTE_ORDER = [
  'kanban', 'dashboard', 'parts', 'jewelries', 'orders',
  'purchase-orders', 'plating', 'handcraft', 'restock', 'inventory', 'inventory-log', 'users',
]
```

Add a route in the children array (place it near the other handcraft entries):

```javascript
{ path: 'restock', component: lazyLoad(() => import('@/views/restock/RestockList.vue')), meta: { perm: 'handcraft' } },
```

- [ ] **Step 12.3: Add the sidebar menu item**

Modify `frontend/src/layouts/DefaultLayout.vue`. Add to `allFlatItems`:

```javascript
{ label: '待补货清单', key: 'restock', icon: icon(AlertCircleOutline), perm: 'handcraft' },
```

(Import `AlertCircleOutline` from `@vicons/ionicons5` at the top of the imports — search for `import { ... } from '@vicons/ionicons5'` and add it.)

Add to `allGroupedItems`'s `生产` group, between `配件采购` and `电镀`:

```javascript
{ label: '待补货清单', key: 'restock', icon: icon(AlertCircleOutline), perm: 'handcraft' },
```

- [ ] **Step 12.4: Smoke-check via build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 12.5: Manual UI test**

In dev mode, open `/restock`. Verify:
- Sidebar shows "待补货清单" under 生产, between 配件采购 and 电镀.
- Pending tab lists aggregated parts; expand reveals sources.
- Click 已补货 on one source — that row disappears (or the card if it was the last source).
- Click 全部已补货 on a card — confirm dialog → all sources removed.
- 搜索/仅看库存为 0 filters work.

- [ ] **Step 12.6: Commit**

```bash
git add frontend/src/views/restock/RestockList.vue frontend/src/router/index.js frontend/src/layouts/DefaultLayout.vue
git commit -m "feat(restock): /restock global 待补货清单 page with sidebar entry"
```

---

## Task 13: 历史 tab on the global page

**Files:**
- Modify: `frontend/src/views/restock/RestockList.vue`

- [ ] **Step 13.1: Replace the placeholder历史 tab**

Modify `RestockList.vue`. Replace the `<n-tab-pane name="history" tab="历史">` block with:

```html
<n-tab-pane name="history" tab="历史">
  <n-data-table
    :columns="historyColumns"
    :data="historyRows"
    :loading="historyLoading"
    :bordered="false"
    size="small"
    :pagination="{ pageSize: 50 }"
  />
</n-tab-pane>
```

- [ ] **Step 13.2: Add the script logic**

Update the `<script setup>` block. Add imports:

```javascript
import { watch } from 'vue'
import { listRestockHistory } from '@/api/restock'
```

Add reactive state and column config:

```javascript
const historyRows = ref([])
const historyLoading = ref(false)

const historyColumns = [
  { title: '配件', key: 'part_id', render: (row) => `${row.part_id} · ${row.part_name}` },
  { title: '手工单', key: 'handcraft_order_id', render: (row) => row.handcraft_order_id || '—' },
  { title: '手工商家', key: 'supplier_name', render: (row) => row.supplier_name || '—' },
  { title: '来源', key: 'source', render: (row) => row.source === 'picking' ? '配货模拟' : '手动添加' },
  { title: '备注', key: 'note', render: (row) => row.note || '—' },
  { title: '标记时间', key: 'created_at', render: (row) => formatDate(row.created_at) },
  { title: '完成时间', key: 'completed_at', render: (row) => formatDate(row.completed_at) },
]

async function loadHistory() {
  historyLoading.value = true
  try {
    const { data } = await listRestockHistory({ limit: 200 })
    historyRows.value = data
  } finally {
    historyLoading.value = false
  }
}

watch(activeTab, (val) => {
  if (val === 'history') loadHistory()
})
```

- [ ] **Step 13.3: Smoke-check via build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 13.4: Manual UI test**

Mark some pending records done, then switch to the 历史 tab. Verify the table shows them with all columns populated.

- [ ] **Step 13.5: Commit**

```bash
git add frontend/src/views/restock/RestockList.vue
git commit -m "feat(restock): 历史 tab on /restock global page"
```

---

## Final Verification

- [ ] **Step F.1: Run the full backend test suite**

Run: `pytest -q`
Expected: all PASS (no regressions in other modules).

- [ ] **Step F.2: Run the frontend build**

Run: `cd frontend && npm run build`
Expected: build succeeds without warnings of unused imports relevant to this work.

- [ ] **Step F.3: Smoke-test the three entry points end-to-end**

With dev servers running:

1. Open a `pending` handcraft order with at least one stock-low part.
2. In 配货模拟 弹窗, mark a row 需补货. Close modal. Reopen — state persists.
3. Open the same order's detail page — 补货清单 card shows the marked record.
4. Use "+ 手动添加" to add a different part with a note. Card now shows two pending rows.
5. Open `/restock`. Pending tab shows both parts aggregated. Expand to see sources.
6. Click 已补货 on one source — disappears.
7. Click 全部已补货 on the other — confirm dialog → disappears.
8. Switch to 历史 tab — all the records that were marked done are listed with completion times.
9. Delete the handcraft order — `/restock` and history both stop showing those entries (cascade).

- [ ] **Step F.4: Final commit (if any docs updates)**

If anything needed tweaking during smoke tests, commit those changes with a `chore(restock): ...` message.
