# 订单附加信息 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add barcode requirements, mark requirements, and general notes fields to orders for internal production reference.

**Architecture:** 5 new nullable columns on Order model, one PATCH endpoint, one new card in OrderDetail.vue between basic info and packaging cost.

**Tech Stack:** FastAPI, SQLAlchemy, Vue 3 + Naive UI, existing ImageUploadModal

**Spec:** `docs/superpowers/specs/2026-04-01-order-extra-info-design.md`

---

## File Structure

| File | Changes |
|------|---------|
| `models/order.py` | Add 5 columns to Order |
| `database.py` | Add schema compat for new columns |
| `schemas/order.py` | Add fields to OrderResponse, add ExtraInfoUpdate schema |
| `services/order.py` | Add `update_extra_info` function |
| `api/orders.py` | Add PATCH extra-info endpoint |
| `frontend/src/views/orders/OrderDetail.vue` | Add "附加信息" card |
| `frontend/src/api/orders.js` | Add `updateExtraInfo` function |
| `tests/test_api_order_todo.py` | Add tests for extra info |

---

## Task 1: Backend — Model + Schema + Service + API

**Files:**
- Modify: `models/order.py` (Order class, line 7-16)
- Modify: `database.py` (ensure_schema_compat)
- Modify: `schemas/order.py` (OrderResponse line 33, add new schema)
- Modify: `services/order.py` (add function)
- Modify: `api/orders.py` (add endpoint)
- Test: `tests/test_api_order_todo.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_api_order_todo.py`:

```python
def test_update_extra_info(client, db):
    """PATCH extra-info updates barcode, mark, and note fields."""
    parts, jewelry, order = _setup_order_with_bom(db)
    resp = client.patch(
        f"/api/orders/{order.id}/extra-info",
        json={
            "barcode_text": "EAN-13, 695开头",
            "mark_text": "客户唛头：ABC Trading",
            "note": "注意包装要求",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["barcode_text"] == "EAN-13, 695开头"
    assert data["mark_text"] == "客户唛头：ABC Trading"
    assert data["note"] == "注意包装要求"
    assert data["barcode_image"] is None
    assert data["mark_image"] is None


def test_update_extra_info_partial(client, db):
    """PATCH extra-info with partial fields only updates those fields."""
    parts, jewelry, order = _setup_order_with_bom(db)
    # Set initial values
    client.patch(
        f"/api/orders/{order.id}/extra-info",
        json={"barcode_text": "初始条码", "note": "初始备注"},
    )
    # Partial update — only update note
    resp = client.patch(
        f"/api/orders/{order.id}/extra-info",
        json={"note": "更新备注"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["barcode_text"] == "初始条码"  # unchanged
    assert data["note"] == "更新备注"  # updated


def test_update_extra_info_with_image(client, db):
    """PATCH extra-info can set image URLs."""
    parts, jewelry, order = _setup_order_with_bom(db)
    resp = client.patch(
        f"/api/orders/{order.id}/extra-info",
        json={
            "barcode_image": "https://oss.example.com/barcode.jpg",
            "mark_image": "https://oss.example.com/mark.jpg",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["barcode_image"] == "https://oss.example.com/barcode.jpg"
    assert data["mark_image"] == "https://oss.example.com/mark.jpg"


def test_update_extra_info_clear_image(client, db):
    """PATCH extra-info can clear image by setting to null."""
    parts, jewelry, order = _setup_order_with_bom(db)
    client.patch(
        f"/api/orders/{order.id}/extra-info",
        json={"barcode_image": "https://oss.example.com/barcode.jpg"},
    )
    resp = client.patch(
        f"/api/orders/{order.id}/extra-info",
        json={"barcode_image": None},
    )
    assert resp.status_code == 200
    assert resp.json()["barcode_image"] is None


def test_get_order_includes_extra_info(client, db):
    """GET order response includes extra info fields."""
    parts, jewelry, order = _setup_order_with_bom(db)
    resp = client.get(f"/api/orders/{order.id}")
    assert resp.status_code == 200
    data = resp.json()
    # All extra fields should be present (null by default)
    assert "barcode_text" in data
    assert "barcode_image" in data
    assert "mark_text" in data
    assert "mark_image" in data
    assert "note" in data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_order_todo.py::test_update_extra_info tests/test_api_order_todo.py::test_get_order_includes_extra_info -v`
Expected: FAIL

- [ ] **Step 3: Add columns to Order model**

In `models/order.py`, add to the Order class after `packaging_cost`:

```python
    barcode_text = Column(Text, nullable=True)
    barcode_image = Column(String, nullable=True)
    mark_text = Column(Text, nullable=True)
    mark_image = Column(String, nullable=True)
    note = Column(Text, nullable=True)
```

- [ ] **Step 4: Add schema compat**

In `database.py`, add to `ensure_schema_compat()`:

```python
# --- order extra info fields ---
if inspector.has_table("order"):
    cols = [c["name"] for c in inspector.get_columns("order")]
    for col_name, col_type in [
        ("barcode_text", "TEXT"),
        ("barcode_image", "VARCHAR"),
        ("mark_text", "TEXT"),
        ("mark_image", "VARCHAR"),
        ("note", "TEXT"),
    ]:
        if col_name not in cols:
            conn.execute(text(
                f'ALTER TABLE "order" ADD COLUMN {col_name} {col_type}'
            ))
```

- [ ] **Step 5: Add fields to OrderResponse schema**

In `schemas/order.py`, add to `OrderResponse` after `packaging_cost`:

```python
    barcode_text: str | None = None
    barcode_image: str | None = None
    mark_text: str | None = None
    mark_image: str | None = None
    note: str | None = None
```

Add new schema:

```python
class ExtraInfoUpdate(BaseModel):
    barcode_text: str | None = None
    barcode_image: str | None = None
    mark_text: str | None = None
    mark_image: str | None = None
    note: str | None = None
```

- [ ] **Step 6: Add service function**

In `services/order.py`, add:

```python
def update_extra_info(db: Session, order_id: str, data: dict) -> Order:
    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        raise ValueError(f"订单 {order_id} 不存在")
    for key, value in data.items():
        if hasattr(order, key):
            setattr(order, key, value)
    db.flush()
    return order
```

- [ ] **Step 7: Add API endpoint**

In `api/orders.py`, add (following the packaging-cost pattern):

```python
from schemas.order import ExtraInfoUpdate
from services.order import update_extra_info

@router.patch("/{order_id}/extra-info", response_model=OrderResponse)
def api_update_extra_info(order_id: str, body: ExtraInfoUpdate, db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        order = update_extra_info(db, order_id, body.model_dump(exclude_unset=True))
    return order
```

- [ ] **Step 8: Run all tests**

Run: `pytest tests/test_api_order_todo.py -v -k "extra_info or get_order_includes"`
Expected: All PASS

- [ ] **Step 9: Run full test suite for regressions**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add models/order.py database.py schemas/order.py services/order.py api/orders.py tests/test_api_order_todo.py
git commit -m "feat: add order extra info fields (barcode, mark, note)"
```

---

## Task 2: Frontend — 附加信息卡片

**Files:**
- Modify: `frontend/src/api/orders.js`
- Modify: `frontend/src/views/orders/OrderDetail.vue`

- [ ] **Step 1: Add API function**

In `frontend/src/api/orders.js`, add:

```javascript
export function updateExtraInfo(orderId, data) {
  return request.patch(`/orders/${orderId}/extra-info`, data)
}
```

- [ ] **Step 2: Add state and methods in OrderDetail.vue**

In `<script setup>`, add:

```javascript
import { updateExtraInfo } from '@/api/orders'
import ImageUploadModal from '@/components/ImageUploadModal.vue'

const extraInfo = ref({
  barcode_text: '',
  barcode_image: null,
  mark_text: '',
  mark_image: null,
  note: '',
})
const savingExtraInfo = ref(false)

// Image upload state
const showImageUpload = ref(false)
const imageUploadTarget = ref('')  // 'barcode' or 'mark'

function initExtraInfo(order) {
  extraInfo.value = {
    barcode_text: order.barcode_text || '',
    barcode_image: order.barcode_image || null,
    mark_text: order.mark_text || '',
    mark_image: order.mark_image || null,
    note: order.note || '',
  }
}

async function saveExtraInfo() {
  savingExtraInfo.value = true
  try {
    await updateExtraInfo(orderId.value, extraInfo.value)
    message.success('附加信息已保存')
  } catch (err) {
    message.error('保存失败')
  } finally {
    savingExtraInfo.value = false
  }
}

function openImageUpload(target) {
  imageUploadTarget.value = target
  showImageUpload.value = true
}

function onImageUploaded(url) {
  if (imageUploadTarget.value === 'barcode') {
    extraInfo.value.barcode_image = url
  } else {
    extraInfo.value.mark_image = url
  }
}

function clearImage(target) {
  if (target === 'barcode') {
    extraInfo.value.barcode_image = null
  } else {
    extraInfo.value.mark_image = null
  }
}
```

Call `initExtraInfo(order)` after fetching order data in the existing load function.

- [ ] **Step 3: Add template — 附加信息卡片**

Insert between the basic info card and the packaging cost card in the `<template>`:

```html
<n-card title="附加信息" style="margin-bottom: 16px;">
  <!-- 条码要求 -->
  <div style="margin-bottom: 20px;">
    <div style="font-weight: 500; margin-bottom: 8px;">条码要求</div>
    <div style="display: flex; gap: 16px;">
      <n-input
        v-model:value="extraInfo.barcode_text"
        type="textarea"
        :rows="3"
        placeholder="条码要求说明..."
        style="flex: 1;"
      />
      <div style="width: 100px;">
        <div v-if="extraInfo.barcode_image" style="position: relative; display: inline-block;">
          <n-image :src="extraInfo.barcode_image" width="100" height="80" object-fit="cover" style="border-radius: 4px;" />
          <n-button circle size="tiny" type="error" style="position: absolute; top: -6px; right: -6px;" @click="clearImage('barcode')">
            <template #icon><n-icon :component="CloseIcon" /></template>
          </n-button>
        </div>
        <n-button v-else dashed style="width: 100px; height: 80px;" @click="openImageUpload('barcode')">
          上传图片
        </n-button>
      </div>
    </div>
  </div>

  <!-- 唛头要求 -->
  <div style="margin-bottom: 20px;">
    <div style="font-weight: 500; margin-bottom: 8px;">唛头要求</div>
    <div style="display: flex; gap: 16px;">
      <n-input
        v-model:value="extraInfo.mark_text"
        type="textarea"
        :rows="3"
        placeholder="唛头要求说明..."
        style="flex: 1;"
      />
      <div style="width: 100px;">
        <div v-if="extraInfo.mark_image" style="position: relative; display: inline-block;">
          <n-image :src="extraInfo.mark_image" width="100" height="80" object-fit="cover" style="border-radius: 4px;" />
          <n-button circle size="tiny" type="error" style="position: absolute; top: -6px; right: -6px;" @click="clearImage('mark')">
            <template #icon><n-icon :component="CloseIcon" /></template>
          </n-button>
        </div>
        <n-button v-else dashed style="width: 100px; height: 80px;" @click="openImageUpload('mark')">
          上传图片
        </n-button>
      </div>
    </div>
  </div>

  <!-- 总备注 -->
  <div style="margin-bottom: 16px;">
    <div style="font-weight: 500; margin-bottom: 8px;">总备注</div>
    <n-input
      v-model:value="extraInfo.note"
      type="textarea"
      :rows="3"
      placeholder="其他注意事项..."
    />
  </div>

  <n-button type="primary" :loading="savingExtraInfo" @click="saveExtraInfo">保存</n-button>

  <!-- Image upload modal (reused) -->
  <ImageUploadModal
    v-model:show="showImageUpload"
    kind="order"
    :entity-id="orderId"
    :suppress-success="true"
    @uploaded="onImageUploaded"
  />
</n-card>
```

- [ ] **Step 4: Import CloseIcon**

Add to imports:

```javascript
import { Close as CloseIcon } from '@vicons/ionicons5'
```

- [ ] **Step 5: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/orders.js frontend/src/views/orders/OrderDetail.vue
git commit -m "feat: add extra info card (barcode, mark, note) to order detail page"
```

---

## Task 3: Backend — Allow 'order' Kind in Upload Policy

**Files:**
- Modify: `services/upload.py` (ALLOWED_KINDS or equivalent validation)

- [ ] **Step 1: Check if 'order' is already an allowed kind**

Read `services/upload.py` and check the allowed kinds list. If "order" is not in the list, add it.

- [ ] **Step 2: Add 'order' to allowed kinds if needed**

```python
# Add "order" to the ALLOWED_KINDS set/list
```

- [ ] **Step 3: Run tests**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 4: Commit if changed**

```bash
git add services/upload.py
git commit -m "feat: allow 'order' kind for image uploads"
```

---

## Task 4: Verify

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 2: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Manual verification**

Start backend + frontend, open an order detail page:
- Verify "附加信息" card appears between basic info and packaging cost
- Verify text fields save correctly
- Verify image upload works for barcode and mark
- Verify image delete works
- Verify fields persist after page reload
