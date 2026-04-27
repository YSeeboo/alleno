import pytest
from services.part import create_part


def test_add_stock(client, db):
    part = create_part(db, {"name": "P1", "category": "小配件"})
    resp = client.post(f"/api/inventory/part/{part.id}/add", json={"qty": 10, "reason": "initial"})
    assert resp.status_code == 200


def test_get_stock(client, db):
    part = create_part(db, {"name": "P1", "category": "小配件"})
    client.post(f"/api/inventory/part/{part.id}/add", json={"qty": 5, "reason": "入库"})
    resp = client.get(f"/api/inventory/part/{part.id}")
    assert resp.status_code == 200
    assert resp.json()["current"] == 5


def test_deduct_stock(client, db):
    part = create_part(db, {"name": "P1", "category": "小配件"})
    client.post(f"/api/inventory/part/{part.id}/add", json={"qty": 10, "reason": "入库"})
    resp = client.post(f"/api/inventory/part/{part.id}/deduct", json={"qty": 3, "reason": "出库"})
    assert resp.status_code == 200
    assert resp.json()["current"] == 7


def test_deduct_insufficient(client, db):
    part = create_part(db, {"name": "P1", "category": "小配件"})
    resp = client.post(f"/api/inventory/part/{part.id}/deduct", json={"qty": 5, "reason": "出库"})
    assert resp.status_code == 400


def test_list_logs_default(client, db):
    """GET /api/inventory/logs returns all logs by default."""
    p1 = create_part(db, {"name": "A", "category": "小配件"})
    p2 = create_part(db, {"name": "B", "category": "链条"})
    client.post(f"/api/inventory/part/{p1.id}/add", json={"qty": 5, "reason": "入库"})
    client.post(f"/api/inventory/part/{p2.id}/add", json={"qty": 3, "reason": "采购"})
    resp = client.get("/api/inventory/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    # most recent first
    assert data["items"][0]["item_id"] == p2.id


def test_list_logs_filter_item_type(client, db):
    from services.jewelry import create_jewelry
    part = create_part(db, {"name": "A", "category": "小配件"})
    jew = create_jewelry(db, {"name": "J1", "category": "单件"})
    client.post(f"/api/inventory/part/{part.id}/add", json={"qty": 5, "reason": "入库"})
    client.post(f"/api/inventory/jewelry/{jew.id}/add", json={"qty": 2, "reason": "入库"})
    resp = client.get("/api/inventory/logs", params={"item_type": "jewelry"})
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["item_type"] == "jewelry"


def test_list_logs_filter_item_id_fuzzy(client, db):
    """Partial item_id match should work (ilike)."""
    p1 = create_part(db, {"name": "A", "category": "小配件"})
    p2 = create_part(db, {"name": "B", "category": "链条"})
    client.post(f"/api/inventory/part/{p1.id}/add", json={"qty": 5, "reason": "入库"})
    client.post(f"/api/inventory/part/{p2.id}/add", json={"qty": 3, "reason": "入库"})
    # Use partial prefix "PJ-X" to match only 小配件 part (PJ-X-xxxxx)
    resp = client.get("/api/inventory/logs", params={"item_id": "PJ-X"})
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["item_id"] == p1.id


def test_list_logs_filter_reason_fuzzy(client, db):
    """Partial reason match should work (ilike)."""
    part = create_part(db, {"name": "A", "category": "小配件"})
    client.post(f"/api/inventory/part/{part.id}/add", json={"qty": 5, "reason": "采购入库"})
    client.post(f"/api/inventory/part/{part.id}/deduct", json={"qty": 2, "reason": "订单出库"})
    # Partial match "采购" should only match "采购入库"
    resp = client.get("/api/inventory/logs", params={"reason": "采购"})
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["reason"] == "采购入库"


def test_list_logs_pagination(client, db):
    part = create_part(db, {"name": "A", "category": "小配件"})
    for i in range(5):
        client.post(f"/api/inventory/part/{part.id}/add", json={"qty": 1, "reason": f"r{i}"})
    # Page 1: newest 2 records (r4, r3)
    resp = client.get("/api/inventory/logs", params={"limit": 2, "offset": 0})
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    reasons_page1 = [it["reason"] for it in data["items"]]
    assert reasons_page1 == ["r4", "r3"]
    # Offset 4: only the oldest record (r0)
    resp2 = client.get("/api/inventory/logs", params={"limit": 2, "offset": 4})
    data2 = resp2.json()
    assert len(data2["items"]) == 1
    assert data2["items"][0]["reason"] == "r0"


def test_list_logs_filter_name_matches_part(client, db):
    """name filter hits parts by name (fuzzy, multi-keyword AND)."""
    p1 = create_part(db, {"name": "红色圆珠吊坠", "category": "吊坠"})
    p2 = create_part(db, {"name": "蓝色方块", "category": "小配件"})
    client.post(f"/api/inventory/part/{p1.id}/add", json={"qty": 5, "reason": "入库"})
    client.post(f"/api/inventory/part/{p2.id}/add", json={"qty": 3, "reason": "入库"})
    # Single keyword
    resp = client.get("/api/inventory/logs", params={"name": "红色"})
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["item_id"] == p1.id
    # Multi-keyword AND: both "红色" and "圆珠" must match
    resp2 = client.get("/api/inventory/logs", params={"name": "红色 圆珠"})
    assert resp2.json()["total"] == 1
    assert resp2.json()["items"][0]["item_id"] == p1.id
    # Multi-keyword AND with no match
    resp3 = client.get("/api/inventory/logs", params={"name": "红色 方块"})
    assert resp3.json()["total"] == 0


def test_list_logs_filter_name_also_matches_part_id(client, db):
    """name filter reuses list_parts logic — matches both Part.name and Part.id."""
    part = create_part(db, {"name": "项链", "category": "链条"})
    client.post(f"/api/inventory/part/{part.id}/add", json={"qty": 5, "reason": "入库"})
    # Partial match against generated part id (PJ-LT-00001 contains "LT")
    resp = client.get("/api/inventory/logs", params={"name": "LT"})
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["item_id"] == part.id


def test_list_logs_filter_name_excludes_jewelry(client, db):
    """name filter is scoped to parts — jewelry logs with matching names are excluded."""
    from services.jewelry import create_jewelry
    part = create_part(db, {"name": "红色配件", "category": "小配件"})
    jew = create_jewelry(db, {"name": "红色饰品", "category": "单件"})
    client.post(f"/api/inventory/part/{part.id}/add", json={"qty": 5, "reason": "入库"})
    client.post(f"/api/inventory/jewelry/{jew.id}/add", json={"qty": 2, "reason": "入库"})
    resp = client.get("/api/inventory/logs", params={"name": "红色"})
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["item_type"] == "part"
    assert data["items"][0]["item_id"] == part.id


def test_list_logs_enriches_item_name_and_image(client, db):
    """Response includes item_name / item_image for both part and jewelry rows."""
    from services.jewelry import create_jewelry
    part = create_part(db, {"name": "金色链条", "category": "链条", "image": "http://img/part.jpg"})
    jew = create_jewelry(db, {"name": "珍珠项链", "category": "单件", "image": "http://img/jew.jpg"})
    client.post(f"/api/inventory/part/{part.id}/add", json={"qty": 5, "reason": "入库"})
    client.post(f"/api/inventory/jewelry/{jew.id}/add", json={"qty": 2, "reason": "入库"})
    resp = client.get("/api/inventory/logs")
    items = {it["item_id"]: it for it in resp.json()["items"]}
    assert items[part.id]["item_name"] == "金色链条"
    assert items[part.id]["item_image"] == "http://img/part.jpg"
    assert items[jew.id]["item_name"] == "珍珠项链"
    assert items[jew.id]["item_image"] == "http://img/jew.jpg"
