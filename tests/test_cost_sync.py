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


def test_detect_purchase_cost_diffs_trailing_null(db, part_a):
    """Last row for same part has price=None → no diff should be produced."""
    from services.cost_sync import detect_purchase_cost_diffs
    order = create_purchase_order(
        db, vendor_name="商家",
        items=[
            {"part_id": part_a.id, "qty": 50, "price": 2.0},
            {"part_id": part_a.id, "qty": 50},
        ],
    )
    diffs = detect_purchase_cost_diffs(db, order)
    assert len(diffs) == 0


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


def test_detect_plating_cost_diffs_trailing_null(db, part_a):
    """Last receipt row for same receive part has price=None → no diff."""
    from services.cost_sync import detect_plating_cost_diffs
    from services.plating_receipt import create_plating_receipt

    variant, poi = _setup_plating_scenario(db, part_a)
    receipt = create_plating_receipt(
        db, vendor_name="电镀商",
        items=[
            {"plating_order_item_id": poi.id, "part_id": variant.id, "qty": 5, "price": 1.5},
            {"plating_order_item_id": poi.id, "part_id": variant.id, "qty": 5},
        ],
    )
    diffs = detect_plating_cost_diffs(db, receipt)
    assert len(diffs) == 0


# --- API Tests ---

def test_api_create_purchase_order_auto_sets_cost(client, db, part_a):
    """Creating a PO with price auto-sets purchase_cost; no diffs remain."""
    assert client.get(f"/api/parts/{part_a.id}").json()["purchase_cost"] is None
    resp = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part_a.id, "qty": 100, "price": 2.5}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["cost_diffs"] == []
    # Part cost was auto-set
    assert client.get(f"/api/parts/{part_a.id}").json()["purchase_cost"] == 2.5


def test_api_create_purchase_order_duplicate_part_uses_last_price(client, db, part_a):
    """Duplicate part_id rows: auto-set uses last-row-wins price."""
    resp = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [
            {"part_id": part_a.id, "qty": 50, "price": 2.0},
            {"part_id": part_a.id, "qty": 50, "price": 3.0},
        ],
    })
    assert resp.status_code == 201
    assert resp.json()["cost_diffs"] == []
    # Last price (3.0) should be the one auto-set
    assert client.get(f"/api/parts/{part_a.id}").json()["purchase_cost"] == 3.0


def test_api_create_purchase_order_no_diffs(client, db, part_a):
    update_part_cost(db, part_a.id, "purchase_cost", 2.5)
    resp = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part_a.id, "qty": 100, "price": 2.5}],
    })
    assert resp.status_code == 201
    assert resp.json()["cost_diffs"] == []


def test_api_get_purchase_order_cost_diffs_empty(client, db, part_a):
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part_a.id, "qty": 100, "price": 2.5}],
    }).json()
    resp = client.get(f"/api/purchase-orders/{po['id']}")
    assert resp.json()["cost_diffs"] == []


def test_api_create_addon_auto_sets_bead_cost(client, db, part_a):
    """Creating a bead_stringing addon auto-sets bead_cost; no diffs remain."""
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part_a.id, "qty": 200, "price": 5.0}],
    }).json()
    item_id = po["items"][0]["id"]
    assert client.get(f"/api/parts/{part_a.id}").json()["bead_cost"] is None
    resp = client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 10, "unit": "条", "price": 3.0},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["cost_diffs"] == []
    # bead_cost was auto-set (unit_cost = 3.0 * 10 / 200 = 0.15)
    assert client.get(f"/api/parts/{part_a.id}").json()["bead_cost"] == 0.15


def test_api_update_addon_returns_cost_diffs(client, db, part_a):
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part_a.id, "qty": 200, "price": 5.0}],
    }).json()
    item_id = po["items"][0]["id"]
    addon = client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 10, "unit": "条", "price": 3.0},
    ).json()
    resp = client.put(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons/{addon['id']}",
        json={"price": 4.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "cost_diffs" in data


def test_api_batch_update_costs(client, db, part_a, part_b):
    resp = client.post("/api/parts/batch-update-costs", json={
        "updates": [
            {"part_id": part_a.id, "field": "purchase_cost", "value": 3.0, "source_id": "CG-0001"},
            {"part_id": part_b.id, "field": "purchase_cost", "value": 5.0, "source_id": "CG-0001"},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated_count"] == 2
    assert len(data["results"]) == 2
    assert all(r["updated"] for r in data["results"])

    p_a = client.get(f"/api/parts/{part_a.id}").json()
    assert p_a["purchase_cost"] == 3.0


def test_api_batch_update_costs_no_change(client, db, part_a):
    update_part_cost(db, part_a.id, "purchase_cost", 3.0)
    resp = client.post("/api/parts/batch-update-costs", json={
        "updates": [
            {"part_id": part_a.id, "field": "purchase_cost", "value": 3.0, "source_id": "CG-0001"},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated_count"] == 0
    assert data["results"][0]["updated"] is False


def test_api_batch_update_costs_invalid_field(client, db, part_a):
    resp = client.post("/api/parts/batch-update-costs", json={
        "updates": [
            {"part_id": part_a.id, "field": "invalid", "value": 3.0},
        ],
    })
    assert resp.status_code == 400


def test_api_create_plating_receipt_returns_cost_diffs(client, db, part_a):
    from services.part import create_part_variant
    from services.plating import create_plating_order, send_plating_order
    from services.inventory import add_stock

    variant = create_part_variant(db, part_a.id, "G")
    add_stock(db, "part", part_a.id, 100, "测试入库")
    order = create_plating_order(db, supplier_name="电镀商", items=[{
        "part_id": part_a.id, "qty": 50, "receive_part_id": variant.id,
    }])
    send_plating_order(db, order.id)
    from models.plating_order import PlatingOrderItem
    poi = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order.id
    ).first()

    resp = client.post("/api/plating-receipts/", json={
        "vendor_name": "电镀商",
        "items": [{"plating_order_item_id": poi.id, "part_id": variant.id, "qty": 10, "price": 1.5}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "cost_diffs" in data
    assert len(data["cost_diffs"]) == 1
    assert data["cost_diffs"][0]["field"] == "plating_cost"


# --- Auto-set initial cost on update tests ---

def test_api_update_item_auto_sets_purchase_cost(client, db, part_a):
    """Updating a purchase item sets purchase_cost if part has none."""
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "商家",
        "items": [{"part_id": part_a.id, "qty": 100}],
    }).json()
    item_id = po["items"][0]["id"]
    # Part has no purchase_cost yet
    assert client.get(f"/api/parts/{part_a.id}").json()["purchase_cost"] is None

    # Update item with a price
    client.put(
        f"/api/purchase-orders/{po['id']}/items/{item_id}",
        json={"price": 2.5},
    )
    # Now part should have purchase_cost
    assert client.get(f"/api/parts/{part_a.id}").json()["purchase_cost"] == 2.5


def test_api_update_item_historical_order_sets_unit_cost(client, db, part_a):
    """Historical order (created before auto-set): item has price but part
    has no cost. User clicks edit and saves without changes → unit_cost updates."""
    # Create order — auto-set fires, sets purchase_cost
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "商家",
        "items": [{"part_id": part_a.id, "qty": 100, "price": 2.5}],
    }).json()
    item_id = po["items"][0]["id"]

    # Simulate historical data: clear cost as if order was created before auto-set
    part_a.purchase_cost = None
    part_a.unit_cost = None
    db.flush()
    p = client.get(f"/api/parts/{part_a.id}").json()
    assert p["purchase_cost"] is None
    assert p["unit_cost"] is None

    # User clicks edit → saves without changing anything (frontend sends all fields)
    client.put(
        f"/api/purchase-orders/{po['id']}/items/{item_id}",
        json={"qty": 100, "unit": "个", "price": 2.5, "note": ""},
    )
    p = client.get(f"/api/parts/{part_a.id}").json()
    assert p["purchase_cost"] == 2.5
    assert p["unit_cost"] == 2.5


def test_api_update_item_overwrites_existing_cost(client, db, part_a):
    """Updating a purchase item always syncs purchase_cost to latest price."""
    update_part_cost(db, part_a.id, "purchase_cost", 1.0)
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "商家",
        "items": [{"part_id": part_a.id, "qty": 100}],
    }).json()
    item_id = po["items"][0]["id"]

    client.put(
        f"/api/purchase-orders/{po['id']}/items/{item_id}",
        json={"price": 9.9},
    )
    # Should be updated to 9.9
    assert client.get(f"/api/parts/{part_a.id}").json()["purchase_cost"] == 9.9


def test_api_create_addon_auto_sets_bead_cost_on_create(client, db, part_a):
    """Creating a bead_stringing addon auto-sets bead_cost when part has none."""
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "商家",
        "items": [{"part_id": part_a.id, "qty": 200, "price": 5.0}],
    }).json()
    item_id = po["items"][0]["id"]
    assert client.get(f"/api/parts/{part_a.id}").json()["bead_cost"] is None

    client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 10, "unit": "条", "price": 3.0},
    )
    # bead_cost should now be set (unit_cost = 3.0 * 10 / 200 = 0.15)
    assert client.get(f"/api/parts/{part_a.id}").json()["bead_cost"] == 0.15


def test_api_update_addon_auto_sets_bead_cost_on_put(client, db, part_b):
    """PUT on a bead_stringing addon auto-sets bead_cost when part has none.
    Use part_b with bead_cost pre-set then cleared to isolate the PUT path."""
    # Create order + bead addon — this auto-sets bead_cost
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "商家",
        "items": [{"part_id": part_b.id, "qty": 200, "price": 5.0}],
    }).json()
    item_id = po["items"][0]["id"]
    addon = client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 10, "unit": "条", "price": 3.0},
    ).json()
    # Create set it to 0.15; now clear it via direct DB write to isolate PUT
    part_b.bead_cost = None
    db.flush()
    assert client.get(f"/api/parts/{part_b.id}").json()["bead_cost"] is None

    # PUT updates the addon — should auto-set bead_cost
    client.put(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons/{addon['id']}",
        json={"price": 4.0},
    )
    # unit_cost = 4.0 * 10 / 200 = 0.2
    assert client.get(f"/api/parts/{part_b.id}").json()["bead_cost"] == 0.2


def test_api_update_addon_overwrites_existing_bead_cost(client, db, part_a):
    """Updating a bead_stringing addon always syncs bead_cost to latest value."""
    update_part_cost(db, part_a.id, "bead_cost", 0.1)
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "商家",
        "items": [{"part_id": part_a.id, "qty": 200, "price": 5.0}],
    }).json()
    item_id = po["items"][0]["id"]
    addon = client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 10, "unit": "条", "price": 3.0},
    ).json()

    client.put(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons/{addon['id']}",
        json={"price": 99.0},
    )
    # unit_cost = 99.0 * 10 / 200 = 4.95
    assert client.get(f"/api/parts/{part_a.id}").json()["bead_cost"] == 4.95
