import pytest
from services.jewelry import create_jewelry, update_jewelry
from services.part import create_part, update_part_cost
from services.bom import set_bom


def _make_jewelry_with_cost(db):
    p1 = create_part(db, {"name": "珠", "category": "小配件"})
    p2 = create_part(db, {"name": "链", "category": "链条"})
    update_part_cost(db, p1.id, "purchase_cost", 0.05)
    update_part_cost(db, p2.id, "purchase_cost", 2.0)
    j = create_jewelry(db, {"name": "项链A", "category": "单件"})
    set_bom(db, j.id, p1.id, 10)
    set_bom(db, j.id, p2.id, 1)
    update_jewelry(db, j.id, {"handcraft_cost": 1.0})
    return j


def test_get_jewelry_includes_cost(client, db):
    j = _make_jewelry_with_cost(db)
    resp = client.get(f"/api/jewelries/{j.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert pytest.approx(data["material_cost"], abs=0.001) == 2.5
    assert pytest.approx(data["handcraft_cost"], abs=0.001) == 1.0
    assert pytest.approx(data["total_cost"], abs=0.001) == 3.5
    assert data["has_incomplete_cost"] is False


def test_list_jewelries_includes_cost(client, db):
    j = _make_jewelry_with_cost(db)
    resp = client.get("/api/jewelries/")
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["id"] == j.id)
    assert pytest.approx(row["total_cost"], abs=0.001) == 3.5
    assert row["has_incomplete_cost"] is False


def test_get_jewelry_incomplete_cost_flag(client, db):
    p = create_part(db, {"name": "无价件", "category": "小配件"})  # unit_cost None
    j = create_jewelry(db, {"name": "X", "category": "单件"})
    set_bom(db, j.id, p.id, 1)
    resp = client.get(f"/api/jewelries/{j.id}")
    data = resp.json()
    assert data["has_incomplete_cost"] is True
    assert pytest.approx(data["material_cost"], abs=0.001) == 0.0


def test_get_jewelry_no_bom_incomplete(client, db):
    j = create_jewelry(db, {"name": "裸件", "category": "单件"})
    update_jewelry(db, j.id, {"handcraft_cost": 5.0})
    resp = client.get(f"/api/jewelries/{j.id}")
    data = resp.json()
    assert data["has_incomplete_cost"] is True
    assert pytest.approx(data["material_cost"], abs=0.001) == 0.0
    assert pytest.approx(data["total_cost"], abs=0.001) == 5.0
