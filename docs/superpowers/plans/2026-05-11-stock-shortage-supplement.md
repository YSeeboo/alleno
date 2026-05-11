# Stock Shortage 一键补进并发出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "一键补进并发出" flow on handcraft (HC) and plating (EP) order send. When stock is insufficient, the existing 库存不足 dialog gains a new button that, after a second-confirmation dialog, atomically supplements the shortfall and re-sends the order in one backend transaction.

**Architecture:**
- Backend: one shared helper `supplement_shortfall()` in `services/inventory.py`; two order-type-specific service functions that wrap it + the existing `send_*_order`; one new API endpoint per order type.
- Frontend: one shared composable `useSendWithStockSupplement` replaces the duplicated `doSend` in `HandcraftDetail.vue` and `PlatingDetail.vue`. Composable handles the two-dialog flow (shortage list → confirmation → API call → toast).
- Atomicity: backend supplement + send live in the same `get_db()` transaction; any failure rolls back both.
- Re-query strategy: frontend queries `batchGetStock` before showing the confirmation dialog (user preview); backend re-queries inside `supplement_shortfall` (actual execution).

**Tech Stack:** FastAPI + SQLAlchemy 2.x + Pydantic v2 (backend); Vue 3.5 + Naive UI + Vite (frontend); pytest for backend tests.

**Spec reference:** `docs/superpowers/specs/2026-05-11-stock-shortage-supplement-design.md`

**Reason / note convention (inventory_log):**
| Order type | reason | note |
|---|---|---|
| 手工单 | `"手工单缺货补进"` | order_id (e.g. `"HC-0042"`) |
| 电镀单 | `"电镀单缺货补进"` | order_id (e.g. `"EP-0042"`) |

---

## File Structure

**Backend — modified / created:**
- `services/inventory.py` — append `supplement_shortfall()`
- `services/handcraft.py` — append `supplement_and_send_handcraft_order()`
- `services/plating.py` — append `supplement_and_send_plating_order()`
- `schemas/handcraft.py` — append `SupplementAndSendHandcraftResponse`
- `schemas/plating.py` — append `SupplementAndSendPlatingResponse`
- `api/handcraft.py` — append `POST /{order_id}/supplement-and-send` route
- `api/plating.py` — append `POST /{order_id}/supplement-and-send` route

**Backend — tests:**
- `tests/test_inventory.py` — 2 new tests for `supplement_shortfall`
- `tests/test_handcraft.py` — 7 new tests for `supplement_and_send_handcraft_order`
- `tests/test_plating.py` — 6 new tests for `supplement_and_send_plating_order`
- `tests/test_api_handcraft.py` — 1 happy-path API test
- `tests/test_api_plating.py` — 1 happy-path API test

**Frontend — new:**
- `frontend/src/composables/useSendWithStockSupplement.js` — new file

**Frontend — modified:**
- `frontend/src/api/handcraft.js` — add `supplementAndSendHandcraft`
- `frontend/src/api/plating.js` — add `supplementAndSendPlating`
- `frontend/src/views/handcraft/HandcraftDetail.vue` — replace inline `doSend` (lines 950–987) with composable
- `frontend/src/views/plating/PlatingDetail.vue` — replace inline `doSend` (lines 765–802) with composable

---

## Task 1: Backend helper — `supplement_shortfall()`

**Files:**
- Modify: `services/inventory.py` (append new function at end of file)
- Test: `tests/test_inventory.py` (append 2 new tests)

The helper takes a `{item_id: needed_qty}` dict, re-queries current stock via `batch_get_stock`, and for each item where `needed > current` calls `add_stock` with the supplied reason/note. Returns a dict of items it actually supplemented (skipping the ones already in stock).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_inventory.py`:

```python
def test_supplement_shortfall_skips_when_enough(db):
    from services.inventory import supplement_shortfall, add_stock, get_stock
    from services.part import create_part
    p = create_part(db, {"name": "扣子", "category": "小配件"})
    add_stock(db, "part", p.id, 100.0, "入库")
    result = supplement_shortfall(
        db, "part", {p.id: 50.0}, reason="手工单缺货补进", note="HC-0001"
    )
    assert result == {}
    assert get_stock(db, "part", p.id) == 100.0  # unchanged


def test_supplement_shortfall_partial(db):
    from services.inventory import supplement_shortfall, add_stock, get_stock
    from services.part import create_part
    p1 = create_part(db, {"name": "扣子", "category": "小配件"})
    p2 = create_part(db, {"name": "链", "category": "链条"})
    p3 = create_part(db, {"name": "吊", "category": "吊坠"})
    add_stock(db, "part", p1.id, 100.0, "入库")   # enough for needs=50
    add_stock(db, "part", p2.id, 30.0, "入库")    # short for needs=50 by 20
    # p3 has zero stock; needs=10 → supplement 10
    result = supplement_shortfall(
        db, "part",
        {p1.id: 50.0, p2.id: 50.0, p3.id: 10.0},
        reason="手工单缺货补进", note="HC-0001",
    )
    assert result == {p2.id: 20.0, p3.id: 10.0}
    assert get_stock(db, "part", p1.id) == 100.0
    assert get_stock(db, "part", p2.id) == 50.0   # 30 + 20
    assert get_stock(db, "part", p3.id) == 10.0
    # Verify the log entries are tagged correctly
    from models.inventory_log import InventoryLog
    logs = (
        db.query(InventoryLog)
        .filter(InventoryLog.reason == "手工单缺货补进")
        .order_by(InventoryLog.id)
        .all()
    )
    assert [(l.item_id, float(l.change_qty), l.note) for l in logs] == [
        (p2.id, 20.0, "HC-0001"),
        (p3.id, 10.0, "HC-0001"),
    ]
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_inventory.py::test_supplement_shortfall_skips_when_enough tests/test_inventory.py::test_supplement_shortfall_partial -v`
Expected: FAIL with `ImportError: cannot import name 'supplement_shortfall'` (or similar).

- [ ] **Step 3: Implement `supplement_shortfall`**

Append to `services/inventory.py`:

```python
def supplement_shortfall(
    db: Session,
    item_type: str,
    needs: dict[str, float],
    reason: str,
    note: str | None = None,
) -> dict[str, float]:
    """Re-query current stock for each item; for any where needed > current,
    call add_stock for the gap. Returns {item_id: gap} for items actually
    supplemented (callers can show this to users). Items already at or above
    needed are skipped (no log written).
    """
    if not needs:
        return {}
    stocks = batch_get_stock(db, item_type, list(needs.keys()))
    supplemented: dict[str, float] = {}
    for item_id, needed in needs.items():
        current = stocks.get(item_id, 0.0)
        gap = float(needed) - float(current)
        if gap > 0:
            add_stock(db, item_type, item_id, gap, reason, note)
            supplemented[item_id] = gap
    return supplemented
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_inventory.py::test_supplement_shortfall_skips_when_enough tests/test_inventory.py::test_supplement_shortfall_partial -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add services/inventory.py tests/test_inventory.py
git commit -m "feat(inventory): add supplement_shortfall helper

Reusable helper that re-queries stock and adds the shortfall for
each item where needed > current, with a configurable reason/note.
Returns the dict of items actually supplemented so callers can
report it to the user."
```

---

## Task 2: Backend service — `supplement_and_send_handcraft_order()`

**Files:**
- Modify: `services/handcraft.py` (append new function after `send_handcraft_order`)
- Test: `tests/test_handcraft.py` (append 7 new tests)

Wraps `supplement_shortfall(reason="手工单缺货补进", note=order_id)` + the existing `send_handcraft_order`. Returns `(order, supplemented_dict)`. All validation lives in `send_handcraft_order`; this function only computes part_totals first to feed into the supplement helper.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_handcraft.py`:

```python
def test_supplement_and_send_normal(setup):
    """1 part short by 5; supplement should write 1 缺货补进 log + 1 手工发出 log."""
    from services.handcraft import supplement_and_send_handcraft_order
    from services.inventory import get_stock
    from models.inventory_log import InventoryLog
    db, p1, _, j1 = setup  # p1 has 200 stock from fixture
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 205, "bom_qty": 200.0}],  # short by 5
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
    )
    result_order, supplemented = supplement_and_send_handcraft_order(db, order.id)
    assert result_order.status == "processing"
    assert supplemented == {p1.id: 5.0}
    assert get_stock(db, "part", p1.id) == 0.0  # 200 + 5 - 205

    logs = (
        db.query(InventoryLog)
        .filter(InventoryLog.item_id == p1.id)
        .order_by(InventoryLog.id)
        .all()
    )
    # ① 入库 200 (fixture) ② 手工单缺货补进 +5 (HC-...) ③ 手工发出 -205
    reasons = [(l.reason, float(l.change_qty), l.note) for l in logs]
    assert reasons[1] == ("手工单缺货补进", 5.0, order.id)
    assert reasons[2][0] == "手工发出"
    assert reasons[2][1] == -205.0


def test_supplement_and_send_no_shortage(setup):
    """Stock is already enough; supplement is skipped, only 手工发出 log written."""
    from services.handcraft import supplement_and_send_handcraft_order
    from services.inventory import get_stock
    from models.inventory_log import InventoryLog
    db, p1, _, j1 = setup  # p1 has 200 stock
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50, "bom_qty": 50.0}],
        jewelries=[{"jewelry_id": j1.id, "qty": 5}],
    )
    result_order, supplemented = supplement_and_send_handcraft_order(db, order.id)
    assert result_order.status == "processing"
    assert supplemented == {}
    assert get_stock(db, "part", p1.id) == 150.0
    assert db.query(InventoryLog).filter(
        InventoryLog.reason == "手工单缺货补进"
    ).count() == 0


def test_supplement_and_send_multi_parts(setup):
    """3 parts: 2 short, 1 enough. Only the 2 short ones get supplemented."""
    from services.handcraft import supplement_and_send_handcraft_order
    db, p1, p2, j1 = setup  # p1=200, p2=100
    # Create a third part with zero stock
    from services.part import create_part
    p3 = create_part(db, {"name": "扣子3", "category": "小配件"})
    order = create_handcraft_order(
        db, "手工坊",
        parts=[
            {"part_id": p1.id, "qty": 50},    # enough
            {"part_id": p2.id, "qty": 150},   # short by 50
            {"part_id": p3.id, "qty": 20},    # short by 20
        ],
        jewelries=[{"jewelry_id": j1.id, "qty": 5}],
    )
    _, supplemented = supplement_and_send_handcraft_order(db, order.id)
    assert supplemented == {p2.id: 50.0, p3.id: 20.0}


def test_supplement_and_send_aggregates_same_part(setup):
    """Same part_id in two part_items: supplement uses the aggregate total."""
    from services.handcraft import supplement_and_send_handcraft_order
    from services.inventory import get_stock
    db, p1, _, j1 = setup  # p1 has 200
    order = create_handcraft_order(
        db, "手工坊",
        parts=[
            {"part_id": p1.id, "qty": 150},
            {"part_id": p1.id, "qty": 100},   # total need = 250, short by 50
        ],
        jewelries=[{"jewelry_id": j1.id, "qty": 5}],
    )
    _, supplemented = supplement_and_send_handcraft_order(db, order.id)
    assert supplemented == {p1.id: 50.0}
    assert get_stock(db, "part", p1.id) == 0.0  # 200 + 50 - 250


def test_supplement_and_send_order_not_pending(setup):
    """Already-sent order must be rejected."""
    from services.handcraft import supplement_and_send_handcraft_order
    db, p1, _, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50}],
        jewelries=[{"jewelry_id": j1.id, "qty": 5}],
    )
    send_handcraft_order(db, order.id)  # now processing
    with pytest.raises(ValueError, match="cannot be sent"):
        supplement_and_send_handcraft_order(db, order.id)


def test_supplement_and_send_order_not_found(db):
    from services.handcraft import supplement_and_send_handcraft_order
    with pytest.raises(ValueError, match="not found"):
        supplement_and_send_handcraft_order(db, "HC-9999")


def test_supplement_and_send_no_part_items(setup):
    """Order with no part_items must be rejected."""
    from services.handcraft import supplement_and_send_handcraft_order
    from models.handcraft_order import HandcraftOrder
    from time_utils import now_beijing
    db, _, _, _ = setup
    # Create an empty order manually (the normal creator requires parts)
    order = HandcraftOrder(
        id="HC-9000", supplier_name="测试", status="pending", created_at=now_beijing()
    )
    db.add(order)
    db.flush()
    with pytest.raises(ValueError, match="no part items"):
        supplement_and_send_handcraft_order(db, "HC-9000")
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_handcraft.py -v -k supplement_and_send`
Expected: 7 failures with `ImportError: cannot import name 'supplement_and_send_handcraft_order'`.

- [ ] **Step 3: Implement the service function**

Append to `services/handcraft.py` (right after `send_handcraft_order` ends around line 320):

```python
def supplement_and_send_handcraft_order(
    db: Session, handcraft_order_id: str
) -> tuple[HandcraftOrder, dict[str, float]]:
    """Supplement any part-stock shortfall for this order, then immediately
    call send_handcraft_order. Returns (order, supplemented) where
    supplemented is {part_id: qty} for parts that needed补进 (may be empty).
    All validation lives in send_handcraft_order; failures roll back.
    """
    order = get_handcraft_order(db, handcraft_order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {handcraft_order_id}")
    if order.status != "pending":
        raise ValueError(
            f"HandcraftOrder {handcraft_order_id} cannot be sent: "
            f"current status is '{order.status}'"
        )
    part_items = (
        db.query(HandcraftPartItem)
        .filter(HandcraftPartItem.handcraft_order_id == handcraft_order_id)
        .all()
    )
    if not part_items:
        raise ValueError(
            f"HandcraftOrder {handcraft_order_id} has no part items "
            f"and cannot be sent"
        )
    part_totals: dict[str, float] = {}
    for item in part_items:
        part_totals[item.part_id] = part_totals.get(item.part_id, 0.0) + float(item.qty)
    supplemented = supplement_shortfall(
        db, "part", part_totals,
        reason="手工单缺货补进",
        note=handcraft_order_id,
    )
    order = send_handcraft_order(db, handcraft_order_id)
    return order, supplemented
```

Add the import at the top of `services/handcraft.py` if `supplement_shortfall` isn't already imported. Check the existing imports block — `services/handcraft.py` imports from `services.inventory` already (verify with `grep "from services.inventory" services/handcraft.py`); just append `supplement_shortfall` to that import list.

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_handcraft.py -v -k supplement_and_send`
Expected: 7 passed.

Run the rest of the file to make sure nothing regressed: `pytest tests/test_handcraft.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add services/handcraft.py tests/test_handcraft.py
git commit -m "feat(handcraft): add supplement_and_send_handcraft_order

Wraps supplement_shortfall + send_handcraft_order in one logical
unit. Used by the new POST /handcraft/{id}/supplement-and-send
endpoint to atomically补进 part shortfalls and send the order.

Inventory log uses reason='手工单缺货补进', note=order_id so the
operation can be filtered out of normal入库 entries."
```

---

## Task 3: Backend service — `supplement_and_send_plating_order()`

**Files:**
- Modify: `services/plating.py` (append new function after `send_plating_order`)
- Test: `tests/test_plating.py` (append 6 new tests)

Mirror of Task 2 for plating orders. Differences: `reason="电镀单缺货补进"`, no jewelry items, item model is `PlatingOrderItem`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plating.py`:

```python
def test_supplement_and_send_normal(setup):
    """1 part short by 5; supplement should write 1 缺货补进 log + 1 电镀发出 log."""
    from services.plating import supplement_and_send_plating_order
    from services.inventory import get_stock
    from models.inventory_log import InventoryLog
    db, p1, _ = setup  # p1 has 200 stock from fixture
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 205, "plating_method": "金色"},  # short by 5
    ])
    result_order, supplemented = supplement_and_send_plating_order(db, order.id)
    assert result_order.status == "processing"
    assert supplemented == {p1.id: 5.0}
    assert get_stock(db, "part", p1.id) == 0.0  # 200 + 5 - 205
    logs = (
        db.query(InventoryLog)
        .filter(InventoryLog.item_id == p1.id)
        .order_by(InventoryLog.id)
        .all()
    )
    reasons = [(l.reason, float(l.change_qty), l.note) for l in logs]
    assert reasons[1] == ("电镀单缺货补进", 5.0, order.id)
    assert reasons[2][0] == "电镀发出"
    assert reasons[2][1] == -205.0


def test_supplement_and_send_no_shortage(setup):
    from services.plating import supplement_and_send_plating_order
    from services.inventory import get_stock
    from models.inventory_log import InventoryLog
    db, p1, _ = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 50, "plating_method": "金色"},
    ])
    _, supplemented = supplement_and_send_plating_order(db, order.id)
    assert supplemented == {}
    assert get_stock(db, "part", p1.id) == 150.0
    assert db.query(InventoryLog).filter(
        InventoryLog.reason == "电镀单缺货补进"
    ).count() == 0


def test_supplement_and_send_multi_parts(setup):
    from services.plating import supplement_and_send_plating_order
    from services.part import create_part
    db, p1, p2 = setup  # p1=200, p2=100
    p3 = create_part(db, {"name": "扣3", "category": "小配件"})
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 50, "plating_method": "金色"},   # enough
        {"part_id": p2.id, "qty": 150, "plating_method": "金色"},  # short 50
        {"part_id": p3.id, "qty": 20, "plating_method": "金色"},   # short 20
    ])
    _, supplemented = supplement_and_send_plating_order(db, order.id)
    assert supplemented == {p2.id: 50.0, p3.id: 20.0}


def test_supplement_and_send_aggregates_same_part(setup):
    from services.plating import supplement_and_send_plating_order
    from services.inventory import get_stock
    db, p1, _ = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 150, "plating_method": "金色"},
        {"part_id": p1.id, "qty": 100, "plating_method": "银色"},
    ])
    _, supplemented = supplement_and_send_plating_order(db, order.id)
    assert supplemented == {p1.id: 50.0}
    assert get_stock(db, "part", p1.id) == 0.0


def test_supplement_and_send_order_not_pending(setup):
    from services.plating import supplement_and_send_plating_order
    db, p1, _ = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 50, "plating_method": "金色"},
    ])
    send_plating_order(db, order.id)
    with pytest.raises(ValueError, match="cannot be sent"):
        supplement_and_send_plating_order(db, order.id)


def test_supplement_and_send_order_not_found(db):
    from services.plating import supplement_and_send_plating_order
    with pytest.raises(ValueError, match="not found"):
        supplement_and_send_plating_order(db, "EP-9999")
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_plating.py -v -k supplement_and_send`
Expected: 6 failures with import error.

- [ ] **Step 3: Implement the service function**

Append to `services/plating.py` (right after `send_plating_order` ends around line 121):

```python
def supplement_and_send_plating_order(
    db: Session, plating_order_id: str
) -> tuple[PlatingOrder, dict[str, float]]:
    """Supplement any part-stock shortfall for this plating order, then
    call send_plating_order. Mirror of supplement_and_send_handcraft_order.
    Returns (order, supplemented_dict).
    """
    order = get_plating_order(db, plating_order_id)
    if order is None:
        raise ValueError(f"PlatingOrder not found: {plating_order_id}")
    if order.status != "pending":
        raise ValueError(
            f"PlatingOrder {plating_order_id} cannot be sent: "
            f"current status is '{order.status}'"
        )
    items = (
        db.query(PlatingOrderItem)
        .filter(PlatingOrderItem.plating_order_id == plating_order_id)
        .all()
    )
    if not items:
        raise ValueError(
            f"PlatingOrder {plating_order_id} has no items and cannot be sent"
        )
    part_totals: dict[str, float] = {}
    for it in items:
        part_totals[it.part_id] = part_totals.get(it.part_id, 0.0) + float(it.qty)
    supplemented = supplement_shortfall(
        db, "part", part_totals,
        reason="电镀单缺货补进",
        note=plating_order_id,
    )
    order = send_plating_order(db, plating_order_id)
    return order, supplemented
```

Add `supplement_shortfall` to the existing `from services.inventory import …` line in `services/plating.py` (verify with `grep "from services.inventory" services/plating.py`).

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_plating.py -v -k supplement_and_send`
Expected: 6 passed.

Run the rest: `pytest tests/test_plating.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add services/plating.py tests/test_plating.py
git commit -m "feat(plating): add supplement_and_send_plating_order

Mirror of supplement_and_send_handcraft_order. Used by the new
POST /plating/{id}/supplement-and-send endpoint.

Inventory log uses reason='电镀单缺货补进', note=order_id."
```

---

## Task 4: Schemas — `SupplementAndSendHandcraftResponse` + `SupplementAndSendPlatingResponse`

**Files:**
- Modify: `schemas/handcraft.py`
- Modify: `schemas/plating.py`

These schemas wrap the existing order response with the `supplemented` dict so the frontend can show the user "实际补进了 N 件".

- [ ] **Step 1: Append to `schemas/handcraft.py`** (anywhere after `HandcraftResponse`, e.g. right after `HandcraftDeliveryImagesUpdate` around line 106)

```python
class SupplementAndSendHandcraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order: HandcraftResponse
    supplemented: dict[str, float] = Field(default_factory=dict)
```

- [ ] **Step 2: Append to `schemas/plating.py`** (after `PlatingDeliveryImagesUpdate` around line 88)

```python
class SupplementAndSendPlatingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order: PlatingResponse
    supplemented: dict[str, float] = Field(default_factory=dict)
```

- [ ] **Step 3: Sanity check — import both schemas in a Python REPL**

Run:
```bash
python -c "from schemas.handcraft import SupplementAndSendHandcraftResponse; from schemas.plating import SupplementAndSendPlatingResponse; print('ok')"
```
Expected output: `ok`

- [ ] **Step 4: Commit**

```bash
git add schemas/handcraft.py schemas/plating.py
git commit -m "feat(schemas): add SupplementAndSend response schemas

Wraps the order response with the supplemented dict so the frontend
can tell the user how many parts were just补进."
```

---

## Task 5: API endpoint — `POST /handcraft/{id}/supplement-and-send`

**Files:**
- Modify: `api/handcraft.py`
- Test: `tests/test_api_handcraft.py` (append 1 new test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api_handcraft.py`:

```python
def test_supplement_and_send_handcraft_order(client, db):
    """Happy path: short by 5 → endpoint returns supplemented={part_id: 5.0}."""
    part = create_part(db, {"name": "P-补", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "J-补", "category": "单件"})
    from services.inventory import add_stock
    add_stock(db, "part", part.id, 5.0, "入库")  # only 5 in stock
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier-补",
        "parts": [{"part_id": part.id, "qty": 10.0}],   # short by 5
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 3}],
    }).json()
    resp = client.post(f"/api/handcraft/{created['id']}/supplement-and-send")
    assert resp.status_code == 200
    data = resp.json()
    assert data["order"]["status"] == "processing"
    assert data["supplemented"] == {part.id: 5.0}


def test_supplement_and_send_handcraft_order_not_found(client, db):
    resp = client.post("/api/handcraft/HC-9999/supplement-and-send")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_api_handcraft.py -v -k supplement_and_send`
Expected: 2 failures (404 → likely 404 already for nonexistent, but the happy path will 404 because the route doesn't exist yet; or 405 method-not-allowed).

- [ ] **Step 3: Add the import and route**

In `api/handcraft.py`:

(a) Extend the `from schemas.handcraft import (...)` block (around lines 12–29) to include `SupplementAndSendHandcraftResponse`. Keep the alphabetical order convention used in that block.

(b) Find the `from services.handcraft import (...)` block (search for it) and add `supplement_and_send_handcraft_order` to it.

(c) Append the new route right after the existing `api_send_handcraft_order` definition (currently ends around line 267):

```python
@router.post(
    "/{order_id}/supplement-and-send",
    response_model=SupplementAndSendHandcraftResponse,
)
def api_supplement_and_send_handcraft_order(order_id: str, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"HandcraftOrder {order_id} not found")
    with service_errors():
        order, supplemented = supplement_and_send_handcraft_order(db, order_id)
    return SupplementAndSendHandcraftResponse(order=order, supplemented=supplemented)
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_api_handcraft.py -v -k supplement_and_send`
Expected: 2 passed.

Run the entire API test file: `pytest tests/test_api_handcraft.py -v`
Expected: no regressions.

- [ ] **Step 5: Commit**

```bash
git add api/handcraft.py tests/test_api_handcraft.py
git commit -m "feat(handcraft-api): add POST /handcraft/{id}/supplement-and-send

Endpoint that supplements part shortfalls and sends the order in
one atomic transaction. Returns the updated order plus the dict
of parts that were actually补进."
```

---

## Task 6: API endpoint — `POST /plating/{id}/supplement-and-send`

**Files:**
- Modify: `api/plating.py`
- Test: `tests/test_api_plating.py` (append 1 new test)

Mirror of Task 5 for plating.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api_plating.py`:

```python
def test_supplement_and_send_plating_order(client, db):
    """Happy path: short by 5 → endpoint returns supplemented={part_id: 5.0}."""
    part = create_part(db, {"name": "P-补-E", "category": "小配件"})
    from services.inventory import add_stock
    add_stock(db, "part", part.id, 5.0, "入库")
    created = client.post("/api/plating/", json={
        "supplier_name": "厂-补",
        "items": [{"part_id": part.id, "qty": 10.0, "plating_method": "金色"}],
    }).json()
    resp = client.post(f"/api/plating/{created['id']}/supplement-and-send")
    assert resp.status_code == 200
    data = resp.json()
    assert data["order"]["status"] == "processing"
    assert data["supplemented"] == {part.id: 5.0}


def test_supplement_and_send_plating_order_not_found(client, db):
    resp = client.post("/api/plating/EP-9999/supplement-and-send")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_api_plating.py -v -k supplement_and_send`
Expected: 2 failures.

- [ ] **Step 3: Add the import and route**

In `api/plating.py`:

(a) Add `SupplementAndSendPlatingResponse` to the `from schemas.plating import (...)` block (lines 12–20).

(b) Add `supplement_and_send_plating_order` to the `from services.plating import (...)` block (around lines 32–…).

(c) Append the new route right after `api_send_plating_order` (currently ends around line 178):

```python
@router.post(
    "/{order_id}/supplement-and-send",
    response_model=SupplementAndSendPlatingResponse,
)
def api_supplement_and_send_plating_order(order_id: str, db: Session = Depends(get_db)):
    order = get_plating_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PlatingOrder {order_id} not found")
    with service_errors():
        order, supplemented = supplement_and_send_plating_order(db, order_id)
    return SupplementAndSendPlatingResponse(order=order, supplemented=supplemented)
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_api_plating.py -v -k supplement_and_send`
Expected: 2 passed.

Run full plating test file: `pytest tests/test_api_plating.py -v`
Expected: no regressions.

- [ ] **Step 5: Commit**

```bash
git add api/plating.py tests/test_api_plating.py
git commit -m "feat(plating-api): add POST /plating/{id}/supplement-and-send

Mirror of the handcraft endpoint for electroplating orders."
```

---

## Task 7: Frontend — API helpers

**Files:**
- Modify: `frontend/src/api/handcraft.js`
- Modify: `frontend/src/api/plating.js`

- [ ] **Step 1: Add `supplementAndSendHandcraft` to `frontend/src/api/handcraft.js`**

Add right after the existing `sendHandcraft` line (line 10):

```js
export const supplementAndSendHandcraft = (id) =>
  api.post(`/handcraft/${id}/supplement-and-send`, null, { _silentError: true })
```

- [ ] **Step 2: Add `supplementAndSendPlating` to `frontend/src/api/plating.js`**

Add right after the existing `sendPlating` line (line 8):

```js
export const supplementAndSendPlating = (id) =>
  api.post(`/plating/${id}/supplement-and-send`, null, { _silentError: true })
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/handcraft.js frontend/src/api/plating.js
git commit -m "feat(frontend-api): add supplementAndSend helpers

Thin wrappers around POST /<type>/{id}/supplement-and-send for both
handcraft and plating orders."
```

---

## Task 8: Frontend composable — `useSendWithStockSupplement.js`

**Files:**
- Create: `frontend/src/composables/useSendWithStockSupplement.js`

Encapsulates the full doSend flow: shortage parsing, two-dialog interaction, batch stock re-query, supplement-and-send call, toast.

- [ ] **Step 1: Create the new file**

Write to `frontend/src/composables/useSendWithStockSupplement.js`:

```js
import { ref, h } from 'vue'
import { NIcon } from 'naive-ui'
import { CopyOutline } from '@vicons/ionicons5'
import { batchGetStock } from '@/api/inventory'

/**
 * Returns { sending, doSend } for an order page that wants the standard
 * 库存不足 → 一键补进并发出 flow.
 *
 * Caller provides:
 *   orderId       — ref/computed -> string (order id, e.g. 'HC-0042')
 *   sendApi       — (id) => Promise            normal send
 *   supplementApi — (id) => Promise<{ data: { supplemented: {pid: qty} } }>
 *   onSuccess     — () => Promise<void>        e.g. loadData() to refresh
 *   message       — useMessage()
 *   dialog        — useDialog()
 */
export function useSendWithStockSupplement({
  orderId,
  sendApi,
  supplementApi,
  onSuccess,
  message,
  dialog,
}) {
  const sending = ref(false)

  const doSend = async () => {
    sending.value = true
    try {
      await sendApi(orderId.value)
      message.success('已确认发出')
      await onSuccess()
    } catch (e) {
      const detail = e.response?.data?.detail || ''
      if (detail.includes('库存不足')) {
        openShortageDialog(detail)
      } else {
        message.error(detail || '发出失败')
      }
    } finally {
      sending.value = false
    }
  }

  const openShortageDialog = (detail) => {
    const items = parseShortageItems(detail)
    dialog.warning({
      title: '库存不足',
      content: () => renderShortageList(items, message),
      negativeText: '知道了',
      positiveText: '一键补进并发出',
      positiveButtonProps: { type: 'warning' },
      onPositiveClick: () => {
        openConfirmDialog(items)
        return true
      },
    })
  }

  const openConfirmDialog = async (items) => {
    const partIds = items.map(it => it.partId).filter(Boolean)
    let stocks = {}
    try {
      const resp = await batchGetStock('part', partIds)
      stocks = resp.data || {}
    } catch (e) {
      message.error('查询库存失败，请重试')
      return
    }
    const shortages = items
      .map(it => ({ partId: it.partId, gap: it.needed - (stocks[it.partId] ?? 0) }))
      .filter(it => it.gap > 0 && it.partId)

    if (shortages.length === 0) {
      await runSupplementAndSend()
      return
    }
    dialog.warning({
      title: '确认补进库存',
      content: () => renderSupplementPreview(shortages, orderId.value),
      negativeText: '取消',
      positiveText: '确认补进并发出',
      positiveButtonProps: { type: 'primary' },
      onPositiveClick: async () => {
        await runSupplementAndSend()
        return true
      },
    })
  }

  const runSupplementAndSend = async () => {
    sending.value = true
    try {
      const resp = await supplementApi(orderId.value)
      const supplemented = resp.data?.supplemented || {}
      const count = Object.keys(supplemented).length
      const total = Object.values(supplemented).reduce((a, b) => a + Number(b), 0)
      if (count === 0) {
        message.success('库存已足，订单已发出')
      } else {
        message.success(`已补进 ${count} 个配件共 ${total} 件，订单已发出`)
      }
      await onSuccess()
    } catch (e) {
      message.error(e.response?.data?.detail || '补进失败')
    } finally {
      sending.value = false
    }
  }

  return { sending, doSend }
}

/**
 * Parse the backend error "库存不足：part PJ-XX 当前库存 X，需要 Y；…" into
 * structured items. Items the regex can't match end up with NaN current/needed
 * but still surface via raw.
 */
function parseShortageItems(detail) {
  const stripped = String(detail).replace(/^库存不足[：:]?\s*/, '')
  return stripped.split('；').filter(Boolean).map(t => {
    const cleaned = t.replace(/^part\s+/i, '').trim()
    const m = cleaned.match(/^(\S+)\s*当前库存\s*([\d.]+)\s*[,，]\s*需要\s*([\d.]+)/)
    if (!m) {
      const fallbackPartId = (cleaned.match(/^(PJ-\S+)/) || [])[1] || ''
      return { partId: fallbackPartId, current: NaN, needed: NaN, raw: cleaned }
    }
    return {
      partId: m[1],
      current: parseFloat(m[2]),
      needed: parseFloat(m[3]),
      raw: cleaned,
    }
  })
}

function renderShortageList(items, message) {
  return h('ul', { style: 'padding-left: 20px; margin: 0;' }, items.map(it => {
    const partId = it.partId
    const rest = partId ? it.raw.slice(partId.length) : it.raw
    return h('li', { style: 'margin: 4px 0; display: flex; align-items: center; gap: 2px;' }, [
      partId ? [
        h('span', null, partId),
        h('span', {
          style: 'display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 4px; cursor: pointer; color: #666; background: #f0f0f0; margin: 0 4px; transition: all 0.2s;',
          onMouseenter: (e) => { e.currentTarget.style.background = '#e0e0e0'; e.currentTarget.style.color = '#333' },
          onMouseleave: (e) => { e.currentTarget.style.background = '#f0f0f0'; e.currentTarget.style.color = '#666' },
          onClick: () => {
            navigator.clipboard
              ?.writeText(partId)
              .then(() => message.success('已复制'))
              .catch(() => message.error('复制失败'))
              ?? message.error('复制失败')
          },
        }, [h(NIcon, { size: 14 }, { default: () => h(CopyOutline) })]),
        h('span', null, rest),
      ] : it.raw,
    ])
  }))
}

function renderSupplementPreview(shortages, orderId) {
  const total = shortages.reduce((sum, s) => sum + Number(s.gap), 0)
  return h('div', null, [
    h('p', { style: 'margin: 0 0 8px;' }, '即将为以下配件补进库存：'),
    h('div', {
      style: 'background:#fafbfc;border:1px solid #efeff5;border-radius:3px;padding:10px 14px;margin:8px 0;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:13px;line-height:1.9;',
    }, shortages.map(s => h('div', null, [
      h('span', { style: 'color:#36ad6a;font-weight:600;' }, s.partId),
      h('span', { style: 'color:#d03050;font-weight:600;margin-left:6px;' }, `+${s.gap}`),
      h('span', null, ' 件'),
    ]))),
    h('p', { style: 'margin: 6px 0 0; font-size: 13px; color: #666;' }, [
      '共 ',
      h('strong', null, String(shortages.length)),
      ' 个配件，总计补进 ',
      h('strong', null, String(total)),
      ' 件。补进成功后将立即继续发出 ',
      h('strong', null, orderId),
      '。',
    ]),
  ])
}
```

- [ ] **Step 2: Quick syntax check**

Run from `frontend/`:
```bash
cd frontend && node --check src/composables/useSendWithStockSupplement.js
```
Expected: no output (success). If it errors on the `import` statement (Node ESM strict-ness varies), skip — the Vite build step in Task 11 will catch real syntax errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/composables/useSendWithStockSupplement.js
git commit -m "feat(frontend): add useSendWithStockSupplement composable

Encapsulates the 库存不足 → 一键补进并发出 flow:
  1. Catches 库存不足 error from send API
  2. Shows shortage list dialog with new '一键补进并发出' button
  3. Re-queries stock via batchGetStock to compute fresh shortfall
  4. Shows confirmation dialog with previewed补进 amounts
  5. Calls supplement-and-send endpoint and toasts the result

Will replace duplicated doSend in HandcraftDetail.vue and
PlatingDetail.vue in subsequent commits."
```

---

## Task 9: Frontend — wire composable into `HandcraftDetail.vue`

**Files:**
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue` (replace lines 950–987 + adjust imports)

- [ ] **Step 1: Update the API import block**

In `HandcraftDetail.vue`, find the `from '@/api/handcraft'` import block (around lines 550–559). Add `supplementAndSendHandcraft` to the imported names. Example before/after of just that import:

Before:
```js
import {
  getHandcraft, getHandcraftParts, getHandcraftJewelries, sendHandcraft,
  // …other imports preserved…
} from '@/api/handcraft'
```

After:
```js
import {
  getHandcraft, getHandcraftParts, getHandcraftJewelries, sendHandcraft, supplementAndSendHandcraft,
  // …other imports preserved…
} from '@/api/handcraft'
```

- [ ] **Step 2: Add composable import**

Add this near the other `@/composables` imports (around line 542):

```js
import { useSendWithStockSupplement } from '@/composables/useSendWithStockSupplement'
```

- [ ] **Step 3: Replace `doSend` and `sending` ref**

Find and delete:
- The line `const sending = ref(false)` (around line 588 — verify with grep before deleting; do not touch any other `sending` ref that may exist for a different purpose).
- The entire `const doSend = async () => { … }` function block (lines 950–987).

Insert in their place (a good spot is wherever `doSend` used to be, around line 950):

```js
const { sending, doSend } = useSendWithStockSupplement({
  orderId: computed(() => route.params.id),
  sendApi: sendHandcraft,
  supplementApi: supplementAndSendHandcraft,
  onSuccess: loadData,
  message,
  dialog,
})
```

`computed` is already imported (line 539). `route`, `message`, `dialog`, `loadData` are already defined in the file.

- [ ] **Step 4: Remove now-unused imports if applicable**

After removing the old `doSend`, the `h`, `NIcon`, `CopyOutline` imports may no longer be needed in this file. Search the file:

```bash
grep -nE "\bh\(|NIcon|CopyOutline" frontend/src/views/handcraft/HandcraftDetail.vue
```

If `h(`, `NIcon`, or `CopyOutline` are still referenced elsewhere in this file, leave the imports alone. If any is now unused, remove it from its import line. **Do not** delete an entire import statement that still has other names in use.

- [ ] **Step 5: Sanity-check the page in dev mode**

Start the backend in one terminal:
```bash
python main.py
```
Start the frontend dev server:
```bash
cd frontend && npm run dev
```
Open the app, navigate to a handcraft order detail page in `pending` status, and click 确认发出.
- If stock is sufficient: should still show "已确认发出" toast and refresh.
- If stock is insufficient: should show the new dialog with "一键补进并发出" button (orange).

If something explodes, check the browser console first.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/handcraft/HandcraftDetail.vue
git commit -m "refactor(handcraft-ui): use useSendWithStockSupplement composable

Replaces the duplicated 库存不足 dialog and doSend logic with the
shared composable. Adds the new '一键补进并发出' affordance on the
existing shortage dialog."
```

---

## Task 10: Frontend — wire composable into `PlatingDetail.vue`

**Files:**
- Modify: `frontend/src/views/plating/PlatingDetail.vue` (replace lines 765–802 + adjust imports)

Mirror of Task 9 for plating.

- [ ] **Step 1: Update the API import block**

In `PlatingDetail.vue`, find the `from '@/api/plating'` import block (around lines 488–…). Add `supplementAndSendPlating`. Example:

Before:
```js
import {
  getPlating, getPlatingItems, sendPlating,
  // …
} from '@/api/plating'
```

After:
```js
import {
  getPlating, getPlatingItems, sendPlating, supplementAndSendPlating,
  // …
} from '@/api/plating'
```

- [ ] **Step 2: Add composable import**

Near the other `@/composables` imports (or wherever appropriate at the top of `<script setup>`):

```js
import { useSendWithStockSupplement } from '@/composables/useSendWithStockSupplement'
```

- [ ] **Step 3: Replace `doSend` and `sending`**

Delete:
- `const sending = ref(false)` around line 512 (verify with grep first).
- The entire `const doSend = async () => { … }` block, lines 765–802.

Insert in place of `doSend`:

```js
const { sending, doSend } = useSendWithStockSupplement({
  orderId: computed(() => route.params.id),
  sendApi: sendPlating,
  supplementApi: supplementAndSendPlating,
  onSuccess: loadData,
  message,
  dialog,
})
```

`computed` should already be imported. Verify with `grep "import.*computed" frontend/src/views/plating/PlatingDetail.vue` — add it to the `vue` import line if missing.

- [ ] **Step 4: Remove now-unused imports if applicable**

Same check as Task 9 — `h`, `NIcon`, `CopyOutline` may have been only used by the now-deleted dialog. Verify:

```bash
grep -nE "\bh\(|NIcon|CopyOutline" frontend/src/views/plating/PlatingDetail.vue
```

Remove names that are no longer referenced. Don't blow away whole import statements that still have other live names.

- [ ] **Step 5: Sanity-check in dev mode**

With the dev server still running, open a plating order detail page in `pending` status and click 确认发出 against a part you know is short on stock. Verify the new flow works end-to-end (shortage dialog → confirm dialog → success toast → order moves to `processing`).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/plating/PlatingDetail.vue
git commit -m "refactor(plating-ui): use useSendWithStockSupplement composable

Mirror of the handcraft refactor in the previous commit. Plating
detail page now offers '一键补进并发出' on the shortage dialog."
```

---

## Task 11: Verification — full backend test pass + frontend build

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

```bash
pytest -q
```
Expected: no failures. If anything fails, fix it before continuing.

- [ ] **Step 2: Run a production frontend build**

```bash
cd frontend && npm run build
```
Expected: builds cleanly. If it errors on `h is not defined` / similar, that means a stale reference was left behind in step 9.4 or 10.4 — fix it.

- [ ] **Step 3: Manual smoke test of the full flow**

With backend + frontend dev servers running:

1. Create or pick a pending handcraft order whose parts have insufficient stock.
2. Click 确认发出 → expect "库存不足" dialog with the new orange button.
3. Click "一键补进并发出" → expect "确认补进库存" dialog showing each part and `+N` per part.
4. Click "确认补进并发出" → expect success toast `已补进 N 个配件共 X 件，订单已发出` and the page refreshes to `processing` status.
5. In the inventory log, verify two entries exist for each shortage part: one `reason="手工单缺货补进"` `note="HC-..."` `change_qty=+gap`, and one `reason="手工发出"` `change_qty=-qty`.
6. Repeat steps 1–5 for a plating order. Verify reason is `"电镀单缺货补进"`.

If anything is off, fix and re-run the relevant focused test. Do not commit smoke-test artifacts.

- [ ] **Step 4: No commit needed for this task** — verification only.

---

## Self-Review Notes (already applied)

- Spec coverage: every requirement in the spec maps to one of Tasks 1–10. The "frontend tests" and "concurrent lock testing" exclusions in the spec are mirrored here (no tasks for them).
- Placeholders: none — every step has runnable code, exact paths, and exact commands.
- Type consistency: `supplement_shortfall` signature, `supplement_and_send_*_order` return type `tuple[Order, dict[str, float]]`, `SupplementAndSend*Response.supplemented` field type all match across tasks.
- Reason strings: `"手工单缺货补进"` (Tasks 2, 5) and `"电镀单缺货补进"` (Tasks 3, 6) are spelled identically wherever they appear, including in test assertions.
