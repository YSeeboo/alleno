from io import BytesIO
from urllib.parse import quote

from PIL import Image
from pypdf import PdfReader

from models.handcraft_order import HandcraftOrder
from services.inventory import add_stock
from services.jewelry import create_jewelry
from services.part import create_part


def test_download_handcraft_pdf_single_page_with_two_images(client, db, monkeypatch):
    monkeypatch.setattr("services.handcraft_pdf.download_image_bytes", _fake_download_image_bytes)

    part = create_part(
        db,
        {
            "name": "PDF手工配件",
            "category": "小配件",
            "image": "https://img.example.com/part.png",
            "unit": "个",
        },
    )
    jewelry = create_jewelry(db, {"name": "成品A", "category": "单件"})
    add_stock(db, "part", part.id, 20.0, "initial stock")
    db.flush()

    create_resp = client.post(
        "/api/handcraft/",
        json={
            "supplier_name": "PDF手工厂",
            "parts": [{"part_id": part.id, "qty": 8, "unit": "个", "note": "要求"}],
            "jewelries": [{"jewelry_id": jewelry.id, "qty": 2}],
        },
    )
    order_id = create_resp.json()["id"]
    order = db.query(HandcraftOrder).filter(HandcraftOrder.id == order_id).first()

    client.patch(
        f"/api/handcraft/{order_id}/delivery-images",
        json={"delivery_images": ["https://img.example.com/a.png", "https://img.example.com/b.png"]},
    )

    response = client.get(f"/api/handcraft/{order_id}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    expected_date = f"{order.created_at.year % 100:02d}{order.created_at.month:02d}{order.created_at.day:02d}"
    expected_filename = f"发出_PDF手工厂_{expected_date}_{order.receipt_code}.pdf"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="handcraft-export.pdf"; filename*=UTF-8\'\'{quote(expected_filename)}'
    )
    assert len(PdfReader(BytesIO(response.content)).pages) == 1


def test_download_handcraft_pdf_moves_image_three_and_four_to_second_page(client, db, monkeypatch):
    monkeypatch.setattr("services.handcraft_pdf.download_image_bytes", _fake_download_image_bytes)

    part = create_part(db, {"name": "PDF分页配件", "category": "小配件", "unit": "个"})
    jewelry = create_jewelry(db, {"name": "成品B", "category": "单件"})
    add_stock(db, "part", part.id, 20.0, "initial stock")
    db.flush()

    create_resp = client.post(
        "/api/handcraft/",
        json={
            "supplier_name": "PDF分页厂",
            "parts": [{"part_id": part.id, "qty": 5, "unit": "个"} for _ in range(18)],
            "jewelries": [{"jewelry_id": jewelry.id, "qty": 2}],
        },
    )
    order_id = create_resp.json()["id"]

    client.patch(
        f"/api/handcraft/{order_id}/delivery-images",
        json={
            "delivery_images": [
                "https://img.example.com/1.png",
                "https://img.example.com/2.png",
                "https://img.example.com/3.png",
                "https://img.example.com/4.png",
            ]
        },
    )

    response = client.get(f"/api/handcraft/{order_id}/pdf")
    assert response.status_code == 200
    # Render order is now: parts → 配件配齐 notice → images. Page 1 holds the
    # first chunk of rows; page 2 holds the remaining row + notice + 4 inline
    # images (≤4 still flow inline, just below the notice now).
    assert len(PdfReader(BytesIO(response.content)).pages) == 2


def test_download_handcraft_pdf_moves_all_images_after_detail_pages_when_more_than_ten_rows(client, db, monkeypatch):
    monkeypatch.setattr("services.handcraft_pdf.download_image_bytes", _fake_download_image_bytes)

    jewelry = create_jewelry(db, {"name": "成品C", "category": "单件"})
    items = []
    for index in range(20):
        part = create_part(
            db,
            {
                "name": f"PDF大单配件{index + 1}",
                "category": "小配件",
                "image": "https://img.example.com/part.png",
                "unit": "个",
            },
        )
        add_stock(db, "part", part.id, 20.0, "initial stock")
        items.append({"part_id": part.id, "qty": 3, "unit": "个", "note": f"备注{index + 1}"})
    db.flush()

    create_resp = client.post(
        "/api/handcraft/",
        json={
            "supplier_name": "PDF大单厂",
            "parts": items,
            "jewelries": [{"jewelry_id": jewelry.id, "qty": 3}],
        },
    )
    order_id = create_resp.json()["id"]

    client.patch(
        f"/api/handcraft/{order_id}/delivery-images",
        json={
            "delivery_images": [
                "https://img.example.com/a.png",
                "https://img.example.com/b.png",
                "https://img.example.com/c.png",
                "https://img.example.com/d.png",
            ]
        },
    )

    response = client.get(f"/api/handcraft/{order_id}/pdf")
    assert response.status_code == 200
    # Same as above: parts → notice → images. 20 rows fit across 2 pages
    # with the notice + 4 inline images on the trailing page.
    assert len(PdfReader(BytesIO(response.content)).pages) == 2


def test_download_handcraft_pdf_order_not_found(client):
    response = client.get("/api/handcraft/HC-9999/pdf")
    assert response.status_code == 404


def _fake_download_image_bytes(source):
    if not source:
        return None
    image = Image.new("RGB", (160, 120), _color_for_source(source))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _color_for_source(source: str) -> tuple[int, int, int]:
    total = sum(ord(char) for char in source)
    return (
        40 + total % 150,
        40 + (total * 3) % 150,
        40 + (total * 5) % 150,
    )


def test_download_handcraft_pdf_blocks_when_shortfall_unfilled(client, db, monkeypatch):
    """Pending RestockRequest with null shortfall_qty must abort PDF export."""
    monkeypatch.setattr("services.handcraft_pdf.download_image_bytes", _fake_download_image_bytes)
    from models.restock_request import RestockRequest

    part = create_part(
        db,
        {"name": "缺件A", "category": "小配件", "unit": "个"},
    )
    add_stock(db, "part", part.id, 5.0, "initial")

    create_resp = client.post(
        "/api/handcraft/",
        json={
            "supplier_name": "缺件商家",
            "parts": [{"part_id": part.id, "qty": 10, "unit": "个"}],
        },
    )
    order_id = create_resp.json()["id"]

    db.add(RestockRequest(
        part_id=part.id, handcraft_order_id=order_id,
        source="picking", status="pending", shortfall_qty=None,
    ))
    db.flush()

    response = client.get(f"/api/handcraft/{order_id}/pdf")
    assert response.status_code == 400
    assert "未填写差额" in response.json()["detail"]
    assert part.id in response.json()["detail"]


def test_download_handcraft_pdf_includes_shortage_section(client, db, monkeypatch):
    """When pending RestockRequest rows have shortfall_qty filled, the PDF
    embeds them. The output is binary so we just assert success + page count."""
    monkeypatch.setattr("services.handcraft_pdf.download_image_bytes", _fake_download_image_bytes)
    from models.restock_request import RestockRequest

    part = create_part(
        db,
        {"name": "缺件B", "category": "小配件", "unit": "个", "image": "https://img.example.com/p.png"},
    )
    add_stock(db, "part", part.id, 3.0, "initial")

    create_resp = client.post(
        "/api/handcraft/",
        json={
            "supplier_name": "齐全商家",
            "parts": [{"part_id": part.id, "qty": 8, "unit": "个"}],
        },
    )
    order_id = create_resp.json()["id"]

    db.add(RestockRequest(
        part_id=part.id, handcraft_order_id=order_id,
        source="picking", status="pending", shortfall_qty=200,
    ))
    db.flush()

    response = client.get(f"/api/handcraft/{order_id}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    # At least one page; can't easily assert text content of PDF binary.
    assert len(PdfReader(BytesIO(response.content)).pages) >= 1


def test_download_handcraft_pdf_no_shortage_notice_when_no_pending(client, db, monkeypatch):
    """No pending records → PDF still produced; the section becomes the
    'all complete' notice. Smoke test, just asserts success."""
    monkeypatch.setattr("services.handcraft_pdf.download_image_bytes", _fake_download_image_bytes)

    part = create_part(db, {"name": "正常A", "category": "小配件", "unit": "个"})
    add_stock(db, "part", part.id, 50.0, "initial")
    create_resp = client.post(
        "/api/handcraft/",
        json={
            "supplier_name": "正常商家",
            "parts": [{"part_id": part.id, "qty": 10, "unit": "个"}],
        },
    )
    order_id = create_resp.json()["id"]

    response = client.get(f"/api/handcraft/{order_id}/pdf")
    assert response.status_code == 200
    assert len(PdfReader(BytesIO(response.content)).pages) >= 1


def test_download_handcraft_pdf_skips_section_for_done_records(client, db, monkeypatch):
    """A done RestockRequest is history — the export should treat the order as
    'all complete' for shortage purposes (no table, just the notice)."""
    monkeypatch.setattr("services.handcraft_pdf.download_image_bytes", _fake_download_image_bytes)
    from models.restock_request import RestockRequest
    from time_utils import now_beijing

    part = create_part(db, {"name": "已补A", "category": "小配件", "unit": "个"})
    add_stock(db, "part", part.id, 3.0, "initial")
    create_resp = client.post(
        "/api/handcraft/",
        json={
            "supplier_name": "已补商家",
            "parts": [{"part_id": part.id, "qty": 5, "unit": "个"}],
        },
    )
    order_id = create_resp.json()["id"]

    db.add(RestockRequest(
        part_id=part.id, handcraft_order_id=order_id,
        source="picking", status="done", completed_at=now_beijing(),
        shortfall_qty=None,
    ))
    db.flush()

    response = client.get(f"/api/handcraft/{order_id}/pdf")
    assert response.status_code == 200


def test_download_handcraft_pdf_overflow_inline_images_with_shortage_does_not_overlap(
    client, db, monkeypatch,
):
    """Regression: when details span multiple pages AND inline images get
    pushed to their own page AND there's a shortage section, the shortage
    section must NOT paint over the images. We check page count: details
    page(s) + inline-images page + shortage page (forced new page) ≥ 3."""
    monkeypatch.setattr("services.handcraft_pdf.download_image_bytes", _fake_download_image_bytes)
    from models.restock_request import RestockRequest

    part = create_part(
        db,
        {"name": "溢出件", "category": "小配件", "unit": "个", "image": "https://img.example.com/p.png"},
    )
    add_stock(db, "part", part.id, 200.0, "init")

    # 60 single-line items so the LAST data page is dense enough that the 4
    # inline images can't fit at its bottom. That's the path Bug 2 covers:
    # _draw_images_page is forced onto its own page, and the shortage section
    # must NOT paint over those images.
    parts_payload = [
        {"part_id": part.id, "qty": 1, "unit": "个", "note": f"row-{i}"}
        for i in range(60)
    ]
    create_resp = client.post(
        "/api/handcraft/",
        json={"supplier_name": "溢出商家", "parts": parts_payload},
    )
    order_id = create_resp.json()["id"]

    client.patch(
        f"/api/handcraft/{order_id}/delivery-images",
        json={"delivery_images": [
            "https://img.example.com/a.png", "https://img.example.com/b.png",
            "https://img.example.com/c.png", "https://img.example.com/d.png",
        ]},
    )

    # One pending shortage (filled) → table prints
    db.add(RestockRequest(
        part_id=part.id, handcraft_order_id=order_id,
        source="picking", status="pending", shortfall_qty=50,
    ))
    db.flush()

    response = client.get(f"/api/handcraft/{order_id}/pdf")
    assert response.status_code == 200
    pages = PdfReader(BytesIO(response.content)).pages
    # data pages + inline-images page + shortage page. Pre-fix the shortage
    # section painted on top of the images page so the count was one less.
    assert len(pages) >= 4, f"expected ≥4 pages (got {len(pages)}); shortage may be overlapping images"


def test_download_handcraft_pdf_zero_shortfall_is_skipped(client, db, monkeypatch):
    """shortfall_qty == 0 means 'not actually short' — keep the row in DB
    as history but suppress it from the supplier PDF (and the small
    semantic mismatch with the '以下配件因库存不足暂未发出' subtitle)."""
    monkeypatch.setattr("services.handcraft_pdf.download_image_bytes", _fake_download_image_bytes)
    from models.restock_request import RestockRequest
    from services.handcraft_export import get_handcraft_export_payload

    part = create_part(db, {"name": "零差额", "category": "小配件", "unit": "个"})
    add_stock(db, "part", part.id, 10.0, "init")
    create_resp = client.post(
        "/api/handcraft/",
        json={
            "supplier_name": "零商家",
            "parts": [{"part_id": part.id, "qty": 5, "unit": "个"}],
        },
    )
    order_id = create_resp.json()["id"]
    db.add(RestockRequest(
        part_id=part.id, handcraft_order_id=order_id,
        source="picking", status="pending", shortfall_qty=0,
    ))
    db.flush()

    payload = get_handcraft_export_payload(db, order_id)
    assert payload["shortage_rows"] == []  # zero skipped → falls back to "all complete" notice

    response = client.get(f"/api/handcraft/{order_id}/pdf")
    assert response.status_code == 200  # gate didn't block (only null does)


def test_handcraft_pdf_appends_receipt_page_with_aliases(client, db, monkeypatch):
    """When jewelry items have resolved customers, the PDF ends with a
    手工回执 page that uses 客户 N aliases — real names must NOT appear."""
    monkeypatch.setattr("services.handcraft_pdf.download_image_bytes", _fake_download_image_bytes)

    part = create_part(db, {"name": "RP配件", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "RP饰品", "category": "单件"})
    add_stock(db, "part", part.id, 100.0, "initial")
    db.flush()

    create_resp = client.post(
        "/api/handcraft/",
        json={
            "supplier_name": "RP手工厂",
            "parts": [{"part_id": part.id, "qty": 10}],
            "jewelries": [
                {"jewelry_id": jewelry.id, "qty": 1000, "customer_name": "周大福"},
                {"jewelry_id": jewelry.id, "qty": 1200, "customer_name": "上海陈姐"},
                {"jewelry_id": jewelry.id, "qty": 200, "customer_name": "广州王哥"},
            ],
        },
    )
    order_id = create_resp.json()["id"]

    response = client.get(f"/api/handcraft/{order_id}/pdf")
    assert response.status_code == 200

    reader = PdfReader(BytesIO(response.content))
    all_text = "\n".join((p.extract_text() or "") for p in reader.pages)
    # Receipt page is present
    assert "手工回执" in all_text
    # Aliases used
    assert "客户 1" in all_text
    assert "客户 2" in all_text
    assert "客户 3" in all_text
    # Real names must NOT appear anywhere in the PDF
    assert "周大福" not in all_text
    assert "上海陈姐" not in all_text
    assert "广州王哥" not in all_text


def test_handcraft_pdf_skips_receipt_page_when_no_customers(client, db, monkeypatch):
    """No 手工回执 page when no jewelry breakdown rows have a customer."""
    monkeypatch.setattr("services.handcraft_pdf.download_image_bytes", _fake_download_image_bytes)

    part = create_part(db, {"name": "NoCustPart", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "NoCustJewelry", "category": "单件"})
    add_stock(db, "part", part.id, 10.0, "initial")
    db.flush()

    create_resp = client.post(
        "/api/handcraft/",
        json={
            "supplier_name": "NoCust厂",
            "parts": [{"part_id": part.id, "qty": 5}],
            "jewelries": [{"jewelry_id": jewelry.id, "qty": 3}],
        },
    )
    order_id = create_resp.json()["id"]

    response = client.get(f"/api/handcraft/{order_id}/pdf")
    reader = PdfReader(BytesIO(response.content))
    all_text = "\n".join((p.extract_text() or "") for p in reader.pages)
    assert "手工回执" not in all_text
