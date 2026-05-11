# Stock Shortage 一键补进并发出 — Design

**Date:** 2026-05-11
**Scope:** 手工单（HC）和电镀单（EP）发出时库存不足的修复流程。
**Author:** Brainstormed with Claude.

---

## 1. 背景

当前 `POST /handcraft/{id}/send` 和 `POST /plating/{id}/send` 都走"预检 → 扣减 → 失败整体回滚"的流程。预检发现库存不足时，后端返回 `库存不足：part PJ-XXX 当前库存 X，需要 Y；…` 字符串，前端弹一个列表 dialog 让用户自己去解决。

由于当前库存账目不够精准，用户经常遇到这个弹窗。一个个去手工入库太麻烦，希望弹窗里直接提供"一键补进库存"的能力，把差额补进后立即继续发出订单。

`HandcraftDetail.vue:950-987` 和 `PlatingDetail.vue:765-802` 的处理逻辑目前是字面级复制，这次顺手抽到共享 composable。

## 2. 用户流程

```
[用户点 确认发出]
        │
        ▼
POST /<type>/{id}/send  ─── 库存不足 ──┐
                                      ▼
        ┌─────────────────────────────────────┐
        │ ① "库存不足" 弹窗                    │
        │   列出每个配件：partId, 当前, 需要  │
        │   [知道了]   [一键补进并发出]        │
        └─────────────────────────────────────┘
                                      │ 点 [一键补进并发出]
                                      ▼
        前端实时查每个配件的最新库存，重算差额。
        若所有差额都已 ≤ 0：跳过下一步，直接调
                                      │ supplement-and-send
                                      ▼
        ┌─────────────────────────────────────┐
        │ ② "确认补进库存" 弹窗               │
        │   逐行列出 partId + 补进数量         │
        │   汇总：共 N 个配件，X 件            │
        │   [取消]    [确认补进并发出]         │
        └─────────────────────────────────────┘
                                      │ 确认
                                      ▼
POST /<type>/{id}/supplement-and-send（后端原子操作）
   1. 重新查询每个配件当前库存
   2. 对差额 > 0 的逐个 add_stock
   3. 立即调用 send_<type>_order
   整事务里跑，任意一步失败统统回滚
                                      │ 成功
                                      ▼
        Toast: 已补进 N 个配件共 X 件，订单已发出
        （N=0 时显示：库存已足，订单已发出）
        刷新订单详情
```

### 设计关键点

- **两次库存查询**：前端在弹二次确认前查一次（给用户看真实预览），后端在 `supplement-and-send` 里再查一次（实际执行依据，防止前端查询和后端执行之间的竞态）。
- **二次确认必有**：避免误点导致幽灵库存。
- **原子操作**：补进和发出在同一个事务里，任意一步失败 inventory_log 不会留下"补进但没发出"的记录。
- **跳过空补进**：后端二次查询发现已经够了时，不写 `change_qty=0` 的空 log，直接进入发出。

## 3. 后端设计

### 3.1 `services/inventory.py` 新增工具

```python
def supplement_shortfall(
    db: Session,
    item_type: str,
    needs: dict[str, float],   # item_id -> 需要数量
    reason: str,
    note: str | None = None,
) -> dict[str, float]:
    """对 needs 里每个 item 重新查询库存，对差额 > 0 的调 add_stock。
    返回实际补进的 {item_id: 补进数量}（差额为 0 的不在返回里、也不写 log）。
    """
```

实现要点：
- 用 `batch_get_stock` 一次查所有。
- 对每个 item：`gap = needs[id] - current_stock`，`gap > 0` 才调 `add_stock`。
- 返回真正补进过的字典；调用方根据它判断要显示什么 toast。

### 3.2 `services/handcraft.py` 新增

```python
def supplement_and_send_handcraft_order(
    db: Session, handcraft_order_id: str
) -> tuple[HandcraftOrder, dict[str, float]]:
    """补进缺货后立即发出。返回 (订单, 实际补进的 {part_id: 数量})。"""
```

流程：
1. 校验订单存在 + 状态 `pending`。
2. 取出 part_items，按 `part_id` 聚合 `qty`。
3. 调 `supplement_shortfall(db, "part", part_totals, reason="手工单缺货补进", note=handcraft_order_id)`。
4. 调现成的 `send_handcraft_order(db, handcraft_order_id)`（在同一 session 内）。
5. 返回 `(order, supplemented)`。

任何一步抛异常都让事务回滚（`get_db()` 已经管这件事）。

### 3.3 `services/plating.py` 新增

完全对称，仅以下不同：
- `reason="电镀单缺货补进"`
- `note=plating_order_id`
- 调 `send_plating_order`

### 3.4 API 端点

```python
# api/handcraft.py
@router.post("/{order_id}/supplement-and-send",
             response_model=SupplementAndSendHandcraftResponse)
def api_supplement_and_send_handcraft(order_id: str, db: Session = Depends(get_db)):
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise HTTPException(404, f"HandcraftOrder {order_id} not found")
    with service_errors():
        order, supplemented = supplement_and_send_handcraft_order(db, order_id)
    return SupplementAndSendHandcraftResponse(order=order, supplemented=supplemented)
```

电镀单镜像。

### 3.5 Response schemas

```python
# schemas/handcraft.py
class SupplementAndSendHandcraftResponse(BaseModel):
    order: HandcraftResponse
    supplemented: dict[str, float]   # {part_id: 实际补进数量}，可能为空
    model_config = ConfigDict(from_attributes=True)
```

电镀单镜像 `SupplementAndSendPlatingResponse`。

### 3.6 Inventory Log 字段约定

| 字段 | 手工单 | 电镀单 |
|---|---|---|
| `reason` | `"手工单缺货补进"` | `"电镀单缺货补进"` |
| `note` | `"HC-0042"` | `"EP-0042"` |
| `change_qty` | 差额（正数） | 差额（正数） |
| `created_at` | 自动北京时间 | 自动北京时间 |

新增 reason 是**标准化分类**，便于未来用 `WHERE reason = '手工单缺货补进'` 统计因缺货而补进的数量。

## 4. 前端设计

### 4.1 共享 composable

新建 `frontend/src/composables/useSendWithStockSupplement.js`，封装：
1. 调 `sendApi(orderId)`。
2. 捕获 `库存不足：…` 错误，弹列表 dialog（沿用现有 UI，加 `positiveText="一键补进并发出"` + `positiveButtonProps.type = "warning"`）。
3. 用户点正按钮后，前端调 `batchGetStock("part", partIds)` 查最新库存、算差额。
4. 弹二次确认 dialog（差额表 + 共 N 件 + 订单号）。所有差额为 0 时跳过此步。
5. 调 `supplementApi(orderId)`，根据返回的 `supplemented` 字典生成 toast 文案。
6. 调用方传入的 `onSuccess()` 回调（一般是 `loadData`）。

接口：
```js
const { sending, doSend } = useSendWithStockSupplement({
  orderId,        // ref/computed -> string
  sendApi,        // (id) => Promise
  supplementApi,  // (id) => Promise<{ supplemented: {[pid]: qty} }>
  onSuccess,      // () => Promise<void>
  message,        // useMessage()
  dialog,         // useDialog()
})
```

### 4.2 调用方变化

`HandcraftDetail.vue` 和 `PlatingDetail.vue` 删掉旧的 `doSend` / `sending` / 错误解析逻辑，改为：

```js
const { sending, doSend } = useSendWithStockSupplement({
  orderId: computed(() => route.params.id),
  sendApi: sendHandcraft,                 // 或 sendPlating
  supplementApi: supplementAndSendHandcraft,  // 或 supplementAndSendPlating
  onSuccess: loadData,
  message, dialog,
})
```

### 4.3 API helpers

`frontend/src/api/handcraft.js`：
```js
export const supplementAndSendHandcraft = (id) =>
  api.post(`/handcraft/${id}/supplement-and-send`, null, { _silentError: true })
```
`plating.js` 镜像。

### 4.4 批量查库存

复用现有 `batchGetStock(itemType, itemIds)`（`frontend/src/api/inventory.js`），对应后端 `POST /inventory/batch-stock`。**不需要新增任何 API。**

### 4.5 视觉规范

- **"一键补进并发出"** 按钮：Naive UI `type="warning"`（橙色），与告警色一致。
- **"知道了"** 保留为 negative button（白底）。
- **二次确认弹窗** 内的差额列表：mono 字体，partId 绿色，数量红色（强调"凭空多出来"）。
- **Toast 文案**：
  - 补进 ≥ 1：`已补进 N 个配件共 X 件，订单已发出`
  - 补进 = 0（二次查询发现已够）：`库存已足，订单已发出`

## 5. 边界情况

| 场景 | 行为 |
|---|---|
| 订单状态非 `pending` | `ValueError` → HTTP 400，前端按普通错误 toast |
| 订单不存在 | HTTP 404 |
| 订单无 part_items | `ValueError` → HTTP 400 |
| 二次查询时所有差额 ≤ 0 | 跳过 add_stock，直接发出，toast 显示"库存已足" |
| 同一 part_id 出现在多行 part_items | 按总量聚合（沿用 `send_*_order` 现有逻辑） |
| `add_stock` 失败 | 整事务回滚，inventory_log 不留补进记录 |
| `send_*_order` 失败 | 整事务回滚（含已写入的补进 log） |
| 两用户并发点"一键补进" | 不加分布式锁；最差结果：补两次进去（多出库存，靠后续盘点修正），不会负库存或状态错乱 |

## 6. 测试

### 6.1 Service 层

`tests/test_services_handcraft.py` 新增 7 个：
1. `test_supplement_and_send_normal` — 1 个配件差 5，验证 `inventory_log` 出现 `手工单缺货补进` + `手工发出` 两条；订单状态 `processing`。
2. `test_supplement_and_send_no_shortage` — 库存已够，无补进 log，只有 `手工发出`。
3. `test_supplement_and_send_multi_parts` — 3 个配件，2 差、1 够；只补 2 个。
4. `test_supplement_and_send_aggregates_same_part` — 同 part_id 两行 part_items，按聚合总量补。
5. `test_supplement_and_send_order_not_pending` — 拒绝。
6. `test_supplement_and_send_order_not_found` — 拒绝。
7. `test_supplement_and_send_no_part_items` — 拒绝。

`tests/test_services_plating.py` 镜像 6 个（不含 jewelry 那条）。

`tests/test_services_inventory.py` 新增 2 个：
- `test_supplement_shortfall_skips_when_enough` — 库存够时不调 add_stock，返回空 dict。
- `test_supplement_shortfall_partial` — 部分需要补、部分不需要。

### 6.2 API 层

`tests/test_api_handcraft.py` / `test_api_plating.py` 各一个 happy-path：
- 验证响应 schema 含 `supplemented` 字段且数值正确。

### 6.3 不写的测试

- 前端单测：项目无前端测试体系，不为此一个功能引入；手动测一遍弹窗流程。
- 并发锁测试：靠数据库事务，不写专门并发测试。

## 7. 文件改动汇总

| 文件 | 改动 |
|---|---|
| `services/inventory.py` | 新增 `supplement_shortfall()` |
| `services/handcraft.py` | 新增 `supplement_and_send_handcraft_order()` |
| `services/plating.py` | 新增 `supplement_and_send_plating_order()` |
| `schemas/handcraft.py` | 新增 `SupplementAndSendHandcraftResponse` |
| `schemas/plating.py` | 新增 `SupplementAndSendPlatingResponse` |
| `api/handcraft.py` | 新增 `POST /{id}/supplement-and-send` |
| `api/plating.py` | 新增 `POST /{id}/supplement-and-send` |
| `frontend/src/composables/useSendWithStockSupplement.js` | **新文件** |
| `frontend/src/api/handcraft.js` | 加 `supplementAndSendHandcraft` |
| `frontend/src/api/plating.js` | 加 `supplementAndSendPlating` |
| `frontend/src/views/handcraft/HandcraftDetail.vue` | 替换 `doSend` 为 composable |
| `frontend/src/views/plating/PlatingDetail.vue` | 替换 `doSend` 为 composable |
| `tests/test_services_handcraft.py` | 7 个新测试 |
| `tests/test_services_plating.py` | 6 个新测试 |
| `tests/test_services_inventory.py` | 2 个新测试 |
| `tests/test_api_handcraft.py` | 1 个新测试 |
| `tests/test_api_plating.py` | 1 个新测试 |

## 8. 不做的事

- 不抽 `send_handcraft_order` / `send_plating_order` 的内部逻辑；新函数调旧函数即可。
- 不引入分布式锁。
- 不动现有"库存不足"列表 dialog 的视觉（仅按钮文案/颜色调整 + 多一个按钮）。
- 不对 jewelry 类型做"一键补进"——发出阶段只扣 part，jewelry 是在 receive 阶段加库存，不会缺货。
