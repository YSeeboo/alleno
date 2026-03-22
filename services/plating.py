from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from models.part import Part
from models.plating_order import PlatingOrder, PlatingOrderItem
from models.vendor_receipt import VendorReceipt
from services._helpers import _next_id
from services.inventory import add_stock, deduct_stock


def _require_part(db: Session, part_id: str) -> None:
    if db.get(Part, part_id) is None:
        raise ValueError(f"Part not found: {part_id}")


def _normalize_delivery_images(delivery_images: Optional[list]) -> list[str]:
    cleaned = [str(item).strip() for item in (delivery_images or []) if str(item).strip()]
    if len(cleaned) > 4:
        raise ValueError("发货图片最多上传 4 张")
    return cleaned


def _vendor_receipt_totals_for_plating(db: Session, order_id: str) -> dict[str, float]:
    rows = (
        db.query(VendorReceipt.item_id, func.sum(VendorReceipt.qty).label("qty"))
        .filter(
            VendorReceipt.order_id == order_id,
            VendorReceipt.order_type == "plating",
            VendorReceipt.item_type == "part",
        )
        .group_by(VendorReceipt.item_id)
        .all()
    )
    return {row.item_id: float(row.qty) for row in rows}


def create_plating_order(db: Session, supplier_name: str, items: list, note: str = None) -> PlatingOrder:
    for item in items:
        _require_part(db, item["part_id"])
        if item.get("receive_part_id"):
            _require_part(db, item["receive_part_id"])
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
            receive_part_id=item.get("receive_part_id"),
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
        receive_id = item.receive_part_id or item.part_id
        add_stock(db, "part", receive_id, qty, "电镀收回")
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
    return (
        db.query(PlatingOrderItem)
        .filter(PlatingOrderItem.plating_order_id == order_id)
        .order_by(PlatingOrderItem.id.asc())
        .all()
    )


def add_plating_item(db: Session, order_id: str, item: dict) -> PlatingOrderItem:
    order = get_plating_order(db, order_id)
    if order is None:
        raise ValueError(f"PlatingOrder not found: {order_id}")
    if order.status != "pending":
        raise ValueError(f"Cannot add item: order {order_id} status is '{order.status}', must be 'pending'")
    _require_part(db, item["part_id"])
    if item.get("receive_part_id"):
        _require_part(db, item["receive_part_id"])
    new_item = PlatingOrderItem(
        plating_order_id=order_id,
        part_id=item["part_id"],
        qty=item["qty"],
        received_qty=0,
        status="未送出",
        plating_method=item.get("plating_method"),
        unit=item.get("unit", "个"),
        note=item.get("note"),
        receive_part_id=item.get("receive_part_id"),
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
    if "part_id" in data:
        if data["part_id"] is None:
            raise ValueError("发出配件不能为空")
        _require_part(db, data["part_id"])
        # Only clear receive_part_id when part_id actually changes
        if data["part_id"] != item.part_id:
            item.part_id = data["part_id"]
            if "receive_part_id" not in data:
                item.receive_part_id = None
    if "receive_part_id" in data:
        if data["receive_part_id"] is not None:
            _require_part(db, data["receive_part_id"])
            # Validate receive part belongs to same family as send part
            send_part_id = item.part_id
            recv_part = db.get(Part, data["receive_part_id"])
            send_part = db.get(Part, send_part_id)
            send_root = send_part.parent_part_id or send_part.id
            recv_root = recv_part.parent_part_id or recv_part.id
            if send_root != recv_root:
                raise ValueError("收回配件必须与发出配件属于同一配件族")
        item.receive_part_id = data["receive_part_id"]
    for field in ("qty", "unit", "note"):
        if field in data and data[field] is not None:
            setattr(item, field, data[field])
    if "plating_method" in data:
        item.plating_method = data["plating_method"]
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


def delete_plating_order(db: Session, order_id: str) -> None:
    order = get_plating_order(db, order_id)
    if order is None:
        raise ValueError(f"PlatingOrder not found: {order_id}")

    items = get_plating_items(db, order_id)
    vendor_received = _vendor_receipt_totals_for_plating(db, order_id)

    sent_by_part: dict[str, float] = {}
    received_by_receive_part: dict[str, float] = {}
    for item in items:
        sent_by_part[item.part_id] = sent_by_part.get(item.part_id, 0.0) + float(item.qty)
        receive_id = item.receive_part_id or item.part_id
        received_by_receive_part[receive_id] = received_by_receive_part.get(receive_id, 0.0) + float(item.received_qty or 0)

    for receive_id, total_received in received_by_receive_part.items():
        legacy_received = total_received - vendor_received.get(receive_id, 0.0)
        if legacy_received > 0:
            deduct_stock(db, "part", receive_id, legacy_received, "电镀收回撤回")

    receipts = db.query(VendorReceipt).filter(
        VendorReceipt.order_id == order_id,
        VendorReceipt.order_type == "plating",
    ).all()
    for receipt in receipts:
        deduct_stock(db, receipt.item_type, receipt.item_id, float(receipt.qty), "电镀收回撤回")
        db.delete(receipt)

    if order.status != "pending":
        for part_id, total_sent in sent_by_part.items():
            add_stock(db, "part", part_id, total_sent, "电镀发出撤回")

    db.query(PlatingOrderItem).filter(PlatingOrderItem.plating_order_id == order_id).delete(synchronize_session=False)
    db.flush()
    db.delete(order)
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


def list_pending_receive_items(db: Session, part_keyword: str = None) -> list:
    SendPart = aliased(Part)
    ReceivePart = aliased(Part)
    q = (
        db.query(
            PlatingOrderItem.id,
            PlatingOrderItem.plating_order_id,
            PlatingOrder.supplier_name,
            PlatingOrderItem.part_id,
            SendPart.name.label("part_name"),
            SendPart.image.label("part_image"),
            PlatingOrderItem.receive_part_id,
            ReceivePart.name.label("receive_part_name"),
            PlatingOrderItem.plating_method,
            PlatingOrderItem.qty,
            PlatingOrderItem.received_qty,
            PlatingOrderItem.unit,
        )
        .join(PlatingOrder, PlatingOrderItem.plating_order_id == PlatingOrder.id)
        .join(SendPart, PlatingOrderItem.part_id == SendPart.id)
        .outerjoin(ReceivePart, PlatingOrderItem.receive_part_id == ReceivePart.id)
        .filter(
            PlatingOrderItem.status == "电镀中",
            func.coalesce(PlatingOrderItem.received_qty, 0) < PlatingOrderItem.qty,
        )
    )
    if part_keyword:
        like_pattern = f"%{part_keyword}%"
        q = q.filter(
            or_(
                SendPart.id.ilike(like_pattern),
                SendPart.name.ilike(like_pattern),
                ReceivePart.id.ilike(like_pattern),
                ReceivePart.name.ilike(like_pattern),
            )
        )
    q = q.order_by(PlatingOrder.created_at.desc())
    rows = q.all()
    return [
        {
            "id": row.id,
            "plating_order_id": row.plating_order_id,
            "supplier_name": row.supplier_name,
            "part_id": row.part_id,
            "part_name": row.part_name,
            "part_image": row.part_image,
            "receive_part_id": row.receive_part_id,
            "receive_part_name": row.receive_part_name,
            "plating_method": row.plating_method,
            "qty": float(row.qty),
            "received_qty": float(row.received_qty or 0),
            "unit": row.unit,
        }
        for row in rows
    ]


def update_plating_delivery_images(db: Session, order_id: str, delivery_images: Optional[list]) -> PlatingOrder:
    order = get_plating_order(db, order_id)
    if order is None:
        raise ValueError(f"PlatingOrder not found: {order_id}")
    order.delivery_images = _normalize_delivery_images(delivery_images)
    db.flush()
    return order
