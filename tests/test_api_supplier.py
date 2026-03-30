def test_create_supplier(client, db):
    resp = client.post("/api/suppliers/", json={"name": "电镀厂A", "type": "plating"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "电镀厂A"
    assert data["type"] == "plating"
    assert "id" in data
    assert "created_at" in data


def test_create_supplier_strips_whitespace(client, db):
    resp = client.post("/api/suppliers/", json={"name": "  电镀厂B  ", "type": "plating"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "电镀厂B"


def test_create_supplier_blank_name_rejected(client, db):
    resp = client.post("/api/suppliers/", json={"name": "   ", "type": "plating"})
    assert resp.status_code == 422


def test_create_supplier_invalid_type_rejected(client, db):
    resp = client.post("/api/suppliers/", json={"name": "Foo", "type": "invalid"})
    assert resp.status_code == 422


def test_create_supplier_duplicate_same_type_rejected(client, db):
    client.post("/api/suppliers/", json={"name": "厂X", "type": "plating"})
    resp = client.post("/api/suppliers/", json={"name": "厂X", "type": "plating"})
    assert resp.status_code == 400


def test_create_supplier_same_name_different_type_allowed(client, db):
    resp1 = client.post("/api/suppliers/", json={"name": "商家Y", "type": "plating"})
    resp2 = client.post("/api/suppliers/", json={"name": "商家Y", "type": "handcraft"})
    assert resp1.status_code == 201
    assert resp2.status_code == 201


def test_list_suppliers(client, db):
    client.post("/api/suppliers/", json={"name": "A", "type": "plating"})
    client.post("/api/suppliers/", json={"name": "B", "type": "handcraft"})
    client.post("/api/suppliers/", json={"name": "C", "type": "plating"})

    resp = client.get("/api/suppliers/")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_list_suppliers_filter_by_type(client, db):
    client.post("/api/suppliers/", json={"name": "A", "type": "plating"})
    client.post("/api/suppliers/", json={"name": "B", "type": "handcraft"})

    resp = client.get("/api/suppliers/?type=plating")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["type"] == "plating"


def test_update_supplier(client, db):
    create_resp = client.post("/api/suppliers/", json={"name": "OldName", "type": "parts"})
    sid = create_resp.json()["id"]

    resp = client.patch(f"/api/suppliers/{sid}", json={"name": "NewName"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "NewName"
    assert resp.json()["type"] == "parts"


def test_update_supplier_duplicate_rejected(client, db):
    client.post("/api/suppliers/", json={"name": "A", "type": "plating"})
    create_resp = client.post("/api/suppliers/", json={"name": "B", "type": "plating"})
    sid = create_resp.json()["id"]

    resp = client.patch(f"/api/suppliers/{sid}", json={"name": "A"})
    assert resp.status_code == 400


def test_update_supplier_not_found(client, db):
    resp = client.patch("/api/suppliers/99999", json={"name": "X"})
    assert resp.status_code == 400


def test_delete_supplier(client, db):
    create_resp = client.post("/api/suppliers/", json={"name": "ToDelete", "type": "customer"})
    sid = create_resp.json()["id"]

    resp = client.delete(f"/api/suppliers/{sid}")
    assert resp.status_code == 204

    list_resp = client.get("/api/suppliers/?type=customer")
    assert len(list_resp.json()) == 0


def test_delete_supplier_not_found(client, db):
    resp = client.delete("/api/suppliers/99999")
    assert resp.status_code == 400


def test_all_valid_types(client, db):
    for t in ["plating", "handcraft", "parts", "customer"]:
        resp = client.post("/api/suppliers/", json={"name": f"test_{t}", "type": t})
        assert resp.status_code == 201, f"Failed for type {t}"
