# 配件级 BOM（子装配件）设计文档

## 背景

部分配件本身需要由多个子配件手工组装而成（如配件 c 由 e、f、g 组合）。当前系统 BOM 只支持"饰品 → 配件"一层关系，无法表达"配件 → 子配件"的组合关系，导致手工单无法正确处理子装配件的发出与收回。

### 示例流程

饰品 A 的 BOM：配件 b, c, d
配件 c 的子配件 BOM：配件 e, f, g

1. 手工单 A（手工商 A）：发出 e, f, g → 收回配件 c
2. 手工单 B（手工商 B）：发出 b, c, d → 收回饰品 A

## 一、数据模型

### 新增表

**`part_bom`** — 配件级 BOM

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String PK | 自动生成（PB-xxxx） |
| parent_part_id | String FK → part.id | 父配件（组合件） |
| child_part_id | String FK → part.id | 子配件（原料） |
| qty_per_unit | Numeric(10,4) | 每个父配件需要的子配件数量 |

### 修改现有表

**`handcraft_jewelry_item`** — 改为"产出明细"，新增 `part_id` 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| part_id | String FK → part.id, nullable | 产出配件（与 jewelry_id 二选一） |

约束：`jewelry_id` 和 `part_id` 必须有且只有一个非空。

**`handcraft_receipt_item`** — 收回单明细，同步支持

已有 `item_type` 字段（"part" / "jewelry"），收回配件产出时 `item_type` 仍为 "part"，但通过 `handcraft_jewelry_item_id` 关联到产出明细。需要确认现有逻辑是否需要调整。

## 二、配件级 BOM 管理

### 服务层

新建 `services/part_bom.py`，复用 `services/bom.py` 的模式：

- `set_part_bom(db, parent_part_id, child_part_id, qty_per_unit)` — 创建或更新
- `get_part_bom(db, parent_part_id)` — 获取父配件的所有子配件 BOM
- `delete_part_bom_item(db, bom_id)` — 删除
- `calculate_child_parts_needed(db, parent_part_id, qty)` — 计算所需子配件数量

### API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/parts/{part_id}/bom` | 获取配件的子配件 BOM |
| POST | `/parts/{part_id}/bom` | 添加/更新子配件 BOM 行 |
| DELETE | `/parts/bom/{bom_id}` | 删除子配件 BOM 行 |

### 前端

配件详情页（`PartDetail.vue`）增加"子配件"区块，布局和饰品详情页的 BOM 管理一致：
- 表格显示：子配件编号、子配件（图片+名称）、每单位用量、操作（删除）
- 添加行：选择配件 + 输入用量 + 确认
- 用量可 inline 编辑

## 三、手工单产出明细改造

### 概念变更

"饰品明细"（HandcraftJewelryItem）改为**"产出明细"**，同时支持：
- 产出饰品（现有功能，`jewelry_id` 非空）
- 产出配件（新功能，`part_id` 非空）

### 收回逻辑

**收回产出配件时**（如收回配件 c）：
1. 增加配件 c 的库存（`add_stock("part", c, qty, "手工收回")`）
2. 自动消耗子配件 e, f, g（复用 `_auto_consume_parts` 模式，但查询 `part_bom` 而非 `bom`）
3. 更新关联的 HandcraftPartItem 的 `received_qty` 和状态

**收回产出饰品时**（现有逻辑不变）：
1. 增加饰品库存
2. 自动消耗配件（查询 `bom` 表）

### 手工单创建/编辑

创建手工单时，产出明细支持：
- 选择饰品（现有）
- 选择配件（新增）

如果选择的配件有子配件 BOM，可以自动将子配件填入配件明细（发出列表）。

### API 变更

**POST `/handcraft`** — 创建手工单，`jewelries` 参数改名为 `outputs`，每项支持：
```
{
  jewelry_id: str | null,   // 二选一
  part_id: str | null,      // 二选一
  qty: int,
  unit: str,
  note: str
}
```

保持向后兼容：如果传入 `jewelry_id` 则行为不变。

**GET handcraft items** — 产出明细返回中增加 `part_id`、`part_name` 字段。

### 前端

手工单详情页（`HandcraftDetail.vue`）：
- "饰品明细"标题改为"产出明细"
- 添加产出项时，可选择"饰品"或"配件"
- 表格中根据 `jewelry_id` / `part_id` 显示对应的名称和图片
- 收回单创建时，同步支持选择配件产出项

## 四、收回单适配

### HandcraftReceipt

收回单已有 `item_type`（"part" / "jewelry"）字段。收回配件产出时：

- `item_type` = "part"（因为产出的是配件）
- `handcraft_jewelry_item_id` 关联到产出明细（虽然名字叫 jewelry_item，但实际上产出的是配件）
- `item_id` = 配件 c 的 part_id

`_apply_receive` 函数需要识别：这条产出明细是饰品还是配件，从而决定：
- 饰品：`add_stock("jewelry", ...)` + 通过 `bom` 消耗配件
- 配件：`add_stock("part", ...)` + 通过 `part_bom` 消耗子配件

### 前端

收回单创建页、收回单详情页中：
- "待收回列表"同时显示饰品产出和配件产出
- 配件产出项的 `item_type` 显示为"配件"而非"饰品"

## 五、组合配件成本

### 成本公式

有 part_bom 的配件（组合件）：
```
unit_cost = Σ(子配件.unit_cost × part_bom.qty_per_unit) + assembly_cost
```

无 part_bom 的配件：`unit_cost` 手动维护（现有逻辑不变）。

### 数据模型

**`part`** 表新增字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| assembly_cost | Numeric(18,7), nullable | 组装手工费 |

### assembly_cost 同步

复用现有 `cost_sync` 模式：手工收回单收回配件 c 时，receipt item 的 `price` 自动同步到 `Part.assembly_cost`（与饰品的 `handcraft_cost` 同步方式一致）。

### unit_cost 自动计算

`unit_cost` 字段保留在数据库中，标记为"自动计算"。触发重算的时机：

1. **part_bom 变化**：增删改子配件 BOM 时重算
2. **子配件 unit_cost 变化**：更新子配件成本时，找到所有引用它的父配件并重算
3. **assembly_cost 变化**：手工收回同步 assembly_cost 后重算

重算函数：`recalc_part_unit_cost(db, part_id)`，在上述三个时机调用。

### 前端

配件详情页：
- 有子配件的配件，`unit_cost` 显示为"自动计算"，不可手动编辑
- 显示成本明细：子配件成本 + 手工费 = 总 unit_cost
- `assembly_cost` 字段可手动编辑（也会被收回单自动同步）

## 六、订单 TodoList 影响

- TodoList 只展示一层，配件 c 作为整体出现
- 配件 c 的库存判断：`get_stock("part", c)` >= 所需数量
- 不展开 c 的子配件（e, f, g 不出现在 TodoList 中）
- 配件汇总（BOM）同样只展示一层
