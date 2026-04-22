# 电镀发出 — 关联电镀回收单 设计文档

## 背景

当前电镀发出和电镀回收的联动性较差。用户只能从回收单创建时选择发出明细（单向），无法从发出侧直接关联到已有的回收单，也无法从发出明细快速跳转到对应的回收单。

## 目标

在电镀单详情的明细表格中新增"关联电镀单"列，支持：
1. 将发出明细关联到已有的电镀回收单
2. 查看已关联的回收单并快速跳转
3. 取消关联（删除回收单中对应的明细）

## 需求概述

### 表格列展示

在现有"关联订单"列右侧新增"关联电镀单"列，根据回收状态展示不同内容：

| 状态 | 条件 | 展示 |
|------|------|------|
| 未送出 | item.status = "未送出" | 显示 "—"，不可操作 |
| 未回收 | item.status ∈ {"电镀中","已收回"} 且 received_qty = 0 | 显示"关联电镀单"文字按钮 |
| 部分回收 | 0 < received_qty < qty | 已关联单号列表（每个带 × 删除按钮）+ "+" 按钮 + "已收 X / Y" 进度提示 |
| 全部回收 | received_qty ≥ qty | 已关联单号列表（可点击跳转，无 × 删除按钮）+ "已全部回收" 提示 |

### 关联弹窗（一步式）

点击"关联电镀单"或"+"按钮弹出弹窗，所有字段同屏展示：

**弹窗布局（从上到下）：**

1. **当前配件信息**（灰色背景条）：配件编号、名称、发出数量、已收数量、剩余可收数量
2. **选择回收单**（radio 列表）：
   - 仅显示同供应商、未付款的回收单
   - 排除已关联过该 `plating_order_item_id` 的回收单
   - 每条显示：回收单号、供应商、创建日期、已有明细数、付款状态
   - 如果没有可选回收单，显示提示文字
3. **回收数量**（必填）：输入框右侧显示"最多 {remaining}"
4. **回收单价**（必填）：输入框右侧显示单位"元/{unit}"
5. **收回配件**（自动填充，只读）：自动取 `receive_part_id`，若无则取 `part_id`
6. **按钮**：取消 / 确认关联

**校验规则：**
- 未选回收单 → toast "请选择回收单"
- 未填数量 → toast "请输入回收数量"
- 数量 > 剩余可收 → toast "回收数量不能超过剩余可收数量"
- 未填单价 → toast "请输入回收单价"
- 确认成功 → toast 成功提示，刷新明细列表

### 取消关联

- 部分回收状态下，每个已关联单号后显示 × 删除按钮
- 点击 × → 二次确认弹窗（提示将回滚库存）→ 调用删除接口 → 刷新列表
- 全部回收状态下不显示 × 删除按钮（回滚风险大）

### 跳转高亮

点击已关联的回收单号，跳转到回收单详情页并高亮对应行：

- 路由：`/plating-receipts/{receipt_id}?highlight={receipt_item_id}`
- 回收单详情页读取 `highlight` query 参数
- `scrollIntoView` 滚动到目标行
- 绿色背景闪烁动画，持续 5 秒，约 3 次，频率低不刺眼
- 左侧绿色指示条辅助定位
- CSS `animation` + `@keyframes` 实现，无需 JS 定时器

## 后端 API 设计

### 新增接口

#### 1. 获取可选回收单列表

```
GET /api/plating/{order_id}/items/{item_id}/available-receipts
```

**逻辑：**
- 查询 `plating_receipt` 表
- 筛选条件：`vendor_name` = 电镀单的 `supplier_name`，`status` = "未付款"
- 排除：已有 `plating_receipt_item.plating_order_item_id = item_id` 的回收单
- 返回字段：`id`、`vendor_name`、`created_at`、`item_count`（已有明细数）

**响应示例：**
```json
[
  {
    "id": "ER-0012",
    "vendor_name": "张三电镀厂",
    "created_at": "2026-04-18T10:00:00",
    "item_count": 3
  }
]
```

#### 2. 关联到回收单

```
POST /api/plating/{order_id}/items/{item_id}/link-receipt
```

**请求体：**
```json
{
  "receipt_id": "ER-0012",
  "qty": 500,
  "price": 0.35
}
```

**后端逻辑（顺序）：**
1. 校验 `plating_order_item` 存在且属于该 order
2. 校验 item status ∈ {"电镀中", "已收回"}
3. 校验 `qty` ≤ `item.qty - item.received_qty`（剩余未收数量）
4. 校验 `plating_receipt` 存在、status = "未付款"
5. 校验回收单 `vendor_name` = 电镀单 `supplier_name`
6. 校验该回收单中不存在相同 `plating_order_item_id` 的记录
7. 自动取 `part_id` = `item.receive_part_id or item.part_id`
8. 调用现有 `add_plating_receipt_items` 服务函数，传入构造好的 item 数据
9. 返回创建的 `plating_receipt_item` 信息

**错误响应：**
- 400：校验失败（附具体原因）
- 404：order/item/receipt 不存在

#### 3. 批量查询关联数据

```
GET /api/plating/{order_id}/receipt-links
```

**逻辑：**
- 查询该电镀单所有 items 关联的 `plating_receipt_item` 记录
- JOIN `plating_receipt` 获取回收单信息

**响应示例：**
```json
{
  "42": [
    {
      "receipt_id": "ER-0012",
      "receipt_item_id": 101,
      "qty": 500,
      "price": 0.35
    }
  ],
  "43": [
    {
      "receipt_id": "ER-0010",
      "receipt_item_id": 88,
      "qty": 200,
      "price": 0.50
    },
    {
      "receipt_id": "ER-0011",
      "receipt_item_id": 92,
      "qty": 100,
      "price": 0.45
    }
  ]
}
```

key 为 `plating_order_item.id`，value 为关联的回收单明细列表。

### 复用接口

**取消关联**复用现有接口：

```
DELETE /api/plating-receipts/{receipt_id}/items/{receipt_item_id}
```

已有完整的库存回滚逻辑（`_reverse_receive`、更新 `received_qty`、检查订单完成状态），无需额外开发。

## 前端改动

### PlatingDetail.vue

1. 新增 `itemReceiptLinks` 响应式变量（map 结构），页面加载时调用 `GET /receipt-links` 填充
2. `itemColumns` 数组中在"关联订单"列后新增"关联电镀单"列
3. 列渲染函数 `renderReceiptLinkCell(row)` 根据回收状态渲染不同内容
4. 新增关联弹窗组件（NModal），包含回收单选择 + 数量 + 价格输入
5. 新增取消关联的二次确认逻辑
6. 关联/取消操作后刷新 `itemReceiptLinks` 和明细列表

### PlatingReceiptDetail.vue

1. 读取 URL query 参数 `highlight`
2. 如果存在 highlight 参数，在数据加载完成后：
   - 找到目标行 DOM 元素
   - `scrollIntoView({ behavior: 'smooth', block: 'center' })`
   - 添加 CSS class 触发闪烁动画
3. 新增 CSS keyframes 动画：绿色背景渐变闪烁，5 秒后自动停止

### API 层（frontend/src/api/plating.js）

新增函数：
- `getAvailableReceipts(orderId, itemId)` → `GET /api/plating/{order_id}/items/{item_id}/available-receipts`
- `linkReceipt(orderId, itemId, data)` → `POST /api/plating/{order_id}/items/{item_id}/link-receipt`
- `getReceiptLinks(orderId)` → `GET /api/plating/{order_id}/receipt-links`

## 边界场景处理

| 场景 | 处理方式 |
|------|---------|
| 无可选回收单 | 弹窗中显示"暂无可用的回收单"提示文字，确认按钮禁用 |
| 同一 item 关联到同一回收单两次 | 后端校验 `plating_order_item_id` 唯一性，返回 400 |
| 电镀单 pending 状态 | "关联电镀单"列显示 "—"，仅 processing/completed 状态才可操作 |
| 取消关联导致回收单为空 | 复用现有逻辑：删除回收单最后一个 item 时提示"不能删除最后一项，请删除整个回收单" |
| 关联后回收单总金额变化 | 复用现有逻辑：`add_plating_receipt_items` 已自动重算 `total_amount` |
| 并发操作（两人同时关联同一 item） | 后端 `qty ≤ remaining` 校验在事务内执行，第二个请求会因数量超限失败 |
