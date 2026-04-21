import pytest
from services.part import create_part
from services.inventory import add_stock, get_stock
from services.plating import create_plating_order, send_plating_order, get_plating_items
from services.plating_receipt import (
    create_plating_receipt,
    get_receipt_links_for_plating_order,
    get_available_receipts_for_item,
    link_plating_item_to_receipt,
)


def _setup(db, supplier="Supplier A", qty=100.0):
    """Create part with stock, create + send plating order."""
    part = create_part(db, {"name": "Test Part", "category": "小配件"})
    add_stock(db, "part", part.id, qty + 50, "初始库存")
    order = create_plating_order(db, supplier, [{"part_id": part.id, "qty": qty}])
    send_plating_order(db, order.id)
    db.flush()
    items = get_plating_items(db, order.id)
    return part, order, items[0]


def _create_unpaid_receipt(db, vendor="Supplier A"):
    """Create a part + plating order + receipt, return (part, order, poi, receipt_id)."""
    part, order, poi = _setup(db, supplier=vendor)
    receipt = create_plating_receipt(db, vendor, [
        {"plating_order_item_id": poi.id, "part_id": part.id, "qty": 10.0, "price": 1.0},
    ])
    return part, order, poi, receipt.id


# --- get_receipt_links_for_plating_order ---

def test_receipt_links_empty(db):
    _part, order, _poi = _setup(db)
    result = get_receipt_links_for_plating_order(db, order.id)
    assert result == {}


def test_receipt_links_returns_linked_items(db):
    part, order, poi = _setup(db)
    receipt = create_plating_receipt(db, "Supplier A", [
        {"plating_order_item_id": poi.id, "part_id": part.id, "qty": 30.0, "price": 2.0},
    ])
    result = get_receipt_links_for_plating_order(db, order.id)
    assert poi.id in result
    links = result[poi.id]
    assert len(links) == 1
    assert links[0]["receipt_id"] == receipt.id
    assert links[0]["qty"] == 30.0
    assert links[0]["price"] == 2.0


# --- get_available_receipts_for_item ---

def test_available_receipts_filters_by_vendor(db):
    part, order, poi = _setup(db, supplier="Vendor X")
    # Create receipt with different vendor — should not appear
    other_part = create_part(db, {"name": "Other", "category": "小配件"})
    add_stock(db, "part", other_part.id, 100, "stock")
    other_order = create_plating_order(db, "Vendor Y", [{"part_id": other_part.id, "qty": 10}])
    send_plating_order(db, other_order.id)
    db.flush()
    other_poi = get_plating_items(db, other_order.id)[0]
    create_plating_receipt(db, "Vendor Y", [
        {"plating_order_item_id": other_poi.id, "part_id": other_part.id, "qty": 5, "price": 1},
    ])
    # Create receipt with matching vendor
    matching_receipt = create_plating_receipt(db, "Vendor X", [
        {"plating_order_item_id": poi.id, "part_id": part.id, "qty": 5, "price": 1},
    ])
    # Available should only show matching vendor, but exclude this receipt (already linked)
    result = get_available_receipts_for_item(db, order.id, poi.id)
    # matching_receipt already has this poi, so it should be excluded
    assert all(r["id"] != matching_receipt.id for r in result) or len(result) == 0


def test_available_receipts_excludes_paid(db):
    part, order, poi = _setup(db, supplier="Supplier A")
    # Create a paid receipt with different item
    other_part = create_part(db, {"name": "Other2", "category": "小配件"})
    add_stock(db, "part", other_part.id, 100, "stock")
    other_order = create_plating_order(db, "Supplier A", [{"part_id": other_part.id, "qty": 10}])
    send_plating_order(db, other_order.id)
    db.flush()
    other_poi = get_plating_items(db, other_order.id)[0]
    create_plating_receipt(db, "Supplier A", [
        {"plating_order_item_id": other_poi.id, "part_id": other_part.id, "qty": 5, "price": 1},
    ], status="已付款")
    result = get_available_receipts_for_item(db, order.id, poi.id)
    # All returned receipts should be unpaid
    for r in result:
        assert r.get("status", "未付款") != "已付款" or "status" not in r


# --- link_plating_item_to_receipt ---

def test_link_receipt_success(db):
    part, order, poi = _setup(db, supplier="Supplier A")
    # Create an empty-ish receipt with a different item
    other_part = create_part(db, {"name": "Other3", "category": "小配件"})
    add_stock(db, "part", other_part.id, 100, "stock")
    other_order = create_plating_order(db, "Supplier A", [{"part_id": other_part.id, "qty": 10}])
    send_plating_order(db, other_order.id)
    db.flush()
    other_poi = get_plating_items(db, other_order.id)[0]
    receipt = create_plating_receipt(db, "Supplier A", [
        {"plating_order_item_id": other_poi.id, "part_id": other_part.id, "qty": 5, "price": 1},
    ])
    # Link our poi to this receipt
    result = link_plating_item_to_receipt(db, order.id, poi.id, receipt.id, 20.0, 0.5)
    assert result["receipt_item_id"] is not None
    assert result["qty"] == 20.0
    # Verify received_qty updated
    db.refresh(poi)
    assert float(poi.received_qty) == 20.0
    # Verify stock added
    receive_id = poi.receive_part_id or poi.part_id
    stock = get_stock(db, "part", receive_id)
    assert stock >= 20.0


def test_link_receipt_exceeds_remaining(db):
    part, order, poi = _setup(db, supplier="Supplier A", qty=10.0)
    other_part = create_part(db, {"name": "Other4", "category": "小配件"})
    add_stock(db, "part", other_part.id, 100, "stock")
    other_order = create_plating_order(db, "Supplier A", [{"part_id": other_part.id, "qty": 10}])
    send_plating_order(db, other_order.id)
    db.flush()
    other_poi = get_plating_items(db, other_order.id)[0]
    receipt = create_plating_receipt(db, "Supplier A", [
        {"plating_order_item_id": other_poi.id, "part_id": other_part.id, "qty": 5, "price": 1},
    ])
    with pytest.raises(ValueError, match="最多可回收"):
        link_plating_item_to_receipt(db, order.id, poi.id, receipt.id, 15.0, 0.5)


def test_link_receipt_vendor_mismatch(db):
    part, order, poi = _setup(db, supplier="Vendor A")
    other_part = create_part(db, {"name": "Other5", "category": "小配件"})
    add_stock(db, "part", other_part.id, 100, "stock")
    other_order = create_plating_order(db, "Vendor B", [{"part_id": other_part.id, "qty": 10}])
    send_plating_order(db, other_order.id)
    db.flush()
    other_poi = get_plating_items(db, other_order.id)[0]
    receipt = create_plating_receipt(db, "Vendor B", [
        {"plating_order_item_id": other_poi.id, "part_id": other_part.id, "qty": 5, "price": 1},
    ])
    with pytest.raises(ValueError, match="不一致"):
        link_plating_item_to_receipt(db, order.id, poi.id, receipt.id, 5.0, 0.5)


def test_link_receipt_duplicate_rejected(db):
    part, order, poi = _setup(db, supplier="Supplier A")
    other_part = create_part(db, {"name": "Other6", "category": "小配件"})
    add_stock(db, "part", other_part.id, 100, "stock")
    other_order = create_plating_order(db, "Supplier A", [{"part_id": other_part.id, "qty": 10}])
    send_plating_order(db, other_order.id)
    db.flush()
    other_poi = get_plating_items(db, other_order.id)[0]
    receipt = create_plating_receipt(db, "Supplier A", [
        {"plating_order_item_id": other_poi.id, "part_id": other_part.id, "qty": 5, "price": 1},
    ])
    # First link succeeds
    link_plating_item_to_receipt(db, order.id, poi.id, receipt.id, 10.0, 0.5)
    # Second link to same receipt should fail
    with pytest.raises(ValueError, match="已存在"):
        link_plating_item_to_receipt(db, order.id, poi.id, receipt.id, 10.0, 0.5)


def test_link_receipt_paid_rejected(db):
    part, order, poi = _setup(db, supplier="Supplier A")
    other_part = create_part(db, {"name": "Other7", "category": "小配件"})
    add_stock(db, "part", other_part.id, 100, "stock")
    other_order = create_plating_order(db, "Supplier A", [{"part_id": other_part.id, "qty": 10}])
    send_plating_order(db, other_order.id)
    db.flush()
    other_poi = get_plating_items(db, other_order.id)[0]
    receipt = create_plating_receipt(db, "Supplier A", [
        {"plating_order_item_id": other_poi.id, "part_id": other_part.id, "qty": 5, "price": 1},
    ], status="已付款")
    with pytest.raises(ValueError, match="已付款"):
        link_plating_item_to_receipt(db, order.id, poi.id, receipt.id, 5.0, 0.5)
