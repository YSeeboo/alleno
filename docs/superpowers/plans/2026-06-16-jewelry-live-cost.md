# 饰品实时总成本（物料 + 手工费）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在饰品详情页和饰品列表页常驻显示"实时总成本 = Σ(配件 unit_cost × BOM 用量) + 饰品 handcraft_cost"，成本不全时打 ⚠️ 标记。

**Architecture:** 把订单成本快照里的单饰品成本计算抽成一个纯函数 `compute_jewelry_cost`，快照与实时饰品页共用它（口径永远一致）。实时成本不落库——在 `GET /api/jewelries` 和 `GET /api/jewelries/{id}` 返回前，批量加载 BOM/配件、把 `material_cost / total_cost / has_incomplete_cost` 三个字段挂到饰品 ORM 实例上（沿用本仓 `_attach_part_colors` / `_attach_actual_qty` 的挂属性模式）。前端在详情页加三行、列表页加一列（合计数 + 悬停拆分 tooltip + ⚠️）。

**Tech Stack:** FastAPI + SQLAlchemy（Decimal 精确计算）、Pydantic v2（`ConfigDict(from_attributes=True)`）、Vue 3 + Naive UI、pytest。

**关键既有事实（实现者须知）：**
- `Part.unit_cost`：原子件 = `purchase_cost + bead_cost + plating_cost`（全空时为 `None`）；组合件 = `Σ(子件.unit_cost × 用量) + assembly_cost`（见 `services/part.py:376` 与 `services/part_bom.py:104`）。本计划**直接读 `part.unit_cost`**，不重算配件成本。
- `Jewelry.handcraft_cost`：来自手工回收单收回饰品时的同步（`services/cost_sync.py:167`），已是饰品上的列。
- 现有快照逻辑：`services/order_cost_snapshot.py:58-94` 的 jewelry 循环就是 `jewelry_unit_cost = Σ(part.unit_cost × qty) + handcraft_cost`。本计划把这段抽出来复用，**不改变快照对外行为**（空 BOM 仍在快照层提前 `raise`，不会进入新函数）。
- 测试夹具：用 `services.jewelry.create_jewelry`、`services.part.create_part`、`services.part.update_part_cost`、`services.bom.set_bom`（见 `tests/test_api_cost_snapshot.py`）。`db` / `client` fixture 见 `tests/conftest.py`。
- 前端无单元测试框架（`frontend/package.json` 无 test 脚本），前端任务以 `npm run build` 通过 + 人工核验为准。

---

## File Structure

- **Create** `services/jewelry_cost.py` — 纯计算 `compute_jewelry_cost()` + 批量挂属性 `attach_jewelry_costs()`。新建独立模块避免与 `order_cost_snapshot` / `jewelry` 服务循环依赖。
- **Modify** `services/order_cost_snapshot.py:58-94` — jewelry 循环改为调用 `compute_jewelry_cost()`。
- **Modify** `schemas/jewelry.py` — `JewelryResponse` 增加三个可选字段。
- **Modify** `api/jewelries.py` — `GET /` 与 `GET /{id}` 返回前挂成本。
- **Modify** `frontend/src/views/jewelries/JewelryDetail.vue` — 加 物料成本 / 总成本 两行（手工费已有）。
- **Modify** `frontend/src/views/jewelries/JewelryList.vue` — 加 总成本 列。
- **Create** `tests/test_jewelry_cost.py` — 纯函数 + 挂属性 服务级测试。
- **Modify/Create** `tests/test_api_jewelry_cost.py` — API 层测试。

---

### Task 1: 抽取 `compute_jewelry_cost` 纯函数

**Files:**
- Create: `services/jewelry_cost.py`
- Test: `tests/test_jewelry_cost.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_jewelry_cost.py`:

```python
from decimal import Decimal

from services.jewelry_cost import compute_jewelry_cost


class _FakeJewelry:
    def __init__(self, handcraft_cost):
        self.handcraft_cost = handcraft_cost


class _FakeBom:
    def __init__(self, part_id, qty_per_unit):
        self.part_id = part_id
        self.qty_per_unit = qty_per_unit


class _FakePart:
    def __init__(self, id, name, unit_cost):
        self.id = id
        self.name = name
        self.unit_cost = unit_cost


def test_compute_basic():
    jewelry = _FakeJewelry(handcraft_cost=1.0)
    bom_rows = [_FakeBom("PJ-X-1", 10), _FakeBom("PJ-LT-1", 1)]
    part_map = {
        "PJ-X-1": _FakePart("PJ-X-1", "珠", Decimal("0.05")),
        "PJ-LT-1": _FakePart("PJ-LT-1", "链", Decimal("2.0")),
    }
    r = compute_jewelry_cost(jewelry, bom_rows, part_map)
    # 物料 = 10×0.05 + 1×2.0 = 2.5
    assert r["material_cost"] == Decimal("2.5000000")
    assert r["handcraft_cost"] == Decimal("1")
    assert r["total_cost"] == Decimal("3.5000000")
    assert r["has_incomplete_cost"] is False
    assert len(r["bom_details"]) == 2


def test_compute_missing_unit_cost_marks_incomplete():
    jewelry = _FakeJewelry(handcraft_cost=None)
    bom_rows = [_FakeBom("PJ-X-1", 1)]
    part_map = {"PJ-X-1": _FakePart("PJ-X-1", "无价", None)}
    r = compute_jewelry_cost(jewelry, bom_rows, part_map)
    assert r["has_incomplete_cost"] is True
    assert r["material_cost"] == Decimal("0E-7")
    assert r["total_cost"] == Decimal("0E-7")


def test_compute_no_bom_marks_incomplete():
    jewelry = _FakeJewelry(handcraft_cost=5.0)
    r = compute_jewelry_cost(jewelry, [], {})
    assert r["has_incomplete_cost"] is True
    assert r["material_cost"] == Decimal("0")
    # 仍把手工费算进去
    assert r["total_cost"] == Decimal("5")


def test_compute_missing_part_marks_incomplete():
    jewelry = _FakeJewelry(handcraft_cost=0)
    bom_rows = [_FakeBom("PJ-GONE", 3)]
    r = compute_jewelry_cost(jewelry, bom_rows, {})  # part_map 缺这个件
    assert r["has_incomplete_cost"] is True
    assert r["material_cost"] == Decimal("0E-7")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_jewelry_cost.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.jewelry_cost'`

- [ ] **Step 3: 写实现**

Create `services/jewelry_cost.py`:

```python
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

_Q7 = Decimal("0.0000001")


def compute_jewelry_cost(jewelry, bom_rows, part_map) -> dict:
    """单饰品成本（物料 + 手工费）的纯计算，被订单成本快照与饰品实时成本共用。

    - jewelry: 任意带 `.handcraft_cost` 的对象（ORM 或测试桩）
    - bom_rows: 该饰品的 Bom 行（带 `.part_id` / `.qty_per_unit`）
    - part_map: {part_id: Part}，Part 带 `.unit_cost` / `.name`

    返回的 material_cost / handcraft_cost / total_cost 均为 Decimal（保留快照层的
    精确累加能力，API 层再转 float）。has_incomplete_cost 在以下任一情况为 True：
    没有 BOM 行、引用的配件不在 part_map、或配件 unit_cost 为 None。
    """
    bom_cost = Decimal(0)
    has_incomplete = False
    bom_details: list[dict] = []
    for row in bom_rows:
        part = part_map.get(row.part_id)
        if part is None or part.unit_cost is None:
            has_incomplete = True
        part_unit_cost = (
            Decimal(str(part.unit_cost))
            if (part is not None and part.unit_cost is not None)
            else Decimal(0)
        )
        qty_per_unit = Decimal(str(row.qty_per_unit))
        subtotal = (part_unit_cost * qty_per_unit).quantize(_Q7, rounding=ROUND_HALF_UP)
        bom_cost += subtotal
        bom_details.append({
            "part_id": row.part_id,
            "part_name": part.name if part else None,
            "unit_cost": float(part_unit_cost),
            "qty_per_unit": float(qty_per_unit),
            "subtotal": float(subtotal),
        })

    if not bom_rows:
        has_incomplete = True

    material_cost = bom_cost.quantize(_Q7, rounding=ROUND_HALF_UP) if bom_rows else Decimal(0)
    handcraft_cost = Decimal(str(jewelry.handcraft_cost or 0))
    total_cost = (material_cost + handcraft_cost).quantize(_Q7, rounding=ROUND_HALF_UP)
    return {
        "material_cost": material_cost,
        "handcraft_cost": handcraft_cost,
        "total_cost": total_cost,
        "has_incomplete_cost": has_incomplete,
        "bom_details": bom_details,
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_jewelry_cost.py -v`
Expected: PASS（4 个测试）

- [ ] **Step 5: 提交**

```bash
git add services/jewelry_cost.py tests/test_jewelry_cost.py
git commit -m "feat(cost): add shared compute_jewelry_cost pure function"
```

---

### Task 2: 快照复用纯函数（行为不变回归）

**Files:**
- Modify: `services/order_cost_snapshot.py:58-94`
- Test: `tests/test_api_cost_snapshot.py`（既有，作为回归门禁，不新增）

- [ ] **Step 1: 先跑既有快照测试，确认当前全绿（基线）**

Run: `pytest tests/test_api_cost_snapshot.py -v`
Expected: PASS（全部）

- [ ] **Step 2: 改实现 — jewelry 循环改调用纯函数**

在 `services/order_cost_snapshot.py` 顶部 import 区加：

```python
from services.jewelry_cost import compute_jewelry_cost
```

把 `services/order_cost_snapshot.py` 的 jewelry 循环（当前 58-94 行）整体替换为：

```python
    for item in jewelry_items:
        jewelry = jewelry_map.get(item.jewelry_id)
        bom_rows = bom_by_jewelry.get(item.jewelry_id, [])
        cost = compute_jewelry_cost(jewelry, bom_rows, part_map)
        if cost["has_incomplete_cost"]:
            has_incomplete = True
        jewelry_unit_cost = cost["total_cost"]  # Decimal
        jewelry_total_cost = (jewelry_unit_cost * item.quantity).quantize(_Q7, rounding=ROUND_HALF_UP)
        total_cost += jewelry_total_cost
        snapshot_items.append({
            "jewelry_id": item.jewelry_id,
            "jewelry_name": jewelry.name if jewelry else None,
            "part_id": None,
            "part_name": None,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price) if item.unit_price is not None else None,
            "handcraft_cost": float(cost["handcraft_cost"]),
            "jewelry_unit_cost": float(jewelry_unit_cost),
            "jewelry_total_cost": float(jewelry_total_cost),
            "bom_details": cost["bom_details"],
        })
```

> 注：空 BOM 的 `raise`（当前 49-53 行的 `if not bom_by_jewelry.get(...)` 守卫）**保留不动**，因此空 BOM 永远不会进入 `compute_jewelry_cost`，快照对外行为不变。

- [ ] **Step 3: 跑快照测试确认仍全绿**

Run: `pytest tests/test_api_cost_snapshot.py -v`
Expected: PASS（与 Step 1 相同结果，尤其 `test_complete_order_with_handcraft_cost`、`test_complete_order_missing_part_cost_marks_incomplete` 仍通过）

- [ ] **Step 4: 提交**

```bash
git add services/order_cost_snapshot.py
git commit -m "refactor(cost): snapshot reuses compute_jewelry_cost (no behavior change)"
```

---

### Task 3: 批量挂成本属性 `attach_jewelry_costs`

**Files:**
- Modify: `services/jewelry_cost.py`
- Test: `tests/test_jewelry_cost.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_jewelry_cost.py` 末尾追加（注意这些用真实 DB fixture）：

```python
import pytest
from services.jewelry import create_jewelry, update_jewelry
from services.part import create_part, update_part_cost
from services.bom import set_bom
from services.jewelry_cost import attach_jewelry_costs


def test_attach_costs_batch(db):
    p1 = create_part(db, {"name": "珠", "category": "小配件"})
    p2 = create_part(db, {"name": "链", "category": "链条"})
    update_part_cost(db, p1.id, "purchase_cost", 0.05)
    update_part_cost(db, p2.id, "purchase_cost", 2.0)

    j1 = create_jewelry(db, {"name": "项链A", "category": "单件"})
    set_bom(db, j1.id, p1.id, 10)   # 0.5
    set_bom(db, j1.id, p2.id, 1)    # 2.0
    update_jewelry(db, j1.id, {"handcraft_cost": 1.0})

    j2 = create_jewelry(db, {"name": "无BOM件", "category": "单件"})

    attach_jewelry_costs(db, [j1, j2])

    assert j1.material_cost == pytest.approx(2.5)
    assert j1.total_cost == pytest.approx(3.5)
    assert j1.has_incomplete_cost is False

    # 无 BOM → 物料 0、标记不完整、总成本 = 0（无手工费）
    assert j2.material_cost == pytest.approx(0.0)
    assert j2.has_incomplete_cost is True
    assert j2.total_cost == pytest.approx(0.0)


def test_attach_costs_incomplete_when_part_has_no_unit_cost(db):
    p = create_part(db, {"name": "无价件", "category": "小配件"})  # 不设成本 → unit_cost None
    j = create_jewelry(db, {"name": "X", "category": "单件"})
    set_bom(db, j.id, p.id, 3)
    attach_jewelry_costs(db, [j])
    assert j.has_incomplete_cost is True
    assert j.material_cost == pytest.approx(0.0)


def test_attach_costs_empty_list_noop(db):
    assert attach_jewelry_costs(db, []) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_jewelry_cost.py::test_attach_costs_batch -v`
Expected: FAIL — `ImportError: cannot import name 'attach_jewelry_costs'`

- [ ] **Step 3: 写实现**

在 `services/jewelry_cost.py` 末尾追加（顶部已有 Decimal import；新增 Session/模型 import）：

```python
from sqlalchemy.orm import Session

from models.bom import Bom
from models.part import Part


def attach_jewelry_costs(db: Session, jewelries: list) -> list:
    """批量给饰品 ORM 实例挂上 material_cost / total_cost / has_incomplete_cost
    三个非持久化属性（不写库）。一次性聚合查 BOM 与配件，避免逐饰品 N+1。"""
    if not jewelries:
        return jewelries

    jewelry_ids = [j.id for j in jewelries]
    boms = db.query(Bom).filter(Bom.jewelry_id.in_(jewelry_ids)).all()
    bom_by_jewelry: dict[str, list] = {}
    part_ids = set()
    for b in boms:
        bom_by_jewelry.setdefault(b.jewelry_id, []).append(b)
        part_ids.add(b.part_id)

    part_map = {}
    if part_ids:
        part_map = {
            p.id: p
            for p in db.query(Part).filter(Part.id.in_(list(part_ids))).all()
        }

    for j in jewelries:
        cost = compute_jewelry_cost(j, bom_by_jewelry.get(j.id, []), part_map)
        j.material_cost = float(cost["material_cost"])
        j.total_cost = float(cost["total_cost"])
        j.has_incomplete_cost = cost["has_incomplete_cost"]
    return jewelries
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_jewelry_cost.py -v`
Expected: PASS（含新增 3 个 + Task 1 的 4 个）

- [ ] **Step 5: 提交**

```bash
git add services/jewelry_cost.py tests/test_jewelry_cost.py
git commit -m "feat(cost): add attach_jewelry_costs batch helper"
```

---

### Task 4: Schema + API 返回成本

**Files:**
- Modify: `schemas/jewelry.py`（`JewelryResponse`）
- Modify: `api/jewelries.py`
- Test: `tests/test_api_jewelry_cost.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_api_jewelry_cost.py`:

```python
import pytest
from services.jewelry import create_jewelry, update_jewelry
from services.part import create_part, update_part_cost
from services.bom import set_bom


def _make_jewelry_with_cost(db):
    p1 = create_part(db, {"name": "珠", "category": "小配件"})
    p2 = create_part(db, {"name": "链", "category": "链条"})
    update_part_cost(db, p1.id, "purchase_cost", 0.05)
    update_part_cost(db, p2.id, "purchase_cost", 2.0)
    j = create_jewelry(db, {"name": "项链A", "category": "单件"})
    set_bom(db, j.id, p1.id, 10)
    set_bom(db, j.id, p2.id, 1)
    update_jewelry(db, j.id, {"handcraft_cost": 1.0})
    return j


def test_get_jewelry_includes_cost(client, db):
    j = _make_jewelry_with_cost(db)
    resp = client.get(f"/api/jewelries/{j.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert pytest.approx(data["material_cost"], abs=0.001) == 2.5
    assert pytest.approx(data["handcraft_cost"], abs=0.001) == 1.0
    assert pytest.approx(data["total_cost"], abs=0.001) == 3.5
    assert data["has_incomplete_cost"] is False


def test_list_jewelries_includes_cost(client, db):
    j = _make_jewelry_with_cost(db)
    resp = client.get("/api/jewelries/")
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["id"] == j.id)
    assert pytest.approx(row["total_cost"], abs=0.001) == 3.5
    assert row["has_incomplete_cost"] is False


def test_get_jewelry_incomplete_cost_flag(client, db):
    p = create_part(db, {"name": "无价件", "category": "小配件"})  # unit_cost None
    j = create_jewelry(db, {"name": "X", "category": "单件"})
    set_bom(db, j.id, p.id, 1)
    resp = client.get(f"/api/jewelries/{j.id}")
    data = resp.json()
    assert data["has_incomplete_cost"] is True
    assert pytest.approx(data["material_cost"], abs=0.001) == 0.0


def test_get_jewelry_no_bom_incomplete(client, db):
    j = create_jewelry(db, {"name": "裸件", "category": "单件"})
    update_jewelry(db, j.id, {"handcraft_cost": 5.0})
    resp = client.get(f"/api/jewelries/{j.id}")
    data = resp.json()
    assert data["has_incomplete_cost"] is True
    assert pytest.approx(data["material_cost"], abs=0.001) == 0.0
    assert pytest.approx(data["total_cost"], abs=0.001) == 5.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_api_jewelry_cost.py -v`
Expected: FAIL — `KeyError: 'material_cost'`（响应里还没有该字段）

- [ ] **Step 3: 改 schema**

在 `schemas/jewelry.py` 的 `JewelryResponse` 里，`handcraft_cost` 行之后、`status` 行之前插入三行：

```python
    material_cost: Optional[float] = None
    total_cost: Optional[float] = None
    has_incomplete_cost: Optional[bool] = None
```

- [ ] **Step 4: 改 API**

在 `api/jewelries.py` import 区加：

```python
from services.jewelry_cost import attach_jewelry_costs
```

把 `api_list_jewelries` 改为：

```python
@router.get("/", response_model=List[JewelryResponse])
def api_list_jewelries(status: Optional[str] = None, category: Optional[str] = None, name: Optional[str] = None, db: Session = Depends(get_db)):
    with service_errors():
        jewelries = list_jewelries(db, status=status, category=category, name=name)
    attach_jewelry_costs(db, jewelries)
    return jewelries
```

把 `api_get_jewelry` 改为：

```python
@router.get("/{jewelry_id}", response_model=JewelryResponse)
def api_get_jewelry(jewelry_id: str, db: Session = Depends(get_db)):
    jewelry = get_jewelry(db, jewelry_id)
    if jewelry is None:
        raise HTTPException(status_code=404, detail=f"Jewelry {jewelry_id} not found")
    attach_jewelry_costs(db, [jewelry])
    return jewelry
```

> 说明：`create / update / copy / status` 端点不挂成本，这些响应里三个字段为 `null`（前端的新建/编辑流程不展示成本）。

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_api_jewelry_cost.py -v`
Expected: PASS（4 个）

- [ ] **Step 6: 跑相关回归**

Run: `pytest tests/test_jewelry.py tests/test_api_cost_snapshot.py tests/test_jewelry_cost.py -v`
Expected: PASS（确保 JewelryResponse 改动没破坏既有饰品测试）

- [ ] **Step 7: 提交**

```bash
git add schemas/jewelry.py api/jewelries.py tests/test_api_jewelry_cost.py
git commit -m "feat(jewelry): expose live material/total cost on GET endpoints"
```

---

### Task 5: 前端详情页加 物料成本 / 总成本

**Files:**
- Modify: `frontend/src/views/jewelries/JewelryDetail.vue`

- [ ] **Step 1: import NTooltip**

把 `JewelryDetail.vue` 的 naive-ui import 块（117-121 行）改为（在 `NModal, NAlert,` 之后加 `NTooltip`）：

```javascript
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NEmpty, NDivider, NSelect, NInputNumber, NPopconfirm, NImage,
  NModal, NAlert, NTooltip,
} from 'naive-ui'
```

- [ ] **Step 2: 加两行 descriptions**

在 `JewelryDetail.vue` 的"手工费"那一行（47 行）之后插入：

```html
          <n-descriptions-item label="物料成本">{{ jewelry.material_cost != null ? fmtMoney(jewelry.material_cost) : '-' }}</n-descriptions-item>
          <n-descriptions-item label="总成本">
            <span>{{ jewelry.total_cost != null ? fmtMoney(jewelry.total_cost) : '-' }}</span>
            <n-tooltip v-if="jewelry.has_incomplete_cost" trigger="hover">
              <template #trigger>
                <span style="color:#f0a020; margin-left:4px; cursor:help;">⚠️</span>
              </template>
              成本不完整：部分配件未录入成本，或饰品缺少 BOM
            </n-tooltip>
          </n-descriptions-item>
```

- [ ] **Step 3: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功，无 `NTooltip is not defined` / 模板编译错误。

- [ ] **Step 4: 人工核验**

启动 `python main.py` + `cd frontend && npm run dev`，打开一个有 BOM 且配件有成本的饰品详情页：
- "物料成本""总成本"两行出现，总成本 = 物料 + 手工费；
- 打开一个缺配件成本或无 BOM 的饰品，总成本旁出现 ⚠️，悬停显示提示文案。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/jewelries/JewelryDetail.vue
git commit -m "feat(jewelry-ui): show material/total cost on detail page"
```

---

### Task 6: 前端列表页加 总成本 列

**Files:**
- Modify: `frontend/src/views/jewelries/JewelryList.vue`

- [ ] **Step 1: import NTooltip**

把 `JewelryList.vue` 的 naive-ui import 块（117-120 行）改为（在 `NDropdown, NAlert,` 之后加 `NTooltip`）：

```javascript
import {
  NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem,
  NModal, NDataTable, NSpin, NEmpty, NImage, NDropdown, NAlert, NTooltip,
} from 'naive-ui'
```

- [ ] **Step 2: 加列**

在 `JewelryList.vue` 的列定义里，"批发价"列（423 行）之后插入这一列（`h`、`fmtMoney`、`NTooltip` 均已可用）：

```javascript
  {
    title: '总成本',
    key: 'total_cost',
    width: 120,
    render: (r) => {
      if (r.total_cost == null) return '-'
      const main = h('span', {}, fmtMoney(r.total_cost))
      const warn = r.has_incomplete_cost
        ? h('span', { style: 'color:#f0a020; margin-left:4px; cursor:help;' }, '⚠️')
        : null
      const breakdown = `物料 ${fmtMoney(r.material_cost ?? 0)} ＋ 手工费 ${fmtMoney(r.handcraft_cost ?? 0)}`
        + (r.has_incomplete_cost ? '（成本不完整）' : '')
      return h(NTooltip, { trigger: 'hover' }, {
        trigger: () => h('span', { style: 'cursor:help;' }, [main, warn]),
        default: () => breakdown,
      })
    },
  },
```

- [ ] **Step 3: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功，无报错。

- [ ] **Step 4: 人工核验**

`npm run dev` 打开饰品列表：
- 新增"总成本"列显示合计数；
- 鼠标悬停显示"物料 X ＋ 手工费 Y"拆分；
- 缺成本的行显示 ⚠️，悬停文案带"（成本不完整）"。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/jewelries/JewelryList.vue
git commit -m "feat(jewelry-ui): add total-cost column with breakdown tooltip to list"
```

---

### Task 7: 全量回归

- [ ] **Step 1: 跑后端全量测试**

Run: `pytest -q`
Expected: PASS（无新增失败；重点关注 `test_jewelry*`、`test_api_jewelry_cost`、`test_api_cost_snapshot`、`test_jewelry_cost`）

- [ ] **Step 2: 前端构建**

Run: `cd frontend && npm run build`
Expected: 构建成功。

- [ ] **Step 3: 提交（如有 lockfile/构建产物变更则一并提交，否则跳过）**

```bash
git status
```

---

## Self-Review

**1. Spec coverage（对照已确认的 5 条范围）：**
- ① 抽公共纯函数 → Task 1（`compute_jewelry_cost`）+ Task 2（快照复用）✅
- ② 实时成本接口/字段（不存储）→ Task 3（`attach_jewelry_costs`）+ Task 4（schema/API）✅
- ③ 成本不全按 0 计 + ⚠️ → `compute_jewelry_cost` 的 `has_incomplete_cost`（Task 1 测试覆盖：缺 unit_cost / 缺件 / 无 BOM）+ 前端 ⚠️（Task 5/6）✅
- ④ 详情页 物料/手工费/总成本 三行 → Task 5（手工费行已存在，补两行）✅
- ⑤ 列表页 总成本 列 + 悬停拆分 + ⚠️，批量聚合避免 N+1 → Task 6 + `attach_jewelry_costs` 单次 BOM/Part 查询 ✅

**2. Placeholder scan：** 无 TBD/TODO；每个改动步骤均给出完整代码与确切文件/行号。

**3. Type consistency：**
- `compute_jewelry_cost` 返回键 `material_cost/handcraft_cost/total_cost/has_incomplete_cost/bom_details` 在 Task 2、Task 3 调用处一致；cost 数值为 Decimal，API/attach 层 `float(...)` 转换一致。
- `attach_jewelry_costs(db, list) -> list` 签名在 Task 3 定义、Task 4 调用一致。
- 新字段 `material_cost/total_cost/has_incomplete_cost` 在 schema（Task 4）、API 测试（Task 4）、前端（Task 5/6）命名一致。

**Edge note（实现者注意）：** 快照层对"空 BOM"仍在调用纯函数前 `raise`（`order_cost_snapshot.py:49-53` 保留），因此 `compute_jewelry_cost` 里"空 BOM → 标记不完整"的分支只服务于饰品实时成本，不影响快照对外行为。
