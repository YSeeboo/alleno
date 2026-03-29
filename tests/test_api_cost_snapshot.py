import pytest
from decimal import Decimal
from services.jewelry import create_jewelry
from services.part import create_part, update_part_cost
from services.bom import set_bom


def _setup_order_with_cost(db, client):
    """创建有完整成本的订单。"""
    part_a = create_part(db, {"name": "A珠", "category": "小配件"})
    part_b = create_part(db, {"name": "B链", "category": "链条"})
    update_part_cost(db, part_a.id, "purchase_cost", 0.05)
    update_part_cost(db, part_b.id, "purchase_cost", 2.0)

    jewelry = create_jewelry(db, {"name": "项链A", "retail_price": 100.0, "category": "单件"})
    set_bom(db, jewelry.id, part_a.id, 10)    # 10 × 0.05 = 0.5
    set_bom(db, jewelry.id, part_b.id, 1)     # 1 × 2.0 = 2.0
    # 饰品单位成本 = 0.5 + 2.0 = 2.5

    resp = client.post("/api/orders/", json={
        "customer_name": "测试客户",
        "items": [{"jewelry_id": jewelry.id, "quantity": 100, "unit_price": 50.0}],
    })
    assert resp.status_code == 201
    order_id = resp.json()["id"]
    return order_id, part_a, part_b, jewelry


def test_complete_order_generates_snapshot(client, db):
    order_id, _, _, _ = _setup_order_with_cost(db, client)
    resp = client.patch(f"/api/orders/{order_id}/status", json={"status": "已完成"})
    assert resp.status_code == 200

    resp = client.get(f"/api/orders/{order_id}/cost-snapshot")
    assert resp.status_code == 200
    snapshot = resp.json()
    assert snapshot["order_id"] == order_id
    # 总成本 = 2.5 × 100 = 250
    assert pytest.approx(snapshot["total_cost"], abs=0.01) == 250.0
    # 利润 = 5000 - 250 = 4750
    assert pytest.approx(snapshot["profit"], abs=0.01) == 4750.0
    assert len(snapshot["items"]) == 1
    assert len(snapshot["items"][0]["bom_details"]) == 2


def test_complete_order_with_packaging_cost(client, db):
    order_id, _, _, _ = _setup_order_with_cost(db, client)
    client.patch(f"/api/orders/{order_id}/packaging-cost", json={"packaging_cost": 50.0})
    client.patch(f"/api/orders/{order_id}/status", json={"status": "已完成"})

    snapshot = client.get(f"/api/orders/{order_id}/cost-snapshot").json()
    # 总成本 = 250 + 50 = 300
    assert pytest.approx(snapshot["total_cost"], abs=0.01) == 300.0
    assert pytest.approx(snapshot["packaging_cost"], abs=0.01) == 50.0
    assert pytest.approx(snapshot["profit"], abs=0.01) == 4700.0


def test_complete_order_with_handcraft_cost(client, db):
    order_id, _, _, jewelry = _setup_order_with_cost(db, client)
    # 设置饰品手工费
    client.patch(f"/api/jewelries/{jewelry.id}", json={"handcraft_cost": 1.0})

    client.patch(f"/api/orders/{order_id}/status", json={"status": "已完成"})
    snapshot = client.get(f"/api/orders/{order_id}/cost-snapshot").json()
    # 饰品单位成本 = 2.5 + 1.0 = 3.5, 总 = 350
    assert pytest.approx(snapshot["total_cost"], abs=0.01) == 350.0
    item = snapshot["items"][0]
    assert pytest.approx(item["handcraft_cost"], abs=0.01) == 1.0
    assert pytest.approx(item["jewelry_unit_cost"], abs=0.01) == 3.5


def test_complete_order_no_bom_rejected(client, db):
    """没有 BOM 的饰品阻止完成。"""
    jewelry = create_jewelry(db, {"name": "裸饰品", "retail_price": 10.0, "category": "单件"})
    resp = client.post("/api/orders/", json={
        "customer_name": "测试",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10.0}],
    })
    order_id = resp.json()["id"]
    resp = client.patch(f"/api/orders/{order_id}/status", json={"status": "已完成"})
    assert resp.status_code == 400


def test_complete_order_missing_part_cost_marks_incomplete(client, db):
    """配件没有 unit_cost 时标记 has_incomplete_cost。"""
    part = create_part(db, {"name": "无价配件", "category": "小配件"})
    # 不设置 purchase_cost，unit_cost 为 None
    jewelry = create_jewelry(db, {"name": "测试饰品", "retail_price": 10.0, "category": "单件"})
    set_bom(db, jewelry.id, part.id, 1)

    resp = client.post("/api/orders/", json={
        "customer_name": "测试",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10.0}],
    })
    order_id = resp.json()["id"]
    client.patch(f"/api/orders/{order_id}/status", json={"status": "已完成"})

    snapshot = client.get(f"/api/orders/{order_id}/cost-snapshot").json()
    assert snapshot["has_incomplete_cost"] == 1
    assert pytest.approx(snapshot["total_cost"], abs=0.01) == 0.0


def test_snapshot_not_found(client, db):
    """未完成的订单没有快照。"""
    jewelry = create_jewelry(db, {"name": "J", "retail_price": 10.0, "category": "单件"})
    resp = client.post("/api/orders/", json={
        "customer_name": "测试",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10.0}],
    })
    order_id = resp.json()["id"]
    resp = client.get(f"/api/orders/{order_id}/cost-snapshot")
    assert resp.status_code == 404


def test_update_packaging_cost(client, db):
    jewelry = create_jewelry(db, {"name": "J", "retail_price": 10.0, "category": "单件"})
    resp = client.post("/api/orders/", json={
        "customer_name": "测试",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10.0}],
    })
    order_id = resp.json()["id"]
    resp = client.patch(f"/api/orders/{order_id}/packaging-cost", json={"packaging_cost": 25.5})
    assert resp.status_code == 200
    assert pytest.approx(resp.json()["packaging_cost"], abs=0.01) == 25.5


def test_snapshot_preserved_on_status_revert(client, db):
    """退回状态时快照保留。"""
    order_id, _, _, _ = _setup_order_with_cost(db, client)
    client.patch(f"/api/orders/{order_id}/status", json={"status": "已完成"})
    # 退回到已取消
    client.patch(f"/api/orders/{order_id}/status", json={"status": "已取消"})
    # 快照仍然存在
    resp = client.get(f"/api/orders/{order_id}/cost-snapshot")
    assert resp.status_code == 200


def test_cancel_order(client, db):
    """订单可以取消。"""
    jewelry = create_jewelry(db, {"name": "J", "retail_price": 10.0, "category": "单件"})
    resp = client.post("/api/orders/", json={
        "customer_name": "测试",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10.0}],
    })
    order_id = resp.json()["id"]
    resp = client.patch(f"/api/orders/{order_id}/status", json={"status": "已取消"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "已取消"


def test_zero_unit_price_preserved_in_snapshot(client, db):
    """unit_price=0 should be stored as 0, not null."""
    part = create_part(db, {"name": "P", "category": "小配件"})
    update_part_cost(db, part.id, "purchase_cost", 1.0)
    jewelry = create_jewelry(db, {"name": "赠品", "retail_price": 0.0, "category": "单件"})
    set_bom(db, jewelry.id, part.id, 1)

    resp = client.post("/api/orders/", json={
        "customer_name": "测试",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 0.0}],
    })
    order_id = resp.json()["id"]
    client.patch(f"/api/orders/{order_id}/status", json={"status": "已完成"})

    snapshot = client.get(f"/api/orders/{order_id}/cost-snapshot").json()
    assert snapshot["items"][0]["unit_price"] == 0.0  # not None


def test_zero_packaging_cost_preserved_in_snapshot(client, db):
    """packaging_cost=0 should be stored as 0, not null."""
    order_id, _, _, _ = _setup_order_with_cost(db, client)
    client.patch(f"/api/orders/{order_id}/packaging-cost", json={"packaging_cost": 0.0})
    client.patch(f"/api/orders/{order_id}/status", json={"status": "已完成"})

    snapshot = client.get(f"/api/orders/{order_id}/cost-snapshot").json()
    assert snapshot["packaging_cost"] == 0.0  # not None


def test_negative_packaging_cost_rejected(client, db):
    """Negative packaging_cost should be rejected."""
    jewelry = create_jewelry(db, {"name": "J", "retail_price": 10.0, "category": "单件"})
    resp = client.post("/api/orders/", json={
        "customer_name": "测试",
        "items": [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10.0}],
    })
    order_id = resp.json()["id"]
    resp = client.patch(f"/api/orders/{order_id}/packaging-cost", json={"packaging_cost": -100})
    assert resp.status_code == 422
