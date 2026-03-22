# 电镀配件颜色变体优化设计

## 问题

1. 电镀单详情中选择"收回配件"时，同名不同颜色的配件只能靠编号区分，无法直观判断颜色
2. 收回配件选择器展示全部配件列表，没有自动定位/过滤到已关联的配件
3. 创建颜色变体配件流程繁琐，需手动填写所有字段

## 设计

### 1. 快速创建颜色变体（后端）

**新增 API**: `POST /api/parts/{part_id}/create-variant`

请求体:
```json
{ "color_code": "G" }
```

color_code 映射:
| color_code | color 值 | 含义 |
|------------|---------|------|
| G | 金色 | Gold |
| S | 白K | Silver |
| RG | 玫瑰金 | Rose Gold |

**逻辑**:
1. 校验 part_id 存在且是根配件（无 parent_part_id）
2. 校验 color_code 合法（G/S/RG）
3. 查询该根配件下是否已存在相同 color 的子配件，若存在则抛出 ValueError（"已存在金色变体"）
4. 创建新配件：复制原件的 `name`、`category`、`unit`、`unit_cost`、`plating_process`、`image`，设置 `color` 为映射值，`parent_part_id` 指向原件
5. 使用 `_next_id_by_category` 生成新 ID
6. 返回新创建的配件

**新增 service 函数**: `create_part_variant(db, part_id, color_code)` in `services/part.py`

### 2. 禁止变体配件修改颜色（后端）

修改 `update_part()` in `services/part.py`:
- 如果配件有 `parent_part_id`（是变体配件），且 `data` 中包含 `color` 字段，则抛出 ValueError（"变体配件不可修改颜色"）

### 3. 获取变体列表（后端）

**新增 API**: `GET /api/parts/{part_id}/variants`

**逻辑**:
1. 查询 part_id 对应的配件
2. 如果是根配件，返回所有 `parent_part_id == part_id` 的子配件
3. 如果是变体配件，返回同 parent 下所有兄弟配件（含自身和 parent）
4. 返回 `List[PartResponse]`

### 4. 文件变更清单

| 文件 | 变更 |
|------|------|
| `services/part.py` | 新增 `create_part_variant()`；修改 `update_part()` 禁止变体改颜色 |
| `schemas/part.py` | 新增 `PartVariantCreate` schema（字段: `color_code: str`） |
| `api/parts.py` | 新增 `POST /{part_id}/create-variant` 和 `GET /{part_id}/variants` 两个端点 |

### 5. 校验规则汇总

- `color_code` 必须是 `G`、`S`、`RG` 之一，否则 400
- 目标配件必须是根配件（无 parent_part_id），否则 400："只有原色配件才能创建颜色变体"
- 同一根配件下同一颜色只能有一个变体，否则 400："已存在{color}变体"
- 变体配件的 `color` 字段不可通过 PATCH 修改，否则 400："变体配件不可修改颜色"
