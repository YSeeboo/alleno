# 货物分拣 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让分拣员通过回执编号或商家筛选，在移动端查看手工单的客户分拣信息（每个饰品要发给哪些客户、各多少件）。

**Architecture:** 后端复用现有 `get_handcraft_jewelry_breakdown` 的形状，新加 3 个服务函数 + 2 个 API 端点，引入 `sorting` 权限位。前端新增 `/cargo-sorting` 路由（移动端为主），3 个 Vue 组件（主页、卡片、底部抽屉），sticky 头部 + 顶部互斥的搜索/商家筛选。

**Tech Stack:** FastAPI + SQLAlchemy（后端）；Vue 3 + Naive UI + Pinia（前端）；pytest（测试）。

**关键设计前提（来自 spec + 探索）：**
- 手工单的客户名解析现有规则：行的 `customer_name` 非空覆盖 `OrderItemLink → Order.customer_name`
- 一个手工单出现在分拣页的条件：至少存在一行客户名能解析为非空
- 现有 handcraft 端点**没有任何**后端权限检查（仅前端路由守卫），所以 `by-receipt-code` 端点也是开放的。新加 `sorting` 权限位后，需要让 `by-receipt-code` 兼容**已有调用者**（`HandcraftList.vue` 也调它）——通过新加 `require_any_permission` 辅助允许 `handcraft OR sorting`
- 数据规模：每商家最多 15 单，超出加「加载更多」

---

## File Structure

**Create:**
- `tests/test_handcraft_sorting.py` — service-layer tests for 3 new functions + 修改后的 breakdown
- `tests/test_api_handcraft_sorting.py` — API + permission tests
- `frontend/src/api/cargoSorting.js` — API 客户端方法
- `frontend/src/components/icons/SortingIcon.vue` — 侧边栏图标组件
- `frontend/src/views/cargo-sorting/CargoSorting.vue` — 主页面
- `frontend/src/views/cargo-sorting/SortingCard.vue` — 单订单卡片
- `frontend/src/views/cargo-sorting/SupplierSheet.vue` — 商家底部抽屉

**Modify:**
- `services/handcraft.py` — 扩展 `get_handcraft_jewelry_breakdown` + 加 3 个新函数
- `api/deps.py` — 加 `require_any_permission` helper
- `api/handcraft.py` — 加 2 个新端点 + 给 `by-receipt-code` 加复合权限
- `frontend/src/router/index.js` — 注册路由 + 权限映射
- `frontend/src/layouts/DefaultLayout.vue` — 「手工单」分组加菜单项
- `frontend/src/views/users/UserList.vue` — 加 `sorting` 权限选项

---

## Task 1: 扩展 `get_handcraft_jewelry_breakdown` 加 `only_with_customer` 参数

**Files:**
- Modify: `services/handcraft.py:421-531`
- Test: `tests/test_handcraft_sorting.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `tests/test_handcraft_sorting.py`：

```python
"""Service-layer tests for cargo-sorting features."""
from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock
from services.handcraft import (
    create_handcraft_order,
    get_handcraft_jewelry_breakdown,
)


def _setup_jewelry(db, name="J1"):
    part = create_part(db, {"name": "P1", "category": "小配件", "color": "古铜"})
    add_stock(db, "part", part.id, 100.0, "init")
    jewelry = create_jewelry(db, {"name": name, "category": "单件"})
    return part, jewelry


def test_breakdown_only_with_customer_filters_anonymous_entries(db):
    """only_with_customer=True 跳过无客户的 entry 和无 entry 的 group。"""
    part, j_with = _setup_jewelry(db, "withCust")
    _, j_without = _setup_jewelry(db, "noCust")

    order = create_handcraft_order(
        db,
        supplier_name="S1",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[
            {"jewelry_id": j_with.id, "qty": 1, "customer_name": "王小姐"},
            {"jewelry_id": j_without.id, "qty": 1},  # no customer
        ],
    )

    full = get_handcraft_jewelry_breakdown(db, order.id)
    assert len(full) == 2

    filtered = get_handcraft_jewelry_breakdown(db, order.id, only_with_customer=True)
    assert len(filtered) == 1
    assert filtered[0]["jewelry_id"] == j_with.id
    assert all(e["customer_name"] is not None for e in filtered[0]["entries"])


def test_breakdown_only_with_customer_treats_empty_string_as_none(db):
    """customer_name 为空串或空白时，等同于 None。"""
    part, jewelry = _setup_jewelry(db)
    order = create_handcraft_order(
        db,
        supplier_name="S1",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[
            {"jewelry_id": jewelry.id, "qty": 1, "customer_name": ""},
            {"jewelry_id": jewelry.id, "qty": 1, "customer_name": "   "},
            {"jewelry_id": jewelry.id, "qty": 1, "customer_name": "张小姐"},
        ],
    )

    filtered = get_handcraft_jewelry_breakdown(db, order.id, only_with_customer=True)
    assert len(filtered) == 1
    assert len(filtered[0]["entries"]) == 1
    assert filtered[0]["entries"][0]["customer_name"] == "张小姐"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_handcraft_sorting.py -v
```

Expected: 2 个 FAIL，原因是 `get_handcraft_jewelry_breakdown` 不接受 `only_with_customer` 参数

- [ ] **Step 3: 修改 service 函数**

在 `services/handcraft.py` 修改函数签名和实现。**完整替换** `def get_handcraft_jewelry_breakdown` 函数的签名行与 body 末尾的 entry 构造段：

签名改为：

```python
def get_handcraft_jewelry_breakdown(
    db: Session, hc_id: str, only_with_customer: bool = False
) -> list[dict]:
```

在 entry 构造完成后，加入过滤。找到现有这段（约第 504-512 行）：

```python
            entries.append({
                "hc_jewelry_item_id": r.id,
                ...
                "is_locked": source == "order",
            })
```

在 `entries.append(...)` 后**保持原样**。然后在 `# Group-level aggregate status` 之前插入：

```python
        if only_with_customer:
            entries = [
                e for e in entries
                if e["customer_name"] and e["customer_name"].strip()
            ]
            if not entries:
                continue
```

注意 `continue` 跳过整个组，所以无 entry 的 group 就不会进 `result`。

- [ ] **Step 4: 运行测试确认通过**

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_handcraft_sorting.py -v
```

Expected: 2 个 PASS。同时跑回归：

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_handcraft_breakdown.py tests/test_api_handcraft.py -v
```

Expected: 所有原有测试仍 PASS（参数默认值 = False 保留原有行为）

- [ ] **Step 5: Commit**

```bash
git add services/handcraft.py tests/test_handcraft_sorting.py
git commit -m "feat(handcraft): breakdown supports only_with_customer filter"
```

---

## Task 2: 加 `_has_sorting_info` 私有谓词

**Files:**
- Modify: `services/handcraft.py`（在 `get_handcraft_jewelry_breakdown` 后追加）
- Test: `tests/test_handcraft_sorting.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_handcraft_sorting.py` 追加：

```python
from services.handcraft import _has_sorting_info


def test_has_sorting_info_true_when_any_row_has_customer(db):
    part, jewelry = _setup_jewelry(db)
    order = create_handcraft_order(
        db,
        supplier_name="S1",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[
            {"jewelry_id": jewelry.id, "qty": 1},
            {"jewelry_id": jewelry.id, "qty": 1, "customer_name": "李太"},
        ],
    )
    assert _has_sorting_info(db, order.id) is True


def test_has_sorting_info_false_when_no_customer(db):
    part, jewelry = _setup_jewelry(db)
    order = create_handcraft_order(
        db,
        supplier_name="S1",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1}],
    )
    assert _has_sorting_info(db, order.id) is False


def test_has_sorting_info_ignores_blank_customer_name(db):
    part, jewelry = _setup_jewelry(db)
    order = create_handcraft_order(
        db,
        supplier_name="S1",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1, "customer_name": "  "}],
    )
    assert _has_sorting_info(db, order.id) is False
```

- [ ] **Step 2: 运行测试确认失败**

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_handcraft_sorting.py -k has_sorting_info -v
```

Expected: 3 FAIL，原因 `_has_sorting_info` 未定义

- [ ] **Step 3: 实现函数**

在 `services/handcraft.py` 的 `get_handcraft_jewelry_breakdown` 函数之后追加：

```python
def _has_sorting_info(db: Session, hc_id: str) -> bool:
    """True iff at least one HandcraftJewelryItem in the order has a resolvable
    non-empty customer name (either manual customer_name or via OrderItemLink)."""
    # 复用 breakdown 的解析逻辑，避免重复实现。性能足够：单订单查询。
    groups = get_handcraft_jewelry_breakdown(db, hc_id, only_with_customer=True)
    return len(groups) > 0
```

- [ ] **Step 4: 运行测试确认通过**

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_handcraft_sorting.py -k has_sorting_info -v
```

Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add services/handcraft.py tests/test_handcraft_sorting.py
git commit -m "feat(handcraft): add _has_sorting_info predicate"
```

---

## Task 3: 加 `list_suppliers_with_sorting`

**Files:**
- Modify: `services/handcraft.py`
- Test: `tests/test_handcraft_sorting.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_handcraft_sorting.py`：

```python
from services.handcraft import list_suppliers_with_sorting


def test_list_suppliers_with_sorting_returns_only_qualifying_suppliers(db):
    part, jewelry = _setup_jewelry(db)
    # Supplier A: 有分拣信息
    create_handcraft_order(
        db, supplier_name="商家A",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1, "customer_name": "C1"}],
    )
    # Supplier B: 无分拣信息
    create_handcraft_order(
        db, supplier_name="商家B",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1}],
    )
    # Supplier A 再来一单（验证去重）
    create_handcraft_order(
        db, supplier_name="商家A",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 2, "customer_name": "C2"}],
    )

    suppliers = list_suppliers_with_sorting(db)
    assert suppliers == ["商家A"]


def test_list_suppliers_with_sorting_empty_when_no_orders(db):
    assert list_suppliers_with_sorting(db) == []
```

- [ ] **Step 2: 运行测试确认失败**

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_handcraft_sorting.py -k list_suppliers_with_sorting -v
```

Expected: FAIL，函数未定义

- [ ] **Step 3: 实现函数**

在 `services/handcraft.py` 追加（`_has_sorting_info` 之后）：

```python
def list_suppliers_with_sorting(db: Session) -> list[str]:
    """Return distinct supplier_name list for handcraft orders that have at least
    one resolvable customer entry. Sorted ascending for stable UI."""
    candidates = (
        db.query(HandcraftOrder.id, HandcraftOrder.supplier_name)
        .order_by(HandcraftOrder.supplier_name.asc())
        .all()
    )
    seen: set[str] = set()
    out: list[str] = []
    for hc_id, name in candidates:
        if name in seen:
            continue
        if _has_sorting_info(db, hc_id):
            seen.add(name)
            out.append(name)
    return out
```

- [ ] **Step 4: 运行测试确认通过**

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_handcraft_sorting.py -k list_suppliers_with_sorting -v
```

Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add services/handcraft.py tests/test_handcraft_sorting.py
git commit -m "feat(handcraft): add list_suppliers_with_sorting"
```

---

## Task 4: 加 `list_handcraft_orders_with_sorting`

**Files:**
- Modify: `services/handcraft.py`
- Test: `tests/test_handcraft_sorting.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_handcraft_sorting.py`：

```python
from services.handcraft import list_handcraft_orders_with_sorting


def test_list_orders_returns_filtered_breakdowns(db):
    part, jewelry = _setup_jewelry(db)
    o = create_handcraft_order(
        db, supplier_name="商家A",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[
            {"jewelry_id": jewelry.id, "qty": 1, "customer_name": "王"},
            {"jewelry_id": jewelry.id, "qty": 1},  # filtered out
        ],
    )

    result = list_handcraft_orders_with_sorting(db, supplier_name="商家A")
    assert result["has_more"] is False
    assert len(result["orders"]) == 1
    order_view = result["orders"][0]
    assert order_view["id"] == o.id
    assert order_view["supplier_name"] == "商家A"
    assert order_view["receipt_code"] == o.receipt_code
    assert order_view["status"] == "pending"
    # breakdown is embedded, anonymous entries filtered out
    assert len(order_view["breakdown"]) == 1
    assert len(order_view["breakdown"][0]["entries"]) == 1


def test_list_orders_excludes_orders_without_sorting_info(db):
    part, jewelry = _setup_jewelry(db)
    create_handcraft_order(
        db, supplier_name="商家A",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1}],  # no customer
    )
    result = list_handcraft_orders_with_sorting(db, supplier_name="商家A")
    assert result == {"orders": [], "has_more": False}


def test_list_orders_pagination_has_more(db):
    """16 个订单，limit=15 → has_more=True；offset=15 → 1 单，has_more=False。"""
    part, jewelry = _setup_jewelry(db)
    for i in range(16):
        create_handcraft_order(
            db, supplier_name="商家A",
            parts=[{"part_id": part.id, "qty": 5}],
            jewelries=[{"jewelry_id": jewelry.id, "qty": 1, "customer_name": f"C{i}"}],
        )

    page1 = list_handcraft_orders_with_sorting(db, supplier_name="商家A", limit=15, offset=0)
    assert len(page1["orders"]) == 15
    assert page1["has_more"] is True

    page2 = list_handcraft_orders_with_sorting(db, supplier_name="商家A", limit=15, offset=15)
    assert len(page2["orders"]) == 1
    assert page2["has_more"] is False


def test_list_orders_exact_15_no_has_more(db):
    """边界：恰好 15 单时 has_more=False。"""
    part, jewelry = _setup_jewelry(db)
    for i in range(15):
        create_handcraft_order(
            db, supplier_name="商家A",
            parts=[{"part_id": part.id, "qty": 5}],
            jewelries=[{"jewelry_id": jewelry.id, "qty": 1, "customer_name": f"C{i}"}],
        )

    result = list_handcraft_orders_with_sorting(db, supplier_name="商家A", limit=15, offset=0)
    assert len(result["orders"]) == 15
    assert result["has_more"] is False


def test_list_orders_unknown_supplier_returns_empty(db):
    result = list_handcraft_orders_with_sorting(db, supplier_name="不存在")
    assert result == {"orders": [], "has_more": False}
```

- [ ] **Step 2: 运行测试确认失败**

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_handcraft_sorting.py -k list_orders -v
```

Expected: 5 FAIL，函数未定义

- [ ] **Step 3: 实现函数**

在 `services/handcraft.py` 追加：

```python
def list_handcraft_orders_with_sorting(
    db: Session,
    supplier_name: str,
    limit: int = 15,
    offset: int = 0,
) -> dict:
    """Return handcraft orders for the supplier that have resolvable customer
    sorting info. Embeds the customer-filtered breakdown.

    Returns:
        {"orders": [{id, supplier_name, receipt_code, status, created_at, breakdown}, ...],
         "has_more": bool}
    """
    # 取该商家全部订单（按创建时间倒序），过滤掉无分拣信息的
    candidates = (
        db.query(HandcraftOrder)
        .filter(HandcraftOrder.supplier_name == supplier_name)
        .order_by(HandcraftOrder.created_at.desc(), HandcraftOrder.id.desc())
        .all()
    )
    qualifying = [o for o in candidates if _has_sorting_info(db, o.id)]

    page = qualifying[offset : offset + limit]
    has_more = len(qualifying) > offset + limit

    orders_out = []
    for o in page:
        orders_out.append({
            "id": o.id,
            "supplier_name": o.supplier_name,
            "receipt_code": o.receipt_code,
            "status": o.status,
            "created_at": o.created_at,
            "breakdown": get_handcraft_jewelry_breakdown(db, o.id, only_with_customer=True),
        })
    return {"orders": orders_out, "has_more": has_more}
```

性能说明：每订单会触发 1 次 breakdown 查询。15 单上限够小，不优化。

- [ ] **Step 4: 运行测试确认通过**

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_handcraft_sorting.py -v
```

Expected: 全部 PASS（13 个测试）

- [ ] **Step 5: Commit**

```bash
git add services/handcraft.py tests/test_handcraft_sorting.py
git commit -m "feat(handcraft): add list_handcraft_orders_with_sorting"
```

---

## Task 5: 加 `require_any_permission` helper

**Files:**
- Modify: `api/deps.py`
- Test: `tests/test_api_handcraft_sorting.py`（新建，先准备 fixture，后续 task 复用）

- [ ] **Step 1: 写失败测试**

新建 `tests/test_api_handcraft_sorting.py`：

```python
"""API + permission tests for cargo-sorting endpoints."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from main import app
from database import Base, get_db
from api.deps import get_current_user
from models.user import User
from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock
from services.handcraft import create_handcraft_order
from time_utils import now_beijing


def _user(perms: list[str], is_admin: bool = False) -> User:
    return User(
        id=99, username="u", password_hash="", owner="t",
        permissions=perms, is_admin=is_admin, is_active=True,
        created_at=now_beijing(),
    )


@pytest.fixture
def client_with_perms(db):
    """Returns a function: (perms_list, is_admin=False) -> TestClient."""
    def _factory(perms, is_admin=False):
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: _user(perms, is_admin)
        return TestClient(app)
    yield _factory
    app.dependency_overrides.clear()


def test_require_any_permission_allows_when_user_has_one(client_with_perms):
    """直接测一个简单端点：require_any_permission('a', 'b') 允许有 a 或 b 的用户。"""
    from fastapi import APIRouter
    from api.deps import require_any_permission

    router = APIRouter()

    @router.get("/_test_any_perm", dependencies=[require_any_permission("foo", "bar")])
    def _h():
        return {"ok": True}

    app.include_router(router)
    try:
        c = client_with_perms(["bar"])
        assert c.get("/_test_any_perm").status_code == 200

        c = client_with_perms(["foo"])
        assert c.get("/_test_any_perm").status_code == 200

        c = client_with_perms(["baz"])
        assert c.get("/_test_any_perm").status_code == 403

        c = client_with_perms([], is_admin=True)
        assert c.get("/_test_any_perm").status_code == 200
    finally:
        # remove the test route to keep app clean
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/_test_any_perm"]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_api_handcraft_sorting.py -v
```

Expected: FAIL（`require_any_permission` 未定义）

- [ ] **Step 3: 实现 helper**

在 `api/deps.py` 文件末尾追加：

```python
def require_any_permission(*perm_keys: str):
    """Allow access if user has ANY of the given permissions (or is admin).
    Use for endpoints that serve multiple roles."""
    def dependency(current_user: User = Depends(get_current_user)):
        if current_user.is_admin:
            return current_user
        perms = set(current_user.permissions or [])
        for old, new in _PERM_ALIASES.items():
            if old in perms:
                perms.add(new)
        if not any(k in perms for k in perm_keys):
            joined = " 或 ".join(perm_keys)
            raise HTTPException(status_code=403, detail=f"无 {joined} 权限")
        return current_user

    return Depends(dependency)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_api_handcraft_sorting.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/deps.py tests/test_api_handcraft_sorting.py
git commit -m "feat(api): add require_any_permission helper"
```

---

## Task 6: 加 schema + `GET /handcraft/suppliers-with-sorting` 端点

**Files:**
- Modify: `schemas/handcraft.py`（追加 response schemas）
- Modify: `api/handcraft.py`（追加端点）
- Test: `tests/test_api_handcraft_sorting.py`

- [ ] **Step 1: 加 response schemas**

在 `schemas/handcraft.py` 文件末尾追加：

```python
class CargoSortingSuppliersResponse(BaseModel):
    suppliers: List[str]


class CargoSortingOrderView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    supplier_name: str
    receipt_code: Optional[str] = None
    status: str
    created_at: datetime
    breakdown: List[HandcraftJewelryBreakdownGroup]


class CargoSortingListResponse(BaseModel):
    orders: List[CargoSortingOrderView]
    has_more: bool
```

如果 `datetime` 未 import，在文件顶部 imports 处加 `from datetime import datetime`（检查是否已存在）。

- [ ] **Step 2: 写失败测试**

追加到 `tests/test_api_handcraft_sorting.py`：

```python
def _setup_part_and_jewelry(db):
    part = create_part(db, {"name": "P1", "category": "小配件", "color": "古铜"})
    add_stock(db, "part", part.id, 100.0, "init")
    jewelry = create_jewelry(db, {"name": "J1", "category": "单件"})
    return part, jewelry


def test_suppliers_with_sorting_returns_filtered_list(client_with_perms, db):
    part, jewelry = _setup_part_and_jewelry(db)
    create_handcraft_order(
        db, supplier_name="商家A",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1, "customer_name": "王"}],
    )
    create_handcraft_order(
        db, supplier_name="商家B",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1}],
    )

    c = client_with_perms(["sorting"])
    resp = c.get("/api/handcraft/suppliers-with-sorting")
    assert resp.status_code == 200
    assert resp.json() == {"suppliers": ["商家A"]}


def test_suppliers_with_sorting_requires_sorting_permission(client_with_perms, db):
    c = client_with_perms(["handcraft"])  # has handcraft but not sorting
    resp = c.get("/api/handcraft/suppliers-with-sorting")
    assert resp.status_code == 403
```

- [ ] **Step 3: 运行测试确认失败**

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_api_handcraft_sorting.py -k suppliers_with_sorting -v
```

Expected: FAIL（端点 404）

- [ ] **Step 4: 实现端点**

(a) 在 `api/handcraft.py` 文件顶部 imports 处追加（位置：紧跟 `from api._errors import service_errors` 后）：

```python
from api.deps import require_permission
```

(b) 找到现有 `from services.handcraft import (` 块，在排序好的导入列表里加入两个新名（保持字母序）：

```python
    list_handcraft_orders_with_sorting,
    list_suppliers_with_sorting,
```

(c) 找到现有 `from schemas.handcraft import (` 块，在导入列表中加入：

```python
    CargoSortingListResponse,
    CargoSortingSuppliersResponse,
```

(d) 在 `api/handcraft.py` 找到 `@router.get("/by-receipt-code/{code}", ...)` 行（约第 158 行），**在它之前**插入新端点：

```python
@router.get(
    "/suppliers-with-sorting",
    response_model=CargoSortingSuppliersResponse,
    dependencies=[require_permission("sorting")],
)
def api_list_suppliers_with_sorting(db: Session = Depends(get_db)):
    return {"suppliers": list_suppliers_with_sorting(db)}
```

注意路径位置：FastAPI 按声明顺序匹配 path，所以 `/suppliers-with-sorting` 必须放在 `/by-receipt-code/{code}` 和 `/{order_id}` 之前，否则会被当成 `{code}` 或 `{order_id}` 参数匹配。

- [ ] **Step 5: 运行测试确认通过**

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_api_handcraft_sorting.py -k suppliers_with_sorting -v
```

Expected: 2 PASS

- [ ] **Step 6: Commit**

```bash
git add api/handcraft.py schemas/handcraft.py tests/test_api_handcraft_sorting.py
git commit -m "feat(api): add suppliers-with-sorting endpoint"
```

---

## Task 7: 加 `GET /handcraft/sorting` 端点

**Files:**
- Modify: `api/handcraft.py`
- Test: `tests/test_api_handcraft_sorting.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_api_handcraft_sorting.py`：

```python
def test_sorting_list_returns_orders_with_breakdown(client_with_perms, db):
    part, jewelry = _setup_part_and_jewelry(db)
    o = create_handcraft_order(
        db, supplier_name="商家A",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1, "customer_name": "王"}],
    )

    c = client_with_perms(["sorting"])
    resp = c.get("/api/handcraft/sorting", params={"supplier_name": "商家A"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_more"] is False
    assert len(body["orders"]) == 1
    assert body["orders"][0]["id"] == o.id
    assert body["orders"][0]["receipt_code"] == o.receipt_code
    assert len(body["orders"][0]["breakdown"]) == 1


def test_sorting_list_pagination(client_with_perms, db):
    part, jewelry = _setup_part_and_jewelry(db)
    for i in range(16):
        create_handcraft_order(
            db, supplier_name="商家A",
            parts=[{"part_id": part.id, "qty": 5}],
            jewelries=[{"jewelry_id": jewelry.id, "qty": 1, "customer_name": f"C{i}"}],
        )

    c = client_with_perms(["sorting"])
    resp = c.get("/api/handcraft/sorting", params={"supplier_name": "商家A", "limit": 15, "offset": 0})
    assert resp.json()["has_more"] is True
    assert len(resp.json()["orders"]) == 15

    resp = c.get("/api/handcraft/sorting", params={"supplier_name": "商家A", "limit": 15, "offset": 15})
    assert resp.json()["has_more"] is False
    assert len(resp.json()["orders"]) == 1


def test_sorting_list_requires_supplier_name(client_with_perms, db):
    c = client_with_perms(["sorting"])
    resp = c.get("/api/handcraft/sorting")
    assert resp.status_code == 422

    resp = c.get("/api/handcraft/sorting", params={"supplier_name": ""})
    assert resp.status_code == 422


def test_sorting_list_unknown_supplier_returns_empty(client_with_perms, db):
    c = client_with_perms(["sorting"])
    resp = c.get("/api/handcraft/sorting", params={"supplier_name": "不存在"})
    assert resp.status_code == 200
    assert resp.json() == {"orders": [], "has_more": False}


def test_sorting_list_requires_sorting_perm(client_with_perms, db):
    c = client_with_perms(["handcraft"])
    resp = c.get("/api/handcraft/sorting", params={"supplier_name": "X"})
    assert resp.status_code == 403
```

- [ ] **Step 2: 运行测试确认失败**

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_api_handcraft_sorting.py -k sorting_list -v
```

Expected: FAIL

- [ ] **Step 3: 实现端点**

在 `api/handcraft.py` 找到刚才加的 `api_list_suppliers_with_sorting` 之后追加：

```python
@router.get(
    "/sorting",
    response_model=CargoSortingListResponse,
    dependencies=[require_permission("sorting")],
)
def api_list_handcraft_orders_with_sorting(
    supplier_name: str = Query(..., min_length=1),
    limit: int = Query(15, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return list_handcraft_orders_with_sorting(
        db, supplier_name=supplier_name, limit=limit, offset=offset
    )
```

注意：`list_handcraft_orders_with_sorting` 已在 Task 6 加到模块顶部 imports，这里直接使用。

注意：`Query(..., min_length=1)` 保证 `supplier_name` 非空（含 `""` 也会 422）。

- [ ] **Step 4: 运行测试确认通过**

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_api_handcraft_sorting.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add api/handcraft.py tests/test_api_handcraft_sorting.py
git commit -m "feat(api): add /handcraft/sorting list endpoint"
```

---

## Task 8: 给 `by-receipt-code` 加复合权限（handcraft OR sorting）

**Files:**
- Modify: `api/handcraft.py:158-164`
- Test: `tests/test_api_handcraft_sorting.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_api_handcraft_sorting.py`：

```python
def test_by_receipt_code_accepts_sorting_perm(client_with_perms, db):
    part, jewelry = _setup_part_and_jewelry(db)
    o = create_handcraft_order(
        db, supplier_name="商家A",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1, "customer_name": "王"}],
    )

    c = client_with_perms(["sorting"])
    resp = c.get(f"/api/handcraft/by-receipt-code/{o.receipt_code}")
    assert resp.status_code == 200


def test_by_receipt_code_accepts_handcraft_perm(client_with_perms, db):
    part, jewelry = _setup_part_and_jewelry(db)
    o = create_handcraft_order(
        db, supplier_name="商家A",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1}],
    )

    c = client_with_perms(["handcraft"])
    resp = c.get(f"/api/handcraft/by-receipt-code/{o.receipt_code}")
    assert resp.status_code == 200


def test_by_receipt_code_rejects_other_perms(client_with_perms, db):
    c = client_with_perms(["inventory"])
    resp = c.get("/api/handcraft/by-receipt-code/ABCDE")
    assert resp.status_code == 403
```

- [ ] **Step 2: 运行测试确认失败**

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_api_handcraft_sorting.py -k by_receipt_code -v
```

Expected: 第三个 FAIL（目前端点无权限保护，所以 inventory 用户也能访问 → 404 而非 403）。前两个 PASS。

- [ ] **Step 3: 加权限**

(a) 在 `api/handcraft.py` 顶部 imports（紧跟 Task 6 加的 `from api.deps import require_permission`）追加：

```python
from api.deps import require_any_permission
```

或合并：

```python
from api.deps import require_any_permission, require_permission
```

(b) 在 `api/handcraft.py` 找到 `by-receipt-code` 端点（约第 158-164 行）：

```python
@router.get("/by-receipt-code/{code}", response_model=HandcraftResponse)
def api_get_handcraft_order_by_receipt_code(code: str, db: Session = Depends(get_db)):
    from services.handcraft import get_handcraft_order_by_receipt_code
    order = get_handcraft_order_by_receipt_code(db, code)
    if order is None:
        raise HTTPException(status_code=404, detail=f"无此回执编号：{code}")
    return order
```

改为：

```python
@router.get(
    "/by-receipt-code/{code}",
    response_model=HandcraftResponse,
    dependencies=[require_any_permission("handcraft", "sorting")],
)
def api_get_handcraft_order_by_receipt_code(code: str, db: Session = Depends(get_db)):
    from services.handcraft import get_handcraft_order_by_receipt_code
    order = get_handcraft_order_by_receipt_code(db, code)
    if order is None:
        raise HTTPException(status_code=404, detail=f"无此回执编号：{code}")
    return order
```

- [ ] **Step 4: 运行测试确认通过**

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_api_handcraft_sorting.py -v
```

Expected: 全部 PASS

跑回归确认 HandcraftList 现有调用不挂（fixture 用 admin，会通过）：

```bash
TEST_DATABASE_URL=postgresql://allen:allen@localhost:5432/allen_shop_test \
  pytest tests/test_api_handcraft.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add api/handcraft.py tests/test_api_handcraft_sorting.py
git commit -m "feat(api): gate by-receipt-code on handcraft or sorting perm"
```

---

## Task 9: 加 `sorting` 权限位到用户管理 UI

**Files:**
- Modify: `frontend/src/views/users/UserList.vue:68-79`

- [ ] **Step 1: 加权限选项**

在 `frontend/src/views/users/UserList.vue` 找到 `permissionOptions` 数组（约第 68 行），在 `{ value: 'inventory', label: '库存' }` 之后、`{ value: 'users', label: '用户管理' }` 之前加入：

```javascript
  { value: 'sorting', label: '货物分拣' },
```

修改后整段：

```javascript
const permissionOptions = [
  { value: 'kanban', label: '进度看板' },
  { value: 'dashboard', label: '仪表盘' },
  { value: 'parts', label: '配件管理' },
  { value: 'jewelries', label: '饰品管理' },
  { value: 'orders', label: '订单管理' },
  { value: 'purchase_orders', label: '配件采购' },
  { value: 'plating', label: '电镀单' },
  { value: 'handcraft', label: '手工单' },
  { value: 'sorting', label: '货物分拣' },
  { value: 'inventory', label: '库存' },
  { value: 'users', label: '用户管理' },
]
```

- [ ] **Step 2: 手测**

启动前端：

```bash
cd frontend && npm run dev
```

打开 http://localhost:5173 → 用户管理 → 新建用户。预期：「权限」勾选区出现「货物分拣」选项。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/users/UserList.vue
git commit -m "feat(users): add sorting permission to user management UI"
```

---

## Task 10: 创建 SortingIcon 组件

**Files:**
- Create: `frontend/src/components/icons/SortingIcon.vue`

- [ ] **Step 1: 读源 SVG**

读取 `frontend/src/assets/icons/分拣.svg` 内容（用 Read tool 读它的 path d 数据）。

- [ ] **Step 2: 创建组件文件**

创建 `frontend/src/components/icons/SortingIcon.vue`。**模板必须包一层 `<template>`，把 SVG 的 `fill` 属性改为 `currentColor` 以适配主题色**：

```vue
<template>
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
    <!-- 把 分拣.svg 里的 <path> 段全部贴在这里，但每个 path 的 fill="xxx" 都换成 fill="currentColor" -->
  </svg>
</template>
```

参考 `HandcraftIcon.vue` 的写法，确认 viewBox 与源 SVG 一致（通常是 `0 0 1024 1024`）。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/icons/SortingIcon.vue "frontend/src/assets/icons/分拣.svg"
git commit -m "feat(icons): add SortingIcon for cargo-sorting page"
```

---

## Task 11: 创建前端 API 客户端

**Files:**
- Create: `frontend/src/api/cargoSorting.js`

- [ ] **Step 1: 创建文件**

创建 `frontend/src/api/cargoSorting.js`：

```javascript
import api from './index'

export const getCargoSortingSuppliers = () =>
  api.get('/handcraft/suppliers-with-sorting')

export const listCargoSortingOrders = (supplierName, { limit = 15, offset = 0 } = {}) =>
  api.get('/handcraft/sorting', {
    params: { supplier_name: supplierName, limit, offset },
  })

// re-export — page 用这个搜索；该方法已在 handcraft.js 定义
export { getHandcraftByReceiptCode } from './handcraft'
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/cargoSorting.js
git commit -m "feat(api): cargo-sorting client functions"
```

---

## Task 12: 注册路由 + 权限映射 + 侧边栏菜单项

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/layouts/DefaultLayout.vue`

- [ ] **Step 1: router/index.js 加权限映射**

在 `frontend/src/router/index.js` 的 `ROUTE_PERMISSION_MAP` 中加：

```javascript
  'cargo-sorting': 'sorting',
```

加在 `'handcraft-receipts': 'handcraft',` 之后。

- [ ] **Step 2: 加路由优先级**

在 `PERMISSION_ROUTE_ORDER` 数组里，在 `'restock'` 之后加 `'cargo-sorting'`：

```javascript
const PERMISSION_ROUTE_ORDER = [
  'kanban', 'dashboard', 'parts', 'jewelries', 'orders',
  'purchase-orders', 'plating', 'handcraft', 'restock', 'cargo-sorting',
  'inventory', 'inventory-log', 'users',
]
```

- [ ] **Step 3: 注册路由**

在 `routes[0].children` 中，找到 `{ path: 'handcraft/:id', ... }` 之后、`{ path: 'restock', ... }` 之前加入：

```javascript
        { path: 'cargo-sorting', component: lazyLoad(() => import('@/views/cargo-sorting/CargoSorting.vue')), meta: { perm: 'sorting' } },
```

- [ ] **Step 4: 加侧边栏菜单项**

在 `frontend/src/layouts/DefaultLayout.vue` 中：

(a) 在 import 区追加：

```javascript
import SortingIcon from '@/components/icons/SortingIcon.vue'
```

(b) `flatItems`（约第 89-90 行附近，「手工回收」后）加入：

```javascript
  { label: '货物分拣', key: 'cargo-sorting', icon: icon(SortingIcon), perm: 'sorting' },
```

(c) `allGroupedItems` 中，「手工单」分组的 `children` 数组末尾加入：

```javascript
          { label: '货物分拣', key: 'cargo-sorting', icon: icon(SortingIcon), perm: 'sorting' },
```

整段后：

```javascript
      {
        label: '手工单', key: 'handcraft-group', icon: icon(HandcraftIcon), perm: 'handcraft',
        children: [
          { label: '手工发出', key: 'handcraft', icon: icon(PaperPlaneOutline), perm: 'handcraft' },
          { label: '手工回收', key: 'handcraft-receipts', icon: icon(DownloadOutline), perm: 'handcraft' },
          { label: '货物分拣', key: 'cargo-sorting', icon: icon(SortingIcon), perm: 'sorting' },
        ],
      },
```

注意：分组的 `perm: 'handcraft'` 不要改 —— 分组本身的展现条件是「有手工权限」；分拣员只有 `sorting` 权限时，「手工单」分组不可见，但「货物分拣」需要独立展示。
**这是个问题。** 分拣员看不到「手工单」分组，所以也看不到嵌在里面的「货物分拣」。

**解决方案：** 既然分拣员只有 `sorting` 权限，把「货物分拣」**单独**作为一个顶层分组项放在「手工单」之后。**修改 (c)：** 不要在「手工单」children 里加，而是在「生产」分组里加一个独立条目（同级于「手工单」），或者把「货物分拣」分组的 `perm` 改为 `sorting` 单独成组。最简单做法：放进「生产」分组里，紧跟「手工单」分组之后：

```javascript
      {
        label: '手工单', key: 'handcraft-group', icon: icon(HandcraftIcon), perm: 'handcraft',
        children: [
          { label: '手工发出', key: 'handcraft', icon: icon(PaperPlaneOutline), perm: 'handcraft' },
          { label: '手工回收', key: 'handcraft-receipts', icon: icon(DownloadOutline), perm: 'handcraft' },
        ],
      },
      { label: '货物分拣', key: 'cargo-sorting', icon: icon(SortingIcon), perm: 'sorting' },
```

视觉上「货物分拣」就在「手工单」分组之后、「库存」分组之前，对管理员是「手工单」分组下的兄弟项；对分拣员则是孤立的、唯一可见的菜单项。`filterChildren` 已会过滤无权限项，所以管理员不会看到（除非也有 sorting 权限）—— 等等，管理员有所有权限，所以会看到。OK。

**重要更正：** 上面 (c) 步骤的最终代码是这两块（一个分组、一个紧跟其后的独立菜单项），都放在「生产」分组的 children 里。flatItems 已经包含了。

- [ ] **Step 5: 验证路由（占位页）**

临时创建占位页以便测试。在终端：

```bash
mkdir -p frontend/src/views/cargo-sorting
```

创建 `frontend/src/views/cargo-sorting/CargoSorting.vue`：

```vue
<template>
  <div style="padding: 24px">货物分拣页面占位 — 待实现</div>
</template>
```

启动前端 `cd frontend && npm run dev`，登录后：
- 用 admin 账号：侧边栏「手工单」分组下方应见独立「货物分拣」菜单，点击进入占位页
- 浏览器地址栏直接访问 `/cargo-sorting`：能进入

- [ ] **Step 6: Commit**

```bash
git add frontend/src/router/index.js frontend/src/layouts/DefaultLayout.vue frontend/src/views/cargo-sorting/CargoSorting.vue
git commit -m "feat(router): register cargo-sorting route and sidebar item"
```

---

## Task 13: 实现 SupplierSheet 组件（底部抽屉）

**Files:**
- Create: `frontend/src/views/cargo-sorting/SupplierSheet.vue`

- [ ] **Step 1: 写组件**

创建 `frontend/src/views/cargo-sorting/SupplierSheet.vue`：

```vue
<template>
  <n-drawer
    :show="show"
    placement="bottom"
    :height="380"
    :auto-focus="false"
    style="border-radius: 16px 16px 0 0"
    @update:show="(v) => emit('update:show', v)"
  >
    <n-drawer-content title="选择手工商家" closable>
      <n-spin :show="loading">
        <div v-if="!loading && suppliers.length === 0" class="empty">
          暂无含分拣信息的商家
        </div>
        <div v-else class="list">
          <div
            v-for="name in suppliers"
            :key="name"
            class="item"
            :class="{ active: name === selected }"
            @click="onPick(name)"
          >
            <span>{{ name }}</span>
            <n-icon v-if="name === selected" :size="18" color="#6366f1">
              <CheckmarkOutline />
            </n-icon>
          </div>
        </div>
      </n-spin>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup>
import { ref, watch } from 'vue'
import { NDrawer, NDrawerContent, NSpin, NIcon } from 'naive-ui'
import { CheckmarkOutline } from '@vicons/ionicons5'
import { getCargoSortingSuppliers } from '@/api/cargoSorting'

const props = defineProps({
  show: { type: Boolean, required: true },
  selected: { type: String, default: '' },
})
const emit = defineEmits(['update:show', 'pick'])

const loading = ref(false)
const suppliers = ref([])

const load = async () => {
  loading.value = true
  try {
    const { data } = await getCargoSortingSuppliers()
    suppliers.value = data.suppliers || []
  } finally {
    loading.value = false
  }
}

watch(() => props.show, (v) => {
  if (v) load()
})

const onPick = (name) => {
  emit('pick', name)
  emit('update:show', false)
}
</script>

<style scoped>
.list { display: flex; flex-direction: column; }
.item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 4px;
  border-bottom: 1px solid #f3f4f6;
  font-size: 15px;
  min-height: 44px;
  cursor: pointer;
}
.item:active { background: #f9fafb; }
.item.active { color: #6366f1; font-weight: 600; }
.empty {
  text-align: center;
  color: #9ca3af;
  padding: 40px 0;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/cargo-sorting/SupplierSheet.vue
git commit -m "feat(cargo-sorting): supplier bottom sheet component"
```

---

## Task 14: 实现 SortingCard 组件（单订单卡片）

**Files:**
- Create: `frontend/src/views/cargo-sorting/SortingCard.vue`

- [ ] **Step 1: 写组件**

创建 `frontend/src/views/cargo-sorting/SortingCard.vue`：

```vue
<template>
  <div class="card">
    <div class="head">
      <div class="receipt-code">{{ order.receipt_code || '—' }}</div>
      <span class="badge" :class="badgeClass">{{ badgeText }}</span>
    </div>
    <div class="meta">{{ order.supplier_name }} · {{ order.breakdown.length }} 个饰品</div>

    <div
      v-for="g in order.breakdown"
      :key="g.jewelry_id"
      class="jewelry-row"
    >
      <div class="thumb-wrap" @click="openPreview(g)">
        <n-image
          :src="g.jewelry_image || ''"
          :preview-src="g.jewelry_image || ''"
          :show-toolbar-tooltip="false"
          object-fit="cover"
          class="thumb"
          :fallback-src="placeholder"
        />
      </div>
      <div class="info">
        <div class="name">{{ g.jewelry_name }}</div>
        <div class="id">{{ g.jewelry_id }}</div>
        <div class="customers">
          <div v-for="(e, idx) in g.entries" :key="idx" class="customer-line">
            {{ e.customer_name }} ×{{ formatQty(e.qty) }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { NImage } from 'naive-ui'

const props = defineProps({
  order: { type: Object, required: true },
})

const placeholder =
  'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 72 72"><rect width="72" height="72" fill="%23f3f4f6"/><text x="50%" y="55%" text-anchor="middle" font-size="11" fill="%239ca3af">无图</text></svg>'

const STATUS_TEXT = {
  pending: '待发出',
  processing: '已发出',
  completed: '已完成',
}

const badgeText = computed(() => STATUS_TEXT[props.order.status] || props.order.status)
const badgeClass = computed(() =>
  props.order.status === 'completed' ? 'badge-green' : 'badge-gray'
)

const formatQty = (q) => (Number.isInteger(q) ? q : q.toFixed(2).replace(/\.?0+$/, ''))

const openPreview = (g) => {
  // n-image 已通过 preview-src 提供点击放大，这里 no-op，保留 hook
}
</script>

<style scoped>
.card {
  background: white;
  border-radius: 14px;
  padding: 14px;
  margin-top: 14px;
  box-shadow: 0 1px 3px rgba(0,0,0,.06);
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 4px;
}
.receipt-code {
  font-size: 18px;
  font-weight: 700;
  color: #111827;
  letter-spacing: .5px;
}
.badge {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 4px;
}
.badge-green { background: #d1fae5; color: #065f46; }
.badge-gray { background: #f3f4f6; color: #6b7280; }
.meta { font-size: 12px; color: #6b7280; }
.jewelry-row {
  display: flex;
  gap: 12px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #e5e7eb;
}
.thumb-wrap {
  flex-shrink: 0;
  width: 72px;
  height: 72px;
  cursor: pointer;
}
.thumb {
  width: 72px !important;
  height: 72px !important;
  border-radius: 8px;
}
.info { flex: 1; min-width: 0; }
.name { font-size: 14px; font-weight: 600; color: #111827; }
.id { font-size: 11px; color: #9ca3af; margin-top: 2px; }
.customers { margin-top: 6px; }
.customer-line {
  font-size: 13px;
  color: #4b5563;
  line-height: 1.7;
}
</style>
```

注意：`n-image` 设 `preview-src` 会自动接管点击放大 + 遮罩关闭，无需额外代码。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/cargo-sorting/SortingCard.vue
git commit -m "feat(cargo-sorting): order card with grouped jewelry rows"
```

---

## Task 15: 实现 CargoSorting 主页面

**Files:**
- Modify: `frontend/src/views/cargo-sorting/CargoSorting.vue`（覆盖 Task 12 的占位实现）

- [ ] **Step 1: 写主页面**

完全覆盖 `frontend/src/views/cargo-sorting/CargoSorting.vue` 的占位内容：

```vue
<template>
  <div class="page">
    <header class="sticky-head">
      <div class="search-box">
        <n-input
          v-model:value="codeInput"
          placeholder="输入回执编号"
          @keydown.enter="onSearch"
          clearable
        />
        <n-button type="primary" @click="onSearch" :loading="searchLoading">搜索</n-button>
      </div>
      <div class="filter-btn" @click="sheetShow = true">
        <span v-if="!selectedSupplier">按商家筛选 ▾</span>
        <span v-else>
          商家：<strong>{{ selectedSupplier }}</strong>
          <span class="clear" @click.stop="clearSupplier">×</span>
        </span>
      </div>
    </header>

    <main class="results">
      <div v-if="loading && orders.length === 0" class="loading">加载中...</div>

      <template v-else-if="orders.length > 0">
        <SortingCard v-for="o in orders" :key="o.id" :order="o" />
        <div v-if="hasMore" class="load-more">
          <n-button block @click="loadMore" :loading="loadMoreLoading">加载更多</n-button>
        </div>
      </template>

      <div v-else-if="hasInteracted" class="empty">
        <p>{{ emptyText }}</p>
      </div>

      <div v-else class="empty initial">
        <p>输入回执编号或选择商家查看分拣信息</p>
      </div>
    </main>

    <SupplierSheet
      v-model:show="sheetShow"
      :selected="selectedSupplier"
      @pick="onSupplierPicked"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { NInput, NButton, useMessage } from 'naive-ui'
import SortingCard from './SortingCard.vue'
import SupplierSheet from './SupplierSheet.vue'
import {
  getHandcraftByReceiptCode,
  listCargoSortingOrders,
} from '@/api/cargoSorting'

const message = useMessage()

const codeInput = ref('')
const selectedSupplier = ref('')
const sheetShow = ref(false)
const orders = ref([])
const loading = ref(false)
const searchLoading = ref(false)
const loadMoreLoading = ref(false)
const hasMore = ref(false)
const hasInteracted = ref(false)
const lastEmptyContext = ref('initial') // 'initial' | 'supplier-empty'

const emptyText = computed(() => {
  if (lastEmptyContext.value === 'supplier-empty') {
    return '该商家暂无含分拣信息的手工单'
  }
  return '输入回执编号或选择商家查看分拣信息'
})

const onSearch = async () => {
  const code = codeInput.value.trim().toUpperCase()
  if (!code) return
  // 互斥：点击搜索就清商家选择
  selectedSupplier.value = ''
  searchLoading.value = true
  try {
    const { data } = await getHandcraftByReceiptCode(code)
    // 把单订单转为列表展示，须 fetch breakdown
    // 这里复用 list 端点反而麻烦——直接构造单卡：调 breakdown 单独取一次
    const breakdownResp = await import('@/api/handcraft').then(m =>
      m.getHandcraftJewelryBreakdown(data.id)
    )
    // 仅保留有客户的 entries 和 group
    const filteredGroups = breakdownResp.data
      .map(g => ({
        ...g,
        entries: g.entries.filter(e => e.customer_name && e.customer_name.trim()),
      }))
      .filter(g => g.entries.length > 0)

    if (filteredGroups.length === 0) {
      message.warning('此手工单没有分拣信息')
      return
    }

    orders.value = [{
      id: data.id,
      supplier_name: data.supplier_name,
      receipt_code: data.receipt_code,
      status: data.status,
      created_at: data.created_at,
      breakdown: filteredGroups,
    }]
    hasMore.value = false
    hasInteracted.value = true
    codeInput.value = code
  } catch (err) {
    if (err.response?.status === 404) {
      message.warning(`无此回执编号：${code}`)
      // 保持上次结果区状态（不动 orders / hasMore）
    } else {
      message.error('搜索失败')
    }
  } finally {
    searchLoading.value = false
  }
}

const fetchSupplierOrders = async (offset = 0) => {
  const { data } = await listCargoSortingOrders(selectedSupplier.value, {
    limit: 15,
    offset,
  })
  return data
}

const onSupplierPicked = async (name) => {
  selectedSupplier.value = name
  codeInput.value = ''  // 互斥
  loading.value = true
  hasInteracted.value = true
  try {
    const data = await fetchSupplierOrders(0)
    orders.value = data.orders
    hasMore.value = data.has_more
    lastEmptyContext.value = orders.value.length === 0 ? 'supplier-empty' : 'initial'
  } catch (err) {
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

const loadMore = async () => {
  loadMoreLoading.value = true
  try {
    const data = await fetchSupplierOrders(orders.value.length)
    orders.value = [...orders.value, ...data.orders]
    hasMore.value = data.has_more
  } catch (err) {
    message.error('加载失败')
  } finally {
    loadMoreLoading.value = false
  }
}

const clearSupplier = () => {
  selectedSupplier.value = ''
  orders.value = []
  hasMore.value = false
  hasInteracted.value = false
  lastEmptyContext.value = 'initial'
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: #f9fafb;
}
.sticky-head {
  position: sticky;
  top: 0;
  z-index: 10;
  background: #f9fafb;
  padding: 16px 16px 12px;
  border-bottom: 1px solid #f3f4f6;
}
.search-box {
  display: flex;
  gap: 8px;
}
.search-box :deep(.n-button) {
  min-height: 44px;
  min-width: 64px;
}
.search-box :deep(.n-input) {
  min-height: 44px;
}
.filter-btn {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: white;
  padding: 12px 14px;
  border-radius: 12px;
  margin-top: 10px;
  font-size: 14px;
  color: #374151;
  min-height: 44px;
  cursor: pointer;
  box-shadow: 0 1px 2px rgba(0,0,0,.04);
}
.clear {
  margin-left: 8px;
  font-size: 16px;
  color: #9ca3af;
  padding: 0 4px;
}
.results {
  padding: 0 16px 24px;
}
.empty, .loading {
  text-align: center;
  color: #9ca3af;
  padding: 60px 0;
  font-size: 13px;
}
.load-more {
  margin-top: 14px;
}
</style>
```

- [ ] **Step 2: 启动前后端做联调**

后端：

```bash
python main.py
```

前端：

```bash
cd frontend && npm run dev
```

打开 http://localhost:5173 → 登录 admin → 进入「货物分拣」。

- [ ] **Step 3: 手测清单**

在浏览器把窗口缩到 **375px 宽**（DevTools → 移动模拟）依次确认：

- [ ] 初始态：空白 + 提示「输入回执编号或选择商家查看分拣信息」
- [ ] 搜索一个不存在的编号 → toast 提示，结果区**保持上次状态**（初始时仍是初始态）
- [ ] 创建一个手工单，给某行 `customer_name`，然后搜索其回执编号 → 看到单卡，含饰品图、客户行
- [ ] 选商家筛选 → 抽屉从底部滑出，列表里只有"有分拣信息"的商家
- [ ] 选中商家后：抽屉关闭，结果区列出该商家所有含分拣的订单（按创建时间倒序）
- [ ] 商家选中后再点搜索：商家选择被清空、结果换成搜索结果
- [ ] 反之搜索后选商家：搜索框被清空
- [ ] 给某商家创建 16 单含分拣 → 「加载更多」按钮出现，点击后第 16 单加入列表、按钮消失
- [ ] 点饰品图 → 弹出全屏大图，点遮罩关闭
- [ ] sticky 头部：向下滚动结果时头部仍在顶部

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/cargo-sorting/CargoSorting.vue
git commit -m "feat(cargo-sorting): main page with search, supplier filter, load-more"
```

---

## Task 16: 真机移动端验证

**Files:** 无代码改动

- [ ] **Step 1: 找到本机 LAN IP**

```bash
ipconfig getifaddr en0
```

- [ ] **Step 2: 配前端允许 LAN 访问**

在 `frontend/package.json` 的 `dev` script 临时加 `--host 0.0.0.0`（如果还没配）。或者运行：

```bash
cd frontend && npm run dev -- --host 0.0.0.0
```

- [ ] **Step 3: 真机访问**

手机连同一 WLAN，浏览器开 `http://<LAN_IP>:5173`，登录测试账号（只有 `sorting` 权限的那种 —— 在用户管理里创建一个），重复 Task 15 Step 3 的手测清单。

- [ ] **Step 4: 验证触控**

- [ ] 搜索按钮、商家按钮、抽屉里的每个商家行 —— 点击都能稳定触发，无误触
- [ ] 饰品图点击有响应区域充足
- [ ] 抽屉支持向下滑动关闭

- [ ] **Step 5: 收尾**

确认手测全过 → 提交一个 commit（即使没有改动也写一条总结）：

```bash
git commit --allow-empty -m "chore(cargo-sorting): manual mobile testing pass"
```

---

## Spec Coverage Self-Review

每条 spec 要求都有对应 task：

| Spec | Task |
|---|---|
| 新增 `sorting` 权限位 | T8(deps), T9(UI) |
| 「手工单」分组第 3 项（侧边栏） | T12（实际落点改为分组后兄弟项，因分拣员独立权限） |
| sticky 顶部 + 搜索 + 商家按钮 | T15 |
| 顶部互斥规则 | T15 |
| 底部抽屉选商家 | T13 |
| 卡片：编号 + 状态徽章 + 商家 + 饰品列表 | T14 |
| 状态徽章 completed=绿 其他=灰 | T14 |
| n-image 点击放大 + 遮罩外关闭 | T14 |
| 三种缺省态 | T15 |
| 15 单上限 + 加载更多按钮 | T4, T7, T15 |
| 移动端触控 ≥44px | T13, T15 |
| 后端服务函数 3 个 + breakdown 扩展 | T1, T2, T3, T4 |
| 2 个 API 端点 | T6, T7 |
| `by-receipt-code` 加复合权限 | T8 |
| 权限注册（UI 勾选） | T9 |
| 后端测试矩阵 | T1-T8 全覆盖 |
| 移动端真机测试 | T16 |

**Out of scope 不实现**：进度记录、下拉刷新、模糊搜索、商家名归一化、导出 —— 均未出现在 task 列表。✓

**侧边栏菜单层级特殊处理记录**：spec 写「分组第 3 子项」，实际改为「分组之外、生产分组下的独立顶层项」——因分拣员仅有 `sorting` 权限时分组本身（`perm: 'handcraft'`）不可见，会把嵌入的「货物分拣」也连带隐藏。这个调整在 T12 内详细说明。
