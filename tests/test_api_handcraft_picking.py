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


def test_get_picking_atomic_zero_stock(client, db):
    """Part with no inventory_log entries shows current_stock=0."""
    _add_atomic_part(db, "PJ-X-NOSTOCK", "无库存件", "small")
    db.add(HandcraftOrder(id="HC-NOSTOCK", supplier_name="商家", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-NOSTOCK",
        part_id="PJ-X-NOSTOCK",
        qty=Decimal("3"),
        bom_qty=None,
    ))
    db.flush()
    body = client.get("/api/handcraft/HC-NOSTOCK/picking").json()
    assert body["groups"][0]["rows"][0]["current_stock"] == 0.0


def _setup_composite(db):
    """1 composite part C with two atom children A(qty=2) and B(qty=3),
    1 handcraft order with 1 part_item of C (qty=5)."""
    db.add(Part(id="PJ-X-00001", name="珠子A", category="吊坠", size_tier="small"))
    db.add(Part(id="PJ-X-00002", name="珠子B", category="吊坠", size_tier="medium"))
    db.add(Part(id="PJ-X-00003", name="组合件C", category="吊坠",
                size_tier="small", is_composite=True))
    db.flush()
    db.add(PartBom(id="PB-1", parent_part_id="PJ-X-00003",
                   child_part_id="PJ-X-00001", qty_per_unit=Decimal("2")))
    db.add(PartBom(id="PB-2", parent_part_id="PJ-X-00003",
                   child_part_id="PJ-X-00002", qty_per_unit=Decimal("3")))
    db.flush()
    _add_inventory(db, "PJ-X-00001", 50)
    _add_inventory(db, "PJ-X-00002", 30)
    db.add(HandcraftOrder(id="HC-COMP", supplier_name="商家", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-COMP",
        part_id="PJ-X-00003",
        qty=Decimal("5"),
        bom_qty=Decimal("5"),
    ))
    db.flush()


def test_get_picking_composite_expands_to_atoms(client, db):
    _setup_composite(db)
    resp = client.get("/api/handcraft/HC-COMP/picking")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["groups"]) == 1
    g = body["groups"][0]
    assert g["parent_is_composite"] is True
    assert g["parent_part_id"] == "PJ-X-00003"
    rows = sorted(g["rows"], key=lambda r: r["part_id"])
    assert len(rows) == 2
    assert rows[0]["part_id"] == "PJ-X-00001"
    assert rows[0]["needed_qty"] == 10.0  # 5 × 2
    assert rows[1]["part_id"] == "PJ-X-00002"
    assert rows[1]["needed_qty"] == 15.0  # 5 × 3
    assert body["progress"] == {"total": 2, "picked": 0}


def test_get_picking_mixed_atomic_and_composite(client, db):
    """Two part_items: one composite, one atomic referencing the same atom.
    Each part_item gets its own group (rule A: 每行独立)."""
    _setup_composite(db)
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-COMP",
        part_id="PJ-X-00001",
        qty=Decimal("8"),
        bom_qty=Decimal("7.5"),
    ))
    db.flush()
    body = client.get("/api/handcraft/HC-COMP/picking").json()
    assert len(body["groups"]) == 2
    atomic_groups = [g for g in body["groups"] if not g["parent_is_composite"]]
    assert len(atomic_groups) == 1
    assert atomic_groups[0]["rows"][0]["part_id"] == "PJ-X-00001"
    assert atomic_groups[0]["rows"][0]["needed_qty"] == 8.0


def test_get_picking_composite_multipath_sums(db, client):
    """If composite C contains atom A twice via different sub-children, the
    expansion sums those contributions into one row."""
    db.add(Part(id="PJ-X-00001", name="A", category="吊坠", size_tier="small"))
    db.add(Part(id="PJ-X-MID1", name="组合件D", category="吊坠",
                size_tier="small", is_composite=True))
    db.add(Part(id="PJ-X-MID2", name="组合件E", category="吊坠",
                size_tier="small", is_composite=True))
    db.add(Part(id="PJ-X-ROOT", name="组合件 F", category="吊坠",
                size_tier="small", is_composite=True))
    db.flush()
    # F → D (×2), F → E (×1)
    db.add(PartBom(id="PB-1", parent_part_id="PJ-X-ROOT",
                   child_part_id="PJ-X-MID1", qty_per_unit=Decimal("2")))
    db.add(PartBom(id="PB-2", parent_part_id="PJ-X-ROOT",
                   child_part_id="PJ-X-MID2", qty_per_unit=Decimal("1")))
    # D → A (×3), E → A (×4)  → expanding F: A = 2×3 + 1×4 = 10 per unit
    db.add(PartBom(id="PB-3", parent_part_id="PJ-X-MID1",
                   child_part_id="PJ-X-00001", qty_per_unit=Decimal("3")))
    db.add(PartBom(id="PB-4", parent_part_id="PJ-X-MID2",
                   child_part_id="PJ-X-00001", qty_per_unit=Decimal("4")))
    db.flush()
    db.add(HandcraftOrder(id="HC-MP", supplier_name="商家", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-MP",
        part_id="PJ-X-ROOT",
        qty=Decimal("5"),
        bom_qty=Decimal("5"),
    ))
    db.flush()
    body = client.get("/api/handcraft/HC-MP/picking").json()
    assert len(body["groups"]) == 1
    g = body["groups"][0]
    assert len(g["rows"]) == 1
    assert g["rows"][0]["part_id"] == "PJ-X-00001"
    assert g["rows"][0]["needed_qty"] == 50.0  # 5 × (2×3 + 1×4) = 50


def test_suggested_qty_atomic_small(client, db):
    """small tier: max(50, theo*2%); suggested = ceil(theo) + ceil(buffer).
    theo=8, ratio_calc=0.16, floor=50 wins. suggested = 8 + 50 = 58."""
    _setup_atomic(db)
    body = client.get("/api/handcraft/HC-TEST-1/picking").json()
    row = body["groups"][0]["rows"][0]
    assert row["suggested_qty"] == 58


def test_suggested_qty_atomic_medium(client, db):
    """medium tier: max(15, theo*1%); suggested = ceil(theo) + ceil(buffer).
    theo=2000, ratio_calc=20.0, ratio wins. suggested = 2000 + 20 = 2020."""
    db.add(Part(id="PJ-X-MED", name="珠子M", category="吊坠", size_tier="medium"))
    db.flush()
    db.add(HandcraftOrder(id="HC-M", supplier_name="商家", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-M",
        part_id="PJ-X-MED",
        qty=Decimal("1500"),
        bom_qty=Decimal("2000"),
    ))
    db.flush()
    body = client.get("/api/handcraft/HC-M/picking").json()
    row = body["groups"][0]["rows"][0]
    assert row["suggested_qty"] == 2020


def test_suggested_qty_none_when_bom_qty_missing(client, db):
    """If part_item.bom_qty is None or 0, suggested_qty is None."""
    _add_atomic_part(db, "PJ-X-NA", "无理论", "small")
    db.add(HandcraftOrder(id="HC-NA", supplier_name="商家", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-NA",
        part_id="PJ-X-NA",
        qty=Decimal("5"),
        bom_qty=None,
    ))
    db.flush()
    body = client.get("/api/handcraft/HC-NA/picking").json()
    assert body["groups"][0]["rows"][0]["suggested_qty"] is None


def test_suggested_qty_composite_uses_atom_tier(client, db):
    """Composite parent has bom_qty=5; expansion gives atom A theoretical
    = 5×2 = 10. A is small-tier → max(50, 10*2%) = 50 → suggested = 10 + 50 = 60.
    Atom B theoretical = 5×3 = 15, medium-tier → max(15, 15*1%) = 15 → 15 + 15 = 30."""
    _setup_composite(db)
    body = client.get("/api/handcraft/HC-COMP/picking").json()
    rows = sorted(body["groups"][0]["rows"], key=lambda r: r["part_id"])
    assert rows[0]["part_id"] == "PJ-X-00001"
    assert rows[0]["suggested_qty"] == 60
    assert rows[1]["part_id"] == "PJ-X-00002"
    assert rows[1]["suggested_qty"] == 30
