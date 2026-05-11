import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.inventory import add_stock, deduct_stock, get_stock, get_stock_log


def test_get_stock_empty(db):
    assert get_stock(db, "part", "PJ-0001") == 0.0


def test_add_stock_returns_log(db):
    log = add_stock(db, "part", "PJ-0001", 100.0, "入库")
    assert log.change_qty == 100.0
    assert log.item_type == "part"
    assert log.item_id == "PJ-0001"


def test_get_stock_after_add(db):
    add_stock(db, "part", "PJ-0001", 100.0, "入库")
    add_stock(db, "part", "PJ-0001", 50.0, "补货")
    assert get_stock(db, "part", "PJ-0001") == 150.0


def test_deduct_stock_success(db):
    add_stock(db, "part", "PJ-0001", 100.0, "入库")
    log = deduct_stock(db, "part", "PJ-0001", 30.0, "出库")
    assert log.change_qty == -30.0
    assert get_stock(db, "part", "PJ-0001") == 70.0


def test_deduct_stock_insufficient(db):
    add_stock(db, "part", "PJ-0001", 10.0, "入库")
    with pytest.raises(ValueError, match="库存不足"):
        deduct_stock(db, "part", "PJ-0001", 20.0, "出库")


def test_get_stock_log_order(db):
    add_stock(db, "part", "PJ-0001", 100.0, "入库")
    add_stock(db, "part", "PJ-0001", 50.0, "补货")
    logs = get_stock_log(db, "part", "PJ-0001")
    assert len(logs) == 2
    # descending by created_at (or id as proxy for insertion order)
    assert logs[0].change_qty == 50.0
    assert logs[1].change_qty == 100.0


def test_get_stock_isolates_item_type(db):
    """part and jewelry stock are independent."""
    add_stock(db, "part", "PJ-0001", 100.0, "入库")
    assert get_stock(db, "jewelry", "PJ-0001") == 0.0


def test_add_stock_rejects_zero(db):
    with pytest.raises(ValueError, match="qty must be positive"):
        add_stock(db, "part", "PJ-0001", 0, "invalid")


def test_deduct_stock_rejects_negative(db):
    with pytest.raises(ValueError, match="qty must be positive"):
        deduct_stock(db, "part", "PJ-0001", -5, "invalid")


def test_supplement_shortfall_skips_when_enough(db):
    from services.inventory import supplement_shortfall, add_stock, get_stock
    from services.part import create_part
    p = create_part(db, {"name": "扣子", "category": "小配件"})
    add_stock(db, "part", p.id, 100.0, "入库")
    result = supplement_shortfall(
        db, "part", {p.id: 50.0}, reason="手工单缺货补进", note="HC-0001"
    )
    assert result == {}
    assert get_stock(db, "part", p.id) == 100.0  # unchanged


def test_supplement_shortfall_partial(db):
    from services.inventory import supplement_shortfall, add_stock, get_stock
    from services.part import create_part
    p1 = create_part(db, {"name": "扣子", "category": "小配件"})
    p2 = create_part(db, {"name": "链", "category": "链条"})
    p3 = create_part(db, {"name": "吊", "category": "吊坠"})
    add_stock(db, "part", p1.id, 100.0, "入库")   # enough for needs=50
    add_stock(db, "part", p2.id, 30.0, "入库")    # short for needs=50 by 20
    # p3 has zero stock; needs=10 → supplement 10
    result = supplement_shortfall(
        db, "part",
        {p1.id: 50.0, p2.id: 50.0, p3.id: 10.0},
        reason="手工单缺货补进", note="HC-0001",
    )
    assert result == {p2.id: 20.0, p3.id: 10.0}
    assert get_stock(db, "part", p1.id) == 100.0
    assert get_stock(db, "part", p2.id) == 50.0   # 30 + 20
    assert get_stock(db, "part", p3.id) == 10.0
    # Verify the log entries are tagged correctly
    from models.inventory_log import InventoryLog
    logs = (
        db.query(InventoryLog)
        .filter(InventoryLog.reason == "手工单缺货补进")
        .order_by(InventoryLog.id)
        .all()
    )
    assert [(l.item_id, float(l.change_qty), l.note) for l in logs] == [
        (p2.id, 20.0, "HC-0001"),
        (p3.id, 10.0, "HC-0001"),
    ]
