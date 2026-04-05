import pytest
from decimal import Decimal
from models.part import Part
from models.plating_order import PlatingOrder, PlatingOrderItem
from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
from models.jewelry import Jewelry
from models.production_loss import ProductionLoss
from services.inventory import add_stock, get_stock


def _setup_plating_with_partial_receive(db):
    """Create plating order: sent 100, received 80, gap 20."""
    part = Part(id="PJ-X-LOSS1", name="损耗测试配件", category="小配件")
    db.add(part)
    db.flush()
    add_stock(db, "part", part.id, 100, "入库")
    db.flush()

    po = PlatingOrder(id="EP-LOSS1", supplier_name="电镀商", status="processing")
    db.add(po)
    db.flush()
    poi = PlatingOrderItem(
        plating_order_id=po.id,
        part_id=part.id,
        qty=100,
        received_qty=80,
        status="电镀中",
    )
    db.add(poi)
    db.flush()
    return part, po, poi


def _setup_handcraft_with_partial_receive(db):
    """Create handcraft order: part sent 50, received 40; jewelry sent 30, received 25."""
    part = Part(id="PJ-X-LOSS2", name="手工损耗配件", category="小配件")
    jewelry = Jewelry(id="SP-LOSS1", name="手工损耗饰品", category="项链")
    db.add_all([part, jewelry])
    db.flush()
    add_stock(db, "part", part.id, 50, "入库")
    db.flush()

    hc = HandcraftOrder(id="HC-LOSS1", supplier_name="手工商", status="processing")
    db.add(hc)
    db.flush()
    hc_part = HandcraftPartItem(
        handcraft_order_id=hc.id,
        part_id=part.id,
        qty=50,
        received_qty=40,
        status="制作中",
    )
    hc_jewelry = HandcraftJewelryItem(
        handcraft_order_id=hc.id,
        jewelry_id=jewelry.id,
        qty=30,
        received_qty=25,
        status="制作中",
    )
    db.add_all([hc_part, hc_jewelry])
    db.flush()
    return part, jewelry, hc, hc_part, hc_jewelry


def test_confirm_plating_loss(client, db):
    """Confirm loss on plating item: received_qty increases, loss record created."""
    part, po, poi = _setup_plating_with_partial_receive(db)
    resp = client.post(
        f"/api/plating/{po.id}/items/{poi.id}/confirm-loss",
        json={"loss_qty": 20, "reason": "电镀损耗"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["loss_qty"] == 20
    assert data["order_type"] == "plating"

    # Verify received_qty updated
    db.refresh(poi)
    assert float(poi.received_qty) == 100
    assert poi.status == "已收回"

    # Verify loss record exists
    loss = db.query(ProductionLoss).filter_by(item_id=poi.id).first()
    assert loss is not None
    assert float(loss.loss_qty) == 20


def test_confirm_plating_loss_completes_order(client, db):
    """After confirming loss on all items, plating order becomes completed."""
    part, po, poi = _setup_plating_with_partial_receive(db)
    client.post(
        f"/api/plating/{po.id}/items/{poi.id}/confirm-loss",
        json={"loss_qty": 20},
    )
    db.refresh(po)
    assert po.status == "completed"


def test_confirm_plating_loss_exceeds_gap(client, db):
    """Cannot confirm loss greater than gap."""
    part, po, poi = _setup_plating_with_partial_receive(db)
    resp = client.post(
        f"/api/plating/{po.id}/items/{poi.id}/confirm-loss",
        json={"loss_qty": 25},  # gap is only 20
    )
    assert resp.status_code == 400


def test_confirm_plating_loss_with_deduction(client, db):
    """Confirm loss with deduction amount."""
    part, po, poi = _setup_plating_with_partial_receive(db)
    resp = client.post(
        f"/api/plating/{po.id}/items/{poi.id}/confirm-loss",
        json={"loss_qty": 20, "deduct_amount": 50.0, "reason": "品质不良"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["deduct_amount"] == 50.0
    assert data["reason"] == "品质不良"


def test_confirm_handcraft_part_loss(client, db):
    """Confirm loss on handcraft part item."""
    part, jewelry, hc, hc_part, hc_jewelry = _setup_handcraft_with_partial_receive(db)
    resp = client.post(
        f"/api/handcraft/{hc.id}/items/{hc_part.id}/confirm-loss",
        json={"loss_qty": 10, "item_type": "part"},
    )
    assert resp.status_code == 200
    db.refresh(hc_part)
    assert float(hc_part.received_qty) == 50
    assert hc_part.status == "已收回"


def test_confirm_handcraft_jewelry_loss(client, db):
    """Confirm loss on handcraft jewelry item."""
    part, jewelry, hc, hc_part, hc_jewelry = _setup_handcraft_with_partial_receive(db)
    resp = client.post(
        f"/api/handcraft/{hc.id}/items/{hc_jewelry.id}/confirm-loss",
        json={"loss_qty": 5, "item_type": "jewelry"},
    )
    assert resp.status_code == 200
    db.refresh(hc_jewelry)
    assert hc_jewelry.received_qty == 30
    assert hc_jewelry.status == "已收回"


def test_confirm_loss_inventory_log(client, db):
    """Confirm loss writes inventory log with change_qty=0."""
    from models.inventory_log import InventoryLog
    part, po, poi = _setup_plating_with_partial_receive(db)
    client.post(
        f"/api/plating/{po.id}/items/{poi.id}/confirm-loss",
        json={"loss_qty": 20, "reason": "正常损耗"},
    )
    log = (
        db.query(InventoryLog)
        .filter_by(item_type="part", item_id=part.id, reason="电镀损耗")
        .first()
    )
    assert log is not None
    assert float(log.change_qty) == 0
    assert "损耗 20" in log.note


def test_batch_confirm_plating_loss_via_receipt(client, db):
    """Batch confirm losses from receipt endpoint."""
    part = Part(id="PJ-X-LOSS3", name="批量损耗配件", category="小配件")
    db.add(part)
    db.flush()
    add_stock(db, "part", part.id, 200, "入库")
    db.flush()

    po = PlatingOrder(id="EP-LOSS2", supplier_name="电镀商B", status="processing")
    db.add(po)
    db.flush()
    poi1 = PlatingOrderItem(plating_order_id=po.id, part_id=part.id, qty=100, received_qty=90, status="电镀中")
    poi2 = PlatingOrderItem(plating_order_id=po.id, part_id=part.id, qty=50, received_qty=45, status="电镀中")
    db.add_all([poi1, poi2])
    db.flush()

    # Create a receipt (qty must fit within remaining gap)
    from services.plating_receipt import create_plating_receipt
    receipt = create_plating_receipt(db, vendor_name="电镀商B", items=[
        {"plating_order_item_id": poi1.id, "part_id": part.id, "qty": 5, "price": 1.0},
    ])
    db.flush()
    # After receipt: poi1 received_qty=95 (gap=5), poi2 received_qty=45 (gap=5)

    resp = client.post(
        f"/api/plating-receipts/{receipt.id}/confirm-loss",
        json={
            "items": [
                {"plating_order_item_id": poi1.id, "loss_qty": 5},
            ]
        },
    )
    assert resp.status_code == 200
    assert resp.json()["confirmed_count"] == 1


def test_batch_confirm_plating_loss_rejects_unrelated_item(client, db):
    """Batch confirm-loss rejects items not belonging to the receipt."""
    part = Part(id="PJ-X-LOSS4", name="越权测试配件", category="小配件")
    db.add(part)
    db.flush()
    add_stock(db, "part", part.id, 200, "入库")
    db.flush()

    po = PlatingOrder(id="EP-LOSS3", supplier_name="电镀商C", status="processing")
    db.add(po)
    db.flush()
    poi1 = PlatingOrderItem(plating_order_id=po.id, part_id=part.id, qty=100, received_qty=90, status="电镀中")
    poi2 = PlatingOrderItem(plating_order_id=po.id, part_id=part.id, qty=50, received_qty=45, status="电镀中")
    db.add_all([poi1, poi2])
    db.flush()

    # Receipt only contains poi1
    from services.plating_receipt import create_plating_receipt
    receipt = create_plating_receipt(db, vendor_name="电镀商C", items=[
        {"plating_order_item_id": poi1.id, "part_id": part.id, "qty": 5, "price": 1.0},
    ])
    db.flush()

    # Try to confirm loss on poi2 via receipt that only has poi1 — should be rejected
    resp = client.post(
        f"/api/plating-receipts/{receipt.id}/confirm-loss",
        json={
            "items": [
                {"plating_order_item_id": poi2.id, "loss_qty": 5},
            ]
        },
    )
    assert resp.status_code == 400

    # poi2 should be untouched
    db.refresh(poi2)
    assert float(poi2.received_qty) == 45


def test_confirm_handcraft_jewelry_loss_fractional_rejected(client, db):
    """Fractional loss_qty on jewelry item should be rejected."""
    part, jewelry, hc, hc_part, hc_jewelry = _setup_handcraft_with_partial_receive(db)
    resp = client.post(
        f"/api/handcraft/{hc.id}/items/{hc_jewelry.id}/confirm-loss",
        json={"loss_qty": 0.5, "item_type": "jewelry"},
    )
    assert resp.status_code == 400

    # received_qty should be unchanged
    db.refresh(hc_jewelry)
    assert hc_jewelry.received_qty == 25


def test_confirm_plating_loss_nonexistent_order_returns_404(client, db):
    """Confirm loss on nonexistent plating order should return 404."""
    resp = client.post(
        "/api/plating/EP-NONEXIST/items/1/confirm-loss",
        json={"loss_qty": 1},
    )
    assert resp.status_code == 404


def test_confirm_handcraft_loss_nonexistent_order_returns_404(client, db):
    """Confirm loss on nonexistent handcraft order should return 404."""
    resp = client.post(
        "/api/handcraft/HC-NONEXIST/items/1/confirm-loss",
        json={"loss_qty": 1, "item_type": "part"},
    )
    assert resp.status_code == 404
