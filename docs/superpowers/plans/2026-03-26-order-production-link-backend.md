# 订单与生产关联 — 后端实现方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现订单配件 TodoList 和订单与电镀单/手工单的关联功能，支持生产进度追踪。

**Architecture:** 新建两张表 `order_todo_item`（订单配件清单行）和 `order_item_link`（关联中间表）。TodoList 基于订单饰品的 BOM 生成并持久化，配件项通过 TodoList 行关联，饰品项直接关联 order_id。关联操作支持单选和批量（按 part_id 自动匹配）。

**Tech Stack:** FastAPI + SQLAlchemy + PostgreSQL + Pydantic V2

**参照文件：**
- `models/order.py` — 现有订单模型
- `services/order.py` — 现有订单服务（含 `get_parts_summary`）
- `services/bom.py` — BOM 查询
- `services/inventory.py` — `get_stock()` 用于库存查询
- `tests/test_api_orders.py` — 现有测试模式

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `models/order.py` | 修改 | 新增 `OrderTodoItem` 和 `OrderItemLink` 模型 |
| `models/__init__.py` | 修改 | 新增 import 和 `__all__` |
| `schemas/order.py` | 修改 | 新增 TodoList 和 Link 相关的请求/响应 schema |
| `services/order_todo.py` | 新建 | TodoList 生成、查询、关联/解除关联的业务逻辑 |
| `api/orders.py` | 修改 | 新增 TodoList 和 Link 相关的 API 端点 |
| `api/plating.py` | 修改 | 新增配件项关联订单的端点（单选 + 批量） |
| `api/handcraft.py` | 修改 | 新增配件项/饰品项关联订单的端点（单选 + 批量） |
| `tests/test_api_order_todo.py` | 新建 | TodoList 和 Link 的 API 测试 |

---

## 后端实现计划

### Task 1: Model — OrderTodoItem + OrderItemLink

**Files:**
- Modify: `models/order.py`
- Modify: `models/__init__.py`

- [ ] **Step 1: 在 `models/order.py` 中新增两个模型**

在文件末尾添加：

```python
class OrderTodoItem(Base):
    __tablename__ = "order_todo_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("order.id"), nullable=False)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    required_qty = Column(Numeric(10, 4), nullable=False)


class OrderItemLink(Base):
    __tablename__ = "order_item_link"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 配件项关联 TodoList 行
    order_todo_item_id = Column(Integer, ForeignKey("order_todo_item.id"), nullable=True)
    # 饰品项直接关联订单
    order_id = Column(String, ForeignKey("order.id"), nullable=True)
    # 三选一：关联的生产项（unique 保证同一生产项只能关联一个订单）
    plating_order_item_id = Column(Integer, ForeignKey("plating_order_item.id"), nullable=True, unique=True)
    handcraft_part_item_id = Column(Integer, ForeignKey("handcraft_part_item.id"), nullable=True, unique=True)
    handcraft_jewelry_item_id = Column(Integer, ForeignKey("handcraft_jewelry_item.id"), nullable=True, unique=True)
```

- [ ] **Step 2: 修改 `models/__init__.py`**

添加 import：
```python
from .order import Order, OrderItem, OrderTodoItem, OrderItemLink
```

在 `__all__` 中添加 `"OrderTodoItem"` 和 `"OrderItemLink"`。

- [ ] **Step 3: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 4: Commit**

```bash
git add models/order.py models/__init__.py
git commit -m "feat: add OrderTodoItem and OrderItemLink models"
```

---

### Task 2: Schema — TodoList 和 Link 的请求/响应

**Files:**
- Modify: `schemas/order.py`

- [ ] **Step 1: 在 `schemas/order.py` 中新增 schema**

在文件末尾添加：

```python
from pydantic import Field


# --- TodoList ---

class OrderTodoItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: str
    part_id: str
    required_qty: float
    # Enriched fields (populated by service)
    part_name: Optional[str] = None
    part_image: Optional[str] = None
    stock_qty: Optional[float] = None           # 当前库存
    gap: Optional[float] = None                 # 缺口 = required_qty - stock_qty
    is_complete: Optional[bool] = None          # stock_qty >= required_qty
    linked_production: Optional[list] = None    # 关联的生产单状态列表


# --- Link ---

class LinkCreateRequest(BaseModel):
    """单选关联：一个生产项关联一个 TodoList 行"""
    order_todo_item_id: Optional[int] = None          # 配件项用
    order_id: Optional[str] = None                     # 饰品项用
    plating_order_item_id: Optional[int] = None        # 三选一
    handcraft_part_item_id: Optional[int] = None       # 三选一
    handcraft_jewelry_item_id: Optional[int] = None    # 三选一


class BatchLinkRequest(BaseModel):
    """批量关联：多个配件项按 part_id 自动匹配 TodoList 行"""
    order_id: str
    plating_order_item_ids: list[int] = Field(default_factory=list)
    handcraft_part_item_ids: list[int] = Field(default_factory=list)


class BatchLinkResponse(BaseModel):
    linked: int              # 成功关联数
    skipped: list[str] = Field(default_factory=list)    # 未匹配的配件名列表


class LinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_todo_item_id: Optional[int] = None
    order_id: Optional[str] = None
    plating_order_item_id: Optional[int] = None
    handcraft_part_item_id: Optional[int] = None
    handcraft_jewelry_item_id: Optional[int] = None


class OrderProgressResponse(BaseModel):
    """订单列表页的生产进度概要"""
    order_id: str
    total: int          # 关联的生产项总数
    completed: int      # 已完成的生产项数
```

- [ ] **Step 2: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 3: Commit**

```bash
git add schemas/order.py
git commit -m "feat: add TodoList and Link schemas for order-production association"
```

---

### Task 3: Service — TodoList 生成与关联逻辑

**Files:**
- Create: `services/order_todo.py`

- [ ] **Step 1: 创建 `services/order_todo.py`**

```python
from typing import Optional

from sqlalchemy.orm import Session

from models.order import Order, OrderItem, OrderTodoItem, OrderItemLink
from models.part import Part
from models.plating_order import PlatingOrderItem
from models.handcraft_order import HandcraftPartItem, HandcraftJewelryItem
from services.bom import get_bom
from services.inventory import get_stock


def generate_todo(db: Session, order_id: str) -> list[dict]:
    """基于订单饰品的 BOM 生成配件 TodoList，持久化存储。

    如果已有 TodoList，重新生成时保留能匹配的关联关系（按 part_id 匹配）。
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None:
        raise ValueError(f"Order not found: {order_id}")

    # 计算 BOM 需求
    items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
    summary: dict[str, float] = {}
    for item in items:
        bom_rows = get_bom(db, item.jewelry_id)
        for row in bom_rows:
            summary[row.part_id] = summary.get(row.part_id, 0.0) + float(row.qty_per_unit) * item.quantity

    # 获取现有 todo items 及其关联
    old_todos = db.query(OrderTodoItem).filter(OrderTodoItem.order_id == order_id).all()
    # 按 part_id 索引旧的 todo item id，用于保留关联
    old_by_part: dict[str, int] = {t.part_id: t.id for t in old_todos}

    # 删除不再需要的 todo items（part_id 不在新 summary 中）
    for todo in old_todos:
        if todo.part_id not in summary:
            # 删除关联
            db.query(OrderItemLink).filter(
                OrderItemLink.order_todo_item_id == todo.id
            ).delete(synchronize_session=False)
            db.delete(todo)
        else:
            # 更新数量
            todo.required_qty = summary[todo.part_id]
    db.flush()

    # 添加新的 todo items（part_id 不在旧列表中）
    existing_parts = {t.part_id for t in old_todos if t.part_id in summary}
    for part_id, qty in summary.items():
        if part_id not in existing_parts:
            db.add(OrderTodoItem(
                order_id=order_id,
                part_id=part_id,
                required_qty=qty,
            ))
    db.flush()

    return get_todo(db, order_id)


def get_todo(db: Session, order_id: str) -> list[dict]:
    """获取订单的 TodoList，返回 enriched 字典列表。"""
    todos = (
        db.query(OrderTodoItem)
        .filter(OrderTodoItem.order_id == order_id)
        .order_by(OrderTodoItem.id.asc())
        .all()
    )
    results = []
    for todo in todos:
        part = db.get(Part, todo.part_id)
        stock = get_stock(db, "part", todo.part_id)
        required = float(todo.required_qty)
        results.append({
            "id": todo.id,
            "order_id": todo.order_id,
            "part_id": todo.part_id,
            "required_qty": required,
            "part_name": part.name if part else None,
            "part_image": part.image if part else None,
            "stock_qty": stock,
            "gap": max(0.0, required - stock),
            "is_complete": stock >= required,
            "linked_production": _get_linked_production(db, todo.id),
        })
    return results


def _get_linked_production(db: Session, todo_item_id: int) -> list[dict]:
    """获取关联到某 TodoList 行的所有生产项及状态。"""
    links = db.query(OrderItemLink).filter(
        OrderItemLink.order_todo_item_id == todo_item_id
    ).all()
    result = []
    for link in links:
        if link.plating_order_item_id:
            poi = db.get(PlatingOrderItem, link.plating_order_item_id)
            if poi:
                result.append({
                    "type": "plating",
                    "order_id": poi.plating_order_id,
                    "item_id": poi.id,
                    "part_id": poi.part_id,
                    "status": poi.status,
                })
        elif link.handcraft_part_item_id:
            hpi = db.get(HandcraftPartItem, link.handcraft_part_item_id)
            if hpi:
                result.append({
                    "type": "handcraft_part",
                    "order_id": hpi.handcraft_order_id,
                    "item_id": hpi.id,
                    "part_id": hpi.part_id,
                    "status": hpi.status,
                })
    return result


def create_link(db: Session, data: dict) -> OrderItemLink:
    """创建单个关联。"""
    # 校验三选一
    production_keys = ["plating_order_item_id", "handcraft_part_item_id", "handcraft_jewelry_item_id"]
    set_keys = [k for k in production_keys if data.get(k) is not None]
    if len(set_keys) != 1:
        raise ValueError("必须指定且仅指定一个生产项（plating_order_item_id / handcraft_part_item_id / handcraft_jewelry_item_id）")

    # 校验关联目标（todo_item 或 order_id 二选一）
    has_todo = data.get("order_todo_item_id") is not None
    has_order = data.get("order_id") is not None
    if not has_todo and not has_order:
        raise ValueError("必须指定 order_todo_item_id 或 order_id")
    if has_todo and has_order:
        raise ValueError("order_todo_item_id 和 order_id 不能同时指定")

    # 饰品项只能用 order_id
    if data.get("handcraft_jewelry_item_id") and has_todo:
        raise ValueError("手工饰品项只能关联 order_id，不能关联 TodoList 行")

    # 配件项只能用 order_todo_item_id
    if (data.get("plating_order_item_id") or data.get("handcraft_part_item_id")) and has_order:
        raise ValueError("配件项只能关联 TodoList 行，不能直接关联 order_id")

    # 校验 todo_item 存在
    if has_todo:
        todo = db.get(OrderTodoItem, data["order_todo_item_id"])
        if todo is None:
            raise ValueError(f"OrderTodoItem not found: {data['order_todo_item_id']}")

    # 校验 order 存在
    if has_order:
        order = db.query(Order).filter(Order.id == data["order_id"]).first()
        if order is None:
            raise ValueError(f"Order not found: {data['order_id']}")

    # 校验唯一性：同一个生产项只能关联一个订单
    prod_key = set_keys[0]
    prod_id = data[prod_key]
    existing = db.query(OrderItemLink).filter(
        getattr(OrderItemLink, prod_key) == prod_id
    ).first()
    if existing:
        raise ValueError(f"该生产项已关联订单，请先解除关联")

    link = OrderItemLink(
        order_todo_item_id=data.get("order_todo_item_id"),
        order_id=data.get("order_id"),
        plating_order_item_id=data.get("plating_order_item_id"),
        handcraft_part_item_id=data.get("handcraft_part_item_id"),
        handcraft_jewelry_item_id=data.get("handcraft_jewelry_item_id"),
    )
    db.add(link)
    db.flush()
    return link


def delete_link(db: Session, link_id: int) -> None:
    """解除关联。"""
    link = db.get(OrderItemLink, link_id)
    if link is None:
        raise ValueError(f"OrderItemLink not found: {link_id}")
    db.delete(link)
    db.flush()


def batch_link(
    db: Session,
    order_id: str,
    plating_order_item_ids: list[int] = None,
    handcraft_part_item_ids: list[int] = None,
) -> dict:
    """批量关联：按 part_id 自动匹配 TodoList 行。

    返回 {"linked": 成功数, "skipped": [未匹配的配件名]}
    """
    # 获取订单的 TodoList，按 part_id 索引
    todos = db.query(OrderTodoItem).filter(OrderTodoItem.order_id == order_id).all()
    if not todos:
        raise ValueError(f"订单 {order_id} 尚未生成配件清单，请先生成")
    todo_by_part: dict[str, int] = {t.part_id: t.id for t in todos}

    linked = 0
    skipped = []

    for poi_id in (plating_order_item_ids or []):
        poi = db.get(PlatingOrderItem, poi_id)
        if poi is None:
            continue
        # 检查是否已关联
        existing = db.query(OrderItemLink).filter(
            OrderItemLink.plating_order_item_id == poi_id
        ).first()
        if existing:
            continue
        todo_id = todo_by_part.get(poi.part_id)
        if todo_id is None:
            part = db.get(Part, poi.part_id)
            skipped.append(part.name if part else poi.part_id)
            continue
        db.add(OrderItemLink(
            order_todo_item_id=todo_id,
            plating_order_item_id=poi_id,
        ))
        linked += 1

    for hpi_id in (handcraft_part_item_ids or []):
        hpi = db.get(HandcraftPartItem, hpi_id)
        if hpi is None:
            continue
        existing = db.query(OrderItemLink).filter(
            OrderItemLink.handcraft_part_item_id == hpi_id
        ).first()
        if existing:
            continue
        todo_id = todo_by_part.get(hpi.part_id)
        if todo_id is None:
            part = db.get(Part, hpi.part_id)
            skipped.append(part.name if part else hpi.part_id)
            continue
        db.add(OrderItemLink(
            order_todo_item_id=todo_id,
            handcraft_part_item_id=hpi_id,
        ))
        linked += 1

    db.flush()
    return {"linked": linked, "skipped": skipped}


def get_links_for_production_item(
    db: Session,
    plating_order_item_id: int = None,
    handcraft_part_item_id: int = None,
    handcraft_jewelry_item_id: int = None,
) -> list[dict]:
    """获取某个生产项关联的订单信息（反向查询，用于电镀/手工单详情页）。"""
    q = db.query(OrderItemLink)
    if plating_order_item_id:
        q = q.filter(OrderItemLink.plating_order_item_id == plating_order_item_id)
    elif handcraft_part_item_id:
        q = q.filter(OrderItemLink.handcraft_part_item_id == handcraft_part_item_id)
    elif handcraft_jewelry_item_id:
        q = q.filter(OrderItemLink.handcraft_jewelry_item_id == handcraft_jewelry_item_id)
    else:
        return []

    links = q.all()
    result = []
    for link in links:
        order_id = link.order_id
        if link.order_todo_item_id:
            todo = db.get(OrderTodoItem, link.order_todo_item_id)
            order_id = todo.order_id if todo else None
        if order_id:
            order = db.query(Order).filter(Order.id == order_id).first()
            result.append({
                "order_id": order_id,
                "customer_name": order.customer_name if order else None,
                "link_id": link.id,
            })
    return result


def get_order_progress(db: Session, order_id: str) -> dict:
    """获取订单的生产进度概要。"""
    # 通过 TodoList 关联的配件项
    todo_ids = [t.id for t in db.query(OrderTodoItem).filter(OrderTodoItem.order_id == order_id).all()]

    links = []
    if todo_ids:
        links.extend(
            db.query(OrderItemLink)
            .filter(OrderItemLink.order_todo_item_id.in_(todo_ids))
            .all()
        )
    # 直接关联 order_id 的饰品项
    links.extend(
        db.query(OrderItemLink)
        .filter(OrderItemLink.order_id == order_id)
        .all()
    )

    total = len(links)
    completed = 0
    for link in links:
        if link.plating_order_item_id:
            poi = db.get(PlatingOrderItem, link.plating_order_item_id)
            if poi and poi.status == "已收回":
                completed += 1
        elif link.handcraft_part_item_id:
            hpi = db.get(HandcraftPartItem, link.handcraft_part_item_id)
            if hpi and hpi.status == "已收回":
                completed += 1
        elif link.handcraft_jewelry_item_id:
            hji = db.get(HandcraftJewelryItem, link.handcraft_jewelry_item_id)
            if hji and hji.status == "已收回":
                completed += 1

    return {"order_id": order_id, "total": total, "completed": completed}
```

- [ ] **Step 2: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 3: Commit**

```bash
git add services/order_todo.py
git commit -m "feat: add order TodoList and Link service logic"
```

---

### Task 4: API — 订单侧端点（TodoList + Link + Progress）

**Files:**
- Modify: `api/orders.py`

- [ ] **Step 1: 在 `api/orders.py` 中新增端点**

在文件顶部添加 import：
```python
from schemas.order import (
    OrderCreate, OrderResponse, OrderItemResponse, StatusUpdate,
    OrderTodoItemResponse, LinkCreateRequest, LinkResponse,
    BatchLinkRequest, BatchLinkResponse, OrderProgressResponse,
)
from services.order_todo import (
    generate_todo, get_todo, create_link, delete_link,
    batch_link, get_order_progress,
)
```

在文件末尾添加端点：

```python
# --- TodoList ---

@router.post("/{order_id}/todo", response_model=list[OrderTodoItemResponse])
def api_generate_todo(order_id: str, db: Session = Depends(get_db)):
    """手动生成/重新生成配件 TodoList"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        return generate_todo(db, order_id)


@router.get("/{order_id}/todo", response_model=list[OrderTodoItemResponse])
def api_get_todo(order_id: str, db: Session = Depends(get_db)):
    """获取配件 TodoList"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return get_todo(db, order_id)


# --- Link ---

@router.post("/{order_id}/links", response_model=LinkResponse, status_code=201)
def api_create_link(order_id: str, body: LinkCreateRequest, db: Session = Depends(get_db)):
    """单选关联"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    data = body.model_dump()
    # 确保饰品项关联的 order_id 与路径一致
    if body.handcraft_jewelry_item_id and not body.order_id:
        data["order_id"] = order_id
    # 校验 todo_item 属于该订单
    if body.order_todo_item_id:
        from models.order import OrderTodoItem
        todo = db.get(OrderTodoItem, body.order_todo_item_id)
        if todo and todo.order_id != order_id:
            raise HTTPException(status_code=400, detail="TodoItem 不属于该订单")
    with service_errors():
        link = create_link(db, data)
    return link


@router.post("/{order_id}/links/batch", response_model=BatchLinkResponse)
def api_batch_link(order_id: str, body: BatchLinkRequest, db: Session = Depends(get_db)):
    """批量关联：按 part_id 自动匹配 TodoList 行"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        result = batch_link(
            db,
            order_id=order_id,
            plating_order_item_ids=body.plating_order_item_ids,
            handcraft_part_item_ids=body.handcraft_part_item_ids,
        )
    return result


@router.delete("/links/{link_id}", status_code=204)
def api_delete_link(link_id: int, db: Session = Depends(get_db)):
    """解除关联（从订单侧）"""
    with service_errors():
        delete_link(db, link_id)


# --- Progress ---

@router.get("/{order_id}/progress", response_model=OrderProgressResponse)
def api_get_order_progress(order_id: str, db: Session = Depends(get_db)):
    """获取订单生产进度概要"""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return get_order_progress(db, order_id)
```

- [ ] **Step 2: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 3: Commit**

```bash
git add api/orders.py
git commit -m "feat: add TodoList, Link, and Progress API endpoints on orders"
```

---

### Task 5: API — 电镀/手工单侧端点（反向查询 + 解除关联）

**Files:**
- Modify: `api/plating.py`
- Modify: `api/handcraft.py`

- [ ] **Step 1: 在 `api/plating.py` 中新增端点**

在 import 中添加：
```python
from services.order_todo import get_links_for_production_item, delete_link
```

在文件末尾添加：
```python
@router.get("/{order_id}/items/{item_id}/orders")
def api_get_plating_item_orders(order_id: str, item_id: int, db: Session = Depends(get_db)):
    """获取电镀配件项关联的订单列表"""
    return get_links_for_production_item(db, plating_order_item_id=item_id)


@router.delete("/{order_id}/items/{item_id}/orders/{link_id}", status_code=204)
def api_delete_plating_item_order_link(order_id: str, item_id: int, link_id: int, db: Session = Depends(get_db)):
    """从电镀单侧解除关联"""
    with service_errors():
        delete_link(db, link_id)
```

- [ ] **Step 2: 在 `api/handcraft.py` 中新增端点**

在 import 中添加：
```python
from services.order_todo import get_links_for_production_item, delete_link
```

在文件末尾添加：
```python
@router.get("/{order_id}/parts/{item_id}/orders")
def api_get_handcraft_part_orders(order_id: str, item_id: int, db: Session = Depends(get_db)):
    """获取手工配件项关联的订单列表"""
    return get_links_for_production_item(db, handcraft_part_item_id=item_id)


@router.delete("/{order_id}/parts/{item_id}/orders/{link_id}", status_code=204)
def api_delete_handcraft_part_order_link(order_id: str, item_id: int, link_id: int, db: Session = Depends(get_db)):
    """从手工单侧解除配件项关联"""
    with service_errors():
        delete_link(db, link_id)


@router.get("/{order_id}/jewelries/{item_id}/orders")
def api_get_handcraft_jewelry_orders(order_id: str, item_id: int, db: Session = Depends(get_db)):
    """获取手工饰品项关联的订单列表"""
    return get_links_for_production_item(db, handcraft_jewelry_item_id=item_id)


@router.delete("/{order_id}/jewelries/{item_id}/orders/{link_id}", status_code=204)
def api_delete_handcraft_jewelry_order_link(order_id: str, item_id: int, link_id: int, db: Session = Depends(get_db)):
    """从手工单侧解除饰品项关联"""
    with service_errors():
        delete_link(db, link_id)
```

- [ ] **Step 3: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 4: Commit**

```bash
git add api/plating.py api/handcraft.py
git commit -m "feat: add order link query and unlink endpoints on plating/handcraft"
```

---

### Task 6: Tests — TodoList 和 Link API 测试

**Files:**
- Create: `tests/test_api_order_todo.py`

- [ ] **Step 1: 编写测试**

```python
import pytest
from services.jewelry import create_jewelry
from services.part import create_part
from services.bom import set_bom
from services.inventory import add_stock
from services.plating import create_plating_order, send_plating_order


def _setup_order_with_bom(db, client):
    """创建配件、饰品、BOM，然后创建订单。"""
    part_a = create_part(db, {"name": "A珠", "category": "小配件"})
    part_b = create_part(db, {"name": "B链", "category": "链条"})
    jewelry = create_jewelry(db, {"name": "项链A", "retail_price": 100.0, "category": "单件"})
    set_bom(db, jewelry.id, part_a.id, 10)    # 每条项链需要 10 颗 A珠
    set_bom(db, jewelry.id, part_b.id, 1)     # 每条项链需要 1 条 B链

    resp = client.post("/api/orders/", json={
        "customer_name": "测试客户",
        "items": [{"jewelry_id": jewelry.id, "quantity": 100, "unit_price": 50.0}],
    })
    assert resp.status_code == 201
    order_id = resp.json()["id"]
    return order_id, part_a, part_b, jewelry


def _setup_plating_order(db, client, part):
    """创建电镀单并发出，返回 order_id 和 item_id。"""
    add_stock(db, "part", part.id, 5000, "入库")
    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀厂A",
        "items": [{"part_id": part.id, "qty": 2000}],
    })
    assert resp.status_code == 201
    plating_order_id = resp.json()["id"]
    client.post(f"/api/plating/{plating_order_id}/send")
    items_resp = client.get(f"/api/plating/{plating_order_id}/items")
    item_id = items_resp.json()[0]["id"]
    return plating_order_id, item_id


# --- TodoList 生成 ---

def test_generate_todo(client, db):
    order_id, part_a, part_b, _ = _setup_order_with_bom(db, client)
    resp = client.post(f"/api/orders/{order_id}/todo")
    assert resp.status_code == 200
    todos = resp.json()
    assert len(todos) == 2
    part_ids = {t["part_id"] for t in todos}
    assert part_a.id in part_ids
    assert part_b.id in part_ids
    # A珠：10 × 100 = 1000
    a_todo = next(t for t in todos if t["part_id"] == part_a.id)
    assert a_todo["required_qty"] == 1000.0


def test_generate_todo_not_found(client, db):
    resp = client.post("/api/orders/OR-9999/todo")
    assert resp.status_code == 404


def test_get_todo(client, db):
    order_id, _, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    resp = client.get(f"/api/orders/{order_id}/todo")
    assert resp.status_code == 200
    todos = resp.json()
    assert len(todos) == 2
    # 没有库存，所以 is_complete 应为 False
    assert all(t["is_complete"] is False for t in todos)


def test_get_todo_with_stock(client, db):
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    add_stock(db, "part", part_a.id, 2000, "入库")
    client.post(f"/api/orders/{order_id}/todo")
    resp = client.get(f"/api/orders/{order_id}/todo")
    todos = resp.json()
    a_todo = next(t for t in todos if t["part_id"] == part_a.id)
    assert a_todo["is_complete"] is True
    assert a_todo["gap"] == 0.0


def test_regenerate_todo_preserves_links(client, db):
    """重新生成 TodoList 时保留已有关联。"""
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    # 创建电镀单并关联
    _, poi_id = _setup_plating_order(db, client, part_a)
    client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "plating_order_item_id": poi_id,
    })

    # 重新生成 TodoList
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo = next(t for t in todos if t["part_id"] == part_a.id)
    # 关联应保留
    assert len(a_todo["linked_production"]) == 1


# --- 单选关联 ---

def test_create_link(client, db):
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    _, poi_id = _setup_plating_order(db, client, part_a)

    resp = client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "plating_order_item_id": poi_id,
    })
    assert resp.status_code == 201


def test_create_link_duplicate_rejected(client, db):
    """同一个生产项不能关联多个订单。"""
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    _, poi_id = _setup_plating_order(db, client, part_a)

    client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "plating_order_item_id": poi_id,
    })
    # 重复关联应报错
    resp = client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "plating_order_item_id": poi_id,
    })
    assert resp.status_code == 400


def test_delete_link(client, db):
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    _, poi_id = _setup_plating_order(db, client, part_a)
    link = client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "plating_order_item_id": poi_id,
    }).json()

    resp = client.delete(f"/api/orders/links/{link['id']}")
    assert resp.status_code == 204


# --- 批量关联 ---

def test_batch_link(client, db):
    order_id, part_a, part_b, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")

    add_stock(db, "part", part_a.id, 5000, "入库")
    add_stock(db, "part", part_b.id, 5000, "入库")
    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀厂A",
        "items": [
            {"part_id": part_a.id, "qty": 1000},
            {"part_id": part_b.id, "qty": 100},
        ],
    })
    plating_id = resp.json()["id"]
    client.post(f"/api/plating/{plating_id}/send")
    items = client.get(f"/api/plating/{plating_id}/items").json()
    poi_ids = [item["id"] for item in items]

    resp = client.post(f"/api/orders/{order_id}/links/batch", json={
        "order_id": order_id,
        "plating_order_item_ids": poi_ids,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["linked"] == 2
    assert data["skipped"] == []


def test_batch_link_with_skip(client, db):
    """批量关联时，TodoList 中不存在的配件跳过。"""
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")

    # 创建一个不在 BOM 中的配件
    part_c = create_part(db, {"name": "C扣", "category": "小配件"})
    add_stock(db, "part", part_a.id, 5000, "入库")
    add_stock(db, "part", part_c.id, 5000, "入库")
    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀厂A",
        "items": [
            {"part_id": part_a.id, "qty": 1000},
            {"part_id": part_c.id, "qty": 500},
        ],
    })
    plating_id = resp.json()["id"]
    client.post(f"/api/plating/{plating_id}/send")
    items = client.get(f"/api/plating/{plating_id}/items").json()
    poi_ids = [item["id"] for item in items]

    resp = client.post(f"/api/orders/{order_id}/links/batch", json={
        "order_id": order_id,
        "plating_order_item_ids": poi_ids,
    })
    data = resp.json()
    assert data["linked"] == 1
    assert "C扣" in data["skipped"]


# --- 反向查询 ---

def test_plating_item_orders(client, db):
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    plating_id, poi_id = _setup_plating_order(db, client, part_a)
    client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "plating_order_item_id": poi_id,
    })

    resp = client.get(f"/api/plating/{plating_id}/items/{poi_id}/orders")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["order_id"] == order_id


# --- 进度概要 ---

def test_order_progress(client, db):
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    _, poi_id = _setup_plating_order(db, client, part_a)
    client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "plating_order_item_id": poi_id,
    })

    resp = client.get(f"/api/orders/{order_id}/progress")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["completed"] == 0  # 电镀中，未收回


def test_order_progress_no_links(client, db):
    order_id, _, _, _ = _setup_order_with_bom(db, client)
    resp = client.get(f"/api/orders/{order_id}/progress")
    data = resp.json()
    assert data["total"] == 0
    assert data["completed"] == 0
```

- [ ] **Step 2: 运行测试**

```bash
pytest tests/test_api_order_todo.py -v
```

- [ ] **Step 3: 修复失败的测试，直到全部通过**

- [ ] **Step 4: 运行全部测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_api_order_todo.py
git commit -m "test: add order TodoList and Link API tests"
```
