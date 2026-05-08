import pytest

from models.handcraft_order import HandcraftOrder
from models.part import Part
from services.restock import create_from_picking, create_manual


def _seed_part(db, part_id="PJ-X-00001", name="小圆环", category="小配件"):
    p = Part(id=part_id, name=name, category=category)
    db.add(p)
    db.flush()
    return p


def _seed_handcraft(db, hc_id="HC-0001", supplier="王师傅"):
    o = HandcraftOrder(id=hc_id, supplier_name=supplier, status="pending")
    db.add(o)
    db.flush()
    return o


def test_create_from_picking_inserts_pending_with_picking_source(db):
    _seed_part(db)
    _seed_handcraft(db)

    rec = create_from_picking(db, part_id="PJ-X-00001", handcraft_order_id="HC-0001")

    assert rec.id is not None
    assert rec.part_id == "PJ-X-00001"
    assert rec.handcraft_order_id == "HC-0001"
    assert rec.source == "picking"
    assert rec.status == "pending"
    assert rec.completed_at is None


def test_create_from_picking_is_idempotent_for_pending(db):
    _seed_part(db)
    _seed_handcraft(db)

    rec1 = create_from_picking(db, "PJ-X-00001", "HC-0001")
    rec2 = create_from_picking(db, "PJ-X-00001", "HC-0001")

    assert rec1.id == rec2.id


def test_create_from_picking_raises_when_already_done(db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")
    rec.status = "done"
    db.flush()

    with pytest.raises(ValueError, match="已为此手工单补过货"):
        create_from_picking(db, "PJ-X-00001", "HC-0001")


def test_create_from_picking_raises_for_missing_part(db):
    _seed_handcraft(db)
    with pytest.raises(ValueError, match="配件不存在"):
        create_from_picking(db, "PJ-X-99999", "HC-0001")


def test_create_from_picking_raises_for_missing_handcraft(db):
    _seed_part(db)
    with pytest.raises(ValueError, match="手工单不存在"):
        create_from_picking(db, "PJ-X-00001", "HC-9999")


def test_create_manual_persists_note_and_source(db):
    _seed_part(db)
    _seed_handcraft(db)

    rec = create_manual(db, "PJ-X-00001", "HC-0001", note="实物找不到")

    assert rec.source == "manual"
    assert rec.note == "实物找不到"
    assert rec.status == "pending"


def test_create_manual_does_not_overwrite_existing_note(db):
    _seed_part(db)
    _seed_handcraft(db)
    create_manual(db, "PJ-X-00001", "HC-0001", note="第一次")

    rec = create_manual(db, "PJ-X-00001", "HC-0001", note="第二次")

    assert rec.note == "第一次"
