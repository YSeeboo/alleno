import pytest
from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock, get_stock


def _setup(db):
    part = create_part(db, {"name": "P1", "category": "小配件", "color": "古铜"})
    jewelry = create_jewelry(db, {"name": "J1", "category": "单件"})
    # Add stock for the part so we can send it
    add_stock(db, "part", part.id, 100.0, "初始入库")
    return part, jewelry


def test_create_handcraft_order(client, db):
    part, jewelry = _setup(db)
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier A",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("HC-")
    assert data["supplier_name"] == "Supplier A"
    assert data["status"] == "pending"
    assert data["delivery_images"] == []

    parts_resp = client.get(f"/api/handcraft/{data['id']}/parts")
    assert parts_resp.status_code == 200
    assert parts_resp.json()[0]["color"] == "古铜"


def test_create_handcraft_order_with_note(client, db):
    part, jewelry = _setup(db)
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier B",
        "parts": [{"part_id": part.id, "qty": 5.0, "bom_qty": 4.0, "note": "extra"}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 3, "note": "rush"}],
        "note": "urgent order",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["note"] == "urgent order"


def test_create_handcraft_order_merge_returns_200(client, db):
    """Second create for same supplier on same day merges and returns 200."""
    part, jewelry = _setup(db)
    resp1 = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier Merge",
        "parts": [{"part_id": part.id, "qty": 5.0}],
    })
    assert resp1.status_code == 201
    order_id = resp1.json()["id"]

    resp2 = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier Merge",
        "parts": [{"part_id": part.id, "qty": 3.0}],
    })
    assert resp2.status_code == 200
    assert resp2.json()["id"] == order_id

    # Verify items accumulated
    parts_resp = client.get(f"/api/handcraft/{order_id}/parts")
    assert len(parts_resp.json()) == 2


def test_create_handcraft_order_different_supplier_no_merge(client, db):
    """Different suppliers always get separate orders with 201."""
    part, jewelry = _setup(db)
    resp1 = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier X",
        "parts": [{"part_id": part.id, "qty": 5.0}],
    })
    assert resp1.status_code == 201

    resp2 = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier Y",
        "parts": [{"part_id": part.id, "qty": 3.0}],
    })
    assert resp2.status_code == 201
    assert resp2.json()["id"] != resp1.json()["id"]


def test_list_handcraft_orders(client, db):
    part, jewelry = _setup(db)
    client.post("/api/handcraft/", json={
        "supplier_name": "Supplier A",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    })
    client.post("/api/handcraft/", json={
        "supplier_name": "Supplier B",
        "parts": [{"part_id": part.id, "qty": 5.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 2}],
    })
    resp = client.get("/api/handcraft/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_list_handcraft_orders_filter_by_status(client, db):
    part, jewelry = _setup(db)
    resp_create = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier A",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    })
    order_id = resp_create.json()["id"]

    # Send to change status to processing
    client.post(f"/api/handcraft/{order_id}/send")

    resp_pending = client.get("/api/handcraft/?status=pending")
    assert resp_pending.status_code == 200
    assert len(resp_pending.json()) == 0

    resp_processing = client.get("/api/handcraft/?status=processing")
    assert resp_processing.status_code == 200
    assert len(resp_processing.json()) == 1


def test_get_handcraft_order(client, db):
    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier A",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    }).json()
    resp = client.get(f"/api/handcraft/{created['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == created["id"]
    assert data["delivery_images"] == []


def test_update_handcraft_delivery_images(client, db):
    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier IMG",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    }).json()

    resp = client.patch(
        f"/api/handcraft/{created['id']}/delivery-images",
        json={
            "delivery_images": [
                "https://img.example.com/a.png",
                " https://img.example.com/b.png ",
            ]
        },
    )

    assert resp.status_code == 200
    assert resp.json()["delivery_images"] == [
        "https://img.example.com/a.png",
        "https://img.example.com/b.png",
    ]

    detail_resp = client.get(f"/api/handcraft/{created['id']}")
    assert detail_resp.json()["delivery_images"] == [
        "https://img.example.com/a.png",
        "https://img.example.com/b.png",
    ]


def test_update_handcraft_delivery_images_rejects_more_than_ten(client, db):
    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier IMG",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    }).json()

    resp = client.patch(
        f"/api/handcraft/{created['id']}/delivery-images",
        json={
            "delivery_images": [f"{i}.png" for i in range(11)]
        },
    )
    assert resp.status_code == 422


def test_handcraft_part_color_reflects_part_update(client, db):
    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier Color",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    }).json()

    resp = client.patch(
        f"/api/parts/{part.id}",
        json={"color": "哑金"},
    )
    assert resp.status_code == 200
    assert resp.json()["color"] == "哑金"

    parts_resp = client.get(f"/api/handcraft/{created['id']}/parts")
    assert parts_resp.status_code == 200
    assert parts_resp.json()[0]["color"] == "哑金"


def test_get_handcraft_order_not_found(client, db):
    resp = client.get("/api/handcraft/HC-9999")
    assert resp.status_code == 404


def test_delete_handcraft_order(client, db):
    part, jewelry = _setup(db)
    db.commit()

    create_resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier Delete",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    })
    order_id = create_resp.json()["id"]

    resp = client.delete(f"/api/handcraft/{order_id}")
    assert resp.status_code == 204

    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
    assert db.query(HandcraftOrder).filter(HandcraftOrder.id == order_id).first() is None
    assert db.query(HandcraftPartItem).filter(HandcraftPartItem.handcraft_order_id == order_id).count() == 0
    assert db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.handcraft_order_id == order_id).count() == 0


def test_delete_completed_handcraft_order_restores_stock_and_clears_receipts(client, db):
    from services.handcraft_receipt import create_handcraft_receipt
    part, jewelry = _setup(db)
    db.commit()

    create_resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier Delete Completed",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    })
    order_id = create_resp.json()["id"]

    send_resp = client.post(f"/api/handcraft/{order_id}/send")
    assert send_resp.status_code == 200

    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
    from models.handcraft_receipt import HandcraftReceipt, HandcraftReceiptItem

    pi = db.query(HandcraftPartItem).filter(HandcraftPartItem.handcraft_order_id == order_id).first()
    ji = db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.handcraft_order_id == order_id).first()

    create_handcraft_receipt(db, "Supplier Delete Completed", [
        {"handcraft_part_item_id": pi.id, "qty": 10.0},
        {"handcraft_jewelry_item_id": ji.id, "qty": 5},
    ])

    assert get_stock(db, "part", part.id) == pytest.approx(100.0)
    assert get_stock(db, "jewelry", jewelry.id) == pytest.approx(5.0)
    assert db.query(HandcraftOrder).filter(HandcraftOrder.id == order_id).first().status == "completed"

    resp = client.delete(f"/api/handcraft/{order_id}")
    assert resp.status_code == 204

    assert get_stock(db, "part", part.id) == pytest.approx(100.0)
    assert get_stock(db, "jewelry", jewelry.id) == pytest.approx(0.0)
    assert db.query(HandcraftOrder).filter(HandcraftOrder.id == order_id).first() is None
    assert db.query(HandcraftPartItem).filter(HandcraftPartItem.handcraft_order_id == order_id).count() == 0
    assert db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.handcraft_order_id == order_id).count() == 0
    assert db.query(HandcraftReceiptItem).count() == 0


def test_send_handcraft_order(client, db):
    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier A",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    }).json()
    resp = client.post(f"/api/handcraft/{created['id']}/send")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processing"


def test_send_handcraft_order_not_found(client, db):
    resp = client.post("/api/handcraft/HC-9999/send")
    assert resp.status_code == 404


def test_send_handcraft_order_insufficient_stock(client, db):
    part = create_part(db, {"name": "P2", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "J2", "category": "单件"})
    # No stock added for part
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier C",
        "parts": [{"part_id": part.id, "qty": 50.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    }).json()
    resp = client.post(f"/api/handcraft/{created['id']}/send")
    assert resp.status_code == 400


def test_receive_handcraft_via_receipt(client, db):
    """Receiving jewelry via HandcraftReceipt (replaces old /receive endpoint)."""
    from services.handcraft_receipt import create_handcraft_receipt
    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier A",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    }).json()
    order_id = created["id"]

    # Send first
    client.post(f"/api/handcraft/{order_id}/send")

    from models.handcraft_order import HandcraftJewelryItem
    ji = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.handcraft_order_id == order_id
    ).first()

    receipt = create_handcraft_receipt(db, "Supplier A", [
        {"handcraft_jewelry_item_id": ji.id, "qty": 3}
    ])
    db.refresh(ji)
    assert ji.received_qty == 3
    assert ji.status == "制作中"


def test_receive_handcraft_completes_order(client, db):
    """Receiving all parts + jewelry completes the order."""
    from services.handcraft_receipt import create_handcraft_receipt
    from models.handcraft_order import HandcraftJewelryItem, HandcraftPartItem
    part, jewelry = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier A",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    }).json()
    order_id = created["id"]
    client.post(f"/api/handcraft/{order_id}/send")

    ji = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.handcraft_order_id == order_id
    ).first()
    pi = db.query(HandcraftPartItem).filter(
        HandcraftPartItem.handcraft_order_id == order_id
    ).first()

    create_handcraft_receipt(db, "Supplier A", [
        {"handcraft_jewelry_item_id": ji.id, "qty": 5},
        {"handcraft_part_item_id": pi.id, "qty": 10.0},
    ])

    order_resp = client.get(f"/api/handcraft/{order_id}")
    assert order_resp.json()["status"] == "completed"


def test_create_handcraft_order_empty_parts(client, db):
    _, jewelry = _setup(db)
    db.commit()
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier EP",
        "parts": [],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 1}],
    })
    assert resp.status_code == 422


def test_create_handcraft_order_empty_jewelries(client, db):
    part, _ = _setup(db)
    db.commit()
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier EJ",
        "parts": [{"part_id": part.id, "qty": 5.0}],
        "jewelries": [],
    })
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"


def test_send_handcraft_order_without_expected_jewelries(client, db):
    part, _ = _setup(db)
    created = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier No Jewelry",
        "parts": [{"part_id": part.id, "qty": 10.0}],
        "jewelries": [],
    }).json()
    resp = client.post(f"/api/handcraft/{created['id']}/send")
    assert resp.status_code == 200
    assert resp.json()["status"] == "processing"


def test_create_handcraft_order_zero_part_qty(client, db):
    part, jewelry = _setup(db)
    db.commit()
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier ZP",
        "parts": [{"part_id": part.id, "qty": 0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 1}],
    })
    assert resp.status_code == 422


def test_create_handcraft_order_negative_part_qty(client, db):
    part, jewelry = _setup(db)
    db.commit()
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier NP",
        "parts": [{"part_id": part.id, "qty": -3.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 1}],
    })
    assert resp.status_code == 422


def test_create_handcraft_order_zero_jewelry_qty(client, db):
    part, jewelry = _setup(db)
    db.commit()
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier ZJ",
        "parts": [{"part_id": part.id, "qty": 5.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 0}],
    })
    assert resp.status_code == 422


def test_create_handcraft_order_negative_jewelry_qty(client, db):
    part, jewelry = _setup(db)
    db.commit()
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Supplier NJ",
        "parts": [{"part_id": part.id, "qty": 5.0}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": -2}],
    })
    assert resp.status_code == 422


def test_handcraft_suppliers_endpoint(client, db):
    """GET /api/handcraft/suppliers returns distinct supplier names."""
    part, jewelry = _setup(db)
    db.commit()
    client.post("/api/handcraft/", json={
        "supplier_name": "商家A",
        "parts": [{"part_id": part.id, "qty": 5}],
    })
    client.post("/api/handcraft/", json={
        "supplier_name": "商家A",
        "parts": [{"part_id": part.id, "qty": 5}],
    })
    client.post("/api/handcraft/", json={
        "supplier_name": "商家B",
        "parts": [{"part_id": part.id, "qty": 5}],
    })

    resp = client.get("/api/handcraft/suppliers")
    assert resp.status_code == 200
    assert set(resp.json()) == {"商家A", "商家B"}


def test_list_handcraft_filter_supplier(client, db):
    """GET /api/handcraft/?supplier_name=X filters by supplier."""
    part, jewelry = _setup(db)
    db.commit()
    client.post("/api/handcraft/", json={
        "supplier_name": "商家C",
        "parts": [{"part_id": part.id, "qty": 5}],
    })
    client.post("/api/handcraft/", json={
        "supplier_name": "商家D",
        "parts": [{"part_id": part.id, "qty": 5}],
    })

    resp = client.get("/api/handcraft/", params={"supplier_name": "商家C"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["supplier_name"] == "商家C"


def test_handcraft_supplier_name_stripped(client, db):
    """Supplier name with whitespace is stripped at schema level."""
    part, jewelry = _setup(db)
    db.commit()
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "  商家E  ",
        "parts": [{"part_id": part.id, "qty": 5}],
    })
    assert resp.status_code == 201
    assert resp.json()["supplier_name"] == "商家E"


# --- pending-receive endpoint tests ---

def _create_and_send(client, db, supplier_name="TestSupplier"):
    part, jewelry = _setup(db)
    db.commit()
    resp = client.post("/api/handcraft/", json={
        "supplier_name": supplier_name,
        "parts": [{"part_id": part.id, "qty": 10}],
        "jewelries": [{"jewelry_id": jewelry.id, "qty": 5}],
    })
    order_id = resp.json()["id"]
    client.post(f"/api/handcraft/{order_id}/send")
    return order_id, part, jewelry


def test_pending_receive_returns_both_types(client, db):
    """After sending, both part and jewelry items appear in pending-receive."""
    order_id, part, jewelry = _create_and_send(client, db)
    resp = client.get("/api/handcraft/items/pending-receive")
    assert resp.status_code == 200
    data = resp.json()
    types = {item["item_type"] for item in data}
    assert "part" in types
    assert "jewelry" in types
    for item in data:
        assert item["handcraft_order_id"] == order_id
        assert "item_name" in item
        assert "item_type" in item


def test_pending_receive_filter_by_supplier(client, db):
    _create_and_send(client, db, supplier_name="SupA")
    _create_and_send(client, db, supplier_name="SupB")
    resp = client.get("/api/handcraft/items/pending-receive", params={"supplier_name": "SupA"})
    data = resp.json()
    assert all(item["supplier_name"] == "SupA" for item in data)
    assert len(data) > 0


def test_pending_receive_filter_by_keyword(client, db):
    _create_and_send(client, db)
    resp = client.get("/api/handcraft/items/pending-receive", params={"keyword": "P1"})
    data = resp.json()
    # Should only return part items matching "P1"
    assert all(item["item_type"] == "part" for item in data)
    assert len(data) > 0


def test_pending_receive_exclude_part_ids_do_not_affect_jewelry(client, db):
    """exclude_part_item_ids should not exclude jewelry items with same integer id."""
    order_id, part, jewelry = _create_and_send(client, db)
    # Get all items to find the IDs
    all_resp = client.get("/api/handcraft/items/pending-receive")
    all_items = all_resp.json()
    part_item = next(i for i in all_items if i["item_type"] == "part")
    jewelry_item = next(i for i in all_items if i["item_type"] == "jewelry")

    # Exclude only part item id — jewelry with same-ish id must still appear
    resp = client.get("/api/handcraft/items/pending-receive", params={
        "exclude_part_item_ids": str(part_item["id"]),
    })
    data = resp.json()
    part_ids = [i["id"] for i in data if i["item_type"] == "part"]
    jewelry_ids = [i["id"] for i in data if i["item_type"] == "jewelry"]
    assert part_item["id"] not in part_ids
    assert jewelry_item["id"] in jewelry_ids


def test_pending_receive_exclude_jewelry_ids_do_not_affect_parts(client, db):
    """exclude_jewelry_item_ids should not exclude part items."""
    order_id, part, jewelry = _create_and_send(client, db)
    all_resp = client.get("/api/handcraft/items/pending-receive")
    all_items = all_resp.json()
    part_item = next(i for i in all_items if i["item_type"] == "part")
    jewelry_item = next(i for i in all_items if i["item_type"] == "jewelry")

    resp = client.get("/api/handcraft/items/pending-receive", params={
        "exclude_jewelry_item_ids": str(jewelry_item["id"]),
    })
    data = resp.json()
    part_ids = [i["id"] for i in data if i["item_type"] == "part"]
    jewelry_ids = [i["id"] for i in data if i["item_type"] == "jewelry"]
    assert jewelry_item["id"] not in jewelry_ids
    assert part_item["id"] in part_ids


def test_pending_receive_empty_when_no_processing_orders(client, db):
    """Pending orders (not sent) should not appear."""
    part, jewelry = _setup(db)
    db.commit()
    client.post("/api/handcraft/", json={
        "supplier_name": "X",
        "parts": [{"part_id": part.id, "qty": 5}],
    })
    resp = client.get("/api/handcraft/items/pending-receive")
    assert resp.status_code == 200
    assert resp.json() == []


def test_pending_receive_exclude_multiple_part_ids(client, db):
    """Multiple exclude_part_item_ids via repeated query key works."""
    from services.part import create_part as svc_create_part

    p1 = svc_create_part(db, {"name": "MP1", "category": "小配件"})
    p2 = svc_create_part(db, {"name": "MP2", "category": "小配件"})
    p3 = svc_create_part(db, {"name": "MP3", "category": "小配件"})
    for p in (p1, p2, p3):
        add_stock(db, "part", p.id, 100, "初始")
    db.commit()
    resp = client.post("/api/handcraft/", json={
        "supplier_name": "Multi",
        "parts": [
            {"part_id": p1.id, "qty": 5},
            {"part_id": p2.id, "qty": 5},
            {"part_id": p3.id, "qty": 5},
        ],
    })
    order_id = resp.json()["id"]
    client.post(f"/api/handcraft/{order_id}/send")

    all_resp = client.get("/api/handcraft/items/pending-receive", params={"supplier_name": "Multi"})
    all_parts = [i for i in all_resp.json() if i["item_type"] == "part"]
    assert len(all_parts) == 3

    ids_to_exclude = [all_parts[0]["id"], all_parts[1]["id"]]
    # Use repeated key format: exclude_part_item_ids=X&exclude_part_item_ids=Y
    resp = client.get(
        f"/api/handcraft/items/pending-receive"
        f"?supplier_name=Multi"
        f"&exclude_part_item_ids={ids_to_exclude[0]}"
        f"&exclude_part_item_ids={ids_to_exclude[1]}"
    )
    assert resp.status_code == 200
    remaining = [i for i in resp.json() if i["item_type"] == "part"]
    assert len(remaining) == 1
    assert remaining[0]["id"] == all_parts[2]["id"]


def test_pending_receive_filter_by_date_on(client, db):
    """date_on filter returns only items from orders created on that date."""
    order_id, part, jewelry = _create_and_send(client, db)
    from datetime import date
    today = date.today().isoformat()

    resp = client.get("/api/handcraft/items/pending-receive", params={"date_on": today})
    assert resp.status_code == 200
    assert len(resp.json()) > 0

    resp2 = client.get("/api/handcraft/items/pending-receive", params={"date_on": "2000-01-01"})
    assert resp2.status_code == 200
    assert len(resp2.json()) == 0


def test_pending_receive_global_sort_interleaves_part_and_jewelry(client, db):
    """Regression: pending-receive results must be globally sorted by
    (created_at desc, handcraft_order_id desc), not concatenated as
    [all parts, all jewelries]. A newer order's jewelry item must come
    before an older order's part item.
    """
    from datetime import datetime
    from models.handcraft_order import HandcraftOrder

    new_id, _, _ = _create_and_send(client, db, supplier_name="NewSup")
    old_id, _, _ = _create_and_send(client, db, supplier_name="OldSup")

    # Force distinct created_at values: older = 2026-04-01, newer = 2026-04-10
    db.query(HandcraftOrder).filter(HandcraftOrder.id == new_id).update(
        {"created_at": datetime(2026, 4, 10, 12, 0, 0)}
    )
    db.query(HandcraftOrder).filter(HandcraftOrder.id == old_id).update(
        {"created_at": datetime(2026, 4, 1, 12, 0, 0)}
    )
    db.commit()

    resp = client.get("/api/handcraft/items/pending-receive")
    assert resp.status_code == 200
    data = resp.json()

    # Each _create_and_send creates 1 part item + 1 jewelry item, so 4 total.
    assert len(data) == 4

    # All rows from the newer order must come strictly before all rows
    # from the older order (regardless of item_type).
    order_ids_in_result = [row["handcraft_order_id"] for row in data]
    assert order_ids_in_result[0] == new_id
    assert order_ids_in_result[1] == new_id
    assert order_ids_in_result[2] == old_id
    assert order_ids_in_result[3] == old_id
