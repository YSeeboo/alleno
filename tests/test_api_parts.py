import pytest

def test_create_part(client):
    resp = client.post("/api/parts/", json={"name": "Ring Base", "category": "吊坠"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("PJ-DZ-")
    assert data["name"] == "Ring Base"
    assert data["category"] == "吊坠"

def test_create_part_invalid_category(client):
    resp = client.post("/api/parts/", json={"name": "X", "category": "invalid"})
    assert resp.status_code == 400

def test_create_part_missing_name(client):
    resp = client.post("/api/parts/", json={"category": "吊坠"})
    assert resp.status_code == 422

def test_create_part_missing_category(client):
    resp = client.post("/api/parts/", json={"name": "X"})
    assert resp.status_code == 422

def test_list_parts(client):
    client.post("/api/parts/", json={"name": "A", "category": "吊坠"})
    client.post("/api/parts/", json={"name": "B", "category": "链条"})
    resp = client.get("/api/parts/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

def test_list_parts_filter(client):
    client.post("/api/parts/", json={"name": "A", "category": "吊坠"})
    client.post("/api/parts/", json={"name": "B", "category": "链条"})
    resp = client.get("/api/parts/?category=吊坠")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "A"


def test_list_parts_filter_name(client):
    client.post("/api/parts/", json={"name": "铜扣环", "category": "吊坠"})
    client.post("/api/parts/", json={"name": "银链条", "category": "链条"})
    resp = client.get("/api/parts/?name=铜")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "铜扣环"


def test_list_parts_filter_name_no_match(client):
    client.post("/api/parts/", json={"name": "铜扣环", "category": "吊坠"})
    resp = client.get("/api/parts/?name=金")
    assert resp.status_code == 200
    assert resp.json() == []

def test_get_part(client):
    created = client.post("/api/parts/", json={"name": "X", "category": "吊坠"}).json()
    resp = client.get(f"/api/parts/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "X"

def test_get_part_not_found(client):
    resp = client.get("/api/parts/PJ-DZ-99999")
    assert resp.status_code == 404

def test_update_part(client):
    created = client.post("/api/parts/", json={"name": "Old", "category": "吊坠"}).json()
    resp = client.patch(f"/api/parts/{created['id']}", json={"name": "New"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"

def test_update_part_not_found(client):
    resp = client.patch("/api/parts/PJ-DZ-99999", json={"name": "X"})
    assert resp.status_code == 404

def test_delete_part(client):
    created = client.post("/api/parts/", json={"name": "ToDelete", "category": "吊坠"}).json()
    resp = client.delete(f"/api/parts/{created['id']}")
    assert resp.status_code == 204
    resp2 = client.get(f"/api/parts/{created['id']}")
    assert resp2.status_code == 404

def test_delete_part_not_found(client):
    resp = client.delete("/api/parts/PJ-DZ-99999")
    assert resp.status_code == 404
