# 成本快照 + 饰品模板 — 后端实现方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现订单完成时的成本快照（含完整 BOM 明细）和饰品模板（快捷创建饰品 BOM）。

**Architecture:** 成本快照在订单状态变为"已完成"时自动生成，存储每个饰品的 BOM 配件成本明细到 `order_cost_snapshot` 和 `order_cost_snapshot_item` 表。饰品模板使用独立的 `jewelry_template` + `jewelry_template_item` 表，创建饰品时可从模板导入 BOM。Jewelry 模型新增 `handcraft_cost` 字段，Order 模型新增 `packaging_cost` 字段。

**Tech Stack:** FastAPI + SQLAlchemy + PostgreSQL + Pydantic V2

**参照文件：**
- `models/order.py` — 现有订单模型
- `models/jewelry.py` — 现有饰品模型
- `models/bom.py` — BOM 模型
- `models/part.py` — 配件模型（含 unit_cost, PartCostLog）
- `services/order.py` — 现有订单服务（含 `get_parts_summary`）
- `services/bom.py` — BOM 查询
- `services/part.py` — `update_part_cost`, `_recalc_unit_cost` 模式
- `services/cost_sync.py` — 成本同步模式

---

## 第一部分：成本快照

### 数据模型

**`Jewelry` 新增字段：**
```python
handcraft_cost = Column(Numeric(18, 7), nullable=True)
```

**`Order` 新增字段：**
```python
packaging_cost = Column(Numeric(18, 7), nullable=True)
```

**新表 `order_cost_snapshot`：**
```python
class OrderCostSnapshot(Base):
    __tablename__ = "order_cost_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("order.id"), nullable=False)
    total_cost = Column(Numeric(18, 7), nullable=False)         # 订单总成本
    packaging_cost = Column(Numeric(18, 7), nullable=True)      # 当时的包装费
    total_amount = Column(Numeric(18, 7), nullable=True)        # 当时的售价总额
    profit = Column(Numeric(18, 7), nullable=True)              # 利润
    has_incomplete_cost = Column(Integer, nullable=False, default=0)  # 是否有配件缺少成本
    created_at = Column(DateTime, default=now_beijing)
```

**新表 `order_cost_snapshot_item`：**
```python
class OrderCostSnapshotItem(Base):
    __tablename__ = "order_cost_snapshot_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(Integer, ForeignKey("order_cost_snapshot.id"), nullable=False)
    jewelry_id = Column(String, nullable=False)
    jewelry_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(18, 7), nullable=True)          # 售价单价
    handcraft_cost = Column(Numeric(18, 7), nullable=True)      # 当时的饰品手工费
    jewelry_unit_cost = Column(Numeric(18, 7), nullable=False)  # 饰品单位成本
    jewelry_total_cost = Column(Numeric(18, 7), nullable=False) # 饰品总成本 = unit_cost × qty
    # BOM 明细存为 JSON，结构: [{part_id, part_name, unit_cost, qty_per_unit, subtotal}, ...]
    bom_details = Column(Text, nullable=True)
```

---

### Task 1: Model — 成本快照表 + Jewelry/Order 新字段

**Files:**
- Create: `models/order_cost_snapshot.py`
- Modify: `models/jewelry.py` — 新增 `handcraft_cost`
- Modify: `models/order.py` — 新增 `packaging_cost`
- Modify: `models/__init__.py` — 新增 import
- Modify: `database.py` — `ensure_schema_compat()` 添加新列

- [ ] **Step 1: 创建 `models/order_cost_snapshot.py`**

```python
import json

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from database import Base
from time_utils import now_beijing


class OrderCostSnapshot(Base):
    __tablename__ = "order_cost_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("order.id"), nullable=False)
    total_cost = Column(Numeric(18, 7), nullable=False)
    packaging_cost = Column(Numeric(18, 7), nullable=True)
    total_amount = Column(Numeric(18, 7), nullable=True)
    profit = Column(Numeric(18, 7), nullable=True)
    has_incomplete_cost = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=now_beijing)

    items = relationship("OrderCostSnapshotItem", backref="snapshot",
                         lazy="select", order_by="OrderCostSnapshotItem.id")


class OrderCostSnapshotItem(Base):
    __tablename__ = "order_cost_snapshot_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(Integer, ForeignKey("order_cost_snapshot.id"), nullable=False)
    jewelry_id = Column(String, nullable=False)
    jewelry_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(18, 7), nullable=True)
    handcraft_cost = Column(Numeric(18, 7), nullable=True)
    jewelry_unit_cost = Column(Numeric(18, 7), nullable=False)
    jewelry_total_cost = Column(Numeric(18, 7), nullable=False)
    bom_details_raw = Column("bom_details", Text, nullable=True)

    @property
    def bom_details(self):
        if not self.bom_details_raw:
            return []
        try:
            return json.loads(self.bom_details_raw)
        except (TypeError, ValueError):
            return []

    @bom_details.setter
    def bom_details(self, value):
        self.bom_details_raw = json.dumps(value, ensure_ascii=False) if value else None
```

- [ ] **Step 2: 修改 `models/jewelry.py`**

在 `Jewelry` 类中新增：
```python
handcraft_cost = Column(Numeric(18, 7), nullable=True)
```

- [ ] **Step 3: 修改 `models/order.py`**

在 `Order` 类中新增：
```python
packaging_cost = Column(Numeric(18, 7), nullable=True)
```

- [ ] **Step 4: 修改 `models/__init__.py`**

添加：
```python
from .order_cost_snapshot import OrderCostSnapshot, OrderCostSnapshotItem
```
以及 `__all__` 中的条目。

- [ ] **Step 5: 修改 `database.py` 的 `ensure_schema_compat()`**

```python
if inspector.has_table("jewelry"):
    columns = {col["name"] for col in inspector.get_columns("jewelry")}
    if "handcraft_cost" not in columns:
        conn.execute(text("ALTER TABLE jewelry ADD COLUMN handcraft_cost NUMERIC(18,7) NULL"))
        logger.warning("Added missing jewelry.handcraft_cost column")

if inspector.has_table("order"):
    columns = {col["name"] for col in inspector.get_columns("order")}
    if "packaging_cost" not in columns:
        conn.execute(text('ALTER TABLE "order" ADD COLUMN packaging_cost NUMERIC(18,7) NULL'))
        logger.warning("Added missing order.packaging_cost column")
```

注意：`order` 是 SQL 保留字，ALTER TABLE 时需要加引号。

- [ ] **Step 6: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 7: Commit**

```bash
git add models/order_cost_snapshot.py models/jewelry.py models/order.py models/__init__.py database.py
git commit -m "feat: add OrderCostSnapshot model and handcraft_cost/packaging_cost fields"
```

---

### Task 2: Schema — 成本快照 + Order/Jewelry 更新

**Files:**
- Create: `schemas/order_cost_snapshot.py`
- Modify: `schemas/order.py` — OrderResponse 新增 `packaging_cost`
- Modify: `schemas/jewelry.py` — JewelryResponse 新增 `handcraft_cost`

- [ ] **Step 1: 创建 `schemas/order_cost_snapshot.py`**

```python
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class BomDetailItem(BaseModel):
    part_id: str
    part_name: Optional[str] = None
    unit_cost: Optional[float] = None
    qty_per_unit: float
    subtotal: Optional[float] = None


class OrderCostSnapshotItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    snapshot_id: int
    jewelry_id: str
    jewelry_name: Optional[str] = None
    quantity: int
    unit_price: Optional[float] = None
    handcraft_cost: Optional[float] = None
    jewelry_unit_cost: float
    jewelry_total_cost: float
    bom_details: list[BomDetailItem] = Field(default_factory=list)


class OrderCostSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: str
    total_cost: float
    packaging_cost: Optional[float] = None
    total_amount: Optional[float] = None
    profit: Optional[float] = None
    has_incomplete_cost: int
    created_at: datetime
    items: list[OrderCostSnapshotItemResponse] = Field(default_factory=list)
```

- [ ] **Step 2: 修改 `schemas/order.py`**

在 `OrderResponse` 中新增：
```python
packaging_cost: Optional[float] = None
```

- [ ] **Step 3: 修改 `schemas/jewelry.py`**

在 `JewelryResponse` 中新增：
```python
handcraft_cost: Optional[float] = None
```

在 `JewelryCreate` 和 `JewelryUpdate` 中新增：
```python
handcraft_cost: Optional[float] = None
```

- [ ] **Step 4: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 5: Commit**

```bash
git add schemas/order_cost_snapshot.py schemas/order.py schemas/jewelry.py
git commit -m "feat: add cost snapshot schemas and update Order/Jewelry schemas"
```

---

### Task 3: Service — 成本快照生成 + packaging_cost 更新

**Files:**
- Create: `services/order_cost_snapshot.py`
- Modify: `services/order.py` — 修改 `update_order_status`，新增 `update_packaging_cost`

- [ ] **Step 1: 创建 `services/order_cost_snapshot.py`**

```python
import json
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from models.jewelry import Jewelry
from models.order import Order, OrderItem
from models.order_cost_snapshot import OrderCostSnapshot, OrderCostSnapshotItem
from models.part import Part
from services.bom import get_bom

_Q7 = Decimal("0.0000001")


def generate_cost_snapshot(db: Session, order_id: str) -> OrderCostSnapshot:
    """订单完成时生成成本快照。"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None:
        raise ValueError(f"Order not found: {order_id}")

    items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
    if not items:
        raise ValueError(f"订单 {order_id} 没有饰品明细")

    # 前置校验：所有饰品必须有 BOM
    for item in items:
        bom_rows = get_bom(db, item.jewelry_id)
        if not bom_rows:
            jewelry = db.get(Jewelry, item.jewelry_id)
            name = jewelry.name if jewelry else item.jewelry_id
            raise ValueError(f"饰品「{name}」({item.jewelry_id}) 没有 BOM，无法生成成本快照")

    has_incomplete = False
    total_cost = Decimal(0)
    snapshot_items = []

    for item in items:
        jewelry = db.get(Jewelry, item.jewelry_id)
        bom_rows = get_bom(db, item.jewelry_id)

        # 计算 BOM 配件成本
        bom_cost = Decimal(0)
        bom_details = []
        for row in bom_rows:
            part = db.get(Part, row.part_id)
            part_unit_cost = Decimal(str(part.unit_cost or 0)) if part else Decimal(0)
            if part and part.unit_cost is None:
                has_incomplete = True
            qty_per_unit = Decimal(str(row.qty_per_unit))
            subtotal = (part_unit_cost * qty_per_unit).quantize(_Q7, rounding=ROUND_HALF_UP)
            bom_cost += subtotal
            bom_details.append({
                "part_id": row.part_id,
                "part_name": part.name if part else None,
                "unit_cost": float(part_unit_cost),
                "qty_per_unit": float(qty_per_unit),
                "subtotal": float(subtotal),
            })

        # 饰品单位成本 = BOM 配件成本 + handcraft_cost
        hc_cost = Decimal(str(jewelry.handcraft_cost or 0)) if jewelry else Decimal(0)
        jewelry_unit_cost = (bom_cost + hc_cost).quantize(_Q7, rounding=ROUND_HALF_UP)
        jewelry_total_cost = (jewelry_unit_cost * item.quantity).quantize(_Q7, rounding=ROUND_HALF_UP)
        total_cost += jewelry_total_cost

        snapshot_items.append({
            "jewelry_id": item.jewelry_id,
            "jewelry_name": jewelry.name if jewelry else None,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price) if item.unit_price else None,
            "handcraft_cost": float(hc_cost),
            "jewelry_unit_cost": float(jewelry_unit_cost),
            "jewelry_total_cost": float(jewelry_total_cost),
            "bom_details": bom_details,
        })

    # 订单总成本 = Σ饰品总成本 + 包装费
    pkg_cost = Decimal(str(order.packaging_cost or 0))
    total_cost = (total_cost + pkg_cost).quantize(_Q7, rounding=ROUND_HALF_UP)

    # 利润
    total_amount = Decimal(str(order.total_amount or 0))
    profit = (total_amount - total_cost).quantize(_Q7, rounding=ROUND_HALF_UP)

    # 创建快照
    snapshot = OrderCostSnapshot(
        order_id=order_id,
        total_cost=total_cost,
        packaging_cost=pkg_cost if pkg_cost else None,
        total_amount=order.total_amount,
        profit=profit,
        has_incomplete_cost=1 if has_incomplete else 0,
    )
    db.add(snapshot)
    db.flush()

    for si in snapshot_items:
        bom_details = si.pop("bom_details")
        item_obj = OrderCostSnapshotItem(snapshot_id=snapshot.id, **si)
        item_obj.bom_details = bom_details
        db.add(item_obj)
    db.flush()

    return snapshot


def get_cost_snapshot(db: Session, order_id: str) -> OrderCostSnapshot | None:
    """获取订单的成本快照（最新一条）。"""
    return (
        db.query(OrderCostSnapshot)
        .filter(OrderCostSnapshot.order_id == order_id)
        .order_by(OrderCostSnapshot.id.desc())
        .first()
    )
```

- [ ] **Step 2: 修改 `services/order.py` — `update_order_status`**

在 `update_order_status` 中，当状态变为 `"已完成"` 时自动生成成本快照：

```python
from services.order_cost_snapshot import generate_cost_snapshot

# 注意：原 _VALID_STATUSES 只有 {"待生产", "生产中", "已完成"}，这里新增 "已取消"
_VALID_STATUSES = {"待生产", "生产中", "已完成", "已取消"}

def update_order_status(db: Session, order_id: str, status: str) -> Order:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {_VALID_STATUSES}")
    order = get_order(db, order_id)
    if order is None:
        raise ValueError(f"Order not found: {order_id}")
    if order.status == status:
        return order  # no-op，避免重复生成快照
    if status == "已完成":
        generate_cost_snapshot(db, order_id)
    order.status = status
    db.flush()
    return order
```

- [ ] **Step 3: 在 `services/order.py` 中新增 `update_packaging_cost`**

```python
def update_packaging_cost(db: Session, order_id: str, packaging_cost: float) -> Order:
    order = get_order(db, order_id)
    if order is None:
        raise ValueError(f"Order not found: {order_id}")
    order.packaging_cost = packaging_cost
    db.flush()
    return order
```

- [ ] **Step 4: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 5: Commit**

```bash
git add services/order_cost_snapshot.py services/order.py
git commit -m "feat: add cost snapshot generation and packaging_cost update"
```

---

### Task 4: API — 成本快照端点 + packaging_cost

**Files:**
- Modify: `api/orders.py`

- [ ] **Step 1: 在 `api/orders.py` 中新增端点**

新增 import：
```python
from schemas.order_cost_snapshot import OrderCostSnapshotResponse
from services.order_cost_snapshot import get_cost_snapshot
from services.order import update_packaging_cost
from pydantic import BaseModel as _BaseModel

class PackagingCostUpdate(_BaseModel):
    packaging_cost: float
```

新增端点：

```python
@router.get("/{order_id}/cost-snapshot", response_model=OrderCostSnapshotResponse)
def api_get_cost_snapshot(order_id: str, db: Session = Depends(get_db)):
    """获取订单的成本快照"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    snapshot = get_cost_snapshot(db, order_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"订单 {order_id} 尚未生成成本快照")
    return snapshot


@router.patch("/{order_id}/packaging-cost", response_model=OrderResponse)
def api_update_packaging_cost(order_id: str, body: PackagingCostUpdate, db: Session = Depends(get_db)):
    """更新订单包装费"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        order = update_packaging_cost(db, order_id, body.packaging_cost)
    return order
```

- [ ] **Step 2: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 3: Commit**

```bash
git add api/orders.py
git commit -m "feat: add cost snapshot and packaging cost API endpoints"
```

---

### Task 5: Service — handcraft_cost 同步（扩展 cost_sync）

**Files:**
- Modify: `services/cost_sync.py`

此 Task 为手工回收单收回饰品时同步 `handcraft_cost` 到 `Jewelry` 模型。如果手工回收单已实现完毕，在其 API 层调用此函数即可。如果尚未实现，此函数先写好等待集成。

- [ ] **Step 1: 在 `services/cost_sync.py` 中新增函数**

```python
def detect_handcraft_jewelry_cost_diffs(db: Session, receipt) -> list[dict]:
    """Detect handcraft_cost diffs for jewelry items in a handcraft receipt."""
    from models.jewelry import Jewelry

    price_map: Dict[str, Optional[float]] = {}
    for ri in receipt.items:
        if ri.item_type != "jewelry" or ri.price is None:
            continue
        price_map[ri.item_id] = float(ri.price)

    diffs = []
    for jewelry_id, new_price in price_map.items():
        jewelry = db.get(Jewelry, jewelry_id)
        if jewelry is None:
            continue
        current = float(jewelry.handcraft_cost) if jewelry.handcraft_cost is not None else None
        if _compare(current, new_price):
            diffs.append({
                "part_id": jewelry_id,       # 复用 CostDiffItem 结构，part_id 字段存 jewelry_id
                "part_name": jewelry.name,
                "field": "handcraft_cost",
                "current_value": current,
                "new_value": new_price,
            })
    return diffs
```

- [ ] **Step 2: 新增 `auto_set_initial_handcraft_cost` 函数**

```python
def auto_set_initial_handcraft_cost(db: Session, jewelry_id: str, price: float) -> None:
    """Sync handcraft receipt jewelry price to Jewelry.handcraft_cost."""
    from models.jewelry import Jewelry
    jewelry = db.get(Jewelry, jewelry_id)
    if jewelry is None:
        return
    new_value = Decimal(str(price)).quantize(_Q7, rounding=ROUND_HALF_UP)
    current = Decimal(str(jewelry.handcraft_cost)).quantize(_Q7, rounding=ROUND_HALF_UP) if jewelry.handcraft_cost is not None else None
    if current == new_value:
        return
    jewelry.handcraft_cost = new_value
    db.flush()
```

此函数在手工回收单 API 中收回饰品时调用，将 price 写入 `Jewelry.handcraft_cost`。集成点在 `api/handcraft_receipt.py` 的创建和添加明细端点中，遍历 items 中 `item_type == "jewelry"` 的项调用。

- [ ] **Step 3: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 4: Commit**

```bash
git add services/cost_sync.py
git commit -m "feat: add handcraft_cost sync for jewelry via cost_sync"
```

---

### Task 6: Tests — 成本快照

**Files:**
- Create: `tests/test_api_cost_snapshot.py`

- [ ] **Step 1: 编写测试**

```python
import pytest
from decimal import Decimal
from services.jewelry import create_jewelry
from services.part import create_part, update_part_cost
from services.bom import set_bom


def _setup_order_with_cost(db, client):
    """创建有完整成本的订单。"""
    part_a = create_part(db, {"name": "A珠", "category": "小配件"})
    part_b = create_part(db, {"name": "B链", "category": "链条"})
    update_part_cost(db, part_a.id, "purchase_cost", 0.05)
    update_part_cost(db, part_b.id, "purchase_cost", 2.0)

    jewelry = create_jewelry(db, {"name": "项链A", "retail_price": 100.0, "category": "单件"})
    set_bom(db, jewelry.id, part_a.id, 10)    # 10 × 0.05 = 0.5
    set_bom(db, jewelry.id, part_b.id, 1)     # 1 × 2.0 = 2.0
    # 饰品单位成本 = 0.5 + 2.0 = 2.5

    resp = client.post("/api/orders/", json={
        "customer_name": "测试客户",
        "items": [{"jewelry_id": jewelry.id, "quantity": 100, "unit_price": 50.0}],
    })
    assert resp.status_code == 201
    order_id = resp.json()["id"]
    return order_id, part_a, part_b, jewelry


def test_complete_order_generates_snapshot(client, db):
    order_id, _, _, _ = _setup_order_with_cost(db, client)
    resp = client.patch(f"/api/orders/{order_id}/status", json={"status": "已完成"})
    assert resp.status_code == 200

    resp = client.get(f"/api/orders/{order_id}/cost-snapshot")
    assert resp.status_code == 200
    snapshot = resp.json()
    assert snapshot["order_id"] == order_id
    # 总成本 = 2.5 × 100 = 250
    assert pytest.approx(snapshot["total_cost"], abs=0.01) == 250.0
    # 利润 = 5000 - 250 = 4750
    assert pytest.approx(snapshot["profit"], abs=0.01) == 4750.0
    assert len(snapshot["items"]) == 1
    assert len(snapshot["items"][0]["bom_details"]) == 2


def test_complete_order_with_packaging_cost(client, db):
    order_id, _, _, _ = _setup_order_with_cost(db, client)
    client.patch(f"/api/orders/{order_id}/packaging-cost", json={"packaging_cost": 50.0})
    client.patch(f"/api/orders/{order_id}/status", json={"status": "已完成"})

    snapshot = client.get(f"/api/orders/{order_id}/cost-snapshot").json()
    # 总成本 = 250 + 50 = 300
    assert pytest.approx(snapshot["total_cost"], abs=0.01) == 300.0
    assert pytest.approx(snapshot["packaging_cost"], abs=0.01) == 50.0
    assert pytest.approx(snapshot["profit"], abs=0.01) == 4700.0


def test_complete_order_with_handcraft_cost(client, db):
    order_id, _, _, jewelry = _setup_order_with_cost(db, client)
    # 设置饰品手工费
    client.patch(f"/api/jewelries/{jewelry.id}", json={"handcraft_cost": 1.0})

    client.patch(f"/api/orders/{order_id}/status", json={"status": "已完成"})
    snapshot = client.get(f"/api/orders/{order_id}/cost-snapshot").json()
    # 饰品单位成本 = 2.5 + 1.0 = 3.5, 总 = 350
    assert pytest.approx(snapshot["total_cost"], abs=0.01) == 350.0
    item = snapshot["items"][0]
    assert pytest.approx(item["handcraft_cost"], abs=0.01) == 1.0
    assert pytest.approx(item["jewelry_unit_cost"], abs=0.01) == 3.5


def test_complete_order_no_bom_rejected(client, db):
    """没有 BOM 的饰品阻止完成。"""
    jewelry = create_jewelry(db, {"name": "裸饰品", "retail_price": 10.0, "category": "单件"})
    resp = client.post("/api/orders/", json={
        "customer_name": "测试",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10.0}],
    })
    order_id = resp.json()["id"]
    resp = client.patch(f"/api/orders/{order_id}/status", json={"status": "已完成"})
    assert resp.status_code == 400


def test_complete_order_missing_part_cost_marks_incomplete(client, db):
    """配件没有 unit_cost 时标记 has_incomplete_cost。"""
    part = create_part(db, {"name": "无价配件", "category": "小配件"})
    # 不设置 purchase_cost，unit_cost 为 None
    jewelry = create_jewelry(db, {"name": "测试饰品", "retail_price": 10.0, "category": "单件"})
    set_bom(db, jewelry.id, part.id, 1)

    resp = client.post("/api/orders/", json={
        "customer_name": "测试",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10.0}],
    })
    order_id = resp.json()["id"]
    client.patch(f"/api/orders/{order_id}/status", json={"status": "已完成"})

    snapshot = client.get(f"/api/orders/{order_id}/cost-snapshot").json()
    assert snapshot["has_incomplete_cost"] == 1
    assert pytest.approx(snapshot["total_cost"], abs=0.01) == 0.0


def test_snapshot_not_found(client, db):
    """未完成的订单没有快照。"""
    jewelry = create_jewelry(db, {"name": "J", "retail_price": 10.0, "category": "单件"})
    resp = client.post("/api/orders/", json={
        "customer_name": "测试",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10.0}],
    })
    order_id = resp.json()["id"]
    resp = client.get(f"/api/orders/{order_id}/cost-snapshot")
    assert resp.status_code == 404


def test_update_packaging_cost(client, db):
    jewelry = create_jewelry(db, {"name": "J", "retail_price": 10.0, "category": "单件"})
    resp = client.post("/api/orders/", json={
        "customer_name": "测试",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10.0}],
    })
    order_id = resp.json()["id"]
    resp = client.patch(f"/api/orders/{order_id}/packaging-cost", json={"packaging_cost": 25.5})
    assert resp.status_code == 200
    assert pytest.approx(resp.json()["packaging_cost"], abs=0.01) == 25.5


def test_snapshot_preserved_on_status_revert(client, db):
    """退回状态时快照保留。"""
    order_id, _, _, _ = _setup_order_with_cost(db, client)
    client.patch(f"/api/orders/{order_id}/status", json={"status": "已完成"})
    # 退回到已取消
    client.patch(f"/api/orders/{order_id}/status", json={"status": "已取消"})
    # 快照仍然存在
    resp = client.get(f"/api/orders/{order_id}/cost-snapshot")
    assert resp.status_code == 200


def test_cancel_order(client, db):
    """订单可以取消。"""
    jewelry = create_jewelry(db, {"name": "J", "retail_price": 10.0, "category": "单件"})
    resp = client.post("/api/orders/", json={
        "customer_name": "测试",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10.0}],
    })
    order_id = resp.json()["id"]
    resp = client.patch(f"/api/orders/{order_id}/status", json={"status": "已取消"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "已取消"
```

- [ ] **Step 2: 运行测试**

```bash
pytest tests/test_api_cost_snapshot.py -v
```

- [ ] **Step 3: 修复失败的测试，直到全部通过**

- [ ] **Step 4: 运行全部测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_api_cost_snapshot.py
git commit -m "test: add cost snapshot and packaging cost API tests"
```

---

## 第二部分：饰品模板

### 数据模型

**新表 `jewelry_template`：**
```python
class JewelryTemplate(Base):
    __tablename__ = "jewelry_template"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    image = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
```

**新表 `jewelry_template_item`：**
```python
class JewelryTemplateItem(Base):
    __tablename__ = "jewelry_template_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(Integer, ForeignKey("jewelry_template.id"), nullable=False)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty_per_unit = Column(Numeric(10, 4), nullable=False)
```

---

### Task 7: Model — JewelryTemplate

**Files:**
- Create: `models/jewelry_template.py`
- Modify: `models/__init__.py`

- [ ] **Step 1: 创建 `models/jewelry_template.py`**

```python
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from database import Base
from time_utils import now_beijing


class JewelryTemplate(Base):
    __tablename__ = "jewelry_template"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    image = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_beijing)

    items = relationship("JewelryTemplateItem", backref="template",
                         lazy="select", order_by="JewelryTemplateItem.id",
                         cascade="all, delete-orphan")


class JewelryTemplateItem(Base):
    __tablename__ = "jewelry_template_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(Integer, ForeignKey("jewelry_template.id"), nullable=False)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty_per_unit = Column(Numeric(10, 4), nullable=False)
```

- [ ] **Step 2: 修改 `models/__init__.py`**

添加：
```python
from .jewelry_template import JewelryTemplate, JewelryTemplateItem
```
以及 `__all__` 中的条目。

- [ ] **Step 3: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 4: Commit**

```bash
git add models/jewelry_template.py models/__init__.py
git commit -m "feat: add JewelryTemplate model"
```

---

### Task 8: Schema — 饰品模板

**Files:**
- Create: `schemas/jewelry_template.py`

- [ ] **Step 1: 创建 `schemas/jewelry_template.py`**

```python
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class JewelryTemplateItemIn(BaseModel):
    part_id: str
    qty_per_unit: float = Field(gt=0)


class JewelryTemplateCreate(BaseModel):
    name: str
    image: Optional[str] = None
    note: Optional[str] = None
    items: List[JewelryTemplateItemIn] = Field(min_length=1)


class JewelryTemplateUpdate(BaseModel):
    name: Optional[str] = None
    image: Optional[str] = None
    note: Optional[str] = None
    items: Optional[List[JewelryTemplateItemIn]] = None  # 如果提供则全量替换


class JewelryTemplateItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int
    part_id: str
    qty_per_unit: float
    # Enriched
    part_name: Optional[str] = None
    part_image: Optional[str] = None


class JewelryTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    image: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime
    items: list[JewelryTemplateItemResponse] = Field(default_factory=list)
```

- [ ] **Step 2: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 3: Commit**

```bash
git add schemas/jewelry_template.py
git commit -m "feat: add JewelryTemplate schemas"
```

---

### Task 9: Service — 饰品模板 CRUD + 导入 BOM

**Files:**
- Create: `services/jewelry_template.py`

- [ ] **Step 1: 创建 `services/jewelry_template.py`**

```python
from typing import Optional

from sqlalchemy.orm import Session

from models.jewelry_template import JewelryTemplate, JewelryTemplateItem
from models.part import Part
from services.bom import set_bom


def _require_part(db: Session, part_id: str) -> None:
    if db.get(Part, part_id) is None:
        raise ValueError(f"Part not found: {part_id}")


def _enrich_items(db: Session, items: list[JewelryTemplateItem]) -> list[dict]:
    """返回 enriched dict 列表。"""
    results = []
    for item in items:
        part = db.get(Part, item.part_id)
        results.append({
            "id": item.id,
            "template_id": item.template_id,
            "part_id": item.part_id,
            "qty_per_unit": float(item.qty_per_unit),
            "part_name": part.name if part else None,
            "part_image": part.image if part else None,
        })
    return results


def create_template(db: Session, data: dict) -> dict:
    for item in data["items"]:
        _require_part(db, item["part_id"])

    template = JewelryTemplate(
        name=data["name"],
        image=data.get("image"),
        note=data.get("note"),
    )
    db.add(template)
    db.flush()

    for item in data["items"]:
        db.add(JewelryTemplateItem(
            template_id=template.id,
            part_id=item["part_id"],
            qty_per_unit=item["qty_per_unit"],
        ))
    db.flush()

    return get_template(db, template.id)


def get_template(db: Session, template_id: int) -> Optional[dict]:
    template = db.get(JewelryTemplate, template_id)
    if template is None:
        return None
    return {
        "id": template.id,
        "name": template.name,
        "image": template.image,
        "note": template.note,
        "created_at": template.created_at,
        "items": _enrich_items(db, template.items),
    }


def list_templates(db: Session) -> list[dict]:
    templates = db.query(JewelryTemplate).order_by(JewelryTemplate.id.desc()).all()
    return [get_template(db, t.id) for t in templates]


def update_template(db: Session, template_id: int, data: dict) -> dict:
    template = db.get(JewelryTemplate, template_id)
    if template is None:
        raise ValueError(f"JewelryTemplate not found: {template_id}")

    for field in ("name", "image", "note"):
        if field in data:
            setattr(template, field, data[field])

    # 如果提供了 items，全量替换
    if "items" in data and data["items"] is not None:
        for item in data["items"]:
            _require_part(db, item["part_id"])
        # 删除旧的
        db.query(JewelryTemplateItem).filter(
            JewelryTemplateItem.template_id == template_id
        ).delete(synchronize_session=False)
        db.flush()
        # 添加新的
        for item in data["items"]:
            db.add(JewelryTemplateItem(
                template_id=template_id,
                part_id=item["part_id"],
                qty_per_unit=item["qty_per_unit"],
            ))

    db.flush()
    return get_template(db, template_id)


def delete_template(db: Session, template_id: int) -> None:
    template = db.get(JewelryTemplate, template_id)
    if template is None:
        raise ValueError(f"JewelryTemplate not found: {template_id}")
    db.delete(template)
    db.flush()


def apply_template_to_jewelry(db: Session, template_id: int, jewelry_id: str) -> list:
    """将模板的配件导入到饰品的 BOM 中（upsert）。"""
    template = db.get(JewelryTemplate, template_id)
    if template is None:
        raise ValueError(f"JewelryTemplate not found: {template_id}")

    results = []
    for item in template.items:
        bom = set_bom(db, jewelry_id, item.part_id, float(item.qty_per_unit))
        results.append(bom)
    return results
```

- [ ] **Step 2: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 3: Commit**

```bash
git add services/jewelry_template.py
git commit -m "feat: add JewelryTemplate service with CRUD and BOM import"
```

---

### Task 10: API — 饰品模板端点

**Files:**
- Create: `api/jewelry_template.py`
- Modify: `main.py` — 注册 router

- [ ] **Step 1: 创建 `api/jewelry_template.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.jewelry_template import (
    JewelryTemplateCreate,
    JewelryTemplateResponse,
    JewelryTemplateUpdate,
)
from services.jewelry_template import (
    create_template,
    delete_template,
    get_template,
    list_templates,
    update_template,
    apply_template_to_jewelry,
)

router = APIRouter(prefix="/api/jewelry-templates", tags=["jewelry-templates"])


@router.get("/", response_model=list[JewelryTemplateResponse])
def api_list_templates(db: Session = Depends(get_db)):
    return list_templates(db)


@router.post("/", response_model=JewelryTemplateResponse, status_code=201)
def api_create_template(body: JewelryTemplateCreate, db: Session = Depends(get_db)):
    with service_errors():
        return create_template(db, body.model_dump())


@router.get("/{template_id}", response_model=JewelryTemplateResponse)
def api_get_template(template_id: int, db: Session = Depends(get_db)):
    result = get_template(db, template_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"JewelryTemplate {template_id} not found")
    return result


@router.patch("/{template_id}", response_model=JewelryTemplateResponse)
def api_update_template(template_id: int, body: JewelryTemplateUpdate, db: Session = Depends(get_db)):
    result = get_template(db, template_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"JewelryTemplate {template_id} not found")
    with service_errors():
        return update_template(db, template_id, body.model_dump(exclude_unset=True))


@router.delete("/{template_id}", status_code=204)
def api_delete_template(template_id: int, db: Session = Depends(get_db)):
    result = get_template(db, template_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"JewelryTemplate {template_id} not found")
    with service_errors():
        delete_template(db, template_id)


@router.post("/{template_id}/apply/{jewelry_id}", status_code=200)
def api_apply_template(template_id: int, jewelry_id: str, db: Session = Depends(get_db)):
    """将模板导入到饰品的 BOM"""
    with service_errors():
        boms = apply_template_to_jewelry(db, template_id, jewelry_id)
    return {"applied": len(boms)}
```

- [ ] **Step 2: 修改 `main.py`**

```python
from api.jewelry_template import router as jewelry_template_router
# ...
app.include_router(jewelry_template_router, dependencies=[require_permission("parts")])
```

- [ ] **Step 3: 修改 `services/upload.py`**

在 `ALLOWED_KINDS` 中添加：
```python
"jewelry-template": "jewelry-templates",
```

- [ ] **Step 4: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 5: Commit**

```bash
git add api/jewelry_template.py main.py services/upload.py
git commit -m "feat: add JewelryTemplate API endpoints"
```

---

### Task 11: Tests — 饰品模板

**Files:**
- Create: `tests/test_api_jewelry_template.py`

- [ ] **Step 1: 编写测试**

```python
import pytest
from services.part import create_part
from services.jewelry import create_jewelry
from services.bom import get_bom


def _create_parts(db):
    a = create_part(db, {"name": "链条", "category": "链条"})
    b = create_part(db, {"name": "龙虾扣", "category": "小配件"})
    return a, b


def test_create_template(client, db):
    a, b = _create_parts(db)
    resp = client.post("/api/jewelry-templates/", json={
        "name": "基础项链",
        "items": [
            {"part_id": a.id, "qty_per_unit": 1},
            {"part_id": b.id, "qty_per_unit": 2},
        ],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "基础项链"
    assert len(data["items"]) == 2


def test_create_template_with_image_and_note(client, db):
    a, _ = _create_parts(db)
    resp = client.post("/api/jewelry-templates/", json={
        "name": "带图模板",
        "image": "https://example.com/img.jpg",
        "note": "测试备注",
        "items": [{"part_id": a.id, "qty_per_unit": 1}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["image"] == "https://example.com/img.jpg"
    assert data["note"] == "测试备注"


def test_list_templates(client, db):
    a, _ = _create_parts(db)
    client.post("/api/jewelry-templates/", json={
        "name": "模板1",
        "items": [{"part_id": a.id, "qty_per_unit": 1}],
    })
    resp = client.get("/api/jewelry-templates/")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_get_template(client, db):
    a, _ = _create_parts(db)
    created = client.post("/api/jewelry-templates/", json={
        "name": "模板X",
        "items": [{"part_id": a.id, "qty_per_unit": 3}],
    }).json()
    resp = client.get(f"/api/jewelry-templates/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["items"][0]["part_name"] == "链条"


def test_get_template_not_found(client, db):
    resp = client.get("/api/jewelry-templates/9999")
    assert resp.status_code == 404


def test_update_template(client, db):
    a, b = _create_parts(db)
    created = client.post("/api/jewelry-templates/", json={
        "name": "旧名",
        "items": [{"part_id": a.id, "qty_per_unit": 1}],
    }).json()
    resp = client.patch(f"/api/jewelry-templates/{created['id']}", json={
        "name": "新名",
        "items": [
            {"part_id": a.id, "qty_per_unit": 2},
            {"part_id": b.id, "qty_per_unit": 4},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "新名"
    assert len(data["items"]) == 2


def test_delete_template(client, db):
    a, _ = _create_parts(db)
    created = client.post("/api/jewelry-templates/", json={
        "name": "待删除",
        "items": [{"part_id": a.id, "qty_per_unit": 1}],
    }).json()
    resp = client.delete(f"/api/jewelry-templates/{created['id']}")
    assert resp.status_code == 204
    resp = client.get(f"/api/jewelry-templates/{created['id']}")
    assert resp.status_code == 404


def test_apply_template_to_jewelry(client, db):
    a, b = _create_parts(db)
    created = client.post("/api/jewelry-templates/", json={
        "name": "模板",
        "items": [
            {"part_id": a.id, "qty_per_unit": 1},
            {"part_id": b.id, "qty_per_unit": 2},
        ],
    }).json()

    jewelry = create_jewelry(db, {"name": "新项链", "retail_price": 100.0, "category": "单件"})
    resp = client.post(f"/api/jewelry-templates/{created['id']}/apply/{jewelry.id}")
    assert resp.status_code == 200
    assert resp.json()["applied"] == 2

    # 验证 BOM 已设置
    bom = get_bom(db, jewelry.id)
    assert len(bom) == 2
    bom_map = {b.part_id: float(b.qty_per_unit) for b in bom}
    assert bom_map[a.id] == 1.0
    assert bom_map[b.id] == 2.0


def test_apply_template_not_found(client, db):
    jewelry = create_jewelry(db, {"name": "J", "retail_price": 10.0, "category": "单件"})
    resp = client.post(f"/api/jewelry-templates/9999/apply/{jewelry.id}")
    assert resp.status_code == 400


def test_create_template_invalid_part(client, db):
    resp = client.post("/api/jewelry-templates/", json={
        "name": "无效",
        "items": [{"part_id": "PJ-X-99999", "qty_per_unit": 1}],
    })
    assert resp.status_code == 400
```

- [ ] **Step 2: 运行测试**

```bash
pytest tests/test_api_jewelry_template.py -v
```

- [ ] **Step 3: 修复失败的测试，直到全部通过**

- [ ] **Step 4: 运行全部测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_api_jewelry_template.py
git commit -m "test: add JewelryTemplate API tests"
```
