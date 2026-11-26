"""Estimate batches and input links must not masquerade as output allocations.

Fictional records only; tests/conftest.py redirects all access to an isolated DB.
"""
from uuid import uuid4

import pytest

from models.bom import Bom
from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem, HandcraftPartItem
from models.inventory_log import InventoryLog
from models.jewelry import Jewelry
from models.order import Order, OrderItem, OrderItemLink, OrderTodoBatch, OrderTodoBatchJewelry, OrderTodoItem
from models.part import Part
from models.plating_order import PlatingOrder, PlatingOrderItem
from models.purchase_order import PurchaseOrder, PurchaseOrderItem
from models.production_allocation import ProductionAllocation
from services.production_allocation import legacy_demand_claim, order_production, production_uses, replace_order_source
from services.order import delete_order_item


@pytest.fixture
def old_estimate(db):
    db.add_all([Order(id="OR-review", customer_name="测试客户"), Order(id="OR-other", customer_name="其他客户"),
                Jewelry(id="SP-review", name="测试饰品", unit="卡"), Part(id="PJ-review", name="测试配件", unit="个"),
                HandcraftOrder(id="HC-history", supplier_name="历史商家", status="completed"),
                HandcraftOrder(id="HC-free", supplier_name="新商家"), PlatingOrder(id="EP-review", supplier_name="测试电镀商")])
    db.flush()
    line = OrderItem(order_id="OR-review", jewelry_id="SP-review", quantity=60, unit_price=1)
    part_line = OrderItem(order_id="OR-review", part_id="PJ-review", quantity=100, unit_price=1)
    batch = OrderTodoBatch(order_id="OR-review")
    db.add_all([line, part_line, batch, Bom(id="BM-review", jewelry_id="SP-review", part_id="PJ-review", qty_per_unit=2)])
    db.flush()
    reference = OrderTodoBatchJewelry(batch_id=batch.id, jewelry_id="SP-review", quantity=50)
    todo = OrderTodoItem(order_id="OR-review", part_id="PJ-review", required_qty=100, batch_id=batch.id)
    material = HandcraftPartItem(handcraft_order_id="HC-history", part_id="PJ-review", qty=20,
                                received_qty=20, consumed_qty=20, status="已收回", unit="个")
    historical = HandcraftJewelryItem(handcraft_order_id="HC-history", jewelry_id="SP-review", qty=10,
                                     received_qty=10, status="已收回", customer_name="测试客户", unit="卡")
    free = HandcraftJewelryItem(handcraft_order_id="HC-free", jewelry_id="SP-review", qty=60, unit="卡")
    part_output = HandcraftJewelryItem(handcraft_order_id="HC-free", part_id="PJ-review", qty=150, unit="个")
    plating = PlatingOrderItem(plating_order_id="EP-review", part_id="PJ-review", qty=200, unit="个")
    db.add_all([reference, todo, material, historical, free, part_output, plating]); db.flush()
    input_link = OrderItemLink(order_todo_item_id=todo.id, handcraft_part_item_id=material.id)
    db.add(input_link); db.flush()
    return locals()


def test_estimate_get_explains_quantity_difference_without_writes(client, db, old_estimate):
    f = old_estimate
    before = (db.query(OrderItemLink).count(), db.query(OrderTodoBatchJewelry).count(), db.query(HandcraftJewelryItem).count())
    for _ in range(2):
        response = client.get("/api/orders/OR-review/production")
        assert response.status_code == 200, response.text
        data = response.json()
        line = next(row for row in data["lines"] if row["id"] == f["line"].id)
        assert line["quantity"] == 60 and not line["legacy_claim"] and float(line["allocated"]) == 0
        assert line["legacy_batches"] == [{"batch_id": f["batch"].id, "quantity": 50,
                                          "production_order_id": None, "source_item_id": None, "blocks_allocation": False}]
        assert not any(row["legacy_claim"] for row in data["materials"])
    assert before == (db.query(OrderItemLink).count(), db.query(OrderTodoBatchJewelry).count(), db.query(HandcraftJewelryItem).count())
    assert db.query(InventoryLog).count() == db.query(ProductionAllocation).count() == 0
    assert f["material"].consumed_qty == 20 and f["historical"].received_qty == 10


def test_new_creation_after_estimate_preserves_all_history(client, db, old_estimate):
    f = old_estimate
    response = client.post("/api/orders/OR-review/production/handcraft", json={
        "order_item_id": f["line"].id, "supplier_name": "新商家", "request_key": str(uuid4()), "allocated_quantity": 5,
        "parts": [{"part_id": "PJ-review", "qty": 10, "unit": "个"}],
        "jewelries": [{"jewelry_id": "SP-review", "qty": 5, "unit": "卡"}],
    })
    assert response.status_code == 201, response.text
    assert db.query(ProductionAllocation).one().quantity == 5
    assert db.get(OrderItemLink, f["input_link"].id) is not None
    assert f["reference"].quantity == 50 and f["reference"].handcraft_jewelry_item_id is None
    assert f["batch"].handcraft_order_id is None
    assert f["historical"].customer_name == "测试客户" and f["historical"].received_qty == 10
    assert f["material"].consumed_qty == 20 and db.query(InventoryLog).count() == 0


@pytest.mark.parametrize("purpose", ["product", "material"])
def test_input_link_does_not_block_existing_output_allocation(db, old_estimate, purpose):
    f = old_estimate
    source = next(s for s in production_uses(db, "handcraft", "HC-free") if s["source_item_id"] == f["part_output"].id)
    row = {"order_item_id": f["part_line"].id, "quantity": 7}
    if purpose == "material":
        demand = order_production(db, "OR-review")["materials"][0]
        row.update(order_item_id=f["line"].id, material_part_id="PJ-review", demand_revision=demand["demand_revision"])
    result = replace_order_source(db, "OR-review", "handcraft", source["source_item_id"], source["revision"], [row])
    assert result["allocated"] == 7 and f["part_output"].received_qty == 0
    assert db.get(OrderItemLink, f["input_link"].id) is not None and db.query(InventoryLog).count() == 0


@pytest.mark.parametrize("binding", ["batch", "output", "both"])
@pytest.mark.parametrize("completed", [False, True])
def test_bound_batch_keeps_demand_protected(db, old_estimate, binding, completed):
    f = old_estimate
    if binding in {"batch", "both"}: f["batch"].handcraft_order_id = "HC-history" if completed else "HC-free"
    if binding in {"output", "both"}: f["reference"].handcraft_jewelry_item_id = f["historical" if completed else "free"].id
    db.flush()
    assert legacy_demand_claim(db, f["line"])
    result = order_production(db, "OR-review")
    assert next(row for row in result["lines"] if row["id"] == f["line"].id)["legacy_batches"][0]["blocks_allocation"]
    source = next(s for s in production_uses(db, "handcraft", "HC-free") if s["source_item_id"] == f["free"].id)
    with pytest.raises(ValueError, match="旧"):
        replace_order_source(db, "OR-review", "handcraft", source["source_item_id"], source["revision"],
                             [{"order_item_id": f["line"].id, "quantity": 5}])
    assert db.query(ProductionAllocation).count() == 0


@pytest.mark.parametrize("source_type", ["plating", "handcraft"])
def test_real_todo_output_link_still_protects_direct_and_bom_demand(db, old_estimate, source_type):
    f = old_estimate
    field, item = ("plating_order_item_id", f["plating"]) if source_type == "plating" else ("handcraft_jewelry_item_id", f["part_output"])
    db.add(OrderItemLink(order_todo_item_id=f["todo"].id, **{field: item.id})); db.flush()
    assert legacy_demand_claim(db, f["part_line"])
    assert order_production(db, "OR-review")["materials"][0]["legacy_claim"]


def test_direct_old_product_link_and_manual_source_are_not_silently_released(db, old_estimate):
    f = old_estimate
    source = next(s for s in production_uses(db, "handcraft", "HC-history") if s["source_item_id"] == f["historical"].id)
    assert source["legacy_claim"] and source["public_unallocated"] is None
    db.add(OrderItemLink(order_id="OR-review", handcraft_jewelry_item_id=f["historical"].id)); db.flush()
    assert legacy_demand_claim(db, f["line"])


def test_purchase_link_remains_history_not_a_production_output_claim(db, old_estimate):
    f = old_estimate
    db.add(PurchaseOrder(id="PO-review", vendor_name="测试采购商")); db.flush()
    purchase = PurchaseOrderItem(purchase_order_id="PO-review", part_id="PJ-review", qty=100)
    db.add(purchase); db.flush()
    link = OrderItemLink(order_todo_item_id=f["todo"].id, purchase_order_item_id=purchase.id)
    db.add(link); db.flush()
    assert not legacy_demand_claim(db, f["part_line"])
    assert not order_production(db, "OR-review")["materials"][0]["legacy_claim"]
    assert db.get(OrderItemLink, link.id) is not None and db.query(InventoryLog).count() == 0
    with pytest.raises(ValueError, match="不能删除"):
        delete_order_item(db, "OR-review", f["part_line"].id)


@pytest.mark.parametrize("line_key", ["line", "part_line"])
def test_reference_batch_and_input_link_still_protect_line_deletion(db, old_estimate, line_key):
    f = old_estimate
    assert not legacy_demand_claim(db, f[line_key])
    with pytest.raises(ValueError, match="不能删除"):
        delete_order_item(db, "OR-review", f[line_key].id)
    assert db.get(OrderItem, f[line_key].id) is not None
    assert db.get(OrderTodoBatchJewelry, f["reference"].id) is not None
    assert db.get(OrderItemLink, f["input_link"].id) is not None


def test_direct_old_part_output_claim_remains_protected(db, old_estimate):
    f = old_estimate
    db.add(OrderItemLink(order_id="OR-review", handcraft_jewelry_item_id=f["part_output"].id)); db.flush()
    assert legacy_demand_claim(db, f["part_line"])


def test_other_order_bound_batch_does_not_claim_this_order(db, old_estimate):
    f = old_estimate
    f["batch"].order_id = "OR-other"; f["batch"].handcraft_order_id = "HC-history"; db.flush()
    line = next(row for row in order_production(db, "OR-review")["lines"] if row["id"] == f["line"].id)
    assert not line["legacy_claim"] and line["legacy_batches"] == []


def test_duplicate_product_lines_share_history_but_not_inferred_quantities(db, old_estimate):
    f = old_estimate
    repeated = OrderItem(order_id="OR-review", jewelry_id="SP-review", quantity=15, unit_price=1)
    db.add(repeated); db.flush()
    source = next(s for s in production_uses(db, "handcraft", "HC-free") if s["source_item_id"] == f["free"].id)
    replace_order_source(db, "OR-review", "handcraft", source["source_item_id"], source["revision"],
                         [{"order_item_id": repeated.id, "quantity": 5}])
    lines = [row for row in order_production(db, "OR-review")["lines"] if row["product_id"] == "SP-review"]
    assert [row["allocated"] for row in lines] == [0, 5]
    assert all(not row["legacy_claim"] and row["legacy_batches"][0]["quantity"] == 50 for row in lines)
