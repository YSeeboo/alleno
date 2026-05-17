"""API + permission tests for cargo-sorting endpoints."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from main import app
from database import Base, get_db
from api.deps import get_current_user
from models.user import User
from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock
from services.handcraft import create_handcraft_order
from time_utils import now_beijing


def _user(perms: list[str], is_admin: bool = False) -> User:
    return User(
        id=99, username="u", password_hash="", owner="t",
        permissions=perms, is_admin=is_admin, is_active=True,
        created_at=now_beijing(),
    )


@pytest.fixture
def client_with_perms(db):
    """Returns a function: (perms_list, is_admin=False) -> TestClient."""
    def _factory(perms, is_admin=False):
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: _user(perms, is_admin)
        return TestClient(app)
    yield _factory
    app.dependency_overrides.clear()


def _setup_part_and_jewelry(db):
    part = create_part(db, {"name": "P1", "category": "小配件", "color": "古铜"})
    add_stock(db, "part", part.id, 100.0, "init")
    jewelry = create_jewelry(db, {"name": "J1", "category": "单件"})
    return part, jewelry


def test_sorting_list_returns_orders_with_breakdown(client_with_perms, db):
    part, jewelry = _setup_part_and_jewelry(db)
    o = create_handcraft_order(
        db, supplier_name="商家A",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1, "customer_name": "王"}],
    )

    c = client_with_perms(["sorting"])
    resp = c.get("/api/handcraft/sorting", params={"supplier_name": "商家A"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_more"] is False
    assert len(body["orders"]) == 1
    assert body["orders"][0]["id"] == o.id
    assert body["orders"][0]["receipt_code"] == o.receipt_code
    assert len(body["orders"][0]["breakdown"]) == 1


def test_sorting_list_pagination(client_with_perms, db):
    from datetime import date, timedelta
    part, jewelry = _setup_part_and_jewelry(db)
    base = date(2026, 1, 1)
    for i in range(16):
        create_handcraft_order(
            db, supplier_name="商家A",
            parts=[{"part_id": part.id, "qty": 5}],
            jewelries=[{"jewelry_id": jewelry.id, "qty": 1, "customer_name": f"C{i}"}],
            created_at=base + timedelta(days=i),
        )

    c = client_with_perms(["sorting"])
    resp = c.get("/api/handcraft/sorting", params={"supplier_name": "商家A", "limit": 15, "offset": 0})
    assert resp.json()["has_more"] is True
    assert len(resp.json()["orders"]) == 15

    resp = c.get("/api/handcraft/sorting", params={"supplier_name": "商家A", "limit": 15, "offset": 15})
    assert resp.json()["has_more"] is False
    assert len(resp.json()["orders"]) == 1


def test_sorting_list_requires_supplier_name(client_with_perms, db):
    c = client_with_perms(["sorting"])
    resp = c.get("/api/handcraft/sorting")
    assert resp.status_code == 422

    resp = c.get("/api/handcraft/sorting", params={"supplier_name": ""})
    assert resp.status_code == 422


def test_sorting_list_unknown_supplier_returns_empty(client_with_perms, db):
    c = client_with_perms(["sorting"])
    resp = c.get("/api/handcraft/sorting", params={"supplier_name": "不存在"})
    assert resp.status_code == 200
    assert resp.json() == {"orders": [], "has_more": False}


def test_sorting_list_requires_sorting_perm(client_with_perms, db):
    c = client_with_perms(["handcraft"])
    resp = c.get("/api/handcraft/sorting", params={"supplier_name": "X"})
    assert resp.status_code == 403


def test_suppliers_with_sorting_returns_filtered_list(client_with_perms, db):
    part, jewelry = _setup_part_and_jewelry(db)
    create_handcraft_order(
        db, supplier_name="商家A",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1, "customer_name": "王"}],
    )
    create_handcraft_order(
        db, supplier_name="商家B",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1}],
    )

    c = client_with_perms(["sorting"])
    resp = c.get("/api/handcraft/suppliers-with-sorting")
    assert resp.status_code == 200
    assert resp.json() == {"suppliers": ["商家A"]}


def test_suppliers_with_sorting_requires_sorting_permission(client_with_perms, db):
    c = client_with_perms(["handcraft"])  # has handcraft but not sorting
    resp = c.get("/api/handcraft/suppliers-with-sorting")
    assert resp.status_code == 403


def test_sorting_by_receipt_code_returns_view(client_with_perms, db):
    part, jewelry = _setup_part_and_jewelry(db)
    o = create_handcraft_order(
        db, supplier_name="商家A",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1, "customer_name": "王"}],
    )

    c = client_with_perms(["sorting"])
    resp = c.get(f"/api/handcraft/sorting/by-receipt-code/{o.receipt_code}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == o.id
    assert body["supplier_name"] == "商家A"
    assert body["receipt_code"] == o.receipt_code
    assert len(body["breakdown"]) == 1
    assert body["breakdown"][0]["entries"][0]["customer_name"] == "王"


def test_sorting_by_receipt_code_is_case_insensitive(client_with_perms, db):
    part, jewelry = _setup_part_and_jewelry(db)
    o = create_handcraft_order(
        db, supplier_name="商家A",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1, "customer_name": "王"}],
    )

    c = client_with_perms(["sorting"])
    # receipt_code is uppercase in storage; try lowercase
    resp = c.get(f"/api/handcraft/sorting/by-receipt-code/{o.receipt_code.lower()}")
    assert resp.status_code == 200
    assert resp.json()["id"] == o.id


def test_sorting_by_receipt_code_404_when_not_found(client_with_perms, db):
    c = client_with_perms(["sorting"])
    resp = c.get("/api/handcraft/sorting/by-receipt-code/ZZZZZ")
    assert resp.status_code == 404


def test_sorting_by_receipt_code_returns_order_with_empty_breakdown(client_with_perms, db):
    """Order exists but has no resolvable customer → still 200, breakdown=[]."""
    part, jewelry = _setup_part_and_jewelry(db)
    o = create_handcraft_order(
        db, supplier_name="商家A",
        parts=[{"part_id": part.id, "qty": 5}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 1}],  # no customer
    )

    c = client_with_perms(["sorting"])
    resp = c.get(f"/api/handcraft/sorting/by-receipt-code/{o.receipt_code}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == o.id
    assert body["breakdown"] == []


def test_sorting_by_receipt_code_requires_sorting_perm(client_with_perms, db):
    c = client_with_perms(["handcraft"])
    resp = c.get("/api/handcraft/sorting/by-receipt-code/ZZZZZ")
    assert resp.status_code == 403
