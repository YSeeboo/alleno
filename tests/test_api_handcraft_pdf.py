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
    expected_filename = f"发出_PDF手工厂_{expected_date}.pdf"
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
            "parts": [{"part_id": part.id, "qty": 5, "unit": "个"} for _ in range(10)],
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
    assert len(PdfReader(BytesIO(response.content)).pages) == 2


def test_download_handcraft_pdf_moves_all_images_after_detail_pages_when_more_than_ten_rows(client, db, monkeypatch):
    monkeypatch.setattr("services.handcraft_pdf.download_image_bytes", _fake_download_image_bytes)

    jewelry = create_jewelry(db, {"name": "成品C", "category": "单件"})
    items = []
    for index in range(11):
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
