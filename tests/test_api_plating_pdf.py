from io import BytesIO
from urllib.parse import quote

from PIL import Image
from pypdf import PdfReader

from models.plating_order import PlatingOrder
from services.inventory import add_stock
from services.part import create_part


def test_download_plating_pdf_single_page_with_two_images(client, db, monkeypatch):
    monkeypatch.setattr("services.plating_pdf.download_image_bytes", _fake_download_image_bytes)

    part = create_part(
        db,
        {
            "name": "PDF配件",
            "category": "小配件",
            "image": "https://img.example.com/part.png",
            "unit": "个",
        },
    )
    add_stock(db, "part", part.id, 20.0, "initial stock")
    db.flush()

    create_resp = client.post(
        "/api/plating/",
        json={
            "supplier_name": "PDF电镀厂",
            "items": [{"part_id": part.id, "qty": 8, "unit": "个", "plating_method": "白K", "note": "要求"}],
        },
    )
    order_id = create_resp.json()["id"]
    order = db.query(PlatingOrder).filter(PlatingOrder.id == order_id).first()

    client.patch(
        f"/api/plating/{order_id}/delivery-images",
        json={"delivery_images": ["https://img.example.com/a.png", "https://img.example.com/b.png"]},
    )

    response = client.get(f"/api/plating/{order_id}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    expected_date = f"{order.created_at.year % 100:02d}{order.created_at.month:02d}{order.created_at.day:02d}"
    expected_filename = f"发出_PDF电镀厂_{expected_date}.pdf"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="plating-export.pdf"; filename*=UTF-8\'\'{quote(expected_filename)}'
    )
    assert len(PdfReader(BytesIO(response.content)).pages) == 1


def test_download_plating_pdf_moves_image_three_and_four_to_second_page(client, db, monkeypatch):
    monkeypatch.setattr("services.plating_pdf.download_image_bytes", _fake_download_image_bytes)

    part = create_part(db, {"name": "PDF分页配件", "category": "小配件", "unit": "个"})
    add_stock(db, "part", part.id, 20.0, "initial stock")
    db.flush()

    create_resp = client.post(
        "/api/plating/",
        json={
            "supplier_name": "PDF分页厂",
            "items": [{"part_id": part.id, "qty": 5, "unit": "个"} for _ in range(18)],
        },
    )
    order_id = create_resp.json()["id"]

    client.patch(
        f"/api/plating/{order_id}/delivery-images",
        json={
            "delivery_images": [
                "https://img.example.com/1.png",
                "https://img.example.com/2.png",
                "https://img.example.com/3.png",
                "https://img.example.com/4.png",
            ]
        },
    )

    response = client.get(f"/api/plating/{order_id}/pdf")
    assert response.status_code == 200
    assert len(PdfReader(BytesIO(response.content)).pages) == 2


def test_download_plating_pdf_moves_all_images_after_detail_pages_when_more_than_ten_rows(client, db, monkeypatch):
    monkeypatch.setattr("services.plating_pdf.download_image_bytes", _fake_download_image_bytes)

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

    create_resp = client.post("/api/plating/", json={"supplier_name": "PDF大单厂", "items": items})
    order_id = create_resp.json()["id"]

    client.patch(
        f"/api/plating/{order_id}/delivery-images",
        json={
            "delivery_images": [
                "https://img.example.com/a.png",
                "https://img.example.com/b.png",
                "https://img.example.com/c.png",
                "https://img.example.com/d.png",
            ]
        },
    )

    response = client.get(f"/api/plating/{order_id}/pdf")
    assert response.status_code == 200
    assert len(PdfReader(BytesIO(response.content)).pages) == 2


def test_download_plating_pdf_order_not_found(client):
    response = client.get("/api/plating/EP-9999/pdf")
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
