"""Service + API tests for handcraft 合并相同 part_id 的 part_item 行.

See docs/superpowers/specs/2026-05-30-handcraft-merge-duplicate-part-items-design.md.
Service-layer tests use the `db` fixture (truncates between tests).
API tests use the `client` fixture (overrides auth, shared session)."""

from decimal import Decimal

import pytest

from models.handcraft_order import (
    HandcraftOrder,
    HandcraftPartItem,
    HandcraftPickingRecord,
    HandcraftPickingWeight,
)
from models.part import Part
from services.handcraft import merge_duplicate_part_items


def _seed_part(db, part_id="PJ-X-LK", *, is_composite=False):
    db.add(Part(
        id=part_id, name="龙虾扣", category="小配件",
        size_tier="small", is_composite=is_composite,
    ))


def _seed_order(db, order_id="HC-M1", status="pending"):
    db.add(HandcraftOrder(id=order_id, supplier_name="S", status=status))


def test_merge_two_duplicate_part_items_returns_summary(db):
    """Happy path: 2 rows qty 100/200 → 1 row qty 300; survivor is smallest id."""
    _seed_part(db)
    _seed_order(db)
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=100))
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=200))
    db.flush()
    rows_before = db.query(HandcraftPartItem).filter_by(handcraft_order_id="HC-M1").all()
    survivor_id = min(r.id for r in rows_before)

    result = merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")

    assert result["before_rows"] == 2
    assert result["after_rows"] == 1
    assert result["merged_qty"] == 300.0
    assert result["merged_part_item_id"] == survivor_id

    remaining = db.query(HandcraftPartItem).filter_by(handcraft_order_id="HC-M1").all()
    assert len(remaining) == 1
    assert remaining[0].id == survivor_id
    assert remaining[0].qty == 300


def test_merge_three_duplicate_part_items_sums_qty(db):
    """qty 1 + 1 + 4 → qty 6, one row remains."""
    _seed_part(db)
    _seed_order(db)
    db.flush()
    for q in (1, 1, 4):
        db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=q))
    db.flush()

    result = merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")

    assert result["before_rows"] == 3
    assert result["merged_qty"] == 6.0
    remaining = db.query(HandcraftPartItem).filter_by(handcraft_order_id="HC-M1").all()
    assert len(remaining) == 1
    assert remaining[0].qty == 6


def test_merge_clears_weight_weight_unit_and_bom_qty_on_survivor(db):
    """Merging wipes weight/weight_unit/bom_qty on the survivor row, since the
    per-jewelry meaning is lost after consolidation."""
    _seed_part(db)
    _seed_order(db)
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-M1", part_id="PJ-X-LK",
        qty=100, weight=Decimal("80"), weight_unit="g", bom_qty=1,
    ))
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-M1", part_id="PJ-X-LK",
        qty=200, weight=Decimal("160"), weight_unit="g", bom_qty=1,
    ))
    db.flush()

    merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")

    survivor = db.query(HandcraftPartItem).filter_by(handcraft_order_id="HC-M1").one()
    assert survivor.weight is None
    assert survivor.weight_unit is None
    assert survivor.bom_qty is None


def test_merge_clears_picking_records_for_all_affected_part_items(db):
    """All HandcraftPickingRecord rows for affected part_item_ids are deleted —
    including the survivor's, because the merge restructures what 'picking'
    means at this scope."""
    _seed_part(db)
    _seed_order(db)
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=100))
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=200))
    db.flush()
    items = db.query(HandcraftPartItem).filter_by(handcraft_order_id="HC-M1").all()
    for it in items:
        db.add(HandcraftPickingRecord(
            handcraft_order_id="HC-M1",
            handcraft_part_item_id=it.id,
            part_id="PJ-X-LK",
        ))
    db.flush()
    assert db.query(HandcraftPickingRecord).count() == 2

    merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")

    assert db.query(HandcraftPickingRecord).count() == 0


def test_merge_clears_picking_weights_for_all_affected_part_items(db):
    """All HandcraftPickingWeight rows for affected part_item_ids are deleted."""
    _seed_part(db)
    _seed_order(db)
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=100))
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=200))
    db.flush()
    items = db.query(HandcraftPartItem).filter_by(handcraft_order_id="HC-M1").all()
    for it in items:
        db.add(HandcraftPickingWeight(
            handcraft_order_id="HC-M1",
            part_item_id=it.id,
            atom_part_id="PJ-X-LK",
            weight=Decimal("80"),
            weight_unit="g",
        ))
    db.flush()
    assert db.query(HandcraftPickingWeight).count() == 2

    merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")

    assert db.query(HandcraftPickingWeight).count() == 0


def test_merge_in_processing_raises(db):
    """Non-pending orders cannot be merged."""
    _seed_part(db)
    _seed_order(db, status="processing")
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=100))
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=200))
    db.flush()

    with pytest.raises(ValueError, match="不在 pending"):
        merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")


def test_merge_in_completed_raises(db):
    _seed_part(db)
    _seed_order(db, status="completed")
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=100))
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=200))
    db.flush()

    with pytest.raises(ValueError, match="不在 pending"):
        merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")


def test_merge_with_fewer_than_two_rows_raises(db):
    """No-op should be explicit — caller asked for a structural change that
    can't happen with <2 rows."""
    _seed_part(db)
    _seed_order(db)
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-LK", qty=100))
    db.flush()

    with pytest.raises(ValueError, match="没有可合并"):
        merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")


def test_merge_with_zero_rows_raises(db):
    _seed_part(db)
    _seed_order(db)
    db.flush()

    with pytest.raises(ValueError, match="没有可合并"):
        merge_duplicate_part_items(db, "HC-M1", "PJ-X-LK")


def test_merge_composite_part_raises(db):
    """Composite parts are out of v1 scope."""
    _seed_part(db, part_id="PJ-X-SET", is_composite=True)
    _seed_order(db)
    db.flush()
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-SET", qty=5))
    db.add(HandcraftPartItem(handcraft_order_id="HC-M1", part_id="PJ-X-SET", qty=3))
    db.flush()

    with pytest.raises(ValueError, match="复合件"):
        merge_duplicate_part_items(db, "HC-M1", "PJ-X-SET")


def test_merge_nonexistent_order_raises(db):
    _seed_part(db)
    db.flush()

    with pytest.raises(ValueError, match="订单"):
        merge_duplicate_part_items(db, "HC-DOES-NOT-EXIST", "PJ-X-LK")


def test_merge_nonexistent_part_raises(db):
    _seed_order(db)
    db.flush()

    with pytest.raises(ValueError, match="配件"):
        merge_duplicate_part_items(db, "HC-M1", "PJ-X-NONE")
