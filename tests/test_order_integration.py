"""Unified order editing must never synthesize fulfillment or rewrite history."""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from models import Order, OrderItem, Part, Jewelry, InventoryLog
from models.order_fulfillment import OrderFulfillment
from models.order import OrderPickingRecord
from services import order as orders, order_fulfillment as fulfillment, picking
from services.inventory import add_stock, get_stock
from services.order_todo import _build_batch_response


@pytest.fixture
def integrated(db):
    db.add_all([Part(id="p", name="配件", category="小配件", unit="个"),
                Jewelry(id="j", name="饰品", category="单件", unit="条")])
    db.flush()
    order = orders.create_order(db, "客户", [
        {"jewelry_id": "j", "quantity": 10, "unit_price": 0.1234567, "customer_code": "A01"},
        {"jewelry_id": "j", "quantity": 20, "unit_price": 2, "customer_code": "A02"},
        {"part_id": "p", "quantity": 10, "unit_price": 1},
    ])
    return order, orders.get_order_items(db, order.id)


def test_new_orders_are_managed_without_activation_and_history_is_not(db, integrated):
    order, lines = integrated
    db.add(Order(id="HISTORICAL", customer_name="旧客户")); db.flush()
    before = db.query(InventoryLog).count()
    assert fulfillment.order_summary(db, order.id)["managed"] is True
    assert fulfillment.order_summary(db, "HISTORICAL")["managed"] is False
    assert db.get(OrderFulfillment, "HISTORICAL") is None
    assert db.query(InventoryLog).count() == before
    summary = fulfillment.order_summary(db, order.id)["lines"]
    assert [row["id"] for row in summary] == [line.id for line in lines]
    assert [row["customer_code"] for row in summary[:2]] == ["A01", "A02"]
    assert Decimal(str(summary[0]["unit_price"])) == Decimal("0.1234567")


def test_unified_edit_retains_exact_line_and_seven_decimal_price(db, integrated):
    order, lines = integrated
    orders.update_order_item(db, order.id, lines[0].id,
                             {"unit_price": 0.7654321, "remarks": "独立行备注", "customer_code": "NEW"})
    orders.update_extra_info(db, order.id, {"note": "要求", "barcode_image": "/uploads/example.png",
                                           "created_at": date(2026, 11, 19)})
    orders.update_packaging_cost(db, order.id, 3.25)
    db.expire_all()
    assert lines[0].jewelry_id == lines[1].jewelry_id == "j"
    assert lines[0].customer_code == "NEW" and lines[1].customer_code == "A02"
    assert lines[0].unit_price == Decimal("0.7654321")
    assert fulfillment.order_summary(db, order.id)["lines"][0]["remarks"] == "独立行备注"
    assert order.total_amount == Decimal("57.6543210")
    assert db.query(InventoryLog).count() == 0


@pytest.mark.parametrize("status", ["已完成", "已取消"])
@pytest.mark.parametrize("operation", ["metadata", "line", "add", "delete", "codes", "packaging", "pick", "unpick", "reset"])
def test_closed_order_history_is_readonly_on_server(db, integrated, status, operation):
    order, lines = integrated
    order.status = status; db.flush()
    actions = {
        "metadata": lambda: orders.update_extra_info(db, order.id, {"note": "改写"}),
        "line": lambda: orders.update_order_item(db, order.id, lines[0].id, {"remarks": "改写"}),
        "add": lambda: orders.add_order_item(db, order.id, {"jewelry_id": "j", "quantity": 1, "unit_price": 1}),
        "delete": lambda: orders.delete_order_item(db, order.id, lines[0].id),
        "codes": lambda: orders.batch_fill_customer_code(db, order.id, [lines[0].id], "X", 1),
        "packaging": lambda: orders.update_packaging_cost(db, order.id, 10),
        "pick": lambda: picking.mark_picked(db, order.id, "p", 10),
        "unpick": lambda: picking.unmark_picked(db, order.id, "p", 10),
        "reset": lambda: picking.reset_picking(db, order.id),
    }
    with pytest.raises(ValueError, match="只读"):
        actions[operation]()
    assert db.query(OrderPickingRecord).count() == 0
    assert db.query(InventoryLog).count() == 0


def test_draft_shipments_block_quantity_reduction_and_hard_deletion(db, integrated):
    order, lines = integrated
    fulfillment.create_shipment(db, {"order_id": order.id, "lines": [{"order_item_id": lines[0].id, "quantity": 8}], "request_key": str(uuid4())})
    with pytest.raises(ValueError, match="草稿"):
        orders.update_order_item(db, order.id, lines[0].id, {"quantity": 7})
    with pytest.raises(ValueError, match="出货凭据"):
        orders.delete_order_item(db, order.id, lines[0].id)
    assert lines[0].quantity == 10


def test_new_order_cannot_complete_by_status_or_hard_delete(db, integrated):
    order, _ = integrated
    with pytest.raises(ValueError, match="足量出货"):
        orders.update_order_status(db, order.id, "已完成")
    with pytest.raises(ValueError, match="保留记录"):
        orders.delete_order(db, order.id)
    assert db.query(InventoryLog).count() == 0


def test_public_stock_without_bom_or_production_completes_only_after_every_line(db, integrated):
    order, lines = integrated
    add_stock(db, "jewelry", "j", 30, "测试入库")
    add_stock(db, "part", "p", 10, "测试入库")
    shipment = fulfillment.create_shipment(db, {"order_id": order.id, "lines": [{"order_item_id": lines[0].id, "quantity": 10}], "request_key": str(uuid4())})
    fulfillment.confirm_shipment(db, shipment["id"], True)
    assert fulfillment.order_summary(db, order.id)["completed_items"] == 1
    assert order.status != "已完成"
    shipment = fulfillment.create_shipment(db, {"order_id": order.id, "lines": [
        {"order_item_id": lines[1].id, "quantity": 20}, {"order_item_id": lines[2].id, "quantity": 10}], "request_key": str(uuid4())})
    fulfillment.confirm_shipment(db, shipment["id"], True)
    assert order.status == "已完成"
    assert get_stock(db, "jewelry", "j") == 0 and get_stock(db, "part", "p") == 0


def test_history_get_does_not_repair_missing_source(db, integrated):
    from types import SimpleNamespace
    order, _ = integrated
    # Model a pre-constraint orphan without disabling real database FK safety.
    batch = SimpleNamespace(id=99, order_id=order.id, handcraft_order_id="MISSING-HISTORICAL-SOURCE", created_at=None)
    result = _build_batch_response(db, batch, [], [])
    assert result["missing_source"] is True
    assert result["handcraft_order_id"] == "MISSING-HISTORICAL-SOURCE"
    assert not db.dirty
    assert batch.handcraft_order_id == "MISSING-HISTORICAL-SOURCE"


@pytest.mark.parametrize("status", ["待生产", "生产中"])
@pytest.mark.parametrize("kind", ["jewelry", "part"])
def test_editable_orders_add_and_delete_independent_items_without_inventory_changes(db, integrated, status, kind):
    order, lines = integrated
    order.status = status; db.flush()
    original_ids = [line.id for line in lines]
    total = order.total_amount
    fields = {f"{kind}_id": "j" if kind == "jewelry" else "p", "quantity": 3, "unit_price": 0.7654321, "remarks": "追加独立行"}
    if kind == "jewelry":
        fields["customer_code"] = "A03"
    added = orders.add_order_item(db, order.id, fields)
    assert added.id not in original_ids
    assert added.unit_price == Decimal("0.7654321")
    assert order.total_amount == total + Decimal("2.2962963")
    summary = fulfillment.order_summary(db, order.id)
    assert summary["total_items"] == 4
    assert summary["lines"][-1]["id"] == added.id
    assert summary["lines"][-1]["shipped"] == 0
    orders.delete_order_item(db, order.id, added.id)
    assert [line.id for line in orders.get_order_items(db, order.id)] == original_ids
    assert lines[0].customer_code == "A01" and lines[1].customer_code == "A02"
    assert order.total_amount == total
    assert order.status == status
    assert db.query(InventoryLog).count() == 0


def test_auto_started_order_can_add_and_delete_unallocated_sibling_but_not_allocated_item(db, integrated):
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    from models.production_allocation import ProductionAllocation
    from services.production_allocation import production_uses, replace_order_source
    order, lines = integrated
    db.add(HandcraftOrder(id="HC-edit", supplier_name="手工商")); db.flush()
    output = HandcraftJewelryItem(handcraft_order_id="HC-edit", jewelry_id="j", qty=5, unit="条")
    db.add(output); db.flush()
    source = production_uses(db, "handcraft", "HC-edit")[0]
    replace_order_source(db, order.id, "handcraft", output.id, source["revision"], [{"order_item_id": lines[0].id, "quantity": 5}])
    assert order.status == "生产中"
    added = orders.add_order_item(db, order.id, {"jewelry_id": "j", "quantity": 2, "unit_price": 1, "customer_code": "NEW"})
    orders.delete_order_item(db, order.id, added.id)
    orders.delete_order_item(db, order.id, lines[1].id)
    with pytest.raises(ValueError, match="生产数量安排"):
        orders.delete_order_item(db, order.id, lines[0].id)
    allocation = db.query(ProductionAllocation).one()
    assert allocation.order_item_id == lines[0].id and allocation.quantity == 5
    assert output.qty == 5
    assert [line.id for line in orders.get_order_items(db, order.id)] == [lines[0].id, lines[2].id]
    assert db.query(InventoryLog).count() == 0


@pytest.mark.parametrize("protection", ["reservation", "draft", "confirmed", "legacy"])
def test_processing_order_still_protects_referenced_items(db, integrated, protection):
    order, lines = integrated
    order.status = "生产中"; db.flush()
    if protection == "reservation":
        add_stock(db, "jewelry", "j", 5, "测试入库")
        fulfillment.reserve(db, order.id, lines[0].id, 5, 0)
    elif protection in {"draft", "confirmed"}:
        shipment = fulfillment.create_shipment(db, {"order_id": order.id, "lines": [{"order_item_id": lines[0].id, "quantity": 5}], "request_key": str(uuid4())})
        if protection == "confirmed":
            add_stock(db, "jewelry", "j", 5, "测试入库")
            fulfillment.confirm_shipment(db, shipment["id"], True)
    else:
        from models.order import OrderTodoBatch, OrderTodoBatchJewelry
        batch = OrderTodoBatch(order_id=order.id)
        db.add(batch); db.flush()
        db.add(OrderTodoBatchJewelry(batch_id=batch.id, jewelry_id="j", quantity=1)); db.flush()
    before = db.query(InventoryLog).count()
    with pytest.raises(ValueError, match="不能删除"):
        orders.delete_order_item(db, order.id, lines[0].id)
    assert len(orders.get_order_items(db, order.id)) == 3
    assert db.query(InventoryLog).count() == before
