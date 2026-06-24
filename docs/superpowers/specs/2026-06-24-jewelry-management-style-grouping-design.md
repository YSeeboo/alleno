# 饰品管理刷新 + 款式归属 / 配件变体折叠 — 设计文档

- 日期：2026-06-24
- 分支：`feat/jewelry-style-grouping`
- Mockup：`docs/superpowers/mockups/jewelry-management-mockup.html`

## 1. 背景与目标

当前饰品管理（`frontend/src/views/jewelries/JewelryList.vue`）相对配件管理（`PartList.vue`）体验落后：

1. 类目只是一个普通文本列，无法按类目筛选、无分组。
2. 视觉仍是旧的 `.page-header / .filter-bar` 风格，未对齐配件页面的刷新设计（统计卡 / chips / ink-outline 按钮 / 设计 token）。
3. 同款不同色/不同吊坠的近似饰品只能各开一条、互不相关，列表臃肿。

本设计解决以上三点，并顺带优化配件管理的变体展示。涉及两个页面：

- **A. 饰品管理** —— 视觉刷新 + 「款式归属」（同款分组）+ 「添加同款」入口。
- **B. 配件管理** —— 变体从平铺改为可展开折叠（纯展示）+ 一个「组合件不允许变体」的守卫。

## 2. 关键决策（已与用户对齐）

| 决策点 | 结论 |
|---|---|
| 归组形态 | 轻量分组（B1）：每条同款仍是独立饰品记录（独立 ID / 库存 / 价格 / BOM / 详情页），不做完整变体生命周期。 |
| 归属存储 | 用一列 `style_group` 存归属（**不靠解析 ID**）；ID 后缀 `-A/-B` 仅作显示。与配件用 `parent_part_id` 列做真相、后缀作装饰的思路一致。 |
| 编号方案 | 基准 `SP-SET-00002`，同款追加 `-A`、`-B`…，基准 ID 不变。 |
| 创建入口 | 在某条饰品上点「＋ 添加同款」（方案 A），以它为基准生成同款。 |
| BOM | 添加同款时**默认带入基准 BOM**（可在详情页清空）。 |
| 列表展示 | **可展开款式组**，默认**折叠**；基准行带 `同款×N` 计数 pill。 |
| 配件范围 | 仅「变体折叠/展开」这一前端展示改动 + 「组合件不允许变体」守卫。 |
| 独立可编辑 | 折叠/归组**只影响列表展示**，绝不改变任何记录的独立性：每条同款成员、每个配件变体都仍有独立详情页、可单独编辑自己的数据。 |

## 3. 数据模型变更

### 3.1 jewelry 表新增 `style_group`

```python
# models/jewelry.py
style_group = Column(String, nullable=True, index=True)
```

- 语义：款式组归属键，值 = 基准饰品 ID（如 `SP-SET-00002`）。
- `NULL` = 未归组（独立单条，列表里无展开箭头）。
- 通过 `ensure_schema_compat()` 的 additive 模式加列（无需 Alembic），与现有惯例一致。
- 配套补一个索引（`index=True` 即可）以支持按组查询。

**为什么不存在 jewelry 上加 `parent_jewelry_id` 这种 FK？** 因为同款成员之间是平级、无父子语义（基准 ID 不变、被删后由前端兜底选表头），只需要一个共享的分组键即可，FK 反而引入删除/级联负担。

### 3.2 配件无模型变更

配件已有 `parent_part_id`，本设计不动配件数据模型。

## 4. 后端变更

### 4.1 饰品 —— 添加同款服务

`services/jewelry.py` 新增：

```python
def add_jewelry_sibling(db: Session, base_id: str, data: dict) -> Jewelry:
    """以 base_id 为基准，创建一条同款饰品。"""
```

行为：

1. **解析基准组**：取 `base = get_jewelry(base_id)`。基准组键 `group = base.style_group or base.id`。
   - 不嵌套：若从某成员（如 `SP-SET-00002-A`）发起，`group` 仍解析为 `SP-SET-00002`，新成员挂回同组，不会出现 `-A-A`。
2. **回填基准的 style_group**：若 `group == base.id` 且基准 `style_group IS NULL`，把基准自身的 `style_group` 写成 `group`（首次成组时让基准也可被 `WHERE style_group = group` 查到）。
3. **分配后缀 ID**：扫描所有 `id LIKE '{group}-%'` 且属于本组的成员，取下一个可用后缀。序列规则：`A..Z` → `AA..AZ` → `BA..` …（26 进制字母序，极少超过 Z）。新 ID = `f"{group}-{suffix}"`。
   - ID 由 `style_group` 推导，但**不作为分组真相**——分组真相始终是 `style_group` 列。
4. **沿用 / 预填**：`category` 沿用基准且锁定；`name / unit / retail_price / wholesale_price / image / color` 由前端传入（弹窗预填基准值后用户可改）。
5. **写库**：创建 jewelry 行，`style_group = group`，`id = 新后缀 ID`。
6. **带入 BOM**：复制基准的 BOM 配件清单到新饰品（复用现有 `copy_jewelry` 的 BOM 复制逻辑，抽出共享 helper）。

对应 API：`api/jewelries.py` 新增 `POST /{base_id}/siblings`（permission `jewelries`），body 复用一个精简的 `JewelrySiblingIn`（name/color/unit/retail_price/wholesale_price/image，均可选）。

前端 API 包装：`frontend/src/api/jewelries.js` 加 `addJewelrySibling(baseId, data)`。

### 4.2 配件 —— 组合件守卫

`services/part.py`：

- `create_part_variant(...)`：在 `_validate_variant_request` 或函数开头加守卫——若根件 `is_composite is True`，`raise ValueError("组合件不支持变体")`。
- `create_part(...)`：当传入 `parent_part_id` 且该 parent `is_composite is True` 时同样报错。

**理由**：现状下给组合件加变体会生成「非组合、带滚算成本、却无 BOM」的畸形记录（`create_part_variant` 不复制 `is_composite` 也不复制组合 BOM）。本守卫把语义说清：组合件的颜色由其子配件决定，要换色应以换色子件另组一个组合件。

### 4.3 列表接口

- `list_jewelries` 保持返回**扁平**列表，并在响应 schema 中带上 `style_group` 字段（`schemas/jewelry.py` 增加 `style_group: Optional[str]`）。前端自行按 `style_group` 拼分组树。
- `list_parts` 已返回扁平列表（含 `parent_part_id`），无需改动。

## 5. 前端变更

### 5.1 饰品管理 JewelryList.vue（对齐配件视觉 + 可展开）

复用 `PartList.vue` 的设计 token 与类名（`.page-top / .stat-strip / .chip / .table-wrap / .btn-ink / .btn-outline / .modal-sec-h / .modal-pill` 等）。

布局：

- **page-top**：面包屑「商品 / 饰品管理」+ 标题 `饰品管理 共 N 件饰品 · M 个款式组` + 操作「从模板创建 / 新增饰品」。
- **stat-strip**（3 卡）：饰品总数 / 低库存预警（低于阈值标红）/ 已停用。
- **filter-row**：类目 chips `全部 / 套装 / 单件 / 单对 / 未分类` + 右侧搜索框。
  - 「未分类」桶：`category` 为空或非法的历史饰品归此。
- **table-wrap**：可展开款式组表格。

分组树构建（前端）：

- 按 `style_group` 分桶。
- **基准/表头行**：组内 `id == style_group` 的那条；若该条已被删除，则取组内**最小 ID** 成员当表头（兜底，不孤儿化）。
- **子行**：组内其余成员，缩进展示，ID 列高亮后缀 `-A`。
- `style_group IS NULL` 的饰品 = 独立单条，无展开箭头。
- 默认**折叠**；基准行带 `同款×N` 计数 pill；展开箭头 `▸`。
- 列：编号 / 饰品(图+名) / 类目 / 颜色(色点) / 单位 / 零售价 / 批发价 / 总成本 / 库存(低库存标红) / 状态 / 操作。
- 价格沿用现有内联编辑（`renderInlinePrice`）。

「添加同款」入口：

- 在基准行（及独立单条行）操作区放「＋ 添加同款」图标按钮。
- 打开「添加同款」弹窗：
  - 标题右侧 ID 预览 `将生成 SP-SET-00002-C`。
  - 顶部提示条：归属款式组、已预填、已带入基准 BOM。
  - 字段：名称 / **图片（预填基准图 + 上传图片按钮，可替换）** / 类目（pill，锁定不可改）/ 颜色 / 单位 / 零售价 / 批发价。
  - 图片上传复用现有 `ImageUploadModal`（`kind="jewelry"`）。
  - 提交调用 `addJewelrySibling(baseId, payload)`，成功后刷新列表并自动展开该组。

弹窗整体改造为分区式（`modal-sec-h` + `modal-grid2` + 类目 pill），与配件弹窗一致；现有「新增 / 编辑 / 复制」弹窗同步对齐视觉。

### 5.2 配件管理 PartList.vue（变体折叠）

- 由 `parent_part_id` 拼分组树：根件（`parent_part_id IS NULL`）为表头行，变体为子行。
- 平铺改为**可展开**，默认**折叠**；根行带 `变体×N` 计数 pill + 展开箭头。
- 组合件：`组合` 标签与 `变体×N` 计数可并存（虽守卫后新组合件不会再有变体，但历史数据可能存在，需兼容展示）。
- 组合件行**隐藏**「＋ 加变体」入口（呼应 §4.2 守卫）。
- 统计卡 / chips / 弹窗保持现状（已是刷新版）。

### 5.3 展开/折叠交互

- 用 `n-data-table` 的可展开行能力（`row-key` + 树形 `children` 或 `expandable` 渲染），或自管理 `expandedGroups` 集合 + 条件渲染子行。实现时选其一，保持两页一致。

## 6. 边界与规则

- **不嵌套**：从任何成员发起「添加同款」都挂回基准组。
- **后缀耗尽**：`A..Z` 后进入 `AA..`，实际几乎不会触及。
- **删除基准**：后端不阻止删除；前端表头兜底取组内最小 ID 成员，避免孤儿组。
- **独立可编辑**：每条同款成员 / 每个配件变体都保留独立详情页与字段编辑能力，归组仅影响列表展示。
- **库存 / 订单 / BOM / 手工 / 电镀**：均不受款式归组影响（仍按各自独立 ID 计算），blast radius 限于列表展示 + 创建便利 + 一列 `style_group` + 一个配件守卫。

## 7. 不做（YAGNI）

- 不做完整饰品变体生命周期（独立电镀/手工状态机等）。
- 不做款式组级别的库存/价格聚合。
- 不做配件数据模型变更、不批量回填历史饰品的 `style_group`（保持各自独立，用户按需「添加同款」）。
- 不引入 `parent_jewelry_id` FK。

## 8. 测试要点

- `add_jewelry_sibling`：基准组解析（从基准 / 从成员发起）、`style_group` 回填、后缀分配（A→B→…、跳过已存在）、类目沿用、BOM 复制、不嵌套。
- 组合件守卫：`create_part_variant` 与 `create_part(parent=composite)` 均报 `ValueError`。
- `list_jewelries` 响应含 `style_group` 字段。
- 前端分组树构建：基准被删的兜底表头选择、未分类桶、独立单条无箭头。
