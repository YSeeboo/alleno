# 电镀回收单优化设计

## 概述

对电镀回收单（PlatingReceipt）流程进行 4 项优化：新建回收单时增加编号/名称搜索、发出日期筛选，以及回收单建成后支持增加行。

## 优化 1-3：新建回收单 - 待回收配件筛选

### 现状

`PlatingReceiptCreate.vue` 选择商家后，调用 `GET /api/plating/items/pending-receive?supplier_name=xxx` 展示该商家全部待回收配件。后端已有 `part_keyword` 参数但前端未使用。无日期筛选。

### 设计

在待回收配件卡片内、表格上方增加筛选行：

| 控件 | 说明 |
|------|------|
| 编号/名称搜索（输入框） | 复用后端 `part_keyword` 参数，ILIKE 模糊匹配 part_id、part_name、receive_part_id、receive_part_name |
| 发出日期（日期选择器） | 精确匹配 `PlatingOrder.created_at::date = 所选日期` |

表格新增"发出日期"列，显示 `PlatingOrder.created_at` 的日期部分。

### 后端改动

**`services/plating.py` — `list_pending_receive_items()`**

新增 `date_on: date = None` 参数：

```python
if date_on:
    q = q.filter(func.cast(PlatingOrder.created_at, Date) == date_on)
```

查询 SELECT 列表新增 `PlatingOrder.created_at`，返回字典新增 `"created_at": row.created_at`。

**`api/plating.py` — `api_list_pending_receive_items`**

新增查询参数 `date_on: Optional[date] = None`，传递给 service。

**`schemas/plating.py` — `PendingReceiveItemResponse`**

新增 `created_at: datetime` 字段。

### 前端改动

**`PlatingReceiptCreate.vue`**

- 在待回收配件卡片顶部新增筛选行：`n-input`（placeholder="编号/名称搜索"）+ `n-date-picker`（type="date"）
- 筛选值变化时（debounce 300ms 对搜索框），调用 `listPendingReceiveItems({ supplier_name, part_keyword, date_on })`
- `pendingColumns` 新增"发出日期"列，显示 `row.created_at` 格式化为日期

**`api/plating.js` — `listPendingReceiveItems()`**

传递新增的 `date_on` 参数。

## 优化 4：回收单详情页增加行

### 现状

`PlatingReceiptDetail.vue` 已支持修改和删除明细行。不支持新增行。

### 设计

在未付款回收单的"回收明细"卡片标题栏右侧新增"+ 增加配件"按钮。点击弹出 Modal，展示该商家的待回收配件列表（复用 `list_pending_receive_items` 接口），支持勾选并填写回收数量和单价。

**Modal 内容：**
- 筛选行：编号/名称搜索 + 发出日期（与新建页面一致）
- 表格列：电镀单号、配件、电镀方式、发出日期、剩余数量、本次回收（输入）、单价（输入）
- 排除当前回收单中已有的 `plating_order_item_id`，避免重复
- 底部"取消"/"确认添加"按钮

**约束：**
- 已付款回收单不显示"+ 增加配件"按钮
- 同一个 `plating_order_item_id` 不能在同一回收单中出现两次

### 后端改动

**`services/plating_receipt.py` — 新增 `add_plating_receipt_items()`**

```python
def add_plating_receipt_items(
    db: Session,
    receipt_id: str,
    items: list,
) -> PlatingReceipt:
```

逻辑：
1. 校验回收单存在且状态为"未付款"
2. 校验 `plating_order_item_id` 不与当前回收单已有项重复
3. 对每个 item：校验 PlatingOrderItem 状态、vendor 一致性、qty 不超过剩余
4. 创建 PlatingReceiptItem，调用 `_apply_receive()`
5. 重算 `total_amount`，检查电镀单完成状态

复用 `create_plating_receipt` 中已有的校验逻辑。

**`api/plating_receipt.py` — 新增端点**

```
POST /api/plating-receipts/{receipt_id}/items
```

请求体 schema（复用已有的 `PlatingReceiptItemCreate`）：

```python
class PlatingReceiptAddItemsRequest(BaseModel):
    items: list[PlatingReceiptItemCreate] = Field(min_length=1)
```

响应：返回完整的 `PlatingReceiptResponse`（含 `cost_diffs`）。与 `create_plating_receipt` 一致，端点需调用 `detect_plating_cost_diffs()` 检测电镀成本变动。

**电镀成本变动处理：** 前端收到响应后，如果 `cost_diffs` 非空，复用成本确认弹窗逻辑（从 `PlatingReceiptCreate.vue` 提取为共享函数或在 `PlatingReceiptDetail.vue` 中内联实现）。

**`services/plating.py` — `list_pending_receive_items()` 新增排除参数**

新增 `exclude_item_ids: list[int] = None` 参数，排除指定的 `PlatingOrderItem.id`：

```python
if exclude_item_ids:
    q = q.filter(PlatingOrderItem.id.notin_(exclude_item_ids))
```

**`api/plating.py` — `api_list_pending_receive_items`**

新增查询参数 `exclude_item_ids: Optional[str] = None`（逗号分隔的 ID 列表，如 `1,2,3`），API 层解析为 `list[int]` 后传递给 service。

### 前端改动

**`PlatingReceiptDetail.vue`**

- 回收明细卡片标题栏：未付款时显示"+ 增加配件"按钮
- 新增 Modal 组件（可内联或抽取为子组件）
- Modal 打开时：从当前 `receipt.items` 提取已有的 `plating_order_item_id` 列表，作为 `exclude_item_ids` 传给 `listPendingReceiveItems`
- 确认添加后：调用 `POST /api/plating-receipts/{id}/items`，成功后刷新详情数据

**`api/platingReceipts.js`**

新增 `addPlatingReceiptItems(receiptId, items)` 方法。

**`api/plating.js` — `listPendingReceiveItems()`**

支持传递 `exclude_item_ids` 参数。

## 涉及文件汇总

| 文件 | 改动类型 |
|------|----------|
| `services/plating.py` | 修改：`list_pending_receive_items` 增加 `date_on`、`exclude_item_ids` 参数，返回值增加 `created_at` |
| `api/plating.py` | 修改：`api_list_pending_receive_items` 增加查询参数 |
| `schemas/plating.py` | 修改：`PendingReceiveItemResponse` 增加 `created_at` 字段 |
| `services/plating_receipt.py` | 新增：`add_plating_receipt_items()` 函数 |
| `api/plating_receipt.py` | 新增：`POST /api/plating-receipts/{receipt_id}/items` 端点 |
| `schemas/plating_receipt.py` | 新增：请求体 schema |
| `frontend/src/views/plating-receipts/PlatingReceiptCreate.vue` | 修改：增加筛选行、发出日期列 |
| `frontend/src/views/plating-receipts/PlatingReceiptDetail.vue` | 修改：增加"+ 增加配件"按钮和 Modal |
| `frontend/src/api/plating.js` | 修改：传递新参数 |
| `frontend/src/api/platingReceipts.js` | 新增：`addPlatingReceiptItems` 方法 |
| `tests/` | 新增：相关测试用例 |
