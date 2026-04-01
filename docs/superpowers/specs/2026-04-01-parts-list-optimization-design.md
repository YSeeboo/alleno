# 配件清单优化 设计文档

## 背景

当前订单配件清单为扁平结构，一个订单只有一份配件清单，不支持按饰品分批生成和分配给不同手工商家。需要优化为支持多批次指定生成、关联手工商家、以及饰品状态追踪。

## 功能点总览

1. 饰品清单增加"状态"列
2. 指定配件清单生成（弹窗勾选饰品）
3. 配件清单折叠结构（大行/小行）
4. 配件汇总（BOM）增加"剩余需求量"
5. 备货进度逻辑修改

---

## 一、数据模型

### 新增表

**`order_todo_batch`** — 指定配件清单批次

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增 |
| order_id | String FK → order.id | 所属订单 |
| handcraft_order_id | String FK → handcraft_order.id, nullable | 关联的手工单 |
| created_at | DateTime | 创建时间 |

**`order_todo_batch_jewelry`** — 批次中勾选的饰品

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增 |
| batch_id | Integer FK → order_todo_batch.id | 所属批次 |
| jewelry_id | String FK → jewelry.id | 饰品 |
| quantity | Integer | 该批次中的数量（首次=下单数量，再次=剩余未分配数量） |

### 修改现有表

**`order_todo_item`** 增加字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| batch_id | Integer FK → order_todo_batch.id, nullable | 所属批次 |

### 扩展性说明

当前批次只关联手工单（`handcraft_order_id`）。未来如需关联电镀单或采购单，只需在 `order_todo_batch` 上新增对应的 nullable FK 字段（如 `plating_order_id`），与现有 `OrderItemLink` 的设计风格一致。

---

## 二、饰品状态计算

状态不存储，实时计算。对订单中每个 `OrderItem`，按优先级判定：

| 优先级 | 状态 | 条件 |
|--------|------|------|
| 1（最高） | 完成备货 | `get_stock("jewelry", jewelry_id) >= order_item.quantity` |
| 2 | 等待手工返回 | 存在关联的 HandcraftJewelryItem（通过 OrderItemLink 或 batch.handcraft_order_id），且条件1不满足 |
| 3 | 等待发往手工 | 该饰品所有 BOM 配件库存均 >= 所需数量（所需 = BOM qty_per_unit × 下单数量），且条件2不满足 |
| 4（默认） | 等待配件备齐 | 以上条件均不满足 |

关键决策：
- 库存使用全局库存（`inventory_log` 的 `SUM(change_qty)`），不做排他预留
- "完成备货"只看饰品库存是否充足，不要求必须关联手工单

---

## 三、指定配件弹窗

点击【生成指定配件清单】按钮弹出。

### 显示列

| 列 | 说明 |
|----|------|
| 勾选列 | 表头有全选框（只全选可勾选行） |
| 饰品编号 | OrderItem.jewelry_id |
| 饰品 | 图片 + 名称 |
| 数量 | 见下方逻辑 |

### 数量列逻辑

- 首次选择（该饰品从未关联过手工单）：显示订单下单数量
- 有剩余未分配：显示剩余未分配数量（下单数量 - 该订单关联的所有手工单中该饰品的 `HandcraftJewelryItem.qty` 之和），附带原始数量参考

### 可选/不可选逻辑

**不可勾选**（行置灰，checkbox disabled，排在底部）：
- 饰品状态为"等待手工返回"或"完成备货"
- 该饰品已全部分配（手工单中 `SUM(HandcraftJewelryItem.qty) >= 下单数量`）

**可勾选**：以上条件均不满足的饰品。

### 生成确认

点击【生成配件清单】后弹出二次确认："会根据已选择的饰品生成指定的配件清单，确定要生成吗？"

---

## 四、配件清单折叠结构

### 大行（批次级别）

每个 `OrderTodoBatch` 对应一个大行，显示：
- 批次标题 + 创建时间
- 【导出 PDF】按钮
- 关联状态：
  - 未关联：显示【关联手工商家】按钮
  - 已关联：显示"✓ 已分配给：（手工商家名）"文字标签（加强提示效果，按钮消失）
  - 手工单被删除：恢复为【关联手工商家】按钮

大行可折叠/展开，切换动画要丝滑。

### 小行（展开后的明细）

分为两部分：

**头部明细 — 已选饰品横排**
- 从左到右排列，图片在上、编号在下
- 悬浮在饰品区域 >1s 显示气泡，鼠标移开后消失
- 气泡显示：配件名称、需要数量、库存数量、缺口

**配件明细 — 表格**

| 列 | 说明 |
|----|------|
| 配件编号 | part_id |
| 配件 | 图片 + 名称 |
| 需要数量 | 该批次所选饰品的 BOM 汇总 |
| 库存数量 | 全局库存 |
| 缺口 | max(0, 需要数量 - 库存数量) |
| 生产单状态 | 关联的电镀/手工/采购单状态（复用现有 OrderItemLink） |
| 完成 | 库存 >= 需要数量 |

---

## 五、关联手工商家

### 弹窗

- 输入框支持搜索已有手工商家（Supplier type="handcraft"）
- 输入名称不存在时显示"+ 新建商家"选项
- 点击【确定】→ 创建手工单 → 前端跳转手工单详情页
- 点击【取消】→ 关闭弹窗

### 后端逻辑（link-supplier）

1. 查找或创建 Supplier（type="handcraft"）
2. 创建 HandcraftOrder（supplier_name, status="pending"）
3. 迁移批次配件 → HandcraftPartItem（qty = 批次汇总数量，用户可在手工单中调整）
4. 迁移批次饰品 → HandcraftJewelryItem（qty = batch_jewelry.quantity，即下单数量或剩余未分配数量，用户可在手工单中调整）
5. 自动创建 OrderItemLink 关联
6. 更新 `batch.handcraft_order_id`
7. 返回手工单 ID

---

## 六、配件汇总（BOM）优化

在现有的配件汇总表格中增加一列"剩余需求量"：

| 列 | 说明 |
|----|------|
| 总需求量 | 所有饰品的 BOM 汇总（不变） |
| 剩余需求量（新增） | 总需求量 - 已到达"等待发往手工"及之后状态的饰品对应的配件需求量 |

即：状态为"等待发往手工"、"等待手工返回"、"完成备货"的饰品，其 BOM 配件需求从剩余需求量中扣减。

---

## 七、备货进度修改

- 文案："备料进度"→"备货进度"
- 计算逻辑：`x / y`
  - x = 状态为"完成备货"的饰品种类数
  - y = 订单中所有饰品的种类数（去重后的 jewelry_id 数量）
- 颜色：x < y 蓝色，x = y 绿色

---

## 八、API 设计

### 新增接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/orders/{order_id}/todo-batch` | 创建指定配件清单批次 |
| GET | `/orders/{order_id}/todo-batches` | 获取订单所有批次（含小行明细） |
| POST | `/orders/{order_id}/todo-batch/{batch_id}/link-supplier` | 关联手工商家，创建手工单 |
| GET | `/orders/{order_id}/jewelry-status` | 获取订单饰品状态列表 |
| GET | `/orders/{order_id}/jewelry-for-batch` | 获取可勾选饰品列表（用于弹窗） |

### 修改接口

| 方法 | 路径 | 变更 |
|------|------|------|
| GET | `/orders/{order_id}/todo` | 保留兼容，新前端改用 todo-batches |
| GET | `/orders/{order_id}/parts-summary` | 返回增加 `remaining_qty` 字段 |
| GET | `/orders/{order_id}/progress` | 逻辑改为：completed = 完成备货饰品种类数，total = 饰品种类数 |
| GET | `/orders/{order_id}/todo-pdf` | 增加 `batch_id` 参数，按批次导出 |

### 请求/响应格式

**POST `/orders/{order_id}/todo-batch`**
```
Request:  { jewelry_ids: [str] }
Response: { batch_id: int, items: [OrderTodoItemResponse] }
```

**POST `.../link-supplier`**
```
Request:  { supplier_name: str }
Response: { handcraft_order_id: str }
```

**GET `/orders/{order_id}/jewelry-status`**
```
Response: [{ jewelry_id: str, jewelry_name: str, quantity: int, status: str }]
```

**GET `/orders/{order_id}/jewelry-for-batch`**
```
Response: [{
  jewelry_id: str,
  jewelry_name: str,
  jewelry_image: str,
  order_quantity: int,
  allocated_quantity: int,      // 已分配给手工单的总量
  remaining_quantity: int,      // 剩余未分配数量
  selectable: bool,             // 是否可勾选
  disabled_reason: str | null   // 不可勾选原因
}]
```

---

## 九、PDF 导出变化

- 改为按批次导出（`batch_id` 参数）
- 表头新增："指定手工：（手工商家名称）"，批次未关联手工商家时不显示
- 数据范围：只导出该批次的配件明细
- 其余格式（标题、订单信息、表格列）不变
