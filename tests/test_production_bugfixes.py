"""Regression coverage for output BOM allocation and default part units."""
import pytest

from models.bom import Bom
from services.handcraft import create_handcraft_order
from services.inventory import add_stock, get_stock
from services.jewelry import create_jewelry
from services.part import create_part
from services.part_bom import set_part_bom


@pytest.fixture
def production(db):
    material = create_part(db, {"name": "链条", "category": "链条", "unit": "米"})
    jewelry = create_jewelry(db, {"name": "项链", "category": "单件"})
    db.add(Bom(id="BM-regression", jewelry_id=jewelry.id, part_id=material.id, qty_per_unit="0.3"))
    add_stock(db, "part", material.id, 100, "入库")
    order = create_handcraft_order(db, "手工厂", [{"part_id": material.id, "qty": 2, "unit": "包"}])
    db.flush()
    return material, jewelry, order


@pytest.mark.parametrize("output_type", ["jewelry", "part"])
def test_add_output_appends_bom_materials_without_overwriting_existing_rows(client, db, production, output_type):
    material, jewelry, order = production
    if output_type == "part":
        composite = create_part(db, {"name": "组合链", "category": "链条", "unit": "条"})
        set_part_bom(db, composite.id, material.id, .3)
        output_id = {"part_id": composite.id}
    else:
        output_id = {"jewelry_id": jewelry.id}
    response = client.post(f"/api/handcraft/{order.id}/jewelries", json={**output_id, "qty": 7})
    assert response.status_code == 201, response.text
    if output_type == "part":
        assert response.json()["unit"] == "条"
    rows = client.get(f"/api/handcraft/{order.id}/parts").json()
    assert len(rows) == 2
    assert rows[0]["qty"] == 2
    assert rows[0]["unit"] == "包"
    assert rows[1]["part_id"] == material.id
    assert rows[1]["qty"] == 2.1
    assert rows[1]["bom_qty"] == 2.1
    assert rows[1]["unit"] == "米"
    assert get_stock(db, "part", material.id) == 100


@pytest.mark.parametrize("mode", ["processing", "customer", "no_bom"])
def test_add_output_does_not_fabricate_dispatched_or_attribution_materials(client, db, production, mode):
    material, jewelry, order = production
    payload = {"jewelry_id": jewelry.id, "qty": 3}
    if mode == "processing":
        assert client.post(f"/api/handcraft/{order.id}/send").status_code == 200
    elif mode == "customer":
        payload["customer_name"] = "客户甲"
    else:
        db.query(Bom).delete()
        db.flush()
    before = client.get(f"/api/handcraft/{order.id}/parts").json()
    stock = get_stock(db, "part", material.id)
    response = client.post(f"/api/handcraft/{order.id}/jewelries", json=payload)
    assert response.status_code == 201, response.text
    assert client.get(f"/api/handcraft/{order.id}/parts").json() == before
    assert get_stock(db, "part", material.id) == stock


@pytest.mark.parametrize("kind", ["plating", "handcraft"])
@pytest.mark.parametrize("unit", [None, "包"])
def test_create_and_add_parts_use_default_unit_but_keep_explicit_override(client, db, kind, unit):
    part = create_part(db, {"name": "链条", "category": "链条", "unit": "米"})
    item = {"part_id": part.id, "qty": 3}
    if unit is not None:
        item["unit"] = unit
    collection = "items" if kind == "plating" else "parts"
    response = client.post(f"/api/{kind}/", json={"supplier_name": "工厂", collection: [item]})
    assert response.status_code == 201, response.text
    order_id = response.json()["id"]
    rows = client.get(f"/api/{kind}/{order_id}/{collection}").json()
    assert rows[0]["unit"] == (unit or "米")
    added = client.post(f"/api/{kind}/{order_id}/{collection}", json=item)
    assert added.status_code == 201, added.text
    assert added.json()["unit"] == (unit or "米")


def test_pending_plating_candidates_exclude_settled_rows_in_partially_received_order(client, db):
    part = create_part(db, {"name": "链条", "category": "链条"})
    add_stock(db, "part", part.id, 100, "入库")
    response = client.post("/api/plating/", json={
        "supplier_name": "电镀厂", "items": [{"part_id": part.id, "qty": 10} for _ in range(3)],
    })
    order_id = response.json()["id"]
    assert client.post(f"/api/plating/{order_id}/send").status_code == 200
    rows = client.get(f"/api/plating/{order_id}/items").json()
    receipt = client.post("/api/plating-receipts/", json={
        "vendor_name": "电镀厂", "items": [
            {"plating_order_item_id": row["id"], "part_id": part.id, "qty": qty}
            for row, qty in zip(rows, [10, 12, 4])
        ],
    })
    assert receipt.status_code == 201, receipt.text
    candidates = client.get("/api/plating/items/pending-receive", params={"supplier_name": "电镀厂"})
    assert candidates.status_code == 200, candidates.text
    assert [row["id"] for row in candidates.json()] == [rows[2]["id"]]


def test_batch_output_sequence_appends_each_bom_once_and_keeps_manual_materials(client, db, production):
    material, jewelry, order = production
    composite = create_part(db, {"name": "组合链", "category": "链条", "unit": "条"})
    set_part_bom(db, composite.id, material.id, .2)
    outputs = [
        {"jewelry_id": jewelry.id, "qty": 3, "unit": "套", "weight": 0, "weight_unit": "g"},
        {"part_id": composite.id, "qty": 4, "unit": "条"},
        {"jewelry_id": jewelry.id, "qty": 2, "unit": "套"},
    ]
    ids = []
    for payload in outputs:
        result = client.post(f"/api/handcraft/{order.id}/jewelries", json=payload)
        assert result.status_code == 201, result.text
        ids.append(result.json()["id"])
    assert len(set(ids)) == 3
    rows = client.get(f"/api/handcraft/{order.id}/parts").json()
    manual = [row for row in rows if row.get("bom_qty") is None]
    generated = [row for row in rows if row.get("bom_qty") is not None]
    assert len(manual) == 1
    assert manual[0]["qty"] == 2
    assert manual[0]["unit"] == "包"
    assert round(sum(row["qty"] for row in generated), 4) == 2.3
    assert get_stock(db, "part", material.id) == 100


def test_batch_order_sequence_keeps_same_product_lines_without_customer_codes(client, db):
    jewelry = create_jewelry(db, {"name": "项链", "category": "单件", "unit": "条"})
    part = create_part(db, {"name": "链条", "category": "链条", "unit": "米"})
    result = client.post("/api/orders/", json={"customer_name": "批量客户", "items": [
        {"jewelry_id": jewelry.id, "quantity": 1, "unit_price": 0},
    ]})
    assert result.status_code == 201, result.text
    order_id = result.json()["id"]
    saved = []
    for payload in [
        {"jewelry_id": jewelry.id, "quantity": 3, "unit_price": 0.1234567},
        {"jewelry_id": jewelry.id, "quantity": 7, "unit_price": 1.1234567},
        {"part_id": part.id, "quantity": 2, "unit_price": 0},
    ]:
        added = client.post(f"/api/orders/{order_id}/items", json=payload)
        assert added.status_code == 201, added.text
        saved.append(added.json())
    assert len({row["id"] for row in saved}) == 3
    assert [row["quantity"] for row in saved] == [3, 7, 2]
    assert [row["unit_price"] for row in saved] == [0.1234567, 1.1234567, 0]
    assert all(row.get("customer_code") is None for row in saved)
    assert get_stock(db, "part", part.id) == 0
