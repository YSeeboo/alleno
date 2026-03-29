import pytest
from services.part import create_part
from services.jewelry import create_jewelry
from services.bom import get_bom


def _create_parts(db):
    a = create_part(db, {"name": "链条", "category": "链条"})
    b = create_part(db, {"name": "龙虾扣", "category": "小配件"})
    return a, b


def test_create_template(client, db):
    a, b = _create_parts(db)
    resp = client.post("/api/jewelry-templates/", json={
        "name": "基础项链",
        "items": [
            {"part_id": a.id, "qty_per_unit": 1},
            {"part_id": b.id, "qty_per_unit": 2},
        ],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "基础项链"
    assert len(data["items"]) == 2


def test_create_template_with_image_and_note(client, db):
    a, _ = _create_parts(db)
    resp = client.post("/api/jewelry-templates/", json={
        "name": "带图模板",
        "image": "https://example.com/img.jpg",
        "note": "测试备注",
        "items": [{"part_id": a.id, "qty_per_unit": 1}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["image"] == "https://example.com/img.jpg"
    assert data["note"] == "测试备注"


def test_list_templates(client, db):
    a, _ = _create_parts(db)
    client.post("/api/jewelry-templates/", json={
        "name": "模板1",
        "items": [{"part_id": a.id, "qty_per_unit": 1}],
    })
    resp = client.get("/api/jewelry-templates/")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_get_template(client, db):
    a, _ = _create_parts(db)
    created = client.post("/api/jewelry-templates/", json={
        "name": "模板X",
        "items": [{"part_id": a.id, "qty_per_unit": 3}],
    }).json()
    resp = client.get(f"/api/jewelry-templates/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["items"][0]["part_name"] == "链条"


def test_get_template_not_found(client, db):
    resp = client.get("/api/jewelry-templates/9999")
    assert resp.status_code == 404


def test_update_template(client, db):
    a, b = _create_parts(db)
    created = client.post("/api/jewelry-templates/", json={
        "name": "旧名",
        "items": [{"part_id": a.id, "qty_per_unit": 1}],
    }).json()
    resp = client.patch(f"/api/jewelry-templates/{created['id']}", json={
        "name": "新名",
        "items": [
            {"part_id": a.id, "qty_per_unit": 2},
            {"part_id": b.id, "qty_per_unit": 4},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "新名"
    assert len(data["items"]) == 2


def test_delete_template(client, db):
    a, _ = _create_parts(db)
    created = client.post("/api/jewelry-templates/", json={
        "name": "待删除",
        "items": [{"part_id": a.id, "qty_per_unit": 1}],
    }).json()
    resp = client.delete(f"/api/jewelry-templates/{created['id']}")
    assert resp.status_code == 204
    resp = client.get(f"/api/jewelry-templates/{created['id']}")
    assert resp.status_code == 404


def test_apply_template_to_jewelry(client, db):
    a, b = _create_parts(db)
    created = client.post("/api/jewelry-templates/", json={
        "name": "模板",
        "items": [
            {"part_id": a.id, "qty_per_unit": 1},
            {"part_id": b.id, "qty_per_unit": 2},
        ],
    }).json()

    jewelry = create_jewelry(db, {"name": "新项链", "retail_price": 100.0, "category": "单件"})
    resp = client.post(f"/api/jewelry-templates/{created['id']}/apply/{jewelry.id}")
    assert resp.status_code == 200
    assert resp.json()["applied"] == 2

    # 验证 BOM 已设置
    bom = get_bom(db, jewelry.id)
    assert len(bom) == 2
    bom_map = {b.part_id: float(b.qty_per_unit) for b in bom}
    assert bom_map[a.id] == 1.0
    assert bom_map[b.id] == 2.0


def test_apply_template_not_found(client, db):
    jewelry = create_jewelry(db, {"name": "J", "retail_price": 10.0, "category": "单件"})
    resp = client.post(f"/api/jewelry-templates/9999/apply/{jewelry.id}")
    assert resp.status_code == 400


def test_create_template_invalid_part(client, db):
    resp = client.post("/api/jewelry-templates/", json={
        "name": "无效",
        "items": [{"part_id": "PJ-X-99999", "qty_per_unit": 1}],
    })
    assert resp.status_code == 400
