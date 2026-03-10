import pytest
from services.part import create_part


def test_add_stock(client, db):
    part = create_part(db, {"name": "P1"})
    resp = client.post(f"/api/inventory/part/{part.id}/add", json={"qty": 10, "reason": "initial"})
    assert resp.status_code == 200


def test_get_stock(client, db):
    part = create_part(db, {"name": "P1"})
    client.post(f"/api/inventory/part/{part.id}/add", json={"qty": 5, "reason": "入库"})
    resp = client.get(f"/api/inventory/part/{part.id}")
    assert resp.status_code == 200
    assert resp.json()["current"] == 5


def test_deduct_stock(client, db):
    part = create_part(db, {"name": "P1"})
    client.post(f"/api/inventory/part/{part.id}/add", json={"qty": 10, "reason": "入库"})
    resp = client.post(f"/api/inventory/part/{part.id}/deduct", json={"qty": 3, "reason": "出库"})
    assert resp.status_code == 200
    assert resp.json()["current"] == 7


def test_deduct_insufficient(client, db):
    part = create_part(db, {"name": "P1"})
    resp = client.post(f"/api/inventory/part/{part.id}/deduct", json={"qty": 5, "reason": "出库"})
    assert resp.status_code == 400


def test_get_stock_log(client, db):
    part = create_part(db, {"name": "P1"})
    client.post(f"/api/inventory/part/{part.id}/add", json={"qty": 10, "reason": "入库"})
    client.post(f"/api/inventory/part/{part.id}/deduct", json={"qty": 3, "reason": "出库"})
    resp = client.get(f"/api/inventory/part/{part.id}/log")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
