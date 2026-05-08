# 手工单缺货补货提醒（Handcraft Restock Reminder）设计

**Date**: 2026-05-07
**Status**: Draft（待用户审阅）
**Related**: `docs/superpowers/specs/2026-04-27-handcraft-picking-simulation-design.md`

## 背景

配货给手工时经常出现"配件不足"的情况。当前系统已有的能力：

- 手工单详情页的**配货模拟弹窗**会显示每行的 `current_stock`，并对 `current_stock < needed_qty` 的行做红色高亮（`stock-low` class）。
- 但红色只是**视觉提示**，没有任何持久化、跨单聚合或后续提醒机制。

实际工作流：仓库在配货时一眼看到"小圆环不够"、"银扣头不够"，但**没有地方记录**。等做完该单的事再回头补货时，往往已经忘了哪些配件需要补。

## 目标

让仓库在配货过程中**顺手把"需要补货"这个事实记下来**，事后能在一个统一的页面看到所有待补货的配件，逐项勾掉已补的。

具体能力：

1. 在配货模拟弹窗里**一键标记**某行"需补货"。
2. 在手工单详情里**手动添加**配货模拟之外发现的补货项（实物丢失、想多备）。
3. 一个**全局「待补货清单」页面**，按配件聚合查看所有手工单的补货需求。
4. 补货完成后**手动勾选"已补货"**关闭记录；保留 `done` 历史以便复盘。

## 非目标

- **不记录补货数量**。只记录"该配件需补货"这一事实。具体补多少、几时去采购，由用户判断。
- **不和「配件采购单」(`PurchaseOrder`) 联动**。补货清单是个独立的"待办本"，不自动开采购单、不被采购单消解。
- **不和 `inventory_log` 联动**。入库不会自动消解补货记录。
- **不修改手工单状态机**。任何状态（pending / processing / completed）的手工单都可以加补货记录。
- **不为前端补单元测试**（项目惯例），依赖手测验证。

## 关键设计决策（与用户确认）

| 决策点 | 选择 |
|---|---|
| 数据来源 | ① 配货模拟弹窗一键标记 + ② 手工单详情手动添加（两者都要） |
| 查看范围 | 全局「待补货清单」页面 |
| 关闭机制 | 手动勾选"已补货"（按手工单来源逐条勾，加一个"全部已补货"批量按钮） |
| 数量 | 不记录数量，只记录事实 |
| 添加权限 | 任何状态的手工单都可以加 |
| 唯一性 | 同一手工单 + 同一配件**永远只有一条记录** |
| 状态流转 | `pending` → `done` 单向，**不可逆** |
| done 处理 | 留作历史（不物理删除） |
| 删手工单 | cascade 删除该单全部补货记录（pending + done） |

## 数据模型

### 新增表 `restock_request`

```python
# models/restock_request.py（新文件）

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from database import Base
from time_utils import now_beijing


class RestockRequest(Base):
    """A pending or completed restock request, scoped to a (part, handcraft_order)
    pair. Pure 'todo list' — does not affect inventory or order status."""

    __tablename__ = "restock_request"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    part_id             = Column(String, ForeignKey("part.id"), nullable=False, index=True)
    handcraft_order_id  = Column(String, ForeignKey("handcraft_order.id"),
                                 nullable=True, index=True)
    source              = Column(String, nullable=False)   # "picking" | "manual"
    status              = Column(String, nullable=False, default="pending")  # pending | done
    note                = Column(Text, nullable=True)
    created_at          = Column(DateTime, default=now_beijing, nullable=False)
    completed_at        = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("part_id", "handcraft_order_id", name="uq_restock_part_order"),
    )
```

**关键决策**：

- **唯一键 `(part_id, handcraft_order_id)`** —— 同一手工单的同一配件永远只一条记录。
  - 配货模拟里再次点击已 pending 的行 → 幂等返回。
  - 已 `done` 的行 → 配货模拟和详情卡片里都显示"✓ 已补过"，复选框/按钮 disable，不允许重新打开。
- **`handcraft_order_id` 允许 null** —— 留出"无手工单来源"的口子（未来若想从全局页直接加补货项）。第一版 UI 不开放此入口，但 schema 留好。
- **`source` 字段**：`picking`（配货模拟弹窗一键添加）/ `manual`（手工单详情手输）。用于 UI 显示"来源"列。
- **删手工单时 cascade**：参考 commit `86719df`（`HandcraftPickingRecord` 的处理方式），在 `delete_handcraft_order` 服务里同步清理。
- **建表方式**：走 `Base.metadata.create_all()`（lifespan 启动），不需要 `ensure_schema_compat()` 加列。

### 模型注册

`models/__init__.py` 加一行 `from .restock_request import RestockRequest`，确保 `create_all()` 看见。

## 后端服务（`services/restock.py` 新文件）

| 函数 | 行为 |
|---|---|
| `create_from_picking(db, part_id, handcraft_order_id)` | 从配货模拟弹窗一键添加。已 pending 幂等返回；已 done 抛 `ValueError("该配件已为此手工单补过货")`。否则插入 pending，`source='picking'`。 |
| `create_manual(db, part_id, handcraft_order_id, note=None)` | 从手工单详情手动添加。同上幂等/已 done 检查；插入 `source='manual'`，可附 `note`。 |
| `mark_done(db, request_id)` | pending → done，写 `completed_at = now_beijing()`。已 done 抛 `ValueError`。 |
| `mark_part_done(db, part_id)` | "全部已补货"用：把该 part 下**所有 pending** 记录批量标 done。返回更新条数。 |
| `delete_pending(db, request_id)` | 撤销标记（仅 pending 可删）。已 done 抛 `ValueError`。 |
| `list_for_handcraft(db, hc_id)` | 手工单详情用，返回该单所有补货记录（pending + done） |
| `list_pending_summary(db)` | 全局「待补货」tab 用。按 part_id 聚合：返回 part 信息、当前库存、来源手工单列表。 |
| `list_history(db, part_id=None, hc_id=None, limit=200)` | 全局「历史」tab 用，列出 done 记录。 |

**实现要点**：

- 所有函数 stateless，调 `db.flush()` 不调 `commit`（项目惯例）。
- 业务错误抛 `ValueError`，由 `service_errors()` → 400。
- `list_pending_summary` 内部用 `_load_stock` 风格的辅助函数算 `current_stock = SUM(change_qty)`，参考 `services/handcraft_picking.py:_load_stock`。
- `mark_part_done` 用一条 UPDATE 完成（`UPDATE restock_request SET status='done', completed_at=now WHERE part_id=? AND status='pending'`），避免 N+1。

### 在 `services/handcraft.py` 的 `delete_handcraft_order` 里加 cascade 清理

类似 `HandcraftPickingRecord` 现行做法：

```python
db.query(RestockRequest).filter_by(handcraft_order_id=hc_id).delete(synchronize_session=False)
```

同时如果删除单条 `HandcraftPartItem`，**不需要**清理对应补货记录 —— 补货是按 `(part_id, handcraft_order_id)` 维度，和 part_item 表无直接外键关系，删某个 part_item 不应影响"我标记过这个配件需补货"的事实。

## 后端 API（`api/restock.py` 新文件）

| Method | Path | Body / Query | 调用服务 |
|---|---|---|---|
| `POST` | `/api/restock-requests` | `{part_id, handcraft_order_id, source: "picking"\|"manual", note?}` | `create_from_picking` 或 `create_manual` 分发 |
| `PATCH` | `/api/restock-requests/{id}` | `{status: "done"}` | `mark_done` |
| `DELETE` | `/api/restock-requests/{id}` | — | `delete_pending`（仅 pending） |
| `POST` | `/api/restock-requests/mark-part-done` | `{part_id}` | `mark_part_done`（全局清单"全部已补货"按钮） |
| `GET` | `/api/restock-requests/summary` | — | `list_pending_summary` |
| `GET` | `/api/restock-requests/history` | `?part_id=&handcraft_order_id=&limit=` | `list_history` |
| `GET` | `/api/handcraft-orders/{hc_id}/restock-requests` | — | `list_for_handcraft` |

最后一条挂在 `api/handcraft.py` 现有 router 下，前面六条用新 router 挂在 `/api/restock-requests`。

### Pydantic schemas（`schemas/restock.py` 新文件）

```python
class RestockRequestCreate(BaseModel):
    part_id: str
    handcraft_order_id: Optional[str] = None
    source: Literal["picking", "manual"]
    note: Optional[str] = None

class RestockRequestRead(BaseModel):
    id: int
    part_id: str
    handcraft_order_id: Optional[str]
    source: str
    status: str
    note: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)

class RestockSourceItem(BaseModel):
    request_id: int
    handcraft_order_id: str
    supplier_name: str
    created_at: datetime

class RestockSummaryItem(BaseModel):
    part_id: str
    part_name: str
    part_image: Optional[str]
    current_stock: float
    source_count: int
    sources: list[RestockSourceItem]
```

## 前端

### 入口 1：配货模拟弹窗（`HandcraftPickingSimulationModal.vue`）

最右边新增一列「需补货」（在现有「已选择」列之后）：

| 行状态 | 显示 |
|---|---|
| 库存充足（`current_stock >= needed_qty`） | 灰色 disabled checkbox + "库存充足"，不可标 |
| 库存不足 + 未标记 | 橙色 checkbox（未勾选） + "未标记"。整行黄底 |
| 已 pending（已标记） | 橙色 checkbox（已勾选） + "⏳ 待补货"。整行橙底 |
| 已 done | 绿色徽章 "✓ 已补过"，无 checkbox（不可重标） |

**交互**：点击未勾选 checkbox → `POST /api/restock-requests` body `{part_id, handcraft_order_id, source: 'picking'}`。点击已勾选 checkbox → `DELETE /api/restock-requests/{id}` 撤销标记（仅 pending 可撤）。

**已 done 状态的判断**：picking 接口的响应里加 `restock_status` 字段（`null` / `pending` / `done`）和 `restock_request_id`（用于 DELETE）。

### 入口 2：手工单详情新增「补货清单」卡片（`HandcraftDetail.vue`）

详情页底部加一张卡片，和"基本信息/配件清单/饰品清单"并列。

**结构**：

- 标题区：「补货清单 · 待补 N · 已补 M」 + 「+ 手动添加」按钮
- 表格列：配件 / 来源 / 状态 / 备注 / 操作
- 数据：调 `GET /api/handcraft-orders/{hc_id}/restock-requests` 拉本单全部记录
- pending 行：「已补货」按钮（→ PATCH 标 done）+「取消」按钮（→ DELETE 撤销）
- done 行：浅灰 + 60% 透明，操作列显示"X/Y 完成"
- 「+ 手动添加」弹窗：选配件（参考 `HandcraftCreate.vue` 现有的 `n-select` + 搜索的 part 选择实现）+ 备注（选填，textarea）

### 入口 3：全局「待补货清单」页面

**侧边栏位置**：`生产` 组下，和「配件采购」并列：

```
生产
├── 订单管理
├── 配件采购
├── 待补货清单     ← 新增
├── 电镀（组）
└── 手工单（组）
```

**路由**：`/restock`，对应 `views/restock/RestockList.vue`（新文件）。

**权限 key**：建议复用 `'handcraft'`（功能起源于手工单缺货）。如果需要单独的 perm，先用 `'handcraft'`，后续再独立。

**页面结构**：

- 顶部 tabs：「待补货 (N)」 / 「历史」
- 「待补货」tab：
  - 过滤区：搜索框（按 part_id / part_name 筛选） + 「仅看库存为 0」复选框
  - 数据：`GET /api/restock-requests/summary`
  - 列表：每个 part 一张大卡片
    - 折叠态：图 / `part_id · part_name` / 当前库存（库存 < 来源数 时红色） / 来源数 / 「全部已补货」按钮 / 展开图标
    - 展开后：每条来源一行（手工单链接 / 手工商家 / 标记时间 / 「已补货」按钮）
  - 「全部已补货」按钮 → `POST /api/restock-requests/mark-part-done` body `{part_id}`，弹确认对话框防误点
  - 单条「已补货」按钮 → `PATCH /api/restock-requests/{id}` `{status: "done"}`
- 「历史」tab：
  - 表格：配件 / 来源手工单 / 标记时间 / 完成时间 / 来源类型（picking/manual）
  - 数据：`GET /api/restock-requests/history`
  - 默认按 `completed_at desc`，分页（每页 50 条）

### 前端 API 客户端

新文件 `frontend/src/api/restock.js`：

```js
export const listRestockSummary = () => http.get('/restock-requests/summary')
export const listRestockHistory = (params) => http.get('/restock-requests/history', { params })
export const listHandcraftRestock = (hcId) => http.get(`/handcraft-orders/${hcId}/restock-requests`)
export const createRestock = (payload) => http.post('/restock-requests', payload)
export const markRestockDone = (id) => http.patch(`/restock-requests/${id}`, { status: 'done' })
export const markPartRestockDone = (partId) => http.post('/restock-requests/mark-part-done', { part_id: partId })
export const deleteRestock = (id) => http.delete(`/restock-requests/${id}`)
```

## 边界与错误处理

| 场景 | 行为 |
|---|---|
| 重复 POST 同一 (part, hc) 且已 pending | 幂等，返回现有记录（200） |
| POST 同一 (part, hc) 但已 done | 400 `"该配件已为此手工单补过货"` |
| PATCH 已 done 的记录改回 pending | 400 `"补货记录已完成，不可重置"` —— 我们不支持已 done 重新打开 |
| DELETE 已 done 记录 | 400 `"已补货的记录不可删除"` |
| `part_id` 不存在 | 400 `"配件不存在"` |
| `handcraft_order_id` 不存在 | 400 `"手工单不存在"` |
| 删手工单 | cascade 删除该单全部 RestockRequest（pending + done）|
| 并发 POST 同一 (part, hc) | 唯一键约束兜底：服务函数 `try` 包 `db.flush()`，捕 `IntegrityError` 后重新查询现有记录返回（幂等语义） |

## 测试计划（后端）

`tests/test_services_restock.py`：

- 创建 from picking：新插入 → pending；已 pending 幂等；已 done 抛错。
- 创建 manual：同上 + note 字段保存。
- `mark_done`：pending → done + completed_at；已 done 抛错。
- `mark_part_done`：批量 update，只影响 pending；返回数量正确。
- `delete_pending`：pending 可删；done 抛错。
- `list_pending_summary`：聚合按 part_id；source_count 正确；当前库存计算正确。
- `list_for_handcraft`：返回 pending + done，按 created_at desc。
- 删手工单 cascade：调 `delete_handcraft_order` 后，相关 RestockRequest 全清掉（pending + done）。

`tests/test_api_restock.py`：

- POST / PATCH / DELETE / GET 每个端点的成功 + 错误码（400 文案）。
- `mark-part-done` 端点。
- 并发 POST 的唯一键冲突（用 `client_real_get_db` 真实 commit 触发）。

## 任务分解（高层）

按顺序：

1. **后端模型 + 迁移**：`models/restock_request.py`，`models/__init__.py` 注册。
2. **后端服务 + 单测**：`services/restock.py` + `tests/test_services_restock.py`。
3. **后端 API + 接口测试**：`schemas/restock.py`、`api/restock.py`、`main.py` 注册 router、`tests/test_api_restock.py`。
4. **手工单删除 cascade**：改 `services/handcraft.py:delete_handcraft_order`，加一行 RestockRequest 清理 + 测试。
5. **picking 接口扩展**：`services/handcraft_picking.py` + schema 加 `restock_status` / `restock_request_id` 字段。
6. **前端 API 客户端**：`frontend/src/api/restock.js`。
7. **前端：配货模拟弹窗加列**：`HandcraftPickingSimulationModal.vue`。
8. **前端：手工单详情补货清单卡片**：`HandcraftDetail.vue` + 手动添加弹窗。
9. **前端：全局清单页**：路由 + `RestockList.vue` + 侧边栏菜单项。

## 开放问题

- **侧边栏菜单图标**：用 `WarningOutline` / `AlertCircleOutline` / `CartOutline` 哪个？实施时定，问题不大。
- **「待补货」红点提醒**：是否在侧边栏菜单项右边显示一个待补货数量的红点徽章？第一版**不做**，可后续加。
- **手工单详情卡片是否显示在已删除手工单上**：手工单不能"软删"，所以无此场景。
