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
