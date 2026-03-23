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
    jew = create_jewelry(db, {"name": "J1", "category": "项链"})
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
