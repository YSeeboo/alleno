# Handcraft Picking — 同配件合并 + 按 atom 称重

> 状态：设计稿（待实现）
> 涉及分支：`feat/handcraft-picking-simulation` 后续迭代
> 日期：2026-05-07

---

## 0. 一条核心约束

**这次改动是「展示层重排 + 称重数据流」。**

不会触碰：
- `inventory_log`（无入出库写入）
- 订单状态机（`pending` / `processing` / `completed` 不变）
- `HandcraftPartItem.qty` / `bom_qty` / `note`
- 库存余额计算（仍然是 `SUM(inventory_log.change_qty)`）

**会写的数据**：
- `HandcraftPickingRecord`（已存在；勾选状态——本次不动其结构）
- 新增 `HandcraftPickingWeight` 表（本次新增；记录每 atom 实际称重）

「全部勾完」**不会**触发任何状态机。要走出库还是要 `POST /send`。

---

## 1. 背景与动机

### 现状
配货模拟（picking simulation）的响应按 `HandcraftPartItem` 分组——一条 part_item 一组。同一原子配件如果对应多条 part_item（用户在创建手工单时按饰品分组录入了多条同 part_id 的 part_item），就会出现多组、需要分散浏览。

### 数据模型现实
- `HandcraftPartItem` 字段：`(handcraft_order_id, part_id, qty, bom_qty, unit, note, weight, weight_unit, status, received_qty)`
- **没有**外键关联到 `HandcraftJewelryItem`——创建手工单时前端按饰品分组录入 parts，但 `normalizedParts()` 在提交时已把所有分组拍平进单一数组（见 `HandcraftCreate.vue:375-391`），饰品来源信息在持久化时已经丢失
- 因此 picking sim 中**不能**展示"这个 part 是为哪个饰品"——数据库里没有

### 痛点
1. **无法一眼看清同配件的总量**：仓库人员需要心算同配件跨 part_item 的总需求
2. **称重信息缺失**：现有的 `HandcraftPartItem.weight` 字段在配件明细面板可编辑，但 picking 模拟里看不到也不能改——而仓库人员**实际称重的时机就在 picking 视图里**
3. **组合件展开后无法按 atom 独立称重**：同一条 `HandcraftPartItem.weight` 字段不能区分"链头 0.5kg + 扣环 0.3kg"

### 目标
1. 同原子配件跨 part_item 来源合并到一个组里展示
2. 每个子项行带可编辑的重量输入框
3. 重量数据与配件明细面板**双向同步**（同一份存储）
4. PDF 跟随 UI 一起合并

### 不在范围内
- 给 `HandcraftPartItem` 加 jewelry 关联外键（更大的设计变更）
- 自动从 BOM 反推饰品来源（启发式且不可靠）

---

## 2. UI 设计

### 2.1 总体布局（layout C）

```
┌─ 配货模拟 · HC-0042 · 张师傅 · pending ─────────────────────┐
│ [导出 PDF] [重置勾选] [关闭]                              │
├──────────────────────────────────────────────────────────┤
│ 总进度 1/6 (17%)  ▰▰▱▱▱▱                                │
│ 原子配件 4 种  ·  part_item 行 6 条                       │
├──────────────────────────────────────────────────────────┤
│ 配件/来源              重量      理论  建议  库存   已配  │
│ ▶ 链头 PJ-X-001 小件 · 1/3 已配                          │
│   合计                          310    410   1000        │
│   ↳ qty 200 · bom 200    [0.500]kg  200   250    —  ☑  │
│   ↳ qty 100 · bom 100    [    ]kg   100   150    —  ☐  │
│   ↳ qty 10 · bom 10 [来自套链 atom]                      │
│                          [    ]kg    10    60    —  ☐  │
│ ▶ 扣环 PJ-X-007 小件 · 0/1 已配                          │
│   合计                            10    60     200       │
│   ↳ qty 10 · bom 10 [来自套链 atom]                      │
│                          [    ]kg    10    60    —  ☐  │
└──────────────────────────────────────────────────────────┘
```

### 2.2 关键视觉规则

- **组头**（橙底，`#fff7e6`）：原子配件名 + ID + size_tier 标签 + 合计理论 + 合计建议 + 库存 + `N/M 已配`
- **组头·已全部配齐**：底色变绿（`#f6ffed`），组头文字变绿
- **组头·库存告警**：组头文字前加 `⚠`，库存数字红色（条件：`current_stock < total_suggested_qty`）
- **子行**：缩进 32px；展示 `qty XXX · bom XXX`（数字直白展示）
- **子行·已勾选**：非重量、非 checkbox 列文字灰色 + 删除线
- **库存只在组头展示一次**（同 atom 全局共享一个库存数）
- **顶部摘要条**：总进度条、原子配件种数、part_item 行总数（**不**说"来源饰品数"——数据不存）
- **组合件 atom 子行**：右侧加小灰标 `[来自 X atom]`（X = 父 part 的名字），区分"用户直接录入的"vs"组合件展开的"

### 2.3 列定义（从左到右）

| 列 | 组头 | 子行 |
|---|---|---|
| 配件 / 来源 | 配件名 + ID + tier + 进度文字 | `qty XXX · bom XXX` + 组合件小标签（如适用） |
| **重量** | — | 数字输入 + 单位下拉（默认 kg） |
| 理论 | 合计（子行求和） | 该 source × atom_ratio |
| 建议 | 合计（子行求和） | `compute_suggested_qty(atom_part, theo)` |
| 库存 | 该 atom 的全局库存 | — |
| 已配 | 进度文字（如 `1/2`） | checkbox（行尾） |

**重要**：重量列在「配件/来源」与「理论」之间——按用户要求。

### 2.4 子行不展示 `note`

`note` 字段保留在 `HandcraftPartItem` 上，配件明细面板继续可编辑，但 picking sim 视图**不显示**。区分同 atom 跨 part_item 的多个子行**仅靠 qty 数字 + 组合件小标签**。

### 2.5 状态门控（read-only / editable）

| 订单状态 | 勾选 | 重量编辑 | 重置 |
|---|---|---|---|
| `pending` | ✅ | ✅ | ✅ |
| `processing` / `completed` | ❌ | ❌ | ❌ |

重量与勾选采用同一套门控——简单一致。如果以后需要"称重可在任何状态下记录"，再单独放开。

### 2.6 排序

- **组之间**：按该原子配件**首次出现**在 part_items 中的顺序（保持创建手工单时的录入顺序感）
- **组内子项**：按 `(part_item.id ASC, atom_part_id ASC)` —— 先按录入顺序，组合件展开行靠后

---

## 3. 数据模型

### 3.1 新增表 `handcraft_picking_weight`

```python
class HandcraftPickingWeight(Base):
    __tablename__ = "handcraft_picking_weight"
    id = Column(Integer, primary_key=True)
    handcraft_order_id = Column(String, ForeignKey("handcraft_order.id", ondelete="CASCADE"), nullable=False)
    part_item_id = Column(Integer, ForeignKey("handcraft_part_item.id", ondelete="CASCADE"), nullable=False)
    atom_part_id = Column(String, ForeignKey("part.id"), nullable=False)
    weight = Column(Numeric(10, 4), nullable=False)
    weight_unit = Column(String, nullable=False, default="kg")
    recorded_at = Column(DateTime, nullable=False, default=now_beijing)

    __table_args__ = (
        UniqueConstraint("part_item_id", "atom_part_id", name="uq_picking_weight_pa"),
        Index("ix_picking_weight_order", "handcraft_order_id"),
    )
```

**设计说明**：
- `(part_item_id, atom_part_id)` 唯一——picking sim 的每个子行对应一行（atomic 1 条；composite N 条）
- 删除 `HandcraftPartItem` 自动 cascade 删除对应权重
- `weight_unit` 默认 `kg`（与现有 `HandcraftPartItem.weight_unit` 默认 `g` 不一致——见 §5 迁移）

### 3.2 旧字段处理：`HandcraftPartItem.weight` / `weight_unit`

**保留字段，但服务层和前端配件明细面板改为读写新表。**

- 字段不删（避免破坏未来可能的引用），但服务层不再写入
- 新代码只读写 `HandcraftPickingWeight`
- 一次性迁移见 §5

### 3.3 配件明细面板的读取逻辑（`HandcraftDetail.vue` 的 parts table）

| 行类型 | 重量列展示 | 编辑行为 |
|---|---|---|
| atomic part_item | `HandcraftPickingWeight.weight`（filter by `(part_item_id, atom_part_id == part_item.part_id)`，唯一一条） | 写入该单条记录（写新表）|
| composite part_item | **SUM** of all `HandcraftPickingWeight.weight` rows where `part_item_id` = this | 🔒 只读，tooltip 提示「请在配货模拟中按 atom 输入」 |

**注意单位混合**：composite 子行可能用不同 unit 称重。SUM 之前需统一单位（约定：先转为 kg 再 SUM；显示成 kg）。

---

## 4. 后端响应改造

### 4.1 新响应结构（`HandcraftPickingResponse`）

```python
class PickingSourceRow(BaseModel):
    """A single (part_item × atom_part_id) slice."""
    part_item_id: int
    atom_part_id: str
    qty: float                          # atomic: part_item.qty 原值；composite: part_item.qty × atom_ratio
    bom_qty: Optional[float]            # atomic: part_item.bom_qty 原值；composite: part_item.bom_qty × atom_ratio
    is_composite_expansion: bool        # 来自组合件展开则为 True
    parent_composite_name: Optional[str]  # is_composite_expansion 为 True 时填，用作小标签
    needed_qty: float                   # = bom_qty × atom_ratio（如适用）；用于建议计算
    suggested_qty: Optional[int]        # 该次 compute_suggested_qty
    weight: Optional[float]             # 从 HandcraftPickingWeight 读
    weight_unit: Optional[str]          # 默认 "kg"
    picked: bool                        # 来自 HandcraftPickingRecord


class PickingGroup(BaseModel):
    """All rows for a single atomic part_id, across all part_items."""
    atom_part_id: str
    atom_part_name: str
    atom_part_image: Optional[str]
    size_tier: SizeTier
    current_stock: float                # 同 atom 全局库存（一次）
    total_needed_qty: float             # 子行求和
    total_suggested_qty: int            # 子行求和（不重新套规则！）
    rows: List[PickingSourceRow]


class HandcraftPickingResponse(BaseModel):
    handcraft_order_id: str
    supplier_name: str
    status: str
    groups: List[PickingGroup]
    progress: HandcraftPickingProgress
```

### 4.2 关键计算规则

- `PickingSourceRow.suggested_qty = compute_suggested_qty(atom_part, needed_qty)` —— 每个 source 各自计算并各自含 floor 兜底
- `PickingGroup.total_suggested_qty = sum(row.suggested_qty for row in rows)` —— **直接求和，不重新套规则**

举例（小件 50/2%）：
- part_item#1 qty=200 → 建议 250（含 floor 50）
- part_item#2 qty=100 → 建议 150（含 floor 50）
- `total_suggested_qty = 400`（不是 350）

### 4.3 排序实现

`atoms_first_seen = {}`——遍历 `part_items`（按 id ASC）时记录每个 `atom_part_id` 首次出现的 `part_item.id`。最终 groups 按这个值排序；组内 rows 按 `(part_item_id ASC, atom_part_id ASC)`。

### 4.4 端点变化

| 端点 | 改动 |
|---|---|
| `GET /api/handcraft/{id}/picking` | 响应结构改为 `groups: List[PickingGroup]`；rows 字段重新设计（见 4.1） |
| `POST /api/handcraft/{id}/picking/mark` | **不变**（粒度仍是 part_item_id × part_id）|
| `POST /api/handcraft/{id}/picking/unmark` | **不变** |
| `DELETE /api/handcraft/{id}/picking/reset` | **不变** |
| `POST /api/handcraft/{id}/picking/pdf` | PDF 渲染按新分组（见 §6）|
| `PUT /api/handcraft/{id}/picking/weight` | **新增**：body `{part_item_id, atom_part_id, weight, weight_unit}`；upsert（pending 状态才允许）|
| `DELETE /api/handcraft/{id}/picking/weight` | **新增**：body `{part_item_id, atom_part_id}`；删除该重量记录（pending 状态才允许）|
| `PATCH /api/handcraft/{id}/parts/{item_id}` (existing) | atomic part_item：weight 字段路由到新表；composite：拒绝 weight 字段（返回 400）|

### 4.5 服务层

新增模块 `services/handcraft_picking_weight.py`：
- `get_weight(db, part_item_id, atom_part_id) -> Optional[Weight]`
- `upsert_weight(db, order_id, part_item_id, atom_part_id, weight, unit) -> Weight` — 必须校验 part_item 属于 order，atom_part_id 真实存在
- `delete_weight(db, part_item_id, atom_part_id) -> bool`
- `sum_weight_by_part_item(db, part_item_id, target_unit="kg") -> Optional[float]` — 给配件明细面板用，混合单位时统一为 kg
- `bulk_load_for_picking(db, order_id) -> dict[(part_item_id, atom_part_id), Weight]` — picking sim 一次性加载

**单位换算约定**：1 kg = 1000 g。混合单位 SUM 时统一转 kg。前端展示时按存储单位原样展示（不强转）。

---

## 5. 迁移

### 5.1 schema 迁移（`ensure_schema_compat`）

- `CREATE TABLE handcraft_picking_weight ...`（如果不存在）
- 不动 `HandcraftPartItem.weight` 列

### 5.2 数据迁移（`ensure_schema_compat` 里幂等执行）

```sql
-- 把已有的 HandcraftPartItem.weight 迁移到新表
-- atomic part_item: atom_part_id = part_item.part_id
-- composite part_item: atom_part_id = part_item.part_id（保留为"整批"语义；用户可后续按 atom 重新输入）
INSERT INTO handcraft_picking_weight
  (handcraft_order_id, part_item_id, atom_part_id, weight, weight_unit, recorded_at)
SELECT
  hpi.handcraft_order_id, hpi.id, hpi.part_id,
  hpi.weight, COALESCE(hpi.weight_unit, 'g'),
  NOW()  -- 实际实现用 now_beijing()
FROM handcraft_part_item hpi
WHERE hpi.weight IS NOT NULL
ON CONFLICT (part_item_id, atom_part_id) DO NOTHING;
```

迁移幂等（`ON CONFLICT DO NOTHING`），不强转 kg（保留原 g）。

### 5.3 单位

- 新表默认 `kg`（DB 默认值）
- 前端默认下拉值：`kg`（新行）、原值（已有行 / 迁移过来的旧行）
- 用户可在 picking sim 切换单位

---

## 6. PDF 改造

PDF 渲染按新分组：每个原子配件一个分组小标题，下面列各 part_item 子行。

```
┌ HC-0042 配货单 · 张师傅 ──────────────────────────────────┐
│ 链头 PJ-X-001 · 小件 · 合计 310（库存 1000）             │
│   qty 200·bom 200    重 0.5kg   建议 250  ☐            │
│   qty 100·bom 100    重 _ _ _   建议 150  ☐            │
│   qty 10·bom 10 [来自套链 atom] 重 _ _ _  建议 60  ☐    │
│                                                       │
│ 心形吊坠 PJ-DZ-005 · 中件 · 合计 100（库存 300）          │
│   qty 100·bom 100    重 _ _ _   建议 115  ☐            │
└───────────────────────────────────────────────────────┘
```

- 排序与 UI 一致（首次出现）
- 已勾选的子行依然不打印（`include_picked=False` 默认）
- 重量字段直接读自 `HandcraftPickingWeight`
- 组合件展开 atom 子行带 `[来自 X atom]` 标签

---

## 7. 前端实现要点

### 7.1 picking sim modal（`HandcraftPickingSimulationModal.vue`）

- 重写 table 渲染逻辑：扁平化 `groups` → 双层 row（组头 + 子行）
- **列序**：`配件/来源 | 重量 | 理论 | 建议 | 库存 | 已配`（重量在理论左侧）
- 子行重量输入：`<n-input-number :precision="4" :min="0" />` + 单位下拉（`kg` / `g`）
- onBlur → `PUT /picking/weight`；输入清空 → `DELETE /picking/weight`
- 库存只在组头展示
- 组头不可勾选（无 master checkbox）
- 子行不展示 `note`

### 7.2 配件明细面板（`HandcraftDetail.vue` 的 parts table）

- 重量列：原子件正常显示输入框 → 走新端点；组合件显示 SUM（read-only）
- 加载页面时 `bulk_load_weight_by_part_item` 拿到每条 part_item 的 weight 视图（atomic 取单条；composite 取 SUM）

### 7.3 共享辅助

- 在前端封装 `pickingWeightApi` 模块，包含 upsert/delete/sumByPartItem 接口

---

## 8. 边界场景

| 场景 | 处理 |
|---|---|
| 同一 atom 既被组合件展开、又被直接添加 | 自动落进同一组（这正是合并的目的）|
| 子项只有 1 个 | 仍显示组头 + 1 子行，保持视觉一致 |
| `bom_qty IS NULL` 或 0 | `needed_qty` 为 0；建议显示 `—`；重量仍可输 |
| 组合件一边 atom 称了、一边没称 | 配件明细面板的 SUM 只算已称的 |
| 删除 part_item | cascade 删除其所有 picking_weight + picking_record 行 |
| 删除组合件父 part（如把套链整条配件改名）| 不影响 picking_weight（FK 是 part_item_id 不是 part.id）|
| 不同 size_tier 同 atom 在合并组内 | 不会发生——`size_tier` 是 `Part` 的字段，同 part_id 必同 tier |
| 重置勾选时是否清重量 | **不清**——重量是物理事实，与勾选状态无关 |
| 配件明细面板 composite 行 SUM 时单位混合 | 统一为 kg 后 SUM；前端文案 "≈ 0.85 kg（折算）" |

---

## 9. 范围外（不在本次实现）

- 整批称重（composite 整批一个数）的专门 UI affordance —— 用户可以"在所有 atom 行随便填一个 + 其余留空"达到效果
- weight 历史变更日志 —— 只保留最新值，不做审计表
- 跨手工单的称重统计 / 报表
- weight 超过库存阈值时的告警
- 单位换算自动化（`g` ↔ `kg`） —— 用户自己选
- 给 `HandcraftPartItem` 加 jewelry 来源外键 —— 更大设计变更

---

## 10. 验证清单（实现完成时）

- [ ] 同 atom 跨 part_item 来源在 UI 中合并显示
- [ ] 组合件展开 atom 子行带「来自 X atom」小标签
- [ ] 子行 checkbox 仍走原 mark/unmark 端点（粒度未变）
- [ ] 重量输入 onBlur 持久化到新表，单位默认 kg
- [ ] 重量在 picking sim 与配件明细面板中显示一致
- [ ] composite part_item 的 atom 行各自独立称重，互不干扰
- [ ] 配件明细面板 composite 行展示 SUM 且只读，混合单位时统一为 kg
- [ ] PDF 按新分组渲染、已勾选行不出现在 PDF
- [ ] 状态非 pending 时所有编辑（勾选+重量）都被禁用
- [ ] 一次性数据迁移：原 `HandcraftPartItem.weight` 迁入新表，幂等
- [ ] 删除 part_item 时 cascade 清理 picking_weight 记录
- [ ] 列序为「配件/来源 → 重量 → 理论 → 建议 → 库存 → 已配」
- [ ] 子行不展示 `note`
- [ ] 测试覆盖：原子件单一来源、原子件多来源、组合件、原子+组合混合
