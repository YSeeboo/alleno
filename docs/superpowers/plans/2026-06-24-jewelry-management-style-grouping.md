# 饰品管理款式归属 + 配件变体折叠 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给饰品加轻量「款式归属」（`style_group` 列 + `-A/-B` 后缀 + 添加同款）并刷新列表视觉，同时把配件变体从平铺改为可展开折叠。

**Architecture:** 后端给 jewelry 加一个 `style_group` 分组键列与「添加同款」服务/接口（复用现有 BOM 复制逻辑、自分配字母后缀 ID）；配件加一个「组合件不支持变体」守卫。前端把 JewelryList 重写为对齐 PartList 的刷新视觉 + 按 `style_group` 拼可展开分组树，并把 PartList 的平铺变体改为按 `parent_part_id` 折叠。

**Tech Stack:** FastAPI + SQLAlchemy (PostgreSQL)；Vue 3.5 + Naive UI；pytest；前端 `npm run build` 作为验证门。

## Global Constraints

- 服务函数为无状态纯函数，调用 `db.flush()`（不 `db.commit()`）；业务错误 `raise ValueError`（API 层经 `service_errors()` 转 400）。— 出自 CLAUDE.md「Service Layer」
- 库存无 stock 列：当前库存 = `SUM(change_qty) FROM inventory_log`；本特性不触碰库存。— CLAUDE.md「Inventory Model」
- 类目变更被禁止：`update_jewelry` 对任何 `category` 键 `raise ValueError`；ID 编码类目。— `services/jewelry.py`
- 加列走 additive 模式：在 `database.py::ensure_schema_compat()` 里 `ALTER TABLE ... ADD COLUMN`，不写 Alembic。— CLAUDE.md「Additive Migrations」
- `part_id` / `jewelry_id` 视为不透明文本，不解析它做业务真相；分组真相存列。— CLAUDE.md + 设计文档 §2
- 后端测试用独立测试库；`db` fixture 做服务层单测，`client` fixture 做 API 测试（已 override 鉴权）。— `tests/conftest.py`
- 提交信息结尾：`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- 设计文档：`docs/superpowers/specs/2026-06-24-jewelry-management-style-grouping-design.md`；Mockup：`docs/superpowers/mockups/jewelry-management-mockup.html`

---

### Task 1: jewelry 加 `style_group` 列 + 响应字段 + additive 迁移

**Files:**
- Modify: `models/jewelry.py`
- Modify: `database.py`（`ensure_schema_compat`，紧随现有各 `ALTER TABLE` 块之后）
- Modify: `schemas/jewelry.py`（`JewelryResponse`）
- Test: `tests/test_api_jewelries.py`

**Interfaces:**
- Produces: `Jewelry.style_group`（`Column(String, nullable=True, index=True)`，默认 `None`）；`JewelryResponse.style_group: Optional[str]`。后续 Task 2/3/5 依赖此列与字段。

- [ ] **Step 1: 写失败测试** — 新建饰品的列表项应带 `style_group` 字段且默认为 null

在 `tests/test_api_jewelries.py` 末尾追加：

```python
def test_jewelry_response_has_style_group_default_null(client):
    client.post("/api/jewelries/", json={"name": "GroupProbe", "category": "套装"})
    resp = client.get("/api/jewelries/")
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["name"] == "GroupProbe")
    assert "style_group" in row
    assert row["style_group"] is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api_jewelries.py::test_jewelry_response_has_style_group_default_null -v`
Expected: FAIL（响应模型无 `style_group` 键 → KeyError/StopIteration）

- [ ] **Step 3: 模型加列**

`models/jewelry.py`，在 `handcraft_cost` 行后追加：

```python
    handcraft_cost = Column(Numeric(18, 7), nullable=True)
    # 款式归属键：值=基准饰品 ID（如 SP-SET-00002）；NULL=未归组。
    # 分组真相存此列，ID 的 -A/-B 后缀仅作显示。
    style_group = Column(String, nullable=True, index=True)
```

- [ ] **Step 4: schema 加字段**

`schemas/jewelry.py`，在 `JewelryResponse` 的 `status: str` 上方追加：

```python
    style_group: Optional[str] = None
```

- [ ] **Step 5: additive 迁移**

`database.py::ensure_schema_compat()`，在 `handcraft_jewelry_item` 块之后、`part` 块之前追加：

```python
        if inspector.has_table("jewelry"):
            columns = {col["name"] for col in inspector.get_columns("jewelry")}
            if "style_group" not in columns:
                conn.execute(text("ALTER TABLE jewelry ADD COLUMN style_group VARCHAR NULL"))
```

（模型上的 `index=True` 由 `_ensure_indexes` 自动建索引 `ix_jewelry_style_group`，无需手写 CREATE INDEX。）

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest tests/test_api_jewelries.py::test_jewelry_response_has_style_group_default_null -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add models/jewelry.py database.py schemas/jewelry.py tests/test_api_jewelries.py
git commit -m "feat(jewelry): add style_group column for style grouping

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `add_jewelry_sibling` 服务（后缀分配 + style_group 回填 + BOM 复制 + 不嵌套）

**Files:**
- Modify: `services/jewelry.py`
- Test: `tests/test_jewelry.py`

**Interfaces:**
- Consumes: `Jewelry.style_group`（Task 1）；现有 `get_jewelry`、`create_jewelry`、`_JEWELRY_MODEL_FIELDS`、`_next_id`、`Bom`。
- Produces:
  - `add_jewelry_sibling(db: Session, base_id: str, override_data: dict) -> Jewelry`
  - 辅助 `_suffix_to_num(s: str) -> int`、`_num_to_suffix(n: int) -> str`、`_next_sibling_suffix(db, group: str) -> str`
  - 行为：新行 `id = f"{group}-{suffix}"`，`style_group = group`，并把基准自身 `style_group` 回填为 `group`；复制 `base_id` 的 BOM。

- [ ] **Step 1: 写失败测试**

在 `tests/test_jewelry.py` 末尾追加（`db` 为服务层 fixture）：

```python
from services.jewelry import create_jewelry, add_jewelry_sibling, get_jewelry
from models.bom import Bom
from models.part import Part


def test_add_sibling_assigns_suffix_and_backfills_group(db):
    base = create_jewelry(db, {"name": "珍珠项链", "category": "套装", "retail_price": 168})
    s1 = add_jewelry_sibling(db, base.id, {"color": "白K"})
    s2 = add_jewelry_sibling(db, base.id, {"color": "玫瑰金"})
    assert s1.id == f"{base.id}-A"
    assert s2.id == f"{base.id}-B"
    # 基准被回填，三者同组
    assert get_jewelry(db, base.id).style_group == base.id
    assert s1.style_group == base.id
    assert s2.style_group == base.id
    # 预填基准值 + override 生效
    assert s1.name == "珍珠项链"
    assert s1.color == "白K"


def test_add_sibling_from_member_does_not_nest(db):
    base = create_jewelry(db, {"name": "耳钉", "category": "单件"})
    a = add_jewelry_sibling(db, base.id, {"color": "白K"})
    # 从成员 -A 再加，仍挂回基准组，得到 -B（不是 -A-A）
    b = add_jewelry_sibling(db, a.id, {"color": "玫瑰金"})
    assert b.id == f"{base.id}-B"
    assert b.style_group == base.id


def test_add_sibling_copies_bom(db):
    db.add(Part(id="PJ-DZ-T1", name="坠", category="吊坠", size_tier="medium"))
    db.flush()
    base = create_jewelry(db, {"name": "带BOM", "category": "套装"})
    db.add(Bom(id="BM-T1", jewelry_id=base.id, part_id="PJ-DZ-T1", qty_per_unit=2))
    db.flush()
    sib = add_jewelry_sibling(db, base.id, {"color": "白K"})
    sib_boms = db.query(Bom).filter(Bom.jewelry_id == sib.id).all()
    assert len(sib_boms) == 1
    assert sib_boms[0].part_id == "PJ-DZ-T1"
    assert float(sib_boms[0].qty_per_unit) == 2


def test_add_sibling_unknown_base_raises(db):
    with pytest.raises(ValueError):
        add_jewelry_sibling(db, "SP-SET-99999", {})
```

确保该文件顶部已 `import pytest`（无则加）。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_jewelry.py -k add_sibling -v`
Expected: FAIL with "cannot import name 'add_jewelry_sibling'"

- [ ] **Step 3: 实现服务**

`services/jewelry.py`，文件末尾追加：

```python
def _suffix_to_num(s: str) -> int:
    """双射 26 进制：A->1, Z->26, AA->27。"""
    n = 0
    for ch in s:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def _num_to_suffix(n: int) -> str:
    out = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(ord("A") + r) + out
    return out


def _next_sibling_suffix(db: Session, group: str) -> str:
    """扫描同组已有后缀成员，返回下一个可用字母后缀。"""
    prefix = f"{group}-"
    members = db.query(Jewelry).filter(Jewelry.style_group == group).all()
    nums = []
    for m in members:
        if m.id.startswith(prefix):
            suf = m.id[len(prefix):]
            if suf.isalpha() and suf.isupper():
                nums.append(_suffix_to_num(suf))
    return _num_to_suffix((max(nums) + 1) if nums else 1)


def add_jewelry_sibling(db: Session, base_id: str, override_data: dict) -> Jewelry:
    """以 base_id 为参照创建一条同款饰品（同 style_group，带后缀 ID，复制 BOM）。"""
    base = get_jewelry(db, base_id)
    if base is None:
        raise ValueError(f"Jewelry not found: {base_id}")
    # 不嵌套：解析到基准组键
    group = base.style_group or base.id
    group_base = base if group == base.id else get_jewelry(db, group)
    # 回填基准自身的 style_group（首次成组）
    if group_base is not None and group_base.style_group is None:
        group_base.style_group = group
        db.flush()

    suffix = _next_sibling_suffix(db, group)
    new_id = f"{group}-{suffix}"

    src = group_base if group_base is not None else base
    base_data = {
        "name": src.name,
        "image": src.image,
        "structure_image": src.structure_image,
        "category": src.category,
        "color": src.color,
        "unit": src.unit,
        "retail_price": src.retail_price,
        "wholesale_price": src.wholesale_price,
        "handcraft_cost": src.handcraft_cost,
    }
    safe_override = {k: v for k, v in (override_data or {}).items() if k != "category"}
    merged = {**base_data, **safe_override}
    fields = {k: v for k, v in merged.items() if k in _JEWELRY_MODEL_FIELDS and k != "style_group"}

    sibling = Jewelry(id=new_id, style_group=group, **fields)
    db.add(sibling)
    db.flush()

    for src_bom in db.query(Bom).filter(Bom.jewelry_id == src.id).all():
        db.add(Bom(
            id=_next_id(db, Bom, "BM"),
            jewelry_id=new_id,
            part_id=src_bom.part_id,
            qty_per_unit=src_bom.qty_per_unit,
        ))
    db.flush()
    return sibling
```

确保文件顶部 imports 含 `from services._helpers import _next_id, _next_id_by_category, keyword_filter` 与 `from models.bom import Bom`（现有；若缺 `_next_id` 则补）。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_jewelry.py -k add_sibling -v`
Expected: PASS（4 个）

- [ ] **Step 5: 提交**

```bash
git add services/jewelry.py tests/test_jewelry.py
git commit -m "feat(jewelry): add_jewelry_sibling service (suffix id + style_group + bom copy)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: 添加同款 API 端点 + schema

**Files:**
- Modify: `schemas/jewelry.py`
- Modify: `api/jewelries.py`
- Test: `tests/test_api_jewelries.py`

**Interfaces:**
- Consumes: `add_jewelry_sibling`（Task 2）；`get_jewelry`、`service_errors`、`JewelryResponse`。
- Produces: `POST /api/jewelries/{base_id}/siblings`，body `JewelrySiblingIn`，返回 `JewelryResponse`（201）。前端 Task 5 依赖此端点。

- [ ] **Step 1: 写失败测试**

`tests/test_api_jewelries.py` 末尾追加：

```python
def test_add_sibling_endpoint(client):
    base = client.post("/api/jewelries/", json={"name": "套链", "category": "套装", "retail_price": 168}).json()
    resp = client.post(f"/api/jewelries/{base['id']}/siblings", json={"color": "白K"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == f"{base['id']}-A"
    assert data["style_group"] == base["id"]
    assert data["color"] == "白K"
    assert data["name"] == "套链"


def test_add_sibling_endpoint_unknown_base_404(client):
    resp = client.post("/api/jewelries/SP-SET-99999/siblings", json={"color": "白K"})
    assert resp.status_code == 404
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api_jewelries.py -k add_sibling_endpoint -v`
Expected: FAIL（404 路由不存在 → 实际可能 405/404 mismatch 或导入错误）

- [ ] **Step 3: 加 schema**

`schemas/jewelry.py`，在 `JewelryCopyRequest` 之后追加：

```python
class JewelrySiblingIn(BaseModel):
    # 全部可选：未传字段沿用基准。category 不接受（沿用基准且锁定）。
    name: Optional[str] = None
    image: Optional[str] = None
    structure_image: Optional[str] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    retail_price: Optional[float] = None
    wholesale_price: Optional[float] = None
    handcraft_cost: Optional[float] = None
```

- [ ] **Step 4: 加端点**

`api/jewelries.py`：import 行加入 `add_jewelry_sibling` 与 `JewelrySiblingIn`：

```python
from schemas.jewelry import JewelryCreate, JewelryUpdate, JewelryResponse, StatusUpdate, JewelryCopyRequest, JewelrySiblingIn
from services.jewelry import (
    create_jewelry, get_jewelry, list_jewelries, update_jewelry,
    delete_jewelry, set_status, copy_jewelry, add_jewelry_sibling,
)
```

文件末尾追加端点：

```python
@router.post("/{base_id}/siblings", response_model=JewelryResponse, status_code=201)
def api_add_jewelry_sibling(base_id: str, body: JewelrySiblingIn, db: Session = Depends(get_db)):
    if get_jewelry(db, base_id) is None:
        raise HTTPException(status_code=404, detail=f"Jewelry {base_id} not found")
    with service_errors():
        sibling = add_jewelry_sibling(db, base_id, body.model_dump(exclude_unset=True))
    attach_jewelry_costs(db, [sibling])
    return sibling
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_api_jewelries.py -k add_sibling_endpoint -v`
Expected: PASS（2 个）

- [ ] **Step 6: 跑整组回归确保未破坏现有饰品测试**

Run: `pytest tests/test_api_jewelries.py tests/test_jewelry.py -q`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add schemas/jewelry.py api/jewelries.py tests/test_api_jewelries.py
git commit -m "feat(jewelry): POST /{base_id}/siblings add-sibling endpoint

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 配件「组合件不支持变体」守卫

**Files:**
- Modify: `services/part.py`（`create_part_variant`、`create_part`）
- Test: `tests/test_part_variants.py`（无则新建）

**Interfaces:**
- Consumes: 现有 `create_part`、`create_part_variant`、`get_part`、`Part`。
- Produces: 组合件作为根件加变体 / 作为父件创建子件时 `raise ValueError("组合件不支持变体")`。

- [ ] **Step 1: 写失败测试**

`tests/test_part_variants.py`（若不存在则新建，含 `import pytest`）追加：

```python
import pytest
from services.part import create_part, create_part_variant
from services.part import get_part


def test_composite_root_rejects_variant(db):
    p = create_part(db, {"name": "套底托", "category": "小配件"})
    get_part(db, p.id).is_composite = True
    db.flush()
    with pytest.raises(ValueError, match="组合件不支持变体"):
        create_part_variant(db, p.id, color_code="G")


def test_create_part_with_composite_parent_rejected(db):
    parent = create_part(db, {"name": "组合父", "category": "小配件"})
    get_part(db, parent.id).is_composite = True
    db.flush()
    with pytest.raises(ValueError, match="组合件不支持变体"):
        create_part(db, {"name": "子件", "category": "小配件", "parent_part_id": parent.id})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_part_variants.py -k composite -v`
Expected: FAIL（未抛出 ValueError，或抛出的是别的消息）

- [ ] **Step 3: 在 `create_part_variant` 加守卫**

`services/part.py::create_part_variant`，紧跟 `source, root, color, spec = _validate_variant_request(...)` 之后插入：

```python
    if root.is_composite:
        raise ValueError("组合件不支持变体")
```

- [ ] **Step 4: 在 `create_part` 加守卫**

`services/part.py::create_part`，在 parent 校验块里 `if parent.parent_part_id is not None:` 分支之后、`data.pop("unit_cost", None)` 之前插入：

```python
        if parent.is_composite:
            raise ValueError("组合件不支持变体")
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_part_variants.py -k composite -v`
Expected: PASS（2 个）

- [ ] **Step 6: 配件回归**

Run: `pytest tests/ -k "part" -q`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add services/part.py tests/test_part_variants.py
git commit -m "feat(parts): reject variants on composite parts

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: 前端 — 饰品列表刷新 + 可展开款式组 + 添加同款弹窗

**Files:**
- Modify: `frontend/src/api/jewelries.js`
- Modify: `frontend/src/views/jewelries/JewelryList.vue`（视觉/逻辑大改）
- 参考：`frontend/src/views/parts/PartList.vue`（样式 token 与类名来源）、Mockup `docs/superpowers/mockups/jewelry-management-mockup.html`

**Interfaces:**
- Consumes: `POST /jewelries/{base_id}/siblings`（Task 3）；响应 `style_group` 字段（Task 1）。
- Produces: `addJewelrySibling(baseId, data)` API 包装；JewelryList 渲染分组树。

无前端单测框架，本任务验证门为 `npm run build` 成功 + 对照 mockup 自检。各步骤逐一落地。

- [ ] **Step 1: 加 API 包装**

`frontend/src/api/jewelries.js` 末尾追加：

```js
export const addJewelrySibling = (baseId, data) => api.post(`/jewelries/${baseId}/siblings`, data)
```

- [ ] **Step 2: 顶部视觉骨架对齐 PartList**

替换 `JewelryList.vue` `<template>` 顶部（`.page-header` + `.filter-bar` 整段）为 PartList 风格的 `.page-top` + `.stat-strip` + `.filter-row`（从 `PartList.vue` 复制对应结构与 `<style>` 类：`.page-top/.page-crumbs/.title-row/.page-title/.title-count/.top-actions/.btn-outline/.btn-ink/.stat-strip/.stat-card/.stat-label/.stat-value/.stat-danger/.mono/.filter-row/.chip-group/.chip/.chip-active/.search-wrap/.table-wrap`）。标题计数与统计：

```html
<h1 class="page-title">饰品管理<span class="title-count">共 {{ rows.length }} 件饰品 · {{ groupCount }} 个款式组</span></h1>
```

```html
<div class="stat-strip">
  <div class="stat-card"><div class="stat-label">饰品总数</div><div class="stat-value mono">{{ rows.length }}</div></div>
  <div class="stat-card"><div class="stat-label">低库存预警</div><div class="stat-value mono" :class="{ 'stat-danger': lowStockCount > 0 }">{{ lowStockCount }}</div></div>
  <div class="stat-card"><div class="stat-label">已停用</div><div class="stat-value mono">{{ inactiveCount }}</div></div>
</div>
```

类目 chips（含「未分类」）：

```html
<div class="chip-group">
  <button v-for="chip in categoryChips" :key="chip.value ?? '__all__'" class="chip"
    :class="{ 'chip-active': filterCategory === chip.value }" @click="selectCategory(chip.value)">{{ chip.label }}</button>
</div>
```

- [ ] **Step 3: script — 状态与计算属性**

在 `<script setup>` 增加：

```js
const filterCategory = ref(undefined) // undefined=全部, '__none__'=未分类
const categoryChips = [
  { label: '全部', value: undefined },
  { label: '套装', value: '套装' },
  { label: '单件', value: '单件' },
  { label: '单对', value: '单对' },
  { label: '未分类', value: '__none__' },
]
const LOW_STOCK = 10
const lowStockCount = computed(() => rows.value.filter((r) => (r.stock ?? 0) < LOW_STOCK).length)
const inactiveCount = computed(() => rows.value.filter((r) => r.status === 'inactive').length)

function selectCategory(v) { filterCategory.value = v; load() }

// 分组树：按 style_group 聚桶；表头=id===group 的那条，缺则取组内最小 id；
// style_group 为空的为独立单条。返回排好序的「显示行」：每个表头行带 _children 数组。
const displayRows = computed(() => {
  const groups = new Map()
  const singles = []
  for (const r of rows.value) {
    if (r.style_group) {
      if (!groups.has(r.style_group)) groups.set(r.style_group, [])
      groups.get(r.style_group).push(r)
    } else {
      singles.push(r)
    }
  }
  const out = []
  for (const [gid, members] of groups) {
    members.sort((a, b) => a.id.localeCompare(b.id))
    const header = members.find((m) => m.id === gid) || members[0]
    const children = members.filter((m) => m.id !== header.id)
    out.push({ ...header, _isHeader: true, _group: gid, _children: children })
  }
  for (const s of singles) out.push({ ...s, _isHeader: false, _group: null, _children: [] })
  out.sort((a, b) => a.id.localeCompare(b.id))
  return out
})
const groupCount = computed(() => displayRows.value.filter((r) => r._children.length > 0).length)

const expanded = ref(new Set())
function toggleGroup(gid) {
  const s = new Set(expanded.value)
  s.has(gid) ? s.delete(gid) : s.add(gid)
  expanded.value = s
}
```

`load()` 改为把 `filterCategory` 映射到请求参数（`'__none__'` 不传 category，前端再过滤出 `!category` 的）：

```js
const load = async () => {
  loading.value = true
  try {
    const params = {}
    if (searchName.value) params.name = searchName.value
    if (filterStatus.value) params.status = filterStatus.value
    if (filterCategory.value && filterCategory.value !== '__none__') params.category = filterCategory.value
    const { data: jewelries } = await listJewelries(params)
    const stockMap = jewelries.length
      ? (await batchGetStock('jewelry', jewelries.map((j) => j.id))).data : {}
    let mapped = jewelries.map((j) => ({ ...j, stock: stockMap[j.id] ?? 0 }))
    if (filterCategory.value === '__none__') mapped = mapped.filter((j) => !j.category)
    rows.value = mapped
  } finally { loading.value = false }
}
```

- [ ] **Step 4: 表格渲染分组（可展开，默认折叠）**

用自管理展开方案：`:data="tableData"`，其中 `tableData` 把每个展开的表头后插入其 `_children`：

```js
const tableData = computed(() => {
  const out = []
  for (const r of displayRows.value) {
    out.push(r)
    if (r._isHeader && expanded.value.has(r._group)) {
      for (const c of r._children) out.push({ ...c, _isChild: true })
    }
  }
  return out
})
```

`columns` 的「编号」列 render 加展开箭头/缩进，「饰品」列在表头行追加 `同款×N` pill，「操作」列表头/单条显示「＋ 添加同款」（子行不显示）：

```js
{ title: '编号', key: 'id', width: 170, render: (row) => {
    const caret = row._isHeader && row._children.length
      ? h('span', { class: 'jw-caret', style: expanded.value.has(row._group) ? 'transform:rotate(90deg)' : '',
          onClick: (e) => { e.stopPropagation(); toggleGroup(row._group) } }, '▸')
      : h('span', { class: 'jw-caret jw-caret-spacer' }, '▸')
    return h('span', { class: 'cell-id' }, [caret, ' ', row.id])
  },
},
```

「饰品」列 render（复用 `renderNamedImage`，表头行补 pill；子行加缩进类）：

```js
{ title: '饰品', key: 'name', minWidth: 200, render: (row) => {
    const nodes = [renderNamedImage(row.name, row.image, row.name)]
    if (row._isHeader && row._children.length)
      nodes.push(h('span', { class: 'jw-count-pill' }, `同款×${row._children.length}`))
    return h('div', { class: row._isChild ? 'jw-name jw-indent' : 'jw-name' }, nodes)
  },
},
```

「操作」列：表头/单条加「＋」按钮 `onClick: () => openAddSibling(row)`；子行只保留详情/编辑/更多。

新增 `<style>`：

```css
.jw-caret{display:inline-flex;width:18px;height:18px;border-radius:5px;cursor:pointer;color:#6b7280;font-size:10px;align-items:center;justify-content:center;transition:transform .12s;}
.jw-caret-spacer{visibility:hidden;cursor:default;}
.jw-count-pill{font-size:10.5px;font-weight:600;padding:1px 7px;border-radius:5px;background:#EEF1F4;color:#475569;margin-left:8px;}
.jw-name{display:inline-flex;align-items:center;gap:8px;}
.jw-indent{padding-left:26px;}
```

- [ ] **Step 5: 「添加同款」弹窗 + 提交逻辑**

新增弹窗状态与函数：

```js
import { addJewelrySibling } from '@/api/jewelries'
const showSiblingModal = ref(false)
const siblingSaving = ref(false)
const siblingBase = ref(null)
const siblingForm = reactive({ name: '', image: '', color: '', unit: null, retail_price: null, wholesale_price: null })

function openAddSibling(row) {
  siblingBase.value = row
  Object.assign(siblingForm, {
    name: row.name, image: row.image || '', color: row.color || '',
    unit: row.unit || null, retail_price: row.retail_price ?? null, wholesale_price: row.wholesale_price ?? null,
  })
  showSiblingModal.value = true
}

async function saveSibling() {
  siblingSaving.value = true
  try {
    const { data } = await addJewelrySibling(siblingBase.value.id, { ...siblingForm })
    message.success('已添加同款')
    showSiblingModal.value = false
    const gid = data.style_group
    if (gid) expanded.value = new Set([...expanded.value, gid])
    await load()
  } catch (e) {
    message.error(e.response?.data?.detail || '添加失败')
  } finally { siblingSaving.value = false }
}
```

弹窗模板（沿用现有 `ImageUploadModal`，类目锁定显示基准类目、不可改；含图片上传入口，对照 mockup ②）：

```html
<n-modal v-model:show="showSiblingModal" preset="card" :style="{ width: isMobile ? '95vw' : '480px' }">
  <template #header>添加同款 · 将生成 {{ siblingBase?.style_group || siblingBase?.id }}-新后缀</template>
  <n-form label-placement="left" label-width="100">
    <n-alert type="warning" style="margin-bottom:12px;">归属款式组 <b>{{ siblingBase?.id }} {{ siblingBase?.name }}</b>，已预填并带入基准 BOM。类目沿用基准不可改。</n-alert>
    <n-form-item label="名称"><n-input v-model:value="siblingForm.name" /></n-form-item>
    <n-form-item label="图片">
      <n-space vertical style="width:100%;">
        <n-space align="center" style="width:100%;">
          <n-input v-model:value="siblingForm.image" placeholder="上传后自动填充，也可手动输入 URL" />
          <n-button @click="openImageModal(null)">上传图片</n-button>
        </n-space>
        <n-image v-if="siblingForm.image" :src="siblingForm.image" :width="72" :height="72" object-fit="cover" style="border-radius:12px;" />
      </n-space>
    </n-form-item>
    <n-form-item label="颜色"><n-input v-model:value="siblingForm.color" /></n-form-item>
    <n-form-item label="单位"><n-select v-model:value="siblingForm.unit" :options="unitOptions" /></n-form-item>
    <n-form-item label="零售价"><n-input-number v-model:value="siblingForm.retail_price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" style="width:100%;" /></n-form-item>
    <n-form-item label="批发价"><n-input-number v-model:value="siblingForm.wholesale_price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" style="width:100%;" /></n-form-item>
  </n-form>
  <template #footer><n-space justify="end"><n-button @click="showSiblingModal = false">取消</n-button><n-button type="primary" :loading="siblingSaving" @click="saveSibling">创建同款</n-button></n-space></template>
</n-modal>
```

让现有 `onImageUploaded` 在同款弹窗打开时写入 `siblingForm.image`：把 `onImageUploaded(url)` 改为——若 `showSiblingModal.value` 为真则 `siblingForm.image = url`，否则 `form.image = url`。

- [ ] **Step 6: 表格 `:data` 切到 `tableData`**

把 `<n-data-table ... :data="rows" .../>` 改为 `:data="tableData"`，并 `:row-key="(r) => r.id"`。

- [ ] **Step 7: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功，无报错。

- [ ] **Step 8: 对照 mockup 自检**

打开应用饰品页核对：默认折叠、`同款×N` pill、展开/收起、未分类 chip、低库存红色、「＋ 添加同款」弹窗含图片上传与 ID 预览。

- [ ] **Step 9: 提交**

```bash
git add frontend/src/api/jewelries.js frontend/src/views/jewelries/JewelryList.vue
git commit -m "feat(jewelry-ui): refresh list + expandable style groups + add-sibling modal

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: 前端 — 配件列表变体折叠

**Files:**
- Modify: `frontend/src/views/parts/PartList.vue`
- 参考：Task 5 的分组树/展开实现（同套思路，按 `parent_part_id` 而非 `style_group`）

**Interfaces:**
- Consumes: `listParts` 返回的 `parent_part_id`、`is_composite`（现有）。
- Produces: PartList 渲染根件折叠 + 隐藏组合件「加变体」入口。

验证门：`npm run build` + 对照 mockup ③。

- [ ] **Step 1: 分组树（按 parent_part_id）**

在 `<script setup>` 增加（镜像 Task 5 的结构，键改为 `parent_part_id`，表头=根件）：

```js
const expanded = ref(new Set())
function toggleGroup(rootId) {
  const s = new Set(expanded.value)
  s.has(rootId) ? s.delete(rootId) : s.add(rootId)
  expanded.value = s
}
const displayRows = computed(() => {
  const variantsByRoot = new Map()
  const roots = []
  for (const r of rows.value) {
    if (r.parent_part_id) {
      if (!variantsByRoot.has(r.parent_part_id)) variantsByRoot.set(r.parent_part_id, [])
      variantsByRoot.get(r.parent_part_id).push(r)
    } else roots.push(r)
  }
  return roots.map((root) => {
    const children = (variantsByRoot.get(root.id) || []).slice().sort((a, b) => a.id.localeCompare(b.id))
    return { ...root, _children: children }
  })
})
const tableData = computed(() => {
  const out = []
  for (const r of displayRows.value) {
    out.push(r)
    if (expanded.value.has(r.id)) for (const c of r._children) out.push({ ...c, _isChild: true })
  }
  return out
})
```

标题计数改为 `共 {{ rows.length }} 个配件 · {{ displayRows.length }} 个根件`。

- [ ] **Step 2: 编号列加展开箭头/缩进，名称列加 `变体×N` pill**

在 `columns` 的编号列 render 前置箭头（根件有子才显示，否则占位 spacer），名称列在根件追加 pill：

```js
// 编号列
render: (row) => {
  const hasKids = !row._isChild && row._children && row._children.length
  const caret = hasKids
    ? h('span', { class: 'pt-caret', style: expanded.value.has(row.id) ? 'transform:rotate(90deg)' : '',
        onClick: (e) => { e.stopPropagation(); toggleGroup(row.id) } }, '▸')
    : h('span', { class: 'pt-caret pt-caret-spacer' }, '▸')
  return h('span', { class: 'cell-id' }, [caret, ' ', row.id])
}
```

名称列现有 render 里，于组合标签处追加：根件且有子时 push `h('span', { class: 'count-pill' }, \`变体×${row._children.length}\`)`；子行外层加 `pt-indent` 类。新增 CSS：

```css
.pt-caret{display:inline-flex;width:18px;height:18px;border-radius:5px;cursor:pointer;color:#6b7280;font-size:10px;align-items:center;justify-content:center;transition:transform .12s;}
.pt-caret-spacer{visibility:hidden;cursor:default;}
.count-pill{font-size:10.5px;font-weight:600;padding:1px 7px;border-radius:5px;background:#EEF1F4;color:#475569;margin-left:6px;}
.pt-indent{padding-left:26px;}
```

- [ ] **Step 3: 组合件隐藏「加变体」入口**

在「操作」列（或变体相关按钮处）对 `row.is_composite` 为真的行不渲染「加变体」按钮。定位现有加变体入口（编辑弹窗内的变体区或行内按钮），加 `v-if="!row.is_composite"` / 条件分支。

- [ ] **Step 4: 表格 `:data` 切到 `tableData`**

`<n-data-table :columns="columns" :data="tableData" :row-key="(r) => r.id" :bordered="false" />`（原为 `:data="rows"`）。`compositeCount`/`lowStockCount` 仍基于 `rows`，无需改。

- [ ] **Step 5: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功。

- [ ] **Step 6: 对照 mockup ③ 自检**

根件折叠、`变体×N`、展开看 `-G/-S/-45cm`、组合件无「加变体」入口且「组合」标签正常。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/views/parts/PartList.vue
git commit -m "feat(parts-ui): fold variants into expandable root rows

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage（对照设计文档各节）：**
- §3.1 `style_group` 列 → Task 1 ✅
- §4.1 添加同款服务（组解析/回填/后缀/沿用/BOM/不嵌套）→ Task 2 ✅；API → Task 3 ✅；前端包装 → Task 5 Step 1 ✅
- §4.2 组合件守卫 → Task 4 ✅
- §4.3 list 响应带 `style_group` → Task 1（schema）✅；list_parts 不改 ✅
- §5.1 饰品视觉刷新 + 分组树 + 未分类桶 + 添加同款弹窗 + 图片上传 → Task 5 ✅
- §5.2 配件变体折叠 + 组合件隐藏加变体 → Task 6 ✅
- §6 边界：不嵌套（Task 2 测试）✅、后缀耗尽（`_num_to_suffix` 支持 AA）✅、删除基准兜底表头（Task 5 displayRows `members[0]`）✅、独立可编辑（折叠纯展示，未改详情/编辑路径）✅

**Placeholder scan:** 无 TBD/TODO；每个代码步骤含完整代码与确切命令。

**Type consistency:** `add_jewelry_sibling(db, base_id, override_data)` 在 Task 2 定义、Task 3 调用一致；`JewelrySiblingIn` 字段与服务读取的 override 键一致；前端 `addJewelrySibling(baseId, data)` 与端点路径一致；`displayRows/_children/_isHeader/_group/tableData/expanded/toggleGroup` 命名在 Task 5 内自洽，Task 6 用同套命名（`pt-` 前缀区分）。

---

## Execution Handoff

计划已保存到 `docs/superpowers/plans/2026-06-24-jewelry-management-style-grouping.md`。
