# Multi-Keyword Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support whitespace-delimited multi-keyword search with AND semantics across all 9 existing `ILIKE`-based list endpoints, so queries like `"背镂空 桃心"` correctly find a part named `"背镂空满钻桃心"`.

**Architecture:** Add one shared helper `keyword_filter(keyword, *columns)` to `services/_helpers.py`. It tokenizes the keyword on any Unicode whitespace, builds an `AND`-of-`OR`s filter (each token OR'd across all columns, then AND'd across tokens), and returns a SQLAlchemy clause (or `None` if the keyword is empty). Every existing call site is migrated to this helper — the filter construction is centralized so future upgrades (e.g. pg_trgm) touch only one function.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x, PostgreSQL (ILIKE), pytest with a truncate-between-tests DB fixture.

**Spec:** `docs/superpowers/specs/2026-04-10-multi-keyword-search-design.md`

---

## File Structure

### New
- `tests/test_helpers_keyword_filter.py` — unit tests for the helper, via the `db` fixture against a real Postgres test DB

### Modified
- `services/_helpers.py` — add `keyword_filter`, extend imports
- `services/part.py` — 1 call site (`list_parts`)
- `services/jewelry.py` — 1 call site (`list_jewelries`)
- `services/inventory.py` — 2 call sites (`get_inventory_overview`, part + jewelry branches)
- `services/plating.py` — 1 call site (4-column search in `list_electroplated_items` or equivalent)
- `services/handcraft.py` — 2 call sites (part items + jewelry items)
- `services/kanban.py` — 2 call sites (`list_vendors`, plating + handcraft branches)
- `tests/test_api_parts.py` — add end-to-end regression test for the `"背镂空 桃心"` case

---

## Task 1: Add `keyword_filter` helper (TDD)

**Files:**
- Modify: `services/_helpers.py`
- Create: `tests/test_helpers_keyword_filter.py`

- [ ] **Step 1.1: Write the failing unit tests**

Create `tests/test_helpers_keyword_filter.py` with the following content. Tests use the existing `db` fixture from `tests/conftest.py` (truncates all tables before each test) and the real `Part` / `PlatingOrder` models so we verify actual Postgres ILIKE behavior, not just AST shape.

```python
from services._helpers import keyword_filter
from models.part import Part
from models.plating_order import PlatingOrder


def _make_parts(db, names):
    """Helper: create parts with the given Chinese names, one per category prefix."""
    parts = []
    for i, name in enumerate(names):
        p = Part(id=f"PJ-DZ-{i + 1:05d}", name=name, category="吊坠")
        db.add(p)
        parts.append(p)
    db.flush()
    return parts


def _query_parts(db, keyword):
    clause = keyword_filter(keyword, Part.name, Part.id)
    q = db.query(Part)
    if clause is not None:
        q = q.filter(clause)
    return q.order_by(Part.id).all()


def test_keyword_filter_none_returns_none():
    assert keyword_filter(None, Part.name) is None


def test_keyword_filter_empty_string_returns_none():
    assert keyword_filter("", Part.name) is None


def test_keyword_filter_whitespace_only_returns_none():
    assert keyword_filter("   ", Part.name) is None
    assert keyword_filter("\t\n ", Part.name) is None
    assert keyword_filter("　　", Part.name) is None  # U+3000 full-width


def test_keyword_filter_single_token_finds_substring(db):
    _make_parts(db, ["背镂空满钻桃心", "纯银链条", "简约吊坠"])
    results = _query_parts(db, "桃心")
    assert len(results) == 1
    assert results[0].name == "背镂空满钻桃心"


def test_keyword_filter_multi_token_half_width_space(db):
    """Primary regression: '背镂空 桃心' must find '背镂空满钻桃心'."""
    _make_parts(db, ["背镂空满钻桃心", "背镂空圆环", "满钻桃心吊坠"])
    results = _query_parts(db, "背镂空 桃心")
    assert len(results) == 1
    assert results[0].name == "背镂空满钻桃心"


def test_keyword_filter_multi_token_full_width_space(db):
    """全角空格 U+3000 must also split tokens."""
    _make_parts(db, ["背镂空满钻桃心", "背镂空圆环"])
    results = _query_parts(db, "背镂空　桃心")
    assert len(results) == 1
    assert results[0].name == "背镂空满钻桃心"


def test_keyword_filter_multi_token_and_semantics(db):
    """Both tokens must match — a non-existent second token yields empty."""
    _make_parts(db, ["背镂空满钻桃心"])
    results = _query_parts(db, "桃心 不存在的词")
    assert results == []


def test_keyword_filter_case_insensitive_ascii(db):
    _make_parts(db, ["taoxin ring"])
    results = _query_parts(db, "TAOXIN")
    assert len(results) == 1


def test_keyword_filter_mixed_id_and_name_token(db):
    """'PJ-DZ 桃心' should find a PJ-DZ-xxx record whose name contains 桃心."""
    parts = _make_parts(db, ["桃心吊坠", "圆环吊坠"])
    results = _query_parts(db, "PJ-DZ 桃心")
    assert len(results) == 1
    assert results[0].name == "桃心吊坠"


def test_keyword_filter_consecutive_whitespace_filtered(db):
    """Multiple spaces between tokens should not produce empty tokens."""
    _make_parts(db, ["背镂空满钻桃心"])
    results = _query_parts(db, "背镂空   桃心")
    assert len(results) == 1


def test_keyword_filter_single_column_and_semantics(db):
    """AND semantics must hold when only one column is passed."""
    db.add(PlatingOrder(id="EP-0001", supplier_name="老王北京电镀厂", status="pending"))
    db.add(PlatingOrder(id="EP-0002", supplier_name="老王上海电镀厂", status="pending"))
    db.add(PlatingOrder(id="EP-0003", supplier_name="老李北京电镀厂", status="pending"))
    db.flush()

    clause = keyword_filter("老王 北京", PlatingOrder.supplier_name)
    assert clause is not None
    results = db.query(PlatingOrder).filter(clause).all()
    assert len(results) == 1
    assert results[0].supplier_name == "老王北京电镀厂"
```

- [ ] **Step 1.2: Run the tests to confirm they fail**

```bash
pytest tests/test_helpers_keyword_filter.py -v
```

Expected: all tests fail with `ImportError: cannot import name 'keyword_filter' from 'services._helpers'`.

- [ ] **Step 1.3: Implement the helper**

Edit `services/_helpers.py`. Change the imports at the top:

```python
# Before
from sqlalchemy import text
from sqlalchemy.orm import Session
```

```python
# After
from typing import Optional

from sqlalchemy import and_, or_, text
from sqlalchemy.orm import Session
```

Append the new function to the end of the file (after `_max_number`):

```python
def keyword_filter(keyword: Optional[str], *columns):
    """Build a multi-keyword search filter.

    Splits ``keyword`` on any Unicode whitespace (including U+3000 全角空格).
    Each token must match at least one of ``columns`` (OR); all tokens must
    match (AND). Uses ILIKE for case-insensitive substring matching.

    Returns a SQLAlchemy clause, or ``None`` if ``keyword`` is empty or
    whitespace-only. Callers should check for ``None`` and skip adding the
    filter in that case.

    Example:
        clause = keyword_filter("背镂空 桃心", Part.name, Part.id)
        if clause is not None:
            q = q.filter(clause)
    """
    if not keyword:
        return None
    tokens = keyword.split()  # no-arg split handles any Unicode whitespace
    if not tokens:
        return None
    return and_(*[
        or_(*[col.ilike(f"%{tok}%") for col in columns])
        for tok in tokens
    ])
```

- [ ] **Step 1.4: Run the tests to confirm they pass**

```bash
pytest tests/test_helpers_keyword_filter.py -v
```

Expected: all 11 tests pass.

- [ ] **Step 1.5: Commit**

```bash
git add services/_helpers.py tests/test_helpers_keyword_filter.py
git commit -m "feat: add keyword_filter helper for multi-token search

Splits on any Unicode whitespace and builds an AND-of-ORs filter
(each token OR'd across columns, tokens AND'd together). Single
point of change for future search upgrades.

Refs: docs/superpowers/specs/2026-04-10-multi-keyword-search-design.md"
```

---

## Task 2: Migrate `services/part.py` + end-to-end regression test

**Files:**
- Modify: `tests/test_api_parts.py` (add test)
- Modify: `services/part.py:60-68`

- [ ] **Step 2.1: Write the failing API regression test**

Append this test to `tests/test_api_parts.py` (directly after `test_list_parts_filter_name_no_match`):

```python
def test_list_parts_multi_keyword_and(client):
    """Regression: '背镂空 桃心' must find '背镂空满钻桃心'.

    Before the keyword_filter migration, this failed because the whole
    string (including the space) was passed to a single ILIKE '%...%'.
    """
    client.post("/api/parts/", json={"name": "背镂空满钻桃心", "category": "吊坠"})
    client.post("/api/parts/", json={"name": "背镂空圆环", "category": "吊坠"})
    client.post("/api/parts/", json={"name": "满钻桃心", "category": "吊坠"})

    resp = client.get("/api/parts/", params={"name": "背镂空 桃心"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "背镂空满钻桃心"
```

- [ ] **Step 2.2: Run the test to confirm it fails**

```bash
pytest tests/test_api_parts.py::test_list_parts_multi_keyword_and -v
```

Expected: FAIL. The response body is `[]` (zero hits) because `services/part.py` still uses a single-string ILIKE.

- [ ] **Step 2.3: Migrate `list_parts` to use the helper**

Edit `services/part.py`. Update the import block at the top:

```python
# Before
from sqlalchemy import or_
from sqlalchemy.orm import Session

from decimal import Decimal, ROUND_HALF_UP

from models.part import Part, PartCostLog
from services._helpers import _next_id_by_category
```

```python
# After
from sqlalchemy.orm import Session

from decimal import Decimal, ROUND_HALF_UP

from models.part import Part, PartCostLog
from services._helpers import _next_id_by_category, keyword_filter
```

(Note: `or_` is no longer needed in this file — double-check with `grep -n "or_(" services/part.py` before removing. If any other call remains, keep the `or_` import.)

Then update `list_parts` (currently lines 60-68):

```python
# Before
def list_parts(db: Session, category: str = None, name: str = None, parent_part_id: str = None) -> List[Part]:
    q = db.query(Part)
    if category is not None:
        q = q.filter(Part.category == category)
    if name is not None:
        q = q.filter(or_(Part.name.ilike(f"%{name}%"), Part.id.ilike(f"%{name}%")))
    if parent_part_id is not None:
        q = q.filter(Part.parent_part_id == parent_part_id)
    return q.order_by(Part.id.desc()).all()
```

```python
# After
def list_parts(db: Session, category: str = None, name: str = None, parent_part_id: str = None) -> List[Part]:
    q = db.query(Part)
    if category is not None:
        q = q.filter(Part.category == category)
    clause = keyword_filter(name, Part.name, Part.id)
    if clause is not None:
        q = q.filter(clause)
    if parent_part_id is not None:
        q = q.filter(Part.parent_part_id == parent_part_id)
    return q.order_by(Part.id.desc()).all()
```

- [ ] **Step 2.4: Run the regression test to confirm it passes**

```bash
pytest tests/test_api_parts.py::test_list_parts_multi_keyword_and -v
```

Expected: PASS.

- [ ] **Step 2.5: Run the full parts test file to check for regressions**

```bash
pytest tests/test_api_parts.py -v
```

Expected: all tests pass (including the existing `test_list_parts_filter_name` and `test_list_parts_filter_name_no_match`).

- [ ] **Step 2.6: Commit**

```bash
git add services/part.py tests/test_api_parts.py
git commit -m "feat: use keyword_filter for part list search

Adds end-to-end regression test for '背镂空 桃心' finding
'背镂空满钻桃心'."
```

---

## Task 3: Migrate `services/jewelry.py`

**Files:**
- Modify: `services/jewelry.py:39-47`

- [ ] **Step 3.1: Migrate `list_jewelries` to use the helper**

Edit `services/jewelry.py`. Update the imports at the top:

```python
# Before
from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.jewelry import Jewelry
from services._helpers import _next_id_by_category
```

```python
# After
from sqlalchemy.orm import Session

from models.jewelry import Jewelry
from services._helpers import _next_id_by_category, keyword_filter
```

(Check with `grep -n "or_(" services/jewelry.py` — if no other `or_` usage remains, drop the import.)

Update `list_jewelries` (currently lines 39-47):

```python
# Before
def list_jewelries(db: Session, category: str = None, status: str = None, name: str = None) -> list:
    q = db.query(Jewelry)
    if category is not None:
        q = q.filter(Jewelry.category == category)
    if status is not None:
        q = q.filter(Jewelry.status == status)
    if name is not None:
        q = q.filter(or_(Jewelry.name.ilike(f"%{name}%"), Jewelry.id.ilike(f"%{name}%")))
    return q.order_by(Jewelry.id.desc()).all()
```

```python
# After
def list_jewelries(db: Session, category: str = None, status: str = None, name: str = None) -> list:
    q = db.query(Jewelry)
    if category is not None:
        q = q.filter(Jewelry.category == category)
    if status is not None:
        q = q.filter(Jewelry.status == status)
    clause = keyword_filter(name, Jewelry.name, Jewelry.id)
    if clause is not None:
        q = q.filter(clause)
    return q.order_by(Jewelry.id.desc()).all()
```

- [ ] **Step 3.2: Run the jewelry tests**

```bash
pytest tests/test_api_jewelries.py -v
```

Expected: all tests pass. (If a test failed due to a whitespace-in-keyword dependency, update that test's expected behavior — see Task 8 cleanup step.)

- [ ] **Step 3.3: Commit**

```bash
git add services/jewelry.py
git commit -m "feat: use keyword_filter for jewelry list search"
```

---

## Task 4: Migrate `services/inventory.py` (2 sites)

**Files:**
- Modify: `services/inventory.py:84-146` (function `get_inventory_overview`)

- [ ] **Step 4.1: Migrate both branches in `get_inventory_overview`**

Edit `services/inventory.py`. Update the imports:

```python
# Before
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.inventory_log import InventoryLog
from models.jewelry import Jewelry
from models.part import Part
```

```python
# After
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.inventory_log import InventoryLog
from models.jewelry import Jewelry
from models.part import Part
from services._helpers import keyword_filter
```

Update the part branch (currently lines 108-109):

```python
# Before
        if name:
            q = q.filter(Part.name.ilike(f"%{name}%") | Part.id.ilike(f"%{name}%"))
```

```python
# After
        clause = keyword_filter(name, Part.name, Part.id)
        if clause is not None:
            q = q.filter(clause)
```

Update the jewelry branch (currently lines 129-130):

```python
# Before
        if name:
            q = q.filter(Jewelry.name.ilike(f"%{name}%") | Jewelry.id.ilike(f"%{name}%"))
```

```python
# After
        clause = keyword_filter(name, Jewelry.name, Jewelry.id)
        if clause is not None:
            q = q.filter(clause)
```

- [ ] **Step 4.2: Run the inventory tests**

```bash
pytest tests/test_api_inventory.py -v
```

Expected: all tests pass.

- [ ] **Step 4.3: Commit**

```bash
git add services/inventory.py
git commit -m "feat: use keyword_filter in inventory overview (parts + jewelries)"
```

---

## Task 5: Migrate `services/plating.py`

**Files:**
- Modify: `services/plating.py:371-380` (the 4-column ILIKE block)

- [ ] **Step 5.1: Migrate the `part_keyword` filter**

Edit `services/plating.py`. Add the helper import near the other service imports (search for `from services._helpers import`; if none exists, add it with the other `from services` imports at the top):

```python
from services._helpers import keyword_filter
```

Update the filter block (currently lines 371-380):

```python
# Before
    if part_keyword:
        like_pattern = f"%{part_keyword}%"
        q = q.filter(
            or_(
                SendPart.id.ilike(like_pattern),
                SendPart.name.ilike(like_pattern),
                ReceivePart.id.ilike(like_pattern),
                ReceivePart.name.ilike(like_pattern),
            )
        )
```

```python
# After
    clause = keyword_filter(
        part_keyword,
        SendPart.id,
        SendPart.name,
        ReceivePart.id,
        ReceivePart.name,
    )
    if clause is not None:
        q = q.filter(clause)
```

Do **not** remove the `or_` import from this file without checking — `grep -n "or_(" services/plating.py` first. Plating has many other uses of `or_`, leave the import.

- [ ] **Step 5.2: Run the plating tests**

```bash
pytest tests/test_api_plating.py tests/test_plating.py -v
```

Expected: all tests pass.

- [ ] **Step 5.3: Commit**

```bash
git add services/plating.py
git commit -m "feat: use keyword_filter in plating electroplated-items search"
```

---

## Task 6: Migrate `services/handcraft.py` (2 sites)

**Files:**
- Modify: `services/handcraft.py:543-545` (part items branch)
- Modify: `services/handcraft.py:596-601` (jewelry items branch)

- [ ] **Step 6.1: Migrate both branches**

Edit `services/handcraft.py`. Add the helper import (check existing `from services._helpers import ...` line and extend it, or add a new one):

```python
from services._helpers import keyword_filter
```

Update the part items branch (currently lines 543-545):

```python
# Before
    if keyword:
        like = f"%{keyword}%"
        pq = pq.filter(or_(Part.id.ilike(like), Part.name.ilike(like)))
```

```python
# After
    clause = keyword_filter(keyword, Part.id, Part.name)
    if clause is not None:
        pq = pq.filter(clause)
```

Update the jewelry items branch (currently lines 596-601):

```python
# Before
    if keyword:
        like = f"%{keyword}%"
        jq = jq.filter(or_(
            Jewelry.id.ilike(like), Jewelry.name.ilike(like),
            Part.id.ilike(like), Part.name.ilike(like),
        ))
```

```python
# After
    clause = keyword_filter(
        keyword, Jewelry.id, Jewelry.name, Part.id, Part.name,
    )
    if clause is not None:
        jq = jq.filter(clause)
```

Do **not** remove the `or_` import without checking — `grep -n "or_(" services/handcraft.py` first.

- [ ] **Step 6.2: Run the handcraft tests**

```bash
pytest tests/test_api_handcraft.py tests/test_handcraft.py -v
```

Expected: all tests pass.

- [ ] **Step 6.3: Commit**

```bash
git add services/handcraft.py
git commit -m "feat: use keyword_filter in handcraft search (parts + jewelries)"
```

---

## Task 7: Migrate `services/kanban.py` (2 sites in `list_vendors`)

**Files:**
- Modify: `services/kanban.py:1247-1265` (`list_vendors`)

- [ ] **Step 7.1: Migrate both supplier-name searches**

Edit `services/kanban.py`. Add the helper import (check existing `from services._helpers import ...` line and extend it, or add a new one):

```python
from services._helpers import keyword_filter
```

Update `list_vendors` (currently lines 1247-1265):

```python
# Before
def list_vendors(db: Session, order_type: str | None = None, q: str | None = None) -> list[str]:
    """Return distinct vendor names for dropdown search."""
    names: set[str] = set()

    if order_type is None or order_type == "plating":
        qb = db.query(PlatingOrder.supplier_name).distinct()
        if q:
            qb = qb.filter(PlatingOrder.supplier_name.ilike(f"%{q}%"))
        for (name,) in qb.all():
            names.add(name)

    if order_type is None or order_type == "handcraft":
        qb = db.query(HandcraftOrder.supplier_name).distinct()
        if q:
            qb = qb.filter(HandcraftOrder.supplier_name.ilike(f"%{q}%"))
        for (name,) in qb.all():
            names.add(name)

    return sorted(names)
```

```python
# After
def list_vendors(db: Session, order_type: str | None = None, q: str | None = None) -> list[str]:
    """Return distinct vendor names for dropdown search."""
    names: set[str] = set()

    if order_type is None or order_type == "plating":
        qb = db.query(PlatingOrder.supplier_name).distinct()
        clause = keyword_filter(q, PlatingOrder.supplier_name)
        if clause is not None:
            qb = qb.filter(clause)
        for (name,) in qb.all():
            names.add(name)

    if order_type is None or order_type == "handcraft":
        qb = db.query(HandcraftOrder.supplier_name).distinct()
        clause = keyword_filter(q, HandcraftOrder.supplier_name)
        if clause is not None:
            qb = qb.filter(clause)
        for (name,) in qb.all():
            names.add(name)

    return sorted(names)
```

- [ ] **Step 7.2: Run the kanban tests**

```bash
pytest tests/test_api_kanban.py -v 2>/dev/null || pytest tests/ -k kanban -v
```

Expected: all tests pass. (If there is no dedicated kanban test file, the `-k kanban` fallback runs anything matching.)

- [ ] **Step 7.3: Commit**

```bash
git add services/kanban.py
git commit -m "feat: use keyword_filter in kanban list_vendors"
```

---

## Task 8: Full test suite + stray test cleanup

**Files:**
- Any `tests/test_api_*.py` with a broken search assertion (only if found)

- [ ] **Step 8.1: Run the full test suite**

```bash
pytest -v
```

Expected: all tests pass. The spec's behavior analysis concluded no existing tests should break, because tokenized AND is a superset of literal substring matching in all non-pathological cases. If a test unexpectedly fails, proceed to 8.2.

- [ ] **Step 8.2: Fix any broken tests (only if 8.1 failed)**

For each failing test, read the assertion and the search query. Decide which case applies:

1. **Test was verifying "search finds this record"** and the new AND behavior is strictly more permissive → the test should still pass; if it doesn't, something is wrong with the migration, not the test. Re-check the relevant service file against Tasks 2–7.

2. **Test was verifying "search does NOT find this record"** and the new AND behavior now finds it → this is an expected behavior change. Update the test's expected count / list. Add a comment explaining why: `# Multi-keyword AND semantics added 2026-04-10; see docs/superpowers/specs/2026-04-10-multi-keyword-search-design.md`.

3. **Test was using a literal multi-space substring** (unlikely) → STOP. Surface this case to the user — the spec flagged this as an edge case requiring discussion.

- [ ] **Step 8.3: Re-run the full suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 8.4: Commit test adjustments (only if 8.2 made changes)**

```bash
git add tests/
git commit -m "test: adjust search expectations for multi-keyword AND semantics"
```

- [ ] **Step 8.5: Final verification — search for any lingering `ilike(f"%{...}%")` patterns**

```bash
grep -rn 'ilike(f"%{' services/
```

Expected: no results except inside `services/_helpers.py` (inside `keyword_filter`), and possibly `services/inventory.py:76-78` for `item_id` / `reason` filters in `list_stock_logs` — those are **out of scope** for this change (they were not in the original 9-site list, and the spec did not propose changing them). If anything else appears, it's a missed migration — go back to the corresponding task.

---

## Done

At this point:
- `keyword_filter` is the single source of truth for all list-endpoint search behavior.
- All 9 original call sites delegate to it.
- The original regression case (`"背镂空 桃心"` → `"背镂空满钻桃心"`) is pinned by an API-level test.
- All pre-existing tests still pass.
- Future search upgrades (pg_trgm, pinyin, fuzzy matching) only need to modify the helper body.
