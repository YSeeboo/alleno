"""Tests for auth and user management endpoints."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models.user import User
from services.auth import hash_password, verify_password, create_token, decode_token, authenticate
from services.user import create_user, list_users, get_user, update_user, delete_user


# ── service: auth ──────────────────────────────────────────────


def test_hash_and_verify_password():
    hashed = hash_password("secret123")
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)


def test_create_and_decode_token():
    token = create_token(42, "alice", False)
    payload = decode_token(token)
    assert payload["user_id"] == 42
    assert payload["username"] == "alice"
    assert payload["is_admin"] is False


def test_decode_token_invalid():
    import pytest
    with pytest.raises(Exception):
        decode_token("invalid.token.here")


def test_authenticate_success(db):
    db.add(User(username="bob", password_hash=hash_password("pass"), owner="test", is_admin=False))
    db.flush()
    user = authenticate(db, "bob", "pass")
    assert user is not None
    assert user.username == "bob"


def test_authenticate_wrong_password(db):
    db.add(User(username="bob", password_hash=hash_password("pass"), owner="test", is_admin=False))
    db.flush()
    assert authenticate(db, "bob", "wrong") is None


def test_authenticate_inactive_user(db):
    db.add(User(username="bob", password_hash=hash_password("pass"), owner="test", is_active=False))
    db.flush()
    assert authenticate(db, "bob", "pass") is None


# ── service: user CRUD ─────────────────────────────────────────


def test_create_user_duplicate(db):
    import pytest
    admin = User(username="admin", password_hash="x", owner="t", is_admin=True)
    db.add(admin)
    db.flush()
    create_user(db, {"username": "alice", "password": "pw", "owner": "o"}, calling_user=admin)
    with pytest.raises(ValueError, match="已存在"):
        create_user(db, {"username": "alice", "password": "pw", "owner": "o"}, calling_user=admin)


def test_create_admin_by_non_admin_rejected(db):
    import pytest
    non_admin = User(username="mgr", password_hash="x", owner="t", permissions=["users"], is_admin=False)
    db.add(non_admin)
    db.flush()
    with pytest.raises(ValueError, match="只有管理员"):
        create_user(db, {"username": "evil", "password": "pw", "owner": "o", "is_admin": True}, calling_user=non_admin)


def test_update_admin_by_non_admin_rejected(db):
    """Non-admin cannot modify admin user at all (including password reset)."""
    import pytest
    non_admin = User(username="mgr", password_hash="x", owner="t", permissions=["users"], is_admin=False)
    db.add(non_admin)
    admin = User(username="admin", password_hash=hash_password("original"), owner="t", is_admin=True)
    db.add(admin)
    db.flush()
    with pytest.raises(ValueError, match="只有管理员才能修改管理员"):
        update_user(db, admin.id, {"password": "hacked"}, calling_user=non_admin)


def test_update_user_escalate_by_non_admin_rejected(db):
    import pytest
    non_admin = User(username="mgr", password_hash="x", owner="t", permissions=["users"], is_admin=False)
    db.add(non_admin)
    target = User(username="bob", password_hash=hash_password("pw"), owner="t", is_admin=False)
    db.add(target)
    db.flush()
    with pytest.raises(ValueError, match="只有管理员"):
        update_user(db, target.id, {"is_admin": True}, calling_user=non_admin)


def test_update_admin_permissions_ignored(db):
    admin = User(username="admin", password_hash=hash_password("pw"), owner="t", is_admin=True)
    db.add(admin)
    db.flush()
    updated = update_user(db, admin.id, {"permissions": ["parts"], "is_admin": False}, calling_user=admin)
    assert updated.is_admin is True  # unchanged
    assert updated.permissions == []  # unchanged


def test_delete_admin_rejected(db):
    import pytest
    admin = User(username="admin", password_hash="x", owner="t", is_admin=True)
    db.add(admin)
    db.flush()
    with pytest.raises(ValueError, match="不能删除管理员"):
        delete_user(db, admin.id)


def test_delete_user_soft(db):
    user = User(username="bob", password_hash="x", owner="t", is_admin=False)
    db.add(user)
    db.flush()
    delete_user(db, user.id)
    assert get_user(db, user.id) is None  # soft-deleted, not visible
    # But raw query still finds it
    raw = db.query(User).filter(User.id == user.id).first()
    assert raw is not None
    assert raw.is_active is False


def test_list_users_excludes_inactive(db):
    db.add(User(username="active", password_hash="x", owner="t"))
    db.add(User(username="gone", password_hash="x", owner="t", is_active=False))
    db.flush()
    users = list_users(db)
    assert len(users) == 1
    assert users[0].username == "active"


# ── API: auth endpoints ───────────────────────────────────────


def test_api_login_success(client, db):
    db.add(User(username="alice", password_hash=hash_password("pw123"), owner="test"))
    db.flush()
    resp = client.post("/api/auth/login", json={"username": "alice", "password": "pw123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["user"]["username"] == "alice"


def test_api_login_wrong_password(client, db):
    db.add(User(username="alice", password_hash=hash_password("pw123"), owner="test"))
    db.flush()
    resp = client.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
    assert resp.status_code == 401


def test_api_me(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == "test-admin"


# ── API: permission enforcement ────────────────────────────────


def test_parts_requires_auth(client, db):
    """Without the auth override, parts endpoint should require auth."""
    from api.deps import get_current_user
    from main import app
    # Remove the auth override to test real behavior
    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]
    try:
        resp = client.get("/api/parts/")
        assert resp.status_code == 401
    finally:
        # Restore for other tests
        from tests.conftest import _fake_admin
        app.dependency_overrides[get_current_user] = lambda: _fake_admin


def test_parts_forbidden_without_permission(client, db):
    """User without 'parts' permission gets 403."""
    from api.deps import get_current_user
    from main import app
    limited_user = User(id=99, username="limited", password_hash="", owner="t", permissions=["orders"], is_admin=False, is_active=True)
    app.dependency_overrides[get_current_user] = lambda: limited_user
    try:
        resp = client.get("/api/parts/")
        assert resp.status_code == 403
    finally:
        from tests.conftest import _fake_admin
        app.dependency_overrides[get_current_user] = lambda: _fake_admin
