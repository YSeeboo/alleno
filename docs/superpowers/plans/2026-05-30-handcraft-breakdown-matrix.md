# 手工单客户分拣 · 矩阵交互 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 HC 详情页的"客户分拣"区从"按饰品分组 + N 个 modal"重构为"按客户视角的二维矩阵 + 一键剩余分给"。

**Architecture:** 替换 `BreakdownEditModal` + `BreakdownChips` 为单一组件 `BreakdownMatrix.vue`,默认只读、点编辑进入可编辑态、统一保存。新增后端 `GET /api/customers/names` 提供历史客户名建议;新增「一键剩余分给某客户」批量入口,语义为 PATCH 占位 entries 而非新建。

**Tech Stack:** FastAPI + SQLAlchemy(后端);Vue 3.5 + Naive UI + Pinia(前端);pytest(测试)。

**Spec:** `docs/superpowers/specs/2026-05-30-handcraft-breakdown-matrix-design.md`

**Key file paths:**
- 后端: `services/customer.py`(新), `api/customers.py`(新), `tests/test_api_customers.py`(新)
- 前端组件: `frontend/src/components/{BreakdownMatrix,CustomerNameSelect,BulkAssignPopover}.vue`(均新)
- 前端 API: `frontend/src/api/customers.js`(新)
- 集成: `frontend/src/views/handcraft/HandcraftDetail.vue`(改);`main.py`(改)
- 删除: `frontend/src/components/BreakdownEditModal.vue`, `frontend/src/components/BreakdownChips.vue`

**Important corrections to spec text:** The real handcraft jewelry endpoint is `/api/handcraft/{id}/jewelries/{item_id}` (plural) — spec writes `/jewelry/{item_id}` (singular). Always use the **plural** form. Frontend helpers `addHandcraftJewelry / updateHandcraftJewelry / deleteHandcraftJewelry` in `frontend/src/api/handcraft.js` already point at the plural route.

---

## File Structure

| File | Responsibility |
|---|---|
| `services/customer.py` | Pure function: `list_distinct_customer_names(db, query, limit)` returning sorted, deduped names from three sources |
| `api/customers.py` | Single `GET /api/customers/names` route, thin wrapper around the service |
| `tests/test_api_customers.py` | Suggest API tests (dedupe, query filter, limit, auth) |
| `main.py` | Register `customers` router with `require_permission("handcraft")` |
| `frontend/src/api/customers.js` | `getCustomerNames(query)` axios call |
| `frontend/src/components/CustomerNameSelect.vue` | `n-select` wrapper: async search, `filterable + tag` semantics (allow new values) |
| `frontend/src/components/BulkAssignPopover.vue` | Popover content: preview of fill plan + `CustomerNameSelect` + confirm/cancel |
| `frontend/src/components/BreakdownMatrix.vue` | Main 2D matrix: transpose backend groups → rows/cols, 4-state cell renderer, edit mode toggle, save diff, bulk-assign integration, mobile sticky styles |
| `frontend/src/views/handcraft/HandcraftDetail.vue` | Swap `BreakdownEditModal + BreakdownChips` for `<BreakdownMatrix>`;remove related state |

Each frontend component owns one responsibility; `BreakdownMatrix` is the only one that knows about HC business rules. `CustomerNameSelect` and `BulkAssignPopover` are reusable, dumb-ish presentation pieces.

---

## Task 1: Verify the foundational assumption — HC creation produces customer_name=None placeholder entries

**Why first:** The whole bulk-assign feature assumes that a newly-created HC has `HandcraftJewelryItem` rows with `customer_name = None` covering the planned production. If this is broken (some path skips it), we discover it now before building UI on top.

**Files:**
- Test: `tests/test_api_handcraft_breakdown_placeholders.py` (new file)

- [ ] **Step 1: Write the verification test**

Create `tests/test_api_handcraft_breakdown_placeholders.py`:

```python
"""Verify the foundational assumption for bulk-assign in the matrix UI:
HC creation with no per-jewelry customer_name produces breakdown entries
where customer_name=None and is_locked=False (i.e. claimable placeholders).
"""
from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock


def _setup(db):
    part = create_part(db, {"name": "P-PH", "category": "小配件", "color": "古铜"})
    jewelry = create_jewelry(db, {"name": "J-PH", "category": "单件"})
    add_stock(db, "part", part.id, 100.0, "init")
    return part, jewelry


def test_hc_create_generates_placeholder_breakdown_entries(client, db):
    """Bulk-assign needs `customer_name = None + is_locked = false` entries
    to PATCH. Confirm HC creation produces them when payload omits customer_name."""
    part, jewelry = _setup(db)

    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Sup-PH",
        "parts": [{"part_id": part.id, "qty": 5.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 7}],
    })
    assert resp.status_code == 201
    hc_id = resp.json()["id"]

    br = client.get(f"/api/handcraft/{hc_id}/jewelry-breakdown")
    assert br.status_code == 200
    groups = br.json()
    assert len(groups) == 1, "Expected exactly one jewelry group"

    g = groups[0]
    assert g["jewelry_id"] == jewelry.id
    assert g["total_qty"] == 7

    # All entries should be claimable placeholders:
    # customer_name=None, source=manual, is_locked=False
    placeholder_qty_sum = 0
    for e in g["entries"]:
        assert e["customer_name"] is None
        assert e["source"] == "manual"
        assert e["is_locked"] is False
        placeholder_qty_sum += e["qty"]
    assert placeholder_qty_sum == 7, (
        "Placeholder qty must cover total_qty so bulk-assign can claim everything"
    )
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_api_handcraft_breakdown_placeholders.py -v`
Expected: PASS

If it FAILS — STOP. The assumption is broken; do not proceed with bulk-assign as designed. Surface the failure to the user with the actual breakdown output, and ask them whether to:
(a) Patch HC creation to always seed placeholder entries, or
(b) Switch bulk-assign semantics to POST new entries (which mutates `total_qty`).

- [ ] **Step 3: Commit**

```bash
git add tests/test_api_handcraft_breakdown_placeholders.py
git commit -m "test(handcraft): verify breakdown placeholders for bulk-assign"
```

---

## Task 2: Service — list_distinct_customer_names

**Files:**
- Create: `services/customer.py`
- Test: `tests/test_service_customer.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_service_customer.py`:

```python
"""Unit tests for services/customer.list_distinct_customer_names."""
import pytest

from services.customer import list_distinct_customer_names
from services.order import create_order
from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock
from services.handcraft import create_handcraft_order, add_handcraft_jewelry


def _seed_part_jewelry(db):
    part = create_part(db, {"name": "P-C", "category": "小配件", "color": "古铜"})
    jewelry = create_jewelry(db, {"name": "J-C", "category": "单件"})
    add_stock(db, "part", part.id, 100.0, "init")
    return part, jewelry


def test_empty_db_returns_empty(db):
    assert list_distinct_customer_names(db) == []


def test_dedupes_across_three_sources(db):
    """Order.customer_name + HandcraftOrder.customer_name + HandcraftJewelryItem.customer_name
    all union into a single deduped list."""
    part, jewelry = _seed_part_jewelry(db)

    # Source 1: Order.customer_name
    create_order(db, {
        "customer_name": "张三",
        "items": [{"jewelry_id": jewelry.id, "qty": 1}],
    })

    # Source 2: HandcraftOrder.customer_name
    create_handcraft_order(db, {
        "supplier_name": "S-A",
        "customer_name": "李四",
        "parts": [{"part_id": part.id, "qty": 1}],
    })

    # Source 3: HandcraftJewelryItem.customer_name — needs an HC then add a manual jewelry row
    hc = create_handcraft_order(db, {
        "supplier_name": "S-B",
        "parts": [{"part_id": part.id, "qty": 1}],
    })
    add_handcraft_jewelry(db, hc.id, {
        "jewelry_id": jewelry.id, "qty": 2, "customer_name": "王五",
    })

    # Add a duplicate "张三" via HC.customer_name to test dedupe
    create_handcraft_order(db, {
        "supplier_name": "S-C",
        "customer_name": "张三",
        "parts": [{"part_id": part.id, "qty": 1}],
    })

    names = list_distinct_customer_names(db)
    assert sorted(names) == sorted(["张三", "李四", "王五"])


def test_query_filters_case_insensitive_substring(db):
    part, jewelry = _seed_part_jewelry(db)
    create_order(db, {"customer_name": "Alice", "items": [{"jewelry_id": jewelry.id, "qty": 1}]})
    create_order(db, {"customer_name": "alex", "items": [{"jewelry_id": jewelry.id, "qty": 1}]})
    create_order(db, {"customer_name": "Bob",   "items": [{"jewelry_id": jewelry.id, "qty": 1}]})

    assert sorted(list_distinct_customer_names(db, query="al")) == ["Alice", "alex"]
    assert sorted(list_distinct_customer_names(db, query="AL")) == ["Alice", "alex"]
    assert list_distinct_customer_names(db, query="Z") == []


def test_excludes_empty_and_whitespace_names(db):
    """Empty strings must not appear in the result."""
    part, jewelry = _seed_part_jewelry(db)
    create_order(db, {"customer_name": "Real", "items": [{"jewelry_id": jewelry.id, "qty": 1}]})
    # Direct insert of an empty-string order would need raw SQL; we trust the
    # service filters '' even if it ever creeps in. Sanity-check via fallback path:
    # NOTE: create_order may reject empty customer_name. The intent here is the
    # service contract — verify it strips empty values defensively.
    names = list_distinct_customer_names(db)
    assert "" not in names
    assert "Real" in names


def test_limit_truncates(db):
    part, jewelry = _seed_part_jewelry(db)
    for i in range(60):
        create_order(db, {
            "customer_name": f"C{i:03d}",
            "items": [{"jewelry_id": jewelry.id, "qty": 1}],
        })
    names = list_distinct_customer_names(db, limit=10)
    assert len(names) == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_service_customer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.customer'`

- [ ] **Step 3: Implement the service**

Create `services/customer.py`:

```python
"""Customer name suggestion service.

There is no Customer master table — `customer_name` is a free-text column on
Order, HandcraftOrder, and HandcraftJewelryItem. This service unions and
dedupes those three sources for a downstream picker.
"""
from sqlalchemy.orm import Session

from models.order import Order
from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem


def list_distinct_customer_names(
    db: Session, query: str | None = None, limit: int = 50,
) -> list[str]:
    """Return sorted distinct customer names from the three known sources.

    `query` filters substring (case-insensitive). Empty names are excluded
    defensively even though the source tables generally validate non-empty.
    """
    order_q = db.query(Order.customer_name).filter(
        Order.customer_name.isnot(None), Order.customer_name != ""
    )
    hc_q = db.query(HandcraftOrder.customer_name).filter(
        HandcraftOrder.customer_name.isnot(None), HandcraftOrder.customer_name != ""
    )
    hcji_q = db.query(HandcraftJewelryItem.customer_name).filter(
        HandcraftJewelryItem.customer_name.isnot(None),
        HandcraftJewelryItem.customer_name != "",
    )
    union_q = order_q.union(hc_q).union(hcji_q)
    rows = union_q.all()
    names = sorted({r[0] for r in rows if r[0] and r[0].strip()})
    if query:
        q = query.strip().lower()
        names = [n for n in names if q in n.lower()]
    return names[:limit]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_service_customer.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/customer.py tests/test_service_customer.py
git commit -m "feat(customer): list_distinct_customer_names service"
```

---

## Task 3: API — GET /api/customers/names

**Files:**
- Create: `api/customers.py`
- Test: `tests/test_api_customers.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_customers.py`:

```python
"""API tests for the customer name suggest endpoint."""
from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock
from services.order import create_order


def _seed(db):
    part = create_part(db, {"name": "P-CA", "category": "小配件", "color": "古铜"})
    jewelry = create_jewelry(db, {"name": "J-CA", "category": "单件"})
    add_stock(db, "part", part.id, 100.0, "init")
    create_order(db, {"customer_name": "张三", "items": [{"jewelry_id": jewelry.id, "qty": 1}]})
    create_order(db, {"customer_name": "张三",  "items": [{"jewelry_id": jewelry.id, "qty": 1}]})  # dup
    create_order(db, {"customer_name": "李四", "items": [{"jewelry_id": jewelry.id, "qty": 1}]})
    create_order(db, {"customer_name": "Tom",  "items": [{"jewelry_id": jewelry.id, "qty": 1}]})


def test_get_names_empty(client):
    resp = client.get("/api/customers/names")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_names_dedupes_and_sorts(client, db):
    _seed(db)
    resp = client.get("/api/customers/names")
    assert resp.status_code == 200
    names = resp.json()
    # 张三 only once
    assert names.count("张三") == 1
    assert set(names) == {"张三", "李四", "Tom"}


def test_get_names_query_filter(client, db):
    _seed(db)
    resp = client.get("/api/customers/names", params={"q": "tom"})
    assert resp.status_code == 200
    assert resp.json() == ["Tom"]


def test_get_names_limit(client, db):
    _seed(db)
    resp = client.get("/api/customers/names", params={"limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_customers.py -v`
Expected: All FAIL with 404 (route not registered yet).

- [ ] **Step 3: Implement the route**

Create `api/customers.py`:

```python
"""Customer name suggest endpoint.

No CRUD — customer_name lives as free text on other models. This is purely a
read-side helper for pickers (used by the HC breakdown matrix and bulk-assign
popover).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from services.customer import list_distinct_customer_names

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("/names", response_model=list[str])
def api_list_customer_names(
    q: Optional[str] = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[str]:
    return list_distinct_customer_names(db, query=q, limit=limit)
```

- [ ] **Step 4: Register in main.py**

Edit `main.py` — add the import next to the other api imports, and register with `require_permission("handcraft")`:

After `from api.restock import router as restock_router` (around line 32), add:
```python
from api.customers import router as customers_router
```

After `app.include_router(handcraft_router, dependencies=[require_permission("handcraft")])` (around line 106), add:
```python
app.include_router(customers_router, dependencies=[require_permission("handcraft")])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_api_customers.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 6: Run the full backend test suite to confirm no regressions**

Run: `pytest -x --ff -q`
Expected: All tests pass (or only pre-existing failures unchanged).

- [ ] **Step 7: Commit**

```bash
git add api/customers.py tests/test_api_customers.py main.py
git commit -m "feat(api): GET /api/customers/names for picker suggestions"
```

---

## Task 4: Frontend api shim — getCustomerNames

**Files:**
- Create: `frontend/src/api/customers.js`

- [ ] **Step 1: Create the shim**

Create `frontend/src/api/customers.js`:

```javascript
import api from './index'

/**
 * Fetch distinct customer names for the picker.
 * @param {string|undefined} query Optional substring filter (case-insensitive)
 * @param {number} limit Max results (default 50)
 * @returns Promise<AxiosResponse<string[]>>
 */
export const getCustomerNames = (query, limit = 50) =>
  api.get('/customers/names', { params: { q: query || undefined, limit } })
```

- [ ] **Step 2: Smoke check that the frontend still builds**

Run: `cd frontend && npm run build`
Expected: build succeeds (no new errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/customers.js
git commit -m "feat(frontend): customer names api shim"
```

---

## Task 5: CustomerNameSelect.vue component

**Files:**
- Create: `frontend/src/components/CustomerNameSelect.vue`

This is a thin wrapper around `n-select` that:
- Loads suggestion options on mount and on filter change
- Accepts user-entered values not in the list (Naive UI: `filterable + tag`)
- Two-way binds via `v-model:value`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/CustomerNameSelect.vue`:

```vue
<template>
  <n-select
    :value="value"
    :options="options"
    filterable
    tag
    clearable
    :placeholder="placeholder"
    :loading="loading"
    :size="size"
    :disabled="disabled"
    @update:value="onUpdate"
    @search="onSearch"
  />
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { NSelect } from 'naive-ui'
import { getCustomerNames } from '@/api/customers'

const props = defineProps({
  value: { type: String, default: null },
  placeholder: { type: String, default: '客户名' },
  size: { type: String, default: 'small' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:value'])

const options = ref([])
const loading = ref(false)

async function loadNames(q) {
  loading.value = true
  try {
    const { data } = await getCustomerNames(q)
    // Naive expects {label, value} options. Customer names are strings; both
    // fields share the same value so user-typed (tag) values still match.
    options.value = (data || []).map((n) => ({ label: n, value: n }))
    // If we have a current value not in the list, surface it as an option so
    // the select renders it instead of blanking.
    if (props.value && !options.value.find((o) => o.value === props.value)) {
      options.value.unshift({ label: props.value, value: props.value })
    }
  } catch (_) {
    options.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => loadNames())

let searchTimer = null
function onSearch(q) {
  // Debounce 200ms so we don't hammer the API while the user is typing.
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => loadNames(q), 200)
}

function onUpdate(v) {
  emit('update:value', v)
}
</script>
```

- [ ] **Step 2: Smoke check build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/CustomerNameSelect.vue
git commit -m "feat(frontend): CustomerNameSelect wrapper with async suggestions"
```

---

## Task 6: BulkAssignPopover.vue component

**Files:**
- Create: `frontend/src/components/BulkAssignPopover.vue`

The component renders the popover contents (it does NOT manage its own trigger/show state — the parent `BreakdownMatrix` controls visibility via `n-popover`'s default slot).

**Props:**
- `previewItems` — `[{jewelry_id, jewelry_name, delta}, ...]` rows to show in the preview
- `hasLocked` — boolean, controls the "不会动 🔒" hint
- `hasPartialManual` — boolean, controls the "其他客户已填的部分" hint

**Emits:**
- `confirm(customerName)` — user clicked 「填入」 with a chosen name
- `cancel` — user clicked 「取消」

- [ ] **Step 1: Create the component**

Create `frontend/src/components/BulkAssignPopover.vue`:

```vue
<template>
  <div class="bap">
    <h4 class="bap__title">⚡ 把剩余数量分给某位客户</h4>
    <div class="bap__preview">
      <div class="bap__preview-head">将填入(基于当前矩阵):</div>
      <ul class="bap__preview-list">
        <li v-for="it in previewItems" :key="it.jewelry_id">
          {{ it.jewelry_name }} <span class="qty">+{{ it.delta }}</span>
        </li>
      </ul>
      <div v-if="totalText" class="bap__preview-foot">{{ totalText }}</div>
    </div>

    <div class="bap__label">选客户(从历史选或输新名)</div>
    <CustomerNameSelect v-model:value="picked" placeholder="客户名" />

    <div class="bap__footer">
      <n-button size="small" @click="$emit('cancel')">取消</n-button>
      <n-button size="small" type="primary" :disabled="!canConfirm" @click="onConfirm">
        填入
      </n-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { NButton } from 'naive-ui'
import CustomerNameSelect from './CustomerNameSelect.vue'

const props = defineProps({
  previewItems: { type: Array, required: true },
  hasLocked: { type: Boolean, default: false },
  hasPartialManual: { type: Boolean, default: false },
})
const emit = defineEmits(['confirm', 'cancel'])

const picked = ref(null)

const totalSum = computed(() =>
  props.previewItems.reduce((s, it) => s + Number(it.delta || 0), 0),
)

const totalText = computed(() => {
  const hints = []
  if (!props.hasLocked && !props.hasPartialManual) {
    hints.push(`✓ 整单全部 ${totalSum.value} 套`)
  } else {
    if (props.hasLocked) hints.push('不会动 🔒 锁定行')
    if (props.hasPartialManual) hints.push('其他客户已填的部分不变')
  }
  return hints.join(' · ')
})

const canConfirm = computed(
  () => !!(picked.value && String(picked.value).trim()),
)

function onConfirm() {
  if (canConfirm.value) emit('confirm', String(picked.value).trim())
}
</script>

<style scoped>
.bap { width: 260px; font-size: 12px; }
.bap__title { margin: 0 0 10px; font-size: 13px; font-weight: 600; }
.bap__preview {
  background: #f9f9fc; border-radius: 3px; padding: 8px 10px;
  margin-bottom: 10px; font-size: 11px; color: #555; line-height: 1.7;
}
.bap__preview-head { color: #666; margin-bottom: 4px; }
.bap__preview-list { list-style: none; margin: 0; padding: 0; }
.bap__preview-list li { padding: 1px 0; }
.bap__preview-list .qty { color: #4338ca; font-family: "SF Mono", Menlo, monospace; }
.bap__preview-foot { color: #18a058; margin-top: 4px; font-size: 11px; }
.bap__label { color: #666; margin-bottom: 4px; }
.bap__footer { display: flex; gap: 6px; justify-content: flex-end; margin-top: 10px; }
</style>
```

- [ ] **Step 2: Smoke check build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/BulkAssignPopover.vue
git commit -m "feat(frontend): BulkAssignPopover with preview and customer picker"
```

---

## Task 7: BreakdownMatrix.vue — skeleton + transpose

Create the component with props, the transpose logic that turns backend `groups` (jewelry-major) into matrix `rows` (customer-major) + `cols` (jewelry), and a minimal placeholder render that proves the data flow.

**Files:**
- Create: `frontend/src/components/BreakdownMatrix.vue`

- [ ] **Step 1: Create the skeleton**

Create `frontend/src/components/BreakdownMatrix.vue`:

```vue
<template>
  <n-card v-if="cols.length > 0" :content-style="collapsed ? 'padding: 0' : undefined">
    <template #header>
      <div class="bm-head" @click="collapsed = !collapsed">
        <span class="chev">{{ collapsed ? '▸' : '▾' }}</span>
        <span class="title">客户分拣</span>
        <span class="status-tag">{{ statusTagText }}</span>
      </div>
    </template>
    <div v-show="!collapsed">
      <!-- Render skeleton — real table comes in next task -->
      <pre class="debug" style="font-size: 11px; background: #f5f5f8; padding: 8px;">
cols: {{ cols.length }}
rows: {{ rows.length }}
placeholder qty: {{ placeholderQtySum }}
</pre>
    </div>
  </n-card>
</template>

<script setup>
import { ref, computed } from 'vue'
import { NCard } from 'naive-ui'

const props = defineProps({
  hcId: { type: String, required: true },
  hcStatus: { type: String, required: true },
  groups: { type: Array, required: true },  // backend breakdown response
})
const emit = defineEmits(['saved'])

const collapsed = ref(false)

// --- Transpose backend groups → rows (customer-major) + cols (jewelry-major) ---

// cols: one entry per jewelry/part group in backend order
const cols = computed(() =>
  (props.groups || []).map((g) => ({
    key: `${g.kind}:${g.jewelry_id}`,
    kind: g.kind,
    jewelry_id: g.jewelry_id,
    jewelry_name: g.jewelry_name,
    total_qty: Number(g.total_qty),
  })),
)

// rows: derived from entries with non-empty customer_name.
// Locked customers first (in their first-seen order), then manual customers
// (also first-seen). Each row aggregates entries by (customer, jewelry).
const rows = computed(() => {
  const order = []     // [customer_name, ...] in display order
  const seen = new Set()
  const isLockedCust = new Map()  // customer_name → boolean (any entry locked?)

  // First pass — locked customers
  for (const g of props.groups || []) {
    for (const e of g.entries || []) {
      const name = e.customer_name
      if (!name || !e.is_locked) continue
      if (!seen.has(name)) {
        seen.add(name)
        order.push(name)
        isLockedCust.set(name, true)
      }
    }
  }
  // Second pass — manual customers
  for (const g of props.groups || []) {
    for (const e of g.entries || []) {
      const name = e.customer_name
      if (!name || e.is_locked) continue
      if (!seen.has(name)) {
        seen.add(name)
        order.push(name)
        if (!isLockedCust.has(name)) isLockedCust.set(name, false)
      }
    }
  }

  // Build per-cell aggregates
  return order.map((name) => {
    const cellsByCol = {}
    for (const g of props.groups || []) {
      const colKey = `${g.kind}:${g.jewelry_id}`
      const matchingEntries = (g.entries || []).filter((e) => e.customer_name === name)
      const lockedEntries = matchingEntries.filter((e) => e.is_locked)
      const manualEntries = matchingEntries.filter((e) => !e.is_locked)
      cellsByCol[colKey] = {
        lockedQty: lockedEntries.reduce((s, e) => s + Number(e.qty), 0),
        lockedSources: lockedEntries.map((e) => e.source_order_id).filter(Boolean),
        manualQty: manualEntries.reduce((s, e) => s + Number(e.qty), 0),
        manualEntryIds: manualEntries.map((e) => e.hc_jewelry_item_id),
      }
    }
    const rowSum = Object.values(cellsByCol).reduce(
      (s, c) => s + c.lockedQty + c.manualQty, 0,
    )
    return {
      customer_name: name,
      is_locked_customer: isLockedCust.get(name) || false,
      cells: cellsByCol,
      row_sum: rowSum,
    }
  })
})

// Placeholder entries: customer_name is null/empty, is_locked false
const placeholderEntries = computed(() => {
  const out = []
  for (const g of props.groups || []) {
    for (const e of g.entries || []) {
      const name = (e.customer_name || '').trim()
      if (!name && !e.is_locked) {
        out.push({ ...e, _col_key: `${g.kind}:${g.jewelry_id}` })
      }
    }
  }
  return out
})

const placeholderQtySum = computed(() =>
  placeholderEntries.value.reduce((s, e) => s + Number(e.qty), 0),
)

// Per-column "assigned" total = sum of all rows' (locked + manual) for that col.
// "Remaining" per col = total_qty - assigned.
const colAssigned = computed(() => {
  const m = {}
  for (const c of cols.value) m[c.key] = 0
  for (const r of rows.value) {
    for (const k of Object.keys(r.cells)) {
      m[k] = (m[k] || 0) + r.cells[k].lockedQty + r.cells[k].manualQty
    }
  }
  return m
})

const totalAssigned = computed(() =>
  Object.values(colAssigned.value).reduce((s, n) => s + n, 0),
)
const totalAll = computed(() =>
  cols.value.reduce((s, c) => s + c.total_qty, 0),
)

const statusTagText = computed(() => {
  if (rows.value.length === 0) {
    return `未分拣 · ${totalAssigned.value}/${totalAll.value}`
  }
  if (props.hcStatus === 'pending') return `pending · 可编辑`
  if (props.hcStatus === 'processing') return `processing · 仅可改客户名 / 删未发出行`
  if (props.hcStatus === 'completed') return `completed · 只读`
  return props.hcStatus
})
</script>

<style scoped>
.bm-head { display: flex; align-items: center; gap: 10px; cursor: pointer; font-size: 14px; }
.chev { color: #888; }
.title { font-weight: 600; }
.status-tag { font-size: 11px; color: #b76100; background: #fff5e0; padding: 2px 8px; border-radius: 10px; font-weight: 400; }
.debug { white-space: pre-wrap; }
</style>
```

- [ ] **Step 2: Smoke check build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/BreakdownMatrix.vue
git commit -m "feat(frontend): BreakdownMatrix skeleton with transpose logic"
```

---

## Task 8: BreakdownMatrix.vue — read-only matrix render (4-state cells)

Replace the debug `<pre>` with a proper read-only table. Implements all 4 cell states and locked customer rows. No editing yet.

**Files:**
- Modify: `frontend/src/components/BreakdownMatrix.vue`

- [ ] **Step 1: Replace the debug placeholder with a real table**

Replace the `<div v-show="!collapsed">` block (the one containing `<pre class="debug">`) with:

```vue
    <div v-show="!collapsed">
      <table class="mx">
        <thead>
          <tr>
            <th class="mx__col-cust">客户</th>
            <th v-for="c in cols" :key="c.key" class="mx__col-jw">
              <span class="jid">{{ c.jewelry_id }}</span>
              <span class="jname">{{ c.jewelry_name }}</span>
              <span class="jtot">{{ c.total_qty }} 套</span>
            </th>
            <th class="mx__col-sum">合计</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.customer_name">
            <td class="mx__cust">
              <template v-if="r.is_locked_customer">
                <div class="lock-name">{{ r.customer_name }}</div>
                <div v-if="lockedSourceLine(r)" class="lock-src">↗ {{ lockedSourceLine(r) }}</div>
              </template>
              <template v-else>
                <span class="manual-name">{{ r.customer_name }}</span>
              </template>
            </td>
            <td v-for="c in cols" :key="c.key" :class="cellClass(r.cells[c.key])">
              <CellReadonly :cell="r.cells[c.key]" />
            </td>
            <td class="mx__row-sum">{{ r.row_sum }}</td>
          </tr>
          <tr v-if="rows.length === 0" class="mx__empty">
            <td :colspan="cols.length + 2">尚未分配给任何客户</td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <td class="mx__foot-label">已分 / 总数</td>
            <td v-for="c in cols" :key="c.key" :class="footCellClass(c)">
              {{ colAssigned[c.key] }} / {{ c.total_qty }}
              <span v-if="colAssigned[c.key] === c.total_qty">✓</span>
              <span v-else>⚠</span>
            </td>
            <td class="mx__foot-total">{{ totalAssigned }} / {{ totalAll }}</td>
          </tr>
        </tfoot>
      </table>
    </div>
```

- [ ] **Step 2: Add the inline `CellReadonly` sub-component**

Add a `<script setup>` defineComponent or a separate inline component. Inside the same SFC, add a child component definition before the main `<script setup>` block, OR import an inline one. For simplicity, define it in the same script using a render function:

Add this above the existing `defineProps` call in the `<script setup>`:

```javascript
import { h, defineComponent } from 'vue'

const CellReadonly = defineComponent({
  name: 'CellReadonly',
  props: { cell: { type: Object, required: true } },
  setup(props) {
    return () => {
      const c = props.cell
      if (!c || (c.lockedQty === 0 && c.manualQty === 0)) {
        return h('span', { class: 'qty-empty' }, '—')
      }
      if (c.lockedQty > 0 && c.manualQty === 0) {
        return h('span', { class: 'qty-locked' }, [
          String(c.lockedQty),
          h('span', { class: 'lock-icon' }, ' 🔒'),
        ])
      }
      if (c.lockedQty === 0 && c.manualQty > 0) {
        return h('span', { class: 'qty-manual' }, String(c.manualQty))
      }
      // Mixed
      return h('span', { class: 'qty-mixed' }, [
        h('span', { class: 'l' }, `${c.lockedQty}🔒`),
        h('span', { class: 'plus' }, ' + '),
        h('span', { class: 'm' }, String(c.manualQty)),
      ])
    }
  },
})
```

Also add `import { h, defineComponent } from 'vue'` to the imports at the top.

- [ ] **Step 3: Add helper functions in `<script setup>`**

Add inside `<script setup>` (after the computed blocks):

```javascript
function cellClass(cell) {
  if (!cell) return ['mx__qty', 'empty']
  if (cell.lockedQty === 0 && cell.manualQty === 0) return ['mx__qty', 'empty']
  if (cell.lockedQty > 0 && cell.manualQty === 0) return ['mx__qty', 'locked']
  if (cell.lockedQty === 0 && cell.manualQty > 0) return ['mx__qty']
  return ['mx__qty', 'mixed']
}

function footCellClass(col) {
  return [
    'mx__foot-cell',
    colAssigned.value[col.key] === col.total_qty ? 'ok' : 'warn',
  ]
}

function lockedSourceLine(row) {
  // Collect first unique source_order_id across this row's cells
  const sources = new Set()
  for (const k of Object.keys(row.cells)) {
    for (const s of row.cells[k].lockedSources || []) sources.add(s)
  }
  return sources.size ? Array.from(sources).join(', ') : ''
}
```

- [ ] **Step 4: Add the CSS for the table**

Replace the existing `<style scoped>` block with:

```vue
<style scoped>
.bm-head { display: flex; align-items: center; gap: 10px; cursor: pointer; font-size: 14px; }
.chev { color: #888; }
.title { font-weight: 600; }
.status-tag {
  font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 400;
  background: #fff5e0; color: #b76100;
}

.mx { width: 100%; border-collapse: collapse; font-size: 12px; }
.mx th, .mx td { border: 1px solid #e8e8ec; padding: 7px 9px; text-align: center; vertical-align: middle; }
.mx thead th { background: #fafafc; font-weight: 600; padding: 6px 8px; }
.mx__col-cust { text-align: left; min-width: 140px; }
.mx__col-jw .jid { display: block; font-family: "SF Mono", Menlo, monospace; font-size: 10px; color: #999; font-weight: 400; line-height: 1.2; }
.mx__col-jw .jname { display: block; font-size: 12px; margin-top: 2px; }
.mx__col-jw .jtot { display: block; font-size: 10px; font-weight: 400; color: #888; font-family: "SF Mono", Menlo, monospace; margin-top: 2px; }
.mx__col-sum { width: 70px; color: #666; }

.mx__cust { text-align: left; background: #fafafc; padding: 6px 9px; }
.lock-name { color: rgba(0,0,0,.7); padding-left: 18px; position: relative; font-size: 12px; }
.lock-name::before { content: "🔒"; position: absolute; left: 0; }
.lock-src { color: #b76100; font-size: 10px; margin-left: 18px; font-family: "SF Mono", Menlo, monospace; margin-top: 2px; }
.manual-name { color: #333; }

.mx__qty { font-family: "SF Mono", Menlo, monospace; color: #333; min-width: 86px; height: 38px; }
.mx__qty.empty { color: #ccc; }
.mx__qty.locked { background: #fff8e6; color: #8a6500; }
.mx__qty.mixed { background: linear-gradient(to right, #fff8e6 50%, #ffffff 50%); }
.qty-empty { color: #ccc; }
.qty-locked { color: #8a6500; }
.qty-mixed .l { color: #8a6500; }
.qty-mixed .plus { color: #888; }

.mx__row-sum { font-family: "SF Mono", Menlo, monospace; background: #fafafc; color: #555; }

.mx__empty td {
  height: 60px; color: #aaa; font-size: 12px;
  background: repeating-linear-gradient(45deg, #fafafc 0 6px, #f4f4f8 6px 12px);
}

.mx tfoot td { background: #eef0fe; font-family: "SF Mono", Menlo, monospace; font-size: 11px; color: #4338ca; padding: 7px 10px; }
.mx__foot-label { font-family: -apple-system, sans-serif; text-align: left; font-weight: 600; }
.mx__foot-cell.ok { color: #18a058; }
.mx__foot-cell.warn { color: #d03050; }
.mx__foot-total { color: #4338ca; }
</style>
```

- [ ] **Step 5: Smoke check build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 6: User smoke test — read-only matrix shows correctly**

Ask the user to:
1. Start backend (`python main.py`) and frontend (`cd frontend && npm run dev`)
2. Temporarily replace the existing `<BreakdownChips>` usage with `<BreakdownMatrix :hc-id="route.params.id" :hc-status="order?.status || 'pending'" :groups="breakdownGroups" />` to see the new component **in place of** the old one. (Or open HandcraftDetail.vue and add a side-by-side render.)
3. Visit an HC detail page with a mix of locked + manual + mixed cells
4. Verify cells render correctly across all 4 states; the locked customer row shows `↗ OR-XX`; the footer shows the right `已分 / 总数` per column

If smoke test passes, revert any temporary integration (we'll do the real integration in Task 17).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/BreakdownMatrix.vue
git commit -m "feat(frontend): BreakdownMatrix read-only render with 4-state cells"
```

---

## Task 9: BreakdownMatrix.vue — edit mode toggle and structure

Add the top-level edit/cancel/save buttons and the rendering branch for "edit mode". The edit-mode rendering of cells comes in the next task — for now, edit mode just renders the read-only cells too, so we can confirm the mode toggle works.

**Files:**
- Modify: `frontend/src/components/BreakdownMatrix.vue`

- [ ] **Step 1: Add a `mode` ref and update header actions**

In `<script setup>`, add after `const collapsed = ref(false)`:

```javascript
// 'view' = read-only, 'edit' = editing local snapshot
const mode = ref('view')
const saving = ref(false)
const message = useMessage()

// Snapshot rows + placeholder entries when entering edit mode, so we can
// compute a diff at save time. `entriesIndex` lets the diff look up the
// per-id (qty, original customer_name) so it can detect "this id moved
// from a placeholder into a customer row" and emit a single PATCH rather
// than (ADD + PATCH) double-writes.
const draft = ref(null)  // { rows: [...], placeholderEntries: [...], entriesIndex: Map<id, {qty, customer_name}> }

function enterEdit() {
  // Deep-clone for safe local mutation. JSON round-trip is fine here:
  // no Date / Map / function values in this state.
  const index = new Map()
  for (const g of props.groups || []) {
    for (const e of g.entries || []) {
      index.set(e.hc_jewelry_item_id, {
        qty: Number(e.qty),
        customer_name: e.customer_name || null,
        is_locked: !!e.is_locked,
      })
    }
  }
  draft.value = {
    rows: JSON.parse(JSON.stringify(rows.value)),
    placeholderEntries: JSON.parse(JSON.stringify(placeholderEntries.value)),
    entriesIndex: index,  // NOT serialized — Maps survive direct assignment fine
  }
  mode.value = 'edit'
}

function cancelEdit() {
  draft.value = null
  mode.value = 'view'
}

const canEdit = computed(() => props.hcStatus !== 'completed')
```

Add `useMessage` to the `naive-ui` import: replace
```javascript
import { NCard } from 'naive-ui'
```
with
```javascript
import { NCard, NButton, useMessage } from 'naive-ui'
```

- [ ] **Step 2: Add action buttons in the header**

Replace the existing `<template #header>` block with:

```vue
    <template #header>
      <div class="bm-head-wrap">
        <div class="bm-head" @click="collapsed = !collapsed">
          <span class="chev">{{ collapsed ? '▸' : '▾' }}</span>
          <span class="title">客户分拣</span>
          <span class="status-tag">{{ statusTagText }}</span>
        </div>
        <div v-if="!collapsed" class="bm-actions">
          <template v-if="mode === 'view'">
            <n-button size="small" :disabled="!canEdit" @click.stop="enterEdit">编辑</n-button>
          </template>
          <template v-else>
            <n-button size="small" :disabled="saving" @click.stop="cancelEdit">取消</n-button>
            <n-button size="small" type="primary" :loading="saving" @click.stop="save">保存</n-button>
          </template>
        </div>
      </div>
    </template>
```

- [ ] **Step 3: Add a stub `save()` placeholder**

In `<script setup>`, add (we'll fill the real implementation in Task 11):

```javascript
async function save() {
  message.warning('保存逻辑将在后续任务实现')
  cancelEdit()
}
```

- [ ] **Step 4: Update CSS**

Add to `<style scoped>` (before the closing `</style>`):

```css
.bm-head-wrap { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.bm-actions { display: flex; gap: 6px; }
```

- [ ] **Step 5: Smoke check build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/BreakdownMatrix.vue
git commit -m "feat(frontend): BreakdownMatrix edit-mode toggle and action buttons"
```

---

## Task 10: BreakdownMatrix.vue — cell editing (number input, customer name, row delete, add row)

Wire up the editable cell renderer, customer name editing per row, row delete, and "+ 加一行客户". Bulk-assign comes in the next task.

**Files:**
- Modify: `frontend/src/components/BreakdownMatrix.vue`

- [ ] **Step 1: Add `CellEditable` sub-component (in `<script setup>`)**

Add after the `CellReadonly` definition:

```javascript
const CellEditable = defineComponent({
  name: 'CellEditable',
  props: {
    cell: { type: Object, required: true },
    qtyEditable: { type: Boolean, default: true },  // false when status forbids
    onChange: { type: Function, required: true },   // (newManualQty: number) => void
  },
  setup(props) {
    return () => {
      const c = props.cell
      const showLock = c.lockedQty > 0
      const input = h('input', {
        type: 'number',
        min: 0,
        value: c.manualQty,
        disabled: !props.qtyEditable,
        class: ['cell-input', c.manualQty === 0 ? 'zero' : ''],
        onInput: (e) => {
          const v = Number(e.target.value)
          props.onChange(Number.isFinite(v) && v >= 0 ? v : 0)
        },
      })
      if (showLock && c.manualQty > 0) {
        return h('span', { class: 'qty-mixed' }, [
          h('span', { class: 'l' }, `${c.lockedQty}🔒`),
          h('span', { class: 'plus' }, ' + '),
          input,
        ])
      }
      if (showLock) {
        return h('span', { class: 'qty-locked-edit' }, [
          h('span', { class: 'l' }, `${c.lockedQty}🔒`),
          h('span', { class: 'plus' }, ' + '),
          input,
        ])
      }
      return input
    }
  },
})
```

- [ ] **Step 2: Wire `mode === 'edit'` branch in the table body**

In the template, replace the existing `<tr v-for="r in rows" ...>` with two branches — one for `view` and one for `edit`. Refactor as:

```vue
        <tbody v-if="mode === 'view'">
          <tr v-for="r in rows" :key="r.customer_name">
            <td class="mx__cust">
              <template v-if="r.is_locked_customer">
                <div class="lock-name">{{ r.customer_name }}</div>
                <div v-if="lockedSourceLine(r)" class="lock-src">↗ {{ lockedSourceLine(r) }}</div>
              </template>
              <template v-else>
                <span class="manual-name">{{ r.customer_name }}</span>
              </template>
            </td>
            <td v-for="c in cols" :key="c.key" :class="cellClass(r.cells[c.key])">
              <CellReadonly :cell="r.cells[c.key]" />
            </td>
            <td class="mx__row-sum">{{ r.row_sum }}</td>
          </tr>
          <tr v-if="rows.length === 0" class="mx__empty">
            <td :colspan="cols.length + 2">尚未分配给任何客户</td>
          </tr>
        </tbody>

        <tbody v-else>
          <tr v-for="(r, ri) in draft.rows" :key="`${r.customer_name}:${ri}`">
            <td class="mx__cust">
              <template v-if="r.is_locked_customer">
                <div class="lock-name">{{ r.customer_name }}</div>
                <div v-if="lockedSourceLine(r)" class="lock-src">↗ {{ lockedSourceLine(r) }}</div>
              </template>
              <template v-else>
                <div class="manual-edit">
                  <div class="manual-edit__name">
                    <CustomerNameSelect
                      v-if="canEditCustomerName"
                      v-model:value="r.customer_name"
                      :disabled="!canEditCustomerName"
                    />
                    <span v-else class="manual-name">{{ r.customer_name }}</span>
                  </div>
                  <n-button
                    v-if="canDeleteRow(r)"
                    text
                    type="error"
                    size="tiny"
                    @click="removeDraftRow(ri)"
                  >×</n-button>
                </div>
              </template>
            </td>
            <td v-for="c in cols" :key="c.key" :class="cellClass(r.cells[c.key])">
              <CellEditable
                v-if="!r.is_locked_customer || r.cells[c.key].manualQty > 0 || canAddNewManual"
                :cell="r.cells[c.key]"
                :qty-editable="canEditQty"
                :on-change="(v) => setCellManual(r, c.key, v)"
              />
              <CellReadonly v-else :cell="r.cells[c.key]" />
            </td>
            <td class="mx__row-sum">{{ draftRowSum(r) }}</td>
          </tr>
          <tr v-if="draft.rows.length === 0" class="mx__empty">
            <td :colspan="cols.length + 2">尚未分配给任何客户</td>
          </tr>
          <tr v-if="canAddNewRow" class="mx__add-bar-row">
            <td :colspan="cols.length + 2">
              <div class="add-bar">
                <span class="add-bar__link" @click="addDraftRow">+ 加一行客户</span>
                <!-- bulk-assign button slot — Task 11 -->
              </div>
            </td>
          </tr>
        </tbody>
```

- [ ] **Step 3: Add helpers + computed gates in `<script setup>`**

Add after `function cancelEdit()`:

```javascript
// Status gates (sourced from the spec's state matrix)
const canAddNewRow = computed(() => props.hcStatus === 'pending')
const canAddNewManual = computed(() => props.hcStatus === 'pending')  // new manual entry on existing row
const canEditQty = computed(() => props.hcStatus === 'pending')
const canEditCustomerName = computed(() => props.hcStatus !== 'completed')

function canDeleteRow(r) {
  if (r.is_locked_customer) return false
  if (props.hcStatus === 'completed') return false
  // processing: only deletable if all manual entries have received_qty == 0
  // (the spec defers exact check to backend; we let DELETE fail loudly if
  // backend rejects, but block obviously-bad delete attempts here)
  if (props.hcStatus === 'processing') {
    // we don't have received_qty per cell in the matrix; rely on backend
    // (a refresh on save-failure will surface remaining state)
  }
  return true
}

function draftRowSum(r) {
  return Object.values(r.cells).reduce((s, c) => s + c.lockedQty + c.manualQty, 0)
}

function setCellManual(r, colKey, newQty) {
  // Mutate the draft row's cell.manualQty in place; mark internal flag for diff.
  const cell = r.cells[colKey]
  cell.manualQty = Number(newQty) || 0
  r._dirty = true
}

function addDraftRow() {
  // New empty manual row; customer_name empty until user picks
  const cells = {}
  for (const c of cols.value) {
    cells[c.key] = { lockedQty: 0, lockedSources: [], manualQty: 0, manualEntryIds: [] }
  }
  draft.value.rows.push({
    customer_name: '',
    is_locked_customer: false,
    cells,
    row_sum: 0,
    _new: true,
    _dirty: true,
  })
}

function removeDraftRow(idx) {
  draft.value.rows.splice(idx, 1)
}
```

- [ ] **Step 4: Update imports + add CSS**

In `<script setup>` imports, add `CustomerNameSelect`:
```javascript
import CustomerNameSelect from './CustomerNameSelect.vue'
```

Add to `<style scoped>`:
```css
.manual-edit { display: flex; gap: 6px; align-items: center; }
.manual-edit__name { flex: 1; }
.cell-input {
  width: 56px; padding: 3px 6px; border: 1px solid #d0d0d6;
  border-radius: 3px; font-family: "SF Mono", Menlo, monospace;
  font-size: 12px; text-align: center;
}
.cell-input:focus { outline: none; border-color: #2080f0; box-shadow: 0 0 0 2px rgba(32,128,240,.12); }
.cell-input.zero { color: #999; }
.cell-input:disabled { background: #fafafa; color: #777; }
.qty-locked-edit { display: inline-flex; align-items: center; gap: 4px; }
.qty-locked-edit .l { color: #8a6500; }
.qty-mixed .plus, .qty-locked-edit .plus { color: #888; }
.mx__add-bar-row td { padding: 6px 10px; background: #f9f9fc; text-align: left; }
.add-bar { display: flex; gap: 10px; align-items: center; }
.add-bar__link { color: #4338ca; cursor: pointer; padding: 4px 8px; border-radius: 3px; font-size: 12px; }
.add-bar__link:hover { background: #eef0fe; }
```

- [ ] **Step 5: Smoke check build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/BreakdownMatrix.vue
git commit -m "feat(frontend): BreakdownMatrix cell editing (input, picker, +/×)"
```

---

## Task 11: BreakdownMatrix.vue — save diff logic

Implement the real `save()` that diffs `draft.value.rows` against the original `rows` and `placeholderEntries`, then sequentially DELETE / PATCH / POST against the backend.

**Files:**
- Modify: `frontend/src/components/BreakdownMatrix.vue`

- [ ] **Step 1: Import handcraft API helpers**

Add to `<script setup>` imports:

```javascript
import {
  addHandcraftJewelry,
  updateHandcraftJewelry,
  deleteHandcraftJewelry,
} from '@/api/handcraft'
```

- [ ] **Step 2: Replace stub `save()` with real implementation**

Replace the existing stub:

```javascript
async function save() {
  message.warning('保存逻辑将在后续任务实现')
  cancelEdit()
}
```

with:

```javascript
async function save() {
  if (saving.value) return
  saving.value = true
  let mutated = false

  try {
    // Compose the operation lists by diffing draft vs original.
    const operations = computeDiff()

    // Validate: customer name required on every kept row
    for (const op of [...operations.adds, ...operations.patches]) {
      if (op.customer_name !== undefined && (!op.customer_name || !op.customer_name.trim())) {
        message.error('客户名不能为空')
        saving.value = false
        return
      }
    }

    // 1. DELETE first
    for (const id of operations.deletes) {
      await deleteHandcraftJewelry(props.hcId, id)
      mutated = true
    }
    // 2. PATCH next
    for (const p of operations.patches) {
      const payload = {}
      if (p.qty !== undefined) payload.qty = p.qty
      if (p.customer_name !== undefined) payload.customer_name = p.customer_name
      if (Object.keys(payload).length === 0) continue
      await updateHandcraftJewelry(props.hcId, p.id, payload)
      mutated = true
    }
    // 3. POST last
    for (const a of operations.adds) {
      const payload = {
        qty: a.qty,
        customer_name: a.customer_name,
      }
      if (a.jewelry_id) payload.jewelry_id = a.jewelry_id
      if (a.part_id) payload.part_id = a.part_id
      await addHandcraftJewelry(props.hcId, payload)
      mutated = true
    }

    message.success('已保存')
    mode.value = 'view'
    draft.value = null
  } catch (err) {
    message.error(err?.response?.data?.detail || '保存失败,请刷新核对')
  } finally {
    if (mutated) emit('saved')
    saving.value = false
  }
}

/**
 * Compute the diff between draft state and original state.
 * Returns {deletes: [item_id, ...], patches: [...], adds: [...]}.
 *
 * Model: each cell in draft.rows has `manualEntryIds` (which IDs back this cell)
 * and `manualQty` (the displayed total). Bulk-assign (Task 12) moves placeholder
 * IDs from `draft.placeholderEntries` INTO `cell.manualEntryIds` and bumps
 * `cell.manualQty` by the placeholder qty. computeDiff detects IDs newly present
 * in a draft cell (vs the original) and emits PATCH customer_name for each.
 *
 * Rules:
 * - newIds in cell (present in draft but not original) → PATCH(id, customer_name=row.name)
 *   (covers bulk-assigned placeholder IDs)
 * - removedIds in cell (in original but not in draft) → DELETE
 * - cell.manualQty - origCell.manualQty - sum(qty of newIds) = userDelta
 *     - userDelta > 0 → ADD (qty=userDelta) (only allowed in pending; backend enforces)
 *     - userDelta < 0 → PATCH first remaining id, qty = origCell.qty - sum(deletedQty) + userDelta
 *     - userDelta == 0 → no qty op
 * - row.customer_name changed vs orig → PATCH customer_name on every retained id
 *   (PATCH-customer-name + PATCH-qty can collapse to one op per id)
 * - Brand-new customer row (not in original): ADD per non-zero cell
 * - Customer row removed from draft entirely → DELETE all manualEntryIds (locked rows skipped)
 */
function computeDiff() {
  const deletes = []
  const patches = []     // [{id, qty?, customer_name?}, ...]
  const adds = []        // [{customer_name, qty, jewelry_id?, part_id?}, ...]
  const idx = draft.value.entriesIndex

  // Index original rows by customer_name for fast lookup
  const originalByName = new Map()
  for (const r of rows.value) originalByName.set(r.customer_name, r)
  const draftNames = new Set(draft.value.rows.map((r) => r.customer_name))

  // Helper: merge PATCH ops for the same id (qty + customer_name in one call)
  const patchById = new Map()
  function patch(id, fields) {
    const existing = patchById.get(id) || { id }
    patchById.set(id, { ...existing, ...fields })
  }

  // Unified per-row diff: orig may be undefined (brand-new row).
  // For brand-new rows, origCell is treated as empty — so all draft ids are
  // newIds and trigger PATCH(customer_name=...). For existing rows, renames
  // and qty edits flow through the same logic.
  for (const r of draft.value.rows) {
    const orig = originalByName.get(r.customer_name)
    const renameChanged = orig && r.customer_name !== orig.customer_name
    for (const c of cols.value) {
      const cell = r.cells[c.key]
      const origCell = (orig?.cells || {})[c.key] || { manualQty: 0, manualEntryIds: [] }
      const origIdSet = new Set(origCell.manualEntryIds || [])
      const draftIdSet = new Set(cell.manualEntryIds || [])

      const newIds = (cell.manualEntryIds || []).filter((id) => !origIdSet.has(id))
      const removedIds = (origCell.manualEntryIds || []).filter((id) => !draftIdSet.has(id))

      // 1. DELETE removed ids
      for (const id of removedIds) deletes.push(id)

      // 2. PATCH customer_name for new ids (bulk-claimed placeholders or
      //    ids moved from a different row). Also PATCH retained ids if
      //    the customer name was renamed in place.
      for (const id of newIds) patch(id, { customer_name: r.customer_name })
      if (renameChanged) {
        for (const id of cell.manualEntryIds || []) {
          if (!newIds.includes(id)) patch(id, { customer_name: r.customer_name })
        }
      }

      // 3. Qty conservation:
      //   origCell.manualQty - removedIdsQty + newIdsQty + userDelta = cell.manualQty
      const newIdsQty = newIds.reduce((s, id) => s + (idx.get(id)?.qty || 0), 0)
      const removedIdsQty = removedIds.reduce((s, id) => s + (idx.get(id)?.qty || 0), 0)
      const userDelta = cell.manualQty - origCell.manualQty + removedIdsQty - newIdsQty

      if (userDelta > 0) {
        adds.push({
          customer_name: r.customer_name,
          qty: userDelta,
          jewelry_id: c.kind === 'jewelry' ? c.jewelry_id : undefined,
          part_id: c.kind === 'part' ? c.jewelry_id : undefined,
        })
      } else if (userDelta < 0) {
        // Need to reduce by abs(userDelta). Prefer reducing a retained id,
        // else a newly-claimed id (each backed by `idx`'s qty). Walk through
        // candidates until the reduction is exhausted.
        const candidates = [
          ...(cell.manualEntryIds || []).filter((id) => origIdSet.has(id)),
          ...newIds,
        ]
        let remaining = -userDelta
        for (const id of candidates) {
          if (remaining <= 0) break
          const baseQty = idx.get(id)?.qty || 0
          if (baseQty === 0) continue
          if (baseQty <= remaining) {
            deletes.push(id)
            remaining -= baseQty
          } else {
            patch(id, { qty: baseQty - remaining })
            remaining = 0
          }
        }
        // remaining > 0 here would mean the user reduced below 0 — guarded
        // by the input's `min=0`, so this should not be reachable.
      }
    }
  }

  // Customer rows that existed but are now gone from draft → DELETE their manual ids.
  // EXCEPT ids that moved to a different draft row (rename / regroup) — those will
  // be PATCHed by the destination row's loop above, so DELETE-ing them here would
  // either run first and break the PATCH, or run after and undo the rename.
  const draftAllIds = new Set()
  for (const r of draft.value.rows) {
    for (const k of Object.keys(r.cells)) {
      for (const id of r.cells[k].manualEntryIds || []) draftAllIds.add(id)
    }
  }
  for (const r of rows.value) {
    if (draftNames.has(r.customer_name)) continue
    if (r.is_locked_customer) continue
    for (const k of Object.keys(r.cells)) {
      for (const id of r.cells[k].manualEntryIds || []) {
        if (!draftAllIds.has(id)) deletes.push(id)
      }
    }
  }

  patches.push(...patchById.values())
  return { deletes, patches, adds }
}
```

- [ ] **Step 3: Smoke check build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/BreakdownMatrix.vue
git commit -m "feat(frontend): BreakdownMatrix save with diff (delete/patch/post)"
```

---

## Task 12: BreakdownMatrix.vue — bulk-assign integration

Wire the `BulkAssignPopover` into the add-bar. On confirm, set `customer_name` on all matching placeholder entries in the draft, mark them dirty, and add a `flash` highlight that fades.

**Files:**
- Modify: `frontend/src/components/BreakdownMatrix.vue`

- [ ] **Step 1: Add bulk-assign state + handler**

In `<script setup>`, add after the helper functions:

```javascript
import BulkAssignPopover from './BulkAssignPopover.vue'
import { NPopover } from 'naive-ui'

const bulkShow = ref(false)
const flashedColKeys = ref(new Set())  // for CSS pulse on newly-filled columns

const bulkPreviewItems = computed(() => {
  if (!draft.value) return []
  // For each column, sum the placeholder qty for that column
  const placeholderByCol = new Map()
  for (const pe of draft.value.placeholderEntries) {
    if ((pe.customer_name || '').trim()) continue  // already claimed by previous bulk click
    const k = pe._col_key
    placeholderByCol.set(k, (placeholderByCol.get(k) || 0) + Number(pe.qty))
  }
  return cols.value
    .filter((c) => placeholderByCol.get(c.key) > 0)
    .map((c) => ({
      jewelry_id: c.jewelry_id,
      jewelry_name: c.jewelry_name,
      delta: placeholderByCol.get(c.key),
    }))
})

const bulkHasLocked = computed(() => rows.value.some((r) => r.is_locked_customer))
const bulkHasPartialManual = computed(() => rows.value.some((r) => !r.is_locked_customer))

const canBulkAssign = computed(
  () => props.hcStatus === 'pending' && bulkPreviewItems.value.length > 0,
)

function onBulkConfirm(customerName) {
  const name = (customerName || '').trim()
  if (!name) return

  // 1. Find or create the destination customer row in draft.
  let row = draft.value.rows.find((r) => r.customer_name === name)
  if (!row) {
    const cells = {}
    for (const c of cols.value) {
      cells[c.key] = { lockedQty: 0, lockedSources: [], manualQty: 0, manualEntryIds: [] }
    }
    row = {
      customer_name: name,
      is_locked_customer: false,
      cells,
      row_sum: 0,
      _new: true,  // brand-new in draft; computeDiff treats it as new-row branch
      _dirty: true,
    }
    draft.value.rows.push(row)
  }

  // 2. Move all unclaimed placeholder entries INTO the row's cells.
  //    Their hc_jewelry_item_id is preserved in cell.manualEntryIds — the diff
  //    will detect these as "newIds" (in draft cell but not in original cell)
  //    and emit a single PATCH(id, customer_name=name) per id.
  const stillPending = []
  for (const pe of draft.value.placeholderEntries) {
    if ((pe.customer_name || '').trim()) {
      // already claimed in a previous bulk-click — keep in array but skip
      stillPending.push(pe)
      continue
    }
    const cell = row.cells[pe._col_key]
    if (!cell) {
      stillPending.push(pe)
      continue
    }
    cell.manualEntryIds.push(pe.hc_jewelry_item_id)
    cell.manualQty += Number(pe.qty)
    flashedColKeys.value.add(`${name}:${pe._col_key}`)
    // Mark the placeholder as claimed and remove it from the "pending" array
    // so subsequent bulk-clicks don't try to re-claim it. We tag it with the
    // claimer's name purely for symmetry with the bulkPreviewItems filter.
    pe.customer_name = name
  }
  // Rebuild placeholderEntries to only contain still-pending ones
  draft.value.placeholderEntries = stillPending

  bulkShow.value = false

  // 3. Schedule flash fade-out
  setTimeout(() => {
    flashedColKeys.value = new Set()
  }, 3000)
}
```

- [ ] **Step 2: Add the popover trigger inside the add-bar**

In the template, find the `<div class="add-bar">` block and add the bulk-assign trigger:

```vue
              <div class="add-bar">
                <span class="add-bar__link" @click="addDraftRow">+ 加一行客户</span>
                <span class="add-bar__sep">|</span>
                <n-popover
                  v-model:show="bulkShow"
                  :show-arrow="true"
                  placement="top"
                  trigger="manual"
                  :disabled="!canBulkAssign"
                >
                  <template #trigger>
                    <n-button
                      size="tiny"
                      :disabled="!canBulkAssign"
                      class="bulk-btn"
                      @click="bulkShow = !bulkShow"
                    >
                      ⚡ 一键剩余分给…
                    </n-button>
                  </template>
                  <BulkAssignPopover
                    :preview-items="bulkPreviewItems"
                    :has-locked="bulkHasLocked"
                    :has-partial-manual="bulkHasPartialManual"
                    @confirm="onBulkConfirm"
                    @cancel="bulkShow = false"
                  />
                </n-popover>
                <span v-if="!canBulkAssign" class="add-bar__hint">
                  {{ props.hcStatus !== 'pending' ? '仅 pending 状态可用' : '已无剩余可分' }}
                </span>
              </div>
```

- [ ] **Step 3: Mark flashed cells in render**

Modify `cellClass(...)` to accept a row + col context so it can add the `flash` class. Replace the existing `cellClass` and add helper:

```javascript
function cellClass(cell, rowName, colKey) {
  const out = []
  if (!cell || (cell.lockedQty === 0 && cell.manualQty === 0)) out.push('empty')
  if (cell?.lockedQty > 0 && cell.manualQty === 0) out.push('locked')
  if (cell?.lockedQty > 0 && cell?.manualQty > 0) out.push('mixed')
  if (rowName && colKey && flashedColKeys.value.has(`${rowName}:${colKey}`)) out.push('flash')
  return ['mx__qty', ...out]
}
```

Update the call sites in the template — find both `:class="cellClass(r.cells[c.key])"` occurrences and change to:

```vue
:class="cellClass(r.cells[c.key], r.customer_name, c.key)"
```

(Both the view tbody and edit tbody.)

- [ ] **Step 4: Add flash CSS + bulk-btn styling**

Append to `<style scoped>`:

```css
.add-bar__sep { color: #ccc; }
.add-bar__hint { color: #999; font-size: 11px; margin-left: 4px; }
.bulk-btn { color: #4338ca; }
.mx__qty.flash { background: #fffae8; transition: background 1.5s ease-out; }
.mx__qty.flash::after { content: "✨"; display: inline-block; margin-left: 4px; font-size: 10px; vertical-align: 2px; }
.mx__qty.flash .cell-input { border-color: #f0c000; box-shadow: 0 0 0 2px rgba(240,192,0,.16); }
```

- [ ] **Step 5: Smoke check build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/BreakdownMatrix.vue
git commit -m "feat(frontend): BreakdownMatrix bulk-assign popover integration"
```

---

## Task 13: BreakdownMatrix.vue — mobile sticky styles

Add the horizontal scroll wrapper, `position: sticky` on the customer column, and sticky-bottom action buttons when in edit mode.

**Files:**
- Modify: `frontend/src/components/BreakdownMatrix.vue`

- [ ] **Step 1: Wrap the table in a scroll container**

Replace the `<div v-show="!collapsed">` outer wrapper such that its child `<table class="mx">` is wrapped in a `<div class="mx-scroll">`:

```vue
    <div v-show="!collapsed">
      <div class="mx-scroll">
        <table class="mx">
          <!-- existing thead/tbody/tfoot — unchanged -->
        </table>
      </div>
      <!-- Sticky-bottom save bar appears only in edit mode on narrow screens -->
      <div v-if="mode === 'edit'" class="mx-sticky-foot">
        <n-button size="small" :disabled="saving" @click="cancelEdit">取消</n-button>
        <n-button size="small" type="primary" :loading="saving" @click="save">保存</n-button>
      </div>
    </div>
```

- [ ] **Step 2: Add the scroll + sticky CSS**

Append to `<style scoped>`:

```css
.mx-scroll { overflow-x: auto; }
.mx thead th.mx__col-cust,
.mx tbody td.mx__cust,
.mx tfoot td.mx__foot-label {
  position: sticky; left: 0; z-index: 2;
  background: #fafafc;  /* repeat the surface bg so cells don't bleed through */
}
.mx tfoot td.mx__foot-label { background: #eef0fe; }
.mx-sticky-foot {
  display: none;  /* hidden on wide screens — top-bar buttons suffice */
}
@media (max-width: 768px) {
  .mx-sticky-foot {
    display: flex; gap: 6px; justify-content: flex-end;
    position: sticky; bottom: 0; padding: 8px 12px;
    background: #fff; border-top: 1px solid #eee;
    box-shadow: 0 -2px 4px rgba(0,0,0,.04);
    z-index: 3;
  }
}
.mx__col-jw { min-width: 90px; }
```

- [ ] **Step 3: Smoke check build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/BreakdownMatrix.vue
git commit -m "feat(frontend): BreakdownMatrix mobile sticky-left + sticky-bottom"
```

---

## Task 14: Integrate `BreakdownMatrix` into `HandcraftDetail.vue`

Replace the existing card (lines around 275-302) and the related state, helpers, and imports.

**Files:**
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue`

- [ ] **Step 1: Inspect the current insertion site to anchor edits**

Run: `grep -n "BreakdownChips\|BreakdownEditModal\|breakdownGroups\|breakdown-group\|editBreakdown\|openBreakdownEditor\|onBreakdownSaved" frontend/src/views/handcraft/HandcraftDetail.vue`

Capture the line ranges for the touched blocks. Then proceed with edits below.

- [ ] **Step 2: Replace the breakdown card block**

Replace the `<n-card v-if="breakdownGroups.length > 0" ...>...</n-card>` block (around `HandcraftDetail.vue:275-302`) with:

```vue
      <BreakdownMatrix
        v-if="breakdownGroups.length > 0 || items.length > 0"
        :hc-id="route.params.id"
        :hc-status="order?.status || 'pending'"
        :groups="breakdownGroups"
        @saved="onBreakdownSaved"
        style="margin-top: 16px;"
      />
```

(`items.length > 0` keeps it visible for empty-customer HCs that still have jewelry plans.)

- [ ] **Step 3: Remove the `<BreakdownEditModal ...>` block**

Delete the block (around `HandcraftDetail.vue:305-312`):
```vue
    <BreakdownEditModal
      v-if="editBreakdownGroup"
      v-model:show="editBreakdownVisible"
      :hc-id="route.params.id"
      :hc-status="order?.status || 'pending'"
      :group="editBreakdownGroup"
      @saved="onBreakdownSaved"
    />
```

- [ ] **Step 4: Update imports**

Replace the lines:
```javascript
import BreakdownChips from '@/components/BreakdownChips.vue'
import BreakdownEditModal from '@/components/BreakdownEditModal.vue'
```
with:
```javascript
import BreakdownMatrix from '@/components/BreakdownMatrix.vue'
```

- [ ] **Step 5: Remove now-unused state / functions**

Search and remove:
- `const editBreakdownVisible = ref(false)`
- `const editBreakdownGroup = ref(null)`
- `function openBreakdownEditor(group) { ... }`
- The `collapsed.breakdown` ref entry — keep it (still used? — verify) or remove if dead. Run:
  - `grep -n "collapsed.breakdown" frontend/src/views/handcraft/HandcraftDetail.vue`
  - If only in the removed block, drop it from the `collapsed` object.

Keep `onBreakdownSaved` — `BreakdownMatrix` still emits `saved` and the handler likely refreshes data.

- [ ] **Step 6: Smoke check build**

Run: `cd frontend && npm run build`
Expected: build succeeds with no warnings about unused imports.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/handcraft/HandcraftDetail.vue
git commit -m "feat(frontend): swap BreakdownEditModal for BreakdownMatrix in HC detail"
```

---

## Task 15: Delete old components

After confirming the smoke test (Task 16) passes, remove the dead files.

**Files:**
- Delete: `frontend/src/components/BreakdownEditModal.vue`
- Delete: `frontend/src/components/BreakdownChips.vue`

- [ ] **Step 1: Re-verify no other references**

Run: `grep -rn "BreakdownChips\|BreakdownEditModal" frontend/src 2>/dev/null`
Expected: empty (the only references should be in `HandcraftDetail.vue` and already removed in Task 14; if not, fix them).

- [ ] **Step 2: Delete the files**

```bash
rm frontend/src/components/BreakdownEditModal.vue
rm frontend/src/components/BreakdownChips.vue
```

- [ ] **Step 3: Smoke check build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add -A frontend/src/components/
git commit -m "chore(frontend): remove BreakdownEditModal and BreakdownChips (replaced by BreakdownMatrix)"
```

---

## Task 16: End-to-end smoke test (user-driven)

Run through the spec's manual verification checklist with the user.

- [ ] **Step 1: Start backend + frontend**

Ask user to run:
```bash
# Terminal 1
python main.py
# Terminal 2
cd frontend && npm run dev
```

- [ ] **Step 2: Walk the user through each item below; capture pass/fail per item**

For each scenario, the user should report PASS or describe the deviation:

1. **Read-only render** — open an HC with locked + manual + mixed cells: 4 cell states render correctly; locked customer row shows `↗ OR-XX`; footer per-column "已分/总数" correct.
2. **pending edit + save** — click 编辑, change a manual qty, add a customer row, click 保存; refresh and confirm the change persisted.
3. **processing state** — open a processing HC: 编辑 still available; entering edit shows that qty inputs are disabled; only customer-name edit / row delete works; add-bar shows ⚡ as disabled with hint "仅 pending 状态可用".
4. **completed state** — open a completed HC: 编辑 button disabled; status tag reads `completed · 只读`.
5. **locked row** — confirm: customer name not editable; no × delete button; locked cells display correctly with hover hint.
6. **Mixed cell `N🔒 + [M]`** — confirm edit-mode renders both halves; changing the manual half + saving works.
7. **Save mid-failure** — temporarily mutate a row's customer_name to something that backend would reject (e.g. empty string after trimming), click 保存; confirm error toast appears and view doesn't escape edit mode (or refreshes correctly).
8. **Mobile (375px viewport)** — DevTools → toggle device toolbar → set to 375px wide: customer column sticks left while scrolling; in edit mode, sticky-bottom save bar appears.
9. **Empty state HC** — open an HC with jewelry plans but no assigned customers: header tag shows `未分拣 · 0/N`; body shows the diagonal-stripe placeholder; entering edit shows the add-bar.
10. **Bulk-assign · empty state** — empty HC: click 编辑 → ⚡ 一键 → popover shows `整单全部 N 套`; pick a new customer "李四" → 填入 → matrix shows a single 李四 row, all green; 保存; refresh confirms persistence.
11. **Bulk-assign · with locked row** — HC with张三 locked row + some unassigned placeholder qty: ⚡ 一键 → popover hint reads "不会动 🔒 锁定行"; pick 张三 → 填入; 张三 row becomes mixed.
12. **Bulk-assign · with partial manual** — HC where 李四 manually filled one cell + placeholders still exist on others: ⚡ 一键 → popover hint includes "其他客户已填的部分不变"; pick 李四 → 填入 累加到 李四 行.
13. **Bulk-assign disabled** — fully-assigned matrix: ⚡ button disabled + hint reads "已无剩余可分".

- [ ] **Step 3: Fix any failures**

For each FAIL: identify the cause, write a fix, re-run that single scenario.

- [ ] **Step 4: When all pass, commit final cleanups (if any)**

```bash
git add -A
git commit -m "chore: smoke test pass — breakdown matrix complete" --allow-empty
```

---

## Self-Review

After completing tasks, verify against the spec:

- [x] **Spec section coverage**
  - 视觉结构 → Tasks 7-9 (skeleton, render, edit toggle)
  - 单元格状态机 → Tasks 8, 10 (CellReadonly + CellEditable)
  - 客户行规则 → Task 10 (canDeleteRow, locked customer name readonly)
  - 客户名 picker → Tasks 4-5 (api + CustomerNameSelect)
  - 状态约束 → Task 10 (canAddNewRow, canEditQty, canEditCustomerName gates)
  - 校验 → Task 11 (save validates non-empty customer name)
  - 一键剩余分给 → Task 12 (BulkAssignPopover integration)
  - 保存策略 → Task 11 (DELETE → PATCH → POST sequential)
  - 手机端 → Task 13 (sticky-left, sticky-bottom)
  - 占位 entries 验证 → Task 1 (foundational test)
  - 后端 suggest API → Tasks 2-3
  - 删除旧组件 → Task 15

- [x] **No placeholders** — every step shows actual code, exact commands, expected outcomes.

- [x] **Type consistency** — `groups` (backend), `cols` (transposed jewelry-major), `rows` (customer-major) used consistently. `placeholderEntries` field name reused identically across Tasks 7, 11, 12. `cellClass(cell, rowName, colKey)` signature is consistent after Task 12 update.

- [x] **Real API paths** — uses `/api/handcraft/{id}/jewelries/{item_id}` (plural) consistently via `addHandcraftJewelry / updateHandcraftJewelry / deleteHandcraftJewelry`. The spec text's singular paths are corrected in the plan header.

---
