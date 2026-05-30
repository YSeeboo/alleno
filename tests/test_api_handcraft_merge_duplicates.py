"""Service + API tests for handcraft 合并相同 part_id 的 part_item 行.

See docs/superpowers/specs/2026-05-30-handcraft-merge-duplicate-part-items-design.md.
Service-layer tests use the `db` fixture (truncates between tests).
API tests use the `client` fixture (overrides auth, shared session)."""

from decimal import Decimal

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
