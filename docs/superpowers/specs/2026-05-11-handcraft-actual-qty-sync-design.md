# Handcraft — 配货模拟「实际」数量同步到详情与发库存

> 状态：设计稿（待实现）
> 涉及分支：从 `main` 起新分支
> 日期：2026-05-11
> 关联前置：`docs/superpowers/specs/2026-05-09-handcraft-picking-actual-qty-design.md`

---

## 0. 核心约束

**扩展现有 `handcraft_picking_weight.actual_qty` 的作用域，不引入新表/新列。**

不会触碰：
- 数据库 schema（不加列、不改列）
- 订单状态机
- 配货模拟弹窗本身的交互
- 配货 PDF 导出逻辑（已使用 `actual_qty ?? needed_qty`）
- 组合配件（`is_composite=true` 的 part_item）的发出/库存行为
- `picked` checkbox 语义

**会改的代码路径：**
- `GET /handcraft/{id}/parts` 响应增加 `actual_qty` 字段（仅原子 item）
- `POST /handcraft/{id}/send` 在原子 item 上用 `actual_qty ?? pi.qty` 作为扣库存数量
- 详情页「发出数量」列展示 `actual_qty ?? pi.qty`，差异时附原值标注
- 详情页在配货模拟弹窗关闭时重新加载明细

---

## 1. 背景

2026-05-09 实现了配货模拟弹窗中的「实际」可编辑列，存到 `handcraft_picking_weight.actual_qty`。但当时的 scope 严格限定在「配货员现场便条」：

- 仅作用于弹窗内组头合计与配货 PDF
- 不回写 `HandcraftPartItem.qty`
- `send_handcraft_order` 按 `pi.qty` 扣库存，与「实际」无关
- 详情页「发出数量」列展示 `pi.qty`，与「实际」无关

用户使用中发现这个边界过窄：填了「实际」却看不到它影响真正发出的数量，体感上像填了个无意义字段。本次将作用域扩展到详情展示与库存扣减。

## 2. 范围决策

**仅原子 part_item 同步，组合 part_item 维持现状。**

| 类型 | 「实际」语义 | 是否同步到详情/发出 |
|---|---|---|
| 原子（`atom_part_id == pi.part_id`） | 即此 part_item 的实际发出量 | ✅ |
| 组合（`atom_part_id != pi.part_id`） | 每个 atom 的实际配货量 | ❌（一个 pi.qty 对应多个 atom 实际值，无法合并） |

天然过滤键：`(handcraft_part_item_id, atom_part_id == pi.part_id)`。组合 part_item 的 picking_weight 行的 `atom_part_id` 是 atom，不等于 `pi.part_id`，因此查不到——同一套查询代码在两种类型上自动正确。

---

## 3. 数据流

```
配货模拟弹窗
  └─ PUT/DELETE /picking/actual_qty
       └─ handcraft_picking_weight.actual_qty  ← 已存在，无改动

GET /handcraft/{id}/parts
  └─ 服务层 join handcraft_picking_weight
       (where atom_part_id == pi.part_id AND actual_qty IS NOT NULL)
  └─ 响应字段 actual_qty 出现在原子 item 上；组合 item 始终为 null

POST /handcraft/{id}/send
  └─ 加载本订单全部 picking_weight
  └─ 对每个 part_item，effective_qty = actual_by_key.get((pi.id, pi.part_id), pi.qty)
  └─ 按 part_id 聚合后扣库存
  └─ 组合 item 因键 (pi.id, pi.part_id) 不存在而落回 pi.qty
```

---

## 4. 后端

### 4.1 `schemas/handcraft.py`

`HandcraftPartItemResponse` 增加字段：

```python
class HandcraftPartItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    handcraft_order_id: str
    part_id: str
    qty: float                              # 「计划」发出量，沿用原义
    actual_qty: Optional[float] = None      # 「实际」覆盖；仅原子 item 可能非 null
    weight: Optional[float] = Field(None, ge=0)
    weight_unit: Optional[str] = None
    received_qty: Optional[float] = 0
    status: str = "未送出"
    bom_qty: Optional[float] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    note: Optional[str] = None
    loss_qty: Optional[float] = None
```

### 4.2 `services/handcraft.py` — `get_handcraft_parts`

仿照 `_attach_loss_qty` 增加 `_attach_actual_qty`：

```python
def _attach_actual_qty(db: Session, items: list, order_id: str) -> list:
    """Attach picking actual_qty to atomic part items only.

    The key (part_item_id, part_id) naturally filters to atomic items:
    composite expansions only produce picking_weight rows where
    atom_part_id != pi.part_id, so the lookup misses for composites.
    """
    if not items:
        return items
    rows = (
        db.query(HandcraftPickingWeight)
        .filter(
            HandcraftPickingWeight.handcraft_order_id == order_id,
            HandcraftPickingWeight.actual_qty.is_not(None),
        )
        .all()
    )
    actual_by_key = {
        (r.handcraft_part_item_id, r.atom_part_id): float(r.actual_qty)
        for r in rows
    }
    for it in items:
        it.actual_qty = actual_by_key.get((it.id, it.part_id))
    return items


def get_handcraft_parts(db: Session, order_id: str) -> list:
    items = (
        db.query(HandcraftPartItem)
        .filter(HandcraftPartItem.handcraft_order_id == order_id)
        .order_by(HandcraftPartItem.id.asc())
        .all()
    )
    items = _attach_part_colors(db, items)
    items = _attach_loss_qty(db, items, order_id, "handcraft_part")
    return _attach_actual_qty(db, items, order_id)
```

### 4.3 `services/handcraft.py` — `send_handcraft_order`

把第 293-295 行的 part_totals 聚合替换为覆盖感知版本：

```python
# Load actual_qty overrides for this order. The key (pi.id, pi.part_id)
# only matches atomic items; composite items naturally fall back to pi.qty.
weight_rows = (
    db.query(HandcraftPickingWeight)
    .filter(
        HandcraftPickingWeight.handcraft_order_id == handcraft_order_id,
        HandcraftPickingWeight.actual_qty.is_not(None),
    )
    .all()
)
actual_by_key = {
    (w.handcraft_part_item_id, w.atom_part_id): float(w.actual_qty)
    for w in weight_rows
}

part_totals: dict[str, float] = {}
for item in part_items:
    effective = actual_by_key.get((item.id, item.part_id), float(item.qty))
    part_totals[item.part_id] = part_totals.get(item.part_id, 0.0) + effective
```

库存检查、扣减、回滚分支无需改动。

### 4.4 不变的部分

- 状态门控（`actual_qty` upsert/delete 已限定 status=pending；send 已限定 status=pending）
- 配货模拟服务 `services/handcraft_picking.py`（已正确读出 actual_qty）
- 配货 PDF `services/handcraft_picking_list_pdf.py`（已使用 actual_qty ?? needed_qty）
- 损耗、回收、撤回逻辑

---

## 5. 前端

### 5.1 `HandcraftDetail.vue` — 「发出数量」列渲染

`itemColumns` 中 `key: 'qty'` 的 render 函数：

```js
{
  title: '发出数量',
  key: 'qty',
  render: (row) => {
    const suggested = computeSuggestedQty(row)
    const planned = row.qty
    const actual = row.actual_qty
    const hasOverride = actual != null && Number(actual) !== Number(planned)
    const displayed = actual ?? planned

    // 主数字 + 可选「(原 X)」+ 既有「建议 N」tooltip
    const mainSpan = hasOverride
      ? h('span', { style: 'white-space: nowrap; font-variant-numeric: tabular-nums;' }, [
          h('span', { style: 'color: #1a8917; font-weight: 600;' }, displayed),
          h('span', { style: 'color: #999; margin-left: 4px; font-size: 12px;' }, `(原 ${planned})`),
        ])
      : h('span', { style: 'font-variant-numeric: tabular-nums;' }, displayed ?? '-')

    if (suggested == null) return mainSpan

    return h(NTooltip, { trigger: 'hover' }, {
      trigger: () => h('span', { style: 'cursor: help; white-space: nowrap;' }, [
        mainSpan,
        h('span', { style: 'color: #1890ff; margin-left: 4px; font-size: 13px;' }, [
          '（建议 ',
          h('span', { style: 'font-weight: 700; font-size: 14px;' }, suggested),
          '）',
        ]),
      ]),
      default: () => buildSuggestedTooltip(row),
    })
  },
}
```

样式约定（与既有页面色彩一致）：
- 覆盖值用绿色（`#1a8917`）轻度高亮
- 原值用灰色小字「(原 N)」放在覆盖值右侧
- 「建议 N」蓝色 tooltip 保持原样

### 5.2 `HandcraftDetail.vue` — 弹窗关闭后刷新明细

```vue
<HandcraftPickingSimulationModal
  v-model:show="pickingModalShow"
  :order-id="String(route.params.id)"
  :status="order?.status || 'pending'"
  @restock-changed="loadRestock"
  @update:show="(v) => { pickingModalShow = v; if (!v) loadData() }"
/>
```

`v-model:show` 与 `@update:show` 共用：保留双向绑定的同时在关闭时触发 `loadData()`。**无条件** reload，不维护 dirty 标志——一次额外的 `getHandcraftParts + 库存查询` 成本可接受，胜过维护脏状态。

### 5.3 配货模拟弹窗本身：不动

`HandcraftPickingSimulationModal.vue` 不需要任何修改。

---

## 6. 边界与回归

| 场景 | 预期行为 |
|---|---|
| 用户在 pending 状态填写实际值后保存 | 详情「发出数量」立即（关闭弹窗后）显示实际值 + (原 X) |
| 用户清空实际值（DELETE） | 详情回退到计划值，无 (原 X) 标注 |
| 实际值 = `needed_qty`（即 BOM 理论值） | modal 内 `isClear` 触发 DELETE，行为等同清空 |
| 实际值 = 计划值（pi.qty）但 ≠ needed_qty | 覆盖保留在 DB；详情列因 `actual == planned` 不显示 (原 X)；send 按 actual 扣库存（数值与 planned 相同，结果等价） |
| 组合 part_item 在配货模拟中设置 atom 实际值 | 详情该组合 item 行的「发出数量」**不变**；send 时仍按 `pi.qty` 扣库存 |
| 用户点「发出」时实际值已设置 | 按 `actual_qty` 扣库存；库存不足判断同样基于聚合后的 effective_qty |
| 用户点「发出」时实际值未设置 | 按 `pi.qty` 扣库存（与今天一致） |
| 同一原子 part 在多个 pi 行中出现，一部分设置了实际值 | 各 pi 行独立查 override；按 part_id 聚合后扣库存 |
| 配货 PDF 行为 | 不变（已使用 `actual_qty ?? needed_qty`） |

### 不在范围

- 详情页 Excel/PDF 导出中「发出数量」列的语义切换（如果导出沿用响应字段 `qty`，本次不动；如果用户提出新增导出 actual_qty 列再单独评估）
- 历史已发出（processing/completed）订单的回填：本次仅影响新走「填实际 → 发出」流程的订单，已 processing 的订单状态不会被本次改动重新计算

---

## 7. 测试

新增（建议放 `tests/test_api_handcraft.py` 与 `tests/test_api_handcraft_picking_weight.py`）：

1. `test_get_parts_includes_actual_qty_for_atomic`
   - 原子 part_item，picking_weight 设 actual_qty=80，pi.qty=100 → 响应 `actual_qty=80, qty=100`
2. `test_get_parts_omits_actual_qty_for_composite`
   - 组合 part_item，picking_weight 在某 atom 上设 actual_qty=50 → 响应该 item 的 `actual_qty is None`
3. `test_get_parts_actual_qty_null_when_no_override`
   - 原子 part_item，无 picking_weight 或 actual_qty=null → 响应 `actual_qty is None`
4. `test_send_handcraft_uses_actual_qty_when_present`
   - 原子 pi.qty=100, actual_qty=80, 初始库存 100 → 发出后 inventory_log 扣减 80
5. `test_send_handcraft_falls_back_to_pi_qty_when_no_override`
   - 原子 pi.qty=100, 无 actual_qty, 初始库存 100 → 发出后扣 100
6. `test_send_handcraft_composite_unaffected_by_atom_actual_qty`
   - 组合 pi（pi.qty=10，组合展开为 atom A×3 + atom B×2），仅在 atom A 上设 actual_qty=99 → 发出仍按 `pi.qty=10` 扣组合 parent 的库存
7. `test_send_handcraft_stock_check_uses_effective_qty`
   - pi.qty=100, actual_qty=80, 库存 90 → 发出成功（按 80 检查），inventory 剩 10
   - 镜像：pi.qty=80, actual_qty=100, 库存 90 → 发出失败（按 100 检查），抛 ValueError "库存不足"
8. `test_send_handcraft_aggregates_overrides_across_items`
   - 同一 part_id 有两个原子 pi 行，分别 actual_qty=30 / actual_qty=40 → 扣 70

前端单元测试：本项目无前端测试基础设施（仅 npm build / 浏览器手工验证），不新增。手工测试单：
- 进入 pending 手工单详情 → 配货模拟 → 修改某原子 item 实际值 → 关闭弹窗 → 详情对应行显示绿色覆盖值 + (原 X)
- 弹窗内重置/清空实际值 → 关闭 → 详情回退到计划值
- 修改组合 item 某 atom 实际值 → 关闭 → 详情该组合行不变
- 点发出 → 库存按实际值扣减（在库存日志中核对）

---

## 8. 兼容性

- 后端响应增加可选字段 `actual_qty`，老前端忽略即可——非破坏性
- 老订单（processing/completed）已经发出，本次改动不影响其库存日志
- 数据库 schema 不变，无需 migration（actual_qty 列在 2026-05-09 已添加）

---

## 9. 实施顺序（建议）

1. 后端 schema 加 `actual_qty` 字段 + `_attach_actual_qty` 服务函数 + 单测
2. 后端 send_handcraft_order 接入 override 查询 + 单测
3. 前端「发出数量」列 render 改造
4. 前端弹窗 `@update:show` 监听加 reload
5. 手工验证全链路

每步独立可测、独立提交。
