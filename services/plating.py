from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models.plating_order import PlatingOrder, PlatingOrderItem
from services._helpers import _next_id
from services.inventory import add_stock, deduct_stock


def create_plating_order(db: Session, supplier_name: str, items: list, note: str = None) -> PlatingOrder:
    order_id = _next_id(db, PlatingOrder, "EP")
    order = PlatingOrder(id=order_id, supplier_name=supplier_name, status="pending", note=note)
    db.add(order)
    db.flush()
    for item in items:
        db.add(PlatingOrderItem(
            plating_order_id=order_id,
            part_id=item["part_id"],
            qty=item["qty"],
            received_qty=0,
            status="未送出",
            plating_method=item.get("plating_method"),
            note=item.get("note"),
        ))
    db.flush()
    return order


def send_plating_order(db: Session, plating_order_id: str) -> PlatingOrder:
    order = get_plating_order(db, plating_order_id)
    if order is None:
        raise ValueError(f"PlatingOrder not found: {plating_order_id}")
    if order.status != "pending":
        raise ValueError(f"PlatingOrder {plating_order_id} cannot be sent: current status is '{order.status}'")
    items = (
        db.query(PlatingOrderItem)
        .filter(PlatingOrderItem.plating_order_id == plating_order_id)
        .all()
    )
    deducted = []
    try:
        for item in items:
            deduct_stock(db, "part", item.part_id, float(item.qty), "电镀发出")
            deducted.append((item.part_id, float(item.qty)))
            item.status = "电镀中"
    except ValueError:
        # Roll back already-deducted stock by adding it back
        for part_id, qty in deducted:
            add_stock(db, "part", part_id, qty, "电镀发出回滚")
        raise
    order.status = "processing"
    db.flush()
    return order


def receive_plating_items(db: Session, plating_order_id: str, receipts: list) -> list:
    updated = []
    for receipt in receipts:
        item = db.query(PlatingOrderItem).filter(
            PlatingOrderItem.id == receipt["plating_order_item_id"]
        ).first()
        if item is None:
            raise ValueError(f"PlatingOrderItem not found: {receipt['plating_order_item_id']}")
        if item.plating_order_id != plating_order_id:
            raise ValueError(
                f"PlatingOrderItem {receipt['plating_order_item_id']} does not belong to order {plating_order_id}"
            )
        qty = receipt["qty"]
        item.received_qty = float(item.received_qty or 0) + qty
        add_stock(db, "part", item.part_id, qty, "电镀收回")
        if float(item.received_qty) >= float(item.qty):
            item.status = "已收回"
        updated.append(item)
    db.flush()
    # Check if all items are received
    all_items = (
        db.query(PlatingOrderItem)
        .filter(PlatingOrderItem.plating_order_id == plating_order_id)
        .all()
    )
    if all(i.status == "已收回" for i in all_items):
        order = get_plating_order(db, plating_order_id)
        order.status = "completed"
        order.completed_at = datetime.now(timezone.utc)
        db.flush()
    return updated


def get_plating_order(db: Session, plating_order_id: str) -> Optional[PlatingOrder]:
    return db.query(PlatingOrder).filter(PlatingOrder.id == plating_order_id).first()


def list_plating_orders(db: Session, status: str = None) -> list:
    q = db.query(PlatingOrder)
    if status is not None:
        q = q.filter(PlatingOrder.status == status)
    return q.all()
