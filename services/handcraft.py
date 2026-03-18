from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
from services._helpers import _next_id
from services.inventory import add_stock, deduct_stock


def create_handcraft_order(
    db: Session,
    supplier_name: str,
    parts: list,
    jewelries: list,
    note: str = None,
) -> HandcraftOrder:
    order_id = _next_id(db, HandcraftOrder, "HC")
    order = HandcraftOrder(id=order_id, supplier_name=supplier_name, status="pending", note=note)
    db.add(order)
    db.flush()
    for p in parts:
        db.add(HandcraftPartItem(
            handcraft_order_id=order_id,
            part_id=p["part_id"],
            qty=p["qty"],
            bom_qty=p.get("bom_qty"),
            unit=p.get("unit", "个"),
            note=p.get("note"),
        ))
    for j in jewelries:
        db.add(HandcraftJewelryItem(
            handcraft_order_id=order_id,
            jewelry_id=j["jewelry_id"],
            qty=j["qty"],
            received_qty=0,
            status="未送出",
            unit=j.get("unit", "套"),
            note=j.get("note"),
        ))
    db.flush()
    return order


def send_handcraft_order(db: Session, handcraft_order_id: str) -> HandcraftOrder:
    order = get_handcraft_order(db, handcraft_order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {handcraft_order_id}")
    if order.status != "pending":
        raise ValueError(f"HandcraftOrder {handcraft_order_id} cannot be sent: current status is '{order.status}'")
    part_items = (
        db.query(HandcraftPartItem)
        .filter(HandcraftPartItem.handcraft_order_id == handcraft_order_id)
        .all()
    )
    if not part_items:
        raise ValueError(f"HandcraftOrder {handcraft_order_id} has no part items and cannot be sent")
    jewelry_items = (
        db.query(HandcraftJewelryItem)
        .filter(HandcraftJewelryItem.handcraft_order_id == handcraft_order_id)
        .all()
    )
    if not jewelry_items:
        raise ValueError(f"HandcraftOrder {handcraft_order_id} has no jewelry items and cannot be sent")
    deducted = []
    try:
        for item in part_items:
            deduct_stock(db, "part", item.part_id, float(item.qty), "手工发出")
            deducted.append((item.part_id, float(item.qty)))
    except ValueError:
        for part_id, qty in deducted:
            add_stock(db, "part", part_id, qty, "手工发出回滚")
        raise
    for ji in jewelry_items:
        ji.status = "制作中"
    order.status = "processing"
    db.flush()
    return order


def receive_handcraft_jewelries(db: Session, handcraft_order_id: str, receipts: list) -> list:
    updated = []
    for receipt in receipts:
        ji = db.query(HandcraftJewelryItem).filter(
            HandcraftJewelryItem.id == receipt["handcraft_jewelry_item_id"]
        ).first()
        if ji is None:
            raise ValueError(f"HandcraftJewelryItem not found: {receipt['handcraft_jewelry_item_id']}")
        if ji.handcraft_order_id != handcraft_order_id:
            raise ValueError(
                f"HandcraftJewelryItem {receipt['handcraft_jewelry_item_id']} does not belong to order {handcraft_order_id}"
            )
        qty = receipt["qty"]
        remaining = ji.qty - (ji.received_qty or 0)
        if qty > remaining:
            raise ValueError(
                f"Cannot receive {qty}: only {remaining} remaining for item {ji.id}"
            )
        ji.received_qty = (ji.received_qty or 0) + qty
        add_stock(db, "jewelry", ji.jewelry_id, qty, "手工完成")
        if ji.received_qty >= ji.qty:
            ji.status = "已收回"
        updated.append(ji)
    db.flush()
    all_jewelry_items = (
        db.query(HandcraftJewelryItem)
        .filter(HandcraftJewelryItem.handcraft_order_id == handcraft_order_id)
        .all()
    )
    if all(ji.status == "已收回" for ji in all_jewelry_items):
        order = get_handcraft_order(db, handcraft_order_id)
        order.status = "completed"
        order.completed_at = datetime.now(timezone.utc)
        db.flush()
    return updated


def get_handcraft_order(db: Session, handcraft_order_id: str) -> Optional[HandcraftOrder]:
    return db.query(HandcraftOrder).filter(HandcraftOrder.id == handcraft_order_id).first()


def list_handcraft_orders(db: Session, status: str = None) -> list:
    q = db.query(HandcraftOrder)
    if status is not None:
        q = q.filter(HandcraftOrder.status == status)
    return q.all()


def get_handcraft_parts(db: Session, order_id: str) -> list:
    return db.query(HandcraftPartItem).filter(
        HandcraftPartItem.handcraft_order_id == order_id
    ).all()


def get_handcraft_jewelries(db: Session, order_id: str) -> list:
    return db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.handcraft_order_id == order_id
    ).all()


def add_handcraft_part(db: Session, order_id: str, item: dict) -> HandcraftPartItem:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    if order.status != "pending":
        raise ValueError(f"Cannot add part: order {order_id} status is '{order.status}', must be 'pending'")
    new_item = HandcraftPartItem(
        handcraft_order_id=order_id,
        part_id=item["part_id"],
        qty=item["qty"],
        bom_qty=item.get("bom_qty"),
        unit=item.get("unit", "个"),
        note=item.get("note"),
    )
    db.add(new_item)
    db.flush()
    return new_item


def update_handcraft_part(db: Session, order_id: str, item_id: int, data: dict) -> HandcraftPartItem:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    if order.status != "pending":
        raise ValueError(f"Cannot update part: order {order_id} status is '{order.status}', must be 'pending'")
    item = db.query(HandcraftPartItem).filter(
        HandcraftPartItem.id == item_id,
        HandcraftPartItem.handcraft_order_id == order_id,
    ).first()
    if item is None:
        raise ValueError(f"HandcraftPartItem {item_id} not found in order {order_id}")
    for field in ("qty", "unit", "note", "bom_qty"):
        if field in data and data[field] is not None:
            setattr(item, field, data[field])
    db.flush()
    return item


def delete_handcraft_part(db: Session, order_id: str, item_id: int) -> None:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    if order.status != "pending":
        raise ValueError(f"Cannot delete part: order {order_id} status is '{order.status}', must be 'pending'")
    item = db.query(HandcraftPartItem).filter(
        HandcraftPartItem.id == item_id,
        HandcraftPartItem.handcraft_order_id == order_id,
    ).first()
    if item is None:
        raise ValueError(f"HandcraftPartItem {item_id} not found in order {order_id}")
    remaining = db.query(HandcraftPartItem).filter(
        HandcraftPartItem.handcraft_order_id == order_id,
        HandcraftPartItem.id != item_id,
    ).count()
    if remaining == 0:
        raise ValueError(f"Cannot delete the last part from order {order_id}; an order must have at least one part item")
    db.delete(item)
    db.flush()


def add_handcraft_jewelry(db: Session, order_id: str, item: dict) -> HandcraftJewelryItem:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    if order.status != "pending":
        raise ValueError(f"Cannot add jewelry: order {order_id} status is '{order.status}', must be 'pending'")
    new_item = HandcraftJewelryItem(
        handcraft_order_id=order_id,
        jewelry_id=item["jewelry_id"],
        qty=item["qty"],
        received_qty=0,
        status="未送出",
        unit=item.get("unit", "套"),
        note=item.get("note"),
    )
    db.add(new_item)
    db.flush()
    return new_item


def update_handcraft_jewelry(db: Session, order_id: str, item_id: int, data: dict) -> HandcraftJewelryItem:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    if order.status != "pending":
        raise ValueError(f"Cannot update jewelry: order {order_id} status is '{order.status}', must be 'pending'")
    item = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.id == item_id,
        HandcraftJewelryItem.handcraft_order_id == order_id,
    ).first()
    if item is None:
        raise ValueError(f"HandcraftJewelryItem {item_id} not found in order {order_id}")
    for field in ("qty", "unit", "note"):
        if field in data and data[field] is not None:
            setattr(item, field, data[field])
    db.flush()
    return item


def delete_handcraft_jewelry(db: Session, order_id: str, item_id: int) -> None:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    if order.status != "pending":
        raise ValueError(f"Cannot delete jewelry: order {order_id} status is '{order.status}', must be 'pending'")
    item = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.id == item_id,
        HandcraftJewelryItem.handcraft_order_id == order_id,
    ).first()
    if item is None:
        raise ValueError(f"HandcraftJewelryItem {item_id} not found in order {order_id}")
    remaining = db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.handcraft_order_id == order_id,
        HandcraftJewelryItem.id != item_id,
    ).count()
    if remaining == 0:
        raise ValueError(f"Cannot delete the last jewelry from order {order_id}; an order must have at least one jewelry item")
    db.delete(item)
    db.flush()


_HANDCRAFT_VALID_STATUSES = {"pending", "processing", "completed"}
_HANDCRAFT_STATUS_RANK = {"pending": 0, "processing": 1, "completed": 2}


def update_handcraft_order_status(db: Session, order_id: str, status: str) -> HandcraftOrder:
    if status not in _HANDCRAFT_VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Valid values: {', '.join(sorted(_HANDCRAFT_VALID_STATUSES))}")
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    current = order.status
    if _HANDCRAFT_STATUS_RANK.get(status, -1) <= _HANDCRAFT_STATUS_RANK.get(current, 99):
        raise ValueError(f"Cannot change status from '{current}' to '{status}': only forward transitions are allowed")
    if current == "pending" and status == "processing":
        raise ValueError("Use POST /send to dispatch a pending order; it deducts inventory and updates item statuses")
    if status == "completed" and order.completed_at is None:
        order.completed_at = datetime.now(timezone.utc)
    order.status = status
    db.flush()
    return order
