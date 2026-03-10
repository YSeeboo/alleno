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
