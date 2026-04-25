import pytest
from decimal import Decimal
from models.order import Order, OrderItem
from models.part import Part
from services.order import create_order, add_order_item, update_order_item


@pytest.fixture
def part_chain(db):
    p = Part(id="PJ-LT-T01", name="链 1.5mm", category="链条",
             unit="米", wholesale_price=Decimal("15"), unit_cost=Decimal("8"))
    db.add(p)
    db.flush()
    return p


def test_create_order_with_part_only(db, part_chain):
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id,
        "quantity": 5,
        "unit_price": 15,
        "remarks": None,
    }])
    items = db.query(OrderItem).filter_by(order_id=order.id).all()
    assert len(items) == 1
    assert items[0].part_id == part_chain.id
    assert items[0].jewelry_id is None
    assert order.total_amount == Decimal("75.0000000")


def test_create_order_writes_back_wholesale_price(db, part_chain):
    create_order(db, "客户A", [{
        "part_id": part_chain.id,
        "quantity": 1,
        "unit_price": 22,
        "remarks": None,
    }])
    db.refresh(part_chain)
    assert part_chain.wholesale_price == Decimal("22")


def test_create_order_does_not_write_back_when_price_matches(db, part_chain):
    create_order(db, "客户A", [{
        "part_id": part_chain.id,
        "quantity": 1,
        "unit_price": 15,  # same as default
        "remarks": None,
    }])
    db.refresh(part_chain)
    assert part_chain.wholesale_price == Decimal("15")


def test_add_part_item_to_existing_order(db, part_chain):
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id,
        "quantity": 1,
        "unit_price": 15,
        "remarks": None,
    }])
    add_order_item(db, order.id, {
        "part_id": part_chain.id,
        "quantity": 2,
        "unit_price": 16,
    })
    items = db.query(OrderItem).filter_by(order_id=order.id).all()
    assert len(items) == 2
    db.refresh(part_chain)
    assert part_chain.wholesale_price == Decimal("16")


def test_update_part_item_unit_price_writes_back(db, part_chain):
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id,
        "quantity": 1,
        "unit_price": 15,
        "remarks": None,
    }])
    item = db.query(OrderItem).filter_by(order_id=order.id).first()
    update_order_item(db, order.id, item.id, {"unit_price": 19.5})
    db.refresh(part_chain)
    assert part_chain.wholesale_price == Decimal("19.5")
