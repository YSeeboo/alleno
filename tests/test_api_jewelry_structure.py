from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest

from api.deps import get_current_user
from main import app
from models.bom import Bom
from models.inventory_log import InventoryLog
from models.jewelry import Jewelry
from models.jewelry_structure import JewelryStructureBatch
from models.part import Part
from models.user import User
from schemas.jewelry_structure import BatchConfirm
from services import jewelry_structure as service


@pytest.fixture
def config(client, db):
    return create_config(client, db)


def create_config(client, db, commit=False):
    for pid, name, unit in [("stud", "耳钉", "个"), ("chain", "链条", "cm"),
                            ("bead4", "4mm 珠子", "颗"), ("bead6", "6mm 珠子", "颗"),
                            ("flower", "花朵吊坠", "个"), ("moon", "月亮吊坠", "个"),
                            ("ring", "开口圈", "个")]:
        db.add(Part(id=pid, name=name, unit=unit))
    db.flush()
    if commit:
        db.commit()
    body = {"name": "耳饰结构", "category": "耳饰", "unit": "对", "slots": [
        {"key": "stud", "name": "耳钉", "part_id": "stud", "qty": "2"},
        {"key": "chain", "name": "链条", "part_id": "chain", "qty": "5"},
        {"key": "bead", "name": "珠子", "part_id": "bead4", "qty": "6"},
        {"key": "pendant", "name": "吊坠", "qty": "2", "selectable": True},
    ]}
    response = client.post("/api/jewelry-structures/", json=body)
    assert response.status_code == 201, response.text
    structure = response.json()
    response = client.post(f"/api/jewelry-structures/{structure['id']}/schemes", json={
        "name": "大珠版", "structure_revision": structure["revision"],
        "overrides": {"bead": {"part_id": "bead6", "qty": "4"}, "chain": {"qty": "4"}},
    })
    assert response.status_code == 201, response.text
    structure = response.json()
    batch = {"structure_id": structure["id"], "structure_revision": structure["revision"],
             "rows": [{"key": "flower-row", "name": "花朵款", "selections": {"pendant": "flower"}},
                      {"key": "moon-row", "name": "月亮款", "scheme_id": structure["schemes"][0]["id"],
                       "selections": {"pendant": "moon"}}]}
    return {"structure": structure, "body": body, "batch": batch}


def preview(client, batch):
    response = client.post("/api/jewelry-structures/preview", json=batch)
    assert response.status_code == 200, response.text
    return response.json()


def confirm_payload(client, batch):
    return {"request_key": str(uuid4()), "preview_token": preview(client, batch)["preview_token"], "batch": batch}


def test_preview_and_confirm_independent_jewelries(client, db, config):
    result = preview(client, config["batch"])
    assert db.query(Jewelry).count() == db.query(Bom).count() == 0
    small, large = result["rows"]
    assert {i["part_id"]: Decimal(i["qty"]) for i in small["bom"]} == {
        "stud": 2, "chain": 5, "bead4": 6, "flower": 2}
    assert {i["part_id"]: Decimal(i["qty"]) for i in large["bom"]} == {
        "stud": 2, "chain": 4, "bead6": 4, "moon": 2}
    response = client.post("/api/jewelry-structures/confirm", json=confirm_payload(client, config["batch"]))
    assert response.status_code == 200, response.text
    assert len(response.json()["rows"]) == db.query(Jewelry).count() == 2
    assert all(j.unit == "对" and j.style_group is None for j in db.query(Jewelry))
    assert db.query(InventoryLog).count() == 0
    before = [(b.id, b.part_id, b.qty_per_unit) for b in db.query(Bom).order_by(Bom.id)]
    updated = deepcopy(config["body"])
    updated["slots"][0]["qty"] = 3
    response = client.put(f"/api/jewelry-structures/{config['structure']['id']}",
                          json={**updated, "revision": config["structure"]["revision"]})
    assert response.status_code == 200
    assert before == [(b.id, b.part_id, b.qty_per_unit) for b in db.query(Bom).order_by(Bom.id)]
    revision = response.json()["revision"]
    response = client.delete(f"/api/jewelry-structures/{config['structure']['id']}?revision={revision}")
    assert response.status_code == 204
    assert db.query(Jewelry).count() == 2 and db.query(Bom).count() == 8
    assert db.query(JewelryStructureBatch).count() == 1


def test_default_single_overrides_and_merge(client, config):
    batch = config["batch"]
    batch["default_scheme_id"] = config["structure"]["schemes"][0]["id"]
    batch["rows"][0].update(overrides={"chain": {"qty": "7.125"}}, removed_keys=["bead"], extras=[
        {"key": "extra-stud", "name": "连接用耳钉", "part_id": "stud", "qty": "0.125"}])
    result = preview(client, batch)
    parts = {i["part_id"]: Decimal(i["qty"]) for i in result["rows"][0]["bom"]}
    assert parts == {"stud": Decimal("2.125"), "chain": Decimal("7.125"), "flower": 2}
    assert {i["part_id"]: Decimal(i["qty"]) for i in result["rows"][1]["bom"]}["chain"] == 4


def test_structure_draft_not_published(client, config):
    batch = config["batch"]
    batch["draft"] = deepcopy(config["body"])
    batch["draft"]["name"] = "草稿结构"
    batch["draft"]["slots"][0]["qty"] = "3"
    result = preview(client, batch)
    assert result["from_draft"] and result["structure_name"] == "草稿结构"
    assert result["rows"][0]["bom"][0]["qty"] == "3.0000"
    assert client.get("/api/jewelry-structures/").json()[0]["name"] == "耳饰结构"


def test_deleted_slot_blocks_scheme_and_repair_is_explicit(client, config):
    body = deepcopy(config["body"])
    body["slots"] = [s for s in body["slots"] if s["key"] != "bead"]
    obj = config["structure"]
    response = client.put(f"/api/jewelry-structures/{obj['id']}", json={**body, "revision": obj["revision"]})
    obj = response.json()
    assert obj["schemes"][0]["invalid_keys"] == ["bead"]
    batch = config["batch"]
    batch["structure_revision"] = obj["revision"]
    assert client.post("/api/jewelry-structures/preview", json=batch).status_code == 400
    scheme = obj["schemes"][0]
    scheme["overrides"].pop("bead")
    response = client.put(f"/api/jewelry-structures/{obj['id']}/schemes/{scheme['id']}", json={
        "name": scheme["name"], "structure_revision": obj["revision"], "overrides": scheme["overrides"]})
    assert response.status_code == 200, response.text
    batch["structure_revision"] = response.json()["revision"]
    assert all(not any(i["key"] == "bead" for i in r["positions"]) for r in preview(client, batch)["rows"])


@pytest.mark.parametrize("change", ["revision", "qty", "name", "unit", "token", "actor"])
def test_preview_tampering_or_staleness(client, db, config, change):
    payload = confirm_payload(client, config["batch"])
    if change == "revision":
        client.put(f"/api/jewelry-structures/{config['structure']['id']}",
                   json={**config["body"], "revision": config["structure"]["revision"]})
    elif change == "qty":
        payload["batch"]["rows"][0]["overrides"] = {"chain": {"qty": "8"}}
    elif change in ("name", "unit"):
        setattr(db.get(Part, "stud"), change, "变更")
        db.flush()
    elif change == "token":
        payload["preview_token"] = "invalid"
    else:
        app.dependency_overrides[get_current_user] = lambda: User(id=2, is_admin=True)
    response = client.post("/api/jewelry-structures/confirm", json=payload)
    assert response.status_code == 409, response.text
    assert db.query(Jewelry).count() == db.query(Bom).count() == 0


def test_idempotent_replay_even_after_structure_deletion(client, db, config):
    payload = confirm_payload(client, config["batch"])
    first = client.post("/api/jewelry-structures/confirm", json=payload)
    assert first.status_code == 200, first.text
    obj = config["structure"]
    client.delete(f"/api/jewelry-structures/{obj['id']}?revision={obj['revision']}")
    payload["preview_token"] = "expired-token-is-irrelevant-on-replay"
    replay = client.post("/api/jewelry-structures/confirm", json=payload)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert db.query(Jewelry).count() == 2
    payload["batch"]["rows"][0]["name"] = "不同批次"
    assert client.post("/api/jewelry-structures/confirm", json=payload).status_code == 409


@pytest.mark.parametrize("case", ["foreign_scheme", "foreign_slot", "missing_part", "missing_selection",
                                  "bad_selection", "empty_bom", "duplicate_extra", "missing_unit"])
def test_invalid_resolved_bom(client, db, config, case):
    batch = config["batch"]
    row = batch["rows"][0]
    if case == "foreign_scheme":
        row["scheme_id"] = 9999
    elif case == "foreign_slot":
        row["overrides"] = {"does-not-exist": {"qty": 1}}
    elif case == "missing_part":
        row["overrides"] = {"stud": {"part_id": "not-a-part"}}
    elif case == "missing_selection":
        row["selections"] = {}
    elif case == "bad_selection":
        row["selections"]["stud"] = "stud"
    elif case == "empty_bom":
        row["removed_keys"] = [s["key"] for s in config["body"]["slots"]]
    elif case == "duplicate_extra":
        row["extras"] = [{"key": "stud", "name": "冲突", "part_id": "stud", "qty": 2}]
    else:
        db.get(Part, "stud").unit = None
        db.flush()
    response = client.post("/api/jewelry-structures/preview", json=batch)
    assert response.status_code == 400, response.text


@pytest.mark.parametrize("qty", [0, -1, "NaN", "Infinity", "0.00001", "1000000", None])
def test_quantity_validation(client, config, qty):
    batch = config["batch"]
    batch["rows"][0]["overrides"] = {"stud": {"qty": qty}}
    response = client.post("/api/jewelry-structures/preview", json=batch)
    assert response.status_code == 422, response.text


def test_optimistic_structure_and_scheme_writes(client, config):
    obj = config["structure"]
    response = client.put(f"/api/jewelry-structures/{obj['id']}", json={**config["body"], "revision": 1})
    assert response.status_code == 409
    response = client.post(f"/api/jewelry-structures/{obj['id']}/schemes", json={
        "name": "错误方案", "structure_revision": obj["revision"], "overrides": {"foreign": {"qty": 2}}})
    assert response.status_code == 400
    response = client.post(f"/api/jewelry-structures/{obj['id']}/schemes", json={
        "name": "不绑定吊坠", "structure_revision": obj["revision"], "overrides": {"pendant": {"part_id": "flower"}}})
    assert response.status_code == 400


def test_all_or_nothing_service_savepoint(client, db, config, monkeypatch):
    payload = BatchConfirm.model_validate(confirm_payload(client, config["batch"]))
    original = service.set_bom
    count = 0

    def failing(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 5:
            raise ValueError("第二件写入失败")
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "set_bom", failing)
    with pytest.raises(ValueError, match="第二件"):
        service.confirm_batch(db, payload, 0)
    assert db.query(Jewelry).count() == db.query(Bom).count() == db.query(JewelryStructureBatch).count() == 0


@pytest.mark.parametrize("permissions,can_read,can_create", [([], False, False), (["parts"], True, False),
                                                            (["jewelries"], False, False), (["parts", "jewelries"], True, True)])
def test_permissions(client, config, permissions, can_read, can_create):
    app.dependency_overrides[get_current_user] = lambda: User(id=7, is_admin=False, permissions=permissions)
    assert (client.get("/api/jewelry-structures/").status_code == 200) is can_read
    assert (client.post("/api/jewelry-structures/preview", json=config["batch"]).status_code == 200) is can_create


def test_removed_legacy_routes(client):
    assert client.get("/api/jewelry-templates/").status_code == 404


@pytest.fixture
def committed_config(client_real_get_db, engine):
    from sqlalchemy.orm import Session
    with Session(engine) as db:
        config = create_config(client_real_get_db, db, commit=True)
    return client_real_get_db, config


def test_real_commit_and_history_is_user_scoped(committed_config, engine):
    from sqlalchemy.orm import Session
    client, config = committed_config
    payload = confirm_payload(client, config["batch"])
    result = client.post("/api/jewelry-structures/confirm", json=payload)
    assert result.status_code == 200, result.text
    with Session(engine) as db:
        assert db.query(Jewelry).count() == 2
        assert db.query(Bom).count() == 8
        assert db.query(JewelryStructureBatch).count() == 1
        assert db.query(InventoryLog).count() == 0
    assert client.get("/api/jewelry-structures/batches").json() == [result.json()]
    app.dependency_overrides[get_current_user] = lambda: User(id=8, is_admin=True)
    assert client.get("/api/jewelry-structures/batches").json() == []


def test_real_rollback_and_same_key_retry(committed_config, engine, monkeypatch):
    from sqlalchemy.orm import Session
    client, config = committed_config
    payload = confirm_payload(client, config["batch"])
    original = service.set_bom
    count = 0

    def failing(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 5:
            raise ValueError("模拟第二件写入失败")
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "set_bom", failing)
    result = client.post("/api/jewelry-structures/confirm", json=payload)
    assert result.status_code == 400, result.text
    with Session(engine) as db:
        assert db.query(Jewelry).count() == db.query(Bom).count() == db.query(JewelryStructureBatch).count() == 0
    monkeypatch.setattr(service, "set_bom", original)
    assert client.post("/api/jewelry-structures/confirm", json=payload).status_code == 200
    with Session(engine) as db:
        assert db.query(Jewelry).count() == 2


def test_concurrent_same_request_commits_once(committed_config, engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    client, config = committed_config
    payload = BatchConfirm.model_validate(confirm_payload(client, config["batch"]))
    barrier = Barrier(2)

    def worker():
        with Session(engine) as db:
            barrier.wait(timeout=10)
            result = service.confirm_batch(db, payload, 0)
            db.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: worker(), range(2)))
    assert results[0] == results[1]
    with Session(engine) as db:
        assert db.query(Jewelry).count() == 2
        assert db.query(Bom).count() == 8
        assert db.query(JewelryStructureBatch).count() == 1


def test_concurrent_different_batches_get_unique_ids(committed_config, engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    client, config = committed_config
    payloads = [BatchConfirm.model_validate(confirm_payload(client, config["batch"])) for _ in range(2)]
    barrier = Barrier(2)

    def worker(payload):
        with Session(engine) as db:
            barrier.wait(timeout=10)
            result = service.confirm_batch(db, payload, 0)
            db.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(worker, payloads))
    assert len({r["jewelry_id"] for result in results for r in result["rows"]}) == 4
    with Session(engine) as db:
        assert db.query(Jewelry).count() == 4
        assert db.query(Bom).count() == 16


def test_expired_preview_cannot_create(client, db, config):
    import jwt
    from config import settings
    payload = confirm_payload(client, config["batch"])
    token = jwt.decode(payload["preview_token"], settings.JWT_SECRET_KEY, algorithms=["HS256"])
    token["exp"] = 1
    payload["preview_token"] = jwt.encode(token, settings.JWT_SECRET_KEY, algorithm="HS256")
    assert client.post("/api/jewelry-structures/confirm", json=payload).status_code == 409
    assert db.query(Jewelry).count() == 0


def test_history_limit(client, db):
    for n in range(25):
        db.add(JewelryStructureBatch(user_id=0, request_key=str(n), payload_digest="a" * 64, result={"n": n}))
    db.flush()
    assert client.get("/api/jewelry-structures/batches").json() == [{"n": n} for n in range(24, 4, -1)]
