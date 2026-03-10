import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.part import create_part
from services.jewelry import create_jewelry
from services.bom import set_bom
from services.order import create_order, get_order, get_order_items, get_parts_summary, update_order_status


@pytest.fixture
def setup(db):
    p1 = create_part(db, {"name": "铜扣"})
    p2 = create_part(db, {"name": "链条"})
    j1 = create_jewelry(db, {"name": "玫瑰戒指"})
    j2 = create_jewelry(db, {"name": "银耳环"})
    set_bom(db, j1.id, p1.id, 2.0)
    set_bom(db, j1.id, p2.id, 1.0)
    set_bom(db, j2.id, p1.id, 1.0)
    return db, p1, p2, j1, j2


def test_create_order_id(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "张三", [
        {"jewelry_id": j1.id, "quantity": 2, "unit_price": 100.0}
    ])
    assert order.id == "OR-0001"
    assert order.customer_name == "张三"
    assert float(order.total_amount) == 200.0


def test_create_order_total_amount(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "李四", [
        {"jewelry_id": j1.id, "quantity": 3, "unit_price": 100.0},
        {"jewelry_id": j2.id, "quantity": 2, "unit_price": 50.0},
    ])
    assert float(order.total_amount) == 400.0


def test_get_order_items(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "张三", [
        {"jewelry_id": j1.id, "quantity": 2, "unit_price": 100.0},
        {"jewelry_id": j2.id, "quantity": 1, "unit_price": 50.0},
    ])
    items = get_order_items(db, order.id)
    assert len(items) == 2


def test_get_parts_summary(setup):
    db, p1, p2, j1, j2 = setup
    # j1 needs 2*p1 + 1*p2 per unit; j2 needs 1*p1 per unit
    # order: 2 j1, 3 j2
    order = create_order(db, "张三", [
        {"jewelry_id": j1.id, "quantity": 2, "unit_price": 100.0},
        {"jewelry_id": j2.id, "quantity": 3, "unit_price": 50.0},
    ])
    summary = get_parts_summary(db, order.id)
    # p1: 2*2 + 3*1 = 7
    # p2: 2*1 = 2
    assert summary[p1.id] == 7.0
    assert summary[p2.id] == 2.0


def test_get_parts_summary_no_bom(setup):
    """Jewelry without BOM should be silently skipped."""
    db, p1, p2, j1, j2 = setup
    j3 = create_jewelry(db, {"name": "无BOM饰品"})
    order = create_order(db, "王五", [
        {"jewelry_id": j3.id, "quantity": 1, "unit_price": 10.0},
    ])
    summary = get_parts_summary(db, order.id)
    assert summary == {}


def test_update_order_status_valid(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "张三", [{"jewelry_id": j1.id, "quantity": 1, "unit_price": 10.0}])
    updated = update_order_status(db, order.id, "生产中")
    assert updated.status == "生产中"


def test_update_order_status_invalid(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "张三", [{"jewelry_id": j1.id, "quantity": 1, "unit_price": 10.0}])
    with pytest.raises(ValueError, match="Invalid status"):
        update_order_status(db, order.id, "取消")
