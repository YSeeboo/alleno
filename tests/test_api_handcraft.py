import pytest
from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock, get_stock
from services.kanban import record_vendor_receipt
from schemas.kanban import ReceiptItemIn


def _setup(db):
    part = create_part(db, {"name": "P1", "category": "小配件", "color": "古铜"})
    jewelry = create_jewelry(db, {"name": "J1", "category": "单件"})
    # Add stock for the part so we can send it
    add_stock(db, "part", part.id, 100.0, "初始入库")
    return part, jewelry


def test_create_handcraft_order(client, db):
    part, jewelry = _setup(db)
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier A",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("HC-")
    assert data["supplier_name"] == "Supplier A"
    assert data["status"] == "pending"
    assert data["delivery_images"] == []

    parts_resp = client.get(f"/api/handcraft/{data['id']}/parts")
    assert parts_resp.status_code == 200
    assert parts_resp.json()[0]["color"] == "古铜"


def test_create_handcraft_order_with_note(client, db):
    part, jewelry = _setup(db)
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier B",
        "parts": [{"part_id": part.id, "qty": 5.0, "bom_qty": 4.0, "note": "extra"}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 3, "note": "rush"}],
        "note": "urgent order",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["note"] == "urgent order"


def test_list_handcraft_orders(client, db):
    part, jewelry = _setup(db)
    client.post("/api/handcraft/", json={
        "supplier_name": "Supplier A",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    })
    client.post("/api/handcraft/", json={
        "supplier_name": "Supplier B",
        "parts": [{"part_id": part.id, "qty": 5.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 2}],
    })
    resp = client.get("/api/handcraft/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_list_handcraft_orders_filter_by_status(client, db):
    part, jewelry = _setup(db)
    resp_create = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier A",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    })
    order_id = resp_create.json()["id"]

    # Send to change status to processing
    client.post(f"/api/handcraft/{order_id}/send")

    resp_pending = client.get("/api/handcraft/?status=pending")
    assert resp_pending.status_code == 200
    assert len(resp_pending.json()) == 0

    resp_processing = client.get("/api/handcraft/?status=processing")
    assert resp_processing.status_code == 200
    assert len(resp_processing.json()) == 1


def test_get_handcraft_order(client, db):
    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier A",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    }).json()
    resp = client.get(f"/api/handcraft/{created['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == created["id"]
    assert data["delivery_images"] == []


def test_update_handcraft_delivery_images(client, db):
    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier IMG",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    }).json()

    resp = client.patch(
        f"/api/handcraft/{created['id']}/delivery-images",
        json={
            "delivery_images": [
                "https://img.example.com/a.png",
                " https://img.example.com/b.png ",
            ]
        },
    )

    assert resp.status_code == 200
    assert resp.json()["delivery_images"] == [
        "https://img.example.com/a.png",
        "https://img.example.com/b.png",
    ]

    detail_resp = client.get(f"/api/handcraft/{created['id']}")
    assert detail_resp.json()["delivery_images"] == [
        "https://img.example.com/a.png",
        "https://img.example.com/b.png",
    ]


def test_update_handcraft_delivery_images_rejects_more_than_four(client, db):
    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier IMG",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    }).json()

    resp = client.patch(
        f"/api/handcraft/{created['id']}/delivery-images",
        json={
            "delivery_images": ["1.png", "2.png", "3.png", "4.png", "5.png"]
        },
    )
    assert resp.status_code == 422


def test_handcraft_part_color_reflects_part_update(client, db):
    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier Color",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    }).json()

    resp = client.patch(
        f"/api/parts/{part.id}",
        json={"color": "哑金"},
    )
    assert resp.status_code == 200
    assert resp.json()["color"] == "哑金"

    parts_resp = client.get(f"/api/handcraft/{created['id']}/parts")
    assert parts_resp.status_code == 200
    assert parts_resp.json()[0]["color"] == "哑金"


def test_get_handcraft_order_not_found(client, db):
    resp = client.get("/api/handcraft/HC-9999")
    assert resp.status_code == 404


def test_delete_handcraft_order(client, db):
    part, jewelry = _setup(db)
    db.commit()

    create_resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier Delete",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    })
    order_id = create_resp.json()["id"]

    resp = client.delete(f"/api/handcraft/{order_id}")
    assert resp.status_code == 204

    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
    assert db.query(HandcraftOrder).filter(HandcraftOrder.id == order_id).first() is None
    assert db.query(HandcraftPartItem).filter(HandcraftPartItem.handcraft_order_id == order_id).count() == 0
    assert db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.handcraft_order_id == order_id).count() == 0


def test_delete_completed_handcraft_order_restores_stock_and_clears_receipts(client, db):
    part, jewelry = _setup(db)
    db.commit()

    create_resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier Delete Completed",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    })
    order_id = create_resp.json()["id"]

    send_resp = client.post(f"/api/handcraft/{order_id}/send")
    assert send_resp.status_code == 200

    record_vendor_receipt(db, "Supplier Delete Completed", "handcraft", order_id, [
        ReceiptItemIn(item_id=part.id, item_type="part", qty=10.0),
        ReceiptItemIn(item_id=jewelry.id, item_type="jewelry", qty=5.0),
    ])

    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
    from models.vendor_receipt import VendorReceipt

    assert get_stock(db, "part", part.id) == pytest.approx(100.0)
    assert get_stock(db, "jewelry", jewelry.id) == pytest.approx(5.0)
    assert db.query(VendorReceipt).filter(VendorReceipt.order_id == order_id).count() == 2
    assert db.query(HandcraftOrder).filter(HandcraftOrder.id == order_id).first().status == "completed"

    resp = client.delete(f"/api/handcraft/{order_id}")
    assert resp.status_code == 204

    assert get_stock(db, "part", part.id) == pytest.approx(100.0)
    assert get_stock(db, "jewelry", jewelry.id) == pytest.approx(0.0)
    assert db.query(HandcraftOrder).filter(HandcraftOrder.id == order_id).first() is None
    assert db.query(HandcraftPartItem).filter(HandcraftPartItem.handcraft_order_id == order_id).count() == 0
    assert db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.handcraft_order_id == order_id).count() == 0
    assert db.query(VendorReceipt).filter(VendorReceipt.order_id == order_id).count() == 0


def test_send_handcraft_order(client, db):
    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier A",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    }).json()
    resp = client.post(f"/api/handcraft/{created['id']}/send")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processing"


def test_send_handcraft_order_not_found(client, db):
    resp = client.post("/api/handcraft/HC-9999/send")
    assert resp.status_code == 404


def test_send_handcraft_order_insufficient_stock(client, db):
    part = create_part(db, {"name": "P2", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "J2", "category": "单件"})
    # No stock added for part
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier C",
        "parts": [{"part_id": part.id, "qty": 50.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    }).json()
    resp = client.post(f"/api/handcraft/{created['id']}/send")
    assert resp.status_code == 400


def test_receive_handcraft_jewelries(client, db):
    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier A",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    }).json()
    order_id = created["id"]

    # Send first
    client.post(f"/api/handcraft/{order_id}/send")

    from models.handcraft_order import HandcraftJewelryItem
    ji = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.handcraft_order_id == order_id
    ).first()

    resp = client.post(f"/api/handcraft/{order_id}/receive", json={
        "receipts": [{"handcraft_jewelry_item_id": ji.id, "qty": 3}]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["received_qty"] == 3
    assert data[0]["status"] == "制作中"  # not yet fully received


def test_receive_handcraft_jewelries_completes_order(client, db):
    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier A",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    }).json()
    order_id = created["id"]

    client.post(f"/api/handcraft/{order_id}/send")

    from models.handcraft_order import HandcraftJewelryItem
    ji = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.handcraft_order_id == order_id
    ).first()

    # Receive all 5
    resp = client.post(f"/api/handcraft/{order_id}/receive", json={
        "receipts": [{"handcraft_jewelry_item_id": ji.id, "qty": 5}]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["status"] == "已收回"

    # Order should now be completed
    order_resp = client.get(f"/api/handcraft/{order_id}")
    assert order_resp.json()["status"] == "completed"


def test_receive_handcraft_order_not_found(client, db):
    resp = client.post("/api/handcraft/HC-9999/receive", json={"receipts": []})
    assert resp.status_code == 404


def test_receive_handcraft_jewelries_over_receive(client, db):
    part, jewelry = _setup(db)
    db.commit()

    create_resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier OVR",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    })
    order_id = create_resp.json()["id"]
    client.post(f"/api/handcraft/{order_id}/send")

    from models.handcraft_order import HandcraftJewelryItem
    ji = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.handcraft_order_id == order_id
    ).first()

    resp = client.post(f"/api/handcraft/{order_id}/receive", json={
        "receipts": [{"handcraft_jewelry_item_id": ji.id, "qty": 10}]
    })
    assert resp.status_code == 400


def test_create_handcraft_order_empty_parts(client, db):
    _, jewelry = _setup(db)
    db.commit()
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier EP",
        "parts": [],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 1}],
    })
    assert resp.status_code == 422


def test_create_handcraft_order_empty_jewelries(client, db):
    part, _ = _setup(db)
    db.commit()
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier EJ",
        "parts": [{"part_id": part.id, "qty": 5.0}],
        "jewelries": [],
    })
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"


def test_send_handcraft_order_without_expected_jewelries(client, db):
    part, _ = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier No Jewelry",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [],
    }).json()
    resp = client.post(f"/api/handcraft/{created['id']}/send")
    assert resp.status_code == 200
    assert resp.json()["status"] == "processing"


def test_create_handcraft_order_zero_part_qty(client, db):
    part, jewelry = _setup(db)
    db.commit()
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier ZP",
        "parts": [{"part_id": part.id, "qty": 0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 1}],
    })
    assert resp.status_code == 422


def test_create_handcraft_order_negative_part_qty(client, db):
    part, jewelry = _setup(db)
    db.commit()
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier NP",
        "parts": [{"part_id": part.id, "qty": -3.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 1}],
    })
    assert resp.status_code == 422


def test_create_handcraft_order_zero_jewelry_qty(client, db):
    part, jewelry = _setup(db)
    db.commit()
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier ZJ",
        "parts": [{"part_id": part.id, "qty": 5.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 0}],
    })
    assert resp.status_code == 422


def test_create_handcraft_order_negative_jewelry_qty(client, db):
    part, jewelry = _setup(db)
    db.commit()
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier NJ",
        "parts": [{"part_id": part.id, "qty": 5.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": -2}],
    })
    assert resp.status_code == 422
