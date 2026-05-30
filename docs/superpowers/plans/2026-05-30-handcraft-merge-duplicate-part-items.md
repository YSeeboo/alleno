# Handcraft 合并相同配件 part_item 行 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户在配货模拟弹窗里按"每个配件"独立决定是否把多条 `HandcraftPartItem` 合并为一条；合并是持久化、不可逆的，仅在 pending 状态、非复合件下可用。

**Architecture:** 新增 `services/handcraft.py::merge_duplicate_part_items()` 纯函数 + `api/handcraft.py` 新 POST 路由；前端 `HandcraftPickingSimulationModal.vue` 的 group-header 内加 inline `合并` 按钮（仅在该组可合并时渲染）+ popconfirm。后端选 `id` 最小行作为幸存行，累加 qty，清空 weight/bom_qty，删除其他行及所有受影响 part_item 的 `HandcraftPickingRecord` / `HandcraftPickingWeight`。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.x / pytest · Vue 3.5 / Naive UI / Vite

**Spec:** `docs/superpowers/specs/2026-05-30-handcraft-merge-duplicate-part-items-design.md`

---

## File Map

| File | Responsibility | Action |
|---|---|---|
| `services/handcraft.py` | Add `merge_duplicate_part_items(db, order_id, part_id)` service function | Modify |
| `api/handcraft.py` | Add `POST /api/handcraft/{order_id}/parts/{part_id}/merge-duplicates` route | Modify |
| `tests/test_api_handcraft_merge_duplicates.py` | All backend tests (service + API) | Create |
| `frontend/src/api/handcraft.js` | Add `mergeHandcraftDuplicateParts(orderId, partId)` | Modify |
| `frontend/src/components/picking/HandcraftPickingSimulationModal.vue` | Add `groupMergeable()` / `groupTotalQty()` / `distinctPartItemCount()` helpers, group-header inline button + popconfirm + handler | Modify |

The plan uses pure TDD: write failing test → run to confirm failure → implement → run to confirm pass → commit. Each task is one cohesive change.

---

## Task 1: Backend service — merge happy path

**Files:**
- Create: `tests/test_api_handcraft_merge_duplicates.py`
- Modify: `services/handcraft.py` (add `merge_duplicate_part_items` at the bottom)

- [ ] **Step 1.1: Write the failing test**

Create `tests/test_api_handcraft_merge_duplicates.py`:

```python
"""Service + API tests for handcraft 合并相同 part_id 的 part_item 行.

See docs/superpowers/specs/2026-05-30-handcraft-merge-duplicate-part-items-design.md.
Service-layer tests use the `db` fixture (truncates between tests).
API tests use the `client` fixture (overrides auth, shared session)."""

from decimal import Decimal

from models.handcraft_order import (
    HandcraftOrder,
    HandcraftPartItem,
    HandcraftPickingRecord,
    HandcraftPickingWeight,
)
from models.part import Part
from services.handcraft import merge_duplicate_part_items


def _seed_part(db, part_id="PJ-X-LK", *, is_composite=False):
    db.add(Part(
        id=part_id, name="龙虾扣", category="小配件",
        size_tier="small", is_composite=is_composite,
    ))


def _seed_order(db, order_id="HC-M1", status="pending"):
    db.add(HandcraftOrder(id=order_id, supplier_name="S", status=status))


def test_merge_two_duplicate_part_items_returns_summary(db):
    """Happy path: 2 rows qty 100/200 → 1 row qty 300; survivor is smallest id."""
    _seed_part(db)
    _seed_order(db)
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=100))
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=200))
    db.flush()
    rows_before = db.query(HandcraftPartItem).filter_by(handcraft_order_id="HC-M1").all()
    survivor_id = min(r.id for r in rows_before)

    result = merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")

    assert result["before_rows"] == 2
    assert result["after_rows"] == 1
    assert result["merged_qty"] == 300.0
    assert result["merged_part_item_id"] == survivor_id

    remaining = db.query(HandcraftPartItem).filter_by(handcraft_order_id="HC-M1").all()
    assert len(remaining) == 1
    assert remaining[0].id == survivor_id
    assert remaining[0].qty == 300


def test_merge_three_duplicate_part_items_sums_qty(db):
    """qty 1 + 1 + 4 → qty 6, one row remains."""
    _seed_part(db)
    _seed_order(db)
    db.flush()
    for q in (1, 1, 4):
        db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=q))
    db.flush()

    result = merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")

    assert result["before_rows"] == 3
    assert result["merged_qty"] == 6.0
    remaining = db.query(HandcraftPartItem).filter_by(handcraft_order_id="HC-M1").all()
    assert len(remaining) == 1
    assert remaining[0].qty == 6
```

- [ ] **Step 1.2: Run test to verify it fails (ImportError)**

Run: `pytest tests/test_api_handcraft_merge_duplicates.py -v`

Expected: FAIL with `ImportError: cannot import name 'merge_duplicate_part_items' from 'services.handcraft'`

- [ ] **Step 1.3: Implement minimal service to make tests pass**

Append to `services/handcraft.py` (at end of file):

```python
def merge_duplicate_part_items(db: Session, order_id: str, part_id: str) -> dict:
    """Merge all HandcraftPartItem rows in an order that share the same part_id.

    The lowest-id row survives; its qty becomes the sum; other rows are deleted.
    Caller (API layer) is responsible for surfacing ValueError as HTTP 400 via
    `service_errors()`.

    Returns: {merged_part_item_id, before_rows, after_rows, merged_qty}.
    """
    rows = (
        db.query(HandcraftPartItem)
        .filter_by(handcraft_order_id=order_id, part_id=part_id)
        .order_by(HandcraftPartItem.id)
        .all()
    )
    survivor, *others = rows
    other_ids = [r.id for r in others]

    total_qty = sum((r.qty for r in rows), Decimal(0))
    survivor.qty = total_qty

    db.query(HandcraftPartItem).filter(
        HandcraftPartItem.id.in_(other_ids)
    ).delete(synchronize_session=False)

    db.flush()
    return {
        "merged_part_item_id": survivor.id,
        "before_rows": len(rows),
        "after_rows": 1,
        "merged_qty": float(total_qty),
    }
```

- [ ] **Step 1.4: Run tests to verify they pass**

Run: `pytest tests/test_api_handcraft_merge_duplicates.py -v`

Expected: 2 passed. Both `test_merge_two_duplicate_part_items_returns_summary` and `test_merge_three_duplicate_part_items_sums_qty` green.

- [ ] **Step 1.5: Commit**

```bash
git add tests/test_api_handcraft_merge_duplicates.py services/handcraft.py
git commit -m "feat(handcraft): add merge_duplicate_part_items service — happy path

- Sums qty of all HandcraftPartItem rows sharing same part_id in an order
- Smallest id wins as survivor; others deleted
- Returns summary {merged_part_item_id, before_rows, after_rows, merged_qty}

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Backend service — clear weight / weight_unit / bom_qty

**Files:**
- Modify: `tests/test_api_handcraft_merge_duplicates.py` (append)
- Modify: `services/handcraft.py` (extend `merge_duplicate_part_items`)

- [ ] **Step 2.1: Write the failing test**

Append to `tests/test_api_handcraft_merge_duplicates.py`:

```python
def test_merge_clears_weight_weight_unit_and_bom_qty_on_survivor(db):
    """Merging wipes weight/weight_unit/bom_qty on the survivor row, since the
    per-jewelry meaning is lost after consolidation."""
    _seed_part(db)
    _seed_order(db)
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-M1", part_id="PJ-X-LK",
        qty=100, weight=Decimal("80"), weight_unit="g", bom_qty=1,
    ))
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-M1", part_id="PJ-X-LK",
        qty=200, weight=Decimal("160"), weight_unit="g", bom_qty=1,
    ))
    db.flush()

    merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")

    survivor = db.query(HandcraftPartItem).filter_by(handcraft_order_id="HC-M1").one()
    assert survivor.weight is None
    assert survivor.weight_unit is None
    assert survivor.bom_qty is None
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `pytest tests/test_api_handcraft_merge_duplicates.py::test_merge_clears_weight_weight_unit_and_bom_qty_on_survivor -v`

Expected: FAIL — `survivor.weight is None` is False (it'll be the pre-existing 80g on the survivor).

- [ ] **Step 2.3: Extend the service**

In `services/handcraft.py`, edit `merge_duplicate_part_items` — after `survivor.qty = total_qty`, add:

```python
    survivor.qty = total_qty
    survivor.weight = None
    survivor.weight_unit = None
    survivor.bom_qty = None
```

- [ ] **Step 2.4: Run all tests for the file**

Run: `pytest tests/test_api_handcraft_merge_duplicates.py -v`

Expected: 3 passed (Task 1's 2 tests still green, new test green).

- [ ] **Step 2.5: Commit**

```bash
git add tests/test_api_handcraft_merge_duplicates.py services/handcraft.py
git commit -m "feat(handcraft): clear weight/weight_unit/bom_qty on merge survivor

Per-jewelry weight/bom_qty have no single meaning after consolidation;
wiping forces the user to re-measure (matches the merged workflow's intent).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Backend service — clear picking_record + picking_weight for affected part_items

**Files:**
- Modify: `tests/test_api_handcraft_merge_duplicates.py` (append)
- Modify: `services/handcraft.py` (extend `merge_duplicate_part_items`)

- [ ] **Step 3.1: Write the failing tests**

Append to `tests/test_api_handcraft_merge_duplicates.py`:

```python
def test_merge_clears_picking_records_for_all_affected_part_items(db):
    """All HandcraftPickingRecord rows for affected part_item_ids are deleted —
    including the survivor's, because the merge restructures what 'picking'
    means at this scope."""
    _seed_part(db)
    _seed_order(db)
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=100))
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=200))
    db.flush()
    items = db.query(HandcraftPartItem).filter_by(handcraft_order_id="HC-M1").all()
    for it in items:
        db.add(HandcraftPickingRecord(
            handcraft_order_id="HC-M1",
            handcraft_part_item_id=it.id,
            part_id="PJ-X-LK",
        ))
    db.flush()
    assert db.query(HandcraftPickingRecord).count() == 2

    merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")

    assert db.query(HandcraftPickingRecord).count() == 0


def test_merge_clears_picking_weights_for_all_affected_part_items(db):
    """All HandcraftPickingWeight rows for affected part_item_ids are deleted."""
    _seed_part(db)
    _seed_order(db)
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=100))
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=200))
    db.flush()
    items = db.query(HandcraftPartItem).filter_by(handcraft_order_id="HC-M1").all()
    for it in items:
        db.add(HandcraftPickingWeight(
            handcraft_order_id="HC-M1",
            part_item_id=it.id,
            atom_part_id="PJ-X-LK",
            weight=Decimal("80"),
            weight_unit="g",
        ))
    db.flush()
    assert db.query(HandcraftPickingWeight).count() == 2

    merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")

    assert db.query(HandcraftPickingWeight).count() == 0
```

- [ ] **Step 3.2: Run tests to verify they fail**

Run: `pytest tests/test_api_handcraft_merge_duplicates.py -v -k "picking"`

Expected: 2 FAIL (records / weights still exist after merge).

- [ ] **Step 3.3: Extend the service**

In `services/handcraft.py`, edit `merge_duplicate_part_items`. Add deletion of picking records and weights **before** mutating qty (so we still know all the ids):

```python
    rows = (
        db.query(HandcraftPartItem)
        .filter_by(handcraft_order_id=order_id, part_id=part_id)
        .order_by(HandcraftPartItem.id)
        .all()
    )
    survivor, *others = rows
    other_ids = [r.id for r in others]
    all_ids = [r.id for r in rows]

    # Wipe all picking state for these part_items — both survivor and others.
    # The restructure invalidates per-jewelry-source picks/weights.
    db.query(HandcraftPickingRecord).filter(
        HandcraftPickingRecord.handcraft_part_item_id.in_(all_ids)
    ).delete(synchronize_session=False)
    db.query(HandcraftPickingWeight).filter(
        HandcraftPickingWeight.part_item_id.in_(all_ids)
    ).delete(synchronize_session=False)

    total_qty = sum((r.qty for r in rows), Decimal(0))
    survivor.qty = total_qty
    survivor.weight = None
    survivor.weight_unit = None
    survivor.bom_qty = None

    db.query(HandcraftPartItem).filter(
        HandcraftPartItem.id.in_(other_ids)
    ).delete(synchronize_session=False)
```

- [ ] **Step 3.4: Run all tests for the file**

Run: `pytest tests/test_api_handcraft_merge_duplicates.py -v`

Expected: 5 passed.

- [ ] **Step 3.5: Commit**

```bash
git add tests/test_api_handcraft_merge_duplicates.py services/handcraft.py
git commit -m "feat(handcraft): clear picking_record + picking_weight on merge

Both survivor and merged-away rows have their picking state wiped — the merge
restructures what one 'pick' covers, so retaining per-row records would
misrepresent reality.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Backend service — guards (status / count / composite)

**Files:**
- Modify: `tests/test_api_handcraft_merge_duplicates.py` (append)
- Modify: `services/handcraft.py` (add validation at top of `merge_duplicate_part_items`)

- [ ] **Step 4.1: Write the failing tests**

Append to `tests/test_api_handcraft_merge_duplicates.py`:

```python
import pytest


def test_merge_in_processing_raises(db):
    """Non-pending orders cannot be merged."""
    _seed_part(db)
    _seed_order(db, status="processing")
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=100))
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=200))
    db.flush()

    with pytest.raises(ValueError, match="不在 pending"):
        merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")


def test_merge_in_completed_raises(db):
    _seed_part(db)
    _seed_order(db, status="completed")
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=100))
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=200))
    db.flush()

    with pytest.raises(ValueError, match="不在 pending"):
        merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")


def test_merge_with_fewer_than_two_rows_raises(db):
    """No-op should be explicit — caller asked for a structural change that
    can't happen with <2 rows."""
    _seed_part(db)
    _seed_order(db)
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=100))
    db.flush()

    with pytest.raises(ValueError, match="没有可合并"):
        merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")


def test_merge_with_zero_rows_raises(db):
    _seed_part(db)
    _seed_order(db)
    db.flush()

    with pytest.raises(ValueError, match="没有可合并"):
        merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")


def test_merge_composite_part_raises(db):
    """Composite parts are out of v1 scope."""
    _seed_part(db, part_id="PJ-X-SET", is_composite=True)
    _seed_order(db)
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-SET", qty=5))
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-SET", qty=3))
    db.flush()

    with pytest.raises(ValueError, match="复合件"):
        merge_duplicate_part_items(db, "HC-M1", "PJ-X-SET")


def test_merge_nonexistent_order_raises(db):
    _seed_part(db)
    db.flush()

    with pytest.raises(ValueError, match="订单"):
        merge_duplicate_part_items(db, "HC-DOES-NOT-EXIST", "PJ-X-LK")


def test_merge_nonexistent_part_raises(db):
    _seed_order(db)
    db.flush()

    with pytest.raises(ValueError, match="配件"):
        merge_duplicate_part_items(db, "HC-M1", "PJ-X-NONE")
```

- [ ] **Step 4.2: Run tests to verify they fail**

Run: `pytest tests/test_api_handcraft_merge_duplicates.py -v`

Expected: 7 FAIL (the new guards don't exist yet — current service either accepts and processes or raises ValueError for empty rows with "not enough values to unpack" from the tuple unpacking).

- [ ] **Step 4.3: Add guards to the service**

In `services/handcraft.py`, prepend validation to `merge_duplicate_part_items` (before fetching rows):

```python
def merge_duplicate_part_items(db: Session, order_id: str, part_id: str) -> dict:
    """... (existing docstring) ..."""
    order = db.get(HandcraftOrder, order_id)
    if order is None:
        raise ValueError(f"订单 {order_id} 不存在")
    if order.status != "pending":
        raise ValueError(f"订单 {order_id} 不在 pending 状态，不可合并")

    part = db.get(Part, part_id)
    if part is None:
        raise ValueError(f"配件 {part_id} 不存在")
    if part.is_composite:
        raise ValueError("复合件暂不支持自动合并")

    rows = (
        db.query(HandcraftPartItem)
        .filter_by(handcraft_order_id=order_id, part_id=part_id)
        .order_by(HandcraftPartItem.id)
        .all()
    )
    if len(rows) < 2:
        raise ValueError(f"订单 {order_id} 中 {part_id} 没有可合并的 part_item 行")

    survivor, *others = rows
    # ... (rest unchanged) ...
```

- [ ] **Step 4.4: Run all tests**

Run: `pytest tests/test_api_handcraft_merge_duplicates.py -v`

Expected: 12 passed.

- [ ] **Step 4.5: Commit**

```bash
git add tests/test_api_handcraft_merge_duplicates.py services/handcraft.py
git commit -m "feat(handcraft): merge guards — pending only, ≥2 rows, non-composite

- ValueError if order status != pending
- ValueError if part_id has <2 rows in order
- ValueError if part is composite (out of v1 scope)
- ValueError if order or part does not exist (API layer surfaces as 4xx)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Backend API route

**Files:**
- Modify: `tests/test_api_handcraft_merge_duplicates.py` (append API tests)
- Modify: `api/handcraft.py` (add route)

- [ ] **Step 5.1: Write the failing tests**

Append to `tests/test_api_handcraft_merge_duplicates.py`:

```python
# --- API layer tests ---


def test_api_merge_two_duplicate_rows_returns_200_summary(client, db):
    db.add(Part(id="PJ-X-LK", name="龙虾扣", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-M1", supplier_name="S", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=100))
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=200))
    db.flush()

    resp = client.post("/api/handcraft/HC-M1/parts/PJ-X-LK/merge-duplicates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["before_rows"] == 2
    assert body["after_rows"] == 1
    assert body["merged_qty"] == 300.0


def test_api_merge_processing_returns_400(client, db):
    db.add(Part(id="PJ-X-LK", name="龙虾扣", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-M1", supplier_name="S", status="processing"))
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=100))
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=200))
    db.flush()

    resp = client.post("/api/handcraft/HC-M1/parts/PJ-X-LK/merge-duplicates")
    assert resp.status_code == 400
    assert "pending" in resp.json()["detail"]


def test_api_merge_no_duplicates_returns_400(client, db):
    db.add(Part(id="PJ-X-LK", name="龙虾扣", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-M1", supplier_name="S", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=100))
    db.flush()

    resp = client.post("/api/handcraft/HC-M1/parts/PJ-X-LK/merge-duplicates")
    assert resp.status_code == 400
    assert "没有可合并" in resp.json()["detail"]


def test_api_merge_composite_returns_400(client, db):
    db.add(Part(id="PJ-X-SET", name="套链", category="小配件", size_tier="small", is_composite=True))
    db.add(HandcraftOrder(id="HC-M1", supplier_name="S", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-SET", qty=5))
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-SET", qty=3))
    db.flush()

    resp = client.post("/api/handcraft/HC-M1/parts/PJ-X-SET/merge-duplicates")
    assert resp.status_code == 400
    assert "复合件" in resp.json()["detail"]


def test_api_merge_nonexistent_order_returns_400(client, db):
    db.add(Part(id="PJ-X-LK", name="龙虾扣", category="小配件", size_tier="small"))
    db.flush()

    resp = client.post("/api/handcraft/HC-NONE/parts/PJ-X-LK/merge-duplicates")
    assert resp.status_code == 400  # service_errors maps ValueError → 400
    assert "订单" in resp.json()["detail"]


def test_api_merge_nonexistent_part_returns_400(client, db):
    db.add(HandcraftOrder(id="HC-M1", supplier_name="S", status="pending"))
    db.flush()

    resp = client.post("/api/handcraft/HC-M1/parts/PJ-X-NONE/merge-duplicates")
    assert resp.status_code == 400
    assert "配件" in resp.json()["detail"]
```

- [ ] **Step 5.2: Run tests to verify they fail (404)**

Run: `pytest tests/test_api_handcraft_merge_duplicates.py -v -k "api_merge"`

Expected: 6 FAIL (route doesn't exist → 404 from FastAPI, not 200/400).

- [ ] **Step 5.3: Add the route**

Open `api/handcraft.py`. Append a new route at the bottom (after the last existing `@router` block):

```python
@router.post("/{order_id}/parts/{part_id}/merge-duplicates")
def api_merge_handcraft_duplicate_parts(
    order_id: str,
    part_id: str,
    db: Session = Depends(get_db),
):
    """Persistently merge all HandcraftPartItem rows in this order that share
    the same part_id. ValueError → 400 via service_errors."""
    from services.handcraft import merge_duplicate_part_items
    with service_errors():
        return merge_duplicate_part_items(db, order_id, part_id)
```

> If `services.handcraft` is already imported at the top of `api/handcraft.py` (check the existing `from services.handcraft import ...` line and add `merge_duplicate_part_items` to that import instead of the local import).

- [ ] **Step 5.4: Run all tests for the file**

Run: `pytest tests/test_api_handcraft_merge_duplicates.py -v`

Expected: 18 passed (12 service + 6 API).

- [ ] **Step 5.5: Verify no regression in the broader handcraft test suite**

Run: `pytest tests/test_api_handcraft.py tests/test_api_handcraft_picking.py tests/test_handcraft.py -v`

Expected: all green (no existing tests broken by the new route or service function).

- [ ] **Step 5.6: Commit**

```bash
git add tests/test_api_handcraft_merge_duplicates.py api/handcraft.py
git commit -m "feat(handcraft): POST /handcraft/{id}/parts/{part_id}/merge-duplicates

Surfaces merge_duplicate_part_items service through the API. ValueError →
400 via service_errors(). Permission gated by existing handcraft router
permission.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Frontend API client

**Files:**
- Modify: `frontend/src/api/handcraft.js`

- [ ] **Step 6.1: Add the API client function**

Open `frontend/src/api/handcraft.js`. After the existing `updateHandcraftPart` / `deleteHandcraftPart` lines (around line 25), add:

```javascript
export const mergeHandcraftDuplicateParts = (id, partId) =>
  api.post(`/handcraft/${id}/parts/${encodeURIComponent(partId)}/merge-duplicates`)
```

> `encodeURIComponent` matters because part_ids like `PJ-DZ-00001-G-45cm` contain hyphens (safe) but variants may include reserved characters in future. Defensive encode now.

- [ ] **Step 6.2: Smoke check in browser console**

There's no automated test for the API client file in this project; the function is exercised through the modal in Task 8. Skip running anything here.

- [ ] **Step 6.3: Commit**

```bash
git add frontend/src/api/handcraft.js
git commit -m "feat(handcraft): add mergeHandcraftDuplicateParts API client

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Frontend — `groupMergeable` computed + helpers

**Files:**
- Modify: `frontend/src/components/picking/HandcraftPickingSimulationModal.vue`

- [ ] **Step 7.1: Locate the script section**

Open `frontend/src/components/picking/HandcraftPickingSimulationModal.vue`. Find the `<script setup>` area. Locate the `displayGroups` computed (around line 290 — earlier grep result showed it at line 303 used with `part_id: g.atom_part_id`).

- [ ] **Step 7.2: Add helper functions near `displayGroups`**

After the `displayGroups` computed property (find it, then add immediately below), add three helpers:

```javascript
// True when this atom group can be persistently merged at the part_item level:
// - readonly off (i.e., order is pending)
// - at least 2 distinct part_item_id values among g.rows
// - NO row is a composite expansion (v1 scope: simple parts only)
function groupMergeable(g) {
  if (readonly.value) return false
  if (g.rows.some((r) => r.is_composite_expansion)) return false
  const ids = new Set(g.rows.map((r) => r.part_item_id))
  return ids.size >= 2
}

function distinctPartItemCount(g) {
  return new Set(g.rows.map((r) => r.part_item_id)).size
}

function groupTotalQty(g) {
  // Sum unique-by-part_item_id (avoid double-counting composite expansion,
  // though groupMergeable already excludes that case — defense in depth).
  const seen = new Set()
  let total = 0
  for (const r of g.rows) {
    if (seen.has(r.part_item_id)) continue
    seen.add(r.part_item_id)
    total += Number(r.qty) || 0
  }
  return total
}
```

- [ ] **Step 7.3: Verify the file still parses (no template change yet)**

Run: `cd frontend && npm run build 2>&1 | tail -20`

Expected: build succeeds (no syntax error introduced by the script edits).

- [ ] **Step 7.4: Commit**

```bash
git add frontend/src/components/picking/HandcraftPickingSimulationModal.vue
git commit -m "feat(handcraft): add groupMergeable/distinctPartItemCount/groupTotalQty helpers

These will drive the inline 合并 button in the next task. Pure additions —
no template changes yet, no behavior change.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Frontend — inline button + popconfirm + handler

**Files:**
- Modify: `frontend/src/components/picking/HandcraftPickingSimulationModal.vue`

- [ ] **Step 8.1: Import the API client function**

At the top of `<script setup>`, locate the existing import from `@/api/handcraft` (around line 10-15). Add `mergeHandcraftDuplicateParts`:

```javascript
import {
  // ... existing names ...
  mergeHandcraftDuplicateParts,
} from '@/api/handcraft'
```

- [ ] **Step 8.2: Add the handler**

Below the `doReset` function (or near other action handlers around line 205), add:

```javascript
async function doMergeGroup(g) {
  try {
    const res = await mergeHandcraftDuplicateParts(props.orderId, g.atom_part_id)
    const { before_rows, after_rows } = res.data || {}
    message.success(`已合并 ${before_rows} 行 → ${after_rows} 行`)
    await loadData()
  } catch (err) {
    message.error(err.response?.data?.detail || '合并失败')
  }
}
```

- [ ] **Step 8.3: Add the inline button to group-header template**

Locate the group-header `<td class="col-source">` block (around line 416-430, based on the earlier read). The current structure is:

```html
<td class="col-source">
  <div class="group-cell">
    <img v-if="g.atom_part_image" :src="g.atom_part_image" class="group-img" />
    <div v-else class="group-img placeholder" />
    <div class="group-meta">
      <div class="group-name-line">
        <span class="group-name">{{ g.atom_part_name }}</span>
        <n-tag size="tiny" type="default" :bordered="false" style="margin-left: 6px;">
          {{ SIZE_TIER_LABEL[g.size_tier] || '小件' }}
        </n-tag>
      </div>
      <div class="group-id">{{ g.atom_part_id }}</div>
    </div>
  </div>
</td>
```

Wrap the existing `<div class="group-cell">` content in a flex container and add the popconfirm/button on the right:

```html
<td class="col-source">
  <div class="group-cell">
    <div class="group-cell-left">
      <img v-if="g.atom_part_image" :src="g.atom_part_image" class="group-img" />
      <div v-else class="group-img placeholder" />
      <div class="group-meta">
        <div class="group-name-line">
          <span class="group-name">{{ g.atom_part_name }}</span>
          <n-tag size="tiny" type="default" :bordered="false" style="margin-left: 6px;">
            {{ SIZE_TIER_LABEL[g.size_tier] || '小件' }}
          </n-tag>
        </div>
        <div class="group-id">{{ g.atom_part_id }}</div>
      </div>
    </div>
    <n-popconfirm
      v-if="groupMergeable(g)"
      @positive-click="doMergeGroup(g)"
      positive-text="确认合并"
      negative-text="取消"
    >
      <template #trigger>
        <n-button text size="tiny" class="inline-merge" @click.stop>合并</n-button>
      </template>
      合并 {{ g.atom_part_name }}（{{ distinctPartItemCount(g) }} 行 → 1 行 · qty {{ fmtQty(groupTotalQty(g)) }}）？
      <br />已有的勾选 / 重量记录会被清空。
      <br /><b>不可撤销。</b>
    </n-popconfirm>
  </div>
</td>
```

> `@click.stop` on the trigger button: the group-header row may have click handlers (e.g., for restock toggling); stop propagation so opening the popconfirm doesn't ripple to the row.

- [ ] **Step 8.4: Add styles**

Find the `<style scoped>` section. Add:

```css
.group-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.group-cell-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}
.inline-merge {
  color: #047857 !important;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 3px;
}
.inline-merge:hover {
  background: #ecfdf5;
}
```

> The existing `.group-cell` (if any) is being redefined — search the styles section first; if `.group-cell` already exists, replace its body rather than appending. The new rules are non-destructive to other group-cell descendants because `.group-meta`, `.group-img`, `.group-name` etc. don't depend on `.group-cell` being non-flex.

- [ ] **Step 8.5: Verify build**

Run: `cd frontend && npm run build 2>&1 | tail -20`

Expected: build succeeds.

- [ ] **Step 8.6: Verify n-popconfirm is registered in this file**

Run: `grep -n "NPopconfirm\|n-popconfirm" frontend/src/components/picking/HandcraftPickingSimulationModal.vue | head -5`

Expected: should already be present (search shows existing `n-popconfirm` usage at line 388 around 重置勾选). If `NPopconfirm` is NOT in the import list, add it to the existing destructure of `naive-ui` components in `<script setup>`.

- [ ] **Step 8.7: Commit**

```bash
git add frontend/src/components/picking/HandcraftPickingSimulationModal.vue
git commit -m "feat(handcraft): inline 合并 button per atom group in picking modal

- Visible only when group has ≥2 distinct part_item sources, no composite
  expansion, and order is pending
- popconfirm shows quantified preview (N 行 → 1 行 · qty X)
- On success, reloads picking data; the merged group's button disappears
  automatically because the group now has only one source

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Final verification

**Files:** none

- [ ] **Step 9.1: Run the full backend test suite**

Run: `pytest -x -q`

Expected: all pass. The `-x` stops on first failure so you catch unrelated regressions quickly.

- [ ] **Step 9.2: Frontend build sanity check**

Run: `cd frontend && npm run build`

Expected: build succeeds with no Vue warnings related to the modified component.

- [ ] **Step 9.3: Manual verification checklist**

Start dev environment and walk through:

```bash
# Terminal 1
docker-compose up -d
python main.py

# Terminal 2
cd frontend && npm run dev
```

Then in the browser, create or find a pending handcraft order with at least one part shared across two jewelries (e.g., create 2 handcraft jewelry items both needing 龙虾扣). Open 配货模拟 and verify:

- [ ] In a group with ≥2 sources → "合并" button visible in group-header title row
- [ ] In a group with 1 source → no button
- [ ] In a group containing composite-expanded rows → no button
- [ ] Switch order to processing (via `POST /send`) → button disappears (readonly)
- [ ] Click button → popconfirm appears with correct N and qty
- [ ] Cancel popconfirm → no API call
- [ ] Confirm popconfirm → toast "已合并 N 行 → 1 行"; table reloads; that group now has 1 row; button gone
- [ ] Other groups' buttons (if any) remain operational and independent
- [ ] Weight input on the merged row is empty (you can fill it as 总重量)
- [ ] No regression on 导出 PDF / 重置勾选 / 只看未完成 switch

- [ ] **Step 9.4: Final commit (only if there are leftover artifacts; otherwise skip)**

If nothing changed, skip. Otherwise:

```bash
git add -A
git commit -m "chore(handcraft): wrap up merge-duplicates feature

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Done

All work in spec `2026-05-30-handcraft-merge-duplicate-part-items-design.md` is implemented and verified. Recommend opening a PR with title like:

> feat(handcraft): 配货模拟弹窗加「合并相同配件」按钮（持久化）

PR body should link to both the spec and this plan, and include the Step 9.3 manual checklist (with checkboxes ticked).
