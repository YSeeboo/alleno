from models.handcraft_order import HandcraftOrder
from models.part import Part


def _seed_part(db, part_id="PJ-X-00001", name="小圆环"):
    db.add(Part(id=part_id, name=name, category="小配件"))
    db.flush()


def _seed_handcraft(db, hc_id="HC-0001", supplier="王师傅"):
    db.add(HandcraftOrder(id=hc_id, supplier_name=supplier, status="pending"))
    db.flush()


def test_post_restock_request_creates_pending(client, db):
    _seed_part(db)
    _seed_handcraft(db)

    resp = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001",
        "handcraft_order_id": "HC-0001",
        "source": "picking",
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["source"] == "picking"
    assert body["part_id"] == "PJ-X-00001"
    assert body["handcraft_order_id"] == "HC-0001"


def test_post_restock_idempotent(client, db):
    _seed_part(db)
    _seed_handcraft(db)
    payload = {"part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking"}

    r1 = client.post("/api/restock-requests", json=payload).json()
    r2 = client.post("/api/restock-requests", json=payload).json()

    assert r1["id"] == r2["id"]


def test_post_restock_already_done_returns_400(client, db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    }).json()
    client.patch(f"/api/restock-requests/{rec['id']}", json={"status": "done"})

    resp = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    })
    assert resp.status_code == 400
    assert "已为此手工单补过货" in resp.json()["detail"]


def test_post_restock_manual_persists_note(client, db):
    _seed_part(db)
    _seed_handcraft(db)
    resp = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001",
        "source": "manual", "note": "实物找不到",
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "manual"
    assert body["note"] == "实物找不到"


def test_patch_marks_done_and_404_for_unknown(client, db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    }).json()

    resp = client.patch(f"/api/restock-requests/{rec['id']}", json={"status": "done"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"
    assert resp.json()["completed_at"] is not None

    again = client.patch(f"/api/restock-requests/{rec['id']}", json={"status": "done"})
    assert again.status_code == 400


def test_delete_only_works_on_pending(client, db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    }).json()

    resp = client.delete(f"/api/restock-requests/{rec['id']}")
    assert resp.status_code == 204

    rec2 = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    }).json()
    client.patch(f"/api/restock-requests/{rec2['id']}", json={"status": "done"})
    resp = client.delete(f"/api/restock-requests/{rec2['id']}")
    assert resp.status_code == 400
    assert "已补货" in resp.json()["detail"]


def test_mark_part_done_endpoint(client, db):
    _seed_part(db, "PJ-X-00001")
    _seed_handcraft(db, "HC-0001")
    _seed_handcraft(db, "HC-0002")
    client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    })
    client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0002", "source": "picking",
    })

    resp = client.post("/api/restock-requests/mark-part-done", json={"part_id": "PJ-X-00001"})
    assert resp.status_code == 200
    assert resp.json() == {"updated": 2}


def test_summary_endpoint_aggregates_by_part(client, db):
    _seed_part(db, "PJ-X-00001", name="小圆环")
    _seed_part(db, "PJ-X-00002", name="银扣头")
    _seed_handcraft(db, "HC-0001")
    _seed_handcraft(db, "HC-0002")
    client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    })
    client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0002", "source": "picking",
    })
    client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00002", "handcraft_order_id": "HC-0001", "source": "picking",
    })

    body = client.get("/api/restock-requests/summary").json()
    by_part = {row["part_id"]: row for row in body}
    assert by_part["PJ-X-00001"]["source_count"] == 2
    assert by_part["PJ-X-00002"]["source_count"] == 1


def test_history_endpoint_lists_done(client, db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    }).json()
    client.patch(f"/api/restock-requests/{rec['id']}", json={"status": "done"})

    body = client.get("/api/restock-requests/history").json()
    assert len(body) == 1
    assert body[0]["id"] == rec["id"]
    assert body[0]["completed_at"] is not None


def test_list_restock_for_handcraft_endpoint(client, db):
    _seed_part(db, "PJ-X-00001")
    _seed_part(db, "PJ-X-00002")
    _seed_handcraft(db, "HC-0001")
    _seed_handcraft(db, "HC-0002")

    client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    })
    client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00002", "handcraft_order_id": "HC-0001", "source": "manual", "note": "x",
    })
    client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0002", "source": "picking",
    })

    body = client.get("/api/handcraft/HC-0001/restock-requests").json()
    assert len(body) == 2
    assert {r["part_id"] for r in body} == {"PJ-X-00001", "PJ-X-00002"}
    for row in body:
        assert row["handcraft_order_id"] == "HC-0001"


def test_put_shortfall_sets_and_clears(client, db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    }).json()

    resp = client.put(f"/api/restock-requests/{rec['id']}/shortfall", json={"shortfall_qty": 7})
    assert resp.status_code == 200
    assert resp.json()["shortfall_qty"] == 7

    resp = client.put(f"/api/restock-requests/{rec['id']}/shortfall", json={"shortfall_qty": None})
    assert resp.status_code == 200
    assert resp.json()["shortfall_qty"] is None


def test_put_shortfall_400_when_done(client, db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    }).json()
    client.patch(f"/api/restock-requests/{rec['id']}", json={"status": "done"})

    resp = client.put(f"/api/restock-requests/{rec['id']}/shortfall", json={"shortfall_qty": 5})
    assert resp.status_code == 400
    assert "不可修改差额" in resp.json()["detail"]


def test_put_shortfall_rejects_negative(client, db):
    _seed_part(db)
    _seed_handcraft(db)
    rec = client.post("/api/restock-requests", json={
        "part_id": "PJ-X-00001", "handcraft_order_id": "HC-0001", "source": "picking",
    }).json()

    resp = client.put(f"/api/restock-requests/{rec['id']}/shortfall", json={"shortfall_qty": -1})
    assert resp.status_code == 422
