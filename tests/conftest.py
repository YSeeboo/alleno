import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import models  # registers all ORM classes with Base
from database import Base, get_db
from main import app

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql://allen:allen@localhost:5432/allen_shop_test")


@pytest.fixture(scope="session")
def engine():
    if not TEST_DATABASE_URL.startswith("postgresql://") and not TEST_DATABASE_URL.startswith(
        "postgresql+psycopg2://"
    ):
        raise RuntimeError("TEST_DATABASE_URL must use PostgreSQL.")

    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


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
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
