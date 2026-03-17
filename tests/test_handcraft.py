import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock, get_stock
from services.handcraft import (
    create_handcraft_order, send_handcraft_order, receive_handcraft_jewelries,
    get_handcraft_order, list_handcraft_orders,
)


@pytest.fixture
def setup(db):
    p1 = create_part(db, {"name": "铜扣", "category": "小配件"})
    p2 = create_part(db, {"name": "银链", "category": "链条"})
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
    assert order.id == "HC-0001"
    assert order.status == "pending"


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
    receive_handcraft_jewelries(db, order.id, [{"handcraft_jewelry_item_id": ji.id, "qty": 6}])
    db.refresh(ji)
    assert ji.received_qty == 6
    assert ji.status == "制作中"  # not yet complete
    assert get_stock(db, "jewelry", j1.id) == 6.0


def test_receive_handcraft_jewelries_completes_order(setup):
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
    receive_handcraft_jewelries(db, order.id, [{"handcraft_jewelry_item_id": ji.id, "qty": 6}])
    receive_handcraft_jewelries(db, order.id, [{"handcraft_jewelry_item_id": ji.id, "qty": 4}])
    db.refresh(ji)
    db.refresh(order)
    assert ji.status == "已收回"
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
