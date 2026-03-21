# 电镀单收回配件改造

## 问题

当前电镀单收回逻辑：发出配件 A → 收回时库存加回配件 A。但实际业务中，电镀后配件颜色改变，收回的是**不同的配件**（如原色 → 金色）。需要支持发出和收回不同配件。

## 方案

在 `PlatingOrderItem` 上新增 `receive_part_id` 字段，创建电镀单时指定发出配件和收回配件。

---

## 数据模型改动

### PlatingOrderItem 新增字段

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| receive_part_id | String | 外键 → part.id，可空 | 收回配件 ID，为空时等于 part_id（向后兼容） |

**向后兼容**：`receive_part_id` 可空，为空表示收回配件与发出配件相同（老数据、同色电镀场景）。

---

## 库存逻辑改动

### 发出（不变）

```
deduct_stock("part", item.part_id, qty, "电镀发出")
```

### 收回（改动）

```python
# 改前
add_stock("part", item.part_id, qty, "电镀收回")

# 改后
receive_id = item.receive_part_id or item.part_id
add_stock("part", receive_id, qty, "电镀收回")
```

### 删除电镀单的库存回滚（改动）

当前删除逻辑中，已收回的库存回滚也要用 `receive_part_id`：

```python
# 改前：deduct_stock("part", part_id, received_qty, "电镀收回撤回")
# 改后：deduct_stock("part", receive_part_id or part_id, received_qty, "电镀收回撤回")
```

发出的库存回滚不变，仍然用 `part_id`。

---

## API 改动

### 创建电镀单 / 添加明细

请求体 item 新增可选字段 `receive_part_id`：

```json
{
  "part_id": "PJ-X-00001",
  "receive_part_id": "PJ-X-00002",
  "qty": 100,
  "plating_method": "金色电镀"
}
```

- `receive_part_id` 可选，不填时收回配件等于发出配件
- 填写时需校验配件存在（与 `part_id` 相同的校验逻辑）

### 修改明细

`receive_part_id` 可修改（仅 pending 状态）。

### 响应

所有返回 `PlatingOrderItem` 的接口新增 `receive_part_id` 字段。

---

## Schema 改动

### PlatingOrderItemCreate / PlatingOrderItemUpdate

新增 `receive_part_id: Optional[str] = None`

### PlatingOrderItemResponse

新增 `receive_part_id: Optional[str] = None`

---

## 前端改动

### 创建/编辑电镀单明细

- 现有"配件"选择框重命名为"发出配件"
- 新增"收回配件"选择框，同样从配件库读取数据
- "收回配件"可选填，不填时表示收回配件与发出配件相同
- 选择发出配件后，可以默认筛选同类配件辅助选择

### 电镀单详情页

- 明细表格新增"收回配件"列
- 如果 `receive_part_id` 为空，显示为"同发出配件"或不显示

---

## 影响范围

### 后端文件

| 文件 | 改动 |
|------|------|
| `models/plating_order.py` | `PlatingOrderItem` 新增 `receive_part_id` 列 |
| `database.py` | `ensure_schema_compat()` 中处理新列的自动添加 |
| `schemas/plating_order.py` | 请求/响应 schema 新增字段 |
| `services/plating.py` | 收回逻辑、删除回滚逻辑使用 `receive_part_id` |
| `api/plating.py` | 无需改动（透传 schema 字段） |

### 前端文件

| 文件 | 改动 |
|------|------|
| `PlatingCreate.vue` | 明细表单新增"收回配件"选择框 |
| `PlatingDetail.vue` | 明细表格新增"收回配件"列 |

### 不受影响

- 电镀单的发出逻辑、状态机、导出功能不变
- 手工单逻辑不受影响
