from datetime import datetime

import pytest

from models.plating_order import PlatingOrder
from services.part import create_part


@pytest.fixture
def order_with_note(client, db):
    part = create_part(db, {"name": "备注测试配件", "category": "小配件"})
    db.commit()
    response = client.post("/api/plating/", json={
        "supplier_name": "备注测试电镀厂",
        "items": [{"part_id": part.id, "qty": 10}],
        "note": "原有备注",
    })
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize("status", ["pending", "processing", "completed"])
def test_update_plating_note_preserves_business_fields(client, db, order_with_note, status):
    order_id = order_with_note["id"]
    order = db.get(PlatingOrder, order_id)
    order.status = status
    db.flush()
    items_before = client.get(f"/api/plating/{order_id}/items").json()

    response = client.patch(f"/api/plating/{order_id}", json={"note": "新的备注\n保留换行"})

    assert response.status_code == 200
    assert response.json()["note"] == "新的备注\n保留换行"
    assert response.json()["status"] == status
    assert response.json()["supplier_name"] == order_with_note["supplier_name"]
    assert response.json()["created_at"] == order_with_note["created_at"]
    assert client.get(f"/api/plating/{order_id}").json()["note"] == "新的备注\n保留换行"
    assert client.get(f"/api/plating/{order_id}/items").json() == items_before


@pytest.mark.parametrize("note", [None, ""])
def test_clear_plating_note(client, order_with_note, note):
    response = client.patch(f"/api/plating/{order_with_note['id']}", json={"note": note})
    assert response.status_code == 200
    assert response.json()["note"] == note


@pytest.mark.parametrize("update", [{}, {"created_at": "2026-11-08"}, {"supplier_name": "另一家电镀厂"}])
def test_omitted_note_is_not_cleared_by_other_updates(client, order_with_note, update):
    response = client.patch(f"/api/plating/{order_with_note['id']}", json=update)
    assert response.status_code == 200
    assert response.json()["note"] == "原有备注"


def test_archived_plating_note_is_read_only(client, db, order_with_note):
    order_id = order_with_note["id"]
    order = db.get(PlatingOrder, order_id)
    order.archived_at = datetime(2026, 11, 8, 10)
    db.flush()

    response = client.patch(f"/api/plating/{order_id}", json={"note": "不应写入"})
    assert response.status_code == 409
    assert client.get(f"/api/plating/{order_id}").json()["note"] == "原有备注"
