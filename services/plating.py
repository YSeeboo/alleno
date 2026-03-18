from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models.part import Part
from models.plating_order import PlatingOrder, PlatingOrderItem
from services._helpers import _next_id
from services.inventory import add_stock, deduct_stock


def _require_part(db: Session, part_id: str) -> None:
    if db.get(Part, part_id) is None:
        raise ValueError(f"Part not found: {part_id}")


def create_plating_order(db: Session, supplier_name: str, items: list, note: str = None) -> PlatingOrder:
    for item in items:
        _require_part(db, item["part_id"])
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
            unit=item.get("unit", "个"),
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
    if not items:
        raise ValueError(f"PlatingOrder {plating_order_id} has no items and cannot be sent")
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
        remaining = float(item.qty) - float(item.received_qty or 0)
        if qty > remaining:
            raise ValueError(
                f"Cannot receive {qty}: only {remaining} remaining for item {item.id}"
            )
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


def get_plating_items(db: Session, order_id: str) -> list:
    return db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order_id
    ).all()


def add_plating_item(db: Session, order_id: str, item: dict) -> PlatingOrderItem:
    order = get_plating_order(db, order_id)
    if order is None:
        raise ValueError(f"PlatingOrder not found: {order_id}")
    if order.status != "pending":
        raise ValueError(f"Cannot add item: order {order_id} status is '{order.status}', must be 'pending'")
    _require_part(db, item["part_id"])
    new_item = PlatingOrderItem(
        plating_order_id=order_id,
        part_id=item["part_id"],
        qty=item["qty"],
        received_qty=0,
        status="未送出",
        plating_method=item.get("plating_method"),
        unit=item.get("unit", "个"),
        note=item.get("note"),
    )
    db.add(new_item)
    db.flush()
    return new_item


def update_plating_item(db: Session, order_id: str, item_id: int, data: dict) -> PlatingOrderItem:
    order = get_plating_order(db, order_id)
    if order is None:
        raise ValueError(f"PlatingOrder not found: {order_id}")
    if order.status != "pending":
        raise ValueError(f"Cannot update item: order {order_id} status is '{order.status}', must be 'pending'")
    item = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.id == item_id,
        PlatingOrderItem.plating_order_id == order_id,
    ).first()
    if item is None:
        raise ValueError(f"PlatingOrderItem {item_id} not found in order {order_id}")
    for field in ("qty", "unit", "plating_method", "note"):
        if field in data and data[field] is not None:
            setattr(item, field, data[field])
    db.flush()
    return item


def delete_plating_item(db: Session, order_id: str, item_id: int) -> None:
    order = get_plating_order(db, order_id)
    if order is None:
        raise ValueError(f"PlatingOrder not found: {order_id}")
    if order.status != "pending":
        raise ValueError(f"Cannot delete item: order {order_id} status is '{order.status}', must be 'pending'")
    item = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.id == item_id,
        PlatingOrderItem.plating_order_id == order_id,
    ).first()
    if item is None:
        raise ValueError(f"PlatingOrderItem {item_id} not found in order {order_id}")
    remaining = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.plating_order_id == order_id,
        PlatingOrderItem.id != item_id,
    ).count()
    if remaining == 0:
        raise ValueError(f"Cannot delete the last item from order {order_id}; an order must have at least one item")
    db.delete(item)
    db.flush()


_PLATING_VALID_STATUSES = {"pending", "processing", "completed"}
_PLATING_STATUS_RANK = {"pending": 0, "processing": 1, "completed": 2}


def update_plating_order_status(db: Session, order_id: str, status: str) -> PlatingOrder:
    if status not in _PLATING_VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Valid values: {', '.join(sorted(_PLATING_VALID_STATUSES))}")
    order = get_plating_order(db, order_id)
    if order is None:
        raise ValueError(f"PlatingOrder not found: {order_id}")
    current = order.status
    if _PLATING_STATUS_RANK.get(status, -1) <= _PLATING_STATUS_RANK.get(current, 99):
        raise ValueError(f"Cannot change status from '{current}' to '{status}': only forward transitions are allowed")
    if current == "pending" and status == "processing":
        raise ValueError("Use POST /send to dispatch a pending order; it deducts inventory and updates item statuses")
    if current == "processing" and status == "completed":
        raise ValueError("Use POST /receive to complete a processing order; items must be fully received first")
    order.status = status
    db.flush()
    return order
