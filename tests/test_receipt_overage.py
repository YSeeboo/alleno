"""Actual receipt quantities are uncapped; stock, settlement and safeguards aren't."""
import pytest

from models.handcraft_order import HandcraftPartItem, HandcraftJewelryItem
from services.part import create_part
from services.jewelry import create_jewelry
from services.inventory import add_stock, get_stock
from services.handcraft import create_handcraft_order, send_handcraft_order
from services.plating import create_plating_order, send_plating_order, get_plating_items
from services.bom import set_bom
from services.handcraft_receipt import (
    create_handcraft_receipt, update_handcraft_receipt_item, delete_handcraft_receipt,
)
from services.production_loss import confirm_handcraft_loss
from time_utils import now_beijing


def _source(db, kind):
    part = create_part(db, {"name": "超收配件", "category": "小配件"})
    add_stock(db, "part", part.id, 100, "测试入库")
    if kind == "plating":
        order = create_plating_order(db, "超收商家", [{"part_id": part.id, "qty": 10}])
        send_plating_order(db, order.id)
        row = get_plating_items(db, order.id)[0]
        return order, row, "part", part.id, {"plating_order_item_id": row.id, "part_id": part.id}
    jewelry = create_jewelry(db, {"name": "超收产出", "category": "单件"})
    order = create_handcraft_order(db, "超收商家", parts=[{"part_id": part.id, "qty": 10}],
                                   jewelries=[{"jewelry_id": jewelry.id, "qty": 10}] if kind == "output" else [])
    send_handcraft_order(db, order.id)
    if kind == "output":
        row = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=order.id).one()
        return order, row, "jewelry", jewelry.id, {"handcraft_jewelry_item_id": row.id}
    row = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).one()
    return order, row, "part", part.id, {"handcraft_part_item_id": row.id}


@pytest.mark.parametrize("kind", ["plating", "output", "material"])
def test_overage_lifecycle_and_source_selection(client, db, kind):
    order, row, stock_type, stock_id, link = _source(db, kind)
    base_stock = get_stock(db, stock_type, stock_id)
    domain = "plating" if kind == "plating" else "handcraft"
    root = f"/api/{domain}-receipts"
    vendor_key = "vendor_name" if kind == "plating" else "supplier_name"
    create = client.post(f"{root}/", json={vendor_key: "超收商家", "items": [{**link, "qty": 12, "price": 2}]})
    assert create.status_code == 201, create.text
    first = create.json()
    assert first["total_amount"] == 24
    db.refresh(row)
    db.refresh(order)
    assert float(row.qty) == 10
    assert float(row.received_qty) == 12
    assert order.status == "completed"
    assert get_stock(db, stock_type, stock_id) == base_stock + 12

    pending_url = f"/api/{domain}/items/pending-receive"
    params = {"supplier_name": "超收商家"}
    def selected(data):
        return [i for i in data if i["id"] == row.id and (domain == "plating" or i["is_output"] == (kind == "output"))]
    assert not selected(client.get(pending_url, params=params).json())
    params["include_settled"] = True
    assert selected(client.get(pending_url, params=params).json())
    assert not client.get(pending_url, params={**params, "supplier_name": "其他商家"}).json()
    assert not client.get(pending_url, params={**params, "date_on": "2000-01-01"}).json()
    keyword = "part_keyword" if domain == "plating" else "keyword"
    assert not client.get(pending_url, params={**params, keyword: "missing-source-xyz"}).json()
    if domain == "handcraft":
        assert selected(client.get(pending_url, params={**params, "receipt_code": order.receipt_code.lower()}).json())
        assert not client.get(pending_url, params={**params, "receipt_code": "XXXXX"}).json()
    exclude = "exclude_item_ids" if domain == "plating" else ("exclude_jewelry_item_ids" if kind == "output" else "exclude_part_item_ids")
    assert not selected(client.get(pending_url, params={**params, exclude: row.id}).json())

    # A settled source can be used in a NEW receipt, then appended to again.
    second = client.post(f"{root}/", json={vendor_key: "超收商家", "items": [{**link, "qty": 3, "price": 2}]})
    assert second.status_code == 201, second.text
    # The same receipt cannot repeat a plating source; append to a receipt
    # containing a different source, just as the UI's exclusion filter does.
    _, _, _, _, other_link = _source(db, kind)
    holder = client.post(f"{root}/", json={vendor_key: "超收商家", "items": [{**other_link, "qty": 1, "price": 2}]})
    assert holder.status_code == 201, holder.text
    appended = client.post(f"{root}/{holder.json()['id']}/items", json={"items": [{**link, "qty": 2, "price": 2}]})
    assert appended.status_code == 201, appended.text
    assert appended.json()["total_amount"] == 6
    edit_url = f"{root}/{first['id']}/items/{first['items'][0]['id']}"
    edited = client.put(edit_url, json={"qty": 20})
    assert edited.status_code == 200, edited.text
    assert client.get(f"{root}/{first['id']}").json()["total_amount"] == 40
    assert get_stock(db, stock_type, stock_id) == base_stock + 25
    assert client.put(edit_url, json={"qty": 0}).status_code == 422
    if kind == "output":
        assert client.put(edit_url, json={"qty": 20.5}).status_code == 400

    # Dropping back below plan reopens, including after deleting another receipt.
    assert client.put(edit_url, json={"qty": 4}).status_code == 200
    assert client.delete(f"{root}/{second.json()['id']}").status_code == 204
    appended_item = next(i for i in appended.json()["items"] if all(i[k] == v for k, v in link.items()))
    assert client.delete(f"{root}/{holder.json()['id']}/items/{appended_item['id']}").status_code == 204
    assert client.get(f"{root}/{holder.json()['id']}").json()["total_amount"] == 2
    db.refresh(order)
    db.refresh(row)
    assert order.status == "processing"
    assert float(row.received_qty) == 4
    assert get_stock(db, stock_type, stock_id) == base_stock + 4
    assert client.delete(f"{root}/{first['id']}").status_code == 204
    assert get_stock(db, stock_type, stock_id) == base_stock


@pytest.mark.parametrize("kind", ["plating", "output", "material"])
def test_settled_selection_excludes_archives_and_drafts(client, db, kind):
    order, row, _, _, _ = _source(db, kind)
    domain = "plating" if kind == "plating" else "handcraft"
    url = f"/api/{domain}/items/pending-receive"
    params = {"include_settled": True, "supplier_name": "超收商家"}
    order.status = "pending"
    db.flush()
    assert client.get(url, params=params).json() == []
    order.status = "completed"
    order.archived_at = now_beijing()
    db.flush()
    assert client.get(url, params=params).json() == []


@pytest.mark.parametrize("kind", ["plating", "output", "material"])
def test_overage_preserves_vendor_payment_and_archive_guards(client, db, kind):
    order, row, _, _, link = _source(db, kind)
    domain = "plating" if kind == "plating" else "handcraft"
    root = f"/api/{domain}-receipts"
    vendor_key = "vendor_name" if domain == "plating" else "supplier_name"
    bad = client.post(f"{root}/", json={vendor_key: "其他商家", "items": [{**link, "qty": 12}]})
    assert bad.status_code == 400
    created = client.post(f"{root}/", json={vendor_key: "超收商家", "items": [{**link, "qty": 12}]})
    assert created.status_code == 201, created.text
    rid = created.json()["id"]
    iid = created.json()["items"][0]["id"]
    assert client.patch(f"{root}/{rid}/status", json={"status": "已付款"}).status_code == 200
    assert client.put(f"{root}/{rid}/items/{iid}", json={"qty": 20}).status_code == 400
    assert client.post(f"{root}/{rid}/items", json={"items": [{**link, "qty": 20}]}).status_code == 400
    assert client.delete(f"{root}/{rid}").status_code == 400
    order.archived_at = now_beijing()
    db.flush()
    archived = client.post(f"{root}/", json={vendor_key: "超收商家", "items": [{**link, "qty": 20}]})
    assert archived.status_code == 400
    db.refresh(row)
    assert float(row.received_qty) == 12


@pytest.mark.parametrize("composite", [False, True])
def test_capped_bom_reversal_preserves_other_outputs_losses_and_returns(db, composite):
    from services.part_bom import set_part_bom

    part = create_part(db, {"name": "共享材料", "category": "小配件"})
    add_stock(db, "part", part.id, 100, "入库")
    jewelry = create_jewelry(db, {"name": "共享产出", "category": "单件"})
    set_bom(db, jewelry.id, part.id, 1)
    output_data = {"jewelry_id": jewelry.id, "qty": 10}
    if composite:
        parent = create_part(db, {"name": "组合产出", "category": "小配件", "is_composite": True})
        set_part_bom(db, parent.id, part.id, 1)
        output_data = {"part_id": parent.id, "qty": 10}
    order = create_handcraft_order(db, "商家", parts=[{"part_id": part.id, "qty": 10}],
                                   jewelries=[output_data, {"jewelry_id": jewelry.id, "qty": 10}])
    send_handcraft_order(db, order.id)
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).one()
    outputs = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=order.id).order_by(HandcraftJewelryItem.id).all()
    # Return two materials, confirm two lost outputs, receive 12 + 3 outputs.
    create_handcraft_receipt(db, "商家", [{"handcraft_part_item_id": pi.id, "qty": 2}])
    confirm_handcraft_loss(db, order.id, outputs[1].id, "jewelry", 2)
    receipt = create_handcraft_receipt(db, "商家", [{"handcraft_jewelry_item_id": outputs[0].id, "qty": 12}])
    other = create_handcraft_receipt(db, "商家", [{"handcraft_jewelry_item_id": outputs[1].id, "qty": 3}])
    assert float(pi.consumed_qty) == 8
    assert receipt.parts_shortfall[0]["shortfall_qty"] == 6
    item = receipt.items[0]
    # 10 remaining outputs still need all 8 available materials; do not unconsume 7.
    update_handcraft_receipt_item(db, receipt.id, item.id, {"qty": 5})
    assert float(pi.consumed_qty) == 8
    # 6 remaining outputs need 6, so only two consumed materials are released.
    update_handcraft_receipt_item(db, receipt.id, item.id, {"qty": 1})
    assert float(pi.consumed_qty) == 6
    delete_handcraft_receipt(db, other.id)
    assert float(pi.consumed_qty) == 3  # one actual + two lost outputs
    delete_handcraft_receipt(db, receipt.id)
    assert float(pi.consumed_qty) == 2  # confirmed losses remain consumed
    assert float(pi.returned_qty) == 2
    assert float(pi.received_qty) == 4
    assert get_stock(db, "part", part.id) == 92  # never fabricated material stock


def test_plating_overage_uses_received_variant_and_preserves_confirmed_loss(db):
    from services.production_loss import confirm_plating_loss
    from services.plating_receipt import create_plating_receipt, delete_plating_receipt

    source = create_part(db, {"name": "发出原色", "category": "小配件"})
    target = create_part(db, {"name": "回收金色", "category": "小配件"})
    add_stock(db, "part", source.id, 100, "入库")
    order = create_plating_order(db, "商家", [{"part_id": source.id, "receive_part_id": target.id, "qty": 10}])
    send_plating_order(db, order.id)
    row = get_plating_items(db, order.id)[0]
    confirm_plating_loss(db, order.id, row.id, 2)
    receipt = create_plating_receipt(db, "商家", [{"plating_order_item_id": row.id, "part_id": target.id, "qty": 12, "price": 3}])
    assert float(row.received_qty) == 14
    assert float(receipt.total_amount) == 36
    assert get_stock(db, "part", target.id) == 12
    assert get_stock(db, "part", source.id) == 90
    delete_plating_receipt(db, receipt.id)
    assert float(row.received_qty) == 2
    assert get_stock(db, "part", target.id) == 0
    assert order.status == "processing"
