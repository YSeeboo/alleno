import pytest
from decimal import Decimal

from models.part import Part
from services.part import create_part, update_part_cost
from services.purchase_order import create_purchase_order, create_purchase_item_addon


@pytest.fixture
def part_a(db):
    return create_part(db, {"name": "配件A", "category": "吊坠"})


@pytest.fixture
def part_b(db):
    return create_part(db, {"name": "配件B", "category": "链条"})


def test_detect_purchase_cost_diffs_no_existing(db, part_a):
    from services.cost_sync import detect_purchase_cost_diffs
    order = create_purchase_order(
        db, vendor_name="商家", items=[{"part_id": part_a.id, "qty": 100, "price": 2.5}],
    )
    diffs = detect_purchase_cost_diffs(db, order)
    assert len(diffs) == 1
    assert diffs[0]["part_id"] == part_a.id
    assert diffs[0]["field"] == "purchase_cost"
    assert diffs[0]["current_value"] is None
    assert diffs[0]["new_value"] == float(Decimal("2.5"))


def test_detect_purchase_cost_diffs_same_value(db, part_a):
    from services.cost_sync import detect_purchase_cost_diffs
    update_part_cost(db, part_a.id, "purchase_cost", 2.5)
    order = create_purchase_order(
        db, vendor_name="商家", items=[{"part_id": part_a.id, "qty": 100, "price": 2.5}],
    )
    diffs = detect_purchase_cost_diffs(db, order)
    assert len(diffs) == 0


def test_detect_purchase_cost_diffs_different_value(db, part_a):
    from services.cost_sync import detect_purchase_cost_diffs
    update_part_cost(db, part_a.id, "purchase_cost", 2.0)
    order = create_purchase_order(
        db, vendor_name="商家", items=[{"part_id": part_a.id, "qty": 100, "price": 3.0}],
    )
    diffs = detect_purchase_cost_diffs(db, order)
    assert len(diffs) == 1
    assert diffs[0]["current_value"] == 2.0
    assert diffs[0]["new_value"] == 3.0


def test_detect_purchase_cost_diffs_no_price(db, part_a):
    from services.cost_sync import detect_purchase_cost_diffs
    order = create_purchase_order(
        db, vendor_name="商家", items=[{"part_id": part_a.id, "qty": 100}],
    )
    diffs = detect_purchase_cost_diffs(db, order)
    assert len(diffs) == 0


def test_detect_purchase_cost_diffs_multiple_items_same_part(db, part_a):
    from services.cost_sync import detect_purchase_cost_diffs
    order = create_purchase_order(
        db, vendor_name="商家",
        items=[
            {"part_id": part_a.id, "qty": 50, "price": 2.0},
            {"part_id": part_a.id, "qty": 50, "price": 3.0},
        ],
    )
    diffs = detect_purchase_cost_diffs(db, order)
    assert len(diffs) == 1
    assert diffs[0]["new_value"] == 3.0


def test_detect_addon_cost_diffs_bead(db, part_a):
    from services.cost_sync import detect_addon_cost_diffs
    order = create_purchase_order(
        db, vendor_name="商家", items=[{"part_id": part_a.id, "qty": 200, "price": 5.0}],
    )
    item = order.items[0]
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    diffs = detect_addon_cost_diffs(db, item, addon)
    assert len(diffs) == 1
    assert diffs[0]["field"] == "bead_cost"
    assert diffs[0]["current_value"] is None
    assert diffs[0]["new_value"] == 0.15


def test_detect_addon_cost_diffs_same_value(db, part_a):
    from services.cost_sync import detect_addon_cost_diffs
    update_part_cost(db, part_a.id, "bead_cost", 0.15)
    order = create_purchase_order(
        db, vendor_name="商家", items=[{"part_id": part_a.id, "qty": 200, "price": 5.0}],
    )
    item = order.items[0]
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    diffs = detect_addon_cost_diffs(db, item, addon)
    assert len(diffs) == 0


def test_detect_addon_cost_diffs_non_bead_type(db, part_a):
    from services.cost_sync import detect_addon_cost_diffs
    order = create_purchase_order(
        db, vendor_name="商家", items=[{"part_id": part_a.id, "qty": 200, "price": 5.0}],
    )
    item = order.items[0]
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="plating_cost", qty=10, unit="条", price=3.0,
    )
    diffs = detect_addon_cost_diffs(db, item, addon)
    assert len(diffs) == 0


# --- Plating receipt cost diff tests ---

def _setup_plating_scenario(db, part):
    from services.part import create_part_variant
    from services.plating import create_plating_order, send_plating_order
    from services.inventory import add_stock
    from models.plating_order import PlatingOrderItem

    variant = create_part_variant(db, part.id, "G")
    add_stock(db, "part", part.id, 100, "测试入库")
    order = create_plating_order(db, supplier_name="电镀商", items=[{
        "part_id": part.id,
        "qty": 50,
        "receive_part_id": variant.id,
    }])
    send_plating_order(db, order.id)
    poi = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order.id
    ).first()
    return variant, poi


def test_detect_plating_cost_diffs_no_existing(db, part_a):
    from services.cost_sync import detect_plating_cost_diffs
    from services.plating_receipt import create_plating_receipt

    variant, poi = _setup_plating_scenario(db, part_a)
    receipt = create_plating_receipt(
        db, vendor_name="电镀商",
        items=[{"plating_order_item_id": poi.id, "part_id": variant.id, "qty": 10, "price": 1.5}],
    )
    diffs = detect_plating_cost_diffs(db, receipt)
    assert len(diffs) == 1
    assert diffs[0]["part_id"] == variant.id
    assert diffs[0]["field"] == "plating_cost"
    assert diffs[0]["new_value"] == 1.5


def test_detect_plating_cost_diffs_same_value(db, part_a):
    from services.cost_sync import detect_plating_cost_diffs
    from services.plating_receipt import create_plating_receipt

    variant, poi = _setup_plating_scenario(db, part_a)
    update_part_cost(db, variant.id, "plating_cost", 1.5)
    receipt = create_plating_receipt(
        db, vendor_name="电镀商",
        items=[{"plating_order_item_id": poi.id, "part_id": variant.id, "qty": 10, "price": 1.5}],
    )
    diffs = detect_plating_cost_diffs(db, receipt)
    assert len(diffs) == 0


def test_detect_plating_cost_diffs_different_value(db, part_a):
    from services.cost_sync import detect_plating_cost_diffs
    from services.plating_receipt import create_plating_receipt

    variant, poi = _setup_plating_scenario(db, part_a)
    update_part_cost(db, variant.id, "plating_cost", 2.0)
    receipt = create_plating_receipt(
        db, vendor_name="电镀商",
        items=[{"plating_order_item_id": poi.id, "part_id": variant.id, "qty": 10, "price": 1.5}],
    )
    diffs = detect_plating_cost_diffs(db, receipt)
    assert len(diffs) == 1
    assert diffs[0]["current_value"] == 2.0
    assert diffs[0]["new_value"] == 1.5
