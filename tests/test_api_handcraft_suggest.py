from services.bom import set_bom
from services.jewelry import create_jewelry
from services.part import create_part, create_part_variant


def _setup_two_jewelries_sharing_part(db):
    """Two jewelries that share PJ-X-* small part and each have their own
    PJ-DZ-* medium part. Returns ids: (j1, j2, shared_x, dz1, dz2)."""
    shared_x = create_part(db, {"name": "耳塞 4mm", "category": "小配件"})
    dz1 = create_part(db, {"name": "小圆吊坠", "category": "吊坠"})
    dz2 = create_part(db, {"name": "心形吊坠", "category": "吊坠"})
    j1 = create_jewelry(db, {"name": "蝴蝶耳钉", "category": "单件"})
    j2 = create_jewelry(db, {"name": "心形耳钉", "category": "单件"})
    set_bom(db, j1.id, shared_x.id, qty_per_unit=1)
    set_bom(db, j1.id, dz1.id, qty_per_unit=1)
    set_bom(db, j2.id, shared_x.id, qty_per_unit=1)
    set_bom(db, j2.id, dz2.id, qty_per_unit=1)
    db.flush()
    return j1.id, j2.id, shared_x.id, dz1.id, dz2.id


def test_suggest_parts_cross_jewelry_aggregation(client, db):
    j1, j2, shared_x, dz1, dz2 = _setup_two_jewelries_sharing_part(db)

    resp = client.post(
        "/api/handcraft/suggest-parts",
        json={"jewelry_items": [
            {"jewelry_id": j1, "qty": 1000},
            {"jewelry_id": j2, "qty": 500},
        ]},
    )
    assert resp.status_code == 200
    rows = {r["part_id"]: r for r in resp.json()}

    # PJ-X 小件: 1000+500=1500, ratio=2% → 30, floor=50 → buffer=50
    assert rows[shared_x]["theoretical_qty"] == 1500
    assert rows[shared_x]["size_tier"] == "small"
    assert rows[shared_x]["buffer"] == 50
    assert rows[shared_x]["suggested_qty"] == 1550

    # PJ-DZ 中件: 1000, ratio=1% → 10, floor=15 → buffer=15
    assert rows[dz1]["size_tier"] == "medium"
    assert rows[dz1]["buffer"] == 15
    assert rows[dz1]["suggested_qty"] == 1015

    # PJ-DZ 中件: 500, ratio=1% → 5, floor=15 → buffer=15
    assert rows[dz2]["buffer"] == 15
    assert rows[dz2]["suggested_qty"] == 515


def test_suggest_parts_ratio_wins_at_large_qty(client, db):
    j1, _, shared_x, _, _ = _setup_two_jewelries_sharing_part(db)
    resp = client.post(
        "/api/handcraft/suggest-parts",
        json={"jewelry_items": [{"jewelry_id": j1, "qty": 8000}]},
    )
    assert resp.status_code == 200
    rows = {r["part_id"]: r for r in resp.json()}
    # 8000 × 2% = 160 > floor 50
    assert rows[shared_x]["buffer"] == 160
    assert rows[shared_x]["suggested_qty"] == 8160


def test_suggest_parts_floor_wins_at_small_qty(client, db):
    j1, _, shared_x, dz1, _ = _setup_two_jewelries_sharing_part(db)
    resp = client.post(
        "/api/handcraft/suggest-parts",
        json={"jewelry_items": [{"jewelry_id": j1, "qty": 100}]},
    )
    assert resp.status_code == 200
    rows = {r["part_id"]: r for r in resp.json()}
    # 100 × 2% = 2 < floor 50
    assert rows[shared_x]["buffer"] == 50
    assert rows[shared_x]["suggested_qty"] == 150
    # 100 × 1% = 1 < floor 15
    assert rows[dz1]["buffer"] == 15
    assert rows[dz1]["suggested_qty"] == 115


def test_suggest_parts_jewelry_without_bom_returns_empty(client, db):
    j = create_jewelry(db, {"name": "现货款", "category": "单件"})
    db.flush()
    resp = client.post(
        "/api/handcraft/suggest-parts",
        json={"jewelry_items": [{"jewelry_id": j.id, "qty": 100}]},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_suggest_parts_unknown_jewelry_id_rejected(client):
    resp = client.post(
        "/api/handcraft/suggest-parts",
        json={"jewelry_items": [{"jewelry_id": "SP-9999", "qty": 100}]},
    )
    assert resp.status_code == 400


def test_suggest_parts_duplicate_jewelry_id_rejected(client, db):
    j1, _, _, _, _ = _setup_two_jewelries_sharing_part(db)
    resp = client.post(
        "/api/handcraft/suggest-parts",
        json={"jewelry_items": [
            {"jewelry_id": j1, "qty": 100},
            {"jewelry_id": j1, "qty": 200},
        ]},
    )
    assert resp.status_code == 400


def test_suggest_parts_empty_request_rejected(client):
    resp = client.post("/api/handcraft/suggest-parts", json={"jewelry_items": []})
    assert resp.status_code == 422


def test_suggest_parts_response_sorted(client, db):
    j1, _, _, _, _ = _setup_two_jewelries_sharing_part(db)
    resp = client.post(
        "/api/handcraft/suggest-parts",
        json={"jewelry_items": [{"jewelry_id": j1, "qty": 100}]},
    )
    rows = resp.json()
    # PJ-DZ-* should come before PJ-X-* (alphabetical category prefix)
    prefixes = ["-".join(r["part_id"].split("-")[:2]) for r in rows]
    assert prefixes == sorted(prefixes)


def test_suggest_parts_uses_part_size_tier_field(client, db):
    """A 小配件 part with size_tier overridden to medium should use the medium rule."""
    j = create_jewelry(db, {"name": "J", "category": "单件"})
    big_x = create_part(db, {"name": "大号挂钩", "category": "小配件", "size_tier": "medium"})
    set_bom(db, j.id, big_x.id, qty_per_unit=1)
    db.flush()

    resp = client.post(
        "/api/handcraft/suggest-parts",
        json={"jewelry_items": [{"jewelry_id": j.id, "qty": 1000}]},
    )
    assert resp.status_code == 200
    row = resp.json()[0]
    assert row["size_tier"] == "medium"
    # medium rule: 1000 × 1% = 10, floor=15 → buffer=15
    assert row["buffer"] == 15


def test_suggest_parts_fractional_bom_qty_no_float_drift(client, db):
    """Regression: 0.3 × 1000 must be exactly 300, not 300.00000000000006.

    Without Decimal arithmetic the float drift would push theoretical_qty into
    301-territory after ceil, breaking buffer math for chains/lengths.
    """
    j = create_jewelry(db, {"name": "长链", "category": "单件"})
    chain = create_part(db, {"name": "链条 0.3m", "category": "链条"})
    set_bom(db, j.id, chain.id, qty_per_unit=0.3)
    db.flush()
    resp = client.post(
        "/api/handcraft/suggest-parts",
        json={"jewelry_items": [{"jewelry_id": j.id, "qty": 1000}]},
    )
    assert resp.status_code == 200
    row = resp.json()[0]
    assert row["theoretical_qty"] == 300.0
    # ceil(300) + max(15, ceil(300 × 1%)) = 300 + 15 = 315
    assert row["suggested_qty"] == 315


def test_suggest_parts_variant_in_bom_inherits_root_size_tier(client, db):
    """Real BOMs reference variant IDs (PJ-LT-00001-G-45cm), not root.

    Variants must take buffer rule from their own size_tier field — which
    is inherited from root at creation and synced when root is updated.
    """
    j = create_jewelry(db, {"name": "金链耳钉", "category": "单件"})
    root = create_part(db, {"name": "链条", "category": "链条"})
    variant = create_part_variant(db, root.id, color_code="G", spec="45cm")
    set_bom(db, j.id, variant.id, qty_per_unit=1)
    db.flush()
    resp = client.post(
        "/api/handcraft/suggest-parts",
        json={"jewelry_items": [{"jewelry_id": j.id, "qty": 100}]},
    )
    assert resp.status_code == 200
    row = resp.json()[0]
    assert row["part_id"] == variant.id
    assert row["size_tier"] == "medium"  # inherited from PJ-LT root
