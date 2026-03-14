import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from models.handcraft_order import HandcraftOrder
from models.plating_order import PlatingOrder
from models.vendor_receipt import VendorReceipt
from schemas.kanban import ReceiptItemIn
from services.handcraft import create_handcraft_order, send_handcraft_order
from services.inventory import add_stock
from services.jewelry import create_jewelry
from services.kanban import get_vendor_detail, record_vendor_receipt
from services.part import create_part
from services.plating import create_plating_order, send_plating_order


# ──────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────

@pytest.fixture
def part(db):
    p = create_part(db, {"name": "铜扣"})
    add_stock(db, "part", p.id, 200.0, "入库")
    return p


@pytest.fixture
def jewelry(db):
    return create_jewelry(db, {"name": "铜项链", "category": "项链"})


@pytest.fixture
def plating_vendor(db, part):
    """Plating order for 电镀厂A with 10 units of part dispatched."""
    order = create_plating_order(db, "电镀厂A", [
        {"part_id": part.id, "qty": 10, "plating_method": "金色"},
    ])
    send_plating_order(db, order.id)
    return order, part


@pytest.fixture
def handcraft_vendor(db, part, jewelry):
    """Handcraft order for 手工厂A: 50 parts dispatched, 10 jewelry expected."""
    order = create_handcraft_order(db, "手工厂A",
        parts=[{"part_id": part.id, "qty": 50, "bom_qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 10}],
    )
    send_handcraft_order(db, order.id)
    return order, part, jewelry


# ──────────────────────────────────────────────────────────────
# 422 input validation
# ──────────────────────────────────────────────────────────────

def _valid_body(**overrides):
    base = {
        "vendor_name": "厂A",
        "order_type": "plating",
        "items": [{"item_id": "PJ-0001", "item_type": "part", "qty": 1}],
    }
    base.update(overrides)
    return base


def test_422_vendor_name_empty(client):
    r = client.post("/api/kanban/return", json=_valid_body(vendor_name=""))
    assert r.status_code == 422


def test_422_vendor_name_blank(client):
    r = client.post("/api/kanban/return", json=_valid_body(vendor_name="   "))
    assert r.status_code == 422


def test_422_item_id_empty(client):
    r = client.post("/api/kanban/return", json=_valid_body(
        items=[{"item_id": "", "item_type": "part", "qty": 1}]
    ))
    assert r.status_code == 422


def test_422_item_id_blank(client):
    r = client.post("/api/kanban/return", json=_valid_body(
        items=[{"item_id": "   ", "item_type": "part", "qty": 1}]
    ))
    assert r.status_code == 422


def test_422_qty_zero(client):
    r = client.post("/api/kanban/return", json=_valid_body(
        items=[{"item_id": "PJ-0001", "item_type": "part", "qty": 0}]
    ))
    assert r.status_code == 422


def test_422_qty_negative(client):
    r = client.post("/api/kanban/return", json=_valid_body(
        items=[{"item_id": "PJ-0001", "item_type": "part", "qty": -1}]
    ))
    assert r.status_code == 422


def test_422_items_empty(client):
    r = client.post("/api/kanban/return", json=_valid_body(items=[]))
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────
# Duplicate item warning (pending_in_request accumulator)
# ──────────────────────────────────────────────────────────────

def test_duplicate_item_second_row_warns(db, plating_vendor):
    """Two rows for the same part in one request; combined qty exceeds cap.

    cap=10, row1=6 (ok, no warn), row2=6 (total 12 > 10, warns).
    Both VendorReceipt rows must still be written.
    """
    order, part = plating_vendor
    items = [
        ReceiptItemIn(item_id=part.id, item_type="part", qty=6),
        ReceiptItemIn(item_id=part.id, item_type="part", qty=6),
    ]
    _, warnings = record_vendor_receipt(db, "电镀厂A", "plating", order.id, items)

    assert len(warnings) == 1
    assert part.id in warnings[0]

    receipts = db.query(VendorReceipt).filter(VendorReceipt.vendor_name == "电镀厂A").all()
    assert len(receipts) == 2
    assert sum(r.qty for r in receipts) == 12.0


def test_duplicate_item_no_warn_within_cap(db, plating_vendor):
    """Two rows for the same part, combined qty still within cap — no warnings."""
    order, part = plating_vendor
    items = [
        ReceiptItemIn(item_id=part.id, item_type="part", qty=4),
        ReceiptItemIn(item_id=part.id, item_type="part", qty=4),
    ]
    _, warnings = record_vendor_receipt(db, "电镀厂A", "plating", order.id, items)

    assert warnings == []
    receipts = db.query(VendorReceipt).filter(VendorReceipt.vendor_name == "电镀厂A").all()
    assert len(receipts) == 2


# ──────────────────────────────────────────────────────────────
# Handcraft vendor detail — part + jewelry both present
# ──────────────────────────────────────────────────────────────

def test_handcraft_detail_includes_part_and_jewelry(db, handcraft_vendor):
    """get_vendor_detail for handcraft must include both part and jewelry items."""
    order, part, jewelry = handcraft_vendor
    detail = get_vendor_detail(db, "手工厂A", "handcraft")

    item_types = {item.item_type for item in detail.items}
    assert "part" in item_types
    assert "jewelry" in item_types


def test_handcraft_detail_jewelry_dispatched_qty_correct(db, handcraft_vendor):
    """Jewelry dispatched_qty should equal the HandcraftJewelryItem qty (10)."""
    order, part, jewelry = handcraft_vendor
    detail = get_vendor_detail(db, "手工厂A", "handcraft")

    j_item = next(i for i in detail.items if i.item_type == "jewelry")
    assert j_item.item_id == jewelry.id
    assert j_item.dispatched_qty == 10.0
    assert j_item.received_qty == 0.0


def test_handcraft_detail_jewelry_received_qty_updates(db, handcraft_vendor):
    """After recording a receipt for jewelry, received_qty in detail should update."""
    order, part, jewelry = handcraft_vendor

    record_vendor_receipt(db, "手工厂A", "handcraft", order.id, [
        ReceiptItemIn(item_id=jewelry.id, item_type="jewelry", qty=5),
    ])

    detail = get_vendor_detail(db, "手工厂A", "handcraft")
    j_item = next(i for i in detail.items if i.item_type == "jewelry")
    assert j_item.received_qty == 5.0


# ──────────────────────────────────────────────────────────────
# Auto-complete orders on full receipt
# ──────────────────────────────────────────────────────────────

def test_plating_autocomplete_on_full_receipt(db, plating_vendor):
    """Receiving all dispatched parts triggers PlatingOrder → completed."""
    order, part = plating_vendor

    record_vendor_receipt(db, "电镀厂A", "plating", order.id, [
        ReceiptItemIn(item_id=part.id, item_type="part", qty=10),
    ])

    db.refresh(order)
    assert order.status == "completed"
    assert order.completed_at is not None


def test_plating_no_autocomplete_on_partial_receipt(db, plating_vendor):
    """Partial receipt must NOT auto-complete the order."""
    order, part = plating_vendor

    record_vendor_receipt(db, "电镀厂A", "plating", order.id, [
        ReceiptItemIn(item_id=part.id, item_type="part", qty=9),
    ])

    db.refresh(order)
    assert order.status == "processing"
    assert order.completed_at is None


def test_handcraft_autocomplete_on_full_jewelry_receipt(db, handcraft_vendor):
    """Receiving all expected jewelry triggers HandcraftOrder → completed."""
    order, part, jewelry = handcraft_vendor

    record_vendor_receipt(db, "手工厂A", "handcraft", order.id, [
        ReceiptItemIn(item_id=jewelry.id, item_type="jewelry", qty=10),
    ])

    db.refresh(order)
    assert order.status == "completed"
    assert order.completed_at is not None


def test_handcraft_no_autocomplete_on_partial_jewelry_receipt(db, handcraft_vendor):
    """Partial jewelry receipt must NOT auto-complete the handcraft order."""
    order, part, jewelry = handcraft_vendor

    record_vendor_receipt(db, "手工厂A", "handcraft", order.id, [
        ReceiptItemIn(item_id=jewelry.id, item_type="jewelry", qty=9),
    ])

    db.refresh(order)
    assert order.status == "processing"
    assert order.completed_at is None


def test_handcraft_autocomplete_accumulates_across_calls(db, handcraft_vendor):
    """Two separate record_vendor_receipt calls totalling full qty must complete the order."""
    order, part, jewelry = handcraft_vendor

    record_vendor_receipt(db, "手工厂A", "handcraft", order.id, [
        ReceiptItemIn(item_id=jewelry.id, item_type="jewelry", qty=6),
    ])
    db.refresh(order)
    assert order.status == "processing"  # not yet complete

    record_vendor_receipt(db, "手工厂A", "handcraft", order.id, [
        ReceiptItemIn(item_id=jewelry.id, item_type="jewelry", qty=4),
    ])
    db.refresh(order)
    assert order.status == "completed"
    assert order.completed_at is not None
