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
    assert delete_weight(db, order_id, pi.id, "PJ-X-WT01") is True
    assert delete_weight(db, order_id, pi.id, "PJ-X-WT01") is False


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


def test_api_put_weight_upsert(client, db):
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem

    db.add(PartModel(id="PJ-X-EP1", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-EP1", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-EP1", part_id="PJ-X-EP1", qty=200, bom_qty=200)
    db.add(pi); db.flush()
    pi_id = pi.id

    r = client.put(f"/api/handcraft/HC-EP1/picking/weight", json={
        "part_item_id": pi_id, "atom_part_id": "PJ-X-EP1",
        "weight": 0.5, "weight_unit": "kg",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["weight"] == 0.5


def test_api_put_weight_blocked_when_status_not_pending(client, db):
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem

    db.add(PartModel(id="PJ-X-EP2", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-EP2", supplier_name="S", status="processing"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-EP2", part_id="PJ-X-EP2", qty=200, bom_qty=200)
    db.add(pi); db.flush()
    r = client.put(f"/api/handcraft/HC-EP2/picking/weight", json={
        "part_item_id": pi.id, "atom_part_id": "PJ-X-EP2",
        "weight": 0.5,
    })
    assert r.status_code == 400


def test_api_delete_weight(client, db):
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem
    from services.handcraft_picking_weight import upsert_weight

    db.add(PartModel(id="PJ-X-EP3", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-EP3", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-EP3", part_id="PJ-X-EP3", qty=200, bom_qty=200)
    db.add(pi); db.flush()
    upsert_weight(db, "HC-EP3", pi.id, "PJ-X-EP3", 0.5, "kg")

    r = client.request("DELETE", f"/api/handcraft/HC-EP3/picking/weight",
                       json={"part_item_id": pi.id, "atom_part_id": "PJ-X-EP3"})
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_patch_atomic_part_weight_lands_in_new_table(client, db):
    """PATCH /handcraft/{id}/parts/{item_id} with weight on atomic part_item
    should write to handcraft_picking_weight, NOT handcraft_part_item.weight."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftPickingWeight

    db.add(PartModel(id="PJ-X-PT1", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-PT1", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-PT1", part_id="PJ-X-PT1", qty=200, bom_qty=200)
    db.add(pi); db.flush()

    r = client.put(f"/api/handcraft/HC-PT1/parts/{pi.id}",
                     json={"weight": 0.5, "weight_unit": "kg"})
    assert r.status_code == 200

    db.refresh(pi)
    assert pi.weight is None

    rows = db.query(HandcraftPickingWeight).filter_by(part_item_id=pi.id).all()
    assert len(rows) == 1
    assert float(rows[0].weight) == 0.5


def test_patch_composite_part_weight_rejected(client, db):
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem
    from services.part_bom import set_part_bom

    db.add(PartModel(id="PJ-X-A1", name="原A", category="小配件", size_tier="small"))
    db.add(PartModel(id="PJ-X-B1", name="原B", category="小配件", size_tier="small"))
    db.add(PartModel(id="PJ-X-CO1", name="组合", category="小配件", size_tier="small"))
    db.flush()
    set_part_bom(db, "PJ-X-CO1", "PJ-X-A1", 1)
    set_part_bom(db, "PJ-X-CO1", "PJ-X-B1", 1)
    db.add(HandcraftOrder(id="HC-PT2", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-PT2", part_id="PJ-X-CO1", qty=10, bom_qty=10)
    db.add(pi); db.flush()

    r = client.put(f"/api/handcraft/HC-PT2/parts/{pi.id}",
                     json={"weight": 0.5, "weight_unit": "kg"})
    assert r.status_code == 400


def test_patch_non_weight_fields_unchanged_for_both(client, db):
    """Non-weight fields still update normally for atomic and composite alike."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem

    db.add(PartModel(id="PJ-X-PT3", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-PT3", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-PT3", part_id="PJ-X-PT3", qty=200, bom_qty=200)
    db.add(pi); db.flush()

    r = client.put(f"/api/handcraft/HC-PT3/parts/{pi.id}", json={"note": "hello"})
    assert r.status_code == 200
    db.refresh(pi)
    assert pi.note == "hello"


def test_delete_part_item_cascades_picking_weight(client, db):
    """Deleting a HandcraftPartItem must cascade-delete its picking_weight rows."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftPickingWeight

    db.add(PartModel(id="PJ-X-CD1", name="链头", category="小配件", size_tier="small"))
    db.add(PartModel(id="PJ-X-CD2", name="扣环", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-CD1", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-CD1", part_id="PJ-X-CD1", qty=200, bom_qty=200)
    # Add a second part_item so delete_handcraft_part doesn't reject the
    # request for being "the last part item".
    pi_keep = HandcraftPartItem(handcraft_order_id="HC-CD1", part_id="PJ-X-CD2", qty=100, bom_qty=100)
    db.add(pi); db.add(pi_keep); db.flush()
    pi_id = pi.id

    upsert_weight(db, "HC-CD1", pi_id, "PJ-X-CD1", 0.5, "kg")
    assert db.query(HandcraftPickingWeight).filter_by(part_item_id=pi_id).count() == 1

    # Delete the part_item via the API endpoint
    r = client.delete(f"/api/handcraft/HC-CD1/parts/{pi_id}")
    assert r.status_code in (200, 204)

    # Picking weight rows should be gone (FK ondelete=CASCADE)
    db.expire_all()
    assert db.query(HandcraftPickingWeight).filter_by(part_item_id=pi_id).count() == 0


def test_ensure_schema_compat_backfills_existing_weights(db):
    """Existing HandcraftPartItem.weight values get migrated to handcraft_picking_weight."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftPickingWeight
    from database import ensure_schema_compat
    from sqlalchemy import text

    db.add(PartModel(id="PJ-X-MG1", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-MGR1", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-MGR1", part_id="PJ-X-MG1", qty=200, bom_qty=200,
                           weight=0.5, weight_unit="g")
    db.add(pi); db.flush()
    pi_id = pi.id

    db.execute(text("DELETE FROM handcraft_picking_weight WHERE part_item_id = :pi"), {"pi": pi_id})
    db.commit()

    ensure_schema_compat(target_engine=db.bind)

    rows = db.query(HandcraftPickingWeight).filter_by(part_item_id=pi_id).all()
    assert len(rows) == 1
    assert float(rows[0].weight) == 0.5
    assert rows[0].weight_unit == "g"

    # Idempotent: run again should not duplicate
    ensure_schema_compat(target_engine=db.bind)
    rows = db.query(HandcraftPickingWeight).filter_by(part_item_id=pi_id).all()
    assert len(rows) == 1


def test_create_handcraft_order_routes_atomic_weight_to_new_table(client, db):
    """POST /api/handcraft/ with weight on an atomic part should land in
    handcraft_picking_weight, not the legacy HandcraftPartItem.weight column."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftPartItem, HandcraftPickingWeight

    db.add(PartModel(id="PJ-X-CHO1", name="链头", category="小配件", size_tier="small"))
    db.commit()

    r = client.post("/api/handcraft/", json={
        "supplier_name": "S-CHO1",
        "parts": [{"part_id": "PJ-X-CHO1", "qty": 200, "bom_qty": 200, "weight": 0.5, "weight_unit": "kg"}],
    })
    assert r.status_code in (200, 201), r.text
    order_id = r.json()["id"]

    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order_id, part_id="PJ-X-CHO1").one()
    assert pi.weight is None  # legacy column not written
    rows = db.query(HandcraftPickingWeight).filter_by(part_item_id=pi.id).all()
    assert len(rows) == 1
    assert float(rows[0].weight) == 0.5
    assert rows[0].weight_unit == "kg"


def test_delete_picking_weight_rejects_cross_order(client, db):
    """A pending order's DELETE endpoint must NOT touch a part_item that
    belongs to another order, even if the caller guesses the auto-increment
    part_item_id."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftPickingWeight

    db.add(PartModel(id="PJ-X-XOA", name="链头A", category="小配件", size_tier="small"))
    db.add(PartModel(id="PJ-X-XOB", name="链头B", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-XOA", supplier_name="S", status="pending"))
    db.add(HandcraftOrder(id="HC-XOB", supplier_name="S", status="pending"))
    db.flush()
    pa = HandcraftPartItem(handcraft_order_id="HC-XOA", part_id="PJ-X-XOA", qty=200, bom_qty=200)
    pb = HandcraftPartItem(handcraft_order_id="HC-XOB", part_id="PJ-X-XOB", qty=200, bom_qty=200)
    db.add(pa); db.add(pb); db.flush()
    upsert_weight(db, "HC-XOA", pa.id, "PJ-X-XOA", 0.5, "kg")
    upsert_weight(db, "HC-XOB", pb.id, "PJ-X-XOB", 0.7, "kg")
    db.commit()

    # Try to delete order B's weight via order A's URL
    r = client.request(
        "DELETE", "/api/handcraft/HC-XOA/picking/weight",
        json={"part_item_id": pb.id, "atom_part_id": "PJ-X-XOB"},
    )
    assert r.status_code >= 400 and r.status_code < 500, r.text

    # Order B's weight row must still be intact
    db.expire_all()
    rows = db.query(HandcraftPickingWeight).filter_by(part_item_id=pb.id).all()
    assert len(rows) == 1
    assert float(rows[0].weight) == 0.7


def test_patch_atomic_part_weight_zero_clears_record(client, db):
    """PATCH /handcraft/{id}/parts/{item_id} with weight=0 should clear the
    picking_weight row (treated the same as null), matching the picking
    endpoint's gt=0 schema and the modal's clear-on-blur semantics."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftPickingWeight

    db.add(PartModel(id="PJ-X-PZ1", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-PZ1", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-PZ1", part_id="PJ-X-PZ1", qty=200, bom_qty=200)
    db.add(pi); db.flush()
    upsert_weight(db, "HC-PZ1", pi.id, "PJ-X-PZ1", 0.5, "kg")
    assert db.query(HandcraftPickingWeight).filter_by(part_item_id=pi.id).count() == 1
    db.commit()

    r = client.put(f"/api/handcraft/HC-PZ1/parts/{pi.id}", json={"weight": 0})
    assert r.status_code == 200, r.text

    db.expire_all()
    assert db.query(HandcraftPickingWeight).filter_by(part_item_id=pi.id).count() == 0


def test_create_handcraft_order_drops_composite_weight(client, db):
    """POST /api/handcraft/ with weight on a composite part should silently
    drop the weight (composite weights are per-atom after expansion)."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftPartItem, HandcraftPickingWeight
    from services.part_bom import set_part_bom

    db.add(PartModel(id="PJ-X-CHO2A", name="原A", category="小配件", size_tier="small"))
    db.add(PartModel(id="PJ-X-CHO2B", name="原B", category="小配件", size_tier="small"))
    db.add(PartModel(id="PJ-X-CHO2", name="组合", category="小配件", size_tier="small"))
    db.flush()
    set_part_bom(db, "PJ-X-CHO2", "PJ-X-CHO2A", 1)
    set_part_bom(db, "PJ-X-CHO2", "PJ-X-CHO2B", 1)
    db.commit()

    r = client.post("/api/handcraft/", json={
        "supplier_name": "S-CHO2",
        "parts": [{"part_id": "PJ-X-CHO2", "qty": 10, "bom_qty": 10, "weight": 0.8, "weight_unit": "kg"}],
    })
    assert r.status_code in (200, 201), r.text
    order_id = r.json()["id"]

    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order_id, part_id="PJ-X-CHO2").one()
    assert pi.weight is None
    assert db.query(HandcraftPickingWeight).filter_by(part_item_id=pi.id).count() == 0


def test_delete_weight_keeps_row_when_actual_qty_present(db):
    """Clearing weight on a row that also holds actual_qty should NOT delete
    the row. Only the weight fields are cleared."""
    from sqlalchemy import update
    order_id, pi = _seed_atomic(db, order_id="HC-WTKEEP")
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")
    # Simulate actual_qty being set (we'll formally test upsert_actual_qty later).
    db.execute(update(HandcraftPickingWeight)
               .where(HandcraftPickingWeight.part_item_id == pi.id,
                      HandcraftPickingWeight.atom_part_id == "PJ-X-WT01")
               .values(actual_qty=Decimal("123.4567")))
    db.flush()

    deleted = delete_weight(db, order_id, pi.id, "PJ-X-WT01")
    assert deleted is True

    row = (db.query(HandcraftPickingWeight)
           .filter_by(part_item_id=pi.id, atom_part_id="PJ-X-WT01")
           .one_or_none())
    assert row is not None, "row should remain because actual_qty is set"
    assert row.weight is None
    assert row.weight_unit is None
    assert row.actual_qty == Decimal("123.4567")


def test_delete_weight_removes_row_when_actual_qty_null(db):
    """Existing behavior: when only weight is set (no actual_qty), clearing
    weight deletes the entire row."""
    order_id, pi = _seed_atomic(db, order_id="HC-WTDROP")
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")

    deleted = delete_weight(db, order_id, pi.id, "PJ-X-WT01")
    assert deleted is True
    assert db.query(HandcraftPickingWeight).filter_by(
        part_item_id=pi.id, atom_part_id="PJ-X-WT01"
    ).count() == 0


def test_upsert_actual_qty_inserts_new_row(db):
    from services.handcraft_picking_weight import upsert_actual_qty
    order_id, pi = _seed_atomic(db, order_id="HC-AQ01")
    row = upsert_actual_qty(db, order_id, pi.id, "PJ-X-WT01", 250.5)
    assert row.actual_qty == Decimal("250.5000")
    assert row.weight is None
    assert row.weight_unit is None


def test_upsert_actual_qty_updates_existing_weight_row(db):
    """A row that has weight gets actual_qty appended without losing weight."""
    from services.handcraft_picking_weight import upsert_actual_qty
    order_id, pi = _seed_atomic(db, order_id="HC-AQ02")
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")
    upsert_actual_qty(db, order_id, pi.id, "PJ-X-WT01", 250)

    row = db.query(HandcraftPickingWeight).filter_by(part_item_id=pi.id).one()
    assert row.weight == Decimal("0.5000")
    assert row.weight_unit == "kg"
    assert row.actual_qty == Decimal("250.0000")


def test_upsert_actual_qty_rejects_part_item_outside_order(db):
    from services.handcraft_picking_weight import upsert_actual_qty
    import pytest
    _, pi = _seed_atomic(db, order_id="HC-AQ03")
    db.add(HandcraftOrder(id="HC-OTHER-AQ", supplier_name="S", status="pending"))
    db.flush()
    with pytest.raises(ValueError, match="不属于"):
        upsert_actual_qty(db, "HC-OTHER-AQ", pi.id, "PJ-X-WT01", 100)


def test_clear_actual_qty_removes_row_when_weight_null(db):
    from services.handcraft_picking_weight import upsert_actual_qty, clear_actual_qty
    order_id, pi = _seed_atomic(db, order_id="HC-AQ04")
    upsert_actual_qty(db, order_id, pi.id, "PJ-X-WT01", 250)
    deleted = clear_actual_qty(db, order_id, pi.id, "PJ-X-WT01")
    assert deleted is True
    assert db.query(HandcraftPickingWeight).filter_by(part_item_id=pi.id).count() == 0


def test_clear_actual_qty_keeps_row_when_weight_present(db):
    from services.handcraft_picking_weight import upsert_actual_qty, clear_actual_qty
    order_id, pi = _seed_atomic(db, order_id="HC-AQ05")
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")
    upsert_actual_qty(db, order_id, pi.id, "PJ-X-WT01", 250)

    deleted = clear_actual_qty(db, order_id, pi.id, "PJ-X-WT01")
    assert deleted is True
    row = db.query(HandcraftPickingWeight).filter_by(part_item_id=pi.id).one()
    assert row.actual_qty is None
    assert row.weight == Decimal("0.5000")


def test_clear_actual_qty_returns_false_when_no_row(db):
    from services.handcraft_picking_weight import clear_actual_qty
    order_id, pi = _seed_atomic(db, order_id="HC-AQ06")
    assert clear_actual_qty(db, order_id, pi.id, "PJ-X-WT01") is False


def test_api_put_actual_qty_upsert(client, db):
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem

    db.add(PartModel(id="PJ-X-EAQ1", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-EAQ1", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-EAQ1", part_id="PJ-X-EAQ1", qty=200, bom_qty=200)
    db.add(pi); db.flush()
    pi_id = pi.id

    r = client.put(f"/api/handcraft/HC-EAQ1/picking/actual_qty", json={
        "part_item_id": pi_id, "atom_part_id": "PJ-X-EAQ1", "qty": 250,
    })
    assert r.status_code == 200, r.text
    assert r.json()["actual_qty"] == 250


def test_api_put_actual_qty_blocked_when_status_not_pending(client, db):
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem

    db.add(PartModel(id="PJ-X-EAQ2", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-EAQ2", supplier_name="S", status="processing"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-EAQ2", part_id="PJ-X-EAQ2", qty=200, bom_qty=200)
    db.add(pi); db.flush()
    r = client.put(f"/api/handcraft/HC-EAQ2/picking/actual_qty", json={
        "part_item_id": pi.id, "atom_part_id": "PJ-X-EAQ2", "qty": 250,
    })
    assert r.status_code == 400


def test_api_delete_actual_qty(client, db):
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem
    from services.handcraft_picking_weight import upsert_actual_qty

    db.add(PartModel(id="PJ-X-EAQ3", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-EAQ3", supplier_name="S", status="pending"))
    db.flush()
    pi = HandcraftPartItem(handcraft_order_id="HC-EAQ3", part_id="PJ-X-EAQ3", qty=200, bom_qty=200)
    db.add(pi); db.flush()
    upsert_actual_qty(db, "HC-EAQ3", pi.id, "PJ-X-EAQ3", 250)

    r = client.request("DELETE", f"/api/handcraft/HC-EAQ3/picking/actual_qty",
                       json={"part_item_id": pi.id, "atom_part_id": "PJ-X-EAQ3"})
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_sum_weight_skips_actual_qty_only_rows(db):
    """actual_qty-only rows have weight=None and must not crash the sum;
    they're invisible to the weight summation."""
    from services.handcraft_picking_weight import upsert_actual_qty
    order_id, pi = _seed_atomic(db, order_id="HC-AQ-SUM1")
    upsert_actual_qty(db, order_id, pi.id, "PJ-X-WT01", 250)
    # No upsert_weight call → row has weight=None
    assert sum_weight_by_part_item(db, pi.id) is None


def test_sum_weight_handles_mixed_actual_only_and_weighed(db):
    """Mixing actual_qty-only and weighed rows: SUM only counts the weighed ones."""
    from services.handcraft_picking_weight import upsert_actual_qty
    order_id, pi = _seed_atomic(db, order_id="HC-AQ-SUM2")
    db.add(PartModel(id="PJ-X-WTC", name="C", category="小配件", size_tier="small"))
    db.flush()
    upsert_weight(db, order_id, pi.id, "PJ-X-WT01", 0.5, "kg")     # weighed
    upsert_actual_qty(db, order_id, pi.id, "PJ-X-WTC", 250)        # actual-only
    total = sum_weight_by_part_item(db, pi.id, target_unit="kg")
    assert abs(total - 0.5) < 1e-6


def test_api_delete_actual_qty_rejects_cross_order(client, db):
    """Issue #8 mirror: cross-order DELETE must be rejected (4xx), not silently
    delete another order's row."""
    from models.part import Part as PartModel
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftPickingWeight
    from services.handcraft_picking_weight import upsert_actual_qty

    db.add(PartModel(id="PJ-X-EAQX", name="链头", category="小配件", size_tier="small"))
    db.add(HandcraftOrder(id="HC-A-AQ", supplier_name="S", status="pending"))
    db.add(HandcraftOrder(id="HC-B-AQ", supplier_name="S", status="pending"))
    db.flush()
    pi_b = HandcraftPartItem(handcraft_order_id="HC-B-AQ", part_id="PJ-X-EAQX", qty=200, bom_qty=200)
    db.add(pi_b); db.flush()
    upsert_actual_qty(db, "HC-B-AQ", pi_b.id, "PJ-X-EAQX", 250)

    r = client.request("DELETE", f"/api/handcraft/HC-A-AQ/picking/actual_qty",
                       json={"part_item_id": pi_b.id, "atom_part_id": "PJ-X-EAQX"})
    assert r.status_code == 400
    # Order B's actual_qty must still be present.
    row = db.query(HandcraftPickingWeight).filter_by(part_item_id=pi_b.id).one()
    assert row.actual_qty == Decimal("250.0000")
