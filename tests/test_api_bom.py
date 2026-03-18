import pytest
from services.part import create_part
from services.jewelry import create_jewelry


def test_upsert_bom(client, db):
    part = create_part(db, {"name": "P1", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "J1", "category": "单件"})
    resp = client.put(f"/api/bom/{jewelry.id}/{part.id}", json={"qty_per_unit": 2})
    assert resp.status_code == 200
    assert resp.json()["qty_per_unit"] == 2


def test_upsert_bom_update(client, db):
    part = create_part(db, {"name": "P1", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "J1", "category": "单件"})
    client.put(f"/api/bom/{jewelry.id}/{part.id}", json={"qty_per_unit": 2})
    resp = client.put(f"/api/bom/{jewelry.id}/{part.id}", json={"qty_per_unit": 5})
    assert resp.status_code == 200
    assert resp.json()["qty_per_unit"] == 5


def test_upsert_bom_invalid_jewelry(client, db):
    part = create_part(db, {"name": "P1", "category": "小配件"})
    resp = client.put(f"/api/bom/SP-9999/{part.id}", json={"qty_per_unit": 2})
    assert resp.status_code == 400


def test_get_bom(client, db):
    part1 = create_part(db, {"name": "P1", "category": "小配件"})
    part2 = create_part(db, {"name": "P2", "category": "吊坠"})
    jewelry = create_jewelry(db, {"name": "J1", "category": "单件"})
    client.put(f"/api/bom/{jewelry.id}/{part1.id}", json={"qty_per_unit": 1})
    client.put(f"/api/bom/{jewelry.id}/{part2.id}", json={"qty_per_unit": 3})
    resp = client.get(f"/api/bom/{jewelry.id}")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_bom_empty(client, db):
    jewelry = create_jewelry(db, {"name": "J1", "category": "单件"})
    resp = client.get(f"/api/bom/{jewelry.id}")
    assert resp.status_code == 200
    assert resp.json() == []


def test_delete_bom(client, db):
    part = create_part(db, {"name": "P1", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "J1", "category": "单件"})
    client.put(f"/api/bom/{jewelry.id}/{part.id}", json={"qty_per_unit": 2})
    resp = client.delete(f"/api/bom/{jewelry.id}/{part.id}")
    assert resp.status_code == 204


def test_delete_bom_not_found(client, db):
    resp = client.delete("/api/bom/SP-9999/PJ-9999")
    assert resp.status_code == 404
