# Handcraft 配货模拟 — 持久化合并相同 part_id 的 part_item 行

> 状态：设计稿（待实现）
> 涉及视图：配货模拟弹窗 `HandcraftPickingSimulationModal.vue`
> 日期：2026-05-30

---

## 0. 一条核心约束

**这次改动是「持久化的 `HandcraftPartItem` 行结构变更」**。

不会触碰：
- `inventory_log`（无入出库写入）
- 订单状态机（仅 `pending` 单允许合并）
- 库存余额计算

会写的数据：
- `HandcraftPartItem`：合并组里 `id` 最小的留下（"幸存行"），其余删除；幸存行的 `qty` 累加；`weight` / `weight_unit` / `bom_qty` 清空
- `HandcraftPickingRecord`：合并组所有受影响 `part_item_id` 的行**全部删除**
- `HandcraftPickingWeight`：同上，全部删除

合并后**不会**触发任何状态机或出库。

---

## 1. 背景与动机

### 现状

2026-05-07 spec(`handcraft-picking-merge-and-weight-design`) 已经把同 `atom_part_id` 的多条 `HandcraftPartItem` **在视图层**合并到一个 group-header 下分行展示——用户能一眼看见"龙虾扣总共 300"，但实际仍是两条 part_item 行（A 饰品 100 + B 饰品 200），picking checkbox 和 weight 输入也是分行的。

### 痛点

仓库实际工作流有两种：

| 模式 | 操作方式 | UI 期望 |
|---|---|---|
| **分饰品配货** | 按饰品分包装（A 一包、B 一包） | 当前两行结构合适 |
| **统一配货** | 把同配件需求一起摸出来，不区分饰品 | 当前两行结构是噪音；用户希望"龙虾扣 300"就是一行 |

第二种模式下，用户只想：
- 一个 qty 字段（已累加）
- 一个 weight 输入（填总重量，不分饰品摊）
- 一个 picked checkbox

视图层的"分行展示"无法表达这种意图，因为底层是两条独立的 `HandcraftPartItem`。

### 目标

让用户**按配件粒度**地决定"这个配件要不要并成一条 part_item"。每个配件独立决策——比如龙虾扣并、银链不并（C 是金色 D 是银色，要分包）。

### 不在范围内

- **复合件（composite part）的合并**：复合件单条 `HandcraftPartItem` 会展开成多组 atom_part_id，"合并复合件"会同时影响多个 group——v1 暂不在表格里提供这个入口。用户如需可走配件明细面板手动改。
- **撤销 / 拆分**：合并不可逆。如果用户要"重新分饰品记录"，需要重建该单的相关 part_items。
- **跨订单合并**：仅限同一手工单内。

---

## 2. UI 设计

### 2.1 入口

在 `HandcraftPickingSimulationModal.vue` 的表格内，**每个 group-header** 行的"配件 / 来源"列右侧加一个 inline 按钮：

```
┌─────────────────────────────────────────────────────────────────────────┐
│ [img] 龙虾扣 14mm 金色 [小件]                              [合并]        │  ← group-header
│       PJ-X-00012-G                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│ qty 100 · 来自 A 饰品 SP-0008          —    100    100         ☐        │
│ qty 200 · 来自 B 饰品 SP-0011          —    200    200         ☐        │
└─────────────────────────────────────────────────────────────────────────┘
```

**样式**：
- 透明背景 + 绿色文字（`color: #047857`），hover 时浅绿背景（`background: #ecfdf5`）
- 文案：纯`合并`（依赖 popconfirm 解释作用）
- size：tiny / 11~12px

### 2.2 可见性规则

按钮在 group-header 上仅当**全部下列条件**满足时渲染：

1. `!readonly`（即手工单状态为 `pending`）
2. `g.rows` 里至少包含 **2 个不同的 `part_item_id`**
3. **没有任何一行 `is_composite_expansion === true`**（v1 排除复合件场景）

> 实现：在 `HandcraftPickingSimulationModal.vue` 的 `displayGroups` 上加一个 computed `groupMergeable(g) → boolean`。

### 2.3 二次确认

`n-popconfirm`，文案量化：

> 合并 `<atom_part_name>`（**N 行 → 1 行** · qty `<sum>`）？
> 已有的勾选 / 重量记录会被清空。
> **不可撤销。**

其中 `N` = 该组 `part_item_id` 去重数；`sum` = 这些 part_items 的 qty 之和。

### 2.4 成功反馈

- `message.success('已合并 N 个 part_item 行')`
- `loadData()` 重新拉取并渲染——合并后该组只剩 1 行，按钮自动消失

### 2.5 失败反馈

- 后端返回 4xx → `message.error(detail)`
- 显示后端的具体错误（如"订单已送出，不可合并"）

### 2.6 PDF 导出

无需任何改动。`HandcraftPickingListPDF`（`services/handcraft_picking_list_pdf.py`）从 `HandcraftPartItem` 直接生成 PDF。合并把多行变 1 行写库后，PDF 下次导出自动反映新结构——这就是"PDF 跟随屏幕视图"的天然形态。

---

## 3. 后端设计

### 3.1 端点

```
POST /handcraft-orders/{order_id}/parts/{part_id}/merge-duplicates
权限: handcraft
```

请求体：无。

返回（`200`）：
```json
{
  "merged_part_item_id": 17,
  "before_rows": 2,
  "after_rows": 1,
  "merged_qty": 300
}
```

### 3.2 校验

返回 `400` 的情况：
| 条件 | detail |
|---|---|
| 订单状态 ≠ `pending`（已送出/已完成） | `订单已不在 pending 状态，不可合并` |
| 该单内 `part_id` 对应的 `HandcraftPartItem` 行数 < 2 | `没有可合并的 part_item 行` |
| `part_id` 指向的 `Part.is_composite == true` | `复合件暂不支持自动合并` |

返回 `404`：
- 订单不存在
- `part_id` 不在该单内

### 3.3 合并算法

服务函数 `services/handcraft.py::merge_duplicate_part_items(db, order_id, part_id)`：

```python
def merge_duplicate_part_items(db, order_id: str, part_id: str) -> dict:
    # 1. 校验订单状态、part is_composite、是否有 ≥2 行
    order = _get_order(db, order_id)
    if order.status != "pending":
        raise ValueError("订单已不在 pending 状态，不可合并")

    part = db.get(Part, part_id)
    if part is None:
        raise HTTPException(404, "part 不存在")  # 或在 api 层抛
    if part.is_composite:
        raise ValueError("复合件暂不支持自动合并")

    rows = db.query(HandcraftPartItem)\
             .filter_by(handcraft_order_id=order_id, part_id=part_id)\
             .order_by(HandcraftPartItem.id)\
             .all()
    if len(rows) < 2:
        raise ValueError("没有可合并的 part_item 行")

    # 2. 选定幸存行
    survivor, *others = rows
    other_ids = [r.id for r in others]

    # 3. 删除所有受影响 part_item 的 picking record / weight
    db.query(HandcraftPickingRecord)\
      .filter(HandcraftPickingRecord.handcraft_part_item_id.in_([r.id for r in rows]))\
      .delete(synchronize_session=False)
    db.query(HandcraftPickingWeight)\
      .filter(HandcraftPickingWeight.part_item_id.in_([r.id for r in rows]))\
      .delete(synchronize_session=False)

    # 4. 累加 qty，清空 weight / bom_qty
    total_qty = sum(r.qty for r in rows)
    survivor.qty = total_qty
    survivor.weight = None
    survivor.weight_unit = None
    survivor.bom_qty = None
    # status / unit / note 保留幸存行原值

    # 5. 删除其他行
    db.query(HandcraftPartItem)\
      .filter(HandcraftPartItem.id.in_(other_ids))\
      .delete(synchronize_session=False)

    db.flush()
    return {
        "merged_part_item_id": survivor.id,
        "before_rows": len(rows),
        "after_rows": 1,
        "merged_qty": float(total_qty),
    }
```

### 3.4 API 层

`api/handcraft.py` 新增：

```python
@router.post("/{order_id}/parts/{part_id}/merge-duplicates")
def merge_duplicates(
    order_id: str,
    part_id: str,
    db: Session = Depends(get_db),
):
    with service_errors():
        return merge_duplicate_part_items(db, order_id, part_id)
```

挂在已存在的 `handcraft` 路由前缀下，权限沿用 `require_permission("handcraft")`。

---

## 4. 前端实现

### 4.1 API client

`frontend/src/api/handcraft.js` 加：

```javascript
export const mergeHandcraftDuplicateParts = (orderId, partId) =>
  api.post(`/handcraft-orders/${orderId}/parts/${encodeURIComponent(partId)}/merge-duplicates`)
```

### 4.2 组件改动

`HandcraftPickingSimulationModal.vue`：

1. **计算属性**
   ```js
   function groupMergeable(g) {
     if (readonly.value) return false
     if (g.rows.some(r => r.is_composite_expansion)) return false
     const partItemIds = new Set(g.rows.map(r => r.part_item_id))
     return partItemIds.size >= 2
   }
   ```

2. **模板**：group-header 的 `col-source` 内，`group-cell` 改为 `flex justify-content: space-between`；右侧条件渲染：
   ```html
   <n-popconfirm
     v-if="groupMergeable(g)"
     @positive-click="doMergeGroup(g)"
   >
     <template #trigger>
       <n-button text size="tiny" class="inline-merge">合并</n-button>
     </template>
     合并 {{ g.atom_part_name }}（{{ distinctPartItemCount(g) }} 行 → 1 行 · qty {{ fmtQty(groupTotalQty(g)) }}）？<br>
     已有的勾选 / 重量记录会被清空。<br>
     <b>不可撤销。</b>
   </n-popconfirm>
   ```

3. **handler**
   ```js
   async function doMergeGroup(g) {
     try {
       const res = await mergeHandcraftDuplicateParts(props.orderId, g.atom_part_id)
       message.success(`已合并 ${res.data.before_rows} 个 part_item 行`)
       await loadData()
     } catch (e) {
       message.error(e.response?.data?.detail || '合并失败')
     }
   }
   ```

4. **样式**（scoped）
   ```css
   .inline-merge {
     color: #047857;
     font-size: 11px;
     padding: 2px 8px;
     border-radius: 3px;
   }
   .inline-merge:hover {
     background: #ecfdf5;
   }
   ```

### 4.3 关于 group-header 的 atom_part_id ↔ part_id

非复合件场景下 `atom_part_id === part_id`，所以前端拿 `g.atom_part_id` 当 `part_id` 传给 API 是安全的。后端再做一次 `Part.is_composite` 校验作为防线。

---

## 5. 测试

### 5.1 后端（pytest）

`tests/test_api_handcraft_merge_duplicates.py`：

- ✅ `test_merge_two_duplicate_part_items_in_pending` — 2 行 qty 100/200 → 1 行 qty 300；其他行被删
- ✅ `test_merge_three_duplicate_part_items` — qty 1+1+4 → qty 6
- ✅ `test_merge_clears_weight_and_bom_qty` — 原幸存行 weight 80g、bom_qty 1 → 合并后均为 None
- ✅ `test_merge_clears_picking_records_for_affected_part_items` — 提前为某 part_item 写一行 picking record，合并后该 record 不存在
- ✅ `test_merge_clears_picking_weights_for_affected_part_items` — 同上，针对 picking weight 表
- ✅ `test_merge_in_processing_returns_400` — 状态 processing → 400 "订单已不在 pending 状态"
- ✅ `test_merge_in_completed_returns_400` — 同上
- ✅ `test_merge_no_duplicates_returns_400` — 只有 1 行 → 400 "没有可合并的 part_item 行"
- ✅ `test_merge_composite_part_returns_400` — `Part.is_composite=True` → 400 "复合件暂不支持自动合并"
- ✅ `test_merge_nonexistent_order_returns_404`
- ✅ `test_merge_part_id_not_in_order_returns_404`
- ✅ `test_merge_picks_smallest_id_as_survivor` — 验证幸存行 id 最小

### 5.2 前端

手动验证清单（写到 PR description）：

- [ ] 含重复非复合件 → 该组 group-header 显示「合并」按钮
- [ ] 不含重复的组 → 没有按钮
- [ ] 复合件展开的组 → 没有按钮
- [ ] readonly（processing/completed）→ 没有按钮
- [ ] 点击 popconfirm 文案正确量化（N 行、qty 总和）
- [ ] 确认合并 → toast 成功 → 表格自动刷新成 1 行
- [ ] weight 字段为空（等待用户填）
- [ ] 不同 group 的合并按钮独立工作（只合并龙虾扣不合并银链）

---

## 6. 与历史 spec 的关系

| Spec | 日期 | 合并的语义 | 数据层 |
|---|---|---|---|
| `2026-05-07-handcraft-picking-merge-and-weight-design` | 2026-05-07 | 视图层 group by atom_part_id（多 part_item 仍然存在，只是显示在一组里） | 不改库 |
| **本 spec** | 2026-05-30 | 持久化合并多条 `HandcraftPartItem` 行为一条 | 改库 |

本 spec 是 2026-05-07 的**自然延续**：05-07 解决了"看不到总量"，05-30 解决了"把分行也消掉"。

---

## 7. 风险与回滚

### 风险

| 风险 | 缓解 |
|---|---|
| 用户误合并丢失分饰品信息 | 二次确认 + 量化文案 + "不可撤销"提示 |
| 跨 `pending` 状态边界（合并过程中订单被发送） | 服务函数在事务内重新读状态校验；并发场景下后赢家自然抛 400 |
| 复合件被错误调用 | 前端不渲染按钮 + 后端独立校验作为防线 |

### 回滚

如果上线后发现问题：
- 前端：把 group-header 上的 `<n-popconfirm v-if="groupMergeable(g)">` 块注释/移除即可
- 后端：路由保留无害（其他人调用要么 4xx 要么生效），但建议同时下线路由

已合并的数据无法自动拆分回原状（不可逆）。
