# Handcraft Picking Actual Qty Sync — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `handcraft_picking_weight.actual_qty` so the value entered in the 配货模拟 modal flows into HandcraftDetail's 发出数量 column and into `send_handcraft_order`'s stock deduction. Atomic part_items only — composite items keep existing behavior.

**Architecture:** Backend joins `handcraft_picking_weight` rows where `atom_part_id == pi.part_id` (a natural filter that excludes composite expansions). The detail GET surfaces `actual_qty` as a new optional field; the send service computes `effective_qty = actual_qty ?? pi.qty` per item before aggregating. Frontend renders the override with a small "(原 N)" annotation and reloads the parts list when the picking modal closes — which also picks up weight changes (`重量` column already reads from the same picking response).

**Tech Stack:** FastAPI + SQLAlchemy 2.x + Pydantic V2 (backend); Vue 3 + Naive UI (frontend); pytest (backend tests; no frontend test infra).

**Spec:** `docs/superpowers/specs/2026-05-11-handcraft-actual-qty-sync-design.md`

---

## File Structure

**Backend (modified, no new files):**
- `schemas/handcraft.py` — add `actual_qty: Optional[float] = None` to `HandcraftPartItemResponse` (line 75-90 block)
- `services/handcraft.py` — add private `_attach_actual_qty` helper near `_attach_loss_qty` (line 349-360 area); call it from `get_handcraft_parts` (line 363-371); replace the aggregation loop in `send_handcraft_order` (line 292-295)
- `tests/test_api_handcraft.py` — append new tests for the new GET behavior (atomic with override, atomic without, composite stays null) and for send behavior (uses override, falls back, composite unaffected, stock check honors effective qty)

**Frontend (modified, no new files):**
- `frontend/src/views/handcraft/HandcraftDetail.vue` — `itemColumns` 发出数量 render (line 1832-1850); `HandcraftPickingSimulationModal` props block (line 528-533)

**Out of scope:** picking modal itself, picking PDF, weight handling code (data layer already unified), composite send/stock logic.

---

## Task 1: Add `actual_qty` to `HandcraftPartItemResponse` schema

**Files:**
- Modify: `schemas/handcraft.py:75-90`

- [ ] **Step 1: Read the current `HandcraftPartItemResponse` block**

Confirm the field list. The current block (lines 75-90):

```python
class HandcraftPartItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    handcraft_order_id: str
    part_id: str
    qty: float
    weight: Optional[float] = Field(None, ge=0)
    weight_unit: Optional[str] = None
    received_qty: Optional[float] = 0
    status: str = "未送出"
    bom_qty: Optional[float] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    note: Optional[str] = None
    loss_qty: Optional[float] = None
```

- [ ] **Step 2: Add `actual_qty` field after `qty`**

Edit `schemas/handcraft.py`:

```python
class HandcraftPartItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    handcraft_order_id: str
    part_id: str
    qty: float
    actual_qty: Optional[float] = None  # picking override; only set for atomic items
    weight: Optional[float] = Field(None, ge=0)
    weight_unit: Optional[str] = None
    received_qty: Optional[float] = 0
    status: str = "未送出"
    bom_qty: Optional[float] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    note: Optional[str] = None
    loss_qty: Optional[float] = None
```

- [ ] **Step 3: Verify existing tests still pass (schema change alone is backward-compatible)**

Run:
```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft.py -x --tb=short
```
Expected: all existing tests pass (new field is optional, defaults to None).

- [ ] **Step 4: Commit**

```bash
git add schemas/handcraft.py
git commit -m "feat(handcraft): add actual_qty field to HandcraftPartItemResponse"
```

---

## Task 2: Write failing test — `get_handcraft_parts` exposes `actual_qty` for atomic items

**Files:**
- Test: `tests/test_api_handcraft.py` (append)

- [ ] **Step 1: Add the failing test**

Append to `tests/test_api_handcraft.py`:

```python
def test_get_parts_includes_actual_qty_for_atomic(client, db):
    """When picking_weight.actual_qty is set on an atomic part_item, the
    parts GET response surfaces it. Key match: (pi.id, pi.part_id)."""
    from decimal import Decimal
    from models.handcraft_order import HandcraftPartItem, HandcraftPickingWeight

    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier AQ1",
        "parts": [{"part_id": part.id, "qty": 100.0}],
    }).json()
    order_id = created["id"]
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order_id).one()

    db.add(HandcraftPickingWeight(
        handcraft_order_id=order_id,
        part_item_id=pi.id,
        atom_part_id=part.id,        # atomic: atom == part
        actual_qty=Decimal("80.0000"),
    ))
    db.flush()

    resp = client.get(f"/api/handcraft/{order_id}/parts")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["qty"] == 100.0
    assert rows[0]["actual_qty"] == 80.0


def test_get_parts_actual_qty_null_when_no_override(client, db):
    """No picking_weight row → actual_qty is None in the response."""
    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier AQ2",
        "parts": [{"part_id": part.id, "qty": 50.0}],
    }).json()
    resp = client.get(f"/api/handcraft/{created['id']}/parts")
    assert resp.status_code == 200
    assert resp.json()[0]["actual_qty"] is None
```

- [ ] **Step 2: Run the tests; confirm they fail**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft.py::test_get_parts_includes_actual_qty_for_atomic tests/test_api_handcraft.py::test_get_parts_actual_qty_null_when_no_override -x --tb=short
```

Expected: `test_get_parts_includes_actual_qty_for_atomic` FAILS with `assert None == 80.0` (or similar — the response field is always None until we wire `_attach_actual_qty`). The "null when no override" test passes because the default is None.

If both pass, the schema fallback masks the missing wiring — STOP and check that the schema field default is `None` and the service hasn't been pre-wired.

- [ ] **Step 3: Stage the tests (no commit yet)**

```bash
git add tests/test_api_handcraft.py
```

---

## Task 3: Implement `_attach_actual_qty` in services/handcraft.py

**Files:**
- Modify: `services/handcraft.py` — add helper after `_attach_loss_qty` (≈line 360); call from `get_handcraft_parts` (line 363-371)

- [ ] **Step 1: Confirm the existing imports include `HandcraftPickingWeight`**

```bash
grep -n "HandcraftPickingWeight\|from models.handcraft_order" /Users/ycb/workspace/allen_shop/services/handcraft.py | head -5
```

If `HandcraftPickingWeight` is NOT already imported in `services/handcraft.py`, add it to the existing `from models.handcraft_order import ...` line at the top of the file. (Check by searching first; do not duplicate the import.)

- [ ] **Step 2: Add the `_attach_actual_qty` helper**

In `services/handcraft.py`, insert directly after `_attach_loss_qty` (around line 360, before `def get_handcraft_parts`):

```python
def _attach_actual_qty(db: Session, items: list, order_id: str) -> list:
    """Attach picking actual_qty to atomic part items only.

    The lookup key (part_item_id, atom_part_id == pi.part_id) naturally
    filters to atomic items: composite expansions only produce
    picking_weight rows where atom_part_id != pi.part_id, so the lookup
    misses and item.actual_qty stays None.
    """
    if not items:
        return items
    rows = (
        db.query(HandcraftPickingWeight)
        .filter(
            HandcraftPickingWeight.handcraft_order_id == order_id,
            HandcraftPickingWeight.actual_qty.is_not(None),
        )
        .all()
    )
    actual_by_key = {
        (r.part_item_id, r.atom_part_id): float(r.actual_qty)
        for r in rows
    }
    for it in items:
        it.actual_qty = actual_by_key.get((it.id, it.part_id))
    return items
```


- [ ] **Step 3: Call it from `get_handcraft_parts`**

Replace the body of `get_handcraft_parts` (line 363-371) with:

```python
def get_handcraft_parts(db: Session, order_id: str) -> list:
    items = (
        db.query(HandcraftPartItem)
        .filter(HandcraftPartItem.handcraft_order_id == order_id)
        .order_by(HandcraftPartItem.id.asc())
        .all()
    )
    items = _attach_part_colors(db, items)
    items = _attach_loss_qty(db, items, order_id, "handcraft_part")
    return _attach_actual_qty(db, items, order_id)
```

- [ ] **Step 4: Run the failing tests; confirm they now pass**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft.py::test_get_parts_includes_actual_qty_for_atomic tests/test_api_handcraft.py::test_get_parts_actual_qty_null_when_no_override -x --tb=short
```

Expected: both PASS.

- [ ] **Step 5: Run the full handcraft test file to catch regressions**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft.py -x --tb=short
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add services/handcraft.py tests/test_api_handcraft.py
git commit -m "feat(handcraft): surface picking actual_qty in GET /parts response

Atomic part_items get actual_qty populated from handcraft_picking_weight
where atom_part_id == pi.part_id. Composite items always see null
(their picking_weight rows have atom_part_id != pi.part_id, so the key
miss is automatic)."
```

---

## Task 4: Write failing test — composite items keep `actual_qty == null`

**Files:**
- Test: `tests/test_api_handcraft.py` (append)

This test guards the natural-filter property. Even if a composite part_item's atom rows have actual_qty set, the GET response for the composite item itself must show `actual_qty is None`.

- [ ] **Step 1: Add the failing test**

Append to `tests/test_api_handcraft.py`:

```python
def test_get_parts_omits_actual_qty_for_composite(client, db):
    """Composite part_items: picking sets actual_qty on atom rows, but the
    composite item itself never gets a (pi.id, pi.part_id) match — so its
    response actual_qty stays None."""
    from decimal import Decimal
    from models.handcraft_order import HandcraftPartItem, HandcraftPickingWeight
    from models.part_bom import PartBom
    from services._helpers import _next_id

    composite = create_part(db, {"name": "Composite C1", "category": "小配件"})
    composite.is_composite = True
    atom = create_part(db, {"name": "Atom A1", "category": "小配件"})
    db.add(PartBom(
        id=_next_id(db, PartBom, "PB"),
        parent_part_id=composite.id,
        child_part_id=atom.id,
        qty_per_unit=Decimal("2"),
    ))
    add_stock(db, "part", atom.id, 100.0, "初始入库")
    db.flush()

    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier Composite",
        "parts": [{"part_id": composite.id, "qty": 5.0}],
    }).json()
    order_id = created["id"]
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order_id).one()

    # Picking modal would store actual_qty on the atom row (atom_part_id != pi.part_id)
    db.add(HandcraftPickingWeight(
        handcraft_order_id=order_id,
        part_item_id=pi.id,
        atom_part_id=atom.id,         # atom_part_id != pi.part_id (composite)
        actual_qty=Decimal("9.0000"),
    ))
    db.flush()

    resp = client.get(f"/api/handcraft/{order_id}/parts")
    assert resp.status_code == 200
    row = resp.json()[0]
    assert row["part_id"] == composite.id
    assert row["actual_qty"] is None   # composite never gets the override
```

- [ ] **Step 2: Run the test; confirm it passes immediately**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft.py::test_get_parts_omits_actual_qty_for_composite -x --tb=short
```

Expected: PASS (the key (pi.id, pi.part_id) where pi.part_id == composite.id doesn't match any picking_weight row, so it stays None).

This test is a regression guard rather than a TDD driver — its purpose is to lock in the natural-filter behavior so a future refactor that keys by part_item_id alone would fail.

- [ ] **Step 3: Commit**

```bash
git add tests/test_api_handcraft.py
git commit -m "test(handcraft): composite items never surface picking actual_qty"
```

---

## Task 5: Write failing tests — `send_handcraft_order` honors actual_qty override

**Files:**
- Test: `tests/test_api_handcraft.py` (append)

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_api_handcraft.py`:

```python
def test_send_handcraft_uses_actual_qty_when_present(client, db):
    """Atomic item with actual_qty=80 and pi.qty=100 → send deducts 80."""
    from decimal import Decimal
    from models.handcraft_order import HandcraftPartItem, HandcraftPickingWeight

    part, jewelry = _setup(db)  # adds 100 stock for the part
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier SAQ1",
        "parts": [{"part_id": part.id, "qty": 100.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 1}],
    }).json()
    order_id = created["id"]
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order_id).one()
    db.add(HandcraftPickingWeight(
        handcraft_order_id=order_id,
        part_item_id=pi.id,
        atom_part_id=part.id,
        actual_qty=Decimal("80.0000"),
    ))
    db.flush()

    resp = client.post(f"/api/handcraft/{order_id}/send")
    assert resp.status_code == 200
    assert get_stock(db, "part", part.id) == pytest.approx(20.0)  # 100 - 80


def test_send_handcraft_falls_back_to_pi_qty_when_no_override(client, db):
    """No actual_qty → behaves exactly as before."""
    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier SAQ2",
        "parts": [{"part_id": part.id, "qty": 30.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 1}],
    }).json()
    resp = client.post(f"/api/handcraft/{created['id']}/send")
    assert resp.status_code == 200
    assert get_stock(db, "part", part.id) == pytest.approx(70.0)  # 100 - 30


def test_send_handcraft_stock_check_uses_effective_qty_under(client, db):
    """actual_qty=80 < stock=90 < pi.qty=100 → send succeeds (uses effective 80)."""
    from decimal import Decimal
    from models.handcraft_order import HandcraftPartItem, HandcraftPickingWeight

    part = create_part(db, {"name": "P-EU", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "J-EU", "category": "单件"})
    add_stock(db, "part", part.id, 90.0, "初始入库")
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier SAQ3",
        "parts": [{"part_id": part.id, "qty": 100.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 1}],
    }).json()
    order_id = created["id"]
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order_id).one()
    db.add(HandcraftPickingWeight(
        handcraft_order_id=order_id,
        part_item_id=pi.id,
        atom_part_id=part.id,
        actual_qty=Decimal("80.0000"),
    ))
    db.flush()

    resp = client.post(f"/api/handcraft/{order_id}/send")
    assert resp.status_code == 200
    assert get_stock(db, "part", part.id) == pytest.approx(10.0)


def test_send_handcraft_stock_check_uses_effective_qty_over(client, db):
    """actual_qty=100 > stock=90 (even though pi.qty=80 would succeed) → fail."""
    from decimal import Decimal
    from models.handcraft_order import HandcraftPartItem, HandcraftPickingWeight

    part = create_part(db, {"name": "P-EO", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "J-EO", "category": "单件"})
    add_stock(db, "part", part.id, 90.0, "初始入库")
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier SAQ4",
        "parts": [{"part_id": part.id, "qty": 80.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 1}],
    }).json()
    order_id = created["id"]
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order_id).one()
    db.add(HandcraftPickingWeight(
        handcraft_order_id=order_id,
        part_item_id=pi.id,
        atom_part_id=part.id,
        actual_qty=Decimal("100.0000"),
    ))
    db.flush()

    resp = client.post(f"/api/handcraft/{order_id}/send")
    assert resp.status_code == 400
    assert "库存不足" in resp.json()["detail"]
    assert get_stock(db, "part", part.id) == pytest.approx(90.0)  # unchanged


def test_send_handcraft_composite_unaffected_by_atom_actual_qty(client, db):
    """Composite pi.qty=5 with atom actual_qty=99 → still deducts composite=5
    (current behavior: send_handcraft aggregates by part_id, including
    composite parents; atom override doesn't apply to the composite key)."""
    from decimal import Decimal
    from models.handcraft_order import HandcraftPartItem, HandcraftPickingWeight
    from models.part_bom import PartBom
    from services._helpers import _next_id

    composite = create_part(db, {"name": "Comp-SC", "category": "小配件"})
    composite.is_composite = True
    atom = create_part(db, {"name": "Atom-SC", "category": "小配件"})
    db.add(PartBom(
        id=_next_id(db, PartBom, "PB"),
        parent_part_id=composite.id,
        child_part_id=atom.id,
        qty_per_unit=Decimal("2"),
    ))
    jewelry = create_jewelry(db, {"name": "J-SC", "category": "单件"})
    add_stock(db, "part", composite.id, 50.0, "初始入库")
    db.flush()

    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier SC",
        "parts": [{"part_id": composite.id, "qty": 5.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 1}],
    }).json()
    order_id = created["id"]
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order_id).one()
    # atom override that should NOT influence the composite's deduction
    db.add(HandcraftPickingWeight(
        handcraft_order_id=order_id,
        part_item_id=pi.id,
        atom_part_id=atom.id,
        actual_qty=Decimal("99.0000"),
    ))
    db.flush()

    resp = client.post(f"/api/handcraft/{order_id}/send")
    assert resp.status_code == 200
    assert get_stock(db, "part", composite.id) == pytest.approx(45.0)  # 50 - 5
```

- [ ] **Step 2: Run the new tests; confirm they fail**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft.py -k "test_send_handcraft_uses_actual_qty or test_send_handcraft_falls_back or test_send_handcraft_stock_check or test_send_handcraft_composite_unaffected" -x --tb=short
```

Expected: tests with overrides FAIL (current behavior deducts pi.qty unconditionally). The "falls_back" and "composite_unaffected" tests should already PASS (they describe current behavior — but they'll guard Task 6).

If any of the OVERRIDE-using tests pass at this point, the wiring is already there — STOP and re-examine.

- [ ] **Step 3: Stage the tests (no commit yet)**

```bash
git add tests/test_api_handcraft.py
```

---

## Task 6: Implement `actual_qty` override in `send_handcraft_order`

**Files:**
- Modify: `services/handcraft.py` — `send_handcraft_order` aggregation loop (lines 292-295)

- [ ] **Step 1: Read the current block**

The current aggregation (line 292-295):

```python
    # Aggregate qty by part_id to avoid double-deducting when same part appears multiple times
    part_totals: dict[str, float] = {}
    for item in part_items:
        part_totals[item.part_id] = part_totals.get(item.part_id, 0.0) + float(item.qty)
```

- [ ] **Step 2: Replace with override-aware aggregation**

Edit `services/handcraft.py` lines 292-295:

```python
    # Load actual_qty overrides for this order. The key (pi.id, pi.part_id)
    # only matches atomic items; composite items naturally fall back to pi.qty
    # because their picking_weight rows have atom_part_id != pi.part_id.
    weight_rows = (
        db.query(HandcraftPickingWeight)
        .filter(
            HandcraftPickingWeight.handcraft_order_id == handcraft_order_id,
            HandcraftPickingWeight.actual_qty.is_not(None),
        )
        .all()
    )
    actual_by_key = {
        (w.part_item_id, w.atom_part_id): float(w.actual_qty)
        for w in weight_rows
    }
    # Aggregate effective qty by part_id (avoids double-deducting when same part appears multiple times)
    part_totals: dict[str, float] = {}
    for item in part_items:
        effective = actual_by_key.get((item.id, item.part_id), float(item.qty))
        part_totals[item.part_id] = part_totals.get(item.part_id, 0.0) + effective
```

- [ ] **Step 3: Run the failing tests; confirm they now pass**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft.py -k "test_send_handcraft_uses_actual_qty or test_send_handcraft_falls_back or test_send_handcraft_stock_check or test_send_handcraft_composite_unaffected" -x --tb=short
```

Expected: all PASS.

- [ ] **Step 4: Run the full test suite for regressions**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_handcraft.py tests/test_api_handcraft_picking_weight.py tests/test_api_handcraft_picking.py tests/test_handcraft.py tests/test_handcraft_item_crud.py -x --tb=short
```

Expected: all PASS. Pay attention to any test that asserts inventory_log totals after `send_handcraft` — those should still match because no actual_qty is set in those existing tests.

- [ ] **Step 5: Commit**

```bash
git add services/handcraft.py tests/test_api_handcraft.py
git commit -m "feat(handcraft): send_handcraft_order honors picking actual_qty for atomic items

For atomic part_items, deduct (actual_qty ?? pi.qty) instead of pi.qty.
Composite part_items are unchanged because the lookup key
(pi.id, pi.part_id) never matches a composite-expanded weight row
(which has atom_part_id != pi.part_id)."
```

---

## Task 7: Frontend — 「发出数量」column shows override with (原 N) marker

**Files:**
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue:1832-1850`

- [ ] **Step 1: Read the current render block**

The current `itemColumns` entry for 发出数量 (line 1832-1850):

```js
{
  title: '发出数量',
  key: 'qty',
  render: (row) => {
    const suggested = computeSuggestedQty(row)
    const actual = row.qty
    if (suggested == null) return actual ?? '-'
    return h(NTooltip, { trigger: 'hover' }, {
      trigger: () => h('span', { style: 'white-space: nowrap; cursor: help; font-variant-numeric: tabular-nums;' }, [
        h('span', null, actual ?? '-'),
        h('span', { style: 'color: #1890ff; margin-left: 4px; font-size: 13px;' }, [
          '（建议 ',
          h('span', { style: 'font-weight: 700; font-size: 14px;' }, suggested),
          '）',
        ]),
      ]),
      default: () => buildSuggestedTooltip(row),
    })
  },
},
```

Notice the existing local variable `actual` refers to `row.qty` (planned). Our new field is `row.actual_qty`. We need to **rename the existing `actual` variable** to avoid clashing.

- [ ] **Step 2: Replace the render with override-aware version**

Edit `frontend/src/views/handcraft/HandcraftDetail.vue` lines 1832-1850:

```js
{
  title: '发出数量',
  key: 'qty',
  render: (row) => {
    const suggested = computeSuggestedQty(row)
    const planned = row.qty
    const override = row.actual_qty
    const hasOverride = override != null && Number(override) !== Number(planned)
    const displayed = override ?? planned

    const mainContent = hasOverride
      ? [
          h('span', { style: 'color: #1a8917; font-weight: 600;' }, displayed),
          h('span', { style: 'color: #999; margin-left: 4px; font-size: 12px;' }, `(原 ${planned})`),
        ]
      : [h('span', null, displayed ?? '-')]

    if (suggested == null) {
      return h('span', { style: 'white-space: nowrap; font-variant-numeric: tabular-nums;' }, mainContent)
    }

    return h(NTooltip, { trigger: 'hover' }, {
      trigger: () => h('span', { style: 'white-space: nowrap; cursor: help; font-variant-numeric: tabular-nums;' }, [
        ...mainContent,
        h('span', { style: 'color: #1890ff; margin-left: 4px; font-size: 13px;' }, [
          '（建议 ',
          h('span', { style: 'font-weight: 700; font-size: 14px;' }, suggested),
          '）',
        ]),
      ]),
      default: () => buildSuggestedTooltip(row),
    })
  },
},
```

- [ ] **Step 3: Run the frontend build to confirm no syntax errors**

```bash
cd /Users/ycb/workspace/allen_shop/frontend && npm run build
```

Expected: build succeeds. If it fails, fix the syntax and re-run.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/handcraft/HandcraftDetail.vue
git commit -m "feat(handcraft-ui): render picking actual_qty in 发出数量 column

When picking modal set an actual_qty different from the planned pi.qty,
the column shows the override value in green with a small grey '(原 N)'
annotation for the planned value. Existing 建议 tooltip stays unchanged."
```

---

## Task 8: Frontend — reload parts list when picking modal closes

**Files:**
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue:528-533`

- [ ] **Step 1: Read the current modal block**

Current (lines 528-533):

```vue
<HandcraftPickingSimulationModal
  v-model:show="pickingModalShow"
  :order-id="String(route.params.id)"
  :status="order?.status || 'pending'"
  @restock-changed="loadRestock"
/>
```

- [ ] **Step 2: Replace `v-model:show` with explicit handler and add close-reload**

Edit `frontend/src/views/handcraft/HandcraftDetail.vue` lines 528-533:

```vue
<HandcraftPickingSimulationModal
  :show="pickingModalShow"
  :order-id="String(route.params.id)"
  :status="order?.status || 'pending'"
  @update:show="(v) => { pickingModalShow = v; if (!v) loadData() }"
  @restock-changed="loadRestock"
/>
```

Why explicit `:show` + `@update:show` instead of `v-model:show`: we need the same handler to update the ref AND trigger reload, so the sugar gets in the way.

- [ ] **Step 3: Run the frontend build**

```bash
cd /Users/ycb/workspace/allen_shop/frontend && npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/handcraft/HandcraftDetail.vue
git commit -m "feat(handcraft-ui): reload handcraft detail when picking modal closes

Ensures actual_qty and weight changes made inside the picking simulation
modal are immediately visible in the handcraft detail page. Single
loadData() call covers both columns because the 重量 column already
reads from the same picking response."
```

---

## Task 9: Manual end-to-end verification

**Files:** none (verification step)

This step is required because there is no frontend test infrastructure in this repo; UI behavior must be confirmed in a real browser before declaring the work done.

- [ ] **Step 1: Start backend and frontend dev servers**

In one terminal:
```bash
cd /Users/ycb/workspace/allen_shop && python main.py
```

In another:
```bash
cd /Users/ycb/workspace/allen_shop/frontend && npm run dev
```

Open http://localhost:5173 in a browser.

- [ ] **Step 2: Verify atomic actual_qty syncs to detail page**

1. Find or create a pending 手工单 with an atomic part_item (e.g., 链头) with planned qty=100. Make sure the part has stock.
2. Open the 手工单详情 page.
3. Click 配货模拟.
4. In the atomic row, click the 实际 input and enter `80`. Blur the input.
5. Close the modal.
6. Confirm: the 发出数量 column now shows `80 (原 100)` in green with grey "(原 100)" annotation, plus the existing blue 建议 tooltip.
7. Re-open the modal, clear the 实际 value (or set it to needed_qty). Close the modal.
8. Confirm: the 发出数量 column reverts to `100`, no green / no "(原 N)".

- [ ] **Step 3: Verify weight sync (附带收益)**

1. Re-open the picking modal.
2. In the same atomic row, enter a weight (e.g., 0.5 kg). Blur.
3. Close the modal.
4. Confirm: the 重量 column on the detail page now shows `0.5 kg`.

- [ ] **Step 4: Verify composite part is unaffected**

1. Find or create a pending 手工单 containing a composite part_item.
2. Open 配货模拟. Note the composite expands to multiple atom rows.
3. Set an 实际 value on one of the atom rows. Close the modal.
4. Confirm: the composite row in the detail's 发出数量 column is UNCHANGED (no green, no "(原 N)"). It still shows the planned pi.qty.

- [ ] **Step 5: Verify send-time stock deduction uses actual_qty**

1. On the order from Step 2 (still pending), set actual_qty=80 for the atomic item (planned=100).
2. Note current part stock via 配件详情 or inventory query.
3. Click 发出.
4. Re-check part stock: should be reduced by 80 (not 100).

- [ ] **Step 6: Verify composite still deducts by pi.qty**

1. On the composite order from Step 4, with an atom override set, click 发出.
2. Re-check the composite part's stock: should be reduced by `pi.qty` (the composite count), NOT by any atom override.

- [ ] **Step 7: Final regression sweep**

```bash
cd /Users/ycb/workspace/allen_shop && /Users/ycb/workspace/allen_shop/.venv/bin/pytest --tb=short
```

Expected: all tests pass.

- [ ] **Step 8: No commit needed** — verification only.

If any check fails, return to the relevant task and fix; otherwise the feature is complete.

---

## Self-Review Notes

- Spec §3 (data flow) — covered by Tasks 3, 6 (backend), 7, 8 (frontend)
- Spec §4.1 (schema) — Task 1
- Spec §4.2 (`_attach_actual_qty`) — Task 3
- Spec §4.3 (`send_handcraft_order`) — Task 6
- Spec §5.1 (column render) — Task 7
- Spec §5.2 (reload-on-close, weight bonus) — Task 8
- Spec §6 (edge cases) — covered by tests in Tasks 2, 4, 5 and verification in Task 9
- Spec §7 (test list) — all eight new test cases present (Tasks 2 + 4 + 5)
- Spec §8 (compatibility) — additive schema field, no migration; covered implicitly
