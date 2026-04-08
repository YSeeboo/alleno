from models.part import Part


def _setup_parts(db):
    """Create parent part c and child parts e, f, g."""
    parent = Part(id="PJ-X-PARENT", name="组合配件C", category="小配件")
    children = [
        Part(id="PJ-X-CHILD-E", name="子配件E", category="小配件"),
        Part(id="PJ-X-CHILD-F", name="子配件F", category="小配件"),
        Part(id="PJ-X-CHILD-G", name="子配件G", category="小配件"),
    ]
    db.add(parent)
    db.add_all(children)
    db.flush()
    return parent, children


def test_set_part_bom(client, db):
    """Create part BOM entries."""
    parent, children = _setup_parts(db)
    for child in children:
        resp = client.post(
            f"/api/parts/{parent.id}/bom",
            json={"child_part_id": child.id, "qty_per_unit": 2.0},
        )
        assert resp.status_code == 200

    resp = client.get(f"/api/parts/{parent.id}/bom")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_update_part_bom_qty(client, db):
    """Update existing part BOM qty."""
    parent, children = _setup_parts(db)
    client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[0].id, "qty_per_unit": 2.0},
    )
    # Update qty
    resp = client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[0].id, "qty_per_unit": 5.0},
    )
    assert resp.status_code == 200
    bom_list = client.get(f"/api/parts/{parent.id}/bom").json()
    assert len(bom_list) == 1
    assert bom_list[0]["qty_per_unit"] == 5.0


def test_delete_part_bom(client, db):
    """Delete a part BOM entry."""
    parent, children = _setup_parts(db)
    resp = client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[0].id, "qty_per_unit": 2.0},
    )
    bom_id = resp.json()["id"]
    del_resp = client.delete(f"/api/parts/bom/{bom_id}")
    assert del_resp.status_code == 204

    bom_list = client.get(f"/api/parts/{parent.id}/bom").json()
    assert len(bom_list) == 0


def test_self_reference_rejected(client, db):
    """Cannot add a part as its own child."""
    parent, _ = _setup_parts(db)
    resp = client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": parent.id, "qty_per_unit": 1.0},
    )
    assert resp.status_code == 400
