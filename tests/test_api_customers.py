"""API tests for the customer name suggest endpoint."""
from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock
from services.order import create_order


def _seed(db):
    part = create_part(db, {"name": "P-CA", "category": "小配件", "color": "古铜"})
    jewelry = create_jewelry(db, {"name": "J-CA", "category": "单件"})
    add_stock(db, "part", part.id, 100.0, "init")
    create_order(db, "张三", [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10}])
    create_order(db, "张三", [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10}])  # dup
    create_order(db, "李四", [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10}])
    create_order(db, "Tom",  [{"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 10}])


def test_get_names_empty(client):
    resp = client.get("/api/customers/names")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_names_dedupes_and_sorts(client, db):
    _seed(db)
    resp = client.get("/api/customers/names")
    assert resp.status_code == 200
    names = resp.json()
    # 张三 only once
    assert names.count("张三") == 1
    assert set(names) == {"张三", "李四", "Tom"}


def test_get_names_query_filter(client, db):
    _seed(db)
    resp = client.get("/api/customers/names", params={"q": "tom"})
    assert resp.status_code == 200
    assert resp.json() == ["Tom"]


def test_get_names_limit(client, db):
    _seed(db)
    resp = client.get("/api/customers/names", params={"limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()) == 2
