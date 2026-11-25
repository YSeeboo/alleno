from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from models.handcraft_order import (
    HandcraftOrder, HandcraftPartItem, HandcraftPickingRecord, HandcraftPickingWeight,
)
from models.handcraft_receipt import HandcraftReceipt, HandcraftReceiptItem
from models.order import OrderItemLink
from models.part import Part
from models.production_loss import ProductionLoss
from services.inventory import add_stock, get_stock
from time_utils import now_beijing


ORDER = "HC-MERGE"
URL = f"/api/handcraft/{ORDER}/part-merge"


def add_rows(db, code, *quantities, unit="颗", order_id=ORDER, composite=False):
    if db.get(Part, code) is None:
        db.add(Part(id=code, name="同名配件", is_composite=composite))
        db.flush()
    rows = [HandcraftPartItem(handcraft_order_id=order_id, part_id=code, qty=qty, unit=unit) for qty in quantities]
    db.add_all(rows)
    db.flush()
    return rows


def preview(client):
    result = client.get(URL)
    assert result.status_code == 200, result.text
    return result.json()


def selection(group):
    return {key: group[key] for key in ("retain_item_id", "revision")}


def apply(client, *groups):
    return client.post(URL, json={"groups": [selection(group) for group in groups]})


def test_selective_merge_commits_exact_quantities_without_touching_stock_or_other_groups(client_real_get_db, engine):
    client = client_real_get_db
    with Session(engine) as db:
        db.add_all([HandcraftOrder(id=id_, supplier_name="供应商") for id_ in (ORDER, "HC-OTHER")])
        db.flush()
        pearl = add_rows(db, "PJ-A", "120.0001", "80.0002", "50.0003")
        ring = add_rows(db, "PJ-B", 60, 40, unit="个")
        other_unit = add_rows(db, "PJ-A", 2, 3, unit="包")
        untouched = add_rows(db, "PJ-SAME-NAME", 30) + add_rows(db, "PJ-A", 99, order_id="HC-OTHER")
        for row, bom, note in zip(pearl, ["1.2", "2.3", "3.4"], ["第一批", "第二批", "第一批"]):
            row.bom_qty, row.note = Decimal(bom), note
        add_stock(db, "part", "PJ-A", 400, "测试")
        survivor = pearl[0].id
        other_rows = {row.id: row.qty for row in [*ring, *other_unit, *untouched]}
        db.commit()

    groups = preview(client)
    assert {(group["part_id"], group["unit"]) for group in groups} == {("PJ-A", "颗"), ("PJ-A", "包"), ("PJ-B", "个")}
    chosen, = [group for group in groups if group["retain_item_id"] == survivor]
    assert [Decimal(row["qty"]) for row in chosen["rows"]] == list(map(Decimal, ["120.0001", "80.0002", "50.0003"]))
    assert Decimal(chosen["merged_qty"]) == Decimal("250.0006")
    assert Decimal(chosen["merged_bom_qty"]) == Decimal("6.9")
    assert chosen["merged_note"] == "第一批\n第二批"
    response = apply(client, chosen)
    assert response.status_code == 200, response.text
    assert response.json() == {"merged_groups": 1, "removed_rows": 2}
    assert apply(client, chosen).status_code == 409
    with Session(engine) as db:
        first = db.get(HandcraftPartItem, survivor)
        assert (first.qty, first.bom_qty, first.note) == (Decimal("250.0006"), Decimal("6.9000"), "第一批\n第二批")
        assert {row.id: row.qty for row in db.query(HandcraftPartItem) if row.id != survivor} == other_rows
        assert db.get(HandcraftOrder, ORDER).status == "pending"
        assert get_stock(db, "part", "PJ-A") == 400

    response = apply(client, *preview(client))
    assert response.status_code == 200, response.text
    assert response.json() == {"merged_groups": 2, "removed_rows": 2}
    assert preview(client) == []


@pytest.mark.parametrize("change,reason", [
    ("picked", "配货"), ("weighed", "称重"), ("actual_qty", "实配"), ("legacy_weight", "称重"),
    ("linked", "关联订单"), ("receipt", "回收记录"), ("loss", "损耗"), ("status", "发出或回收"),
    ("qty", "明细已变更"), ("note", "明细已变更"), ("added_row", "明细已变更"),
])
def test_rechecks_all_groups_before_applying_any_of_them(client, db, change, reason):
    db.add(HandcraftOrder(id=ORDER, supplier_name="供应商"))
    db.flush()
    add_rows(db, "PJ-SAFE", 60, 40)
    _, row = add_rows(db, "PJ-CHANGING", 120, 80)
    before = preview(client)
    assert len(before) == 2 and all(group["revision"] for group in before)
    if change == "picked":
        db.add(HandcraftPickingRecord(handcraft_order_id=ORDER, handcraft_part_item_id=row.id, part_id=row.part_id))
    elif change in ("weighed", "actual_qty"):
        values = {"weight": 10, "weight_unit": "g"} if change == "weighed" else {"actual_qty": 80}
        db.add(HandcraftPickingWeight(handcraft_order_id=ORDER, part_item_id=row.id, atom_part_id=row.part_id, **values))
    elif change == "legacy_weight":
        row.weight = 10
    elif change == "linked":
        db.add(OrderItemLink(handcraft_part_item_id=row.id))
    elif change == "receipt":
        db.add(HandcraftReceipt(id="HCR-TEST", supplier_name="供应商"))
        db.flush()
        db.add(HandcraftReceiptItem(handcraft_receipt_id="HCR-TEST", handcraft_part_item_id=row.id,
                                    item_id=row.part_id, item_type="part", qty=1))
    elif change == "loss":
        db.add(ProductionLoss(order_type="handcraft", order_id=ORDER, item_type="handcraft_part", item_id=row.id, loss_qty=1))
    elif change == "status":
        row.status = "制作中"
    elif change == "qty":
        row.qty = 85
    elif change == "note":
        row.note = "更新备注"
    else:
        add_rows(db, row.part_id, 50)
    db.flush()

    response = apply(client, *before)
    assert response.status_code == 409, response.text
    assert reason in response.json()["detail"]
    assert [row.qty for row in db.query(HandcraftPartItem).filter_by(part_id="PJ-SAFE").order_by(HandcraftPartItem.id)] == [60, 40]
    updated, = [group for group in preview(client) if group["part_id"] == "PJ-CHANGING"]
    if "变更" not in reason:
        assert not updated["revision"] and reason in updated["blocked_reason"]
    else:
        assert updated["revision"] != before[-1]["revision"]


def test_blocks_unsupported_groups_without_affecting_eligible_groups(client, db):
    db.add(HandcraftOrder(id=ORDER, supplier_name="供应商"))
    db.flush()
    add_rows(db, "PJ-SAFE", 2, 3)
    add_rows(db, "PJ-COMPOSITE", 2, 3, composite=True)
    add_rows(db, "PJ-OVERFLOW", "999999.9999", "0.0001")
    add_rows(db, "PJ-MISSING-UNIT", 2, 3, unit="")
    one, _ = add_rows(db, "PJ-MIXED-BOM", 2, 3)
    one.bom_qty = 1
    db.flush()
    groups = {group["part_id"]: group for group in preview(client)}
    assert [(code, groups[code]["revision"]) for code in groups if groups[code]["revision"]] == [("PJ-SAFE", groups["PJ-SAFE"]["revision"])]
    for code, reason in {"PJ-COMPOSITE": "组合配件", "PJ-OVERFLOW": "上限", "PJ-MISSING-UNIT": "缺少单位", "PJ-MIXED-BOM": "理论用量"}.items():
        assert reason in groups[code]["blocked_reason"]


@pytest.mark.parametrize("closed_state", ["processing", "completed", "archived"])
def test_only_pending_unarchived_orders_allow_merge(client, db, closed_state):
    order = HandcraftOrder(id=ORDER, supplier_name="供应商")
    db.add(order)
    db.flush()
    add_rows(db, "PJ-A", 1, 2)
    group, = preview(client)
    if closed_state == "archived":
        order.archived_at = now_beijing()
    else:
        order.status = closed_state
    db.flush()
    assert preview(client) == []
    assert apply(client, group).status_code == 409
    assert db.query(HandcraftPartItem).count() == 2


def test_rejects_empty_and_duplicate_selections(client, db):
    db.add(HandcraftOrder(id=ORDER, supplier_name="供应商"))
    db.flush()
    add_rows(db, "PJ-A", 1, 2)
    group, = preview(client)
    assert apply(client).status_code == 422
    assert apply(client, group, group).status_code == 422
    assert db.query(HandcraftPartItem).count() == 2
