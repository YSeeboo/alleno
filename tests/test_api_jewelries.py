import pytest


def test_create_jewelry(client):
    resp = client.post("/api/jewelries/", json={"name": "Ring", "category": "单件"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("SP-PCS-")
    assert data["name"] == "Ring"


def test_create_jewelry_invalid_category(client):
    resp = client.post("/api/jewelries/", json={"name": "X", "category": "invalid"})
    assert resp.status_code == 400


def test_create_jewelry_missing_name(client):
    resp = client.post("/api/jewelries/", json={"retail_price": 25.0, "category": "单件"})
    assert resp.status_code == 422


def test_create_jewelry_missing_category(client):
    resp = client.post("/api/jewelries/", json={"name": "X"})
    assert resp.status_code == 422


def test_list_jewelries(client):
    client.post("/api/jewelries/", json={"name": "Necklace", "category": "单件"})
    client.post("/api/jewelries/", json={"name": "Bracelet", "category": "套装"})
    resp = client.get("/api/jewelries/")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2


def test_list_jewelries_filtered(client):
    client.post("/api/jewelries/", json={"name": "Gold Ring", "status": "active", "category": "单件"})
    client.post("/api/jewelries/", json={"name": "Silver Ring", "status": "inactive", "category": "单件"})
    resp = client.get("/api/jewelries/?status=active&category=单件")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    for item in data:
        assert item["status"] == "active"
        assert item["category"] == "单件"


def test_get_jewelry(client):
    create_resp = client.post("/api/jewelries/", json={"name": "Earrings", "category": "单对"})
    jewelry_id = create_resp.json()["id"]
    resp = client.get(f"/api/jewelries/{jewelry_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == jewelry_id
    assert data["name"] == "Earrings"


def test_get_jewelry_not_found(client):
    resp = client.get("/api/jewelries/SP-PCS-99999")
    assert resp.status_code == 404


def test_update_jewelry(client):
    create_resp = client.post("/api/jewelries/", json={"name": "Pendant", "retail_price": 50.0, "category": "单件"})
    jewelry_id = create_resp.json()["id"]
    resp = client.patch(f"/api/jewelries/{jewelry_id}", json={"name": "Gold Pendant", "retail_price": 60.0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Gold Pendant"
    assert data["retail_price"] == 60.0


def test_update_jewelry_not_found(client):
    resp = client.patch("/api/jewelries/SP-PCS-99999", json={"name": "Ghost"})
    assert resp.status_code == 404


def test_delete_jewelry(client):
    create_resp = client.post("/api/jewelries/", json={"name": "Anklet", "category": "单件"})
    jewelry_id = create_resp.json()["id"]
    resp = client.delete(f"/api/jewelries/{jewelry_id}")
    assert resp.status_code == 204
    # Verify it's gone
    get_resp = client.get(f"/api/jewelries/{jewelry_id}")
    assert get_resp.status_code == 404


def test_delete_jewelry_not_found(client):
    resp = client.delete("/api/jewelries/SP-PCS-99999")
    assert resp.status_code == 404


def test_set_status(client):
    create_resp = client.post("/api/jewelries/", json={"name": "Brooch", "status": "active", "category": "单件"})
    jewelry_id = create_resp.json()["id"]
    resp = client.patch(f"/api/jewelries/{jewelry_id}/status", json={"status": "inactive"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "inactive"
