"""Verify the foundational assumption for bulk-assign in the matrix UI:
HC creation with no per-jewelry customer_name produces breakdown entries
where customer_name=None and is_locked=False (i.e. claimable placeholders).
"""
from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock


def _setup(db):
    part = create_part(db, {"name": "P-PH", "category": "小配件", "color": "古铜"})
    jewelry = create_jewelry(db, {"name": "J-PH", "category": "单件"})
    add_stock(db, "part", part.id, 100.0, "init")
    return part, jewelry


def test_hc_create_generates_placeholder_breakdown_entries(client, db):
    """Bulk-assign needs `customer_name = None + is_locked = false` entries
    to PATCH. Confirm HC creation produces them when payload omits customer_name."""
    part, jewelry = _setup(db)

    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Sup-PH",
        "parts": [{"part_id": part.id, "qty": 5.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 7}],
    })
    assert resp.status_code == 201
    hc_id = resp.json()["id"]

    br = client.get(f"/api/handcraft/{hc_id}/jewelry-breakdown")
    assert br.status_code == 200
    groups = br.json()
    assert len(groups) == 1, "Expected exactly one jewelry group"

    g = groups[0]
    assert g["jewelry_id"] == jewelry.id
    assert g["total_qty"] == 7

    # All entries should be claimable placeholders:
    # customer_name=None, source=manual, is_locked=False
    placeholder_qty_sum = 0
    for e in g["entries"]:
        assert e["customer_name"] is None
        assert e["source"] == "manual"
        assert e["is_locked"] is False
        placeholder_qty_sum += e["qty"]
    assert placeholder_qty_sum == 7, (
        "Placeholder qty must cover total_qty so bulk-assign can claim everything"
    )
