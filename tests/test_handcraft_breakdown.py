import pytest


@pytest.fixture
def hc_with_mixed_breakdown(db):
    """HC-MIX with: A客户·1000 (from OR-A), B客户·1200 (from OR-B), C客户·200 (manual).
    All three rows are jewelry_id=SP-MIX."""
    from models.order import Order, OrderItemLink
    from models.jewelry import Jewelry
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    from services.handcraft import _gen_receipt_code

    db.add(Jewelry(id="SP-MIX", name="混合测试", category="吊坠"))
    db.flush()

    hc = HandcraftOrder(id="HC-MIX", supplier_name="王", status="pending",
                        receipt_code=_gen_receipt_code(db))
    db.add(hc)
    db.flush()

    db.add(Order(id="OR-A", customer_name="A客户", status="待生产"))
    db.add(Order(id="OR-B", customer_name="B客户", status="待生产"))
    db.flush()

    j1 = HandcraftJewelryItem(handcraft_order_id="HC-MIX", jewelry_id="SP-MIX",
                              qty=1000, received_qty=0, status="未送出", unit="套",
                              customer_name=None)
    j2 = HandcraftJewelryItem(handcraft_order_id="HC-MIX", jewelry_id="SP-MIX",
                              qty=1200, received_qty=0, status="未送出", unit="套",
                              customer_name=None)
    j3 = HandcraftJewelryItem(handcraft_order_id="HC-MIX", jewelry_id="SP-MIX",
                              qty=200, received_qty=0, status="未送出", unit="套",
                              customer_name="C客户")
    db.add_all([j1, j2, j3])
    db.flush()

    db.add(OrderItemLink(order_id="OR-A", handcraft_jewelry_item_id=j1.id))
    db.add(OrderItemLink(order_id="OR-B", handcraft_jewelry_item_id=j2.id))
    db.flush()
    return hc.id


def test_breakdown_groups_by_jewelry_id(db, hc_with_mixed_breakdown):
    from services.handcraft import get_handcraft_jewelry_breakdown
    groups = get_handcraft_jewelry_breakdown(db, hc_with_mixed_breakdown)
    assert len(groups) == 1
    g = groups[0]
    assert g["jewelry_id"] == "SP-MIX"
    assert g["total_qty"] == 2400
    assert len(g["entries"]) == 3


def test_breakdown_entries_resolve_source(db, hc_with_mixed_breakdown):
    from services.handcraft import get_handcraft_jewelry_breakdown
    groups = get_handcraft_jewelry_breakdown(db, hc_with_mixed_breakdown)
    entries = {e["customer_name"]: e for e in groups[0]["entries"]}
    assert entries["A客户"]["source"] == "order"
    assert entries["A客户"]["source_order_id"] == "OR-A"
    assert entries["A客户"]["is_locked"] is True
    assert entries["B客户"]["source"] == "order"
    assert entries["C客户"]["source"] == "manual"
    assert entries["C客户"]["source_order_id"] is None
    assert entries["C客户"]["is_locked"] is False


def test_breakdown_empty_when_no_rows(db):
    from services.handcraft import get_handcraft_jewelry_breakdown
    from models.handcraft_order import HandcraftOrder
    from services.handcraft import _gen_receipt_code
    db.add(HandcraftOrder(id="HC-EMPTY", supplier_name="x", status="pending",
                          receipt_code=_gen_receipt_code(db)))
    db.flush()
    assert get_handcraft_jewelry_breakdown(db, "HC-EMPTY") == []


def test_breakdown_api_endpoint(client, db, hc_with_mixed_breakdown):
    r = client.get(f"/api/handcraft/{hc_with_mixed_breakdown}/jewelry-breakdown")
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    assert data[0]["jewelry_id"] == "SP-MIX"
    assert data[0]["total_qty"] == 2400


def test_batch_breakdown_preview_returns_jewelry_list(db, client):
    from tests.helpers import seed_order_with_batch
    from services.order_todo import link_supplier
    order_id, batch_id = seed_order_with_batch(db, qty=500)
    result = link_supplier(db, order_id, batch_id, "王师傅")
    hc_id = result["handcraft_order_id"]
    db.flush()

    r = client.get(
        f"/api/orders/{order_id}/todo-batch/{batch_id}/breakdown-preview"
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data is not None
    assert data["handcraft_order_id"] == hc_id
    assert data["receipt_code"] is not None
    assert data["supplier_name"] == "王师傅"
    assert data["customer_name"] == "T 客户"
    assert len(data["jewelry_items"]) == 1
    assert data["jewelry_items"][0]["jewelry_id"] == "SP-T100"
    assert data["jewelry_items"][0]["qty"] == 500


def test_batch_breakdown_preview_returns_null_when_unassigned(db, client):
    from tests.helpers import seed_order_with_batch
    order_id, batch_id = seed_order_with_batch(db, qty=10)
    db.flush()

    r = client.get(
        f"/api/orders/{order_id}/todo-batch/{batch_id}/breakdown-preview"
    )
    assert r.status_code == 200
    assert r.json() is None
