"""Tests for weight and weight_unit fields on order and receipt items."""


def test_plating_item_weight(client, db):
    """Plating order item stores and returns weight."""
    from models.part import Part
    from services.inventory import add_stock

    part = Part(id="PJ-X-WT1", name="重量测试", category="小配件")
    db.add(part)
    db.flush()
    add_stock(db, "part", part.id, 100, "入库")
    db.flush()

    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀商",
        "items": [{"part_id": part.id, "qty": 50, "weight": 150.5, "weight_unit": "g"}],
    })
    assert resp.status_code in (200, 201)
    order_id = resp.json()["id"]

    items_resp = client.get(f"/api/plating/{order_id}/items")
    assert items_resp.status_code == 200
    item = items_resp.json()[0]
    assert item["weight"] == 150.5
    assert item["weight_unit"] == "g"


def test_plating_item_weight_default_none(client, db):
    """Weight defaults to None when not provided."""
    from models.part import Part
    from services.inventory import add_stock

    part = Part(id="PJ-X-WT2", name="无重量", category="小配件")
    db.add(part)
    db.flush()
    add_stock(db, "part", part.id, 100, "入库")
    db.flush()

    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀商",
        "items": [{"part_id": part.id, "qty": 50}],
    })
    assert resp.status_code in (200, 201)
    order_id = resp.json()["id"]

    items_resp = client.get(f"/api/plating/{order_id}/items")
    item = items_resp.json()[0]
    assert item["weight"] is None


def test_handcraft_part_item_weight(client, db):
    """Handcraft part item stores and returns weight."""
    from models.part import Part
    from services.inventory import add_stock

    part = Part(id="PJ-X-WT3", name="手工重量测试", category="小配件")
    db.add(part)
    db.flush()
    add_stock(db, "part", part.id, 100, "入库")
    db.flush()

    resp = client.post("/api/handcraft/", json={
        "supplier_name": "手工商",
        "parts": [{"part_id": part.id, "qty": 30, "weight": 2.5, "weight_unit": "kg"}],
    })
    assert resp.status_code in (200, 201)
    order_id = resp.json()["id"]

    parts_resp = client.get(f"/api/handcraft/{order_id}/parts")
    assert parts_resp.status_code == 200
    item = parts_resp.json()[0]
    assert item["weight"] == 2.5
    assert item["weight_unit"] == "kg"


def test_handcraft_jewelry_item_weight(client, db):
    """Handcraft jewelry item stores and returns weight."""
    from models.part import Part
    from models.jewelry import Jewelry
    from services.inventory import add_stock

    part = Part(id="PJ-X-WT4", name="手工配件", category="小配件")
    db.add(part)
    db.flush()
    add_stock(db, "part", part.id, 100, "入库")
    jewelry = Jewelry(id="SP-0001", name="测试饰品", category="项链")
    db.add(jewelry)
    db.flush()

    resp = client.post("/api/handcraft/", json={
        "supplier_name": "手工商",
        "parts": [{"part_id": part.id, "qty": 30}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 10, "weight": 5.0, "weight_unit": "g"}],
    })
    assert resp.status_code in (200, 201)
    order_id = resp.json()["id"]

    jewelries_resp = client.get(f"/api/handcraft/{order_id}/jewelries")
    assert jewelries_resp.status_code == 200
    j_item = jewelries_resp.json()[0]
    assert j_item["weight"] == 5.0
    assert j_item["weight_unit"] == "g"


def test_plating_item_update_weight(client, db):
    """Plating order item weight can be updated via PUT."""
    from models.part import Part
    from services.inventory import add_stock

    part = Part(id="PJ-X-WT5", name="更新重量", category="小配件")
    db.add(part)
    db.flush()
    add_stock(db, "part", part.id, 100, "入库")
    db.flush()

    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀商",
        "items": [{"part_id": part.id, "qty": 50}],
    })
    order_id = resp.json()["id"]
    item_id = client.get(f"/api/plating/{order_id}/items").json()[0]["id"]

    # Update weight
    update_resp = client.put(f"/api/plating/{order_id}/items/{item_id}", json={
        "weight": 200.0, "weight_unit": "kg",
    })
    assert update_resp.status_code == 200
    assert update_resp.json()["weight"] == 200.0
    assert update_resp.json()["weight_unit"] == "kg"

    # Verify persisted
    item = client.get(f"/api/plating/{order_id}/items").json()[0]
    assert item["weight"] == 200.0
    assert item["weight_unit"] == "kg"


def test_handcraft_part_update_weight(client, db):
    """Handcraft part item weight can be updated via PUT."""
    from models.part import Part
    from services.inventory import add_stock

    part = Part(id="PJ-X-WT6", name="手工更新重量", category="小配件")
    db.add(part)
    db.flush()
    add_stock(db, "part", part.id, 100, "入库")
    db.flush()

    resp = client.post("/api/handcraft/", json={
        "supplier_name": "手工商",
        "parts": [{"part_id": part.id, "qty": 30}],
    })
    order_id = resp.json()["id"]
    item_id = client.get(f"/api/handcraft/{order_id}/parts").json()[0]["id"]

    update_resp = client.put(f"/api/handcraft/{order_id}/parts/{item_id}", json={
        "weight": 3.5, "weight_unit": "kg",
    })
    assert update_resp.status_code == 200
    assert update_resp.json()["weight"] == 3.5
    assert update_resp.json()["weight_unit"] == "kg"


def test_plating_receipt_item_weight(client, db):
    """Plating receipt item stores weight on creation."""
    from models.part import Part
    from services.inventory import add_stock

    part = Part(id="PJ-X-WT7", name="回收单重量", category="小配件")
    db.add(part)
    db.flush()
    add_stock(db, "part", part.id, 100, "入库")
    db.flush()

    # Create plating order and send it
    order_resp = client.post("/api/plating/", json={
        "supplier_name": "电镀商",
        "items": [{"part_id": part.id, "qty": 50}],
    })
    order_id = order_resp.json()["id"]
    client.post(f"/api/plating/{order_id}/send")
    poi_id = client.get(f"/api/plating/{order_id}/items").json()[0]["id"]

    # Create receipt with weight
    receipt_resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "电镀商",
        "items": [{
            "plating_order_item_id": poi_id,
            "part_id": part.id,
            "qty": 30,
            "weight": 75.0,
            "weight_unit": "g",
        }],
    })
    assert receipt_resp.status_code in (200, 201)
    receipt_item = receipt_resp.json()["items"][0]
    assert receipt_item["weight"] == 75.0
    assert receipt_item["weight_unit"] == "g"


def test_plating_receipt_item_update_weight(client, db):
    """Plating receipt item weight can be updated via PUT."""
    from models.part import Part
    from services.inventory import add_stock

    part = Part(id="PJ-X-WT8", name="回收单更新重量", category="小配件")
    db.add(part)
    db.flush()
    add_stock(db, "part", part.id, 100, "入库")
    db.flush()

    # Create plating order and send
    order_resp = client.post("/api/plating/", json={
        "supplier_name": "电镀商",
        "items": [{"part_id": part.id, "qty": 50}],
    })
    order_id = order_resp.json()["id"]
    client.post(f"/api/plating/{order_id}/send")
    poi_id = client.get(f"/api/plating/{order_id}/items").json()[0]["id"]

    # Create receipt without weight
    receipt_resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "电镀商",
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 30}],
    })
    receipt_id = receipt_resp.json()["id"]
    item_id = receipt_resp.json()["items"][0]["id"]

    # Update weight
    update_resp = client.put(f"/api/plating-receipts/{receipt_id}/items/{item_id}", json={
        "weight": 100.0, "weight_unit": "kg",
    })
    assert update_resp.status_code == 200
    updated_item = next(i for i in update_resp.json()["items"] if i["id"] == item_id)
    assert updated_item["weight"] == 100.0
    assert updated_item["weight_unit"] == "kg"


def test_handcraft_receipt_item_weight(client, db):
    """Handcraft receipt item stores weight on creation."""
    from models.part import Part
    from services.inventory import add_stock

    part = Part(id="PJ-X-WT9", name="手工回收重量", category="小配件")
    db.add(part)
    db.flush()
    add_stock(db, "part", part.id, 100, "入库")
    db.flush()

    # Create handcraft order and send
    order_resp = client.post("/api/handcraft/", json={
        "supplier_name": "手工商",
        "parts": [{"part_id": part.id, "qty": 50}],
    })
    order_id = order_resp.json()["id"]
    client.post(f"/api/handcraft/{order_id}/send")
    hpi_id = client.get(f"/api/handcraft/{order_id}/parts").json()[0]["id"]

    # Create receipt with weight
    receipt_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "手工商",
        "items": [{
            "handcraft_part_item_id": hpi_id,
            "qty": 20,
            "weight": 45.0,
            "weight_unit": "g",
        }],
    })
    assert receipt_resp.status_code in (200, 201)
    receipt_item = receipt_resp.json()["items"][0]
    assert receipt_item["weight"] == 45.0
    assert receipt_item["weight_unit"] == "g"


def test_weight_negative_rejected(client, db):
    """Negative weight is rejected by the API."""
    from models.part import Part
    from services.inventory import add_stock

    part = Part(id="PJ-X-WTA", name="负重量测试", category="小配件")
    db.add(part)
    db.flush()
    add_stock(db, "part", part.id, 100, "入库")
    db.flush()

    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀商",
        "items": [{"part_id": part.id, "qty": 50, "weight": -5.0}],
    })
    assert resp.status_code == 422
