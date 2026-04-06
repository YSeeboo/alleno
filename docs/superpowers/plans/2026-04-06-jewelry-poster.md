# 饰品大图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a jewelry poster PDF (3x3 grid per page) for order items, showing large product images with name, quantity, price, and customer code.

**Architecture:** New `services/jewelry_poster.py` using ReportLab. Two endpoints: PDF download and HTML preview. Reuse existing image download helpers. Frontend adds two buttons on OrderDetail.

**Tech Stack:** FastAPI, ReportLab, Vue 3 + Naive UI

**Spec:** `docs/superpowers/specs/2026-04-06-jewelry-poster-design.md`

---

## File Structure

| File | Changes |
|------|---------|
| `services/jewelry_poster.py` | New: PDF generation + HTML preview |
| `api/orders.py` | Add 2 endpoints (PDF download + HTML preview) |
| `frontend/src/api/orders.js` | Add API functions |
| `frontend/src/views/orders/OrderDetail.vue` | Add buttons |
| `tests/test_jewelry_poster.py` | New test file |

---

## Task 1: Backend — PDF Generation Service

**Files:**
- Create: `services/jewelry_poster.py`
- Test: `tests/test_jewelry_poster.py`

- [ ] **Step 1: Write failing test**

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
    # PDF magic bytes
    assert resp.content[:5] == b"%PDF-"


def test_generate_poster_pdf_pagination(client, db):
    """More than 9 items should produce multi-page PDF."""
    order, jewelries = _setup_order_with_jewelry(db, count=12)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jewelry_poster.py -v`
Expected: FAIL

- [ ] **Step 3: Implement jewelry_poster service**

Create `services/jewelry_poster.py`:

```python
import math
from io import BytesIO
from decimal import Decimal
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFont, stringWidth
from reportlab.pdfgen import canvas

from models.order import Order, OrderItem
from models.jewelry import Jewelry
from services.plating_export import download_pdf_image_bytes
from PIL import Image as PILImage

FONT_NAME = "STSong-Light"
PAGE_W, PAGE_H = A4  # 595 x 842
MARGIN = 20
COLS = 3
ROWS = 3
PER_PAGE = COLS * ROWS

CELL_W = (PAGE_W - MARGIN * 2) / COLS
CELL_H = (PAGE_H - MARGIN * 2 - 30) / ROWS  # 30pt reserved for page header
IMG_PADDING = 6
TEXT_AREA_H = CELL_H * 0.2  # text area ≤ 20% of cell height


def build_jewelry_poster_pdf(db: Session, order_id: str) -> tuple[bytes, str]:
    """Generate a 3x3 grid jewelry poster PDF for an order."""
    registerFont(UnicodeCIDFont(FONT_NAME))

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

    # Fetch jewelry info
    jewelry_ids = [it.jewelry_id for it in items]
    jewelries = db.query(Jewelry).filter(Jewelry.id.in_(jewelry_ids)).all()
    j_map = {j.id: j for j in jewelries}

    # Build data list
    poster_items = []
    for it in items:
        j = j_map.get(it.jewelry_id)
        poster_items.append({
            "image_url": j.image if j else None,
            "quantity": it.quantity,
            "unit_price": float(it.unit_price) if it.unit_price else 0,
            "customer_code": getattr(it, "customer_code", None),
            "remarks": it.remarks,
        })

    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    total_pages = math.ceil(len(poster_items) / PER_PAGE)

    for page_idx in range(total_pages):
        if page_idx > 0:
            pdf.showPage()

        # Page header
        pdf.setFont(FONT_NAME, 10)
        header_y = PAGE_H - MARGIN - 12
        pdf.drawString(MARGIN, header_y, f"订单：{order_id}    客户：{order.customer_name}")

        grid_top = header_y - 18

        start = page_idx * PER_PAGE
        end = min(start + PER_PAGE, len(poster_items))
        page_items = poster_items[start:end]

        for idx, item in enumerate(page_items):
            col = idx % COLS
            row = idx // COLS
            x = MARGIN + col * CELL_W
            y = grid_top - (row + 1) * CELL_H

            # Draw cell border (light)
            pdf.setStrokeColorRGB(0.85, 0.85, 0.85)
            pdf.setLineWidth(0.5)
            pdf.rect(x, y, CELL_W, CELL_H)

            # Image area
            img_x = x + IMG_PADDING
            img_y = y + TEXT_AREA_H
            img_max_w = CELL_W - IMG_PADDING * 2
            img_max_h = CELL_H - TEXT_AREA_H - IMG_PADDING

            if item["image_url"]:
                try:
                    img_bytes = download_pdf_image_bytes(item["image_url"])
                    if img_bytes:
                        pil_img = PILImage.open(BytesIO(img_bytes))
                        iw, ih = pil_img.size
                        scale = min(img_max_w / iw, img_max_h / ih)
                        draw_w = iw * scale
                        draw_h = ih * scale
                        # Center image in area
                        offset_x = img_x + (img_max_w - draw_w) / 2
                        offset_y = img_y + (img_max_h - draw_h) / 2
                        reader = ImageReader(BytesIO(img_bytes))
                        pdf.drawImage(
                            reader, offset_x, offset_y,
                            width=draw_w, height=draw_h,
                            preserveAspectRatio=True, mask="auto",
                        )
                except Exception:
                    _draw_no_image(pdf, img_x, img_y, img_max_w, img_max_h)
            else:
                _draw_no_image(pdf, img_x, img_y, img_max_w, img_max_h)

            # Text area (≤ 20% of cell height)
            text_x = x + IMG_PADDING
            text_y = y + TEXT_AREA_H - 12
            max_text_w = CELL_W - IMG_PADDING * 2

            pdf.setFont(FONT_NAME, 7)
            pdf.setFillColorRGB(0, 0, 0)

            # Quantity + Price
            price_str = f"{item['unit_price']:.0f}" if item["unit_price"] == int(item["unit_price"]) else f"{item['unit_price']:.2f}"
            pdf.drawString(text_x, text_y, f"数量: {item['quantity']}    单价: ¥{price_str}")

            # Customer code (if any)
            if item.get("customer_code"):
                text_y -= 11
                pdf.drawString(text_x, text_y, f"货号: {item['customer_code']}")

            # Remarks (if any, truncate to fit)
            if item.get("remarks"):
                text_y -= 11
                remarks = item["remarks"]
                while stringWidth(remarks, FONT_NAME, 7) > max_text_w and len(remarks) > 1:
                    remarks = remarks[:-1]
                pdf.drawString(text_x, text_y, remarks)

    pdf.save()
    filename = f"饰品大图_{order_id}.pdf"
    return buf.getvalue(), filename


def _draw_no_image(pdf, x, y, w, h):
    """Draw a placeholder for missing images."""
    pdf.setStrokeColorRGB(0.8, 0.8, 0.8)
    pdf.setFillColorRGB(0.95, 0.95, 0.95)
    pdf.rect(x, y, w, h, fill=1)
    pdf.setFillColorRGB(0.6, 0.6, 0.6)
    pdf.setFont(FONT_NAME, 9)
    text_w = stringWidth("暂无图片", FONT_NAME, 9)
    pdf.drawString(x + (w - text_w) / 2, y + h / 2 - 4, "暂无图片")


def build_jewelry_poster_html(db: Session, order_id: str) -> str:
    """Generate an HTML preview of the jewelry poster."""
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

        img_html = (
            f'<img src="{image_url}" style="width:100%;height:80%;object-fit:contain;background:#f5f5f5;">'
            if image_url
            else '<div style="width:100%;height:80%;background:#f5f5f5;display:flex;align-items:center;justify-content:center;color:#999;">暂无图片</div>'
        )

        code_html = f'<div style="color:#888;font-size:12px;">货号: {customer_code}</div>' if customer_code else ""
        remarks_html = f'<div style="color:#888;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{remarks}</div>' if remarks else ""

        cards_html += f"""
        <div style="border:1px solid #e8e8e8;border-radius:4px;padding:8px;text-align:center;display:flex;flex-direction:column;">
            {img_html}
            <div style="font-size:13px;">数量: {it.quantity} &nbsp; 单价: ¥{price_str}</div>
            {code_html}
            {remarks_html}
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>饰品大图 - {order_id}</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; margin: 20px; color: #333; }}
        .header {{ margin-bottom: 16px; font-size: 14px; color: #666; }}
        .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
        @media print {{
            body {{ margin: 10px; }}
            .grid {{ gap: 8px; }}
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

Ensure `from urllib.parse import quote` is imported at the top of `api/orders.py` (may already be present for the todo-pdf endpoint).

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_jewelry_poster.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add services/jewelry_poster.py api/orders.py tests/test_jewelry_poster.py
git commit -m "feat: add jewelry poster PDF and HTML preview endpoints"
```

---

## Task 2: Frontend — Buttons on OrderDetail

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

## Task 3: Verify

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 2: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Manual verification**

- Open order detail with jewelry items that have images
- Click "下载饰品大图" → verify PDF downloads, 3x3 grid, images clear
- Click "预览饰品大图" → verify HTML opens in new tab, correct layout
- Test with >9 items → verify pagination in PDF
- Test with customer_code set → verify it appears
- Test with jewelry missing image → verify placeholder
