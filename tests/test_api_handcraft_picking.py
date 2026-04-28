"""API + service tests for /api/handcraft/{id}/picking/... endpoints.

Note: these tests use the API client to hit FastAPI; service-layer logic is
exercised through the routes. The test DB fixture in conftest.py truncates
all tables between tests."""

from decimal import Decimal

from models.handcraft_order import (
    HandcraftOrder,
    HandcraftPartItem,
    HandcraftPickingRecord,
)
from models.inventory_log import InventoryLog
from models.part import Part
from models.part_bom import PartBom


def _add_atomic_part(db, pid="PJ-X-00001", name="珠子", tier="small"):
    db.add(Part(id=pid, name=name, category="吊坠", size_tier=tier))


def _add_inventory(db, pid, qty, reason="期初"):
    db.add(InventoryLog(
        item_type="part", item_id=pid, change_qty=Decimal(str(qty)), reason=reason,
    ))


def _setup_atomic(db):
    """1 atomic part with stock, 1 handcraft order with 1 part_item."""
    _add_atomic_part(db, "PJ-X-00001", "珠子A", "small")
    _add_inventory(db, "PJ-X-00001", 50)
    db.add(HandcraftOrder(id="HC-TEST-1", supplier_name="商家A", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-TEST-1",
        part_id="PJ-X-00001",
        qty=Decimal("10"),
        bom_qty=Decimal("8"),
    ))
    db.flush()


def test_get_picking_order_not_found(client, db):
    resp = client.get("/api/handcraft/HC-NOPE/picking")
    assert resp.status_code == 400
    assert "HC-NOPE" in resp.json()["detail"]


def test_get_picking_empty_order(client, db):
    db.add(HandcraftOrder(id="HC-EMPTY", supplier_name="商家", status="pending"))
    db.flush()
    resp = client.get("/api/handcraft/HC-EMPTY/picking")
    assert resp.status_code == 200
    body = resp.json()
    assert body["handcraft_order_id"] == "HC-EMPTY"
    assert body["supplier_name"] == "商家"
    assert body["status"] == "pending"
    assert body["groups"] == []
    assert body["progress"] == {"total": 0, "picked": 0}


def test_get_picking_atomic_single_item(client, db):
    _setup_atomic(db)
    resp = client.get("/api/handcraft/HC-TEST-1/picking")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert len(body["groups"]) == 1
    g = body["groups"][0]
    assert g["parent_part_id"] == "PJ-X-00001"
    assert g["parent_is_composite"] is False
    assert g["parent_qty"] == 10.0
    assert g["parent_bom_qty"] == 8.0
    assert len(g["rows"]) == 1
    row = g["rows"][0]
    assert row["part_id"] == "PJ-X-00001"
    assert row["part_name"] == "珠子A"
    assert row["size_tier"] == "small"
    assert row["needed_qty"] == 10.0
    assert row["current_stock"] == 50.0
    assert row["picked"] is False
    assert body["progress"] == {"total": 1, "picked": 0}


def test_get_picking_atomic_zero_stock(client, db):
    """Part with no inventory_log entries shows current_stock=0."""
    _add_atomic_part(db, "PJ-X-NOSTOCK", "无库存件", "small")
    db.add(HandcraftOrder(id="HC-NOSTOCK", supplier_name="商家", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-NOSTOCK",
        part_id="PJ-X-NOSTOCK",
        qty=Decimal("3"),
        bom_qty=None,
    ))
    db.flush()
    body = client.get("/api/handcraft/HC-NOSTOCK/picking").json()
    assert body["groups"][0]["rows"][0]["current_stock"] == 0.0


def _setup_composite(db):
    """1 composite part C with two atom children A(qty=2) and B(qty=3),
    1 handcraft order with 1 part_item of C (qty=5)."""
    db.add(Part(id="PJ-X-00001", name="珠子A", category="吊坠", size_tier="small"))
    db.add(Part(id="PJ-X-00002", name="珠子B", category="吊坠", size_tier="medium"))
    db.add(Part(id="PJ-X-00003", name="组合件C", category="吊坠",
                size_tier="small", is_composite=True))
    db.flush()
    db.add(PartBom(id="PB-1", parent_part_id="PJ-X-00003",
                   child_part_id="PJ-X-00001", qty_per_unit=Decimal("2")))
    db.add(PartBom(id="PB-2", parent_part_id="PJ-X-00003",
                   child_part_id="PJ-X-00002", qty_per_unit=Decimal("3")))
    db.flush()
    _add_inventory(db, "PJ-X-00001", 50)
    _add_inventory(db, "PJ-X-00002", 30)
    db.add(HandcraftOrder(id="HC-COMP", supplier_name="商家", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-COMP",
        part_id="PJ-X-00003",
        qty=Decimal("5"),
        bom_qty=Decimal("5"),
    ))
    db.flush()


def test_get_picking_composite_expands_to_atoms(client, db):
    _setup_composite(db)
    resp = client.get("/api/handcraft/HC-COMP/picking")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["groups"]) == 1
    g = body["groups"][0]
    assert g["parent_is_composite"] is True
    assert g["parent_part_id"] == "PJ-X-00003"
    rows = sorted(g["rows"], key=lambda r: r["part_id"])
    assert len(rows) == 2
    assert rows[0]["part_id"] == "PJ-X-00001"
    assert rows[0]["needed_qty"] == 10.0  # 5 × 2
    assert rows[1]["part_id"] == "PJ-X-00002"
    assert rows[1]["needed_qty"] == 15.0  # 5 × 3
    assert body["progress"] == {"total": 2, "picked": 0}


def test_get_picking_mixed_atomic_and_composite(client, db):
    """Two part_items: one composite, one atomic referencing the same atom.
    Each part_item gets its own group (rule A: 每行独立)."""
    _setup_composite(db)
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-COMP",
        part_id="PJ-X-00001",
        qty=Decimal("8"),
        bom_qty=Decimal("7.5"),
    ))
    db.flush()
    body = client.get("/api/handcraft/HC-COMP/picking").json()
    assert len(body["groups"]) == 2
    atomic_groups = [g for g in body["groups"] if not g["parent_is_composite"]]
    assert len(atomic_groups) == 1
    assert atomic_groups[0]["rows"][0]["part_id"] == "PJ-X-00001"
    assert atomic_groups[0]["rows"][0]["needed_qty"] == 8.0


def test_get_picking_composite_multipath_sums(db, client):
    """If composite C contains atom A twice via different sub-children, the
    expansion sums those contributions into one row."""
    db.add(Part(id="PJ-X-00001", name="A", category="吊坠", size_tier="small"))
    db.add(Part(id="PJ-X-MID1", name="组合件D", category="吊坠",
                size_tier="small", is_composite=True))
    db.add(Part(id="PJ-X-MID2", name="组合件E", category="吊坠",
                size_tier="small", is_composite=True))
    db.add(Part(id="PJ-X-ROOT", name="组合件 F", category="吊坠",
                size_tier="small", is_composite=True))
    db.flush()
    # F → D (×2), F → E (×1)
    db.add(PartBom(id="PB-1", parent_part_id="PJ-X-ROOT",
                   child_part_id="PJ-X-MID1", qty_per_unit=Decimal("2")))
    db.add(PartBom(id="PB-2", parent_part_id="PJ-X-ROOT",
                   child_part_id="PJ-X-MID2", qty_per_unit=Decimal("1")))
    # D → A (×3), E → A (×4)  → expanding F: A = 2×3 + 1×4 = 10 per unit
    db.add(PartBom(id="PB-3", parent_part_id="PJ-X-MID1",
                   child_part_id="PJ-X-00001", qty_per_unit=Decimal("3")))
    db.add(PartBom(id="PB-4", parent_part_id="PJ-X-MID2",
                   child_part_id="PJ-X-00001", qty_per_unit=Decimal("4")))
    db.flush()
    db.add(HandcraftOrder(id="HC-MP", supplier_name="商家", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-MP",
        part_id="PJ-X-ROOT",
        qty=Decimal("5"),
        bom_qty=Decimal("5"),
    ))
    db.flush()
    body = client.get("/api/handcraft/HC-MP/picking").json()
    assert len(body["groups"]) == 1
    g = body["groups"][0]
    assert len(g["rows"]) == 1
    assert g["rows"][0]["part_id"] == "PJ-X-00001"
    assert g["rows"][0]["needed_qty"] == 50.0  # 5 × (2×3 + 1×4) = 50


def test_suggested_qty_atomic_small(client, db):
    """small tier: max(50, theo*2%); suggested = ceil(theo) + ceil(buffer).
    theo=8, ratio_calc=0.16, floor=50 wins. suggested = 8 + 50 = 58."""
    _setup_atomic(db)
    body = client.get("/api/handcraft/HC-TEST-1/picking").json()
    row = body["groups"][0]["rows"][0]
    assert row["suggested_qty"] == 58


def test_suggested_qty_atomic_medium(client, db):
    """medium tier: max(15, theo*1%); suggested = ceil(theo) + ceil(buffer).
    theo=2000, ratio_calc=20.0, ratio wins. suggested = 2000 + 20 = 2020."""
    db.add(Part(id="PJ-X-MED", name="珠子M", category="吊坠", size_tier="medium"))
    db.flush()
    db.add(HandcraftOrder(id="HC-M", supplier_name="商家", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-M",
        part_id="PJ-X-MED",
        qty=Decimal("1500"),
        bom_qty=Decimal("2000"),
    ))
    db.flush()
    body = client.get("/api/handcraft/HC-M/picking").json()
    row = body["groups"][0]["rows"][0]
    assert row["suggested_qty"] == 2020


def test_suggested_qty_none_when_bom_qty_missing_or_zero(client, db):
    """If part_item.bom_qty is None or 0, suggested_qty is None."""
    _add_atomic_part(db, "PJ-X-NA", "无理论", "small")
    _add_atomic_part(db, "PJ-X-ZERO", "零理论", "small")
    db.add(HandcraftOrder(id="HC-NA", supplier_name="商家", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-NA",
        part_id="PJ-X-NA",
        qty=Decimal("5"),
        bom_qty=None,
    ))
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-NA",
        part_id="PJ-X-ZERO",
        qty=Decimal("3"),
        bom_qty=Decimal("0"),
    ))
    db.flush()
    body = client.get("/api/handcraft/HC-NA/picking").json()
    groups_by_part = {g["parent_part_id"]: g for g in body["groups"]}
    assert groups_by_part["PJ-X-NA"]["rows"][0]["suggested_qty"] is None
    assert groups_by_part["PJ-X-ZERO"]["rows"][0]["suggested_qty"] is None


def test_suggested_qty_atomic_small_ratio_wins(client, db):
    """small tier with theoretical large enough that ratio>floor.
    bom_qty=3000, ratio=0.02 → 60 > 50, ratio wins. suggested = 3000 + 60 = 3060."""
    _add_atomic_part(db, "PJ-X-BIG", "大件S", "small")
    db.add(HandcraftOrder(id="HC-BIG", supplier_name="商家", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-BIG",
        part_id="PJ-X-BIG",
        qty=Decimal("100"),
        bom_qty=Decimal("3000"),
    ))
    db.flush()
    body = client.get("/api/handcraft/HC-BIG/picking").json()
    assert body["groups"][0]["rows"][0]["suggested_qty"] == 3060


def test_suggested_qty_composite_uses_atom_tier(client, db):
    """Composite parent has bom_qty=5; expansion gives atom A theoretical
    = 5×2 = 10. A is small-tier → max(50, 10*2%) = 50 → suggested = 10 + 50 = 60.
    Atom B theoretical = 5×3 = 15, medium-tier → max(15, 15*1%) = 15 → 15 + 15 = 30."""
    _setup_composite(db)
    body = client.get("/api/handcraft/HC-COMP/picking").json()
    rows = sorted(body["groups"][0]["rows"], key=lambda r: r["part_id"])
    assert rows[0]["part_id"] == "PJ-X-00001"
    assert rows[0]["size_tier"] == "small"
    assert rows[0]["suggested_qty"] == 60
    assert rows[1]["part_id"] == "PJ-X-00002"
    assert rows[1]["size_tier"] == "medium"
    assert rows[1]["suggested_qty"] == 30


def test_compute_suggested_qty_unit_none_tier_falls_back_to_small():
    """Unit test: _compute_suggested_qty(t=8, tier=None) should fall back to small."""
    from services.handcraft_picking import _compute_suggested_qty
    # tier=None → small rules: max(50, 8*0.02)=50, suggested = 8 + 50 = 58
    assert _compute_suggested_qty(8.0, None) == 58
    # tier="bogus" → also falls back to small
    assert _compute_suggested_qty(8.0, "bogus") == 58
    # theoretical=None → None
    assert _compute_suggested_qty(None, "small") is None
    # theoretical=0 → None
    assert _compute_suggested_qty(0, "small") is None
    # theoretical=-1 → None (negative guarded)
    assert _compute_suggested_qty(-1, "small") is None


# --- Task 5: mark / unmark / reset picking ---


def test_mark_picked_persists_and_shows_in_get(client, db):
    _setup_atomic(db)
    body_before = client.get("/api/handcraft/HC-TEST-1/picking").json()
    pi_id = body_before["groups"][0]["part_item_id"]

    resp = client.post(
        "/api/handcraft/HC-TEST-1/picking/mark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
    )
    assert resp.status_code == 200
    assert resp.json()["picked"] is True

    body_after = client.get("/api/handcraft/HC-TEST-1/picking").json()
    assert body_after["groups"][0]["rows"][0]["picked"] is True
    assert body_after["progress"] == {"total": 1, "picked": 1}


def test_mark_idempotent(client, db):
    _setup_atomic(db)
    pi_id = client.get("/api/handcraft/HC-TEST-1/picking").json()["groups"][0]["part_item_id"]
    for _ in range(3):
        r = client.post(
            "/api/handcraft/HC-TEST-1/picking/mark",
            json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
        )
        assert r.status_code == 200
    count = (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_order_id="HC-TEST-1").count()
    )
    assert count == 1


def test_mark_invalid_part_id_rejected(client, db):
    _setup_atomic(db)
    pi_id = client.get("/api/handcraft/HC-TEST-1/picking").json()["groups"][0]["part_item_id"]
    resp = client.post(
        "/api/handcraft/HC-TEST-1/picking/mark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-NOTREAL"},
    )
    assert resp.status_code == 400
    assert "配货范围" in resp.json()["detail"]


def test_mark_blocked_when_status_not_pending(client, db):
    _setup_atomic(db)
    db.query(HandcraftOrder).filter_by(id="HC-TEST-1").update({"status": "processing"})
    db.flush()
    pi_id = (
        db.query(HandcraftPartItem)
        .filter_by(handcraft_order_id="HC-TEST-1").first().id
    )
    resp = client.post(
        "/api/handcraft/HC-TEST-1/picking/mark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
    )
    assert resp.status_code == 400
    assert "只读" in resp.json()["detail"]


def test_unmark_removes_record(client, db):
    _setup_atomic(db)
    pi_id = client.get("/api/handcraft/HC-TEST-1/picking").json()["groups"][0]["part_item_id"]
    client.post(
        "/api/handcraft/HC-TEST-1/picking/mark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
    )
    resp = client.post(
        "/api/handcraft/HC-TEST-1/picking/unmark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
    )
    assert resp.status_code == 200
    assert resp.json()["picked"] is False
    assert (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_order_id="HC-TEST-1").count() == 0
    )


def test_unmark_idempotent_for_nonexistent(client, db):
    _setup_atomic(db)
    pi_id = client.get("/api/handcraft/HC-TEST-1/picking").json()["groups"][0]["part_item_id"]
    resp = client.post(
        "/api/handcraft/HC-TEST-1/picking/unmark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
    )
    assert resp.status_code == 200
    assert resp.json()["picked"] is False


def test_unmark_blocked_when_status_not_pending(client, db):
    _setup_atomic(db)
    pi_id = client.get("/api/handcraft/HC-TEST-1/picking").json()["groups"][0]["part_item_id"]
    # mark first while still pending
    client.post(
        "/api/handcraft/HC-TEST-1/picking/mark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
    )
    # transition to processing
    db.query(HandcraftOrder).filter_by(id="HC-TEST-1").update({"status": "processing"})
    db.flush()
    resp = client.post(
        "/api/handcraft/HC-TEST-1/picking/unmark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
    )
    assert resp.status_code == 400
    assert "只读" in resp.json()["detail"]


def test_reset_deletes_all_records(client, db):
    _setup_composite(db)
    pi_id = client.get("/api/handcraft/HC-COMP/picking").json()["groups"][0]["part_item_id"]
    client.post(
        "/api/handcraft/HC-COMP/picking/mark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
    )
    client.post(
        "/api/handcraft/HC-COMP/picking/mark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00002"},
    )
    resp = client.delete("/api/handcraft/HC-COMP/picking/reset")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2
    assert (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_order_id="HC-COMP").count() == 0
    )


def test_reset_blocked_when_not_pending(client, db):
    _setup_atomic(db)
    db.query(HandcraftOrder).filter_by(id="HC-TEST-1").update({"status": "completed"})
    db.flush()
    resp = client.delete("/api/handcraft/HC-TEST-1/picking/reset")
    assert resp.status_code == 400
    assert "只读" in resp.json()["detail"]


def test_delete_part_item_cleans_picking_records(client, db):
    """Deleting a HandcraftPartItem must purge its picking records to avoid
    FK violations and stale rows."""
    _setup_atomic(db)
    # Add a second part_item so delete_handcraft_part doesn't reject the last one.
    db.add(Part(id="PJ-X-EXTRA", name="额外", category="吊坠", size_tier="small"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-TEST-1",
        part_id="PJ-X-EXTRA",
        qty=Decimal("1"),
        bom_qty=Decimal("1"),
    ))
    db.flush()
    target_id = (
        db.query(HandcraftPartItem)
        .filter_by(handcraft_order_id="HC-TEST-1", part_id="PJ-X-00001")
        .one().id
    )

    # Mark the target as picked.
    resp_mark = client.post(
        "/api/handcraft/HC-TEST-1/picking/mark",
        json={"part_item_id": target_id, "part_id": "PJ-X-00001"},
    )
    assert resp_mark.status_code == 200
    assert (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_part_item_id=target_id).count() == 1
    )

    # Delete the part_item via the API.
    resp = client.delete(f"/api/handcraft/HC-TEST-1/parts/{target_id}")
    assert resp.status_code in (200, 204)

    # Picking record must be gone too.
    assert (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_part_item_id=target_id).count() == 0
    )


def test_delete_handcraft_order_cleans_picking_records(client, db):
    """Deleting a handcraft order must purge picking records to avoid FK
    violation on the bulk part_item delete inside delete_handcraft_order."""
    _setup_atomic(db)
    pi_id = client.get("/api/handcraft/HC-TEST-1/picking").json()["groups"][0]["part_item_id"]
    resp_mark = client.post(
        "/api/handcraft/HC-TEST-1/picking/mark",
        json={"part_item_id": pi_id, "part_id": "PJ-X-00001"},
    )
    assert resp_mark.status_code == 200
    assert (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_order_id="HC-TEST-1").count() == 1
    )

    resp = client.delete("/api/handcraft/HC-TEST-1")
    assert resp.status_code in (200, 204)

    # Picking records and the order itself should all be gone.
    assert (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_order_id="HC-TEST-1").count() == 0
    )
    assert db.query(HandcraftOrder).filter_by(id="HC-TEST-1").one_or_none() is None


# --- Task 7: PDF export ---


def test_pdf_export_returns_pdf(client, db):
    _setup_atomic(db)
    resp = client.post("/api/handcraft/HC-TEST-1/picking/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert len(resp.content) > 500


def test_pdf_export_empty_order_400(client, db):
    db.add(HandcraftOrder(id="HC-PDFEMPTY", supplier_name="商家", status="pending"))
    db.flush()
    resp = client.post("/api/handcraft/HC-PDFEMPTY/picking/pdf")
    assert resp.status_code == 400
    assert "无可导出" in resp.json()["detail"]


def test_get_picking_composite_with_no_bom_returns_empty_rows(client, db):
    """A composite part_item with no PartBom rows produces a group with rows=[].
    Frontend's displayGroups filters those out so the user never sees a header
    with nothing under it; PDF's _filter_groups does the same. Lock the
    backend contract: the group is still returned (so frontend knows it
    exists), but rows is empty."""
    db.add(Part(id="PJ-X-EMPTY", name="空组合", category="吊坠",
                size_tier="small", is_composite=True))
    db.flush()
    db.add(HandcraftOrder(id="HC-EMPTYC", supplier_name="商家", status="pending"))
    db.flush()
    db.add(HandcraftPartItem(
        handcraft_order_id="HC-EMPTYC",
        part_id="PJ-X-EMPTY",
        qty=Decimal("3"),
        bom_qty=Decimal("3"),
    ))
    db.flush()
    body = client.get("/api/handcraft/HC-EMPTYC/picking").json()
    assert len(body["groups"]) == 1
    assert body["groups"][0]["parent_part_id"] == "PJ-X-EMPTY"
    assert body["groups"][0]["rows"] == []
    assert body["progress"] == {"total": 0, "picked": 0}


def test_mark_request_rejects_invalid_field_values(client, db):
    """Pydantic Field constraints reject zero/negative part_item_id and empty
    part_id at the schema layer (defense-in-depth before service validation)."""
    _setup_atomic(db)
    # part_item_id must be > 0
    resp = client.post(
        "/api/handcraft/HC-TEST-1/picking/mark",
        json={"part_item_id": 0, "part_id": "PJ-X-00001"},
    )
    assert resp.status_code == 422
    # part_id must be non-empty
    pi_id = client.get("/api/handcraft/HC-TEST-1/picking").json()["groups"][0]["part_item_id"]
    resp = client.post(
        "/api/handcraft/HC-TEST-1/picking/mark",
        json={"part_item_id": pi_id, "part_id": ""},
    )
    assert resp.status_code == 422
