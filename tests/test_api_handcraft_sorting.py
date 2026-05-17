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


def test_require_any_permission_allows_when_user_has_one(client_with_perms):
    """直接测一个简单端点：require_any_permission('a', 'b') 允许有 a 或 b 的用户。"""
    from fastapi import APIRouter
    from api.deps import require_any_permission

    router = APIRouter()

    @router.get("/_test_any_perm", dependencies=[require_any_permission("foo", "bar")])
    def _h():
        return {"ok": True}

    app.include_router(router)
    try:
        c = client_with_perms(["bar"])
        assert c.get("/_test_any_perm").status_code == 200

        c = client_with_perms(["foo"])
        assert c.get("/_test_any_perm").status_code == 200

        c = client_with_perms(["baz"])
        assert c.get("/_test_any_perm").status_code == 403

        c = client_with_perms([], is_admin=True)
        assert c.get("/_test_any_perm").status_code == 200
    finally:
        # remove the test route to keep app clean
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/_test_any_perm"]
