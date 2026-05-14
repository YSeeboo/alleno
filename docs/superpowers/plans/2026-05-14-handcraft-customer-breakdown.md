# Handcraft Customer Breakdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add customer-breakdown ("客户分拣") metadata to handcraft orders so the user can sort returned goods by customer, while keeping HC numbering and customer identities opaque to the supplier via a separate `receipt_code` and per-HC ephemeral aliases ("客户 1/2/3").

**Architecture:**
- Two additive columns: `HandcraftOrder.receipt_code` (5-char opaque code, supplier-facing) and `HandcraftJewelryItem.customer_name` (manual entry; from-order rows derive customer name via existing `OrderItemLink` chain).
- HC detail "产出明细" becomes an aggregated view grouped by `jewelry_id`, each group showing breakdown chips with source markers (订单来源 vs 手填).
- Order detail's batch shows a "分拣预览" banner inside the expanded `batch-detail` (Option B), driven by a new backend query.
- Supplier-facing PDFs use `receipt_code` instead of HC ID and replace customer names with ephemeral `客户 N` aliases enumerated per HC.

**Tech Stack:** FastAPI · SQLAlchemy 2.x · PostgreSQL (additive migration via `ensure_schema_compat()`, no Alembic) · pytest · Vue 3.5 + Naive UI · ReportLab (PDF)

**Conventions to respect:**
- Service functions are stateless pure functions; they call `db.flush()`, not `db.commit()`. Business errors raise `ValueError`; the API layer wraps with `service_errors()`.
- New IDs/codes via `secrets`, not `random`.
- `ensure_schema_compat()` uses inline `ALTER TABLE ... ADD COLUMN` blocks gated by `if column_name not in columns:` — follow that pattern.
- `bom_qty` on part items remains reference-only — do not touch.

---

## Phase 1 — Receipt code infrastructure

### Task 1.1: Add `receipt_code` column to `HandcraftOrder` model (nullable)

**Files:**
- Modify: `models/handcraft_order.py`
- Modify: `database.py:ensure_schema_compat`

- [ ] **Step 1: Add the column on the model (nullable for now — Phase 1.5 tightens it)**

In `models/handcraft_order.py`, add to the `HandcraftOrder` class:

```python
receipt_code = Column(String(5), nullable=True, unique=True, index=True)
```

Place it directly after `id`.

- [ ] **Step 2: Add the additive migration in `ensure_schema_compat`**

In `database.py`, inside the `ensure_schema_compat` body, find the existing block that operates on `handcraft_order` (e.g. the `delivery_images` add) and add another gated block alongside it:

```python
if inspector.has_table("handcraft_order"):
    columns = {col["name"] for col in inspector.get_columns("handcraft_order")}
    if "receipt_code" not in columns:
        conn.execute(text("ALTER TABLE handcraft_order ADD COLUMN receipt_code VARCHAR(5) NULL"))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_handcraft_order_receipt_code "
            "ON handcraft_order (receipt_code)"
        ))
```

- [ ] **Step 3: Commit**

```bash
git add models/handcraft_order.py database.py
git commit -m "feat(handcraft): add nullable receipt_code column on handcraft_order"
```

---

### Task 1.2: `_gen_receipt_code` generator

**Files:**
- Modify: `services/handcraft.py`
- Test: `tests/test_receipt_code.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_receipt_code.py`:

```python
import pytest

from services.handcraft import _gen_receipt_code, _RECEIPT_CODE_ALPHABET
from models.handcraft_order import HandcraftOrder


def test_gen_receipt_code_is_5_chars(db):
    code = _gen_receipt_code(db)
    assert len(code) == 5


def test_gen_receipt_code_uses_safe_alphabet(db):
    code = _gen_receipt_code(db)
    assert all(c in _RECEIPT_CODE_ALPHABET for c in code)
    # ensure ambiguous chars are excluded
    assert all(c not in code for c in "0OIL1")


def test_gen_receipt_code_is_unique(db):
    code1 = _gen_receipt_code(db)
    db.add(HandcraftOrder(id="HC-T1", supplier_name="王", status="pending", receipt_code=code1))
    db.flush()
    code2 = _gen_receipt_code(db)
    assert code1 != code2


def test_gen_receipt_code_raises_after_too_many_collisions(db, monkeypatch):
    import services.handcraft as svc
    fixed = "AAAAA"

    def stub_choice(_alphabet):
        return fixed[0]  # always 'A', so generated code is always "AAAAA"
    monkeypatch.setattr(svc.secrets, "choice", stub_choice)

    db.add(HandcraftOrder(id="HC-T2", supplier_name="王", status="pending", receipt_code=fixed))
    db.flush()
    with pytest.raises(RuntimeError, match="无法生成唯一回执码"):
        _gen_receipt_code(db, max_tries=3)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_receipt_code.py -v
```

Expected: ImportError (`_gen_receipt_code` / `_RECEIPT_CODE_ALPHABET` not found in `services.handcraft`).

- [ ] **Step 3: Implement the generator**

In `services/handcraft.py`, near the top of the file (after the existing imports), add:

```python
import secrets

_RECEIPT_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 28 chars, excludes 0/O/1/I/L


def _gen_receipt_code(db: Session, max_tries: int = 10) -> str:
    """Generate a unique 5-char opaque receipt code for a HandcraftOrder.

    Uses cryptographic randomness and rejects on collision via the unique index.
    28^5 ≈ 17.2M combinations — collisions are negligible at realistic volumes.
    """
    for _ in range(max_tries):
        code = "".join(secrets.choice(_RECEIPT_CODE_ALPHABET) for _ in range(5))
        if not db.query(HandcraftOrder.id).filter_by(receipt_code=code).first():
            return code
    raise RuntimeError("无法生成唯一回执码（碰撞次数超限）")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_receipt_code.py -v
```

Expected: all 4 pass.

- [ ] **Step 5: Commit**

```bash
git add services/handcraft.py tests/test_receipt_code.py
git commit -m "feat(handcraft): add _gen_receipt_code with collision-safe alphabet"
```

---

### Task 1.3: Wire `receipt_code` into `create_handcraft_order`

**Files:**
- Modify: `services/handcraft.py:create_handcraft_order`
- Test: `tests/test_receipt_code.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_receipt_code.py`:

```python
from services.handcraft import create_handcraft_order


def test_create_handcraft_order_assigns_receipt_code(db):
    # Need at least one part to satisfy create_handcraft_order requirements
    from models.part import Part
    db.add(Part(id="PJ-DZ-00001", name="测试", category="吊坠"))
    db.flush()
    order = create_handcraft_order(
        db,
        supplier_name="王师傅",
        parts=[{"part_id": "PJ-DZ-00001", "qty": 10}],
    )
    assert order.receipt_code is not None
    assert len(order.receipt_code) == 5


def test_create_handcraft_order_auto_merge_does_not_regenerate_code(db):
    from models.part import Part
    db.add(Part(id="PJ-DZ-00002", name="测试2", category="吊坠"))
    db.flush()
    first = create_handcraft_order(
        db, supplier_name="陈师傅",
        parts=[{"part_id": "PJ-DZ-00002", "qty": 5}],
    )
    original_code = first.receipt_code
    second = create_handcraft_order(
        db, supplier_name="陈师傅",
        parts=[{"part_id": "PJ-DZ-00002", "qty": 7}],
    )
    # auto-merge: same id and same code
    assert second.id == first.id
    assert second.receipt_code == original_code
```

- [ ] **Step 2: Run tests, observe failure**

```bash
pytest tests/test_receipt_code.py::test_create_handcraft_order_assigns_receipt_code -v
```

Expected: FAIL — `order.receipt_code is None`.

- [ ] **Step 3: Update `create_handcraft_order`**

In `services/handcraft.py`, find the `else` branch around line 211 (the branch that creates a new HandcraftOrder when there's no existing one to merge into):

```python
    else:
        order_id = _next_id(db, HandcraftOrder, "HC")
        order = HandcraftOrder(id=order_id, supplier_name=supplier_name, status="pending", note=note)
```

Change to:

```python
    else:
        order_id = _next_id(db, HandcraftOrder, "HC")
        order = HandcraftOrder(
            id=order_id,
            supplier_name=supplier_name,
            status="pending",
            note=note,
            receipt_code=_gen_receipt_code(db),
        )
```

The auto-merge branch (`if existing:`) doesn't touch `receipt_code`, so merged orders keep their original code.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_receipt_code.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add services/handcraft.py tests/test_receipt_code.py
git commit -m "feat(handcraft): create_handcraft_order assigns receipt_code on new HC"
```

---

### Task 1.4: Wire `receipt_code` into `link_supplier`

**Files:**
- Modify: `services/order_todo.py:link_supplier` (~line 820)
- Test: `tests/test_receipt_code.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_receipt_code.py`:

```python
def test_link_supplier_assigns_receipt_code(db, client):
    """End-to-end: creating HC via order_todo.link_supplier sets a receipt_code."""
    from tests.helpers import seed_order_with_batch  # see step 2
    order_id, batch_id = seed_order_with_batch(db)
    from services.order_todo import link_supplier
    result = link_supplier(db, order_id, batch_id, "王师傅")
    hc = db.query(HandcraftOrder).filter_by(id=result["handcraft_order_id"]).first()
    assert hc.receipt_code is not None
    assert len(hc.receipt_code) == 5
```

- [ ] **Step 2: Create the test helper**

Look for an existing seed helper in `tests/` — if none exists in `tests/helpers.py` for this purpose, create the file. Otherwise add to existing helpers module.

Create `tests/helpers.py` (or extend if it exists):

```python
"""Reusable test seed helpers."""

from models.part import Part
from models.jewelry import Jewelry
from models.bom import Bom
from models.order import Order
from models.order_todo import OrderTodoBatch, OrderTodoItem, OrderTodoBatchJewelry


def seed_order_with_batch(db, qty: int = 100):
    """Seed an order + jewelry + part + bom + batch. Returns (order_id, batch_id)."""
    db.add(Part(id="PJ-DZ-T100", name="测试主石", category="吊坠"))
    db.add(Jewelry(id="SP-T100", name="测试饰品", category="吊坠"))
    db.flush()
    db.add(Bom(jewelry_id="SP-T100", part_id="PJ-DZ-T100", qty_per_unit=1))
    db.flush()

    order = Order(id="OR-T100", customer_name="T 客户", status="pending")
    db.add(order)
    db.flush()

    batch = OrderTodoBatch(order_id=order.id)
    db.add(batch)
    db.flush()

    db.add(OrderTodoBatchJewelry(batch_id=batch.id, jewelry_id="SP-T100", quantity=qty))
    db.add(OrderTodoItem(batch_id=batch.id, part_id="PJ-DZ-T100", required_qty=qty))
    db.flush()

    return order.id, batch.id
```

> If you find any of the column names don't match the live model (e.g. `quantity` vs `qty`), fix the helper to match the model — `git grep "OrderTodoBatchJewelry"` to verify field names.

- [ ] **Step 3: Run test, observe failure**

```bash
pytest tests/test_receipt_code.py::test_link_supplier_assigns_receipt_code -v
```

Expected: FAIL — HC.receipt_code is None.

- [ ] **Step 4: Update `link_supplier`**

In `services/order_todo.py`, find the `else` branch inside `link_supplier` that creates a new `HCOrder` (search for `_next_id(db, HCOrder, "HC")`):

```python
    else:
        hc_id = _next_id(db, HCOrder, "HC")
        hc = HCOrder(id=hc_id, supplier_name=supplier_name, status="pending")
```

Change to:

```python
    else:
        from services.handcraft import _gen_receipt_code
        hc_id = _next_id(db, HCOrder, "HC")
        hc = HCOrder(
            id=hc_id,
            supplier_name=supplier_name,
            status="pending",
            receipt_code=_gen_receipt_code(db),
        )
```

(Keep the import local to avoid circular-import risk if `services.handcraft` imports anything from `services.order_todo`.)

- [ ] **Step 5: Run test, expect pass**

```bash
pytest tests/test_receipt_code.py::test_link_supplier_assigns_receipt_code -v
```

- [ ] **Step 6: Commit**

```bash
git add services/order_todo.py tests/test_receipt_code.py tests/helpers.py
git commit -m "feat(handcraft): link_supplier assigns receipt_code on new HC"
```

---

### Task 1.5: Backfill existing rows + enforce NOT NULL

**Files:**
- Modify: `database.py:ensure_schema_compat`
- Test: `tests/test_db_compat.py` (extend or create)

- [ ] **Step 1: Add backfill + NOT NULL tightening in `ensure_schema_compat`**

In `database.py`, after the column-add block from Task 1.1 (still inside the `if inspector.has_table("handcraft_order"):` block), append:

```python
    # Backfill receipt_code for any pre-existing rows
    missing_rows = conn.execute(text(
        "SELECT id FROM handcraft_order WHERE receipt_code IS NULL"
    )).scalars().all()
    if missing_rows:
        import secrets
        from services.handcraft import _RECEIPT_CODE_ALPHABET
        used_codes = set(conn.execute(text(
            "SELECT receipt_code FROM handcraft_order WHERE receipt_code IS NOT NULL"
        )).scalars().all())
        for hc_id in missing_rows:
            for _ in range(20):
                code = "".join(secrets.choice(_RECEIPT_CODE_ALPHABET) for _ in range(5))
                if code not in used_codes:
                    used_codes.add(code)
                    break
            else:
                raise RuntimeError(f"Failed to backfill receipt_code for {hc_id}")
            conn.execute(
                text("UPDATE handcraft_order SET receipt_code=:c WHERE id=:id"),
                {"c": code, "id": hc_id},
            )

    # Lock to NOT NULL once everything has a code. Query pg_attribute directly
    # rather than the cached SQLAlchemy inspector (which was created at function
    # start and may not reflect mid-function DDL).
    is_nullable = conn.execute(text(
        "SELECT NOT attnotnull FROM pg_attribute "
        "WHERE attrelid = 'handcraft_order'::regclass "
        "AND attname = 'receipt_code' AND attnum > 0"
    )).scalar()
    if is_nullable:
        conn.execute(text(
            "ALTER TABLE handcraft_order ALTER COLUMN receipt_code SET NOT NULL"
        ))
```

> The backfill uses a raw-connection version of the generator (no `db` Session needed). The retry budget is 20 — at 17M+ codes available, this is overwhelmingly safe.

- [ ] **Step 2: Write the failing test**

In `tests/test_db_compat.py`, add:

```python
from sqlalchemy import text
from database import ensure_schema_compat


def test_ensure_schema_compat_backfills_receipt_code(db, monkeypatch):
    """After ensure_schema_compat runs, no handcraft_order row should have NULL receipt_code."""
    # Insert a row with receipt_code NULL to simulate pre-migration state
    db.execute(text(
        "ALTER TABLE handcraft_order ALTER COLUMN receipt_code DROP NOT NULL"
    ))
    db.execute(text(
        "INSERT INTO handcraft_order (id, supplier_name, status, receipt_code) "
        "VALUES ('HC-OLD1', '历史商家', 'completed', NULL)"
    ))
    db.commit()
    ensure_schema_compat(db.get_bind())
    code = db.execute(text(
        "SELECT receipt_code FROM handcraft_order WHERE id='HC-OLD1'"
    )).scalar()
    assert code is not None
    assert len(code) == 5
```

- [ ] **Step 3: Run test, expect pass**

```bash
pytest tests/test_db_compat.py::test_ensure_schema_compat_backfills_receipt_code -v
```

- [ ] **Step 4: Make sure full existing suite still passes**

```bash
pytest -x
```

Expected: all pre-existing tests still pass. If anything fails because a test or fixture constructs `HandcraftOrder(...)` directly without `receipt_code`, find every such call:

```bash
git grep -n "HandcraftOrder(" tests/
```

For each match in `tests/`, add `receipt_code=...` to the constructor:
- For tests that don't care about the value, pass any 5-char unique string (e.g. `f"T{i:04d}"` where `i` is unique per fixture)
- For tests that exercise generation, use `receipt_code=_gen_receipt_code(db)` (import from `services.handcraft`)

Re-run `pytest -x` until clean.

- [ ] **Step 5: Commit**

```bash
git add database.py tests/test_db_compat.py
git commit -m "feat(handcraft): backfill receipt_code and enforce NOT NULL on existing rows"
```

---

### Task 1.6: Lookup-by-code service + API

**Files:**
- Modify: `services/handcraft.py`
- Modify: `api/handcraft.py`
- Test: `tests/test_api_handcraft.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api_handcraft.py`:

```python
def test_get_handcraft_order_by_receipt_code(client, db):
    from models.part import Part
    db.add(Part(id="PJ-DZ-LC1", name="lookup test", category="吊坠"))
    db.flush()
    from services.handcraft import create_handcraft_order
    order = create_handcraft_order(
        db, supplier_name="李师傅",
        parts=[{"part_id": "PJ-DZ-LC1", "qty": 1}],
    )
    db.flush()

    r = client.get(f"/api/handcraft-orders/by-receipt-code/{order.receipt_code}")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == order.id


def test_get_handcraft_order_by_receipt_code_404(client):
    r = client.get("/api/handcraft-orders/by-receipt-code/ZZZZZ")
    assert r.status_code == 404


def test_get_handcraft_order_by_receipt_code_case_insensitive(client, db):
    from models.part import Part
    db.add(Part(id="PJ-DZ-LC2", name="ci test", category="吊坠"))
    db.flush()
    from services.handcraft import create_handcraft_order
    order = create_handcraft_order(
        db, supplier_name="李师傅2",
        parts=[{"part_id": "PJ-DZ-LC2", "qty": 1}],
    )
    db.flush()

    r = client.get(f"/api/handcraft-orders/by-receipt-code/{order.receipt_code.lower()}")
    assert r.status_code == 200
```

- [ ] **Step 2: Run, expect fail**

```bash
pytest tests/test_api_handcraft.py::test_get_handcraft_order_by_receipt_code -v
```

Expected: 404 (route doesn't exist yet).

- [ ] **Step 3: Add the service function**

In `services/handcraft.py`, add:

```python
def get_handcraft_order_by_receipt_code(db: Session, code: str) -> Optional[HandcraftOrder]:
    """Look up a handcraft order by its 5-char opaque receipt code.

    Case-insensitive — the alphabet is uppercase but users may type lowercase.
    """
    return db.query(HandcraftOrder).filter_by(receipt_code=code.upper()).first()
```

- [ ] **Step 4: Add the API endpoint**

In `api/handcraft.py`, add an endpoint *above* the existing `/{handcraft_order_id}` path-parameter route so FastAPI routes `/by-receipt-code/{code}` first:

```python
@router.get("/by-receipt-code/{code}", response_model=HandcraftOrderResponse)
def api_get_handcraft_order_by_receipt_code(code: str, db: Session = Depends(get_db)):
    from services.handcraft import get_handcraft_order_by_receipt_code
    order = get_handcraft_order_by_receipt_code(db, code)
    if order is None:
        raise HTTPException(status_code=404, detail=f"无此回执编号：{code}")
    return order
```

- [ ] **Step 5: Run tests, expect pass**

```bash
pytest tests/test_api_handcraft.py::test_get_handcraft_order_by_receipt_code tests/test_api_handcraft.py::test_get_handcraft_order_by_receipt_code_404 tests/test_api_handcraft.py::test_get_handcraft_order_by_receipt_code_case_insensitive -v
```

- [ ] **Step 6: Commit**

```bash
git add services/handcraft.py api/handcraft.py tests/test_api_handcraft.py
git commit -m "feat(handcraft): GET /api/handcraft-orders/by-receipt-code/{code}"
```

---

## Phase 2 — Customer name + breakdown queries

### Task 2.1: Add `customer_name` column to `HandcraftJewelryItem`

**Files:**
- Modify: `models/handcraft_order.py`
- Modify: `database.py:ensure_schema_compat`
- Modify: `schemas/handcraft_order.py`

- [ ] **Step 1: Add column on the model**

In `models/handcraft_order.py`, in the `HandcraftJewelryItem` class:

```python
customer_name = Column(String, nullable=True)
```

- [ ] **Step 2: Add migration block**

In `database.py:ensure_schema_compat`, inside the existing `handcraft_jewelry_item`-related block (or add a new gated block if there isn't one):

```python
if inspector.has_table("handcraft_jewelry_item"):
    columns = {col["name"] for col in inspector.get_columns("handcraft_jewelry_item")}
    if "customer_name" not in columns:
        conn.execute(text("ALTER TABLE handcraft_jewelry_item ADD COLUMN customer_name VARCHAR NULL"))
```

- [ ] **Step 3: Extend Pydantic schemas**

In `schemas/handcraft_order.py`, find the existing `HandcraftJewelryItemCreate`, `HandcraftJewelryItemUpdate`, and `HandcraftJewelryItemResponse` (or equivalent names — `git grep "class HandcraftJewelryItem"` in schemas/). Add to each:

```python
customer_name: Optional[str] = None
```

If the file doesn't already import `Optional`, add `from typing import Optional`.

- [ ] **Step 4: Verify the existing suite still passes**

```bash
pytest -x
```

Expected: pass (column is additive).

- [ ] **Step 5: Commit**

```bash
git add models/handcraft_order.py database.py schemas/handcraft_order.py
git commit -m "feat(handcraft): add customer_name column on handcraft_jewelry_item"
```

---

### Task 2.2: `get_handcraft_jewelry_breakdown` service + API

**Files:**
- Modify: `services/handcraft.py`
- Modify: `schemas/handcraft_order.py`
- Modify: `api/handcraft.py`
- Test: `tests/test_handcraft_breakdown.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_handcraft_breakdown.py`:

```python
import pytest


@pytest.fixture
def hc_with_mixed_breakdown(db):
    """HC-X with: A客户·1000 (from OR-A), B客户·1200 (from OR-B), C客户·200 (manual).
    All three rows are jewelry_id=SP-MIX."""
    from models.part import Part
    from models.jewelry import Jewelry
    from models.order import Order
    from models.order_todo import OrderItemLink
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    from services.handcraft import _gen_receipt_code

    db.add(Jewelry(id="SP-MIX", name="混合测试", category="吊坠"))
    db.flush()

    hc = HandcraftOrder(id="HC-MIX", supplier_name="王", status="pending",
                       receipt_code=_gen_receipt_code(db))
    db.add(hc)
    db.flush()

    # From-order rows
    db.add(Order(id="OR-A", customer_name="A客户", status="pending"))
    db.add(Order(id="OR-B", customer_name="B客户", status="pending"))
    db.flush()

    j1 = HandcraftJewelryItem(handcraft_order_id="HC-MIX", jewelry_id="SP-MIX",
                              qty=1000, received_qty=0, status="未送出", unit="套",
                              customer_name=None)
    j2 = HandcraftJewelryItem(handcraft_order_id="HC-MIX", jewelry_id="SP-MIX",
                              qty=1200, received_qty=0, status="未送出", unit="套",
                              customer_name=None)
    j3 = HandcraftJewelryItem(handcraft_order_id="HC-MIX", jewelry_id="SP-MIX",
                              qty=200, received_qty=0, status="未送出", unit="套",
                              customer_name="C客户")
    db.add_all([j1, j2, j3])
    db.flush()

    db.add(OrderItemLink(order_id="OR-A", handcraft_jewelry_item_id=j1.id))
    db.add(OrderItemLink(order_id="OR-B", handcraft_jewelry_item_id=j2.id))
    db.flush()
    return hc.id


def test_breakdown_groups_by_jewelry_id(db, hc_with_mixed_breakdown):
    from services.handcraft import get_handcraft_jewelry_breakdown
    groups = get_handcraft_jewelry_breakdown(db, hc_with_mixed_breakdown)
    assert len(groups) == 1
    g = groups[0]
    assert g["jewelry_id"] == "SP-MIX"
    assert g["total_qty"] == 2400
    assert len(g["entries"]) == 3


def test_breakdown_entries_resolve_source(db, hc_with_mixed_breakdown):
    from services.handcraft import get_handcraft_jewelry_breakdown
    groups = get_handcraft_jewelry_breakdown(db, hc_with_mixed_breakdown)
    entries = {e["customer_name"]: e for e in groups[0]["entries"]}
    assert entries["A客户"]["source"] == "order"
    assert entries["A客户"]["source_order_id"] == "OR-A"
    assert entries["A客户"]["is_locked"] is True
    assert entries["B客户"]["source"] == "order"
    assert entries["C客户"]["source"] == "manual"
    assert entries["C客户"]["source_order_id"] is None
    assert entries["C客户"]["is_locked"] is False


def test_breakdown_api_endpoint(client, db, hc_with_mixed_breakdown):
    r = client.get(f"/api/handcraft-orders/{hc_with_mixed_breakdown}/jewelry-breakdown")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert data[0]["jewelry_id"] == "SP-MIX"
    assert data[0]["total_qty"] == 2400
```

- [ ] **Step 2: Run, expect fail**

```bash
pytest tests/test_handcraft_breakdown.py -v
```

Expected: ImportError on `get_handcraft_jewelry_breakdown`.

- [ ] **Step 3: Implement the service function**

In `services/handcraft.py`:

```python
def get_handcraft_jewelry_breakdown(db: Session, hc_id: str) -> list[dict]:
    """Aggregated jewelry view for HC detail.

    Returns one group per (jewelry_id, part_id) — usually jewelry_id, but a
    HandcraftJewelryItem can also be a part-output (part_id set instead).
    Each group sums qty/received_qty and lists per-row entries with the
    resolved customer name and its source ("order" or "manual").
    """
    from models.jewelry import Jewelry
    from models.part import Part
    from models.order import Order
    from models.order_todo import OrderItemLink

    rows = (
        db.query(HandcraftJewelryItem)
        .filter(HandcraftJewelryItem.handcraft_order_id == hc_id)
        .order_by(HandcraftJewelryItem.id.asc())
        .all()
    )
    if not rows:
        return []

    # Bulk-resolve OrderItemLink → Order for any rows with no customer_name
    row_ids = [r.id for r in rows]
    link_rows = (
        db.query(OrderItemLink.handcraft_jewelry_item_id, Order.id.label("order_id"),
                 Order.customer_name)
        .join(Order, Order.id == OrderItemLink.order_id)
        .filter(OrderItemLink.handcraft_jewelry_item_id.in_(row_ids))
        .all()
    )
    link_by_item = {lr.handcraft_jewelry_item_id: lr for lr in link_rows}

    # Jewelry / Part name + image lookups (for output kinds)
    jewelry_ids = {r.jewelry_id for r in rows if r.jewelry_id}
    part_ids = {r.part_id for r in rows if r.part_id and not r.jewelry_id}
    jewelry_map = {
        j.id: j for j in db.query(Jewelry).filter(Jewelry.id.in_(jewelry_ids)).all()
    } if jewelry_ids else {}
    part_map = {
        p.id: p for p in db.query(Part).filter(Part.id.in_(part_ids)).all()
    } if part_ids else {}

    # Group rows by their identity (jewelry_id preferred, else part_id)
    from collections import defaultdict
    grouped: dict[tuple[str, str], list[HandcraftJewelryItem]] = defaultdict(list)
    for r in rows:
        kind = "jewelry" if r.jewelry_id else "part"
        identity = r.jewelry_id or r.part_id
        grouped[(kind, identity)].append(r)

    _STATUS_RANK = {"未送出": 0, "制作中": 1, "已收回": 2}
    result = []
    for (kind, identity), group_rows in grouped.items():
        if kind == "jewelry":
            obj = jewelry_map.get(identity)
            name = obj.name if obj else identity
            image = getattr(obj, "image", None) if obj else None
        else:
            obj = part_map.get(identity)
            name = obj.name if obj else identity
            image = getattr(obj, "image", None) if obj else None

        entries = []
        for r in group_rows:
            link = link_by_item.get(r.id)
            if r.customer_name is not None:
                customer = r.customer_name
                source = "manual"
                source_order_id = None
            elif link:
                customer = link.customer_name
                source = "order"
                source_order_id = link.order_id
            else:
                customer = None
                source = "manual"
                source_order_id = None
            entries.append({
                "hc_jewelry_item_id": r.id,
                "qty": float(r.qty),
                "received_qty": float(r.received_qty or 0),
                "customer_name": customer,
                "source": source,
                "source_order_id": source_order_id,
                "is_locked": source == "order",
            })

        # Group-level aggregate status: lowest rank wins (any unsent → 未送出)
        status = min(group_rows, key=lambda r: _STATUS_RANK.get(r.status, 99)).status

        result.append({
            "kind": kind,
            "jewelry_id": identity,
            "jewelry_name": name,
            "jewelry_image": image,
            "total_qty": sum(float(r.qty) for r in group_rows),
            "received_qty": sum(float(r.received_qty or 0) for r in group_rows),
            "status": status,
            "entries": entries,
        })
    return result
```

- [ ] **Step 4: Add Pydantic response schemas**

In `schemas/handcraft_order.py`:

```python
from typing import Literal

class HandcraftJewelryBreakdownEntry(BaseModel):
    hc_jewelry_item_id: int
    qty: float
    received_qty: float
    customer_name: Optional[str] = None
    source: Literal["order", "manual"]
    source_order_id: Optional[str] = None
    is_locked: bool

    model_config = ConfigDict(from_attributes=True)


class HandcraftJewelryBreakdownGroup(BaseModel):
    kind: Literal["jewelry", "part"]
    jewelry_id: str
    jewelry_name: str
    jewelry_image: Optional[str] = None
    total_qty: float
    received_qty: float
    status: str
    entries: list[HandcraftJewelryBreakdownEntry]

    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 5: Add the API endpoint**

In `api/handcraft.py`:

```python
@router.get("/{handcraft_order_id}/jewelry-breakdown",
            response_model=list[HandcraftJewelryBreakdownGroup])
def api_get_handcraft_jewelry_breakdown(
    handcraft_order_id: str, db: Session = Depends(get_db),
):
    from services.handcraft import get_handcraft_jewelry_breakdown
    return get_handcraft_jewelry_breakdown(db, handcraft_order_id)
```

Add `HandcraftJewelryBreakdownGroup` to the imports near the top of the file.

- [ ] **Step 6: Run tests, expect pass**

```bash
pytest tests/test_handcraft_breakdown.py -v
```

- [ ] **Step 7: Commit**

```bash
git add services/handcraft.py schemas/handcraft_order.py api/handcraft.py tests/test_handcraft_breakdown.py
git commit -m "feat(handcraft): aggregated jewelry breakdown service + API"
```

---

### Task 2.3: `get_batch_breakdown_preview` service + API

**Files:**
- Modify: `services/order_todo.py`
- Modify: `schemas/order.py` (or `schemas/order_todo.py` — match wherever batch schemas live)
- Modify: `api/orders.py`
- Test: `tests/test_api_order_todo.py` (extend)

- [ ] **Step 1: Write the failing test**

In `tests/test_api_order_todo.py` (or a new file if you prefer), add:

```python
def test_batch_breakdown_preview_returns_jewelry_list(db, client):
    from tests.helpers import seed_order_with_batch
    order_id, batch_id = seed_order_with_batch(db, qty=500)
    from services.order_todo import link_supplier
    result = link_supplier(db, order_id, batch_id, "王师傅")
    hc_id = result["handcraft_order_id"]

    r = client.get(f"/api/orders/{order_id}/batches/{batch_id}/breakdown-preview")
    assert r.status_code == 200
    data = r.json()
    assert data is not None
    assert data["handcraft_order_id"] == hc_id
    assert data["receipt_code"] is not None
    assert data["supplier_name"] == "王师傅"
    assert data["customer_name"] == "T 客户"
    assert len(data["jewelry_items"]) == 1
    assert data["jewelry_items"][0]["jewelry_id"] == "SP-T100"
    assert data["jewelry_items"][0]["qty"] == 500


def test_batch_breakdown_preview_returns_null_when_unassigned(db, client):
    from tests.helpers import seed_order_with_batch
    order_id, batch_id = seed_order_with_batch(db, qty=10)

    r = client.get(f"/api/orders/{order_id}/batches/{batch_id}/breakdown-preview")
    assert r.status_code == 200
    assert r.json() is None
```

- [ ] **Step 2: Run, expect fail (404)**

```bash
pytest tests/test_api_order_todo.py::test_batch_breakdown_preview_returns_jewelry_list -v
```

- [ ] **Step 3: Implement service function**

In `services/order_todo.py`:

```python
def get_batch_breakdown_preview(db: Session, order_id: str, batch_id: int) -> Optional[dict]:
    """Return a preview of how this batch contributes to its assigned HC's customer breakdown.

    Returns None when the batch is not yet linked to a handcraft order.
    """
    from models.jewelry import Jewelry
    from models.handcraft_order import HandcraftOrder as HCOrder, HandcraftJewelryItem
    from models.order import Order

    batch = db.query(OrderTodoBatch).filter_by(id=batch_id, order_id=order_id).first()
    if batch is None:
        raise ValueError(f"批次 {batch_id} 不存在")
    if not batch.handcraft_order_id:
        return None

    hc = db.query(HCOrder).filter_by(id=batch.handcraft_order_id).first()
    if hc is None:
        return None

    order = db.query(Order).filter_by(id=order_id).first()

    rows = (
        db.query(HandcraftJewelryItem, Jewelry)
        .outerjoin(Jewelry, HandcraftJewelryItem.jewelry_id == Jewelry.id)
        .join(OrderTodoBatchJewelry,
              OrderTodoBatchJewelry.handcraft_jewelry_item_id == HandcraftJewelryItem.id)
        .filter(OrderTodoBatchJewelry.batch_id == batch_id)
        .all()
    )

    return {
        "handcraft_order_id": hc.id,
        "receipt_code": hc.receipt_code,
        "supplier_name": hc.supplier_name,
        "customer_name": order.customer_name if order else None,
        "jewelry_items": [
            {
                "jewelry_id": j.id if j else hj.jewelry_id,
                "jewelry_name": j.name if j else (hj.jewelry_id or ""),
                "qty": float(hj.qty),
            }
            for hj, j in rows
        ],
    }
```

- [ ] **Step 4: Pydantic schemas**

In `schemas/order.py` (create if missing; check `git ls-files schemas/` first):

```python
from typing import Optional
from pydantic import BaseModel, ConfigDict


class BatchBreakdownPreviewItem(BaseModel):
    jewelry_id: str
    jewelry_name: str
    qty: float

    model_config = ConfigDict(from_attributes=True)


class BatchBreakdownPreview(BaseModel):
    handcraft_order_id: str
    receipt_code: str
    supplier_name: str
    customer_name: Optional[str] = None
    jewelry_items: list[BatchBreakdownPreviewItem]

    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 5: Add API endpoint**

In `api/orders.py`, near the existing order_todo / batch endpoints:

```python
@router.get(
    "/{order_id}/batches/{batch_id}/breakdown-preview",
    response_model=Optional[BatchBreakdownPreview],
)
def api_get_batch_breakdown_preview(order_id: str, batch_id: int, db: Session = Depends(get_db)):
    from services.order_todo import get_batch_breakdown_preview
    with service_errors():
        return get_batch_breakdown_preview(db, order_id, batch_id)
```

Import `BatchBreakdownPreview` and `Optional` at the top of `api/orders.py`.

- [ ] **Step 6: Run tests, expect pass**

```bash
pytest tests/test_api_order_todo.py::test_batch_breakdown_preview_returns_jewelry_list tests/test_api_order_todo.py::test_batch_breakdown_preview_returns_null_when_unassigned -v
```

- [ ] **Step 7: Commit**

```bash
git add services/order_todo.py schemas/order.py api/orders.py tests/test_api_order_todo.py
git commit -m "feat(orders): GET /api/orders/{id}/batches/{bid}/breakdown-preview"
```

---

### Task 2.4: `update_handcraft_jewelry` allows `customer_name` in processing

**Files:**
- Modify: `services/handcraft.py:update_handcraft_jewelry`
- Test: `tests/test_handcraft_breakdown.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_handcraft_breakdown.py`:

```python
def test_update_customer_name_allowed_in_processing(db):
    """customer_name is pure metadata — editable in pending and processing."""
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    from models.jewelry import Jewelry
    from services.handcraft import _gen_receipt_code, update_handcraft_jewelry

    db.add(Jewelry(id="SP-UJ", name="x", category="吊坠"))
    db.flush()
    hc = HandcraftOrder(id="HC-UJ", supplier_name="测", status="processing",
                       receipt_code=_gen_receipt_code(db))
    db.add(hc)
    db.flush()
    j = HandcraftJewelryItem(handcraft_order_id="HC-UJ", jewelry_id="SP-UJ",
                            qty=100, received_qty=0, status="制作中", unit="套",
                            customer_name="旧客户")
    db.add(j)
    db.flush()

    updated = update_handcraft_jewelry(db, "HC-UJ", j.id, {"customer_name": "新客户"})
    assert updated.customer_name == "新客户"


def test_update_qty_still_blocked_in_processing(db):
    """qty edits remain pending-only — existing rule."""
    import pytest
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    from models.jewelry import Jewelry
    from services.handcraft import _gen_receipt_code, update_handcraft_jewelry

    db.add(Jewelry(id="SP-UJ2", name="x", category="吊坠"))
    db.flush()
    hc = HandcraftOrder(id="HC-UJ2", supplier_name="测", status="processing",
                       receipt_code=_gen_receipt_code(db))
    db.add(hc)
    db.flush()
    j = HandcraftJewelryItem(handcraft_order_id="HC-UJ2", jewelry_id="SP-UJ2",
                            qty=100, received_qty=0, status="制作中", unit="套")
    db.add(j)
    db.flush()

    with pytest.raises(ValueError, match="status"):
        update_handcraft_jewelry(db, "HC-UJ2", j.id, {"qty": 200})


def test_update_customer_name_blocked_for_order_linked_row(db, hc_with_mixed_breakdown):
    """From-order rows: customer_name must be edited at the order, not here."""
    import pytest
    from models.handcraft_order import HandcraftJewelryItem
    from services.handcraft import update_handcraft_jewelry

    j = db.query(HandcraftJewelryItem).filter_by(
        handcraft_order_id=hc_with_mixed_breakdown, qty=1000
    ).first()  # A 客户 row, has OrderItemLink
    with pytest.raises(ValueError, match="订单"):
        update_handcraft_jewelry(db, hc_with_mixed_breakdown, j.id,
                                {"customer_name": "改名"})


def test_update_customer_name_blocked_when_completed(db):
    import pytest
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    from models.jewelry import Jewelry
    from services.handcraft import _gen_receipt_code, update_handcraft_jewelry

    db.add(Jewelry(id="SP-UJ3", name="x", category="吊坠"))
    db.flush()
    hc = HandcraftOrder(id="HC-UJ3", supplier_name="测", status="completed",
                       receipt_code=_gen_receipt_code(db))
    db.add(hc)
    db.flush()
    j = HandcraftJewelryItem(handcraft_order_id="HC-UJ3", jewelry_id="SP-UJ3",
                            qty=100, received_qty=100, status="已收回", unit="套",
                            customer_name="x")
    db.add(j)
    db.flush()
    with pytest.raises(ValueError):
        update_handcraft_jewelry(db, "HC-UJ3", j.id, {"customer_name": "y"})
```

- [ ] **Step 2: Run, observe failures**

```bash
pytest tests/test_handcraft_breakdown.py -v
```

Expected: the new tests fail because existing `update_handcraft_jewelry` is pending-only.

- [ ] **Step 3: Modify `update_handcraft_jewelry`**

In `services/handcraft.py:update_handcraft_jewelry`, replace the existing function body with this revised structure:

```python
def update_handcraft_jewelry(db: Session, order_id: str, item_id: int, data: dict) -> HandcraftJewelryItem:
    from models.order_todo import OrderItemLink

    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    item = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.id == item_id,
        HandcraftJewelryItem.handcraft_order_id == order_id,
    ).first()
    if item is None:
        raise ValueError(f"HandcraftJewelryItem {item_id} not found in order {order_id}")

    # customer_name has looser rules: pending or processing, never when completed,
    # and never on rows that are linked to an order (must edit at the source).
    if "customer_name" in data:
        if order.status == "completed":
            raise ValueError("已完成的手工单不能修改客户名")
        has_order_link = db.query(OrderItemLink.id).filter_by(
            handcraft_jewelry_item_id=item.id
        ).first() is not None
        if has_order_link:
            raise ValueError("订单来源行的客户名需在对应订单详情修改")
        item.customer_name = data["customer_name"]

    # All other fields follow the existing pending-only rule.
    other_fields = {k: v for k, v in data.items() if k != "customer_name"}
    if other_fields:
        if order.status != "pending":
            raise ValueError(
                f"Cannot update jewelry: order {order_id} status is '{order.status}', "
                f"must be 'pending'"
            )
        for field in ("qty", "unit", "note"):
            if field in other_fields and other_fields[field] is not None:
                setattr(item, field, other_fields[field])
        for wf in ("weight", "weight_unit"):
            if wf in other_fields:
                setattr(item, wf, other_fields[wf])

    db.flush()
    return item
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_handcraft_breakdown.py -v
```

- [ ] **Step 5: Run the whole suite for regressions**

```bash
pytest -x
```

If a pre-existing test was relying on the old pending-only-everything behavior with `customer_name=None` passed in update payloads, it may need adjustment — `customer_name=None` is now interpreted as "set to None" rather than ignored. Use `data.pop("customer_name", None) if data["customer_name"] is None else ...` if you find this is an issue, but most callers should be explicit.

- [ ] **Step 6: Commit**

```bash
git add services/handcraft.py tests/test_handcraft_breakdown.py
git commit -m "feat(handcraft): allow customer_name edits in processing for manual rows"
```

---

### Task 2.5: `add_handcraft_jewelry` accepts `customer_name` (pending-only)

**Files:**
- Modify: `services/handcraft.py:add_handcraft_jewelry`
- Test: `tests/test_handcraft_breakdown.py` (extend)

> **Note:** The design says new manual entries are pending-only. The existing `add_handcraft_jewelry` allows `pending` and `processing`. We will **tighten** it: when `customer_name` is set, require pending. When not set (the legacy code path that adds an unattributed jewelry row, e.g. via `link_supplier`), keep allowing processing — that path is internal infrastructure, not user UI.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_handcraft_breakdown.py`:

```python
def test_add_manual_jewelry_allowed_in_pending(db):
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    from models.jewelry import Jewelry
    from services.handcraft import _gen_receipt_code, add_handcraft_jewelry

    db.add(Jewelry(id="SP-AJ", name="x", category="吊坠"))
    db.flush()
    hc = HandcraftOrder(id="HC-AJ", supplier_name="测", status="pending",
                       receipt_code=_gen_receipt_code(db))
    db.add(hc)
    db.flush()

    item = add_handcraft_jewelry(db, "HC-AJ",
        {"jewelry_id": "SP-AJ", "qty": 50, "customer_name": "Z 客户"})
    assert item.customer_name == "Z 客户"


def test_add_manual_jewelry_blocked_in_processing(db):
    import pytest
    from models.handcraft_order import HandcraftOrder
    from models.jewelry import Jewelry
    from services.handcraft import _gen_receipt_code, add_handcraft_jewelry

    db.add(Jewelry(id="SP-AJ2", name="x", category="吊坠"))
    db.flush()
    hc = HandcraftOrder(id="HC-AJ2", supplier_name="测", status="processing",
                       receipt_code=_gen_receipt_code(db))
    db.add(hc)
    db.flush()
    with pytest.raises(ValueError, match="手填客户"):
        add_handcraft_jewelry(db, "HC-AJ2",
            {"jewelry_id": "SP-AJ2", "qty": 50, "customer_name": "Z 客户"})
```

- [ ] **Step 2: Run, observe failure**

```bash
pytest tests/test_handcraft_breakdown.py::test_add_manual_jewelry_blocked_in_processing -v
```

- [ ] **Step 3: Modify `add_handcraft_jewelry`**

In `services/handcraft.py:add_handcraft_jewelry`, find the existing function and (a) accept `customer_name`, (b) add the processing-state guard:

```python
def add_handcraft_jewelry(db: Session, order_id: str, item: dict) -> HandcraftJewelryItem:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    if order.status not in ("pending", "processing"):
        raise ValueError(
            f"Cannot add jewelry: order {order_id} status is '{order.status}', "
            f"must be 'pending' or 'processing'"
        )
    customer_name = item.get("customer_name")
    if customer_name is not None and order.status != "pending":
        raise ValueError("发出后不可新增手填客户分拣行；请在 pending 状态完成")

    jewelry_id = item.get("jewelry_id")
    part_id = item.get("part_id")
    if jewelry_id and part_id:
        raise ValueError("产出项不能同时指定 jewelry_id 和 part_id")
    if jewelry_id:
        _require_jewelry(db, jewelry_id)
    elif part_id:
        _require_part(db, part_id)
    else:
        raise ValueError("产出项必须指定 jewelry_id 或 part_id")
    item_status = "制作中" if order.status == "processing" else "未送出"
    default_unit = "套" if jewelry_id else "个"
    new_item = HandcraftJewelryItem(
        handcraft_order_id=order_id,
        jewelry_id=jewelry_id,
        part_id=part_id,
        qty=item["qty"],
        weight=item.get("weight"),
        weight_unit=item.get("weight_unit"),
        received_qty=0,
        status=item_status,
        unit=item.get("unit") or default_unit,
        note=item.get("note"),
        customer_name=customer_name,
    )
    db.add(new_item)
    db.flush()
    return new_item
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_handcraft_breakdown.py -v
pytest -x  # full regression
```

- [ ] **Step 5: Commit**

```bash
git add services/handcraft.py tests/test_handcraft_breakdown.py
git commit -m "feat(handcraft): add_handcraft_jewelry accepts customer_name (pending-only)"
```

---

## Phase 3 — PDF rendering

### Task 3.1: Replace HC-XXXX with receipt_code on supplier-facing PDFs

**Files:**
- Modify: `services/handcraft_pdf.py`
- Modify: `services/handcraft_picking_list_pdf.py`
- Test: `tests/test_api_handcraft_pdf.py` (extend) or add to `tests/test_api_handcraft_picking.py`

- [ ] **Step 1: Locate where HC ID currently appears in the supplier PDF**

```bash
grep -n 'order\.id\|handcraft_order_id\|手工单号\|"HC-\|order_id' services/handcraft_pdf.py services/handcraft_picking_list_pdf.py
```

Note each line — these are the call sites that need to switch to `order.receipt_code` for supplier-facing pages.

- [ ] **Step 2: Write a failing test**

Append to `tests/test_api_handcraft_pdf.py`:

```python
def test_handcraft_pdf_uses_receipt_code_not_hc_id(client, db):
    from models.part import Part
    db.add(Part(id="PJ-DZ-PDF1", name="x", category="吊坠"))
    db.flush()
    from services.handcraft import create_handcraft_order
    order = create_handcraft_order(
        db, supplier_name="王",
        parts=[{"part_id": "PJ-DZ-PDF1", "qty": 1}],
    )
    db.flush()

    r = client.get(f"/api/handcraft-orders/{order.id}/pdf")
    assert r.status_code == 200
    body = r.content
    # The PDF binary should contain the receipt_code and NOT the HC ID
    assert order.receipt_code.encode("ascii") in body
    assert order.id.encode("ascii") not in body
```

Find the exact PDF endpoint path — `grep -rn 'pdf' api/handcraft.py | head` — and adjust the URL above if the path differs.

- [ ] **Step 3: Run, expect fail**

```bash
pytest tests/test_api_handcraft_pdf.py::test_handcraft_pdf_uses_receipt_code_not_hc_id -v
```

- [ ] **Step 4: Replace HC ID with receipt_code in the PDFs**

In `services/handcraft_pdf.py`, at every place where `order.id` or the HC ID string is rendered into the supplier-facing PDF (header title, watermark, footer label, etc.), swap to `f"回执编号 · {order.receipt_code}"` or just `order.receipt_code`. Concrete pattern:

Before:
```python
header_text = f"手工单 {order.id}"
```

After:
```python
header_text = f"回执编号 · {order.receipt_code}"
```

Do the same audit in `services/handcraft_picking_list_pdf.py`. Internal-only PDFs (`services/handcraft_receipt.py` if it generates one) keep HC ID — those don't go to the supplier.

- [ ] **Step 5: Run tests, expect pass**

```bash
pytest tests/test_api_handcraft_pdf.py -v
pytest -x  # regression
```

- [ ] **Step 6: Commit**

```bash
git add services/handcraft_pdf.py services/handcraft_picking_list_pdf.py tests/test_api_handcraft_pdf.py
git commit -m "feat(handcraft): supplier-facing PDFs print receipt_code, not HC ID"
```

---

### Task 3.2: Append "手工回执" page with 客户 N aliasing

**Files:**
- Modify: `services/handcraft_pdf.py`
- Test: `tests/test_api_handcraft_pdf.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api_handcraft_pdf.py`:

```python
def test_handcraft_pdf_appends_receipt_page_with_aliases(client, db):
    """手工回执 page: present, uses 客户 1/2/3 aliases, hides real customer names."""
    from models.part import Part
    from models.jewelry import Jewelry
    from models.handcraft_order import HandcraftJewelryItem
    db.add(Part(id="PJ-DZ-RP", name="x", category="吊坠"))
    db.add(Jewelry(id="SP-RP", name="回执页测试饰品", category="吊坠"))
    db.flush()
    from services.handcraft import create_handcraft_order
    order = create_handcraft_order(
        db, supplier_name="王",
        parts=[{"part_id": "PJ-DZ-RP", "qty": 1}],
    )
    # Add three manual breakdown rows
    db.add_all([
        HandcraftJewelryItem(handcraft_order_id=order.id, jewelry_id="SP-RP",
                             qty=1000, received_qty=0, status="未送出", unit="套",
                             customer_name="周大福"),
        HandcraftJewelryItem(handcraft_order_id=order.id, jewelry_id="SP-RP",
                             qty=1200, received_qty=0, status="未送出", unit="套",
                             customer_name="上海陈姐"),
        HandcraftJewelryItem(handcraft_order_id=order.id, jewelry_id="SP-RP",
                             qty=200, received_qty=0, status="未送出", unit="套",
                             customer_name="广州王哥"),
    ])
    db.flush()

    r = client.get(f"/api/handcraft-orders/{order.id}/pdf")
    body = r.content
    assert "手工回执".encode("utf-8") in body
    assert "客户 1".encode("utf-8") in body
    assert "客户 2".encode("utf-8") in body
    assert "客户 3".encode("utf-8") in body
    # Real names must not appear on this supplier-facing PDF
    assert "周大福".encode("utf-8") not in body
    assert "上海陈姐".encode("utf-8") not in body
    assert "广州王哥".encode("utf-8") not in body
```

> Note: ReportLab encodes Chinese via the embedded font. If the test font is bundled, this byte-search works. If the bytes are encoded differently, switch to extracting text via `pypdf` or `pdfminer` — but try the bytes approach first.

- [ ] **Step 2: Run, expect fail (no 手工回执 page yet)**

```bash
pytest tests/test_api_handcraft_pdf.py::test_handcraft_pdf_appends_receipt_page_with_aliases -v
```

- [ ] **Step 3: Implement the receipt page renderer**

In `services/handcraft_pdf.py`, add a helper that takes the breakdown groups and emits a new ReportLab `Page`. Sketch:

```python
def _render_handcraft_receipt_page(story, order, breakdown_groups, styles):
    """Append the "手工回执" supplier page with 客户 N aliasing.

    Only jewelry-kind groups with at least one breakdown entry are included.
    Customer real names are replaced by per-HC sequential aliases (客户 1, 客户 2...),
    enumerated within each jewelry group by hc_jewelry_item_id order.
    """
    from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors

    story.append(PageBreak())
    story.append(Paragraph("<b>手工回执</b>", styles["title-large"]))
    story.append(Paragraph(f"回执编号 · {order.receipt_code}", styles["subtitle-mono"]))
    story.append(Spacer(1, 12))

    # Meta strip: 手工商家 / 发出日期
    meta = [[f"手工商家：{order.supplier_name}",
             f"发出日期：{order.created_at.strftime('%Y-%m-%d') if order.created_at else '—'}"]]
    t = Table(meta, colWidths=[260, 260])
    t.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 1, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
    ]))
    story.append(t)
    story.append(Spacer(1, 16))

    story.append(Paragraph("<b>客户分拣</b>", styles["section-title"]))
    story.append(Spacer(1, 8))

    for group in breakdown_groups:
        if group["kind"] != "jewelry":
            continue
        entries = [e for e in group["entries"] if e["customer_name"]]
        if not entries:
            continue
        # Group header
        story.append(Paragraph(
            f"{group['jewelry_name']}　共 {int(group['total_qty'])} 套",
            styles["group-head"],
        ))
        # Lines with 客户 N aliases (enumerated by hc_jewelry_item_id order — stable)
        rows = []
        for idx, e in enumerate(sorted(entries, key=lambda x: x["hc_jewelry_item_id"]), 1):
            rows.append(["☐", f"客户 {idx}", f"{int(e['qty'])}"])
        body = Table(rows, colWidths=[24, 200, 80])
        body.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 12),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.lightgrey),
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(body)
        story.append(Spacer(1, 12))

    story.append(Spacer(1, 18))
    story.append(Paragraph(
        "请于回货时随成品一并交回此单以便分拣核对",
        styles["note-dashed"],
    ))
```

Then in the existing PDF entry function (`build_handcraft_order_pdf`), after the existing pages are appended:

```python
from services.handcraft import get_handcraft_jewelry_breakdown
breakdown = get_handcraft_jewelry_breakdown(db, order_id)
_render_handcraft_receipt_page(story, order, breakdown, styles)
```

> The exact `styles["title-large"]` / `styles["subtitle-mono"]` / etc. names must match the style dict the existing PDF uses. Look at how the existing pages build paragraphs and reuse those style keys (or define new ones near the top of the file). Match the existing PDF's font registration — ReportLab needs the CJK font registered to render Chinese.

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_api_handcraft_pdf.py -v
```

If the byte-search test fails because Chinese is encoded across multiple PDF objects, switch to extracting text:

```python
from io import BytesIO
from pypdf import PdfReader
reader = PdfReader(BytesIO(r.content))
all_text = "\n".join(p.extract_text() or "" for p in reader.pages)
assert "手工回执" in all_text
assert "客户 1" in all_text
assert "周大福" not in all_text
```

Pin `pypdf` in `requirements.txt` (dev-only acceptable).

- [ ] **Step 5: Commit**

```bash
git add services/handcraft_pdf.py tests/test_api_handcraft_pdf.py
git commit -m "feat(handcraft): append 手工回执 last page with 客户 N aliasing"
```

---

## Phase 4 — Frontend

### Task 4.1: API client additions + HC list lookup-by-code search

**Files:**
- Modify: `frontend/src/api/handcraft.js`
- Modify: `frontend/src/api/orders.js`
- Modify: `frontend/src/views/handcraft/HandcraftList.vue`

> Frontend tests are not part of this project — verify manually in the browser.

- [ ] **Step 1: Add API client wrappers**

In `frontend/src/api/handcraft.js`, add:

```javascript
export function getHandcraftByReceiptCode(code) {
  return api.get(`/api/handcraft-orders/by-receipt-code/${encodeURIComponent(code)}`)
}

export function getHandcraftJewelryBreakdown(hcId) {
  return api.get(`/api/handcraft-orders/${encodeURIComponent(hcId)}/jewelry-breakdown`)
}
```

In `frontend/src/api/orders.js`:

```javascript
export function getBatchBreakdownPreview(orderId, batchId) {
  return api.get(`/api/orders/${encodeURIComponent(orderId)}/batches/${batchId}/breakdown-preview`)
}
```

Adjust the import name (`api` vs `axios` instance) to match the existing pattern in the file.

- [ ] **Step 2: Add a receipt-code search box on the HC list page**

In `frontend/src/views/handcraft/HandcraftList.vue`, add an `n-input` + button near the existing list filters:

```vue
<n-input-group>
  <n-input v-model:value="receiptCodeInput" placeholder="回执编号 (5 位)"
           maxlength="5" @keyup.enter="jumpByReceiptCode" />
  <n-button type="primary" @click="jumpByReceiptCode" :loading="lookingUp">
    扫码跳转
  </n-button>
</n-input-group>
```

Wire it up in the `<script setup>`:

```javascript
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { getHandcraftByReceiptCode } from '@/api/handcraft'

const router = useRouter()
const message = useMessage()
const receiptCodeInput = ref('')
const lookingUp = ref(false)

async function jumpByReceiptCode() {
  const code = receiptCodeInput.value.trim().toUpperCase()
  if (code.length !== 5) {
    message.warning('请输入 5 位回执编号')
    return
  }
  lookingUp.value = true
  try {
    const { data } = await getHandcraftByReceiptCode(code)
    router.push(`/handcraft/${data.id}`)
  } catch (err) {
    if (err?.response?.status === 404) {
      message.error(`无此回执编号：${code}`)
    } else {
      message.error('查询失败')
    }
  } finally {
    lookingUp.value = false
  }
}
```

- [ ] **Step 3: Manual verification**

```bash
# Backend:
python main.py
# Frontend (new shell):
cd frontend && npm run dev
```

In the browser, go to the handcraft list page. Confirm:
1. Search input shows next to existing filters
2. Typing a valid `receipt_code` and pressing Enter navigates to that HC detail page
3. Typing an invalid code shows the "无此回执编号" error
4. Empty / wrong-length input shows a warning, no API call

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/handcraft.js frontend/src/api/orders.js frontend/src/views/handcraft/HandcraftList.vue
git commit -m "feat(handcraft): receipt-code lookup search on handcraft list"
```

---

### Task 4.2: HC detail — aggregated jewelry view with breakdown chips

**Files:**
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue`
- Create: `frontend/src/components/BreakdownChips.vue`

- [ ] **Step 1: Create the chips component**

Create `frontend/src/components/BreakdownChips.vue`:

```vue
<template>
  <div class="breakdown-chips">
    <span
      v-for="e in entries"
      :key="e.hc_jewelry_item_id"
      class="chip"
      :class="{ 'chip--manual': e.source === 'manual' }"
      :title="chipTitle(e)"
    >
      <span class="chip__name">{{ e.customer_name || '—' }}</span>
      <span class="chip__qty">{{ formatQty(e.qty) }}</span>
      <span class="chip__source">
        <template v-if="e.source === 'order'">↗ {{ e.source_order_id }}</template>
        <template v-else>手填</template>
      </span>
    </span>
    <span v-if="!entries.length" class="empty">— 未分拣</span>
  </div>
</template>

<script setup>
defineProps({
  entries: { type: Array, required: true },
})
function formatQty(n) {
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}
function chipTitle(e) {
  return e.source === 'order'
    ? `来自订单 ${e.source_order_id}，需到订单详情修改`
    : 'HC 详情手填，可在此处编辑'
}
</script>

<style scoped>
.breakdown-chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.chip {
  display: inline-flex; align-items: baseline; gap: 6px;
  padding: 2px 9px; background: #f5f5f8; border: 1px solid #e0e0e6;
  border-radius: 3px; font-size: 13px; line-height: 20px;
}
.chip--manual { background: #eef0fe; border-color: #e0e3fc; }
.chip__qty { font-family: "SF Mono", Menlo, monospace; color: rgba(0,0,0,.45); font-size: 12px; }
.chip__source {
  font-size: 11px; color: rgba(0,0,0,.3);
  margin-left: 2px; padding-left: 6px; border-left: 1px solid #e0e0e6;
}
.chip--manual .chip__source { color: #4338CA; border-left-color: #e0e3fc; }
.empty { color: rgba(0,0,0,.45); font-size: 13px; }
</style>
```

- [ ] **Step 2: Use the breakdown API in HandcraftDetail.vue**

In `frontend/src/views/handcraft/HandcraftDetail.vue`, add to `<script setup>`:

```javascript
import BreakdownChips from '@/components/BreakdownChips.vue'
import { getHandcraftJewelryBreakdown } from '@/api/handcraft'

const breakdownGroups = ref([])

async function loadBreakdown() {
  if (!order.value) return
  const { data } = await getHandcraftJewelryBreakdown(order.value.id)
  breakdownGroups.value = data
}

// call loadBreakdown() in the existing onMounted / after order is fetched
```

Replace (or add alongside) the existing "产出明细" `n-data-table` with a render that uses `breakdownGroups`:

```vue
<n-card title="产出明细 / 客户分拣" style="margin-bottom: 16px;">
  <div v-for="g in breakdownGroups" :key="g.jewelry_id" class="group-row">
    <div class="group-row__head">
      <span class="group-row__id">{{ g.jewelry_id }}</span>
      <span class="group-row__name">{{ g.jewelry_name }}</span>
      <span class="group-row__qty">
        <strong>{{ g.total_qty }}</strong> 套 ·
        已收 {{ g.received_qty }} ·
        <n-tag size="small">{{ g.status }}</n-tag>
      </span>
      <n-button size="small" @click="openBreakdownEditor(g)">编辑分拣</n-button>
    </div>
    <div class="group-row__breakdown">
      <BreakdownChips :entries="g.entries" />
    </div>
  </div>
  <n-empty v-if="!breakdownGroups.length" description="无产出项" />
</n-card>
```

Add minimal scoped CSS to make the rows readable:

```css
.group-row { padding: 10px 0; border-bottom: 1px solid #e8e8ec; }
.group-row:last-child { border-bottom: none; }
.group-row__head { display: flex; gap: 12px; align-items: baseline; }
.group-row__id { font-family: monospace; color: rgba(0,0,0,.45); font-size: 13px; }
.group-row__name { font-weight: 500; font-size: 15px; }
.group-row__qty { margin-left: auto; color: rgba(0,0,0,.65); font-size: 13px; }
.group-row__breakdown { margin-top: 6px; padding-left: 4px; }
```

`openBreakdownEditor(g)` is wired in Task 4.3.

- [ ] **Step 3: Manual verification**

Start backend + frontend. Open a HC detail page that has multiple jewelry items of the same jewelry_id (or seed test data). Confirm:
1. Rows are grouped by jewelry_id
2. Total qty / received qty / status display correctly
3. Chips show with source markers (`↗ OR-XXXX` for order, `手填` for manual)
4. Hover tooltip shows the explanation
5. "编辑分拣" button is present but doesn't yet open anything (will be wired in 4.3)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/BreakdownChips.vue frontend/src/views/handcraft/HandcraftDetail.vue
git commit -m "feat(handcraft): aggregated jewelry breakdown view on HC detail"
```

---

### Task 4.3: BreakdownEditModal — edit manual breakdown rows

**Files:**
- Create: `frontend/src/components/BreakdownEditModal.vue`
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue`
- Modify: `frontend/src/api/handcraft.js`

- [ ] **Step 1: Add API wrappers for jewelry-item add/update/delete with customer_name**

These endpoints already exist in `api/handcraft.py` — they just now accept `customer_name`. In `frontend/src/api/handcraft.js`:

```javascript
export function addHandcraftJewelry(hcId, payload) {
  return api.post(`/api/handcraft-orders/${encodeURIComponent(hcId)}/jewelries`, payload)
}
export function updateHandcraftJewelry(hcId, itemId, payload) {
  return api.patch(`/api/handcraft-orders/${encodeURIComponent(hcId)}/jewelries/${itemId}`, payload)
}
export function deleteHandcraftJewelry(hcId, itemId) {
  return api.delete(`/api/handcraft-orders/${encodeURIComponent(hcId)}/jewelries/${itemId}`)
}
```

> Verify the actual endpoint URLs match `api/handcraft.py` — adjust paths if different.

- [ ] **Step 2: Create the modal**

Create `frontend/src/components/BreakdownEditModal.vue`:

```vue
<template>
  <n-modal :show="show" preset="card" :title="title" :style="{ width: '640px' }"
           @update:show="$emit('update:show', $event)">
    <p class="hint">
      订单来源行只读，需要修改请回到对应订单。手填行可在此处编辑、删除。
    </p>
    <n-data-table :columns="columns" :data="rows" :bordered="false" size="small" />
    <n-button v-if="canAddManual" dashed block style="margin-top: 12px;"
              @click="addManualRow">
      + 添加手填客户
    </n-button>
    <div class="footer">
      <span class="sum" :class="sumClass">
        合计 <strong>{{ sumQty }}</strong> / {{ group.total_qty }}
      </span>
      <n-button @click="$emit('update:show', false)">关闭</n-button>
      <n-button type="primary" :loading="saving" @click="save">保存</n-button>
    </div>
  </n-modal>
</template>

<script setup>
import { ref, computed, watch, h } from 'vue'
import { NInput, NInputNumber, NButton, NTag, useMessage } from 'naive-ui'
import {
  addHandcraftJewelry, updateHandcraftJewelry, deleteHandcraftJewelry,
} from '@/api/handcraft'

const props = defineProps({
  show: Boolean,
  hcId: String,
  hcStatus: String,
  group: { type: Object, required: true },
})
const emit = defineEmits(['update:show', 'saved'])
const message = useMessage()

const rows = ref([])
const saving = ref(false)

watch(() => props.show, (v) => {
  if (v) {
    rows.value = props.group.entries.map(e => ({ ...e, _dirty: false, _new: false }))
  }
})

const canAddManual = computed(() => props.hcStatus === 'pending')

const sumQty = computed(() => rows.value.reduce((a, r) => a + Number(r.qty || 0), 0))
const sumClass = computed(() =>
  sumQty.value === props.group.total_qty ? 'sum--ok' : 'sum--err'
)
const title = computed(() => `编辑客户分拣 · ${props.group.jewelry_name}`)

const columns = [
  {
    title: '客户',
    key: 'customer_name',
    render: (row) => row.is_locked
      ? h('span', { style: 'color: rgba(0,0,0,.65)' }, row.customer_name)
      : h(NInput, {
          value: row.customer_name,
          'onUpdate:value': v => { row.customer_name = v; row._dirty = true }
        }),
  },
  {
    title: '数量',
    key: 'qty',
    width: 100,
    render: (row) => row.is_locked || (!row._new && props.hcStatus !== 'pending')
      ? h('span', { style: 'font-family: monospace' }, row.qty)
      : h(NInputNumber, {
          value: row.qty, min: 0.0001, showButton: false,
          'onUpdate:value': v => { row.qty = v; row._dirty = true }
        }),
  },
  {
    title: '来源',
    key: 'source',
    width: 180,
    render: (row) => row.source === 'order'
      ? h(NTag, { size: 'small' }, () => `🔒 ${row.source_order_id}`)
      : h(NTag, { size: 'small', type: 'info' }, () => '手填'),
  },
  {
    title: '',
    key: 'action',
    width: 60,
    render: (row) => row.is_locked
      ? null
      : h(NButton, {
          size: 'small', text: true,
          onClick: () => { rows.value = rows.value.filter(r => r !== row) }
        }, () => '×'),
  },
]

function addManualRow() {
  rows.value.push({
    hc_jewelry_item_id: null,
    qty: 0,
    customer_name: '',
    source: 'manual',
    source_order_id: null,
    is_locked: false,
    _new: true,
    _dirty: true,
  })
}

async function save() {
  saving.value = true
  try {
    // Server-side: original entries that no longer exist in `rows` → delete (if not locked).
    const survivingIds = new Set(rows.value.filter(r => !r._new).map(r => r.hc_jewelry_item_id))
    for (const orig of props.group.entries) {
      if (orig.is_locked) continue
      if (!survivingIds.has(orig.hc_jewelry_item_id)) {
        await deleteHandcraftJewelry(props.hcId, orig.hc_jewelry_item_id)
      }
    }
    // New / dirty manual rows
    for (const r of rows.value) {
      if (r.is_locked) continue
      if (r._new) {
        await addHandcraftJewelry(props.hcId, {
          jewelry_id: props.group.jewelry_id,
          qty: r.qty,
          customer_name: r.customer_name,
        })
      } else if (r._dirty) {
        const payload = { customer_name: r.customer_name }
        if (props.hcStatus === 'pending') payload.qty = r.qty
        await updateHandcraftJewelry(props.hcId, r.hc_jewelry_item_id, payload)
      }
    }
    message.success('已保存')
    emit('saved')
    emit('update:show', false)
  } catch (err) {
    message.error(err?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.hint { color: rgba(0,0,0,.45); font-size: 12px; margin-bottom: 12px; }
.footer { margin-top: 16px; display: flex; gap: 8px; align-items: center; }
.sum { margin-right: auto; color: rgba(0,0,0,.65); font-size: 13px; }
.sum strong { font-family: monospace; }
.sum--ok strong { color: #18a058; }
.sum--err strong { color: #d03050; }
</style>
```

- [ ] **Step 3: Wire it up on HandcraftDetail.vue**

In `frontend/src/views/handcraft/HandcraftDetail.vue` `<script setup>`:

```javascript
import BreakdownEditModal from '@/components/BreakdownEditModal.vue'

const editModalShow = ref(false)
const editModalGroup = ref(null)

function openBreakdownEditor(group) {
  editModalGroup.value = group
  editModalShow.value = true
}

function onBreakdownSaved() {
  loadBreakdown()
}
```

In `<template>`, add the modal:

```vue
<BreakdownEditModal
  v-if="editModalGroup"
  v-model:show="editModalShow"
  :hc-id="order.id"
  :hc-status="order.status"
  :group="editModalGroup"
  @saved="onBreakdownSaved"
/>
```

- [ ] **Step 4: Manual verification**

Confirm the matrix from §"手填行规则" works in the UI:
- pending: can add manual row, edit any manual row's customer_name / qty, delete manual rows; cannot touch order rows
- processing: cannot add; can edit customer_name on manual rows; cannot edit qty; cannot delete
- completed: all fields read-only or modal won't accept changes (server enforces — verify the error shows)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/BreakdownEditModal.vue frontend/src/views/handcraft/HandcraftDetail.vue frontend/src/api/handcraft.js
git commit -m "feat(handcraft): breakdown edit modal for manual customer rows"
```

---

### Task 4.4: BreakdownBanner on OrderDetail batch (Option B)

**Files:**
- Create: `frontend/src/components/BreakdownBanner.vue`
- Modify: `frontend/src/views/orders/OrderDetail.vue`

- [ ] **Step 1: Create the banner component**

Create `frontend/src/components/BreakdownBanner.vue`:

```vue
<template>
  <div v-if="preview" class="banner">
    <div class="banner__icon">📋</div>
    <div class="banner__body">
      <div class="banner__head">
        <span class="banner__title">客户分拣预览</span>
        <span class="banner__hc">
          已并入 <strong>{{ preview.handcraft_order_id }}</strong>
          <span class="mono">· 回执 {{ preview.receipt_code }}</span>
        </span>
      </div>
      <div class="banner__desc">
        此订单<template v-if="preview.customer_name">（<strong>{{ preview.customer_name }}</strong>）</template>在该 HC 的分拣中将占：
      </div>
      <ul class="banner__list">
        <li v-for="it in preview.jewelry_items" :key="it.jewelry_id">
          {{ it.jewelry_name }}<span class="qty"> · {{ it.qty }} 套</span>
        </li>
      </ul>
    </div>
    <div class="banner__action">
      <n-button @click="jumpToHc">查看 HC →</n-button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getBatchBreakdownPreview } from '@/api/orders'

const props = defineProps({ orderId: String, batchId: [String, Number] })
const router = useRouter()
const preview = ref(null)

async function load() {
  if (!props.orderId || !props.batchId) {
    preview.value = null
    return
  }
  const { data } = await getBatchBreakdownPreview(props.orderId, props.batchId)
  preview.value = data
}
watch(() => [props.orderId, props.batchId], load, { immediate: true })

function jumpToHc() {
  if (preview.value) {
    router.push(`/handcraft/${preview.value.handcraft_order_id}`)
  }
}
</script>

<style scoped>
.banner {
  display: flex; gap: 14px; align-items: flex-start;
  background: #ecf3fd; border: 1px solid #c6dcf9;
  padding: 12px 14px; border-radius: 4px; margin-bottom: 14px;
}
.banner__icon { font-size: 18px; flex-shrink: 0; }
.banner__body { flex: 1; }
.banner__head { display: flex; gap: 10px; align-items: baseline; margin-bottom: 6px; }
.banner__title { font-weight: 600; font-size: 13px; }
.banner__hc { font-size: 12px; color: rgba(0,0,0,.65); }
.banner__hc strong { color: #2080f0; font-family: monospace; }
.banner__hc .mono { font-family: monospace; color: rgba(0,0,0,.45); }
.banner__desc { font-size: 13px; color: rgba(0,0,0,.65); margin-bottom: 6px; }
.banner__desc strong { color: rgba(0,0,0,.88); font-weight: 500; }
.banner__list { list-style: none; margin-left: 4px; padding: 0; }
.banner__list li::before { content: "· "; color: rgba(0,0,0,.45); font-weight: 700; }
.banner__list .qty { font-family: monospace; color: rgba(0,0,0,.65); }
.banner__action { margin-left: auto; flex-shrink: 0; }
</style>
```

- [ ] **Step 2: Use in OrderDetail.vue**

In `frontend/src/views/orders/OrderDetail.vue`, import the component:

```javascript
import BreakdownBanner from '@/components/BreakdownBanner.vue'
```

Find the `batch-detail` div (around line 335 — `<div v-show="expandedBatchIds.has(batch.id)" class="batch-detail">`). At the very top of its content, before the existing jewelry-card row, insert:

```vue
<BreakdownBanner
  v-if="batch.supplier_name"
  :order-id="route.params.id"
  :batch-id="batch.id"
/>
```

> The `v-if="batch.supplier_name"` ensures unassigned batches don't fire the request. (Backend returns `null` for unassigned, but skipping the call is cheaper.)

- [ ] **Step 3: Manual verification**

Open an order with an assigned batch. Confirm:
1. Batch header still shows `✓ 已分配给：王师傅`
2. Expand the batch → the blue banner appears at the top of the detail area, showing HC id + receipt code + jewelry list
3. Clicking "查看 HC →" navigates to the HC detail page
4. Unassigned batches don't show the banner
5. Collapsed batch view is unchanged (clean)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/BreakdownBanner.vue frontend/src/views/orders/OrderDetail.vue
git commit -m "feat(orders): show breakdown preview banner in expanded batch detail"
```

---

## Final validation

- [ ] **Step 1: Full backend regression**

```bash
pytest
```

Expected: all green.

- [ ] **Step 2: Frontend smoke test (manual)**

End-to-end walkthrough in browser:

1. Create a customer order with one jewelry item × 100
2. Generate batch in 订单详情 → 关联手工商家 → 王师傅
3. Verify banner appears in expanded batch detail with `HC-XXXX` + `receipt_code`
4. Open the linked HC detail → confirm the jewelry shows as 1 row in aggregated view with one chip "客户名 · 100 · ↗ OR-XXXX"
5. Click 编辑分拣 → confirm the order row is locked with 🔒
6. Click 添加手填客户 → add "测试客户 · 50" → save
7. Reload HC detail → confirm two chips display, one locked (order), one editable (手填)
8. Export the configured PDF → verify last page is the "手工回执" page, customers shown as 客户 1 / 客户 2, real names absent, receipt_code present, HC ID absent
9. Note the receipt_code on the PDF, go back to HandcraftList, paste it into the search box → should jump to that HC detail

- [ ] **Step 3: Final commit if touch-ups needed**

```bash
git status
# if anything's still uncommitted from manual testing fixes:
git add -A
git commit -m "chore: post-implementation touch-ups"
```

---

## Notes for the implementer

- **CJK font in PDF:** ReportLab needs the CJK font registered before the receipt page can render Chinese. Look at the existing `services/handcraft_pdf.py` font-registration block — reuse the same font.
- **`OrderItemLink` shape:** Verify the actual column names (`order_id`, `handcraft_jewelry_item_id`, `handcraft_part_item_id`, `order_todo_item_id`) match what's in `models/order_todo.py`. The plan assumes the names I observed via `git grep "OrderItemLink"` — fix if they differ.
- **Schema file name:** `schemas/order.py` may already exist. `git ls-files schemas/` first. If yes, append to it; if no, create as shown in Task 2.3.
- **`db.flush()` not `db.commit()`** in every service function. The session lifecycle is owned by `get_db()`.
- **PR boundary:** If you need to ship incrementally instead of all-at-once, the natural cut points are: Phase 1 (receipt_code only), Phase 2 (breakdown + customer_name), Phase 3 (PDF), Phase 4 (frontend). Each phase produces a working build.
