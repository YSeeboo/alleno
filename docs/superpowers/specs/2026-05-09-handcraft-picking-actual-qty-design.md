# Handcraft Picking — 子行「实际」列可编辑

> 状态：设计稿（待实现）
> 涉及分支：从 `main` 起新分支
> 日期：2026-05-09

---

## 0. 一条核心约束

**这次改动是「展示层 + 一个新可空字段」。**

不会触碰：
- `inventory_log`（无入出库写入）
- 订单状态机
- `HandcraftPartItem.qty` / `bom_qty`（用户编辑的是实际配货量，不动原始分配）
- 库存余额计算
- `picked` checkbox 与 `HandcraftPickingRecord` 的语义（实际数量与勾选独立）

**会写的数据：** 现有 `handcraft_picking_weight` 表新增 `actual_qty` 字段。

---

## 1. 背景

picking 模拟现在的子行「理论」列展示 `needed_qty = bom_qty × atom_ratio`，只读。仓库实际配货时，发出的数量可能与 BOM 理论值不一致（找零、损耗、就近凑整），用户需要能记录实际发出量，且这个值要随订单走（持久化）。

之前的「建议」列已经基于 BOM 理论值给出推荐发出量（含 buffer），用户期望：
- 「建议」保持作为"参考推荐"，**不变**
- 「理论」列改名「实际」，可编辑，默认值仍是 `needed_qty`

## 2. UI 设计

### 2.1 列改动（picking modal）

| 旧 | 新 |
|---|---|
| 子行「理论」单元格：只读，显示 `r.needed_qty` | 「实际」单元格：可点击编辑，默认 `r.needed_qty`，存储覆盖值 |
| 组头「合计 {{ total_needed_qty }}」 | 「合计 {{ sum of (actual_qty ?? needed_qty) }}」 |

### 2.2 子行编辑控件

- `<n-input-number>` 复用 weight 列的紧凑样式（`precision: 4`, `:show-button="false"`）
- 默认值：当 `actual_qty` 为 null 时显示 `needed_qty`；非 null 时显示 `actual_qty`
- `onBlur`：
  - 输入 = 默认值（即 `needed_qty`）→ 调 DELETE，回到 null（避免无意义存储）
  - 输入 = 空/0 → 同上 DELETE
  - 输入 ≠ 默认值且 > 0 → 调 PUT 上报
- `onFocus`：和 weight 一样快照，避免 blur 时无谓 DELETE
- 视觉上需要与「理论"不可编辑」时代区分开：如更柔和的输入框边框、无 `_qty` 颜色等（保持本任务最小代码动）

### 2.3 状态门控

| 订单状态 | 编辑 |
|---|---|
| `pending` | ✅ |
| `processing` / `completed` | ❌（只读，显示当前值） |

### 2.4 picked checkbox 关系

完全独立。设置实际数量**不**自动勾选；勾选/取消勾选**不**修改实际数量。

---

## 3. 「建议」列保持不变

- 仍 = `compute_suggested_qty(atom_part, needed_qty)`，按 BOM 理论值算
- 用户编辑实际值不重算建议
- 组头 `total_suggested_qty` = sum 子行 suggested_qty（与现状一致）
- 库存红色告警条件保持 `current_stock < total_suggested_qty`（不变）

---

## 4. 数据模型

### 4.1 现有表加字段

```python
# models/handcraft_order.py — HandcraftPickingWeight 已存在
class HandcraftPickingWeight(Base):
    __tablename__ = "handcraft_picking_weight"
    id = Column(Integer, primary_key=True, autoincrement=True)
    handcraft_order_id = Column(String, ForeignKey("handcraft_order.id", ondelete="CASCADE"), nullable=False, index=True)
    part_item_id = Column(Integer, ForeignKey("handcraft_part_item.id", ondelete="CASCADE"), nullable=False)
    atom_part_id = Column(String, ForeignKey("part.id"), nullable=False)
    weight = Column(Numeric(10, 4), nullable=True)        # 改成 nullable
    weight_unit = Column(String, nullable=True, default="kg")  # 改成 nullable
    actual_qty = Column(Numeric(10, 4), nullable=True)    # ✨ 新增
    recorded_at = Column(DateTime, nullable=False, default=now_beijing)
    __table_args__ = (
        UniqueConstraint("part_item_id", "atom_part_id", name="uq_picking_weight_pa"),
    )
```

**注意：** 把 `weight` 和 `weight_unit` 从 `nullable=False` 改成 `nullable=True`。原因：现在一行可能只有 `actual_qty` 而没有 weight，反之亦然；唯一约束 `(part_item_id, atom_part_id)` 仍唯一。

### 4.2 schema 迁移

`ensure_schema_compat`：
- 若 `actual_qty` 列不存在 → `ALTER TABLE ... ADD COLUMN actual_qty NUMERIC(10,4) NULL`
- `weight` 列从 NOT NULL 改 NULL：`ALTER TABLE ... ALTER COLUMN weight DROP NOT NULL`（同 `weight_unit`）

---

## 5. 后端响应 / 端点

### 5.1 `PickingSourceRow` 加字段

```python
class PickingSourceRow(BaseModel):
    # ... 现有字段 ...
    actual_qty: Optional[float] = None  # ✨ 新增；None = 用户未改
```

`get_handcraft_picking_simulation` 从 `bulk_load_for_picking` 读 row.actual_qty 填入。

### 5.2 新端点

| 端点 | 行为 |
|---|---|
| `PUT /api/handcraft/{order_id}/picking/actual_qty` | body `{part_item_id, atom_part_id, qty}`；pending only；upsert |
| `DELETE /api/handcraft/{order_id}/picking/actual_qty` | body `{part_item_id, atom_part_id}`；pending only；置 actual_qty 为 null |

请求 schema：

```python
class HandcraftPickingActualQtyUpsertRequest(BaseModel):
    part_item_id: int = Field(gt=0)
    atom_part_id: str = Field(min_length=1)
    qty: float = Field(gt=0)


class HandcraftPickingActualQtyDeleteRequest(BaseModel):
    part_item_id: int = Field(gt=0)
    atom_part_id: str = Field(min_length=1)
```

校验复用 `_validate_part_item_in_order(order_id, part_item_id)`，防越权（与 weight 端点同款）。

### 5.3 服务层

新函数在 `services/handcraft_picking_weight.py`（保持模块名 — 现已扩成"per-atom 测量"）：

- `upsert_actual_qty(db, order_id, part_item_id, atom_part_id, qty) -> HandcraftPickingWeight`
- `clear_actual_qty(db, order_id, part_item_id, atom_part_id) -> bool`

行不存在时 `upsert_actual_qty` 创建新行（weight=NULL）；存在时只更新 `actual_qty`。`clear_actual_qty` 把 `actual_qty` 设回 NULL；如果该行 `weight` 也是 NULL 则整行删除（避免空骨架）。

---

## 6. PDF 改动

PDF 子行「需要」列改成「实际」：值取 `actual_qty if not None else needed_qty`。组头「合计 N」用同样的 sum 规则。其他列保持不变。

---

## 7. 前端实现要点

### 7.1 picking modal `HandcraftPickingSimulationModal.vue`

- 表头列名「理论」改「实际」
- 子行渲染：原读 `r.needed_qty` 的位置改读 `r.actual_qty ?? r.needed_qty`
- 加 `<n-input-number>` 控件，复用 weight 列的 focus/blur 快照模式：
  ```js
  function onActualQtyFocus(row) { row._actualAtFocus = row.actual_qty ?? null }
  async function onActualQtyBlur(group, row) {
    if (readonly.value) return
    const fresh = row._localActualQty
    const prev = row._actualAtFocus
    const isClear = fresh == null || fresh === '' || Number(fresh) <= 0 || Number(fresh) === Number(row.needed_qty)
    if (isClear) {
      if (prev != null) await deleteHandcraftPickingActualQty(orderId, row.part_item_id, row.atom_part_id)
      row.actual_qty = null
    } else {
      const resp = await upsertHandcraftPickingActualQty(orderId, row.part_item_id, row.atom_part_id, Number(fresh))
      row.actual_qty = Number(resp.data.actual_qty)
    }
  }
  ```
- 组头「合计」改成 `groupActualSum(g)` —— sum of `(r.actual_qty ?? r.needed_qty)` over `g.rows`

### 7.2 前端 API client（`frontend/src/api/handcraft.js`）

```js
export const upsertHandcraftPickingActualQty = (id, partItemId, atomPartId, qty) =>
  api.put(`/handcraft/${id}/picking/actual_qty`, {
    part_item_id: partItemId,
    atom_part_id: atomPartId,
    qty,
  })

export const deleteHandcraftPickingActualQty = (id, partItemId, atomPartId) =>
  api.delete(`/handcraft/${id}/picking/actual_qty`, {
    data: { part_item_id: partItemId, atom_part_id: atomPartId },
  })
```

---

## 8. 边界场景

| 场景 | 处理 |
|---|---|
| 用户输入等于 needed_qty | 视为"未改"，DELETE actual_qty 行 |
| 用户输入空/0 | 同上，DELETE |
| 同行已有 weight + 设了 actual_qty | 一行存两个字段 |
| 删除 part_item | cascade 删除整行（包括 actual_qty）|
| 数据迁移 | 新增 actual_qty 列；现有 picking_weight 行的 actual_qty 默认 NULL |
| 状态非 pending 的旧订单 | 现有 actual_qty 值仍展示，但只读 |
| 合计含 None | sum 用 `(r.actual_qty ?? r.needed_qty)` fallback |

---

## 9. 验证清单

- [ ] 列名「理论」改「实际」（modal 与 PDF）
- [ ] 子行点击单元格变成可编辑输入框（pending 状态）
- [ ] 默认显示 needed_qty；编辑后显示用户值
- [ ] PUT 端点成功写入；DELETE 成功清空回 null
- [ ] 「建议」列与 `total_suggested_qty` 不变（仍按 needed_qty 算）
- [ ] 组头「合计」反映实际值之和
- [ ] PDF 跟随更新
- [ ] 状态非 pending 时只读
- [ ] 输入等于默认值或为 0/空 → 自动 DELETE，不创建无意义行
- [ ] picked checkbox 与 actual_qty 互不影响
- [ ] 跨订单越权 PUT/DELETE 被拒（同 #8 防护）
- [ ] cascade：删除 part_item / order 一并清掉 picking_weight 行
- [ ] schema 迁移幂等（`ensure_schema_compat` 重复运行不报错）

---

## 10. 范围外

- 实际数量与库存的扣减联动（不做 — 与既有"无库存副作用"原则一致）
- 实际数量的历史记录 / 审计表
- 自动从已勾选的 atom 推断实际值
- 改 picked checkbox 语义为"已配齐 = actual_qty == suggested_qty"
- 表重命名（`HandcraftPickingWeight` → `HandcraftPickingMeasurement`）；以后再做
