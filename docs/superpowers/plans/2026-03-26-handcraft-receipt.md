# 手工回收单（HandcraftReceipt）实现方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建独立的手工回收单（HR-），支持收回配件和饰品，跨多个手工单，带付款状态和成本同步。

**Architecture:** 完全参照电镀回收单（PlatingReceipt / ER-）的结构，新建 HandcraftReceipt + HandcraftReceiptItem。收回配件时更新 `HandcraftPartItem.received_qty`（新增字段），收回饰品时更新 `HandcraftJewelryItem.received_qty`。配件的手工费通过 cost_sync 写入 `Part.bead_cost`。现有的 `receive_handcraft_jewelries` 函数和 `POST /handcraft/{id}/receive` 端点将被废弃移除。

**Tech Stack:** FastAPI + SQLAlchemy + PostgreSQL + Pydantic V2

**参照文件：** 以下电镀回收单文件是本方案的模板，每个新文件的结构和逻辑应与对应的电镀回收单文件保持一致：
- `models/plating_receipt.py` → `models/handcraft_receipt.py`
- `schemas/plating_receipt.py` → `schemas/handcraft_receipt.py`
- `services/plating_receipt.py` → `services/handcraft_receipt.py`
- `api/plating_receipt.py` → `api/handcraft_receipt.py`
- `services/cost_sync.py` → 扩展，新增 `detect_handcraft_bead_cost_diffs`

---

## 与电镀回收单的关键差异

| 维度 | 电镀回收单 (ER-) | 手工回收单 (HR-) |
|------|-----------------|-----------------|
| ID 前缀 | `ER-` | `HR-` |
| 商家字段 | `vendor_name` | `supplier_name` |
| 回收对象 | 仅配件 (part) | **配件 (part) + 饰品 (jewelry)** |
| 关联订单项 | `plating_order_item_id` | `handcraft_part_item_id` 或 `handcraft_jewelry_item_id`（二选一） |
| `receive_part_id` | 支持（收回配件可与发出配件不同） | **不需要**（收回即发出的同一配件） |
| 库存操作 | `add_stock("part", ...)` | 配件: `add_stock("part", ...)`；饰品: `add_stock("jewelry", ...)` |
| 库存原因 | `"电镀收回"` / `"电镀收回撤回"` | `"手工收回"` / `"手工收回撤回"` |
| 成本同步 | `plating_cost` 字段 | `bead_cost` 字段（仅配件项有 price 时） |
| 订单完成判断 | 所有 `PlatingOrderItem.received_qty >= qty` | 所有 `HandcraftPartItem.received_qty >= qty` **且** 所有 `HandcraftJewelryItem.received_qty >= qty` |
| 图片上限 | 9 张 | 9 张 |

---

## 数据模型变更

### 新增模型：`HandcraftReceipt` + `HandcraftReceiptItem`

```python
# models/handcraft_receipt.py

class HandcraftReceipt(Base):
    __tablename__ = "handcraft_receipt"

    id = Column(String, primary_key=True)                    # HR-0001
    supplier_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="未付款")  # 未付款 / 已付款
    total_amount = Column(Numeric(18, 7), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
    paid_at = Column(DateTime, nullable=True)
    delivery_images_raw = Column("delivery_images", Text, nullable=True)

    items = relationship("HandcraftReceiptItem", backref="handcraft_receipt",
                         lazy="select", order_by="HandcraftReceiptItem.id")

    # delivery_images property getter/setter — 同 PlatingReceipt


class HandcraftReceiptItem(Base):
    __tablename__ = "handcraft_receipt_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    handcraft_receipt_id = Column(String, ForeignKey("handcraft_receipt.id"), nullable=False)

    # 二选一关联：配件项 或 饰品项
    handcraft_part_item_id = Column(Integer, ForeignKey("handcraft_part_item.id"), nullable=True)
    handcraft_jewelry_item_id = Column(Integer, ForeignKey("handcraft_jewelry_item.id"), nullable=True)

    # 冗余存储，方便查询（类似 PlatingReceiptItem.part_id）
    item_id = Column(String, nullable=False)        # part_id 或 jewelry_id
    item_type = Column(String, nullable=False)       # "part" 或 "jewelry"

    qty = Column(Numeric(10, 4), nullable=False)
    unit = Column(String, nullable=True, default="个")
    price = Column(Numeric(18, 7), nullable=True)    # 手工费单价（仅配件项有意义）
    amount = Column(Numeric(18, 7), nullable=True)   # qty × price
    note = Column(Text, nullable=True)
```

### 现有模型变更：`HandcraftPartItem` 新增 `received_qty` 和 `status`

```python
# models/handcraft_order.py — HandcraftPartItem 新增字段

received_qty = Column(Numeric(10, 4), nullable=True, default=0)
status = Column(String, nullable=False, default="未送出")  # 未送出 / 制作中 / 已收回
```

同时修改 `services/handcraft.py` 中的 `send_handcraft_order`，在发出时将 `HandcraftPartItem.status` 也设为 `"制作中"`（当前只设了 jewelry items 的 status）。

---

## 后端实现计划

### Task 1: Model — HandcraftReceipt + HandcraftReceiptItem

**Files:**
- Create: `models/handcraft_receipt.py`
- Modify: `models/__init__.py` — 添加 import 和 `__all__`
- Modify: `models/handcraft_order.py` — `HandcraftPartItem` 新增 `received_qty`, `status`
- Modify: `database.py` — `ensure_schema_compat()` 添加新列迁移

- [ ] **Step 1: 创建 `models/handcraft_receipt.py`**

参照 `models/plating_receipt.py`，创建 `HandcraftReceipt` 和 `HandcraftReceiptItem` 模型。字段见上方数据模型设计。

- [ ] **Step 2: 修改 `HandcraftPartItem`**

在 `models/handcraft_order.py` 的 `HandcraftPartItem` 类中新增：
```python
received_qty = Column(Numeric(10, 4), nullable=True, default=0)
status = Column(String, nullable=False, default="未送出")
```

- [ ] **Step 3: 修改 `models/__init__.py`**

添加 `from .handcraft_receipt import HandcraftReceipt, HandcraftReceiptItem`，以及 `__all__` 中的条目。

- [ ] **Step 4: 修改 `database.py` 的 `ensure_schema_compat()`**

为 `handcraft_part_item` 表添加 `received_qty` 和 `status` 的 additive migration：
```sql
ALTER TABLE handcraft_part_item ADD COLUMN received_qty NUMERIC(10,4) DEFAULT 0;
ALTER TABLE handcraft_part_item ADD COLUMN status VARCHAR NOT NULL DEFAULT '未送出';
```

**重要：数据迁移** — `status` 列添加后，需要修正已有数据：
```sql
-- 已发出的手工单，配件状态应为 "制作中"
UPDATE handcraft_part_item SET status = '制作中'
WHERE handcraft_order_id IN (SELECT id FROM handcraft_order WHERE status = 'processing');
-- 已完成的手工单，配件状态应为 "已收回"
UPDATE handcraft_part_item SET status = '已收回'
WHERE handcraft_order_id IN (SELECT id FROM handcraft_order WHERE status = 'completed');
```

将上述逻辑放入 `ensure_schema_compat()` 中，在添加列之后执行数据迁移。

- [ ] **Step 5: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 6: Commit**

```bash
git add models/handcraft_receipt.py models/__init__.py models/handcraft_order.py database.py
git commit -m "feat: add HandcraftReceipt model and HandcraftPartItem received_qty/status fields"
```

---

### Task 2: Schema — 手工回收单的请求/响应 Schema

**Files:**
- Create: `schemas/handcraft_receipt.py`

- [ ] **Step 1: 创建 `schemas/handcraft_receipt.py`**

参照 `schemas/plating_receipt.py`，创建以下 schema：

```python
class HandcraftReceiptItemCreate(BaseModel):
    # 二选一
    handcraft_part_item_id: Optional[int] = None
    handcraft_jewelry_item_id: Optional[int] = None
    qty: float = Field(gt=0)
    unit: Optional[str] = "个"
    price: Optional[float] = Field(None, ge=0)    # 手工费单价
    note: Optional[str] = None

    # 自定义校验：part_item_id 和 jewelry_item_id 必须有且仅有一个

class HandcraftReceiptCreate(BaseModel):
    supplier_name: str          # strip + 非空校验
    items: List[HandcraftReceiptItemCreate] = Field(min_length=1)
    status: str = "未付款"
    note: Optional[str] = None

class HandcraftReceiptAddItemsRequest(BaseModel):
    items: List[HandcraftReceiptItemCreate] = Field(min_length=1)

class HandcraftReceiptItemUpdate(BaseModel):
    qty: float = Field(None, gt=0)
    unit: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    note: Optional[str] = None

class HandcraftReceiptStatusUpdate(BaseModel):
    status: str

class HandcraftReceiptDeliveryImagesUpdate(BaseModel):
    delivery_images: List[str] = Field(default_factory=list, max_length=9)

class HandcraftReceiptItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    handcraft_receipt_id: str
    handcraft_part_item_id: Optional[int] = None
    handcraft_jewelry_item_id: Optional[int] = None
    item_id: str                              # part_id 或 jewelry_id
    item_type: str                            # "part" 或 "jewelry"
    qty: float
    unit: Optional[str] = None
    price: Optional[float] = None
    amount: Optional[float] = None
    note: Optional[str] = None
    # Enriched fields
    item_name: Optional[str] = None           # 配件名或饰品名
    handcraft_order_id: Optional[str] = None  # 来源手工单号
    color: Optional[str] = None               # 配件颜色（仅 part 类型）

class HandcraftReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    supplier_name: str
    status: str
    total_amount: Optional[float] = None
    note: Optional[str] = None
    created_at: datetime
    paid_at: Optional[datetime] = None
    delivery_images: list[str] = Field(default_factory=list)
    items: list[HandcraftReceiptItemResponse] = Field(default_factory=list)
    cost_diffs: list[CostDiffItem] = Field(default_factory=list)
```

- [ ] **Step 2: 修改 `schemas/handcraft.py` — `HandcraftPartItemResponse` 新增字段**

新增 `received_qty` 和 `status` 字段：
```python
class HandcraftPartItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    handcraft_order_id: str
    part_id: str
    qty: float
    received_qty: Optional[float] = 0
    status: str = "未送出"
    bom_qty: Optional[float] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    note: Optional[str] = None
```

- [ ] **Step 3: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 4: Commit**

```bash
git add schemas/handcraft_receipt.py schemas/handcraft.py
git commit -m "feat: add HandcraftReceipt schemas and update HandcraftPartItemResponse"
```

---

### Task 3: Service — 核心业务逻辑

**Files:**
- Create: `services/handcraft_receipt.py`
- Modify: `services/handcraft.py` — 修改 `send_handcraft_order` 和 `delete_handcraft_order`
- Modify: `services/cost_sync.py` — 新增 `detect_handcraft_bead_cost_diffs`

- [ ] **Step 1: 修改 `services/handcraft.py` — `send_handcraft_order`**

在发出时，除了设置 `HandcraftJewelryItem.status = "制作中"`，也要设置 `HandcraftPartItem.status = "制作中"`。

在 `send_handcraft_order` 函数中，for 循环设置 jewelry status 之后添加：
```python
for pi in part_items:
    pi.status = "制作中"
```

- [ ] **Step 2: 创建 `services/handcraft_receipt.py`**

参照 `services/plating_receipt.py` 的完整逻辑，实现以下函数：

**核心辅助函数：**
- `_recalc_total(db, receipt)` — 重算 total_amount
- `_check_handcraft_order_completion(db, handcraft_order_id)` — 检查手工单是否全部收回（配件和饰品都要检查）
- `_apply_receive(db, item, item_type, qty)` — 更新 received_qty + add_stock
- `_reverse_receive(db, item, item_type, qty)` — 撤回 received_qty + deduct_stock
- `_resolve_order_item(db, item_data)` — 根据 `handcraft_part_item_id` 或 `handcraft_jewelry_item_id` 查找对应项，返回 `(order_item, item_id, item_type, handcraft_order_id)`
- `_enrich_receipt(db, receipt)` — 填充 enriched 字段（item_name, handcraft_order_id, color）

**`_apply_receive` 逻辑：**
```python
def _apply_receive(db, order_item, item_type, qty):
    order_item.received_qty = float(order_item.received_qty or 0) + qty
    if item_type == "part":
        add_stock(db, "part", order_item.part_id, qty, "手工收回")
        item_id = order_item.part_id
    else:  # jewelry
        add_stock(db, "jewelry", order_item.jewelry_id, qty, "手工收回")
        item_id = order_item.jewelry_id
    if float(order_item.received_qty) >= float(order_item.qty):
        order_item.status = "已收回"
    else:
        order_item.status = "制作中"
```

**`_reverse_receive` 逻辑：**
```python
def _reverse_receive(db, order_item, item_type, qty):
    order_item.received_qty = float(order_item.received_qty or 0) - qty
    if item_type == "part":
        deduct_stock(db, "part", order_item.part_id, qty, "手工收回撤回")
    else:
        deduct_stock(db, "jewelry", order_item.jewelry_id, qty, "手工收回撤回")
    if float(order_item.received_qty) >= float(order_item.qty):
        order_item.status = "已收回"
    else:
        order_item.status = "制作中"
```

**`_check_handcraft_order_completion` 逻辑：**
```python
def _check_handcraft_order_completion(db, handcraft_order_id):
    part_items = db.query(HandcraftPartItem).filter(...).all()
    jewelry_items = db.query(HandcraftJewelryItem).filter(...).all()
    all_items = part_items + jewelry_items
    if all(float(i.received_qty or 0) >= float(i.qty) for i in all_items):
        order = db.query(HandcraftOrder).filter(...).first()
        if order and order.status == "processing":
            order.status = "completed"
            order.completed_at = now_beijing()
    else:
        order = db.query(HandcraftOrder).filter(...).first()
        if order and order.status == "completed":
            order.status = "processing"
            order.completed_at = None
```

**CRUD 函数（参照 plating_receipt.py 的对应函数）：**
- `create_handcraft_receipt(db, supplier_name, items, status, note)` — 创建回收单
  - 校验 status 有效
  - 遍历 items，校验每项关联的手工单项存在、状态为 "制作中" 或 "已收回"
  - 校验 supplier_name 一致性（回收单的 supplier_name 必须匹配关联手工单的 supplier_name）
  - 校验 qty 不超过剩余可收回数量
  - 创建 HandcraftReceiptItem，计算 amount = qty × price
  - 调用 `_apply_receive`
  - 调用 `_check_handcraft_order_completion`
  - 计算 total_amount

- `add_handcraft_receipt_items(db, receipt_id, items)` — 添加明细
  - 回收单必须未付款
  - 同创建逻辑中的校验和库存操作

- `list_handcraft_receipts(db, supplier_name=None)` — 列表查询
- `get_handcraft_receipt(db, receipt_id)` — 单条查询（含 enrich）
- `get_handcraft_receipt_items(db, receipt_id)` — 查询明细

- `delete_handcraft_receipt(db, receipt_id)` — 删除回收单
  - 必须未付款
  - 遍历 items 调用 `_reverse_receive`
  - 重新检查订单完成状态

- `update_handcraft_receipt_status(db, receipt_id, status)` — 更新付款状态
- `update_handcraft_receipt_images(db, receipt_id, delivery_images)` — 更新图片

- `update_handcraft_receipt_item(db, receipt_id, item_id, data)` — 更新明细
  - 必须未付款
  - qty 变更时计算 diff，apply/reverse receive
  - 重算 amount 和 total_amount

- `delete_handcraft_receipt_item(db, receipt_id, item_id)` — 删除明细
  - 必须未付款
  - 不能删除最后一条明细
  - 调用 `_reverse_receive`

- `get_handcraft_receipt_supplier_names(db)` — 获取商家列表

- [ ] **Step 3: 修改 `services/cost_sync.py`**

新增 `detect_handcraft_bead_cost_diffs` 函数：

```python
def detect_handcraft_bead_cost_diffs(db: Session, receipt) -> list[dict]:
    """Detect bead_cost diffs for part items in a handcraft receipt."""
    from models.handcraft_order import HandcraftPartItem

    price_map: Dict[str, Optional[float]] = {}
    for ri in receipt.items:
        if ri.item_type != "part" or ri.price is None:
            continue
        price_map[ri.item_id] = float(ri.price)

    diffs = []
    for part_id, new_price in price_map.items():
        part = db.get(Part, part_id)
        if part is None:
            continue
        current = float(part.bead_cost) if part.bead_cost is not None else None
        if _compare(current, new_price):
            diffs.append({
                "part_id": part_id,
                "part_name": part.name,
                "field": "bead_cost",
                "current_value": current,
                "new_value": new_price,
            })
    return diffs
```

- [ ] **Step 4: 修改 `services/handcraft.py` — `delete_handcraft_order`**

删除手工单时，需要同时处理关联的 `HandcraftReceiptItem` 和 `HandcraftReceipt`。

在 `delete_handcraft_order` 中，删除配件项和饰品项之前，先查找并处理关联的回收单明细：
```python
# 查找通过 handcraft_part_item_id 或 handcraft_jewelry_item_id 关联的 receipt items
part_item_ids = [p.id for p in part_items]
jewelry_item_ids = [j.id for j in jewelry_items]
related_receipt_items = db.query(HandcraftReceiptItem).filter(
    or_(
        HandcraftReceiptItem.handcraft_part_item_id.in_(part_item_ids),
        HandcraftReceiptItem.handcraft_jewelry_item_id.in_(jewelry_item_ids),
    )
).all()

# 收集受影响的 receipt_ids
affected_receipt_ids = {ri.handcraft_receipt_id for ri in related_receipt_items}

# 撤回库存
for ri in related_receipt_items:
    if ri.item_type == "part":
        deduct_stock(db, "part", ri.item_id, float(ri.qty), "手工收回撤回")
    else:
        deduct_stock(db, "jewelry", ri.item_id, float(ri.qty), "手工收回撤回")
    db.delete(ri)
db.flush()

# 清理空的回收单，重算非空回收单的 total_amount
for receipt_id in affected_receipt_ids:
    remaining = db.query(HandcraftReceiptItem).filter(
        HandcraftReceiptItem.handcraft_receipt_id == receipt_id
    ).count()
    if remaining == 0:
        receipt = db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first()
        if receipt:
            db.delete(receipt)
    else:
        receipt = db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first()
        if receipt:
            _recalc_total(db, receipt)
```

**迁移说明：** 新的 HandcraftReceipt 完全取代 VendorReceipt 在手工单上的角色。修改步骤：
1. 删除 `delete_handcraft_order` 中所有 `VendorReceipt` 相关的查询和库存撤回代码（`order_type == "handcraft"` 的部分）
2. 删除 `_vendor_receipt_totals_for_handcraft` 辅助函数
3. 删除 legacy `received_qty` 撤回逻辑（`jewelry_received_totals` / `legacy_received` 的部分）
4. 替换为上述 HandcraftReceiptItem 的撤回逻辑
5. 生产环境中如果存在旧的 `VendorReceipt` 记录（`order_type == "handcraft"`），需要在部署前手动确认是否需要迁移到 HandcraftReceiptItem，或直接忽略（因为已经在库存中生效的不需要重复处理）

- [ ] **Step 5: 移除旧的 `receive_handcraft_jewelries`**

从 `services/handcraft.py` 中删除 `receive_handcraft_jewelries` 函数。
从 `api/handcraft.py` 中删除 `POST /{order_id}/receive` 端点及相关 schema import。
从 `schemas/handcraft.py` 中删除 `ReceiptItem` 和 `ReceiptRequest`。

- [ ] **Step 6: 运行测试，修复失败的测试**

```bash
pytest tests/ -x -q
```

需要更新的测试：
- 引用 `receive_handcraft_jewelries` 的测试 → 改为使用新的 HandcraftReceipt API
- `send_handcraft_order` 相关测试 → 验证发出后 `HandcraftPartItem.status` 也变为 `"制作中"`
- `delete_handcraft_order` 相关测试 → 验证新的 HandcraftReceiptItem 撤回逻辑

- [ ] **Step 7: Commit**

```bash
git add services/handcraft_receipt.py services/handcraft.py services/cost_sync.py api/handcraft.py schemas/handcraft.py
git commit -m "feat: add HandcraftReceipt service with receive, cost sync, and remove legacy receive endpoint"
```

---

### Task 4: API — 手工回收单端点

**Files:**
- Create: `api/handcraft_receipt.py`
- Modify: `main.py` — 注册 router
- Modify: `services/upload.py` — 添加 `ALLOWED_KINDS` 条目

- [ ] **Step 1: 创建 `api/handcraft_receipt.py`**

参照 `api/plating_receipt.py`，创建以下端点：

| Method | Endpoint | 功能 |
|--------|----------|------|
| GET | `/api/handcraft-receipts/` | 列表（可按 supplier_name 筛选） |
| GET | `/api/handcraft-receipts/suppliers` | 获取商家列表 |
| POST | `/api/handcraft-receipts/` | 创建回收单（返回含 cost_diffs） |
| POST | `/api/handcraft-receipts/{id}/items` | 添加明细（返回含 cost_diffs） |
| GET | `/api/handcraft-receipts/{id}` | 获取单条 |
| DELETE | `/api/handcraft-receipts/{id}` | 删除（必须未付款） |
| PATCH | `/api/handcraft-receipts/{id}/status` | 更新付款状态 |
| PATCH | `/api/handcraft-receipts/{id}/delivery-images` | 更新图片 |
| PUT | `/api/handcraft-receipts/{id}/items/{item_id}` | 更新明细 |
| DELETE | `/api/handcraft-receipts/{id}/items/{item_id}` | 删除明细 |

创建和添加明细端点需要调用 `detect_handcraft_bead_cost_diffs` 并将结果放入 response 的 `cost_diffs`。

- [ ] **Step 2: 修改 `main.py`**

```python
from api.handcraft_receipt import router as handcraft_receipt_router
# ...
app.include_router(handcraft_receipt_router, dependencies=[require_permission("handcraft")])
```

- [ ] **Step 3: 修改 `services/upload.py`**

在 `ALLOWED_KINDS` 中添加：
```python
"handcraft-receipts": "handcraft-receipts",
```

同时更新错误提示文案。

- [ ] **Step 4: 运行测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 5: Commit**

```bash
git add api/handcraft_receipt.py main.py services/upload.py
git commit -m "feat: add HandcraftReceipt API endpoints and register router"
```

---

### Task 5: Tests — 手工回收单 API 测试

**Files:**
- Create: `tests/test_api_handcraft_receipt.py`

- [ ] **Step 1: 编写测试**

参照电镀回收单的测试模式，覆盖以下场景：

**基本 CRUD:**
- 创建回收单（含配件项）→ 验证 201 + 库存增加 + received_qty 更新
- 创建回收单（含饰品项）→ 验证 201 + 库存增加 + received_qty 更新
- 创建回收单（混合配件和饰品项）
- 查询列表、单条查询
- 删除回收单 → 验证库存撤回

**订单完成:**
- 配件全部收回 + 饰品全部收回 → 手工单状态变 `completed`
- 仅配件全部收回，饰品未收完 → 手工单保持 `processing`

**约束校验:**
- qty 超过剩余可收回数量 → 400
- 已付款回收单不能添加/删除/修改明细
- supplier_name 不一致 → 400
- handcraft_part_item_id 和 handcraft_jewelry_item_id 同时为空 → 400
- handcraft_part_item_id 和 handcraft_jewelry_item_id 同时有值 → 400
- 不能删除最后一条明细

**付款状态:**
- 未付款 → 已付款（paid_at 设置）
- 已付款 → 未付款（paid_at 清除）

**明细更新:**
- 修改 qty → 库存差额调整
- 修改 price → amount 重算

**成本同步:**
- 创建含 price 的配件回收项 → cost_diffs 返回 bead_cost 差异

**部分收回:**
- 第一次收回部分数量 → status 保持 "制作中"
- 第二次收回剩余数量 → status 变 "已收回"

**跨手工单:**
- 一个回收单包含来自两个不同手工单的项 → 两个手工单都正确更新

辅助函数（在测试文件中）：
```python
def _create_handcraft_order(client, supplier_name="测试手工商"):
    """创建一个含配件和饰品的手工单并发出"""
    # 1. 创建配件和饰品
    # 2. 给配件入库
    # 3. 创建手工单
    # 4. 发出手工单
    # 返回 order_id, part_item_ids, jewelry_item_ids
```

- [ ] **Step 2: 运行测试**

```bash
pytest tests/test_api_handcraft_receipt.py -v
```

- [ ] **Step 3: 修复失败的测试，直到全部通过**

- [ ] **Step 4: 运行全部测试确认无回归**

```bash
pytest tests/ -x -q
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_api_handcraft_receipt.py
git commit -m "test: add HandcraftReceipt API tests"
```

---

## 前端实现计划

前端部分作为独立任务，参照电镀回收单的前端页面实现。需要创建和修改的文件：

### Task 6: 前端 — API 层 + 路由

**Files:**
- Create: `frontend/src/api/handcraftReceipts.js`
- Modify: `frontend/src/router/index.js`

- [ ] **Step 1: 创建 `frontend/src/api/handcraftReceipts.js`**

参照 `frontend/src/api/platingReceipts.js`（如存在）或直接根据后端 API 端点创建：
```javascript
import request from './request'

export const listHandcraftReceipts = (params) => request.get('/handcraft-receipts/', { params })
export const getHandcraftReceipt = (id) => request.get(`/handcraft-receipts/${id}`)
export const createHandcraftReceipt = (data) => request.post('/handcraft-receipts/', data)
export const addHandcraftReceiptItems = (id, data) => request.post(`/handcraft-receipts/${id}/items`, data)
export const deleteHandcraftReceipt = (id) => request.delete(`/handcraft-receipts/${id}`)
export const updateHandcraftReceiptStatus = (id, data) => request.patch(`/handcraft-receipts/${id}/status`, data)
export const updateHandcraftReceiptImages = (id, data) => request.patch(`/handcraft-receipts/${id}/delivery-images`, data)
export const updateHandcraftReceiptItem = (id, itemId, data) => request.put(`/handcraft-receipts/${id}/items/${itemId}`, data)
export const deleteHandcraftReceiptItem = (id, itemId) => request.delete(`/handcraft-receipts/${id}/items/${itemId}`)
export const getHandcraftReceiptSuppliers = () => request.get('/handcraft-receipts/suppliers')
```

- [ ] **Step 2: 添加路由**

在 `frontend/src/router/index.js` 中添加手工回收单的路由：
```javascript
{
  path: '/handcraft-receipts',
  component: () => import('../views/handcraft-receipts/HandcraftReceiptList.vue'),
  meta: { requiresAuth: true, permission: 'handcraft' }
},
{
  path: '/handcraft-receipts/create',
  component: () => import('../views/handcraft-receipts/HandcraftReceiptCreate.vue'),
  meta: { requiresAuth: true, permission: 'handcraft' }
},
{
  path: '/handcraft-receipts/:id',
  component: () => import('../views/handcraft-receipts/HandcraftReceiptDetail.vue'),
  meta: { requiresAuth: true, permission: 'handcraft' }
},
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/handcraftReceipts.js frontend/src/router/index.js
git commit -m "feat: add handcraft receipt API layer and routes"
```

---

### Task 7: 前端 — 创建页面

**Files:**
- Create: `frontend/src/views/handcraft-receipts/HandcraftReceiptCreate.vue`

- [ ] **Step 1: 创建 `HandcraftReceiptCreate.vue`**

参照 `frontend/src/views/plating-receipts/PlatingReceiptCreate.vue` 的结构和交互：

核心功能：
- 选择 supplier_name（从手工商家列表中选择，复用 `getHandcraftSupplierNames` API）
- 选中商家后，加载该商家下所有 `processing` 状态的手工单的配件项和饰品项（状态为 "制作中" 且有剩余可收回数量）
- 用户勾选要收回的项，填写收回数量、手工费单价
- 提交创建回收单
- 创建成功后如有 cost_diffs，弹窗提示用户是否更新配件成本

关键差异（vs 电镀回收单创建页面）：
- 列表中同时展示**配件项和饰品项**（可用 tab 或分组区分）
- 配件项显示 `price` 输入框（手工费单价）
- 饰品项的 `price` 可选填

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/handcraft-receipts/HandcraftReceiptCreate.vue
git commit -m "feat: add HandcraftReceiptCreate page"
```

---

### Task 8: 前端 — 详情页面

**Files:**
- Create: `frontend/src/views/handcraft-receipts/HandcraftReceiptDetail.vue`

- [ ] **Step 1: 创建 `HandcraftReceiptDetail.vue`**

参照 `frontend/src/views/plating-receipts/PlatingReceiptDetail.vue`：

核心功能：
- 显示回收单基本信息（supplier_name, status, total_amount, created_at, paid_at）
- 显示明细列表（区分配件项和饰品项）
- 付款状态切换（未付款 ↔ 已付款）
- 未付款状态下可编辑明细（qty, price, note）、删除明细、添加新明细
- 图片上传/展示
- 删除回收单

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/handcraft-receipts/HandcraftReceiptDetail.vue
git commit -m "feat: add HandcraftReceiptDetail page"
```

---

### Task 9: 前端 — 列表页面 + 导航入口

**Files:**
- Create: `frontend/src/views/handcraft-receipts/HandcraftReceiptList.vue`
- Modify: `frontend/src/layouts/DefaultLayout.vue` — 添加侧边栏导航项

- [ ] **Step 1: 创建 `HandcraftReceiptList.vue`**

参照电镀回收单列表页面：
- 按 supplier_name 筛选
- 显示 status, total_amount, created_at
- 点击跳转详情页
- 新建按钮跳转创建页

- [ ] **Step 2: 修改 `DefaultLayout.vue`**

在侧边栏手工单相关位置添加"手工回收单"入口。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/handcraft-receipts/ frontend/src/layouts/DefaultLayout.vue
git commit -m "feat: add HandcraftReceiptList page and sidebar navigation"
```

---

### Task 10: 前端 — 手工单详情页集成

**Files:**
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue`

- [ ] **Step 1: 更新手工单详情页**

- 配件列表新增 `received_qty` 和 `status` 列的显示
- 移除旧的"收回饰品"操作（原 `POST /handcraft/{id}/receive` 的前端调用）
- 添加关联回收单的入口/链接

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/handcraft/HandcraftDetail.vue
git commit -m "feat: update HandcraftDetail to show part received_qty and link to receipts"
```
