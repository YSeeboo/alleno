"""Reusable test seed helpers for handcraft customer breakdown work."""

from models.part import Part
from models.jewelry import Jewelry
from models.bom import Bom
from models.order import Order, OrderTodoBatch, OrderTodoItem, OrderTodoBatchJewelry
from services._helpers import _next_id
from services.inventory import add_stock


def seed_order_with_batch(db, qty: int = 100):
    """Seed an order + jewelry + part + bom + batch + part stock.

    Returns (order_id, batch_id) for use in link_supplier / preview tests.
    Part stock is seeded to qty so link_supplier's availability check passes.
    """
    db.add(Part(id="PJ-DZ-T100", name="测试主石", category="吊坠"))
    db.add(Jewelry(id="SP-T100", name="测试饰品", category="吊坠"))
    db.flush()
    db.add(Bom(id=_next_id(db, Bom, "BM"),
               jewelry_id="SP-T100", part_id="PJ-DZ-T100", qty_per_unit=1))
    db.flush()
    add_stock(db, "part", "PJ-DZ-T100", qty, "test seed")
    db.flush()

    order = Order(id="OR-T100", customer_name="T 客户", status="待生产")
    db.add(order)
    db.flush()

    batch = OrderTodoBatch(order_id=order.id)
    db.add(batch)
    db.flush()

    db.add(OrderTodoBatchJewelry(batch_id=batch.id, jewelry_id="SP-T100", quantity=qty))
    db.add(OrderTodoItem(order_id=order.id, part_id="PJ-DZ-T100",
                         required_qty=qty, batch_id=batch.id))
    db.flush()

    return order.id, batch.id
