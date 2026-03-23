# 采购单附加费用（穿珠费用）设计

## 概述

在采购单详情页的购入明细中，为每个配件行支持附加费用子行。第一种附加费用为"穿珠费用"，后续将扩展"电镀成本"等。

## 需求

- 操作列新增 `···` 按钮，点击展开子菜单，第一个选项"穿珠费用"
- 点击后在配件行下方插入穿珠费用子行
- 子行字段：名称固定"穿珠子"，数量（自定义），单位固定"条"，单价（自定义），金额（自动算）
- 单配件穿珠成本 = 穿珠金额 / 配件购入数量，最多保留 7 位小数，不可手动修改
- 穿珠费用计入采购单总金额
- 每个配件行每种费用类型最多一条
- 数据持久化到后端数据库（含 unit_cost）
- 已付款状态下不可新增/编辑/移除

## 数据模型

新建 `purchase_order_item_addon` 表：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | 自增主键 |
| `purchase_order_item_id` | Integer FK → purchase_order_item.id | 所属配件行 |
| `type` | String, NOT NULL | 费用类型，如 `"bead_stringing"`（穿珠），后续 `"plating_cost"`（电镀）|
| `qty` | Numeric(10,4), NOT NULL | 数量，独立于配件购入数量 |
| `unit` | String | 单位，穿珠默认 `"条"` |
| `price` | Numeric(18,7), NOT NULL | 单价 |
| `amount` | Numeric(18,7) | 金额 = qty × price，后端计算 |
| `unit_cost` | Numeric(18,7) | 单配件成本 = amount / 父配件 qty，后端计算，最多 7 位小数 |

约束：
- `(purchase_order_item_id, type)` 唯一约束
- `amount` 和 `unit_cost` 由后端自动计算，前端只展示

SQLAlchemy model 放在 `models/purchase_order.py` 中，与 `PurchaseOrderItem` 同文件。

关系：
- `PurchaseOrderItem` 添加 `relationship("PurchaseOrderItemAddon", backref="purchase_order_item", cascade="all, delete-orphan")` — 删除配件行时自动级联删除其 addon
- 新表通过 `Base.metadata.create_all()` 自动创建，无需 `ensure_schema_compat` 处理
- 不同费用类型的 `unit` 默认值不同（穿珠 `"条"`，未来电镀可能不同），前端按 type 设置默认值，后端不硬编码

## API 设计

基础路径：`/purchase-orders/{po_id}/items/{item_id}/addons`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `.../addons` | 新增附加费用，body: `{ type, qty, unit, price }` |
| `PUT` | `.../addons/{addon_id}` | 修改 qty/price |
| `DELETE` | `.../addons/{addon_id}` | 移除附加费用 |

- addon 数据随 `GET /purchase-orders/{po_id}` 返回，嵌套在每个 item 的 `addons` 字段
- 所有写操作校验采购单非"已付款"状态
- POST 校验同一 item 下同 type 不重复
- 创建/修改/删除后自动重算采购单 total_amount — 修改现有 `_recalc_total` 函数，使其同时合计配件 amount 和所有 addon amount
- 删除配件行时，其 addon 通过 SQLAlchemy cascade 自动删除，无需额外处理

## 前端交互

### 操作列改造

- 现有"修改""删除"按钮后，新增 `···` 按钮
- 点击弹出 NPopover 子菜单，第一个选项"穿珠费用"
- 该配件已有穿珠费用行时，选项置灰不可点击
- 已付款状态下 `···` 按钮不显示

### 穿珠费用子行

- 点击"穿珠费用"后，配件行下方插入子行，初始为编辑态（数量和单价输入框）
- 用户填写后点"保存"调 POST 接口
- 保存成功后子行切换为展示态
- 展示态下双击数量/单价可编辑（调 PUT）
- 子行有"移除"按钮（调 DELETE，二次确认）

### 子行 UI 差异

- 淡蓝渐变背景（`linear-gradient(90deg, #f0f7ff, #fafcff)`）
- 左侧 `└` 缩进符，体现归属关系
- 行高更小（padding 6px vs 配件行 12px）
- 字号略小（13px vs 14px）
- 配件列显示蓝色"穿珠子"文字
- 单位列固定显示"条"
- 备注列位置显示蓝色标签：`单配件穿珠成本: ¥x.xxxxxxx`
- 操作列只有"移除"按钮

### 数据流

- `GET /purchase-orders/{po_id}` 返回的每个 item 带 `addons` 数组
- 前端根据 addons 在对应配件行下方渲染子行（NDataTable 的 expand 或 flat data 方式）
- 写操作成功后 reload 整个采购单数据
