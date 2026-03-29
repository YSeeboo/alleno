import pytest
from services.jewelry import create_jewelry
from services.part import create_part
from services.bom import set_bom
from services.inventory import add_stock
from services.plating import create_plating_order, send_plating_order


def _setup_order_with_bom(db, client):
    """创建配件、饰品、BOM，然后创建订单。"""
    part_a = create_part(db, {"name": "A珠", "category": "小配件"})
    part_b = create_part(db, {"name": "B链", "category": "链条"})
    jewelry = create_jewelry(db, {"name": "项链A", "retail_price": 100.0, "category": "单件"})
    set_bom(db, jewelry.id, part_a.id, 10)    # 每条项链需要 10 颗 A珠
    set_bom(db, jewelry.id, part_b.id, 1)     # 每条项链需要 1 条 B链

    resp = client.post("/api/orders/", json={
        "customer_name": "测试客户",
        "items": [{"jewelry_id": jewelry.id, "quantity": 100, "unit_price": 50.0}],
    })
    assert resp.status_code == 201
    order_id = resp.json()["id"]
    return order_id, part_a, part_b, jewelry


def _setup_plating_order(db, client, part):
    """创建电镀单并发出，返回 order_id 和 item_id。"""
    add_stock(db, "part", part.id, 5000, "入库")
    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀厂A",
        "items": [{"part_id": part.id, "qty": 2000}],
    })
    assert resp.status_code == 201
    plating_order_id = resp.json()["id"]
    client.post(f"/api/plating/{plating_order_id}/send")
    items_resp = client.get(f"/api/plating/{plating_order_id}/items")
    item_id = items_resp.json()[0]["id"]
    return plating_order_id, item_id


# --- TodoList 生成 ---

def test_generate_todo(client, db):
    order_id, part_a, part_b, _ = _setup_order_with_bom(db, client)
    resp = client.post(f"/api/orders/{order_id}/todo")
    assert resp.status_code == 200
    todos = resp.json()
    assert len(todos) == 2
    part_ids = {t["part_id"] for t in todos}
    assert part_a.id in part_ids
    assert part_b.id in part_ids
    # A珠：10 × 100 = 1000
    a_todo = next(t for t in todos if t["part_id"] == part_a.id)
    assert a_todo["required_qty"] == 1000.0


def test_generate_todo_not_found(client, db):
    resp = client.post("/api/orders/OR-9999/todo")
    assert resp.status_code == 404


def test_get_todo(client, db):
    order_id, _, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    resp = client.get(f"/api/orders/{order_id}/todo")
    assert resp.status_code == 200
    todos = resp.json()
    assert len(todos) == 2
    # 没有库存，所以 is_complete 应为 False
    assert all(t["is_complete"] is False for t in todos)


def test_get_todo_with_stock(client, db):
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    add_stock(db, "part", part_a.id, 2000, "入库")
    client.post(f"/api/orders/{order_id}/todo")
    resp = client.get(f"/api/orders/{order_id}/todo")
    todos = resp.json()
    a_todo = next(t for t in todos if t["part_id"] == part_a.id)
    assert a_todo["is_complete"] is True
    assert a_todo["gap"] == 0.0


def test_regenerate_todo_preserves_links(client, db):
    """重新生成 TodoList 时保留已有关联。"""
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    # 创建电镀单并关联
    _, poi_id = _setup_plating_order(db, client, part_a)
    client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "plating_order_item_id": poi_id,
    })

    # 重新生成 TodoList
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo = next(t for t in todos if t["part_id"] == part_a.id)
    # 关联应保留
    assert len(a_todo["linked_production"]) == 1


# --- 单选关联 ---

def test_create_link(client, db):
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    _, poi_id = _setup_plating_order(db, client, part_a)

    resp = client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "plating_order_item_id": poi_id,
    })
    assert resp.status_code == 201


def test_create_link_duplicate_rejected(client, db):
    """同一个生产项不能关联多个订单。"""
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    _, poi_id = _setup_plating_order(db, client, part_a)

    client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "plating_order_item_id": poi_id,
    })
    # 重复关联应报错
    resp = client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "plating_order_item_id": poi_id,
    })
    assert resp.status_code == 400


def test_delete_link(client, db):
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    _, poi_id = _setup_plating_order(db, client, part_a)
    link = client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "plating_order_item_id": poi_id,
    }).json()

    resp = client.delete(f"/api/orders/links/{link['id']}")
    assert resp.status_code == 204


# --- 批量关联 ---

def test_batch_link(client, db):
    order_id, part_a, part_b, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")

    add_stock(db, "part", part_a.id, 5000, "入库")
    add_stock(db, "part", part_b.id, 5000, "入库")
    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀厂A",
        "items": [
            {"part_id": part_a.id, "qty": 1000},
            {"part_id": part_b.id, "qty": 100},
        ],
    })
    plating_id = resp.json()["id"]
    client.post(f"/api/plating/{plating_id}/send")
    items = client.get(f"/api/plating/{plating_id}/items").json()
    poi_ids = [item["id"] for item in items]

    resp = client.post(f"/api/orders/{order_id}/links/batch", json={
        "order_id": order_id,
        "plating_order_item_ids": poi_ids,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["linked"] == 2
    assert data["skipped"] == []


def test_batch_link_with_skip(client, db):
    """批量关联时，TodoList 中不存在的配件跳过。"""
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")

    # 创建一个不在 BOM 中的配件
    part_c = create_part(db, {"name": "C扣", "category": "小配件"})
    add_stock(db, "part", part_a.id, 5000, "入库")
    add_stock(db, "part", part_c.id, 5000, "入库")
    resp = client.post("/api/plating/", json={
        "supplier_name": "电镀厂A",
        "items": [
            {"part_id": part_a.id, "qty": 1000},
            {"part_id": part_c.id, "qty": 500},
        ],
    })
    plating_id = resp.json()["id"]
    client.post(f"/api/plating/{plating_id}/send")
    items = client.get(f"/api/plating/{plating_id}/items").json()
    poi_ids = [item["id"] for item in items]

    resp = client.post(f"/api/orders/{order_id}/links/batch", json={
        "order_id": order_id,
        "plating_order_item_ids": poi_ids,
    })
    data = resp.json()
    assert data["linked"] == 1
    assert "C扣" in data["skipped"]


# --- 反向查询 ---

def test_plating_item_orders(client, db):
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    plating_id, poi_id = _setup_plating_order(db, client, part_a)
    client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "plating_order_item_id": poi_id,
    })

    resp = client.get(f"/api/plating/{plating_id}/items/{poi_id}/orders")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["order_id"] == order_id


# --- 进度概要 ---

def test_order_progress(client, db):
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    _, poi_id = _setup_plating_order(db, client, part_a)
    client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "plating_order_item_id": poi_id,
    })

    resp = client.get(f"/api/orders/{order_id}/progress")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["completed"] == 0  # 电镀中，未收回


def test_order_progress_no_links(client, db):
    order_id, _, _, _ = _setup_order_with_bom(db, client)
    resp = client.get(f"/api/orders/{order_id}/progress")
    data = resp.json()
    assert data["total"] == 0
    assert data["completed"] == 0


# --- Fix: part_id mismatch rejected ---

def test_create_link_part_id_mismatch_rejected(client, db):
    """配件项的 part_id 必须与 TodoList 行的 part_id 一致。"""
    order_id, part_a, part_b, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    # Get todo for part_b
    b_todo_id = next(t["id"] for t in todos if t["part_id"] == part_b.id)

    # Create plating order for part_a
    _, poi_id = _setup_plating_order(db, client, part_a)

    # Try to link part_a's plating item to part_b's todo — should fail
    resp = client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": b_todo_id,
        "plating_order_item_id": poi_id,
    })
    assert resp.status_code == 400


# --- Fix: reverse-side unlink scoping ---

def test_plating_unlink_wrong_item_rejected(client, db):
    """删除关联时 link_id 必须属于路径中的 item_id。"""
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    plating_id, poi_id = _setup_plating_order(db, client, part_a)
    link = client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "plating_order_item_id": poi_id,
    }).json()

    # Try to delete with wrong item_id (999)
    resp = client.delete(f"/api/plating/{plating_id}/items/999/orders/{link['id']}")
    assert resp.status_code == 404


def test_plating_unlink_wrong_order_id_rejected(client, db):
    """删除关联时 item_id 必须属于路径中的 order_id。"""
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    plating_id, poi_id = _setup_plating_order(db, client, part_a)
    link = client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "plating_order_item_id": poi_id,
    }).json()

    # Try to delete with wrong plating order_id
    resp = client.delete(f"/api/plating/EP-9999/items/{poi_id}/orders/{link['id']}")
    assert resp.status_code == 404


# --- Fix: body order_id mismatch rejected ---

def test_create_link_body_order_id_mismatch_rejected(client, db):
    """body 中的 order_id 必须与路径 order_id 一致。"""
    order_id, part_a, _, jewelry = _setup_order_with_bom(db, client)

    resp = client.post(f"/api/orders/{order_id}/links", json={
        "order_id": "OR-9999",
        "handcraft_jewelry_item_id": 1,
    })
    assert resp.status_code == 400


# --- 采购单关联 ---

def _setup_purchase_order(db, client, part):
    """创建采购单，返回 order_id 和 item_id。"""
    resp = client.post("/api/purchase-orders/", json={
        "vendor_name": "供应商A",
        "items": [{"part_id": part.id, "qty": 500, "price": 1.0}],
    })
    assert resp.status_code == 201
    po_id = resp.json()["id"]
    item_id = resp.json()["items"][0]["id"]
    return po_id, item_id


def test_create_link_purchase_order_item(client, db):
    """采购单配件项可以关联 TodoList 行。"""
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    po_id, poi_id = _setup_purchase_order(db, client, part_a)

    resp = client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "purchase_order_item_id": poi_id,
    })
    assert resp.status_code == 201
    assert resp.json()["purchase_order_item_id"] == poi_id


def test_batch_link_purchase_order_items(client, db):
    """采购单配件项可以批量关联。"""
    order_id, part_a, part_b, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")

    resp = client.post("/api/purchase-orders/", json={
        "vendor_name": "供应商A",
        "items": [
            {"part_id": part_a.id, "qty": 500, "price": 1.0},
            {"part_id": part_b.id, "qty": 50, "price": 2.0},
        ],
    })
    po_id = resp.json()["id"]
    poi_ids = [item["id"] for item in resp.json()["items"]]

    resp = client.post(f"/api/orders/{order_id}/links/batch", json={
        "order_id": order_id,
        "purchase_order_item_ids": poi_ids,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["linked"] == 2
    assert data["skipped"] == []


def test_purchase_item_orders_reverse_lookup(client, db):
    """采购单配件项可以反向查询关联的订单。"""
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    po_id, poi_id = _setup_purchase_order(db, client, part_a)
    client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "purchase_order_item_id": poi_id,
    })

    resp = client.get(f"/api/purchase-orders/{po_id}/items/{poi_id}/orders")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["order_id"] == order_id


def test_purchase_item_unlink(client, db):
    """采购单侧可以解除关联。"""
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    po_id, poi_id = _setup_purchase_order(db, client, part_a)
    link = client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "purchase_order_item_id": poi_id,
    }).json()

    resp = client.delete(f"/api/purchase-orders/{po_id}/items/{poi_id}/orders/{link['id']}")
    assert resp.status_code == 204

    # Verify unlinked
    resp = client.get(f"/api/purchase-orders/{po_id}/items/{poi_id}/orders")
    assert resp.json() == []


def test_purchase_link_progress_counts_as_completed(client, db):
    """采购单关联的配件项在进度中视为已完成。"""
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    po_id, poi_id = _setup_purchase_order(db, client, part_a)
    client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "purchase_order_item_id": poi_id,
    })

    resp = client.get(f"/api/orders/{order_id}/progress")
    data = resp.json()
    assert data["total"] == 1
    assert data["completed"] == 1


def test_linked_production_shows_purchase_type(client, db):
    """TodoList linked_production 显示采购单类型。"""
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    po_id, poi_id = _setup_purchase_order(db, client, part_a)
    client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "purchase_order_item_id": poi_id,
    })

    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo = next(t for t in todos if t["part_id"] == part_a.id)
    assert len(a_todo["linked_production"]) == 1
    lp = a_todo["linked_production"][0]
    assert lp["type"] == "purchase"
    assert lp["status"] == "已采购"
    assert lp["order_id"] == po_id
