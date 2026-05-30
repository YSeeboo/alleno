# 手工单客户分拣 · 矩阵交互设计

## 背景

`HandcraftDetail.vue` 当前的"客户分拣"区域按饰品分组 (一个 jewelry 一组),每组一个"编辑分拣"按钮 → 打开 `BreakdownEditModal` → 在 modal 里维护该饰品的客户列表。

**问题**: 操作者的真实工作流是"按客户视角分配" (给张三这一票:A 饰品 2 件 + B 饰品 1 件 + …),而当前 UI 强制"按饰品视角逐一处理",一个饰品一个 modal,饰品种类一多就要"开窗-填-关窗-再开下一个",非常碎片化。

**目标**: 一屏看全 HC 单的所有客户分拣,加一行 = 加一位客户、横向把他这一票几种饰品填了即可。

## 范围

- ✅ 仅改 HC 详情页的"客户分拣"区域 (替换 `BreakdownEditModal` + `BreakdownChips`)
- ✅ 新增"历史客户名 suggest"API
- ❌ 不改 PDF 输出 (`handcraft_pdf.py`)
- ❌ 不改 cargo sorting 模块 (它独立消费 breakdown 数据)
- ❌ 不引入 `Customer` 主数据表 (沿用现状:`customer_name` 是文本列)

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

### 单元格状态机

每个 `(customer, jewelry)` 单元格只有 4 种形态:

| 形态 | 后端数据 | 渲染 | 可编辑 |
|---|---|---|---|
| 空 | 该 customer 该 jewelry 没有任何 entry | `—` 灰字 | 点击 → 变成 `[0]` 数字框 |
| 仅手填 | ≥1 个 manual entry,无 locked | `[N]` 数字框,N = manual qty 之和 | 是 (状态约束下) |
| 仅锁定 | ≥1 个 locked entry, 无 manual | `N 🔒` 黄底,N = locked qty 之和 | 否,hover 显示来源订单列表 |
| 锁+手填 | ≥1 个 locked + ≥1 个 manual | `N🔒 + [M]` 黄白渐变背景 | 仅 manual 数字框 `M` 可编辑 |

**对手填数字的语义**: 把同一 `(customer, jewelry)` 下的所有 manual entries 折叠成单一 qty。前端编辑时:
- 折叠 qty 从 0 → 正数:`POST /handcraft/{id}/jewelry`(add 新 manual entry)
- 折叠 qty 改变:`PATCH /handcraft/{id}/jewelry/{item_id}`(update 现有 manual entry)
- 折叠 qty 从正数 → 0:`DELETE /handcraft/{id}/jewelry/{item_id}`(delete 该 manual entry)
- 若历史上不慎存在多个 manual entry 在同 `(customer, jewelry)`:保留全部 entries,展示时合计,编辑时只 update 第一个、delete 其余 (一次性 normalize)

### 客户行规则

| 行类型 | 客户名 | 整行 × 删除 |
|---|---|---|
| 全 locked(只有订单来源 entries) | 只读,带 🔒 与 `↗ OR-XX` | 不显示 |
| 全 manual | `pending` 状态可改(下拉 picker),改名后批量 update 该行所有 manual entries 的 `customer_name`;`processing` 状态只读 | `pending` / `processing` 都显示;点击删除该行所有 manual entries |
| 混合(部分 locked + 部分 manual) | 只读(锁定来源决定身份) | 不显示;只能格子级把 manual 改 0 |

(客户名"可改"以下表的状态约束为前提。)

### 客户名 picker(下拉建议)

加新行时,客户名输入框是"可搜索的 select",数据源:`order.customer_name` ∪ `handcraft_order.customer_name` ∪ `handcraft_jewelry_item.customer_name`(把过去 HC 内手填的客户名也带上),去重排序。允许输入下拉外的新名(直接打字回车即新增)。

实现:新增 `GET /api/customers/names?q=`,返回去重的客户名数组(≤ 50 条,按出现频次或字母序)。

### 状态约束(沿用现有后端规则)

| HC 状态 | 允许操作 |
|---|---|
| `pending` | 全部 manual 可编辑:加/删客户行、加/删/改单元格数字、改客户名 |
| `processing` | 仅可加/删手填行 (新加客户行 + 新填空单元格);现有手填数字 **不可改**;客户名不可改 |
| `completed` | 全只读 |

(`locked` entries 任何状态都不可在此处改/删 — 沿用现有后端规则,要改回订单。)

UI 在 header 用 tag 明示当前可做什么,例如 `processing · 仅可加/删手填行`。

### 校验

- 每列底显示"已分 / 总数",相等显示绿色 ✓,不等显示红色 ⚠
- 不强制一次分完就能保存(与当前后端一致 — 允许部分分拣)
- 保存时仅做"客户名非空"和"数量 ≥ 0"的基础校验

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

- `frontend/src/components/BreakdownMatrix.vue` — 主组件(只读 + 编辑双态、矩阵渲染、保存 diff)
- `frontend/src/components/CustomerNameSelect.vue` — 客户名下拉(包装 `n-select`,异步搜索,允许输入新值)
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

## 未决事项

- **列顺序** — 暂沿用 backend 返回的 first-seen 顺序(`HandcraftJewelryItem.id asc`);后续若用户希望按 jewelry_id 字母序可再加 sort
- **行顺序** — locked 客户行优先(按订单加入顺序),然后是 manual 客户行(按 first-seen);保存后新加的客户行追加末尾
- **客户名重命名的副作用** — 现版方案:改 manual 行客户名等于改该客户所有 manual entries 的 `customer_name`。后端目前 `PATCH` 一次只改一行,前端需要循环 patch 多次。若该行只有 1 个 entry 是普通情况,这没问题;多 entry 场景比较罕见,先这样,出现性能问题再考虑批量端点
