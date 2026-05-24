# 订单删除 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给订单管理页加一个删除入口，允许硬删除「待生产」状态的订单及其所有 FK 子行，删除前二次确认并告知级联影响。

**Architecture:** 后端在 `services/order.py` 新增 `delete_order()`（按外键依赖顺序级联删子行）和 `get_order_delete_preview()`（返回级联数量）；`api/orders.py` 暴露 `DELETE /{order_id}` 和 `GET /{order_id}/delete-preview`。前端 `OrderList.vue` 新增「操作」列，红色「删除」按钮（仅待生产可点，其余禁用+悬停提示），点击先取 preview 再弹 NaiveUI `dialog.warning` 二次确认。

**Tech Stack:** FastAPI + SQLAlchemy（service 用 `db.flush()`，commit 由 `get_db()` 负责；业务错误 raise `ValueError`，API 用 `service_errors()` 转 400）；Vue 3 + Naive UI（`useDialog`/`useMessage` 已由 App.vue 的 provider 提供）；pytest。

设计依据：`docs/superpowers/specs/2026-05-24-order-deletion-design.md`

---

## File Structure

- **Modify** `services/order.py` — 新增 `delete_order()` 和 `get_order_delete_preview()`。已有 `from models.order import Order, OrderItem, OrderTodoBatch, OrderTodoBatchJewelry, OrderItemLink`（第 9 行），需补充 import `OrderTodoItem, OrderPickingRecord`。
- **Modify** `api/orders.py` — 新增两个路由；`from services.order import (...)` 块（约第 23-38 行）补 `delete_order, get_order_delete_preview`。
- **Modify** `frontend/src/api/orders.js` — 新增 `deleteOrder` 和 `getOrderDeletePreview`。
- **Modify** `frontend/src/views/orders/OrderList.vue` — 新增「操作」列、删除按钮、确认流程。
- **Modify** `tests/test_order.py` — service 层测试。
- **Modify** `tests/test_api_orders.py` — API 层测试。

子行级联删除顺序（外键依赖，子先于父）：
1. `order_picking_record`（FK order_id）
2. `order_item_link`（FK order_id 或 order_todo_item_id → 必须先于 order_todo_item 和 order 删）
3. `order_todo_batch_jewelry`（FK batch_id → 先于 batch 删）
4. `order_todo_item`（FK order_id, batch_id → 先于 batch 删）
5. `order_todo_batch`（FK order_id）
6. `order_item`（FK order_id）
7. `order`

`order_cost_snapshot`（仅已完成生成）、`production_loss`/`vendor_receipt`（引用 EP-/HC- 单，无 FK）均与待生产订单无关，不处理。

---

## Task 1: Service 层 `delete_order` 与 `get_order_delete_preview`

**Files:**
- Modify: `services/order.py:9`（import）、文件末尾追加两个函数
- Test: `tests/test_order.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_order.py` 末尾追加（复用文件已有的 `setup` fixture）：

```python
from services.order import delete_order, get_order_delete_preview
from services.order_todo import create_batch
from services.picking import mark_picked


def test_delete_pending_order_removes_order_and_items(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "张三", [
        {"jewelry_id": j1.id, "quantity": 2, "unit_price": 100.0},
        {"part_id": p1.id, "quantity": 5, "unit_price": 3.0},
    ])
    oid = order.id
    delete_order(db, oid)
    assert get_order(db, oid) is None
    assert get_order_items(db, oid) == []


def test_delete_order_rejects_non_pending(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "李四", [
        {"part_id": p1.id, "quantity": 1, "unit_price": 3.0},
    ])
    # 入库后转已完成，使其离开待生产
    from services.inventory import add_stock
    add_stock(db, "part", p1.id, 10, "测试入库")
    update_order_status(db, order.id, "已完成")
    with pytest.raises(ValueError, match="待生产"):
        delete_order(db, order.id)
    assert get_order(db, order.id) is not None


def test_delete_order_not_found(setup):
    db, *_ = setup
    with pytest.raises(ValueError, match="不存在|not found|OR-9999"):
        delete_order(db, "OR-9999")


def test_delete_order_cascades_picking_records(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "王五", [
        {"part_id": p1.id, "quantity": 2, "unit_price": 3.0},
    ])
    mark_picked(db, order.id, p1.id, 1.0)
    from models.order import OrderPickingRecord
    assert db.query(OrderPickingRecord).filter_by(order_id=order.id).count() == 1
    delete_order(db, order.id)
    assert db.query(OrderPickingRecord).filter_by(order_id=order.id).count() == 0


def test_delete_preview_counts(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "赵六", [
        {"jewelry_id": j1.id, "quantity": 1, "unit_price": 100.0},
        {"part_id": p1.id, "quantity": 2, "unit_price": 3.0},
    ])
    preview = get_order_delete_preview(db, order.id)
    assert preview["item_count"] == 2
    assert preview["batch_count"] == 0
    assert preview["link_count"] == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_order.py -k "delete" -v`
Expected: FAIL — `ImportError: cannot import name 'delete_order'`

- [ ] **Step 3: 实现**

在 `services/order.py` 第 9 行的 import 增补 `OrderTodoItem, OrderPickingRecord`：

```python
from models.order import (
    Order, OrderItem, OrderTodoItem, OrderTodoBatch,
    OrderTodoBatchJewelry, OrderItemLink, OrderPickingRecord,
)
```

在文件末尾追加：

```python
def get_order_delete_preview(db: Session, order_id: str) -> dict:
    """返回级联删除将影响的数量，供前端二次确认弹窗展示。
    订单不存在 -> ValueError。"""
    order = get_order(db, order_id)
    if order is None:
        raise ValueError(f"订单 {order_id} 不存在")
    item_count = db.query(OrderItem).filter(OrderItem.order_id == order_id).count()
    batch_count = db.query(OrderTodoBatch).filter(OrderTodoBatch.order_id == order_id).count()
    todo_item_ids = [
        r[0] for r in db.query(OrderTodoItem.id)
        .filter(OrderTodoItem.order_id == order_id).all()
    ]
    link_q = db.query(OrderItemLink).filter(
        (OrderItemLink.order_id == order_id)
        | (OrderItemLink.order_todo_item_id.in_(todo_item_ids) if todo_item_ids else False)
    )
    link_count = link_q.count()
    return {"item_count": item_count, "batch_count": batch_count, "link_count": link_count}


def delete_order(db: Session, order_id: str) -> None:
    """硬删除待生产订单及其所有 FK 子行。
    非待生产 / 不存在 -> ValueError。commit 由 get_db() 负责。"""
    order = get_order(db, order_id)
    if order is None:
        raise ValueError(f"订单 {order_id} 不存在")
    if order.status != "待生产":
        raise ValueError(f"订单状态为「{order.status}」，只能删除「待生产」状态的订单")

    # 先收集子行 id（外键依赖：子先于父删）
    todo_item_ids = [
        r[0] for r in db.query(OrderTodoItem.id)
        .filter(OrderTodoItem.order_id == order_id).all()
    ]
    batch_ids = [
        r[0] for r in db.query(OrderTodoBatch.id)
        .filter(OrderTodoBatch.order_id == order_id).all()
    ]

    db.query(OrderPickingRecord).filter(
        OrderPickingRecord.order_id == order_id
    ).delete(synchronize_session=False)

    db.query(OrderItemLink).filter(OrderItemLink.order_id == order_id).delete(
        synchronize_session=False
    )
    if todo_item_ids:
        db.query(OrderItemLink).filter(
            OrderItemLink.order_todo_item_id.in_(todo_item_ids)
        ).delete(synchronize_session=False)

    if batch_ids:
        db.query(OrderTodoBatchJewelry).filter(
            OrderTodoBatchJewelry.batch_id.in_(batch_ids)
        ).delete(synchronize_session=False)

    db.query(OrderTodoItem).filter(OrderTodoItem.order_id == order_id).delete(
        synchronize_session=False
    )
    db.query(OrderTodoBatch).filter(OrderTodoBatch.order_id == order_id).delete(
        synchronize_session=False
    )
    db.query(OrderItem).filter(OrderItem.order_id == order_id).delete(
        synchronize_session=False
    )
    db.delete(order)
    db.flush()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_order.py -k "delete" -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add services/order.py tests/test_order.py
git commit -m "feat(order): add delete_order + get_order_delete_preview service

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: API 路由 `DELETE /{order_id}` 与 `GET /{order_id}/delete-preview`

**Files:**
- Modify: `api/orders.py`（import 块约第 23-38 行；在第 149 行 `api_delete_order_item` 之后插入新路由）
- Test: `tests/test_api_orders.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_api_orders.py` 末尾追加：

```python
def test_delete_preview(client, db):
    _, jewelry = _setup(db)
    created = client.post("/api/orders/", json={
        "customer_name": "Carol",
        "items": [{"jewelry_id": jewelry.id, "quantity": 2, "unit_price": 100.0}]
    }).json()
    resp = client.get(f"/api/orders/{created['id']}/delete-preview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["item_count"] == 1
    assert body["batch_count"] == 0
    assert body["link_count"] == 0


def test_delete_pending_order(client, db):
    _, jewelry = _setup(db)
    created = client.post("/api/orders/", json={
        "customer_name": "Dave",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 50.0}]
    }).json()
    resp = client.delete(f"/api/orders/{created['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/orders/{created['id']}").status_code == 404


def test_delete_order_not_found(client, db):
    resp = client.delete("/api/orders/OR-9999")
    assert resp.status_code == 404


def test_delete_non_pending_order_rejected(client, db):
    part, _ = _setup(db)
    from services.inventory import add_stock
    add_stock(db, "part", part.id, 10, "测试入库")
    created = client.post("/api/orders/", json={
        "customer_name": "Eve",
        "items": [{"part_id": part.id, "quantity": 1, "unit_price": 3.0}]
    }).json()
    client.patch(f"/api/orders/{created['id']}/status", json={"status": "已完成"})
    resp = client.delete(f"/api/orders/{created['id']}")
    assert resp.status_code == 400
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api_orders.py -k "delete" -v`
Expected: FAIL — `delete-preview` 返回 404（路由不存在），`DELETE` 返回 405 Method Not Allowed

- [ ] **Step 3: 实现**

在 `api/orders.py` 的 `from services.order import (...)` 块内（约第 23-38 行）追加两个名字：

```python
    delete_order,
    get_order_delete_preview,
```

在第 149 行 `api_delete_order_item` 函数之后插入：

```python
@router.get("/{order_id}/delete-preview")
def api_delete_preview(order_id: str, db: Session = Depends(get_db)):
    if get_order(db, order_id) is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        return get_order_delete_preview(db, order_id)


@router.delete("/{order_id}", status_code=204)
def api_delete_order(order_id: str, db: Session = Depends(get_db)):
    if get_order(db, order_id) is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        delete_order(db, order_id)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_api_orders.py -k "delete" -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 全量回归 + 提交**

Run: `pytest tests/test_order.py tests/test_api_orders.py -q`
Expected: all pass

```bash
git add api/orders.py tests/test_api_orders.py
git commit -m "feat(order): add DELETE /{id} and GET /{id}/delete-preview endpoints

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 前端 API 模块 + OrderList 删除入口

**Files:**
- Modify: `frontend/src/api/orders.js`
- Modify: `frontend/src/views/orders/OrderList.vue`

- [ ] **Step 1: 新增前端 API 函数**

在 `frontend/src/api/orders.js` 的 `deleteOrderItem` 行附近追加：

```javascript
export const deleteOrder = (id) => api.delete(`/orders/${id}`)
export const getOrderDeletePreview = (id) => api.get(`/orders/${id}/delete-preview`)
```

- [ ] **Step 2: OrderList.vue — 引入依赖与处理函数**

修改 `frontend/src/views/orders/OrderList.vue` 的 `<script setup>`：

把第 31 行 naive-ui 的 import 改为补充 `NTooltip, useDialog, useMessage`：

```javascript
import { NButton, NSelect, NDataTable, NSpin, NEmpty, NTag, NTooltip, useDialog, useMessage } from 'naive-ui'
```

把第 32 行 api import 改为补充新函数：

```javascript
import { listOrders, batchGetProgress, deleteOrder, getOrderDeletePreview } from '@/api/orders'
```

在 `const { isMobile } = useIsMobile()`（第 37 行）之后追加：

```javascript
const dialog = useDialog()
const message = useMessage()

const confirmDelete = async (row) => {
  let parts = []
  try {
    const { data } = await getOrderDeletePreview(row.id)
    if (data.item_count) parts.push(`${data.item_count} 个明细`)
    if (data.batch_count) parts.push(`${data.batch_count} 个备货批次`)
    if (data.link_count) parts.push(`${data.link_count} 个生产单关联`)
  } catch (_) {
    return // 预览失败由拦截器提示，终止
  }
  const cascade = parts.length ? `，将一并删除：${parts.join('、')}` : ''
  dialog.warning({
    title: '确认删除订单',
    content: `确认删除订单 ${row.id}？此操作不可恢复${cascade}。`,
    positiveText: '确认删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      await deleteOrder(row.id)
      message.success('订单已删除')
      await load()
    },
  })
}
```

- [ ] **Step 3: OrderList.vue — 新增「操作」列**

在 `columns` 数组（第 74-122 行）的最后一项「创建时间」之后追加一列。把第 121 行的「创建时间」项后面（数组闭合 `]` 之前）插入：

```javascript
  {
    title: '操作',
    key: 'actions',
    width: 80,
    render: (r) => {
      const isPending = r.status === '待生产'
      const btn = h(
        NButton,
        {
          text: true,
          type: 'error',
          disabled: !isPending,
          onClick: (e) => { e.stopPropagation(); confirmDelete(r) },
        },
        { default: () => '删除' }
      )
      if (isPending) return btn
      return h(
        NTooltip,
        null,
        { trigger: () => btn, default: () => '只能删除待生产状态的订单' }
      )
    },
  },
```

> 注意：禁用的 `NButton` 不触发点击，`stopPropagation` 仅在可点击（待生产）时生效，足以阻止行跳转。

- [ ] **Step 4: 手动验证**

Run: `cd frontend && npm run build`
Expected: 构建成功，无报错。

随后人工自测（dev server）：
- 待生产订单行「删除」可点 → 弹窗列出明细数量 → 确认后行消失、出现「订单已删除」提示。
- 生产中/已完成订单行「删除」置灰，悬停显示「只能删除待生产状态的订单」。
- 点击删除按钮不会跳转到订单详情页。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/api/orders.js frontend/src/views/orders/OrderList.vue
git commit -m "feat(order-list): add delete button with cascade-aware confirm dialog

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review Notes

- **Spec coverage:** 范围/规则（仅待生产、硬删、级联+告知）→ Task 1 `delete_order` 状态校验与级联删除；数据流向 7 张表顺序 → Task 1 实现；后端两 service + 两 API → Task 1/2；前端列+按钮+禁用提示+弹窗列数量 → Task 3。全部覆盖。
- **Type consistency:** preview 返回键 `item_count`/`batch_count`/`link_count` 在 service、API 测试、前端 `confirmDelete` 三处一致。函数名 `delete_order`/`get_order_delete_preview` 全程一致。
- **No placeholders:** 所有步骤含完整代码与确切命令。
