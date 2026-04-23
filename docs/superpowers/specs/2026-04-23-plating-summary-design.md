# 电镀汇总 设计文档

## 背景

当前系统中查看某个配件的电镀进度需要在「电镀发出」「电镀回收」两个独立列表之间反复切换，操作路径长。例如想知道"某个配件最近一次发出去镀了几天还没回来"或"某商家手上还压着哪些配件"，都要逐单点开详情才能看到。

需要一个 per-item 粒度的汇总视图，把所有电镀配件的发出/回收状态一屏列出，便于直观掌握当前电镀情况。

## 目标

新增 **电镀汇总** 子页面，提供：

1. 「已发出」与「已收回」两个 tab，per-item 粒度展示电镀配件的全量历史
2. 商家、日期、关键字筛选；可按发出天数排序
3. 一键跳转到对应的电镀单 / 回收单详情，并高亮目标行（复用现有高亮模式）
4. 在汇总页直接触发「确认损耗」操作（复用现有逻辑）

## 导航与菜单调整

修改 `frontend/src/layouts/DefaultLayout.vue` 的菜单分组：

| 当前 | 调整后 |
|------|--------|
| 电镀单 / 电镀发出 / 电镀回收 | **电镀** / 电镀发出 / 电镀回收 / **电镀汇总** |

- 父分组 key 仍用 `plating-group`，label 由「电镀单」改为「电镀」
- 新增第三个子项 `plating-summary`，使用 `frontend/src/assets/icons/汇总.svg`（参考现有 `PlatingIcon.vue` 的封装方式新建 `PlatingSummaryIcon.vue`）
- 路由：`/plating-summary` → `frontend/src/views/plating/PlatingSummary.vue`
- 权限：复用 `plating` perm

## 数据语义

### 行粒度

**一个 `PlatingOrderItem` 对应一行**。同一个配件如果在多个电镀单里同时存在，就有多行（每个电镀单独立一行）。

### 关键字段澄清

- `PlatingOrderItem.received_qty` 在确认损耗时会被自动加上 `loss_qty`（见 `services/production_loss.py::confirm_plating_loss` line 63）。也就是说 `received_qty` 已经隐含了"实收 + 已确认损耗"两部分。
- 实际收回数（仅指真实回收事件）= `SUM(plating_receipt_item.qty WHERE plating_order_item_id = X)`
- 已确认损耗数 = `SUM(production_loss.loss_qty WHERE order_type='plating' AND item_type='plating_item' AND item_id = X)`
- 三者关系恒等：`真实收回 + 已确认损耗 = received_qty`；`未回收 = qty - received_qty`

### 「已发出」tab — 入选与排序规则

- **入选条件**：所有 `PlatingOrderItem`（全量历史，不论是否已收回）
- **分区**：
  - 进行中 = `received_qty < qty`
  - 已完成 = `received_qty >= qty`（包括全部真实回收 / 部分回收+剩余已确认损耗 / 全部确认损耗 三种情况）
- **默认排序**：先按 `is_completed` 升序（进行中在前），再按发出日期降序
- **手动排序**：点击「发出天数」列头时，**忽略分区**，所有行混在一起按发出天数降序排（已完成行的发出天数显示为 `—`，参与排序时按 0 处理排在最后）

### 「已收回」tab — 入选与排序规则

- **入选条件**：`received_qty > 0`（等价于"至少有一次回收事件 OR 已确认损耗"，因为两者都会让 `received_qty` 变正）
- **分区**：与已发出 tab 一致
  - 进行中 = `received_qty < qty`
  - 已完结 = `received_qty >= qty`
- **默认排序**：先按 `is_completed` 升序（进行中在前），再按 **最新收回日期降序**（与日期筛选维度一致——最近收回的排最前）。100% 损耗无回收的 item 走 NULLS LAST 沉到分区末尾。
- **手动排序**：本 tab 暂不开放列头点击排序

### 两个 tab 的重叠关系

- 进行中且已有部分真实回收的 item → **同时出现**在两个 tab
- 全部回收完成 / 已确认损耗的 item → 在两个 tab 中都属于"沉底"区
- 全部确认损耗（无真实回收，loss = qty）的 item → 在「已收回」tab 出现并位于沉底区（按 Q-E 决议）

## 列定义

### 共用列

| 列 | 说明 |
|----|------|
| 商家 | `plating_order.supplier_name` |
| ID | 配件 ID（如 PJ-DZ-00012） |
| 配件 | 缩略图 + 名称（图片复用 `renderImageThumb()`，自带 lightbox） |
| 电镀颜色 | `plating_order_item.plating_method` 的单值（G/S/RG 任一） |
| 收回配件 | 缩略图 + 名称：`receive_part_id` 对应的配件；未回收行此列空 |
| 发出日期 | `plating_order.created_at` 的日期部分（北京时区，YYYY-MM-DD） |
| 发出数量 | `qty` |
| 单位 | `unit` |
| 重量 | `weight` + `weight_unit` |
| 备注 | `note` |
| 电镀单号 | `plating_order.id`（如 EP-0042），可点击跳转 + 高亮 |

### 「已发出」特有列

| 列 | 位置 | 说明 |
|----|------|------|
| **发出天数** | 商家与 ID 之间 | 计算公式：`max(0, today - dispatch_date - 1)`，单位"天"。已完成行显示 `—`。颜色：0 天=绿，1–7 天=黄，≥8 天=红。可点击列头排序。 |

发出天数计算细节：
- `today` = 北京时区当日（`now_beijing().date()`）
- `dispatch_date` = `plating_order.created_at` 转北京时区后的日期
- 例：4 月 23 日发出，4 月 26 日查看 → `26 - 23 - 1 = 2` 天
- 同日查看 → `23 - 23 - 1 = -1`，取 0

### 「已收回」特有列

| 列 | 位置 | 说明 |
|----|------|------|
| **收回日期** | 发出日期之后 | 同 item 多次回收时，**最新在前、全部用逗号分隔** |
| **已回收** | 备注之前 | 真实回收数（`SUM(plating_receipt_item.qty)`），**不含**已确认损耗 |
| **未回收** | 已回收之后 | `qty - received_qty`（即剩余既未回收也未确认损耗的部分） |
| **损耗** | 未回收之后、备注之前 | 三态显示，规则见下 |
| **回收单号** | 列尾 | 同 item 多次回收时，最新在前、全部逗号分隔，每个均可点击跳转 + 高亮 |

#### 损耗列三态

设 `actual_received` = 真实回收数（`SUM(plating_receipt_item.qty)`），`loss_total` = 已确认损耗数（`SUM(production_loss.loss_qty)`）。

| 条件 | 显示 |
|------|------|
| `loss_total > 0`（已确认损耗，可能仅部分） | 红色字体显示 `loss_total` |
| `loss_total == 0` 且 `qty == actual_received` | `—` |
| `loss_total == 0` 且 `qty > actual_received` | 【确认损耗】按钮 |

【确认损耗】按钮点击：

- 弹出与「回收单详情」一致的损耗确认弹窗（loss_qty / deduct_amount / reason）
- 后端接口为 `POST /plating-receipts/{receipt_id}/confirm-loss`，必须依附在某个回收单上
- 由于按钮只会出现在 `qty > actual_received` 的行（≥1 次真实回收），从该 item 的最新一次 `plating_receipt_item.plating_receipt_id` 取 `receipt_id` 作为接口入参
- 边界：理论上 100% 损耗（无真实回收）的 item 不会显示该按钮（已落入"已确认损耗"分支显示红字），不存在"无回收单可挂载"的状况

## 顶部工具栏

布局：标题下一行，左侧 tab 切换，右侧筛选区。

```
电镀汇总
[已发出] [已收回]                     [📅 日期] [商家▾] [🔍 搜索框]
```

### 筛选控件

| 控件 | 行为 |
|------|------|
| 日期 | 支持单日 / 区间两种模式（NDatePicker `type="daterange"`）；已发出 tab 按发出日期过滤、已收回 tab 按收回日期过滤（多回收时只要任一回收日落在范围内即匹配） |
| 商家 | 下拉源 = 所有历史电镀商家（复用 `getPlatingSuppliers()`） |
| 搜索框 | 按配件 ID + 配件名搜索；后端复用 `keyword_filter()`（多 token AND ILIKE）；前端 300ms 防抖（沿用 PartList 模式） |

筛选状态在 tab 切换时**保留**（用户切回原 tab 不丢失筛选）。

## 跳转 / 高亮

复用现有 `?highlight=<id>` + `receipt-highlight-row` 闪烁动画方案：

| 来源 | 目标 | 高亮目标 |
|------|------|---------|
| 汇总「电镀单号」点击 | `/plating/{order_id}?highlight={item_id}` | 电镀单详情中对应明细行 |
| 汇总「回收单号」点击 | `/plating-receipts/{receipt_id}?highlight={receipt_item_id}` | 回收单详情中对应明细行 |

### 返回时保留汇总筛选

跳转时把当前筛选状态写入 URL query：

- 汇总页路由：`/plating-summary?tab=out&supplier=锦泰镀业&date=2026-04-17,2026-04-23&q=圆形&page=2`
- 跳转到详情页前，把当前 query 序列化进 `history.state.summaryReturn`
- 详情页提供「返回汇总」入口，触发 `router.back()`；浏览器原生后退也能恢复
- 实现：使用 `useRoute().query` 双向同步页面 state（每次筛选变化 `router.replace` 更新 query），无需手动 state 管理

## 分页

- 默认 30 条/页
- 后端分页：`?skip=&limit=`
- 前端 NPagination 组件，支持跳转任意页

## 移动端

- 列多采用横滑（`overflow-x: auto` 包裹 table）
- 不做列折叠 / 二级展开

## 后端设计

### 新增 service: `services/plating_summary.py`

两个查询函数，输出统一为 per-item DTO：

```python
def list_dispatched(
    db: Session,
    *,
    supplier_name: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    part_keyword: str | None = None,
    sort: Literal["dispatch_date_desc", "days_out_desc"] = "dispatch_date_desc",
    skip: int = 0,
    limit: int = 30,
) -> tuple[list[DispatchedItemDTO], int]:
    """
    返回 (items, total)。items 已按 (is_completed asc, sort) 排序。
    sort='days_out_desc' 时打平分区，全量按发出天数排。
    """

def list_received(
    db: Session,
    *,
    supplier_name: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    part_keyword: str | None = None,
    skip: int = 0,
    limit: int = 30,
) -> tuple[list[ReceivedItemDTO], int]:
    """
    返回 (items, total)。仅返回 received_qty > 0 的 item
    （等价于"至少有一次真实回收 OR 已确认过损耗"）。
    排序固定 (is_completed asc, dispatch_date desc)。
    """
```

### 新增 API: `api/plating_summary.py`

```
GET /api/plating-summary/dispatched   → list_dispatched
GET /api/plating-summary/received     → list_received
```

Query 参数对齐 service 函数签名。响应包：

```json
{
  "items": [ { ... DTO ... } ],
  "total": 47
}
```

### DTO 字段

**DispatchedItemDTO**（已发出）：

```
plating_order_item_id, plating_order_id, supplier_name,
part_id, part_name, part_image,
plating_method, qty, unit, weight, weight_unit, note,
dispatch_date,                              # date (北京时区)
days_out,                                   # int | None；已完成时为 None
is_completed,                               # bool（用于前端样式）
receive_part_id, receive_part_name, receive_part_image  # 已完成行才有值
```

**ReceivedItemDTO**（已收回）增量字段：

```
actual_received_qty,         # SUM(plating_receipt_item.qty)
unreceived_qty,              # qty - received_qty
loss_total_qty,              # SUM(production_loss.loss_qty)
loss_state,                  # "none" | "pending" | "confirmed"
                             #   none      = qty == actual_received_qty AND loss_total_qty == 0
                             #   pending   = qty > actual_received_qty AND loss_total_qty == 0
                             #   confirmed = loss_total_qty > 0
receipts: [                  # 按 plating_receipt.created_at desc
  { receipt_id, receipt_item_id, receipt_date }
],
latest_receipt_id            # 便于「确认损耗」按钮拼 endpoint，取 receipts[0].receipt_id
```

### 复用与避免重复

- 关键字过滤：复用 `services/_helpers.py::keyword_filter()`
- 商家下拉：复用 `services/plating.py` 中已有的 supplier 列表查询（前端继续调 `getPlatingSuppliers()`）
- 损耗确认：复用 `POST /plating-receipts/{receipt_id}/confirm-loss`（receipt_id 取该 item 最新一次回收所属的回收单 ID），无需新接口
- 商家筛选数据源：所有历史电镀商家（不随 tab/筛选变化）

### 性能考虑

- 主查询基于 `plating_order_item` 表 join `plating_order`，`plating_part`（配件名/图）：
  - 已有索引：`plating_order_item.plating_order_id`（外键自动）
  - 建议补索引：`plating_order_item.part_id`（如果未有），`plating_order.created_at`
- 「已收回」需要分别聚合 `plating_receipt_item`（真实回收数 + 回收单列表）和 `production_loss`（已确认损耗数）→ 在 service 层做三步查询（先取 item id 集合，再批量取 receipts、losses），避免笛卡尔展开
- `production_loss` 表按 `(order_type, item_type, item_id)` 查询，建议补复合索引
- 默认 30/页配合 skip/limit；count 单独执行

## 前端设计

### 文件结构

```
frontend/src/views/plating/
  PlatingSummary.vue              # 新增主页面（含两个 tab 表格）
frontend/src/components/icons/
  PlatingSummaryIcon.vue          # 新增（封装汇总.svg）
frontend/src/api/
  platingSummary.js               # 新增 API 封装（getDispatched, getReceived）
```

### 路由

`frontend/src/router/index.js` 新增：

```js
{
  path: '/plating-summary',
  name: 'plating-summary',
  component: () => import('@/views/plating/PlatingSummary.vue'),
  meta: { perm: 'plating' }
}
```

### 组件内部结构

`PlatingSummary.vue` 单一文件即可，不再拆子组件：

- `tab` ref：`'out' | 'in'`，默认 `'out'`，与 URL `?tab=` 双向同步
- `filters` ref：`{ supplier, dateRange, q }`，与 URL query 双向同步
- 两个独立的 `useDataLoader` 状态（dispatched / received），切 tab 时保留对方状态
- 表格组件：`NDataTable` + 不同的 columns 配置
- 列单元格的图片渲染、跳转链接、损耗按钮都用现有 `utils/ui.js` 的 helper

### 样式规则

- 行底色按 `is_completed` 切换：完成行用 `var(--c-row-done-bg)` 灰底
- 分区分隔行：表格内插入伪行（`render-summary` 或 NDataTable 的 row class hook）
- 发出天数颜色梯度：0 → success；1–7 → warning；≥8 → danger
- 损耗数字红色：`color: var(--n-color-error)`

## 边界情况

| 场景 | 处理 |
|------|------|
| 当天发出当天看（days_out 公式 = -1） | 显示 0 天 |
| 已完成行的发出天数 | 显示 `—`；点列头排序时按 0 计 |
| 同一 item 多次部分回收 | 在已收回 tab 单独一行；收回日期 / 回收单号列均"最新在前、逗号分隔" |
| 100% 确认损耗（actual_received=0, loss_total=qty） | 出现在已收回 tab 沉底区；已回收=0，未回收=0，损耗=qty 红字 |
| `receive_part_id` 为空 | 收回配件列回退显示 `part_id` 对应的配件（与现有「收回配件」展示规则一致） |
| 跳转高亮目标 item 不在当前页 | 由详情页负责，与现有跳转一致；汇总页不需要特殊处理 |

## 测试

### 后端单测（`tests/test_api_plating_summary.py`）

- `list_dispatched` 默认排序：进行中在前 + 发出日期降序
- `list_dispatched` `sort=days_out_desc` 打平分区
- `list_received` 入选条件：仅 `received_qty > 0`（同时覆盖"有真实回收"与"已确认损耗"两种来源）
- `list_received` 多回收聚合：`receipts` 按 created_at 降序，`actual_received_qty` 与 `loss_total_qty` 拆分正确（不重叠）
- `loss_state` 三态判定：none / pending / confirmed 各对应一条 fixture
- 100% 损耗 item（actual_received=0, loss=qty）出现在已收回 tab
- 商家筛选 / 日期范围筛选 / 关键字搜索 各自正确性
- 分页 skip/limit 正确

### 前端

- 不强制写组件单测；冒烟手动验证：菜单重命名、新子项跳转、tab 切换、筛选 URL 同步、跳转返回保留状态、确认损耗弹窗

## 不在本次范围

- 导出 Excel（沿用现有 `plating_excel.py` 模式可后续加）
- 颜色筛选
- 移动端列折叠 / 二级展开
- 汇总页发起新的电镀单 / 回收单创建动作

## 修改/新增文件清单

**新增：**

- `services/plating_summary.py`
- `api/plating_summary.py`
- `tests/test_api_plating_summary.py`
- `frontend/src/views/plating/PlatingSummary.vue`
- `frontend/src/components/icons/PlatingSummaryIcon.vue`
- `frontend/src/api/platingSummary.js`

**修改：**

- `main.py`：注册新 router
- `frontend/src/layouts/DefaultLayout.vue`：菜单分组重命名 + 新增子项
- `frontend/src/router/index.js`：新增路由
- `frontend/src/views/plating/PlatingDetail.vue`：支持「返回汇总并保持筛选」
- `frontend/src/views/plating-receipts/PlatingReceiptDetail.vue`：同上
