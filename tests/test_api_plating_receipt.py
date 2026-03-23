# tests/test_api_plating_receipt.py
import pytest

from services.part import create_part
from services.inventory import add_stock, get_stock
from services.plating import (
    create_plating_order, send_plating_order, get_plating_order, get_plating_items,
    delete_plating_order,
)
from models.plating_receipt import PlatingReceipt, PlatingReceiptItem


def _setup_processing_plating(db, part_name="P1", qty=10.0, supplier="Supplier A",
                               plating_method="金色", receive_part_id=None):
    """Helper: create a part with stock, create + send a plating order."""
    part = create_part(db, {"name": part_name, "category": "小配件"})
    add_stock(db, "part", part.id, qty + 10, "初始库存")

    items = [{"part_id": part.id, "qty": qty, "plating_method": plating_method}]
    if receive_part_id:
        items[0]["receive_part_id"] = receive_part_id
    order = create_plating_order(db, supplier, items)
    send_plating_order(db, order.id)
    db.flush()
    return part, order


def test_create_plating_receipt(client, db):
    part, order = _setup_processing_plating(db)
    poi_id = get_plating_items(db, order.id)[0].id

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Supplier A",
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 5.0, "price": 2.0}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("ER-")
    assert data["status"] == "未付款"
    assert data["total_amount"] == 10.0
    assert len(data["items"]) == 1
    assert data["items"][0]["qty"] == 5.0


def test_create_receipt_exceeds_remaining(client, db):
    part, order = _setup_processing_plating(db, qty=10.0)
    poi_id = get_plating_items(db, order.id)[0].id

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Supplier A",
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 15.0}],
    })
    assert resp.status_code == 400


def test_delete_paid_receipt_rejected(client, db):
    part, order = _setup_processing_plating(db)
    poi_id = get_plating_items(db, order.id)[0].id

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Supplier A",
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 5.0}],
        "status": "已付款",
    })
    receipt_id = resp.json()["id"]

    del_resp = client.delete(f"/api/plating-receipts/{receipt_id}")
    assert del_resp.status_code == 400


def test_delivery_images_max_9(client, db):
    part, order = _setup_processing_plating(db)
    poi_id = get_plating_items(db, order.id)[0].id

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Supplier A",
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 5.0}],
    })
    receipt_id = resp.json()["id"]

    # 9 images OK
    img_resp = client.patch(f"/api/plating-receipts/{receipt_id}/delivery-images", json={
        "delivery_images": [f"img{i}.jpg" for i in range(9)]
    })
    assert img_resp.status_code == 200

    # 10 images rejected (Pydantic max_length=9 catches it → 422)
    img_resp2 = client.patch(f"/api/plating-receipts/{receipt_id}/delivery-images", json={
        "delivery_images": [f"img{i}.jpg" for i in range(10)]
    })
    assert img_resp2.status_code in (400, 422)


def test_create_receipt_completes_plating_order(client, db):
    """Fully receive all items -> plating order status becomes 'completed'."""
    part, order = _setup_processing_plating(db, qty=10.0)
    poi_id = get_plating_items(db, order.id)[0].id

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Supplier A",
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 10.0, "price": 1.0}],
    })
    assert resp.status_code == 201

    # Plating order should now be completed
    updated_order = get_plating_order(db, order.id)
    assert updated_order.status == "completed"


def test_create_receipt_partial_receive(client, db):
    """Partial receive, plating order stays 'processing'."""
    part, order = _setup_processing_plating(db, qty=10.0)
    poi_id = get_plating_items(db, order.id)[0].id

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Supplier A",
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 5.0}],
    })
    assert resp.status_code == 201

    updated_order = get_plating_order(db, order.id)
    assert updated_order.status == "processing"


def test_delete_receipt_reverses_stock(client, db):
    """Delete unpaid receipt, verify stock reversed and plating order received_qty reversed."""
    part, order = _setup_processing_plating(db, qty=10.0)
    poi_id = get_plating_items(db, order.id)[0].id

    stock_before = get_stock(db, "part", part.id)

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Supplier A",
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 5.0}],
    })
    receipt_id = resp.json()["id"]
    assert get_stock(db, "part", part.id) == pytest.approx(stock_before + 5.0)

    del_resp = client.delete(f"/api/plating-receipts/{receipt_id}")
    assert del_resp.status_code == 204

    # Stock should be back to before
    assert get_stock(db, "part", part.id) == pytest.approx(stock_before)

    # Plating order item received_qty should be back to 0
    poi = get_plating_items(db, order.id)[0]
    assert float(poi.received_qty) == pytest.approx(0.0)


def test_update_receipt_item_qty(client, db):
    """Change qty, verify stock diff applied."""
    part, order = _setup_processing_plating(db, qty=10.0)
    poi_id = get_plating_items(db, order.id)[0].id

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Supplier A",
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 5.0, "price": 1.0}],
    })
    receipt_id = resp.json()["id"]
    item_id = resp.json()["items"][0]["id"]
    stock_after_create = get_stock(db, "part", part.id)

    # Increase qty to 8
    update_resp = client.put(f"/api/plating-receipts/{receipt_id}/items/{item_id}", json={"qty": 8.0})
    assert update_resp.status_code == 200
    assert update_resp.json()["qty"] == 8.0

    # Stock should have increased by 3 more
    assert get_stock(db, "part", part.id) == pytest.approx(stock_after_create + 3.0)


def test_delete_receipt_item(client, db):
    """Delete item from receipt with 2 items, verify stock reversed."""
    part1, order1 = _setup_processing_plating(db, part_name="DP1", qty=10.0)
    part2, order2 = _setup_processing_plating(db, part_name="DP2", qty=10.0)
    poi1_id = get_plating_items(db, order1.id)[0].id
    poi2_id = get_plating_items(db, order2.id)[0].id

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Supplier A",
        "items": [
            {"plating_order_item_id": poi1_id, "part_id": part1.id, "qty": 5.0},
            {"plating_order_item_id": poi2_id, "part_id": part2.id, "qty": 3.0},
        ],
    })
    receipt_id = resp.json()["id"]
    item1_id = resp.json()["items"][0]["id"]

    stock_before_delete = get_stock(db, "part", part1.id)

    del_resp = client.delete(f"/api/plating-receipts/{receipt_id}/items/{item1_id}")
    assert del_resp.status_code == 204

    # Stock of part1 should be reversed
    assert get_stock(db, "part", part1.id) == pytest.approx(stock_before_delete - 5.0)


def test_status_toggle(client, db):
    """Toggle 未付款 <-> 已付款."""
    part, order = _setup_processing_plating(db)
    poi_id = get_plating_items(db, order.id)[0].id

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Supplier A",
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 5.0}],
    })
    receipt_id = resp.json()["id"]
    assert resp.json()["status"] == "未付款"

    # Toggle to 已付款
    status_resp = client.patch(f"/api/plating-receipts/{receipt_id}/status", json={"status": "已付款"})
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "已付款"
    assert status_resp.json()["paid_at"] is not None

    # Toggle back to 未付款
    status_resp2 = client.patch(f"/api/plating-receipts/{receipt_id}/status", json={"status": "未付款"})
    assert status_resp2.status_code == 200
    assert status_resp2.json()["status"] == "未付款"
    assert status_resp2.json()["paid_at"] is None


def test_list_receipts(client, db):
    """List all, list by vendor_name."""
    part1, order1 = _setup_processing_plating(db, part_name="LP1", supplier="Vendor X")
    part2, order2 = _setup_processing_plating(db, part_name="LP2", supplier="Vendor Y")
    poi1_id = get_plating_items(db, order1.id)[0].id
    poi2_id = get_plating_items(db, order2.id)[0].id

    client.post("/api/plating-receipts/", json={
        "vendor_name": "Vendor X",
        "items": [{"plating_order_item_id": poi1_id, "part_id": part1.id, "qty": 5.0}],
    })
    client.post("/api/plating-receipts/", json={
        "vendor_name": "Vendor Y",
        "items": [{"plating_order_item_id": poi2_id, "part_id": part2.id, "qty": 3.0}],
    })

    # List all
    all_resp = client.get("/api/plating-receipts/")
    assert all_resp.status_code == 200
    assert len(all_resp.json()) == 2

    # List by vendor
    filtered_resp = client.get("/api/plating-receipts/?vendor_name=Vendor X")
    assert filtered_resp.status_code == 200
    assert len(filtered_resp.json()) == 1
    assert filtered_resp.json()[0]["vendor_name"] == "Vendor X"


def test_receipt_with_receive_part_id(client, db):
    """Plating order item with receive_part_id, verify stock goes to receive_part_id."""
    part_a = create_part(db, {"name": "原色件", "category": "小配件"})
    part_b = create_part(db, {"name": "金色件", "category": "小配件", "parent_part_id": part_a.id})
    add_stock(db, "part", part_a.id, 30.0, "初始库存")

    order = create_plating_order(db, "Supplier RCV", [
        {"part_id": part_a.id, "qty": 10.0, "plating_method": "金色", "receive_part_id": part_b.id}
    ])
    send_plating_order(db, order.id)
    db.flush()

    poi = get_plating_items(db, order.id)[0]

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Supplier RCV",
        "items": [{"plating_order_item_id": poi.id, "part_id": part_b.id, "qty": 10.0, "price": 1.5}],
    })
    assert resp.status_code == 201

    # Stock should go to part_b, not part_a
    assert get_stock(db, "part", part_a.id) == pytest.approx(20.0)  # 30 - 10 sent
    assert get_stock(db, "part", part_b.id) == pytest.approx(10.0)  # 10 received


def test_delete_plating_order_cleans_up_empty_receipt(db):
    """Deleting a plating order should delete PlatingReceiptItems and remove
    empty PlatingReceipt records, not leave orphaned receipts."""
    part, order = _setup_processing_plating(db, qty=10.0)
    poi_id = get_plating_items(db, order.id)[0].id

    from services.plating_receipt import create_plating_receipt
    receipt = create_plating_receipt(db, vendor_name="Supplier A", items=[
        {"plating_order_item_id": poi_id, "part_id": part.id, "qty": 5.0, "price": 2.0},
    ])
    receipt_id = receipt.id
    db.flush()

    # Verify receipt exists
    assert db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first() is not None

    # Delete the plating order
    delete_plating_order(db, order.id)
    db.flush()

    # Receipt should be gone (it had no other items)
    assert db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first() is None
    # Receipt items should also be gone
    assert db.query(PlatingReceiptItem).filter(PlatingReceiptItem.plating_receipt_id == receipt_id).count() == 0


def test_delete_plating_order_keeps_receipt_with_remaining_items(db):
    """If a receipt has items from multiple plating orders, deleting one order
    should only remove the related items and recalc total, not delete the receipt."""
    part1, order1 = _setup_processing_plating(db, part_name="MR1", qty=10.0)
    part2, order2 = _setup_processing_plating(db, part_name="MR2", qty=10.0)
    poi1_id = get_plating_items(db, order1.id)[0].id
    poi2_id = get_plating_items(db, order2.id)[0].id

    from services.plating_receipt import create_plating_receipt
    receipt = create_plating_receipt(db, vendor_name="Supplier A", items=[
        {"plating_order_item_id": poi1_id, "part_id": part1.id, "qty": 5.0, "price": 2.0},
        {"plating_order_item_id": poi2_id, "part_id": part2.id, "qty": 3.0, "price": 1.0},
    ])
    receipt_id = receipt.id
    db.flush()
    assert float(receipt.total_amount) == pytest.approx(13.0)  # 5*2 + 3*1

    # Delete order1
    delete_plating_order(db, order1.id)
    db.flush()

    # Receipt should still exist with 1 item
    pr = db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first()
    assert pr is not None
    remaining = db.query(PlatingReceiptItem).filter(PlatingReceiptItem.plating_receipt_id == receipt_id).all()
    assert len(remaining) == 1
    assert remaining[0].part_id == part2.id
    # Total should be recalculated
    assert float(pr.total_amount) == pytest.approx(3.0)


def test_create_receipt_cross_vendor_rejected(client, db):
    """Creating a receipt with items from a different vendor should fail."""
    part_a, order_a = _setup_processing_plating(db, part_name="CVA", qty=10.0, supplier="Vendor A")
    poi_a_id = get_plating_items(db, order_a.id)[0].id

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Vendor B",
        "items": [{"plating_order_item_id": poi_a_id, "part_id": part_a.id, "qty": 5.0}],
    })
    assert resp.status_code == 400
    assert "不一致" in resp.json()["detail"]


def test_kanban_rollback_then_delete_receipt_no_double_deduct(db):
    """Bug regression: kanban processing→pending rollback cleans up receipt items and stock.
    After rollback the receipt should be gone, so no double-deduct occurs."""
    from services.kanban import change_order_status

    part, order = _setup_processing_plating(db, qty=10.0)
    poi_id = get_plating_items(db, order.id)[0].id

    # Initial stock: 20 (added 20) - 10 (sent) = 10
    assert get_stock(db, "part", part.id) == pytest.approx(10.0)

    # Receive 5 via plating receipt
    from services.plating_receipt import create_plating_receipt
    receipt = create_plating_receipt(db, vendor_name="Supplier A", items=[
        {"plating_order_item_id": poi_id, "part_id": part.id, "qty": 5.0, "price": 2.0},
    ])
    receipt_id = receipt.id
    db.flush()

    # Stock should be 15 (10 + 5 received)
    assert get_stock(db, "part", part.id) == pytest.approx(15.0)

    # Kanban rollback: processing → pending (reverses stock from receipts + send)
    change_order_status(db, order.id, "plating", "pending")
    db.flush()

    # Stock should be back to 20 (all stock effects reversed)
    assert get_stock(db, "part", part.id) == pytest.approx(20.0)

    # Receipt should have been cleaned up by kanban rollback
    assert db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first() is None
    assert db.query(PlatingReceiptItem).filter(PlatingReceiptItem.plating_receipt_id == receipt_id).count() == 0

    # PlatingOrderItem received_qty should be 0
    poi = get_plating_items(db, order.id)[0]
    assert float(poi.received_qty or 0) == 0.0


def test_kanban_completed_to_processing_cleans_receipts(db):
    """Kanban completed→processing rollback should clean up receipt data."""
    from services.kanban import change_order_status

    part, order = _setup_processing_plating(db, qty=10.0)
    poi_id = get_plating_items(db, order.id)[0].id

    # Fully receive
    from services.plating_receipt import create_plating_receipt
    receipt = create_plating_receipt(db, vendor_name="Supplier A", items=[
        {"plating_order_item_id": poi_id, "part_id": part.id, "qty": 10.0, "price": 1.0},
    ])
    receipt_id = receipt.id
    db.flush()

    # Order should be completed
    order_after = get_plating_order(db, order.id)
    assert order_after.status == "completed"

    stock_before_rollback = get_stock(db, "part", part.id)

    # Rollback: completed → processing
    change_order_status(db, order.id, "plating", "processing")
    db.flush()

    # Stock should have the 10 received reversed
    expected_stock = stock_before_rollback - 10.0
    assert get_stock(db, "part", part.id) == pytest.approx(expected_stock)

    # Receipt should be gone
    assert db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first() is None

    # received_qty should be 0
    poi = get_plating_items(db, order.id)[0]
    assert float(poi.received_qty or 0) == 0.0


def test_create_receipt_null_price(client, db):
    """Price=null should be stored as null, not 0."""
    part, order = _setup_processing_plating(db, qty=10.0)
    poi_id = get_plating_items(db, order.id)[0].id

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "Supplier A",
        "items": [{"plating_order_item_id": poi_id, "part_id": part.id, "qty": 5.0, "price": None}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["items"][0]["price"] is None
    assert data["items"][0]["amount"] is None
    assert data["total_amount"] == 0.0
