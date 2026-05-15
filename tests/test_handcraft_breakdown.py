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


def test_update_customer_name_allowed_in_processing(db):
    """customer_name is pure metadata — editable in pending and processing."""
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    from models.jewelry import Jewelry
    from services.handcraft import _gen_receipt_code, update_handcraft_jewelry

    db.add(Jewelry(id="SP-UJ", name="x", category="吊坠"))
    db.flush()
    hc = HandcraftOrder(id="HC-UJ", supplier_name="测", status="processing",
                        receipt_code=_gen_receipt_code(db))
    db.add(hc)
    db.flush()
    j = HandcraftJewelryItem(handcraft_order_id="HC-UJ", jewelry_id="SP-UJ",
                             qty=100, received_qty=0, status="制作中", unit="套",
                             customer_name="旧客户")
    db.add(j)
    db.flush()

    updated = update_handcraft_jewelry(db, "HC-UJ", j.id, {"customer_name": "新客户"})
    assert updated.customer_name == "新客户"


def test_update_qty_still_blocked_in_processing(db):
    """qty edits remain pending-only — existing rule."""
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    from models.jewelry import Jewelry
    from services.handcraft import _gen_receipt_code, update_handcraft_jewelry

    db.add(Jewelry(id="SP-UJ2", name="x", category="吊坠"))
    db.flush()
    hc = HandcraftOrder(id="HC-UJ2", supplier_name="测", status="processing",
                        receipt_code=_gen_receipt_code(db))
    db.add(hc)
    db.flush()
    j = HandcraftJewelryItem(handcraft_order_id="HC-UJ2", jewelry_id="SP-UJ2",
                             qty=100, received_qty=0, status="制作中", unit="套")
    db.add(j)
    db.flush()

    with pytest.raises(ValueError, match="status"):
        update_handcraft_jewelry(db, "HC-UJ2", j.id, {"qty": 200})


def test_update_customer_name_blocked_for_order_linked_row(db, hc_with_mixed_breakdown):
    """From-order rows: customer_name must be edited at the order, not here."""
    from models.handcraft_order import HandcraftJewelryItem
    from services.handcraft import update_handcraft_jewelry

    # Find the row that came from OR-A (qty=1000, customer_name=None)
    j = db.query(HandcraftJewelryItem).filter_by(
        handcraft_order_id=hc_with_mixed_breakdown, qty=1000,
    ).first()
    with pytest.raises(ValueError, match="订单"):
        update_handcraft_jewelry(db, hc_with_mixed_breakdown, j.id,
                                 {"customer_name": "改名"})


def test_update_customer_name_blocked_when_completed(db):
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    from models.jewelry import Jewelry
    from services.handcraft import _gen_receipt_code, update_handcraft_jewelry

    db.add(Jewelry(id="SP-UJ3", name="x", category="吊坠"))
    db.flush()
    hc = HandcraftOrder(id="HC-UJ3", supplier_name="测", status="completed",
                        receipt_code=_gen_receipt_code(db))
    db.add(hc)
    db.flush()
    j = HandcraftJewelryItem(handcraft_order_id="HC-UJ3", jewelry_id="SP-UJ3",
                             qty=100, received_qty=100, status="已收回", unit="套",
                             customer_name="x")
    db.add(j)
    db.flush()
    with pytest.raises(ValueError):
        update_handcraft_jewelry(db, "HC-UJ3", j.id, {"customer_name": "y"})


def test_add_manual_jewelry_allowed_in_pending(db):
    from models.handcraft_order import HandcraftOrder
    from models.jewelry import Jewelry
    from services.handcraft import _gen_receipt_code, add_handcraft_jewelry

    db.add(Jewelry(id="SP-AJ", name="x", category="吊坠"))
    db.flush()
    hc = HandcraftOrder(id="HC-AJ", supplier_name="测", status="pending",
                        receipt_code=_gen_receipt_code(db))
    db.add(hc)
    db.flush()

    item = add_handcraft_jewelry(db, "HC-AJ",
        {"jewelry_id": "SP-AJ", "qty": 50, "customer_name": "Z 客户"})
    assert item.customer_name == "Z 客户"


def test_add_manual_jewelry_blocked_in_processing(db):
    from models.handcraft_order import HandcraftOrder
    from models.jewelry import Jewelry
    from services.handcraft import _gen_receipt_code, add_handcraft_jewelry

    db.add(Jewelry(id="SP-AJ2", name="x", category="吊坠"))
    db.flush()
    hc = HandcraftOrder(id="HC-AJ2", supplier_name="测", status="processing",
                        receipt_code=_gen_receipt_code(db))
    db.add(hc)
    db.flush()
    with pytest.raises(ValueError, match="手填客户"):
        add_handcraft_jewelry(db, "HC-AJ2",
            {"jewelry_id": "SP-AJ2", "qty": 50, "customer_name": "Z 客户"})


def test_add_jewelry_without_customer_name_still_allowed_in_processing(db):
    """Internal callers (link_supplier) add HC jewelry rows in processing too.
    Only when caller passes customer_name does the rule kick in."""
    from models.handcraft_order import HandcraftOrder
    from models.jewelry import Jewelry
    from services.handcraft import _gen_receipt_code, add_handcraft_jewelry

    db.add(Jewelry(id="SP-AJ3", name="x", category="吊坠"))
    db.flush()
    hc = HandcraftOrder(id="HC-AJ3", supplier_name="测", status="processing",
                        receipt_code=_gen_receipt_code(db))
    db.add(hc)
    db.flush()

    item = add_handcraft_jewelry(db, "HC-AJ3",
        {"jewelry_id": "SP-AJ3", "qty": 50})
    assert item.customer_name is None


def test_delete_jewelry_blocked_when_order_linked(db, hc_with_mixed_breakdown):
    """delete_handcraft_jewelry must refuse to delete an order-linked row
    so the FK doesn't blow up the request with a 500."""
    from models.handcraft_order import HandcraftJewelryItem, HandcraftOrder
    from services.handcraft import delete_handcraft_jewelry

    # The hc_with_mixed_breakdown fixture leaves HC-MIX in pending, with
    # an order-linked row at qty=1000. Confirm that's the case, then delete.
    hc = db.query(HandcraftOrder).filter_by(id=hc_with_mixed_breakdown).first()
    assert hc.status == "pending"
    linked_row = db.query(HandcraftJewelryItem).filter_by(
        handcraft_order_id=hc_with_mixed_breakdown, qty=1000,
    ).first()
    with pytest.raises(ValueError, match="订单"):
        delete_handcraft_jewelry(db, hc_with_mixed_breakdown, linked_row.id)


def test_delete_part_blocked_when_order_linked(db):
    """delete_handcraft_part must refuse to delete an order-linked part row."""
    from tests.helpers import seed_order_with_batch
    from services.order_todo import link_supplier
    from services.handcraft import delete_handcraft_part
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem

    order_id, batch_id = seed_order_with_batch(db, qty=100)
    result = link_supplier(db, order_id, batch_id, "王师傅")
    hc_id = result["handcraft_order_id"]
    # link_supplier created HC + part item + OrderItemLink to OrderTodoItem.
    # The HC stays pending (default state).
    hc = db.query(HandcraftOrder).filter_by(id=hc_id).first()
    assert hc.status == "pending"
    part_item = db.query(HandcraftPartItem).filter_by(
        handcraft_order_id=hc_id,
    ).first()
    with pytest.raises(ValueError, match="订单"):
        delete_handcraft_part(db, hc_id, part_item.id)


def test_create_link_blocked_when_jewelry_has_customer_name(db):
    """A manual breakdown row (has customer_name) must not be retro-linked
    to an order — the two are mutually exclusive."""
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    from models.order import Order, OrderItem
    from models.jewelry import Jewelry
    from services.handcraft import _gen_receipt_code
    from services.order_todo import create_link

    db.add(Jewelry(id="SP-CL", name="x", category="吊坠"))
    db.flush()
    hc = HandcraftOrder(id="HC-CL", supplier_name="x", status="pending",
                        receipt_code=_gen_receipt_code(db))
    db.add(hc)
    db.add(Order(id="OR-CL", customer_name="Z 客户", status="待生产"))
    db.flush()
    db.add(OrderItem(order_id="OR-CL", jewelry_id="SP-CL", quantity=50, unit_price=1))
    db.flush()
    hji = HandcraftJewelryItem(handcraft_order_id="HC-CL", jewelry_id="SP-CL",
                               qty=50, received_qty=0, status="未送出", unit="套",
                               customer_name="手填客户A")
    db.add(hji)
    db.flush()

    with pytest.raises(ValueError, match="手填客户名"):
        create_link(db, {
            "order_id": "OR-CL",
            "handcraft_jewelry_item_id": hji.id,
        })
