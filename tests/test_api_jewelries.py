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


def _put_bom(client, jewelry_id, part_id, qty):
    return client.put(f"/api/bom/{jewelry_id}/{part_id}", json={"qty_per_unit": qty})


def _create_part(client, name="珍珠", category="小配件"):
    return client.post("/api/parts/", json={"name": name, "category": category, "unit": "颗"}).json()


def test_copy_jewelry_basic(client):
    src = client.post("/api/jewelries/", json={
        "name": "源套装", "category": "套装", "color": "金", "unit": "套",
        "retail_price": 200.0, "wholesale_price": 120.0,
    }).json()
    p = _create_part(client)
    _put_bom(client, src["id"], p["id"], 1.5)

    resp = client.post(f"/api/jewelries/{src['id']}/copy", json={"name": "源套装-副本"})
    assert resp.status_code == 201
    new = resp.json()
    assert new["id"] != src["id"]
    assert new["id"].startswith("SP-SET-")
    assert new["name"] == "源套装-副本"
    assert new["category"] == "套装"
    assert new["color"] == "金"
    assert new["retail_price"] == 200.0

    bom_resp = client.get(f"/api/bom/{new['id']}")
    assert bom_resp.status_code == 200
    bom_rows = bom_resp.json()
    assert len(bom_rows) == 1
    assert bom_rows[0]["part_id"] == p["id"]
    assert float(bom_rows[0]["qty_per_unit"]) == 1.5


def test_copy_jewelry_new_stock_is_zero(client):
    src = client.post("/api/jewelries/", json={"name": "S", "category": "单件"}).json()
    # Give source some stock so the test actually verifies inventory is NOT cloned.
    add = client.post(f"/api/inventory/jewelry/{src['id']}/add", json={"qty": 5, "reason": "test seed"})
    assert add.status_code == 200, add.text

    resp = client.post(f"/api/jewelries/{src['id']}/copy", json={"name": "S-副本"})
    new_id = resp.json()["id"]

    # Confirm source actually has stock now
    src_stock = client.get(f"/api/inventory/jewelry/{src['id']}")
    assert src_stock.json()["current"] == 5

    # The new jewelry must NOT have inherited any stock
    stock_resp = client.get(f"/api/inventory/jewelry/{new_id}")
    assert stock_resp.status_code == 200
    assert stock_resp.json()["current"] == 0


def test_copy_jewelry_source_not_found(client):
    resp = client.post("/api/jewelries/SP-PCS-99999/copy", json={"name": "X"})
    assert resp.status_code == 404


def test_copy_jewelry_missing_name(client):
    src = client.post("/api/jewelries/", json={"name": "S", "category": "单件"}).json()
    resp = client.post(f"/api/jewelries/{src['id']}/copy", json={})
    assert resp.status_code == 422


def test_copy_jewelry_override_fields(client):
    src = client.post("/api/jewelries/", json={
        "name": "S", "category": "单件", "color": "金", "retail_price": 50.0,
    }).json()
    resp = client.post(f"/api/jewelries/{src['id']}/copy", json={
        "name": "S-副本", "color": "银", "retail_price": 80.0,
    })
    new = resp.json()
    assert new["name"] == "S-副本"
    assert new["color"] == "银"
    assert new["retail_price"] == 80.0


def test_copy_jewelry_category_in_payload_ignored(client):
    src = client.post("/api/jewelries/", json={"name": "S", "category": "套装"}).json()
    resp = client.post(f"/api/jewelries/{src['id']}/copy", json={
        "name": "S-副本",
        "category": "单件",  # not declared in JewelryCopyRequest; Pydantic drops it
    })
    assert resp.status_code == 201
    new = resp.json()
    assert new["category"] == "套装"
    assert new["id"].startswith("SP-SET-")


def test_jewelry_response_has_style_group_default_null(client):
    client.post("/api/jewelries/", json={"name": "GroupProbe", "category": "套装"})
    resp = client.get("/api/jewelries/")
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["name"] == "GroupProbe")
    assert "style_group" in row
    assert row["style_group"] is None


def test_add_sibling_endpoint(client):
    base = client.post("/api/jewelries/", json={"name": "套链", "category": "套装", "retail_price": 168}).json()
    resp = client.post(f"/api/jewelries/{base['id']}/siblings", json={"color": "白K"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == f"{base['id']}-A"
    assert data["style_group"] == base["id"]
    assert data["color"] == "白K"
    assert data["name"] == "套链"


def test_add_sibling_endpoint_unknown_base_404(client):
    resp = client.post("/api/jewelries/SP-SET-99999/siblings", json={"color": "白K"})
    assert resp.status_code == 404
