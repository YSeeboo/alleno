"""Tests for plating order line-item CRUD endpoints and status change."""
import pytest

from services.inventory import add_stock
from services.part import create_part
from services.plating import create_plating_order, send_plating_order


# ──────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────

@pytest.fixture
def part(db):
    p = create_part(db, {"name": "铜扣", "category": "小配件"})
    add_stock(db, "part", p.id, 500.0, "入库")
    db.commit()
    return p


@pytest.fixture
def part2(db):
    p = create_part(db, {"name": "银扣", "category": "小配件"})
    add_stock(db, "part", p.id, 500.0, "入库")
    db.commit()
    return p


@pytest.fixture
def pending_order(client, part):
    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀厂A",
        "items": [{"part_id": part.id, "qty": 10.0, "plating_method": "金色"}],
    })
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def sent_order(client, part):
    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀厂B",
        "items": [{"part_id": part.id, "qty": 10.0, "plating_method": "银色"}],
    })
    order_id = resp.json()["id"]
    client.post(f"/api/plating/{order_id}/send")
    return resp.json()


# ──────────────────────────────────────────────────────────────
# POST /api/plating/{order_id}/items — add item
# ──────────────────────────────────────────────────────────────

def test_add_item_pending_order(client, pending_order, part2):
    order_id = pending_order["id"]
    resp = client.post(f"/api/plating/{order_id}/items", json={
        "part_id": part2.id,
        "qty": 20.0,
        "plating_method": "镍色",
        "unit": "个",
        "note": "extra batch",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["part_id"] == part2.id
    assert float(data["qty"]) == 20.0
    assert data["plating_method"] == "镍色"
    assert data["unit"] == "个"
    assert data["note"] == "extra batch"
    assert data["plating_order_id"] == order_id


def test_add_item_order_not_found(client):
    resp = client.post("/api/plating/EP-9999/items", json={
        "part_id": "PJ-0001", "qty": 5.0,
    })
    assert resp.status_code == 404


def test_add_item_non_pending_order_rejected(client, sent_order, part2):
    order_id = sent_order["id"]
    resp = client.post(f"/api/plating/{order_id}/items", json={
        "part_id": part2.id,
        "qty": 5.0,
    })
    assert resp.status_code == 400
    assert "pending" in resp.json()["detail"].lower()


def test_add_item_zero_qty_rejected(client, pending_order, part2):
    order_id = pending_order["id"]
    resp = client.post(f"/api/plating/{order_id}/items", json={
        "part_id": part2.id, "qty": 0,
    })
    assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────
# PUT /api/plating/{order_id}/items/{item_id} — edit item
# ──────────────────────────────────────────────────────────────

def _get_first_item_id(client, order_id):
    resp = client.get(f"/api/plating/{order_id}/items")
    assert resp.status_code == 200
    return resp.json()[0]["id"]


def test_edit_item_pending_order(client, pending_order):
    order_id = pending_order["id"]
    item_id = _get_first_item_id(client, order_id)

    resp = client.put(f"/api/plating/{order_id}/items/{item_id}", json={
        "qty": 25.0,
        "plating_method": "哑金",
        "note": "updated note",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert float(data["qty"]) == 25.0
    assert data["plating_method"] == "哑金"
    assert data["note"] == "updated note"


def test_edit_item_sent_order_rejected(client, sent_order):
    """Editing is blocked when order is not pending."""
    order_id = sent_order["id"]
    item_id = _get_first_item_id(client, order_id)

    resp = client.put(f"/api/plating/{order_id}/items/{item_id}", json={
        "note": "corrected note",
    })
    assert resp.status_code == 400


def test_edit_item_not_found(client, pending_order):
    order_id = pending_order["id"]
    resp = client.put(f"/api/plating/{order_id}/items/99999", json={"note": "x"})
    assert resp.status_code == 400


def test_edit_item_order_not_found(client):
    resp = client.put("/api/plating/EP-9999/items/1", json={"note": "x"})
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────
# DELETE /api/plating/{order_id}/items/{item_id} — delete item
# ──────────────────────────────────────────────────────────────

def test_delete_item_pending_order(client, pending_order, part2):
    order_id = pending_order["id"]
    # First add a second item to delete
    add_resp = client.post(f"/api/plating/{order_id}/items", json={
        "part_id": part2.id, "qty": 5.0,
    })
    item_id = add_resp.json()["id"]

    resp = client.delete(f"/api/plating/{order_id}/items/{item_id}")
    assert resp.status_code == 204

    # Verify it's gone
    items_resp = client.get(f"/api/plating/{order_id}/items")
    ids = [i["id"] for i in items_resp.json()]
    assert item_id not in ids


def test_delete_item_non_pending_order_rejected(client, sent_order):
    order_id = sent_order["id"]
    item_id = _get_first_item_id(client, order_id)

    resp = client.delete(f"/api/plating/{order_id}/items/{item_id}")
    assert resp.status_code == 400
    assert "pending" in resp.json()["detail"].lower()


def test_delete_item_not_found(client, pending_order):
    order_id = pending_order["id"]
    resp = client.delete(f"/api/plating/{order_id}/items/99999")
    assert resp.status_code == 400


def test_delete_item_order_not_found(client):
    resp = client.delete("/api/plating/EP-9999/items/1")
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────
# PATCH /api/plating/{order_id}/status — change order status
# ──────────────────────────────────────────────────────────────

def test_patch_status_processing_to_completed_rejected(client, sent_order):
    """processing -> completed must go through POST /receive, not PATCH /status."""
    order_id = sent_order["id"]
    resp = client.patch(f"/api/plating/{order_id}/status", json={"status": "completed"})
    assert resp.status_code == 400


def test_patch_status_pending_to_processing_rejected(client, pending_order):
    """pending -> processing must go through POST /send, not PATCH /status."""
    order_id = pending_order["id"]
    resp = client.patch(f"/api/plating/{order_id}/status", json={"status": "processing"})
    assert resp.status_code == 400


def test_patch_status_invalid_value_rejected(client, pending_order):
    """Non-enum status values are rejected."""
    order_id = pending_order["id"]
    resp = client.patch(f"/api/plating/{order_id}/status", json={"status": "garbage"})
    assert resp.status_code == 400


def test_patch_status_order_not_found(client):
    resp = client.patch("/api/plating/EP-9999/status", json={"status": "processing"})
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────
# qty > 0 validation
# ──────────────────────────────────────────────────────────────

def test_edit_item_zero_qty_rejected(client, pending_order):
    """qty=0 must be rejected by the update schema."""
    order_id = pending_order["id"]
    item_id = _get_first_item_id(client, order_id)
    resp = client.put(f"/api/plating/{order_id}/items/{item_id}", json={"qty": 0})
    assert resp.status_code == 422


def test_edit_item_negative_qty_rejected(client, pending_order):
    """Negative qty must be rejected by the update schema."""
    order_id = pending_order["id"]
    item_id = _get_first_item_id(client, order_id)
    resp = client.put(f"/api/plating/{order_id}/items/{item_id}", json={"qty": -5})
    assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────
# Empty-order prevention
# ──────────────────────────────────────────────────────────────

def test_delete_last_item_rejected(client, pending_order):
    """Cannot delete the only remaining item in an order."""
    order_id = pending_order["id"]
    item_id = _get_first_item_id(client, order_id)
    resp = client.delete(f"/api/plating/{order_id}/items/{item_id}")
    assert resp.status_code == 400
