from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy.orm import Session

from models.inventory_log import InventoryLog
from models.part import Part
from models.part_bom import PartBom
from models.plating_order import CompositePlatingTarget, PlatingOrder, PlatingOrderItem
from models.production_loss import ProductionLoss
from services.composite_plating import composite_plating_target
from services.inventory import add_stock, get_stock
from services.part import create_part, create_part_variant, update_part
from services.part_bom import delete_part_bom_item, set_part_bom


def make_assembly(db, name="原色挂件", children=None):
    if children is None:
        children = [create_part(db, {"name": n, "category": "小配件", "purchase_cost": c})
                    for n, c in [("扣头", Decimal("0.6")), ("链条", Decimal("0.2"))]]
    assembly = create_part(db, {"name": name, "category": "吊坠", "color": "原色", "unit": "件",
                               "spec": "20mm", "assembly_cost": Decimal("0.5")})
    for child, qty in zip(children, [Decimal("1"), Decimal("1.2501")]):
        set_part_bom(db, assembly.id, child.id, qty)
    return assembly, children


def test_whole_assembly_create_send_partial_receive(client, db):
    source, children = make_assembly(db)
    for child in children:
        add_stock(db, "part", child.id, 37, "测试备货")
    add_stock(db, "part", source.id, 100, "测试备货")
    url = f"/api/plating/composite-targets/{source.id}"
    response = client.get(url, params={"color_code": "G"})
    assert response.status_code == 200
    proposal = response.json()
    assert proposal["part"] is None and proposal["unit"] == "件"
    assert not db.get(Part, proposal["suggested_id"])
    response = client.post(url, json={"color_code": "G"})
    assert response.status_code == 200
    data = response.json()
    target = data["part"]
    assert data["created"] and target["id"] == proposal["suggested_id"] and target["name"] == proposal["suggested_name"]
    assert target["is_composite"] and target["color"] == "金色" and target["unit"] == "件"
    assert target["parent_part_id"] is None and target["spec"] == "20mm"
    assert target["unit_cost"] == pytest.approx(float(source.unit_cost))
    assert target["plating_cost"] is None
    bom = lambda pid: {(row.child_part_id, row.qty_per_unit) for row in db.query(PartBom).filter_by(parent_part_id=pid)}
    assert bom(target["id"]) == bom(source.id) == {(children[0].id, Decimal("1")), (children[1].id, Decimal("1.2501"))}
    assert client.get(url, params={"color_code": "G"}).json()["part"]["id"] == target["id"]
    assert client.post(url, json={"color_code": "G"}).json()["created"] is False
    assert db.query(CompositePlatingTarget).count() == 1
    assert get_stock(db, "part", target["id"]) == 0

    response = client.post("/api/plating/", json={"supplier_name": "验收电镀", "items": [
        {"part_id": source.id, "receive_part_id": target["id"], "qty": 100},
    ]})
    assert response.status_code == 201, response.text
    order_url = f'/api/plating/{response.json()["id"]}'
    item, = client.get(order_url + "/items").json()
    assert (item["plating_method"], item["unit"]) == ("金", "件")
    assert get_stock(db, "part", source.id) == 100
    assert client.post(order_url + "/send").json()["status"] == "processing"
    assert client.put(f'{order_url}/items/{item["id"]}', json={"receive_part_id": None}).status_code == 400
    response = client.post("/api/plating-receipts/", json={"vendor_name": "验收电镀", "items": [
        {"plating_order_item_id": item["id"], "part_id": target["id"], "qty": 98, "unit": "件", "price": 5},
    ]})
    assert response.status_code == 201, response.text
    assert client.get(order_url).json()["status"] == "processing"
    pending, = client.get("/api/plating/items/pending-receive").json()
    assert pending["part_is_composite"] and pending["receive_part_id"] == target["id"]
    assert pending["qty"] - pending["received_qty"] == 2
    assert not db.query(ProductionLoss).count()
    assert get_stock(db, "part", source.id) == 0
    assert get_stock(db, "part", target["id"]) == 98
    assert db.get(Part, target["id"]).unit_cost == source.unit_cost
    for child in children:
        assert get_stock(db, "part", child.id) == 37
    assert db.query(Part).count() == 4


def test_invalid_targets_and_legacy_pending_repair(client, db):
    source, children = make_assembly(db)
    other, _ = make_assembly(db, "无关挂件", children)
    other_target = composite_plating_target(db, other.id, "G", create=True)["part"]
    gold = composite_plating_target(db, source.id, "G", create=True)["part"]
    silver = composite_plating_target(db, source.id, "SV", create=True)["part"]
    legacy = PlatingOrder(id="EP-LEGACY", supplier_name="验收电镀", status="pending")
    db.add(legacy)
    db.flush()
    row = PlatingOrderItem(plating_order_id=legacy.id, part_id=source.id, qty=100, unit="件")
    db.add(row)
    db.flush()
    url = f"/api/plating/{legacy.id}"
    base = dict(part_id=source.id, qty=100, plating_method="金", unit="件")
    for receive_id in [None, source.id, other.id, children[0].id, other_target.id, silver.id, "MISSING"]:
        item = dict(base, receive_part_id=receive_id)
        assert client.post("/api/plating/", json={"supplier_name": "验收电镀", "items": [item]}).status_code == 400
        assert client.post(url + "/items", json=item).status_code == 400
    update_url = f"{url}/items/{row.id}"
    for changes in [{"receive_part_id": other_target.id}, {"receive_part_id": gold.id, "plating_method": "银"},
                    {"receive_part_id": gold.id, "unit": "包"}]:
        assert client.put(update_url, json=changes).status_code == 400
    for action in ("send", "supplement-and-send"):
        response = client.post(f"{url}/{action}")
        assert response.status_code == 400 and "收回编号" in response.json()["detail"]
    assert not db.query(InventoryLog).count()

    response = client.put(update_url, json={"receive_part_id": gold.id, "plating_method": "金"})
    assert response.status_code == 200 and response.json()["receive_part_id"] == gold.id
    assert client.put(update_url, json={"receive_part_id": None}).status_code == 400
    response = client.post(url + "/items", json=dict(base, receive_part_id=gold.id, qty=1))
    assert response.status_code == 201
    response = client.post(url + "/supplement-and-send")
    assert response.status_code == 200 and response.json()["supplemented"] == {source.id: 101}
    assert get_stock(db, "part", source.id) == get_stock(db, "part", gold.id) == 0


def test_do_not_guess_link_or_allow_normal_variant_and_bom_removal(db):
    source, children = make_assembly(db)
    suspect_id = f"{source.id}-EP-G"
    db.add(Part(id=suspect_id, name="重名挂件", color="金色", category="吊坠"))
    db.flush()
    with pytest.raises(ValueError, match="编号.*已被占用"):
        composite_plating_target(db, source.id, "G", create=True)
    with pytest.raises(ValueError, match="仅组合件"):
        composite_plating_target(db, children[0].id, "G", create=True)
    target = composite_plating_target(db, source.id, "SV", create=True)["part"]
    with pytest.raises(ValueError, match="组合件不支持变体"):
        create_part_variant(db, target.id, "G")
    with pytest.raises(ValueError, match="不可修改颜色"):
        update_part(db, target.id, {"color": "金色"})
    with pytest.raises(ValueError, match="暂不支持镀色组合件再次送镀"):
        composite_plating_target(db, target.id, "G", create=True)
    first, last = db.query(PartBom).filter_by(parent_part_id=target.id).all()
    delete_part_bom_item(db, first.id)
    with pytest.raises(ValueError, match="至少保留一条 BOM"):
        delete_part_bom_item(db, last.id)
    with pytest.raises(ValueError, match="BOM 不一致"):
        composite_plating_target(db, source.id, "SV")


def test_concurrent_target_confirmations_reuse_one_sku(db, engine):
    source, _ = make_assembly(db)
    source_id = source.id
    db.commit()
    barrier = Barrier(2)

    def confirm():
        with Session(engine) as session, session.begin():
            barrier.wait(timeout=5)
            info = composite_plating_target(session, source_id, "G", create=True)
            return info["part"].id, info["created"]

    with ThreadPoolExecutor(2) as pool:
        a, b = pool.map(lambda _: confirm(), range(2))
    assert a[0] == b[0] and a[1] != b[1]
    assert db.query(CompositePlatingTarget).count() == 1
    assert db.query(PartBom).filter_by(parent_part_id=a[0]).count() == 2
