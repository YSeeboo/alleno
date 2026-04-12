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


# ──────────────────────────────────────────────────────────────
# Auto unit_cost recalculation
# ──────────────────────────────────────────────────────────────

def test_recalc_unit_cost_on_bom_change(client, db):
    """Setting part BOM auto-recalculates parent unit_cost."""
    parent, children = _setup_parts(db)
    # Set child costs
    children[0].unit_cost = 10.0
    children[1].unit_cost = 20.0
    children[2].unit_cost = 5.0
    db.flush()

    # Add BOM: e*2 + f*1 + g*3
    client.post(f"/api/parts/{parent.id}/bom", json={"child_part_id": children[0].id, "qty_per_unit": 2.0})
    client.post(f"/api/parts/{parent.id}/bom", json={"child_part_id": children[1].id, "qty_per_unit": 1.0})
    client.post(f"/api/parts/{parent.id}/bom", json={"child_part_id": children[2].id, "qty_per_unit": 3.0})

    db.refresh(parent)
    # Expected: 10*2 + 20*1 + 5*3 = 55, no assembly_cost yet
    assert float(parent.unit_cost) == 55.0


def test_recalc_includes_assembly_cost(client, db):
    """unit_cost includes assembly_cost."""
    parent, children = _setup_parts(db)
    children[0].unit_cost = 10.0
    parent.assembly_cost = 8.0
    db.flush()

    client.post(f"/api/parts/{parent.id}/bom", json={"child_part_id": children[0].id, "qty_per_unit": 2.0})

    db.refresh(parent)
    # Expected: 10*2 + 8 = 28
    assert float(parent.unit_cost) == 28.0


def test_recalc_on_child_cost_change(client, db):
    """Updating child part unit_cost triggers parent recalc."""
    parent, children = _setup_parts(db)
    children[0].unit_cost = 10.0
    db.flush()

    client.post(f"/api/parts/{parent.id}/bom", json={"child_part_id": children[0].id, "qty_per_unit": 2.0})
    db.refresh(parent)
    assert float(parent.unit_cost) == 20.0

    # Update child cost via cost update endpoint
    from services.part import update_part_cost
    update_part_cost(db, children[0].id, "purchase_cost", 15.0)
    db.refresh(parent)
    # Child unit_cost is now 15 (purchase_cost only), parent = 15*2 = 30
    assert float(parent.unit_cost) == 30.0


def test_recalc_on_bom_delete(client, db):
    """Deleting a BOM row recalculates parent unit_cost."""
    parent, children = _setup_parts(db)
    children[0].unit_cost = 10.0
    children[1].unit_cost = 20.0
    db.flush()

    resp1 = client.post(f"/api/parts/{parent.id}/bom", json={"child_part_id": children[0].id, "qty_per_unit": 1.0})
    resp2 = client.post(f"/api/parts/{parent.id}/bom", json={"child_part_id": children[1].id, "qty_per_unit": 1.0})
    db.refresh(parent)
    assert float(parent.unit_cost) == 30.0

    # Delete one BOM row
    bom_id = resp2.json()["id"]
    client.delete(f"/api/parts/bom/{bom_id}")
    db.refresh(parent)
    assert float(parent.unit_cost) == 10.0


def test_recalc_on_assembly_cost_change(client, db):
    """Updating assembly_cost via PATCH triggers recalc."""
    parent, children = _setup_parts(db)
    children[0].unit_cost = 10.0
    db.flush()

    client.post(f"/api/parts/{parent.id}/bom", json={"child_part_id": children[0].id, "qty_per_unit": 2.0})
    db.refresh(parent)
    assert float(parent.unit_cost) == 20.0

    # Update assembly_cost
    resp = client.patch(f"/api/parts/{parent.id}", json={"assembly_cost": 5.0})
    assert resp.status_code == 200
    db.refresh(parent)
    assert float(parent.unit_cost) == 25.0


def test_is_composite_flag_set_on_bom_create(client, db):
    """is_composite should be True after adding a BOM child."""
    parent, children = _setup_parts(db)
    assert parent.is_composite is False
    client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[0].id, "qty_per_unit": 2.0},
    )
    db.refresh(parent)
    assert parent.is_composite is True


def test_is_composite_flag_cleared_on_last_bom_delete(client, db):
    """is_composite should revert to False when all BOM children are removed."""
    parent, children = _setup_parts(db)
    resp = client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[0].id, "qty_per_unit": 2.0},
    )
    bom_id = resp.json()["id"]
    db.refresh(parent)
    assert parent.is_composite is True
    client.delete(f"/api/parts/bom/{bom_id}")
    db.refresh(parent)
    assert parent.is_composite is False


def test_is_composite_stays_true_when_one_bom_deleted(client, db):
    """is_composite should stay True if other BOM children remain."""
    parent, children = _setup_parts(db)
    resp1 = client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[0].id, "qty_per_unit": 2.0},
    )
    client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[1].id, "qty_per_unit": 1.0},
    )
    bom_id = resp1.json()["id"]
    client.delete(f"/api/parts/bom/{bom_id}")
    db.refresh(parent)
    assert parent.is_composite is True


def test_assembly_cost_synced_from_handcraft_receipt(client, db):
    """Handcraft receipt price syncs to Part.assembly_cost and triggers recalc."""
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem

    parent, children = _setup_parts(db)
    children[0].unit_cost = 10.0
    db.flush()

    from services.part_bom import set_part_bom
    set_part_bom(db, parent.id, children[0].id, 2.0)
    db.flush()

    # Create processing handcraft order
    hc = HandcraftOrder(id="HC-COSTSYNC1", supplier_name="手工商C", status="processing")
    db.add(hc)
    db.flush()

    hp = HandcraftPartItem(handcraft_order_id=hc.id, part_id=children[0].id, qty=20, status="制作中")
    hj = HandcraftJewelryItem(handcraft_order_id=hc.id, part_id=parent.id, qty=10, status="制作中")
    db.add_all([hp, hj])
    db.flush()

    # Create receipt with price=3.0 per unit
    resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "手工商C",
        "items": [{
            "handcraft_jewelry_item_id": hj.id,
            "qty": 10,
            "price": 3.0,
        }],
    })
    assert resp.status_code == 201

    db.refresh(parent)
    # assembly_cost should be 3.0, unit_cost = 10*2 + 3 = 23
    assert float(parent.assembly_cost) == 3.0
    assert float(parent.unit_cost) == 23.0


def test_part_response_includes_is_composite(client, db):
    """GET /api/parts/{id} should include is_composite field."""
    parent, children = _setup_parts(db)
    resp = client.get(f"/api/parts/{parent.id}")
    assert resp.status_code == 200
    assert resp.json()["is_composite"] is False

    client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[0].id, "qty_per_unit": 2.0},
    )
    resp = client.get(f"/api/parts/{parent.id}")
    assert resp.json()["is_composite"] is True


def test_list_parts_includes_is_composite(client, db):
    """GET /api/parts/ should include is_composite for each part."""
    parent, children = _setup_parts(db)
    client.post(
        f"/api/parts/{parent.id}/bom",
        json={"child_part_id": children[0].id, "qty_per_unit": 2.0},
    )
    resp = client.get("/api/parts/")
    assert resp.status_code == 200
    parts_map = {p["id"]: p for p in resp.json()}
    assert parts_map[parent.id]["is_composite"] is True
    assert parts_map[children[0].id]["is_composite"] is False
