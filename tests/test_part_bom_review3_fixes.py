"""Tests for third code review: cycle detection + scoped cost_diffs."""
import pytest

from models.part import Part
from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
from services.part_bom import set_part_bom
from services.inventory import add_stock


# ──────────────────────────────────────────────────────────────
# Finding 1 (高危): circular part_bom causes infinite recursion
# ──────────────────────────────────────────────────────────────

def test_circular_bom_rejected(client, db):
    """A -> B -> A cycle must be rejected at set_part_bom time."""
    a = Part(id="PJ-X-CYC-A", name="A", category="小配件")
    b = Part(id="PJ-X-CYC-B", name="B", category="小配件")
    db.add_all([a, b])
    db.flush()

    # A -> B OK
    resp = client.post(f"/api/parts/{a.id}/bom",
                       json={"child_part_id": b.id, "qty_per_unit": 1.0})
    assert resp.status_code == 200

    # B -> A would create cycle, must fail
    resp = client.post(f"/api/parts/{b.id}/bom",
                       json={"child_part_id": a.id, "qty_per_unit": 1.0})
    assert resp.status_code == 400


def test_longer_circular_bom_rejected(client, db):
    """A -> B -> C -> A cycle must be rejected."""
    a = Part(id="PJ-X-CYC3-A", name="A3", category="小配件")
    b = Part(id="PJ-X-CYC3-B", name="B3", category="小配件")
    c = Part(id="PJ-X-CYC3-C", name="C3", category="小配件")
    db.add_all([a, b, c])
    db.flush()

    # A -> B, B -> C: OK
    client.post(f"/api/parts/{a.id}/bom",
                json={"child_part_id": b.id, "qty_per_unit": 1.0})
    client.post(f"/api/parts/{b.id}/bom",
                json={"child_part_id": c.id, "qty_per_unit": 1.0})

    # C -> A would create A -> B -> C -> A cycle
    resp = client.post(f"/api/parts/{c.id}/bom",
                       json={"child_part_id": a.id, "qty_per_unit": 1.0})
    assert resp.status_code == 400


def test_recalc_survives_if_cycle_somehow_exists(db):
    """Even if a cycle exists in DB, recalc should not infinite-loop."""
    from services.part_bom import recalc_part_unit_cost
    from models.part_bom import PartBom
    from services._helpers import _next_id

    a = Part(id="PJ-X-SAFE-A", name="SafeA", category="小配件", unit_cost=10)
    b = Part(id="PJ-X-SAFE-B", name="SafeB", category="小配件", unit_cost=20)
    db.add_all([a, b])
    db.flush()

    # Manually create cycle: A -> B -> A (bypassing validation)
    db.add(PartBom(id=_next_id(db, PartBom, "PB"), parent_part_id=a.id, child_part_id=b.id, qty_per_unit=1))
    db.add(PartBom(id=_next_id(db, PartBom, "PB"), parent_part_id=b.id, child_part_id=a.id, qty_per_unit=1))
    db.flush()

    # Should terminate without RecursionError
    recalc_part_unit_cost(db, a.id)
    # We don't assert exact values — just that it didn't crash


# ──────────────────────────────────────────────────────────────
# Finding 2 (中危): cost_diffs in add-items includes old items
# ──────────────────────────────────────────────────────────────

def test_add_receipt_items_cost_diffs_only_new(client, db):
    """cost_diffs returned by add-items should only reflect new items."""
    parent1 = Part(id="PJ-X-CD1", name="组合件CD1", category="小配件")
    parent2 = Part(id="PJ-X-CD2", name="组合件CD2", category="小配件")
    child1 = Part(id="PJ-X-CDC1", name="子件CD1", category="小配件")
    child2 = Part(id="PJ-X-CDC2", name="子件CD2", category="小配件")
    db.add_all([parent1, parent2, child1, child2])
    db.flush()

    child1.unit_cost = 10.0
    child2.unit_cost = 10.0
    db.flush()

    set_part_bom(db, parent1.id, child1.id, 1.0)
    set_part_bom(db, parent2.id, child2.id, 1.0)
    db.flush()

    # Create handcraft order
    hc = HandcraftOrder(id="HC-CDIFF1", supplier_name="手工商CD", status="processing")
    db.add(hc)
    db.flush()

    hp1 = HandcraftPartItem(handcraft_order_id=hc.id, part_id=child1.id, qty=10, status="制作中")
    hp2 = HandcraftPartItem(handcraft_order_id=hc.id, part_id=child2.id, qty=10, status="制作中")
    hj1 = HandcraftJewelryItem(handcraft_order_id=hc.id, part_id=parent1.id, qty=5, status="制作中")
    hj2 = HandcraftJewelryItem(handcraft_order_id=hc.id, part_id=parent2.id, qty=5, status="制作中")
    db.add_all([hp1, hp2, hj1, hj2])
    db.flush()

    # Create receipt with parent1 at price=3.0
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "手工商CD",
        "items": [{
            "handcraft_jewelry_item_id": hj1.id,
            "qty": 5,
            "price": 3.0,
        }],
    })
    assert resp.status_code == 201
    receipt_id = resp.json()["id"]

    # Now externally change parent1's assembly_cost
    parent1.assembly_cost = 99.0
    db.flush()

    # Add parent2 to the same receipt
    resp2 = client.post(f"/api/handcraft-receipts/{receipt_id}/items", json={
        "items": [{
            "handcraft_jewelry_item_id": hj2.id,
            "qty": 5,
            "price": 4.0,
        }],
    })
    assert resp2.status_code == 201
    data = resp2.json()

    # cost_diffs should only mention parent2 (the new item), not parent1
    diff_part_ids = [d["part_id"] for d in data.get("cost_diffs", [])]
    assert parent2.id in diff_part_ids or len(diff_part_ids) == 0  # parent2 may or may not diff
    assert parent1.id not in diff_part_ids  # parent1 must NOT appear
