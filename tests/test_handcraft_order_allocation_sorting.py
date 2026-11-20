"""Order production shares and HC customer sorting must read the same quantities."""
from decimal import Decimal

import pytest

from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
from models.inventory_log import InventoryLog
from models.jewelry import Jewelry
from models.order import Order, OrderItem, OrderItemLink
from models.production_allocation import ProductionAllocation
from services.handcraft import (
    get_handcraft_jewelry_breakdown,
    list_suppliers_with_sorting,
    list_handcraft_orders_with_sorting,
    update_handcraft_jewelry,
)
from services.production_allocation import order_production, production_uses, replace_order_source


@pytest.fixture
def shared(db):
    db.add_all([
        Jewelry(id="SP-SHARED", name="饰品 1", unit="个"),
        Order(id="OR-A", customer_name="客户 a"),
        Order(id="OR-B", customer_name="客户 b"),
        HandcraftOrder(id="HC-A", supplier_name="共享手工商", status="processing"),
    ])
    db.flush()
    a = OrderItem(order_id="OR-A", jewelry_id="SP-SHARED", quantity=30, unit_price=1)
    b = OrderItem(order_id="OR-B", jewelry_id="SP-SHARED", quantity=20, unit_price=1)
    output = HandcraftJewelryItem(handcraft_order_id="HC-A", jewelry_id="SP-SHARED", qty=40,
                                 unit="个", status="制作中", received_qty=12)
    db.add_all([a, b, output])
    db.flush()
    return a, b, output


def assign(db, line, output, quantity):
    source = next(row for row in production_uses(db, "handcraft", "HC-A") if row["source_item_id"] == output.id)
    return replace_order_source(db, line.order_id, "handcraft", output.id, source["revision"],
                                [{"order_item_id": line.id, "quantity": quantity}])


def test_40_output_30_order_share_is_locked_in_sorting_without_duplicate_production(client, db, shared):
    a, _, output = shared
    source = production_uses(db, "handcraft", "HC-A")[0]
    response = client.put("/api/orders/OR-A/production", json={
        "source_type": "handcraft", "source_item_id": output.id, "revision": source["revision"],
        "allocations": [{"order_item_id": a.id, "quantity": 30}],
    })
    assert response.status_code == 200, response.text
    group = client.get("/api/handcraft/HC-A/jewelry-breakdown").json()[0]
    assert group["total_qty"] == 40
    assert group["received_qty"] == 12
    assert group["quantity_managed"]
    customer, remainder = group["entries"]
    assert customer["customer_name"] == "客户 a"
    assert customer["qty"] == 30
    assert customer["source_order_id"] == "OR-A"
    assert customer["source_order_item_id"] == a.id
    assert customer["source_allocation_id"]
    assert customer["is_locked"]
    assert customer["received_qty"] is None  # No invented customer receipts.
    assert remainder["customer_name"] is None
    assert remainder["qty"] == 10
    assert remainder["is_quantity_remainder"]
    assert sum(e["qty"] for e in group["entries"]) == 40
    assert output.qty == 40 and output.received_qty == 12
    assert db.query(HandcraftJewelryItem).count() == 1
    assert db.query(InventoryLog).count() == 0
    assert db.query(OrderItemLink).count() == 0


def test_other_customer_can_only_take_remaining_10_and_adjustments_are_live(db, shared):
    a, b, output = shared
    assign(db, a, output, 30)
    with pytest.raises(ValueError, match="容量"):
        assign(db, b, output, 11)
    assign(db, b, output, 10)
    group = get_handcraft_jewelry_breakdown(db, "HC-A")[0]
    assert [(e["customer_name"], e["qty"]) for e in group["entries"]] == [("客户 a", 30), ("客户 b", 10)]
    assign(db, a, output, 20)
    group = get_handcraft_jewelry_breakdown(db, "HC-A")[0]
    assert sum(e["qty"] for e in group["entries"]) == 40
    assert next(e for e in group["entries"] if e.get("is_quantity_remainder"))["qty"] == 10
    assign(db, a, output, 0)
    group = get_handcraft_jewelry_breakdown(db, "HC-A")[0]
    assert not any(e["customer_name"] == "客户 a" for e in group["entries"])
    assert next(e for e in group["entries"] if e.get("is_quantity_remainder"))["qty"] == 30
    assign(db, b, output, 0)
    group = get_handcraft_jewelry_breakdown(db, "HC-A")[0]
    assert not group["quantity_managed"]
    assert group["entries"][0]["qty"] == 40
    assert not group["entries"][0].get("is_quantity_remainder")


def test_quantity_allocations_qualify_for_supplier_and_sorting_lists(db, shared):
    a, _, output = shared
    assert list_suppliers_with_sorting(db) == []
    assign(db, a, output, 30)
    assert list_suppliers_with_sorting(db) == ["共享手工商"]
    result = list_handcraft_orders_with_sorting(db, "共享手工商")
    assert len(result["orders"]) == 1
    assert result["orders"][0]["breakdown"][0]["entries"][0]["qty"] == 30
    assert len(result["orders"][0]["breakdown"][0]["entries"]) == 1  # No anonymous remainder.
    assign(db, a, output, 0)
    assert list_suppliers_with_sorting(db) == []


def test_repeated_product_lines_and_same_customer_orders_keep_exact_identity(db, shared):
    a, b, output = shared
    db.get(Order, "OR-B").customer_name = "客户 a"
    extra = OrderItem(order_id="OR-A", jewelry_id="SP-SHARED", quantity=5, unit_price=1)
    db.add(extra)
    db.flush()
    assign(db, a, output, 25)
    source = production_uses(db, "handcraft", "HC-A")[0]
    replace_order_source(db, "OR-A", "handcraft", output.id, source["revision"], [
        {"order_item_id": a.id, "quantity": 25}, {"order_item_id": extra.id, "quantity": 5}])
    assign(db, b, output, 10)
    entries = get_handcraft_jewelry_breakdown(db, "HC-A")[0]["entries"]
    assert {e["source_order_item_id"] for e in entries} == {a.id, extra.id, b.id}
    assert len(entries) == 3 and sum(e["qty"] for e in entries) == 40
    assert {e["source_order_id"] for e in entries} == {"OR-A", "OR-B"}


def test_manual_rows_still_editable_but_cannot_overwrite_allocated_physical_output(db, shared):
    a, _, output = shared
    assign(db, a, output, 30)
    with pytest.raises(ValueError, match="按订单数量"):
        update_handcraft_jewelry(db, "HC-A", output.id, {"customer_name": "手填覆盖"})
    manual = HandcraftJewelryItem(handcraft_order_id="HC-A", jewelry_id="SP-SHARED", qty=5,
                                 unit="个", customer_name="手填客户")
    db.add(manual)
    db.flush()
    group = get_handcraft_jewelry_breakdown(db, "HC-A")[0]
    assert group["total_qty"] == 45
    assert sum(e["qty"] for e in group["entries"]) == 45
    assert next(e for e in group["entries"] if e["customer_name"] == "手填客户")["source"] == "manual"


def test_old_exact_links_remain_associated_even_in_completed_history(db, shared):
    _, _, output = shared
    db.add(OrderItemLink(order_id="OR-A", handcraft_jewelry_item_id=output.id))
    db.get(HandcraftOrder, "HC-A").status = "completed"
    db.flush()
    sources = order_production(db, "OR-A")["sources"]
    assert len(sources) == 1
    assert sources[0]["linked_order_ids"] == ["OR-A"]
    assert sources[0]["legacy_claim"]
    assert sources[0]["allocated"] == Decimal(0)


def test_old_customer_attribution_does_not_associate_matching_customer_name(db, shared):
    _, _, output = shared
    output.customer_name = "客户 a"
    db.flush()
    source = order_production(db, "OR-A")["sources"][0]
    assert source["linked_order_ids"] == []
    assert source["allocations"] == []
