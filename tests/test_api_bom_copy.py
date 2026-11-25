from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy.orm import Session

from api.deps import get_current_user
from main import app
from models.user import User
from services import bom


@pytest.fixture
def catalog(client_real_get_db):
    client = client_real_get_db
    source, target, empty = [client.post("/api/jewelries/", json={
        "name": name, "category": "项链", "unit": "条", "retail_price": price, "handcraft_cost": price,
    }).json()["id"] for name, price in [("珍珠长款", 12), ("珍珠短款", 6), ("空用料款", 0)]]
    p1, p2, p3 = [client.post("/api/parts/", json={"name": name, "category": "小配件"}).json()["id"]
                  for name in ["珍珠", "挂扣", "串珠线"]]
    for jewelry, part, qty in [(source, p1, 48), (source, p2, 2), (source, p3, 0.5), (target, p1, 36)]:
        assert client.put(f"/api/bom/{jewelry}/{part}", json={"qty_per_unit": qty}).status_code == 200
    return client, source, target, empty, p1, p2, p3


def contents(client, jewelry):
    return {row["part_id"]: row["qty_per_unit"] for row in client.get(f"/api/bom/{jewelry}").json()}


def payload(source, *rows, source_unit="条", target_unit="条", confirmed=False):
    return {"source_id": source, "source_unit": source_unit, "target_unit": target_unit,
            "unit_confirmed": confirmed, "items": [{"part_id": p, "qty_per_unit": q} for p, q in rows]}


def test_search_and_preview_do_not_write(catalog):
    client, source, target, empty, p1, p2, p3 = catalog
    path = f"/api/bom/{target}/copy-sources"
    first = client.get(path, params={"limit": 1}).json()
    assert first == {"items": [{"id": empty, "name": "空用料款", "unit": "条", "status": "active", "part_count": 0}], "has_more": True}
    assert client.get(path, params={"limit": 1, "offset": 1}).json()["items"][0]["id"] == source
    for query in ["珍珠", source.lower(), f"长款 {source.lower()}"]:
        result = client.get(path, params={"q": query}).json()
        assert [(row["id"], row["part_count"]) for row in result["items"]] == [(source, 3)]
    assert client.get(path, params={"q": "无匹配"}).json() == {"items": [], "has_more": False}

    preview = client.get(f"/api/bom/{target}/copy-preview/{source}").json()
    assert preview["source"]["unit"] == preview["target_unit"] == "条"
    assert {row["part_id"]: row["qty_per_unit"] for row in preview["rows"]} == {p1: 48, p2: 2, p3: 0.5}
    assert client.get(f"/api/bom/{target}/copy-preview/{empty}").json()["rows"] == []
    assert client.get(f"/api/bom/{target}/copy-preview/{target}").status_code == 400
    assert client.get(f"/api/bom/{target}/copy-preview/missing").status_code == 404
    assert contents(client, target) == {p1: 36}


def test_copies_selected_quantities_only_and_is_safe_to_repeat(catalog):
    client, source, target, empty, p1, p2, p3 = catalog
    before = client.get(f"/api/jewelries/{target}").json()
    path = f"/api/bom/{target}/copy"
    request = payload(source, (p1, 48), (p2, "1.2345"))
    response = client.post(path, json=request)
    assert response.status_code == 200, response.text
    assert response.json() == {"added_part_ids": [p2], "skipped_part_ids": [p1]}
    assert client.post(path, json=request).json() == {"added_part_ids": [], "skipped_part_ids": [p1, p2]}
    assert contents(client, target) == {p1: 36, p2: 1.2345}
    assert contents(client, source) == {p1: 48, p2: 2, p3: 0.5}
    after = client.get(f"/api/jewelries/{target}").json()
    for field in ("id", "name", "unit", "retail_price", "wholesale_price", "handcraft_cost"):
        assert after[field] == before[field]
    assert client.post(f"/api/bom/{empty}/copy", json=payload(source, (p3, "0.5"))).json()["added_part_ids"] == [p3]
    assert contents(client, empty) == {p3: 0.5}


def test_invalid_or_stale_request_writes_nothing(catalog):
    client, source, target, empty, p1, p2, p3 = catalog
    path = f"/api/bom/{target}/copy"
    for bad in [0, -1, "0.00001", "1000000", "NaN", "Infinity"]:
        assert client.post(path, json=payload(source, (p2, 1), (p3, bad))).status_code == 422
    assert client.post(path, json=payload(source)).status_code == 422
    assert client.post(path, json=payload(source, (p2, 1), (p2, 2))).status_code == 422
    assert client.post(path, json=payload(source, (p2, 1), ("not-in-source", 1))).status_code == 409
    assert client.post(path, json=payload(empty, (p2, 1))).status_code == 409
    assert client.post(path, json=payload(target, (p1, 1))).status_code == 400
    assert client.post(path, json=payload("missing", (p2, 1))).status_code == 404
    assert client.delete(f"/api/bom/{source}/{p3}").status_code == 204
    assert client.post(path, json=payload(source, (p2, 1), (p3, 1))).status_code == 409
    assert contents(client, target) == {p1: 36}


def test_units_rechecked_and_never_converted(catalog):
    client, source, target, _, p1, p2, p3 = catalog
    path = f"/api/bom/{target}/copy"
    assert client.patch(f"/api/jewelries/{source}", json={"unit": "对"}).status_code == 200
    assert client.post(path, json=payload(source, (p2, "2.5"), confirmed=True)).status_code == 409
    assert client.post(path, json=payload(source, (p2, "2.5"), source_unit="对")).status_code == 400
    assert contents(client, target) == {p1: 36}
    assert client.post(path, json=payload(source, (p2, "2.5"), source_unit="对", confirmed=True)).status_code == 200
    assert client.patch(f"/api/jewelries/{target}", json={"unit": None}).status_code == 200
    assert client.post(path, json=payload(source, (p3, 1), source_unit="对", confirmed=True)).status_code == 409
    assert client.post(path, json=payload(source, (p3, 1), source_unit="对", target_unit=None)).status_code == 400
    assert contents(client, target) == {p1: 36, p2: 2.5}


@pytest.mark.parametrize("permissions", [[], ["parts"], ["jewelries"]])
def test_copy_endpoints_require_both_permissions(catalog, permissions):
    client, source, target, _, _, p2, _ = catalog
    app.dependency_overrides[get_current_user] = lambda: User(is_admin=False, permissions=permissions)
    assert client.get(f"/api/bom/{target}/copy-sources").status_code == 403
    assert client.get(f"/api/bom/{target}/copy-preview/{source}").status_code == 403
    assert client.post(f"/api/bom/{target}/copy", json=payload(source, (p2, 1))).status_code == 403


def test_save_skips_part_inserted_by_concurrent_bom_writer(catalog, engine, monkeypatch):
    client, source, target, _, p1, p2, p3 = catalog
    assert client.get(f"/api/bom/{target}/copy-preview/{source}").status_code == 200
    path = f"/api/bom/{target}/copy"
    waiting = Event()
    lock = bom.lock_bom

    def mark_lock(db, jewelry_id):
        if jewelry_id == target:
            waiting.set()
        lock(db, jewelry_id)

    with ThreadPoolExecutor(max_workers=1) as executor, Session(engine) as writer:
        bom.set_bom(writer, target, p2, 99)  # Hold the target advisory lock until commit.
        monkeypatch.setattr(bom, "lock_bom", mark_lock)
        pending = executor.submit(client.post, path, json=payload(source, (p2, 2), (p3, 0.5)))
        try:
            assert waiting.wait(5)
            assert not pending.done()
        finally:
            writer.commit()
        response = pending.result(timeout=5)
    assert response.status_code == 200, response.text
    assert response.json() == {"added_part_ids": [p3], "skipped_part_ids": [p2]}
    assert contents(client, target) == {p1: 36, p2: 99, p3: 0.5}
