# 生产损耗确认 设计文档

## 背景

电镀/手工加工过程中会产生正常损耗，收回数量可能小于发出数量。当前系统要求 `received_qty >= qty` 才能结单，无法处理损耗场景。需要增加"确认损耗"机制，让用户确认差额后结单，同时保留损耗记录供追溯和对账。

## 核心流程

```
发出 100 → 收回 80 → 差额 20
                        ↓
               商家补做 → 收回 15（通过现有收回功能）
                        ↓
                   剩余差额 5
                        ↓
              确认损耗 5 → 配件行标记"已收回" → 可结单
```

损耗确认是**最终操作**——只有确定不再追回时才确认。之前的补做回来用现有收回流程即可。

## 数据模型

### 新增表

**`production_loss`** — 损耗记录

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增 |
| order_type | String | "plating" 或 "handcraft" |
| order_id | String | 电镀/手工单 ID |
| item_id | Integer | PlatingOrderItem.id 或 HandcraftPartItem.id 或 HandcraftJewelryItem.id |
| item_type | String | "plating_item"、"handcraft_part"、"handcraft_jewelry" |
| part_id | String, nullable | 配件 ID（配件类损耗时填） |
| jewelry_id | String, nullable | 饰品 ID（饰品类损耗时填） |
| loss_qty | Numeric(10,4) | 损耗数量 |
| deduct_amount | Numeric(18,7), nullable | 扣款金额（不扣款则为 null 或 0） |
| reason | Text, nullable | 损耗原因 |
| note | Text, nullable | 备注 |
| created_at | DateTime | 确认时间 |

### 不修改现有表

- `PlatingOrderItem`、`HandcraftPartItem`、`HandcraftJewelryItem` 不加字段
- 确认损耗时直接将 `received_qty` 加上损耗数量，使 `received_qty >= qty`，触发现有的状态变更逻辑（"已收回"）和结单检查

## 确认损耗逻辑

1. 计算当前差额：`loss_qty = qty - received_qty`（用户可修改，但不能超过差额）
2. 创建 `production_loss` 记录
3. 写一条库存日志：`change_qty=0, reason="电镀损耗"/"手工损耗", note="损耗 {loss_qty}，原因：{reason}"`
4. 将 `received_qty += loss_qty`，触发现有状态更新逻辑（配件行变为"已收回"，满足条件时订单自动完成）
5. 如果有扣款金额，记录到 `deduct_amount` 供后续对账

## API

### 新增接口

**POST `/plating/{order_id}/items/{item_id}/confirm-loss`** — 电镀配件确认损耗

```
Request: {
  loss_qty: float,              // 损耗数量，默认填入当前差额
  deduct_amount: float | null,  // 扣款金额
  reason: str | null,           // 原因
  note: str | null              // 备注
}
Response: ProductionLossResponse
```

**POST `/handcraft/{order_id}/items/{item_id}/confirm-loss`** — 手工配件/饰品确认损耗

```
Request: 同上
Response: ProductionLossResponse
```

请求中需要额外参数 `item_type`（"part" 或 "jewelry"）来区分手工单的配件行和饰品行。

**POST `/plating-receipts/{receipt_id}/confirm-loss`** — 从收回单确认损耗（批量）

```
Request: {
  items: [{
    plating_order_item_id: int,
    loss_qty: float,
    deduct_amount: float | null,
    reason: str | null,
  }]
}
Response: { confirmed_count: int }
```

**POST `/handcraft-receipts/{receipt_id}/confirm-loss`** — 同上，手工收回单

```
Request: {
  items: [{
    item_id: int,
    item_type: str,       // "part" 或 "jewelry"
    loss_qty: float,
    deduct_amount: float | null,
    reason: str | null,
  }]
}
Response: { confirmed_count: int }
```

**GET `/production-losses`** — 查询损耗记录

```
Query: order_type?, order_id?, supplier_name?
Response: list[ProductionLossResponse]
```

## 前端

### 入口 1：电镀/手工单详情页

配件行（或饰品行）当 `received_qty < qty` 且状态为"电镀中"/"制作中"时，显示：
- 差额提示：`已收回 80 / 发出 100，差额 20`
- 【确认损耗】按钮

点击后弹窗：
- 损耗数量（默认填入差额，可修改，不能超过差额）
- 扣款金额（可选）
- 原因（可选）
- 备注（可选）
- 【确定】【取消】

### 入口 2：收回单详情页

收回单中显示关联的电镀/手工单配件行的差额信息。当有差额时，显示【确认损耗】按钮，逻辑同上。

### 损耗记录查看

暂不做独立页面，在电镀/手工单详情页中，已确认损耗的配件行显示损耗标记（如"损耗 5"标签），悬浮显示详情（损耗数量、扣款、原因）。
