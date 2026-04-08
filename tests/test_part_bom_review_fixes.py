"""Tests for code review findings on part sub-assembly feature."""
import pytest

from models.part import Part
from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
from services.part_bom import set_part_bom
from services.inventory import add_stock, get_stock


# ──────────────────────────────────────────────────────────────
# Finding 1 (高危): delete handcraft order with part output
#   reverses stock using wrong item type
# ──────────────────────────────────────────────────────────────

def test_delete_handcraft_order_with_received_part_output(client, db):
    """Deleting a handcraft order that has received part output
    should correctly reverse 'part' stock, not 'jewelry' stock."""
    parent = Part(id="PJ-X-DEL1", name="组合配件D", category="小配件")
    child1 = Part(id="PJ-X-DC1", name="子配件D1", category="小配件")
    db.add_all([parent, child1])
    db.flush()

    set_part_bom(db, parent.id, child1.id, 2.0)
    db.flush()

    # Stock child parts for sending
    add_stock(db, "part", child1.id, 100, "入库")
    db.flush()

    # Create and send handcraft order
    hc = HandcraftOrder(id="HC-DEL-PO1", supplier_name="手工商D", status="pending")
    db.add(hc)
    db.flush()

    hp1 = HandcraftPartItem(handcraft_order_id=hc.id, part_id=child1.id, qty=20, status="未送出")
    hj = HandcraftJewelryItem(handcraft_order_id=hc.id, part_id=parent.id, qty=10, status="未送出")
    db.add_all([hp1, hj])
    db.flush()

    # Send order (deducts child stock)
    resp = client.post(f"/api/handcraft/{hc.id}/send")
    assert resp.status_code == 200

    child1_stock_after_send = get_stock(db, "part", child1.id)
    assert child1_stock_after_send == 80  # 100 - 20

    # Receive part output via receipt
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "手工商D",
        "items": [{
            "handcraft_jewelry_item_id": hj.id,
            "qty": 10,
            "price": 1.0,
        }],
    })
    assert resp.status_code == 201

    parent_stock = get_stock(db, "part", parent.id)
    assert parent_stock == 10

    # Delete the handcraft order — this should reverse everything correctly
    resp = client.delete(f"/api/handcraft/{hc.id}")
    assert resp.status_code == 204

    # Parent part stock should be back to 0 (receipt reversed)
    assert get_stock(db, "part", parent.id) == 0
    # Child part stock should be back to 100 (send reversed)
    assert get_stock(db, "part", child1.id) == 100


# ──────────────────────────────────────────────────────────────
# Finding 2 (中危): schema validation for jewelry_id / part_id
# ──────────────────────────────────────────────────────────────

def test_handcraft_output_item_neither_id_rejected():
    """HandcraftJewelryIn rejects when neither jewelry_id nor part_id is set."""
    from schemas.handcraft import HandcraftJewelryIn
    with pytest.raises(Exception):  # ValidationError
        HandcraftJewelryIn(qty=1)


def test_handcraft_output_item_both_ids_rejected():
    """HandcraftJewelryIn rejects when both jewelry_id and part_id are set."""
    from schemas.handcraft import HandcraftJewelryIn
    with pytest.raises(Exception):  # ValidationError
        HandcraftJewelryIn(jewelry_id="SP-0001", part_id="PJ-X-0001", qty=1)


def test_service_rejects_both_ids(db):
    """Service layer rejects output item with both jewelry_id and part_id."""
    from models.jewelry import Jewelry
    j = Jewelry(id="SP-BOTH1", name="测试饰品", category="单件")
    p = Part(id="PJ-X-BOTH1", name="测试配件", category="小配件")
    db.add_all([j, p])
    db.flush()
    add_stock(db, "part", p.id, 100, "入库")
    db.flush()

    from services.handcraft import create_handcraft_order
    with pytest.raises(ValueError, match="不能同时"):
        create_handcraft_order(
            db,
            supplier_name="测试",
            parts=[{"part_id": p.id, "qty": 10}],
            jewelries=[{"jewelry_id": j.id, "part_id": p.id, "qty": 5}],
        )


# ──────────────────────────────────────────────────────────────
# Finding 3 (中危): PartBomSet allows qty_per_unit <= 0
# ──────────────────────────────────────────────────────────────

def test_part_bom_zero_qty_rejected():
    """PartBomSet rejects qty_per_unit of 0."""
    from schemas.part_bom import PartBomSet
    with pytest.raises(Exception):
        PartBomSet(child_part_id="PJ-X-0001", qty_per_unit=0)


def test_part_bom_negative_qty_rejected():
    """PartBomSet rejects negative qty_per_unit."""
    from schemas.part_bom import PartBomSet
    with pytest.raises(Exception):
        PartBomSet(child_part_id="PJ-X-0001", qty_per_unit=-1)


def test_part_bom_api_zero_qty_rejected(client, db):
    """API rejects zero qty_per_unit."""
    parent = Part(id="PJ-X-ZQ1", name="Parent", category="小配件")
    child = Part(id="PJ-X-ZQ2", name="Child", category="小配件")
    db.add_all([parent, child])
    db.flush()
    resp = client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": child.id, "qty_per_unit": 0},
    )
    assert resp.status_code == 422
