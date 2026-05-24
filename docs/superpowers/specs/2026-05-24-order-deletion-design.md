# 订单删除功能设计

日期：2026-05-24

## 背景

当前订单一旦创建就无法删除，不符合常识。需要提供"订单删除"入口。订单完成时会扣库存（`inventory_log` 写 `订单出货`），且订单牵连备货批次、生产单关联、拣货记录、成本快照等多张子表，因此删除的数据流向需要明确约束，避免留下脏数据或破坏有价值的历史。

## 范围与规则

- **允许删除 `待生产` 与 `已取消` 状态的订单。** 其它状态（`生产中`/`已完成`）一律拒绝。
  - 理由：这两种状态的订单从未扣过库存（扣库存发生在转 `已完成` 时），也不会有 `order_cost_snapshot`（仅 `已完成` 生成）。删除它无需库存回退，是干净操作。`已取消` 订单已无业务价值，允许清理。
- **硬删除**：物理删除订单及其所有 FK 子行。订单号 `OR-XXXX` 不回收（自增计数不回退）。不引入软删除列，避免改动所有订单查询。
- **级联删除 + 弹窗告知（方案 C）**：订单可能已挂上备货批次、生产单关联等子数据（创建这些数据时不校验订单状态）。删除时一并清理，并在二次确认弹窗中列出将被删除的具体数量，让用户知情。
- **手工单联动**：`link_supplier` 会把备货批次迁移成一张 pending 手工单（`HandcraftOrder` + `HandcraftPartItem`/`HandcraftJewelryItem`），而订单状态仍可为 `待生产`/`已取消`。删除订单时通过复用 `services.order_todo.delete_batch` 逐批处理：它会清理这些 pending 手工数据；若手工单已发出（非 pending，真实库存已扣），`delete_batch` 抛错，整张订单删除被拒绝。

## 数据流向：删除一个可删除（待生产 / 已取消）订单

删除顺序：

1. **逐批 `delete_batch(db, order_id, batch.id)`** —— 处理每个 `order_todo_batch`。`delete_batch` 内部：
   - 若批次已 `link_supplier`（`batch.handcraft_order_id` 非空）：清理该批次迁移出去的 pending `HandcraftPartItem`/`HandcraftJewelryItem` 与对应 `order_item_link`，并在手工单清空后删除 `HandcraftOrder`；**手工单非 pending 时抛错**，使整张订单删除被拒绝。
   - 删除该批次的 `order_todo_item`、`order_todo_batch_jewelry`、`order_todo_batch` 及其 link。
2. 删除剩余 FK 子行，最后删订单本身：

| 表 | 说明 | 处理方 |
|----|------|----|
| `order_picking_record` | 拣货模拟记录 | delete_order |
| `order_item_link`（order_id 直挂） | 饰品项与生产单的关联 | delete_order |
| `order_todo_item`（无批次，generate_todo 生成）+ 其 link | 备货明细 | delete_order |
| `order_cost_snapshot_item` / `order_cost_snapshot` | 成本快照 | delete_order |
| `order_item` | 订单明细 | delete_order |
| `order` | 订单本身 | delete_order |
| `order_todo_batch` / `order_todo_batch_jewelry` / 批次 `order_todo_item` | 备货批次 | delete_batch（步骤 1） |
| `handcraft_order` / `handcraft_part_item` / `handcraft_jewelry_item`（pending） | 由 link_supplier 迁移产生 | delete_batch（步骤 1） |

**不受影响 / 无需处理：**
- `production_loss`、`vendor_receipt`：其 `order_id` 引用的是电镀/手工单（EP-/HC-），非客户订单，且无 FK，与本功能无关。
- `inventory_log`：可删除状态的订单从未产生库存变动，无需写回退记录。

> 注意：`order_item_link` 仅删除"关联关系"，不删除手动 `create_link` 关联的独立电镀单/采购单本身。但 `link_supplier` 自动迁移生成的 **pending 手工单** 是为本订单专门创建的，随订单一并清理（见步骤 1）。

## 后端

### Service（`services/order.py`）

```python
def get_order_delete_preview(db, order_id: str) -> dict:
    """返回级联删除将影响的数量，供前端弹窗展示。
    订单不存在 -> ValueError。
    返回 {"item_count", "batch_count", "link_count"}。
    （picking_record、todo_item 等也会被删，但不在弹窗中单列，只展示用户可感知的明细/批次/关联三项。）
    """

def delete_order(db, order_id: str) -> None:
    """删除待生产订单及其所有 FK 子行。
    1. 取订单；不存在 -> ValueError。
    2. status != "待生产" -> ValueError("只能删除待生产状态的订单")。
    3. 按 FK 依赖顺序删除子行：order_picking_record -> order_item_link
       -> order_todo_batch_jewelry -> order_todo_item -> order_todo_batch
       -> order_item -> order。
    4. 使用 db.flush()（commit 交给 get_db()）。
    """
```

子行删除使用按 `order_id` 过滤的批量 `delete()`（`order_todo_batch_jewelry` 经由其 batch_id 关联，需先查出该订单的 batch id 列表再删）。

### API（`api/orders.py`）

- `GET /api/orders/{order_id}/delete-preview` → `200` + `{"item_count": int, "batch_count": int, "link_count": int}`
- `DELETE /api/orders/{order_id}` → 成功 `204 No Content`；状态非法经 `service_errors()` 转 `400`；订单不存在转 `400`。

## 前端（`frontend/src/views/orders/OrderList.vue`）

- 在「创建时间」列**之后**新增一列「操作」。
- 该列渲染一个红色文字「删除」按钮（`NButton text type="error"`）：
  - **始终显示**；当行 `status !== '待生产'` 时**禁用**（`disabled`），并加 `NTooltip` 悬停提示："只能删除待生产状态的订单"。
  - `@click.stop`，防止触发整行跳转到详情页。
- 点击流程：
  1. 调 `GET /delete-preview` 取影响数量。
  2. 弹 NaiveUI 二次确认对话框（`useDialog().warning`），内容列出具体数量：
     > 确认删除订单 **OR-0007**？
     > 此操作不可恢复，将一并删除：5 个明细、2 个备货批次、1 个生产单关联。
  3. 确认后调 `DELETE`，成功 → 刷新列表 + `message.success("订单已删除")`。

## 测试（TDD）

### Service（`tests/test_*_order*.py`）
- 删除 `待生产` 订单成功，订单及其 `order_item` 行均被清除。
- 删除带备货批次 / 生产单关联的 `待生产` 订单：相关 `order_todo_batch`、`order_todo_item`、`order_todo_batch_jewelry`、`order_item_link`、`order_picking_record` 行全部被清除，且不报外键错误。
- 删除 `生产中` / `已完成` / `已取消` 订单 → 抛 `ValueError`。
- 删除不存在订单 → 抛 `ValueError`。
- `get_order_delete_preview` 返回的 `item_count` / `batch_count` / `link_count` 与实际子行数一致。

### API
- `DELETE /api/orders/{order_id}`（待生产）→ `204`，再次 `GET` 该订单 → `404`/不存在。
- `DELETE` 非 `待生产` 订单 → `400`。
- `GET /api/orders/{order_id}/delete-preview` → `200` 且数量正确。
