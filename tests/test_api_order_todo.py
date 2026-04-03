import pytest
from services.jewelry import create_jewelry
from services.part import create_part
from services.bom import set_bom
from services.inventory import add_stock
from services.plating import create_plating_order, send_plating_order
from models.order import OrderTodoBatch, OrderTodoBatchJewelry, OrderItemLink, OrderItem


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
    """进度 = 完成备货的饰品种类数 / 饰品种类数。"""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)

    # 1 种饰品，库存为 0，completed=0
    resp = client.get(f"/api/orders/{order_id}/progress")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["completed"] == 0

    # 入库饰品库存满足需求量
    order_item = db.query(OrderItem).filter_by(order_id=order_id).first()
    add_stock(db, "jewelry", jewelry.id, order_item.quantity, "入库")
    db.flush()

    resp = client.get(f"/api/orders/{order_id}/progress")
    data = resp.json()
    assert data["total"] == 1
    assert data["completed"] == 1


def test_order_progress_no_completed(client, db):
    """有饰品但无库存时 completed=0。"""
    order_id, _, _, _ = _setup_order_with_bom(db, client)
    resp = client.get(f"/api/orders/{order_id}/progress")
    data = resp.json()
    assert data["total"] == 1  # 1 jewelry type
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


def test_purchase_link_progress_stock_based(client, db):
    """进度基于饰品库存是否满足订单需求量。"""
    order_id, part_a, _, jewelry = _setup_order_with_bom(db, client)

    # 1 种饰品，饰品库存为 0
    resp = client.get(f"/api/orders/{order_id}/progress")
    data = resp.json()
    assert data["total"] == 1
    assert data["completed"] == 0

    # 入库饰品满足需求量
    order_item = db.query(OrderItem).filter_by(order_id=order_id).first()
    add_stock(db, "jewelry", jewelry.id, order_item.quantity, "入库")
    db.flush()
    resp = client.get(f"/api/orders/{order_id}/progress")
    data = resp.json()
    assert data["total"] == 1
    assert data["completed"] == 1


def test_delete_purchase_order_with_link(client, db):
    """Deleting a purchase order with linked items should not cause FK error."""
    order_id, part_a, _, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    po_id, poi_id = _setup_purchase_order(db, client, part_a)
    client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "purchase_order_item_id": poi_id,
    })

    # Delete the purchase order — should succeed, not FK error
    resp = client.delete(f"/api/purchase-orders/{po_id}")
    assert resp.status_code == 204

    # Link should be gone — verify via todo's linked_production
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo = next(t for t in todos if t["part_id"] == part_a.id)
    assert a_todo["linked_production"] == []


def test_delete_purchase_item_with_link(client, db):
    """Deleting a single purchase item with a link should clean up the link."""
    order_id, part_a, part_b, _ = _setup_order_with_bom(db, client)
    client.post(f"/api/orders/{order_id}/todo")
    todos = client.get(f"/api/orders/{order_id}/todo").json()
    a_todo_id = next(t["id"] for t in todos if t["part_id"] == part_a.id)

    # Create PO with 2 items so we can delete one (can't delete last item)
    resp = client.post("/api/purchase-orders/", json={
        "vendor_name": "供应商A",
        "items": [
            {"part_id": part_a.id, "qty": 500, "price": 1.0},
            {"part_id": part_b.id, "qty": 100, "price": 2.0},
        ],
    })
    po_id = resp.json()["id"]
    poi_a_id = next(i["id"] for i in resp.json()["items"] if i["part_id"] == part_a.id)

    client.post(f"/api/orders/{order_id}/links", json={
        "order_todo_item_id": a_todo_id,
        "purchase_order_item_id": poi_a_id,
    })

    # Delete the linked item
    resp = client.delete(f"/api/purchase-orders/{po_id}/items/{poi_a_id}")
    assert resp.status_code == 204


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


# --- Batch tables ---

def test_batch_tables_exist(db):
    """Verify new batch tables are created."""
    from sqlalchemy import inspect
    inspector = inspect(db.bind)
    assert inspector.has_table("order_todo_batch")
    assert inspector.has_table("order_todo_batch_jewelry")
    # Verify batch_id column on order_todo_item
    cols = [c["name"] for c in inspector.get_columns("order_todo_item")]
    assert "batch_id" in cols


# --- Jewelry Status ---

def test_jewelry_status_waiting_parts(client, db):
    """Jewelry with insufficient part stock → 等待配件备齐."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    resp = client.get(f"/api/orders/{order_id}/jewelry-status")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "等待配件备齐"


def test_jewelry_status_waiting_handcraft(client, db):
    """Jewelry with sufficient part stock but no handcraft link → 等待发往手工."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    from models.bom import Bom
    bom_rows = db.query(Bom).filter_by(jewelry_id=jewelry.id).all()
    order_item = db.query(OrderItem).filter_by(order_id=order_id).first()
    for bom in bom_rows:
        needed = float(bom.qty_per_unit) * order_item.quantity
        add_stock(db, "part", bom.part_id, needed + 10, "test stock")
    db.flush()
    resp = client.get(f"/api/orders/{order_id}/jewelry-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["status"] == "等待发往手工"


def test_jewelry_status_completed(client, db):
    """Jewelry with sufficient jewelry stock → 完成备货."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    order_item = db.query(OrderItem).filter_by(order_id=order_id).first()
    add_stock(db, "jewelry", jewelry.id, order_item.quantity + 5, "test stock")
    db.flush()
    resp = client.get(f"/api/orders/{order_id}/jewelry-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["status"] == "完成备货"


# --- Jewelry for Batch ---

def test_jewelry_for_batch_all_selectable(client, db):
    """All jewelry selectable when no handcraft orders exist."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    resp = client.get(f"/api/orders/{order_id}/jewelry-for-batch")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    item = data[0]
    assert item["selectable"] is True
    assert item["allocated_quantity"] == 0
    assert item["remaining_quantity"] == item["order_quantity"]


def test_jewelry_for_batch_partially_allocated(client, db):
    """Jewelry partially allocated shows remaining quantity."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    order_item = db.query(OrderItem).filter_by(order_id=order_id).first()
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    hc = HandcraftOrder(id="HC-TEST1", supplier_name="TestSupplier", status="pending")
    db.add(hc)
    db.flush()
    hc_j = HandcraftJewelryItem(
        handcraft_order_id=hc.id,
        jewelry_id=jewelry.id,
        qty=3,
    )
    db.add(hc_j)
    db.flush()
    link = OrderItemLink(order_id=order_id, handcraft_jewelry_item_id=hc_j.id)
    db.add(link)
    db.flush()

    resp = client.get(f"/api/orders/{order_id}/jewelry-for-batch")
    assert resp.status_code == 200
    data = resp.json()
    item = data[0]
    assert item["allocated_quantity"] == 3
    assert item["remaining_quantity"] == order_item.quantity - 3
    assert item["selectable"] is True


def test_jewelry_for_batch_fully_allocated_not_selectable(client, db):
    """Jewelry fully allocated to handcraft → not selectable."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    order_item = db.query(OrderItem).filter_by(order_id=order_id).first()
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    hc = HandcraftOrder(id="HC-TEST2", supplier_name="TestSupplier", status="pending")
    db.add(hc)
    db.flush()
    hc_j = HandcraftJewelryItem(
        handcraft_order_id=hc.id,
        jewelry_id=jewelry.id,
        qty=order_item.quantity,
    )
    db.add(hc_j)
    db.flush()
    link = OrderItemLink(order_id=order_id, handcraft_jewelry_item_id=hc_j.id)
    db.add(link)
    db.flush()

    resp = client.get(f"/api/orders/{order_id}/jewelry-for-batch")
    assert resp.status_code == 200
    data = resp.json()
    item = data[0]
    assert item["selectable"] is False


# --- Create Batch ---

def test_create_batch(client, db):
    """Create a batch with selected jewelry, generates part todo items."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    order_item = db.query(OrderItem).filter_by(order_id=order_id).first()
    resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": order_item.quantity}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["order_id"] == order_id
    assert len(data["jewelries"]) == 1
    assert data["jewelries"][0]["jewelry_id"] == jewelry.id
    assert len(data["items"]) > 0
    for item in data["items"]:
        assert "batch_id" in item


def test_create_batch_invalid_jewelry(client, db):
    """Reject jewelry_id not in the order."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": "SP-NONEXISTENT", "quantity": 10}]},
    )
    assert resp.status_code == 400


def test_get_batches(client, db):
    """Get all batches for an order."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    order_item = db.query(OrderItem).filter_by(order_id=order_id).first()
    client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": order_item.quantity}]},
    )
    resp = client.get(f"/api/orders/{order_id}/todo-batches")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["batches"]) == 1
    batch = data["batches"][0]
    assert batch["order_id"] == order_id
    assert len(batch["jewelries"]) == 1
    assert len(batch["items"]) > 0


# --- Link Supplier ---

def test_link_supplier_creates_handcraft_order(client, db):
    """Linking supplier creates HC order with migrated parts and jewelry."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    # Stock must be sufficient for link_supplier
    add_stock(db, "part", part_a.id, 1000, "入库")
    add_stock(db, "part", part_b.id, 100, "入库")
    batch_resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": db.query(OrderItem).filter_by(order_id=order_id).first().quantity}]},
    )
    batch_id = batch_resp.json()["id"]

    resp = client.post(
        f"/api/orders/{order_id}/todo-batch/{batch_id}/link-supplier",
        json={"supplier_name": "王师傅手工坊"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "handcraft_order_id" in data
    hc_id = data["handcraft_order_id"]
    assert hc_id.startswith("HC-")

    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
    hc = db.query(HandcraftOrder).filter_by(id=hc_id).first()
    assert hc is not None
    assert hc.supplier_name == "王师傅手工坊"
    assert hc.status == "pending"

    hc_parts = db.query(HandcraftPartItem).filter_by(handcraft_order_id=hc_id).all()
    assert len(hc_parts) > 0

    hc_jewelries = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=hc_id).all()
    assert len(hc_jewelries) == 1
    assert hc_jewelries[0].jewelry_id == jewelry.id

    # Verify batch now has handcraft_order_id and items show is_allocated
    batches_resp = client.get(f"/api/orders/{order_id}/todo-batches")
    batch = batches_resp.json()["batches"][0]
    assert batch["handcraft_order_id"] == hc_id
    assert batch["supplier_name"] == "王师傅手工坊"
    # After allocation, items should show is_allocated=True, stock/gap=None
    for item in batch["items"]:
        assert item["is_allocated"] is True
        assert item["stock_qty"] is None
        assert item["gap"] is None


def test_batch_items_unallocated_show_stock(client, db):
    """Unallocated batch items show stock_qty and gap, is_allocated=False."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    add_stock(db, "part", part_a.id, 500, "入库")  # less than needed (1000)
    batch_resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": db.query(OrderItem).filter_by(order_id=order_id).first().quantity}]},
    )
    batches_resp = client.get(f"/api/orders/{order_id}/todo-batches")
    batch = batches_resp.json()["batches"][0]
    for item in batch["items"]:
        assert item["is_allocated"] is False
        assert item["stock_qty"] is not None
        assert item["gap"] is not None


def test_link_supplier_insufficient_stock(client, db):
    """Link supplier fails when stock is insufficient."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    batch_resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": db.query(OrderItem).filter_by(order_id=order_id).first().quantity}]},
    )
    batch_id = batch_resp.json()["id"]
    # No stock added — should fail
    resp = client.post(
        f"/api/orders/{order_id}/todo-batch/{batch_id}/link-supplier",
        json={"supplier_name": "王师傅手工坊"},
    )
    assert resp.status_code == 400
    assert "库存数量不足" in resp.json()["detail"]


def test_link_supplier_double_allocation_rejected(client, db):
    """Second batch allocation fails when pending HC already reserves the stock."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    # Stock enough for ~60% of order (A: 600/1000, B: 60/100)
    add_stock(db, "part", part_a.id, 600, "入库")
    add_stock(db, "part", part_b.id, 60, "入库")

    qty = db.query(OrderItem).filter_by(order_id=order_id).first().quantity
    # Create and allocate first batch (50 qty)
    b1 = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": qty // 2}]},
    )
    batch1_id = b1.json()["id"]
    resp1 = client.post(
        f"/api/orders/{order_id}/todo-batch/{batch1_id}/link-supplier",
        json={"supplier_name": "商家A"},
    )
    assert resp1.status_code == 200

    # Create second batch (another 50 qty) — stock is now fully reserved by first
    b2 = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": qty - qty // 2}]},
    )
    batch2_id = b2.json()["id"]
    resp2 = client.post(
        f"/api/orders/{order_id}/todo-batch/{batch2_id}/link-supplier",
        json={"supplier_name": "商家B"},
    )
    assert resp2.status_code == 400
    assert "库存数量不足" in resp2.json()["detail"]
    assert "已预留" in resp2.json()["detail"]


def test_link_supplier_already_linked(client, db):
    """Cannot link supplier to an already-linked batch."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    add_stock(db, "part", part_a.id, 1000, "入库")
    add_stock(db, "part", part_b.id, 100, "入库")
    batch_resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": db.query(OrderItem).filter_by(order_id=order_id).first().quantity}]},
    )
    batch_id = batch_resp.json()["id"]
    client.post(
        f"/api/orders/{order_id}/todo-batch/{batch_id}/link-supplier",
        json={"supplier_name": "王师傅手工坊"},
    )
    resp = client.post(
        f"/api/orders/{order_id}/todo-batch/{batch_id}/link-supplier",
        json={"supplier_name": "另一个商家"},
    )
    assert resp.status_code == 400


# --- Delete Batch ---


def test_delete_batch_unlinked(client, db):
    """Delete a batch that has not been linked to a supplier."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    qty = db.query(OrderItem).filter_by(order_id=order_id).first().quantity
    batch_resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": qty}]},
    )
    batch_id = batch_resp.json()["id"]

    resp = client.delete(f"/api/orders/{order_id}/todo-batch/{batch_id}")
    assert resp.status_code == 204

    # Batch no longer exists
    batches = client.get(f"/api/orders/{order_id}/todo-batches").json()["batches"]
    assert len(batches) == 0

    # Jewelry is available again for new batch
    for_batch = client.get(f"/api/orders/{order_id}/jewelry-for-batch").json()
    assert for_batch[0]["remaining_quantity"] == qty


def test_delete_batch_pending_handcraft(client, db):
    """Delete a batch linked to a pending handcraft order cleans up HC order."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    add_stock(db, "part", part_a.id, 1000, "入库")
    add_stock(db, "part", part_b.id, 100, "入库")
    qty = db.query(OrderItem).filter_by(order_id=order_id).first().quantity
    batch_resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": qty}]},
    )
    batch_id = batch_resp.json()["id"]
    link_resp = client.post(
        f"/api/orders/{order_id}/todo-batch/{batch_id}/link-supplier",
        json={"supplier_name": "商家A"},
    )
    hc_id = link_resp.json()["handcraft_order_id"]

    resp = client.delete(f"/api/orders/{order_id}/todo-batch/{batch_id}")
    assert resp.status_code == 204

    # HC order should be deleted
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
    assert db.query(HandcraftOrder).filter_by(id=hc_id).first() is None
    assert db.query(HandcraftPartItem).filter_by(handcraft_order_id=hc_id).count() == 0
    assert db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=hc_id).count() == 0

    # Links should be cleaned up
    assert db.query(OrderItemLink).filter_by(order_todo_item_id=None).filter(
        OrderItemLink.handcraft_part_item_id.isnot(None)
    ).count() == 0


def test_delete_batch_preserves_manual_hc_items(client, db):
    """Deleting a batch only removes batch-created HC items, not manually-added ones."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    add_stock(db, "part", part_a.id, 1000, "入库")
    add_stock(db, "part", part_b.id, 100, "入库")
    qty = db.query(OrderItem).filter_by(order_id=order_id).first().quantity
    batch_resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": qty}]},
    )
    batch_id = batch_resp.json()["id"]
    link_resp = client.post(
        f"/api/orders/{order_id}/todo-batch/{batch_id}/link-supplier",
        json={"supplier_name": "商家C"},
    )
    hc_id = link_resp.json()["handcraft_order_id"]

    # Manually add an extra part item to the HC order
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
    extra_part = HandcraftPartItem(
        handcraft_order_id=hc_id, part_id=part_a.id, qty=50,
    )
    db.add(extra_part)
    db.flush()
    extra_part_id = extra_part.id

    # Delete batch
    resp = client.delete(f"/api/orders/{order_id}/todo-batch/{batch_id}")
    assert resp.status_code == 204

    # HC order should still exist (has the manually-added item)
    hc = db.query(HandcraftOrder).filter_by(id=hc_id).first()
    assert hc is not None

    # The manually-added item should still be there
    assert db.query(HandcraftPartItem).filter_by(id=extra_part_id).first() is not None

    # Batch-created items should be gone
    batch_created_parts = db.query(HandcraftPartItem).filter_by(
        handcraft_order_id=hc_id
    ).all()
    assert len(batch_created_parts) == 1  # only the manually-added one
    assert batch_created_parts[0].id == extra_part_id


def test_delete_batch_preserves_manual_hc_jewelry(client, db):
    """Deleting a batch preserves manually-added HC jewelry items linked to the order."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    add_stock(db, "part", part_a.id, 1000, "入库")
    add_stock(db, "part", part_b.id, 100, "入库")
    qty = db.query(OrderItem).filter_by(order_id=order_id).first().quantity
    batch_resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": qty}]},
    )
    batch_id = batch_resp.json()["id"]
    link_resp = client.post(
        f"/api/orders/{order_id}/todo-batch/{batch_id}/link-supplier",
        json={"supplier_name": "商家D"},
    )
    hc_id = link_resp.json()["handcraft_order_id"]

    # Manually add an extra jewelry item with the SAME jewelry_id to HC order
    # This is the critical case: same jewelry_id should NOT be deleted
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    extra_jewelry = HandcraftJewelryItem(
        handcraft_order_id=hc_id, jewelry_id=jewelry.id, qty=5,
    )
    db.add(extra_jewelry)
    db.flush()
    extra_jewelry_id = extra_jewelry.id
    # Link the manual jewelry to the order
    manual_link = OrderItemLink(order_id=order_id, handcraft_jewelry_item_id=extra_jewelry.id)
    db.add(manual_link)
    db.flush()

    # Delete batch
    resp = client.delete(f"/api/orders/{order_id}/todo-batch/{batch_id}")
    assert resp.status_code == 204

    # HC order should still exist
    assert db.query(HandcraftOrder).filter_by(id=hc_id).first() is not None
    # Manual jewelry item should still be there
    assert db.query(HandcraftJewelryItem).filter_by(id=extra_jewelry_id).first() is not None
    # Its link should still exist
    assert db.query(OrderItemLink).filter_by(handcraft_jewelry_item_id=extra_jewelry_id).first() is not None


def test_delete_batch_processing_rejected(client, db):
    """Cannot delete a batch whose handcraft order has been sent."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    add_stock(db, "part", part_a.id, 2000, "入库")
    add_stock(db, "part", part_b.id, 200, "入库")
    qty = db.query(OrderItem).filter_by(order_id=order_id).first().quantity
    batch_resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": qty}]},
    )
    batch_id = batch_resp.json()["id"]
    link_resp = client.post(
        f"/api/orders/{order_id}/todo-batch/{batch_id}/link-supplier",
        json={"supplier_name": "商家B"},
    )
    hc_id = link_resp.json()["handcraft_order_id"]
    # Send the handcraft order (stock deducted)
    client.post(f"/api/handcraft/{hc_id}/send")

    resp = client.delete(f"/api/orders/{order_id}/todo-batch/{batch_id}")
    assert resp.status_code == 400
    assert "已发出" in resp.json()["detail"] or "无法删除" in resp.json()["detail"]


def test_delete_batch_not_found(client, db):
    """Delete non-existent batch returns 400."""
    order_id, *_ = _setup_order_with_bom(db, client)
    resp = client.delete(f"/api/orders/{order_id}/todo-batch/9999")
    assert resp.status_code == 400


# --- Progress (new logic) ---

def test_order_progress_new_logic(client, db):
    """Progress: x = 完成备货 jewelry count, y = distinct jewelry count."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    # No jewelry stock → 0 completed
    resp = client.get(f"/api/orders/{order_id}/progress")
    assert resp.status_code == 200
    data = resp.json()
    assert data["completed"] == 0
    assert data["total"] == 1  # 1 distinct jewelry

    # Add enough jewelry stock
    order_item = db.query(OrderItem).filter_by(order_id=order_id).first()
    add_stock(db, "jewelry", jewelry.id, order_item.quantity, "test")
    db.flush()
    resp = client.get(f"/api/orders/{order_id}/progress")
    data = resp.json()
    assert data["completed"] == 1
    assert data["total"] == 1


# --- Parts Summary (with remaining_qty) ---

def test_parts_summary_with_remaining(client, db):
    """Parts summary returns total_qty and remaining_qty."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    resp = client.get(f"/api/orders/{order_id}/parts-summary")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    for item in data:
        assert "total_qty" in item
        assert "remaining_qty" in item
        assert "part_id" in item


# --- Batch PDF Export ---

def test_download_batch_pdf(client, db):
    """Download PDF for a specific batch."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    batch_resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": db.query(OrderItem).filter_by(order_id=order_id).first().quantity}]},
    )
    batch_id = batch_resp.json()["id"]
    resp = client.get(f"/api/orders/{order_id}/todo-pdf?batch_id={batch_id}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


# --- Bug fix: create_batch must reject non-selectable jewelry ---

def test_create_batch_rejects_fully_allocated(client, db):
    """Cannot create batch for jewelry that is already fully allocated."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    order_item = db.query(OrderItem).filter_by(order_id=order_id).first()
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    hc = HandcraftOrder(id="HC-FULL", supplier_name="TestSupplier", status="pending")
    db.add(hc)
    db.flush()
    hc_j = HandcraftJewelryItem(
        handcraft_order_id=hc.id,
        jewelry_id=jewelry.id,
        qty=order_item.quantity,  # fully allocated
    )
    db.add(hc_j)
    db.flush()
    link = OrderItemLink(order_id=order_id, handcraft_jewelry_item_id=hc_j.id)
    db.add(link)
    db.flush()

    # Should be rejected — jewelry is fully allocated
    resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": db.query(OrderItem).filter_by(order_id=order_id).first().quantity}]},
    )
    assert resp.status_code == 400


def test_create_batch_rejects_completed_jewelry(client, db):
    """Cannot create batch for jewelry with status 完成备货."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    order_item = db.query(OrderItem).filter_by(order_id=order_id).first()
    add_stock(db, "jewelry", jewelry.id, order_item.quantity, "test")
    db.flush()

    resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": db.query(OrderItem).filter_by(order_id=order_id).first().quantity}]},
    )
    assert resp.status_code == 400


# --- Bug fix: same jewelry_id multiple rows in an order ---

def _setup_order_with_duplicate_jewelry(db, client):
    """Create order with the same jewelry appearing twice (different prices)."""
    part_a = create_part(db, {"name": "A珠", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "项链X", "retail_price": 100.0, "category": "单件"})
    set_bom(db, jewelry.id, part_a.id, 5)  # 每件需要 5 颗 A珠

    resp = client.post("/api/orders/", json={
        "customer_name": "重复饰品客户",
        "items": [
            {"jewelry_id": jewelry.id, "quantity": 10, "unit_price": 50.0},
            {"jewelry_id": jewelry.id, "quantity": 20, "unit_price": 45.0},
        ],
    })
    assert resp.status_code == 201
    order_id = resp.json()["id"]
    return order_id, part_a, jewelry


def test_jewelry_status_duplicate_rows_aggregates(client, db):
    """When same jewelry appears twice, status uses aggregated quantity."""
    order_id, part_a, jewelry = _setup_order_with_duplicate_jewelry(db, client)
    # Total qty = 10 + 20 = 30. Add jewelry stock = 25 (not enough)
    add_stock(db, "jewelry", jewelry.id, 25, "test")
    db.flush()
    resp = client.get(f"/api/orders/{order_id}/jewelry-status")
    assert resp.status_code == 200
    data = resp.json()
    # Should have 1 entry (aggregated), not 2
    assert len(data) == 1
    assert data[0]["quantity"] == 30
    assert data[0]["status"] == "等待配件备齐"  # 25 < 30

    # Add enough to reach 30
    add_stock(db, "jewelry", jewelry.id, 5, "test")
    db.flush()
    resp = client.get(f"/api/orders/{order_id}/jewelry-status")
    data = resp.json()
    assert data[0]["status"] == "完成备货"


def test_progress_duplicate_rows(client, db):
    """Progress with duplicate jewelry rows counts distinct jewelry types."""
    order_id, part_a, jewelry = _setup_order_with_duplicate_jewelry(db, client)
    resp = client.get(f"/api/orders/{order_id}/progress")
    data = resp.json()
    assert data["total"] == 1  # 1 distinct jewelry
    assert data["completed"] == 0


def test_parts_summary_duplicate_rows(client, db):
    """Parts summary with duplicate rows aggregates correctly."""
    order_id, part_a, jewelry = _setup_order_with_duplicate_jewelry(db, client)
    resp = client.get(f"/api/orders/{order_id}/parts-summary")
    data = resp.json()
    assert len(data) == 1
    # Total = 5 * (10 + 20) = 150
    assert data[0]["total_qty"] == 150.0


def test_create_batch_duplicate_rows_uses_total(client, db):
    """Create batch with duplicate jewelry rows uses aggregated quantity."""
    order_id, part_a, jewelry = _setup_order_with_duplicate_jewelry(db, client)
    # Total aggregated = 10 + 20 = 30, request all 30
    resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": 30}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["jewelries"][0]["quantity"] == 30
    # BOM parts: 5 * 30 = 150
    assert data["items"][0]["required_qty"] == 150.0


def test_create_batch_partial_quantity(client, db):
    """Create batch with partial quantity (less than remaining)."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    # Order has 100 units, request only 40
    resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": 40}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["jewelries"][0]["quantity"] == 40
    # BOM: part_a needs 10 per unit → 400, part_b needs 1 per unit → 40
    part_a_item = next(i for i in data["items"] if i["part_id"] == part_a.id)
    assert part_a_item["required_qty"] == 400.0


def test_create_batch_exceeding_quantity_rejected(client, db):
    """Reject batch with quantity exceeding remaining."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    # Order has 100 units, try 200
    resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": 200}]},
    )
    assert resp.status_code == 400


# --- Bug fix: remaining_qty should use allocated qty, not status ---

def test_parts_summary_remaining_partial_handcraft(client, db):
    """remaining_qty should deduct only allocated qty, not full order qty."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    # Order has 100 units. Allocate only 30 to handcraft.
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    hc = HandcraftOrder(id="HC-PART", supplier_name="TestSupplier", status="pending")
    db.add(hc)
    db.flush()
    hc_j = HandcraftJewelryItem(
        handcraft_order_id=hc.id,
        jewelry_id=jewelry.id,
        qty=30,
    )
    db.add(hc_j)
    db.flush()
    link = OrderItemLink(order_id=order_id, handcraft_jewelry_item_id=hc_j.id)
    db.add(link)
    db.flush()

    # Status should be 等待手工返回 (has handcraft link, not enough jewelry stock)
    status_resp = client.get(f"/api/orders/{order_id}/jewelry-status")
    assert status_resp.json()[0]["status"] == "等待手工返回"

    resp = client.get(f"/api/orders/{order_id}/parts-summary")
    data = resp.json()
    # BOM: part_a needs 10 per unit, part_b needs 1 per unit
    # Total: part_a = 1000, part_b = 100
    # Allocated 30 units → deduct: part_a = 300, part_b = 30
    # Remaining: part_a = 700, part_b = 70 (NOT 0!)
    a_summary = next(d for d in data if d["part_id"] == part_a.id)
    b_summary = next(d for d in data if d["part_id"] == part_b.id)
    assert a_summary["total_qty"] == 1000.0
    assert a_summary["remaining_qty"] == 700.0  # not 0
    assert b_summary["total_qty"] == 100.0
    assert b_summary["remaining_qty"] == 70.0  # not 0


# --- Bug fix: duplicate jewelry_ids in create_batch request ---

def test_create_batch_rejects_empty_items(client, db):
    """Empty items should be rejected."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": []},
    )
    assert resp.status_code == 422  # pydantic min_length=1


def test_create_batch_rejects_duplicate_jewelry_ids(client, db):
    """Duplicate jewelry_ids in request should be rejected."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [
            {"jewelry_id": jewelry.id, "quantity": 5},
            {"jewelry_id": jewelry.id, "quantity": 5},
        ]},
    )
    assert resp.status_code == 400


# --- Bug fix: remaining_qty must use per-jewelry allocated qty ---

def test_parts_summary_remaining_with_sufficient_parts_partial_batch(client, db):
    """Even when all parts have sufficient stock (等待发往手工),
    remaining_qty should deduct only allocated qty, not full order qty.
    Scenario: 100 units ordered, 30 sent to handcraft, all parts in stock.
    remaining_qty should be (100-30)*bom = 70*bom, not 0.
    """
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    order_item = db.query(OrderItem).filter_by(order_id=order_id).first()
    total_qty = order_item.quantity  # 100

    # Add enough part stock so all BOM parts are sufficient
    from models.bom import Bom
    bom_rows = db.query(Bom).filter_by(jewelry_id=jewelry.id).all()
    for bom in bom_rows:
        needed = float(bom.qty_per_unit) * total_qty
        add_stock(db, "part", bom.part_id, needed + 100, "test stock")
    db.flush()

    # Now create a partial handcraft allocation of 30 units
    from models.handcraft_order import HandcraftOrder, HandcraftJewelryItem
    hc = HandcraftOrder(id="HC-PARTIAL2", supplier_name="TestHC", status="pending")
    db.add(hc)
    db.flush()
    hc_j = HandcraftJewelryItem(
        handcraft_order_id=hc.id,
        jewelry_id=jewelry.id,
        qty=30,
    )
    db.add(hc_j)
    db.flush()
    link = OrderItemLink(order_id=order_id, handcraft_jewelry_item_id=hc_j.id)
    db.add(link)
    db.flush()

    # Status should be 等待手工返回 (has handcraft link)
    status_resp = client.get(f"/api/orders/{order_id}/jewelry-status")
    assert status_resp.json()[0]["status"] == "等待手工返回"

    resp = client.get(f"/api/orders/{order_id}/parts-summary")
    data = resp.json()
    # Only 30 allocated → deduct 30 units worth of BOM
    # part_a: total=1000, deduct=30*10=300, remaining=700
    a_summary = next(d for d in data if d["part_id"] == part_a.id)
    assert a_summary["remaining_qty"] == 700.0

    # part_b: total=100, deduct=30*1=30, remaining=70
    b_summary = next(d for d in data if d["part_id"] == part_b.id)
    assert b_summary["remaining_qty"] == 70.0


def test_parts_summary_remaining_no_allocation(client, db):
    """When parts are sufficient but nothing allocated, remaining = total.
    (等待发往手工 with 0 allocated should NOT deduct anything)
    """
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    order_item = db.query(OrderItem).filter_by(order_id=order_id).first()

    # Add enough part stock
    from models.bom import Bom
    bom_rows = db.query(Bom).filter_by(jewelry_id=jewelry.id).all()
    for bom in bom_rows:
        needed = float(bom.qty_per_unit) * order_item.quantity
        add_stock(db, "part", bom.part_id, needed + 100, "test stock")
    db.flush()

    # Status = 等待发往手工, allocated = 0
    status_resp = client.get(f"/api/orders/{order_id}/jewelry-status")
    assert status_resp.json()[0]["status"] == "等待发往手工"

    resp = client.get(f"/api/orders/{order_id}/parts-summary")
    data = resp.json()
    # Nothing allocated → remaining = total
    a_summary = next(d for d in data if d["part_id"] == part_a.id)
    assert a_summary["remaining_qty"] == a_summary["total_qty"]


# --- 饰品回收自动消耗配件 ---

def test_jewelry_receive_consumes_parts(client, db):
    """When jewelry is received back, corresponding parts should be auto-consumed via BOM."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    # BOM: part_a x10, part_b x1 per jewelry. Order qty=100.

    # Add part stock and create handcraft order via batch flow
    add_stock(db, "part", part_a.id, 2000, "入库")
    add_stock(db, "part", part_b.id, 200, "入库")
    db.flush()

    # Create batch and link supplier
    batch_resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": 100}]},
    )
    batch_id = batch_resp.json()["id"]
    link_resp = client.post(
        f"/api/orders/{order_id}/todo-batch/{batch_id}/link-supplier",
        json={"supplier_name": "手工商家A"},
    )
    hc_id = link_resp.json()["handcraft_order_id"]

    # Send the handcraft order
    client.post(f"/api/handcraft/{hc_id}/send")

    # Get the jewelry item id
    from models.handcraft_order import HandcraftJewelryItem, HandcraftPartItem
    hc_j = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=hc_id).first()
    assert hc_j is not None

    # Receive 60 jewelry (60% of 100)
    receipt_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "手工商家A",
        "items": [{"handcraft_jewelry_item_id": hc_j.id, "qty": 60, "price": 5.0}],
    })
    assert receipt_resp.status_code == 201

    # Check part items: should be auto-consumed proportionally
    db.expire_all()
    hc_parts = db.query(HandcraftPartItem).filter_by(handcraft_order_id=hc_id).all()
    part_a_item = next(p for p in hc_parts if p.part_id == part_a.id)
    part_b_item = next(p for p in hc_parts if p.part_id == part_b.id)

    # part_a: BOM=10 per jewelry, 60 received → consumed 600, qty was 1000, received_qty=600
    assert float(part_a_item.received_qty) == 600.0
    # part_b: BOM=1 per jewelry, 60 received → consumed 60, qty was 100, received_qty=60
    assert float(part_b_item.received_qty) == 60.0

    # Receive remaining 40 jewelry
    receipt_resp2 = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "手工商家A",
        "items": [{"handcraft_jewelry_item_id": hc_j.id, "qty": 40, "price": 5.0}],
    })
    assert receipt_resp2.status_code == 201

    db.expire_all()
    hc_parts = db.query(HandcraftPartItem).filter_by(handcraft_order_id=hc_id).all()
    part_a_item = next(p for p in hc_parts if p.part_id == part_a.id)
    part_b_item = next(p for p in hc_parts if p.part_id == part_b.id)

    # All consumed
    assert float(part_a_item.received_qty) == 1000.0
    assert part_a_item.status == "已收回"
    assert float(part_b_item.received_qty) == 100.0
    assert part_b_item.status == "已收回"


def test_jewelry_receive_consumes_parts_capped(client, db):
    """Part consumption is capped at part's remaining receivable qty."""
    part_a = create_part(db, {"name": "大珠", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "手链Z", "retail_price": 50.0, "category": "单件"})
    from services.bom import set_bom
    set_bom(db, jewelry.id, part_a.id, 20)  # 每件需要20颗

    add_stock(db, "part", part_a.id, 500, "入库")
    db.flush()

    # Create handcraft order: send only 100 parts but BOM says 10×20=200
    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
    from services._helpers import _next_id
    hc_id = _next_id(db, HandcraftOrder, "HC")
    hc = HandcraftOrder(id=hc_id, supplier_name="手工B", status="pending")
    db.add(hc)
    db.flush()
    hc_p = HandcraftPartItem(handcraft_order_id=hc_id, part_id=part_a.id, qty=100, status="未送出")
    hc_j = HandcraftJewelryItem(handcraft_order_id=hc_id, jewelry_id=jewelry.id, qty=10, status="未送出")
    db.add(hc_p)
    db.add(hc_j)
    db.flush()

    # Send the order
    client.post(f"/api/handcraft/{hc_id}/send")
    db.expire_all()

    # Receive all 10 jewelry. BOM says 20×10=200 parts consumed, but only 100 sent.
    receipt_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "手工B",
        "items": [{"handcraft_jewelry_item_id": hc_j.id, "qty": 10, "price": 3.0}],
    })
    assert receipt_resp.status_code == 201

    db.expire_all()
    hc_p = db.query(HandcraftPartItem).filter_by(handcraft_order_id=hc_id, part_id=part_a.id).first()
    # Capped at 100 (the sent qty), not 200
    assert float(hc_p.received_qty) == 100.0
    assert hc_p.status == "已收回"


def test_jewelry_receive_reverse_restores_parts(client, db):
    """Deleting a receipt should reverse the auto-consumed parts."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    add_stock(db, "part", part_a.id, 2000, "入库")
    add_stock(db, "part", part_b.id, 200, "入库")
    db.flush()

    batch_resp = client.post(
        f"/api/orders/{order_id}/todo-batch",
        json={"items": [{"jewelry_id": jewelry.id, "quantity": 100}]},
    )
    batch_id = batch_resp.json()["id"]
    link_resp = client.post(
        f"/api/orders/{order_id}/todo-batch/{batch_id}/link-supplier",
        json={"supplier_name": "手工商家C"},
    )
    hc_id = link_resp.json()["handcraft_order_id"]
    client.post(f"/api/handcraft/{hc_id}/send")

    from models.handcraft_order import HandcraftJewelryItem, HandcraftPartItem
    hc_j = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=hc_id).first()

    # Receive 50 jewelry
    receipt_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "手工商家C",
        "items": [{"handcraft_jewelry_item_id": hc_j.id, "qty": 50, "price": 5.0}],
    })
    assert receipt_resp.status_code == 201
    receipt_id = receipt_resp.json()["id"]

    db.expire_all()
    pa = db.query(HandcraftPartItem).filter_by(handcraft_order_id=hc_id, part_id=part_a.id).first()
    assert float(pa.received_qty) == 500.0  # 50 * 10

    # Delete the receipt → should reverse
    resp = client.delete(f"/api/handcraft-receipts/{receipt_id}")
    assert resp.status_code == 204

    db.expire_all()
    pa = db.query(HandcraftPartItem).filter_by(handcraft_order_id=hc_id, part_id=part_a.id).first()
    assert float(pa.received_qty) == 0.0
    assert pa.status == "制作中"

    pb = db.query(HandcraftPartItem).filter_by(handcraft_order_id=hc_id, part_id=part_b.id).first()
    assert float(pb.received_qty) == 0.0
    assert pb.status == "制作中"


def test_jewelry_receive_duplicate_part_rows_not_double_counted(client, db):
    """Same part_id in multiple rows should not double-consume."""
    part_a = create_part(db, {"name": "铜珠", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "耳环Y", "retail_price": 30.0, "category": "单件"})
    from services.bom import set_bom
    set_bom(db, jewelry.id, part_a.id, 5)  # 每件需要5颗

    add_stock(db, "part", part_a.id, 500, "入库")
    db.flush()

    from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
    from services._helpers import _next_id
    hc_id = _next_id(db, HandcraftOrder, "HC")
    hc = HandcraftOrder(id=hc_id, supplier_name="手工D", status="pending")
    db.add(hc)
    db.flush()
    # Two rows with same part_id, qty=10 each
    hc_p1 = HandcraftPartItem(handcraft_order_id=hc_id, part_id=part_a.id, qty=10, status="未送出")
    hc_p2 = HandcraftPartItem(handcraft_order_id=hc_id, part_id=part_a.id, qty=10, status="未送出")
    hc_j = HandcraftJewelryItem(handcraft_order_id=hc_id, jewelry_id=jewelry.id, qty=2, status="未送出")
    db.add_all([hc_p1, hc_p2, hc_j])
    db.flush()

    client.post(f"/api/handcraft/{hc_id}/send")
    db.expire_all()

    # Receive 2 jewelry. BOM=5*2=10 total consumption across both rows.
    receipt_resp = client.post("/api/handcraft-receipts/", json={
        "supplier_name": "手工D",
        "items": [{"handcraft_jewelry_item_id": hc_j.id, "qty": 2, "price": 3.0}],
    })
    assert receipt_resp.status_code == 201

    db.expire_all()
    rows = db.query(HandcraftPartItem).filter_by(handcraft_order_id=hc_id, part_id=part_a.id).all()
    total_consumed = sum(float(r.received_qty or 0) for r in rows)
    # Should be 10 total (5*2), NOT 20 (10+10)
    assert total_consumed == 10.0


# --- handcraft_cost batch update ---

def test_batch_update_jewelry_handcraft_cost(client, db):
    """batch-update-costs with field=handcraft_cost should update Jewelry, not Part."""
    order_id, part_a, part_b, jewelry = _setup_order_with_bom(db, client)
    resp = client.post("/api/parts/batch-update-costs", json={
        "updates": [{
            "part_id": jewelry.id,
            "field": "handcraft_cost",
            "value": 8.5,
            "source_id": "HR-TEST",
        }],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated_count"] == 1
    assert data["results"][0]["updated"] is True

    # Verify jewelry.handcraft_cost was actually set
    from models.jewelry import Jewelry
    db.expire_all()
    j = db.get(Jewelry, jewelry.id)
    assert float(j.handcraft_cost) == 8.5


# --- Extra Info ---


def test_update_extra_info(client, db):
    """PATCH extra-info updates barcode, mark, and note fields."""
    order_id, *_ = _setup_order_with_bom(db, client)
    resp = client.patch(
        f"/api/orders/{order_id}/extra-info",
        json={
            "barcode_text": "EAN-13, 695开头",
            "mark_text": "客户唛头：ABC Trading",
            "note": "注意包装要求",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["barcode_text"] == "EAN-13, 695开头"
    assert data["mark_text"] == "客户唛头：ABC Trading"
    assert data["note"] == "注意包装要求"
    assert data["barcode_image"] is None
    assert data["mark_image"] is None


def test_update_extra_info_partial(client, db):
    """PATCH extra-info with partial fields only updates those fields."""
    order_id, *_ = _setup_order_with_bom(db, client)
    # Set initial values
    client.patch(
        f"/api/orders/{order_id}/extra-info",
        json={"barcode_text": "初始条码", "note": "初始备注"},
    )
    # Partial update — only update note
    resp = client.patch(
        f"/api/orders/{order_id}/extra-info",
        json={"note": "更新备注"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["barcode_text"] == "初始条码"  # unchanged
    assert data["note"] == "更新备注"  # updated


def test_update_extra_info_with_image(client, db):
    """PATCH extra-info can set image URLs."""
    order_id, *_ = _setup_order_with_bom(db, client)
    resp = client.patch(
        f"/api/orders/{order_id}/extra-info",
        json={
            "barcode_image": "https://oss.example.com/barcode.jpg",
            "mark_image": "https://oss.example.com/mark.jpg",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["barcode_image"] == "https://oss.example.com/barcode.jpg"
    assert data["mark_image"] == "https://oss.example.com/mark.jpg"


def test_update_extra_info_clear_image(client, db):
    """PATCH extra-info can clear image by setting to null."""
    order_id, *_ = _setup_order_with_bom(db, client)
    client.patch(
        f"/api/orders/{order_id}/extra-info",
        json={"barcode_image": "https://oss.example.com/barcode.jpg"},
    )
    resp = client.patch(
        f"/api/orders/{order_id}/extra-info",
        json={"barcode_image": None},
    )
    assert resp.status_code == 200
    assert resp.json()["barcode_image"] is None


def test_get_order_includes_extra_info(client, db):
    """GET order response includes extra info fields."""
    order_id, *_ = _setup_order_with_bom(db, client)
    resp = client.get(f"/api/orders/{order_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "barcode_text" in data
    assert "barcode_image" in data
    assert "mark_text" in data
    assert "mark_image" in data
    assert "note" in data
