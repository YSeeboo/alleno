import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database as _db_module
from db_safety import assert_safe_test_database_url

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql://allen:allen@localhost:5432/allen_shop_test")

# --- Safety: redirect database.engine to the test DB BEFORE app import ---
# main.py lifespan calls create_all(bind=engine) and ensure_schema_compat()
# using database.engine. Without this patch, those would hit the MAIN database.
assert_safe_test_database_url(TEST_DATABASE_URL, context="pytest test database")
_test_engine = create_engine(TEST_DATABASE_URL)
_db_module.engine = _test_engine
_db_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

import models  # noqa: E402 — registers all ORM classes with Base
from database import Base, get_db  # noqa: E402
from main import app  # noqa: E402
from api.deps import get_current_user  # noqa: E402
from models.user import User  # noqa: E402
from time_utils import now_beijing  # noqa: E402

# A fake admin user returned by the overridden get_current_user dependency
_fake_admin = User(id=0, username="test-admin", password_hash="", owner="test", permissions=[], is_admin=True, is_active=True, created_at=now_beijing())


@pytest.fixture(scope="session")
def engine():
    Base.metadata.create_all(_test_engine)
    yield _test_engine
    Base.metadata.drop_all(_test_engine)


@pytest.fixture
def db(engine):
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))

    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(db):
    """FastAPI TestClient with the test DB injected via dependency override."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: _fake_admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_real_get_db(engine):
    """TestClient that exercises the real get_db() commit/rollback path.

    Unlike `client`, this fixture does NOT inject a shared session — each
    request goes through a fresh get_db() generator, so commit() is called
    on success and rollback() on failure, exactly as in production.
    """
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))

    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def real_get_db():
        db = Session()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = real_get_db
    app.dependency_overrides[get_current_user] = lambda: _fake_admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
