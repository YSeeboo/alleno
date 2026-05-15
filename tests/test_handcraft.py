import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.part import create_part
from services.part import update_part
from services.jewelry import create_jewelry
from services.inventory import add_stock, get_stock
from services.handcraft import (
    create_handcraft_order, send_handcraft_order,
    get_handcraft_order, get_handcraft_parts, list_handcraft_orders, update_handcraft_delivery_images,
)


@pytest.fixture
def setup(db):
    p1 = create_part(db, {"name": "铜扣", "category": "小配件", "color": "古铜"})
    p2 = create_part(db, {"name": "银链", "category": "链条", "color": "银色"})
    j1 = create_jewelry(db, {"name": "玫瑰戒指", "category": "单件"})
    add_stock(db, "part", p1.id, 200.0, "入库")
    add_stock(db, "part", p2.id, 100.0, "入库")
    return db, p1, p2, j1


def test_create_handcraft_order(setup):
    db, p1, p2, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50, "bom_qty": 48.0}],
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
    )
    from models.handcraft_order import HandcraftPartItem
    part_item = db.query(HandcraftPartItem).filter(HandcraftPartItem.handcraft_order_id == order.id).first()
    assert order.id == "HC-0001"
    assert order.status == "pending"
    assert part_item.part_id == p1.id


def test_auto_merge_same_supplier_same_day(setup):
    """同一天同一供应商的手工单自动合并到一张单"""
    db, p1, p2, j1 = setup
    order1 = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50}],
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
        note="第一批",
    )
    order2 = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p2.id, "qty": 30}],
        note="第二批",
    )
    # Should reuse the same order
    assert order2.id == order1.id
    # Items should be accumulated
    from models.handcraft_order import HandcraftPartItem, HandcraftJewelryItem
    parts = db.query(HandcraftPartItem).filter(HandcraftPartItem.handcraft_order_id == order1.id).all()
    jewelries = db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.handcraft_order_id == order1.id).all()
    assert len(parts) == 2
    assert len(jewelries) == 1
    # Notes should be merged
    assert "第一批" in order1.note
    assert "第二批" in order1.note


def test_no_merge_different_supplier(setup):
    """不同供应商不合并"""
    db, p1, p2, j1 = setup
    order1 = create_handcraft_order(
        db, "手工坊A",
        parts=[{"part_id": p1.id, "qty": 50}],
    )
    order2 = create_handcraft_order(
        db, "手工坊B",
        parts=[{"part_id": p2.id, "qty": 30}],
    )
    assert order1.id != order2.id


def test_no_merge_when_existing_is_processing(setup):
    """已发出的单不合并"""
    db, p1, p2, j1 = setup
    order1 = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50}],
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
    )
    send_handcraft_order(db, order1.id)
    order2 = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p2.id, "qty": 30}],
    )
    assert order2.id != order1.id


def test_send_handcraft_order_deducts_parts(setup):
    db, p1, p2, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50, "bom_qty": 48.0}],
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
    )
    send_handcraft_order(db, order.id)
    assert get_stock(db, "part", p1.id) == 150.0  # 200 - 50
    assert get_handcraft_order(db, order.id).status == "processing"


def test_send_handcraft_order_jewelry_status(setup):
    db, p1, p2, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50, "bom_qty": 48.0}],
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
    )
    send_handcraft_order(db, order.id)
    from models.handcraft_order import HandcraftJewelryItem
    items = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.handcraft_order_id == order.id
    ).all()
    assert all(i.status == "制作中" for i in items)


def test_send_handcraft_order_without_expected_jewelries(setup):
    db, p1, _, _ = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50, "bom_qty": 48.0}],
        jewelries=[],
    )
    send_handcraft_order(db, order.id)
    assert get_stock(db, "part", p1.id) == 150.0
    assert get_handcraft_order(db, order.id).status == "processing"


def test_send_handcraft_order_insufficient_stock(setup):
    db, p1, p2, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 300, "bom_qty": 300.0}],  # only 200
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
    )
    with pytest.raises(ValueError, match="库存不足"):
        send_handcraft_order(db, order.id)
    assert get_stock(db, "part", p1.id) == 200.0


def test_receive_handcraft_jewelries_partial(setup):
    from services.handcraft_receipt import create_handcraft_receipt
    db, p1, p2, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50}],
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
    )
    send_handcraft_order(db, order.id)
    from models.handcraft_order import HandcraftJewelryItem
    ji = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.handcraft_order_id == order.id
    ).first()
    create_handcraft_receipt(db, "手工坊", [{"handcraft_jewelry_item_id": ji.id, "qty": 6}])
    db.refresh(ji)
    assert ji.received_qty == 6
    assert ji.status == "制作中"  # not yet complete
    assert get_stock(db, "jewelry", j1.id) == 6.0


def test_receive_handcraft_jewelries_completes_order(setup):
    from services.handcraft_receipt import create_handcraft_receipt
    from models.handcraft_order import HandcraftJewelryItem, HandcraftPartItem
    db, p1, p2, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50}],
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
    )
    send_handcraft_order(db, order.id)
    ji = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.handcraft_order_id == order.id
    ).first()
    pi = db.query(HandcraftPartItem).filter(
        HandcraftPartItem.handcraft_order_id == order.id
    ).first()
    # Receive all jewelry and all parts
    create_handcraft_receipt(db, "手工坊", [
        {"handcraft_jewelry_item_id": ji.id, "qty": 6},
        {"handcraft_part_item_id": pi.id, "qty": 25},
    ])
    create_handcraft_receipt(db, "手工坊", [
        {"handcraft_jewelry_item_id": ji.id, "qty": 4},
        {"handcraft_part_item_id": pi.id, "qty": 25},
    ])
    db.refresh(ji)
    db.refresh(pi)
    db.refresh(order)
    assert ji.status == "已收回"
    assert pi.status == "已收回"
    assert order.status == "completed"
    assert order.completed_at is not None
    assert get_stock(db, "jewelry", j1.id) == 10.0


def test_list_handcraft_orders_filter(setup):
    db, p1, p2, j1 = setup
    create_handcraft_order(db, "坊A", parts=[{"part_id": p1.id, "qty": 10}], jewelries=[{"jewelry_id": j1.id, "qty": 5}])
    create_handcraft_order(db, "坊B", parts=[{"part_id": p2.id, "qty": 10}], jewelries=[{"jewelry_id": j1.id, "qty": 3}])
    assert len(list_handcraft_orders(db)) == 2
    assert len(list_handcraft_orders(db, status="processing")) == 0


def test_send_handcraft_order_twice_raises(setup):
    """Sending an already-processing order should raise ValueError."""
    db, p1, p2, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50}],
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
    )
    send_handcraft_order(db, order.id)
    with pytest.raises(ValueError, match="cannot be sent"):
        send_handcraft_order(db, order.id)
    # Stock should only be deducted once
    assert get_stock(db, "part", p1.id) == 150.0  # 200 - 50


def test_update_handcraft_delivery_images(setup):
    db, p1, _, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 20}],
        jewelries=[{"jewelry_id": j1.id, "qty": 5}],
    )

    update_handcraft_delivery_images(db, order.id, ["https://img.test/a.png", " https://img.test/b.png "])
    db.refresh(order)

    assert order.delivery_images == ["https://img.test/a.png", "https://img.test/b.png"]


def test_update_handcraft_delivery_images_rejects_more_than_four(setup):
    db, p1, _, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 20}],
        jewelries=[{"jewelry_id": j1.id, "qty": 5}],
    )

    with pytest.raises(ValueError, match="最多上传 10 张"):
        update_handcraft_delivery_images(db, order.id, [
            f"{i}.png" for i in range(11)
        ])


def test_handcraft_part_color_follows_part_color(setup):
    db, p1, _, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 20}],
        jewelries=[{"jewelry_id": j1.id, "qty": 5}],
    )

    update_part(db, p1.id, {"color": "哑金"})
    item = get_handcraft_parts(db, order.id)[0]
    assert item.color == "哑金"


def test_supplement_and_send_normal(setup):
    """1 part short by 5; supplement should write 1 缺货补进 log + 1 手工发出 log."""
    from services.handcraft import supplement_and_send_handcraft_order
    from services.inventory import get_stock
    from models.inventory_log import InventoryLog
    db, p1, _, j1 = setup  # p1 has 200 stock from fixture
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 205, "bom_qty": 200.0}],  # short by 5
        jewelries=[{"jewelry_id": j1.id, "qty": 10}],
    )
    result_order, supplemented = supplement_and_send_handcraft_order(db, order.id)
    assert result_order.status == "processing"
    assert supplemented == {p1.id: 5.0}
    assert get_stock(db, "part", p1.id) == 0.0  # 200 + 5 - 205

    logs = (
        db.query(InventoryLog)
        .filter(InventoryLog.item_id == p1.id)
        .order_by(InventoryLog.id)
        .all()
    )
    # ① 入库 200 (fixture) ② 手工单缺货补进 +5 (HC-...) ③ 手工发出 -205
    reasons = [(l.reason, float(l.change_qty), l.note) for l in logs]
    assert reasons[1] == ("手工单缺货补进", 5.0, order.id)
    assert reasons[2][0] == "手工发出"
    assert reasons[2][1] == -205.0


def test_supplement_and_send_no_shortage(setup):
    """Stock is already enough; supplement is skipped, only 手工发出 log written."""
    from services.handcraft import supplement_and_send_handcraft_order
    from services.inventory import get_stock
    from models.inventory_log import InventoryLog
    db, p1, _, j1 = setup  # p1 has 200 stock
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50, "bom_qty": 50.0}],
        jewelries=[{"jewelry_id": j1.id, "qty": 5}],
    )
    result_order, supplemented = supplement_and_send_handcraft_order(db, order.id)
    assert result_order.status == "processing"
    assert supplemented == {}
    assert get_stock(db, "part", p1.id) == 150.0
    assert db.query(InventoryLog).filter(
        InventoryLog.reason == "手工单缺货补进"
    ).count() == 0


def test_supplement_and_send_multi_parts(setup):
    """3 parts: 2 short, 1 enough. Only the 2 short ones get supplemented."""
    from services.handcraft import supplement_and_send_handcraft_order
    db, p1, p2, j1 = setup  # p1=200, p2=100
    # Create a third part with zero stock
    from services.part import create_part
    p3 = create_part(db, {"name": "扣子3", "category": "小配件"})
    order = create_handcraft_order(
        db, "手工坊",
        parts=[
            {"part_id": p1.id, "qty": 50},    # enough
            {"part_id": p2.id, "qty": 150},   # short by 50
            {"part_id": p3.id, "qty": 20},    # short by 20
        ],
        jewelries=[{"jewelry_id": j1.id, "qty": 5}],
    )
    _, supplemented = supplement_and_send_handcraft_order(db, order.id)
    assert supplemented == {p2.id: 50.0, p3.id: 20.0}


def test_supplement_and_send_aggregates_same_part(setup):
    """Same part_id in two part_items: supplement uses the aggregate total."""
    from services.handcraft import supplement_and_send_handcraft_order
    from services.inventory import get_stock
    db, p1, _, j1 = setup  # p1 has 200
    order = create_handcraft_order(
        db, "手工坊",
        parts=[
            {"part_id": p1.id, "qty": 150},
            {"part_id": p1.id, "qty": 100},   # total need = 250, short by 50
        ],
        jewelries=[{"jewelry_id": j1.id, "qty": 5}],
    )
    _, supplemented = supplement_and_send_handcraft_order(db, order.id)
    assert supplemented == {p1.id: 50.0}
    assert get_stock(db, "part", p1.id) == 0.0  # 200 + 50 - 250


def test_supplement_and_send_order_not_pending(setup):
    """Already-sent order must be rejected."""
    from services.handcraft import supplement_and_send_handcraft_order
    db, p1, _, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 50}],
        jewelries=[{"jewelry_id": j1.id, "qty": 5}],
    )
    send_handcraft_order(db, order.id)  # now processing
    with pytest.raises(ValueError, match="cannot be sent"):
        supplement_and_send_handcraft_order(db, order.id)


def test_supplement_and_send_order_not_found(db):
    from services.handcraft import supplement_and_send_handcraft_order
    with pytest.raises(ValueError, match="not found"):
        supplement_and_send_handcraft_order(db, "HC-9999")


def test_supplement_and_send_no_part_items(setup):
    """Order with no part_items must be rejected."""
    from services.handcraft import supplement_and_send_handcraft_order
    from models.handcraft_order import HandcraftOrder
    from time_utils import now_beijing
    db, _, _, _ = setup
    # Create an empty order manually (the normal creator requires parts)
    order = HandcraftOrder(
        id="HC-9000", supplier_name="测试", status="pending", created_at=now_beijing()
    )
    db.add(order)
    db.flush()
    with pytest.raises(ValueError, match="no part items"):
        supplement_and_send_handcraft_order(db, "HC-9000")


def test_supplement_and_send_uses_picking_actual_qty(setup):
    """When a part item has a 勾选'd picking actual_qty > pi.qty, supplement
    must top up to actual_qty (the amount send will deduct), not to pi.qty.
    Pre-fix: supplement adds (pi.qty - current), then send tries to deduct
    actual_qty, fails 库存不足 by exactly (actual_qty - pi.qty).
    """
    from services.handcraft import supplement_and_send_handcraft_order
    from models.handcraft_order import HandcraftPartItem
    from services.inventory import deduct_stock
    db, p1, _, j1 = setup  # p1 starts at 200
    # Drain p1 to 0 so any miscount surfaces immediately.
    deduct_stock(db, "part", p1.id, 200.0, "归零")
    assert get_stock(db, "part", p1.id) == 0.0

    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 100, "bom_qty": 100.0}],
        jewelries=[{"jewelry_id": j1.id, "qty": 1}],
    )
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).one()
    # picking 实际称重 = 105 (e.g. rounded up to a packaging unit)
    _seed_picking_actual_qty(db, order.id, pi.id, p1.id, 105.0)
    _mark_picked(db, order.id, pi.id, p1.id)

    result_order, supplemented = supplement_and_send_handcraft_order(db, order.id)
    assert result_order.status == "processing"
    # Must supplement to actual_qty=105, not pi.qty=100
    assert supplemented == {p1.id: 105.0}
    # Net: 0 + 105 (supplement) - 105 (send) = 0
    assert get_stock(db, "part", p1.id) == 0.0


# --- Picked-state gate + Edit sync (Bug 1 / Bug 2 fix coverage) ---


def _seed_picking_actual_qty(db, order_id, part_item_id, atom_part_id, qty):
    """Insert a HandcraftPickingWeight row with actual_qty (no record yet)."""
    from decimal import Decimal
    from models.handcraft_order import HandcraftPickingWeight
    db.add(HandcraftPickingWeight(
        handcraft_order_id=order_id,
        part_item_id=part_item_id,
        atom_part_id=atom_part_id,
        actual_qty=Decimal(str(qty)),
    ))
    db.flush()


def _mark_picked(db, order_id, part_item_id, atom_part_id):
    from models.handcraft_order import HandcraftPickingRecord
    db.add(HandcraftPickingRecord(
        handcraft_order_id=order_id,
        handcraft_part_item_id=part_item_id,
        part_id=atom_part_id,
    ))
    db.flush()


def test_actual_qty_without_picked_falls_back_to_pi_qty(setup):
    """Gate: actual_qty is set but the row was not 勾选'd → send uses pi.qty,
    not the override. Encodes the new spec: 填数字+未勾选=不采纳."""
    db, p1, _, j1 = setup
    order = create_handcraft_order(
        db, "GateSupp1",
        parts=[{"part_id": p1.id, "qty": 100.0}],
        jewelries=[{"jewelry_id": j1.id, "qty": 1}],
    )
    from models.handcraft_order import HandcraftPartItem
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).one()
    _seed_picking_actual_qty(db, order.id, pi.id, p1.id, 80.0)  # filled but not picked

    send_handcraft_order(db, order.id)
    # Pre-stock was 200; no gate would deduct 80 → 120 left.
    # With gate, deducts pi.qty=100 → 100 left.
    assert get_stock(db, "part", p1.id) == pytest.approx(100.0)


def test_actual_qty_with_picked_overrides_pi_qty(setup):
    """Gate positive case: filled + 勾选 → send uses actual_qty."""
    db, p1, _, j1 = setup
    order = create_handcraft_order(
        db, "GateSupp2",
        parts=[{"part_id": p1.id, "qty": 100.0}],
        jewelries=[{"jewelry_id": j1.id, "qty": 1}],
    )
    from models.handcraft_order import HandcraftPartItem
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).one()
    _seed_picking_actual_qty(db, order.id, pi.id, p1.id, 80.0)
    _mark_picked(db, order.id, pi.id, p1.id)

    send_handcraft_order(db, order.id)
    # Pre-stock 200, deduct effective 80 → 120 left.
    assert get_stock(db, "part", p1.id) == pytest.approx(120.0)


def test_update_handcraft_part_qty_overwrites_measured_actual_qty(setup):
    """Spec lock-in: Edit qty unconditionally overwrites actual_qty, even
    when actual_qty differs from the original pi.qty (i.e. the user
    measured something different during picking). Confirmed semantic — see
    conversation 2026-05-13. If this assumption changes, update the spec
    AND this test together."""
    from services.handcraft import update_handcraft_part
    from models.handcraft_order import HandcraftPartItem, HandcraftPickingWeight
    db, p1, _, j1 = setup
    order = create_handcraft_order(
        db, "MeasureSupp",
        parts=[{"part_id": p1.id, "qty": 100.0}],
        jewelries=[{"jewelry_id": j1.id, "qty": 1}],
    )
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).one()
    _seed_picking_actual_qty(db, order.id, pi.id, p1.id, 80.0)  # measured 80, planned 100
    _mark_picked(db, order.id, pi.id, p1.id)

    update_handcraft_part(db, order.id, pi.id, {"qty": 110.0})

    row = db.query(HandcraftPickingWeight).filter_by(
        part_item_id=pi.id, atom_part_id=p1.id,
    ).one()
    assert float(row.actual_qty) == pytest.approx(110.0)


def test_update_handcraft_part_qty_noop_leaves_actual_qty_alone(setup):
    """No-op PATCH (resubmitting the same qty) must not write to the
    picking_weight row. Without the equality check, idempotent client
    retries would churn the audit log and reset the override."""
    from services.handcraft import update_handcraft_part
    from models.handcraft_order import HandcraftPartItem, HandcraftPickingWeight
    db, p1, _, j1 = setup
    order = create_handcraft_order(
        db, "NoopSupp",
        parts=[{"part_id": p1.id, "qty": 100.0}],
        jewelries=[{"jewelry_id": j1.id, "qty": 1}],
    )
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).one()
    _seed_picking_actual_qty(db, order.id, pi.id, p1.id, 80.0)
    _mark_picked(db, order.id, pi.id, p1.id)

    update_handcraft_part(db, order.id, pi.id, {"qty": 100.0})  # same as current

    row = db.query(HandcraftPickingWeight).filter_by(
        part_item_id=pi.id, atom_part_id=p1.id,
    ).one()
    assert float(row.actual_qty) == pytest.approx(80.0)  # preserved


def test_update_handcraft_part_qty_syncs_actual_qty(setup):
    """Bug 1 fix: when picking has set actual_qty (and is picked), Edit qty
    must propagate to actual_qty so the override stays consistent."""
    from services.handcraft import update_handcraft_part
    from models.handcraft_order import HandcraftPartItem, HandcraftPickingWeight
    db, p1, _, j1 = setup
    order = create_handcraft_order(
        db, "EditSupp",
        parts=[{"part_id": p1.id, "qty": 100.0}],
        jewelries=[{"jewelry_id": j1.id, "qty": 1}],
    )
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).one()
    _seed_picking_actual_qty(db, order.id, pi.id, p1.id, 80.0)
    _mark_picked(db, order.id, pi.id, p1.id)

    update_handcraft_part(db, order.id, pi.id, {"qty": 110.0})

    row = db.query(HandcraftPickingWeight).filter_by(
        part_item_id=pi.id, atom_part_id=p1.id,
    ).one()
    assert float(row.actual_qty) == pytest.approx(110.0)


def test_export_payload_uses_effective_qty_when_picked(setup):
    """Bug 2 fix: PDF/Excel payload returns actual_qty when picked."""
    from services.handcraft_export import get_handcraft_export_payload
    from models.handcraft_order import HandcraftPartItem
    db, p1, _, j1 = setup
    order = create_handcraft_order(
        db, "ExportSupp1",
        parts=[{"part_id": p1.id, "qty": 100.0}],
        jewelries=[{"jewelry_id": j1.id, "qty": 1}],
    )
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).one()
    _seed_picking_actual_qty(db, order.id, pi.id, p1.id, 80.0)
    _mark_picked(db, order.id, pi.id, p1.id)

    payload = get_handcraft_export_payload(db, order.id)
    assert payload["details"][0]["qty"] == pytest.approx(80.0)


def test_export_payload_uses_pi_qty_when_not_picked(setup):
    """Gate: filled actual_qty but no 勾选 → export falls back to pi.qty."""
    from services.handcraft_export import get_handcraft_export_payload
    from models.handcraft_order import HandcraftPartItem
    db, p1, _, j1 = setup
    order = create_handcraft_order(
        db, "ExportSupp2",
        parts=[{"part_id": p1.id, "qty": 100.0}],
        jewelries=[{"jewelry_id": j1.id, "qty": 1}],
    )
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).one()
    _seed_picking_actual_qty(db, order.id, pi.id, p1.id, 80.0)  # no _mark_picked

    payload = get_handcraft_export_payload(db, order.id)
    assert payload["details"][0]["qty"] == pytest.approx(100.0)
