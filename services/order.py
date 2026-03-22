from typing import Optional

from sqlalchemy.orm import Session

from models.order import Order, OrderItem
from services._helpers import _next_id
from services.bom import get_bom

_VALID_STATUSES = {"待生产", "生产中", "已完成"}


def create_order(db: Session, customer_name: str, items: list) -> Order:
    order_id = _next_id(db, Order, "OR")
    total = 0.0
    order = Order(id=order_id, customer_name=customer_name)
    db.add(order)
    db.flush()
    for item in items:
        unit_price = round(item["unit_price"], 3)
        subtotal = round(item["quantity"] * unit_price, 3)
        total += subtotal
        db.add(OrderItem(
            order_id=order_id,
            jewelry_id=item["jewelry_id"],
            quantity=item["quantity"],
            unit_price=unit_price,
            remarks=item.get("remarks"),
        ))
    order.total_amount = round(total, 3)
    db.flush()
    return order


def get_order(db: Session, order_id: str) -> Optional[Order]:
    return db.query(Order).filter(Order.id == order_id).first()


def list_orders(db: Session, status: Optional[str] = None, customer_name: Optional[str] = None) -> list:
    q = db.query(Order)
    if status is not None:
        q = q.filter(Order.status == status)
    if customer_name is not None:
        q = q.filter(Order.customer_name.contains(customer_name))
    return q.order_by(Order.created_at.desc()).all()


def get_order_items(db: Session, order_id: str) -> list:
    return db.query(OrderItem).filter(OrderItem.order_id == order_id).all()


def get_parts_summary(db: Session, order_id: str) -> dict:
    items = get_order_items(db, order_id)
    summary: dict = {}
    for item in items:
        bom_rows = get_bom(db, item.jewelry_id)
        for row in bom_rows:
            part_id = row.part_id
            needed = float(row.qty_per_unit) * item.quantity
            summary[part_id] = summary.get(part_id, 0.0) + needed
    return summary


def update_order_status(db: Session, order_id: str, status: str) -> Order:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {_VALID_STATUSES}")
    order = get_order(db, order_id)
    if order is None:
        raise ValueError(f"Order not found: {order_id}")
    order.status = status
    db.flush()
    return order
