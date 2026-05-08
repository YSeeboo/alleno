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


# ---------------------------------------------------------------------------
# mark_done
# ---------------------------------------------------------------------------
from services.restock import mark_done


def test_mark_done_transitions_pending_to_done(db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")

    updated = mark_done(db, rec.id)

    assert updated.status == "done"
    assert updated.completed_at is not None


def test_mark_done_raises_when_already_done(db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")
    mark_done(db, rec.id)

    with pytest.raises(ValueError, match="已完成"):
        mark_done(db, rec.id)


def test_mark_done_raises_for_unknown_id(db):
    with pytest.raises(ValueError, match="补货记录不存在"):
        mark_done(db, 99999)


# ---------------------------------------------------------------------------
# mark_part_done
# ---------------------------------------------------------------------------
from services.restock import mark_part_done


def test_mark_part_done_updates_only_pending_for_that_part(db):
    _seed_part(db, "PJ-X-00001")
    _seed_part(db, "PJ-X-00002")
    _seed_handcraft(db, "HC-0001")
    _seed_handcraft(db, "HC-0002")

    a = create_from_picking(db, "PJ-X-00001", "HC-0001")
    b = create_from_picking(db, "PJ-X-00001", "HC-0002")
    other = create_from_picking(db, "PJ-X-00002", "HC-0001")
    # mark `other` done so it is excluded from the update
    mark_done(db, other.id)
    # also pre-mark one of the same-part records done — should NOT be touched
    pre_done = create_from_picking(db, "PJ-X-00001", "HC-0001")  # idempotent, returns a
    assert pre_done.id == a.id

    count = mark_part_done(db, "PJ-X-00001")
    db.refresh(a)
    db.refresh(b)
    db.refresh(other)

    assert count == 2
    assert a.status == "done" and a.completed_at is not None
    assert b.status == "done" and b.completed_at is not None
    assert other.status == "done"  # was already done, untouched but still done


def test_mark_part_done_returns_zero_when_no_pending(db):
    _seed_part(db, "PJ-X-00001")

    count = mark_part_done(db, "PJ-X-00001")

    assert count == 0


# ---------------------------------------------------------------------------
# delete_pending
# ---------------------------------------------------------------------------
from services.restock import delete_pending


def test_delete_pending_removes_pending_record(db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")

    delete_pending(db, rec.id)

    from models.restock_request import RestockRequest as R
    assert db.query(R).filter_by(id=rec.id).one_or_none() is None


def test_delete_pending_raises_when_done(db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")
    mark_done(db, rec.id)

    with pytest.raises(ValueError, match="已补货的记录不可删除"):
        delete_pending(db, rec.id)


def test_delete_pending_raises_for_unknown_id(db):
    with pytest.raises(ValueError, match="补货记录不存在"):
        delete_pending(db, 99999)
