# 电镀单回收交互改造

## 目标

优化电镀单的回收操作体验，提供三个层级的回收入口，覆盖不同业务场景。

## 核心决策

- 看板只负责"看进度"，回收操作放在电镀单模块
- 三个层级的回收入口，各解决一个场景
- 复用现有的 `POST /api/plating/{order_id}/receive` 接口，无需新增后端 API

---

## 回收入口总览

| 层级 | 入口位置 | 操作 | 场景 |
|------|---------|------|------|
| 列表页【回收】| 电镀单列表页顶部，与【新建电镀单】并排 | 按配件搜索，跨订单回收 | 收到一批某种配件，不确定在哪个订单 |
| 详情页【整单回收】| 电镀单详情页顶部 | 该订单所有未收回明细一键全部回收 | 某厂家的单子整批回来了 |
| 明细行【全部回收/部分回收】| 电镀单详情页明细表格每行 | 针对单行明细操作 | 逐条处理回收 |

---

## 一、列表页【回收】按钮

### 位置

电镀单列表页顶部，与【新建电镀单】按钮并排：

```
【新建电镀单】  【回收】
```

### 交互流程

1. 点击【回收】→ 弹出回收弹窗
2. 弹窗顶部：配件搜索框（支持按配件 ID 或名称搜索）
3. 搜索后展示匹配的电镀单明细列表（跨订单聚合），只展示状态为"电镀中"的明细

### 回收弹窗

**搜索区域**：
- 配件搜索框（NAutoComplete 或 NSelect remote），按 ID/名称模糊搜索

**搜索结果表格**：

| 列 | 说明 |
|----|------|
| 电镀单号 | 所属电镀单 ID，可点击跳转详情 |
| 厂家 | 电镀单的 supplier_name |
| 发出配件 | 配件名称 + 图片缩略图 |
| 收回配件 | receive_part_id 对应的配件名称，为空显示"同发出配件" |
| 电镀工艺 | plating_method |
| 发出数量 | qty |
| 已收回 | received_qty |
| 未收回 | qty - received_qty |
| 操作 | 【全部回收】【部分回收】 |

**操作交互**：
- 【全部回收】：点击后直接将该行未收回数量全部回收，调用 receive API
- 【部分回收】：点击后弹出小弹窗，输入回收数量，点【确定】调用 receive API，点【取消】关闭
- 回收成功后刷新表格数据，已全部收回的行自动消失

### 后端支持

需要一个查询接口来支持按配件搜索跨订单的电镀中明细：

**GET `/api/plating/items/pending-receive`**
- 查询参数：`part_keyword`（可选，按配件 ID 或名称模糊搜索）
- 返回：所有状态为"电镀中"且未完全收回的 PlatingOrderItem 列表，附带电镀单信息（order_id、supplier_name）和配件信息（part_name、part_image、receive_part_name）
- 排序：按电镀单创建时间倒序

响应示例：
```json
[
  {
    "id": 1,
    "plating_order_id": "EP-0001",
    "supplier_name": "张三电镀厂",
    "part_id": "PJ-DZ-00001",
    "part_name": "圆扣",
    "part_image": "https://...",
    "receive_part_id": "PJ-DZ-00002",
    "receive_part_name": "圆扣-金色",
    "plating_method": "金色电镀",
    "qty": 100,
    "received_qty": 30,
    "unit": "个"
  }
]
```

---

## 二、详情页【整单回收】按钮

### 位置

电镀单详情页顶部操作区，仅在订单状态为 `processing` 时显示：

```
← 返回    EP-0001    【确认发出】/【整单回收】    导出Excel  导出PDF
```

### 交互流程

1. 点击【整单回收】→ 二次确认弹窗："确认将该电镀单所有未收回配件全部回收？"
2. 确认 → 调用 receive API，将所有未完全收回的明细按剩余数量全部回收
3. 成功后刷新页面，订单自动变为 `completed`

### 实现逻辑

前端遍历当前订单的所有明细，筛选出 `received_qty < qty` 的项，构造 receipts 数组：

```javascript
const receipts = items
  .filter(item => item.received_qty < item.qty)
  .map(item => ({
    plating_order_item_id: item.id,
    qty: item.qty - item.received_qty
  }))

await receivePlating(orderId, receipts)
```

---

## 三、明细行【全部回收】【部分回收】

### 位置

电镀单详情页明细表格，操作列中。仅在明细状态为"电镀中"且 `received_qty < qty` 时显示。

### 现有操作列

当前操作列有：编辑、删除（仅 pending 状态）。新增回收按钮不与这些冲突（回收只在 processing 状态出现）。

### 交互

**【全部回收】**：
- 点击 → 直接将该行剩余数量全部回收
- 调用 `receivePlating(orderId, [{ plating_order_item_id: item.id, qty: remaining }])`
- 成功后刷新明细数据

**【部分回收】**：
- 点击 → 弹出小弹窗（NModal 或 NPopover）
- 显示：配件名称、发出数量、已收回、未收回
- 输入框：回收数量（NInputNumber，max 为未收回数量，min 为 0.0001）
- 【确定】调用 receive API，【取消】关闭弹窗
- 成功后刷新明细数据

---

## 影响范围

### 后端

| 文件 | 改动 |
|------|------|
| `services/plating.py` | 新增 `list_pending_receive_items(db, part_keyword)` 查询函数 |
| `api/plating.py` | 新增 `GET /api/plating/items/pending-receive` 端点 |
| `schemas/plating.py` | 新增 `PendingReceiveItemResponse` 响应 schema |

### 前端

| 文件 | 改动 |
|------|------|
| `PlatingList.vue` | 新增【回收】按钮 + 回收弹窗（搜索 + 结果表格 + 回收操作） |
| `PlatingDetail.vue` | 新增【整单回收】按钮；明细行新增【全部回收】【部分回收】按钮 |
| `plating.js` | 新增 `listPendingReceiveItems(params)` API 调用 |

### 不受影响

- 现有 `POST /api/plating/{order_id}/receive` 接口不变
- 电镀单创建、发出、删除逻辑不变
- 前端 `receivePlating()` API 调用不变，三个层级的回收都复用此函数
