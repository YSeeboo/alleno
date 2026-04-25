# 订单支持购买配件 (Order Part Items) — 设计稿

**日期**：2026-04-25
**状态**：待实现
**背景**：当前 `OrderItem` 只能引用饰品 (`jewelry_id`)，但实际业务中存在客户单独购买配件的场景（如：链条按米卖、零散小配件出货）。需要在订单内同时支持饰品销售和配件销售。

---

## 1. 需求总览

| 决策点 | 结论 |
|---|---|
| 销售模式 | 一张订单可同时含饰品 + 配件（混合销售） |
| 配件下游流程 | 完全等同饰品（除无 BOM）：进 TodoList、备货模拟、配货 |
| TodoList 同 part 合并 | BOM 来源 + 直购合并成一行，"来源"列区分 |
| 配件售价来源 | `part.wholesale_price` 默认填入；下单时手填值回写 part 表 |
| 库存扣减时机 | 订单"已完成"时自动扣 `part` 库存；状态回滚时反向恢复 |
| UI 布局 | 饰品 / 配件分组卡片，"+ 添加" 按钮位于卡片右上角 |
| OrderItem 表结构 | 单表 + nullable `jewelry_id` / `part_id` + DB CHECK XOR |
| 配件下单数量 | 整数（与饰品相同），保持 `OrderItem.quantity` 为 int |

---

## 2. 数据模型变更

### 2.1 `Part`（新增字段）

```python
class Part(Base):
    ...
    wholesale_price = Column(Numeric(18, 7), nullable=True)
```

### 2.2 `OrderItem`（修改 + 新增字段 + DB 约束）

```python
class OrderItem(Base):
    __tablename__ = "order_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("order.id"), nullable=False, index=True)
    jewelry_id = Column(String, ForeignKey("jewelry.id"), nullable=True)   # 改 nullable
    part_id    = Column(String, ForeignKey("part.id"),    nullable=True)   # 新增
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(18, 7), nullable=False)
    remarks = Column(Text, nullable=True)
    customer_code = Column(String, nullable=True)   # 仅适用 jewelry 项

    __table_args__ = (
        CheckConstraint(
            "(jewelry_id IS NULL) <> (part_id IS NULL)",
            name="ck_order_item_jewelry_xor_part"
        ),
    )
```

### 2.3 迁移策略

走现有 `database.ensure_schema_compat()` 的 additive 模式：
- `ALTER TABLE part ADD COLUMN wholesale_price NUMERIC(18,7) NULL`
- `ALTER TABLE order_item ALTER COLUMN jewelry_id DROP NOT NULL`
- `ALTER TABLE order_item ADD COLUMN part_id VARCHAR REFERENCES part(id) NULL`
- `ALTER TABLE order_item ADD CONSTRAINT ck_order_item_jewelry_xor_part CHECK ((jewelry_id IS NULL) <> (part_id IS NULL))`

启动时检查列/约束是否存在，缺失则补齐。已有 OrderItem rows 全都 `jewelry_id NOT NULL / part_id NULL`，对 CHECK 天然有效。

### 2.4 `InventoryLog`

无需变更。已支持 `item_type='part'` 和 `'jewelry'`，配件项扣减直接复用 `deduct_stock(db, "part", part_id, qty, "订单出货")`。

---

## 3. Service 层

### 3.1 `services/order.py`

#### `create_order` / `add_order_item`

接受 items 时每项 `jewelry_id` 和 `part_id` 二选一：
- 为 part 项时，校验 `part_id` 存在；若 `unit_price != part.wholesale_price` 则回写 `part.wholesale_price = unit_price`
- 为 jewelry 项时，行为不变

#### `update_order_item`

允许修改 part 项的 `quantity` / `unit_price` / `remarks`。
- 若 `unit_price` 变更，回写 `part.wholesale_price`
- `customer_code` 仅适用 jewelry 项；对 part 项设 customer_code 抛 `ValueError("配件项不允许设置客户货号")`

#### `update_order_status`

新增逻辑（核心）：

```python
# Δ 状态 → "已完成"
if status == "已完成" and order.status != "已完成":
    part_items = [i for i in items if i.part_id is not None]
    # 1) Dry-run 预校验所有 part 项库存
    needed = aggregate_qty_by_part_id(part_items)
    stocks = batch_get_stock(db, "part", list(needed.keys()))
    insufficient = [(pid, n, stocks.get(pid, 0)) for pid, n in needed.items() if stocks.get(pid, 0) < n]
    if insufficient:
        raise ValueError(f"配件库存不足：{format(insufficient)}")
    # 2) 实际扣减
    for pid, qty in needed.items():
        deduct_stock(db, "part", pid, qty, "订单出货")
    # 3) 走原 generate_cost_snapshot

# Δ "已完成" → 任意其他状态
elif order.status == "已完成" and status != "已完成":
    part_items = [i for i in items if i.part_id is not None]
    needed = aggregate_qty_by_part_id(part_items)
    for pid, qty in needed.items():
        add_stock(db, "part", pid, qty, "订单出货撤回")
```

**幂等性**：状态从"已完成" → "已取消" → "已完成"，每次扣减/恢复对称，不会重复或漏。

#### `get_parts_summary`（TodoList 聚合）

在现有 BOM 累加之后，**追加直购贡献**：
```python
# 现有
total_map[pid] = Σ(BOM 来源)  # 来自 jewelry items 的 BOM 展开

# 新增
direct_map[pid] = Σ(本订单中 part_id == pid 的 OrderItem.quantity)
total_map[pid] += direct_map[pid]

# source_jewelries 列表追加 direct 类型条目
source_map[pid].append({
    "source_type": "direct",
    "jewelry_id": None,
    "qty_per_unit": None,
    "order_qty": direct_qty,
    "subtotal": direct_qty,
})
# 现有 BOM 来源同步加 source_type="jewelry"
```

#### `_calc_global_part_demand`（跨订单 part 全局占用）

同样追加：所有 active 订单的 part 直购需求要计入 `global_demand_map`，否则跨订单的 part 库存竞争统计会偏小。

### 3.2 `services/picking.py`（备货模拟）

`build_picking_rows` 在生成 part variants 时，追加直购的 part：
- 直购的 part 作为额外 `PickingVariant`(`qty_per_unit=quantity`, `units_count=1`)
- `is_composite_child=False`
- 同一 part 若既有 BOM 又有直购，append 一个新 variant 行（不合并），保持"来源"清晰

### 3.3 `services/order_cost_snapshot.py`

订单完成时为 part 项生成快照行：
- `cost = part.unit_cost × qty`
- `revenue = unit_price × qty`
- 加入订单总成本/总利润计算

### 3.4 不变更的服务

- `services/handcraft.py`、`services/plating.py`：直购 part 不进入这些上游加工链路；它们继续只看 `OrderItem.jewelry_id` → BOM → part
- `services/bom.py`：BOM 概念只属于 jewelry，不变
- `services/purchase_order.py`：采购入库 `add_stock(db, "part", ...)` 行为不变；TodoList 缺口（含直购）通过库存层面自然被采购入库覆盖

---

## 4. API + Schema

### 4.1 `schemas/order.py`

#### `OrderItemCreate`

```python
class OrderItemCreate(BaseModel):
    jewelry_id: Optional[str] = None
    part_id: Optional[str] = None
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    remarks: Optional[str] = None

    @model_validator(mode="after")
    def _xor(self):
        if (self.jewelry_id is None) == (self.part_id is None):
            raise ValueError("jewelry_id 和 part_id 必须且只能填一个")
        return self
```

#### `OrderItemResponse`（增字段）

```python
class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: str
    jewelry_id: Optional[str] = None    # 改 Optional
    part_id: Optional[str] = None       # 新增
    quantity: int
    unit_price: float
    remarks: Optional[str] = None
    customer_code: str | None = None
    # Enriched fields (populated by service when serving response)
    part_name: Optional[str] = None
    part_image: Optional[str] = None
    part_unit: Optional[str] = None
```

#### `OrderItemUpdate`

字段不变，但 service 层校验：customer_code 仅 jewelry 项可设。

### 4.2 `schemas/part.py`

`PartResponse` / `PartCreate` / `PartUpdate` 加 `wholesale_price: Optional[float] = None`。

### 4.3 API 端点

不新增端点，全部复用现有：
- `POST /orders` —— items 里二选一
- `POST /orders/{id}/items` —— 同
- `PATCH /orders/{id}/items/{item_id}` —— 同
- `DELETE /orders/{id}/items/{item_id}` —— 同
- `PATCH /orders/{id}/status` —— → "已完成" 触发库存扣减；不足返回 HTTP 400

### 4.4 TodoList 响应（向后兼容）

`PartsSummaryItemResponse.source_jewelries` 列表条目类型扩展：
```python
class SourceJewelryItem(BaseModel):
    source_type: Literal["jewelry", "direct"] = "jewelry"   # 新增字段，默认 jewelry 保持兼容
    jewelry_id: Optional[str] = None    # 改 Optional（direct 时为 None）
    jewelry_name: str = ""
    qty_per_unit: Optional[float] = None  # 改 Optional（direct 时为 None）
    order_qty: int
    subtotal: float
```

---

## 5. 前端

### 5.1 `frontend/src/views/orders/OrderCreate.vue`

重构为分组卡片布局：
```
[客户信息]
┌── 💎 饰品明细 (n 项)         小计 ¥xxx [+ 添加饰品]──┐
│ 表格：饰品 | 数量 | 单价 | 小计 | 备注 | ×      │
└─────────────────────────────────────────────────┘
┌── 🔧 配件明细 (n 项)         小计 ¥xxx [+ 添加配件]──┐
│ 表格：配件 | 数量 | 单价 | 小计 | 备注 | ×      │
└─────────────────────────────────────────────────┘
[订单总额 ¥xxx]                       [提交订单]
```

数据结构：
```js
const jewelryItems = ref([])  // [{jewelry_id, quantity, unit_price, remarks}]
const partItems    = ref([])  // [{part_id, quantity, unit_price, remarks}]

const submit = () => {
  const items = [
    ...jewelryItems.value.map(i => ({ ...i, part_id: null })),
    ...partItems.value.map(i => ({ ...i, jewelry_id: null })),
  ]
  // POST /orders with { customer_name, items, created_at }
}
```

**"+ 添加" 按钮**：弹出 picker 对话框（jewelry / part）。配件 picker 选中后：
```js
items[idx].unit_price = part.wholesale_price ?? 0
```

### 5.2 `frontend/src/views/orders/OrderDetail.vue`

同样的分组：
- 饰品明细卡片：含现有 customer_code、批量编号、status 联动等所有功能
- 配件明细卡片：无 customer_code、无批量编号；单价改动时调 PATCH，后端会回写 part.wholesale_price

### 5.3 TodoList 视图

`source_jewelries` 列表渲染时区分 `source_type`：
- `"jewelry"` → 显示原样（饰品名 × 数量）
- `"direct"` → 显示 "客户直购 × N"

### 5.4 配货模拟视图

直购 part 作为额外 variant 行展示，左上无 `is_composite_child` 标识。

### 5.5 新组件

`frontend/src/components/PartPickerDialog.vue`（参考现有 jewelry-picker）：
- 支持搜索、按类别筛选
- 选中返回 part 完整对象（含 wholesale_price、unit、image）

---

## 6. 边界情况 & 错误处理

| 场景 | 处理 |
|---|---|
| 状态 → "已完成" 但 part 库存不足 | 整体 reject，raise `ValueError`，状态不变；前端显示具体不足的 part 与差额 |
| "已完成" → 任意其他状态（含"已取消"）| 自动 add_stock 回滚所有 part 项 |
| 重复扣减/恢复 | 状态切换对称扣减，幂等 |
| 对 part 项设 customer_code | raise ValueError；前端配件表格不展示该列 |
| 同一 part 既来自 BOM 又来自直购 | TodoList 合并行，source_jewelries 列表中两类来源都展示；备货模拟分开 variant 展示 |
| 跨订单 part 全局占用 | `_calc_global_part_demand` 同步累加各 active 订单的直购需求 |
| 直购 part 走采购单 | OrderItemLink 不变（不引入 direct 链接）；采购入库通过库存层面覆盖直购需求 |
| OrderItem 双 ID 双填 / 双空 | DB CHECK 兜底 + Pydantic XOR 校验前置 reject |
| `unit_price` 回写 `part.wholesale_price` | 创建/修改 part 项时同步回写（覆盖式，不区分是否为空） |

---

## 7. 测试

### 新增测试文件
- `tests/test_api_order_part_items.py`
- `tests/test_service_order_part_items.py`

### 关键 case

**Service 层**
- create_order：仅 jewelry / 仅 part / 混合
- create_order：part 项 unit_price 与 part.wholesale_price 不一致 → 回写
- update_order_item：part 项 unit_price 修改 → 回写
- update_order_item_customer_code：part 项 → ValueError
- batch_fill_customer_code：含 part 项 → ValueError
- get_parts_summary：BOM + 直购合并、source_jewelries 含两种 source_type
- _calc_global_part_demand：跨订单累加直购需求
- update_order_status → "已完成"：part 库存正确扣减 + cost snapshot 含 part 行
- update_order_status → "已完成"：任一 part 库存不足 → 整体 reject、状态回滚
- update_order_status：已完成 → 已取消 → part 库存回滚
- update_order_status：已完成 → 生产中 → 已完成 → 幂等

**API 层**
- POST /orders：XOR 校验失败（双填、双空）→ 400
- DB CHECK 验证：直接 db.add OrderItem 双填 → IntegrityError
- PATCH /orders/{id}/status → "已完成" 库存不足 → 400
- 配货模拟接口：返回 part 直购 variant

**回归覆盖**
- `tests/test_api_orders.py`、`tests/test_service_order_*.py`、`tests/test_picking_*.py`、`tests/test_inventory_log.py` 全跑通

---

## 8. 不在本次范围

- 配件销售相关报表（如"配件销售 Top N"）—— 后续单独立项
- 配件售价历史记录（`part.wholesale_price` 只存最新值，不存历史）
- Bot / Agent 工具增加"创建含配件订单"能力 —— 后续按需扩展
- OrderItemLink 的 direct part 维度（直购不进入生产链路追踪）
