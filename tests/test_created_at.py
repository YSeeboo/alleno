"""Tests for editable created_at on production orders and receipts.

Covers:
- POST with created_at for all 5 order types (order, plating, handcraft,
  plating_receipt, handcraft_receipt)
- PATCH created_at on all 5 types preserves time-of-day
- Handcraft auto-merge is skipped when created_at is explicitly provided
- List endpoints sort by created_at DESC so backfilled orders land in
  their historical position
"""

from datetime import date, datetime, timedelta

import pytest

from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock
from services.handcraft import create_handcraft_order
from services.plating import create_plating_order
from services.plating_receipt import create_plating_receipt
from services.handcraft_receipt import create_handcraft_receipt
from services.purchase_order import create_purchase_order
from services.order import create_order
from models.handcraft_order import HandcraftOrder
from models.plating_order import PlatingOrder, PlatingOrderItem
from models.plating_receipt import PlatingReceipt
from models.handcraft_receipt import HandcraftReceipt
from models.purchase_order import PurchaseOrder
from models.order import Order


@pytest.fixture
def setup(db):
    p1 = create_part(db, {"name": "扣子", "category": "小配件", "color": "金"})
    p2 = create_part(db, {"name": "链条", "category": "链条", "color": "银"})
    j1 = create_jewelry(db, {"name": "戒指", "category": "单件"})
    add_stock(db, "part", p1.id, 500.0, "入库")
    add_stock(db, "part", p2.id, 200.0, "入库")
    db.commit()
    return db, p1, p2, j1


# --- POST with created_at ---


def test_post_order_with_created_at(client, db, setup):
    _, _, _, j1 = setup
    resp = client.post("/api/orders/", json={
        "customer_name": "张三",
        "items": [{"jewelry_id": j1.id, "quantity": 1, "unit_price": 10.0}],
        "created_at": "2024-01-15",
    })
    assert resp.status_code == 201
    order = db.query(Order).filter_by(id=resp.json()["id"]).first()
    # User only provided a date, so we store midnight — we must not fabricate
    # a time-of-day the user never supplied.
    assert order.created_at == datetime(2024, 1, 15, 0, 0, 0)


def test_post_plating_with_created_at(client, db, setup):
    _, p1, _, _ = setup
    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀厂A",
        "items": [{"part_id": p1.id, "qty": 10}],
        "created_at": "2023-06-01",
    })
    assert resp.status_code == 201
    order = db.query(PlatingOrder).filter_by(id=resp.json()["id"]).first()
    assert order.created_at.date() == date(2023, 6, 1)


def test_post_handcraft_with_created_at(client, db, setup):
    _, p1, _, j1 = setup
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "手工坊A",
        "parts": [{"part_id": p1.id, "qty": 20}],
        "jewelries": [{"jewelry_id": j1.id, "qty": 2}],
        "created_at": "2023-12-25",
    })
    assert resp.status_code == 201
    order = db.query(HandcraftOrder).filter_by(id=resp.json()["id"]).first()
    assert order.created_at.date() == date(2023, 12, 25)


def test_post_plating_receipt_with_created_at(client, db, setup):
    _, p1, _, _ = setup
    # First create a plating order in 电镀中 state so it can be received
    po = create_plating_order(db, "厂A", items=[{"part_id": p1.id, "qty": 10}])
    from services.plating import send_plating_order
    send_plating_order(db, po.id)
    db.commit()
    poi = db.query(PlatingOrderItem).filter_by(plating_order_id=po.id).first()

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "厂A",
        "items": [{
            "plating_order_item_id": poi.id,
            "part_id": p1.id,
            "qty": 5,
        }],
        "created_at": "2024-02-10",
    })
    assert resp.status_code == 201
    receipt = db.query(PlatingReceipt).filter_by(id=resp.json()["id"]).first()
    assert receipt.created_at.date() == date(2024, 2, 10)


def test_post_purchase_order_with_created_at(client, db, setup):
    _, p1, _, _ = setup
    resp = client.post("/api/purchase-orders/", json={
        "vendor_name": "供应商A",
        "items": [{"part_id": p1.id, "qty": 10, "price": 5.5}],
        "created_at": "2023-09-15",
    })
    assert resp.status_code == 201
    order = db.query(PurchaseOrder).filter_by(id=resp.json()["id"]).first()
    assert order.created_at == datetime(2023, 9, 15, 0, 0, 0)


def test_post_handcraft_receipt_with_created_at(client, db, setup):
    _, p1, _, j1 = setup
    # Create handcraft order and send it
    hc = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 20}],
        jewelries=[{"jewelry_id": j1.id, "qty": 2}],
    )
    from services.handcraft import send_handcraft_order
    send_handcraft_order(db, hc.id)
    db.commit()
    from models.handcraft_order import HandcraftJewelryItem
    hji = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=hc.id).first()

    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "手工坊",
        "items": [{
            "handcraft_jewelry_item_id": hji.id,
            "qty": 1,
        }],
        "created_at": "2024-03-05",
    })
    assert resp.status_code == 201
    receipt = db.query(HandcraftReceipt).filter_by(id=resp.json()["id"]).first()
    assert receipt.created_at.date() == date(2024, 3, 5)


# --- PATCH created_at preserves time-of-day ---


def _set_time(db, obj, year, month, day, hour, minute, second):
    """Force a known timestamp on an ORM row so we can verify time preservation."""
    obj.created_at = datetime(year, month, day, hour, minute, second)
    db.flush()
    db.commit()


def test_patch_order_created_at_preserves_time(client, db, setup):
    _, _, _, j1 = setup
    order = create_order(db, "张三", [{"jewelry_id": j1.id, "quantity": 1, "unit_price": 10.0}])
    _set_time(db, order, 2024, 1, 15, 14, 30, 45)

    resp = client.patch(f"/api/orders/{order.id}/extra-info", json={"created_at": "2023-08-20"})
    assert resp.status_code == 200
    db.refresh(order)
    assert order.created_at == datetime(2023, 8, 20, 14, 30, 45)


def test_patch_plating_created_at_preserves_time(client, db, setup):
    _, p1, _, _ = setup
    order = create_plating_order(db, "厂A", items=[{"part_id": p1.id, "qty": 10}])
    _set_time(db, order, 2024, 1, 15, 9, 15, 30)

    resp = client.patch(f"/api/plating/{order.id}", json={"created_at": "2023-07-01"})
    assert resp.status_code == 200
    db.refresh(order)
    assert order.created_at == datetime(2023, 7, 1, 9, 15, 30)


def test_patch_handcraft_created_at_preserves_time(client, db, setup):
    _, p1, _, j1 = setup
    order = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 10}],
        jewelries=[{"jewelry_id": j1.id, "qty": 1}],
    )
    _set_time(db, order, 2024, 5, 10, 16, 45, 12)

    resp = client.patch(f"/api/handcraft/{order.id}", json={"created_at": "2023-11-11"})
    assert resp.status_code == 200
    db.refresh(order)
    assert order.created_at == datetime(2023, 11, 11, 16, 45, 12)


def test_patch_plating_receipt_created_at_preserves_time(client, db, setup):
    _, p1, _, _ = setup
    po = create_plating_order(db, "厂A", items=[{"part_id": p1.id, "qty": 10}])
    from services.plating import send_plating_order
    send_plating_order(db, po.id)
    poi = db.query(PlatingOrderItem).filter_by(plating_order_id=po.id).first()
    receipt = create_plating_receipt(
        db, "厂A",
        items=[{"plating_order_item_id": poi.id, "part_id": p1.id, "qty": 5}],
    )
    _set_time(db, receipt, 2024, 2, 10, 11, 22, 33)

    resp = client.patch(f"/api/plating-receipts/{receipt.id}", json={"created_at": "2023-09-15"})
    assert resp.status_code == 200
    db.refresh(receipt)
    assert receipt.created_at == datetime(2023, 9, 15, 11, 22, 33)


def test_patch_purchase_order_created_at_preserves_time(client, db, setup):
    _, p1, _, _ = setup
    order = create_purchase_order(
        db, "供应商A",
        items=[{"part_id": p1.id, "qty": 10, "price": 5.5}],
    )
    _set_time(db, order, 2024, 4, 20, 13, 55, 7)

    resp = client.patch(f"/api/purchase-orders/{order.id}", json={"created_at": "2023-12-01"})
    assert resp.status_code == 200
    db.refresh(order)
    assert order.created_at == datetime(2023, 12, 1, 13, 55, 7)


# --- paid_at timeline consistency for backfilled paid orders ---


def test_purchase_order_paid_backfill_anchors_paid_at_to_created_at(client, db, setup):
    """Backfilling a 已付款 purchase order must anchor paid_at to created_at,
    not to now(), otherwise the timeline is inconsistent."""
    _, p1, _, _ = setup
    resp = client.post("/api/purchase-orders/", json={
        "vendor_name": "供应商A",
        "items": [{"part_id": p1.id, "qty": 5, "price": 1.0}],
        "status": "已付款",
        "created_at": "2023-09-15",
    })
    assert resp.status_code == 201
    order = db.query(PurchaseOrder).filter_by(id=resp.json()["id"]).first()
    assert order.created_at == datetime(2023, 9, 15, 0, 0, 0)
    assert order.paid_at == order.created_at


def test_patch_purchase_order_created_at_after_paid_at_rejected(client, db, setup):
    """PATCH created_at to a date later than existing paid_at must be rejected."""
    _, p1, _, _ = setup
    order = create_purchase_order(
        db, "供应商A",
        items=[{"part_id": p1.id, "qty": 5, "price": 1.0}],
        status="已付款",
        created_at=date(2023, 9, 15),
    )
    db.commit()
    # paid_at was anchored to 2023-09-15; trying to push created_at past that must fail.
    resp = client.patch(f"/api/purchase-orders/{order.id}", json={"created_at": "2024-01-01"})
    assert resp.status_code == 400
    assert "付款时间" in resp.json()["detail"]
    db.refresh(order)
    assert order.created_at.date() == date(2023, 9, 15)


def test_plating_receipt_paid_backfill_anchors_paid_at(client, db, setup):
    _, p1, _, _ = setup
    po = create_plating_order(db, "厂A", items=[{"part_id": p1.id, "qty": 10}])
    from services.plating import send_plating_order
    send_plating_order(db, po.id)
    db.commit()
    poi = db.query(PlatingOrderItem).filter_by(plating_order_id=po.id).first()

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "厂A",
        "items": [{"plating_order_item_id": poi.id, "part_id": p1.id, "qty": 5}],
        "status": "已付款",
        "created_at": "2023-11-20",
    })
    assert resp.status_code == 201
    receipt = db.query(PlatingReceipt).filter_by(id=resp.json()["id"]).first()
    assert receipt.created_at == datetime(2023, 11, 20, 0, 0, 0)
    assert receipt.paid_at == receipt.created_at


def test_patch_plating_receipt_created_at_after_paid_at_rejected(client, db, setup):
    _, p1, _, _ = setup
    po = create_plating_order(db, "厂A", items=[{"part_id": p1.id, "qty": 10}])
    from services.plating import send_plating_order
    send_plating_order(db, po.id)
    poi = db.query(PlatingOrderItem).filter_by(plating_order_id=po.id).first()
    receipt = create_plating_receipt(
        db, "厂A",
        items=[{"plating_order_item_id": poi.id, "part_id": p1.id, "qty": 5}],
        status="已付款",
        created_at=date(2023, 11, 20),
    )
    db.commit()
    resp = client.patch(f"/api/plating-receipts/{receipt.id}", json={"created_at": "2024-05-01"})
    assert resp.status_code == 400
    assert "付款时间" in resp.json()["detail"]


def test_handcraft_receipt_paid_backfill_anchors_paid_at(client, db, setup):
    _, p1, _, j1 = setup
    hc = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 10}],
        jewelries=[{"jewelry_id": j1.id, "qty": 1}],
    )
    from services.handcraft import send_handcraft_order
    send_handcraft_order(db, hc.id)
    db.commit()
    from models.handcraft_order import HandcraftJewelryItem
    hji = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=hc.id).first()

    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "手工坊",
        "items": [{"handcraft_jewelry_item_id": hji.id, "qty": 1}],
        "status": "已付款",
        "created_at": "2023-08-10",
    })
    assert resp.status_code == 201
    receipt = db.query(HandcraftReceipt).filter_by(id=resp.json()["id"]).first()
    assert receipt.created_at == datetime(2023, 8, 10, 0, 0, 0)
    assert receipt.paid_at == receipt.created_at


def test_patch_handcraft_receipt_created_at_after_paid_at_rejected(client, db, setup):
    _, p1, _, j1 = setup
    hc = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 10}],
        jewelries=[{"jewelry_id": j1.id, "qty": 1}],
    )
    from services.handcraft import send_handcraft_order
    send_handcraft_order(db, hc.id)
    from models.handcraft_order import HandcraftJewelryItem
    hji = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=hc.id).first()
    receipt = create_handcraft_receipt(
        db, "手工坊",
        items=[{"handcraft_jewelry_item_id": hji.id, "qty": 1}],
        status="已付款",
        created_at=date(2023, 8, 10),
    )
    db.commit()
    resp = client.patch(f"/api/handcraft-receipts/{receipt.id}", json={"created_at": "2024-02-15"})
    assert resp.status_code == 400
    assert "付款时间" in resp.json()["detail"]


# --- status-change path: paid_at must stay >= created_at ---


def test_purchase_order_status_to_paid_clamps_paid_at_to_future_created_at(client, db, setup):
    """If a purchase order has a future created_at and is later transitioned
    to 已付款 via PATCH /status, paid_at must be clamped to created_at so the
    timeline stays consistent (paid_at >= created_at)."""
    _, p1, _, _ = setup
    # Create an unpaid order with a future created_at.
    future = date.today() + timedelta(days=365)
    resp = client.post("/api/purchase-orders/", json={
        "vendor_name": "供应商A",
        "items": [{"part_id": p1.id, "qty": 5, "price": 1.0}],
        "status": "未付款",
        "created_at": future.strftime("%Y-%m-%d"),
    })
    assert resp.status_code == 201
    order_id = resp.json()["id"]

    # Transition to 已付款 via the status endpoint.
    resp = client.patch(f"/api/purchase-orders/{order_id}/status", json={"status": "已付款"})
    assert resp.status_code == 200
    order = db.query(PurchaseOrder).filter_by(id=order_id).first()
    assert order.paid_at >= order.created_at


def test_plating_receipt_status_to_paid_clamps_paid_at(client, db, setup):
    _, p1, _, _ = setup
    po = create_plating_order(db, "厂A", items=[{"part_id": p1.id, "qty": 10}])
    from services.plating import send_plating_order
    send_plating_order(db, po.id)
    db.commit()
    poi = db.query(PlatingOrderItem).filter_by(plating_order_id=po.id).first()

    future = date.today() + timedelta(days=365)
    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "厂A",
        "items": [{"plating_order_item_id": poi.id, "part_id": p1.id, "qty": 5}],
        "status": "未付款",
        "created_at": future.strftime("%Y-%m-%d"),
    })
    assert resp.status_code == 201
    receipt_id = resp.json()["id"]

    resp = client.patch(f"/api/plating-receipts/{receipt_id}/status", json={"status": "已付款"})
    assert resp.status_code == 200
    receipt = db.query(PlatingReceipt).filter_by(id=receipt_id).first()
    assert receipt.paid_at >= receipt.created_at


def test_handcraft_receipt_status_to_paid_clamps_paid_at(client, db, setup):
    _, p1, _, j1 = setup
    hc = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 10}],
        jewelries=[{"jewelry_id": j1.id, "qty": 1}],
    )
    from services.handcraft import send_handcraft_order
    send_handcraft_order(db, hc.id)
    db.commit()
    from models.handcraft_order import HandcraftJewelryItem
    hji = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=hc.id).first()

    future = date.today() + timedelta(days=365)
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "手工坊",
        "items": [{"handcraft_jewelry_item_id": hji.id, "qty": 1}],
        "status": "未付款",
        "created_at": future.strftime("%Y-%m-%d"),
    })
    assert resp.status_code == 201
    receipt_id = resp.json()["id"]

    resp = client.patch(f"/api/handcraft-receipts/{receipt_id}/status", json={"status": "已付款"})
    assert resp.status_code == 200
    receipt = db.query(HandcraftReceipt).filter_by(id=receipt_id).first()
    assert receipt.paid_at >= receipt.created_at


def test_purchase_order_status_to_paid_past_created_at_uses_now(client, db, setup):
    """Regression guard: normal flow (past created_at) must still set paid_at to now,
    not accidentally clamp backwards to the old created_at."""
    _, p1, _, _ = setup
    # Unpaid order backfilled to a past date.
    order = create_purchase_order(
        db, "供应商A",
        items=[{"part_id": p1.id, "qty": 5, "price": 1.0}],
        status="未付款",
        created_at=date(2023, 1, 1),
    )
    db.commit()

    resp = client.patch(f"/api/purchase-orders/{order.id}/status", json={"status": "已付款"})
    assert resp.status_code == 200
    db.refresh(order)
    # paid_at should be "now" (today), not clamped back to 2023-01-01
    assert order.paid_at.date() >= date.today()


def test_list_purchase_orders_sorted_with_id_tiebreaker(client, db, setup):
    """Two backfilled purchase orders with identical midnight created_at must
    be returned in a deterministic order via the id DESC tie-breaker.
    """
    _, p1, _, _ = setup
    r1 = client.post("/api/purchase-orders/", json={
        "vendor_name": "供应商A",
        "items": [{"part_id": p1.id, "qty": 5, "price": 1.0}],
        "created_at": "2023-10-01",
    })
    r2 = client.post("/api/purchase-orders/", json={
        "vendor_name": "供应商A",
        "items": [{"part_id": p1.id, "qty": 5, "price": 1.0}],
        "created_at": "2023-10-01",
    })
    id1, id2 = r1.json()["id"], r2.json()["id"]
    o1 = db.query(PurchaseOrder).filter_by(id=id1).first()
    o2 = db.query(PurchaseOrder).filter_by(id=id2).first()
    assert o1.created_at == datetime(2023, 10, 1, 0, 0, 0)
    assert o2.created_at == datetime(2023, 10, 1, 0, 0, 0)
    resp = client.get("/api/purchase-orders/", params={"vendor_name": "供应商A"})
    ids = [o["id"] for o in resp.json()]
    assert ids.index(id2) < ids.index(id1)


def test_patch_handcraft_receipt_created_at_preserves_time(client, db, setup):
    _, p1, _, j1 = setup
    hc = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 10}],
        jewelries=[{"jewelry_id": j1.id, "qty": 1}],
    )
    from services.handcraft import send_handcraft_order
    send_handcraft_order(db, hc.id)
    from models.handcraft_order import HandcraftJewelryItem
    hji = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=hc.id).first()
    receipt = create_handcraft_receipt(
        db, "手工坊",
        items=[{"handcraft_jewelry_item_id": hji.id, "qty": 1}],
    )
    _set_time(db, receipt, 2024, 3, 5, 20, 10, 5)

    resp = client.patch(f"/api/handcraft-receipts/{receipt.id}", json={"created_at": "2023-10-01"})
    assert resp.status_code == 200
    db.refresh(receipt)
    assert receipt.created_at == datetime(2023, 10, 1, 20, 10, 5)


# --- Handcraft auto-merge is skipped when created_at is explicit ---


def test_handcraft_explicit_created_at_skips_merge(client, db, setup):
    """When补录历史单据, we don't want same-day merge to collapse them."""
    _, p1, p2, j1 = setup
    r1 = client.post("/api/handcraft/", json={
        "supplier_name": "手工坊",
        "parts": [{"part_id": p1.id, "qty": 20}],
        "jewelries": [{"jewelry_id": j1.id, "qty": 2}],
        "created_at": "2023-10-01",
    })
    assert r1.status_code == 201
    r2 = client.post("/api/handcraft/", json={
        "supplier_name": "手工坊",
        "parts": [{"part_id": p2.id, "qty": 15}],
        "created_at": "2023-10-01",
    })
    # Should be 201 (new order), not 200 (merged)
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


def test_handcraft_merge_target_is_deterministic(client, db, setup):
    """When multiple pending handcraft orders exist for the same supplier on
    the same day (e.g. two backfills stored as midnight), a subsequent default
    create (no explicit created_at) must deterministically merge into the
    earliest row by `(created_at ASC, id ASC)` — not into whichever row the
    database happens to return first.
    """
    from time_utils import now_beijing
    _, p1, p2, _ = setup
    today = now_beijing().date()

    # Two backfilled pending orders, both stored as midnight TODAY so they
    # share the same created_at timestamp. The ONLY way to tie-break them is
    # by id.
    hc1 = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 10}],
        created_at=today,
    )
    hc2 = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p2.id, "qty": 10}],
        created_at=today,
    )
    assert hc1.created_at == hc2.created_at  # identical midnight timestamp
    assert hc1.id < hc2.id  # hc1 is the earliest by id

    # Default create (no created_at) must merge into hc1, not hc2.
    hc3 = create_handcraft_order(
        db, "手工坊",
        parts=[{"part_id": p1.id, "qty": 5}],
    )
    assert hc3.id == hc1.id
    assert getattr(hc3, "merged", False) is True


def test_handcraft_without_created_at_still_merges(client, db, setup):
    """Regression guard: default auto-merge behavior still works."""
    _, p1, p2, j1 = setup
    r1 = client.post("/api/handcraft/", json={
        "supplier_name": "手工坊",
        "parts": [{"part_id": p1.id, "qty": 20}],
        "jewelries": [{"jewelry_id": j1.id, "qty": 2}],
    })
    r2 = client.post("/api/handcraft/", json={
        "supplier_name": "手工坊",
        "parts": [{"part_id": p2.id, "qty": 15}],
    })
    # Second call merges into the first
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]


# --- List endpoints sort by created_at DESC ---


def test_list_plating_orders_sorted_by_created_at_desc(client, db, setup):
    _, p1, _, _ = setup
    # Create two orders: newer first, then backfill an older one
    client.post("/api/plating/", json={
        "supplier_name": "厂A",
        "items": [{"part_id": p1.id, "qty": 10}],
        "created_at": "2024-05-01",
    })
    client.post("/api/plating/", json={
        "supplier_name": "厂A",
        "items": [{"part_id": p1.id, "qty": 10}],
        "created_at": "2023-01-15",
    })
    resp = client.get("/api/plating/")
    ids = [o["created_at"][:10] for o in resp.json()]
    assert ids == sorted(ids, reverse=True)
    assert ids[0] == "2024-05-01"
    assert ids[-1] == "2023-01-15"


def test_same_day_backfills_have_deterministic_order(client, db, setup):
    """Two orders backfilled with the same date share an identical (midnight)
    created_at. The list endpoint must still return them in a deterministic
    order via an `id DESC` tie-breaker, so the most recently inserted row
    comes first regardless of stored timestamp.
    """
    _, p1, _, _ = setup
    r1 = client.post("/api/plating/", json={
        "supplier_name": "厂A",
        "items": [{"part_id": p1.id, "qty": 5}],
        "created_at": "2023-10-01",
    })
    r2 = client.post("/api/plating/", json={
        "supplier_name": "厂A",
        "items": [{"part_id": p1.id, "qty": 5}],
        "created_at": "2023-10-01",
    })
    id1, id2 = r1.json()["id"], r2.json()["id"]
    o1 = db.query(PlatingOrder).filter_by(id=id1).first()
    o2 = db.query(PlatingOrder).filter_by(id=id2).first()
    # Both stored as midnight — no fabricated time-of-day.
    assert o1.created_at == datetime(2023, 10, 1, 0, 0, 0)
    assert o2.created_at == datetime(2023, 10, 1, 0, 0, 0)
    # List endpoint returns them deterministically with the newer id first.
    resp = client.get("/api/plating/", params={"supplier_name": "厂A"})
    ids = [o["id"] for o in resp.json()]
    assert ids.index(id2) < ids.index(id1)


def test_pending_receive_same_day_backfills_deterministic(client, db, setup):
    """Pending-receive endpoints (used by the receipt-creation pages) must
    also apply the id tie-breaker, otherwise same-day backfills produce an
    unstable candidate list in the UI.
    """
    _, p1, _, j1 = setup
    # Two plating orders backfilled on the same date, both sent so their
    # items show up in the pending-receive list.
    from services.plating import send_plating_order
    po1 = create_plating_order(
        db, "厂A",
        items=[{"part_id": p1.id, "qty": 5}],
        created_at=date(2023, 10, 1),
    )
    po2 = create_plating_order(
        db, "厂A",
        items=[{"part_id": p1.id, "qty": 5}],
        created_at=date(2023, 10, 1),
    )
    send_plating_order(db, po1.id)
    send_plating_order(db, po2.id)
    db.commit()

    resp = client.get("/api/plating/items/pending-receive", params={"supplier_name": "厂A"})
    assert resp.status_code == 200
    order_ids = [r["plating_order_id"] for r in resp.json()]
    assert po2.id in order_ids and po1.id in order_ids
    # Newer id first (id DESC tie-breaker)
    assert order_ids.index(po2.id) < order_ids.index(po1.id)

    # Same for handcraft pending-receive parts
    from services.handcraft import send_handcraft_order
    hc1 = create_handcraft_order(
        db, "坊A",
        parts=[{"part_id": p1.id, "qty": 5}],
        jewelries=[{"jewelry_id": j1.id, "qty": 1}],
        created_at=date(2023, 10, 1),
    )
    hc2 = create_handcraft_order(
        db, "坊A",
        parts=[{"part_id": p1.id, "qty": 5}],
        jewelries=[{"jewelry_id": j1.id, "qty": 1}],
        created_at=date(2023, 10, 1),
    )
    send_handcraft_order(db, hc1.id)
    send_handcraft_order(db, hc2.id)
    db.commit()

    resp = client.get("/api/handcraft/items/pending-receive", params={"supplier_name": "坊A"})
    assert resp.status_code == 200
    rows = resp.json()
    part_rows = [r for r in rows if not r.get("is_output")]
    part_order_ids = [r["handcraft_order_id"] for r in part_rows]
    assert hc2.id in part_order_ids and hc1.id in part_order_ids
    assert part_order_ids.index(hc2.id) < part_order_ids.index(hc1.id)
    jewelry_rows = [r for r in rows if r.get("is_output")]
    jewelry_order_ids = [r["handcraft_order_id"] for r in jewelry_rows]
    assert jewelry_order_ids.index(hc2.id) < jewelry_order_ids.index(hc1.id)


def test_list_handcraft_orders_sorted_by_created_at_desc(client, db, setup):
    _, p1, p2, j1 = setup
    client.post("/api/handcraft/", json={
        "supplier_name": "坊A",
        "parts": [{"part_id": p1.id, "qty": 10}],
        "created_at": "2024-04-10",
    })
    client.post("/api/handcraft/", json={
        "supplier_name": "坊B",
        "parts": [{"part_id": p2.id, "qty": 10}],
        "created_at": "2022-11-20",
    })
    resp = client.get("/api/handcraft/")
    dates = [o["created_at"][:10] for o in resp.json()]
    assert dates == sorted(dates, reverse=True)
    assert dates[0] == "2024-04-10"
    assert dates[-1] == "2022-11-20"
