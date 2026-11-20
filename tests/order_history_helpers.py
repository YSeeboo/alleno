"""Explicit test-only legacy fixtures. Never use this in application code.

Historical compatibility tests predate the automatic fulfillment ledger. Remove
only a pristine fixture's ledger, before any fulfillment operations, to model
an order that was already present before the unified flow was introduced.
"""
from models.order_fulfillment import OrderFulfillment
from services.order import create_order


def as_historical_order(db, order_id):
    ledger = db.get(OrderFulfillment, order_id)
    assert ledger is not None
    db.delete(ledger)
    db.flush()


def create_historical_order(db, *args, **kwargs):
    order = create_order(db, *args, **kwargs)
    as_historical_order(db, order.id)
    return order
