# 手工单配货模拟（Handcraft Picking Simulation）设计

**Date**: 2026-04-27
**Status**: Draft（待用户审阅）
**Related**: `docs/superpowers/specs/2026-04-16-picking-simulation-design.md`（订单端原版）

## 背景

订单详情页的「配件汇总（BOM）」卡片提供「配货模拟」功能：聚合订单需要的所有配件、展开复合件到原子件、对比当前库存、勾选拣货进度、导出 PDF。仓库人员用它在出库前完成备料核对。

手工单详情页的「配件明细」卡也描述了"要发出的配件清单"，但目前**没有**对应的配货模拟视图。仓库在发出手工单前缺少同样的备料/勾选/打印工具。

本设计在手工单详情页引入「配货模拟」，复用订单端的视觉风格与交互习惯，但适配手工单独立的数据模型（扁平 `HandcraftPartItem` 列表，无 BOM 反推），并增加一列「建议数量」。

## 目标

仓库人员在发出手工单前能够：

1. 一键打开模态，查看展开后**所有要从仓库拣的原子配件**清单。
2. 每行对照**实际需要数量** vs **当前库存** vs **建议数量（含 buffer）**。
3. 勾选拣货完成进度，状态持久化（关闭模态再打开仍在）。
4. 「只看未完成」过滤、「重置勾选」清空、「导出 PDF」给现场打印。
5. 已发出（`processing`/`completed`）的手工单仍可打开模态，但只读。

## 非目标

- 不复用 `OrderPickingRecord` 表 —— 外键不同（`order_item` vs `handcraft_part_item`）。
- 不修改手工单状态机或扣库存逻辑 —— 配货模拟是纯 UI 助手，零侧效应。
- 不抽 `services/picking.py` 与新服务的公共基类 —— 数据模型差异大，强行复用代价高于收益。
- 不改手工单创建/编辑流程，不动 `HandcraftPartItem` schema。
- 不为前端补单元测试（项目惯例），依赖手测验证。

## 与订单端配货模拟的关键差异

| 维度 | 订单端 | 手工单端 |
|---|---|---|
| 数据来源 | `OrderItem` 经 BOM 反推 | `HandcraftPartItem` 用户手填 |
| 行模型 | 按 `(part_id, qty_per_unit)` 聚合 → 变体 | 每条 `HandcraftPartItem` 一组（独立勾选） |
| 复合件 | 递归展开成原子 | 同样递归展开，但归属到所属 part_item 分组 |
| 展示 | 扁平表（按 part 合并，多变体子行） | 按 part_item 分组，每组一行或多行原子 |
| 建议数量 | 无 | 有，按原子件 size_tier 重新计算 |
| 状态门控 | 不限 | `pending` 可写，其他状态只读 |

## 数据模型

### 新增表 `handcraft_picking_record`

```python
# models/handcraft_order.py 新增

class HandcraftPickingRecord(Base):
    """Per-row picking state for handcraft orders' 配货模拟.
    Row exists = picked; no row = not picked."""

    __tablename__ = "handcraft_picking_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    handcraft_order_id = Column(String, ForeignKey("handcraft_order.id"),
                                nullable=False, index=True)
    handcraft_part_item_id = Column(Integer, ForeignKey("handcraft_part_item.id"),
                                    nullable=False)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    picked_at = Column(DateTime, default=now_beijing, nullable=False)

    __table_args__ = (
        UniqueConstraint("handcraft_part_item_id", "part_id",
                         name="uq_handcraft_picking_record_item_part"),
    )
```

**关键决策**：

- **唯一键 `(handcraft_part_item_id, part_id)`** —— 拣货行的天然 key：
  - 原子件 part_item：`part_id == part_item.part_id`，唯一一条记录。
  - 复合件 part_item：展开后每个原子 atom 一条记录，`part_id == atom_id`。
  - 复合 BOM 多路径汇到同一原子时，读取阶段聚合 `needed_qty` 求和；持久化只一条。
- **冗余 `handcraft_order_id`** —— 便于按手工单批量查询/重置（避免 join）。
- **不加 `ON DELETE CASCADE`** —— 删除走应用层（删除 part item 的服务里同步清理）。
- **建表方式**：走 `Base.metadata.create_all()`（lifespan 启动），不需要 `ensure_schema_compat()` 加列。

### 添加表注册

在 `models/__init__.py` 的导入和 `__all__` 中添加 `HandcraftPickingRecord`。

## 后端服务与 API

### 新建 `services/handcraft_picking.py`

与 `services/picking.py` 平行，**不**复用，避免污染订单语义。

#### 核心函数

```python
def get_handcraft_picking_simulation(
    db: Session, handcraft_order_id: str
) -> HandcraftPickingResponse: ...

def mark_picked(
    db: Session, handcraft_order_id: str, part_item_id: int, part_id: str
) -> HandcraftPickingMarkResult: ...

def unmark_picked(
    db: Session, handcraft_order_id: str, part_item_id: int, part_id: str
) -> HandcraftPickingMarkResult: ...

def reset_picking(db: Session, handcraft_order_id: str) -> int: ...
```

#### `get_handcraft_picking_simulation` 流程

1. 加载 `HandcraftOrder` + 所有 `HandcraftPartItem`。空 part_items → 返回空 groups。
2. 加载所有相关 `Part`（直接的 + 复合件展开后涉及的），缓存 `is_composite`、`size_tier`、`name`、`image`。
3. 对每条 `HandcraftPartItem` 展开成"分组 → 拣货行"：
   - **原子件**：1 个分组 1 行，`needed_qty = part_item.qty`。
   - **复合件**：1 个分组 N 行（递归展开），每行 `needed_qty = parent.qty × atom_ratio`，多路径汇到同一原子时 `needed_qty` 求和。
4. 对每行计算 `suggested_qty`（详见下节）。
5. Batch 拉 `current_stock`（`SUM(InventoryLog.change_qty) WHERE item_type='part'`）。
6. Batch 拉 `picked_keys`（`HandcraftPickingRecord` 这个手工单的所有记录）。
7. 组装 response。

#### 复合件展开

复用 `services/picking._expand_to_atoms`（已稳定，处理递归 / cycle 防护 / Decimal 累乘 / 4 位小数量化）。这是跨服务 import，但不构成循环依赖，可接受。

#### 「建议数量」计算

规则与前端 `HandcraftDetail.vue` 的 `computeSuggestedQty` 完全一致：

```
BUFFER_RULES = {
    'small':  { ratio: 0.02, floor: 50 },
    'medium': { ratio: 0.01, floor: 15 },
}

suggested = ceil(theoretical) + ceil(max(floor, theoretical * ratio))
```

- **`tier`**：原子行用该原子件自己的 `Part.size_tier`（fallback 到 `small`，与前端一致）。
- **`theoretical`**：
  - 原子件 part_item：`theoretical = part_item.bom_qty`。
  - 复合件展开的原子行：`theoretical = parent.bom_qty × atom_ratio_in_composite`。
- **`bom_qty` 为空或 0**：`suggested_qty = None`，前端不显示「建议」标签。

将该规则在 `services/handcraft_picking.py` 中复现一份（不依赖前端临时算），原因：PDF 在后端生成需要 suggested；后端是单一可信源。

#### 状态门控

`mark_picked` / `unmark_picked` / `reset_picking` 进入服务后立即检查：

```python
if order.status != "pending":
    raise ValueError("手工单已发出，配货模拟为只读")
```

服务层是兜底防御；前端也会按 status 隐藏交互。

#### 孤儿记录处理

修改 `services/handcraft.py` 中删除 `HandcraftPartItem` 的函数，在 `db.delete(item)` 之前：

```python
db.query(HandcraftPickingRecord).filter_by(
    handcraft_part_item_id=item.id
).delete(synchronize_session=False)
```

避免外键约束错误，同时保持数据干净（不像订单端 `unmark_picked` 那种"允许操作孤儿"的隐性兼容路径）。

### 响应 Schema

```python
# schemas/handcraft.py 新增

class HandcraftPickingVariant(BaseModel):
    """One picking row inside a part_item group. For atomic items this is the
    only row; for composites this is one expanded atom."""
    part_id: str
    part_name: str
    part_image: Optional[str]
    needed_qty: float
    suggested_qty: Optional[int]
    current_stock: float
    picked: bool

class HandcraftPickingGroup(BaseModel):
    """One handcraft_part_item, with one or more picking rows under it."""
    part_item_id: int
    parent_part_id: str
    parent_part_name: str
    parent_part_image: Optional[str]
    parent_is_composite: bool
    parent_qty: float
    parent_bom_qty: Optional[float]
    rows: list[HandcraftPickingVariant]

class HandcraftPickingProgress(BaseModel):
    total: int
    picked: int

class HandcraftPickingResponse(BaseModel):
    handcraft_order_id: str
    supplier_name: str
    status: str  # 让前端决定只读/可编辑
    groups: list[HandcraftPickingGroup]
    progress: HandcraftPickingProgress
```

### API 路由（`api/handcraft.py` 新增）

```
GET    /handcraft/{order_id}/picking         → HandcraftPickingResponse
POST   /handcraft/{order_id}/picking/mark    body: {part_item_id, part_id}
POST   /handcraft/{order_id}/picking/unmark  body: {part_item_id, part_id}
DELETE /handcraft/{order_id}/picking/reset
POST   /handcraft/{order_id}/picking/pdf     → application/pdf (binary)
```

均走 `service_errors()` 把 `ValueError` 转成 HTTP 400，与项目惯例一致。

### PDF 导出

新建 `services/handcraft_picking_list_pdf.py`，参考 `services/picking_list_pdf.py` 的版式：

- 标题：「手工单配货清单」
- Header：手工单号 + 手工商家 + 日期
- 表格：分组展示，每组带 part_item 头（`组合件A × 5`），下面是原子拣货行
- 列：配件编号 / 配件 / 需要 / 建议 / 库存
- 已勾选行加删除线 + 灰底（与现场打印对照）

空清单 raise `ValueError("无可导出内容")`，前端 blob 解析 detail 提示。

## 前端

### 新建组件 `frontend/src/components/picking/HandcraftPickingSimulationModal.vue`

不复用 `PickingSimulationModal.vue`：数据结构（分组 vs 扁平变体）、列差异（多了「建议」列）、状态控制都不一样，强行复用会被 prop 分支噪声压垮。两组件结构互相平行，未来各自演进。

#### Props

```js
{
  show: Boolean,
  orderId: String,        // handcraft order id, e.g. HC-0042
  status: String,         // pending / processing / completed
}
```

#### 派生

- `readonly = status !== 'pending'` —— 控制 checkbox / 重置 / PDF 是否可点。
- `displayGroups`：基于 `data.groups` 应用「只看未完成」过滤；过滤后空的 group 整个隐藏。
- `progressText`：`X / Y 已完成`。

#### 展示结构（按 part_item 分组）

```
┌────────────────────────────────────────────────────────────────┐
│ 手工单 HC-0042 · 商家：xxx     进度: 12/30 已完成   [只看未完成 ⚪]│
│                                            [导出 PDF] [重置勾选] │
├────────────────────────────────────────────────────────────────┤
│ ▼ 行1：组合件A × 5 (理论 5)                                      │
│   ┌──────────┬─────────┬────────┬────────┬─────┐              │
│   │ atom1    │ 需要 10 │ 建议 12│ 库存 50│ ☐  │              │
│   │ atom2    │ 需要 15 │ 建议 18│ 库存 30│ ☐  │              │
│ ▼ 行2：atom1 × 8 (理论 7.5)                                      │
│   │ atom1    │ 需要 8  │ 建议 10│ 库存 50│ ☐  │              │
└────────────────────────────────────────────────────────────────┘
```

列定义：

| 列 | 内容 |
|---|---|
| 配件编号 | atom 的 `part_id` |
| 配件 | atom 头像 + 名字（若来自复合件展开，加「组合」小标签） |
| 需要 | `needed_qty`（千分位，整数省略小数点） |
| 建议 | `suggested_qty`（蓝色，tooltip 说明计算过程，参考现有 `buildSuggestedTooltip`） |
| 库存 | `current_stock`，`current_stock < needed_qty` 时红色 |
| 完成 | checkbox（readonly 时禁用） |

分组头展示该 part_item 的元信息：`▼ 行N：原 part_item 的配件 × qty (理论 X)`。

#### 只读语义（`readonly=true`）

- checkbox `disabled`
- 「重置勾选」按钮隐藏
- 「导出 PDF」按钮隐藏（已发出后导出意义不大）
- 「只看未完成」switch 仍可用（纯前端过滤，无副作用）

#### 乐观更新

复用订单端的写法：checkbox 切换时先改本地 state、调用 API，失败回滚（参考 `PickingSimulationModal.vue:58-71`）。

### API 客户端 `frontend/src/api/handcraft.js` 新增

```js
export const getHandcraftPicking = (id) => api.get(`/handcraft/${id}/picking`)
export const markHandcraftPicked = (id, partItemId, partId) =>
  api.post(`/handcraft/${id}/picking/mark`, { part_item_id: partItemId, part_id: partId })
export const unmarkHandcraftPicked = (id, partItemId, partId) =>
  api.post(`/handcraft/${id}/picking/unmark`, { part_item_id: partItemId, part_id: partId })
export const resetHandcraftPicking = (id) =>
  api.delete(`/handcraft/${id}/picking/reset`)
export const downloadHandcraftPickingPdf = (id) =>
  api.post(`/handcraft/${id}/picking/pdf`, {}, { responseType: 'blob' })
```

### 接入点：`HandcraftDetail.vue` 的「配件明细」卡 header

按钮顺序（左 → 右）：

```
[裁剪统计] [配货模拟] [批量关联订单] [+ 添加配件 (pending)]
```

`配货模拟` 按钮：

- 始终显示（不按 status 隐藏，因为 `processing`/`completed` 也能查阅历史）。
- `pending` 时主色 `type="primary"`，其他状态默认色。
- 点击 → `pickingModalShow = true`。

模态末尾挂在模板根：

```html
<HandcraftPickingSimulationModal
  v-model:show="pickingModalShow"
  :order-id="String(route.params.id)"
  :status="order?.status || 'pending'"
/>
```

## 测试

新建 `tests/test_api_handcraft_picking.py`，参考 `tests/test_api_picking.py` 形态。覆盖：

| 场景 | 断言要点 |
|---|---|
| 空手工单（无 part item） | `groups=[]`, `progress.total=0` |
| 全原子件 part items | 一组一行，`needed_qty = qty`，`current_stock` 正确 |
| 单个复合件 part item | 一组多行，每行 `needed_qty = parent.qty × atom_ratio` |
| 复合件多路径汇到同一 atom | 该 atom 的 `needed_qty` 是路径之和，picking 记录唯一 |
| 同一原子 part_id 出现在多个 part items | 多组，每组各自一行，可独立勾选 |
| 复合件含 cycle | `_expand_to_atoms` 已防 cycle，确认不死循环 |
| `mark` → `unmark` → `mark` | 幂等，记录恰好一条 |
| `mark` 不属于该手工单的 (item, atom) | raise ValueError → 400 |
| `mark` 在 `processing` / `completed` 状态 | raise ValueError("已发出，只读") → 400 |
| `reset` 删除所有记录，返回数量 | 包括跨 part_item 的全部 |
| 删除 `HandcraftPartItem` 后 picking 孤儿被清理 | 服务层删除路径覆盖 |
| `bom_qty` 为空或 0 | `suggested_qty=None` |
| `size_tier` 缺失 | 回落 `small` |
| `current_stock` 计算正确 | 一笔入库 + 一笔出库的 sum |

前端无单元测试（项目惯例），依赖手测：

- `pending` 状态下勾选/取消/重置/PDF 导出都正常
- `processing` 状态下打开为只读，checkbox 禁用，重置/PDF 按钮隐藏
- 复合件展开的原子行显示「组合」小标签
- 库存不足时数字红色
- 「只看未完成」隐藏已勾选行 + 空 group

## 错误处理

| 触发 | 用户看到 |
|---|---|
| 后端 raise ValueError | API 走 `service_errors()` 转 400，前端 `message.error(detail)` |
| 网络/服务挂掉 | `message.error('加载配货数据失败')`，关闭模态 |
| checkbox 乐观更新失败 | 本地状态回滚，`message.error(detail)` |
| 已发出后误点 mark | 后端 400 拦截 + 前端 readonly UI 双重防护 |
| PDF 导出空清单 | 后端 raise ValueError("无可导出内容")，前端读 blob 解析 detail 显示 |

## 边界与约定

1. **数量精度**：`needed_qty` 沿用 picking 服务的 4 位小数量化（`round(Decimal, 4)`）；`suggested_qty` 始终为整数（`ceil`）。
2. **库存对比着色**：`current_stock < needed_qty` 红色；建议数量不参与红色判定。
3. **进度计数**：`total = sum(len(group.rows) for group in groups)`，`picked` 数同；分组本身不算入分母。
4. **PDF 中的「建议」列**：和模态同步显示；已勾选行删除线 + 灰底。
5. **菜单入口**：本功能纯模态，不需要新菜单。
6. **i18n**：项目无 i18n 框架，文案硬编码中文，与现有惯例一致。
7. **`/send` 不清空 picking 记录**：状态从 `pending` → `processing` 时保留勾选历史，便于事后只读查阅。
8. **`HandcraftPartItem` 编辑边界**：picking 记录主键是 `(part_item_id, part_id)`，仅 `qty` 变化无影响；若 `part_id` 被修改（罕见，且仅在 `pending` 状态可能），需在 `update_handcraft_part_item` 服务里同步清理 stale 记录（实现时按需添加，本设计不强制）。

## 风险与不做的事

- ❌ 不修改 `services/picking.py` —— 哪怕逻辑相似也不抽公共基类，避免破坏订单端。
- ❌ 不复用 `OrderPickingRecord` 表 —— 外键模型不一样。
- ❌ 不改 `HandcraftPartItem` 模型 —— picking 是独立维度。
- ⚠️ 复用 `_expand_to_atoms` 是跨服务 import —— 可接受（不是循环依赖，且该函数已稳定）。

## 文件清单（新增 / 修改）

**新增**：
- `models/handcraft_order.py` 增 `HandcraftPickingRecord` 类
- `services/handcraft_picking.py`
- `services/handcraft_picking_list_pdf.py`
- `frontend/src/components/picking/HandcraftPickingSimulationModal.vue`
- `tests/test_api_handcraft_picking.py`

**修改**：
- `models/__init__.py` 导出 `HandcraftPickingRecord`
- `schemas/handcraft.py` 增 picking 相关 Pydantic 模型
- `api/handcraft.py` 增 5 个 picking 路由
- `services/handcraft.py` 删除 `HandcraftPartItem` 时同步清理 picking 记录
- `frontend/src/api/handcraft.js` 增 5 个 client 函数
- `frontend/src/views/handcraft/HandcraftDetail.vue` 接入按钮 + 模态
