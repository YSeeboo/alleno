from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
from models.jewelry import Jewelry
from models.part import Part
from models.vendor_receipt import VendorReceipt
from services._helpers import _next_id
from services.inventory import add_stock, deduct_stock


def _require_part(db: Session, part_id: str) -> None:
    if db.get(Part, part_id) is None:
        raise ValueError(f"Part not found: {part_id}")


def _require_jewelry(db: Session, jewelry_id: str) -> None:
    if db.get(Jewelry, jewelry_id) is None:
        raise ValueError(f"Jewelry not found: {jewelry_id}")


def _normalize_delivery_images(delivery_images: Optional[list]) -> list[str]:
    cleaned = [str(item).strip() for item in (delivery_images or []) if str(item).strip()]
    if len(cleaned) > 4:
        raise ValueError("发货图片最多上传 4 张")
    return cleaned


def _vendor_receipt_totals_for_handcraft(db: Session, order_id: str) -> dict[tuple[str, str], float]:
    rows = (
        db.query(
            VendorReceipt.item_id,
            VendorReceipt.item_type,
            func.sum(VendorReceipt.qty).label("qty"),
        )
        .filter(
            VendorReceipt.order_id == order_id,
            VendorReceipt.order_type == "handcraft",
        )
        .group_by(VendorReceipt.item_id, VendorReceipt.item_type)
        .all()
    )
    return {(row.item_id, row.item_type): float(row.qty) for row in rows}


def _attach_part_colors(db: Session, items: list[HandcraftPartItem]) -> list[HandcraftPartItem]:
    if not items:
        return items
    part_ids = {item.part_id for item in items}
    parts = {
        part.id: part
        for part in db.query(Part).filter(Part.id.in_(part_ids)).all()
    }
    for item in items:
        part = parts.get(item.part_id)
        item.color = part.color if part else None
    return items


def create_handcraft_order(
    db: Session,
    supplier_name: str,
    parts: list,
    jewelries: Optional[list] = None,
    note: str = None,
) -> HandcraftOrder:
    for p in parts:
        _require_part(db, p["part_id"])
    for j in jewelries or []:
        _require_jewelry(db, j["jewelry_id"])
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
    for j in jewelries or []:
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
    all_jewelry_items = (
        db.query(HandcraftJewelryItem)
        .filter(HandcraftJewelryItem.handcraft_order_id == handcraft_order_id)
        .all()
    )
    if not all_jewelry_items:
        raise ValueError(f"HandcraftOrder {handcraft_order_id} has no jewelry items to receive")
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
    items = (
        db.query(HandcraftPartItem)
        .filter(HandcraftPartItem.handcraft_order_id == order_id)
        .order_by(HandcraftPartItem.id.asc())
        .all()
    )
    return _attach_part_colors(db, items)


def get_handcraft_jewelries(db: Session, order_id: str) -> list:
    return db.query(HandcraftJewelryItem).filter(
        HandcraftJewelryItem.handcraft_order_id == order_id
    ).all()


def update_handcraft_delivery_images(db: Session, order_id: str, delivery_images: Optional[list]) -> HandcraftOrder:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    order.delivery_images = _normalize_delivery_images(delivery_images)
    db.flush()
    return order


def add_handcraft_part(db: Session, order_id: str, item: dict) -> HandcraftPartItem:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")
    if order.status != "pending":
        raise ValueError(f"Cannot add part: order {order_id} status is '{order.status}', must be 'pending'")
    _require_part(db, item["part_id"])
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
    return _attach_part_colors(db, [new_item])[0]


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
    for field in ("qty", "unit", "note"):
        if field in data and data[field] is not None:
            setattr(item, field, data[field])
    if "bom_qty" in data:
        item.bom_qty = data["bom_qty"]  # allow setting to None to clear
    db.flush()
    return _attach_part_colors(db, [item])[0]


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
    _require_jewelry(db, item["jewelry_id"])
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


def delete_handcraft_order(db: Session, order_id: str) -> None:
    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")

    part_items = get_handcraft_parts(db, order_id)
    jewelry_items = get_handcraft_jewelries(db, order_id)
    vendor_received = _vendor_receipt_totals_for_handcraft(db, order_id)

    jewelry_received_totals: dict[str, float] = {}
    for jewelry_item in jewelry_items:
        jewelry_received_totals[jewelry_item.jewelry_id] = jewelry_received_totals.get(
            jewelry_item.jewelry_id,
            0.0,
        ) + float(jewelry_item.received_qty or 0)

    for jewelry_id, total_received in jewelry_received_totals.items():
        legacy_received = total_received - vendor_received.get((jewelry_id, "jewelry"), 0.0)
        if legacy_received > 0:
            deduct_stock(db, "jewelry", jewelry_id, legacy_received, "手工完成撤回")

    receipts = db.query(VendorReceipt).filter(
        VendorReceipt.order_id == order_id,
        VendorReceipt.order_type == "handcraft",
    ).all()
    for receipt in receipts:
        reason = "手工完成撤回" if receipt.item_type == "jewelry" else "手工退回撤回"
        deduct_stock(db, receipt.item_type, receipt.item_id, float(receipt.qty), reason)
        db.delete(receipt)

    if order.status != "pending":
        part_totals: dict[str, float] = {}
        for part_item in part_items:
            part_totals[part_item.part_id] = part_totals.get(part_item.part_id, 0.0) + float(part_item.qty)
        for part_id, total_sent in part_totals.items():
            add_stock(db, "part", part_id, total_sent, "手工发出撤回")

    db.query(HandcraftPartItem).filter(HandcraftPartItem.handcraft_order_id == order_id).delete(synchronize_session=False)
    db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.handcraft_order_id == order_id).delete(synchronize_session=False)
    db.flush()
    db.delete(order)
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
    if current == "processing" and status == "completed":
        raise ValueError("Use POST /receive to complete a processing order; items must be fully received first")
    order.status = status
    db.flush()
    return order
