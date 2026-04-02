# 客户货号 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add customer article number (客户货号) field to order items with inline editing and batch sequential fill.

**Architecture:** One new column on OrderItem, one PATCH endpoint for single update, one POST endpoint for batch sequential fill, inline edit in frontend table.

**Tech Stack:** FastAPI, SQLAlchemy, Vue 3 + Naive UI

**Spec:** `docs/superpowers/specs/2026-04-01-customer-code-design.md`

---

## File Structure

| File | Changes |
|------|---------|
| `models/order.py` | Add `customer_code` column to OrderItem |
| `database.py` | Add schema compat for new column |
| `schemas/order.py` | Add `customer_code` to OrderItemResponse, add new schemas |
| `services/order.py` | Add `update_order_item_customer_code` and `batch_fill_customer_code` |
| `api/orders.py` | Add PATCH item and POST batch-customer-code endpoints |
| `frontend/src/api/orders.js` | Add API functions |
| `frontend/src/views/orders/OrderDetail.vue` | Add column, inline edit, checkbox, batch fill modal |
| `tests/test_api_order_todo.py` | Add tests |

---

## Task 1: Backend — Model + Schema Compat

**Files:**
- Modify: `models/order.py` (OrderItem class, line 18-27)
- Modify: `database.py` (ensure_schema_compat)

- [ ] **Step 1: Add column to OrderItem**

In `models/order.py`, add to the OrderItem class after `remarks`:

```python
    customer_code = Column(String, nullable=True)
```

- [ ] **Step 2: Add schema compat**

In `database.py`, add to `ensure_schema_compat()`:

```python
# --- order_item.customer_code ---
if inspector.has_table("order_item"):
    cols = [c["name"] for c in inspector.get_columns("order_item")]
    if "customer_code" not in cols:
        conn.execute(text(
            "ALTER TABLE order_item ADD COLUMN customer_code VARCHAR"
        ))
```

- [ ] **Step 3: Verify model loads**

Run: `python -c "from models.order import OrderItem; print([c.name for c in OrderItem.__table__.columns])"`
Expected: Output includes `customer_code`

- [ ] **Step 4: Commit**

```bash
git add models/order.py database.py
git commit -m "feat: add customer_code column to OrderItem"
```

---

## Task 2: Backend — Schemas + Service + API

**Files:**
- Modify: `schemas/order.py` (OrderItemResponse line 22, add new schemas)
- Modify: `services/order.py` (add functions)
- Modify: `api/orders.py` (add endpoints)
- Test: `tests/test_api_order_todo.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_api_order_todo.py`:

```python
def test_update_item_customer_code(client, db):
    """PATCH updates customer_code on a single order item."""
    parts, jewelry, order = _setup_order_with_bom(db)
    item = db.query(OrderItem).filter_by(order_id=order.id).first()
    resp = client.patch(
        f"/api/orders/{order.id}/items/{item.id}",
        json={"customer_code": "MG-01"},
    )
    assert resp.status_code == 200
    assert resp.json()["customer_code"] == "MG-01"


def test_update_item_customer_code_clear(client, db):
    """PATCH can clear customer_code by setting to null."""
    parts, jewelry, order = _setup_order_with_bom(db)
    item = db.query(OrderItem).filter_by(order_id=order.id).first()
    client.patch(
        f"/api/orders/{order.id}/items/{item.id}",
        json={"customer_code": "MG-01"},
    )
    resp = client.patch(
        f"/api/orders/{order.id}/items/{item.id}",
        json={"customer_code": None},
    )
    assert resp.status_code == 200
    assert resp.json()["customer_code"] is None


def test_batch_fill_customer_code(client, db):
    """POST batch fills sequential customer codes."""
    from models.part import Part
    from models.jewelry import Jewelry
    from models.bom import Bom

    # Create 3 jewelry items with BOM
    p1 = Part(id="PJ-X-00099", name="配件A", category="小配件")
    db.add(p1)
    db.flush()

    jewelries = []
    for i in range(3):
        j = Jewelry(id=f"SP-TEST-{i}", name=f"饰品{i}", category="项链")
        db.add(j)
        db.flush()
        bom = Bom(id=f"BM-TEST-{i}", jewelry_id=j.id, part_id=p1.id, qty_per_unit=1)
        db.add(bom)
        jewelries.append(j)
    db.flush()

    # Create order with 3 items
    from services.order import create_order
    order = create_order(db, "测试客户", [
        {"jewelry_id": jewelries[0].id, "quantity": 10, "unit_price": 100},
        {"jewelry_id": jewelries[1].id, "quantity": 20, "unit_price": 200},
        {"jewelry_id": jewelries[2].id, "quantity": 30, "unit_price": 300},
    ])
    db.flush()

    items = db.query(OrderItem).filter_by(order_id=order.id).order_by(OrderItem.id).all()
    item_ids = [it.id for it in items]

    resp = client.post(
        f"/api/orders/{order.id}/items/batch-customer-code",
        json={
            "item_ids": item_ids,
            "prefix": "MG-",
            "start_number": 2,
            "padding": 2,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["updated_count"] == 3

    # Verify codes assigned in order
    items_resp = client.get(f"/api/orders/{order.id}/items")
    codes = [it["customer_code"] for it in sorted(items_resp.json(), key=lambda x: x["id"])]
    assert codes == ["MG-02", "MG-03", "MG-04"]


def test_batch_fill_customer_code_padding(client, db):
    """Batch fill respects padding parameter."""
    parts, jewelry, order = _setup_order_with_bom(db)
    item = db.query(OrderItem).filter_by(order_id=order.id).first()
    resp = client.post(
        f"/api/orders/{order.id}/items/batch-customer-code",
        json={
            "item_ids": [item.id],
            "prefix": "AB",
            "start_number": 5,
            "padding": 3,
        },
    )
    assert resp.status_code == 200
    updated = client.get(f"/api/orders/{order.id}/items")
    assert updated.json()[0]["customer_code"] == "AB005"


def test_get_items_includes_customer_code(client, db):
    """GET items response includes customer_code field."""
    parts, jewelry, order = _setup_order_with_bom(db)
    resp = client.get(f"/api/orders/{order.id}/items")
    assert resp.status_code == 200
    assert "customer_code" in resp.json()[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_order_todo.py::test_update_item_customer_code tests/test_api_order_todo.py::test_batch_fill_customer_code tests/test_api_order_todo.py::test_get_items_includes_customer_code -v`
Expected: FAIL

- [ ] **Step 3: Update schemas**

In `schemas/order.py`, add to `OrderItemResponse` after `remarks`:

```python
    customer_code: str | None = None
```

Add new schemas:

```python
class OrderItemUpdate(BaseModel):
    customer_code: str | None = None


class BatchCustomerCodeRequest(BaseModel):
    item_ids: list[int]
    prefix: str
    start_number: int
    padding: int = 2


class BatchCustomerCodeResponse(BaseModel):
    updated_count: int
```

- [ ] **Step 4: Add service functions**

In `services/order.py`, add:

```python
def update_order_item_customer_code(db: Session, order_id: str, item_id: int, customer_code: str | None) -> OrderItem:
    item = db.query(OrderItem).filter_by(id=item_id, order_id=order_id).first()
    if not item:
        raise ValueError(f"订单项 {item_id} 不存在")
    item.customer_code = customer_code
    db.flush()
    return item


def batch_fill_customer_code(
    db: Session,
    order_id: str,
    item_ids: list[int],
    prefix: str,
    start_number: int,
    padding: int = 2,
) -> int:
    # Validate all items belong to this order
    items = (
        db.query(OrderItem)
        .filter(OrderItem.id.in_(item_ids), OrderItem.order_id == order_id)
        .order_by(OrderItem.id)
        .all()
    )
    if len(items) != len(item_ids):
        raise ValueError("部分订单项不存在或不属于该订单")

    for i, item in enumerate(items):
        code = f"{prefix}{start_number + i:0{padding}d}"
        item.customer_code = code
    db.flush()
    return len(items)
```

- [ ] **Step 5: Add API endpoints**

In `api/orders.py`, add:

```python
from schemas.order import OrderItemUpdate, BatchCustomerCodeRequest

@router.patch("/{order_id}/items/{item_id}", response_model=OrderItemResponse)
def api_update_order_item(order_id: str, item_id: int, body: OrderItemUpdate, db: Session = Depends(get_db)):
    with service_errors():
        return update_order_item_customer_code(db, order_id, item_id, body.customer_code)


@router.post("/{order_id}/items/batch-customer-code")
def api_batch_customer_code(order_id: str, body: BatchCustomerCodeRequest, db: Session = Depends(get_db)):
    with service_errors():
        count = batch_fill_customer_code(
            db, order_id, body.item_ids, body.prefix, body.start_number, body.padding,
        )
        return {"updated_count": count}
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_api_order_todo.py -v -k "customer_code or get_items_includes"`
Expected: All PASS

- [ ] **Step 7: Run full test suite**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add schemas/order.py services/order.py api/orders.py tests/test_api_order_todo.py
git commit -m "feat: add customer code update and batch fill endpoints"
```

---

## Task 3: Frontend — Inline Edit + Batch Fill

**Files:**
- Modify: `frontend/src/api/orders.js`
- Modify: `frontend/src/views/orders/OrderDetail.vue`

- [ ] **Step 1: Add API functions**

In `frontend/src/api/orders.js`, add:

```javascript
export function updateOrderItem(orderId, itemId, data) {
  return request.patch(`/orders/${orderId}/items/${itemId}`, data)
}

export function batchFillCustomerCode(orderId, data) {
  return request.post(`/orders/${orderId}/items/batch-customer-code`, data)
}
```

- [ ] **Step 2: Add state for inline edit and batch fill**

In OrderDetail.vue `<script setup>`:

```javascript
import { updateOrderItem, batchFillCustomerCode } from '@/api/orders'

const editingCustomerCode = ref(null)  // item id being edited
const editingCodeValue = ref('')
const checkedItemIds = ref([])
const showBatchCodeModal = ref(false)
const batchCodeForm = ref({ prefix: '', start_number: 1, padding: 2 })
const batchCodeFilling = ref(false)

function startEditCode(item) {
  editingCustomerCode.value = item.id
  editingCodeValue.value = item.customer_code || ''
}

async function saveCustomerCode(item) {
  const value = editingCodeValue.value.trim() || null
  try {
    await updateOrderItem(orderId.value, item.id, { customer_code: value })
    item.customer_code = value
  } catch (err) {
    message.error('保存失败')
  }
  editingCustomerCode.value = null
}

function batchCodePreview() {
  const { prefix, start_number, padding } = batchCodeForm.value
  const count = checkedItemIds.value.length
  if (count === 0 || !prefix) return ''
  const codes = []
  for (let i = 0; i < Math.min(count, 5); i++) {
    codes.push(prefix + String(start_number + i).padStart(padding, '0'))
  }
  if (count > 5) codes.push('...')
  return codes.join(', ')
}

async function confirmBatchCode() {
  batchCodeFilling.value = true
  try {
    await batchFillCustomerCode(orderId.value, {
      item_ids: checkedItemIds.value,
      ...batchCodeForm.value,
    })
    showBatchCodeModal.value = false
    checkedItemIds.value = []
    await loadItems()
    message.success('批量填入成功')
  } catch (err) {
    message.error('批量填入失败')
  } finally {
    batchCodeFilling.value = false
  }
}
```

- [ ] **Step 3: Add checkbox column and customer_code column to table**

In the `itemColumns` definition, add checkbox as first column:

```javascript
{
  type: 'selection',
  width: 40,
}
```

Add customer_code column after `jewelry_id`:

```javascript
{
  title: '客户货号',
  key: 'customer_code',
  width: 120,
  render(row) {
    if (editingCustomerCode.value === row.id) {
      return h(NInput, {
        value: editingCodeValue.value,
        size: 'small',
        autofocus: true,
        onUpdateValue: (v) => { editingCodeValue.value = v },
        onBlur: () => saveCustomerCode(row),
        onKeydown: (e) => { if (e.key === 'Enter') saveCustomerCode(row) },
      })
    }
    return h('span', {
      style: {
        cursor: 'pointer',
        color: row.customer_code ? '#333' : '#ccc',
      },
      onClick: () => startEditCode(row),
    }, row.customer_code || '—')
  },
}
```

Handle checked rows:

```javascript
// Add to n-data-table:
// :row-key="row => row.id"
// v-model:checked-row-keys="checkedItemIds"
```

- [ ] **Step 4: Add batch fill button and modal**

Above the items table, add conditional button:

```html
<n-button
  v-if="checkedItemIds.length > 0"
  size="small"
  type="primary"
  @click="showBatchCodeModal = true"
>
  批量填入客户货号 ({{ checkedItemIds.length }})
</n-button>
```

Add modal:

```html
<n-modal v-model:show="showBatchCodeModal" preset="card" title="批量填入客户货号" style="width: 420px;">
  <n-form label-placement="left" label-width="80">
    <n-form-item label="前缀">
      <n-input v-model:value="batchCodeForm.prefix" placeholder="如 MG-" />
    </n-form-item>
    <n-form-item label="起始号">
      <n-input-number v-model:value="batchCodeForm.start_number" :min="0" />
    </n-form-item>
    <n-form-item label="位数">
      <n-input-number v-model:value="batchCodeForm.padding" :min="1" :max="6" />
    </n-form-item>
  </n-form>
  <div v-if="batchCodePreview()" style="margin-top: 8px; color: #666; font-size: 12px;">
    预览：{{ batchCodePreview() }}
  </div>
  <template #footer>
    <n-space justify="end">
      <n-button @click="showBatchCodeModal = false">取消</n-button>
      <n-button type="primary" :loading="batchCodeFilling" :disabled="!batchCodeForm.prefix" @click="confirmBatchCode">确定</n-button>
    </n-space>
  </template>
</n-modal>
```

- [ ] **Step 5: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/orders.js frontend/src/views/orders/OrderDetail.vue
git commit -m "feat: add customer code inline edit and batch fill to order items"
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

- Verify "客户货号" column appears in order items table
- Verify clicking "—" enters inline edit mode, blur/enter saves
- Verify checkbox selection works
- Verify batch fill modal shows preview
- Verify batch fill assigns sequential codes correctly
