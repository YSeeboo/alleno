# 订单条码标记（has_barcode） Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `Order` 增加独立布尔标记 `has_barcode`，在创建/详情可编辑，在列表与详情用蓝白 chip 展示。

**Architecture:** 单列 BOOLEAN（非空，默认 false）+ 增量 ALTER（沿用 `ensure_schema_compat`），与既有 `barcode_text` / `barcode_image` 完全解耦。复用现有 PATCH `/orders/{id}/extra-info` 端点保存。

**Tech Stack:** FastAPI / SQLAlchemy / Pydantic v2 / PostgreSQL / Vue 3 + Naive UI

---

## Spec 注解（与设计文档的小修正）

实际代码 `services/order.py::update_extra_info`（**不是 `update_order_extra_info`**）位于 `services/order.py:464-474`。其实现已经是动态的：

```python
for key, value in data.items():
    ...
    if hasattr(order, key):
        setattr(order, key, value)
```

只要 `has_barcode` 出现在 ORM model 和 `ExtraInfoUpdate` schema 中，**无需修改 service**。本计划据此调整。

---

## 文件清单

**后端（修改）:**
- `models/order.py` — 在 `Order` 类加 `has_barcode` 列
- `database.py` — 在 `ensure_schema_compat()` 中追加增量 ALTER
- `schemas/order.py` — 扩展 `OrderCreate` / `ExtraInfoUpdate` / `OrderResponse`
- `services/order.py` — `create_order` 函数签名加 `has_barcode`
- `api/orders.py` — `api_create_order` 透传 `has_barcode`

**后端（测试）:**
- `tests/test_db_compat.py` — 验证缺列自动补齐
- `tests/test_api_orders.py` — 创建路径用例（3）
- `tests/test_api_order_todo.py` — extra-info 路径用例（1）

**前端（修改）:**
- `frontend/src/views/orders/OrderCreate.vue` — 创建表单加 checkbox
- `frontend/src/views/orders/OrderList.vue` — 客户名列加 chip
- `frontend/src/views/orders/OrderDetail.vue` — 头部 chip + 附加信息区 checkbox

不修改：前端 `frontend/src/api/orders.js`（已是透传 wrapper，无需改动）；测试 fixture `tests/conftest.py`。

---

## Task 1: 数据模型 + 增量迁移

**Files:**
- Modify: `models/order.py:17-30`（`Order` 类）
- Modify: `database.py:251-271`（`ensure_schema_compat` 的 order 表分支）
- Test: `tests/test_db_compat.py`（新增一个用例）

- [ ] **Step 1: 写失败的迁移测试**

在 `tests/test_db_compat.py` 末尾追加：

```python
def test_ensure_schema_compat_adds_has_barcode_to_order(engine):
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE "order" DROP COLUMN IF EXISTS has_barcode'))

    ensure_schema_compat(engine)

    with engine.begin() as conn:
        cols = {c["name"]: c for c in inspect(conn).get_columns("order")}
        assert "has_barcode" in cols
        assert cols["has_barcode"]["nullable"] is False
        # Server default backfills false for existing rows; verify via PG catalog
        default = cols["has_barcode"].get("default")
        assert default is not None and "false" in str(default).lower()
```

- [ ] **Step 2: 跑测试验证它失败**

Run: `pytest tests/test_db_compat.py::test_ensure_schema_compat_adds_has_barcode_to_order -v`

Expected: FAIL — 列 `has_barcode` 在 model 里不存在，create_all 不会创建；ensure_schema_compat 也没补它。

- [ ] **Step 3: 给 Order model 添加 `has_barcode` 列**

`models/order.py` 在 import 段保证 `Boolean` 已导入；当前 import 行：

```python
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
```

改为（加 `Boolean`）：

```python
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
```

然后在 `Order` 类内 `note` 字段下方（约第 29-30 行之间）插入：

```python
    has_barcode = Column(Boolean, nullable=False, server_default="false", default=False)
```

完整的 `Order` 类应类似：

```python
class Order(Base):
    __tablename__ = "order"

    id = Column(String, primary_key=True)
    customer_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="待生产")
    total_amount = Column(Numeric(18, 7), nullable=True)
    packaging_cost = Column(Numeric(18, 7), nullable=True)
    barcode_text = Column(Text, nullable=True)
    barcode_image = Column(String, nullable=True)
    mark_text = Column(Text, nullable=True)
    mark_image = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    has_barcode = Column(Boolean, nullable=False, server_default="false", default=False)
    created_at = Column(DateTime, default=now_beijing)
```

- [ ] **Step 4: 在 `ensure_schema_compat` 中追加增量 ALTER**

在 `database.py` 的 "order extra info fields" 块（约第 257-271 行）**之后**插入新块（保持紧邻 order 表的其他迁移）：

```python
        # --- order.has_barcode (boolean flag, decoupled from barcode_text/image) ---
        if inspector.has_table("order"):
            cols = [c["name"] for c in inspector.get_columns("order")]
            if "has_barcode" not in cols:
                conn.execute(text(
                    'ALTER TABLE "order" ADD COLUMN has_barcode BOOLEAN NOT NULL DEFAULT false'
                ))
                logger.warning("Added missing order.has_barcode column")
```

- [ ] **Step 5: 跑测试验证它过**

Run: `pytest tests/test_db_compat.py::test_ensure_schema_compat_adds_has_barcode_to_order -v`

Expected: PASS

- [ ] **Step 6: 跑全部 db_compat 测试，确保没破坏现有迁移**

Run: `pytest tests/test_db_compat.py -v`

Expected: 所有用例 PASS。

- [ ] **Step 7: 提交**

```bash
git add models/order.py database.py tests/test_db_compat.py
git commit -m "$(cat <<'EOF'
feat(order): add has_barcode boolean column with auto migration

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Pydantic schemas

**Files:**
- Modify: `schemas/order.py:20-23` (`OrderCreate`)
- Modify: `schemas/order.py:47-60` (`OrderResponse`)
- Modify: `schemas/order.py:80-87` (`ExtraInfoUpdate`)

不写独立测试 — 通过 Task 3/4/5 的端到端 API 测试覆盖。

- [ ] **Step 1: 修改 `OrderCreate`**

`schemas/order.py` 中找到：

```python
class OrderCreate(BaseModel):
    customer_name: str
    items: List[OrderItemCreate]
    created_at: Optional[date] = None
```

改为：

```python
class OrderCreate(BaseModel):
    customer_name: str
    items: List[OrderItemCreate]
    created_at: Optional[date] = None
    has_barcode: bool = False
```

- [ ] **Step 2: 修改 `OrderResponse`**

找到：

```python
class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_name: str
    status: str
    total_amount: Optional[float] = None
    packaging_cost: Optional[float] = None
    barcode_text: Optional[str] = None
    barcode_image: Optional[str] = None
    mark_text: Optional[str] = None
    mark_image: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime
```

在 `note` 行之后插入 `has_barcode: bool = False`：

```python
class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_name: str
    status: str
    total_amount: Optional[float] = None
    packaging_cost: Optional[float] = None
    barcode_text: Optional[str] = None
    barcode_image: Optional[str] = None
    mark_text: Optional[str] = None
    mark_image: Optional[str] = None
    note: Optional[str] = None
    has_barcode: bool = False
    created_at: datetime
```

- [ ] **Step 3: 修改 `ExtraInfoUpdate`**

找到：

```python
class ExtraInfoUpdate(BaseModel):
    customer_name: Optional[str] = None
    barcode_text: Optional[str] = None
    barcode_image: Optional[str] = None
    mark_text: Optional[str] = None
    mark_image: Optional[str] = None
    note: Optional[str] = None
    created_at: Optional[date] = None
```

在 `note` 行之后插入 `has_barcode: Optional[bool] = None`：

```python
class ExtraInfoUpdate(BaseModel):
    customer_name: Optional[str] = None
    barcode_text: Optional[str] = None
    barcode_image: Optional[str] = None
    mark_text: Optional[str] = None
    mark_image: Optional[str] = None
    note: Optional[str] = None
    has_barcode: Optional[bool] = None
    created_at: Optional[date] = None
```

- [ ] **Step 4: 跑现有 schema 相关的 API 测试，确认没有副作用**

Run: `pytest tests/test_api_orders.py tests/test_api_order_todo.py -v -x`

Expected: 所有现有测试 PASS（schema 改动是纯追加可选字段，不会破坏现有调用）。

- [ ] **Step 5: 暂不提交**，下一任务一并提交（schema 与 service/API 强耦合）。

---

## Task 3: 创建订单接受 has_barcode

**Files:**
- Modify: `services/order.py:46-70`（`create_order` 函数）
- Modify: `api/orders.py:72-77`（`api_create_order`）
- Test: `tests/test_api_orders.py`（追加 3 用例）

- [ ] **Step 1: 写失败的测试 — 默认值**

在 `tests/test_api_orders.py` 末尾追加：

```python
def test_create_order_default_has_barcode_false(client, db):
    _, jewelry = _setup(db)
    resp = client.post("/api/orders/", json={
        "customer_name": "Alice",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 100.0}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["has_barcode"] is False


def test_create_order_with_has_barcode_true(client, db):
    _, jewelry = _setup(db)
    resp = client.post("/api/orders/", json={
        "customer_name": "Bob",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 100.0}],
        "has_barcode": True,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["has_barcode"] is True
    # Verify persisted by re-fetching
    fetched = client.get(f"/api/orders/{data['id']}").json()
    assert fetched["has_barcode"] is True


def test_create_order_with_has_barcode_false_explicit(client, db):
    _, jewelry = _setup(db)
    resp = client.post("/api/orders/", json={
        "customer_name": "Charlie",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 100.0}],
        "has_barcode": False,
    })
    assert resp.status_code == 201
    assert resp.json()["has_barcode"] is False
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/test_api_orders.py::test_create_order_default_has_barcode_false tests/test_api_orders.py::test_create_order_with_has_barcode_true tests/test_api_orders.py::test_create_order_with_has_barcode_false_explicit -v`

Expected: 三个用例都 FAIL（响应不含 `has_barcode` 字段；Task 2 的 schema 改动让响应包含字段但默认 False 会让 `has_barcode=true` 用例失败，因为 service 没接住）。

- [ ] **Step 3: 修改 `services/order.py::create_order`**

当前签名（`services/order.py:46`）：

```python
def create_order(db: Session, customer_name: str, items: list, created_at: Optional[date_type] = None) -> Order:
    order_id = _next_id(db, Order, "OR")
    total = Decimal(0)
    order = Order(id=order_id, customer_name=customer_name)
    if created_at is not None:
        order.created_at = _user_date_to_datetime(created_at)
    db.add(order)
```

改为：

```python
def create_order(
    db: Session,
    customer_name: str,
    items: list,
    created_at: Optional[date_type] = None,
    has_barcode: bool = False,
) -> Order:
    order_id = _next_id(db, Order, "OR")
    total = Decimal(0)
    order = Order(id=order_id, customer_name=customer_name, has_barcode=has_barcode)
    if created_at is not None:
        order.created_at = _user_date_to_datetime(created_at)
    db.add(order)
```

（函数其余部分不变。）

- [ ] **Step 4: 修改 `api/orders.py::api_create_order`**

当前（`api/orders.py:72-77`）：

```python
@router.post("/", response_model=OrderResponse, status_code=201)
def api_create_order(body: OrderCreate, db: Session = Depends(get_db)):
    items = [item.model_dump() for item in body.items]
    with service_errors():
        order = create_order(db, body.customer_name, items, created_at=body.created_at)
    return order
```

改为：

```python
@router.post("/", response_model=OrderResponse, status_code=201)
def api_create_order(body: OrderCreate, db: Session = Depends(get_db)):
    items = [item.model_dump() for item in body.items]
    with service_errors():
        order = create_order(
            db, body.customer_name, items,
            created_at=body.created_at,
            has_barcode=body.has_barcode,
        )
    return order
```

- [ ] **Step 5: 跑测试验证它过**

Run: `pytest tests/test_api_orders.py::test_create_order_default_has_barcode_false tests/test_api_orders.py::test_create_order_with_has_barcode_true tests/test_api_orders.py::test_create_order_with_has_barcode_false_explicit -v`

Expected: 三个全部 PASS。

- [ ] **Step 6: 跑完整 test_api_orders.py 确认没回归**

Run: `pytest tests/test_api_orders.py -v -x`

Expected: 全部 PASS。

- [ ] **Step 7: 提交**

```bash
git add schemas/order.py services/order.py api/orders.py tests/test_api_orders.py
git commit -m "$(cat <<'EOF'
feat(order): accept has_barcode at order creation

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: PATCH /extra-info 接受 has_barcode

`update_extra_info` 服务函数已经是动态的（`setattr` 任何 `hasattr(order, key)` 的字段），所以 Task 2 加了 schema 字段后，端到端已经能跑通。本任务只补测试以锁定行为。

**Files:**
- Test: `tests/test_api_order_todo.py`（追加 1 用例，紧跟现有 extra-info 测试组）

- [ ] **Step 1: 写测试**

在 `tests/test_api_order_todo.py` 末尾（约第 2098 行 `test_get_order_includes_extra_info` 之后）追加：

```python
def test_patch_extra_info_toggles_has_barcode_independently(client, db):
    """has_barcode is decoupled from barcode_text/image — toggling one
    must not touch the other."""
    order_id, *_ = _setup_order_with_bom(db, client)

    # Initial state: has_barcode=False (server default)
    resp = client.get(f"/api/orders/{order_id}")
    assert resp.json()["has_barcode"] is False

    # Set barcode_text and has_barcode together
    resp = client.patch(
        f"/api/orders/{order_id}/extra-info",
        json={"barcode_text": "EAN-13", "has_barcode": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["barcode_text"] == "EAN-13"
    assert data["has_barcode"] is True

    # Toggle has_barcode off — barcode_text MUST be unchanged
    resp = client.patch(
        f"/api/orders/{order_id}/extra-info",
        json={"has_barcode": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_barcode"] is False
    assert data["barcode_text"] == "EAN-13"  # not cleared

    # Toggle barcode_text — has_barcode must be unchanged
    resp = client.patch(
        f"/api/orders/{order_id}/extra-info",
        json={"barcode_text": "Code128"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["barcode_text"] == "Code128"
    assert data["has_barcode"] is False  # unchanged


def test_get_order_includes_has_barcode_field(client, db):
    """GET order response must include has_barcode field."""
    order_id, *_ = _setup_order_with_bom(db, client)
    resp = client.get(f"/api/orders/{order_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "has_barcode" in data
    assert data["has_barcode"] is False
```

- [ ] **Step 2: 跑测试**

Run: `pytest tests/test_api_order_todo.py::test_patch_extra_info_toggles_has_barcode_independently tests/test_api_order_todo.py::test_get_order_includes_has_barcode_field -v`

Expected: 两个用例都 PASS（schema 与 model 已就位，service 是动态 setter）。

- [ ] **Step 3: 跑完整 test_api_order_todo.py 确认没回归**

Run: `pytest tests/test_api_order_todo.py -v -x`

Expected: 全部 PASS。

- [ ] **Step 4: 提交**

```bash
git add tests/test_api_order_todo.py
git commit -m "$(cat <<'EOF'
test(order): lock has_barcode independence from barcode_text via extra-info

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 后端整体回归

- [ ] **Step 1: 跑全量后端测试**

Run: `pytest -v`

Expected: 全部 PASS。如果有不相关的偶发失败（如远程数据库问题），单独定位；如果失败与本次改动有关，回到对应 Task 修复。

- [ ] **Step 2: 启动开发服务器验证启动迁移生效**

Run: `python main.py`

Expected: 日志中如果旧 DB 没有 `has_barcode` 列，会看到 `WARNING: Added missing order.has_barcode column`；如果已有，则静默。

按 `Ctrl-C` 退出。

- [ ] **Step 3: 用 curl 手测一次完整链路（可选但推荐）**

```bash
# 创建一个带 has_barcode=true 的订单（假设饰品 SP-0001 已存在）
curl -s -X POST http://localhost:8000/api/orders/ \
  -H 'Content-Type: application/json' \
  -d '{"customer_name":"测试客户","items":[{"jewelry_id":"SP-0001","quantity":1,"unit_price":100}],"has_barcode":true}' | jq '.has_barcode'
```

Expected: `true`

---

## Task 6: 前端 — OrderCreate.vue 加 checkbox

**Files:**
- Modify: `frontend/src/views/orders/OrderCreate.vue:1-184`

- [ ] **Step 1: 添加 NCheckbox 到 import 列表**

找到第 98 行：

```js
import { NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem, NCard, NText, NH2, NDatePicker } from 'naive-ui'
```

改为：

```js
import { NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem, NCard, NText, NH2, NDatePicker, NCheckbox } from 'naive-ui'
```

- [ ] **Step 2: 添加 reactive 变量**

找到第 110-114 行：

```js
const customerName = ref('')
const createdAtTs = ref(null)
const jewelryItems = reactive([])
const partItems = reactive([])
const submitting = ref(false)
```

在 `createdAtTs` 之后插入 `hasBarcode`：

```js
const customerName = ref('')
const createdAtTs = ref(null)
const hasBarcode = ref(false)
const jewelryItems = reactive([])
const partItems = reactive([])
const submitting = ref(false)
```

- [ ] **Step 3: 在模板中加 checkbox 行**

找到模板中"创建时间"的 form-item（第 12-20 行）：

```vue
      <n-form-item label="创建时间">
        <n-date-picker
          v-model:value="createdAtTs"
          type="date"
          clearable
          placeholder="不填则使用当前时间"
          :style="{ width: isMobile ? '100%' : '300px' }"
        />
      </n-form-item>
```

在其**正下方**（仍在 `<n-form>` 内）追加：

```vue
      <n-form-item label=" ">
        <n-checkbox v-model:checked="hasBarcode">需要贴条码</n-checkbox>
      </n-form-item>
```

> 注意：`label=" "`（一个空格）保留对齐缩进；`label=""` 会让 Naive UI 完全省略 label gutter，与上方两行错位。

- [ ] **Step 4: 把 has_barcode 加入提交 payload**

找到 `submit()` 函数中第 159-161 行：

```js
    const payload = { customer_name: customerName.value, items }
    const createdAt = tsToDateStr(createdAtTs.value)
    if (createdAt) payload.created_at = createdAt
```

改为：

```js
    const payload = { customer_name: customerName.value, items, has_barcode: hasBarcode.value }
    const createdAt = tsToDateStr(createdAtTs.value)
    if (createdAt) payload.created_at = createdAt
```

- [ ] **Step 5: 启动前端并在浏览器中手测**

```bash
cd frontend && npm run dev
```

打开 http://localhost:5173/orders/create

验证：
1. "创建时间"下方出现一行 `[☐] 需要贴条码`，默认未勾
2. 不勾，填入客户名 + 任一饰品，点"提交订单" → 创建成功，跳转详情页
3. 用 DevTools 检查请求 Payload，`has_barcode: false`
4. 重复一次但勾上 checkbox → 请求 Payload `has_barcode: true`

按 `Ctrl-C` 退出 dev server。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/orders/OrderCreate.vue
git commit -m "$(cat <<'EOF'
feat(order-create): add 需要贴条码 checkbox below 创建时间

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: 前端 — OrderList.vue 客户名列加 chip

**Files:**
- Modify: `frontend/src/views/orders/OrderList.vue:31`（import）
- Modify: `frontend/src/views/orders/OrderList.vue:74-103`（columns）

- [ ] **Step 1: 添加 NTag 到 import**

找到第 31 行：

```js
import { NButton, NSelect, NDataTable, NSpin, NEmpty } from 'naive-ui'
```

改为：

```js
import { NButton, NSelect, NDataTable, NSpin, NEmpty, NTag } from 'naive-ui'
```

- [ ] **Step 2: 改造客户名列**

找到第 76 行：

```js
  { title: '客户名', key: 'customer_name' },
```

改为：

```js
  {
    title: '客户名',
    key: 'customer_name',
    render: (r) => {
      if (!r.has_barcode) return r.customer_name
      return h('span', null, [
        r.customer_name,
        h(
          NTag,
          {
            size: 'small',
            bordered: false,
            color: { color: '#00A0E9', textColor: '#fff' },
            style: 'margin-left: 8px; font-weight: 600; letter-spacing: 0.5px;',
          },
          { default: () => '有条码' }
        ),
      ])
    },
  },
```

- [ ] **Step 3: 浏览器手测**

```bash
cd frontend && npm run dev
```

打开 http://localhost:5173/orders

验证：
1. 有 `has_barcode=true` 的订单：客户名右侧出现宝矿力蓝白 `有条码` chip
2. `has_barcode=false` 的订单：客户名后无 chip
3. chip 不撑宽客户名列，整体布局保持不变
4. 点行能正常跳转详情页（rowProps 仍生效）

按 `Ctrl-C` 退出。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/orders/OrderList.vue
git commit -m "$(cat <<'EOF'
feat(order-list): show 有条码 chip after customer_name

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: 前端 — OrderDetail.vue 头部 chip + 附加信息区 checkbox

**Files:**
- Modify: `frontend/src/views/orders/OrderDetail.vue`（多处）

- [ ] **Step 1: 先确认导入**

打开文件，搜索 `from 'naive-ui'` 的 import 行。需要确认 `NTag`、`NCheckbox` 都在列表里。如不在，加进去。NTag 大概率已存在（详情页用了状态 tag）。NCheckbox 新增。

如果当前 import 类似：

```js
import { ..., NTag, ... } from 'naive-ui'
```

则改为加入 `NCheckbox`：

```js
import { ..., NTag, NCheckbox, ... } from 'naive-ui'
```

- [ ] **Step 2: 在客户名旁加 chip（头部）**

找到第 13-27 行 "客户名" 的 `n-descriptions-item`：

```vue
          <n-descriptions-item label="客户名">
            <template v-if="editingCustomerName">
              <n-space align="center" size="small">
                <n-input v-model:value="editingCustomerNameVal" size="small" :style="{ width: isMobile ? '100%' : '160px' }" />
                <n-button size="small" type="primary" :loading="savingCustomerName" @click="saveCustomerName">确认</n-button>
                <n-button size="small" :disabled="savingCustomerName" @click="editingCustomerName = false">取消</n-button>
              </n-space>
            </template>
            <template v-else>
              {{ order?.customer_name }}
              <n-button text type="primary" size="small" style="margin-left: 6px;" @click="startEditCustomerName">
                <template #icon><n-icon :component="CreateOutline" /></template>
              </n-button>
            </template>
          </n-descriptions-item>
```

把非编辑分支中的客户名后插入 chip：

```vue
          <n-descriptions-item label="客户名">
            <template v-if="editingCustomerName">
              <n-space align="center" size="small">
                <n-input v-model:value="editingCustomerNameVal" size="small" :style="{ width: isMobile ? '100%' : '160px' }" />
                <n-button size="small" type="primary" :loading="savingCustomerName" @click="saveCustomerName">确认</n-button>
                <n-button size="small" :disabled="savingCustomerName" @click="editingCustomerName = false">取消</n-button>
              </n-space>
            </template>
            <template v-else>
              {{ order?.customer_name }}
              <n-tag
                v-if="order?.has_barcode"
                size="small"
                :bordered="false"
                :color="{ color: '#00A0E9', textColor: '#fff' }"
                style="margin-left: 8px; font-weight: 600; letter-spacing: 0.5px;"
              >有条码</n-tag>
              <n-button text type="primary" size="small" style="margin-left: 6px;" @click="startEditCustomerName">
                <template #icon><n-icon :component="CreateOutline" /></template>
              </n-button>
            </template>
          </n-descriptions-item>
```

- [ ] **Step 3: 把 `has_barcode` 加入 extraInfo reactive**

找到第 750-756 行：

```js
const extraInfo = ref({
  barcode_text: '',
  barcode_image: null,
  mark_text: '',
  mark_image: null,
  note: '',
})
```

改为：

```js
const extraInfo = ref({
  has_barcode: false,
  barcode_text: '',
  barcode_image: null,
  mark_text: '',
  mark_image: null,
  note: '',
})
```

- [ ] **Step 4: 在 `initExtraInfo` 同步字段**

找到第 761-769 行：

```js
function initExtraInfo(o) {
  extraInfo.value = {
    barcode_text: o.barcode_text || '',
    barcode_image: o.barcode_image || null,
    mark_text: o.mark_text || '',
    mark_image: o.mark_image || null,
    note: o.note || '',
  }
}
```

改为：

```js
function initExtraInfo(o) {
  extraInfo.value = {
    has_barcode: !!o.has_barcode,
    barcode_text: o.barcode_text || '',
    barcode_image: o.barcode_image || null,
    mark_text: o.mark_text || '',
    mark_image: o.mark_image || null,
    note: o.note || '',
  }
}
```

- [ ] **Step 5: 在附加信息区"条码要求"块上方加 checkbox 行**

找到第 69-92 行的 "条码要求" 块：

```vue
            <!-- 条码要求 -->
            <div style="margin-bottom: 20px;">
              <div style="font-weight: 500; margin-bottom: 8px;">条码要求</div>
              <div style="display: flex; gap: 16px;">
                <n-input ...
```

在 `<!-- 条码要求 -->` 注释**上方**插入新块：

```vue
            <!-- 是否有条码 -->
            <div style="margin-bottom: 16px;">
              <n-checkbox v-model:checked="extraInfo.has_barcode">需要贴条码</n-checkbox>
            </div>

            <!-- 条码要求 -->
```

> 复用 extraInfo reactive 对象意味着「保存附加信息」按钮一并提交 has_barcode；无需新增按钮或处理函数。`saveExtraInfo()` 已经 `await updateExtraInfo(order.value.id, extraInfo.value)`，Task 2 让后端 `ExtraInfoUpdate` schema 接受 `has_barcode`，端到端打通。

- [ ] **Step 6: 浏览器手测**

```bash
cd frontend && npm run dev
```

打开 http://localhost:5173/orders/{某个订单的 id}

验证：
1. 如果该订单 `has_barcode=true` → 头部客户名右侧出现宝矿力蓝白 chip
2. 展开"附加信息"折叠面板 → 第一行就是 `[✓] 需要贴条码` 勾选框
3. 取消勾选 → 点保存 → 刷新页面 → chip 消失，勾选框为未勾选
4. 重新勾上 → 点保存 → 刷新 → chip 重新出现
5. 切换 has_barcode 时，barcode_text 和 barcode_image 完全不变（不被联动清空）

按 `Ctrl-C` 退出。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/views/orders/OrderDetail.vue
git commit -m "$(cat <<'EOF'
feat(order-detail): show 有条码 chip in header + edit toggle in extra-info

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: 端到端冒烟

- [ ] **Step 1: 启动后端 + 前端**

终端 A：`python main.py`
终端 B：`cd frontend && npm run dev`

- [ ] **Step 2: 完整路径手测**

1. 打开 http://localhost:5173/orders/create
2. 填客户名 "测试-有条码"，勾选"需要贴条码"，添加一个饰品 → 提交
3. 跳转到详情页 → 验证头部出现蓝白 `有条码` chip
4. 展开"附加信息" → 验证勾选框是选中状态
5. 返回订单列表 → 该订单客户名后出现 chip
6. 再创建一单 "测试-无条码"，不勾选 → 详情头部无 chip，列表无 chip
7. 进入 "测试-有条码" 的详情页 → 取消勾选 → 保存 → 刷新页面：列表无 chip，详情无 chip
8. 重新勾上 → 保存 → 列表和详情都恢复 chip

- [ ] **Step 3: 跑全量后端测试做最终 sanity check**

Run: `pytest -v`

Expected: 全部 PASS。

- [ ] **Step 4: 总结性提交（如有零散改动）**

如果上面 Task 6/7/8 已经各自提交且无遗漏，跳过此步。如果在手测过程中发现并修复了小问题，单独 commit：

```bash
git status
git diff
# 按需 add + commit
```

---

## 完成判据

- ✅ `pytest` 全部通过
- ✅ 新建订单可勾选"需要贴条码"
- ✅ 订单列表 / 详情页头部，`has_barcode=true` 的订单显示宝矿力蓝白 `有条码` chip
- ✅ 详情页附加信息区可独立切换 has_barcode，与 barcode_text/image 互不影响
- ✅ 启动后端时旧 DB 自动加列，老订单 has_barcode 全为 false
- ✅ 8 个 commit（5 后端 + 3 前端，或按 task 数）
