import pytest

from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock, get_stock
from services.handcraft import create_handcraft_order, send_handcraft_order
from models.handcraft_order import HandcraftPartItem, HandcraftJewelryItem
from models.handcraft_receipt import HandcraftReceipt, HandcraftReceiptItem


def _create_sent_handcraft(db, supplier_name="测试手工商", part_qty=10.0, jewelry_qty=5):
    """Create a part + jewelry, stock the part, create + send a handcraft order."""
    part = create_part(db, {"name": "配件A", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "饰品A", "category": "单件"})
    add_stock(db, "part", part.id, part_qty + 20, "初始入库")
    order = create_handcraft_order(
        db, supplier_name,
        parts=[{"part_id": part.id, "qty": part_qty}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": jewelry_qty}] if jewelry_qty else [],
    )
    send_handcraft_order(db, order.id)
    db.flush()
    pi = db.query(HandcraftPartItem).filter(HandcraftPartItem.handcraft_order_id == order.id).first()
    ji = db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.handcraft_order_id == order.id).first()
    return part, jewelry, order, pi, ji


# ── Basic CRUD ──────────────────────────────────────────────────────────


def test_create_receipt_with_part_item(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 5.0, "price": 1.5}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("HR-")
    assert data["status"] == "未付款"
    assert data["total_amount"] == pytest.approx(7.5)
    assert len(data["items"]) == 1
    assert data["items"][0]["item_type"] == "part"
    assert data["items"][0]["item_id"] == part.id
    # Stock: 30 initial - 10 sent + 5 received = 25
    assert get_stock(db, "part", part.id) == pytest.approx(25.0)


def test_create_receipt_with_jewelry_item(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_jewelry_item_id": ji.id, "qty": 3}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["items"][0]["item_type"] == "jewelry"
    assert get_stock(db, "jewelry", jewelry.id) == pytest.approx(3.0)


def test_create_receipt_mixed_items(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [
            {"handcraft_part_item_id": pi.id, "qty": 5.0, "price": 2.0},
            {"handcraft_jewelry_item_id": ji.id, "qty": 3},
        ],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total_amount"] == pytest.approx(10.0)  # only part item has price


def test_list_receipts(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 3.0}],
    })
    resp = client.get("/api/handcraft-receipts/")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_receipt(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    create_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 3.0}],
    })
    receipt_id = create_resp.json()["id"]
    resp = client.get(f"/api/handcraft-receipts/{receipt_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == receipt_id


def test_get_receipt_not_found(client, db):
    resp = client.get("/api/handcraft-receipts/HR-9999")
    assert resp.status_code == 404


def test_delete_receipt(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    create_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 5.0}],
    })
    receipt_id = create_resp.json()["id"]
    stock_after_receive = get_stock(db, "part", part.id)

    del_resp = client.delete(f"/api/handcraft-receipts/{receipt_id}")
    assert del_resp.status_code == 204

    # Stock reversed
    assert get_stock(db, "part", part.id) == pytest.approx(stock_after_receive - 5.0)
    assert db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first() is None


# ── Order completion ────────────────────────────────────────────────────


def test_all_received_completes_order(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [
            {"handcraft_part_item_id": pi.id, "qty": 10.0},
            {"handcraft_jewelry_item_id": ji.id, "qty": 5},
        ],
    })
    order_resp = client.get(f"/api/handcraft/{order.id}")
    assert order_resp.json()["status"] == "completed"


def test_only_parts_received_stays_processing(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 10.0}],
    })
    order_resp = client.get(f"/api/handcraft/{order.id}")
    assert order_resp.json()["status"] == "processing"


def test_only_jewelry_received_stays_processing(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_jewelry_item_id": ji.id, "qty": 5}],
    })
    order_resp = client.get(f"/api/handcraft/{order.id}")
    assert order_resp.json()["status"] == "processing"


# ── Constraint validation ──────────────────────────────────────────────


def test_qty_exceeds_remaining(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 15.0}],
    })
    assert resp.status_code == 400


def test_paid_receipt_cannot_add_items(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    create_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 3.0}],
        "status": "已付款",
    })
    receipt_id = create_resp.json()["id"]
    add_resp = client.post(f"/api/handcraft-receipts/{receipt_id}/items", json={
        "items": [{"handcraft_jewelry_item_id": ji.id, "qty": 2}],
    })
    assert add_resp.status_code == 400


def test_paid_receipt_cannot_delete(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    create_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 3.0}],
        "status": "已付款",
    })
    receipt_id = create_resp.json()["id"]
    resp = client.delete(f"/api/handcraft-receipts/{receipt_id}")
    assert resp.status_code == 400


def test_supplier_mismatch_rejected(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db, supplier_name="手工商A")
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "手工商B",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 3.0}],
    })
    assert resp.status_code == 400


def test_both_item_ids_empty_rejected(client, db):
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"qty": 3.0}],
    })
    assert resp.status_code == 422


def test_both_item_ids_set_rejected(client, db):
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": 1, "handcraft_jewelry_item_id": 1, "qty": 3.0}],
    })
    assert resp.status_code == 422


def test_cannot_delete_last_item(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    create_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 3.0}],
    })
    receipt_id = create_resp.json()["id"]
    item_id = create_resp.json()["items"][0]["id"]
    resp = client.delete(f"/api/handcraft-receipts/{receipt_id}/items/{item_id}")
    assert resp.status_code == 400


# ── Payment status ─────────────────────────────────────────────────────


def test_payment_status_toggle(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    create_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 3.0}],
    })
    receipt_id = create_resp.json()["id"]

    # Mark paid
    pay_resp = client.patch(f"/api/handcraft-receipts/{receipt_id}/status", json={"status": "已付款"})
    assert pay_resp.status_code == 200
    assert pay_resp.json()["status"] == "已付款"
    assert pay_resp.json()["paid_at"] is not None

    # Mark unpaid
    unpay_resp = client.patch(f"/api/handcraft-receipts/{receipt_id}/status", json={"status": "未付款"})
    assert unpay_resp.status_code == 200
    assert unpay_resp.json()["status"] == "未付款"
    assert unpay_resp.json()["paid_at"] is None


# ── Item update ─────────────────────────────────────────────────────────


def test_update_item_qty_adjusts_stock(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    create_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 3.0, "price": 1.0}],
    })
    receipt_id = create_resp.json()["id"]
    item_id = create_resp.json()["items"][0]["id"]
    stock_after_3 = get_stock(db, "part", part.id)

    # Update qty from 3 to 5
    resp = client.put(f"/api/handcraft-receipts/{receipt_id}/items/{item_id}", json={"qty": 5.0})
    assert resp.status_code == 200
    assert get_stock(db, "part", part.id) == pytest.approx(stock_after_3 + 2.0)


def test_update_item_price_recalcs_amount(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    create_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 4.0, "price": 1.0}],
    })
    receipt_id = create_resp.json()["id"]
    item_id = create_resp.json()["items"][0]["id"]

    resp = client.put(f"/api/handcraft-receipts/{receipt_id}/items/{item_id}", json={"price": 3.0})
    assert resp.status_code == 200
    assert resp.json()["amount"] == pytest.approx(12.0)


# ── Cost sync ──────────────────────────────────────────────────────────


def test_cost_diffs_returned_on_create(client, db):
    # A方案: part receipts no longer produce bead_cost diffs; only jewelry/assembly diffs remain.
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 5.0, "price": 2.5}],
    })
    assert resp.status_code == 201
    data = resp.json()
    # No bead_cost diff: part receipt = pure surplus return, no cost sync
    assert all(d.get("field") != "bead_cost" for d in data.get("cost_diffs", []))


def test_part_receive_does_not_sync_bead_cost(client, db):
    from services.part import create_part
    from services.inventory import add_stock
    from services.handcraft import create_handcraft_order, send_handcraft_order
    from models.handcraft_order import HandcraftPartItem
    from models.part import Part

    part = create_part(db, {"name": "穿珠件", "category": "小配件"})
    add_stock(db, "part", part.id, 500, "入库")
    order = create_handcraft_order(db, "商家B", parts=[{"part_id": part.id, "qty": 50}])
    send_handcraft_order(db, order.id)
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).first()

    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "商家B",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 20, "price": 3.3}],
    })
    assert resp.status_code == 201
    # A方案：配件回收纯退料，不写 bead_cost；也不在 cost_diffs 里冒出 bead_cost
    assert all(d.get("field") != "bead_cost" for d in resp.json().get("cost_diffs", []))
    db.expire(db.get(Part, part.id))
    assert db.get(Part, part.id).bead_cost is None


# ── Partial receive ────────────────────────────────────────────────────


def test_partial_receive_then_full(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)

    # First: partial receive
    client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 4.0}],
    })
    db.refresh(pi)
    assert pi.status == "制作中"
    assert float(pi.received_qty) == pytest.approx(4.0)

    # Second: receive rest
    client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 6.0}],
    })
    db.refresh(pi)
    assert pi.status == "已收回"
    assert float(pi.received_qty) == pytest.approx(10.0)


# ── Cross-order receipt ────────────────────────────────────────────────


def test_cross_order_receipt(client, db):
    """One receipt with items from two different handcraft orders."""
    part1 = create_part(db, {"name": "配件1", "category": "小配件"})
    part2 = create_part(db, {"name": "配件2", "category": "小配件"})
    add_stock(db, "part", part1.id, 50, "入库")
    add_stock(db, "part", part2.id, 50, "入库")

    order1 = create_handcraft_order(db, "同商家", parts=[{"part_id": part1.id, "qty": 10}])
    send_handcraft_order(db, order1.id)
    order2 = create_handcraft_order(db, "同商家", parts=[{"part_id": part2.id, "qty": 20}])
    send_handcraft_order(db, order2.id)

    pi1 = db.query(HandcraftPartItem).filter(HandcraftPartItem.handcraft_order_id == order1.id).first()
    pi2 = db.query(HandcraftPartItem).filter(HandcraftPartItem.handcraft_order_id == order2.id).first()

    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "同商家",
        "items": [
            {"handcraft_part_item_id": pi1.id, "qty": 10.0},
            {"handcraft_part_item_id": pi2.id, "qty": 20.0},
        ],
    })
    assert resp.status_code == 201

    # Both orders should be completed (no jewelry to receive)
    o1 = client.get(f"/api/handcraft/{order1.id}").json()
    o2 = client.get(f"/api/handcraft/{order2.id}").json()
    assert o1["status"] == "completed"
    assert o2["status"] == "completed"


# ── Enriched fields ────────────────────────────────────────────────────


def test_enriched_fields_on_get(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    create_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [
            {"handcraft_part_item_id": pi.id, "qty": 3.0},
            {"handcraft_jewelry_item_id": ji.id, "qty": 2},
        ],
    })
    receipt_id = create_resp.json()["id"]
    resp = client.get(f"/api/handcraft-receipts/{receipt_id}")
    data = resp.json()

    part_item = next(i for i in data["items"] if i["item_type"] == "part")
    jewelry_item = next(i for i in data["items"] if i["item_type"] == "jewelry")

    assert part_item["item_name"] == "配件A"
    assert part_item["handcraft_order_id"] == order.id
    assert jewelry_item["item_name"] == "饰品A"
    assert jewelry_item["handcraft_order_id"] == order.id


# ── Suppliers endpoint ─────────────────────────────────────────────────


def test_suppliers_endpoint(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 3.0}],
    })
    resp = client.get("/api/handcraft-receipts/suppliers")
    assert resp.status_code == 200
    assert "测试手工商" in resp.json()


# ── Add items to existing receipt ──────────────────────────────────────


def test_add_items_to_receipt(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    create_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 3.0, "price": 1.0}],
    })
    receipt_id = create_resp.json()["id"]

    add_resp = client.post(f"/api/handcraft-receipts/{receipt_id}/items", json={
        "items": [{"handcraft_jewelry_item_id": ji.id, "qty": 2}],
    })
    assert add_resp.status_code == 201
    assert len(add_resp.json()["items"]) == 2


# ── Delivery images ───────────────────────────────────────────────────


def test_delivery_images(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    create_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 3.0}],
    })
    receipt_id = create_resp.json()["id"]

    resp = client.patch(f"/api/handcraft-receipts/{receipt_id}/delivery-images", json={
        "delivery_images": ["https://img.test/a.png", "https://img.test/b.png"],
    })
    assert resp.status_code == 200
    assert resp.json()["delivery_images"] == ["https://img.test/a.png", "https://img.test/b.png"]


# ── Send also sets part status ─────────────────────────────────────────


def test_send_sets_part_item_status(client, db):
    """Sending a handcraft order sets part items status to 制作中."""
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    db.refresh(pi)
    assert pi.status == "制作中"


# ── Filter by supplier ─────────────────────────────────────────────────


def test_list_filter_by_supplier(client, db):
    part, jewelry, order, pi, ji = _create_sent_handcraft(db, supplier_name="商家X")
    client.post("/api/handcraft-receipts/", json={
        "supplier_name": "商家X",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 3.0}],
    })
    resp = client.get("/api/handcraft-receipts/", params={"supplier_name": "商家X"})
    assert len(resp.json()) == 1
    resp2 = client.get("/api/handcraft-receipts/", params={"supplier_name": "商家Y"})
    assert len(resp2.json()) == 0


# ── Paid receipt blocks order deletion ─────────────────────────────────


def test_delete_order_blocked_by_paid_receipt(client, db):
    """Cannot delete a handcraft order if it has a paid receipt."""
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    create_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 3.0}],
        "status": "已付款",
    })
    assert create_resp.status_code == 201

    del_resp = client.delete(f"/api/handcraft/{order.id}")
    assert del_resp.status_code == 400
    assert "已付款" in del_resp.json()["detail"]


# ── Jewelry qty must be integer ────────────────────────────────────────


def test_jewelry_fractional_qty_rejected(client, db):
    """Jewelry receipt qty must be an integer."""
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_jewelry_item_id": ji.id, "qty": 2.5}],
    })
    assert resp.status_code == 422


def test_jewelry_integer_qty_accepted(client, db):
    """Jewelry receipt with integer qty (as float) should be accepted."""
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_jewelry_item_id": ji.id, "qty": 3.0}],
    })
    assert resp.status_code == 201


def test_jewelry_fractional_qty_rejected_at_service_level(db):
    """Service-level guard blocks fractional jewelry qty (bypasses schema)."""
    from services.handcraft_receipt import create_handcraft_receipt
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    with pytest.raises(ValueError, match="整数"):
        create_handcraft_receipt(db, "测试手工商", [
            {"handcraft_jewelry_item_id": ji.id, "qty": 2.5},
        ])


def test_both_item_ids_rejected_at_service_level(db):
    """Service-level guard blocks both item IDs set (bypasses schema)."""
    from services.handcraft_receipt import create_handcraft_receipt
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    with pytest.raises(ValueError, match="其中之一"):
        create_handcraft_receipt(db, "测试手工商", [
            {"handcraft_part_item_id": pi.id, "handcraft_jewelry_item_id": ji.id, "qty": 3},
        ])


def test_neither_item_id_rejected_at_service_level(db):
    """Service-level guard blocks missing item IDs (bypasses schema)."""
    from services.handcraft_receipt import create_handcraft_receipt
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    with pytest.raises(ValueError, match="其中之一"):
        create_handcraft_receipt(db, "测试手工商", [
            {"qty": 3},
        ])


# ── Handcraft cost sync ──────────────────────────────────────────────


def test_jewelry_handcraft_cost_synced_on_create(client, db):
    """Creating a receipt with jewelry price syncs handcraft_cost to Jewelry."""
    from models.jewelry import Jewelry
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_jewelry_item_id": ji.id, "qty": 3, "price": 5.0}],
    })
    assert resp.status_code == 201
    db.refresh(jewelry)
    assert float(jewelry.handcraft_cost) == pytest.approx(5.0)


def test_jewelry_handcraft_cost_diff_returned_and_synced(client, db):
    """When jewelry has a different handcraft_cost, diff is returned AND value is synced."""
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    jewelry.handcraft_cost = 3.0
    db.flush()
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_jewelry_item_id": ji.id, "qty": 2, "price": 7.0}],
    })
    assert resp.status_code == 201
    data = resp.json()
    # Diff should show old→new (detected before auto-set)
    hc_diffs = [d for d in data["cost_diffs"] if d["field"] == "handcraft_cost"]
    assert len(hc_diffs) == 1
    assert hc_diffs[0]["current_value"] == pytest.approx(3.0)
    assert hc_diffs[0]["new_value"] == pytest.approx(7.0)
    # Value should be synced after
    db.refresh(jewelry)
    assert float(jewelry.handcraft_cost) == pytest.approx(7.0)


def test_jewelry_handcraft_cost_diff_on_add_items(client, db):
    """Adding jewelry items to existing receipt syncs handcraft_cost."""
    from models.jewelry import Jewelry
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    create_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 3.0}],
    })
    receipt_id = create_resp.json()["id"]

    add_resp = client.post(f"/api/handcraft-receipts/{receipt_id}/items", json={
        "items": [{"handcraft_jewelry_item_id": ji.id, "qty": 2, "price": 8.0}],
    })
    assert add_resp.status_code == 201
    db.refresh(jewelry)
    assert float(jewelry.handcraft_cost) == pytest.approx(8.0)


# ── actual_qty (picking override) interacts with receipt cap + status ──


def _create_sent_handcraft_with_actual_qty(db, pi_qty=10.0, actual_qty=8.0):
    """Create + send a handcraft order whose atomic part item has an actual_qty
    override stashed in handcraft_picking_weight, plus a matching
    handcraft_picking_record so the override is honored as 勾选'd."""
    from decimal import Decimal
    from models.handcraft_order import HandcraftPickingRecord, HandcraftPickingWeight

    part = create_part(db, {"name": "配件AQ", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "饰品AQ", "category": "单件"})
    add_stock(db, "part", part.id, 100.0, "初始入库")
    order = create_handcraft_order(
        db, "测试手工商",
        parts=[{"part_id": part.id, "qty": pi_qty}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1}],
    )
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).one()
    db.add(HandcraftPickingWeight(
        handcraft_order_id=order.id,
        part_item_id=pi.id,
        atom_part_id=part.id,
        actual_qty=Decimal(str(actual_qty)),
    ))
    db.add(HandcraftPickingRecord(
        handcraft_order_id=order.id,
        handcraft_part_item_id=pi.id,
        part_id=part.id,
    ))
    db.flush()
    send_handcraft_order(db, order.id)
    db.flush()
    return part, jewelry, order, pi


def test_receipt_cap_rejects_over_effective_qty(client, db):
    """pi.qty=10, actual_qty=8: trying to receive 9 must fail (cap is 8)."""
    part, jewelry, order, pi = _create_sent_handcraft_with_actual_qty(db)
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 9.0}],
    })
    assert resp.status_code == 400
    assert "最多可回收 8" in resp.json()["detail"]


def test_receipt_at_effective_qty_flips_to_完成(client, db):
    """Receiving exactly effective_qty (8) must flip status to 已收回 even
    though pi.qty is still 10."""
    part, jewelry, order, pi = _create_sent_handcraft_with_actual_qty(db)
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 8.0}],
    })
    assert resp.status_code == 201
    db.refresh(pi)
    assert pi.status == "已收回"
    # Stock: 100 - 8 sent + 8 received = 100
    assert get_stock(db, "part", part.id) == pytest.approx(100.0)


def test_receipt_add_items_cap_uses_effective_qty(client, db):
    """The add-items endpoint enforces the same effective cap on subsequent receipts."""
    part, jewelry, order, pi = _create_sent_handcraft_with_actual_qty(db)
    # First receive 5 (under effective=8)
    create_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 5.0}],
    })
    assert create_resp.status_code == 201
    receipt_id = create_resp.json()["id"]

    # Try to add 4 more → would total 9 > effective 8 → reject
    add_resp = client.post(f"/api/handcraft-receipts/{receipt_id}/items", json={
        "items": [{"handcraft_part_item_id": pi.id, "qty": 4.0}],
    })
    assert add_resp.status_code == 400
    assert "最多可回收 3" in add_resp.json()["detail"]


def test_receipt_edit_qty_cap_uses_effective_qty(client, db):
    """Edit qty validation also uses effective cap."""
    part, jewelry, order, pi = _create_sent_handcraft_with_actual_qty(db)
    create_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 5.0}],
    })
    receipt_id = create_resp.json()["id"]
    item_id = create_resp.json()["items"][0]["id"]

    # Edit existing item to qty=9 → exceeds effective=8 → reject
    edit_resp = client.put(
        f"/api/handcraft-receipts/{receipt_id}/items/{item_id}",
        json={"qty": 9.0},
    )
    assert edit_resp.status_code == 400
    assert "最多可回收 8" in edit_resp.json()["detail"]


def test_order_auto_completes_when_all_effective_qty_received(client, db):
    """When every part item has received effective qty AND jewelry items are
    fully received, the order must auto-flip to completed. Previously the
    order-level completion check used pi.qty, so orders with actual_qty
    overrides got stuck in processing forever."""
    from models.handcraft_order import HandcraftOrder

    part, jewelry, order, pi = _create_sent_handcraft_with_actual_qty(db, pi_qty=10.0, actual_qty=8.0)

    # Receive effective (8) parts + all (1) jewelry
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [
            {"handcraft_part_item_id": pi.id, "qty": 8.0},
            {"handcraft_jewelry_item_id":
                db.query(HandcraftJewelryItem)
                .filter_by(handcraft_order_id=order.id).one().id,
             "qty": 1},
        ],
    })
    assert resp.status_code == 201

    db.refresh(order)
    assert order.status == "completed", (
        f"order should auto-complete (all effective qty received), got {order.status}"
    )


def test_receipt_response_reports_parts_shortfall(client, db):
    from services.part import create_part
    from services.jewelry import create_jewelry
    from services.bom import set_bom
    from services.inventory import add_stock
    from services.handcraft import create_handcraft_order, send_handcraft_order
    from models.handcraft_order import HandcraftJewelryItem

    part = create_part(db, {"name": "珠", "category": "小配件"})
    add_stock(db, "part", part.id, 1000, "入库")
    jewelry = create_jewelry(db, {"name": "项链", "category": "单件"})
    set_bom(db, jewelry.id, part.id, 10)
    order = create_handcraft_order(
        db, "商家S",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 10}],
    )
    send_handcraft_order(db, order.id)
    ji = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=order.id).first()

    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "商家S",
        "items": [{"handcraft_jewelry_item_id": ji.id, "qty": 10}],
    })
    assert resp.status_code == 201
    sf = resp.json()["parts_shortfall"]
    assert any(x["part_id"] == part.id and abs(x["shortfall_qty"] - 95.0) < 1e-6 for x in sf)


def test_pending_receive_filter_by_receipt_code(client, db):
    from datetime import date
    from services.part import create_part
    from services.inventory import add_stock
    from services.handcraft import create_handcraft_order, send_handcraft_order

    p = create_part(db, {"name": "珠", "category": "小配件"})
    add_stock(db, "part", p.id, 1000, "入库")
    # o1: today (will get a receipt_code)
    o1 = create_handcraft_order(db, "商家R", parts=[{"part_id": p.id, "qty": 10}])
    send_handcraft_order(db, o1.id)
    # o2: historic date forces a separate order (no auto-merge)
    o2 = create_handcraft_order(db, "商家R", parts=[{"part_id": p.id, "qty": 20}], created_at=date(2020, 1, 1))
    send_handcraft_order(db, o2.id)

    from models.handcraft_order import HandcraftOrder
    code1 = db.query(HandcraftOrder).filter_by(id=o1.id).first().receipt_code

    resp = client.get(f"/api/handcraft/items/pending-receive?receipt_code={code1}")
    assert resp.status_code == 200
    rows = resp.json()
    assert rows, "should return items for that order"
    assert all(r["handcraft_order_id"] == o1.id for r in rows)
