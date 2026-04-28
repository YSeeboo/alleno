# 手工单配货模拟 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在手工单详情页加入「配货模拟」功能（按 part_item 分组、复合件展开为原子件、含建议数量、状态门控、PDF 导出），与订单端同名功能视觉对齐但数据模型独立。

**Architecture:** 新增 `HandcraftPickingRecord` 表存储勾选状态；新建 `services/handcraft_picking.py` 复用 `services/picking._expand_to_atoms` 做复合件展开；前端新增独立的 `HandcraftPickingSimulationModal.vue`，挂在 `HandcraftDetail.vue` 的「配件明细」卡 header。`pending` 状态可写，其他状态只读。

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic v2 + ReportLab（PDF）；Vue 3 + Naive UI + Pinia（前端）。

**Spec Reference:** `docs/superpowers/specs/2026-04-27-handcraft-picking-simulation-design.md`

---

## File Structure

**Create**：
- `services/handcraft_picking.py` — 拣货模拟服务（核心逻辑）
- `services/handcraft_picking_list_pdf.py` — PDF 生成
- `tests/test_api_handcraft_picking.py` — API + 服务集成测试
- `frontend/src/components/picking/HandcraftPickingSimulationModal.vue` — 模态组件

**Modify**：
- `models/handcraft_order.py` — 新增 `HandcraftPickingRecord` 类
- `models/__init__.py` — 导出新模型
- `schemas/handcraft.py` — 新增 4 个 Pydantic 响应模型
- `api/handcraft.py` — 新增 5 个路由
- `services/handcraft.py` — `delete_handcraft_part` 同步清理孤儿记录
- `frontend/src/api/handcraft.js` — 新增 5 个 API client 函数
- `frontend/src/views/handcraft/HandcraftDetail.vue` — 新增按钮 + 模态挂载

---

## Task 1: 数据模型与 Pydantic schema 骨架

**Files:**
- Modify: `models/handcraft_order.py`（追加新 class）
- Modify: `models/__init__.py:1-50`
- Modify: `schemas/handcraft.py`（追加 4 个 BaseModel）

- [ ] **Step 1.1: 在 `models/handcraft_order.py` 末尾追加 `HandcraftPickingRecord`**

```python
# 在文件顶部 import 区追加
from sqlalchemy import UniqueConstraint
```

```python
# 在 HandcraftJewelryItem class 之后追加：
class HandcraftPickingRecord(Base):
    """Per-row picking state for handcraft orders' 配货模拟.
    Row exists = picked; no row = not picked. UI-only helper, does not affect
    inventory or order status."""

    __tablename__ = "handcraft_picking_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    handcraft_order_id = Column(
        String, ForeignKey("handcraft_order.id"), nullable=False, index=True
    )
    handcraft_part_item_id = Column(
        Integer, ForeignKey("handcraft_part_item.id"), nullable=False
    )
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    picked_at = Column(DateTime, default=now_beijing, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "handcraft_part_item_id", "part_id",
            name="uq_handcraft_picking_record_item_part",
        ),
    )
```

注意：`models/handcraft_order.py` 顶部已有 `Column, DateTime, ForeignKey, Integer, Numeric, String, Text` 的 import；需要追加 `UniqueConstraint`。`now_beijing` 已经被 import。

- [ ] **Step 1.2: 在 `models/__init__.py` 注册新模型**

修改两处：

```python
# 原行 8：
from .handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
# 改为：
from .handcraft_order import (
    HandcraftOrder,
    HandcraftPartItem,
    HandcraftJewelryItem,
    HandcraftPickingRecord,
)
```

在 `__all__` 列表里 `"HandcraftJewelryItem"` 之后追加 `"HandcraftPickingRecord"`。

- [ ] **Step 1.3: 在 `schemas/handcraft.py` 追加 Pydantic 模型**

在文件末尾追加：

```python
# --- Picking simulation (配货模拟) ---


class HandcraftPickingVariant(BaseModel):
    """One picking row inside a part_item group. For atomic items this is the
    only row; for composites this is one expanded atom."""
    part_id: str
    part_name: str
    part_image: Optional[str] = None
    needed_qty: float
    suggested_qty: Optional[int] = None
    current_stock: float
    picked: bool


class HandcraftPickingGroup(BaseModel):
    part_item_id: int
    parent_part_id: str
    parent_part_name: str
    parent_part_image: Optional[str] = None
    parent_is_composite: bool
    parent_qty: float
    parent_bom_qty: Optional[float] = None
    rows: List[HandcraftPickingVariant]


class HandcraftPickingProgress(BaseModel):
    total: int
    picked: int


class HandcraftPickingResponse(BaseModel):
    handcraft_order_id: str
    supplier_name: str
    status: str
    groups: List[HandcraftPickingGroup]
    progress: HandcraftPickingProgress


class HandcraftPickingMarkRequest(BaseModel):
    part_item_id: int
    part_id: str
```

- [ ] **Step 1.4: 验证 — 运行测试 fixture 自检**

Run:
```bash
pytest tests/test_api_picking.py -v --tb=short -x 2>&1 | tail -20
```

Expected: 全部通过（验证我们没破坏现有订单端 picking 测试，也验证 `Base.metadata.create_all` 能成功创建新表）。

- [ ] **Step 1.5: Commit**

```bash
git add models/handcraft_order.py models/__init__.py schemas/handcraft.py
git commit -m "feat(handcraft): add HandcraftPickingRecord model + picking schemas"
```

---

## Task 2: `get_handcraft_picking_simulation` — 原子件 + 空场景

**Files:**
- Create: `services/handcraft_picking.py`
- Create: `tests/test_api_handcraft_picking.py`

- [ ] **Step 2.1: 写第一批失败测试（空、原子件、库存对照、订单不存在）**

创建 `tests/test_api_handcraft_picking.py`：

```python
"""API + service tests for /api/handcraft/{id}/picking/... endpoints.

Note: these tests use the API client to hit FastAPI; service-layer logic is
exercised through the routes. The test DB fixture in conftest.py truncates
all tables between tests."""

from decimal import Decimal

from models.handcraft_order import (
    HandcraftOrder,
    HandcraftPartItem,
    HandcraftPickingRecord,
)
from models.inventory_log import InventoryLog
from models.part import Part
from models.part_bom import PartBom


def _add_atomic_part(db, pid="PJ-X-00001", name="珠子", tier="small"):
    db.add(Part(id=pid, name=name, category="吊坠", size_tier=tier))


def _add_inventory(db, pid, qty, reason="期初"):
    db.add(InventoryLog(
        item_type="part", item_id=pid, change_qty=Decimal(str(qty)), reason=reason,
    ))


def _setup_atomic(db):
    """1 atomic part with stock, 1 handcraft order with 1 part_item."""
    _add_atomic_part(db, "PJ-X-00001", "珠子A", "small")
    _add_inventory(db, "PJ-X-00001", 50)
    db.add(HandcraftOrder(id="HC-TEST-1", supplier_name="商家A", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-TEST-1",
        part_id="PJ-X-00001",
        qty=Decimal("10"),
        bom_qty=Decimal("8"),
    ))
    db.flush()


def test_get_picking_order_not_found(client, db):
    resp = client.get("/api/handcraft/HC-NOPE/picking")
    assert resp.status_code == 400
    assert "HC-NOPE" in resp.json()["detail"]


def test_get_picking_empty_order(client, db):
    db.add(HandcraftOrder(id="HC-EMPTY", supplier_name="商家", status="pending"))
    db.flush()
    resp = client.get("/api/handcraft/HC-EMPTY/picking")
    assert resp.status_code == 200
    body = resp.json()
    assert body["handcraft_order_id"] == "HC-EMPTY"
    assert body["supplier_name"] == "商家"
    assert body["status"] == "pending"
    assert body["groups"] == []
    assert body["progress"] == {"total": 0, "picked": 0}


def test_get_picking_atomic_single_item(client, db):
    _setup_atomic(db)
    resp = client.get("/api/handcraft/HC-TEST-1/picking")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert len(body["groups"]) == 1
    g = body["groups"][0]
    assert g["parent_part_id"] == "PJ-X-00001"
    assert g["parent_is_composite"] is False
    assert g["parent_qty"] == 10.0
    assert g["parent_bom_qty"] == 8.0
    assert len(g["rows"]) == 1
    row = g["rows"][0]
    assert row["part_id"] == "PJ-X-00001"
    assert row["part_name"] == "珠子A"
    assert row["needed_qty"] == 10.0
    assert row["current_stock"] == 50.0
    assert row["picked"] is False
    assert body["progress"] == {"total": 1, "picked": 0}
```

- [ ] **Step 2.2: 运行测试，确认失败**

Run:
```bash
pytest tests/test_api_handcraft_picking.py -v --tb=short
```

Expected: 4 个测试全部 FAIL。`test_get_picking_order_not_found` 等 3 个会因路由不存在返回 404（FastAPI 默认）；测试断言 400 → 失败。

- [ ] **Step 2.3: 创建 `services/handcraft_picking.py` 最小实现（仅原子件）**

```python
"""Handcraft picking simulation (手工单配货模拟) service.

Aggregates a handcraft order's part items into a picker-friendly grouped
structure: each HandcraftPartItem becomes one group with one or more rows.
Atomic part_items produce a single row; composite part_items expand to
multiple atom rows (via services.picking._expand_to_atoms).

Picked state persists per (handcraft_part_item_id, part_id) in
handcraft_picking_record. This module does NOT touch inventory_log or
order status — purely a UI helper.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.handcraft_order import (
    HandcraftOrder,
    HandcraftPartItem,
    HandcraftPickingRecord,
)
from models.inventory_log import InventoryLog
from models.part import Part
from schemas.handcraft import (
    HandcraftPickingGroup,
    HandcraftPickingProgress,
    HandcraftPickingResponse,
    HandcraftPickingVariant,
)


def get_handcraft_picking_simulation(
    db: Session, handcraft_order_id: str
) -> HandcraftPickingResponse:
    """Aggregate all parts needed for the handcraft order into a picking-oriented
    structure. Raises ValueError if the order does not exist."""
    order = db.query(HandcraftOrder).filter_by(id=handcraft_order_id).one_or_none()
    if order is None:
        raise ValueError(f"手工单 {handcraft_order_id} 不存在")

    part_items = (
        db.query(HandcraftPartItem)
        .filter_by(handcraft_order_id=handcraft_order_id)
        .order_by(HandcraftPartItem.id.asc())
        .all()
    )
    if not part_items:
        return HandcraftPickingResponse(
            handcraft_order_id=order.id,
            supplier_name=order.supplier_name,
            status=order.status,
            groups=[],
            progress=HandcraftPickingProgress(total=0, picked=0),
        )

    # Step 1: load all parts referenced (direct + composite-expanded).
    expanded = _expand_part_items(db, part_items)

    # Step 2: gather all atomic part ids that appear in any picking row.
    atom_ids = sorted({row[1] for rows in expanded.values() for row in rows})
    parts_by_id = _load_parts(db, atom_ids + [pi.part_id for pi in part_items])

    # Step 3: batch-load current_stock per atom.
    stock_by_part = _load_stock(db, atom_ids)

    # Step 4: batch-load picked records for this order, keyed by (part_item_id, part_id).
    picked_keys = _load_picked_keys(db, handcraft_order_id)

    # Step 5: assemble groups.
    groups: list[HandcraftPickingGroup] = []
    total = 0
    picked_count = 0
    for pi in part_items:
        rows: list[HandcraftPickingVariant] = []
        for atom_id, needed_qty in expanded[pi.id]:
            atom_part = parts_by_id[atom_id]
            is_picked = (pi.id, atom_id) in picked_keys
            rows.append(HandcraftPickingVariant(
                part_id=atom_id,
                part_name=atom_part.name,
                part_image=atom_part.image,
                needed_qty=needed_qty,
                suggested_qty=None,  # filled in Task 4
                current_stock=stock_by_part.get(atom_id, 0.0),
                picked=is_picked,
            ))
            total += 1
            if is_picked:
                picked_count += 1
        parent_part = parts_by_id[pi.part_id]
        groups.append(HandcraftPickingGroup(
            part_item_id=pi.id,
            parent_part_id=pi.part_id,
            parent_part_name=parent_part.name,
            parent_part_image=parent_part.image,
            parent_is_composite=bool(parent_part.is_composite),
            parent_qty=float(pi.qty),
            parent_bom_qty=float(pi.bom_qty) if pi.bom_qty is not None else None,
            rows=rows,
        ))

    return HandcraftPickingResponse(
        handcraft_order_id=order.id,
        supplier_name=order.supplier_name,
        status=order.status,
        groups=groups,
        progress=HandcraftPickingProgress(total=total, picked=picked_count),
    )


def _expand_part_items(
    db: Session, part_items: list[HandcraftPartItem]
) -> dict[int, list[tuple[str, float]]]:
    """For each HandcraftPartItem, return a list of (atom_part_id, needed_qty)
    tuples. Atomic part_items return a single tuple; composite items expand
    via BOM. Multiple paths arriving at the same atom are summed."""
    if not part_items:
        return {}

    parent_part_ids = list({pi.part_id for pi in part_items})
    parent_parts = db.query(Part).filter(Part.id.in_(parent_part_ids)).all()
    is_composite = {p.id: bool(p.is_composite) for p in parent_parts}

    out: dict[int, list[tuple[str, float]]] = {}
    for pi in part_items:
        if is_composite.get(pi.part_id, False):
            # Composite — leave to Task 3.
            out[pi.id] = []
        else:
            out[pi.id] = [(pi.part_id, float(pi.qty))]
    return out


def _load_parts(db: Session, part_ids: list[str]) -> dict[str, Part]:
    if not part_ids:
        return {}
    rows = db.query(Part).filter(Part.id.in_(set(part_ids))).all()
    return {p.id: p for p in rows}


def _load_stock(db: Session, part_ids: list[str]) -> dict[str, float]:
    if not part_ids:
        return {}
    rows = (
        db.query(InventoryLog.item_id,
                 func.coalesce(func.sum(InventoryLog.change_qty), 0))
        .filter(InventoryLog.item_type == "part",
                InventoryLog.item_id.in_(part_ids))
        .group_by(InventoryLog.item_id)
        .all()
    )
    return {pid: float(q) for pid, q in rows}


def _load_picked_keys(
    db: Session, handcraft_order_id: str
) -> set[tuple[int, str]]:
    rows = (
        db.query(HandcraftPickingRecord)
        .filter(HandcraftPickingRecord.handcraft_order_id == handcraft_order_id)
        .all()
    )
    return {(r.handcraft_part_item_id, r.part_id) for r in rows}
```

- [ ] **Step 2.4: 添加 GET 路由（最小，让测试能跑）**

修改 `api/handcraft.py`：

在文件末尾追加：

```python
# --- Picking simulation (配货模拟) ---

from schemas.handcraft import (
    HandcraftPickingMarkRequest,
    HandcraftPickingResponse,
)
from services.handcraft_picking import get_handcraft_picking_simulation


@router.get("/{order_id}/picking", response_model=HandcraftPickingResponse)
def api_get_handcraft_picking(order_id: str, db: Session = Depends(get_db)):
    """Aggregate handcraft order parts into a picking-oriented grouped structure."""
    with service_errors():
        return get_handcraft_picking_simulation(db, order_id)
```

注：如果 import 列表风格里其他 import 都在文件顶部，可以把这两行 import 上移到现有 schemas/services import 块，保持风格一致。如果就近 import 是项目的惯例（看现有代码就近 import 出现过），保持上述形式。

- [ ] **Step 2.5: 运行测试，确认 4 个测试都通过**

Run:
```bash
pytest tests/test_api_handcraft_picking.py -v --tb=short
```

Expected: 4 个测试全部 PASS。

- [ ] **Step 2.6: Commit**

```bash
git add services/handcraft_picking.py api/handcraft.py tests/test_api_handcraft_picking.py
git commit -m "feat(handcraft): get_handcraft_picking_simulation for atomic part items"
```

---

## Task 3: 复合件展开

**Files:**
- Modify: `services/handcraft_picking.py:_expand_part_items`
- Modify: `tests/test_api_handcraft_picking.py`（追加测试）

- [ ] **Step 3.1: 写复合件展开的失败测试**

在 `tests/test_api_handcraft_picking.py` 末尾追加：

```python
def _setup_composite(db):
    """1 composite part C with two atom children A(qty=2) and B(qty=3),
    1 handcraft order with 1 part_item of C (qty=5)."""
    db.add(Part(id="PJ-X-00001", name="珠子A", category="吊坠", size_tier="small"))
    db.add(Part(id="PJ-X-00002", name="珠子B", category="吊坠", size_tier="medium"))
    db.add(Part(id="PJ-X-00003", name="组合件C", category="吊坠",
                size_tier="small", is_composite=True))
    db.flush()
    db.add(PartBom(id="PB-1", parent_part_id="PJ-X-00003",
                   child_part_id="PJ-X-00001", qty_per_unit=Decimal("2")))
    db.add(PartBom(id="PB-2", parent_part_id="PJ-X-00003",
                   child_part_id="PJ-X-00002", qty_per_unit=Decimal("3")))
    db.flush()
    _add_inventory(db, "PJ-X-00001", 50)
    _add_inventory(db, "PJ-X-00002", 30)
    db.add(HandcraftOrder(id="HC-COMP", supplier_name="商家", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-COMP",
        part_id="PJ-X-00003",
        qty=Decimal("5"),
        bom_qty=Decimal("5"),
    ))
    db.flush()


def test_get_picking_composite_expands_to_atoms(client, db):
    _setup_composite(db)
    resp = client.get("/api/handcraft/HC-COMP/picking")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["groups"]) == 1
    g = body["groups"][0]
    assert g["parent_is_composite"] is True
    assert g["parent_part_id"] == "PJ-X-00003"
    rows = sorted(g["rows"], key=lambda r: r["part_id"])
    assert len(rows) == 2
    assert rows[0]["part_id"] == "PJ-X-00001"
    assert rows[0]["needed_qty"] == 10.0  # 5 × 2
    assert rows[1]["part_id"] == "PJ-X-00002"
    assert rows[1]["needed_qty"] == 15.0  # 5 × 3
    assert body["progress"] == {"total": 2, "picked": 0}


def test_get_picking_mixed_atomic_and_composite(client, db):
    """Two part_items: one composite, one atomic referencing the same atom.
    Each part_item gets its own group (rule A: 每行独立)."""
    _setup_composite(db)
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-COMP",
        part_id="PJ-X-00001",
        qty=Decimal("8"),
        bom_qty=Decimal("7.5"),
    ))
    db.flush()
    body = client.get("/api/handcraft/HC-COMP/picking").json()
    assert len(body["groups"]) == 2
    # Group 1: composite — 2 atom rows
    # Group 2: atomic PJ-X-00001 — 1 row, qty=8
    atomic_groups = [g for g in body["groups"] if not g["parent_is_composite"]]
    assert len(atomic_groups) == 1
    assert atomic_groups[0]["rows"][0]["part_id"] == "PJ-X-00001"
    assert atomic_groups[0]["rows"][0]["needed_qty"] == 8.0


def test_get_picking_composite_multipath_sums(db, client):
    """If composite C contains atom A twice via different sub-children, the
    expansion sums those contributions into one row."""
    db.add(Part(id="PJ-X-00001", name="A", category="吊坠", size_tier="small"))
    db.add(Part(id="PJ-X-MID1", name="组合件D", category="吊坠",
                size_tier="small", is_composite=True))
    db.add(Part(id="PJ-X-MID2", name="组合件E", category="吊坠",
                size_tier="small", is_composite=True))
    db.add(Part(id="PJ-X-ROOT", name="组合件 F", category="吊坠",
                size_tier="small", is_composite=True))
    db.flush()
    # F → D (×2), F → E (×1)
    db.add(PartBom(id="PB-1", parent_part_id="PJ-X-ROOT",
                   child_part_id="PJ-X-MID1", qty_per_unit=Decimal("2")))
    db.add(PartBom(id="PB-2", parent_part_id="PJ-X-ROOT",
                   child_part_id="PJ-X-MID2", qty_per_unit=Decimal("1")))
    # D → A (×3), E → A (×4)  → expanding F: A = 2×3 + 1×4 = 10 per unit
    db.add(PartBom(id="PB-3", parent_part_id="PJ-X-MID1",
                   child_part_id="PJ-X-00001", qty_per_unit=Decimal("3")))
    db.add(PartBom(id="PB-4", parent_part_id="PJ-X-MID2",
                   child_part_id="PJ-X-00001", qty_per_unit=Decimal("4")))
    db.flush()
    db.add(HandcraftOrder(id="HC-MP", supplier_name="商家", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-MP",
        part_id="PJ-X-ROOT",
        qty=Decimal("5"),
        bom_qty=Decimal("5"),
    ))
    db.flush()
    body = client.get("/api/handcraft/HC-MP/picking").json()
    assert len(body["groups"]) == 1
    g = body["groups"][0]
    assert len(g["rows"]) == 1
    assert g["rows"][0]["part_id"] == "PJ-X-00001"
    assert g["rows"][0]["needed_qty"] == 50.0  # 5 × (2×3 + 1×4) = 50
```

- [ ] **Step 3.2: 运行测试，确认 3 个新测试失败**

Run:
```bash
pytest tests/test_api_handcraft_picking.py::test_get_picking_composite_expands_to_atoms tests/test_api_handcraft_picking.py::test_get_picking_mixed_atomic_and_composite tests/test_api_handcraft_picking.py::test_get_picking_composite_multipath_sums -v
```

Expected: 3 个新测试 FAIL（rows 数为 0，因为 `_expand_part_items` 复合件分支返回 `[]`）。

- [ ] **Step 3.3: 实现复合件展开（复用 `_expand_to_atoms`）**

修改 `services/handcraft_picking.py` 的 `_expand_part_items`：

```python
def _expand_part_items(
    db: Session, part_items: list[HandcraftPartItem]
) -> dict[int, list[tuple[str, float]]]:
    """For each HandcraftPartItem, return a list of (atom_part_id, needed_qty)
    tuples. Atomic part_items return a single tuple; composite items expand
    via BOM. Multiple paths arriving at the same atom are summed."""
    from services.picking import _expand_to_atoms

    if not part_items:
        return {}

    parent_part_ids = list({pi.part_id for pi in part_items})
    parent_parts = db.query(Part).filter(Part.id.in_(parent_part_ids)).all()
    is_composite = {p.id: bool(p.is_composite) for p in parent_parts}

    out: dict[int, list[tuple[str, float]]] = {}
    for pi in part_items:
        if is_composite.get(pi.part_id, False):
            # _expand_to_atoms expects a multiplier (composite count). For
            # handcraft, the part_item.qty IS the count of composites to send.
            atoms = _expand_to_atoms(db, pi.part_id, Decimal(str(pi.qty)))
            # atoms is a list of (atom_id, effective_qty) where effective_qty
            # already equals composite_count × child_ratio_in_BOM. Sum
            # contributions per atom_id (multipath).
            agg: dict[str, float] = defaultdict(float)
            for atom_id, atom_qty in atoms:
                agg[atom_id] += atom_qty
            out[pi.id] = [(aid, round(q, 4)) for aid, q in agg.items()]
        else:
            out[pi.id] = [(pi.part_id, float(pi.qty))]
    return out
```

注：`_expand_to_atoms(db, composite_part_id, multiplier)` 已经接受一个 `multiplier`（Decimal）作为根乘数，返回 `[(atom_id, effective_qty_per_unit)]`。在订单端调用时 `multiplier = b.qty_per_unit`（每件饰品需要多少组合件），然后再乘 `oi.quantity`。在我们这里 `multiplier = pi.qty`（直接是要发出的组合件总数），所以返回值就是每个原子件的总需求。

- [ ] **Step 3.4: 运行所有 handcraft picking 测试，全部通过**

Run:
```bash
pytest tests/test_api_handcraft_picking.py -v --tb=short
```

Expected: 全部 PASS（含 Task 2 的 4 个 + Task 3 的 3 个）。

- [ ] **Step 3.5: Commit**

```bash
git add services/handcraft_picking.py tests/test_api_handcraft_picking.py
git commit -m "feat(handcraft): expand composite parts to atoms in picking simulation"
```

---

## Task 4: `suggested_qty` 字段（按原子件 size_tier）

**Files:**
- Modify: `services/handcraft_picking.py`
- Modify: `tests/test_api_handcraft_picking.py`（追加）

- [ ] **Step 4.1: 写 suggested_qty 失败测试**

追加到 `tests/test_api_handcraft_picking.py`：

```python
def test_suggested_qty_atomic_small(client, db):
    """small tier: max(50, theo*2%); suggested = ceil(theo) + ceil(buffer).
    theo=8, ratio_calc=0.16, floor=50 wins. suggested = 8 + 50 = 58."""
    _setup_atomic(db)
    body = client.get("/api/handcraft/HC-TEST-1/picking").json()
    row = body["groups"][0]["rows"][0]
    assert row["suggested_qty"] == 58


def test_suggested_qty_atomic_medium(client, db):
    """medium tier: max(15, theo*1%); suggested = ceil(theo) + ceil(buffer).
    theo=2000, ratio_calc=20.0, ratio wins. suggested = 2000 + 20 = 2020."""
    db.add(Part(id="PJ-X-MED", name="珠子M", category="吊坠", size_tier="medium"))
    db.flush()
    db.add(HandcraftOrder(id="HC-M", supplier_name="商家", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-M",
        part_id="PJ-X-MED",
        qty=Decimal("1500"),
        bom_qty=Decimal("2000"),
    ))
    db.flush()
    body = client.get("/api/handcraft/HC-M/picking").json()
    row = body["groups"][0]["rows"][0]
    assert row["suggested_qty"] == 2020


def test_suggested_qty_none_when_bom_qty_missing(client, db):
    """If part_item.bom_qty is None or 0, suggested_qty is None."""
    _add_atomic_part(db, "PJ-X-NA", "无理论", "small")
    db.add(HandcraftOrder(id="HC-NA", supplier_name="商家", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-NA",
        part_id="PJ-X-NA",
        qty=Decimal("5"),
        bom_qty=None,
    ))
    db.flush()
    body = client.get("/api/handcraft/HC-NA/picking").json()
    assert body["groups"][0]["rows"][0]["suggested_qty"] is None


def test_suggested_qty_composite_uses_atom_tier(client, db):
    """Composite parent has bom_qty=5; expansion gives atom A theoretical
    = 5×2 = 10. A is small-tier → max(50, 10*2%) = 50 → suggested = 10 + 50 = 60.
    Atom B theoretical = 5×3 = 15, medium-tier → max(15, 15*1%) = 15 → 15 + 15 = 30."""
    _setup_composite(db)
    body = client.get("/api/handcraft/HC-COMP/picking").json()
    rows = sorted(body["groups"][0]["rows"], key=lambda r: r["part_id"])
    assert rows[0]["part_id"] == "PJ-X-00001"
    assert rows[0]["suggested_qty"] == 60
    assert rows[1]["part_id"] == "PJ-X-00002"
    assert rows[1]["suggested_qty"] == 30
```

- [ ] **Step 4.2: 运行，确认 4 个测试 FAIL（suggested_qty 全为 None）**

Run:
```bash
pytest tests/test_api_handcraft_picking.py -k suggested -v
```

Expected: 4 个新测试 FAIL（前 3 个 assert 60/2020/None 但实际为 None；第 4 个 assert 60/30 但实际为 None）。

- [ ] **Step 4.3: 实现 suggested_qty 计算**

修改 `services/handcraft_picking.py`，在文件中加入 helper 和集成：

```python
# --- Suggested qty rule (mirror of frontend HandcraftDetail.computeSuggestedQty) ---

_BUFFER_RULES: dict[str, dict[str, float]] = {
    "small":  {"ratio": 0.02, "floor": 50},
    "medium": {"ratio": 0.01, "floor": 15},
}


def _compute_suggested_qty(theoretical: Optional[float], size_tier: Optional[str]) -> Optional[int]:
    """Apply: suggested = ceil(theoretical) + ceil(max(floor, theoretical * ratio)).
    Returns None when theoretical is missing or non-positive (no suggestion).
    Unknown size_tier falls back to 'small' (matches the frontend default)."""
    if theoretical is None or theoretical <= 0:
        return None
    rule = _BUFFER_RULES.get(size_tier or "small", _BUFFER_RULES["small"])
    # Round to 4 decimals (matches DB Numeric(10,4)) before ceil — same as frontend.
    t = round(theoretical, 4)
    buffer = math.ceil(max(rule["floor"], t * rule["ratio"]))
    return math.ceil(t) + buffer
```

然后修改 `get_handcraft_picking_simulation`，把每个 row 的 `suggested_qty` 真实计算出来。需要"每行的理论值"：

- 原子件行：`theoretical = pi.bom_qty`（如有）
- 复合件展开行：`theoretical = (pi.bom_qty / pi.qty) × atom_needed_qty`，但这复杂；更直接是：在展开阶段就记录 atom 的"per-composite-unit"用量，然后乘以 `pi.bom_qty`。

为了不让 `_expand_part_items` 返回值膨胀，改成展开时返回 `(atom_id, needed_qty, per_composite_unit)`：

修改 `_expand_part_items`：

```python
def _expand_part_items(
    db: Session, part_items: list[HandcraftPartItem]
) -> dict[int, list[tuple[str, float, Optional[float]]]]:
    """For each HandcraftPartItem, return a list of
    (atom_part_id, needed_qty, atom_ratio_per_composite_unit) tuples.

    - Atomic part_items: (part_id, qty, 1.0). atom_ratio=1.0 means
      theoretical_for_atom = parent.bom_qty × 1.0 = parent.bom_qty.
    - Composite items: each expanded atom carries its BOM ratio
      (atom_qty_per_composite_unit). theoretical_for_atom = parent.bom_qty × ratio.
    """
    from services.picking import _expand_to_atoms

    if not part_items:
        return {}

    parent_part_ids = list({pi.part_id for pi in part_items})
    parent_parts = db.query(Part).filter(Part.id.in_(parent_part_ids)).all()
    is_composite = {p.id: bool(p.is_composite) for p in parent_parts}

    out: dict[int, list[tuple[str, float, Optional[float]]]] = {}
    for pi in part_items:
        if is_composite.get(pi.part_id, False):
            # Re-call _expand_to_atoms with multiplier=1.0 to get per-unit ratios,
            # then scale by pi.qty for needed_qty. Two-pass keeps the math clear.
            atoms_per_unit = _expand_to_atoms(db, pi.part_id, Decimal("1.0"))
            agg_ratio: dict[str, float] = defaultdict(float)
            for atom_id, ratio in atoms_per_unit:
                agg_ratio[atom_id] += ratio
            qty = float(pi.qty)
            out[pi.id] = [
                (aid, round(r * qty, 4), round(r, 4))
                for aid, r in agg_ratio.items()
            ]
        else:
            out[pi.id] = [(pi.part_id, float(pi.qty), 1.0)]
    return out
```

然后更新 `get_handcraft_picking_simulation` 内的 row 组装循环：

```python
        for atom_id, needed_qty, atom_ratio in expanded[pi.id]:
            atom_part = parts_by_id[atom_id]
            is_picked = (pi.id, atom_id) in picked_keys
            theoretical = (
                float(pi.bom_qty) * atom_ratio
                if pi.bom_qty is not None and atom_ratio is not None
                else None
            )
            suggested = _compute_suggested_qty(theoretical, atom_part.size_tier)
            rows.append(HandcraftPickingVariant(
                part_id=atom_id,
                part_name=atom_part.name,
                part_image=atom_part.image,
                needed_qty=needed_qty,
                suggested_qty=suggested,
                current_stock=stock_by_part.get(atom_id, 0.0),
                picked=is_picked,
            ))
            total += 1
            if is_picked:
                picked_count += 1
```

- [ ] **Step 4.4: 运行所有 handcraft picking 测试**

Run:
```bash
pytest tests/test_api_handcraft_picking.py -v --tb=short
```

Expected: 全部 PASS。

- [ ] **Step 4.5: Commit**

```bash
git add services/handcraft_picking.py tests/test_api_handcraft_picking.py
git commit -m "feat(handcraft): compute suggested_qty per atom using size_tier rules"
```

---

## Task 5: `mark_picked` / `unmark_picked` + 状态门控

**Files:**
- Modify: `services/handcraft_picking.py`
- Modify: `api/handcraft.py`
- Modify: `tests/test_api_handcraft_picking.py`

- [ ] **Step 5.1: 写 mark/unmark 失败测试**

追加到 `tests/test_api_handcraft_picking.py`：

```python
def test_mark_picked_persists_and_shows_in_get(client, db):
    _setup_atomic(db)
    body_before = client.get("/api/handcraft/HC-TEST-1/picking").json()
    pi_id = body_before["groups"][0]["part_item_id"]

    resp = client.post(
        "/api/handcraft/HC-TEST-1/picking/mark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
    )
    assert resp.status_code == 200
    assert resp.json()["picked"] is True

    body_after = client.get("/api/handcraft/HC-TEST-1/picking").json()
    assert body_after["groups"][0]["rows"][0]["picked"] is True
    assert body_after["progress"] == {"total": 1, "picked": 1}


def test_mark_idempotent(client, db):
    _setup_atomic(db)
    pi_id = client.get("/api/handcraft/HC-TEST-1/picking").json()["groups"][0]["part_item_id"]
    for _ in range(3):
        r = client.post(
            "/api/handcraft/HC-TEST-1/picking/mark",
            json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
        )
        assert r.status_code == 200
    count = (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_order_id="HC-TEST-1").count()
    )
    assert count == 1


def test_mark_invalid_part_id_rejected(client, db):
    _setup_atomic(db)
    pi_id = client.get("/api/handcraft/HC-TEST-1/picking").json()["groups"][0]["part_item_id"]
    resp = client.post(
        "/api/handcraft/HC-TEST-1/picking/mark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-NOTREAL"},
    )
    assert resp.status_code == 400
    assert "配货范围" in resp.json()["detail"]


def test_mark_blocked_when_status_not_pending(client, db):
    _setup_atomic(db)
    db.query(HandcraftOrder).filter_by(id="HC-TEST-1").update({"status": "processing"})
    db.flush()
    pi_id = (
        db.query(HandcraftPartItem)
        .filter_by(handcraft_order_id="HC-TEST-1").first().id
    )
    resp = client.post(
        "/api/handcraft/HC-TEST-1/picking/mark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
    )
    assert resp.status_code == 400
    assert "只读" in resp.json()["detail"]


def test_unmark_removes_record(client, db):
    _setup_atomic(db)
    pi_id = client.get("/api/handcraft/HC-TEST-1/picking").json()["groups"][0]["part_item_id"]
    client.post(
        "/api/handcraft/HC-TEST-1/picking/mark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
    )
    resp = client.post(
        "/api/handcraft/HC-TEST-1/picking/unmark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
    )
    assert resp.status_code == 200
    assert resp.json()["picked"] is False
    assert (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_order_id="HC-TEST-1").count() == 0
    )


def test_unmark_idempotent_for_nonexistent(client, db):
    _setup_atomic(db)
    pi_id = client.get("/api/handcraft/HC-TEST-1/picking").json()["groups"][0]["part_item_id"]
    resp = client.post(
        "/api/handcraft/HC-TEST-1/picking/unmark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
    )
    assert resp.status_code == 200
    assert resp.json()["picked"] is False
```

- [ ] **Step 5.2: 运行，确认全部 FAIL（路由/服务函数不存在）**

Run:
```bash
pytest tests/test_api_handcraft_picking.py -k "mark" -v --tb=short
```

Expected: 6 个新测试 FAIL，主要因为 `/picking/mark` 路由 404。

- [ ] **Step 5.3: 在 `services/handcraft_picking.py` 末尾追加 mark/unmark/reset**

```python
# --- State mutations ---


@dataclass
class HandcraftPickingMarkResult:
    picked: bool
    picked_at: Optional[datetime] = None


def _check_writable(order: HandcraftOrder) -> None:
    if order.status != "pending":
        raise ValueError("手工单已发出，配货模拟为只读")


def _validate_pair_in_order(
    db: Session, handcraft_order_id: str, part_item_id: int, part_id: str
) -> HandcraftOrder:
    """Verify the (part_item_id, part_id) pair is part of this handcraft order's
    picking aggregation. Returns the order for caller to use. Does NOT check
    writable status — that's a separate gate."""
    order = (
        db.query(HandcraftOrder)
        .filter_by(id=handcraft_order_id)
        .one_or_none()
    )
    if order is None:
        raise ValueError(f"手工单 {handcraft_order_id} 不存在")

    part_item = (
        db.query(HandcraftPartItem)
        .filter_by(id=part_item_id, handcraft_order_id=handcraft_order_id)
        .one_or_none()
    )
    if part_item is None:
        raise ValueError("该配件/变体不在此手工单配货范围内")

    expanded = _expand_part_items(db, [part_item])
    valid_atoms = {atom_id for atom_id, _, _ in expanded[part_item.id]}
    if part_id not in valid_atoms:
        raise ValueError("该配件/变体不在此手工单配货范围内")

    return order


def mark_picked(
    db: Session, handcraft_order_id: str, part_item_id: int, part_id: str
) -> HandcraftPickingMarkResult:
    """Mark a (part_item, atom) pair as picked. Idempotent."""
    order = _validate_pair_in_order(db, handcraft_order_id, part_item_id, part_id)
    _check_writable(order)

    existing = (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_part_item_id=part_item_id, part_id=part_id)
        .one_or_none()
    )
    if existing is not None:
        return HandcraftPickingMarkResult(picked=True, picked_at=existing.picked_at)

    rec = HandcraftPickingRecord(
        handcraft_order_id=handcraft_order_id,
        handcraft_part_item_id=part_item_id,
        part_id=part_id,
    )
    db.add(rec)
    db.flush()
    return HandcraftPickingMarkResult(picked=True, picked_at=rec.picked_at)


def unmark_picked(
    db: Session, handcraft_order_id: str, part_item_id: int, part_id: str
) -> HandcraftPickingMarkResult:
    """Unmark a (part_item, atom) pair. Idempotent — silent if no record exists.
    Validates that the order exists and is writable, but does NOT validate that
    the pair is still in the aggregation (allows cleanup of stale records)."""
    order = (
        db.query(HandcraftOrder)
        .filter_by(id=handcraft_order_id)
        .one_or_none()
    )
    if order is None:
        raise ValueError(f"手工单 {handcraft_order_id} 不存在")
    _check_writable(order)

    (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_part_item_id=part_item_id, part_id=part_id)
        .delete(synchronize_session=False)
    )
    db.flush()
    return HandcraftPickingMarkResult(picked=False)


def reset_picking(db: Session, handcraft_order_id: str) -> int:
    """Delete all picking records for the order. Returns delete count.
    Raises ValueError if order does not exist or is not writable."""
    order = (
        db.query(HandcraftOrder)
        .filter_by(id=handcraft_order_id)
        .one_or_none()
    )
    if order is None:
        raise ValueError(f"手工单 {handcraft_order_id} 不存在")
    _check_writable(order)

    deleted = (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_order_id=handcraft_order_id)
        .delete(synchronize_session=False)
    )
    db.flush()
    return deleted
```

- [ ] **Step 5.4: 添加路由到 `api/handcraft.py`**

在 `api/handcraft.py` 已添加的 picking 区块继续追加（与 GET 路由放一起）：

```python
from services.handcraft_picking import (
    get_handcraft_picking_simulation,
    mark_picked as handcraft_mark_picked,
    unmark_picked as handcraft_unmark_picked,
    reset_picking as handcraft_reset_picking,
)


@router.post("/{order_id}/picking/mark")
def api_handcraft_picking_mark(
    order_id: str,
    body: HandcraftPickingMarkRequest,
    db: Session = Depends(get_db),
):
    """Mark a (part_item, atom) pair as picked. Idempotent. Pending only."""
    with service_errors():
        result = handcraft_mark_picked(db, order_id, body.part_item_id, body.part_id)
    return {"picked": result.picked, "picked_at": result.picked_at}


@router.post("/{order_id}/picking/unmark")
def api_handcraft_picking_unmark(
    order_id: str,
    body: HandcraftPickingMarkRequest,
    db: Session = Depends(get_db),
):
    """Unmark a (part_item, atom) pair. Idempotent. Pending only."""
    with service_errors():
        result = handcraft_unmark_picked(db, order_id, body.part_item_id, body.part_id)
    return {"picked": result.picked}


@router.delete("/{order_id}/picking/reset")
def api_handcraft_picking_reset(order_id: str, db: Session = Depends(get_db)):
    """Clear all picking records for this handcraft order. Pending only."""
    with service_errors():
        deleted = handcraft_reset_picking(db, order_id)
    return {"deleted": deleted}
```

- [ ] **Step 5.5: 写 reset 测试**

追加到 `tests/test_api_handcraft_picking.py`：

```python
def test_reset_deletes_all_records(client, db):
    _setup_composite(db)
    pi_id = client.get("/api/handcraft/HC-COMP/picking").json()["groups"][0]["part_item_id"]
    client.post(
        "/api/handcraft/HC-COMP/picking/mark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
    )
    client.post(
        "/api/handcraft/HC-COMP/picking/mark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00002"},
    )
    resp = client.delete("/api/handcraft/HC-COMP/picking/reset")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2
    assert (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_order_id="HC-COMP").count() == 0
    )


def test_reset_blocked_when_not_pending(client, db):
    _setup_atomic(db)
    db.query(HandcraftOrder).filter_by(id="HC-TEST-1").update({"status": "completed"})
    db.flush()
    resp = client.delete("/api/handcraft/HC-TEST-1/picking/reset")
    assert resp.status_code == 400
    assert "只读" in resp.json()["detail"]
```

- [ ] **Step 5.6: 跑所有测试**

Run:
```bash
pytest tests/test_api_handcraft_picking.py -v --tb=short
```

Expected: 全部 PASS。

- [ ] **Step 5.7: Commit**

```bash
git add services/handcraft_picking.py api/handcraft.py tests/test_api_handcraft_picking.py
git commit -m "feat(handcraft): mark/unmark/reset picking with status gating"
```

---

## Task 6: 删除 `HandcraftPartItem` 时清理孤儿 picking 记录

**Files:**
- Modify: `services/handcraft.py:417-436`（`delete_handcraft_part`）
- Modify: `tests/test_api_handcraft_picking.py`

- [ ] **Step 6.1: 写孤儿清理测试**

追加到 `tests/test_api_handcraft_picking.py`：

```python
def test_delete_part_item_cleans_picking_records(client, db):
    """Deleting a HandcraftPartItem must purge its picking records to avoid
    FK violations and stale rows."""
    _setup_atomic(db)
    # Add a second part_item so delete_handcraft_part doesn't reject the last one.
    db.add(Part(id="PJ-X-EXTRA", name="额外", category="吊坠", size_tier="small"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-TEST-1",
        part_id="PJ-X-EXTRA",
        qty=Decimal("1"),
        bom_qty=Decimal("1"),
    ))
    db.flush()
    target_id = (
        db.query(HandcraftPartItem)
        .filter_by(handcraft_order_id="HC-TEST-1", part_id="PJ-X-00001")
        .one().id
    )

    # Mark the target as picked.
    client.post(
        "/api/handcraft/HC-TEST-1/picking/mark",
        json={"part_item_id": target_id, "part_id": "PJ-X-00001"},
    )
    assert (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_part_item_id=target_id).count() == 1
    )

    # Delete the part_item via the API.
    resp = client.delete(f"/api/handcraft/HC-TEST-1/parts/{target_id}")
    assert resp.status_code in (200, 204)

    # Picking record must be gone too.
    assert (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_part_item_id=target_id).count() == 0
    )
```

- [ ] **Step 6.2: 运行，确认 FAIL（FK 约束错误或残留记录）**

Run:
```bash
pytest tests/test_api_handcraft_picking.py::test_delete_part_item_cleans_picking_records -v
```

Expected: FAIL（外键约束抛 IntegrityError，DELETE 返回 500/400，或断言 count==0 失败）。

- [ ] **Step 6.3: 修改 `services/handcraft.py:delete_handcraft_part`**

在文件顶部 import 区追加：

```python
from models.handcraft_order import (
    HandcraftJewelryItem,
    HandcraftOrder,
    HandcraftPartItem,
    HandcraftPickingRecord,
)
```

（如果上述 import 已部分存在，只追加 `HandcraftPickingRecord` 即可。验证后调整。）

将 `delete_handcraft_part` 函数中 `db.delete(item)` 这行**前**插入：

```python
    # Clean up any picking records for this part item before deleting.
    db.query(HandcraftPickingRecord).filter_by(
        handcraft_part_item_id=item_id
    ).delete(synchronize_session=False)
    db.flush()
```

完整的 `delete_handcraft_part`（参考）：

```python
def delete_handcraft_part(db: Session, order_id: str, item_id: int) -> None:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    if order.status != "pending":
        raise ValueError(f"Cannot delete part: order {order_id} status is '{order.status}', must be 'pending'")
    item = db.query(HandcraftPartItem).filter(
        HandcraftPartItem.id == item_id,
        HandcraftPartItem.handcraft_order_id == order_id,
    ).first()
    if item is None:
        raise ValueError(f"HandcraftPartItem {item_id} not found in order {order_id}")
    remaining = db.query(HandcraftPartItem).filter(
        HandcraftPartItem.handcraft_order_id == order_id,
        HandcraftPartItem.id != item_id,
    ).count()
    if remaining == 0:
        raise ValueError(f"Cannot delete the last part from order {order_id}; an order must have at least one part item")
    # Clean up any picking records for this part item before deleting.
    db.query(HandcraftPickingRecord).filter_by(
        handcraft_part_item_id=item_id
    ).delete(synchronize_session=False)
    db.flush()
    db.delete(item)
    db.flush()
```

- [ ] **Step 6.4: 跑该测试 + 全套**

Run:
```bash
pytest tests/test_api_handcraft_picking.py -v --tb=short
pytest tests/ -k "handcraft" -v --tb=short
```

Expected: 全部 PASS（含手工单端原有测试，确认我们没破坏 `delete_handcraft_part` 其他逻辑）。

- [ ] **Step 6.5: Commit**

```bash
git add services/handcraft.py tests/test_api_handcraft_picking.py
git commit -m "fix(handcraft): clean up picking records when deleting part item"
```

---

## Task 7: PDF 导出（service + 路由）

**Files:**
- Create: `services/handcraft_picking_list_pdf.py`
- Modify: `api/handcraft.py`
- Modify: `tests/test_api_handcraft_picking.py`

- [ ] **Step 7.1: 写 PDF 导出 smoke 测试**

追加到 `tests/test_api_handcraft_picking.py`：

```python
def test_pdf_export_returns_pdf(client, db):
    _setup_atomic(db)
    resp = client.post("/api/handcraft/HC-TEST-1/picking/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert len(resp.content) > 500  # roughly non-empty


def test_pdf_export_empty_order_400(client, db):
    db.add(HandcraftOrder(id="HC-PDFEMPTY", supplier_name="商家", status="pending"))
    db.flush()
    resp = client.post("/api/handcraft/HC-PDFEMPTY/picking/pdf")
    assert resp.status_code == 400
    assert "无可导出" in resp.json()["detail"]
```

- [ ] **Step 7.2: 运行，确认 FAIL（路由不存在 → 404）**

Run:
```bash
pytest tests/test_api_handcraft_picking.py -k pdf -v
```

Expected: 2 个测试 FAIL。

- [ ] **Step 7.3: 创建 `services/handcraft_picking_list_pdf.py`**

参考 `services/picking_list_pdf.py` 的结构，但表格更简单（无 variant 子行，分组头展示 part_item 元信息）。

```python
"""Generate a printable picking list PDF for handcraft 配货模拟.

Layout: A4, 45×45pt images. Each handcraft_part_item is rendered as a
section: a header row showing the part_item's parent part + qty, followed
by one or more atom rows. By default, already-picked rows are filtered out.
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFont, stringWidth
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from services._pdf_helpers import prefetch_images, fit_image
from services.handcraft_picking import get_handcraft_picking_simulation
from time_utils import now_beijing

_PAGE_WIDTH, _PAGE_HEIGHT = A4
_MARGIN_X = 40
_MARGIN_TOP = 36
_MARGIN_BOTTOM = 30
_CONTENT_WIDTH = _PAGE_WIDTH - _MARGIN_X * 2  # 515pt
_IMAGE_SIZE = 45
_GROUP_HEADER_H = 22
_ROW_H = 50
_HEADER_ROW_H = 24
_FONT = "STSong-Light"

_FOOTER_FONT_SIZE = 8
_FOOTER_COLOR = colors.HexColor("#888888")
_FOOTER_RIGHT_TEXT = "Allen Shop · 饰品店管理系统"

# Column widths sum to 515pt:
# 配件编号(70) 配件(195) 需要(60) 建议(60) 库存(60) 完成(70)
_COL_W = [70, 195, 60, 60, 60, 70]
_HEADERS = ["配件编号", "配件", "需要", "建议", "库存", "完成"]


class _NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        self._saved_page_states.append(dict(self.__dict__))
        total = len(self._saved_page_states)
        for i, state in enumerate(self._saved_page_states, 1):
            self.__dict__.update(state)
            self._draw_page_footer(i, total)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_page_footer(self, page_num: int, total: int) -> None:
        self.saveState()
        self.setFont(_FONT, _FOOTER_FONT_SIZE)
        self.setFillColor(_FOOTER_COLOR)
        footer_y = _MARGIN_BOTTOM - 16
        left_text = f"第 {page_num} / {total} 页"
        self.drawString(_MARGIN_X, footer_y, left_text)
        right_tw = stringWidth(_FOOTER_RIGHT_TEXT, _FONT, _FOOTER_FONT_SIZE)
        self.drawString(_PAGE_WIDTH - _MARGIN_X - right_tw, footer_y, _FOOTER_RIGHT_TEXT)
        self.restoreState()


@lru_cache(maxsize=1)
def _register_fonts() -> bool:
    registerFont(UnicodeCIDFont(_FONT))
    return True


def _filter_groups(groups, include_picked: bool):
    if include_picked:
        return groups
    out = []
    for g in groups:
        rows = [r for r in g.rows if not r.picked]
        if rows:
            out.append(g.model_copy(update={"rows": rows}))
    return out


def _fmt_qty(v) -> str:
    """Trim trailing zeros for integers; keep up to 4 decimals otherwise."""
    if v is None:
        return "-"
    f = float(v)
    if f == int(f):
        return str(int(f))
    return f"{f:g}"


def build_handcraft_picking_list_pdf(
    db: Session,
    handcraft_order_id: str,
    include_picked: bool = False,
) -> tuple[bytes, str]:
    """Build the PDF. Returns (bytes, suggested_filename). Raises ValueError if
    nothing to export (empty order, or all rows picked & include_picked=False)."""
    _register_fonts()
    sim = get_handcraft_picking_simulation(db, handcraft_order_id)
    groups = _filter_groups(sim.groups, include_picked=include_picked)
    if not groups:
        raise ValueError("无可导出内容")

    # Pre-fetch atom images.
    image_urls = [r.part_image for g in groups for r in g.rows if r.part_image]
    image_cache = prefetch_images(image_urls)

    buf = BytesIO()
    c = _NumberedCanvas(buf, pagesize=A4)

    title = f"手工单配货清单 — {sim.handcraft_order_id}"
    subtitle = f"商家：{sim.supplier_name}    导出时间：{now_beijing().strftime('%Y-%m-%d %H:%M')}"

    y = _PAGE_HEIGHT - _MARGIN_TOP

    def _draw_title():
        nonlocal y
        c.setFont(_FONT, 14)
        c.setFillColor(colors.black)
        c.drawString(_MARGIN_X, y, title)
        y -= 18
        c.setFont(_FONT, 9)
        c.setFillColor(colors.HexColor("#666"))
        c.drawString(_MARGIN_X, y, subtitle)
        y -= 14

    def _draw_table_header():
        nonlocal y
        c.setFillColor(colors.HexColor("#fafbfc"))
        c.rect(_MARGIN_X, y - _HEADER_ROW_H, _CONTENT_WIDTH, _HEADER_ROW_H, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont(_FONT, 9)
        x = _MARGIN_X
        for i, label in enumerate(_HEADERS):
            tw = stringWidth(label, _FONT, 9)
            c.drawString(x + (_COL_W[i] - tw) / 2, y - _HEADER_ROW_H + 8, label)
            x += _COL_W[i]
        y -= _HEADER_ROW_H

    def _ensure_space(needed: float):
        nonlocal y
        if y - needed < _MARGIN_BOTTOM + 30:
            c.showPage()
            y = _PAGE_HEIGHT - _MARGIN_TOP
            _draw_title()
            _draw_table_header()

    _draw_title()
    _draw_table_header()

    for g in groups:
        # Group header
        _ensure_space(_GROUP_HEADER_H)
        c.setFillColor(colors.HexColor("#eef3fb"))
        c.rect(_MARGIN_X, y - _GROUP_HEADER_H, _CONTENT_WIDTH, _GROUP_HEADER_H, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont(_FONT, 9)
        composite_tag = " [组合]" if g.parent_is_composite else ""
        bom_tag = f"  理论 {_fmt_qty(g.parent_bom_qty)}" if g.parent_bom_qty else ""
        text = f"{g.parent_part_id}  {g.parent_part_name}{composite_tag}  × {_fmt_qty(g.parent_qty)}{bom_tag}"
        c.drawString(_MARGIN_X + 8, y - _GROUP_HEADER_H + 8, text)
        y -= _GROUP_HEADER_H

        # Rows
        for r in g.rows:
            _ensure_space(_ROW_H)
            c.setFillColor(colors.white)
            c.rect(_MARGIN_X, y - _ROW_H, _CONTENT_WIDTH, _ROW_H, fill=0, stroke=1)
            x = _MARGIN_X
            # 配件编号
            c.setFillColor(colors.black)
            c.setFont(_FONT, 9)
            c.drawString(x + 4, y - _ROW_H / 2 - 3, r.part_id)
            x += _COL_W[0]
            # 配件 (image + name)
            if r.part_image and r.part_image in image_cache:
                fit_image(c, image_cache[r.part_image],
                          x + 4, y - _ROW_H + 4, _IMAGE_SIZE, _IMAGE_SIZE)
            c.drawString(x + 4 + _IMAGE_SIZE + 6, y - _ROW_H / 2 - 3, r.part_name)
            x += _COL_W[1]
            # 需要
            c.drawString(x + 4, y - _ROW_H / 2 - 3, _fmt_qty(r.needed_qty))
            x += _COL_W[2]
            # 建议
            sug = "-" if r.suggested_qty is None else str(r.suggested_qty)
            c.setFillColor(colors.HexColor("#1890ff"))
            c.drawString(x + 4, y - _ROW_H / 2 - 3, sug)
            c.setFillColor(colors.black)
            x += _COL_W[3]
            # 库存
            stock_color = colors.HexColor("#d03050") if r.current_stock < r.needed_qty else colors.black
            c.setFillColor(stock_color)
            c.drawString(x + 4, y - _ROW_H / 2 - 3, _fmt_qty(r.current_stock))
            c.setFillColor(colors.black)
            x += _COL_W[4]
            # 完成 (empty checkbox; picked rows would be filtered already
            #        unless include_picked)
            box_y = y - _ROW_H / 2 - 6
            c.rect(x + (_COL_W[5] - 12) / 2, box_y, 12, 12, fill=0, stroke=1)
            if r.picked:
                c.line(x + (_COL_W[5] - 12) / 2, box_y,
                       x + (_COL_W[5] + 12) / 2, box_y + 12)
                c.line(x + (_COL_W[5] + 12) / 2, box_y,
                       x + (_COL_W[5] - 12) / 2, box_y + 12)
            y -= _ROW_H

    c.save()
    pdf_bytes = buf.getvalue()
    buf.close()
    filename = f"手工单配货清单-{handcraft_order_id}.pdf"
    return pdf_bytes, filename
```

- [ ] **Step 7.4: 添加 PDF 路由到 `api/handcraft.py`**

```python
from urllib.parse import quote  # already imported at top of file
from fastapi.responses import Response  # already imported

from services.handcraft_picking_list_pdf import build_handcraft_picking_list_pdf


@router.post("/{order_id}/picking/pdf")
def api_handcraft_picking_pdf(order_id: str, db: Session = Depends(get_db)):
    """Export the handcraft picking list PDF (unpicked rows only by default)."""
    with service_errors():
        file_bytes, filename = build_handcraft_picking_list_pdf(
            db, order_id, include_picked=False,
        )
    return Response(
        content=file_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="handcraft-picking-{order_id}.pdf"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )
```

注：检查 `api/handcraft.py` 顶部 `from urllib.parse import quote` 与 `from fastapi.responses import Response` 是否已 import；订单端 PDF 路由用了它们，handcraft 现有 PDF 路由也大概率用。如缺则补上。

- [ ] **Step 7.5: 跑 PDF 测试**

Run:
```bash
pytest tests/test_api_handcraft_picking.py -k pdf -v
```

Expected: PASS。

- [ ] **Step 7.6: 跑全套测试，确认无回归**

Run:
```bash
pytest tests/test_api_handcraft_picking.py tests/test_api_picking.py -v --tb=short
```

Expected: 全部 PASS。

- [ ] **Step 7.7: Commit**

```bash
git add services/handcraft_picking_list_pdf.py api/handcraft.py tests/test_api_handcraft_picking.py
git commit -m "feat(handcraft): export picking list as PDF"
```

---

## Task 8: 前端 API client 函数

**Files:**
- Modify: `frontend/src/api/handcraft.js`

- [ ] **Step 8.1: 在 `frontend/src/api/handcraft.js` 末尾追加 picking 相关 client 函数**

```js
// --- Picking simulation (配货模拟) ---
export const getHandcraftPicking = (id) => api.get(`/handcraft/${id}/picking`)

export const markHandcraftPicked = (id, partItemId, partId) =>
  api.post(`/handcraft/${id}/picking/mark`, {
    part_item_id: partItemId,
    part_id: partId,
  })

export const unmarkHandcraftPicked = (id, partItemId, partId) =>
  api.post(`/handcraft/${id}/picking/unmark`, {
    part_item_id: partItemId,
    part_id: partId,
  })

export const resetHandcraftPicking = (id) =>
  api.delete(`/handcraft/${id}/picking/reset`)

export const downloadHandcraftPickingPdf = (id) =>
  api.post(`/handcraft/${id}/picking/pdf`, {}, { responseType: 'blob' })
```

- [ ] **Step 8.2: Commit**

```bash
git add frontend/src/api/handcraft.js
git commit -m "feat(handcraft): frontend API client for picking simulation"
```

---

## Task 9: 前端模态组件

**Files:**
- Create: `frontend/src/components/picking/HandcraftPickingSimulationModal.vue`

- [ ] **Step 9.1: 创建模态组件**

写入 `frontend/src/components/picking/HandcraftPickingSimulationModal.vue`：

```vue
<script setup>
import { ref, computed, watch } from 'vue'
import {
  NModal, NButton, NCheckbox, NSwitch, NTag, NSpace, NPopconfirm,
  NSpin, NTooltip, useMessage,
} from 'naive-ui'
import {
  getHandcraftPicking,
  markHandcraftPicked,
  unmarkHandcraftPicked,
  resetHandcraftPicking,
  downloadHandcraftPickingPdf,
} from '@/api/handcraft'
import { useIsMobile } from '@/composables/useIsMobile'

const { isMobile } = useIsMobile()

const props = defineProps({
  show: { type: Boolean, required: true },
  orderId: { type: String, required: true },
  status: { type: String, required: true },  // pending / processing / completed
})
const emit = defineEmits(['update:show'])

const message = useMessage()
const loading = ref(false)
const data = ref(null)
const onlyUnpicked = ref(false)
const exporting = ref(false)

const readonly = computed(() => props.status !== 'pending')

const displayGroups = computed(() => {
  if (!data.value) return []
  if (!onlyUnpicked.value) return data.value.groups
  return data.value.groups
    .map((g) => ({ ...g, rows: g.rows.filter((r) => !r.picked) }))
    .filter((g) => g.rows.length > 0)
})

async function load() {
  loading.value = true
  try {
    const resp = await getHandcraftPicking(props.orderId)
    data.value = resp.data
  } catch (err) {
    message.error(err.response?.data?.detail || '加载配货数据失败')
    emit('update:show', false)
  } finally {
    loading.value = false
  }
}

watch(() => props.show, (v) => {
  if (v) {
    data.value = null
    onlyUnpicked.value = false
    load()
  }
})

async function toggleRow(group, row) {
  if (readonly.value) return
  const prev = row.picked
  row.picked = !prev
  data.value.progress.picked += row.picked ? 1 : -1
  try {
    const fn = row.picked ? markHandcraftPicked : unmarkHandcraftPicked
    await fn(props.orderId, group.part_item_id, row.part_id)
  } catch (err) {
    row.picked = prev
    data.value.progress.picked += prev ? 1 : -1
    message.error(err.response?.data?.detail || '操作失败')
  }
}

async function doReset() {
  try {
    await resetHandcraftPicking(props.orderId)
    await load()
    message.success('已重置所有勾选')
  } catch (err) {
    message.error(err.response?.data?.detail || '重置失败')
  }
}

async function doExport() {
  exporting.value = true
  try {
    const resp = await downloadHandcraftPickingPdf(props.orderId)
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `手工单配货清单_${props.orderId}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    let detail = '导出失败'
    if (err.response?.data instanceof Blob) {
      try {
        const text = await err.response.data.text()
        const parsed = JSON.parse(text)
        detail = parsed.detail || detail
      } catch { /* fallthrough */ }
    } else {
      detail = err.response?.data?.detail || detail
    }
    message.error(detail)
  } finally {
    exporting.value = false
  }
}

function fmtQty(v) {
  if (v == null) return '-'
  const f = Number(v)
  if (Number.isNaN(f)) return String(v)
  const r = parseFloat(f.toPrecision(12))
  if (r === Math.trunc(r)) return String(Math.trunc(r))
  return r.toString()
}

const SUGGESTED_TOOLTIP_RULES = {
  small:  { ratio: 0.02, floor: 50, label: '小件' },
  medium: { ratio: 0.01, floor: 15, label: '中件' },
}

function suggestedTooltip(row, group) {
  if (row.suggested_qty == null) return ''
  // tier is not in the response; fall back to small if absent
  const tier = row._tier || 'small'
  const rule = SUGGESTED_TOOLTIP_RULES[tier] || SUGGESTED_TOOLTIP_RULES.small
  // theoretical = parent.bom_qty × atom_ratio for composite, else part_item.bom_qty
  // Since we don't have ratio in response, just describe the rule.
  return `${rule.label}规则: max(${rule.floor}, 理论×${rule.ratio * 100}%) | 建议数量为 ceil(理论) + ceil(buffer)`
}
</script>

<template>
  <n-modal
    :show="show"
    @update:show="(v) => emit('update:show', v)"
    preset="card"
    :style="{ width: isMobile ? '95vw' : '960px', maxWidth: '95vw' }"
    :title="`配货模拟 · 手工单 ${orderId}`"
  >
    <n-spin :show="loading">
      <div v-if="data">
        <div class="header-row">
          <div>
            商家：<b>{{ data.supplier_name }}</b>
            <span class="progress">
              进度：{{ data.progress.picked }} / {{ data.progress.total }} 已完成
            </span>
            <n-tag v-if="readonly" size="small" type="warning" style="margin-left: 12px;">
              只读 ({{ data.status === 'processing' ? '处理中' : '已完成' }})
            </n-tag>
          </div>
          <n-space>
            <span>
              只看未完成
              <n-switch v-model:value="onlyUnpicked" size="small" />
            </span>
            <n-button
              v-if="!readonly"
              type="primary"
              :loading="exporting"
              @click="doExport"
            >
              导出 PDF
            </n-button>
            <n-popconfirm v-if="!readonly" @positive-click="doReset">
              <template #trigger>
                <n-button>重置勾选</n-button>
              </template>
              确认清空本手工单的所有勾选记录？
            </n-popconfirm>
          </n-space>
        </div>

        <div class="table-scroll">
          <table class="picking-table">
            <thead>
              <tr>
                <th>配件编号</th>
                <th>配件</th>
                <th>需要</th>
                <th>建议</th>
                <th>库存</th>
                <th>完成</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="g in displayGroups" :key="g.part_item_id">
                <tr class="group-header">
                  <td colspan="6">
                    <span class="group-id">{{ g.parent_part_id }}</span>
                    <span class="group-name">{{ g.parent_part_name }}</span>
                    <n-tag v-if="g.parent_is_composite" size="tiny" type="info" :bordered="false" style="margin-left: 6px;">
                      组合
                    </n-tag>
                    <span class="group-qty">× {{ fmtQty(g.parent_qty) }}</span>
                    <span v-if="g.parent_bom_qty != null" class="group-bom">
                      理论 {{ fmtQty(g.parent_bom_qty) }}
                    </span>
                  </td>
                </tr>
                <tr
                  v-for="r in g.rows"
                  :key="`${g.part_item_id}-${r.part_id}`"
                  :class="{ 'row-picked': r.picked }"
                >
                  <td>{{ r.part_id }}</td>
                  <td>
                    <div class="part-cell">
                      <img v-if="r.part_image" :src="r.part_image" class="part-img" />
                      <div v-else class="part-img placeholder" />
                      <div class="part-name">{{ r.part_name }}</div>
                    </div>
                  </td>
                  <td class="num">{{ fmtQty(r.needed_qty) }}</td>
                  <td class="num suggested">
                    <n-tooltip v-if="r.suggested_qty != null" trigger="hover">
                      <template #trigger>
                        <span>{{ r.suggested_qty }}</span>
                      </template>
                      {{ suggestedTooltip(r, g) }}
                    </n-tooltip>
                    <span v-else class="dim">-</span>
                  </td>
                  <td
                    class="num"
                    :class="{ 'stock-low': r.current_stock < r.needed_qty }"
                  >
                    {{ fmtQty(r.current_stock) }}
                  </td>
                  <td class="num">
                    <n-checkbox
                      :checked="r.picked"
                      :disabled="readonly"
                      @update:checked="toggleRow(g, r)"
                    />
                  </td>
                </tr>
              </template>
              <tr v-if="displayGroups.length === 0">
                <td colspan="6" class="empty">没有数据</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </n-spin>
  </n-modal>
</template>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.progress {
  margin-left: 20px;
  color: #4361ee;
  font-weight: 500;
}
.table-scroll {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.picking-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  min-width: 580px;
}
.picking-table th,
.picking-table td {
  border: 1px solid #eee;
  padding: 8px;
  vertical-align: middle;
}
.picking-table thead th {
  background: #fafbfc;
  font-weight: 600;
}
.picking-table .num {
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.picking-table .suggested {
  color: #1890ff;
  font-weight: 600;
}
.picking-table .stock-low {
  color: #d03050;
  font-weight: 600;
}
.picking-table .group-header td {
  background: #eef3fb;
  font-weight: 500;
  font-size: 13px;
}
.picking-table .group-header .group-id {
  color: #888;
  margin-right: 6px;
  font-variant-numeric: tabular-nums;
}
.picking-table .group-header .group-qty {
  margin-left: 8px;
  color: #4361ee;
}
.picking-table .group-header .group-bom {
  margin-left: 8px;
  color: #999;
  font-size: 12px;
}
.picking-table .row-picked td:not(.group-header td) {
  opacity: 0.5;
  text-decoration: line-through;
}
.part-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.part-img {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 4px;
  flex-shrink: 0;
}
.part-img.placeholder {
  background: #f0f0f0;
}
.part-name {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.dim {
  color: #bbb;
}
.empty {
  text-align: center;
  color: #999;
  padding: 24px !important;
}
</style>
```

- [ ] **Step 9.2: Commit**

```bash
git add frontend/src/components/picking/HandcraftPickingSimulationModal.vue
git commit -m "feat(handcraft): HandcraftPickingSimulationModal component"
```

---

## Task 10: 在 HandcraftDetail.vue 接入按钮和模态

**Files:**
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue`（多处）

- [ ] **Step 10.1: 找到 import 区，加上模态组件**

打开 `frontend/src/views/handcraft/HandcraftDetail.vue`，定位到 `<script setup>` 顶部 import 区，加入：

```js
import HandcraftPickingSimulationModal from '@/components/picking/HandcraftPickingSimulationModal.vue'
```

放在已有 `import` 行附近（具体行号取决于文件状态；与其他 component import 放一起）。

- [ ] **Step 10.2: 添加 ref 和 open 函数**

在 `<script setup>` 里（与其他 modal state 邻近），加入：

```js
const pickingModalShow = ref(false)
function openPickingSimulation() {
  pickingModalShow.value = true
}
```

- [ ] **Step 10.3: 在「配件明细」卡 header 添加按钮**

在 `HandcraftDetail.vue:195-225` 的 `n-card title="配件明细"` 块里，定位到 `template #header-extra` 内的 `<n-space size="small">`：

原有：

```vue
<n-space size="small">
  <n-button
    v-if="items.length > 0"
    size="small"
    :loading="cuttingStatsLoading"
    @click="openCuttingStatsModal"
  >
    裁剪统计
  </n-button>
  <n-button
    v-if="items.length > 0"
    size="small"
    @click="openBatchLinkModal"
  >
    批量关联订单
  </n-button>
  <n-button
    v-if="order?.status === 'pending'"
    type="primary"
    size="small"
    @click="openAddModal"
  >
    + 添加配件
  </n-button>
</n-space>
```

改为（在「裁剪统计」右、「批量关联订单」前插入）：

```vue
<n-space size="small">
  <n-button
    v-if="items.length > 0"
    size="small"
    :loading="cuttingStatsLoading"
    @click="openCuttingStatsModal"
  >
    裁剪统计
  </n-button>
  <n-button
    v-if="items.length > 0"
    size="small"
    :type="order?.status === 'pending' ? 'primary' : 'default'"
    @click="openPickingSimulation"
  >
    配货模拟
  </n-button>
  <n-button
    v-if="items.length > 0"
    size="small"
    @click="openBatchLinkModal"
  >
    批量关联订单
  </n-button>
  <n-button
    v-if="order?.status === 'pending'"
    type="primary"
    size="small"
    @click="openAddModal"
  >
    + 添加配件
  </n-button>
</n-space>
```

- [ ] **Step 10.4: 在 `</template>` 之前挂载模态组件**

定位到 `HandcraftDetail.vue` 模板的最末尾（`</template>` 闭标签之前）。该文件的现有模态都挂在 `<n-spin>` 之外、模板根 `<div>` 内。在最后一个现有 `<n-modal>` 后追加：

```vue
<HandcraftPickingSimulationModal
  v-model:show="pickingModalShow"
  :order-id="String(route.params.id)"
  :status="order?.status || 'pending'"
/>
```

- [ ] **Step 10.5: 启动前后端，手测**

启动后端：

```bash
python main.py
```

另一个终端启动前端：

```bash
cd frontend && npm run dev
```

打开浏览器，访问任意一个手工单详情页（路径形如 `/handcraft/HC-XXXX`）。

手测清单（**逐项验证**）：

- [ ] **pending 状态**：「配件明细」header 看到「配货模拟」按钮，主色（蓝色）
- [ ] 点击按钮，模态打开，显示分组结构
- [ ] 原子件 part_item 一组一行；复合件 part_item 一组多行带「组合」小标签
- [ ] 「需要」「建议」「库存」列数字正确；库存 < 需要时数字红色
- [ ] 勾选 checkbox：进度数字 +1；关闭模态再打开仍为已勾选状态
- [ ] 取消勾选：进度 -1
- [ ] 「只看未完成」switch：隐藏已勾选行，整组都勾完时整组隐藏
- [ ] 「重置勾选」按钮：弹确认 → 确认 → 全部清空
- [ ] 「导出 PDF」按钮：下载得到一个可打开的 PDF
- [ ] **processing/completed 状态**（可临时改库里 status 测）：
  - 按钮仍可见，颜色为默认（非 primary）
  - 模态可打开，header 有「只读」黄色 tag
  - checkbox `disabled`，无法勾选
  - 「导出 PDF」「重置勾选」按钮隐藏
  - 「只看未完成」switch 仍可用

如有问题，回到对应 Step 修复后重测。

- [ ] **Step 10.6: 跑后端测试一遍，确认前端改动没碰到后端**

Run:
```bash
pytest tests/test_api_handcraft_picking.py -v --tb=short
```

Expected: 全部 PASS。

- [ ] **Step 10.7: Commit**

```bash
git add frontend/src/views/handcraft/HandcraftDetail.vue
git commit -m "feat(handcraft): wire 配货模拟 button into HandcraftDetail"
```

---

## Task 11: 收尾 — 全套测试 + 文档更新

**Files:**
- 无新文件改动；只跑测试 + 整理 commit history

- [ ] **Step 11.1: 跑全套后端测试（确认无回归）**

Run:
```bash
pytest tests/ --tb=short -q
```

Expected: 全部 PASS。如果发现非 picking 测试失败，回头查根因。

- [ ] **Step 11.2: 前端构建检查（无编译错误）**

Run:
```bash
cd frontend && npm run build
```

Expected: 构建成功，dist 目录生成。

- [ ] **Step 11.3: 写一段简短的 PR 描述（用于 review/合并）**

不要新建 markdown 文件。在 commit log 里以最后一个 commit 描述清楚即可，或者写到 PR 描述里。范例 PR 描述：

```
手工单配货模拟（HandcraftPickingSimulation）

为手工单详情页加入与订单端对应的「配货模拟」功能。

- 后端：HandcraftPickingRecord 表 + services/handcraft_picking.py + 5 个路由
- 复合件递归展开为原子件（复用 services.picking._expand_to_atoms）
- 含「建议数量」按原子件 size_tier 计算
- 状态门控：pending 可写，processing/completed 只读
- PDF 导出（reportlab）
- 前端 HandcraftPickingSimulationModal 挂在 HandcraftDetail 配件明细卡 header

Spec: docs/superpowers/specs/2026-04-27-handcraft-picking-simulation-design.md
Plan: docs/superpowers/plans/2026-04-27-handcraft-picking-simulation.md
```

- [ ] **Step 11.4: 最终核对（可选 — 用 superpowers:verification-before-completion）**

如果你按 superpowers 工作流执行，调用 `verification-before-completion` 跑一次最终核验：

- 全套 pytest 通过
- 前端 npm run build 通过
- 至少手测过 pending 和 processing 各一次

---

## 测试矩阵速览

| 测试 | Task | 用途 |
|---|---|---|
| `test_get_picking_order_not_found` | 2 | 不存在手工单 → 400 |
| `test_get_picking_empty_order` | 2 | 无 part item → 空 groups |
| `test_get_picking_atomic_single_item` | 2 | 原子件基础场景 |
| `test_get_picking_composite_expands_to_atoms` | 3 | 复合件展开 |
| `test_get_picking_mixed_atomic_and_composite` | 3 | 多组分组独立 |
| `test_get_picking_composite_multipath_sums` | 3 | 多路径汇到同 atom 求和 |
| `test_suggested_qty_atomic_small` | 4 | small tier 规则 |
| `test_suggested_qty_atomic_medium` | 4 | medium tier 规则 |
| `test_suggested_qty_none_when_bom_qty_missing` | 4 | bom_qty=None |
| `test_suggested_qty_composite_uses_atom_tier` | 4 | 展开行用原子 tier |
| `test_mark_picked_persists_and_shows_in_get` | 5 | mark + 持久化 |
| `test_mark_idempotent` | 5 | 重复 mark 单行 |
| `test_mark_invalid_part_id_rejected` | 5 | 无效 atom 报 400 |
| `test_mark_blocked_when_status_not_pending` | 5 | 状态门控 |
| `test_unmark_removes_record` | 5 | unmark |
| `test_unmark_idempotent_for_nonexistent` | 5 | unmark 不存在 silent |
| `test_reset_deletes_all_records` | 5 | reset 全删 |
| `test_reset_blocked_when_not_pending` | 5 | reset 状态门控 |
| `test_delete_part_item_cleans_picking_records` | 6 | 孤儿清理 |
| `test_pdf_export_returns_pdf` | 7 | PDF smoke |
| `test_pdf_export_empty_order_400` | 7 | PDF 空内容 → 400 |

合计 21 个测试。前端无单元测试，依赖 Task 10.5 的手测清单。
