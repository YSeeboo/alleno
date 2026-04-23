from datetime import date, timedelta
from decimal import Decimal

import pytest

from models.plating_order import PlatingOrder, PlatingOrderItem
from models.part import Part
from services.plating_summary import list_dispatched
from time_utils import now_beijing


def _make_part(db, pid: str, name: str = "测试配件"):
    p = Part(id=pid, name=name, category="吊坠", unit="件")
    db.add(p); db.flush()
    return p


def _make_order(db, oid: str, supplier: str, *, days_ago: int = 0):
    created = now_beijing() - timedelta(days=days_ago)
    o = PlatingOrder(id=oid, supplier_name=supplier, status="processing", created_at=created)
    db.add(o); db.flush()
    return o


def _make_item(db, *, order_id: str, part_id: str, qty: float, received: float = 0):
    it = PlatingOrderItem(
        plating_order_id=order_id, part_id=part_id,
        qty=Decimal(str(qty)), received_qty=Decimal(str(received)),
        status="电镀中" if received < qty else "已收回",
        plating_method="G", unit="件",
    )
    db.add(it); db.flush()
    return it


def test_list_dispatched_empty(db):
    items, total = list_dispatched(db)
    assert items == []
    assert total == 0


def test_list_dispatched_default_sort_partition(db):
    """Completed items sink to bottom; within each partition, dispatch date desc."""
    _make_part(db, "PJ-DZ-00001")
    _make_part(db, "PJ-DZ-00002")
    _make_part(db, "PJ-DZ-00003")

    # Order A: 10 days ago, in-progress (qty 10, received 5)
    _make_order(db, "EP-0001", "厂A", days_ago=10)
    _make_item(db, order_id="EP-0001", part_id="PJ-DZ-00001", qty=10, received=5)

    # Order B: 1 day ago, in-progress (qty 5, received 0)
    _make_order(db, "EP-0002", "厂B", days_ago=1)
    _make_item(db, order_id="EP-0002", part_id="PJ-DZ-00002", qty=5, received=0)

    # Order C: 5 days ago, completed (qty 8, received 8)
    _make_order(db, "EP-0003", "厂C", days_ago=5)
    _make_item(db, order_id="EP-0003", part_id="PJ-DZ-00003", qty=8, received=8)

    items, total = list_dispatched(db)
    assert total == 3
    # Order: in-progress B (newer) → in-progress A (older) → completed C
    assert [i["plating_order_id"] for i in items] == ["EP-0002", "EP-0001", "EP-0003"]
    assert [i["is_completed"] for i in items] == [False, False, True]


def test_list_dispatched_supplier_filter(db):
    _make_part(db, "PJ-DZ-A1")
    _make_part(db, "PJ-DZ-A2")
    _make_order(db, "EP-A1", "厂A", days_ago=2)
    _make_item(db, order_id="EP-A1", part_id="PJ-DZ-A1", qty=5)
    _make_order(db, "EP-A2", "厂B", days_ago=2)
    _make_item(db, order_id="EP-A2", part_id="PJ-DZ-A2", qty=5)

    items, total = list_dispatched(db, supplier_name="厂A")
    assert total == 1
    assert items[0]["supplier_name"] == "厂A"


def test_list_dispatched_date_range_filter(db):
    _make_part(db, "PJ-DZ-D1")
    _make_part(db, "PJ-DZ-D2")
    _make_order(db, "EP-D1", "厂", days_ago=10)
    _make_item(db, order_id="EP-D1", part_id="PJ-DZ-D1", qty=5)
    _make_order(db, "EP-D2", "厂", days_ago=2)
    _make_item(db, order_id="EP-D2", part_id="PJ-DZ-D2", qty=5)

    today = now_beijing().date()
    items, total = list_dispatched(db, date_from=today - timedelta(days=5))
    assert total == 1
    assert items[0]["plating_order_id"] == "EP-D2"


def test_list_dispatched_keyword_filter(db):
    _make_part(db, "PJ-DZ-K1", name="圆形吊坠")
    _make_part(db, "PJ-DZ-K2", name="椭圆吊坠")
    _make_order(db, "EP-K1", "厂", days_ago=2)
    _make_item(db, order_id="EP-K1", part_id="PJ-DZ-K1", qty=5)
    _make_order(db, "EP-K2", "厂", days_ago=2)
    _make_item(db, order_id="EP-K2", part_id="PJ-DZ-K2", qty=5)

    items, total = list_dispatched(db, part_keyword="圆形")
    assert total == 1
    assert items[0]["part_name"] == "圆形吊坠"


def test_list_dispatched_sort_days_out_flattens_partition(db):
    """When sort=days_out_desc, completed items are NOT pushed to bottom."""
    _make_part(db, "PJ-DZ-S1")
    _make_part(db, "PJ-DZ-S2")
    _make_part(db, "PJ-DZ-S3")
    _make_order(db, "EP-S1", "厂", days_ago=20)
    _make_item(db, order_id="EP-S1", part_id="PJ-DZ-S1", qty=5, received=5)
    _make_order(db, "EP-S2", "厂", days_ago=10)
    _make_item(db, order_id="EP-S2", part_id="PJ-DZ-S2", qty=5, received=0)
    _make_order(db, "EP-S3", "厂", days_ago=2)
    _make_item(db, order_id="EP-S3", part_id="PJ-DZ-S3", qty=5, received=0)

    items, total = list_dispatched(db, sort="days_out_desc")
    assert [i["plating_order_id"] for i in items] == ["EP-S2", "EP-S3", "EP-S1"]


def test_list_dispatched_pagination(db):
    for i in range(5):
        pid = f"PJ-DZ-P{i}"
        _make_part(db, pid)
        _make_order(db, f"EP-P{i}", "厂", days_ago=i)
        _make_item(db, order_id=f"EP-P{i}", part_id=pid, qty=5)
    items, total = list_dispatched(db, skip=2, limit=2)
    assert total == 5
    assert len(items) == 2
