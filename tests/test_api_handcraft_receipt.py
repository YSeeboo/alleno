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
    part, jewelry, order, pi, ji = _create_sent_handcraft(db)
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "测试手工商",
        "items": [{"handcraft_part_item_id": pi.id, "qty": 5.0, "price": 2.5}],
    })
    assert resp.status_code == 201
    data = resp.json()
    # Part has no bead_cost set, so there should be a diff
    assert len(data["cost_diffs"]) == 1
    assert data["cost_diffs"][0]["field"] == "bead_cost"
    assert data["cost_diffs"][0]["new_value"] == pytest.approx(2.5)


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
