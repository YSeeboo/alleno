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
