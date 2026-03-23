import pytest
from decimal import Decimal

from services.purchase_order import (
    create_purchase_order,
    create_purchase_item_addon,
    update_purchase_item_addon,
    delete_purchase_item_addon,
    get_purchase_order,
)


@pytest.fixture
def part(db):
    from models.part import Part
    p = Part(id="PJ-DZ-00001", name="测试配件", category="吊坠")
    db.add(p)
    db.flush()
    return p


@pytest.fixture
def order_and_item(db, part):
    order = create_purchase_order(
        db,
        vendor_name="测试商家",
        items=[{"part_id": part.id, "qty": 200, "unit": "条", "price": 5.0}],
    )
    return order, order.items[0]


def test_create_addon(db, order_and_item):
    order, item = order_and_item
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    assert addon.type == "bead_stringing"
    assert addon.qty == 10
    assert addon.price == Decimal("3")
    assert addon.amount == Decimal("30")
    assert addon.unit_cost == Decimal("0.15")


def test_create_addon_updates_total(db, order_and_item):
    order, item = order_and_item
    original_total = float(order.total_amount)
    create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    refreshed = get_purchase_order(db, order.id)
    assert float(refreshed.total_amount) == original_total + 30


def test_create_addon_duplicate_type_rejected(db, order_and_item):
    order, item = order_and_item
    create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    with pytest.raises(ValueError, match="已存在"):
        create_purchase_item_addon(
            db, order.id, item.id, type="bead_stringing", qty=5, unit="条", price=2.0,
        )


def test_create_addon_paid_order_rejected(db, order_and_item):
    order, item = order_and_item
    from services.purchase_order import update_purchase_order_status
    update_purchase_order_status(db, order.id, "已付款")
    with pytest.raises(ValueError, match="已付款"):
        create_purchase_item_addon(
            db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
        )


def test_update_addon(db, order_and_item):
    order, item = order_and_item
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    updated = update_purchase_item_addon(db, order.id, item.id, addon.id, qty=20, price=4.0)
    assert updated.qty == 20
    assert updated.price == Decimal("4")
    assert updated.amount == Decimal("80")
    assert updated.unit_cost == Decimal("0.4")


def test_update_addon_updates_total(db, order_and_item):
    order, item = order_and_item
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    update_purchase_item_addon(db, order.id, item.id, addon.id, qty=20, price=4.0)
    refreshed = get_purchase_order(db, order.id)
    assert float(refreshed.total_amount) == 1080


def test_delete_addon(db, order_and_item):
    order, item = order_and_item
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    delete_purchase_item_addon(db, order.id, item.id, addon.id)
    refreshed = get_purchase_order(db, order.id)
    assert float(refreshed.total_amount) == 1000
    assert len(refreshed.items[0].addons) == 0


def test_delete_addon_paid_rejected(db, order_and_item):
    order, item = order_and_item
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    from services.purchase_order import update_purchase_order_status
    update_purchase_order_status(db, order.id, "已付款")
    with pytest.raises(ValueError, match="已付款"):
        delete_purchase_item_addon(db, order.id, item.id, addon.id)


def test_delete_order_cascades_addons(db, part):
    from services.purchase_order import delete_purchase_order
    order = create_purchase_order(
        db,
        vendor_name="测试商家",
        items=[{"part_id": part.id, "qty": 200, "unit": "条", "price": 5.0}],
    )
    item = order.items[0]
    create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    delete_purchase_order(db, order.id)
    from models.purchase_order import PurchaseOrderItemAddon
    remaining = db.query(PurchaseOrderItemAddon).all()
    assert len(remaining) == 0


def test_update_item_qty_recalcs_addon_unit_cost(db, order_and_item):
    from services.purchase_order import update_purchase_item
    order, item = order_and_item
    addon = create_purchase_item_addon(
        db, order.id, item.id, type="bead_stringing", qty=10, unit="条", price=3.0,
    )
    assert addon.unit_cost == Decimal("0.15")
    update_purchase_item(db, order.id, item.id, {"qty": 100})
    db.refresh(addon)
    assert addon.unit_cost == Decimal("0.3")


# --- API Tests ---

def _create_part_via_db(db):
    from models.part import Part
    p = Part(id="PJ-DZ-00099", name="API测试配件", category="吊坠")
    db.add(p)
    db.flush()
    return p


def test_api_create_addon(client, db):
    part = _create_part_via_db(db)
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part.id, "qty": 100, "unit": "条", "price": 2.0}],
    }).json()
    item_id = po["items"][0]["id"]
    resp = client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 5, "unit": "条", "price": 1.0},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["type"] == "bead_stringing"
    assert data["amount"] == 5.0
    assert data["unit_cost"] == 0.05


def test_api_addon_in_order_response(client, db):
    part = _create_part_via_db(db)
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part.id, "qty": 100, "unit": "条", "price": 2.0}],
    }).json()
    item_id = po["items"][0]["id"]
    client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 5, "unit": "条", "price": 1.0},
    )
    resp = client.get(f"/api/purchase-orders/{po['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"][0]["addons"]) == 1
    assert data["total_amount"] == 205.0


def test_api_update_addon(client, db):
    part = _create_part_via_db(db)
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part.id, "qty": 100, "unit": "条", "price": 2.0}],
    }).json()
    item_id = po["items"][0]["id"]
    addon = client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 5, "unit": "条", "price": 1.0},
    ).json()
    resp = client.put(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons/{addon['id']}",
        json={"qty": 10, "price": 2.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["amount"] == 20.0
    assert data["unit_cost"] == 0.2


def test_api_delete_addon(client, db):
    part = _create_part_via_db(db)
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part.id, "qty": 100, "unit": "条", "price": 2.0}],
    }).json()
    item_id = po["items"][0]["id"]
    addon = client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 5, "unit": "条", "price": 1.0},
    ).json()
    resp = client.delete(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons/{addon['id']}",
    )
    assert resp.status_code == 204
    order = client.get(f"/api/purchase-orders/{po['id']}").json()
    assert order["total_amount"] == 200.0
    assert len(order["items"][0]["addons"]) == 0


def test_api_create_addon_paid_returns_400(client, db):
    part = _create_part_via_db(db)
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [{"part_id": part.id, "qty": 100, "unit": "条", "price": 2.0}],
    }).json()
    item_id = po["items"][0]["id"]
    client.patch(f"/api/purchase-orders/{po['id']}/status", json={"status": "已付款"})
    resp = client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 5, "unit": "条", "price": 1.0},
    )
    assert resp.status_code == 400


def test_api_delete_item_cascades_addon(client, db):
    part = _create_part_via_db(db)
    po = client.post("/api/purchase-orders", json={
        "vendor_name": "API商家",
        "items": [
            {"part_id": part.id, "qty": 100, "unit": "条", "price": 2.0},
            {"part_id": part.id, "qty": 50, "unit": "条", "price": 1.0},
        ],
    }).json()
    item_id = po["items"][0]["id"]
    client.post(
        f"/api/purchase-orders/{po['id']}/items/{item_id}/addons",
        json={"type": "bead_stringing", "qty": 5, "unit": "条", "price": 1.0},
    )
    resp = client.delete(f"/api/purchase-orders/{po['id']}/items/{item_id}")
    assert resp.status_code == 204
    order = client.get(f"/api/purchase-orders/{po['id']}").json()
    assert len(order["items"]) == 1
    assert order["total_amount"] == 50.0
