# 复制饰品 (Jewelry Copy) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "复制" action in 饰品管理 list that opens a prefilled modal and creates a new jewelry record cloning the source's basic info + BOM rows.

**Architecture:** Backend gets a new atomic endpoint `POST /api/jewelries/{source_id}/copy` that creates a new Jewelry (same category as source, override-able via request body) plus duplicates BOM rows. Frontend reuses the existing create/edit modal in a third "copy" mode (banner + disabled category + new save branch).

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic V2 (backend); Vue 3 + Naive UI + Pinia (frontend); pytest (tests).

**Spec:** `docs/superpowers/specs/2026-05-10-jewelry-copy-design.md`

---

## File Structure

| Path | Action | Responsibility |
|------|--------|----------------|
| `services/jewelry.py` | Modify | Add `copy_jewelry()` |
| `schemas/jewelry.py` | Modify | Add `JewelryCopyRequest` |
| `api/jewelries.py` | Modify | Add `POST /{source_id}/copy` endpoint |
| `tests/test_jewelry.py` | Modify | Service-level tests for `copy_jewelry` |
| `tests/test_api_jewelries.py` | Modify | API-level tests for the new endpoint |
| `frontend/src/api/jewelries.js` | Modify | Add `copyJewelry()` |
| `frontend/src/views/jewelries/JewelryList.vue` | Modify | Banner, copy state, dropdown menu, save branch |

---

## Task 1: Service `copy_jewelry` (TDD)

**Files:**
- Modify: `services/jewelry.py`
- Test: `tests/test_jewelry.py`

- [ ] **Step 1.1: Write the failing service tests**

Append to `tests/test_jewelry.py`:

```python
# ---------------------------------------------------------------------------
# copy_jewelry tests
# ---------------------------------------------------------------------------

from services.jewelry import copy_jewelry
from services.bom import set_bom, get_bom
from services.part import create_part


def _seed_part(db, name="珍珠", category="小配件"):
    return create_part(db, {"name": name, "category": category, "unit": "颗"})


def test_copy_jewelry_basic_info(db):
    src = create_jewelry(db, {
        "name": "源套装",
        "category": "套装",
        "color": "金",
        "unit": "套",
        "retail_price": 200.0,
        "wholesale_price": 120.0,
        "image": "src.jpg",
        "structure_image": "src-struct.jpg",
        "handcraft_cost": 30.0,
    })
    new = copy_jewelry(db, src.id, {"name": "源套装-副本"})
    assert new.id != src.id
    assert new.id.startswith("SP-SET-")
    assert new.name == "源套装-副本"
    assert new.category == "套装"
    assert new.color == "金"
    assert new.unit == "套"
    assert float(new.retail_price) == 200.0
    assert float(new.wholesale_price) == 120.0
    assert new.image == "src.jpg"
    assert new.structure_image == "src-struct.jpg"
    assert float(new.handcraft_cost) == 30.0
    assert new.status == "active"


def test_copy_jewelry_clones_bom(db):
    src = create_jewelry(db, {"name": "S", "category": "单件"})
    p1 = _seed_part(db, name="珍珠")
    p2 = _seed_part(db, name="链子")
    set_bom(db, src.id, p1.id, 2.5)
    set_bom(db, src.id, p2.id, 1.0)

    new = copy_jewelry(db, src.id, {"name": "S-副本"})
    rows = get_bom(db, new.id)
    parts = {r.part_id: float(r.qty_per_unit) for r in rows}
    assert parts == {p1.id: 2.5, p2.id: 1.0}


def test_copy_jewelry_override_fields(db):
    src = create_jewelry(db, {"name": "S", "category": "单件", "color": "金", "retail_price": 50.0})
    new = copy_jewelry(db, src.id, {"name": "S-副本", "color": "银", "retail_price": 80.0})
    assert new.name == "S-副本"
    assert new.color == "银"
    assert float(new.retail_price) == 80.0


def test_copy_jewelry_ignores_category_in_override(db):
    src = create_jewelry(db, {"name": "S", "category": "套装"})
    new = copy_jewelry(db, src.id, {"name": "S-副本", "category": "单件"})
    assert new.category == "套装"
    assert new.id.startswith("SP-SET-")


def test_copy_jewelry_source_not_found(db):
    with pytest.raises(ValueError, match="Jewelry not found"):
        copy_jewelry(db, "SP-PCS-99999", {"name": "X"})


def test_copy_jewelry_empty_bom(db):
    src = create_jewelry(db, {"name": "S", "category": "单件"})
    new = copy_jewelry(db, src.id, {"name": "S-副本"})
    assert get_bom(db, new.id) == []
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `pytest tests/test_jewelry.py -v -k copy_jewelry`
Expected: 6 FAILs with `ImportError: cannot import name 'copy_jewelry' from 'services.jewelry'`.

- [ ] **Step 1.3: Implement `copy_jewelry` in `services/jewelry.py`**

Append at the end of `services/jewelry.py`:

```python
def copy_jewelry(db: Session, source_id: str, override_data: dict) -> Jewelry:
    """Clone a jewelry's basic info + BOM rows into a new jewelry record.

    - Raises ValueError if source_id does not exist.
    - Category is always inherited from source (any 'category' key in
      override_data is ignored).
    - Inventory log is NOT cloned; the new jewelry starts at stock 0.
    - status defaults to 'active'.
    """
    from models.bom import Bom
    from services._helpers import _next_id

    source = get_jewelry(db, source_id)
    if source is None:
        raise ValueError(f"Jewelry not found: {source_id}")

    base_data = {
        "name": source.name,
        "image": source.image,
        "structure_image": source.structure_image,
        "category": source.category,
        "color": source.color,
        "unit": source.unit,
        "retail_price": float(source.retail_price) if source.retail_price is not None else None,
        "wholesale_price": float(source.wholesale_price) if source.wholesale_price is not None else None,
        "handcraft_cost": float(source.handcraft_cost) if source.handcraft_cost is not None else None,
    }
    merged = {**base_data, **(override_data or {})}
    merged["category"] = source.category  # force, ignore any override

    new_jewelry = create_jewelry(db, merged)

    src_boms = db.query(Bom).filter(Bom.jewelry_id == source_id).all()
    for src_bom in src_boms:
        new_bom = Bom(
            id=_next_id(db, Bom, "BM"),
            jewelry_id=new_jewelry.id,
            part_id=src_bom.part_id,
            qty_per_unit=src_bom.qty_per_unit,
        )
        db.add(new_bom)
    db.flush()
    return new_jewelry
```

- [ ] **Step 1.4: Run tests to verify they pass**

Run: `pytest tests/test_jewelry.py -v -k copy_jewelry`
Expected: 6 PASS.

- [ ] **Step 1.5: Run the full service test file to make sure nothing broke**

Run: `pytest tests/test_jewelry.py -v`
Expected: all PASS.

- [ ] **Step 1.6: Commit**

```bash
git add services/jewelry.py tests/test_jewelry.py
git commit -m "feat(jewelry): add copy_jewelry service that clones basic info + BOM"
```

---

## Task 2: Schema `JewelryCopyRequest`

**Files:**
- Modify: `schemas/jewelry.py`

- [ ] **Step 2.1: Add the schema**

In `schemas/jewelry.py`, append after `JewelryUpdate`:

```python
class JewelryCopyRequest(BaseModel):
    name: str
    image: Optional[str] = None
    structure_image: Optional[str] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    retail_price: Optional[float] = None
    wholesale_price: Optional[float] = None
    handcraft_cost: Optional[float] = None
    # Note: no `category` field — category is forced to source jewelry's.
```

- [ ] **Step 2.2: Sanity-check the import**

Run: `python -c "from schemas.jewelry import JewelryCopyRequest; print(JewelryCopyRequest.model_fields.keys())"`
Expected: `dict_keys(['name', 'image', 'structure_image', 'color', 'unit', 'retail_price', 'wholesale_price', 'handcraft_cost'])`

- [ ] **Step 2.3: Commit**

```bash
git add schemas/jewelry.py
git commit -m "feat(jewelry): add JewelryCopyRequest schema"
```

---

## Task 3: API endpoint `POST /api/jewelries/{source_id}/copy` (TDD)

**Files:**
- Modify: `api/jewelries.py`
- Test: `tests/test_api_jewelries.py`

- [ ] **Step 3.1: Write failing API tests**

Append to `tests/test_api_jewelries.py`:

```python
def _put_bom(client, jewelry_id, part_id, qty):
    return client.put(f"/api/bom/{jewelry_id}/{part_id}", json={"qty_per_unit": qty})


def _create_part(client, name="珍珠", category="小配件"):
    return client.post("/api/parts/", json={"name": name, "category": category, "unit": "颗"}).json()


def test_copy_jewelry_basic(client):
    src = client.post("/api/jewelries/", json={
        "name": "源套装", "category": "套装", "color": "金", "unit": "套",
        "retail_price": 200.0, "wholesale_price": 120.0,
    }).json()
    p = _create_part(client)
    _put_bom(client, src["id"], p["id"], 1.5)

    resp = client.post(f"/api/jewelries/{src['id']}/copy", json={"name": "源套装-副本"})
    assert resp.status_code == 201
    new = resp.json()
    assert new["id"] != src["id"]
    assert new["id"].startswith("SP-SET-")
    assert new["name"] == "源套装-副本"
    assert new["category"] == "套装"
    assert new["color"] == "金"
    assert new["retail_price"] == 200.0

    bom_resp = client.get(f"/api/bom/{new['id']}")
    assert bom_resp.status_code == 200
    bom_rows = bom_resp.json()
    assert len(bom_rows) == 1
    assert bom_rows[0]["part_id"] == p["id"]
    assert float(bom_rows[0]["qty_per_unit"]) == 1.5


def test_copy_jewelry_new_stock_is_zero(client):
    src = client.post("/api/jewelries/", json={"name": "S", "category": "单件"}).json()
    # Inflate src stock via inventory adjust if available; otherwise rely on the
    # implicit guarantee — copy must NOT touch inventory_log for the new id.
    resp = client.post(f"/api/jewelries/{src['id']}/copy", json={"name": "S-副本"})
    new_id = resp.json()["id"]
    stock_resp = client.get(f"/api/inventory/jewelry/{new_id}")
    assert stock_resp.status_code == 200
    assert stock_resp.json()["current"] == 0


def test_copy_jewelry_source_not_found(client):
    resp = client.post("/api/jewelries/SP-PCS-99999/copy", json={"name": "X"})
    assert resp.status_code == 400


def test_copy_jewelry_missing_name(client):
    src = client.post("/api/jewelries/", json={"name": "S", "category": "单件"}).json()
    resp = client.post(f"/api/jewelries/{src['id']}/copy", json={})
    assert resp.status_code == 422


def test_copy_jewelry_override_fields(client):
    src = client.post("/api/jewelries/", json={
        "name": "S", "category": "单件", "color": "金", "retail_price": 50.0,
    }).json()
    resp = client.post(f"/api/jewelries/{src['id']}/copy", json={
        "name": "S-副本", "color": "银", "retail_price": 80.0,
    })
    new = resp.json()
    assert new["name"] == "S-副本"
    assert new["color"] == "银"
    assert new["retail_price"] == 80.0


def test_copy_jewelry_category_in_payload_ignored(client):
    src = client.post("/api/jewelries/", json={"name": "S", "category": "套装"}).json()
    resp = client.post(f"/api/jewelries/{src['id']}/copy", json={
        "name": "S-副本",
        "category": "单件",  # should be silently ignored by Pydantic + service guard
    })
    assert resp.status_code == 201
    new = resp.json()
    assert new["category"] == "套装"
    assert new["id"].startswith("SP-SET-")
```


- [ ] **Step 3.2: Run tests to verify they fail**

Run: `pytest tests/test_api_jewelries.py -v -k copy_jewelry`
Expected: 6 FAILs with 404 (route not registered).

- [ ] **Step 3.3: Add the endpoint to `api/jewelries.py`**

Update the import and append the route:

```python
from schemas.jewelry import JewelryCreate, JewelryUpdate, JewelryResponse, StatusUpdate, JewelryCopyRequest
from services.jewelry import (
    create_jewelry, get_jewelry, list_jewelries, update_jewelry,
    delete_jewelry, set_status, copy_jewelry,
)
```

Then append at the end of the file:

```python
@router.post("/{source_id}/copy", response_model=JewelryResponse, status_code=201)
def api_copy_jewelry(source_id: str, body: JewelryCopyRequest, db: Session = Depends(get_db)):
    with service_errors():
        new_jewelry = copy_jewelry(db, source_id, body.model_dump(exclude_unset=True))
    return new_jewelry
```

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `pytest tests/test_api_jewelries.py -v -k copy_jewelry`
Expected: 6 PASS.

- [ ] **Step 3.5: Run the full API test file to confirm no regression**

Run: `pytest tests/test_api_jewelries.py -v`
Expected: all PASS.

- [ ] **Step 3.6: Commit**

```bash
git add api/jewelries.py tests/test_api_jewelries.py
git commit -m "feat(jewelry): add POST /jewelries/{id}/copy endpoint"
```

---

## Task 4: Frontend API client

**Files:**
- Modify: `frontend/src/api/jewelries.js`

- [ ] **Step 4.1: Add `copyJewelry`**

Append to `frontend/src/api/jewelries.js`:

```js
export const copyJewelry = (sourceId, data) => api.post(`/jewelries/${sourceId}/copy`, data)
```

- [ ] **Step 4.2: Commit**

```bash
git add frontend/src/api/jewelries.js
git commit -m "feat(jewelry): add copyJewelry API client"
```

---

## Task 5: Frontend list page integration

**Files:**
- Modify: `frontend/src/views/jewelries/JewelryList.vue`

- [ ] **Step 5.1: Import the new API + add copy state**

In `<script setup>`, change the API import (around line 113) to include `copyJewelry`:

```js
import { listJewelries, createJewelry, updateJewelry, updateJewelryStatus, deleteJewelry, copyJewelry } from '@/api/jewelries'
```

After the `selectedTemplate` ref (around line 221), add:

```js
const copySourceId = ref(null)
const copySourceName = ref('')
```

- [ ] **Step 5.2: Show banner + copy mode title in modal**

Replace the modal opening tag (around line 30) — change the title:

```vue
<n-modal v-model:show="showModal" preset="card" :title="modalTitle" :style="{ width: isMobile ? '95vw' : '480px' }">
```

Add `NAlert` to the existing naive-ui import block (around line 110-112). The current line is:

```js
import {
  NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem,
  NModal, NDataTable, NSpin, NEmpty, NImage, NDropdown,
} from 'naive-ui'
```

Change to:

```js
import {
  NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem,
  NModal, NDataTable, NSpin, NEmpty, NImage, NDropdown, NAlert,
} from 'naive-ui'
```

Then add a computed for the title near the existing `canUseTemplates` computed (around line 125):

```js
const modalTitle = computed(() => {
  if (editingId.value) return '编辑饰品'
  if (copySourceId.value) return '复制饰品'
  return '新增饰品'
})
```

Inside the `<form @submit.prevent="save">` block, just before `<n-form ...>`, add the banner:

```vue
<n-alert
  v-if="copySourceId"
  type="warning"
  style="margin-bottom: 12px;"
>
  从 <b>{{ copySourceId }} {{ copySourceName }}</b> 复制（含 BOM 配件清单）。类目沿用源饰品。
</n-alert>
```

- [ ] **Step 5.3: Disable category in copy mode + adjust hint**

Find the existing category form item (around lines 53–60). Replace it with:

```vue
<n-form-item
  label="类目"
  path="category"
  :rule="(editingId || copySourceId) ? undefined : { required: true, message: '请选择类目', trigger: 'change' }"
>
  <n-select v-model:value="form.category" :options="categoryOptions" clearable placeholder="请选择类目" :disabled="!!editingId || !!copySourceId" />
  <span v-if="editingId" style="color: #999; font-size: 12px; margin-left: 8px;">类目不可修改</span>
  <span v-else-if="copySourceId" style="color: #999; font-size: 12px; margin-left: 8px;">复制时不可修改</span>
</n-form-item>
```

- [ ] **Step 5.4: Add `openCopy` and clear `copySourceId` in other open functions**

Around `openCreate` (line 275), update it to clear `copySourceId`:

```js
const openCreate = () => {
  editingId.value = null
  selectedTemplate.value = null
  copySourceId.value = null
  Object.assign(form, { name: '', image: '', category: null, color: '', unit: null, retail_price: null, wholesale_price: null })
  showModal.value = true
}
```

Update `openEdit` (line 282) similarly — set `copySourceId.value = null` at the top of the function.

Update `selectTemplate` (line 266) — add `copySourceId.value = null` after `selectedTemplate.value = tpl`.

Add a new function right after `openEdit`:

```js
const openCopy = (row) => {
  editingId.value = null
  selectedTemplate.value = null
  copySourceId.value = row.id
  copySourceName.value = row.name
  const cat = row.category && VALID_CATEGORIES.includes(row.category) ? row.category : null
  Object.assign(form, {
    name: `${row.name}-副本`,
    image: row.image || '',
    category: cat,
    color: row.color || '',
    unit: row.unit || null,
    retail_price: row.retail_price ?? null,
    wholesale_price: row.wholesale_price ?? null,
  })
  showModal.value = true
}
```

- [ ] **Step 5.5: Wire dropdown menu**

Find the actions render in `columns` (around lines 392–406). Replace the `NDropdown` block with:

```js
h(NDropdown, {
  options: [
    { label: '复制', key: 'copy' },
    { label: '删除', key: 'delete' },
  ],
  onSelect: (key) => {
    if (key === 'copy') openCopy(row)
    if (key === 'delete') confirmDelete(row)
  },
}, {
  default: () => h('button', { class: 'icon-btn', title: '更多' }, '⋮'),
}),
```

- [ ] **Step 5.6: Add the copy branch in `save()`**

Find `save()` (around line 307). Replace the function body with:

```js
const save = async () => {
  await formRef.value?.validate()
  saving.value = true
  try {
    if (editingId.value) {
      const { category, ...updateData } = form
      await updateJewelry(editingId.value, updateData)
      message.success('保存成功')
      showModal.value = false
      await load()
    } else if (copySourceId.value) {
      const { category, ...copyData } = form
      const { data: newJewelry } = await copyJewelry(copySourceId.value, copyData)
      message.success('复制成功')
      copySourceId.value = null
      copySourceName.value = ''
      showModal.value = false
      router.push(`/jewelries/${newJewelry.id}`)
    } else {
      const { data: newJewelry } = await createJewelry(form)
      if (selectedTemplate.value) {
        try {
          await applyTemplate(selectedTemplate.value.id, newJewelry.id)
          message.success('饰品已创建并导入模板 BOM')
        } catch (_) {
          message.success('饰品已创建，但模板导入失败')
        }
        selectedTemplate.value = null
        showModal.value = false
        router.push(`/jewelries/${newJewelry.id}`)
      } else {
        message.success('保存成功')
        showModal.value = false
        await load()
      }
    }
  } finally {
    saving.value = false
  }
}
```

- [ ] **Step 5.7: Build the frontend**

Run: `cd frontend && npm run build`
Expected: Vite build succeeds with no Vue compilation errors.

- [ ] **Step 5.8: Commit**

```bash
git add frontend/src/views/jewelries/JewelryList.vue
git commit -m "feat(jewelry): add 复制 action to jewelry list page"
```

---

## Task 6: Manual UI verification

**Files:** none

- [ ] **Step 6.1: Start backend + frontend dev servers**

In one terminal:
```bash
python main.py
```
In another:
```bash
cd frontend && npm run dev
```

- [ ] **Step 6.2: Verify happy path**

1. Open `http://localhost:5173/jewelries`
2. Pick any jewelry that has BOM rows (or first add a few BOM rows in the detail page)
3. Click "⋮" → "复制"
4. Confirm the modal:
   - Title is "复制饰品"
   - Yellow banner shows source ID + name + 提示文案
   - Name field is `${源名称}-副本`
   - All other fields prefilled
   - Category is disabled, hint shows "复制时不可修改"
5. Tweak the name + retail price, click 保存
6. Page navigates to `/jewelries/<new-id>`
7. Detail page shows:
   - New jewelry record with the values you entered
   - BOM table fully matches source (same parts + qty_per_unit)
   - 当前库存 = 0

- [ ] **Step 6.3: Verify mode reset**

1. Go back to list, click 「新增饰品」: form must be blank, no banner, category enabled.
2. Click 「⋮ → 复制」 on a row → reopen「编辑」on a different row → verify banner is gone, hint is "类目不可修改".

- [ ] **Step 6.4: Verify validation**

1. Click 复制 → empty out the name → click 保存 → expect "请输入名称".

- [ ] **Step 6.5: Mark complete**

If all five checks pass, the feature is done. Otherwise file findings as additional issues.

---

## Self-Review Checklist (do NOT skip)

After implementation, run end-to-end:

```bash
pytest tests/test_jewelry.py tests/test_api_jewelries.py -v
```
All must pass.

Frontend smoke check from Task 6 must all pass.
