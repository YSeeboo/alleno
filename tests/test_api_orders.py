import pytest
from sqlalchemy import text
from services.jewelry import create_jewelry
from services.part import create_part
from services.bom import set_bom


def _setup(db):
    part = create_part(db, {"name": "P1", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "J1", "retail_price": 100.0, "category": "单件"})
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
    assert isinstance(data, list)


def test_update_order_status(client, db):
    part, jewelry = _setup(db)
    set_bom(db, jewelry.id, part.id, 1)
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


# --- Add / Delete order items ---

def _create_order(client, jewelry):
    return client.post("/api/orders/", json={
        "customer_name": "Test",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 50.0}],
    }).json()


def test_add_order_item(client, db):
    _, jewelry = _setup(db)
    j2 = create_jewelry(db, {"name": "J2", "retail_price": 200.0, "category": "单件"})
    order = _create_order(client, jewelry)
    resp = client.post(f"/api/orders/{order['id']}/items", json={
        "jewelry_id": j2.id, "quantity": 3, "unit_price": 80.0,
    })
    assert resp.status_code == 201
    # total recalculated: 50*1 + 80*3 = 290
    updated = client.get(f"/api/orders/{order['id']}").json()
    assert float(updated["total_amount"]) == pytest.approx(290.0)


def test_delete_order_item(client, db):
    _, jewelry = _setup(db)
    order = _create_order(client, jewelry)
    items = client.get(f"/api/orders/{order['id']}/items").json()
    resp = client.delete(f"/api/orders/{order['id']}/items/{items[0]['id']}")
    assert resp.status_code == 204
    updated = client.get(f"/api/orders/{order['id']}").json()
    assert float(updated["total_amount"]) == 0.0


def test_add_item_blocked_when_not_pending(client, db):
    _, jewelry = _setup(db)
    order = _create_order(client, jewelry)
    client.patch(f"/api/orders/{order['id']}/status", json={"status": "生产中"})
    resp = client.post(f"/api/orders/{order['id']}/items", json={
        "jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10.0,
    })
    assert resp.status_code == 400


def test_delete_item_blocked_when_not_pending(client, db):
    _, jewelry = _setup(db)
    order = _create_order(client, jewelry)
    items = client.get(f"/api/orders/{order['id']}/items").json()
    client.patch(f"/api/orders/{order['id']}/status", json={"status": "生产中"})
    resp = client.delete(f"/api/orders/{order['id']}/items/{items[0]['id']}")
    assert resp.status_code == 400


def test_add_item_invalid_quantity_rejected(client, db):
    _, jewelry = _setup(db)
    order = _create_order(client, jewelry)
    resp = client.post(f"/api/orders/{order['id']}/items", json={
        "jewelry_id": jewelry.id, "quantity": 0, "unit_price": 10.0,
    })
    assert resp.status_code == 422


def test_add_item_negative_price_rejected(client, db):
    _, jewelry = _setup(db)
    order = _create_order(client, jewelry)
    resp = client.post(f"/api/orders/{order['id']}/items", json={
        "jewelry_id": jewelry.id, "quantity": 1, "unit_price": -5.0,
    })
    assert resp.status_code == 422


def test_order_create_rejects_both_null_in_item(client):
    r = client.post("/api/orders/", json={
        "customer_name": "x",
        "items": [{"quantity": 1, "unit_price": 0}],
    })
    assert r.status_code == 422


def test_order_create_rejects_both_set_in_item(client, db):
    # Need valid jewelry & part to make pydantic ID checks pass
    db.execute(text(
        "INSERT INTO jewelry (id, name, status) VALUES ('SP-T1', 'j', 'active')"
    ))
    db.execute(text("INSERT INTO part (id, name) VALUES ('PJ-T1', 'p')"))
    db.commit()
    r = client.post("/api/orders/", json={
        "customer_name": "x",
        "items": [{
            "jewelry_id": "SP-T1",
            "part_id": "PJ-T1",
            "quantity": 1,
            "unit_price": 0,
        }],
    })
    assert r.status_code == 422


def test_get_order_items_enriches_part_info(client, db):
    from sqlalchemy import text
    db.execute(text(
        "INSERT INTO part (id, name, unit, image, wholesale_price) "
        "VALUES ('PJ-EN1', '玫瑰金链', '米', '/images/chain.png', 15)"
    ))
    db.commit()
    r = client.post("/api/orders/", json={
        "customer_name": "E",
        "items": [{"part_id": "PJ-EN1", "quantity": 3, "unit_price": 15}],
    })
    order_id = r.json()["id"]
    r = client.get(f"/api/orders/{order_id}/items")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    item = items[0]
    assert item["part_id"] == "PJ-EN1"
    assert item["jewelry_id"] is None
    assert item["part_name"] == "玫瑰金链"
    assert item["part_unit"] == "米"
    assert item["part_image"] == "/images/chain.png"


def test_add_order_item_missing_part_returns_400(client, db):
    from sqlalchemy import text
    db.execute(text("INSERT INTO part (id, name) VALUES ('PJ-VAL1', 'p')"))
    db.commit()
    r = client.post("/api/orders/", json={
        "customer_name": "x",
        "items": [{"part_id": "PJ-VAL1", "quantity": 1, "unit_price": 10}],
    })
    order_id = r.json()["id"]
    r = client.post(f"/api/orders/{order_id}/items", json={
        "part_id": "PJ-NOTREAL", "quantity": 1, "unit_price": 10,
    })
    assert r.status_code == 400
    assert "PJ-NOTREAL" in r.json()["detail"]
