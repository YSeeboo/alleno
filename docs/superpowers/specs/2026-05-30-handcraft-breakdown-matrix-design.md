# 手工单客户分拣 · 矩阵交互设计

## 背景

`HandcraftDetail.vue` 当前的"客户分拣"区域按饰品分组 (一个 jewelry 一组),每组一个"编辑分拣"按钮 → 打开 `BreakdownEditModal` → 在 modal 里维护该饰品的客户列表。

**问题**: 操作者的真实工作流是"按客户视角分配" (给张三这一票:A 饰品 2 件 + B 饰品 1 件 + …),而当前 UI 强制"按饰品视角逐一处理",一个饰品一个 modal,饰品种类一多就要"开窗-填-关窗-再开下一个",非常碎片化。

**目标**: 一屏看全 HC 单的所有客户分拣,加一行 = 加一位客户、横向把他这一票几种饰品填了即可。

## 范围

- ✅ 仅改 HC 详情页的"客户分拣"区域 (替换 `BreakdownEditModal` + `BreakdownChips`)
- ✅ 新增"历史客户名 suggest"API
- ✅ 「一键剩余分给某客户」批量入口 (编辑态下,把每列剩余数量填入选定客户)
- ❌ 不改 PDF 输出 (`handcraft_pdf.py`)
- ❌ 不改 cargo sorting 模块 (它独立消费 breakdown 数据)
- ❌ 不引入 `Customer` 主数据表 (沿用现状:`customer_name` 是文本列)
- ❌ 不新增后端批量端点 (`POST /handcraft/{id}/jewelry` × N 即可,沿用现有 add 语义)

## 用户场景与约束

| 维度 | 约束 |
|---|---|
| 工作流视角 | 按客户视角(行 = 客户,横向把他要的几种饰品填了) |
| 设备 | PC + 手机都要 |
| 典型规模 | ≤ 3 种饰品 × ≤ 3 个客户(小规模) |
| 客户名 | 多数老客户重复出现,需要从历史去重作下拉建议 |
| 同客户同饰品 | 可能出现"订单锁定 + 手填补",单元格要能并存显示 |
| 数据来源 | 沿用现有 `GET /handcraft/{id}/jewelry-breakdown` 输出 |

## 设计

### 视觉结构

替换 `HandcraftDetail.vue:275-302` 的"客户分拣"卡片为新组件 `BreakdownMatrix`:

```
┌─ 客户分拣  [processing · 仅可加/删手填行]    [取消] [保存] ─┐
│ ┌──────┬─SP-001──┬─SP-002──┬─SP-003──┬─合计─┐              │
│ │客户  │ 珍珠项链 │ 蝴蝶耳环 │ 银戒指   │       │              │
│ │      │ 已分 5/5 │ 已分 4/4 │ 已分 2/3 │       │              │
│ ├──────┼─────────┼─────────┼─────────┼──────┤              │
│ │🔒张三│  2 🔒   │ 1🔒+[1] │   —     │  4   │              │
│ │  OR-12│         │         │         │       │              │
│ │李四 ▾ ×│  [3]   │  [2]    │  [1]    │  6   │              │
│ │王五 ▾ ×│   —    │  [1]    │  [1]    │  2   │              │
│ │+ 加客户                                       │              │
│ ├──────┼─────────┼─────────┼─────────┼──────┤              │
│ │已分/总│  5/5 ✓ │ 4/4 ✓  │ 2/3 ⚠  │11/12 │              │
│ └──────┴─────────┴─────────┴─────────┴──────┘              │
└────────────────────────────────────────────────────────────┘
```

- **列**: 该 HC 单的所有 jewelry/part(按 backend 返回顺序);最后一列"该客户合计"
- **行**: 该 HC 单出现过的所有客户(锁定客户优先,然后是手填客户);最后一行"已分/总数"
- **顶部按钮**: 默认"编辑";点后变成"取消 / 保存"
- **空表态**: 没有任何 customer 已分配的 entries 时,表体显示一行灰底斜纹的"尚未分配给任何客户"提示,header tag 变为 `未分拣 · 0/N`。列头和 footer 仍然渲染(让用户知道有哪几种饰品要分)。

### 单元格状态机

每个 `(customer, jewelry)` 单元格只有 4 种形态:

| 形态 | 后端数据 | 渲染 | 可编辑 |
|---|---|---|---|
| 空 | 该 customer 该 jewelry 没有任何 entry | `—` 灰字 | 点击 → 变成 `[0]` 数字框 |
| 仅手填 | ≥1 个 manual entry,无 locked | `[N]` 数字框,N = manual qty 之和 | 是 (状态约束下) |
| 仅锁定 | ≥1 个 locked entry, 无 manual | `N 🔒` 黄底,N = locked qty 之和 | 否,hover 显示来源订单列表 |
| 锁+手填 | ≥1 个 locked + ≥1 个 manual | `N🔒 + [M]` 黄白渐变背景 | 仅 manual 数字框 `M` 可编辑 |

**对手填数字的语义**: 把同一 `(customer, jewelry)` 下的所有 manual entries 折叠成单一 qty。前端编辑时:
- 折叠 qty 从 0 → 正数:`POST /handcraft/{id}/jewelry`(add 新 manual entry,仅 `pending`)
- 折叠 qty 改变:`PATCH /handcraft/{id}/jewelry/{item_id}`(update qty,仅 `pending`)
- 折叠 qty 从正数 → 0:`DELETE /handcraft/{id}/jewelry/{item_id}`(`pending` 可删;`processing` 需 `received_qty == 0`)
- 若历史上不慎存在多个 manual entry 在同 `(customer, jewelry)`:保留全部 entries,展示时合计,编辑时只 update 第一个、delete 其余 (一次性 normalize)

**占位 entries (`customer_name = None / 空 + 非 locked`)**: backend `breakdown` 返回它们(`customer_name: null, source: "manual", is_locked: false`),但矩阵**不显示为客户行**(没有客户维度可定位)。它们的 qty 仍然计入该列的 `total_qty`,所以 footer 的"未分差额" = `total_qty - sum(已显示的客户行 qty)` 正好等于占位 entries 的 qty 之和。一键分配就是把这些占位 entries 的 `customer_name` 认领给指定客户。

### 客户行规则

| 行类型 | 客户名 | 整行 × 删除 |
|---|---|---|
| 全 locked(只有订单来源 entries) | 只读,带 🔒 与 `↗ OR-XX` | 不显示 |
| 全 manual | 可改(下拉 picker),改名后批量 update 该行所有 manual entries 的 `customer_name` | 显示;点击删除该行所有 manual entries(`processing` 下若该行有 entry `received_qty > 0` → 整行删按钮 disabled,提示"已有回收,需先撤销回收单") |
| 混合(部分 locked + 部分 manual) | 只读(锁定来源决定身份) | 不显示;只能格子级把 manual 改 0 |

(以下表的"状态约束"为前提:客户名在 `pending` / `processing` 可改、`completed` 只读;删除行需要 `received_qty == 0`。)

### 客户名 picker(下拉建议)

加新行时,客户名输入框是"可搜索的 select",数据源:`order.customer_name` ∪ `handcraft_order.customer_name` ∪ `handcraft_jewelry_item.customer_name`(把过去 HC 内手填的客户名也带上),去重排序。允许输入下拉外的新名(直接打字回车即新增)。

实现:新增 `GET /api/customers/names?q=`,返回去重的客户名数组(≤ 50 条,按出现频次或字母序)。

### 状态约束(沿用现有后端规则)

| HC 状态 | 允许操作 |
|---|---|
| `pending` | 全部 manual 可编辑:加/删客户行、加/删/改单元格数字、改客户名、一键分配 |
| `processing` | 仅可改 manual 行客户名 + 删手填行 (`received_qty == 0` 才能删);不能加新行、不能改数量、不能一键分配 |
| `completed` | 全只读 |

(`locked` entries 任何状态都不可在此处改/删 — 沿用现有后端规则,要改回订单。)

**后端依据**:
- `add_handcraft_jewelry`: `customer_name is not None` 时仅 `pending` 允许 (services/handcraft.py:1010-1012)
- `update_handcraft_jewelry`: `customer_name` 字段在 `pending` / `processing` 都可改;其他字段(qty/unit/...) 仅 `pending`
- `delete_handcraft_jewelry`: `pending` 可删;`processing` 可删但 `received_qty == 0`;`completed` 不能删

UI 在 header 用 tag 明示当前可做什么,例如 `processing · 仅可改客户名 / 删未发出行`。

### 校验

- 每列底显示"已分 / 总数",相等显示绿色 ✓,不等显示红色 ⚠
- 不强制一次分完就能保存(与当前后端一致 — 允许部分分拣)
- 保存时仅做"客户名非空"和"数量 ≥ 0"的基础校验

### 一键剩余分给某客户

**问题场景**: 整单的饰品都属于同一位客户(常见;尤其是没有订单来源的纯手填 HC 单)。逐列填客户 + 数字会很繁琐(N 种饰品 ≈ 3+2N 次操作)。

**入口位置**: 编辑态下,表底的 add-bar 一行里,与「+ 加一行客户」并列:

```
┌─ + 加一行客户  |  ⚡ 一键剩余分给…  把所有未分配的数量给某位客户 ─┐
```

只在编辑态显示。当矩阵已无剩余可分时(所有列 `已分 == 总数`),按钮 disabled + 文案变为 `已无剩余可分`。

**点击后**: 弹出一个 popover (不是 modal,锚定在按钮上方),内容:

```
⚡ 把剩余数量分给某位客户

将填入 (基于当前矩阵):
  · 珍珠项链 +5 · 蝴蝶耳环 +4 · 银戒指 +3
  ✓ 整单全部 12 套         ← 或 "不会动 🔒 锁定行 / 李四已填的 1 套"

选客户  [李        ] ▾
        ├ 李四  (出现 8 次)
        ├ 李芳  (出现 1 次)
        └ + 新建客户「李」

                          [取消]  [填入]
```

- **预览**: 实时算出每列将填入的差值 `sum(qty of entries with customer_name=None)`,只列出差值 > 0 的项;说明"不会动 🔒 / 其他客户已填的部分"
- **客户输入**: 复用 `CustomerNameSelect` 组件(与「+ 加一行客户」的 picker 一致)
- **填入语义**(关键 — 与 mockup 描述不同,以此为准): 点「填入」后,**只改本地编辑状态**(不立即发请求):
  - 找该 HC 下所有 `customer_name = None / 空 + 非 locked` 的 entries(矩阵不显示但 backend 返回里有,代表"待分客户的占位产能")
  - 把它们的本地 `customer_name` 全部 set 为选定客户,标 `_dirty`
  - **不 add 新 entry**(避免 `total_qty = sum(entries.qty)` 膨胀);**不 delete 占位 entry**
  - 选定客户已存在为 manual 行 → 该客户的所有"折叠 qty"会包含这些被认领的 entries,展示成累加
  - 选定客户已存在为 locked 行 → 该行的对应单元格变成"锁+手填"混合
  - 新填入的格子 css 加 `flash` 类,显示黄底 + ✨ 角标,3 秒后淡出
- **保存触发**: 用户再点「保存」时,这些 `_dirty` entries 走 `PATCH /handcraft/{id}/jewelry/{item_id}` 路径(N 个占位 entry = N 次 PATCH);沿用现有"保存策略"
- **取消**: 点「取消」/「编辑→取消」即丢弃本地修改,矩阵回到加载时状态

**禁用条件**:
- HC 状态非 `pending`(因为 processing 不能 add 带 customer_name 的 entry;为统一起见 bulk-assign 也只在 pending 启用,即便其底层用 PATCH,避免"按钮在 processing 可点但行为有限"的混乱)
- 没有任何 `customer_name = None / 空` 的可认领 entries(显示"已无剩余可分")

**不做的事**:
- 不 add 新 HandcraftJewelryItem(避免 `total_qty` 膨胀)
- 不 delete 占位 entries
- 不引入新的后端端点 — 复用现有 `PATCH /handcraft/{id}/jewelry/{item_id}`

### 保存策略

沿用现 `BreakdownEditModal.save()` 的多请求 diff 模式:

1. 对比快照 vs 当前,生成 `{deletes: [...], updates: [...], adds: [...]}`
2. 顺序发: DELETE → PATCH → POST
3. 任一失败:`message.error(...)` 并重新拉取 breakdown(可能已有部分生效,展示真实状态)
4. 全部成功:`message.success("已保存")`,退出编辑态

**未来优化**: 后端加一个 `PUT /handcraft/{id}/breakdown` 批量端点,前端发整个矩阵,后端 transactional reconcile。本次先不做。

### 手机端

矩阵保持二维结构,处理方式:
- 表格容器水平滚动 (`overflow-x: auto`)
- 第一列(客户)`position: sticky; left: 0;`
- 编辑态时,「保存 / 取消」按钮组 `position: sticky; bottom: 0;` 始终可见
- 列宽固定 (jewelry 列 ≥ 80px),不做"窄屏转置"

## 组件 / 文件改动

### 新增

- `frontend/src/components/BreakdownMatrix.vue` — 主组件(只读 + 编辑双态、矩阵渲染、保存 diff、空表态、bulk-assign 入口)
- `frontend/src/components/CustomerNameSelect.vue` — 客户名下拉(包装 `n-select`,异步搜索,允许输入新值)
- `frontend/src/components/BulkAssignPopover.vue` — 「一键剩余分给」浮层(预览剩余 + 客户输入 + 填入按钮);由 `BreakdownMatrix` 控制显隐
- `frontend/src/api/customers.js` — `getCustomerNames(query)` 调用 suggest API
- `api/customers.py` — `GET /names` 路由
- `services/customer.py` — `list_distinct_customer_names(db, query)` 服务函数
- `tests/test_api_customers.py` — suggest API 测试(去重、模糊匹配、空查询返 top N)

### 修改

- `frontend/src/views/handcraft/HandcraftDetail.vue` —
  - `:275-302` 用 `<BreakdownMatrix :hc-id :hc-status :groups @saved>` 替换原卡片
  - `openBreakdownEditor` / `onBreakdownSaved` / `editBreakdownGroup` / `editBreakdownVisible` 等状态删除
  - `import BreakdownChips / BreakdownEditModal` 改为 `import BreakdownMatrix`
- `main.py` — 注册 `customers` 路由,`require_permission("handcraft")`(沿用 handcraft 权限,避免新建权限项)

### 删除

- `frontend/src/components/BreakdownEditModal.vue`
- `frontend/src/components/BreakdownChips.vue`

(已确认两者只在 `HandcraftDetail.vue` 引用)

## 后端 API · 客户名 suggest

```
GET /api/customers/names?q=<optional>&limit=50

Response: ["张三", "李四", "王五", ...]
```

实现:
```python
def list_distinct_customer_names(
    db: Session, query: str | None = None, limit: int = 50,
) -> list[str]:
    # UNION 来源
    order_names = db.query(Order.customer_name).filter(
        Order.customer_name.isnot(None), Order.customer_name != ""
    )
    hc_names = db.query(HandcraftOrder.customer_name).filter(
        HandcraftOrder.customer_name.isnot(None), HandcraftOrder.customer_name != ""
    )
    # HC jewelry manual customer_name 也算
    hc_jewelry_names = db.query(HandcraftJewelryItem.customer_name).filter(
        HandcraftJewelryItem.customer_name.isnot(None),
        HandcraftJewelryItem.customer_name != "",
    )
    union_q = order_names.union(hc_names).union(hc_jewelry_names)
    rows = union_q.all()
    names = sorted({r[0] for r in rows})
    if query:
        q = query.strip().lower()
        names = [n for n in names if q in n.lower()]
    return names[:limit]
```

权限:复用 `require_permission("handcraft")`(只在 HC 详情用)。

## 测试计划

### 后端

`tests/test_api_customers.py`:
- 空库返空数组
- 三个来源都去重(同名只出现一次)
- query 模糊匹配大小写不敏感
- `limit` 截断
- 未登录 / 无 handcraft 权限 → 403

### 前端

无 e2e 框架,沿用现有"组件由 user smoke test"约定。手动验证清单:
1. pending HC + 多种 jewelry:加客户、跨饰品填数、保存,再次进入看是否回放正确
2. processing HC:确认数量字段只读、可加新手填行
3. completed HC:整体只读
4. 含 locked entries 的客户行:整行删除按钮不存在,客户名只读
5. 锁+手填混合单元格:能正确显示 `N🔒 + [M]`,改 M 保存生效
6. 保存中途失败 (mock 一个 DELETE 失败):弹错并重新拉取
7. 手机宽度 (375px):横滚 + sticky-left + sticky-bottom 按钮表现
8. **空表 HC** (新建、无 entries):header tag 显示 `未分拣 · 0/N`,表体显示斜纹"尚未分配"提示;进编辑态后 add-bar 出现
9. **一键剩余分给 · 空表场景**:编辑 → ⚡ 一键 → 选客户「李四」→ 填入 → 保存,完成后矩阵 1 行李四、全绿;再次进入回放正确
10. **一键剩余分给 · 已有 locked 行**:点 ⚡ 一键,popover 预览写明"不会动 🔒 ...";选已存在的 locked 客户「张三」→ 填入,该行变成"锁+手填混合"
11. **一键剩余分给 · 已有 manual 部分**:选已存在的 manual 客户「李四」→ 填入,李四这一行的相应单元格数字累加
12. **一键按钮禁用**:矩阵已分满 → 按钮 disabled + 文案「已无剩余可分」

## 未决事项

- **列顺序** — 暂沿用 backend 返回的 first-seen 顺序(`HandcraftJewelryItem.id asc`);后续若用户希望按 jewelry_id 字母序可再加 sort
- **行顺序** — locked 客户行优先(按订单加入顺序),然后是 manual 客户行(按 first-seen);保存后新加的客户行追加末尾
- **客户名重命名的副作用** — 现版方案:改 manual 行客户名等于改该客户所有 manual entries 的 `customer_name`。后端目前 `PATCH` 一次只改一行,前端需要循环 patch 多次。若该行只有 1 个 entry 是普通情况,这没问题;多 entry 场景比较罕见,先这样,出现性能问题再考虑批量端点
- **没有占位 entry 时的一键** — 若 HC 单创建后所有 entries 都已分了客户(无 `customer_name = None` 占位),「⚡ 一键」按钮显示 disabled + 文案「已无剩余可分」。希望"在已分基础上再加产能给某客户" 的场景,本期通过手动「+ 加一行客户」+ 填数完成(只 pending 可加新 entry)
- **picking_simulation 生成的 entries 形态** — 现假设 picking_simulation 至少生成 `customer_name = None` 占位 entries(覆盖单内全部产能),一键分配才有可认领对象。后续需要 verify;如果某些 picking 流程不生成占位 entry,需要 picking_simulation 配合补 None 占位,或一键分配 fallback 到 add 路径(可能影响 total_qty 语义,需进一步设计)
