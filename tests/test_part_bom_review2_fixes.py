"""Tests for second code review findings on part sub-assembly cost calculation."""
import pytest

from models.part import Part
from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
from services.part_bom import set_part_bom
from services.inventory import add_stock, get_stock


# ──────────────────────────────────────────────────────────────
# Finding 1 (高危): multi-level part_bom cost propagation
# ──────────────────────────────────────────────────────────────

def test_multilevel_cost_propagation(client, db):
    """Cost changes in a grandchild should propagate through all ancestor levels.

    Setup: A -> B -> C (A uses B, B uses C)
    When C's cost changes, both B and A should be recalculated.
    """
    part_c = Part(id="PJ-X-LV-C", name="底层配件C", category="小配件")
    part_b = Part(id="PJ-X-LV-B", name="中间配件B", category="小配件")
    part_a = Part(id="PJ-X-LV-A", name="顶层配件A", category="小配件")
    db.add_all([part_c, part_b, part_a])
    db.flush()

    # C costs 10
    part_c.unit_cost = 10.0
    db.flush()

    # B = 2*C = 20
    set_part_bom(db, part_b.id, part_c.id, 2.0)
    db.refresh(part_b)
    assert float(part_b.unit_cost) == 20.0

    # A = 3*B = 60
    set_part_bom(db, part_a.id, part_b.id, 3.0)
    db.refresh(part_a)
    assert float(part_a.unit_cost) == 60.0

    # Now update C's cost to 15 via cost update
    from services.part import update_part_cost
    update_part_cost(db, part_c.id, "purchase_cost", 15.0)

    # B should be 2*15 = 30
    db.refresh(part_b)
    assert float(part_b.unit_cost) == 30.0

    # A should be 3*30 = 90 (not stuck at 60)
    db.refresh(part_a)
    assert float(part_a.unit_cost) == 90.0


def test_multilevel_assembly_cost_propagation(client, db):
    """assembly_cost change on mid-level part should propagate to top-level."""
    part_c = Part(id="PJ-X-AC-C", name="底层C", category="小配件")
    part_b = Part(id="PJ-X-AC-B", name="中间B", category="小配件")
    part_a = Part(id="PJ-X-AC-A", name="顶层A", category="小配件")
    db.add_all([part_c, part_b, part_a])
    db.flush()

    part_c.unit_cost = 10.0
    db.flush()

    set_part_bom(db, part_b.id, part_c.id, 1.0)  # B = C + assembly
    set_part_bom(db, part_a.id, part_b.id, 1.0)  # A = B

    db.refresh(part_b)
    assert float(part_b.unit_cost) == 10.0
    db.refresh(part_a)
    assert float(part_a.unit_cost) == 10.0

    # Set assembly_cost on B
    resp = client.patch(f"/api/parts/{part_b.id}", json={"assembly_cost": 5.0})
    assert resp.status_code == 200

    db.refresh(part_b)
    assert float(part_b.unit_cost) == 15.0  # 10 + 5

    # A should reflect B's new unit_cost
    db.refresh(part_a)
    assert float(part_a.unit_cost) == 15.0  # 1 * 15


# ──────────────────────────────────────────────────────────────
# Finding 2 (中危): deleting last BOM row leaves stale unit_cost
# ──────────────────────────────────────────────────────────────

def test_delete_last_bom_reverts_to_manual_cost(client, db):
    """After deleting all part_bom rows, unit_cost should revert to
    the standard _recalc_unit_cost (purchase + bead + plating)."""
    parent = Part(id="PJ-X-DELLAST", name="组合件", category="小配件")
    child = Part(id="PJ-X-DELLAST-C", name="子件", category="小配件")
    db.add_all([parent, child])
    db.flush()

    # Set manual cost fields on parent
    parent.purchase_cost = 3.0
    parent.plating_cost = 2.0
    child.unit_cost = 10.0
    db.flush()

    # Before BOM: unit_cost should be purchase + plating = 5
    from services.part import _recalc_unit_cost
    _recalc_unit_cost(parent)
    db.flush()
    db.refresh(parent)
    assert float(parent.unit_cost) == 5.0

    # Add BOM: unit_cost becomes 10*2 = 20 (BOM overrides manual)
    resp = client.post(f"/api/parts/{parent.id}/bom",
                       json={"child_part_id": child.id, "qty_per_unit": 2.0})
    bom_id = resp.json()["id"]
    db.refresh(parent)
    assert float(parent.unit_cost) == 20.0

    # Delete the only BOM row: should revert to manual cost = 5
    client.delete(f"/api/parts/bom/{bom_id}")
    db.refresh(parent)
    assert float(parent.unit_cost) == 5.0


# ──────────────────────────────────────────────────────────────
# Finding 3 (中危): adding items to receipt re-syncs all old prices
# ──────────────────────────────────────────────────────────────

def test_add_receipt_items_does_not_resync_old_prices(client, db):
    """Adding items to an existing receipt should only sync costs for
    newly added items, not replay old items."""
    parent1 = Part(id="PJ-X-RS1", name="组合件1", category="小配件")
    parent2 = Part(id="PJ-X-RS2", name="组合件2", category="小配件")
    child1 = Part(id="PJ-X-RSC1", name="子件1", category="小配件")
    child2 = Part(id="PJ-X-RSC2", name="子件2", category="小配件")
    db.add_all([parent1, parent2, child1, child2])
    db.flush()

    child1.unit_cost = 10.0
    child2.unit_cost = 10.0
    db.flush()

    set_part_bom(db, parent1.id, child1.id, 1.0)
    set_part_bom(db, parent2.id, child2.id, 1.0)
    db.flush()

    # Create processing handcraft order with both parents as outputs
    hc = HandcraftOrder(id="HC-RESYNC1", supplier_name="手工商RS", status="processing")
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
        "supplier_name": "手工商RS",
        "items": [{
            "handcraft_jewelry_item_id": hj1.id,
            "qty": 5,
            "price": 3.0,
        }],
    })
    assert resp.status_code == 201
    receipt_id = resp.json()["id"]

    db.refresh(parent1)
    assert float(parent1.assembly_cost) == 3.0

    # Now externally update parent1's assembly_cost to 7.0 (e.g. from a newer receipt)
    parent1.assembly_cost = 7.0
    db.flush()

    # Add parent2 to the same receipt at price=4.0
    resp2 = client.post(f"/api/handcraft-receipts/{receipt_id}/items", json={
        "items": [{
            "handcraft_jewelry_item_id": hj2.id,
            "qty": 5,
            "price": 4.0,
        }],
    })
    assert resp2.status_code == 201

    # parent2 should get assembly_cost=4.0
    db.refresh(parent2)
    assert float(parent2.assembly_cost) == 4.0

    # parent1 should NOT be reverted to 3.0 — it should stay at 7.0
    db.refresh(parent1)
    assert float(parent1.assembly_cost) == 7.0
