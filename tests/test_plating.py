import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.part import create_part
from services.inventory import add_stock, get_stock
from services.plating import (
    create_plating_order, send_plating_order,
    get_plating_order, list_plating_orders, update_plating_delivery_images,
)
from services.plating_receipt import create_plating_receipt


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
    # Receive 50 of 100 via plating receipt
    create_plating_receipt(db, "厂A", [{"plating_order_item_id": item.id, "part_id": p1.id, "qty": 50}])
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
    # Receive in two batches via plating receipts
    create_plating_receipt(db, "厂A", [{"plating_order_item_id": item.id, "part_id": p1.id, "qty": 60}])
    create_plating_receipt(db, "厂A", [{"plating_order_item_id": item.id, "part_id": p1.id, "qty": 40}])
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


def test_update_plating_delivery_images(setup):
    db, p1, _ = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 20, "plating_method": "金色"},
    ])

    update_plating_delivery_images(db, order.id, ["https://img.test/a.png", " https://img.test/b.png "])
    db.refresh(order)

    assert order.delivery_images == ["https://img.test/a.png", "https://img.test/b.png"]


def test_update_plating_delivery_images_rejects_more_than_four(setup):
    db, p1, _ = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 20, "plating_method": "金色"},
    ])

    with pytest.raises(ValueError, match="最多上传 10 张"):
        update_plating_delivery_images(db, order.id, [
            f"{i}.png" for i in range(11)
        ])


def test_supplement_and_send_normal(setup):
    """1 part short by 5; supplement should write 1 缺货补进 log + 1 电镀发出 log."""
    from services.plating import supplement_and_send_plating_order
    from services.inventory import get_stock
    from models.inventory_log import InventoryLog
    db, p1, _ = setup  # p1 has 200 stock from fixture
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 205, "plating_method": "金色"},  # short by 5
    ])
    result_order, supplemented = supplement_and_send_plating_order(db, order.id)
    assert result_order.status == "processing"
    assert supplemented == {p1.id: 5.0}
    assert get_stock(db, "part", p1.id) == 0.0  # 200 + 5 - 205
    logs = (
        db.query(InventoryLog)
        .filter(InventoryLog.item_id == p1.id)
        .order_by(InventoryLog.id)
        .all()
    )
    reasons = [(l.reason, float(l.change_qty), l.note) for l in logs]
    assert reasons[1] == ("电镀单缺货补进", 5.0, order.id)
    assert reasons[2][0] == "电镀发出"
    assert reasons[2][1] == -205.0


def test_supplement_and_send_no_shortage(setup):
    from services.plating import supplement_and_send_plating_order
    from services.inventory import get_stock
    from models.inventory_log import InventoryLog
    db, p1, _ = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 50, "plating_method": "金色"},
    ])
    _, supplemented = supplement_and_send_plating_order(db, order.id)
    assert supplemented == {}
    assert get_stock(db, "part", p1.id) == 150.0
    assert db.query(InventoryLog).filter(
        InventoryLog.reason == "电镀单缺货补进"
    ).count() == 0


def test_supplement_and_send_multi_parts(setup):
    from services.plating import supplement_and_send_plating_order
    from services.part import create_part
    db, p1, p2 = setup  # p1=200, p2=100
    p3 = create_part(db, {"name": "扣3", "category": "小配件"})
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 50, "plating_method": "金色"},   # enough
        {"part_id": p2.id, "qty": 150, "plating_method": "金色"},  # short 50
        {"part_id": p3.id, "qty": 20, "plating_method": "金色"},   # short 20
    ])
    _, supplemented = supplement_and_send_plating_order(db, order.id)
    assert supplemented == {p2.id: 50.0, p3.id: 20.0}


def test_supplement_and_send_aggregates_same_part(setup):
    from services.plating import supplement_and_send_plating_order
    from services.inventory import get_stock
    db, p1, _ = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 150, "plating_method": "金色"},
        {"part_id": p1.id, "qty": 100, "plating_method": "银色"},
    ])
    _, supplemented = supplement_and_send_plating_order(db, order.id)
    assert supplemented == {p1.id: 50.0}
    assert get_stock(db, "part", p1.id) == 0.0


def test_supplement_and_send_order_not_pending(setup):
    from services.plating import supplement_and_send_plating_order
    db, p1, _ = setup
    order = create_plating_order(db, "厂A", [
        {"part_id": p1.id, "qty": 50, "plating_method": "金色"},
    ])
    send_plating_order(db, order.id)
    with pytest.raises(ValueError, match="cannot be sent"):
        supplement_and_send_plating_order(db, order.id)


def test_supplement_and_send_order_not_found(db):
    from services.plating import supplement_and_send_plating_order
    with pytest.raises(ValueError, match="not found"):
        supplement_and_send_plating_order(db, "EP-9999")


def test_supplement_and_send_no_items(setup):
    """Order with no items must be rejected."""
    from services.plating import supplement_and_send_plating_order
    from models.plating_order import PlatingOrder
    from time_utils import now_beijing
    db, _, _ = setup
    order = PlatingOrder(
        id="EP-9000", supplier_name="测试", status="pending", created_at=now_beijing()
    )
    db.add(order)
    db.flush()
    with pytest.raises(ValueError, match="no items"):
        supplement_and_send_plating_order(db, "EP-9000")
