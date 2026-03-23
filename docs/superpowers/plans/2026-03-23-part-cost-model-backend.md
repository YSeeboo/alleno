# 配件成本模型（后端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cost breakdown fields (purchase_cost, bead_cost, plating_cost) to Part, a cost change log table, and a cost-logs API endpoint.

**Architecture:** Three new nullable columns on Part, a new `PartCostLog` model, a `update_part_cost` service function that updates one cost field + recalcs unit_cost + logs the change. `update_part` blocks direct unit_cost writes. `create_part_variant` stops inheriting cost fields.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, Pydantic v2, pytest

**Spec:** `docs/superpowers/specs/2026-03-23-part-cost-model-design.md`

---

### Task 1: Model — Part 新字段 + PartCostLog

**Files:**
- Modify: `models/part.py` (add 3 columns + new class)
- Modify: `models/__init__.py` (add import)
- Modify: `database.py` (add ensure_schema_compat entries)

- [ ] **Step 1: Add cost fields and PartCostLog model to `models/part.py`**

Add imports:

```python
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from database import Base
from time_utils import now_beijing
```

Add 3 columns to `Part` class (after `unit_cost`):

```python
    purchase_cost = Column(Numeric(18, 7), nullable=True)
    bead_cost = Column(Numeric(18, 7), nullable=True)
    plating_cost = Column(Numeric(18, 7), nullable=True)
```

Add new class after `Part`:

```python
class PartCostLog(Base):
    __tablename__ = "part_cost_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    field = Column(String, nullable=False)
    cost_before = Column(Numeric(18, 7), nullable=True)
    cost_after = Column(Numeric(18, 7), nullable=True)
    unit_cost_before = Column(Numeric(18, 7), nullable=True)
    unit_cost_after = Column(Numeric(18, 7), nullable=True)
    source_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
```

- [ ] **Step 2: Register in `models/__init__.py`**

```python
from .part import Part, PartCostLog
```

Add `"PartCostLog"` to `__all__`.

- [ ] **Step 3: Add ensure_schema_compat entries in `database.py`**

In the existing `if inspector.has_table("part"):` block (around line 41), after the `parent_part_id` check, add:

```python
            for cost_col in ("purchase_cost", "bead_cost", "plating_cost"):
                if cost_col not in columns:
                    conn.execute(text(f"ALTER TABLE part ADD COLUMN {cost_col} NUMERIC(18,7) NULL"))
                    logger.warning("Added missing part.%s column", cost_col)
```

- [ ] **Step 4: Verify**

Run: `python -c "from models import *; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add models/part.py models/__init__.py database.py
git commit -m "feat: add Part cost fields and PartCostLog model"
```

---

### Task 2: Schemas — cost fields + log response

**Files:**
- Modify: `schemas/part.py`

- [ ] **Step 1: Add cost fields to PartResponse**

In `PartResponse` class, after `unit_cost` field, add:

```python
    purchase_cost: Optional[float] = None
    bead_cost: Optional[float] = None
    plating_cost: Optional[float] = None
```

- [ ] **Step 2: Add PartCostLogResponse schema**

At the end of the file, add:

```python
from datetime import datetime

class PartCostLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    part_id: str
    field: str
    cost_before: Optional[float] = None
    cost_after: Optional[float] = None
    unit_cost_before: Optional[float] = None
    unit_cost_after: Optional[float] = None
    source_id: Optional[str] = None
    created_at: datetime
```

Note: move the `datetime` import to the top of the file with other imports.

- [ ] **Step 3: Remove `unit_cost` from `PartUpdate`**

In `PartUpdate` class, remove:

```python
    unit_cost: Optional[float] = None
```

This prevents direct manual updates to `unit_cost`.

- [ ] **Step 4: Commit**

```bash
git add schemas/part.py
git commit -m "feat: add cost breakdown fields to Part schemas"
```

---

### Task 3: Service — update_part_cost + update_part fix + variant fix

**Files:**
- Modify: `services/part.py`
- Create: `tests/test_part_cost.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_part_cost.py`:

```python
import pytest
from decimal import Decimal

from models.part import Part
from services.part import create_part, update_part, create_part_variant


@pytest.fixture
def part(db):
    return create_part(db, {"name": "测试配件", "category": "吊坠"})


def test_update_part_cost_purchase(db, part):
    from services.part import update_part_cost
    log = update_part_cost(db, part.id, "purchase_cost", 2.5, source_id="CG-0001")
    assert log is not None
    assert log.field == "purchase_cost"
    assert log.cost_before is None
    assert log.cost_after == Decimal("2.5")
    assert log.unit_cost_before is None or log.unit_cost_before == 0
    assert log.unit_cost_after == Decimal("2.5")
    assert log.source_id == "CG-0001"
    assert part.purchase_cost == Decimal("2.5")
    assert part.unit_cost == Decimal("2.5")


def test_update_part_cost_accumulates(db, part):
    from services.part import update_part_cost
    update_part_cost(db, part.id, "purchase_cost", 2.5)
    update_part_cost(db, part.id, "bead_cost", 0.15)
    update_part_cost(db, part.id, "plating_cost", 1.0)
    assert part.unit_cost == Decimal("3.65")


def test_update_part_cost_no_change_returns_none(db, part):
    from services.part import update_part_cost
    update_part_cost(db, part.id, "purchase_cost", 2.5)
    result = update_part_cost(db, part.id, "purchase_cost", 2.5)
    assert result is None


def test_update_part_cost_invalid_field(db, part):
    from services.part import update_part_cost
    with pytest.raises(ValueError, match="无效"):
        update_part_cost(db, part.id, "invalid_field", 1.0)


def test_update_part_cost_logs_recorded(db, part):
    from services.part import update_part_cost, list_part_cost_logs
    update_part_cost(db, part.id, "purchase_cost", 2.5, source_id="CG-0001")
    update_part_cost(db, part.id, "bead_cost", 0.15, source_id="CG-0001")
    logs = list_part_cost_logs(db, part.id)
    assert len(logs) == 2
    assert logs[0].field == "bead_cost"  # DESC order
    assert logs[1].field == "purchase_cost"


def test_update_part_ignores_unit_cost(db, part):
    """update_part should ignore unit_cost in data dict."""
    from services.part import update_part_cost
    update_part_cost(db, part.id, "purchase_cost", 2.5)
    updated = update_part(db, part.id, {"name": "新名称", "unit_cost": 999})
    assert updated.unit_cost == Decimal("2.5")  # not overwritten
    assert updated.name == "新名称"


def test_create_variant_no_cost_inheritance(db, part):
    """Variants should not inherit cost fields from parent."""
    from services.part import update_part_cost
    update_part_cost(db, part.id, "purchase_cost", 2.5)
    update_part_cost(db, part.id, "bead_cost", 0.15)
    variant = create_part_variant(db, part.id, "G")
    assert variant.purchase_cost is None
    assert variant.bead_cost is None
    assert variant.plating_cost is None
    assert variant.unit_cost is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_part_cost.py -v`
Expected: FAIL (ImportError — functions don't exist)

- [ ] **Step 3: Add `update_part_cost` and `list_part_cost_logs` to `services/part.py`**

Add import at top:

```python
from decimal import Decimal, ROUND_HALF_UP

from models.part import Part, PartCostLog
```

(Replace existing `from models.part import Part`)

Add constant:

```python
_COST_FIELDS = {"purchase_cost", "bead_cost", "plating_cost"}
_Q7 = Decimal("0.0000001")
```

Add functions at the end of the file:

```python
def _recalc_unit_cost(part: Part) -> None:
    """Recalculate unit_cost from the three cost components."""
    purchase = Decimal(str(part.purchase_cost or 0))
    bead = Decimal(str(part.bead_cost or 0))
    plating = Decimal(str(part.plating_cost or 0))
    total = purchase + bead + plating
    part.unit_cost = total if total else None


def update_part_cost(
    db: Session, part_id: str, field: str, value: float, source_id: str | None = None,
) -> PartCostLog | None:
    if field not in _COST_FIELDS:
        raise ValueError(f"无效的成本字段: {field}")
    part = get_part(db, part_id)
    if part is None:
        raise ValueError(f"Part not found: {part_id}")

    old_field_value = getattr(part, field)
    old_unit_cost = part.unit_cost

    new_value = Decimal(str(value)).quantize(_Q7, rounding=ROUND_HALF_UP)

    # Compare: treat None as different from 0
    old_comparable = Decimal(str(old_field_value)).quantize(_Q7, rounding=ROUND_HALF_UP) if old_field_value is not None else None
    if old_comparable == new_value:
        return None

    setattr(part, field, new_value)
    _recalc_unit_cost(part)

    log = PartCostLog(
        part_id=part_id,
        field=field,
        cost_before=old_field_value,
        cost_after=new_value,
        unit_cost_before=old_unit_cost,
        unit_cost_after=part.unit_cost,
        source_id=source_id,
    )
    db.add(log)
    db.flush()
    return log


def list_part_cost_logs(db: Session, part_id: str) -> list[PartCostLog]:
    return (
        db.query(PartCostLog)
        .filter(PartCostLog.part_id == part_id)
        .order_by(PartCostLog.created_at.desc())
        .all()
    )
```

- [ ] **Step 4: Fix `update_part` to ignore `unit_cost`**

In `services/part.py`, in the `update_part` function, before the `for key, value in data.items():` loop (line 89), add:

```python
    data.pop("unit_cost", None)
```

- [ ] **Step 5: Fix `create_part_variant` to not inherit cost fields**

In `services/part.py`, in the `create_part_variant` function (around line 157-170), change the variant creation to:

```python
    variant = Part(
        id=_next_id_by_category(db, Part, prefix),
        name=variant_name,
        category=parent.category,
        unit=parent.unit,
        plating_process=parent.plating_process,
        image=parent.image,
        color=color,
        parent_part_id=part_id,
    )
```

Remove `unit_cost=parent.unit_cost` from the constructor.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_part_cost.py -v`
Expected: All 7 tests PASS

- [ ] **Step 7: Run full test suite**

Run: `pytest --tb=short`
Expected: All existing tests PASS. Note: if any existing test relies on `unit_cost` being in `PartUpdate` or variant inheriting `unit_cost`, it may need adjustment.

- [ ] **Step 8: Commit**

```bash
git add services/part.py tests/test_part_cost.py
git commit -m "feat: add update_part_cost service, block direct unit_cost writes"
```

---

### Task 4: API — cost-logs endpoint

**Files:**
- Modify: `api/parts.py`

- [ ] **Step 1: Write API tests**

Append to `tests/test_part_cost.py`:

```python
# --- API Tests ---

def test_api_part_response_includes_cost_fields(client, db):
    from models.part import Part as PartModel
    p = PartModel(id="PJ-DZ-99999", name="API测试配件", category="吊坠")
    db.add(p)
    db.flush()
    resp = client.get("/api/parts/PJ-DZ-99999")
    assert resp.status_code == 200
    data = resp.json()
    assert "purchase_cost" in data
    assert "bead_cost" in data
    assert "plating_cost" in data
    assert data["purchase_cost"] is None


def test_api_get_cost_logs(client, db):
    from services.part import update_part_cost
    p = Part(id="PJ-DZ-99998", name="日志测试配件", category="吊坠")
    db.add(p)
    db.flush()
    update_part_cost(db, p.id, "purchase_cost", 2.5, source_id="CG-0001")
    update_part_cost(db, p.id, "bead_cost", 0.15, source_id="CG-0001")

    resp = client.get(f"/api/parts/{p.id}/cost-logs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["field"] == "bead_cost"  # DESC order
    assert data[0]["source_id"] == "CG-0001"
    assert data[1]["field"] == "purchase_cost"


def test_api_get_cost_logs_empty(client, db):
    p = Part(id="PJ-DZ-99997", name="空日志配件", category="吊坠")
    db.add(p)
    db.flush()
    resp = client.get(f"/api/parts/{p.id}/cost-logs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_api_update_part_ignores_unit_cost(client, db):
    from services.part import update_part_cost
    p = Part(id="PJ-DZ-99996", name="忽略成本配件", category="吊坠")
    db.add(p)
    db.flush()
    update_part_cost(db, p.id, "purchase_cost", 5.0)

    resp = client.patch("/api/parts/PJ-DZ-99996", json={"unit_cost": 999})
    assert resp.status_code == 200
    assert resp.json()["unit_cost"] == 5.0  # not overwritten
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_part_cost.py::test_api_get_cost_logs -v`
Expected: FAIL (404 — route doesn't exist)

- [ ] **Step 3: Add API endpoint to `api/parts.py`**

Add schema import:

```python
from schemas.part import PartCreate, FindOrCreateVariantResponse, PartCostLogResponse, PartImportResponse, PartResponse, PartUpdate, PartVariantCreate
```

Add service import:

```python
from services.part import COLOR_VARIANTS, create_part, create_part_variant, find_or_create_variant, get_part, list_part_cost_logs, list_part_variants, list_parts, update_part, delete_part
```

Add endpoint (before `/{part_id}` GET route to avoid path conflicts):

```python
@router.get("/{part_id}/cost-logs", response_model=list[PartCostLogResponse])
def api_get_part_cost_logs(part_id: str, db: Session = Depends(get_db)):
    part = get_part(db, part_id)
    if part is None:
        raise HTTPException(status_code=404, detail=f"Part {part_id} not found")
    return list_part_cost_logs(db, part_id)
```

- [ ] **Step 4: Run all tests**

Run: `pytest tests/test_part_cost.py -v`
Expected: All 11 tests PASS (7 service + 4 API)

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add api/parts.py schemas/part.py tests/test_part_cost.py
git commit -m "feat: add cost-logs API endpoint and cost fields in Part response"
```
