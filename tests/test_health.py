"""Liveness probes must work without credentials or database access."""

import pytest
from fastapi.testclient import TestClient

import main
from database import get_db


@pytest.fixture
def probe_client(monkeypatch):
    def unavailable(*args, **kwargs):
        raise AssertionError("Liveness probe must not access the database")

    monkeypatch.setattr(main, "SessionLocal", unavailable)
    monkeypatch.setattr(main.engine, "connect", unavailable)
    monkeypatch.setitem(main.app.dependency_overrides, get_db, unavailable)
    # Do not enter the lifespan context: these tests exercise HTTP handlers,
    # not startup schema creation or the destructive business DB fixtures.
    client = TestClient(main.app)
    yield client
    client.close()


@pytest.mark.parametrize("path", ["/health", "/api/health"])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer expired-or-invalid"}])
def test_liveness_is_public_and_database_independent(probe_client, path, headers):
    response = probe_client.get(path, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app": "Allenop"}


@pytest.mark.parametrize("path", ["/health", "/api/health"])
def test_head_liveness(probe_client, path):
    response = probe_client.head(path)
    assert response.status_code == 200
    assert response.content == b""


def test_existing_root_probe_unchanged(probe_client):
    assert probe_client.get("/").json() == {"status": "ok", "app": "Allenop"}


def test_liveness_does_not_turn_unknown_paths_into_success(probe_client):
    assert probe_client.get("/CLodopfuncs.js").status_code == 404
    assert probe_client.get("/api/not-a-real-endpoint").status_code == 404
