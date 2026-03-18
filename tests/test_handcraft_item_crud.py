"""Tests for handcraft order line-item CRUD endpoints and status change."""
import pytest

from services.handcraft import create_handcraft_order, send_handcraft_order
from services.inventory import add_stock
from services.jewelry import create_jewelry
from services.part import create_part


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
def jewelry(db):
    j = create_jewelry(db, {"name": "铜项链", "category": "单件"})
    db.commit()
    return j


@pytest.fixture
def jewelry2(db):
    j = create_jewelry(db, {"name": "银手镯", "category": "单件"})
    db.commit()
    return j


@pytest.fixture
def pending_order(client, part, jewelry):
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "手工厂A",
        "parts": [{"part_id": part.id, "qty": 50.0, "bom_qty": 5.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 10}],
    })
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def sent_order(client, part, jewelry):
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "手工厂B",
        "parts": [{"part_id": part.id, "qty": 50.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 10}],
    })
    order_id = resp.json()["id"]
    client.post(f"/api/handcraft/{order_id}/send")
    return resp.json()


# ──────────────────────────────────────────────────────────────
# POST /api/handcraft/{order_id}/parts — add part row
# ──────────────────────────────────────────────────────────────

def test_add_part_pending_order(client, pending_order, part2):
    order_id = pending_order["id"]
    resp = client.post(f"/api/handcraft/{order_id}/parts", json={
        "part_id": part2.id,
        "qty": 30.0,
        "bom_qty": 3.0,
        "unit": "个",
        "note": "extra parts",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["part_id"] == part2.id
    assert float(data["qty"]) == 30.0
    assert float(data["bom_qty"]) == 3.0
    assert data["unit"] == "个"
    assert data["note"] == "extra parts"
    assert data["handcraft_order_id"] == order_id


def test_add_part_order_not_found(client):
    resp = client.post("/api/handcraft/HC-9999/parts", json={
        "part_id": "PJ-0001", "qty": 5.0,
    })
    assert resp.status_code == 404


def test_add_part_non_pending_order_rejected(client, sent_order, part2):
    order_id = sent_order["id"]
    resp = client.post(f"/api/handcraft/{order_id}/parts", json={
        "part_id": part2.id, "qty": 5.0,
    })
    assert resp.status_code == 400
    assert "pending" in resp.json()["detail"].lower()


def test_add_part_zero_qty_rejected(client, pending_order, part2):
    order_id = pending_order["id"]
    resp = client.post(f"/api/handcraft/{order_id}/parts", json={
        "part_id": part2.id, "qty": 0,
    })
    assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────
# PUT /api/handcraft/{order_id}/parts/{item_id} — edit part row
# ──────────────────────────────────────────────────────────────

def _get_first_part_id(client, order_id):
    resp = client.get(f"/api/handcraft/{order_id}/parts")
    assert resp.status_code == 200
    return resp.json()[0]["id"]


def _get_first_jewelry_id(client, order_id):
    resp = client.get(f"/api/handcraft/{order_id}/jewelries")
    assert resp.status_code == 200
    return resp.json()[0]["id"]


def test_edit_part_pending_order(client, pending_order):
    order_id = pending_order["id"]
    item_id = _get_first_part_id(client, order_id)

    resp = client.put(f"/api/handcraft/{order_id}/parts/{item_id}", json={
        "qty": 60.0,
        "bom_qty": 6.0,
        "note": "updated",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert float(data["qty"]) == 60.0
    assert float(data["bom_qty"]) == 6.0
    assert data["note"] == "updated"


def test_edit_part_sent_order_rejected(client, sent_order):
    """Editing part rows is blocked when order is not pending."""
    order_id = sent_order["id"]
    item_id = _get_first_part_id(client, order_id)

    resp = client.put(f"/api/handcraft/{order_id}/parts/{item_id}", json={
        "note": "corrected",
    })
    assert resp.status_code == 400


def test_edit_part_not_found(client, pending_order):
    order_id = pending_order["id"]
    resp = client.put(f"/api/handcraft/{order_id}/parts/99999", json={"note": "x"})
    assert resp.status_code == 400


def test_edit_part_order_not_found(client):
    resp = client.put("/api/handcraft/HC-9999/parts/1", json={"note": "x"})
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────
# DELETE /api/handcraft/{order_id}/parts/{item_id} — delete part row
# ──────────────────────────────────────────────────────────────

def test_delete_part_pending_order(client, pending_order, part2):
    order_id = pending_order["id"]
    # Add a second part to delete
    add_resp = client.post(f"/api/handcraft/{order_id}/parts", json={
        "part_id": part2.id, "qty": 5.0,
    })
    item_id = add_resp.json()["id"]

    resp = client.delete(f"/api/handcraft/{order_id}/parts/{item_id}")
    assert resp.status_code == 204

    parts_resp = client.get(f"/api/handcraft/{order_id}/parts")
    ids = [p["id"] for p in parts_resp.json()]
    assert item_id not in ids


def test_delete_part_non_pending_order_rejected(client, sent_order):
    order_id = sent_order["id"]
    item_id = _get_first_part_id(client, order_id)

    resp = client.delete(f"/api/handcraft/{order_id}/parts/{item_id}")
    assert resp.status_code == 400
    assert "pending" in resp.json()["detail"].lower()


def test_delete_part_not_found(client, pending_order):
    order_id = pending_order["id"]
    resp = client.delete(f"/api/handcraft/{order_id}/parts/99999")
    assert resp.status_code == 400


def test_delete_part_order_not_found(client):
    resp = client.delete("/api/handcraft/HC-9999/parts/1")
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────
# POST /api/handcraft/{order_id}/jewelries — add jewelry row
# ──────────────────────────────────────────────────────────────

def test_add_jewelry_pending_order(client, pending_order, jewelry2):
    order_id = pending_order["id"]
    resp = client.post(f"/api/handcraft/{order_id}/jewelries", json={
        "jewelry_id": jewelry2.id,
        "qty": 5,
        "unit": "套",
        "note": "second product",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["jewelry_id"] == jewelry2.id
    assert data["qty"] == 5
    assert data["unit"] == "套"
    assert data["note"] == "second product"
    assert data["handcraft_order_id"] == order_id
    assert data["status"] == "未送出"


def test_add_jewelry_order_not_found(client):
    resp = client.post("/api/handcraft/HC-9999/jewelries", json={
        "jewelry_id": "SP-0001", "qty": 5,
    })
    assert resp.status_code == 404


def test_add_jewelry_non_pending_order_rejected(client, sent_order, jewelry2):
    order_id = sent_order["id"]
    resp = client.post(f"/api/handcraft/{order_id}/jewelries", json={
        "jewelry_id": jewelry2.id, "qty": 5,
    })
    assert resp.status_code == 400
    assert "pending" in resp.json()["detail"].lower()


def test_add_jewelry_zero_qty_rejected(client, pending_order, jewelry2):
    order_id = pending_order["id"]
    resp = client.post(f"/api/handcraft/{order_id}/jewelries", json={
        "jewelry_id": jewelry2.id, "qty": 0,
    })
    assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────
# PUT /api/handcraft/{order_id}/jewelries/{item_id} — edit jewelry row
# ──────────────────────────────────────────────────────────────

def test_edit_jewelry_pending_order(client, pending_order):
    order_id = pending_order["id"]
    item_id = _get_first_jewelry_id(client, order_id)

    resp = client.put(f"/api/handcraft/{order_id}/jewelries/{item_id}", json={
        "qty": 20,
        "note": "increased order",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["qty"] == 20
    assert data["note"] == "increased order"


def test_edit_jewelry_sent_order_rejected(client, sent_order):
    """Editing jewelry rows is blocked when order is not pending."""
    order_id = sent_order["id"]
    item_id = _get_first_jewelry_id(client, order_id)

    resp = client.put(f"/api/handcraft/{order_id}/jewelries/{item_id}", json={
        "note": "corrected note",
    })
    assert resp.status_code == 400


def test_edit_jewelry_not_found(client, pending_order):
    order_id = pending_order["id"]
    resp = client.put(f"/api/handcraft/{order_id}/jewelries/99999", json={"note": "x"})
    assert resp.status_code == 400


def test_edit_jewelry_order_not_found(client):
    resp = client.put("/api/handcraft/HC-9999/jewelries/1", json={"note": "x"})
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────
# DELETE /api/handcraft/{order_id}/jewelries/{item_id} — delete jewelry row
# ──────────────────────────────────────────────────────────────

def test_delete_jewelry_pending_order(client, pending_order, jewelry2):
    order_id = pending_order["id"]
    # Add a second jewelry to delete
    add_resp = client.post(f"/api/handcraft/{order_id}/jewelries", json={
        "jewelry_id": jewelry2.id, "qty": 3,
    })
    item_id = add_resp.json()["id"]

    resp = client.delete(f"/api/handcraft/{order_id}/jewelries/{item_id}")
    assert resp.status_code == 204

    jewelries_resp = client.get(f"/api/handcraft/{order_id}/jewelries")
    ids = [j["id"] for j in jewelries_resp.json()]
    assert item_id not in ids


def test_delete_jewelry_non_pending_order_rejected(client, sent_order):
    order_id = sent_order["id"]
    item_id = _get_first_jewelry_id(client, order_id)

    resp = client.delete(f"/api/handcraft/{order_id}/jewelries/{item_id}")
    assert resp.status_code == 400
    assert "pending" in resp.json()["detail"].lower()


def test_delete_jewelry_not_found(client, pending_order):
    order_id = pending_order["id"]
    resp = client.delete(f"/api/handcraft/{order_id}/jewelries/99999")
    assert resp.status_code == 400


def test_delete_jewelry_order_not_found(client):
    resp = client.delete("/api/handcraft/HC-9999/jewelries/1")
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────
# PATCH /api/handcraft/{order_id}/status — change order status
# ──────────────────────────────────────────────────────────────

def test_patch_status_processing_to_completed_rejected(client, sent_order):
    """processing -> completed must go through POST /receive, not PATCH /status."""
    order_id = sent_order["id"]
    resp = client.patch(f"/api/handcraft/{order_id}/status", json={"status": "completed"})
    assert resp.status_code == 400


def test_patch_status_pending_to_processing_rejected(client, pending_order):
    """pending -> processing must go through POST /send, not PATCH /status."""
    order_id = pending_order["id"]
    resp = client.patch(f"/api/handcraft/{order_id}/status", json={"status": "processing"})
    assert resp.status_code == 400


def test_patch_status_invalid_value_rejected(client, pending_order):
    """Non-enum status values are rejected."""
    order_id = pending_order["id"]
    resp = client.patch(f"/api/handcraft/{order_id}/status", json={"status": "garbage"})
    assert resp.status_code == 400


def test_patch_status_order_not_found(client):
    resp = client.patch("/api/handcraft/HC-9999/status", json={"status": "processing"})
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────
# qty > 0 validation
# ──────────────────────────────────────────────────────────────

def test_edit_part_zero_qty_rejected(client, pending_order):
    order_id = pending_order["id"]
    item_id = _get_first_part_id(client, order_id)
    resp = client.put(f"/api/handcraft/{order_id}/parts/{item_id}", json={"qty": 0})
    assert resp.status_code == 422


def test_edit_jewelry_negative_qty_rejected(client, pending_order):
    order_id = pending_order["id"]
    item_id = _get_first_jewelry_id(client, order_id)
    resp = client.put(f"/api/handcraft/{order_id}/jewelries/{item_id}", json={"qty": -1})
    assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────
# Empty-order prevention
# ──────────────────────────────────────────────────────────────

def test_delete_last_part_rejected(client, pending_order):
    """Cannot delete the only remaining part in an order."""
    order_id = pending_order["id"]
    item_id = _get_first_part_id(client, order_id)
    resp = client.delete(f"/api/handcraft/{order_id}/parts/{item_id}")
    assert resp.status_code == 400


def test_delete_last_jewelry_rejected(client, pending_order):
    """Cannot delete the only remaining jewelry in an order."""
    order_id = pending_order["id"]
    item_id = _get_first_jewelry_id(client, order_id)
    resp = client.delete(f"/api/handcraft/{order_id}/jewelries/{item_id}")
    assert resp.status_code == 400
