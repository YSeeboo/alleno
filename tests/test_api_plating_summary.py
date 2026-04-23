from datetime import date, timedelta
from decimal import Decimal

import pytest

from models.plating_order import PlatingOrder, PlatingOrderItem
from models.part import Part
from models.plating_receipt import PlatingReceipt, PlatingReceiptItem
from models.production_loss import ProductionLoss
from services.plating_summary import list_dispatched, list_received
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


def _make_receipt(db, rid: str, vendor: str, *, days_ago: int = 0):
    created = now_beijing() - timedelta(days=days_ago)
    r = PlatingReceipt(id=rid, vendor_name=vendor, status="未付款", created_at=created)
    db.add(r); db.flush()
    return r


def _make_receipt_item(db, *, receipt_id: str, plating_order_item_id: int,
                       part_id: str, qty: float, price: float = 1.0):
    ri = PlatingReceiptItem(
        plating_receipt_id=receipt_id,
        plating_order_item_id=plating_order_item_id,
        part_id=part_id,
        qty=Decimal(str(qty)),
        price=Decimal(str(price)),
        amount=Decimal(str(qty * price)),
        unit="件",
    )
    db.add(ri); db.flush()
    return ri


def _make_loss(db, *, order_id: str, item_id: int, loss_qty: float, part_id: str):
    pl = ProductionLoss(
        order_type="plating", order_id=order_id, item_id=item_id,
        item_type="plating_item", part_id=part_id,
        loss_qty=Decimal(str(loss_qty)),
    )
    db.add(pl); db.flush()
    return pl


def test_list_received_inclusion_excludes_zero_received(db):
    _make_part(db, "PJ-DZ-R1")
    _make_part(db, "PJ-DZ-R2")
    _make_order(db, "EP-R1", "厂A", days_ago=2)
    _make_item(db, order_id="EP-R1", part_id="PJ-DZ-R1", qty=10, received=0)
    _make_order(db, "EP-R2", "厂A", days_ago=2)
    it2 = _make_item(db, order_id="EP-R2", part_id="PJ-DZ-R2", qty=10, received=5)

    items, total = list_received(db)
    assert total == 1
    assert items[0]["plating_order_item_id"] == it2.id


def test_list_received_actual_vs_loss_split(db):
    _make_part(db, "PJ-DZ-S1")
    _make_order(db, "EP-S1", "厂", days_ago=2)
    poi = _make_item(db, order_id="EP-S1", part_id="PJ-DZ-S1", qty=10, received=8)
    _make_receipt(db, "ER-S1", "厂", days_ago=1)
    _make_receipt_item(db, receipt_id="ER-S1", plating_order_item_id=poi.id,
                       part_id="PJ-DZ-S1", qty=5)
    _make_loss(db, order_id="EP-S1", item_id=poi.id, loss_qty=3, part_id="PJ-DZ-S1")

    items, _ = list_received(db)
    assert items[0]["actual_received_qty"] == 5
    assert items[0]["loss_total_qty"] == 3
    assert items[0]["unreceived_qty"] == 2


def test_list_received_loss_state(db):
    _make_part(db, "PJ-DZ-N1")
    _make_order(db, "EP-N1", "厂", days_ago=2)
    poi1 = _make_item(db, order_id="EP-N1", part_id="PJ-DZ-N1", qty=5, received=5)
    _make_receipt(db, "ER-N1", "厂", days_ago=1)
    _make_receipt_item(db, receipt_id="ER-N1", plating_order_item_id=poi1.id,
                       part_id="PJ-DZ-N1", qty=5)

    _make_part(db, "PJ-DZ-P1")
    _make_order(db, "EP-P1", "厂", days_ago=2)
    poi2 = _make_item(db, order_id="EP-P1", part_id="PJ-DZ-P1", qty=10, received=5)
    _make_receipt(db, "ER-P1", "厂", days_ago=1)
    _make_receipt_item(db, receipt_id="ER-P1", plating_order_item_id=poi2.id,
                       part_id="PJ-DZ-P1", qty=5)

    _make_part(db, "PJ-DZ-C1")
    _make_order(db, "EP-C1", "厂", days_ago=2)
    poi3 = _make_item(db, order_id="EP-C1", part_id="PJ-DZ-C1", qty=10, received=10)
    _make_receipt(db, "ER-C1", "厂", days_ago=1)
    _make_receipt_item(db, receipt_id="ER-C1", plating_order_item_id=poi3.id,
                       part_id="PJ-DZ-C1", qty=8)
    _make_loss(db, order_id="EP-C1", item_id=poi3.id, loss_qty=2, part_id="PJ-DZ-C1")

    items, _ = list_received(db)
    by_id = {i["plating_order_item_id"]: i for i in items}
    assert by_id[poi1.id]["loss_state"] == "none"
    assert by_id[poi2.id]["loss_state"] == "pending"
    assert by_id[poi3.id]["loss_state"] == "confirmed"


def test_list_received_multi_receipt_aggregation(db):
    _make_part(db, "PJ-DZ-M1")
    _make_order(db, "EP-M1", "厂", days_ago=10)
    poi = _make_item(db, order_id="EP-M1", part_id="PJ-DZ-M1", qty=10, received=8)
    _make_receipt(db, "ER-M1", "厂", days_ago=5)
    _make_receipt_item(db, receipt_id="ER-M1", plating_order_item_id=poi.id,
                       part_id="PJ-DZ-M1", qty=3)
    _make_receipt(db, "ER-M2", "厂", days_ago=2)
    _make_receipt_item(db, receipt_id="ER-M2", plating_order_item_id=poi.id,
                       part_id="PJ-DZ-M1", qty=5)

    items, _ = list_received(db)
    item = items[0]
    assert [r["receipt_id"] for r in item["receipts"]] == ["ER-M2", "ER-M1"]
    assert item["latest_receipt_id"] == "ER-M2"
    assert item["actual_received_qty"] == 8


def test_list_received_full_loss_no_receipt_appears(db):
    _make_part(db, "PJ-DZ-F1")
    _make_order(db, "EP-F1", "厂", days_ago=2)
    poi = _make_item(db, order_id="EP-F1", part_id="PJ-DZ-F1", qty=10, received=10)
    _make_loss(db, order_id="EP-F1", item_id=poi.id, loss_qty=10, part_id="PJ-DZ-F1")

    items, total = list_received(db)
    assert total == 1
    assert items[0]["actual_received_qty"] == 0
    assert items[0]["loss_total_qty"] == 10
    assert items[0]["unreceived_qty"] == 0
    assert items[0]["loss_state"] == "confirmed"
    assert items[0]["receipts"] == []
    assert items[0]["latest_receipt_id"] is None


def test_list_received_date_range_filter_on_receipt_date(db):
    _make_part(db, "PJ-DZ-DR1")
    _make_part(db, "PJ-DZ-DR2")
    _make_order(db, "EP-DR1", "厂", days_ago=20)
    poi1 = _make_item(db, order_id="EP-DR1", part_id="PJ-DZ-DR1", qty=5, received=5)
    _make_receipt(db, "ER-DR1", "厂", days_ago=15)
    _make_receipt_item(db, receipt_id="ER-DR1", plating_order_item_id=poi1.id,
                       part_id="PJ-DZ-DR1", qty=5)

    _make_order(db, "EP-DR2", "厂", days_ago=10)
    poi2 = _make_item(db, order_id="EP-DR2", part_id="PJ-DZ-DR2", qty=5, received=5)
    _make_receipt(db, "ER-DR2", "厂", days_ago=2)
    _make_receipt_item(db, receipt_id="ER-DR2", plating_order_item_id=poi2.id,
                       part_id="PJ-DZ-DR2", qty=5)

    today = now_beijing().date()
    items, total = list_received(db, date_from=today - timedelta(days=5))
    assert total == 1
    assert items[0]["plating_order_item_id"] == poi2.id


def test_list_received_pagination(db):
    for i in range(5):
        pid = f"PJ-DZ-RP{i}"
        _make_part(db, pid)
        _make_order(db, f"EP-RP{i}", "厂", days_ago=i)
        poi = _make_item(db, order_id=f"EP-RP{i}", part_id=pid, qty=5, received=5)
        _make_receipt(db, f"ER-RP{i}", "厂", days_ago=i)
        _make_receipt_item(db, receipt_id=f"ER-RP{i}", plating_order_item_id=poi.id,
                           part_id=pid, qty=5)
    items, total = list_received(db, skip=2, limit=2)
    assert total == 5
    assert len(items) == 2


def test_api_dispatched_smoke(client, db):
    _make_part(db, "PJ-DZ-API1")
    _make_order(db, "EP-API1", "厂A", days_ago=2)
    _make_item(db, order_id="EP-API1", part_id="PJ-DZ-API1", qty=5)

    resp = client.get("/api/plating-summary/dispatched")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["plating_order_id"] == "EP-API1"
    assert body["items"][0]["is_completed"] is False


def test_api_dispatched_filters_pass_through(client, db):
    _make_part(db, "PJ-DZ-API2")
    _make_part(db, "PJ-DZ-API3")
    _make_order(db, "EP-API2", "厂A", days_ago=2)
    _make_item(db, order_id="EP-API2", part_id="PJ-DZ-API2", qty=5)
    _make_order(db, "EP-API3", "厂B", days_ago=2)
    _make_item(db, order_id="EP-API3", part_id="PJ-DZ-API3", qty=5)

    resp = client.get("/api/plating-summary/dispatched", params={"supplier_name": "厂A"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_api_received_smoke(client, db):
    _make_part(db, "PJ-DZ-RA1")
    _make_order(db, "EP-RA1", "厂", days_ago=2)
    poi = _make_item(db, order_id="EP-RA1", part_id="PJ-DZ-RA1", qty=5, received=5)
    _make_receipt(db, "ER-RA1", "厂", days_ago=1)
    _make_receipt_item(db, receipt_id="ER-RA1", plating_order_item_id=poi.id,
                       part_id="PJ-DZ-RA1", qty=5)

    resp = client.get("/api/plating-summary/received")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["loss_state"] == "none"
    assert body["items"][0]["latest_receipt_id"] == "ER-RA1"
