from decimal import Decimal
from sqlalchemy import text

from services.part import create_part
from services.inventory import add_stock
from services.handcraft import create_handcraft_order, send_handcraft_order
from models.handcraft_order import HandcraftPartItem
from models.handcraft_receipt import HandcraftReceipt, HandcraftReceiptItem
from database import backfill_handcraft_part_counters


def test_backfill_splits_received_into_returned_and_consumed(db):
    part = create_part(db, {"name": "珠", "category": "小配件"})
    add_stock(db, "part", part.id, 1000, "测试入库")
    order = create_handcraft_order(db, "商家A", parts=[{"part_id": part.id, "qty": 100}])
    send_handcraft_order(db, order.id)
    pi = db.query(HandcraftPartItem).filter_by(handcraft_order_id=order.id).first()

    # Simulate legacy state: received_qty=70, of which 30 came from a direct
    # part receipt and 40 from auto-consume. Counters not yet split.
    pi.received_qty = 70
    pi.returned_qty = 0
    pi.consumed_qty = 0
    receipt = HandcraftReceipt(id="HR-BF1", supplier_name="商家A", status="未付款")
    db.add(receipt)
    db.flush()
    db.add(HandcraftReceiptItem(
        handcraft_receipt_id="HR-BF1",
        handcraft_part_item_id=pi.id,
        item_id=part.id,
        item_type="part",
        qty=30,
        unit="个",
    ))
    db.flush()

    backfill_handcraft_part_counters(db.connection())
    db.expire(pi)

    assert float(pi.returned_qty) == 30.0   # from the part receipt
    assert float(pi.consumed_qty) == 40.0   # 70 - 30
    assert float(pi.received_qty) == 70.0   # unchanged total
