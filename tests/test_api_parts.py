import pytest

def test_create_part(client):
    resp = client.post("/api/parts/", json={"name": "Ring Base", "category": "rings"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("PJ-")
    assert data["name"] == "Ring Base"
    assert data["category"] == "rings"

def test_create_part_missing_name(client):
    resp = client.post("/api/parts/", json={})
    assert resp.status_code == 422

def test_list_parts(client):
    client.post("/api/parts/", json={"name": "A", "category": "rings"})
    client.post("/api/parts/", json={"name": "B", "category": "chains"})
    resp = client.get("/api/parts/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

def test_list_parts_filter(client):
    client.post("/api/parts/", json={"name": "A", "category": "rings"})
    client.post("/api/parts/", json={"name": "B", "category": "chains"})
    resp = client.get("/api/parts/?category=rings")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "A"

def test_get_part(client):
    created = client.post("/api/parts/", json={"name": "X"}).json()
    resp = client.get(f"/api/parts/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "X"

def test_get_part_not_found(client):
    resp = client.get("/api/parts/PJ-9999")
    assert resp.status_code == 404

def test_update_part(client):
    created = client.post("/api/parts/", json={"name": "Old"}).json()
    resp = client.patch(f"/api/parts/{created['id']}", json={"name": "New"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"

def test_update_part_not_found(client):
    resp = client.patch("/api/parts/PJ-9999", json={"name": "X"})
    assert resp.status_code == 404

def test_delete_part(client):
    created = client.post("/api/parts/", json={"name": "ToDelete"}).json()
    resp = client.delete(f"/api/parts/{created['id']}")
    assert resp.status_code == 204
    resp2 = client.get(f"/api/parts/{created['id']}")
    assert resp2.status_code == 404

def test_delete_part_not_found(client):
    resp = client.delete("/api/parts/PJ-9999")
    assert resp.status_code == 404
