# 电镀配件颜色变体优化 V2

## 背景

V1 方案（配件页创建变体 + 电镀单下拉选择）流程繁琐，用户需在配件页和电镀单之间来回切换。V2 将变体创建直接集成到电镀单操作中。

## 可配置颜色变体

`services/part.py` 中定义：

```python
COLOR_VARIANTS = [
    {"code": "G", "label": "金色"},
    {"code": "S", "label": "白K"},
    {"code": "RG", "label": "玫瑰金"},
]
COLOR_SUFFIXES = [v["label"] for v in COLOR_VARIANTS]
```

后续增加颜色只需追加此列表。

### 变体判断规则

配件名称以 `_{任一 COLOR_SUFFIXES}` 结尾即为变体（如 `_金色`、`_白K`、`_玫瑰金`）。

### 变体命名

`{原件 name}_{颜色 label}`，如：`猪鼻子 2x10_金色`

## 后端变更

### 1. 修改 `create_part_variant(db, part_id, color_code)`

- 校验发出配件非变体（名称不以任何 `COLOR_SUFFIXES` 结尾），否则 ValueError "当前非原色配件，不可创建变体"
- 新配件名称 = `{原件 name}_{颜色 label}`
- 查找同 parent 下是否已存在该名称的配件，存在则直接返回
- 不存在则创建：复制 `name`(加后缀)、`category`、`unit`、`unit_cost`、`plating_process`、`image`，设 `color` 为颜色 label，`parent_part_id` 指向原件

### 2. 新增 API `POST /api/parts/{part_id}/find-or-create-variant`

请求体：`{ "color_code": "G" }`

逻辑：
- 校验 part_id 存在且非变体
- 根据 color_code 查找映射
- 构造目标名称 `{原件 name}_{颜色 label}`
- 查找同 parent 下是否已存在该名称的配件
  - 已存在 → 返回 `{ "part": PartResponse, "created": false }`
  - 不存在 → 返回 `{ "part": null, "created": false, "suggested_name": "猪鼻子 2x10_金色" }`

创建通过 `POST /api/parts/{part_id}/create-variant` 触发（用户确认后）。

### 3. 修改 `update_part()`

变体配件（名称以颜色后缀结尾）不可修改 `color` 字段。

### 4. 新增 API `GET /api/parts/color-variants`

返回 `COLOR_VARIANTS` 列表，前端用此获取可用颜色选项，而非硬编码。

### 5. Schema 变更

`schemas/part.py` 新增：

```python
class FindOrCreateVariantResponse(BaseModel):
    part: Optional[PartResponse] = None
    created: bool = False
    suggested_name: Optional[str] = None
```

## 前端变更

### 1. 电镀单 - 添加明细弹窗

```
发出配件:  [下拉选择]
电镀颜色:  [G] [S] [RG]  (可不选，不选=收回原件)
对应配件:  猪鼻子 2x10_金色 (PJ-DZ-00003)  ← 已存在时直接展示
           或 [新建] 按钮 ← 不存在时显示
数量:      [___]
单位:      [___]
备注:      [___]
```

- 选择发出配件后默认选中 G
- 选中 G/S/RG 时调用 `find-or-create-variant` 查询
- 不选任何颜色时，对应配件区域不显示，`receive_part_id` 为 null
- 点击"新建"弹出确认框："当前没有 猪鼻子 2x10_金色，确定新建吗？"
- 确认后调用 `create-variant`，成功后自动填充 `receive_part_id`
- 订单非 pending 状态时 G/S/RG 不可操作

### 2. 电镀单详情 - 明细表格列

| 编号 | 配件 | 数量 | 电镀颜色 | 收回配件 | 已收回 | 操作 |

- **电镀颜色**列：根据 `receive_part` 名称后缀匹配显示 G/S/RG 角标，无收回配件显示 `-`
- 删除原"电镀方式"下拉，`plating_method` 根据颜色选择自动设置
- 取消收回配件列的角标

### 3. 配件管理页

移除 V1 新增的 G/S/RG 创建按钮（变体创建已迁移到电镀单流程中）。

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `services/part.py` | `COLOR_VARIANTS` 配置；修改 `create_part_variant` 命名和变体判断逻辑；新增 `find_or_create_variant` |
| `schemas/part.py` | 新增 `FindOrCreateVariantResponse` |
| `api/parts.py` | 新增 `POST /{id}/find-or-create-variant`；新增 `GET /color-variants` |
| `frontend/src/api/parts.js` | 新增 `findOrCreateVariant`、`getColorVariants` API 调用 |
| `frontend/src/views/plating/PlatingCreate.vue` | 收回配件下拉改为 G/S/RG 按钮 + 对应配件展示 |
| `frontend/src/views/plating/PlatingDetail.vue` | 同上；明细表列调整 |
| `frontend/src/views/parts/PartList.vue` | 移除 V1 的 G/S/RG 按钮 |
