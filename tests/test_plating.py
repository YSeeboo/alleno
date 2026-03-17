import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.part import create_part
from services.inventory import add_stock, get_stock
from services.plating import (
    create_plating_order, send_plating_order, receive_plating_items,
    get_plating_order, list_plating_orders,
)


@pytest.fixture
def setup(db):
    p1 = create_part(db, {"name": "铜扣", "category": "小配件"})
    p2 = create_part(db, {"name": "银链", "category": "链条"})
    add_stock(db, "part", p1.id, 200.0, "入库")
    add_stock(db, "part", p2.id, 100.0, "入库")
    return db, p1, p2


def test_create_plating_order(setup):
    db, p1, p2 = setup
    order = create_plating_order(db, "金牌电镀厂", [
        {"part_id": p1.id, "qty": 100, "plating_method": "金色"},
        {"part_id": p2.id, "qty": 50, "plating_method": "银色"},
    ])
    assert order.id == "EP-0001"
    assert order.status == "pending"


def test_send_plating_order_deducts_stock(setup):
    db, p1, p2 = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 100, "plating_method": "金色"},
    ])
    send_plating_order(db, order.id)
    assert get_stock(db, "part", p1.id) == 100.0  # 200 - 100
    assert get_plating_order(db, order.id).status == "processing"


def test_send_plating_order_items_status(setup):
    db, p1, p2 = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 50, "plating_method": "金色"},
    ])
    send_plating_order(db, order.id)
    from models.plating_order import PlatingOrderItem
    items = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order.id
    ).all()
    assert all(i.status == "电镀中" for i in items)


def test_send_plating_order_insufficient_stock(setup):
    db, p1, p2 = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 300, "plating_method": "金色"},  # only 200
    ])
    with pytest.raises(ValueError, match="库存不足"):
        send_plating_order(db, order.id)
    # Stock must not have changed
    assert get_stock(db, "part", p1.id) == 200.0


def test_send_plating_order_partial_rollback(setup):
    """If second item fails, first item's deduction must be rolled back."""
    db, p1, p2 = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 100, "plating_method": "金色"},  # OK
        {"part_id": p2.id, "qty": 500, "plating_method": "银色"},  # FAIL
    ])
    with pytest.raises(ValueError, match="库存不足"):
        send_plating_order(db, order.id)
    assert get_stock(db, "part", p1.id) == 200.0  # rolled back
    assert get_stock(db, "part", p2.id) == 100.0  # untouched


def test_receive_plating_items_partial(setup):
    db, p1, p2 = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 100, "plating_method": "金色"},
    ])
    send_plating_order(db, order.id)
    from models.plating_order import PlatingOrderItem
    item = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order.id
    ).first()
    # Receive 50 of 100
    receive_plating_items(db, order.id, [{"plating_order_item_id": item.id, "qty": 50}])
    db.refresh(item)
    assert float(item.received_qty) == 50.0
    assert item.status == "电镀中"  # not yet complete
    assert get_stock(db, "part", p1.id) == 150.0  # 100 deducted, 50 returned


def test_receive_plating_items_completes_order(setup):
    db, p1, p2 = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 100, "plating_method": "金色"},
    ])
    send_plating_order(db, order.id)
    from models.plating_order import PlatingOrderItem
    item = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order.id
    ).first()
    # Receive in two batches
    receive_plating_items(db, order.id, [{"plating_order_item_id": item.id, "qty": 60}])
    receive_plating_items(db, order.id, [{"plating_order_item_id": item.id, "qty": 40}])
    db.refresh(item)
    db.refresh(order)
    assert item.status == "已收回"
    assert order.status == "completed"
    assert order.completed_at is not None


def test_list_plating_orders_filter(setup):
    db, p1, p2 = setup
    create_plating_order(db, "厂A", [{"part_id": p1.id, "qty": 10, "plating_method": "金色"}])
    create_plating_order(db, "厂B", [{"part_id": p2.id, "qty": 10, "plating_method": "银色"}])
    assert len(list_plating_orders(db)) == 2
    assert len(list_plating_orders(db, status="pending")) == 2
    assert len(list_plating_orders(db, status="processing")) == 0


def test_send_plating_order_twice_raises(setup):
    """Sending an already-processing order should raise ValueError."""
    db, p1, p2 = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 50, "plating_method": "金色"},
    ])
    send_plating_order(db, order.id)
    with pytest.raises(ValueError, match="cannot be sent"):
        send_plating_order(db, order.id)
    # Stock should only be deducted once
    assert get_stock(db, "part", p1.id) == 150.0  # 200 - 50
