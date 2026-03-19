import pytest

from services.part import create_part
from services.inventory import add_stock, get_stock
from services.kanban import record_vendor_receipt
from schemas.kanban import ReceiptItemIn


def test_create_plating_order(client, db):
    part = create_part(db, {"name": "P1", "category": "小配件"})
    db.commit()

    resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier A",
        "items": [
            {"part_id": part.id, "qty": 10.0, "plating_method": "金色"}
        ],
        "note": "test order",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["supplier_name"] == "Supplier A"
    assert data["status"] == "pending"
    assert data["id"].startswith("EP-")
    assert data["delivery_images"] == []


def test_list_plating_orders(client, db):
    part = create_part(db, {"name": "P2", "category": "小配件"})
    db.commit()

    client.post("/api/plating/", json={
        "supplier_name": "Supplier B",
        "items": [{"part_id": part.id, "qty": 5.0}],
    })
    client.post("/api/plating/", json={
        "supplier_name": "Supplier C",
        "items": [{"part_id": part.id, "qty": 3.0}],
    })

    resp = client.get("/api/plating/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_list_plating_orders_filter_by_status(client, db):
    part = create_part(db, {"name": "P3", "category": "小配件"})
    db.commit()

    client.post("/api/plating/", json={
        "supplier_name": "Supplier D",
        "items": [{"part_id": part.id, "qty": 5.0}],
    })

    resp = client.get("/api/plating/?status=pending")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "pending"

    resp2 = client.get("/api/plating/?status=processing")
    assert resp2.status_code == 200
    assert len(resp2.json()) == 0


def test_get_plating_order(client, db):
    part = create_part(db, {"name": "P4", "category": "小配件"})
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier E",
        "items": [{"part_id": part.id, "qty": 8.0}],
    })
    order_id = create_resp.json()["id"]

    resp = client.get(f"/api/plating/{order_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == order_id


def test_get_plating_order_not_found(client, db):
    resp = client.get("/api/plating/EP-9999")
    assert resp.status_code == 404


def test_delete_plating_order(client, db):
    part = create_part(db, {"name": "P_delete", "category": "小配件"})
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier Delete",
        "items": [{"part_id": part.id, "qty": 8.0}],
    })
    order_id = create_resp.json()["id"]

    resp = client.delete(f"/api/plating/{order_id}")
    assert resp.status_code == 204

    from models.plating_order import PlatingOrder, PlatingOrderItem
    assert db.query(PlatingOrder).filter(PlatingOrder.id == order_id).first() is None
    assert db.query(PlatingOrderItem).filter(PlatingOrderItem.plating_order_id == order_id).count() == 0


def test_delete_completed_plating_order_restores_stock_and_clears_receipts(client, db):
    part = create_part(db, {"name": "P_delete_completed", "category": "小配件"})
    add_stock(db, "part", part.id, 30.0, "initial stock")
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier Delete Completed",
        "items": [{"part_id": part.id, "qty": 10.0}],
    })
    order_id = create_resp.json()["id"]

    send_resp = client.post(f"/api/plating/{order_id}/send")
    assert send_resp.status_code == 200

    record_vendor_receipt(db, "Supplier Delete Completed", "plating", order_id, [
        ReceiptItemIn(item_id=part.id, item_type="part", qty=10.0),
    ])

    from models.plating_order import PlatingOrder, PlatingOrderItem
    from models.vendor_receipt import VendorReceipt

    assert get_stock(db, "part", part.id) == pytest.approx(30.0)
    assert db.query(VendorReceipt).filter(VendorReceipt.order_id == order_id).count() == 1
    assert db.query(PlatingOrder).filter(PlatingOrder.id == order_id).first().status == "completed"

    resp = client.delete(f"/api/plating/{order_id}")
    assert resp.status_code == 204

    assert get_stock(db, "part", part.id) == pytest.approx(30.0)
    assert db.query(PlatingOrder).filter(PlatingOrder.id == order_id).first() is None
    assert db.query(PlatingOrderItem).filter(PlatingOrderItem.plating_order_id == order_id).count() == 0
    assert db.query(VendorReceipt).filter(VendorReceipt.order_id == order_id).count() == 0


def test_send_plating_order(client, db):
    part = create_part(db, {"name": "P5", "category": "小配件"})
    add_stock(db, "part", part.id, 20.0, "initial stock")
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier F",
        "items": [{"part_id": part.id, "qty": 10.0, "plating_method": "银色"}],
    })
    order_id = create_resp.json()["id"]

    resp = client.post(f"/api/plating/{order_id}/send")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processing"


def test_send_plating_order_insufficient_stock(client, db):
    part = create_part(db, {"name": "P6", "category": "小配件"})
    db.commit()
    # No stock added

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier G",
        "items": [{"part_id": part.id, "qty": 10.0}],
    })
    order_id = create_resp.json()["id"]

    resp = client.post(f"/api/plating/{order_id}/send")
    assert resp.status_code == 400


def test_send_plating_order_not_found(client, db):
    resp = client.post("/api/plating/EP-9999/send")
    assert resp.status_code == 404


def test_receive_plating_items(client, db):
    part = create_part(db, {"name": "P7", "category": "小配件"})
    add_stock(db, "part", part.id, 50.0, "initial stock")
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier H",
        "items": [{"part_id": part.id, "qty": 10.0, "plating_method": "镀金"}],
    })
    order_id = create_resp.json()["id"]

    # Send the order first
    client.post(f"/api/plating/{order_id}/send")

    # Get the order items to find item IDs — query the order directly
    # The receive endpoint needs plating_order_item_id
    # We need to find the item id; let's check via the DB fixture
    from models.plating_order import PlatingOrderItem
    items = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order_id
    ).all()
    assert len(items) == 1
    item_id = items[0].id

    resp = client.post(f"/api/plating/{order_id}/receive", json={
        "receipts": [{"plating_order_item_id": item_id, "qty": 5.0}]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert float(data[0]["received_qty"]) == 5.0
    assert data[0]["status"] == "电镀中"  # not fully received yet


def test_receive_plating_items_completes_order(client, db):
    part = create_part(db, {"name": "P8", "category": "小配件"})
    add_stock(db, "part", part.id, 50.0, "initial stock")
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier I",
        "items": [{"part_id": part.id, "qty": 10.0}],
    })
    order_id = create_resp.json()["id"]

    client.post(f"/api/plating/{order_id}/send")

    from models.plating_order import PlatingOrderItem
    items = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order_id
    ).all()
    item_id = items[0].id

    # Receive full qty
    resp = client.post(f"/api/plating/{order_id}/receive", json={
        "receipts": [{"plating_order_item_id": item_id, "qty": 10.0}]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["status"] == "已收回"

    # Check order is now completed
    order_resp = client.get(f"/api/plating/{order_id}")
    assert order_resp.json()["status"] == "completed"


def test_receive_plating_items_order_not_found(client, db):
    resp = client.post("/api/plating/EP-9999/receive", json={
        "receipts": [{"plating_order_item_id": 1, "qty": 5.0}]
    })
    assert resp.status_code == 404


def test_receive_plating_items_over_receive(client, db):
    part = create_part(db, {"name": "P_over", "category": "小配件"})
    add_stock(db, "part", part.id, 50.0, "initial stock")
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier OVR",
        "items": [{"part_id": part.id, "qty": 10.0}],
    })
    order_id = create_resp.json()["id"]
    client.post(f"/api/plating/{order_id}/send")

    from models.plating_order import PlatingOrderItem
    item_id = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order_id
    ).first().id

    resp = client.post(f"/api/plating/{order_id}/receive", json={
        "receipts": [{"plating_order_item_id": item_id, "qty": 15.0}]
    })
    assert resp.status_code == 400


def test_create_plating_order_empty_items(client, db):
    resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier Empty",
        "items": [],
    })
    assert resp.status_code == 422


def test_create_plating_order_zero_qty(client, db):
    part = create_part(db, {"name": "P_zero", "category": "小配件"})
    db.commit()
    resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier Z",
        "items": [{"part_id": part.id, "qty": 0}],
    })
    assert resp.status_code == 422


def test_create_plating_order_negative_qty(client, db):
    part = create_part(db, {"name": "P_neg", "category": "小配件"})
    db.commit()
    resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier N",
        "items": [{"part_id": part.id, "qty": -5.0}],
    })
    assert resp.status_code == 422


def test_update_plating_delivery_images(client, db):
    part = create_part(db, {"name": "P_img", "category": "小配件"})
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier IMG",
        "items": [{"part_id": part.id, "qty": 8.0}],
    })
    order_id = create_resp.json()["id"]

    resp = client.patch(f"/api/plating/{order_id}/delivery-images", json={
        "delivery_images": [
            "https://img.example.com/a.png",
            "https://img.example.com/b.png",
        ],
    })
    assert resp.status_code == 200
    assert resp.json()["delivery_images"] == [
        "https://img.example.com/a.png",
        "https://img.example.com/b.png",
    ]

    detail_resp = client.get(f"/api/plating/{order_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["delivery_images"] == [
        "https://img.example.com/a.png",
        "https://img.example.com/b.png",
    ]


def test_update_plating_delivery_images_rejects_more_than_four(client, db):
    part = create_part(db, {"name": "P_img_limit", "category": "小配件"})
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier IMG LIMIT",
        "items": [{"part_id": part.id, "qty": 6.0}],
    })
    order_id = create_resp.json()["id"]

    resp = client.patch(f"/api/plating/{order_id}/delivery-images", json={
        "delivery_images": ["1.png", "2.png", "3.png", "4.png", "5.png"],
    })
    assert resp.status_code == 422


def test_get_plating_items_keeps_id_order_after_update(client, db):
    parts = []
    for index in range(3):
        part = create_part(db, {"name": f"排序配件{index + 1}", "category": "小配件"})
        parts.append(part)
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "排序测试电镀厂",
        "items": [
            {"part_id": parts[0].id, "qty": 1, "unit": "个"},
            {"part_id": parts[1].id, "qty": 2, "unit": "个"},
            {"part_id": parts[2].id, "qty": 3, "unit": "个"},
        ],
    })
    order_id = create_resp.json()["id"]

    before_resp = client.get(f"/api/plating/{order_id}/items")
    assert before_resp.status_code == 200
    before_ids = [item["id"] for item in before_resp.json()]

    client.put(f"/api/plating/{order_id}/items/{before_ids[1]}", json={"unit": "条"})

    after_resp = client.get(f"/api/plating/{order_id}/items")
    assert after_resp.status_code == 200
    after_ids = [item["id"] for item in after_resp.json()]

    assert after_ids == before_ids
