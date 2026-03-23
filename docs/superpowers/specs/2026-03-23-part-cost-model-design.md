# 配件成本模型设计（Spec A）

## 概述

为配件建立成本体系，将单件成本拆分为三个独立维度（购入单价、穿珠费用、电镀费用），记录价格变动日志，并在配件详情页展示价格变动历史。

本 spec 为 Spec A（数据基础），Spec B（采购单/电镀回收的成本同步弹窗）依赖本 spec。

## 数据模型

### Part 表新增字段

通过 `ensure_schema_compat()` 自动加列：

| 字段 | 类型 | 说明 |
|------|------|------|
| `purchase_cost` | Numeric(18,7), nullable | 购入单价，来源：采购单 |
| `bead_cost` | Numeric(18,7), nullable | 穿珠费用，来源：采购单 addon |
| `plating_cost` | Numeric(18,7), nullable | 电镀费用，来源：电镀回收单 |

- `unit_cost` 保留，值 = `(purchase_cost or 0) + (bead_cost or 0) + (plating_cost or 0)`
- 任一分项变动时由后端自动重算 `unit_cost`
- 电镀费用只记在电镀后的配件上（如"圈金色"），原件（如"圈原件"）的 `plating_cost` 始终为 0/null
- 每个配件的三项成本独立存储，子配件（通过 `parent_part_id` 关联）不自动继承原件的 `purchase_cost` / `bead_cost`
- `create_part_variant` 创建变体时，不复制原件的成本字段（`purchase_cost` / `bead_cost` / `plating_cost` 均为 null），同时不再复制 `unit_cost`
- 现有 `PartUpdate` schema 中如果包含 `unit_cost` 字段，`update_part` 应忽略它（不允许手动直接设置 `unit_cost`，必须通过 `update_part_cost` 间接更新）

### 新建 `part_cost_log` 表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | 自增 |
| `part_id` | String FK → part.id, NOT NULL | 配件 |
| `field` | String, NOT NULL | 变动字段：`purchase_cost` / `bead_cost` / `plating_cost` |
| `cost_before` | Numeric(18,7), nullable | 变动前该字段值 |
| `cost_after` | Numeric(18,7), nullable | 变动后该字段值 |
| `unit_cost_before` | Numeric(18,7), nullable | 变动前 unit_cost |
| `unit_cost_after` | Numeric(18,7), nullable | 变动后 unit_cost |
| `source_id` | String, nullable | 触发来源单据 ID（如 CG-0012、PR-0003）|
| `created_at` | DateTime | 变动时间，默认 `now_beijing()` |

Model 放在 `models/part.py` 中，与 Part 同文件。

## Service 层

### `update_part_cost(db, part_id, field, value, source_id=None)`

通用成本更新函数：

1. 读取 Part，校验存在
2. 记录旧值：`cost_before` = 当前 field 值，`unit_cost_before` = 当前 unit_cost
3. 设置 field 新值
4. 重算 `unit_cost` = `(purchase_cost or 0) + (bead_cost or 0) + (plating_cost or 0)`
5. 如果 field 值有变化（旧值 != 新值），写一条 `part_cost_log` 记录
6. `db.flush()`
7. 返回 log 记录（值未变化时返回 None）

`field` 参数仅接受 `purchase_cost` / `bead_cost` / `plating_cost`，其他值 raise `ValueError`。

### `list_part_cost_logs(db, part_id)`

按 `created_at DESC` 返回该配件的所有成本变动日志。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/parts/{part_id}/cost-logs` | 获取配件价格变动日志 |

- 返回 `list[PartCostLogResponse]`，按 `created_at DESC`
- 成本更新不单独暴露 API — 在 Spec B 中由采购单/电镀回收的业务流程调用 `update_part_cost` 触发

### Part 响应扩展

`PartResponse` schema 新增字段：
- `purchase_cost: Optional[float] = None`
- `bead_cost: Optional[float] = None`
- `plating_cost: Optional[float] = None`

### PartCostLogResponse schema

```
id: int
part_id: str
field: str
cost_before: Optional[float]
cost_after: Optional[float]
unit_cost_before: Optional[float]
unit_cost_after: Optional[float]
source_id: Optional[str]
created_at: datetime
```

## 前端 — 配件详情页

### 单件成本展示改造

将现有 `单件成本` 描述项从简单数值改为：

```
¥ 3.65  (采购 2.50 + 穿珠 0.15 + 电镀 1.00)  [📋]
```

- 总价加粗显示
- 括号内分项明细，null/0 的项不显示
- 如果三项全为 null，显示 `-`
- 右侧 📋 图标入口

### 价格变动历史弹窗

使用 NPopover（trigger="hover"）实现：

- 悬浮或点击图标展示弹窗
- 鼠标移出图标和弹窗区域时关闭

弹窗内容为表格，列：

| 列 | 说明 |
|----|------|
| 时间 | `created_at`，格式 MM/DD HH:mm |
| 当前价格 | `unit_cost_after`，¥ 格式 |
| 变动 | `unit_cost_after - unit_cost_before`，正数绿色 `+ x.xx`，负数红色 `- x.xx` |
| 原因 | `field` 映射中文标签，统一颜色样式 |
| 来源 | `source_id`，可点击跳转对应单据详情 |

字段中文映射：
- `purchase_cost` → "采购费用更新"
- `bead_cost` → "穿珠费用更新"
- `plating_cost` → "电镀费用更新"

来源跳转规则：
- `CG-` 前缀 → `/purchase-orders/{source_id}`
- `ER-` 前缀 → `/plating-receipts/{source_id}`

按 `created_at DESC` 排序，最新在上。

### 数据加载

配件详情页 `onMounted` 时，并行请求：
- 现有的 `getPart`, `getStock`, `getStockLog`
- 新增 `getPartCostLogs(part_id)` — 获取价格变动日志

弹窗数据随页面加载，不做懒加载。
