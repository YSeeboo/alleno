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


# ---------------------------------------------------------------------------
# list_for_handcraft
# ---------------------------------------------------------------------------
from services.restock import list_for_handcraft


def test_list_for_handcraft_returns_pending_and_done_newest_first(db):
    _seed_part(db, "PJ-X-00001")
    _seed_part(db, "PJ-X-00002")
    _seed_handcraft(db)

    rec1 = create_from_picking(db, "PJ-X-00001", "HC-0001")
    rec2 = create_manual(db, "PJ-X-00002", "HC-0001", note="实物找不到")
    mark_done(db, rec1.id)

    rows = list_for_handcraft(db, "HC-0001")

    assert len(rows) == 2
    assert {r.id for r in rows} == {rec1.id, rec2.id}


def test_list_for_handcraft_excludes_other_orders(db):
    _seed_part(db)
    _seed_handcraft(db, "HC-0001")
    _seed_handcraft(db, "HC-0002")
    create_from_picking(db, "PJ-X-00001", "HC-0001")
    create_from_picking(db, "PJ-X-00001", "HC-0002")

    rows = list_for_handcraft(db, "HC-0001")
    assert len(rows) == 1
    assert rows[0].handcraft_order_id == "HC-0001"


# ---------------------------------------------------------------------------
# list_pending_summary
# ---------------------------------------------------------------------------
from services.restock import list_pending_summary
from services.inventory import add_stock


def test_list_pending_summary_aggregates_by_part(db):
    _seed_part(db, "PJ-X-00001", name="小圆环")
    _seed_part(db, "PJ-X-00002", name="银扣头")
    _seed_handcraft(db, "HC-0001", supplier="王师傅")
    _seed_handcraft(db, "HC-0002", supplier="李姐")

    add_stock(db, "part", "PJ-X-00001", 5.0, "测试入库")

    create_from_picking(db, "PJ-X-00001", "HC-0001")
    create_from_picking(db, "PJ-X-00001", "HC-0002")
    create_from_picking(db, "PJ-X-00002", "HC-0001")

    summary = list_pending_summary(db)
    summary_by_part = {row["part_id"]: row for row in summary}

    assert set(summary_by_part) == {"PJ-X-00001", "PJ-X-00002"}
    a = summary_by_part["PJ-X-00001"]
    assert a["part_name"] == "小圆环"
    assert a["current_stock"] == 5.0
    assert a["source_count"] == 2
    assert {s["handcraft_order_id"] for s in a["sources"]} == {"HC-0001", "HC-0002"}
    assert {s["supplier_name"] for s in a["sources"]} == {"王师傅", "李姐"}


def test_list_pending_summary_excludes_done(db):
    _seed_part(db, "PJ-X-00001")
    _seed_handcraft(db, "HC-0001")
    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")
    mark_done(db, rec.id)

    summary = list_pending_summary(db)
    assert summary == []


# ---------------------------------------------------------------------------
# list_history
# ---------------------------------------------------------------------------
from services.restock import list_history


def test_list_history_returns_done_records_with_part_and_supplier(db):
    _seed_part(db, "PJ-X-00001", name="小圆环")
    _seed_part(db, "PJ-X-00002")
    _seed_handcraft(db, "HC-0001", supplier="王师傅")

    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")
    mark_done(db, rec.id)
    # an unrelated pending record — should NOT appear in history
    create_from_picking(db, "PJ-X-00002", "HC-0001")

    rows = list_history(db)

    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == rec.id
    assert row["part_id"] == "PJ-X-00001"
    assert row["part_name"] == "小圆环"
    assert row["handcraft_order_id"] == "HC-0001"
    assert row["supplier_name"] == "王师傅"
    assert row["completed_at"] is not None


def test_list_history_filter_by_part_and_handcraft(db):
    _seed_part(db, "PJ-X-00001")
    _seed_part(db, "PJ-X-00002")
    _seed_handcraft(db, "HC-0001")
    _seed_handcraft(db, "HC-0002")

    a = create_from_picking(db, "PJ-X-00001", "HC-0001"); mark_done(db, a.id)
    b = create_from_picking(db, "PJ-X-00002", "HC-0001"); mark_done(db, b.id)
    c = create_from_picking(db, "PJ-X-00001", "HC-0002"); mark_done(db, c.id)

    rows = list_history(db, part_id="PJ-X-00001")
    assert {r["id"] for r in rows} == {a.id, c.id}

    rows = list_history(db, handcraft_order_id="HC-0001")
    assert {r["id"] for r in rows} == {a.id, b.id}


# ---------------------------------------------------------------------------
# delete_handcraft_order cascade
# ---------------------------------------------------------------------------
from services.handcraft import delete_handcraft_order


def test_delete_handcraft_order_cascades_restock_requests(db):
    _seed_part(db, "PJ-X-00001")
    _seed_handcraft(db, "HC-0001")
    rec_pending = create_from_picking(db, "PJ-X-00001", "HC-0001")

    _seed_part(db, "PJ-X-00002")
    rec_done = create_manual(db, "PJ-X-00002", "HC-0001")
    mark_done(db, rec_done.id)

    delete_handcraft_order(db, "HC-0001")

    from models.restock_request import RestockRequest as R
    remaining = db.query(R).filter_by(handcraft_order_id="HC-0001").all()
    assert remaining == []


from services.restock import update_shortfall


def test_update_shortfall_sets_value(db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")

    updated = update_shortfall(db, rec.id, 12.5)

    assert float(updated.shortfall_qty) == 12.5


def test_update_shortfall_clears_value(db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")
    update_shortfall(db, rec.id, 5)

    updated = update_shortfall(db, rec.id, None)

    assert updated.shortfall_qty is None


def test_update_shortfall_raises_when_done(db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = create_from_picking(db, "PJ-X-00001", "HC-0001")
    mark_done(db, rec.id)

    with pytest.raises(ValueError, match="不可修改差额"):
        update_shortfall(db, rec.id, 10)


def test_update_shortfall_raises_for_unknown(db):
    with pytest.raises(ValueError, match="补货记录不存在"):
        update_shortfall(db, 99999, 1)
