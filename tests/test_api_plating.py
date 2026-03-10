import pytest

from services.part import create_part
from services.inventory import add_stock


def test_create_plating_order(client, db):
    part = create_part(db, {"name": "P1"})
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


def test_list_plating_orders(client, db):
    part = create_part(db, {"name": "P2"})
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
    part = create_part(db, {"name": "P3"})
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
    part = create_part(db, {"name": "P4"})
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


def test_send_plating_order(client, db):
    part = create_part(db, {"name": "P5"})
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
    part = create_part(db, {"name": "P6"})
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
    part = create_part(db, {"name": "P7"})
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
    part = create_part(db, {"name": "P8"})
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
