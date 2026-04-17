"""API tests for /api/orders/{id}/picking/... endpoints."""

from decimal import Decimal

from models.bom import Bom
from models.jewelry import Jewelry
from models.order import Order, OrderItem, OrderPickingRecord
from models.part import Part


def _setup(db):
    """Minimal fixture: 1 order, 1 jewelry, 1 part."""
    db.add(Part(id="PJ-X-00001", name="珠子", category="吊坠"))
    db.add(Jewelry(id="SP-0001", name="J", category="戒指"))
    db.flush()
    db.add(Bom(id="BM-0001", jewelry_id="SP-0001", part_id="PJ-X-00001",
               qty_per_unit=Decimal("2.0")))
    db.add(Order(id="OR-TEST-1", customer_name="张三"))
    db.flush()
    db.add(OrderItem(order_id="OR-TEST-1", jewelry_id="SP-0001",
                     quantity=5, unit_price=Decimal("1.0")))
    db.flush()


def test_get_picking_returns_aggregated_structure(client, db):
    _setup(db)
    resp = client.get("/api/orders/OR-TEST-1/picking")
    assert resp.status_code == 200
    body = resp.json()
    assert body["order_id"] == "OR-TEST-1"
    assert body["customer_name"] == "张三"
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["part_id"] == "PJ-X-00001"
    assert row["variants"][0]["qty_per_unit"] == 2.0
    assert row["variants"][0]["subtotal"] == 10.0
    assert body["progress"] == {"total": 1, "picked": 0}


def test_get_picking_order_not_found(client, db):
    resp = client.get("/api/orders/OR-NOPE/picking")
    assert resp.status_code == 400  # bubbles as ValueError → 400 via service_errors
    assert "OR-NOPE" in resp.json()["detail"]


def test_post_mark_marks_variant(client, db):
    _setup(db)
    resp = client.post(
        "/api/orders/OR-TEST-1/picking/mark",
        json={"part_id": "PJ-X-00001", "qty_per_unit": 2.0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["picked"] is True
    assert body["picked_at"] is not None

    # Confirm it sticks on the next GET.
    g = client.get("/api/orders/OR-TEST-1/picking").json()
    assert g["rows"][0]["variants"][0]["picked"] is True
    assert g["progress"]["picked"] == 1


def test_post_mark_idempotent(client, db):
    _setup(db)
    for _ in range(3):
        r = client.post(
            "/api/orders/OR-TEST-1/picking/mark",
            json={"part_id": "PJ-X-00001", "qty_per_unit": 2.0},
        )
        assert r.status_code == 200
    count = db.query(OrderPickingRecord).filter_by(order_id="OR-TEST-1").count()
    assert count == 1


def test_post_mark_invalid_variant_rejected(client, db):
    _setup(db)
    resp = client.post(
        "/api/orders/OR-TEST-1/picking/mark",
        json={"part_id": "PJ-X-00001", "qty_per_unit": 999.0},  # wrong qty
    )
    assert resp.status_code == 400
    assert "配货范围" in resp.json()["detail"]


def test_post_unmark_removes_record(client, db):
    _setup(db)
    client.post(
        "/api/orders/OR-TEST-1/picking/mark",
        json={"part_id": "PJ-X-00001", "qty_per_unit": 2.0},
    )
    resp = client.post(
        "/api/orders/OR-TEST-1/picking/unmark",
        json={"part_id": "PJ-X-00001", "qty_per_unit": 2.0},
    )
    assert resp.status_code == 200
    assert resp.json()["picked"] is False

    g = client.get("/api/orders/OR-TEST-1/picking").json()
    assert g["rows"][0]["variants"][0]["picked"] is False


def test_post_unmark_idempotent(client, db):
    _setup(db)
    resp = client.post(
        "/api/orders/OR-TEST-1/picking/unmark",
        json={"part_id": "PJ-X-00001", "qty_per_unit": 2.0},
    )
    assert resp.status_code == 200  # no error when nothing to delete


def test_delete_reset_clears_all(client, db):
    _setup(db)
    # Add a second part and variant for realism.
    db.add(Part(id="PJ-X-00002", name="链扣", category="吊坠"))
    db.flush()
    db.add(Bom(id="BM-0002", jewelry_id="SP-0001", part_id="PJ-X-00002",
               qty_per_unit=Decimal("1.0")))
    db.flush()
    client.post("/api/orders/OR-TEST-1/picking/mark",
                json={"part_id": "PJ-X-00001", "qty_per_unit": 2.0})
    client.post("/api/orders/OR-TEST-1/picking/mark",
                json={"part_id": "PJ-X-00002", "qty_per_unit": 1.0})

    resp = client.delete("/api/orders/OR-TEST-1/picking/reset")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 2}

    count = db.query(OrderPickingRecord).filter_by(order_id="OR-TEST-1").count()
    assert count == 0


# --- PDF generation ---


def test_build_picking_list_pdf_returns_bytes(db):
    from services.picking_list_pdf import build_picking_list_pdf
    _setup(db)
    file_bytes, filename = build_picking_list_pdf(db, "OR-TEST-1", "张三", include_picked=False)
    assert isinstance(file_bytes, bytes)
    assert file_bytes.startswith(b"%PDF")
    assert filename == "配货清单_OR-TEST-1.pdf"


def test_build_picking_list_pdf_empty_raises(db):
    """Order with no items (or all picked and include_picked=False) → ValueError."""
    from services.picking_list_pdf import build_picking_list_pdf
    import pytest
    db.add(Order(id="OR-EMPTY", customer_name="X"))
    db.flush()
    with pytest.raises(ValueError, match="没有需要配货"):
        build_picking_list_pdf(db, "OR-EMPTY", "X", include_picked=False)


def test_build_picking_list_pdf_filters_picked_by_default(db):
    """When include_picked=False (default), rows with all variants picked
    are omitted; partially picked rows keep only unpicked variants."""
    from services.picking_list_pdf import build_picking_list_pdf
    from services.picking import mark_picked
    _setup(db)
    mark_picked(db, "OR-TEST-1", "PJ-X-00001", 2.0)
    # Only variant → now fully picked → PDF should raise "nothing to pick".
    import pytest
    with pytest.raises(ValueError, match="没有需要配货"):
        build_picking_list_pdf(db, "OR-TEST-1", "张三", include_picked=False)


def test_build_picking_list_pdf_include_picked_flag(db):
    """include_picked=True renders picked rows too, so the PDF is non-empty."""
    from services.picking_list_pdf import build_picking_list_pdf
    from services.picking import mark_picked
    _setup(db)
    mark_picked(db, "OR-TEST-1", "PJ-X-00001", 2.0)
    file_bytes, _ = build_picking_list_pdf(db, "OR-TEST-1", "张三", include_picked=True)
    assert file_bytes.startswith(b"%PDF")


def test_post_picking_pdf_returns_pdf(client, db):
    _setup(db)
    resp = client.post("/api/orders/OR-TEST-1/picking/pdf", json={})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    disp = resp.headers["content-disposition"]
    assert "配货清单_OR-TEST-1.pdf" in disp or "picking-list-OR-TEST-1.pdf" in disp


def test_post_picking_pdf_400_when_nothing_to_pick(client, db):
    db.add(Order(id="OR-EMPTY", customer_name="X"))
    db.flush()
    resp = client.post("/api/orders/OR-EMPTY/picking/pdf", json={})
    assert resp.status_code == 400
    assert "没有需要配货" in resp.json()["detail"]


def test_post_picking_pdf_include_picked_flag(client, db):
    _setup(db)
    client.post("/api/orders/OR-TEST-1/picking/mark",
                json={"part_id": "PJ-X-00001", "qty_per_unit": 2.0})
    # Default (include_picked=False) → 400 (everything picked).
    r1 = client.post("/api/orders/OR-TEST-1/picking/pdf", json={})
    assert r1.status_code == 400
    # include_picked=True → 200 PDF.
    r2 = client.post("/api/orders/OR-TEST-1/picking/pdf",
                     json={"include_picked": True})
    assert r2.status_code == 200
    assert r2.content.startswith(b"%PDF")


# --- PDF footer regression ---


def _extract_pdf_pages(pdf_bytes: bytes) -> list[str]:
    """Extract text per page from a PDF using pypdf."""
    from io import BytesIO
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(pdf_bytes))
    return [page.extract_text() or "" for page in reader.pages]


def test_picking_pdf_single_page_has_footer(db):
    """Single-page PDF must contain footer text proving NumberedCanvas
    stamps the last (and only) page."""
    from services.picking_list_pdf import build_picking_list_pdf
    _setup(db)
    file_bytes, _ = build_picking_list_pdf(db, "OR-TEST-1", "张三")
    pages = _extract_pdf_pages(file_bytes)
    assert len(pages) == 1
    text = pages[0]
    assert "1 / 1" in text, f"Footer page numbering missing. Page text: {text[:200]}"
    assert "Allen Shop" in text, f"Footer brand missing. Page text: {text[:200]}"


def test_picking_pdf_multi_page_has_footer_on_all_pages(db):
    """Generate a PDF with enough parts to span 2 pages. Verify footer
    appears on every page with correct page numbers."""
    from services.picking_list_pdf import build_picking_list_pdf
    # 15 parts → 15 rows → should exceed one page (~12 rows/page at 55pt).
    jewelry = Jewelry(id="SP-0001", name="J", category="戒指")
    db.add(jewelry)
    db.flush()
    order = Order(id="OR-MULTI", customer_name="测试多页")
    db.add(order)
    db.flush()
    db.add(OrderItem(order_id="OR-MULTI", jewelry_id="SP-0001",
                     quantity=3, unit_price=Decimal("1.0")))
    db.flush()
    for i in range(15):
        pid = f"PJ-X-{i:05d}"
        db.add(Part(id=pid, name=f"配件{i}", category="吊坠"))
        db.flush()
        db.add(Bom(id=f"BM-M{i:04d}", jewelry_id="SP-0001", part_id=pid,
                   qty_per_unit=Decimal("1.0")))
    db.flush()

    file_bytes, _ = build_picking_list_pdf(db, "OR-MULTI", "测试多页")
    pages = _extract_pdf_pages(file_bytes)
    assert len(pages) >= 2, f"Expected 2+ pages, got {len(pages)}"
    total = len(pages)
    for i, text in enumerate(pages, 1):
        assert f"{i} / {total}" in text, (
            f"Page {i}: footer numbering '{i} / {total}' missing. Text: {text[:200]}"
        )
        assert "Allen Shop" in text, (
            f"Page {i}: footer brand missing. Text: {text[:200]}"
        )
