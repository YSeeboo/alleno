"""Tests for handcraft picking weight service + endpoints.

Domain: per-atom weight tracking for handcraft picking.
"""

from decimal import Decimal

from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftPickingWeight
from models.part import Part as PartModel
from services.handcraft_picking_weight import (
    upsert_weight, delete_weight, sum_weight_by_part_item, bulk_load_for_picking,
)


def _seed_atomic(db, order_id="HC-WT01", part_id="PJ-X-WT01", qty=200, bom_qty=200):
    db.add(PartModel(id=part_id, name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id=order_id, supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id=order_id, part_id=part_id, qty=qty, bom_qty=bom_qty)
    db.add(pi); db.flush()
    return order_id, pi


def test_upsert_weight_inserts_new_row(db):
    order_id, pi = _seed_atomic(db)
    row = upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")
    assert row.weight == Decimal("0.5000")
    assert row.weight_unit == "kg"


def test_upsert_weight_updates_existing(db):
    order_id, pi = _seed_atomic(db)
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.7, "kg")
    rows = db.query(HandcraftPickingWeight).filter_by(part_item_id=pi.id).all()
    assert len(rows) == 1
    assert rows[0].weight == Decimal("0.7000")


def test_upsert_weight_rejects_part_item_outside_order(db):
    _, pi = _seed_atomic(db, order_id="HC-WT02")
    db.add(HandcraftOrder(id="HC-OTHER", supplier_name="S", status="pending"))
    db.flush()
    import pytest
    with pytest.raises(ValueError, match="不属于"):
        upsert_weight(db, "HC-OTHER", pi.id, "PJ-X-WT01", 0.5, "kg")


def test_upsert_weight_rejects_bad_atom_part_id(db):
    order_id, pi = _seed_atomic(db, order_id="HC-WT03")
    import pytest
    with pytest.raises(ValueError, match="配件 .* 不存在"):
        upsert_weight(db, order_id, pi.id, "PJ-NOPE", 0.5, "kg")


def test_delete_weight(db):
    order_id, pi = _seed_atomic(db, order_id="HC-WT04")
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")
    assert delete_weight(db, pi.id, "PJ-X-WT01") is True
    assert delete_weight(db, pi.id, "PJ-X-WT01") is False


def test_sum_weight_handles_mixed_units(db):
    order_id, pi = _seed_atomic(db, order_id="HC-WT05")
    db.add(PartModel(id="PJ-X-WTB", name="扣环", category="小配件", size_tier="small"))
    db.flush()
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")     # 500 g
    upsert_weight(db, order_id, pi.id, "PJ-X-WTB", 300, "g")       # 300 g
    total_kg = sum_weight_by_part_item(db, pi.id, target_unit="kg")
    assert abs(total_kg - 0.8) < 1e-6


def test_sum_weight_returns_none_when_no_rows(db):
    _, pi = _seed_atomic(db, order_id="HC-WT06")
    assert sum_weight_by_part_item(db, pi.id) is None


def test_bulk_load_returns_keyed_dict(db):
    order_id, pi = _seed_atomic(db, order_id="HC-WT07")
    db.add(PartModel(id="PJ-X-WTB", name="扣环", category="小配件", size_tier="small"))
    db.flush()
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")
    upsert_weight(db, order_id, pi.id, "PJ-X-WTB", 0.3, "kg")
    loaded = bulk_load_for_picking(db, order_id)
    assert (pi.id, "PJ-X-WT01") in loaded
    assert (pi.id, "PJ-X-WTB") in loaded
    assert float(loaded[(pi.id, "PJ-X-WT01")].weight) == 0.5
