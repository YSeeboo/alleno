"""API + service tests for /api/handcraft/{id}/picking/... endpoints.

Note: these tests use the API client to hit FastAPI; service-layer logic is
exercised through the routes. The test DB fixture in conftest.py truncates
all tables between tests."""

from decimal import Decimal

from models.handcraft_order import (
    HandcraftOrder,
    HandcraftPartItem,
    HandcraftPickingRecord,
)
from models.inventory_log import InventoryLog
from models.part import Part
from models.part_bom import PartBom


def _add_atomic_part(db, pid="PJ-X-00001", name="珠子", tier="small"):
    db.add(Part(id=pid, name=name, category="吊坠", size_tier=tier))


def _add_inventory(db, pid, qty, reason="期初"):
    db.add(InventoryLog(
        item_type="part", item_id=pid, change_qty=Decimal(str(qty)), reason=reason,
    ))


def _setup_atomic(db):
    """1 atomic part with stock, 1 handcraft order with 1 part_item."""
    _add_atomic_part(db, "PJ-X-00001", "珠子A", "small")
    _add_inventory(db, "PJ-X-00001", 50)
    db.add(HandcraftOrder(id="HC-TEST-1", supplier_name="商家A", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-TEST-1",
        part_id="PJ-X-00001",
        qty=Decimal("10"),
        bom_qty=Decimal("8"),
    ))
    db.flush()


def test_get_picking_order_not_found(client, db):
    resp = client.get("/api/handcraft/HC-NOPE/picking")
    assert resp.status_code == 400
    assert "HC-NOPE" in resp.json()["detail"]


def test_get_picking_empty_order(client, db):
    db.add(HandcraftOrder(id="HC-EMPTY", supplier_name="商家", status="pending"))
    db.flush()
    resp = client.get("/api/handcraft/HC-EMPTY/picking")
    assert resp.status_code == 200
    body = resp.json()
    assert body["handcraft_order_id"] == "HC-EMPTY"
    assert body["supplier_name"] == "商家"
    assert body["status"] == "pending"
    assert body["groups"] == []
    assert body["progress"] == {"total": 0, "picked": 0}


def test_get_picking_atomic_single_item(client, db):
    _setup_atomic(db)
    resp = client.get("/api/handcraft/HC-TEST-1/picking")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert len(body["groups"]) == 1
    g = body["groups"][0]
    assert g["parent_part_id"] == "PJ-X-00001"
    assert g["parent_is_composite"] is False
    assert g["parent_qty"] == 10.0
    assert g["parent_bom_qty"] == 8.0
    assert len(g["rows"]) == 1
    row = g["rows"][0]
    assert row["part_id"] == "PJ-X-00001"
    assert row["part_name"] == "珠子A"
    assert row["needed_qty"] == 10.0
    assert row["current_stock"] == 50.0
    assert row["picked"] is False
    assert body["progress"] == {"total": 1, "picked": 0}
