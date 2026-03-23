# 成本同步设计（Spec B）

## 概述

在采购单创建和电镀回收单创建时，自动检测配件成本差异，前端弹窗提示用户确认是否更新配件成本。

依赖 Spec A（配件成本模型）：Part 的 `purchase_cost`、`bead_cost`、`plating_cost` 字段和 `update_part_cost` 函数。

## 触发时机

- **采购单创建时**（`POST /api/purchase-orders`）：对比 `purchase_cost`
- **穿珠费用 addon 创建/修改时**（`POST/PUT .../addons`）：对比 `bead_cost`
- **电镀回收单创建时**（`POST /api/plating-receipts`）：对比 `plating_cost`

## 后端 — 成本差异检测

### 采购单创建后的差异检测

在 `create_purchase_order` 返回之前，对比每个 item：

| 对比项 | 采购单数据 | 配件现有值 |
|--------|-----------|-----------|
| 购入单价 | item 的 `price` | `part.purchase_cost` |

- 仅当采购单 item 有 `price` 时才对比 `purchase_cost`
- 同一个 part_id 在采购单中可能出现多次（多行），取最后一行的值
- 对比使用 Decimal 精度（quantize 到 7 位小数），None 与 0 视为不同

注意：穿珠费用（bead_cost）不在采购单创建时检测，因为 addon 是在采购单创建之后才单独添加的。

### 穿珠费用 addon 创建/修改后的差异检测

在 `create_purchase_item_addon` 和 `update_purchase_item_addon` 返回之前，对比：

| 对比项 | addon 数据 | 配件现有值 |
|--------|-----------|-----------|
| 穿珠费用 | addon 的 `unit_cost` | `part.bead_cost`（通过父 item 的 `part_id` 找到配件）|

- 仅对 type=`bead_stringing` 的 addon 做检测
- addon 的 API 响应（`PurchaseOrderItemAddonResponse`）新增 `cost_diffs` 字段

### 电镀回收单创建后的差异检测

在 `create_plating_receipt` 返回之前，对比每个 item：

| 对比项 | 回收单数据 | 配件现有值 |
|--------|-----------|-----------|
| 电镀费用 | item 的 `price` | `part.plating_cost`（通过 plating_order_item 的 `receive_part_id` 找到收回配件）|

- 仅当 item 有 `price` 时才对比
- 同一个 receive_part_id 出现多次时，取最后一行的值

### 差异检测实现

新建独立 service 函数 `detect_purchase_cost_diffs(db, order)`、`detect_addon_cost_diffs(db, item, addon)` 和 `detect_plating_cost_diffs(db, receipt)`：

- 不修改现有创建逻辑，创建完成后调用检测函数
- 返回差异列表：`[{ part_id, part_name, field, current_value, new_value }]`
- 差异数据附加到响应中

### 响应扩展

`PurchaseOrderResponse`、`PurchaseOrderItemAddonResponse` 和 `PlatingReceiptResponse` 各新增一个可选字段：

```
cost_diffs: list[CostDiffItem] = Field(default_factory=list)
```

`CostDiffItem` schema：
```
part_id: str
part_name: str
field: str          # purchase_cost / bead_cost / plating_cost
current_value: Optional[float]   # 配件现有值
new_value: float                 # 新值
```

- `cost_diffs` 仅在创建接口返回时填充，GET 接口返回空数组
- 这样不影响现有的 GET/LIST 接口行为

## 后端 — 批量成本更新 API

### `POST /api/parts/batch-update-costs`

请求体：
```json
{
  "updates": [
    { "part_id": "PJ-DZ-00012", "field": "purchase_cost", "value": 3.00, "source_id": "CG-0012" },
    { "part_id": "PJ-DZ-00012", "field": "bead_cost", "value": 0.20, "source_id": "CG-0012" }
  ]
}
```

- 内部循环调用 `update_part_cost`（Spec A），一个事务完成
- 值未变化的跳过
- 返回结果列表

响应：
```json
{
  "updated_count": 2,
  "results": [
    { "part_id": "PJ-DZ-00012", "field": "purchase_cost", "updated": true },
    { "part_id": "PJ-DZ-00012", "field": "bead_cost", "updated": true }
  ]
}
```

Schema：

```
class BatchCostUpdateItem(BaseModel):
    part_id: str
    field: str
    value: float = Field(ge=0)
    source_id: Optional[str] = None

class BatchCostUpdateRequest(BaseModel):
    updates: list[BatchCostUpdateItem] = Field(min_length=1)

class BatchCostUpdateResultItem(BaseModel):
    part_id: str
    field: str
    updated: bool

class BatchCostUpdateResponse(BaseModel):
    updated_count: int
    results: list[BatchCostUpdateResultItem]
```

## 前端 — 成本差异弹窗

### 采购单创建页（PurchaseOrderCreate.vue）

创建成功后：
1. 检查响应 `cost_diffs` 是否非空
2. 非空则弹出 NModal 确认弹窗
3. 弹窗标题："当前成本与配件已有成本金额不相同，是否更新配件成本？"
4. 弹窗副标题显示来源单号
5. 弹窗表格列：配件编号、配件名称、原单价、更新单价
   - 更新值用红色加粗标出
6. "确认更新"按钮 → 调 `POST /api/parts/batch-update-costs`，成功后提示"配件成本已更新"，跳转详情页
7. "跳过"按钮 → 关闭弹窗，跳转详情页
8. 无论选择哪个，采购单本身已创建成功

### 采购单详情页 — 穿珠费用 addon 保存后（PurchaseOrderDetail.vue）

addon 创建/修改成功后：
1. 检查 addon 响应 `cost_diffs` 是否非空
2. 非空则弹出 NModal 确认弹窗
3. 弹窗标题："当前穿珠成本与配件已有穿珠成本金额不相同，是否更新穿珠成本？"
4. 弹窗表格列：配件编号、配件名称、原穿珠费用、更新穿珠费用
5. "确认更新" → 调 `POST /api/parts/batch-update-costs`
6. "跳过" → 关闭弹窗

### 电镀回收单创建页（PlatingReceiptCreate 或相关页面）

同上逻辑，但：
- 弹窗标题："当前电镀成本与配件已有电镀成本金额不相同，是否更新电镀成本？"
- 表格列：配件编号、配件名称、原电镀费用、更新电镀费用
- 每行只有一个 field（plating_cost），无需合并
