# 配件清单优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize the order parts list to support batch-based generation, jewelry status tracking, supplier linking, and improved progress calculation.

**Architecture:** Add `OrderTodoBatch` and `OrderTodoBatchJewelry` tables to group parts lists by batch. Jewelry status is computed in real-time from inventory/handcraft data. Each batch can link to a handcraft supplier, auto-creating a HandcraftOrder with migrated parts/jewelry data.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, Vue 3 + Naive UI, ReportLab (PDF)

**Spec:** `docs/superpowers/specs/2026-04-01-parts-list-optimization-design.md`

---

## File Structure

### New Files
- (none — all changes go into existing files)

### Modified Files

| File | Changes |
|------|---------|
| `models/order.py` | Add `OrderTodoBatch`, `OrderTodoBatchJewelry` models; add `batch_id` to `OrderTodoItem` |
| `database.py` | Add schema compat for new tables/columns |
| `schemas/order.py` | Add batch-related request/response schemas |
| `services/order_todo.py` | Add batch CRUD, jewelry status, jewelry-for-batch, link-supplier; modify progress |
| `services/order.py` | Modify `get_parts_summary` to include `remaining_qty` |
| `services/order_todo_pdf.py` | Add `batch_id` parameter, add supplier header line |
| `api/orders.py` | Add 5 new endpoints, modify progress/PDF/parts-summary endpoints |
| `frontend/src/api/orders.js` | Add new API functions |
| `frontend/src/views/orders/OrderDetail.vue` | Jewelry status column, batch modal, collapsible structure, supplier modal, BOM update |
| `frontend/src/views/orders/OrderList.vue` | Rename "备料进度" → "备货进度" |
| `tests/test_api_order_todo.py` | Add tests for all new functionality |

---

## Task 1: Data Models — New Tables + Schema Compat

**Files:**
- Modify: `models/order.py` (after line 36, OrderTodoItem class)
- Modify: `database.py` (ensure_schema_compat function)
- Test: `tests/test_api_order_todo.py`

- [ ] **Step 1: Add new models and batch_id column**

In `models/order.py`, add `batch_id` to `OrderTodoItem` and add two new classes after `OrderItemLink`:

```python
# Add to OrderTodoItem class (after required_qty):
    batch_id = Column(Integer, ForeignKey("order_todo_batch.id"), nullable=True)

# Add after OrderItemLink class:
class OrderTodoBatch(Base):
    __tablename__ = "order_todo_batch"
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("order.id"), nullable=False)
    handcraft_order_id = Column(String, ForeignKey("handcraft_order.id"), nullable=True)
    created_at = Column(DateTime, default=now_beijing)


class OrderTodoBatchJewelry(Base):
    __tablename__ = "order_todo_batch_jewelry"
    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey("order_todo_batch.id"), nullable=False)
    jewelry_id = Column(String, ForeignKey("jewelry.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
```

- [ ] **Step 2: Add schema compat for new tables/columns**

In `database.py`, add to `ensure_schema_compat()` — after existing column checks, add migration for `order_todo_item.batch_id`:

```python
# --- order_todo_item.batch_id ---
if inspector.has_table("order_todo_item"):
    cols = [c["name"] for c in inspector.get_columns("order_todo_item")]
    if "batch_id" not in cols:
        conn.execute(text(
            "ALTER TABLE order_todo_item ADD COLUMN batch_id INTEGER"
        ))
```

Note: `order_todo_batch` and `order_todo_batch_jewelry` tables are auto-created by `Base.metadata.create_all()` in `main.py` lifespan — no ALTER needed for new tables.

- [ ] **Step 3: Write test to verify models exist**

Add to the top of `tests/test_api_order_todo.py`:

```python
from models.order import OrderTodoBatch, OrderTodoBatchJewelry
```

Then add test:

```python
def test_batch_tables_exist(db):
    """Verify new batch tables are created."""
    from sqlalchemy import inspect
    inspector = inspect(db.bind)
    assert inspector.has_table("order_todo_batch")
    assert inspector.has_table("order_todo_batch_jewelry")
    # Verify batch_id column on order_todo_item
    cols = [c["name"] for c in inspector.get_columns("order_todo_item")]
    assert "batch_id" in cols
```

- [ ] **Step 4: Run test**

Run: `pytest tests/test_api_order_todo.py::test_batch_tables_exist -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add models/order.py database.py tests/test_api_order_todo.py
git commit -m "feat: add OrderTodoBatch and OrderTodoBatchJewelry models"
```

---

## Task 2: Schemas — Batch Request/Response Types

**Files:**
- Modify: `schemas/order.py` (add new schemas after existing ones)

- [ ] **Step 1: Add new schemas**

Append to `schemas/order.py`:

```python
# --- Batch schemas ---

class TodoBatchCreateRequest(BaseModel):
    jewelry_ids: list[str]


class TodoBatchJewelryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    jewelry_id: str
    jewelry_name: str
    jewelry_image: str | None = None
    quantity: int


class TodoBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_id: str
    handcraft_order_id: str | None = None
    supplier_name: str | None = None
    created_at: datetime
    jewelries: list[TodoBatchJewelryResponse] = []
    items: list[OrderTodoItemResponse] = []


class TodoBatchListResponse(BaseModel):
    batches: list[TodoBatchResponse]


class LinkSupplierRequest(BaseModel):
    supplier_name: str


class LinkSupplierResponse(BaseModel):
    handcraft_order_id: str


class JewelryStatusResponse(BaseModel):
    jewelry_id: str
    jewelry_name: str
    jewelry_image: str | None = None
    quantity: int
    status: str


class JewelryForBatchResponse(BaseModel):
    jewelry_id: str
    jewelry_name: str
    jewelry_image: str | None = None
    order_quantity: int
    allocated_quantity: int
    remaining_quantity: int
    selectable: bool
    disabled_reason: str | None = None


class PartsSummaryItemResponse(BaseModel):
    part_id: str
    part_name: str
    part_image: str | None = None
    total_qty: float
    remaining_qty: float
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from schemas.order import TodoBatchCreateRequest, TodoBatchResponse, JewelryStatusResponse, JewelryForBatchResponse, PartsSummaryItemResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add schemas/order.py
git commit -m "feat: add batch and jewelry status schemas"
```

---

## Task 3: Service — Jewelry Status Calculation

**Files:**
- Modify: `services/order_todo.py`
- Test: `tests/test_api_order_todo.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_api_order_todo.py`. First add a helper that sets up a full order with BOM (reuse `_setup_order_with_bom` pattern):

```python
def test_jewelry_status_waiting_parts(client, db):
    """Jewelry with insufficient part stock → 等待配件备齐."""
    parts, jewelry, order = _setup_order_with_bom(db)
    # No stock added, so parts are insufficient
    resp = client.get(f"/api/orders/{order.id}/jewelry-status")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "等待配件备齐"


def test_jewelry_status_waiting_handcraft(client, db):
    """Jewelry with sufficient part stock but no handcraft link → 等待发往手工."""
    parts, jewelry, order = _setup_order_with_bom(db)
    # Add enough stock for all parts
    from services.inventory import add_stock
    from models.bom import Bom
    bom_rows = db.query(Bom).filter_by(jewelry_id=jewelry.id).all()
    for bom in bom_rows:
        needed = float(bom.qty_per_unit) * order.items[0].quantity if hasattr(order, 'items') else float(bom.qty_per_unit) * 10
        add_stock(db, "part", bom.part_id, needed + 10, "test stock")
    db.flush()
    resp = client.get(f"/api/orders/{order.id}/jewelry-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["status"] == "等待发往手工"


def test_jewelry_status_completed(client, db):
    """Jewelry with sufficient jewelry stock → 完成备货."""
    parts, jewelry, order = _setup_order_with_bom(db)
    from services.inventory import add_stock
    # Add jewelry stock >= order quantity
    item = db.query(OrderItem).filter_by(order_id=order.id).first()
    add_stock(db, "jewelry", jewelry.id, item.quantity + 5, "test stock")
    db.flush()
    resp = client.get(f"/api/orders/{order.id}/jewelry-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["status"] == "完成备货"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_order_todo.py::test_jewelry_status_waiting_parts tests/test_api_order_todo.py::test_jewelry_status_waiting_handcraft tests/test_api_order_todo.py::test_jewelry_status_completed -v`
Expected: FAIL (endpoint not found)

- [ ] **Step 3: Implement `get_jewelry_status` in service**

Add to `services/order_todo.py`:

```python
from models.bom import Bom
from models.jewelry import Jewelry

def get_jewelry_status(db: Session, order_id: str) -> list[dict]:
    """Compute status for each jewelry item in the order.

    Priority (highest first):
    1. 完成备货  — jewelry stock >= order quantity
    2. 等待手工返回 — linked to HandcraftJewelryItem (via OrderItemLink or batch)
    3. 等待发往手工 — all BOM parts have sufficient stock
    4. 等待配件备齐 — default
    """
    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        raise ValueError(f"订单 {order_id} 不存在")

    items = db.query(OrderItem).filter_by(order_id=order_id).all()
    if not items:
        return []

    jewelry_ids = [it.jewelry_id for it in items]

    # Batch fetch jewelry stock
    jewelry_stocks = batch_get_stock(db, "jewelry", jewelry_ids)

    # Batch fetch part stock for BOM check
    all_bom = db.query(Bom).filter(Bom.jewelry_id.in_(jewelry_ids)).all()
    all_part_ids = list({b.part_id for b in all_bom})
    part_stocks = batch_get_stock(db, "part", all_part_ids) if all_part_ids else {}

    # Check handcraft links: via OrderItemLink
    linked_jewelry_ids_via_link = set()
    links = (
        db.query(OrderItemLink.handcraft_jewelry_item_id)
        .filter(
            OrderItemLink.order_id == order_id,
            OrderItemLink.handcraft_jewelry_item_id.isnot(None),
        )
        .all()
    )
    if links:
        hc_item_ids = [l[0] for l in links]
        hc_items = db.query(HandcraftJewelryItem).filter(
            HandcraftJewelryItem.id.in_(hc_item_ids)
        ).all()
        linked_jewelry_ids_via_link = {hci.jewelry_id for hci in hc_items}

    # Check handcraft links: via batch
    linked_jewelry_ids_via_batch = set()
    batches = (
        db.query(OrderTodoBatch)
        .filter(
            OrderTodoBatch.order_id == order_id,
            OrderTodoBatch.handcraft_order_id.isnot(None),
        )
        .all()
    )
    for batch in batches:
        hc_j_items = (
            db.query(HandcraftJewelryItem)
            .filter_by(handcraft_order_id=batch.handcraft_order_id)
            .all()
        )
        for hci in hc_j_items:
            linked_jewelry_ids_via_batch.add(hci.jewelry_id)

    linked_jewelry_ids = linked_jewelry_ids_via_link | linked_jewelry_ids_via_batch

    # Build BOM lookup: jewelry_id -> [(part_id, qty_per_unit)]
    bom_map: dict[str, list[tuple[str, float]]] = {}
    for b in all_bom:
        bom_map.setdefault(b.jewelry_id, []).append((b.part_id, float(b.qty_per_unit)))

    # Fetch jewelry info
    jewelries = db.query(Jewelry).filter(Jewelry.id.in_(jewelry_ids)).all()
    jewelry_info = {j.id: j for j in jewelries}

    result = []
    for item in items:
        jid = item.jewelry_id
        qty = item.quantity
        j = jewelry_info.get(jid)

        # Priority 1: 完成备货
        if jewelry_stocks.get(jid, 0) >= qty:
            status = "完成备货"
        # Priority 2: 等待手工返回
        elif jid in linked_jewelry_ids:
            status = "等待手工返回"
        # Priority 3: 等待发往手工
        elif _all_parts_sufficient(bom_map.get(jid, []), qty, part_stocks):
            status = "等待发往手工"
        # Priority 4: default
        else:
            status = "等待配件备齐"

        result.append({
            "jewelry_id": jid,
            "jewelry_name": j.name if j else "",
            "jewelry_image": j.image if j else None,
            "quantity": qty,
            "status": status,
        })

    return result


def _all_parts_sufficient(bom_parts: list[tuple[str, float]], order_qty: int, part_stocks: dict[str, float]) -> bool:
    """Check if all BOM parts have sufficient stock for the given order quantity."""
    if not bom_parts:
        return True
    for part_id, qty_per_unit in bom_parts:
        needed = qty_per_unit * order_qty
        if part_stocks.get(part_id, 0) < needed:
            return False
    return True
```

Add imports at top of `services/order_todo.py` (if not already present):

```python
from models.order import OrderTodoBatch, OrderTodoBatchJewelry
from models.handcraft_order import HandcraftJewelryItem
from models.bom import Bom
from models.jewelry import Jewelry
from services.inventory import batch_get_stock
```

- [ ] **Step 4: Add API endpoint**

Add to `api/orders.py`:

```python
from services.order_todo import get_jewelry_status

@router.get("/{order_id}/jewelry-status")
def jewelry_status(order_id: str, db: Session = Depends(get_db)):
    with service_errors():
        return get_jewelry_status(db, order_id)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_api_order_todo.py::test_jewelry_status_waiting_parts tests/test_api_order_todo.py::test_jewelry_status_waiting_handcraft tests/test_api_order_todo.py::test_jewelry_status_completed -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/order_todo.py api/orders.py tests/test_api_order_todo.py
git commit -m "feat: add jewelry status calculation endpoint"
```

---

## Task 4: Service — Jewelry-for-Batch (Selectable List)

**Files:**
- Modify: `services/order_todo.py`
- Modify: `api/orders.py`
- Test: `tests/test_api_order_todo.py`

- [ ] **Step 1: Write failing tests**

```python
def test_jewelry_for_batch_all_selectable(client, db):
    """All jewelry selectable when no handcraft orders exist."""
    parts, jewelry, order = _setup_order_with_bom(db)
    resp = client.get(f"/api/orders/{order.id}/jewelry-for-batch")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    item = data[0]
    assert item["selectable"] is True
    assert item["allocated_quantity"] == 0
    assert item["remaining_quantity"] == item["order_quantity"]


def test_jewelry_for_batch_partially_allocated(client, db):
    """Jewelry partially allocated shows remaining quantity."""
    parts, jewelry, order = _setup_order_with_bom(db)
    order_item = db.query(OrderItem).filter_by(order_id=order.id).first()
    # Create a handcraft order with partial qty
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    hc = HandcraftOrder(id="HC-TEST1", supplier_name="TestSupplier", status="pending")
    db.add(hc)
    db.flush()
    hc_j = HandcraftJewelryItem(
        handcraft_order_id=hc.id,
        jewelry_id=jewelry.id,
        qty=3,
    )
    db.add(hc_j)
    db.flush()
    # Link via OrderItemLink
    link = OrderItemLink(order_id=order.id, handcraft_jewelry_item_id=hc_j.id)
    db.add(link)
    db.flush()

    resp = client.get(f"/api/orders/{order.id}/jewelry-for-batch")
    assert resp.status_code == 200
    data = resp.json()
    item = data[0]
    assert item["allocated_quantity"] == 3
    assert item["remaining_quantity"] == order_item.quantity - 3
    assert item["selectable"] is True


def test_jewelry_for_batch_fully_allocated_not_selectable(client, db):
    """Jewelry fully allocated to handcraft → not selectable."""
    parts, jewelry, order = _setup_order_with_bom(db)
    order_item = db.query(OrderItem).filter_by(order_id=order.id).first()
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    hc = HandcraftOrder(id="HC-TEST2", supplier_name="TestSupplier", status="pending")
    db.add(hc)
    db.flush()
    hc_j = HandcraftJewelryItem(
        handcraft_order_id=hc.id,
        jewelry_id=jewelry.id,
        qty=order_item.quantity,  # fully allocated
    )
    db.add(hc_j)
    db.flush()
    link = OrderItemLink(order_id=order.id, handcraft_jewelry_item_id=hc_j.id)
    db.add(link)
    db.flush()

    resp = client.get(f"/api/orders/{order.id}/jewelry-for-batch")
    assert resp.status_code == 200
    data = resp.json()
    item = data[0]
    assert item["selectable"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_order_todo.py::test_jewelry_for_batch_all_selectable tests/test_api_order_todo.py::test_jewelry_for_batch_partially_allocated tests/test_api_order_todo.py::test_jewelry_for_batch_fully_allocated_not_selectable -v`
Expected: FAIL

- [ ] **Step 3: Implement `get_jewelry_for_batch`**

Add to `services/order_todo.py`:

```python
def get_jewelry_for_batch(db: Session, order_id: str) -> list[dict]:
    """Get jewelry list for batch selection modal.

    Returns each jewelry with order_quantity, allocated_quantity, remaining_quantity,
    selectable flag, and disabled_reason.
    """
    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        raise ValueError(f"订单 {order_id} 不存在")

    items = db.query(OrderItem).filter_by(order_id=order_id).all()
    if not items:
        return []

    # Get jewelry status for disable check
    statuses = get_jewelry_status(db, order_id)
    status_map = {s["jewelry_id"]: s["status"] for s in statuses}

    # Calculate allocated quantities per jewelry_id
    # Find all HandcraftJewelryItems linked to this order (via OrderItemLink)
    allocated_map: dict[str, int] = {}
    links = (
        db.query(OrderItemLink)
        .filter(
            OrderItemLink.order_id == order_id,
            OrderItemLink.handcraft_jewelry_item_id.isnot(None),
        )
        .all()
    )
    if links:
        hc_item_ids = [l.handcraft_jewelry_item_id for l in links]
        hc_items = db.query(HandcraftJewelryItem).filter(
            HandcraftJewelryItem.id.in_(hc_item_ids)
        ).all()
        for hci in hc_items:
            allocated_map[hci.jewelry_id] = allocated_map.get(hci.jewelry_id, 0) + hci.qty

    # Also check via batch links
    batches = (
        db.query(OrderTodoBatch)
        .filter(
            OrderTodoBatch.order_id == order_id,
            OrderTodoBatch.handcraft_order_id.isnot(None),
        )
        .all()
    )
    for batch in batches:
        hc_j_items = (
            db.query(HandcraftJewelryItem)
            .filter_by(handcraft_order_id=batch.handcraft_order_id)
            .all()
        )
        for hci in hc_j_items:
            # Avoid double-counting if also linked via OrderItemLink
            if hci.id not in {l.handcraft_jewelry_item_id for l in links}:
                allocated_map[hci.jewelry_id] = allocated_map.get(hci.jewelry_id, 0) + hci.qty

    jewelry_ids = [it.jewelry_id for it in items]
    jewelries = db.query(Jewelry).filter(Jewelry.id.in_(jewelry_ids)).all()
    jewelry_info = {j.id: j for j in jewelries}

    result = []
    for item in items:
        jid = item.jewelry_id
        j = jewelry_info.get(jid)
        allocated = allocated_map.get(jid, 0)
        remaining = item.quantity - allocated
        status = status_map.get(jid, "等待配件备齐")

        # Determine selectability
        selectable = True
        disabled_reason = None
        if status in ("等待手工返回", "完成备货"):
            selectable = False
            disabled_reason = status
        elif remaining <= 0:
            selectable = False
            disabled_reason = "已全部分配"

        result.append({
            "jewelry_id": jid,
            "jewelry_name": j.name if j else "",
            "jewelry_image": j.image if j else None,
            "order_quantity": item.quantity,
            "allocated_quantity": allocated,
            "remaining_quantity": max(0, remaining),
            "selectable": selectable,
            "disabled_reason": disabled_reason,
        })

    # Sort: selectable first, then non-selectable
    result.sort(key=lambda x: (not x["selectable"], x["jewelry_id"]))
    return result
```

- [ ] **Step 4: Add API endpoint**

Add to `api/orders.py`:

```python
from services.order_todo import get_jewelry_for_batch

@router.get("/{order_id}/jewelry-for-batch")
def jewelry_for_batch(order_id: str, db: Session = Depends(get_db)):
    with service_errors():
        return get_jewelry_for_batch(db, order_id)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_api_order_todo.py::test_jewelry_for_batch_all_selectable tests/test_api_order_todo.py::test_jewelry_for_batch_partially_allocated tests/test_api_order_todo.py::test_jewelry_for_batch_fully_allocated_not_selectable -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/order_todo.py api/orders.py tests/test_api_order_todo.py
git commit -m "feat: add jewelry-for-batch selection endpoint"
```

---

## Task 5: Service — Create Batch (Generate Specified Parts List)

**Files:**
- Modify: `services/order_todo.py`
- Modify: `api/orders.py`
- Test: `tests/test_api_order_todo.py`

- [ ] **Step 1: Write failing tests**

```python
def test_create_batch(client, db):
    """Create a batch with selected jewelry, generates part todo items."""
    parts, jewelry, order = _setup_order_with_bom(db)
    resp = client.post(
        f"/api/orders/{order.id}/todo-batch",
        json={"jewelry_ids": [jewelry.id]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["order_id"] == order.id
    assert len(data["jewelries"]) == 1
    assert data["jewelries"][0]["jewelry_id"] == jewelry.id
    assert len(data["items"]) > 0  # BOM parts should be generated
    # Verify todo items have batch_id set
    for item in data["items"]:
        assert "batch_id" in item


def test_create_batch_invalid_jewelry(client, db):
    """Reject jewelry_id not in the order."""
    parts, jewelry, order = _setup_order_with_bom(db)
    resp = client.post(
        f"/api/orders/{order.id}/todo-batch",
        json={"jewelry_ids": ["SP-NONEXISTENT"]},
    )
    assert resp.status_code == 400


def test_get_batches(client, db):
    """Get all batches for an order."""
    parts, jewelry, order = _setup_order_with_bom(db)
    # Create a batch first
    client.post(
        f"/api/orders/{order.id}/todo-batch",
        json={"jewelry_ids": [jewelry.id]},
    )
    resp = client.get(f"/api/orders/{order.id}/todo-batches")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["batches"]) == 1
    batch = data["batches"][0]
    assert batch["order_id"] == order.id
    assert len(batch["jewelries"]) == 1
    assert len(batch["items"]) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_order_todo.py::test_create_batch tests/test_api_order_todo.py::test_create_batch_invalid_jewelry tests/test_api_order_todo.py::test_get_batches -v`
Expected: FAIL

- [ ] **Step 3: Implement `create_batch` and `get_batches`**

Add to `services/order_todo.py`:

```python
def create_batch(db: Session, order_id: str, jewelry_ids: list[str]) -> dict:
    """Create a new todo batch for selected jewelry items.

    Generates OrderTodoItems for BOM parts of selected jewelry.
    """
    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        raise ValueError(f"订单 {order_id} 不存在")

    # Validate all jewelry_ids belong to this order
    order_items = db.query(OrderItem).filter_by(order_id=order_id).all()
    order_jewelry_map = {oi.jewelry_id: oi for oi in order_items}
    for jid in jewelry_ids:
        if jid not in order_jewelry_map:
            raise ValueError(f"饰品 {jid} 不在订单 {order_id} 中")

    # Get allocation info to determine quantities
    for_batch = get_jewelry_for_batch(db, order_id)
    allocation_map = {fb["jewelry_id"]: fb for fb in for_batch}

    # Create batch
    batch = OrderTodoBatch(order_id=order_id)
    db.add(batch)
    db.flush()

    # Create batch jewelry entries
    batch_jewelries = []
    for jid in jewelry_ids:
        alloc = allocation_map.get(jid)
        if alloc and alloc["remaining_quantity"] > 0:
            qty = alloc["remaining_quantity"]
        else:
            qty = order_jewelry_map[jid].quantity
        bj = OrderTodoBatchJewelry(
            batch_id=batch.id,
            jewelry_id=jid,
            quantity=qty,
        )
        db.add(bj)
        batch_jewelries.append(bj)
    db.flush()

    # Generate BOM-based todo items for this batch
    from services.bom import get_bom
    part_qty_map: dict[str, float] = {}
    for bj in batch_jewelries:
        bom_rows = get_bom(db, bj.jewelry_id)
        for bom in bom_rows:
            pid = bom.part_id
            part_qty_map[pid] = part_qty_map.get(pid, 0) + float(bom.qty_per_unit) * bj.quantity

    # Create OrderTodoItem for each part
    todo_items = []
    for part_id, required_qty in part_qty_map.items():
        todo = OrderTodoItem(
            order_id=order_id,
            part_id=part_id,
            required_qty=required_qty,
            batch_id=batch.id,
        )
        db.add(todo)
        todo_items.append(todo)
    db.flush()

    return _build_batch_response(db, batch, batch_jewelries, todo_items)


def get_batches(db: Session, order_id: str) -> list[dict]:
    """Get all batches for an order with enriched details."""
    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        raise ValueError(f"订单 {order_id} 不存在")

    batches = (
        db.query(OrderTodoBatch)
        .filter_by(order_id=order_id)
        .order_by(OrderTodoBatch.created_at)
        .all()
    )

    result = []
    for batch in batches:
        batch_jewelries = (
            db.query(OrderTodoBatchJewelry)
            .filter_by(batch_id=batch.id)
            .all()
        )
        todo_items = (
            db.query(OrderTodoItem)
            .filter_by(batch_id=batch.id)
            .all()
        )
        result.append(_build_batch_response(db, batch, batch_jewelries, todo_items))

    return result


def _build_batch_response(db: Session, batch, batch_jewelries, todo_items) -> dict:
    """Build enriched batch response dict."""
    from models.handcraft_order import HandcraftOrder as HCOrder

    # Get supplier name if linked
    supplier_name = None
    if batch.handcraft_order_id:
        hc = db.query(HCOrder).filter_by(id=batch.handcraft_order_id).first()
        if hc:
            supplier_name = hc.supplier_name
        else:
            # Handcraft order was deleted — clear the link
            batch.handcraft_order_id = None
            db.flush()

    # Enrich jewelry info
    jewelry_ids = [bj.jewelry_id for bj in batch_jewelries]
    jewelries = db.query(Jewelry).filter(Jewelry.id.in_(jewelry_ids)).all() if jewelry_ids else []
    j_info = {j.id: j for j in jewelries}

    jewelry_list = []
    for bj in batch_jewelries:
        j = j_info.get(bj.jewelry_id)
        jewelry_list.append({
            "jewelry_id": bj.jewelry_id,
            "jewelry_name": j.name if j else "",
            "jewelry_image": j.image if j else None,
            "quantity": bj.quantity,
        })

    # Enrich todo items (reuse get_todo enrichment pattern)
    part_ids = [t.part_id for t in todo_items]
    from models.part import Part
    parts_db = db.query(Part).filter(Part.id.in_(part_ids)).all() if part_ids else []
    part_info = {p.id: p for p in parts_db}
    part_stocks = batch_get_stock(db, "part", part_ids) if part_ids else {}

    items_list = []
    for t in todo_items:
        p = part_info.get(t.part_id)
        stock = part_stocks.get(t.part_id, 0.0)
        req = float(t.required_qty)
        gap = max(0.0, req - stock)
        items_list.append({
            "id": t.id,
            "order_id": t.order_id,
            "part_id": t.part_id,
            "required_qty": req,
            "batch_id": t.batch_id,
            "part_name": p.name if p else "",
            "part_image": p.image if p else None,
            "stock_qty": stock,
            "gap": gap,
            "is_complete": stock >= req,
            "linked_production": _get_linked_production(db, t.id),
        })

    return {
        "id": batch.id,
        "order_id": batch.order_id,
        "handcraft_order_id": batch.handcraft_order_id,
        "supplier_name": supplier_name,
        "created_at": batch.created_at,
        "jewelries": jewelry_list,
        "items": items_list,
    }
```

- [ ] **Step 4: Add API endpoints**

Add to `api/orders.py`:

```python
from services.order_todo import create_batch, get_batches
from schemas.order import TodoBatchCreateRequest, TodoBatchListResponse

@router.post("/{order_id}/todo-batch")
def create_todo_batch(order_id: str, req: TodoBatchCreateRequest, db: Session = Depends(get_db)):
    with service_errors():
        return create_batch(db, order_id, req.jewelry_ids)


@router.get("/{order_id}/todo-batches")
def get_todo_batches(order_id: str, db: Session = Depends(get_db)):
    with service_errors():
        return {"batches": get_batches(db, order_id)}
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_api_order_todo.py::test_create_batch tests/test_api_order_todo.py::test_create_batch_invalid_jewelry tests/test_api_order_todo.py::test_get_batches -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/order_todo.py api/orders.py tests/test_api_order_todo.py
git commit -m "feat: add batch creation and listing endpoints"
```

---

## Task 6: Service — Link Supplier (Create Handcraft Order from Batch)

**Files:**
- Modify: `services/order_todo.py`
- Modify: `api/orders.py`
- Test: `tests/test_api_order_todo.py`

- [ ] **Step 1: Write failing tests**

```python
def test_link_supplier_creates_handcraft_order(client, db):
    """Linking supplier creates HC order with migrated parts and jewelry."""
    parts, jewelry, order = _setup_order_with_bom(db)
    # Create batch first
    batch_resp = client.post(
        f"/api/orders/{order.id}/todo-batch",
        json={"jewelry_ids": [jewelry.id]},
    )
    batch_id = batch_resp.json()["id"]

    # Link supplier
    resp = client.post(
        f"/api/orders/{order.id}/todo-batch/{batch_id}/link-supplier",
        json={"supplier_name": "王师傅手工坊"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "handcraft_order_id" in data
    hc_id = data["handcraft_order_id"]
    assert hc_id.startswith("HC-")

    # Verify handcraft order has parts and jewelry
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
    hc = db.query(HandcraftOrder).filter_by(id=hc_id).first()
    assert hc is not None
    assert hc.supplier_name == "王师傅手工坊"
    assert hc.status == "pending"

    hc_parts = db.query(HandcraftPartItem).filter_by(handcraft_order_id=hc_id).all()
    assert len(hc_parts) > 0  # BOM parts migrated

    hc_jewelries = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=hc_id).all()
    assert len(hc_jewelries) == 1
    assert hc_jewelries[0].jewelry_id == jewelry.id

    # Verify batch now has handcraft_order_id
    batches_resp = client.get(f"/api/orders/{order.id}/todo-batches")
    batch = batches_resp.json()["batches"][0]
    assert batch["handcraft_order_id"] == hc_id
    assert batch["supplier_name"] == "王师傅手工坊"


def test_link_supplier_already_linked(client, db):
    """Cannot link supplier to an already-linked batch."""
    parts, jewelry, order = _setup_order_with_bom(db)
    batch_resp = client.post(
        f"/api/orders/{order.id}/todo-batch",
        json={"jewelry_ids": [jewelry.id]},
    )
    batch_id = batch_resp.json()["id"]
    # First link
    client.post(
        f"/api/orders/{order.id}/todo-batch/{batch_id}/link-supplier",
        json={"supplier_name": "王师傅手工坊"},
    )
    # Second link should fail
    resp = client.post(
        f"/api/orders/{order.id}/todo-batch/{batch_id}/link-supplier",
        json={"supplier_name": "另一个商家"},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_order_todo.py::test_link_supplier_creates_handcraft_order tests/test_api_order_todo.py::test_link_supplier_already_linked -v`
Expected: FAIL

- [ ] **Step 3: Implement `link_supplier`**

Add to `services/order_todo.py`:

```python
def link_supplier(db: Session, order_id: str, batch_id: int, supplier_name: str) -> dict:
    """Link a handcraft supplier to a batch, creating a HandcraftOrder.

    1. Find or create Supplier (type=handcraft)
    2. Create HandcraftOrder
    3. Migrate batch parts → HandcraftPartItem
    4. Migrate batch jewelry → HandcraftJewelryItem
    5. Create OrderItemLinks
    6. Update batch.handcraft_order_id
    """
    from models.supplier import Supplier
    from models.handcraft_order import HandcraftOrder as HCOrder
    from services._helpers import _next_id

    batch = db.query(OrderTodoBatch).filter_by(id=batch_id, order_id=order_id).first()
    if not batch:
        raise ValueError(f"批次 {batch_id} 不存在")
    if batch.handcraft_order_id:
        # Check if the HC order still exists
        hc_exists = db.query(HCOrder).filter_by(id=batch.handcraft_order_id).first()
        if hc_exists:
            raise ValueError("该批次已关联手工商家")
        # HC order was deleted, clear the stale link
        batch.handcraft_order_id = None
        db.flush()

    # Find or create supplier
    supplier = (
        db.query(Supplier)
        .filter_by(name=supplier_name, type="handcraft")
        .first()
    )
    if not supplier:
        supplier = Supplier(name=supplier_name, type="handcraft")
        db.add(supplier)
        db.flush()

    # Create handcraft order
    hc_id = _next_id(db, HCOrder, "HC")
    hc = HCOrder(id=hc_id, supplier_name=supplier_name, status="pending")
    db.add(hc)
    db.flush()

    # Migrate parts: batch todo items → HandcraftPartItem
    todo_items = db.query(OrderTodoItem).filter_by(batch_id=batch_id).all()
    for todo in todo_items:
        hc_part = HandcraftPartItem(
            handcraft_order_id=hc_id,
            part_id=todo.part_id,
            qty=float(todo.required_qty),
        )
        db.add(hc_part)
        db.flush()
        # Create OrderItemLink for part
        link = OrderItemLink(
            order_todo_item_id=todo.id,
            handcraft_part_item_id=hc_part.id,
        )
        db.add(link)

    # Migrate jewelry: batch jewelry → HandcraftJewelryItem
    batch_jewelries = db.query(OrderTodoBatchJewelry).filter_by(batch_id=batch_id).all()
    for bj in batch_jewelries:
        hc_jewelry = HandcraftJewelryItem(
            handcraft_order_id=hc_id,
            jewelry_id=bj.jewelry_id,
            qty=bj.quantity,
        )
        db.add(hc_jewelry)
        db.flush()
        # Create OrderItemLink for jewelry
        link = OrderItemLink(
            order_id=order_id,
            handcraft_jewelry_item_id=hc_jewelry.id,
        )
        db.add(link)

    # Update batch
    batch.handcraft_order_id = hc_id
    db.flush()

    return {"handcraft_order_id": hc_id}
```

Add import at top: `from models.handcraft_order import HandcraftPartItem`

- [ ] **Step 4: Add API endpoint**

Add to `api/orders.py`:

```python
from services.order_todo import link_supplier
from schemas.order import LinkSupplierRequest

@router.post("/{order_id}/todo-batch/{batch_id}/link-supplier")
def link_batch_supplier(
    order_id: str,
    batch_id: int,
    req: LinkSupplierRequest,
    db: Session = Depends(get_db),
):
    with service_errors():
        return link_supplier(db, order_id, batch_id, req.supplier_name)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_api_order_todo.py::test_link_supplier_creates_handcraft_order tests/test_api_order_todo.py::test_link_supplier_already_linked -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/order_todo.py api/orders.py tests/test_api_order_todo.py
git commit -m "feat: add link-supplier endpoint to create handcraft order from batch"
```

---

## Task 7: Service — Updated Progress + Parts Summary

**Files:**
- Modify: `services/order_todo.py` (get_order_progress)
- Modify: `services/order.py` (get_parts_summary)
- Modify: `api/orders.py`
- Test: `tests/test_api_order_todo.py`

- [ ] **Step 1: Write failing tests**

```python
def test_order_progress_new_logic(client, db):
    """Progress: x = 完成备货 jewelry count, y = distinct jewelry count."""
    parts, jewelry, order = _setup_order_with_bom(db)
    # No jewelry stock → 0 completed
    resp = client.get(f"/api/orders/{order.id}/progress")
    assert resp.status_code == 200
    data = resp.json()
    assert data["completed"] == 0
    assert data["total"] == 1  # 1 distinct jewelry

    # Add enough jewelry stock
    from services.inventory import add_stock
    item = db.query(OrderItem).filter_by(order_id=order.id).first()
    add_stock(db, "jewelry", jewelry.id, item.quantity, "test")
    db.flush()
    resp = client.get(f"/api/orders/{order.id}/progress")
    data = resp.json()
    assert data["completed"] == 1
    assert data["total"] == 1


def test_parts_summary_with_remaining(client, db):
    """Parts summary returns total_qty and remaining_qty."""
    parts, jewelry, order = _setup_order_with_bom(db)
    resp = client.get(f"/api/orders/{order.id}/parts-summary")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    for item in data:
        assert "total_qty" in item
        assert "remaining_qty" in item
        assert "part_id" in item
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_order_todo.py::test_order_progress_new_logic tests/test_api_order_todo.py::test_parts_summary_with_remaining -v`
Expected: FAIL

- [ ] **Step 3: Update `get_order_progress`**

Replace the existing `get_order_progress` function in `services/order_todo.py`:

```python
def get_order_progress(db: Session, order_id: str) -> dict:
    """Get order stocking progress.

    x = jewelry items with status '完成备货'
    y = distinct jewelry types in the order
    """
    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        raise ValueError(f"订单 {order_id} 不存在")

    statuses = get_jewelry_status(db, order_id)
    total = len(statuses)
    completed = sum(1 for s in statuses if s["status"] == "完成备货")

    return {"order_id": order_id, "total": total, "completed": completed}
```

- [ ] **Step 4: Update `get_parts_summary`**

Replace `get_parts_summary` in `services/order.py` to return enriched list instead of dict:

```python
def get_parts_summary(db: Session, order_id: str) -> list[dict]:
    """Get aggregated parts summary with total and remaining quantities.

    remaining_qty = total_qty minus parts needed by jewelry in
    '等待发往手工', '等待手工返回', '完成备货' statuses.
    """
    from models.bom import Bom
    from models.part import Part
    from services.order_todo import get_jewelry_status

    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        raise ValueError(f"订单 {order_id} 不存在")

    items = db.query(OrderItem).filter_by(order_id=order_id).all()
    if not items:
        return []

    # Calculate total BOM requirements
    total_map: dict[str, float] = {}
    for oi in items:
        bom_rows = db.query(Bom).filter_by(jewelry_id=oi.jewelry_id).all()
        for bom in bom_rows:
            pid = bom.part_id
            total_map[pid] = total_map.get(pid, 0) + float(bom.qty_per_unit) * oi.quantity

    # Calculate deduction for jewelry past '等待配件备齐'
    statuses = get_jewelry_status(db, order_id)
    deduct_statuses = {"等待发往手工", "等待手工返回", "完成备货"}
    deduct_map: dict[str, float] = {}
    item_by_jewelry = {oi.jewelry_id: oi for oi in items}
    for s in statuses:
        if s["status"] in deduct_statuses:
            jid = s["jewelry_id"]
            oi = item_by_jewelry.get(jid)
            if oi:
                bom_rows = db.query(Bom).filter_by(jewelry_id=jid).all()
                for bom in bom_rows:
                    pid = bom.part_id
                    deduct_map[pid] = deduct_map.get(pid, 0) + float(bom.qty_per_unit) * oi.quantity

    # Enrich with part info
    part_ids = list(total_map.keys())
    parts = db.query(Part).filter(Part.id.in_(part_ids)).all() if part_ids else []
    part_info = {p.id: p for p in parts}

    result = []
    for pid, total_qty in total_map.items():
        p = part_info.get(pid)
        remaining = total_qty - deduct_map.get(pid, 0)
        result.append({
            "part_id": pid,
            "part_name": p.name if p else "",
            "part_image": p.image if p else None,
            "total_qty": total_qty,
            "remaining_qty": max(0.0, remaining),
        })

    return result
```

Update the API endpoint in `api/orders.py` — the `get_parts_summary` route should return the new list format directly (it currently returns a dict).

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_api_order_todo.py::test_order_progress_new_logic tests/test_api_order_todo.py::test_parts_summary_with_remaining -v`
Expected: PASS

- [ ] **Step 6: Run existing progress test to check backwards compat**

Run: `pytest tests/test_api_order_todo.py -v -k "progress"`
Expected: Review output — if the old test `test_order_progress` fails due to new logic, update it to match the new behavior (completed now counts jewelry with sufficient stock, not todo items).

- [ ] **Step 7: Commit**

```bash
git add services/order_todo.py services/order.py api/orders.py tests/test_api_order_todo.py
git commit -m "feat: update progress to jewelry-based, add remaining_qty to parts summary"
```

---

## Task 8: Service — Batch PDF Export

**Files:**
- Modify: `services/order_todo_pdf.py`
- Modify: `api/orders.py`
- Test: `tests/test_api_order_todo.py`

- [ ] **Step 1: Write failing test**

```python
def test_download_batch_pdf(client, db):
    """Download PDF for a specific batch."""
    parts, jewelry, order = _setup_order_with_bom(db)
    batch_resp = client.post(
        f"/api/orders/{order.id}/todo-batch",
        json={"jewelry_ids": [jewelry.id]},
    )
    batch_id = batch_resp.json()["id"]
    resp = client.get(f"/api/orders/{order.id}/todo-pdf?batch_id={batch_id}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_order_todo.py::test_download_batch_pdf -v`
Expected: FAIL

- [ ] **Step 3: Modify `build_order_todo_pdf`**

Update the function signature in `services/order_todo_pdf.py` to accept optional `batch_id` and `supplier_name`:

```python
def build_order_todo_pdf(
    db: Session,
    order_id: str,
    customer_name: str,
    created_at,
    batch_id: int | None = None,
    supplier_name: str | None = None,
) -> tuple[bytes, str]:
```

Inside the function, change how `rows` are fetched:

```python
    # Replace the existing get_todo() call with:
    if batch_id is not None:
        from services.order_todo import get_batches
        batches = get_batches(db, order_id)
        batch_data = next((b for b in batches if b["id"] == batch_id), None)
        if not batch_data:
            raise ValueError(f"批次 {batch_id} 不存在")
        rows = batch_data["items"]
        if not supplier_name and batch_data.get("supplier_name"):
            supplier_name = batch_data["supplier_name"]
    else:
        rows = get_todo(db, order_id)
```

In the header drawing section, after the line that draws customer name and date, add:

```python
    # After the existing info line, add supplier line if present:
    if supplier_name:
        c.setFont(FONT_NAME, 9)
        c.drawString(LEFT, y, f"指定手工：{supplier_name}")
        y -= 16
```

- [ ] **Step 4: Update PDF API endpoint**

Modify the existing todo-pdf endpoint in `api/orders.py` to accept optional `batch_id` query param:

```python
@router.get("/{order_id}/todo-pdf")
def download_todo_pdf(
    order_id: str,
    batch_id: int | None = None,
    db: Session = Depends(get_db),
):
    with service_errors():
        order = get_order(db, order_id)
        pdf_bytes, filename = build_order_todo_pdf(
            db,
            order_id,
            order.customer_name,
            order.created_at,
            batch_id=batch_id,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
```

- [ ] **Step 5: Run test**

Run: `pytest tests/test_api_order_todo.py::test_download_batch_pdf -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/order_todo_pdf.py api/orders.py tests/test_api_order_todo.py
git commit -m "feat: support batch-level PDF export with supplier header"
```

---

## Task 9: Frontend — API Functions + OrderList Progress

**Files:**
- Modify: `frontend/src/api/orders.js`
- Modify: `frontend/src/views/orders/OrderList.vue`

- [ ] **Step 1: Add new API functions**

Add to `frontend/src/api/orders.js`:

```javascript
export function getJewelryStatus(orderId) {
  return request.get(`/orders/${orderId}/jewelry-status`)
}

export function getJewelryForBatch(orderId) {
  return request.get(`/orders/${orderId}/jewelry-for-batch`)
}

export function createTodoBatch(orderId, jewelryIds) {
  return request.post(`/orders/${orderId}/todo-batch`, { jewelry_ids: jewelryIds })
}

export function getTodoBatches(orderId) {
  return request.get(`/orders/${orderId}/todo-batches`)
}

export function linkBatchSupplier(orderId, batchId, supplierName) {
  return request.post(`/orders/${orderId}/todo-batch/${batchId}/link-supplier`, {
    supplier_name: supplierName,
  })
}

export function downloadBatchPdf(orderId, batchId) {
  return request.get(`/orders/${orderId}/todo-pdf`, {
    params: { batch_id: batchId },
    responseType: 'blob',
  })
}
```

- [ ] **Step 2: Update OrderList progress label**

In `frontend/src/views/orders/OrderList.vue`, find the column definition for "备料进度" and rename to "备货进度". The existing `getProgress()` API call remains the same — the backend logic already returns the new calculation.

- [ ] **Step 3: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/orders.js frontend/src/views/orders/OrderList.vue
git commit -m "feat: add batch API functions, rename progress label to 备货进度"
```

---

## Task 10: Frontend — Jewelry Status Column

**Files:**
- Modify: `frontend/src/views/orders/OrderDetail.vue`

- [ ] **Step 1: Add jewelry status state and fetch**

In the `<script setup>` section, add:

```javascript
import { getJewelryStatus } from '@/api/orders'

const jewelryStatusMap = ref({})

async function loadJewelryStatus() {
  const { data } = await getJewelryStatus(orderId.value)
  const map = {}
  for (const item of data) {
    map[item.jewelry_id] = item.status
  }
  jewelryStatusMap.value = map
}
```

Call `loadJewelryStatus()` in the existing `onMounted` or data loading function.

- [ ] **Step 2: Add status column to order items table**

In the order items table columns definition, add a new column between the "操作" and "备注" columns:

```javascript
{
  title: '状态',
  key: 'status',
  align: 'center',
  width: 140,
  render(row) {
    const status = jewelryStatusMap.value[row.jewelry_id]
    const colorMap = {
      '等待配件备齐': { color: '#fa8c16', bg: '#fff7e6' },
      '等待发往手工': { color: '#13c2c2', bg: '#e6fffb' },
      '等待手工返回': { color: '#1890ff', bg: '#e6f7ff' },
      '完成备货': { color: '#52c41a', bg: '#f6ffed' },
    }
    const c = colorMap[status] || { color: '#999', bg: '#f5f5f5' }
    return h(NTag, {
      size: 'small',
      bordered: false,
      style: { color: c.color, backgroundColor: c.bg },
    }, { default: () => status || '—' })
  },
}
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/orders/OrderDetail.vue
git commit -m "feat: add jewelry status column to order items table"
```

---

## Task 11: Frontend — Batch Select Modal + Collapsible Structure

**Files:**
- Modify: `frontend/src/views/orders/OrderDetail.vue`

This is the largest frontend task. It replaces the flat todo list with the batch-based collapsible structure.

- [ ] **Step 1: Add batch-related state**

```javascript
import {
  getJewelryForBatch, createTodoBatch, getTodoBatches,
  linkBatchSupplier, downloadBatchPdf,
} from '@/api/orders'

const batches = ref([])
const expandedBatchIds = ref(new Set())
const showBatchModal = ref(false)
const batchJewelryList = ref([])
const selectedJewelryIds = ref([])
const batchGenerating = ref(false)

async function loadBatches() {
  const { data } = await getTodoBatches(orderId.value)
  batches.value = data.batches
}

async function loadJewelryForBatch() {
  const { data } = await getJewelryForBatch(orderId.value)
  batchJewelryList.value = data
}
```

- [ ] **Step 2: Implement batch select modal**

Add modal template in the `<template>` section. Use Naive UI's `<n-modal>` component:

```html
<n-modal v-model:show="showBatchModal" preset="card" title="选择饰品生成配件清单" style="width: 620px;">
  <n-data-table
    :columns="batchSelectColumns"
    :data="batchJewelryList"
    :row-key="row => row.jewelry_id"
    :row-class-name="row => row.selectable ? '' : 'row-disabled'"
    v-model:checked-row-keys="selectedJewelryIds"
    size="small"
  />
  <template #footer>
    <n-space justify="end">
      <n-button @click="showBatchModal = false">取消</n-button>
      <n-button type="primary" :loading="batchGenerating" :disabled="selectedJewelryIds.length === 0" @click="confirmCreateBatch">
        生成配件清单
      </n-button>
    </n-space>
  </template>
</n-modal>
```

Define `batchSelectColumns` with: checkbox (selectable rows only), jewelry_id, jewelry (image + name), quantity (showing remaining if partially allocated).

Implement `confirmCreateBatch`:
```javascript
async function confirmCreateBatch() {
  const confirmed = await dialog.warning({
    title: '确认',
    content: '会根据已选择的饰品生成指定的配件清单，确定要生成吗？',
    positiveText: '确定',
    negativeText: '取消',
  })
  if (!confirmed) return
  batchGenerating.value = true
  try {
    await createTodoBatch(orderId.value, selectedJewelryIds.value)
    showBatchModal.value = false
    await loadBatches()
    await loadJewelryStatus()
  } finally {
    batchGenerating.value = false
  }
}
```

- [ ] **Step 3: Implement collapsible batch structure**

Replace the existing flat todo list section with the batch-based structure:

```html
<n-card title="配件清单">
  <template #header-extra>
    <n-button type="primary" @click="openBatchModal">生成指定配件清单</n-button>
  </template>

  <div v-for="batch in batches" :key="batch.id" class="batch-row">
    <!-- Big row (header) -->
    <div class="batch-header" @click="toggleBatch(batch.id)">
      <div class="batch-header-left">
        <n-icon :component="expandedBatchIds.has(batch.id) ? ChevronDown : ChevronRight" />
        <span class="batch-title">批次 {{ batch.id }}</span>
        <span class="batch-date">{{ formatDate(batch.created_at) }}</span>
      </div>
      <div class="batch-header-right" @click.stop>
        <n-button size="small" @click="doBatchPdfExport(batch)">导出 PDF</n-button>
        <template v-if="batch.supplier_name">
          <n-tag type="success" :bordered="false" strong>✓ 已分配给：{{ batch.supplier_name }}</n-tag>
        </template>
        <template v-else>
          <n-button size="small" type="primary" @click="openSupplierModal(batch)">关联手工商家</n-button>
        </template>
      </div>
    </div>

    <!-- Small row (detail), with transition -->
    <n-collapse-transition :show="expandedBatchIds.has(batch.id)">
      <div class="batch-detail">
        <!-- Jewelry header row -->
        <div class="batch-jewelry-row">
          <div v-for="j in batch.jewelries" :key="j.jewelry_id" class="jewelry-card"
               @mouseenter="startHover(j, $event)" @mouseleave="cancelHover()">
            <n-image :src="j.jewelry_image" width="64" height="64" object-fit="cover" fallback-src="/placeholder.png" />
            <div class="jewelry-card-label">{{ j.jewelry_id }}</div>
          </div>
        </div>
        <!-- Parts detail table -->
        <n-data-table :columns="batchItemColumns" :data="batch.items" size="small" />
      </div>
    </n-collapse-transition>
  </div>

  <n-empty v-if="batches.length === 0" description="暂无配件清单，点击上方按钮生成" />
</n-card>
```

- [ ] **Step 4: Implement hover tooltip for jewelry cards**

Use a reactive ref for the popover. When the user hovers on a jewelry card for >1s, compute that jewelry's BOM parts from the batch items:

```javascript
const hoverTimer = ref(null)
const hoverJewelry = ref(null)
const hoverPosition = ref({ x: 0, y: 0 })

function startHover(jewelry, event) {
  cancelHover()
  hoverTimer.value = setTimeout(() => {
    hoverJewelry.value = jewelry
    hoverPosition.value = { x: event.clientX, y: event.clientY }
  }, 1000)
}

function cancelHover() {
  if (hoverTimer.value) clearTimeout(hoverTimer.value)
  hoverJewelry.value = null
}
```

Render the tooltip as a floating div positioned near the cursor showing: part name, needed qty, stock qty, gap.

- [ ] **Step 5: Implement batch PDF export**

```javascript
async function doBatchPdfExport(batch) {
  const { data } = await downloadBatchPdf(orderId.value, batch.id)
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = `配件清单_${orderId.value}_批次${batch.id}.pdf`
  a.click()
  URL.revokeObjectURL(url)
}
```

- [ ] **Step 6: Add CSS for batch structure**

```css
.batch-row {
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  margin-bottom: 8px;
}
.batch-header {
  padding: 12px 16px;
  background: #fafafa;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  border-radius: 6px;
}
.batch-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.batch-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.batch-detail {
  padding: 16px;
}
.batch-jewelry-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.jewelry-card {
  text-align: center;
  cursor: pointer;
}
.jewelry-card-label {
  font-size: 11px;
  color: #666;
  margin-top: 4px;
}
.row-disabled {
  opacity: 0.45;
}
```

- [ ] **Step 7: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/orders/OrderDetail.vue
git commit -m "feat: add batch select modal and collapsible batch structure"
```

---

## Task 12: Frontend — Supplier Modal + BOM Update

**Files:**
- Modify: `frontend/src/views/orders/OrderDetail.vue`

- [ ] **Step 1: Add supplier modal state and template**

```javascript
const showSupplierModal = ref(false)
const supplierBatchId = ref(null)
const supplierName = ref('')
const supplierOptions = ref([])
const linkingSupplier = ref(false)

function openSupplierModal(batch) {
  supplierBatchId.value = batch.id
  supplierName.value = ''
  showSupplierModal.value = true
  loadSuppliers()
}

async function loadSuppliers() {
  // Fetch existing handcraft suppliers
  const { data } = await request.get('/suppliers', { params: { type: 'handcraft' } })
  supplierOptions.value = data.map(s => ({ label: s.name, value: s.name }))
}

async function confirmLinkSupplier() {
  if (!supplierName.value.trim()) return
  linkingSupplier.value = true
  try {
    const { data } = await linkBatchSupplier(orderId.value, supplierBatchId.value, supplierName.value.trim())
    showSupplierModal.value = false
    // Navigate to handcraft order detail
    router.push(`/handcraft/${data.handcraft_order_id}`)
  } finally {
    linkingSupplier.value = false
  }
}
```

Template:
```html
<n-modal v-model:show="showSupplierModal" preset="card" title="关联手工商家" style="width: 440px;">
  <n-auto-complete
    v-model:value="supplierName"
    :options="supplierOptions"
    placeholder="输入商家名称"
    clearable
  />
  <div style="font-size: 12px; color: #999; margin-top: 6px;">输入商家名称，可选择已有商家或自动新建</div>
  <template #footer>
    <n-space justify="end">
      <n-button @click="showSupplierModal = false">取消</n-button>
      <n-button type="primary" :loading="linkingSupplier" :disabled="!supplierName.trim()" @click="confirmLinkSupplier">
        确定
      </n-button>
    </n-space>
  </template>
</n-modal>
```

- [ ] **Step 2: Update BOM summary section**

Replace the existing parts summary section to show both `total_qty` and `remaining_qty`:

```javascript
const partsSummaryColumns = [
  { title: '配件编号', key: 'part_id' },
  {
    title: '配件',
    key: 'part_name',
    render(row) {
      return h('div', { style: 'display:flex;align-items:center;gap:6px' }, [
        row.part_image ? h(NImage, { src: row.part_image, width: 28, height: 28, objectFit: 'cover' }) : null,
        row.part_name,
      ])
    },
  },
  { title: '总需求量', key: 'total_qty', align: 'center' },
  {
    title: '剩余需求量',
    key: 'remaining_qty',
    align: 'center',
    render(row) {
      const color = row.remaining_qty > 0 ? '#ff4d4f' : '#52c41a'
      return h('span', { style: { color, fontWeight: 500 } }, row.remaining_qty)
    },
  },
]
```

Update the parts summary data loading to use the new response format (list of objects instead of dict).

- [ ] **Step 3: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/orders/OrderDetail.vue
git commit -m "feat: add supplier modal and update BOM summary with remaining qty"
```

---

## Task 13: Run All Tests + Fix Regressions

**Files:**
- Possibly modify: `tests/test_api_order_todo.py`, `tests/test_api_parts.py`

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`
Expected: Review output for any regressions

- [ ] **Step 2: Fix any broken tests**

The `get_parts_summary` return type changed from `dict` to `list[dict]`. Update any existing tests that depend on the old format. Also update the old `test_order_progress` test if it expects the old logic (total = todo item count).

- [ ] **Step 3: Run full test suite again**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 4: Commit fixes if any**

```bash
git add tests/
git commit -m "fix: update existing tests for new progress and parts summary formats"
```

---

## Task 14: Final Verification

- [ ] **Step 1: Start backend and verify endpoints**

Run: `python main.py`
Test manually with curl or browser:
- `GET /api/orders/{id}/jewelry-status`
- `GET /api/orders/{id}/jewelry-for-batch`
- `POST /api/orders/{id}/todo-batch` with `{"jewelry_ids": [...]}`
- `GET /api/orders/{id}/todo-batches`
- `POST /api/orders/{id}/todo-batch/{batch_id}/link-supplier` with `{"supplier_name": "..."}`
- `GET /api/orders/{id}/progress`
- `GET /api/orders/{id}/parts-summary`

- [ ] **Step 2: Start frontend and verify UI**

Run: `cd frontend && npm run dev`
Verify:
- Jewelry status column displays correctly
- 【生成指定配件清单】button opens modal
- Batch collapsible structure works
- Supplier linking navigates to handcraft order
- PDF export works per batch
- BOM summary shows both columns
- OrderList shows "备货进度" with new logic

- [ ] **Step 3: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "chore: final cleanup for parts list optimization"
```
