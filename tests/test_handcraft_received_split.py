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
