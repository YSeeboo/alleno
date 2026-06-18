# 手工回收后端重构（received_qty 拆分 + A方案 + #2/#3 + 回执码过滤）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把手工配件的 `received_qty` 拆成「退回量 returned_qty / 被成品消耗量 consumed_qty」两个可区分来源，从根上消除双重入账与撤销歧义；同时落地 A方案（配件回收纯退料、去掉配件价→bead_cost 同步）、修 #2（自动核销改用 effective_qty 封顶）、加 #3（产出项 BOM 配件不足时上报）、给待回收接口加回执码过滤。

**Architecture:** `HandcraftPartItem` 新增 `returned_qty`/`consumed_qty` 两列作为来源真相，保留 `received_qty` 为「总已收 = returned + consumed」（既有 SQL/状态/完工/待回收 remaining 不动）。回收/撤销/自动核销在 `services/handcraft_receipt.py` 内同时维护「对应桶 + received_qty」。`ensure_schema_compat` 加列并回填（returned = 该 part_item 的 part 类型回执明细之和；consumed = received − returned）。A方案在 `api/handcraft_receipt.py` + `services/cost_sync.py` 去掉配件价→bead_cost。回执码过滤加到 `services/handcraft.py` 的待回收查询。

**Tech Stack:** FastAPI + SQLAlchemy（Postgres）、Decimal/float 库存、pytest（DB-backed，**必须用 `.venv/bin/python -m pytest`**——PATH 的 python 是 3.9 会因 `|` 语法崩溃；测试较慢 ~3-4s/项）。

---

## 关键既有事实（实现者须知）

- **库存无 stock 列**：当前库存 = `SUM(inventory_log.change_qty)`。`services/inventory.py` 提供 `add_stock(db, type, id, qty, reason)`、`deduct_stock(...)`、`batch_get_stock(db, type, [ids]) -> {id: float}`。
- **回收逻辑全在 `services/handcraft_receipt.py`**（此文件在 origin/main 与本地 main 一致）。核心私有函数：`_apply_receive`、`_auto_consume_parts`、`_auto_consume_child_parts`、`_reverse_receive`、`_reverse_auto_consume_parts`、`_reverse_auto_consume_child_parts`、`_effective_qty`、`_check_handcraft_order_completion`。
- `_effective_qty(db, oi, item_type)`：对 `item_type=="part"` 返回配货实际数量覆盖值（勾选且填了 actual_qty 时）否则 `float(oi.qty)`；非 part 一律 `float(oi.qty)`。**这是配件「实际发出量」的权威来源**，所有上限都用它。
- **当前**（拆分前）`_apply_receive` 对 part 直接 `received_qty += qty` 并 `add_stock`；`_auto_consume_parts` 也 `received_qty += actual` 但**不动库存**，且封顶用 `pi.qty`（这是 #2 的 bug）。两者共用 `received_qty`（这是 #1/#4 的根因）。
- **完工判定** `_check_handcraft_order_completion` 用 `received_qty >= _effective_qty`——保留 `received_qty` 为总量后**此函数不用改**。
- **A方案现状**：`api/handcraft_receipt.py` 在 create/add 端点调用 `detect_handcraft_bead_cost_diffs`（cost_sync）把 part 行的 price 同步到 `Part.bead_cost`。`detect_handcraft_bead_cost_diffs` 仅被这两处调用。
- **迁移模式**：`database.py` 的 `ensure_schema_compat()`（约 201-216 行）已有「`inspector.has_table` → `ALTER TABLE ... ADD COLUMN` → `UPDATE` 数据迁移」的现成范式，新列照此追加。
- **测试基底**：本计划基于**本地 main（handcraft lineage，最新 handcraft 代码）**执行，不是 origin/main。`tests/conftest.py` 的 `db` fixture 每个测试前 truncate；`create_all()` 按模型建表，所以新列在测试库自动存在（无需依赖 ALTER）。
- 测试用服务层直接构造（避开 API 形状猜测）：`services.part.create_part`、`services.jewelry.create_jewelry`、`services.bom.set_bom`、`services.inventory.add_stock/batch_get_stock`、`services.handcraft.create_handcraft_order/send_handcraft_order`、`services.handcraft_receipt.create_handcraft_receipt/delete_handcraft_receipt`。

---

## File Structure

- **Modify** `models/handcraft_order.py` — `HandcraftPartItem` 加 `returned_qty`/`consumed_qty` 两列。
- **Modify** `database.py` — `ensure_schema_compat`：加列 + 抽一个可测的回填函数 `backfill_handcraft_part_counters(conn)`。
- **Modify** `services/handcraft_receipt.py` — 收/撤/自动核销维护双桶；自动核销改 effective 封顶（#2）+ 上报不足（#3）。
- **Modify** `schemas/handcraft_receipt.py` — 回执响应加 `parts_shortfall` 字段。
- **Modify** `api/handcraft_receipt.py` — 去掉配件价→bead_cost（A方案）；把 #3 不足挂到响应。
- **Modify** `services/cost_sync.py` — 删除只被手工回收用的 `detect_handcraft_bead_cost_diffs`。
- **Modify** `services/handcraft.py` — `list_handcraft_pending_receive_items` 加 `receipt_code` 过滤。
- **Modify** `api/handcraft.py` — 待回收接口加 `receipt_code` 查询参数。
- **Test** `tests/test_handcraft_received_split.py`（新）、`tests/test_handcraft_backfill.py`（新）、调整 `tests/test_api_handcraft_receipt.py` / `tests/test_cost_sync.py` 中关于 bead_cost 的断言。

---

### Task 1: 模型加列 `returned_qty` / `consumed_qty`

**Files:**
- Modify: `models/handcraft_order.py`（`HandcraftPartItem`，约 50 行 `received_qty` 之后）
- Test: `tests/test_handcraft_received_split.py`（新）

- [ ] **Step 1: 写失败测试**

Create `tests/test_handcraft_received_split.py`:

```python
from services.part import create_part
from services.inventory import add_stock
from services.handcraft import create_handcraft_order, send_handcraft_order
from models.handcraft_order import HandcraftPartItem


def _send_order_with_part(db, qty=100, stock=1000):
    part = create_part(db, {"name": "珠", "category": "小配件"})
    add_stock(db, "part", part.id, stock, "测试入库")
    order = create_handcraft_order(db, "商家A", parts=[{"part_id": part.id, "qty": qty}])
    send_handcraft_order(db, order.id)
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).first()
    return part, order, pi


def test_new_part_item_has_zero_split_counters(db):
    _, _, pi = _send_order_with_part(db)
    assert float(pi.returned_qty or 0) == 0.0
    assert float(pi.consumed_qty or 0) == 0.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_handcraft_received_split.py::test_new_part_item_has_zero_split_counters -v`
Expected: FAIL — `AttributeError: 'HandcraftPartItem' object has no attribute 'returned_qty'`

- [ ] **Step 3: 加列**

在 `models/handcraft_order.py` 的 `HandcraftPartItem` 里，`received_qty` 那一行（`received_qty = Column(Numeric(10, 4), nullable=True, default=0)`）之后插入：

```python
    # Split sources of received_qty (received_qty == returned_qty + consumed_qty):
    #   returned_qty — surplus parts physically returned to stock (moves inventory)
    #   consumed_qty — parts embodied into received outputs via BOM auto-consume (no inventory move)
    returned_qty = Column(Numeric(10, 4), nullable=True, default=0)
    consumed_qty = Column(Numeric(10, 4), nullable=True, default=0)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_handcraft_received_split.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add models/handcraft_order.py tests/test_handcraft_received_split.py
git commit -m "feat(handcraft): add returned_qty/consumed_qty columns to part item"
```

---

### Task 2: 迁移加列 + 可测回填函数

**Files:**
- Modify: `database.py`（`ensure_schema_compat`，handcraft_part_item 段约 201-216 行附近）
- Test: `tests/test_handcraft_backfill.py`（新）

回填规则：`returned_qty = Σ(该 part_item 的 item_type='part' 回执明细 qty)`；`consumed_qty = received_qty − returned_qty`（钳到 ≥0）。

- [ ] **Step 1: 写失败测试**

Create `tests/test_handcraft_backfill.py`:

```python
from decimal import Decimal
from sqlalchemy import text

from services.part import create_part
from services.inventory import add_stock
from services.handcraft import create_handcraft_order, send_handcraft_order
from models.handcraft_order import HandcraftPartItem
from models.handcraft_receipt import HandcraftReceipt, HandcraftReceiptItem
from database import backfill_handcraft_part_counters


def test_backfill_splits_received_into_returned_and_consumed(db):
    part = create_part(db, {"name": "珠", "category": "小配件"})
    add_stock(db, "part", part.id, 1000, "测试入库")
    order = create_handcraft_order(db, "商家A", parts=[{"part_id": part.id, "qty": 100}])
    send_handcraft_order(db, order.id)
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).first()

    # Simulate legacy state: received_qty=70, of which 30 came from a direct
    # part receipt and 40 from auto-consume. Counters not yet split.
    pi.received_qty = 70
    pi.returned_qty = 0
    pi.consumed_qty = 0
    receipt = HandcraftReceipt(id="HR-BF1", supplier_name="商家A", status="未付款")
    db.add(receipt)
    db.flush()
    db.add(HandcraftReceiptItem(
        handcraft_receipt_id="HR-BF1",
        handcraft_part_item_id=pi.id,
        item_id=part.id,
        item_type="part",
        qty=30,
        unit="个",
    ))
    db.flush()

    backfill_handcraft_part_counters(db.connection())
    db.expire(pi)

    assert float(pi.returned_qty) == 30.0   # from the part receipt
    assert float(pi.consumed_qty) == 40.0   # 70 - 30
    assert float(pi.received_qty) == 70.0   # unchanged total
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_handcraft_backfill.py -v`
Expected: FAIL — `ImportError: cannot import name 'backfill_handcraft_part_counters'`

- [ ] **Step 3: 实现回填函数 + 接到 ensure_schema_compat**

在 `database.py` 顶部已 `from sqlalchemy import text`（确认；若无则在导入区补上）。在 `ensure_schema_compat` 定义之前（模块级）加函数：

```python
def backfill_handcraft_part_counters(conn):
    """One-time split of handcraft_part_item.received_qty into returned/consumed.

    returned_qty := Σ qty of this part_item's item_type='part' receipt rows
                    (direct surplus returns).
    consumed_qty := max(received_qty - returned_qty, 0)  (the rest = auto-consumed).

    Idempotent: recomputes both columns from receipts each run, so re-running
    after more receipts land stays correct. Only rewrites rows where the split
    is stale, to avoid churn.
    """
    conn.execute(text("""
        WITH ret AS (
            SELECT hri.handcraft_part_item_id AS pid,
                   COALESCE(SUM(hri.qty), 0) AS returned
            FROM handcraft_receipt_item hri
            WHERE hri.item_type = 'part'
              AND hri.handcraft_part_item_id IS NOT NULL
            GROUP BY hri.handcraft_part_item_id
        )
        UPDATE handcraft_part_item p
        SET returned_qty = COALESCE(ret.returned, 0),
            consumed_qty = GREATEST(COALESCE(p.received_qty, 0) - COALESCE(ret.returned, 0), 0)
        FROM ret
        WHERE p.id = ret.pid
    """))
    # Part items with received_qty but no part receipts → all consumed.
    conn.execute(text("""
        UPDATE handcraft_part_item p
        SET returned_qty = 0,
            consumed_qty = COALESCE(p.received_qty, 0)
        WHERE COALESCE(p.received_qty, 0) > 0
          AND NOT EXISTS (
            SELECT 1 FROM handcraft_receipt_item hri
            WHERE hri.handcraft_part_item_id = p.id AND hri.item_type = 'part'
          )
    """))
```

然后在 `ensure_schema_compat` 的 handcraft_part_item 段（即现有处理 `received_qty`/`status` 列的 `if inspector.has_table("handcraft_part_item"):` 块内），在已有逻辑之后追加：

```python
            cols2 = {col["name"] for col in inspector.get_columns("handcraft_part_item")}
            added_split = False
            if "returned_qty" not in cols2:
                conn.execute(text("ALTER TABLE handcraft_part_item ADD COLUMN returned_qty NUMERIC(10,4) DEFAULT 0"))
                logger.warning("Added missing handcraft_part_item.returned_qty column")
                added_split = True
            if "consumed_qty" not in cols2:
                conn.execute(text("ALTER TABLE handcraft_part_item ADD COLUMN consumed_qty NUMERIC(10,4) DEFAULT 0"))
                logger.warning("Added missing handcraft_part_item.consumed_qty column")
                added_split = True
            if added_split:
                backfill_handcraft_part_counters(conn)
                logger.warning("Backfilled handcraft_part_item returned_qty/consumed_qty")
```

> 注意：用 `conn`（`ensure_schema_compat` 里已有的连接变量名——实现者先读该函数确认连接变量名，若不是 `conn` 则改成实际名）。`backfill_handcraft_part_counters` 接收该连接。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_handcraft_backfill.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add database.py tests/test_handcraft_backfill.py
git commit -m "feat(handcraft): migrate + backfill returned_qty/consumed_qty"
```

---

### Task 3: `_apply_receive` 维护 returned 桶（配件直接退料）

**Files:**
- Modify: `services/handcraft_receipt.py`（`_apply_receive`，约 108-128 行）
- Test: `tests/test_handcraft_received_split.py`（追加）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_handcraft_received_split.py` 末尾追加：

```python
from services.handcraft_receipt import create_handcraft_receipt
from services.inventory import batch_get_stock


def test_direct_part_receive_records_returned_and_adds_stock(db):
    part, order, pi = _send_order_with_part(db, qty=100, stock=1000)
    # after send: stock = 1000 - 100 = 900
    assert batch_get_stock(db, "part", [part.id])[part.id] == 900.0

    create_handcraft_receipt(db, "商家A", items=[
        {"handcraft_part_item_id": pi.id, "qty": 30},
    ])
    db.expire(pi)
    assert float(pi.returned_qty) == 30.0
    assert float(pi.consumed_qty or 0) == 0.0
    assert float(pi.received_qty) == 30.0
    # surplus returned → stock back up by 30
    assert batch_get_stock(db, "part", [part.id])[part.id] == 930.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest "tests/test_handcraft_received_split.py::test_direct_part_receive_records_returned_and_adds_stock" -v`
Expected: FAIL — `returned_qty` 仍为 0（当前 `_apply_receive` 不写 returned_qty）。

- [ ] **Step 3: 改 `_apply_receive`**

把 `services/handcraft_receipt.py` 的 `_apply_receive` 整体替换为：

```python
def _apply_receive(db: Session, order_item, item_type: str, qty: float) -> dict:
    """Add qty to received_qty, update item status, add stock.

    For part items (direct surplus return): also bump returned_qty.
    For jewelry/part-output items: add stock and auto-consume the sent parts
    via BOM (which bumps the parts' consumed_qty). Returns the BOM shortfall
    dict {part_id: qty} from auto-consume (empty when fully covered / N/A).
    """
    order_item.received_qty = float(order_item.received_qty or 0) + qty
    shortfall: dict[str, float] = {}
    if item_type == "part":
        order_item.returned_qty = float(order_item.returned_qty or 0) + qty
        add_stock(db, "part", order_item.part_id, qty, "手工收回")
    else:
        if order_item.jewelry_id:
            add_stock(db, "jewelry", order_item.jewelry_id, qty, "手工收回")
            shortfall = _auto_consume_parts(db, order_item.handcraft_order_id, order_item.jewelry_id, qty)
        elif order_item.part_id:
            add_stock(db, "part", order_item.part_id, qty, "手工收回")
            shortfall = _auto_consume_child_parts(db, order_item.handcraft_order_id, order_item.part_id, qty)
    if float(order_item.received_qty) >= _effective_qty(db, order_item, item_type):
        order_item.status = "已收回"
    else:
        order_item.status = "制作中"
    return shortfall
```

> 此处 `_auto_consume_*` 改为返回 shortfall（Task 4 实现）。本任务先改 `_apply_receive`；若此时 `_auto_consume_*` 尚未返回 dict，jewelry 路径的 `shortfall` 会是 `None`——这不影响本任务的 part 测试。Task 4 会让它们返回 dict。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest "tests/test_handcraft_received_split.py::test_direct_part_receive_records_returned_and_adds_stock" -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add services/handcraft_receipt.py tests/test_handcraft_received_split.py
git commit -m "feat(handcraft): direct part receive records returned_qty"
```

---

### Task 4: 自动核销写 consumed 桶 + effective 封顶(#2) + 不足上报(#3)

**Files:**
- Modify: `services/handcraft_receipt.py`（`_auto_consume_parts` 约 131-170、`_auto_consume_child_parts` 约 173-206）
- Test: `tests/test_handcraft_received_split.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
from services.jewelry import create_jewelry
from services.bom import set_bom
from models.handcraft_order import HandcraftJewelryItem


def test_jewelry_receive_consumes_parts_into_consumed_bucket(db):
    part = create_part(db, {"name": "珠", "category": "小配件"})
    add_stock(db, "part", part.id, 1000, "入库")
    jewelry = create_jewelry(db, {"name": "项链", "category": "单件"})
    set_bom(db, jewelry.id, part.id, 2)  # 1 件饰品吃 2 颗珠
    order = create_handcraft_order(
        db, "商家A",
        parts=[{"part_id": part.id, "qty": 100}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 10}],
    )
    send_handcraft_order(db, order.id)
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).first()
    ji = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=order.id).first()

    create_handcraft_receipt(db, "商家A", items=[
        {"handcraft_jewelry_item_id": ji.id, "qty": 10},
    ])
    db.expire(pi)
    # 10 件 × 2 = 20 颗进入 consumed，不动库存（库存仍是 send 后的 900）
    assert float(pi.consumed_qty) == 20.0
    assert float(pi.returned_qty or 0) == 0.0
    assert float(pi.received_qty) == 20.0
    assert batch_get_stock(db, "part", [part.id])[part.id] == 900.0


def test_auto_consume_reports_shortfall_when_parts_insufficient(db):
    part = create_part(db, {"name": "珠", "category": "小配件"})
    add_stock(db, "part", part.id, 1000, "入库")
    jewelry = create_jewelry(db, {"name": "项链", "category": "单件"})
    set_bom(db, jewelry.id, part.id, 10)  # 需要很多
    order = create_handcraft_order(
        db, "商家A",
        parts=[{"part_id": part.id, "qty": 5}],   # 只发了 5 颗
        jewelries=[{"jewelry_id": jewelry.id, "qty": 10}],  # 需 100 颗
    )
    send_handcraft_order(db, order.id)
    ji = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=order.id).first()

    receipt = create_handcraft_receipt(db, "商家A", items=[
        {"handcraft_jewelry_item_id": ji.id, "qty": 10},
    ])
    # 95 颗缺口应被上报（100 需求 - 5 实发）
    assert any(
        s["part_id"] == part.id and abs(s["shortfall_qty"] - 95.0) < 1e-6
        for s in receipt.parts_shortfall
    )
```

> 第二个测试断言 `receipt.parts_shortfall`——该聚合在 Task 5 实装。本任务先让 `_auto_consume_*` 返回 shortfall dict 并被 `create_handcraft_receipt` 收集成 `receipt.parts_shortfall`（Task 5 完整做响应/接口）。为让本任务可独立验证，**本任务也在 `create_handcraft_receipt`/`add_handcraft_receipt_items` 内把 `_apply_receive` 的返回聚合到 `receipt.parts_shortfall`**（见 Step 3 末）。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest "tests/test_handcraft_received_split.py::test_jewelry_receive_consumes_parts_into_consumed_bucket" "tests/test_handcraft_received_split.py::test_auto_consume_reports_shortfall_when_parts_insufficient" -v`
Expected: FAIL（consumed_qty 未写 / `parts_shortfall` 不存在）。

- [ ] **Step 3: 重写两个自动核销函数 + 聚合 shortfall**

把 `_auto_consume_parts` 替换为：

```python
def _auto_consume_parts(db: Session, handcraft_order_id: str, jewelry_id: str, jewelry_qty: float) -> dict:
    """When jewelry is received, auto-consume the order's sent parts per BOM.

    Consumption per part_id = BOM qty_per_unit × jewelry_qty, distributed across
    that part's rows, each capped at its remaining capacity
    `_effective_qty(pi) - received_qty` (effective = picking actual_qty override
    when set — fixes the old pi.qty cap). Writes consumed_qty (NOT returned_qty)
    and bumps received_qty; moves NO stock. Returns {part_id: unmet_qty} for
    parts whose BOM demand exceeded what was sent.
    """
    from models.bom import Bom
    from collections import defaultdict

    bom_rows = db.query(Bom).filter_by(jewelry_id=jewelry_id).all()
    if not bom_rows:
        return {}
    bom_map = {b.part_id: float(b.qty_per_unit) for b in bom_rows}
    part_items = db.query(HandcraftPartItem).filter_by(handcraft_order_id=handcraft_order_id).all()
    by_part: dict[str, list] = defaultdict(list)
    for pi in part_items:
        if pi.part_id in bom_map:
            by_part[pi.part_id].append(pi)

    shortfall: dict[str, float] = {}
    for part_id, qty_per in bom_map.items():
        total_consumption = qty_per * jewelry_qty
        for pi in by_part.get(part_id, []):
            if total_consumption <= 0:
                break
            available = _effective_qty(db, pi, "part") - float(pi.received_qty or 0)
            actual = min(total_consumption, available)
            if actual <= 0:
                continue
            pi.consumed_qty = float(pi.consumed_qty or 0) + actual
            pi.received_qty = float(pi.received_qty or 0) + actual
            if float(pi.received_qty) >= _effective_qty(db, pi, "part"):
                pi.status = "已收回"
            else:
                pi.status = "制作中"
            total_consumption -= actual
        if total_consumption > 1e-9:
            shortfall[part_id] = total_consumption
    db.flush()
    return shortfall
```

把 `_auto_consume_child_parts` 替换为同构版本（唯一差别：BOM 来自 `PartBom`，键为 `parent_part_id`/`child_part_id`）：

```python
def _auto_consume_child_parts(db: Session, handcraft_order_id: str, parent_part_id: str, parent_qty: float) -> dict:
    """When a composite part output is received, auto-consume its child parts
    per part_bom. Same semantics as _auto_consume_parts: writes consumed_qty,
    effective cap, no stock move, returns {child_part_id: unmet_qty}."""
    from models.part_bom import PartBom
    from collections import defaultdict

    bom_rows = db.query(PartBom).filter_by(parent_part_id=parent_part_id).all()
    if not bom_rows:
        return {}
    bom_map = {b.child_part_id: float(b.qty_per_unit) for b in bom_rows}
    part_items = db.query(HandcraftPartItem).filter_by(handcraft_order_id=handcraft_order_id).all()
    by_part: dict[str, list] = defaultdict(list)
    for pi in part_items:
        if pi.part_id in bom_map:
            by_part[pi.part_id].append(pi)

    shortfall: dict[str, float] = {}
    for part_id, qty_per in bom_map.items():
        total_consumption = qty_per * parent_qty
        for pi in by_part.get(part_id, []):
            if total_consumption <= 0:
                break
            available = _effective_qty(db, pi, "part") - float(pi.received_qty or 0)
            actual = min(total_consumption, available)
            if actual <= 0:
                continue
            pi.consumed_qty = float(pi.consumed_qty or 0) + actual
            pi.received_qty = float(pi.received_qty or 0) + actual
            if float(pi.received_qty) >= _effective_qty(db, pi, "part"):
                pi.status = "已收回"
            else:
                pi.status = "制作中"
            total_consumption -= actual
        if total_consumption > 1e-9:
            shortfall[part_id] = total_consumption
    db.flush()
    return shortfall
```

在 `create_handcraft_receipt` 里，`_apply_receive` 的调用点改为收集 shortfall。当前是：

```python
        _apply_receive(db, order_item, item_type, qty)
        affected_orders.add(hc_order_id)
```

替换为（同时在函数顶部、`affected_orders = set()` 附近加 `shortfall_acc: dict[str, float] = {}`）：

```python
        sf = _apply_receive(db, order_item, item_type, qty)
        for pid, q in (sf or {}).items():
            shortfall_acc[pid] = shortfall_acc.get(pid, 0.0) + q
        affected_orders.add(hc_order_id)
```

并在 `create_handcraft_receipt` 末尾、`return receipt` 之前，把累积的 shortfall 解析成带名字的列表挂到 receipt（非持久化属性）：

```python
    receipt.parts_shortfall = _resolve_parts_shortfall(db, shortfall_acc)
```

在 `add_handcraft_receipt_items` 里做同样的 `shortfall_acc` 收集 + 末尾 `receipt.parts_shortfall = _resolve_parts_shortfall(db, shortfall_acc)`。

在文件内新增辅助函数（`Part` 已在文件顶部 import）：

```python
def _resolve_parts_shortfall(db: Session, shortfall_acc: dict) -> list:
    """Turn {part_id: unmet_qty} into [{part_id, part_name, shortfall_qty}]."""
    if not shortfall_acc:
        return []
    parts = {p.id: p for p in db.query(Part).filter(Part.id.in_(list(shortfall_acc.keys()))).all()}
    return [
        {
            "part_id": pid,
            "part_name": parts[pid].name if pid in parts else pid,
            "shortfall_qty": float(qty),
        }
        for pid, qty in shortfall_acc.items()
    ]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_handcraft_received_split.py -v`
Expected: PASS（含 consumed 桶 + shortfall 两个新测试 + 之前的）

- [ ] **Step 5: 提交**

```bash
git add services/handcraft_receipt.py tests/test_handcraft_received_split.py
git commit -m "feat(handcraft): auto-consume writes consumed_qty, effective cap, reports shortfall"
```

---

### Task 5: `parts_shortfall` 上响应/接口（#3 对外可见）

**Files:**
- Modify: `schemas/handcraft_receipt.py`（`HandcraftReceiptResponse`）
- Modify: `api/handcraft_receipt.py`（create / add-items 端点把 `parts_shortfall` 放进响应）
- Test: `tests/test_api_handcraft_receipt.py`（追加一个 API 级断言）

- [ ] **Step 1: 写失败测试**

先读 `tests/test_api_handcraft_receipt.py` 顶部，复用其既有的下单/发出辅助（若有 `_create_and_send` 之类）。追加：

```python
def test_receipt_response_reports_parts_shortfall(client, db):
    from services.part import create_part
    from services.jewelry import create_jewelry
    from services.bom import set_bom
    from services.inventory import add_stock
    from services.handcraft import create_handcraft_order, send_handcraft_order
    from models.handcraft_order import HandcraftJewelryItem

    part = create_part(db, {"name": "珠", "category": "小配件"})
    add_stock(db, "part", part.id, 1000, "入库")
    jewelry = create_jewelry(db, {"name": "项链", "category": "单件"})
    set_bom(db, jewelry.id, part.id, 10)
    order = create_handcraft_order(
        db, "商家S",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 10}],
    )
    send_handcraft_order(db, order.id)
    ji = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=order.id).first()

    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "商家S",
        "items": [{"handcraft_jewelry_item_id": ji.id, "qty": 10}],
    })
    assert resp.status_code == 201
    sf = resp.json()["parts_shortfall"]
    assert any(x["part_id"] == part.id and abs(x["shortfall_qty"] - 95.0) < 1e-6 for x in sf)
```

- [ ] **Step 2: 跑确认失败**

Run: `.venv/bin/python -m pytest "tests/test_api_handcraft_receipt.py::test_receipt_response_reports_parts_shortfall" -v`
Expected: FAIL — 响应无 `parts_shortfall` 键（KeyError）。

- [ ] **Step 3: schema 加字段**

在 `schemas/handcraft_receipt.py` 的 `HandcraftReceiptResponse` 加（与既有 `cost_diffs` 之类附加字段同区；先读该类确认风格）：

```python
    parts_shortfall: list[dict] = []
```

- [ ] **Step 4: API 把 shortfall 放进响应**

在 `api/handcraft_receipt.py` 的 `api_create_handcraft_receipt` 里，构造 `resp = HandcraftReceiptResponse.model_validate(receipt)` 之后、`return resp` 之前加：

```python
    resp.parts_shortfall = getattr(receipt, "parts_shortfall", []) or []
```

`api_add_handcraft_receipt_items` 里对其 `resp` 做同样赋值。

- [ ] **Step 5: 跑确认通过**

Run: `.venv/bin/python -m pytest "tests/test_api_handcraft_receipt.py::test_receipt_response_reports_parts_shortfall" -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add schemas/handcraft_receipt.py api/handcraft_receipt.py tests/test_api_handcraft_receipt.py
git commit -m "feat(handcraft): expose auto-consume parts shortfall on receipt response"
```

---

### Task 6: 撤销按来源精确回退（根治 #4）

**Files:**
- Modify: `services/handcraft_receipt.py`（`_reverse_receive` 约 209-228、`_reverse_auto_consume_parts` 约 231-268、`_reverse_auto_consume_child_parts` 约 271-304）
- Test: `tests/test_handcraft_received_split.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
def test_delete_part_receipt_reverses_returned_only(db):
    part, order, pi = _send_order_with_part(db, qty=100, stock=1000)
    receipt = create_handcraft_receipt(db, "商家A", items=[
        {"handcraft_part_item_id": pi.id, "qty": 30},
    ])
    db.expire(pi)
    assert float(pi.returned_qty) == 30.0
    assert batch_get_stock(db, "part", [part.id])[part.id] == 930.0

    from services.handcraft_receipt import delete_handcraft_receipt
    delete_handcraft_receipt(db, receipt.id)
    db.expire(pi)
    assert float(pi.returned_qty) == 0.0
    assert float(pi.consumed_qty or 0) == 0.0
    assert float(pi.received_qty) == 0.0
    assert batch_get_stock(db, "part", [part.id])[part.id] == 900.0


def test_delete_jewelry_receipt_reverses_consumed_only_no_stock(db):
    part = create_part(db, {"name": "珠", "category": "小配件"})
    add_stock(db, "part", part.id, 1000, "入库")
    jewelry = create_jewelry(db, {"name": "项链", "category": "单件"})
    set_bom(db, jewelry.id, part.id, 2)
    order = create_handcraft_order(
        db, "商家A",
        parts=[{"part_id": part.id, "qty": 100}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 10}],
    )
    send_handcraft_order(db, order.id)
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).first()
    ji = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=order.id).first()
    receipt = create_handcraft_receipt(db, "商家A", items=[{"handcraft_jewelry_item_id": ji.id, "qty": 10}])
    db.expire(pi)
    assert float(pi.consumed_qty) == 20.0

    from services.handcraft_receipt import delete_handcraft_receipt
    delete_handcraft_receipt(db, receipt.id)
    db.expire(pi)
    assert float(pi.consumed_qty) == 0.0
    assert float(pi.returned_qty or 0) == 0.0
    assert float(pi.received_qty) == 0.0
    # 配件库存自始至终未变（消耗不动库存）→ 仍是 send 后的 900
    assert batch_get_stock(db, "part", [part.id])[part.id] == 900.0
```

- [ ] **Step 2: 跑确认失败**

Run: `.venv/bin/python -m pytest "tests/test_handcraft_received_split.py::test_delete_part_receipt_reverses_returned_only" "tests/test_handcraft_received_split.py::test_delete_jewelry_receipt_reverses_consumed_only_no_stock" -v`
Expected: FAIL（撤销未维护 returned/consumed 桶）。

- [ ] **Step 3: 改三个 reverse 函数**

把 `_reverse_receive` 替换为：

```python
def _reverse_receive(db: Session, order_item, item_type: str, qty: float) -> None:
    """Reverse qty from received_qty; mirror of _apply_receive.

    Part (direct return): decrement returned_qty + deduct stock.
    Jewelry/part-output: deduct stock + reverse auto-consumed parts (which
    decrement consumed_qty).
    """
    order_item.received_qty = float(order_item.received_qty or 0) - qty
    if item_type == "part":
        order_item.returned_qty = float(order_item.returned_qty or 0) - qty
        deduct_stock(db, "part", order_item.part_id, qty, "手工收回撤回")
    else:
        if order_item.jewelry_id:
            deduct_stock(db, "jewelry", order_item.jewelry_id, qty, "手工收回撤回")
            _reverse_auto_consume_parts(db, order_item.handcraft_order_id, order_item.jewelry_id, qty)
        elif order_item.part_id:
            deduct_stock(db, "part", order_item.part_id, qty, "手工收回撤回")
            _reverse_auto_consume_child_parts(db, order_item.handcraft_order_id, order_item.part_id, qty)
    if float(order_item.received_qty) >= _effective_qty(db, order_item, item_type):
        order_item.status = "已收回"
    else:
        order_item.status = "制作中"
```

在 `_reverse_auto_consume_parts` 的回退循环里，把每行：

```python
            pi.received_qty = current - reverse_amount
```

替换为同时回退 consumed 桶：

```python
            pi.received_qty = current - reverse_amount
            pi.consumed_qty = float(pi.consumed_qty or 0) - reverse_amount
```

对 `_reverse_auto_consume_child_parts` 做完全相同的两行替换（它的循环结构与 `_reverse_auto_consume_parts` 一致）。

> 这两个 reverse-auto-consume 函数其余逻辑（按 BOM × qty 计算 total_to_reverse、reversed(rows) 逐行回退、状态重算）保持不变。

- [ ] **Step 4: 跑确认通过**

Run: `.venv/bin/python -m pytest tests/test_handcraft_received_split.py -v`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add services/handcraft_receipt.py tests/test_handcraft_received_split.py
git commit -m "feat(handcraft): reverse receive decrements the correct source bucket"
```

---

### Task 7: A方案 — 去掉「配件价 → bead_cost」同步

**Files:**
- Modify: `api/handcraft_receipt.py`（create / add-items 端点）
- Modify: `services/cost_sync.py`（删除 `detect_handcraft_bead_cost_diffs`）
- Modify/Remove: `tests/test_cost_sync.py` / `tests/test_api_handcraft_receipt.py` 中断言「配件价同步到 bead_cost」的用例
- Test: `tests/test_api_handcraft_receipt.py`（新增反向断言）

- [ ] **Step 1: 先定位现有依赖**

Run: `grep -rn "detect_handcraft_bead_cost_diffs\|bead_cost" tests/ api/handcraft_receipt.py services/cost_sync.py | grep -v __pycache__`
读出：① `api/handcraft_receipt.py` 调 `detect_handcraft_bead_cost_diffs` 的两处（约 68、109 行附近）；② 任何断言「手工回收 part 行 → bead_cost」的测试。

- [ ] **Step 2: 写/改测试到目标行为**

在 `tests/test_api_handcraft_receipt.py` 追加（断言配件回收**不再**产生 bead_cost 变更）：

```python
def test_part_receive_does_not_sync_bead_cost(client, db):
    from services.part import create_part
    from services.inventory import add_stock
    from services.handcraft import create_handcraft_order, send_handcraft_order
    from models.handcraft_order import HandcraftPartItem
    from models.part import Part

    part = create_part(db, {"name": "穿珠件", "category": "小配件"})
    add_stock(db, "part", part.id, 500, "入库")
    order = create_handcraft_order(db, "商家B", parts=[{"part_id": part.id, "qty": 50}])
    send_handcraft_order(db, order.id)
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).first()

    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "商家B",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 20, "price": 3.3}],
    })
    assert resp.status_code == 201
    # A方案：配件回收纯退料，不写 bead_cost；也不在 cost_diffs 里冒出 bead_cost
    assert all(d.get("field") != "bead_cost" for d in resp.json().get("cost_diffs", []))
    db.expire(db.get(Part, part.id))
    assert db.get(Part, part.id).bead_cost is None
```

同时**删除/改写**任何与之矛盾的旧用例（Step 1 找到的「断言 part 价同步 bead_cost」的测试）——删掉这些用例或改成上面的反向断言。

- [ ] **Step 3: 跑确认失败**

Run: `.venv/bin/python -m pytest "tests/test_api_handcraft_receipt.py::test_part_receive_does_not_sync_bead_cost" -v`
Expected: FAIL（当前仍会把 part 价同步进 bead_cost / cost_diffs）。

- [ ] **Step 4: 去掉 bead 同步**

在 `api/handcraft_receipt.py`：删除两处 `detect_handcraft_bead_cost_diffs(...)` 调用，以及对应的 import 名（从 `from services.cost_sync import (...)` 列表里移除 `detect_handcraft_bead_cost_diffs`）。`cost_diffs` 仍由 jewelry/assembly 两个 detect 组成，保持不变。

在 `services/cost_sync.py`：删除 `detect_handcraft_bead_cost_diffs` 函数（确认 Step 1 grep 显示它仅被 `api/handcraft_receipt.py` 调用；若别处也用则保留函数，仅去调用）。

- [ ] **Step 5: 跑确认通过 + 局部回归**

Run: `.venv/bin/python -m pytest tests/test_api_handcraft_receipt.py tests/test_cost_sync.py -v`
Expected: PASS（新反向断言通过；删改后的旧用例不再失败）

- [ ] **Step 6: 提交**

```bash
git add api/handcraft_receipt.py services/cost_sync.py tests/test_api_handcraft_receipt.py tests/test_cost_sync.py
git commit -m "feat(handcraft): drop part-price to bead_cost sync (parts = pure surplus return)"
```

---

### Task 8: 待回收接口加 `receipt_code` 过滤

**Files:**
- Modify: `services/handcraft.py`（`list_handcraft_pending_receive_items`）
- Modify: `api/handcraft.py`（`GET /handcraft/items/pending-receive`）
- Test: `tests/test_api_handcraft_receipt.py` 或 `tests/test_api_handcraft.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
def test_pending_receive_filter_by_receipt_code(client, db):
    from services.part import create_part
    from services.inventory import add_stock
    from services.handcraft import create_handcraft_order, send_handcraft_order

    p = create_part(db, {"name": "珠", "category": "小配件"})
    add_stock(db, "part", p.id, 1000, "入库")
    o1 = create_handcraft_order(db, "商家R", parts=[{"part_id": p.id, "qty": 10}])
    send_handcraft_order(db, o1.id)
    o2 = create_handcraft_order(db, "商家R", parts=[{"part_id": p.id, "qty": 20}], created_at=None)
    # 两单同商家同日会自动合并；为确保两单，给 o2 指定一个不同创建日期
    # （create_handcraft_order 在 created_at 非空时不合并）
    from datetime import date
    o2 = create_handcraft_order(db, "商家R", parts=[{"part_id": p.id, "qty": 20}], created_at=date(2020, 1, 1))
    send_handcraft_order(db, o2.id)

    code1 = db.query(type(o1)).filter_by(id=o1.id).first().receipt_code

    resp = client.get(f"/api/handcraft/items/pending-receive?receipt_code={code1}")
    assert resp.status_code == 200
    rows = resp.json()
    assert rows, "should return items for that order"
    assert all(r["handcraft_order_id"] == o1.id for r in rows)
```

> 注：`create_handcraft_order` 对「同商家、同日、pending」会自动合并；测试里用 `created_at` 区分两单（指定值时不合并）。实现者执行时如该合并规则有变，按当前 `create_handcraft_order` 实际行为调整夹具，保证存在两张不同的单。

- [ ] **Step 2: 跑确认失败**

Run: `.venv/bin/python -m pytest "tests/test_api_handcraft_receipt.py::test_pending_receive_filter_by_receipt_code" -v`
Expected: FAIL — 当前接口无 `receipt_code` 参数，返回两单的项（断言 `all(... == o1.id)` 失败）或 422。

- [ ] **Step 3: 服务层加过滤**

先读 `services/handcraft.py` 的 `list_handcraft_pending_receive_items` 当前签名与实现。把签名加一个参数：

```python
def list_handcraft_pending_receive_items(
    db: Session,
    keyword: str = None,
    supplier_name: str = None,
    date_on: date_type = None,
    exclude_part_item_ids: list[int] = None,
    exclude_jewelry_item_ids: list[int] = None,
    receipt_code: str = None,
) -> list:
```

在两条子查询（part 分支 `pq` 与 jewelry 分支 `jq`）里，各自在已有 `if supplier_name:` 过滤之后，追加：

```python
    if receipt_code:
        pq = pq.filter(HandcraftOrder.receipt_code == receipt_code.upper())
```

（jewelry 分支同理对 `jq` 加 `jq = jq.filter(HandcraftOrder.receipt_code == receipt_code.upper())`。两个子查询都已 join 了 `HandcraftOrder`，可直接过滤。`.upper()` 与 `get_handcraft_order_by_receipt_code` 的大小写不敏感一致。）

- [ ] **Step 4: API 加查询参数**

在 `api/handcraft.py` 的 `api_list_handcraft_pending_receive_items`（约 140-158 行）签名加 `receipt_code: Optional[str] = None`，并透传给服务函数 `list_handcraft_pending_receive_items(..., receipt_code=receipt_code)`。先读该端点确认它如何转发参数。

- [ ] **Step 5: 跑确认通过**

Run: `.venv/bin/python -m pytest "tests/test_api_handcraft_receipt.py::test_pending_receive_filter_by_receipt_code" -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add services/handcraft.py api/handcraft.py tests/test_api_handcraft_receipt.py
git commit -m "feat(handcraft): filter pending-receive items by receipt_code"
```

---

### Task 9: 回归

- [ ] **Step 1: 手工相关全量**

Run: `.venv/bin/python -m pytest -p no:xdist -q tests/test_handcraft_received_split.py tests/test_handcraft_backfill.py tests/test_api_handcraft_receipt.py tests/test_api_handcraft.py tests/test_handcraft.py tests/test_cost_sync.py tests/test_weight.py`
Expected: 新测试全过；既有手工/成本测试无新增失败（注意 `tests/test_weight.py` 里有**预先存在**的 handcraft 重量失败 `test_handcraft_part_item_weight`/`test_handcraft_part_update_weight`，与本计划无关——若执行前它们就红，执行后仍红即可，不要试图修）。

- [ ] **Step 2: 全量冒烟（可选，慢）**

Run: `.venv/bin/python -m pytest -p no:xdist -q`
Expected: 仅既有预存失败（bot / weight / part_cost / plating / order_todo / snapshot-not-found 等，与本计划无关）。

---

## Self-Review

**1. Spec coverage（对照确认的 4 点设计 + Stream B 后端范围）：**
- 列策略 A（保留 received_qty + 加 returned/consumed）→ Task 1 ✅
- 上限语义（两操作同受 effective−received 约束，记入不同桶）→ Task 4（available = effective − received）✅
- 残留 #1 仅可见、不硬阻止 → 未加阻止逻辑；#3 上报覆盖"不足"可见性 → Task 4/5 ✅
- 回填（returned=Σ part 回执；consumed=received−returned）→ Task 2 ✅
- A方案（去 bead_cost 同步）→ Task 7 ✅
- #2（自动核销 effective 封顶）→ Task 4 ✅
- #3（不足上报）→ Task 4 + Task 5（响应字段）✅
- 回执码过滤 → Task 8 ✅
- 撤销根治 #4 → Task 6 ✅

**2. Placeholder scan：** 各步均有完整代码/命令；无 TBD。`_auto_consume_*` 的旧体被整体替换给出。reverse 函数用"逐行替换两行"方式明确。

**3. Type consistency：**
- `_apply_receive` 现返回 `dict`（shortfall），调用点（create/add）已相应改为收集；`delete`/`update_receipt_item` 路径只调 `_reverse_receive`（返回 None，不受影响）。
- `_auto_consume_parts`/`_auto_consume_child_parts` 均返回 `dict`，与 `_apply_receive` 的聚合一致。
- `receipt.parts_shortfall` 在 service 设为 `list[dict{part_id,part_name,shortfall_qty}]`，schema 字段 `parts_shortfall: list[dict] = []`，API 透传——三处形状一致。
- 列名 `returned_qty`/`consumed_qty` 在模型、迁移、收/撤、回填中一致。

**4. 与 B2（前端）的接口契约**（供 B2 计划衔接）：
- `GET /handcraft/items/pending-receive?receipt_code=XXXXX` → 仅该单待回收项。
- `POST /handcraft-receipts/`（及 add-items）响应新增 `parts_shortfall: [{part_id, part_name, shortfall_qty}]`，供前端提示"产出项所需配件不足"。
- 配件回收不再接受/同步价格（B2 配件回收弹窗不放单价输入）。

**遗留 advisory（非本计划范围）：** `received_qty` 作为派生总量与两桶的一致性靠"成对更新"维护；若未来引入绕过 `_apply_receive/_reverse_receive` 直接改 received_qty 的路径，需同步维护两桶。
