import pytest

from services.part import create_part
from services.inventory import add_stock, get_stock
from services.plating_receipt import create_plating_receipt


def test_create_plating_order(client, db):
    part = create_part(db, {"name": "P1", "category": "小配件"})
    db.commit()

    resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier A",
        "items": [
            {"part_id": part.id, "qty": 10.0, "plating_method": "金色"}
        ],
        "note": "test order",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["supplier_name"] == "Supplier A"
    assert data["status"] == "pending"
    assert data["id"].startswith("EP-")
    assert data["delivery_images"] == []


def test_list_plating_orders(client, db):
    part = create_part(db, {"name": "P2", "category": "小配件"})
    db.commit()

    client.post("/api/plating/", json={
        "supplier_name": "Supplier B",
        "items": [{"part_id": part.id, "qty": 5.0}],
    })
    client.post("/api/plating/", json={
        "supplier_name": "Supplier C",
        "items": [{"part_id": part.id, "qty": 3.0}],
    })

    resp = client.get("/api/plating/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_list_plating_orders_filter_by_status(client, db):
    part = create_part(db, {"name": "P3", "category": "小配件"})
    db.commit()

    client.post("/api/plating/", json={
        "supplier_name": "Supplier D",
        "items": [{"part_id": part.id, "qty": 5.0}],
    })

    resp = client.get("/api/plating/?status=pending")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "pending"

    resp2 = client.get("/api/plating/?status=processing")
    assert resp2.status_code == 200
    assert len(resp2.json()) == 0


def test_get_plating_order(client, db):
    part = create_part(db, {"name": "P4", "category": "小配件"})
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier E",
        "items": [{"part_id": part.id, "qty": 8.0}],
    })
    order_id = create_resp.json()["id"]

    resp = client.get(f"/api/plating/{order_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == order_id


def test_get_plating_order_not_found(client, db):
    resp = client.get("/api/plating/EP-9999")
    assert resp.status_code == 404


def test_delete_plating_order(client, db):
    part = create_part(db, {"name": "P_delete", "category": "小配件"})
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier Delete",
        "items": [{"part_id": part.id, "qty": 8.0}],
    })
    order_id = create_resp.json()["id"]

    resp = client.delete(f"/api/plating/{order_id}")
    assert resp.status_code == 204

    from models.plating_order import PlatingOrder, PlatingOrderItem
    assert db.query(PlatingOrder).filter(PlatingOrder.id == order_id).first() is None
    assert db.query(PlatingOrderItem).filter(PlatingOrderItem.plating_order_id == order_id).count() == 0


def test_delete_completed_plating_order_restores_stock_and_clears_receipts(client, db):
    """Delete a completed plating order (received via plating receipt) restores stock."""
    from services.plating import create_plating_order, send_plating_order, get_plating_items

    part = create_part(db, {"name": "P_delete_completed", "category": "小配件"})
    add_stock(db, "part", part.id, 30.0, "initial stock")
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier Delete Completed",
        "items": [{"part_id": part.id, "qty": 10.0}],
    })
    order_id = create_resp.json()["id"]

    send_resp = client.post(f"/api/plating/{order_id}/send")
    assert send_resp.status_code == 200

    from models.plating_order import PlatingOrder, PlatingOrderItem

    item_id = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order_id
    ).first().id

    # Use plating receipt instead of old receive endpoint
    create_plating_receipt(db, "Supplier Delete Completed", [
        {"plating_order_item_id": item_id, "part_id": part.id, "qty": 10.0}
    ])

    assert get_stock(db, "part", part.id) == pytest.approx(30.0)
    assert db.query(PlatingOrder).filter(PlatingOrder.id == order_id).first().status == "completed"

    resp = client.delete(f"/api/plating/{order_id}")
    assert resp.status_code == 204

    assert get_stock(db, "part", part.id) == pytest.approx(30.0)
    assert db.query(PlatingOrder).filter(PlatingOrder.id == order_id).first() is None
    assert db.query(PlatingOrderItem).filter(PlatingOrderItem.plating_order_id == order_id).count() == 0


def test_send_plating_order(client, db):
    part = create_part(db, {"name": "P5", "category": "小配件"})
    add_stock(db, "part", part.id, 20.0, "initial stock")
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier F",
        "items": [{"part_id": part.id, "qty": 10.0, "plating_method": "银色"}],
    })
    order_id = create_resp.json()["id"]

    resp = client.post(f"/api/plating/{order_id}/send")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processing"


def test_send_plating_order_insufficient_stock(client, db):
    part = create_part(db, {"name": "P6", "category": "小配件"})
    db.commit()
    # No stock added

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier G",
        "items": [{"part_id": part.id, "qty": 10.0}],
    })
    order_id = create_resp.json()["id"]

    resp = client.post(f"/api/plating/{order_id}/send")
    assert resp.status_code == 400


def test_send_plating_order_not_found(client, db):
    resp = client.post("/api/plating/EP-9999/send")
    assert resp.status_code == 404


def test_create_plating_order_empty_items(client, db):
    resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier Empty",
        "items": [],
    })
    assert resp.status_code == 422


def test_create_plating_order_zero_qty(client, db):
    part = create_part(db, {"name": "P_zero", "category": "小配件"})
    db.commit()
    resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier Z",
        "items": [{"part_id": part.id, "qty": 0}],
    })
    assert resp.status_code == 422


def test_create_plating_order_negative_qty(client, db):
    part = create_part(db, {"name": "P_neg", "category": "小配件"})
    db.commit()
    resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier N",
        "items": [{"part_id": part.id, "qty": -5.0}],
    })
    assert resp.status_code == 422


def test_update_plating_delivery_images(client, db):
    part = create_part(db, {"name": "P_img", "category": "小配件"})
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier IMG",
        "items": [{"part_id": part.id, "qty": 8.0}],
    })
    order_id = create_resp.json()["id"]

    resp = client.patch(f"/api/plating/{order_id}/delivery-images", json={
        "delivery_images": [
            "https://img.example.com/a.png",
            "https://img.example.com/b.png",
        ],
    })
    assert resp.status_code == 200
    assert resp.json()["delivery_images"] == [
        "https://img.example.com/a.png",
        "https://img.example.com/b.png",
    ]

    detail_resp = client.get(f"/api/plating/{order_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["delivery_images"] == [
        "https://img.example.com/a.png",
        "https://img.example.com/b.png",
    ]


def test_update_plating_delivery_images_rejects_more_than_ten(client, db):
    part = create_part(db, {"name": "P_img_limit", "category": "小配件"})
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Supplier IMG LIMIT",
        "items": [{"part_id": part.id, "qty": 6.0}],
    })
    order_id = create_resp.json()["id"]

    resp = client.patch(f"/api/plating/{order_id}/delivery-images", json={
        "delivery_images": [f"{i}.png" for i in range(11)],
    })
    assert resp.status_code == 422


def test_get_plating_items_keeps_id_order_after_update(client, db):
    parts = []
    for index in range(3):
        part = create_part(db, {"name": f"排序配件{index + 1}", "category": "小配件"})
        parts.append(part)
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "排序测试电镀厂",
        "items": [
            {"part_id": parts[0].id, "qty": 1, "unit": "个"},
            {"part_id": parts[1].id, "qty": 2, "unit": "个"},
            {"part_id": parts[2].id, "qty": 3, "unit": "个"},
        ],
    })
    order_id = create_resp.json()["id"]

    before_resp = client.get(f"/api/plating/{order_id}/items")
    assert before_resp.status_code == 200
    before_ids = [item["id"] for item in before_resp.json()]

    client.put(f"/api/plating/{order_id}/items/{before_ids[1]}", json={"unit": "条"})

    after_resp = client.get(f"/api/plating/{order_id}/items")
    assert after_resp.status_code == 200
    after_ids = [item["id"] for item in after_resp.json()]

    assert after_ids == before_ids


# ──────────────────────────────────────────────────────────────
# receive_part_id: receive to a different part
# ──────────────────────────────────────────────────────────────

def test_receive_with_receive_part_id_adds_stock_to_target(client, db):
    """When receive_part_id is set, received stock goes to that part, not part_id."""
    part_a = create_part(db, {"name": "原色扣", "category": "小配件"})
    part_b = create_part(db, {"name": "金色扣", "category": "小配件", "parent_part_id": part_a.id})
    add_stock(db, "part", part_a.id, 100.0, "入库")
    db.commit()

    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀厂R",
        "items": [{"part_id": part_a.id, "qty": 20.0, "receive_part_id": part_b.id}],
    })
    order_id = resp.json()["id"]
    client.post(f"/api/plating/{order_id}/send")

    from models.plating_order import PlatingOrderItem
    item = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order_id
    ).first()
    assert item.receive_part_id == part_b.id

    # Receive full qty via plating receipt
    create_plating_receipt(db, "电镀厂R", [
        {"plating_order_item_id": item.id, "part_id": part_b.id, "qty": 20.0}
    ])

    # Stock: part_a sent 20, part_b received 20
    assert get_stock(db, "part", part_a.id) == pytest.approx(80.0)
    assert get_stock(db, "part", part_b.id) == pytest.approx(20.0)


def test_receive_part_id_roundtrip_processing_to_pending(client, db):
    """processing->pending rollback correctly reverses receive_part_id stock."""
    from services.kanban import change_order_status

    part_a = create_part(db, {"name": "原色链", "category": "链条"})
    part_b = create_part(db, {"name": "金色链", "category": "链条", "parent_part_id": part_a.id})
    add_stock(db, "part", part_a.id, 50.0, "入库")
    db.commit()

    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀厂RT",
        "items": [{"part_id": part_a.id, "qty": 10.0, "receive_part_id": part_b.id}],
    })
    order_id = resp.json()["id"]
    client.post(f"/api/plating/{order_id}/send")

    from models.plating_order import PlatingOrderItem
    item = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order_id
    ).first()
    create_plating_receipt(db, "电镀厂RT", [
        {"plating_order_item_id": item.id, "part_id": part_b.id, "qty": 5.0}
    ])

    assert get_stock(db, "part", part_a.id) == pytest.approx(40.0)
    assert get_stock(db, "part", part_b.id) == pytest.approx(5.0)

    # Rollback to pending: receive_part_id stock reversed, sent stock restored
    change_order_status(db, order_id, "plating", "pending")
    assert get_stock(db, "part", part_a.id) == pytest.approx(50.0)
    assert get_stock(db, "part", part_b.id) == pytest.approx(0.0)


def test_force_complete_plating_blocked(client, db):
    """Kanban processing→completed is blocked for plating orders; must use PlatingReceipt."""
    from services.kanban import change_order_status

    part_a = create_part(db, {"name": "原色吊坠", "category": "吊坠"})
    add_stock(db, "part", part_a.id, 30.0, "入库")
    db.commit()

    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀厂FC",
        "items": [{"part_id": part_a.id, "qty": 10.0}],
    })
    order_id = resp.json()["id"]
    client.post(f"/api/plating/{order_id}/send")

    with pytest.raises(ValueError, match="回收单"):
        change_order_status(db, order_id, "plating", "completed")


def test_delete_plating_order_with_receive_part_id_restores_stock(client, db):
    """Delete rollback deducts from receive_part_id, adds back to part_id."""
    part_a = create_part(db, {"name": "原色X", "category": "小配件"})
    part_b = create_part(db, {"name": "金色X", "category": "小配件", "parent_part_id": part_a.id})
    add_stock(db, "part", part_a.id, 50.0, "入库")
    db.commit()

    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀厂DEL",
        "items": [{"part_id": part_a.id, "qty": 10.0, "receive_part_id": part_b.id}],
    })
    order_id = resp.json()["id"]
    client.post(f"/api/plating/{order_id}/send")

    from models.plating_order import PlatingOrderItem
    item = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order_id
    ).first()
    create_plating_receipt(db, "电镀厂DEL", [
        {"plating_order_item_id": item.id, "part_id": part_b.id, "qty": 10.0}
    ])

    assert get_stock(db, "part", part_a.id) == pytest.approx(40.0)
    assert get_stock(db, "part", part_b.id) == pytest.approx(10.0)

    resp = client.delete(f"/api/plating/{order_id}")
    assert resp.status_code == 204

    # Everything restored: sent from A comes back, received to B reversed
    assert get_stock(db, "part", part_a.id) == pytest.approx(50.0)
    assert get_stock(db, "part", part_b.id) == pytest.approx(0.0)


def test_pending_receive_items_include_created_at(client, db):
    """GET /api/plating/items/pending-receive returns created_at field."""
    from services.plating import create_plating_order, send_plating_order

    part = create_part(db, {"name": "测试扣", "category": "小配件"})
    add_stock(db, "part", part.id, 100, "初始")
    order = create_plating_order(db, "厂A", [{"part_id": part.id, "qty": 50, "plating_method": "金色"}])
    send_plating_order(db, order.id)
    db.flush()

    resp = client.get("/api/plating/items/pending-receive")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    assert "created_at" in items[0]
    assert items[0]["created_at"] is not None


def test_pending_receive_items_filter_date_on(client, db):
    """GET /api/plating/items/pending-receive?date_on=YYYY-MM-DD filters by created_at date."""
    from services.plating import create_plating_order, send_plating_order
    from models.plating_order import PlatingOrder
    from datetime import datetime

    part = create_part(db, {"name": "扣A", "category": "小配件"})
    add_stock(db, "part", part.id, 200, "初始")

    # Order 1 — today
    o1 = create_plating_order(db, "厂A", [{"part_id": part.id, "qty": 10, "plating_method": "金色"}])
    send_plating_order(db, o1.id)

    # Order 2 — force to a different date
    o2 = create_plating_order(db, "厂A", [{"part_id": part.id, "qty": 20, "plating_method": "银色"}])
    send_plating_order(db, o2.id)
    db.query(PlatingOrder).filter(PlatingOrder.id == o2.id).update(
        {"created_at": datetime(2025, 1, 15, 10, 0, 0)}
    )
    db.flush()

    # Filter by o2's date — should only return o2's item
    resp = client.get("/api/plating/items/pending-receive", params={"date_on": "2025-01-15"})
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["plating_order_id"] == o2.id

    # Filter by today — should only return o1's item
    from time_utils import now_beijing
    today_str = now_beijing().strftime("%Y-%m-%d")
    resp2 = client.get("/api/plating/items/pending-receive", params={"date_on": today_str})
    items2 = resp2.json()
    assert len(items2) == 1
    assert items2[0]["plating_order_id"] == o1.id


def test_pending_receive_items_exclude_item_ids(client, db):
    """GET /api/plating/items/pending-receive?exclude_item_ids=1,2 excludes those items."""
    from services.plating import create_plating_order, send_plating_order, get_plating_items

    p1 = create_part(db, {"name": "扣X", "category": "小配件"})
    p2 = create_part(db, {"name": "扣Y", "category": "小配件"})
    add_stock(db, "part", p1.id, 100, "初始")
    add_stock(db, "part", p2.id, 100, "初始")

    order = create_plating_order(db, "厂B", [
        {"part_id": p1.id, "qty": 10, "plating_method": "金色"},
        {"part_id": p2.id, "qty": 20, "plating_method": "银色"},
    ])
    send_plating_order(db, order.id)
    db.flush()

    items = get_plating_items(db, order.id)
    exclude_id = items[0].id

    # Without exclusion — both items
    resp_all = client.get("/api/plating/items/pending-receive", params={"supplier_name": "厂B"})
    assert len(resp_all.json()) == 2

    # With exclusion — only the non-excluded item
    resp_excl = client.get("/api/plating/items/pending-receive", params={
        "supplier_name": "厂B",
        "exclude_item_ids": str(exclude_id),
    })
    items_excl = resp_excl.json()
    assert len(items_excl) == 1
    assert items_excl[0]["id"] != exclude_id


def test_pending_receive_items_exclude_item_ids_invalid(client, db):
    """GET /api/plating/items/pending-receive?exclude_item_ids=abc returns 422."""
    resp = client.get("/api/plating/items/pending-receive?exclude_item_ids=abc")
    assert resp.status_code == 422


def test_pending_receive_items_exclude_multiple_ids(client, db):
    """GET /api/plating/items/pending-receive?exclude_item_ids=1&exclude_item_ids=2 works as list."""
    from services.plating import create_plating_order, send_plating_order, get_plating_items

    p1 = create_part(db, {"name": "扣M1", "category": "小配件"})
    p2 = create_part(db, {"name": "扣M2", "category": "小配件"})
    p3 = create_part(db, {"name": "扣M3", "category": "小配件"})
    for p in (p1, p2, p3):
        add_stock(db, "part", p.id, 100, "初始")

    order = create_plating_order(db, "厂M", [
        {"part_id": p1.id, "qty": 10, "plating_method": "金色"},
        {"part_id": p2.id, "qty": 10, "plating_method": "银色"},
        {"part_id": p3.id, "qty": 10, "plating_method": "玫瑰金"},
    ])
    send_plating_order(db, order.id)
    db.flush()

    items = get_plating_items(db, order.id)
    id1, id2, id3 = items[0].id, items[1].id, items[2].id

    # Exclude two of three
    resp = client.get(
        f"/api/plating/items/pending-receive?supplier_name=厂M&exclude_item_ids={id1}&exclude_item_ids={id2}",
    )
    assert resp.status_code == 200
    result = resp.json()
    assert len(result) == 1
    assert result[0]["id"] == id3


def test_plating_suppliers_endpoint(client, db):
    """GET /api/plating/suppliers returns distinct supplier names."""
    from services.plating import create_plating_order

    p = create_part(db, {"name": "S1", "category": "小配件"})
    create_plating_order(db, "厂X", [{"part_id": p.id, "qty": 5, "plating_method": "金色"}])
    create_plating_order(db, "厂X", [{"part_id": p.id, "qty": 5, "plating_method": "银色"}])
    create_plating_order(db, "厂Y", [{"part_id": p.id, "qty": 5, "plating_method": "金色"}])
    db.flush()

    resp = client.get("/api/plating/suppliers")
    assert resp.status_code == 200
    names = resp.json()
    assert set(names) == {"厂X", "厂Y"}


def test_list_plating_orders_filter_supplier(client, db):
    """GET /api/plating/?supplier_name=X filters by supplier."""
    from services.plating import create_plating_order

    p = create_part(db, {"name": "S2", "category": "小配件"})
    create_plating_order(db, "厂A", [{"part_id": p.id, "qty": 5, "plating_method": "金色"}])
    create_plating_order(db, "厂B", [{"part_id": p.id, "qty": 5, "plating_method": "银色"}])
    db.flush()

    resp = client.get("/api/plating/", params={"supplier_name": "厂A"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["supplier_name"] == "厂A"


def test_list_plating_orders_filter_supplier_multi_keyword(client, db):
    """Regression: supplier_name supports multi-keyword AND search.

    '老王 北京' should find '老王北京电镀厂' but not '老王上海电镀厂'
    or '老李北京电镀厂'.
    """
    from services.plating import create_plating_order

    p = create_part(db, {"name": "S4", "category": "小配件"})
    create_plating_order(db, "老王北京电镀厂", [{"part_id": p.id, "qty": 5}])
    create_plating_order(db, "老王上海电镀厂", [{"part_id": p.id, "qty": 5}])
    create_plating_order(db, "老李北京电镀厂", [{"part_id": p.id, "qty": 5}])
    db.flush()

    resp = client.get("/api/plating/", params={"supplier_name": "老王 北京"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["supplier_name"] == "老王北京电镀厂"


def test_list_plating_orders_empty_supplier_name_returns_empty(client, db):
    """Regression: explicit empty/whitespace supplier_name must return no
    rows, not fall through to an unfiltered query.

    Pre-fix, the keyword_filter migration broke this edge case: empty
    strings returned None from the helper, which caused the call site to
    skip the filter entirely and return every order. supplier_name=None
    (parameter absent) should still return all rows.
    """
    from services.plating import create_plating_order, list_plating_orders

    p = create_part(db, {"name": "S5", "category": "小配件"})
    create_plating_order(db, "供应商A", [{"part_id": p.id, "qty": 5}])
    create_plating_order(db, "供应商B", [{"part_id": p.id, "qty": 5}])
    db.flush()

    # Service-level: None returns all, empty/whitespace returns none.
    assert len(list_plating_orders(db, supplier_name=None)) == 2
    assert list_plating_orders(db, supplier_name="") == []
    assert list_plating_orders(db, supplier_name="   ") == []
    assert list_plating_orders(db, supplier_name="\t\n") == []

    # API-level: ?supplier_name= (empty string in URL) must not return all.
    resp = client.get("/api/plating/", params={"supplier_name": ""})
    assert resp.status_code == 200
    assert resp.json() == []


def test_plating_supplier_name_stripped(client, db):
    """Supplier name with whitespace is stripped at schema level."""
    p = create_part(db, {"name": "S3", "category": "小配件"})
    db.flush()

    resp = client.post("/api/plating/", json={
        "supplier_name": "  厂Z  ",
        "items": [{"part_id": p.id, "qty": 5, "plating_method": "金色"}],
    })
    assert resp.status_code == 201
    assert resp.json()["supplier_name"] == "厂Z"


def test_update_plating_order_supplier_name(client, db):
    part = create_part(db, {"name": "PU1", "category": "小配件"})
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Old Supplier",
        "items": [{"part_id": part.id, "qty": 5.0}],
    })
    order_id = create_resp.json()["id"]

    resp = client.patch(f"/api/plating/{order_id}", json={"supplier_name": "New Supplier"})
    assert resp.status_code == 200
    assert resp.json()["supplier_name"] == "New Supplier"
    assert resp.json()["id"] == order_id


def test_update_plating_order_blank_supplier_name(client, db):
    part = create_part(db, {"name": "PU2", "category": "小配件"})
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Some Supplier",
        "items": [{"part_id": part.id, "qty": 5.0}],
    })
    order_id = create_resp.json()["id"]

    resp = client.patch(f"/api/plating/{order_id}", json={"supplier_name": "   "})
    assert resp.status_code == 422


def test_update_plating_order_not_pending(client, db):
    part = create_part(db, {"name": "PU3", "category": "小配件"})
    add_stock(db, "part", part.id, 100.0, "initial")
    db.commit()

    create_resp = client.post("/api/plating/", json={
        "supplier_name": "Some Supplier",
        "items": [{"part_id": part.id, "qty": 5.0}],
    })
    order_id = create_resp.json()["id"]

    client.post(f"/api/plating/{order_id}/send")

    resp = client.patch(f"/api/plating/{order_id}", json={"supplier_name": "New"})
    assert resp.status_code == 400


def test_update_plating_order_not_found(client, db):
    resp = client.patch("/api/plating/EP-9999", json={"supplier_name": "X"})
    assert resp.status_code == 400
