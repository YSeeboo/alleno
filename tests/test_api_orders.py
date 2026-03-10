import pytest
from services.jewelry import create_jewelry
from services.part import create_part
from services.bom import set_bom


def _setup(db):
    part = create_part(db, {"name": "P1"})
    jewelry = create_jewelry(db, {"name": "J1", "retail_price": 100.0})
    return part, jewelry


def test_create_order(client, db):
    _, jewelry = _setup(db)
    resp = client.post("/api/orders/", json={
        "customer_name": "Alice",
        "items": [{"jewelry_id": jewelry.id, "quantity": 2, "unit_price": 100.0}]
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("OR-")
    assert data["customer_name"] == "Alice"


def test_get_order(client, db):
    _, jewelry = _setup(db)
    created = client.post("/api/orders/", json={
        "customer_name": "Alice",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 50.0}]
    }).json()
    resp = client.get(f"/api/orders/{created['id']}")
    assert resp.status_code == 200


def test_get_order_not_found(client, db):
    resp = client.get("/api/orders/OR-9999")
    assert resp.status_code == 404


def test_get_order_items(client, db):
    _, jewelry = _setup(db)
    created = client.post("/api/orders/", json={
        "customer_name": "Bob",
        "items": [{"jewelry_id": jewelry.id, "quantity": 3, "unit_price": 75.0}]
    }).json()
    resp = client.get(f"/api/orders/{created['id']}/items")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["quantity"] == 3


def test_get_parts_summary(client, db):
    part, jewelry = _setup(db)
    set_bom(db, jewelry.id, part.id, 2)
    created = client.post("/api/orders/", json={
        "customer_name": "Bob",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 75.0}]
    }).json()
    resp = client.get(f"/api/orders/{created['id']}/parts-summary")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_update_order_status(client, db):
    _, jewelry = _setup(db)
    created = client.post("/api/orders/", json={
        "customer_name": "Carol",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 50.0}]
    }).json()
    resp = client.patch(f"/api/orders/{created['id']}/status", json={"status": "已完成"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "已完成"


def test_update_status_not_found(client, db):
    resp = client.patch("/api/orders/OR-9999/status", json={"status": "已完成"})
    assert resp.status_code == 404
