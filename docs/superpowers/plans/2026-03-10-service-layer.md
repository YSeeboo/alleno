# Service Layer Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement all six service modules (inventory, part, jewelry, bom, order, plating, handcraft) with pytest tests, plus a verification script that exercises the full domain flow end-to-end.

**Architecture:** Thin service layer sitting between SQLAlchemy models and the future API/bot layer. Each service receives a `db: Session` and raises Python-native exceptions (`ValueError`/`RuntimeError`) on business rule violations. A shared `_next_id` helper generates formatted IDs. The inventory service is the only cross-cutting dependency — all other services call it for stock mutations.

**Tech Stack:** Python 3.9, SQLAlchemy 2.x ORM, SQLite (in-memory for tests), pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `tests/conftest.py` | Create | Shared pytest fixtures: in-memory DB session, pre-seeded Part/Jewelry |
| `services/_helpers.py` | Create | `_next_id(db, model, prefix, width=4)` |
| `services/inventory.py` | Create | `add_stock`, `deduct_stock`, `get_stock`, `get_stock_log` |
| `services/part.py` | Create | CRUD for Part |
| `services/jewelry.py` | Create | CRUD + `set_status` for Jewelry |
| `services/bom.py` | Create | `set_bom`, `get_bom`, `delete_bom_item`, `calculate_parts_needed` |
| `services/order.py` | Create | `create_order`, `get_order`, `get_order_items`, `get_parts_summary`, `update_order_status` |
| `services/plating.py` | Create | `create_plating_order`, `send_plating_order`, `receive_plating_items`, `get_plating_order`, `list_plating_orders` |
| `services/handcraft.py` | Create | `create_handcraft_order`, `send_handcraft_order`, `receive_handcraft_jewelries`, `get_handcraft_order`, `list_handcraft_orders` |
| `scripts/verify_services.py` | Create | End-to-end verification script (no pytest, uses real SQLite file) |

---

## Chunk 1: Foundation — conftest, helpers, inventory service

### Task 1: Test fixture (conftest.py)

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `tests/__init__.py`** (empty file)

- [ ] **Step 2: Create `tests/conftest.py`**

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # registers all ORM classes with Base
from database import Base


@pytest.fixture
def db():
    engine = create_engine(os.getenv("TEST_DATABASE_URL", "postgresql://allen:allen@localhost:5432/allen_shop_test"))
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
```

- [ ] **Step 3: Verify fixture works**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/ -v --co
```
Expected: collected 0 items (no errors).

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: add pytest conftest with in-memory SQLite fixture"
```

---

### Task 2: `_next_id` helper

**Files:**
- Create: `services/_helpers.py`
- Create: `tests/test_helpers.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_helpers.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import Part
from services._helpers import _next_id


def test_next_id_first_row(db):
    """When table is empty, returns prefix-0001."""
    result = _next_id(db, Part, "PJ")
    assert result == "PJ-0001"


def test_next_id_increments(db):
    """When existing IDs present, returns max+1."""
    db.add(Part(id="PJ-0003", name="test"))
    db.add(Part(id="PJ-0001", name="test2"))
    db.flush()
    result = _next_id(db, Part, "PJ")
    assert result == "PJ-0004"


def test_next_id_custom_width(db):
    result = _next_id(db, Part, "PJ", width=6)
    assert result == "PJ-000001"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/test_helpers.py -v
```
Expected: ImportError or AttributeError — `services._helpers` does not exist.

- [ ] **Step 3: Implement `services/_helpers.py`**

```python
from sqlalchemy.orm import Session


def _next_id(db: Session, model, prefix: str, width: int = 4) -> str:
    """Return the next formatted ID for a model with string PKs like 'PJ-0001'."""
    rows = db.query(model.id).all()
    max_n = 0
    for (row_id,) in rows:
        try:
            n = int(row_id.split("-")[-1])
            if n > max_n:
                max_n = n
        except (ValueError, IndexError):
            pass
    return f"{prefix}-{max_n + 1:0{width}d}"
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/test_helpers.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/_helpers.py tests/test_helpers.py
git commit -m "feat: add _next_id helper for formatted PK generation"
```

---

### Task 3: Inventory service

**Files:**
- Create: `services/inventory.py`
- Create: `tests/test_inventory.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_inventory.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.inventory import add_stock, deduct_stock, get_stock, get_stock_log


def test_get_stock_empty(db):
    assert get_stock(db, "part", "PJ-0001") == 0.0


def test_add_stock_returns_log(db):
    log = add_stock(db, "part", "PJ-0001", 100.0, "入库")
    assert log.change_qty == 100.0
    assert log.item_type == "part"
    assert log.item_id == "PJ-0001"


def test_get_stock_after_add(db):
    add_stock(db, "part", "PJ-0001", 100.0, "入库")
    add_stock(db, "part", "PJ-0001", 50.0, "补货")
    assert get_stock(db, "part", "PJ-0001") == 150.0


def test_deduct_stock_success(db):
    add_stock(db, "part", "PJ-0001", 100.0, "入库")
    log = deduct_stock(db, "part", "PJ-0001", 30.0, "出库")
    assert log.change_qty == -30.0
    assert get_stock(db, "part", "PJ-0001") == 70.0


def test_deduct_stock_insufficient(db):
    add_stock(db, "part", "PJ-0001", 10.0, "入库")
    with pytest.raises(ValueError, match="库存不足"):
        deduct_stock(db, "part", "PJ-0001", 20.0, "出库")


def test_get_stock_log_order(db):
    add_stock(db, "part", "PJ-0001", 100.0, "入库")
    add_stock(db, "part", "PJ-0001", 50.0, "补货")
    logs = get_stock_log(db, "part", "PJ-0001")
    assert len(logs) == 2
    # descending by created_at (or id as proxy for insertion order)
    assert logs[0].change_qty == 50.0
    assert logs[1].change_qty == 100.0


def test_get_stock_isolates_item_type(db):
    """part and jewelry stock are independent."""
    add_stock(db, "part", "PJ-0001", 100.0, "入库")
    assert get_stock(db, "jewelry", "PJ-0001") == 0.0
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/test_inventory.py -v
```

- [ ] **Step 3: Implement `services/inventory.py`**

```python
from sqlalchemy import func
from sqlalchemy.orm import Session

from models.inventory_log import InventoryLog


def get_stock(db: Session, item_type: str, item_id: str) -> float:
    result = db.query(func.sum(InventoryLog.change_qty)).filter(
        InventoryLog.item_type == item_type,
        InventoryLog.item_id == item_id,
    ).scalar()
    return float(result) if result is not None else 0.0


def add_stock(db: Session, item_type: str, item_id: str, qty: float, reason: str, note: str = None) -> InventoryLog:
    log = InventoryLog(item_type=item_type, item_id=item_id, change_qty=qty, reason=reason, note=note)
    db.add(log)
    db.flush()
    return log


def deduct_stock(db: Session, item_type: str, item_id: str, qty: float, reason: str, note: str = None) -> InventoryLog:
    current = get_stock(db, item_type, item_id)
    if current < qty:
        raise ValueError(f"库存不足：{item_type} {item_id} 当前库存 {current}，需要 {qty}")
    log = InventoryLog(item_type=item_type, item_id=item_id, change_qty=-qty, reason=reason, note=note)
    db.add(log)
    db.flush()
    return log


def get_stock_log(db: Session, item_type: str, item_id: str) -> list:
    return (
        db.query(InventoryLog)
        .filter(InventoryLog.item_type == item_type, InventoryLog.item_id == item_id)
        .order_by(InventoryLog.created_at.desc())
        .all()
    )
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/test_inventory.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/inventory.py tests/test_inventory.py
git commit -m "feat: implement inventory service (add/deduct/get/log)"
```

---

## Chunk 2: Part, Jewelry, BOM services

### Task 4: Part service

**Files:**
- Create: `services/part.py`
- Create: `tests/test_part.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_part.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.part import create_part, get_part, list_parts, update_part, delete_part


def test_create_part_generates_id(db):
    part = create_part(db, {"name": "铜扣", "category": "扣件"})
    assert part.id == "PJ-0001"
    assert part.name == "铜扣"


def test_create_part_sequential_ids(db):
    p1 = create_part(db, {"name": "A"})
    p2 = create_part(db, {"name": "B"})
    assert p1.id == "PJ-0001"
    assert p2.id == "PJ-0002"


def test_get_part_found(db):
    create_part(db, {"name": "铜扣"})
    part = get_part(db, "PJ-0001")
    assert part is not None
    assert part.name == "铜扣"


def test_get_part_not_found(db):
    assert get_part(db, "PJ-9999") is None


def test_list_parts_all(db):
    create_part(db, {"name": "A", "category": "扣件"})
    create_part(db, {"name": "B", "category": "链条"})
    assert len(list_parts(db)) == 2


def test_list_parts_filter_category(db):
    create_part(db, {"name": "A", "category": "扣件"})
    create_part(db, {"name": "B", "category": "链条"})
    results = list_parts(db, category="扣件")
    assert len(results) == 1
    assert results[0].name == "A"


def test_update_part_partial(db):
    create_part(db, {"name": "铜扣", "category": "扣件"})
    part = update_part(db, "PJ-0001", {"name": "铜扣V2"})
    assert part.name == "铜扣V2"
    assert part.category == "扣件"  # untouched


def test_update_part_not_found(db):
    with pytest.raises(ValueError):
        update_part(db, "PJ-9999", {"name": "X"})


def test_delete_part(db):
    create_part(db, {"name": "铜扣"})
    delete_part(db, "PJ-0001")
    assert get_part(db, "PJ-0001") is None


def test_delete_part_not_found(db):
    with pytest.raises(ValueError):
        delete_part(db, "PJ-9999")
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/test_part.py -v
```

- [ ] **Step 3: Implement `services/part.py`**

```python
from sqlalchemy.orm import Session

from models.part import Part
from services._helpers import _next_id


def create_part(db: Session, data: dict) -> Part:
    part = Part(id=_next_id(db, Part, "PJ"), **data)
    db.add(part)
    db.flush()
    return part


def get_part(db: Session, part_id: str) -> Part | None:
    return db.query(Part).filter(Part.id == part_id).first()


def list_parts(db: Session, category: str = None) -> list:
    q = db.query(Part)
    if category is not None:
        q = q.filter(Part.category == category)
    return q.all()


def update_part(db: Session, part_id: str, data: dict) -> Part:
    part = get_part(db, part_id)
    if part is None:
        raise ValueError(f"Part not found: {part_id}")
    for key, value in data.items():
        setattr(part, key, value)
    db.flush()
    return part


def delete_part(db: Session, part_id: str) -> None:
    part = get_part(db, part_id)
    if part is None:
        raise ValueError(f"Part not found: {part_id}")
    db.delete(part)
    db.flush()
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/test_part.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/part.py tests/test_part.py
git commit -m "feat: implement part service (CRUD)"
```

---

### Task 5: Jewelry service

**Files:**
- Create: `services/jewelry.py`
- Create: `tests/test_jewelry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_jewelry.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.jewelry import create_jewelry, get_jewelry, list_jewelries, update_jewelry, set_status, delete_jewelry


def test_create_jewelry_id(db):
    j = create_jewelry(db, {"name": "玫瑰戒指"})
    assert j.id == "SP-0001"
    assert j.status == "active"


def test_get_jewelry(db):
    create_jewelry(db, {"name": "玫瑰戒指"})
    j = get_jewelry(db, "SP-0001")
    assert j.name == "玫瑰戒指"


def test_get_jewelry_not_found(db):
    assert get_jewelry(db, "SP-9999") is None


def test_list_jewelries_filter_status(db):
    create_jewelry(db, {"name": "A"})
    j2 = create_jewelry(db, {"name": "B"})
    set_status(db, j2.id, "inactive")
    active = list_jewelries(db, status="active")
    assert len(active) == 1


def test_list_jewelries_filter_category(db):
    create_jewelry(db, {"name": "A", "category": "戒指"})
    create_jewelry(db, {"name": "B", "category": "项链"})
    assert len(list_jewelries(db, category="戒指")) == 1


def test_set_status_valid(db):
    create_jewelry(db, {"name": "A"})
    j = set_status(db, "SP-0001", "inactive")
    assert j.status == "inactive"


def test_set_status_invalid(db):
    create_jewelry(db, {"name": "A"})
    with pytest.raises(ValueError, match="Invalid status"):
        set_status(db, "SP-0001", "deleted")


def test_update_jewelry_partial(db):
    create_jewelry(db, {"name": "A", "category": "戒指"})
    j = update_jewelry(db, "SP-0001", {"name": "B"})
    assert j.name == "B"
    assert j.category == "戒指"


def test_delete_jewelry(db):
    create_jewelry(db, {"name": "A"})
    delete_jewelry(db, "SP-0001")
    assert get_jewelry(db, "SP-0001") is None


def test_delete_jewelry_not_found(db):
    with pytest.raises(ValueError):
        delete_jewelry(db, "SP-9999")
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/test_jewelry.py -v
```

- [ ] **Step 3: Implement `services/jewelry.py`**

```python
from sqlalchemy.orm import Session

from models.jewelry import Jewelry
from services._helpers import _next_id

_VALID_STATUSES = {"active", "inactive"}


def create_jewelry(db: Session, data: dict) -> Jewelry:
    jewelry = Jewelry(id=_next_id(db, Jewelry, "SP"), **data)
    db.add(jewelry)
    db.flush()
    return jewelry


def get_jewelry(db: Session, jewelry_id: str) -> Jewelry | None:
    return db.query(Jewelry).filter(Jewelry.id == jewelry_id).first()


def list_jewelries(db: Session, category: str = None, status: str = None) -> list:
    q = db.query(Jewelry)
    if category is not None:
        q = q.filter(Jewelry.category == category)
    if status is not None:
        q = q.filter(Jewelry.status == status)
    return q.all()


def update_jewelry(db: Session, jewelry_id: str, data: dict) -> Jewelry:
    jewelry = get_jewelry(db, jewelry_id)
    if jewelry is None:
        raise ValueError(f"Jewelry not found: {jewelry_id}")
    for key, value in data.items():
        setattr(jewelry, key, value)
    db.flush()
    return jewelry


def set_status(db: Session, jewelry_id: str, status: str) -> Jewelry:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {_VALID_STATUSES}")
    return update_jewelry(db, jewelry_id, {"status": status})


def delete_jewelry(db: Session, jewelry_id: str) -> None:
    jewelry = get_jewelry(db, jewelry_id)
    if jewelry is None:
        raise ValueError(f"Jewelry not found: {jewelry_id}")
    db.delete(jewelry)
    db.flush()
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/test_jewelry.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/jewelry.py tests/test_jewelry.py
git commit -m "feat: implement jewelry service (CRUD + set_status)"
```

---

### Task 6: BOM service

**Files:**
- Create: `services/bom.py`
- Create: `tests/test_bom.py`

Note: The `bom` table has no unique constraint on `(jewelry_id, part_id)`. The `set_bom` function must handle upsert logic manually by querying for an existing row.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_bom.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.part import create_part
from services.jewelry import create_jewelry
from services.bom import set_bom, get_bom, delete_bom_item, calculate_parts_needed


@pytest.fixture
def seeded(db):
    p1 = create_part(db, {"name": "铜扣"})
    p2 = create_part(db, {"name": "链条"})
    j = create_jewelry(db, {"name": "玫瑰戒指"})
    return db, p1, p2, j


def test_set_bom_creates_new(seeded):
    db, p1, p2, j = seeded
    bom = set_bom(db, j.id, p1.id, 2.0)
    assert bom.id == "BM-0001"
    assert float(bom.qty_per_unit) == 2.0


def test_set_bom_updates_existing(seeded):
    db, p1, p2, j = seeded
    bom1 = set_bom(db, j.id, p1.id, 2.0)
    bom2 = set_bom(db, j.id, p1.id, 5.0)
    # Same record, just updated
    assert bom1.id == bom2.id
    assert float(bom2.qty_per_unit) == 5.0


def test_set_bom_multiple_parts(seeded):
    db, p1, p2, j = seeded
    set_bom(db, j.id, p1.id, 2.0)
    set_bom(db, j.id, p2.id, 1.0)
    rows = get_bom(db, j.id)
    assert len(rows) == 2


def test_get_bom_empty(db):
    j = create_jewelry(db, {"name": "X"})
    assert get_bom(db, j.id) == []


def test_delete_bom_item(seeded):
    db, p1, p2, j = seeded
    bom = set_bom(db, j.id, p1.id, 2.0)
    delete_bom_item(db, bom.id)
    assert get_bom(db, j.id) == []


def test_delete_bom_item_not_found(db):
    with pytest.raises(ValueError):
        delete_bom_item(db, "BM-9999")


def test_calculate_parts_needed(seeded):
    db, p1, p2, j = seeded
    set_bom(db, j.id, p1.id, 2.0)
    set_bom(db, j.id, p2.id, 3.0)
    needed = calculate_parts_needed(db, j.id, qty=5)
    assert needed[p1.id] == 10.0  # 2 * 5
    assert needed[p2.id] == 15.0  # 3 * 5
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/test_bom.py -v
```

- [ ] **Step 3: Implement `services/bom.py`**

```python
from sqlalchemy.orm import Session

from models.bom import Bom
from services._helpers import _next_id


def set_bom(db: Session, jewelry_id: str, part_id: str, qty_per_unit: float) -> Bom:
    existing = (
        db.query(Bom)
        .filter(Bom.jewelry_id == jewelry_id, Bom.part_id == part_id)
        .first()
    )
    if existing:
        existing.qty_per_unit = qty_per_unit
        db.flush()
        return existing
    bom = Bom(
        id=_next_id(db, Bom, "BM"),
        jewelry_id=jewelry_id,
        part_id=part_id,
        qty_per_unit=qty_per_unit,
    )
    db.add(bom)
    db.flush()
    return bom


def get_bom(db: Session, jewelry_id: str) -> list:
    return db.query(Bom).filter(Bom.jewelry_id == jewelry_id).all()


def delete_bom_item(db: Session, bom_id: str) -> None:
    bom = db.query(Bom).filter(Bom.id == bom_id).first()
    if bom is None:
        raise ValueError(f"BOM item not found: {bom_id}")
    db.delete(bom)
    db.flush()


def calculate_parts_needed(db: Session, jewelry_id: str, qty: int) -> dict:
    rows = get_bom(db, jewelry_id)
    return {row.part_id: float(row.qty_per_unit) * qty for row in rows}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/test_bom.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/bom.py tests/test_bom.py
git commit -m "feat: implement bom service (set_bom upsert, calculate_parts_needed)"
```

---

## Chunk 3: Order, Plating, Handcraft services

### Task 7: Order service

**Files:**
- Create: `services/order.py`
- Create: `tests/test_order.py`

Note: The `order` table name is a SQL reserved word. SQLAlchemy handles quoting automatically when using the ORM — no raw SQL needed here.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_order.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.part import create_part
from services.jewelry import create_jewelry
from services.bom import set_bom
from services.order import create_order, get_order, get_order_items, get_parts_summary, update_order_status


@pytest.fixture
def setup(db):
    p1 = create_part(db, {"name": "铜扣"})
    p2 = create_part(db, {"name": "链条"})
    j1 = create_jewelry(db, {"name": "玫瑰戒指"})
    j2 = create_jewelry(db, {"name": "银耳环"})
    set_bom(db, j1.id, p1.id, 2.0)
    set_bom(db, j1.id, p2.id, 1.0)
    set_bom(db, j2.id, p1.id, 1.0)
    return db, p1, p2, j1, j2


def test_create_order_id(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "张三", [
        {"jewelry_id": j1.id, "quantity": 2, "unit_price": 100.0}
    ])
    assert order.id == "OR-0001"
    assert order.customer_name == "张三"
    assert float(order.total_amount) == 200.0


def test_create_order_total_amount(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "李四", [
        {"jewelry_id": j1.id, "quantity": 3, "unit_price": 100.0},
        {"jewelry_id": j2.id, "quantity": 2, "unit_price": 50.0},
    ])
    assert float(order.total_amount) == 400.0


def test_get_order_items(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "张三", [
        {"jewelry_id": j1.id, "quantity": 2, "unit_price": 100.0},
        {"jewelry_id": j2.id, "quantity": 1, "unit_price": 50.0},
    ])
    items = get_order_items(db, order.id)
    assert len(items) == 2


def test_get_parts_summary(setup):
    db, p1, p2, j1, j2 = setup
    # j1 needs 2*p1 + 1*p2 per unit; j2 needs 1*p1 per unit
    # order: 2 j1, 3 j2
    order = create_order(db, "张三", [
        {"jewelry_id": j1.id, "quantity": 2, "unit_price": 100.0},
        {"jewelry_id": j2.id, "quantity": 3, "unit_price": 50.0},
    ])
    summary = get_parts_summary(db, order.id)
    # p1: 2*2 + 3*1 = 7
    # p2: 2*1 = 2
    assert summary[p1.id] == 7.0
    assert summary[p2.id] == 2.0


def test_get_parts_summary_no_bom(setup):
    """Jewelry without BOM should be silently skipped."""
    db, p1, p2, j1, j2 = setup
    j3 = create_jewelry(db, {"name": "无BOM饰品"})
    order = create_order(db, "王五", [
        {"jewelry_id": j3.id, "quantity": 1, "unit_price": 10.0},
    ])
    summary = get_parts_summary(db, order.id)
    assert summary == {}


def test_update_order_status_valid(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "张三", [{"jewelry_id": j1.id, "quantity": 1, "unit_price": 10.0}])
    updated = update_order_status(db, order.id, "生产中")
    assert updated.status == "生产中"


def test_update_order_status_invalid(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "张三", [{"jewelry_id": j1.id, "quantity": 1, "unit_price": 10.0}])
    with pytest.raises(ValueError, match="Invalid status"):
        update_order_status(db, order.id, "取消")
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/test_order.py -v
```

- [ ] **Step 3: Implement `services/order.py`**

```python
from sqlalchemy.orm import Session

from models.order import Order, OrderItem
from services._helpers import _next_id
from services.bom import get_bom

_VALID_STATUSES = {"待生产", "生产中", "已完成"}


def create_order(db: Session, customer_name: str, items: list) -> Order:
    order_id = _next_id(db, Order, "OR")
    total = sum(item["quantity"] * item["unit_price"] for item in items)
    order = Order(id=order_id, customer_name=customer_name, total_amount=total)
    db.add(order)
    db.flush()
    for item in items:
        db.add(OrderItem(
            order_id=order_id,
            jewelry_id=item["jewelry_id"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            remarks=item.get("remarks"),
        ))
    db.flush()
    return order


def get_order(db: Session, order_id: str) -> Order | None:
    return db.query(Order).filter(Order.id == order_id).first()


def get_order_items(db: Session, order_id: str) -> list:
    return db.query(OrderItem).filter(OrderItem.order_id == order_id).all()


def get_parts_summary(db: Session, order_id: str) -> dict:
    items = get_order_items(db, order_id)
    summary: dict[str, float] = {}
    for item in items:
        bom_rows = get_bom(db, item.jewelry_id)
        for row in bom_rows:
            part_id = row.part_id
            needed = float(row.qty_per_unit) * item.quantity
            summary[part_id] = summary.get(part_id, 0.0) + needed
    return summary


def update_order_status(db: Session, order_id: str, status: str) -> Order:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {_VALID_STATUSES}")
    order = get_order(db, order_id)
    if order is None:
        raise ValueError(f"Order not found: {order_id}")
    order.status = status
    db.flush()
    return order
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/test_order.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/order.py tests/test_order.py
git commit -m "feat: implement order service (create, items, parts summary, status)"
```

---

### Task 8: Plating service

**Files:**
- Create: `services/plating.py`
- Create: `tests/test_plating.py`

Key behaviors:
- `send_plating_order`: deducts stock for ALL items atomically — if ANY item fails, none are deducted (use a local rollback list).
- `receive_plating_items`: marks order `completed` when ALL items reach `received_qty >= qty`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_plating.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.part import create_part
from services.inventory import add_stock, get_stock
from services.plating import (
    create_plating_order, send_plating_order, receive_plating_items,
    get_plating_order, list_plating_orders,
)


@pytest.fixture
def setup(db):
    p1 = create_part(db, {"name": "铜扣"})
    p2 = create_part(db, {"name": "链条"})
    add_stock(db, "part", p1.id, 200.0, "入库")
    add_stock(db, "part", p2.id, 100.0, "入库")
    return db, p1, p2


def test_create_plating_order(setup):
    db, p1, p2 = setup
    order = create_plating_order(db, "金牌电镀厂", [
        {"part_id": p1.id, "qty": 100, "plating_method": "金色"},
        {"part_id": p2.id, "qty": 50, "plating_method": "银色"},
    ])
    assert order.id == "EP-0001"
    assert order.status == "pending"


def test_send_plating_order_deducts_stock(setup):
    db, p1, p2 = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 100, "plating_method": "金色"},
    ])
    send_plating_order(db, order.id)
    assert get_stock(db, "part", p1.id) == 100.0  # 200 - 100
    assert get_plating_order(db, order.id).status == "processing"


def test_send_plating_order_items_status(setup):
    db, p1, p2 = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 50, "plating_method": "金色"},
    ])
    updated = send_plating_order(db, order.id)
    from models.plating_order import PlatingOrderItem
    items = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order.id
    ).all()
    assert all(i.status == "电镀中" for i in items)


def test_send_plating_order_insufficient_stock(setup):
    db, p1, p2 = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 300, "plating_method": "金色"},  # only 200
    ])
    with pytest.raises(ValueError, match="库存不足"):
        send_plating_order(db, order.id)
    # Stock must not have changed
    assert get_stock(db, "part", p1.id) == 200.0


def test_send_plating_order_partial_rollback(setup):
    """If second item fails, first item's deduction must be rolled back."""
    db, p1, p2 = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 100, "plating_method": "金色"},  # OK
        {"part_id": p2.id, "qty": 500, "plating_method": "银色"},  # FAIL
    ])
    with pytest.raises(ValueError, match="库存不足"):
        send_plating_order(db, order.id)
    assert get_stock(db, "part", p1.id) == 200.0  # rolled back
    assert get_stock(db, "part", p2.id) == 100.0  # untouched


def test_receive_plating_items_partial(setup):
    db, p1, p2 = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 100, "plating_method": "金色"},
    ])
    send_plating_order(db, order.id)
    from models.plating_order import PlatingOrderItem
    item = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order.id
    ).first()
    # Receive 50 of 100
    receive_plating_items(db, order.id, [{"plating_order_item_id": item.id, "qty": 50}])
    db.refresh(item)
    assert float(item.received_qty) == 50.0
    assert item.status == "电镀中"  # not yet complete
    assert get_stock(db, "part", p1.id) == 150.0  # 100 deducted, 50 returned


def test_receive_plating_items_completes_order(setup):
    db, p1, p2 = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 100, "plating_method": "金色"},
    ])
    send_plating_order(db, order.id)
    from models.plating_order import PlatingOrderItem
    item = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order.id
    ).first()
    # Receive in two batches
    receive_plating_items(db, order.id, [{"plating_order_item_id": item.id, "qty": 60}])
    receive_plating_items(db, order.id, [{"plating_order_item_id": item.id, "qty": 40}])
    db.refresh(item)
    db.refresh(order)
    assert item.status == "已收回"
    assert order.status == "completed"
    assert order.completed_at is not None


def test_list_plating_orders_filter(setup):
    db, p1, p2 = setup
    create_plating_order(db, "厂A", [{"part_id": p1.id, "qty": 10, "plating_method": "金色"}])
    create_plating_order(db, "厂B", [{"part_id": p2.id, "qty": 10, "plating_method": "银色"}])
    assert len(list_plating_orders(db)) == 2
    assert len(list_plating_orders(db, status="pending")) == 2
    assert len(list_plating_orders(db, status="processing")) == 0
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/test_plating.py -v
```

- [ ] **Step 3: Implement `services/plating.py`**

```python
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.plating_order import PlatingOrder, PlatingOrderItem
from services._helpers import _next_id
from services.inventory import add_stock, deduct_stock


def create_plating_order(db: Session, supplier_name: str, items: list, note: str = None) -> PlatingOrder:
    order_id = _next_id(db, PlatingOrder, "EP")
    order = PlatingOrder(id=order_id, supplier_name=supplier_name, status="pending", note=note)
    db.add(order)
    db.flush()
    for item in items:
        db.add(PlatingOrderItem(
            plating_order_id=order_id,
            part_id=item["part_id"],
            qty=item["qty"],
            received_qty=0,
            status="未送出",
            plating_method=item.get("plating_method"),
            note=item.get("note"),
        ))
    db.flush()
    return order


def send_plating_order(db: Session, plating_order_id: str) -> PlatingOrder:
    order = get_plating_order(db, plating_order_id)
    if order is None:
        raise ValueError(f"PlatingOrder not found: {plating_order_id}")
    items = (
        db.query(PlatingOrderItem)
        .filter(PlatingOrderItem.plating_order_id == plating_order_id)
        .all()
    )
    deducted = []
    try:
        for item in items:
            log = deduct_stock(db, "part", item.part_id, float(item.qty), "电镀发出")
            deducted.append((item.part_id, float(item.qty)))
            item.status = "电镀中"
    except ValueError:
        # Roll back already-deducted stock by adding it back
        for part_id, qty in deducted:
            add_stock(db, "part", part_id, qty, "电镀发出回滚")
        raise
    order.status = "processing"
    db.flush()
    return order


def receive_plating_items(db: Session, plating_order_id: str, receipts: list) -> list:
    updated = []
    for receipt in receipts:
        item = db.query(PlatingOrderItem).filter(
            PlatingOrderItem.id == receipt["plating_order_item_id"]
        ).first()
        if item is None:
            raise ValueError(f"PlatingOrderItem not found: {receipt['plating_order_item_id']}")
        qty = receipt["qty"]
        item.received_qty = float(item.received_qty or 0) + qty
        add_stock(db, "part", item.part_id, qty, "电镀收回")
        if float(item.received_qty) >= float(item.qty):
            item.status = "已收回"
        updated.append(item)
    db.flush()
    # Check if all items are received
    all_items = (
        db.query(PlatingOrderItem)
        .filter(PlatingOrderItem.plating_order_id == plating_order_id)
        .all()
    )
    if all(i.status == "已收回" for i in all_items):
        order = get_plating_order(db, plating_order_id)
        order.status = "completed"
        order.completed_at = datetime.now(timezone.utc)
        db.flush()
    return updated


def get_plating_order(db: Session, plating_order_id: str) -> PlatingOrder | None:
    return db.query(PlatingOrder).filter(PlatingOrder.id == plating_order_id).first()


def list_plating_orders(db: Session, status: str = None) -> list:
    q = db.query(PlatingOrder)
    if status is not None:
        q = q.filter(PlatingOrder.status == status)
    return q.all()
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/test_plating.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/plating.py tests/test_plating.py
git commit -m "feat: implement plating service (create, send, receive with atomic rollback)"
```

---

### Task 9: Handcraft service

**Files:**
- Create: `services/handcraft.py`
- Create: `tests/test_handcraft.py`

Note: `HandcraftPartItem` has **no status column** — parts are tracked only at the order level. Jewelry items have a status column.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_handcraft.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock, get_stock
from services.handcraft import (
    create_handcraft_order, send_handcraft_order, receive_handcraft_jewelries,
    get_handcraft_order, list_handcraft_orders,
)


@pytest.fixture
def setup(db):
    p1 = create_part(db, {"name": "铜扣"})
    p2 = create_part(db, {"name": "链条"})
    j1 = create_jewelry(db, {"name": "玫瑰戒指"})
    add_stock(db, "part", p1.id, 200.0, "入库")
    add_stock(db, "part", p2.id, 100.0, "入库")
    return db, p1, p2, j1


def test_create_handcraft_order(setup):
    db, p1, p2, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50, "bom_qty": 48.0}],
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
    )
    assert order.id == "HC-0001"
    assert order.status == "pending"


def test_send_handcraft_order_deducts_parts(setup):
    db, p1, p2, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50, "bom_qty": 48.0}],
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
    )
    send_handcraft_order(db, order.id)
    assert get_stock(db, "part", p1.id) == 150.0  # 200 - 50
    assert get_handcraft_order(db, order.id).status == "processing"


def test_send_handcraft_order_jewelry_status(setup):
    db, p1, p2, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50, "bom_qty": 48.0}],
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
    )
    send_handcraft_order(db, order.id)
    from models.handcraft_order import HandcraftJewelryItem
    items = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.handcraft_order_id == order.id
    ).all()
    assert all(i.status == "制作中" for i in items)


def test_send_handcraft_order_insufficient_stock(setup):
    db, p1, p2, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 300, "bom_qty": 300.0}],  # only 200
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
    )
    with pytest.raises(ValueError, match="库存不足"):
        send_handcraft_order(db, order.id)
    assert get_stock(db, "part", p1.id) == 200.0


def test_receive_handcraft_jewelries_partial(setup):
    db, p1, p2, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50}],
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
    )
    send_handcraft_order(db, order.id)
    from models.handcraft_order import HandcraftJewelryItem
    ji = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.handcraft_order_id == order.id
    ).first()
    receive_handcraft_jewelries(db, order.id, [{"handcraft_jewelry_item_id": ji.id, "qty": 6}])
    db.refresh(ji)
    assert ji.received_qty == 6
    assert ji.status == "制作中"  # not yet complete
    assert get_stock(db, "jewelry", j1.id) == 6.0


def test_receive_handcraft_jewelries_completes_order(setup):
    db, p1, p2, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50}],
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
    )
    send_handcraft_order(db, order.id)
    from models.handcraft_order import HandcraftJewelryItem
    ji = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.handcraft_order_id == order.id
    ).first()
    receive_handcraft_jewelries(db, order.id, [{"handcraft_jewelry_item_id": ji.id, "qty": 6}])
    receive_handcraft_jewelries(db, order.id, [{"handcraft_jewelry_item_id": ji.id, "qty": 4}])
    db.refresh(ji)
    db.refresh(order)
    assert ji.status == "已收回"
    assert order.status == "completed"
    assert order.completed_at is not None
    assert get_stock(db, "jewelry", j1.id) == 10.0


def test_list_handcraft_orders_filter(setup):
    db, p1, p2, j1 = setup
    create_handcraft_order(db, "坊A", parts=[{"part_id": p1.id, "qty": 10}], jewelries=[{"jewelry_id": j1.id, "qty": 5}])
    create_handcraft_order(db, "坊B", parts=[{"part_id": p2.id, "qty": 10}], jewelries=[{"jewelry_id": j1.id, "qty": 3}])
    assert len(list_handcraft_orders(db)) == 2
    assert len(list_handcraft_orders(db, status="processing")) == 0
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/test_handcraft.py -v
```

- [ ] **Step 3: Implement `services/handcraft.py`**

```python
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
from services._helpers import _next_id
from services.inventory import add_stock, deduct_stock


def create_handcraft_order(
    db: Session,
    supplier_name: str,
    parts: list,
    jewelries: list,
    note: str = None,
) -> HandcraftOrder:
    order_id = _next_id(db, HandcraftOrder, "HC")
    order = HandcraftOrder(id=order_id, supplier_name=supplier_name, status="pending", note=note)
    db.add(order)
    db.flush()
    for p in parts:
        db.add(HandcraftPartItem(
            handcraft_order_id=order_id,
            part_id=p["part_id"],
            qty=p["qty"],
            bom_qty=p.get("bom_qty"),
            note=p.get("note"),
        ))
    for j in jewelries:
        db.add(HandcraftJewelryItem(
            handcraft_order_id=order_id,
            jewelry_id=j["jewelry_id"],
            qty=j["qty"],
            received_qty=0,
            status="未送出",
            note=j.get("note"),
        ))
    db.flush()
    return order


def send_handcraft_order(db: Session, handcraft_order_id: str) -> HandcraftOrder:
    order = get_handcraft_order(db, handcraft_order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {handcraft_order_id}")
    part_items = (
        db.query(HandcraftPartItem)
        .filter(HandcraftPartItem.handcraft_order_id == handcraft_order_id)
        .all()
    )
    jewelry_items = (
        db.query(HandcraftJewelryItem)
        .filter(HandcraftJewelryItem.handcraft_order_id == handcraft_order_id)
        .all()
    )
    deducted = []
    try:
        for item in part_items:
            deduct_stock(db, "part", item.part_id, float(item.qty), "手工发出")
            deducted.append((item.part_id, float(item.qty)))
    except ValueError:
        for part_id, qty in deducted:
            add_stock(db, "part", part_id, qty, "手工发出回滚")
        raise
    for ji in jewelry_items:
        ji.status = "制作中"
    order.status = "processing"
    db.flush()
    return order


def receive_handcraft_jewelries(db: Session, handcraft_order_id: str, receipts: list) -> list:
    updated = []
    for receipt in receipts:
        ji = db.query(HandcraftJewelryItem).filter(
            HandcraftJewelryItem.id == receipt["handcraft_jewelry_item_id"]
        ).first()
        if ji is None:
            raise ValueError(f"HandcraftJewelryItem not found: {receipt['handcraft_jewelry_item_id']}")
        qty = receipt["qty"]
        ji.received_qty = (ji.received_qty or 0) + qty
        add_stock(db, "jewelry", ji.jewelry_id, qty, "手工完成")
        if ji.received_qty >= ji.qty:
            ji.status = "已收回"
        updated.append(ji)
    db.flush()
    all_jewelry_items = (
        db.query(HandcraftJewelryItem)
        .filter(HandcraftJewelryItem.handcraft_order_id == handcraft_order_id)
        .all()
    )
    if all(ji.status == "已收回" for ji in all_jewelry_items):
        order = get_handcraft_order(db, handcraft_order_id)
        order.status = "completed"
        order.completed_at = datetime.now(timezone.utc)
        db.flush()
    return updated


def get_handcraft_order(db: Session, handcraft_order_id: str) -> HandcraftOrder | None:
    return db.query(HandcraftOrder).filter(HandcraftOrder.id == handcraft_order_id).first()


def list_handcraft_orders(db: Session, status: str = None) -> list:
    q = db.query(HandcraftOrder)
    if status is not None:
        q = q.filter(HandcraftOrder.status == status)
    return q.all()
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/test_handcraft.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/handcraft.py tests/test_handcraft.py
git commit -m "feat: implement handcraft service (create, send, receive with atomic rollback)"
```

---

## Chunk 4: Verification script + final check

### Task 10: End-to-end verification script

**Files:**
- Create: `scripts/verify_services.py`

This script uses a real SQLite file (not in-memory) so you can inspect the DB after running. It exercises all four domain flows from the completion criteria.

- [ ] **Step 1: Create `scripts/verify_services.py`**

```python
"""
End-to-end verification script for Allen Shop service layer.
Run from project root:  python scripts/verify_services.py
Uses `TEST_DATABASE_URL` (defaults to `postgresql://allen:allen@localhost:5432/allen_shop_test`).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from database import Base

engine = create_engine(os.getenv("TEST_DATABASE_URL", "postgresql://allen:allen@localhost:5432/allen_shop_test"))
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

from services.part import create_part
from services.jewelry import create_jewelry
from services.bom import set_bom
from services.inventory import add_stock, get_stock
from services.order import create_order, get_parts_summary
from services.plating import create_plating_order, send_plating_order, receive_plating_items, get_plating_order
from services.handcraft import create_handcraft_order, send_handcraft_order, receive_handcraft_jewelries, get_handcraft_order

print("=" * 60)
print("Flow 1: 创建配件 → 入库 → 查库存")
p1 = create_part(db, {"name": "铜扣", "category": "扣件"})
p2 = create_part(db, {"name": "银链", "category": "链条"})
add_stock(db, "part", p1.id, 500.0, "初始入库")
add_stock(db, "part", p2.id, 300.0, "初始入库")
stock_p1 = get_stock(db, "part", p1.id)
assert stock_p1 == 500.0, f"Expected 500, got {stock_p1}"
print(f"  ✓ {p1.id} 库存 = {stock_p1}")

print("=" * 60)
print("Flow 2: 创建饰品 → 设置 BOM → 创建订单 → 查配件汇总")
j1 = create_jewelry(db, {"name": "玫瑰戒指", "category": "戒指"})
j2 = create_jewelry(db, {"name": "银耳环", "category": "耳环"})
set_bom(db, j1.id, p1.id, 2.0)
set_bom(db, j1.id, p2.id, 1.0)
set_bom(db, j2.id, p1.id, 1.0)
# Order: 3 j1 + 2 j2
order = create_order(db, "张三", [
    {"jewelry_id": j1.id, "quantity": 3, "unit_price": 100.0},
    {"jewelry_id": j2.id, "quantity": 2, "unit_price": 50.0},
])
summary = get_parts_summary(db, order.id)
# p1: 3*2 + 2*1 = 8; p2: 3*1 = 3
assert summary[p1.id] == 8.0, f"p1 expected 8, got {summary[p1.id]}"
assert summary[p2.id] == 3.0, f"p2 expected 3, got {summary[p2.id]}"
print(f"  ✓ {order.id} 配件汇总: {p1.id}={summary[p1.id]}, {p2.id}={summary[p2.id]}")

print("=" * 60)
print("Flow 3: 电镀单 → 发出 → 分两次收回 → status=completed")
plating = create_plating_order(db, "金牌电镀厂", [
    {"part_id": p1.id, "qty": 100, "plating_method": "金色"},
])
send_plating_order(db, plating.id)
assert get_stock(db, "part", p1.id) == 400.0  # 500 - 100
from models.plating_order import PlatingOrderItem
pi = db.query(PlatingOrderItem).filter(PlatingOrderItem.plating_order_id == plating.id).first()
receive_plating_items(db, plating.id, [{"plating_order_item_id": pi.id, "qty": 60}])
assert get_plating_order(db, plating.id).status == "processing"
receive_plating_items(db, plating.id, [{"plating_order_item_id": pi.id, "qty": 40}])
db.refresh(pi)
final_plating = get_plating_order(db, plating.id)
assert final_plating.status == "completed", f"Expected completed, got {final_plating.status}"
assert final_plating.completed_at is not None
assert get_stock(db, "part", p1.id) == 500.0  # fully returned
print(f"  ✓ {plating.id} 最终 status = {final_plating.status}")

print("=" * 60)
print("Flow 4: 手工单 → 发出 → 分两次收回饰品 → status=completed")
handcraft = create_handcraft_order(
    db, "手工坊",
    parts=[{"part_id": p2.id, "qty": 50, "bom_qty": 48.0}],
    jewelries=[{"jewelry_id": j1.id, "qty": 20}],
)
send_handcraft_order(db, handcraft.id)
assert get_stock(db, "part", p2.id) == 250.0  # 300 - 50
from models.handcraft_order import HandcraftJewelryItem
hji = db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.handcraft_order_id == handcraft.id).first()
receive_handcraft_jewelries(db, handcraft.id, [{"handcraft_jewelry_item_id": hji.id, "qty": 12}])
assert get_handcraft_order(db, handcraft.id).status == "processing"
receive_handcraft_jewelries(db, handcraft.id, [{"handcraft_jewelry_item_id": hji.id, "qty": 8}])
db.refresh(hji)
final_hc = get_handcraft_order(db, handcraft.id)
assert final_hc.status == "completed", f"Expected completed, got {final_hc.status}"
assert get_stock(db, "jewelry", j1.id) == 20.0
print(f"  ✓ {handcraft.id} 最终 status = {final_hc.status}")

db.commit()
db.close()
os.remove(DB_PATH)
print("=" * 60)
print("✓ All verification flows passed!")
```

- [ ] **Step 2: Run verification script**

```bash
cd /Users/ycb/workspace/allen_shop && python scripts/verify_services.py
```

Expected output:
```
============================================================
Flow 1: 创建配件 → 入库 → 查库存
  ✓ PJ-0001 库存 = 500.0
============================================================
Flow 2: 创建饰品 → 设置 BOM → 创建订单 → 查配件汇总
  ✓ OR-0001 配件汇总: PJ-0001=8.0, PJ-0002=3.0
============================================================
Flow 3: 电镀单 → 发出 → 分两次收回 → status=completed
  ✓ EP-0001 最终 status = completed
============================================================
Flow 4: 手工单 → 发出 → 分两次收回饰品 → status=completed
  ✓ HC-0001 最终 status = completed
============================================================
✓ All verification flows passed!
```

- [ ] **Step 3: Run all tests**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pytest tests/ -v
```

Expected: All tests PASS, no failures.

- [ ] **Step 4: Commit**

```bash
git add scripts/verify_services.py
git commit -m "test: add end-to-end verification script for service layer"
```

---

## Summary

| Service | File | Tests |
|---------|------|-------|
| Helpers | `services/_helpers.py` | `tests/test_helpers.py` |
| Inventory | `services/inventory.py` | `tests/test_inventory.py` |
| Part | `services/part.py` | `tests/test_part.py` |
| Jewelry | `services/jewelry.py` | `tests/test_jewelry.py` |
| BOM | `services/bom.py` | `tests/test_bom.py` |
| Order | `services/order.py` | `tests/test_order.py` |
| Plating | `services/plating.py` | `tests/test_plating.py` |
| Handcraft | `services/handcraft.py` | `tests/test_handcraft.py` |
| Verification | `scripts/verify_services.py` | (standalone script) |
