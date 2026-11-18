"""Output settlement is independent of sent-material balances; no forced stock."""
from datetime import datetime

import pytest
from sqlalchemy import text

from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem, HandcraftPickingRecord, HandcraftPickingWeight
from services.handcraft import create_handcraft_order, send_handcraft_order
from services.handcraft_receipt import create_handcraft_receipt, handcraft_order_is_settled, _check_handcraft_order_completion
from services.inventory import add_stock, get_stock
from services.jewelry import create_jewelry
from services.part import create_part


def make_order(db, *, outputs=True, composite=False):
    material = create_part(db, {"name": "包装", "category": "小配件"})
    product = (create_part(db, {"name": "组合产出", "category": "小配件", "is_composite": True})
               if composite else create_jewelry(db, {"name": "饰品", "category": "单件"}))
    add_stock(db, "part", material.id, 100, "测试入库")
    order = create_handcraft_order(db, "结清测试商家", parts=[{"part_id": material.id, "qty": 30}],
        jewelries=[{"part_id" if composite else "jewelry_id": product.id, "qty": 10}] if outputs else [])
    send_handcraft_order(db, order.id)
    part = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).one()
    output = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=order.id).one_or_none()
    return order, material, product, part, output


def unchanged_business(db):
    db.flush()
    tables = ("handcraft_part_item", "handcraft_jewelry_item", "handcraft_receipt", "handcraft_receipt_item",
              "production_loss", "vendor_receipt", "inventory_log", "id_counter")
    return {table: sorted(db.execute(text(f'SELECT row_to_json(t)::text FROM "{table}" t')).scalars()) for table in tables}


@pytest.mark.parametrize("composite", [False, True])
def test_output_receipt_completes_without_processing_material_balance(client, db, composite):
    order, material, product, part, output = make_order(db, composite=composite)
    response = client.post("/api/handcraft-receipts/", json={"supplier_name": order.supplier_name,
        "items": [{"handcraft_jewelry_item_id": output.id, "qty": 10}]})
    assert response.status_code == 201
    db.refresh(order)
    db.refresh(part)
    assert order.status == "completed" and order.completed_at
    assert float(part.received_qty or 0) == float(part.returned_qty or 0) == float(part.consumed_qty or 0) == 0
    assert part.status == "制作中"
    assert get_stock(db, "part", material.id) == 70
    assert get_stock(db, "part" if composite else "jewelry", product.id) == 10


@pytest.mark.parametrize("received,loss", [(0, 10), (7, 3)])
def test_loss_settles_output_without_fake_receipts_or_material_returns(client, db, received, loss):
    order, material, product, part, output = make_order(db)
    if received:
        create_handcraft_receipt(db, order.supplier_name, [{"handcraft_jewelry_item_id": output.id, "qty": received}])
    response = client.post(f"/api/handcraft/{order.id}/items/{output.id}/confirm-loss",
                           json={"item_type": "jewelry", "loss_qty": loss})
    assert response.status_code == 200
    db.refresh(order)
    db.refresh(part)
    assert order.status == "completed"
    assert float(part.received_qty or 0) == 0
    assert get_stock(db, "part", material.id) == 70
    assert get_stock(db, "jewelry", product.id) == received
    assert db.execute(text("SELECT COALESCE(SUM(qty), 0) FROM handcraft_receipt_item")).scalar() == received


def test_each_output_must_be_settled_not_just_total_quantity(db):
    order, _, product, _, output = make_order(db)
    output.received_qty = 20
    second = HandcraftJewelryItem(handcraft_order_id=order.id, jewelry_id=product.id, qty=10, received_qty=0, status="制作中")
    db.add(second)
    db.flush()
    _check_handcraft_order_completion(db, order.id)
    assert order.status == "processing"
    second.received_qty = 10
    _check_handcraft_order_completion(db, order.id)
    assert order.status == "completed"


@pytest.mark.parametrize("mutation", ["delete", "reduce", "delete_item"])
def test_reversing_output_receipt_reopens_order_even_with_unsettled_materials(client, db, mutation):
    order, _, _, part, output = make_order(db)
    receipt = create_handcraft_receipt(db, order.supplier_name, [
        {"handcraft_jewelry_item_id": output.id, "qty": 10},
        {"handcraft_part_item_id": part.id, "qty": 1},
    ])
    assert order.status == "completed"
    if mutation == "delete":
        response = client.delete(f"/api/handcraft-receipts/{receipt.id}")
    elif mutation == "delete_item":
        response = client.delete(f"/api/handcraft-receipts/{receipt.id}/items/{receipt.items[0].id}")
    else:
        response = client.put(f"/api/handcraft-receipts/{receipt.id}/items/{receipt.items[0].id}", json={"qty": 9})
    assert response.status_code in (200, 204)
    db.refresh(order)
    assert order.status == "processing" and order.completed_at is None


def test_material_return_and_its_reversal_do_not_reopen_output_settled_order(client, db):
    order, _, _, part, output = make_order(db)
    create_handcraft_receipt(db, order.supplier_name, [{"handcraft_jewelry_item_id": output.id, "qty": 10}])
    completed_at = order.completed_at
    receipt = create_handcraft_receipt(db, order.supplier_name, [{"handcraft_part_item_id": part.id, "qty": 5}])
    response = client.delete(f"/api/handcraft-receipts/{receipt.id}")
    assert response.status_code == 204
    db.refresh(order)
    assert order.status == "completed" and order.completed_at == completed_at


@pytest.mark.parametrize("entry", ["handcraft", "kanban"])
def test_existing_stuck_order_can_finish_without_any_business_side_effects(client, db, entry):
    order, _, _, _, output = make_order(db)
    create_handcraft_receipt(db, order.supplier_name, [{"handcraft_jewelry_item_id": output.id, "qty": 10}])
    # Reproduce a pre-fix order whose output settled while materials blocked it.
    order.status, order.completed_at = "processing", None
    before = unchanged_business(db)
    response = (client.patch(f"/api/handcraft/{order.id}/status", json={"status": "completed"}) if entry == "handcraft"
        else client.post("/api/kanban/order-status", json={"order_id": order.id, "order_type": "handcraft", "new_status": "completed"}))
    assert response.status_code == 200
    db.refresh(order)
    assert order.status == "completed" and order.completed_at
    assert unchanged_business(db) == before
    finished_at = order.completed_at
    response = client.patch(f"/api/handcraft/{order.id}/status", json={"status": "completed"})
    assert response.status_code == 200
    db.refresh(order)
    assert order.completed_at == finished_at and unchanged_business(db) == before


@pytest.mark.parametrize("entry", ["handcraft", "kanban"])
def test_unsettled_output_cannot_be_forced_complete_or_added_to_stock(client, db, entry):
    order, _, _, _, _ = make_order(db)
    before = unchanged_business(db)
    response = (client.patch(f"/api/handcraft/{order.id}/status", json={"status": "completed"}) if entry == "handcraft"
        else client.post("/api/kanban/order-status", json={"order_id": order.id, "order_type": "handcraft", "new_status": "completed"}))
    assert response.status_code == 400
    assert "结清" in response.json()["detail"]
    db.refresh(order)
    assert order.status == "processing" and unchanged_business(db) == before


def test_no_outputs_preserves_material_effective_quantity_rule(client, db):
    order, material, _, part, _ = make_order(db, outputs=False)
    db.add(HandcraftPickingRecord(handcraft_order_id=order.id, handcraft_part_item_id=part.id, part_id=material.id))
    db.add(HandcraftPickingWeight(handcraft_order_id=order.id, part_item_id=part.id, atom_part_id=material.id, actual_qty=8))
    db.flush()
    create_handcraft_receipt(db, order.supplier_name, [{"handcraft_part_item_id": part.id, "qty": 7}])
    assert order.status == "processing"
    create_handcraft_receipt(db, order.supplier_name, [{"handcraft_part_item_id": part.id, "qty": 1}])
    assert order.status == "completed"


def test_empty_order_never_completes(db):
    order = HandcraftOrder(id="HC-EMPTY", supplier_name="空单", status="processing")
    db.add(order)
    db.flush()
    assert not handcraft_order_is_settled(db, order.id)
    _check_handcraft_order_completion(db, order.id)
    assert order.status == "processing"


@pytest.mark.parametrize("state", ["pending", "archived"])
def test_pending_and_archived_orders_cannot_be_finished(client, db, state):
    order, _, _, _, output = make_order(db)
    output.received_qty = output.qty
    if state == "pending":
        order.status = "pending"
    else:
        order.archived_at = datetime(2026, 11, 17)
    db.flush()
    before = unchanged_business(db)
    response = client.patch(f"/api/handcraft/{order.id}/status", json={"status": "completed"})
    assert response.status_code in (400, 409)
    assert unchanged_business(db) == before
    _check_handcraft_order_completion(db, order.id)
    assert order.status != "completed"
