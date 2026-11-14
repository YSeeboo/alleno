"""Classifying a product must not reinterpret its quantity or change its identity."""
from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from models.bom import Bom
from models.inventory_log import InventoryLog
from models.jewelry import Jewelry
from models.order import Order, OrderItem
from schemas.jewelry_options import JEWELRY_TYPES
from schemas.jewelry_structure import StructureWrite
from services.jewelry import create_jewelry, update_jewelry
from tests.test_api_jewelry_structure import create_config, confirm_payload


@pytest.mark.parametrize("category", JEWELRY_TYPES)
def test_new_types_use_category_independent_ids(client, category):
    response = client.post("/api/jewelries/", json={
        "name": "新饰品", "category": category, "unit": "个",
    })
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["category"] == category and result["unit"] == "个"
    assert result["id"] == "SP-00001"


def test_types_share_sequence_and_do_not_reuse_deleted_ids(client):
    first = client.post("/api/jewelries/", json={"name": "A", "category": "耳饰", "unit": "对"}).json()
    second = client.post("/api/jewelries/", json={"name": "B", "category": "项链", "unit": "条"}).json()
    assert first["id"] == "SP-00001"
    assert second["id"] == "SP-00002"
    assert client.delete(f"/api/jewelries/{second['id']}").status_code == 204
    third = client.post("/api/jewelries/", json={"name": "C", "category": "戒指", "unit": "枚"}).json()
    assert third["id"] == "SP-00003"


def test_new_sequence_coexists_with_preexisting_and_legacy_ids(db):
    db.add_all([
        Jewelry(id="SP-00042", name="较早编号", category="项链", unit="条"),
        Jewelry(id="SP-PAIR-00043", name="旧编号", category="单对", unit="对"),
    ])
    db.flush()
    jewelry = create_jewelry(db, {"name": "耳饰", "category": "耳饰", "unit": "个"})
    assert jewelry.id == "SP-00044"
    assert db.get(Jewelry, "SP-PAIR-00043").unit == "对"


@pytest.mark.parametrize("unit", ["个", "对", "条", "枚", "件", "套", "卡"])
def test_type_does_not_override_unit(client, unit):
    jewelry = client.post("/api/jewelries/", json={"name": "A", "category": "耳饰", "unit": unit}).json()
    result = client.patch(f"/api/jewelries/{jewelry['id']}", json={"category": "组合套装"})
    assert result.status_code == 200
    assert result.json()["unit"] == unit
    assert result.json()["id"] == jewelry["id"]


def test_classification_preserves_references_quantities_prices_and_siblings(client, db):
    source = client.post("/api/jewelries/", json={
        "name": "耳钉", "category": "单对", "unit": "对", "retail_price": 39.99,
    }).json()
    part = client.post("/api/parts/", json={"name": "耳针", "category": "小配件", "unit": "个"}).json()
    assert client.put(f"/api/bom/{source['id']}/{part['id']}", json={"qty_per_unit": "2"}).status_code == 200
    sibling = client.post(f"/api/jewelries/{source['id']}/siblings", json={"color": "银"}).json()
    assert client.post(f"/api/inventory/jewelry/{source['id']}/add", json={"qty": 5, "reason": "test"}).status_code == 200
    order = Order(id="order-category", customer_name="测试客户")
    db.add(order)
    db.flush()
    db.add(OrderItem(order_id=order.id, jewelry_id=source["id"], quantity=3, unit_price=Decimal("29.99")))
    db.flush()

    def snapshot(model):
        return [tuple(getattr(obj, col.name) for col in model.__table__.columns)
                for obj in db.query(model).order_by(model.id)]

    protected = {model: snapshot(model) for model in [Bom, InventoryLog, Order, OrderItem]}
    result = client.patch(f"/api/jewelries/{source['id']}", json={"category": "耳饰"})
    assert result.status_code == 200, result.text
    jewelry = result.json()
    assert jewelry["id"] == source["id"] and jewelry["category"] == "耳饰"
    assert jewelry["unit"] == "对" and jewelry["retail_price"] == 39.99
    assert jewelry["style_group"] == source["id"]
    assert client.get(f"/api/jewelries/{sibling['id']}").json()["category"] == "单对"
    assert client.get(f"/api/inventory/jewelry/{source['id']}").json()["current"] == 5
    for model, before in protected.items():
        assert snapshot(model) == before


@pytest.mark.parametrize("category", [None, "", "不存在的类目"])
def test_invalid_reclassification_leaves_record_unchanged(db, category):
    jewelry = create_jewelry(db, {"name": "A", "category": "单对", "unit": "对"})
    with pytest.raises(ValueError, match="Invalid category"):
        update_jewelry(db, jewelry.id, {"category": category})
    assert jewelry.category == "单对" and jewelry.unit == "对"


def test_filter_uses_type_not_unit(client):
    for name, category, unit in [("A", "耳饰", "对"), ("B", "耳饰", "个"), ("C", "项链", "条")]:
        assert client.post("/api/jewelries/", json={"name": name, "category": category, "unit": unit}).status_code == 201
    result = client.get("/api/jewelries/", params={"category": "耳饰"}).json()
    assert {j["name"] for j in result} == {"A", "B"}
    assert {j["unit"] for j in result} == {"对", "个"}


@pytest.mark.parametrize("operation", ["copy", "siblings"])
def test_copy_and_sibling_allow_explicit_classification(client, operation):
    source = client.post("/api/jewelries/", json={"name": "A", "category": "单对", "unit": "对"}).json()
    response = client.post(f"/api/jewelries/{source['id']}/{operation}", json={"name": "B", "category": "耳饰"})
    assert response.status_code == 201, response.text
    assert response.json()["category"] == "耳饰" and response.json()["unit"] == "对"
    assert client.get(f"/api/jewelries/{source['id']}").json()["category"] == "单对"


@pytest.mark.parametrize("category,unit", [("项链", "条"), ("戒指", "枚"), ("耳饰", "个"), ("组合套装", "套"), ("耳饰", "卡")])
def test_structure_batch_carries_independent_type_and_unit(client, db, category, unit):
    config = create_config(client, db)
    batch = deepcopy(config["batch"])
    batch["draft"] = {**config["body"], "category": category, "unit": unit}
    payload = confirm_payload(client, batch)
    result = client.post("/api/jewelry-structures/confirm", json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["category"] == category and result.json()["unit"] == unit
    for jewelry in db.query(Jewelry):
        assert jewelry.category == category and jewelry.unit == unit
        assert jewelry.id.startswith("SP-")
    saved = client.get("/api/jewelry-structures/").json()[0]
    assert saved["category"] == "耳饰" and saved["unit"] == "对"


def test_structure_reclassification_preserves_existing_jewelry_and_creation_snapshot(client, db):
    config = create_config(client, db)
    original_payload = confirm_payload(client, config["batch"])
    result = client.post("/api/jewelry-structures/confirm", json=original_payload)
    assert result.status_code == 200
    original = result.json()
    obj = config["structure"]
    response = client.put(f"/api/jewelry-structures/{obj['id']}", json={
        **config["body"], "revision": obj["revision"], "category": "项链", "unit": "条",
    })
    assert response.status_code == 200
    assert all(j.category == "耳饰" and j.unit == "对" for j in db.query(Jewelry))
    replay = client.post("/api/jewelry-structures/confirm", json=original_payload)
    assert replay.status_code == 200 and replay.json() == original
    replay_payload = confirm_payload(client, {**config["batch"], "structure_revision": response.json()["revision"]})
    assert original["category"] == "耳饰" and original["unit"] == "对"
    assert client.post("/api/jewelry-structures/confirm", json=replay_payload).json()["unit"] == "条"


@pytest.mark.parametrize("category,unit", [("未知", "对"), ("耳饰", "公斤"), (None, "对"), ("耳饰", None)])
def test_structure_rejects_invalid_type_or_unit(category, unit):
    with pytest.raises(ValidationError):
        StructureWrite(name="结构", category=category, unit=unit, slots=[{"key": "x", "name": "位置"}])


def test_legacy_structure_remains_readable_without_migration():
    for category in ["套装", "单件", "单对"]:
        value = StructureWrite(name="旧结构", category=category, unit="对", slots=[{"key": "x", "name": "位置"}])
        assert value.category == category
