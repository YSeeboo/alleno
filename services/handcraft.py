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
            note=p.get("note"),
        ))
    for j in jewelries:
        db.add(HandcraftJewelryItem(
            handcraft_order_id=order_id,
            jewelry_id=j["jewelry_id"],
            qty=j["qty"],
            received_qty=0,
            status="未送出",
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
    jewelry_items = (
        db.query(HandcraftJewelryItem)
        .filter(HandcraftJewelryItem.handcraft_order_id == handcraft_order_id)
        .all()
    )
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
