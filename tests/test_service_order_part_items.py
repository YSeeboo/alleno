import pytest
from decimal import Decimal
from models.order import Order, OrderItem
from models.part import Part
from services.inventory import add_stock, get_stock
from services.order import create_order, add_order_item, update_order_item, update_order_status
from services.order import update_order_item_customer_code, batch_fill_customer_code
from services.order import get_parts_summary


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


def test_create_order_mixed_jewelry_and_part(db, part_chain):
    from models.jewelry import Jewelry
    db.add(Jewelry(id="SP-MIX1", name="环", status="active",
                   handcraft_cost=0, wholesale_price=100))
    db.flush()
    order = create_order(db, "客户A", [
        {"jewelry_id": "SP-MIX1", "quantity": 2, "unit_price": 100, "remarks": None},
        {"part_id": part_chain.id, "quantity": 3, "unit_price": 15, "remarks": None},
    ])
    items = db.query(OrderItem).filter_by(order_id=order.id).order_by(OrderItem.id).all()
    assert len(items) == 2
    assert items[0].jewelry_id == "SP-MIX1" and items[0].part_id is None
    assert items[1].part_id == part_chain.id and items[1].jewelry_id is None
    # 2*100 + 3*15 = 245
    assert order.total_amount == Decimal("245.0000000")


def test_complete_order_deducts_part_stock(db, part_chain):
    add_stock(db, "part", part_chain.id, 100, "测试入库")
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id, "quantity": 5, "unit_price": 15, "remarks": None,
    }])
    update_order_status(db, order.id, "已完成")
    assert get_stock(db, "part", part_chain.id) == 95


def test_complete_order_rejects_when_part_stock_insufficient(db, part_chain):
    add_stock(db, "part", part_chain.id, 3, "测试入库")
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id, "quantity": 5, "unit_price": 15, "remarks": None,
    }])
    with pytest.raises(ValueError, match="配件库存不足"):
        update_order_status(db, order.id, "已完成")
    db.refresh(order)
    assert order.status == "待生产"
    assert get_stock(db, "part", part_chain.id) == 3  # untouched


def test_uncomplete_restores_part_stock(db, part_chain):
    add_stock(db, "part", part_chain.id, 100, "测试入库")
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id, "quantity": 5, "unit_price": 15, "remarks": None,
    }])
    update_order_status(db, order.id, "已完成")
    update_order_status(db, order.id, "已取消")
    assert get_stock(db, "part", part_chain.id) == 100


def test_complete_aggregates_same_part_across_items(db, part_chain):
    add_stock(db, "part", part_chain.id, 10, "测试入库")
    order = create_order(db, "客户A", [
        {"part_id": part_chain.id, "quantity": 4, "unit_price": 15, "remarks": None},
        {"part_id": part_chain.id, "quantity": 4, "unit_price": 15, "remarks": None},
    ])
    update_order_status(db, order.id, "已完成")
    assert get_stock(db, "part", part_chain.id) == 2


def test_complete_order_jewelry_only_does_not_touch_stock(db):
    from models.jewelry import Jewelry
    from models.bom import Bom
    db.add(Jewelry(id="SP-T2", name="j", status="active",
                   handcraft_cost=0, wholesale_price=100))
    db.add(Part(id="PJ-T2", name="p", unit_cost=10))
    db.flush()
    db.add(Bom(id="BM-T2", jewelry_id="SP-T2", part_id="PJ-T2", qty_per_unit=1))
    db.flush()
    order = create_order(db, "客户A", [{
        "jewelry_id": "SP-T2", "quantity": 1, "unit_price": 100, "remarks": None,
    }])
    update_order_status(db, order.id, "已完成")
    db.refresh(order)
    assert order.status == "已完成"


def test_reject_customer_code_on_part_item(db, part_chain):
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id, "quantity": 1, "unit_price": 15, "remarks": None,
    }])
    item = db.query(OrderItem).filter_by(order_id=order.id).first()
    with pytest.raises(ValueError, match="配件项不允许设置客户货号"):
        update_order_item_customer_code(db, order.id, item.id, "C001")


def test_reject_batch_customer_code_with_part_item(db, part_chain):
    from models.jewelry import Jewelry
    db.add(Jewelry(id="SP-T3", name="j", status="active", wholesale_price=100))
    db.flush()
    order = create_order(db, "客户A", [
        {"jewelry_id": "SP-T3", "quantity": 1, "unit_price": 100, "remarks": None},
        {"part_id": part_chain.id, "quantity": 1, "unit_price": 15, "remarks": None},
    ])
    items = db.query(OrderItem).filter_by(order_id=order.id).all()
    item_ids = [i.id for i in items]
    with pytest.raises(ValueError, match="配件项不允许设置客户货号"):
        batch_fill_customer_code(db, order.id, item_ids, "C", 0, 2)


def test_parts_summary_merges_bom_and_direct(db, part_chain):
    from models.jewelry import Jewelry
    from models.bom import Bom
    db.add(Jewelry(id="SP-T4", name="j", status="active",
                   handcraft_cost=0, wholesale_price=200))
    db.flush()
    db.add(Bom(id="BM-T4", jewelry_id="SP-T4", part_id=part_chain.id, qty_per_unit=3))
    db.flush()
    order = create_order(db, "客户A", [
        {"jewelry_id": "SP-T4", "quantity": 1, "unit_price": 200, "remarks": None},
        {"part_id": part_chain.id, "quantity": 5, "unit_price": 15, "remarks": None},
    ])
    summary = get_parts_summary(db, order.id)
    row = next(r for r in summary if r["part_id"] == part_chain.id)
    assert row["total_qty"] == 8  # 3 BOM + 5 direct (ceil)
    sources = row["source_jewelries"]
    types = {s.get("source_type", "jewelry") for s in sources}
    assert "direct" in types
    assert "jewelry" in types
    direct = next(s for s in sources if s.get("source_type") == "direct")
    assert direct["order_qty"] == 5


def test_parts_summary_direct_only_order(db, part_chain):
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id, "quantity": 7, "unit_price": 15, "remarks": None,
    }])
    summary = get_parts_summary(db, order.id)
    assert len(summary) == 1
    row = summary[0]
    assert row["part_id"] == part_chain.id
    assert row["total_qty"] == 7
    assert row["source_jewelries"][0].get("source_type") == "direct"


def test_global_part_demand_includes_direct_purchases_across_orders(db, part_chain):
    """When Order A directly buys 50 of part X, Order B's parts-summary
    `global_demand` for part X should include that 50 (so cross-order
    contention is reflected)."""
    from models.jewelry import Jewelry
    from models.bom import Bom

    # Order A: directly buys 50 of part_chain
    create_order(db, "A", [{
        "part_id": part_chain.id, "quantity": 50, "unit_price": 15, "remarks": None,
    }])

    # Order B: a jewelry order whose BOM also uses part_chain (qty 2 per unit, 1 unit)
    db.add(Jewelry(id="SP-GD1", name="j", status="active",
                   handcraft_cost=0, wholesale_price=200))
    db.flush()
    db.add(Bom(id="BM-GD1", jewelry_id="SP-GD1", part_id=part_chain.id, qty_per_unit=2))
    db.flush()
    order_b = create_order(db, "B", [
        {"jewelry_id": "SP-GD1", "quantity": 1, "unit_price": 200, "remarks": None},
    ])

    summary = get_parts_summary(db, order_b.id)
    row = next(r for r in summary if r["part_id"] == part_chain.id)
    # global_demand = Order B's BOM (2) + Order A's direct (50) = 52
    assert row["global_demand"] >= 52


def test_add_order_item_with_missing_part_raises_value_error(db, part_chain):
    """Missing part_id in add_order_item must raise ValueError (HTTP 400),
    not flow through to an IntegrityError (HTTP 500)."""
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id, "quantity": 1, "unit_price": 15, "remarks": None,
    }])
    with pytest.raises(ValueError, match="配件 PJ-NOPE 不存在"):
        add_order_item(db, order.id, {
            "part_id": "PJ-NOPE", "quantity": 1, "unit_price": 10,
        })


def test_update_order_item_with_null_unit_price_does_not_crash(db, part_chain):
    """PATCH with explicit unit_price=null should not crash."""
    order = create_order(db, "客户A", [{
        "part_id": part_chain.id, "quantity": 1, "unit_price": 15, "remarks": None,
    }])
    item = db.query(OrderItem).filter_by(order_id=order.id).first()
    # Should not raise — null unit_price is treated as "no price change"
    update_order_item(db, order.id, item.id, {"unit_price": None, "quantity": 2})
    db.refresh(item)
    assert item.quantity == 2
    # Wholesale price unchanged because unit_price was null
    db.refresh(part_chain)
    assert part_chain.wholesale_price == Decimal("15")
