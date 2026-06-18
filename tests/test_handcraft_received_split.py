from services.part import create_part
from services.inventory import add_stock
from services.handcraft import create_handcraft_order, send_handcraft_order
from models.handcraft_order import HandcraftPartItem


def _send_order_with_part(db, qty=100, stock=1000):
    part = create_part(db, {"name": "珠", "category": "小配件"})
    add_stock(db, "part", part.id, stock, "测试入库")
    order = create_handcraft_order(db, "商家A", parts=[{"part_id": part.id, "qty": qty}])
    send_handcraft_order(db, order.id)
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).first()
    return part, order, pi


def test_new_part_item_has_zero_split_counters(db):
    _, _, pi = _send_order_with_part(db)
    assert float(pi.returned_qty or 0) == 0.0
    assert float(pi.consumed_qty or 0) == 0.0


from services.handcraft_receipt import create_handcraft_receipt
from services.inventory import batch_get_stock
from services.jewelry import create_jewelry
from services.bom import set_bom
from models.handcraft_order import HandcraftJewelryItem


def test_direct_part_receive_records_returned_and_adds_stock(db):
    part, order, pi = _send_order_with_part(db, qty=100, stock=1000)
    # after send: stock = 1000 - 100 = 900
    assert batch_get_stock(db, "part", [part.id])[part.id] == 900.0

    create_handcraft_receipt(db, "商家A", items=[
        {"handcraft_part_item_id": pi.id, "qty": 30},
    ])
    db.expire(pi)
    assert float(pi.returned_qty) == 30.0
    assert float(pi.consumed_qty or 0) == 0.0
    assert float(pi.received_qty) == 30.0
    # surplus returned → stock back up by 30
    assert batch_get_stock(db, "part", [part.id])[part.id] == 930.0


def test_jewelry_receive_consumes_parts_into_consumed_bucket(db):
    part = create_part(db, {"name": "珠", "category": "小配件"})
    add_stock(db, "part", part.id, 1000, "入库")
    jewelry = create_jewelry(db, {"name": "项链", "category": "单件"})
    set_bom(db, jewelry.id, part.id, 2)  # 1 件饰品吃 2 颗珠
    order = create_handcraft_order(
        db, "商家A",
        parts=[{"part_id": part.id, "qty": 100}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 10}],
    )
    send_handcraft_order(db, order.id)
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).first()
    ji = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=order.id).first()

    create_handcraft_receipt(db, "商家A", items=[
        {"handcraft_jewelry_item_id": ji.id, "qty": 10},
    ])
    db.expire(pi)
    # 10 件 × 2 = 20 颗进入 consumed，不动库存（库存仍是 send 后的 900）
    assert float(pi.consumed_qty) == 20.0
    assert float(pi.returned_qty or 0) == 0.0
    assert float(pi.received_qty) == 20.0
    assert batch_get_stock(db, "part", [part.id])[part.id] == 900.0


def test_delete_part_receipt_reverses_returned_only(db):
    part, order, pi = _send_order_with_part(db, qty=100, stock=1000)
    receipt = create_handcraft_receipt(db, "商家A", items=[
        {"handcraft_part_item_id": pi.id, "qty": 30},
    ])
    db.expire(pi)
    assert float(pi.returned_qty) == 30.0
    assert batch_get_stock(db, "part", [part.id])[part.id] == 930.0

    from services.handcraft_receipt import delete_handcraft_receipt
    delete_handcraft_receipt(db, receipt.id)
    db.expire(pi)
    assert float(pi.returned_qty) == 0.0
    assert float(pi.consumed_qty or 0) == 0.0
    assert float(pi.received_qty) == 0.0
    assert batch_get_stock(db, "part", [part.id])[part.id] == 900.0


def test_delete_jewelry_receipt_reverses_consumed_only_no_stock(db):
    part = create_part(db, {"name": "珠", "category": "小配件"})
    add_stock(db, "part", part.id, 1000, "入库")
    jewelry = create_jewelry(db, {"name": "项链", "category": "单件"})
    set_bom(db, jewelry.id, part.id, 2)
    order = create_handcraft_order(
        db, "商家A",
        parts=[{"part_id": part.id, "qty": 100}],
        jewelries=[{"jewelry_id": jewelry.id, "qty": 10}],
    )
    send_handcraft_order(db, order.id)
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).first()
    ji = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=order.id).first()
    receipt = create_handcraft_receipt(db, "商家A", items=[{"handcraft_jewelry_item_id": ji.id, "qty": 10}])
    db.expire(pi)
    assert float(pi.consumed_qty) == 20.0

    from services.handcraft_receipt import delete_handcraft_receipt
    delete_handcraft_receipt(db, receipt.id)
    db.expire(pi)
    assert float(pi.consumed_qty) == 0.0
    assert float(pi.returned_qty or 0) == 0.0
    assert float(pi.received_qty) == 0.0
    # 配件库存自始至终未变（消耗不动库存）→ 仍是 send 后的 900
    assert batch_get_stock(db, "part", [part.id])[part.id] == 900.0


def test_auto_consume_reports_shortfall_when_parts_insufficient(db):
    part = create_part(db, {"name": "珠", "category": "小配件"})
    add_stock(db, "part", part.id, 1000, "入库")
    jewelry = create_jewelry(db, {"name": "项链", "category": "单件"})
    set_bom(db, jewelry.id, part.id, 10)  # 需要很多
    order = create_handcraft_order(
        db, "商家A",
        parts=[{"part_id": part.id, "qty": 5}],   # 只发了 5 颗
        jewelries=[{"jewelry_id": jewelry.id, "qty": 10}],  # 需 100 颗
    )
    send_handcraft_order(db, order.id)
    ji = db.query(HandcraftJewelryItem).filter_by(handcraft_order_id=order.id).first()

    receipt = create_handcraft_receipt(db, "商家A", items=[
        {"handcraft_jewelry_item_id": ji.id, "qty": 10},
    ])
    # 95 颗缺口应被上报（100 需求 - 5 实发）
    assert any(
        s["part_id"] == part.id and abs(s["shortfall_qty"] - 95.0) < 1e-6
        for s in receipt.parts_shortfall
    )
