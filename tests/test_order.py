import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.part import create_part
from services.jewelry import create_jewelry
from services.bom import set_bom
from services.order import create_order, get_order, get_order_items, get_parts_summary, update_order_status


@pytest.fixture
def setup(db):
    p1 = create_part(db, {"name": "铜扣", "category": "小配件"})
    p2 = create_part(db, {"name": "银链", "category": "链条"})
    j1 = create_jewelry(db, {"name": "玫瑰戒指", "category": "单件"})
    j2 = create_jewelry(db, {"name": "银耳环", "category": "单对"})
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
    summary_map = {s["part_id"]: s["total_qty"] for s in summary}
    assert summary_map[p1.id] == 7.0
    assert summary_map[p2.id] == 2.0


def test_get_parts_summary_no_bom(setup):
    """Jewelry without BOM should be silently skipped."""
    db, p1, p2, j1, j2 = setup
    j3 = create_jewelry(db, {"name": "无BOM饰品", "category": "单件"})
    order = create_order(db, "王五", [
        {"jewelry_id": j3.id, "quantity": 1, "unit_price": 10.0},
    ])
    summary = get_parts_summary(db, order.id)
    assert summary == []


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


from services.order import delete_order, get_order_delete_preview
from services.order_todo import create_batch
from services.picking import mark_picked


def test_delete_pending_order_removes_order_and_items(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "张三", [
        {"jewelry_id": j1.id, "quantity": 2, "unit_price": 100.0},
        {"part_id": p1.id, "quantity": 5, "unit_price": 3.0},
    ])
    oid = order.id
    delete_order(db, oid)
    assert get_order(db, oid) is None
    assert get_order_items(db, oid) == []


def test_delete_order_rejects_non_pending(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "李四", [
        {"part_id": p1.id, "quantity": 1, "unit_price": 3.0},
    ])
    from services.inventory import add_stock
    add_stock(db, "part", p1.id, 10, "测试入库")
    update_order_status(db, order.id, "已完成")
    with pytest.raises(ValueError, match="待生产"):
        delete_order(db, order.id)
    assert get_order(db, order.id) is not None


def test_delete_order_not_found(setup):
    db, *_ = setup
    with pytest.raises(ValueError, match="不存在|not found|OR-9999"):
        delete_order(db, "OR-9999")


def test_delete_order_cascades_picking_records(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "王五", [
        {"part_id": p1.id, "quantity": 2, "unit_price": 3.0},
    ])
    mark_picked(db, order.id, p1.id, 2.0)
    from models.order import OrderPickingRecord
    assert db.query(OrderPickingRecord).filter_by(order_id=order.id).count() == 1
    delete_order(db, order.id)
    assert db.query(OrderPickingRecord).filter_by(order_id=order.id).count() == 0


def test_delete_order_after_revert_from_completed(setup):
    """已完成会生成成本快照；回退到待生产后快照仍在。删除时必须连带清理，
    否则 order_cost_snapshot 的外键会导致删除报错。"""
    db, p1, p2, j1, j2 = setup
    from services.inventory import add_stock
    add_stock(db, "part", p1.id, 100, "测试入库")
    order = create_order(db, "钱七", [
        {"part_id": p1.id, "quantity": 3, "unit_price": 3.0},
    ])
    update_order_status(db, order.id, "已完成")  # 生成快照
    from models.order_cost_snapshot import OrderCostSnapshot
    assert db.query(OrderCostSnapshot).filter_by(order_id=order.id).count() == 1
    update_order_status(db, order.id, "待生产")  # 回退，快照仍在
    delete_order(db, order.id)
    assert get_order(db, order.id) is None
    assert db.query(OrderCostSnapshot).filter_by(order_id=order.id).count() == 0


def test_delete_preview_counts(setup):
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "赵六", [
        {"jewelry_id": j1.id, "quantity": 1, "unit_price": 100.0},
        {"part_id": p1.id, "quantity": 2, "unit_price": 3.0},
    ])
    preview = get_order_delete_preview(db, order.id)
    assert preview["item_count"] == 2
    assert preview["batch_count"] == 0
    assert preview["link_count"] == 0


def test_delete_order_cascades_todo_batch(setup):
    """待生产订单已排了备货批次时，删除必须连带清掉 batch / batch_jewelry /
    todo_item，否则外键报错。这是 delete_order 中最复杂的级联路径。"""
    db, p1, p2, j1, j2 = setup
    order = create_order(db, "孙八", [
        {"jewelry_id": j1.id, "quantity": 2, "unit_price": 100.0},
    ])
    create_batch(db, order.id, [(j1.id, 1)])

    from models.order import OrderTodoBatch, OrderTodoBatchJewelry, OrderTodoItem
    assert db.query(OrderTodoBatch).filter_by(order_id=order.id).count() == 1
    assert db.query(OrderTodoItem).filter_by(order_id=order.id).count() > 0
    batch_ids = [b.id for b in db.query(OrderTodoBatch).filter_by(order_id=order.id).all()]
    assert db.query(OrderTodoBatchJewelry).filter(
        OrderTodoBatchJewelry.batch_id.in_(batch_ids)
    ).count() == 1

    assert get_order_delete_preview(db, order.id)["batch_count"] == 1

    delete_order(db, order.id)

    assert get_order(db, order.id) is None
    assert db.query(OrderTodoBatch).filter_by(order_id=order.id).count() == 0
    assert db.query(OrderTodoItem).filter_by(order_id=order.id).count() == 0
    assert db.query(OrderTodoBatchJewelry).filter(
        OrderTodoBatchJewelry.batch_id.in_(batch_ids)
    ).count() == 0
