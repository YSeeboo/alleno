# 饰品大图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a jewelry poster PDF with auto-layout for order items, showing large product images with quantity, price, customer code, and remarks.

**Architecture:** New `services/jewelry_poster.py` generates HTML with CSS Flexbox layout, uses weasyprint to convert to PDF. HTML preview and PDF share the same template. Frontend adds two buttons on OrderDetail.

**Tech Stack:** FastAPI, weasyprint, Vue 3 + Naive UI

**Spec:** `docs/superpowers/specs/2026-04-06-jewelry-poster-design.md`

---

## File Structure

| File | Changes |
|------|---------|
| `requirements.txt` | Add `weasyprint` |
| `services/jewelry_poster.py` | New: HTML template + PDF generation |
| `api/orders.py` | Add 2 endpoints (PDF download + HTML preview) |
| `frontend/src/api/orders.js` | Add API functions |
| `frontend/src/views/orders/OrderDetail.vue` | Add buttons |
| `tests/test_jewelry_poster.py` | New test file |

---

## Task 1: Install weasyprint

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add weasyprint to requirements**

Add `weasyprint` to `requirements.txt`.

- [ ] **Step 2: Install**

Run: `pip install weasyprint`

On macOS, if not already installed: `brew install pango` (system dependency).

- [ ] **Step 3: Verify import**

Run: `python -c "import weasyprint; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add weasyprint dependency for jewelry poster PDF"
```

---

## Task 2: Backend — Poster Service + API

**Files:**
- Create: `services/jewelry_poster.py`
- Modify: `api/orders.py`
- Test: `tests/test_jewelry_poster.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_jewelry_poster.py`:

```python
import pytest
from models.part import Part
from models.jewelry import Jewelry
from models.bom import Bom
from models.order import Order, OrderItem


def _setup_order_with_jewelry(db, count=3):
    """Create order with multiple jewelry items."""
    part = Part(id="PJ-X-POSTER1", name="测试配件", category="小配件")
    db.add(part)
    db.flush()

    jewelries = []
    for i in range(count):
        j = Jewelry(id=f"SP-POSTER-{i}", name=f"测试饰品{i}", category="项链")
        db.add(j)
        jewelries.append(j)
    db.flush()

    for j in jewelries:
        bom = Bom(id=f"BM-POSTER-{j.id}", jewelry_id=j.id, part_id=part.id, qty_per_unit=1)
        db.add(bom)
    db.flush()

    from services.order import create_order
    items = [
        {"jewelry_id": j.id, "quantity": 10 + i, "unit_price": 100 + i * 10}
        for i, j in enumerate(jewelries)
    ]
    order = create_order(db, "海报测试客户", items)
    db.flush()
    return order, jewelries


def test_generate_poster_pdf(client, db):
    """Generate poster PDF returns valid PDF bytes."""
    order, jewelries = _setup_order_with_jewelry(db, count=3)
    resp = client.get(f"/api/orders/{order.id}/jewelry-poster-pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert len(resp.content) > 0
    assert resp.content[:5] == b"%PDF-"


def test_generate_poster_pdf_many_items(client, db):
    """Many items should produce multi-page PDF."""
    order, jewelries = _setup_order_with_jewelry(db, count=15)
    resp = client.get(f"/api/orders/{order.id}/jewelry-poster-pdf")
    assert resp.status_code == 200
    assert resp.content[:5] == b"%PDF-"


def test_generate_poster_pdf_empty_order(client, db):
    """Order with no items returns 400."""
    from services.order import create_order
    order = create_order(db, "空订单客户", [])
    db.flush()
    resp = client.get(f"/api/orders/{order.id}/jewelry-poster-pdf")
    assert resp.status_code == 400


def test_generate_poster_preview(client, db):
    """Generate HTML preview returns valid HTML."""
    order, jewelries = _setup_order_with_jewelry(db, count=3)
    resp = client.get(f"/api/orders/{order.id}/jewelry-poster-preview")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "数量:" in resp.text


def test_poster_includes_customer_code(client, db):
    """Poster preview includes customer code when set."""
    order, jewelries = _setup_order_with_jewelry(db, count=1)
    item = db.query(OrderItem).filter_by(order_id=order.id).first()
    item.customer_code = "MG-01"
    db.flush()
    resp = client.get(f"/api/orders/{order.id}/jewelry-poster-preview")
    assert resp.status_code == 200
    assert "MG-01" in resp.text


def test_poster_includes_remarks(client, db):
    """Poster preview includes remarks when set."""
    order, jewelries = _setup_order_with_jewelry(db, count=1)
    item = db.query(OrderItem).filter_by(order_id=order.id).first()
    item.remarks = "特殊包装要求"
    db.flush()
    resp = client.get(f"/api/orders/{order.id}/jewelry-poster-preview")
    assert resp.status_code == 200
    assert "特殊包装要求" in resp.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jewelry_poster.py -v`
Expected: FAIL

- [ ] **Step 3: Implement jewelry_poster service**

Create `services/jewelry_poster.py`:

```python
from sqlalchemy.orm import Session
from models.order import Order, OrderItem
from models.jewelry import Jewelry


def _build_poster_html(db: Session, order_id: str, for_pdf: bool = False) -> str:
    """Generate HTML for jewelry poster.

    Args:
        for_pdf: If True, uses @page CSS for weasyprint PDF pagination.
                 If False, uses screen-friendly layout.
    """
    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        raise ValueError(f"订单 {order_id} 不存在")

    items = (
        db.query(OrderItem)
        .filter_by(order_id=order_id)
        .order_by(OrderItem.id)
        .all()
    )
    if not items:
        raise ValueError("订单中没有饰品")

    jewelry_ids = [it.jewelry_id for it in items]
    jewelries = db.query(Jewelry).filter(Jewelry.id.in_(jewelry_ids)).all()
    j_map = {j.id: j for j in jewelries}

    cards_html = ""
    for it in items:
        j = j_map.get(it.jewelry_id)
        image_url = j.image if j and j.image else ""
        price = float(it.unit_price) if it.unit_price else 0
        price_str = f"{price:.0f}" if price == int(price) else f"{price:.2f}"
        customer_code = getattr(it, "customer_code", None) or ""
        remarks = it.remarks or ""

        if image_url:
            img_html = f'<img class="card-img" src="{image_url}">'
        else:
            img_html = '<div class="card-img no-image">暂无图片</div>'

        info_parts = [f"数量: {it.quantity} &nbsp; 单价: ¥{price_str}"]
        if customer_code:
            info_parts.append(f"货号: {customer_code}")
        if remarks:
            info_parts.append(remarks)
        info_html = "<br>".join(info_parts)

        cards_html += f"""
        <div class="card">
            {img_html}
            <div class="card-info">{info_html}</div>
        </div>
        """

    # PDF uses @page for A4 sizing and proper pagination
    pdf_css = """
        @page {
            size: A4 portrait;
            margin: 12mm;
        }
        body {
            margin: 0;
        }
    """ if for_pdf else ""

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>饰品大图 - {order_id}</title>
    <style>
        {pdf_css}
        body {{
            font-family: "STSong", "SimSun", "PingFang SC", sans-serif;
            color: #333;
            padding: 8px;
        }}
        .header {{
            font-size: 13px;
            color: #666;
            margin-bottom: 12px;
        }}
        .grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        .card {{
            width: calc(33.33% - 8px);
            border: 1px solid #ddd;
            border-radius: 4px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            page-break-inside: avoid;
            break-inside: avoid;
        }}
        .card-img {{
            width: 100%;
            aspect-ratio: 1 / 1;
            object-fit: contain;
            background: #f8f8f8;
            display: block;
        }}
        .no-image {{
            display: flex;
            align-items: center;
            justify-content: center;
            color: #bbb;
            font-size: 14px;
        }}
        .card-info {{
            padding: 6px 8px;
            font-size: 11px;
            line-height: 1.5;
            color: #555;
            border-top: 1px solid #eee;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
    </style>
</head>
<body>
    <div class="header">订单：{order_id} &nbsp;&nbsp; 客户：{order.customer_name}</div>
    <div class="grid">
        {cards_html}
    </div>
</body>
</html>"""


def build_jewelry_poster_pdf(db: Session, order_id: str) -> tuple[bytes, str]:
    """Generate jewelry poster PDF using weasyprint."""
    import weasyprint
    html_str = _build_poster_html(db, order_id, for_pdf=True)
    pdf_bytes = weasyprint.HTML(string=html_str).write_pdf()
    filename = f"饰品大图_{order_id}.pdf"
    return pdf_bytes, filename


def build_jewelry_poster_html(db: Session, order_id: str) -> str:
    """Generate HTML preview of jewelry poster."""
    return _build_poster_html(db, order_id, for_pdf=False)
```

- [ ] **Step 4: Add API endpoints**

In `api/orders.py`, add:

```python
from services.jewelry_poster import build_jewelry_poster_pdf, build_jewelry_poster_html
from fastapi.responses import HTMLResponse

@router.get("/{order_id}/jewelry-poster-pdf")
def api_jewelry_poster_pdf(order_id: str, db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        pdf_bytes, filename = build_jewelry_poster_pdf(db, order_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{quote(filename)}"'
        },
    )


@router.get("/{order_id}/jewelry-poster-preview")
def api_jewelry_poster_preview(order_id: str, db: Session = Depends(get_db)):
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    with service_errors():
        html = build_jewelry_poster_html(db, order_id)
    return HTMLResponse(content=html)
```

Ensure `from urllib.parse import quote` is imported at the top of `api/orders.py`.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_jewelry_poster.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add services/jewelry_poster.py api/orders.py tests/test_jewelry_poster.py
git commit -m "feat: add jewelry poster PDF and HTML preview with auto-layout"
```

---

## Task 3: Frontend — Buttons on OrderDetail

**Files:**
- Modify: `frontend/src/api/orders.js`
- Modify: `frontend/src/views/orders/OrderDetail.vue`

- [ ] **Step 1: Add API functions**

In `frontend/src/api/orders.js`, add:

```javascript
export function downloadJewelryPosterPdf(orderId) {
  return request.get(`/orders/${orderId}/jewelry-poster-pdf`, {
    responseType: 'blob',
  })
}

export function getJewelryPosterPreviewUrl(orderId) {
  return `${request.defaults.baseURL}/orders/${orderId}/jewelry-poster-preview`
}
```

- [ ] **Step 2: Add buttons and handlers in OrderDetail.vue**

In `<script setup>`, add:

```javascript
import { downloadJewelryPosterPdf, getJewelryPosterPreviewUrl } from '@/api/orders'

const downloadingPoster = ref(false)

async function doDownloadPoster() {
  downloadingPoster.value = true
  try {
    const { data } = await downloadJewelryPosterPdf(orderId.value)
    const url = URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = `饰品大图_${orderId.value}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    message.error('下载失败')
  } finally {
    downloadingPoster.value = false
  }
}

function doPreviewPoster() {
  window.open(getJewelryPosterPreviewUrl(orderId.value), '_blank')
}
```

In the 饰品清单 card header-extra area, add buttons:

```html
<n-button size="small" :loading="downloadingPoster" @click="doDownloadPoster">下载饰品大图</n-button>
<n-button size="small" @click="doPreviewPoster">预览饰品大图</n-button>
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/orders.js frontend/src/views/orders/OrderDetail.vue
git commit -m "feat: add jewelry poster download and preview buttons"
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

- Open order detail with jewelry items that have images
- Click "下载饰品大图" → verify PDF downloads, auto-layout, images not compressed
- Click "预览饰品大图" → verify HTML opens in new tab, responsive layout
- Test with >9 items → verify auto-pagination in PDF
- Test with mixed image aspect ratios → verify layout adapts
- Test with customer_code and remarks → verify they appear
- Test with jewelry missing image → verify placeholder
