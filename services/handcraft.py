from datetime import date as date_type
from typing import Optional

from sqlalchemy import Date, func, or_
from sqlalchemy.orm import Session

from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
from models.jewelry import Jewelry
from models.part import Part
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
    # Aggregate qty by part_id to avoid double-deducting when same part appears multiple times
    part_totals: dict[str, float] = {}
    for item in part_items:
        part_totals[item.part_id] = part_totals.get(item.part_id, 0.0) + float(item.qty)
    deducted = []
    try:
        for part_id, total_qty in part_totals.items():
            deduct_stock(db, "part", part_id, total_qty, "手工发出")
            deducted.append((part_id, total_qty))
    except ValueError:
        for part_id, qty in deducted:
            add_stock(db, "part", part_id, qty, "手工发出回滚")
        raise
    for pi in part_items:
        pi.status = "制作中"
    for ji in jewelry_items:
        ji.status = "制作中"
    order.status = "processing"
    db.flush()
    return order



def get_handcraft_order(db: Session, handcraft_order_id: str) -> Optional[HandcraftOrder]:
    return db.query(HandcraftOrder).filter(HandcraftOrder.id == handcraft_order_id).first()


def list_handcraft_orders(db: Session, status: str = None, supplier_name: str = None) -> list:
    q = db.query(HandcraftOrder)
    if status is not None:
        q = q.filter(HandcraftOrder.status == status)
    if supplier_name is not None:
        q = q.filter(HandcraftOrder.supplier_name == supplier_name)
    return q.all()


def get_handcraft_supplier_names(db: Session) -> list[str]:
    rows = db.query(HandcraftOrder.supplier_name).distinct().all()
    return [row[0] for row in rows]


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
    if order.status not in ("pending", "processing"):
        raise ValueError(f"Cannot add jewelry: order {order_id} status is '{order.status}', must be 'pending' or 'processing'")
    _require_jewelry(db, item["jewelry_id"])
    item_status = "制作中" if order.status == "processing" else "未送出"
    new_item = HandcraftJewelryItem(
        handcraft_order_id=order_id,
        jewelry_id=item["jewelry_id"],
        qty=item["qty"],
        received_qty=0,
        status=item_status,
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
    from models.handcraft_receipt import HandcraftReceipt, HandcraftReceiptItem
    from sqlalchemy import or_

    order = get_handcraft_order(db, order_id)
    if order is None:
        raise ValueError(f"HandcraftOrder not found: {order_id}")

    part_items = get_handcraft_parts(db, order_id)
    jewelry_items = get_handcraft_jewelries(db, order_id)

    # Reverse HandcraftReceiptItem stock operations
    part_item_ids = [p.id for p in part_items]
    jewelry_item_ids = [j.id for j in jewelry_items]
    filter_clauses = []
    if part_item_ids:
        filter_clauses.append(HandcraftReceiptItem.handcraft_part_item_id.in_(part_item_ids))
    if jewelry_item_ids:
        filter_clauses.append(HandcraftReceiptItem.handcraft_jewelry_item_id.in_(jewelry_item_ids))

    related_receipt_items = []
    if filter_clauses:
        related_receipt_items = db.query(HandcraftReceiptItem).filter(
            or_(*filter_clauses)
        ).all()

    affected_receipt_ids = {ri.handcraft_receipt_id for ri in related_receipt_items}

    # Block deletion if any related receipt is paid
    for receipt_id in affected_receipt_ids:
        receipt = db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first()
        if receipt and receipt.status == "已付款":
            raise ValueError(f"手工单关联的回收单 {receipt_id} 已付款，无法删除手工单")

    for ri in related_receipt_items:
        if ri.item_type == "part":
            deduct_stock(db, "part", ri.item_id, float(ri.qty), "手工收回撤回")
        else:
            deduct_stock(db, "jewelry", ri.item_id, float(ri.qty), "手工收回撤回")
        db.delete(ri)
    db.flush()

    # Clean up empty receipts, recalc non-empty ones
    for receipt_id in affected_receipt_ids:
        remaining = db.query(HandcraftReceiptItem).filter(
            HandcraftReceiptItem.handcraft_receipt_id == receipt_id
        ).count()
        if remaining == 0:
            receipt = db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first()
            if receipt:
                db.delete(receipt)
        else:
            from services.handcraft_receipt import _recalc_total
            receipt = db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first()
            if receipt:
                _recalc_total(db, receipt)

    # Reverse sent stock for parts
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


def list_handcraft_pending_receive_items(
    db: Session,
    keyword: str = None,
    supplier_name: str = None,
    date_on: date_type = None,
    exclude_part_item_ids: list[int] = None,
    exclude_jewelry_item_ids: list[int] = None,
) -> list:
    """Return part items and jewelry items from processing handcraft orders
    that still have remaining qty to receive."""
    results = []

    # Part items
    pq = (
        db.query(
            HandcraftPartItem.id,
            HandcraftPartItem.handcraft_order_id,
            HandcraftOrder.supplier_name,
            HandcraftPartItem.part_id.label("item_id"),
            Part.name.label("item_name"),
            Part.image.label("item_image"),
            Part.color,
            HandcraftPartItem.qty,
            HandcraftPartItem.received_qty,
            HandcraftPartItem.unit,
            HandcraftOrder.created_at,
        )
        .join(HandcraftOrder, HandcraftPartItem.handcraft_order_id == HandcraftOrder.id)
        .join(Part, HandcraftPartItem.part_id == Part.id)
        .filter(
            HandcraftPartItem.status == "制作中",
            func.coalesce(HandcraftPartItem.received_qty, 0) < HandcraftPartItem.qty,
        )
    )
    if supplier_name:
        pq = pq.filter(HandcraftOrder.supplier_name == supplier_name)
    if date_on:
        pq = pq.filter(func.cast(HandcraftOrder.created_at, Date) == date_on)
    if exclude_part_item_ids:
        pq = pq.filter(HandcraftPartItem.id.notin_(exclude_part_item_ids))
    if keyword:
        like = f"%{keyword}%"
        pq = pq.filter(or_(Part.id.ilike(like), Part.name.ilike(like)))
    pq = pq.order_by(HandcraftOrder.created_at.desc())

    for row in pq.all():
        results.append({
            "id": row.id,
            "handcraft_order_id": row.handcraft_order_id,
            "supplier_name": row.supplier_name,
            "item_id": row.item_id,
            "item_name": row.item_name,
            "item_image": row.item_image,
            "item_type": "part",
            "color": row.color,
            "qty": float(row.qty),
            "received_qty": float(row.received_qty or 0),
            "unit": row.unit,
            "created_at": row.created_at,
        })

    # Jewelry items
    jq = (
        db.query(
            HandcraftJewelryItem.id,
            HandcraftJewelryItem.handcraft_order_id,
            HandcraftOrder.supplier_name,
            HandcraftJewelryItem.jewelry_id.label("item_id"),
            Jewelry.name.label("item_name"),
            Jewelry.image.label("item_image"),
            HandcraftJewelryItem.qty,
            HandcraftJewelryItem.received_qty,
            HandcraftJewelryItem.unit,
            HandcraftOrder.created_at,
        )
        .join(HandcraftOrder, HandcraftJewelryItem.handcraft_order_id == HandcraftOrder.id)
        .join(Jewelry, HandcraftJewelryItem.jewelry_id == Jewelry.id)
        .filter(
            HandcraftJewelryItem.status == "制作中",
            func.coalesce(HandcraftJewelryItem.received_qty, 0) < HandcraftJewelryItem.qty,
        )
    )
    if supplier_name:
        jq = jq.filter(HandcraftOrder.supplier_name == supplier_name)
    if date_on:
        jq = jq.filter(func.cast(HandcraftOrder.created_at, Date) == date_on)
    if exclude_jewelry_item_ids:
        jq = jq.filter(HandcraftJewelryItem.id.notin_(exclude_jewelry_item_ids))
    if keyword:
        like = f"%{keyword}%"
        jq = jq.filter(or_(Jewelry.id.ilike(like), Jewelry.name.ilike(like)))
    jq = jq.order_by(HandcraftOrder.created_at.desc())

    for row in jq.all():
        results.append({
            "id": row.id,
            "handcraft_order_id": row.handcraft_order_id,
            "supplier_name": row.supplier_name,
            "item_id": row.item_id,
            "item_name": row.item_name,
            "item_image": row.item_image,
            "item_type": "jewelry",
            "color": None,
            "qty": int(row.qty),
            "received_qty": int(row.received_qty or 0),
            "unit": row.unit,
            "created_at": row.created_at,
        })

    return results
