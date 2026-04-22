from datetime import datetime, timezone, date as date_type
from typing import Optional

from sqlalchemy import func, Date
from sqlalchemy.orm import Session, aliased

from models.part import Part
from models.plating_order import PlatingOrder, PlatingOrderItem
from models.vendor_receipt import VendorReceipt
from services._helpers import _next_id, keyword_filter
from services.inventory import add_stock, batch_get_stock, deduct_stock


def _user_date_to_datetime(d: Optional[date_type]) -> Optional[datetime]:
    """Store a user-supplied date as midnight. Same-day ordering is handled by
    an `id DESC` tie-breaker in list queries, not by fabricating a time-of-day."""
    if d is None:
        return None
    return datetime.combine(d, datetime.min.time())


def _replace_date(existing: Optional[datetime], new_date: date_type) -> datetime:
    """Combine new_date with the time-of-day from existing; fall back to midnight."""
    time_of_day = existing.time() if existing else datetime.min.time()
    return datetime.combine(new_date, time_of_day)


def _require_part(db: Session, part_id: str) -> None:
    if db.get(Part, part_id) is None:
        raise ValueError(f"Part not found: {part_id}")


def _normalize_delivery_images(delivery_images: Optional[list]) -> list[str]:
    cleaned = [str(item).strip() for item in (delivery_images or []) if str(item).strip()]
    if len(cleaned) > 10:
        raise ValueError("发货图片最多上传 10 张")
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


def create_plating_order(db: Session, supplier_name: str, items: list, note: str = None, created_at: Optional[date_type] = None) -> PlatingOrder:
    for item in items:
        _require_part(db, item["part_id"])
        if item.get("receive_part_id"):
            _require_part(db, item["receive_part_id"])
    order_id = _next_id(db, PlatingOrder, "EP")
    order = PlatingOrder(id=order_id, supplier_name=supplier_name, status="pending", note=note)
    if created_at is not None:
        order.created_at = _user_date_to_datetime(created_at)
    db.add(order)
    db.flush()
    for item in items:
        db.add(PlatingOrderItem(
            plating_order_id=order_id,
            part_id=item["part_id"],
            qty=item["qty"],
            weight=item.get("weight"),
            weight_unit=item.get("weight_unit"),
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
    # Aggregate total qty per part and batch-check stock before deducting
    part_totals: dict[str, float] = {}
    for item in items:
        part_totals[item.part_id] = part_totals.get(item.part_id, 0.0) + float(item.qty)
    stocks = batch_get_stock(db, "part", list(part_totals.keys()))
    insufficient = []
    for part_id, total_qty in part_totals.items():
        current = stocks.get(part_id, 0.0)
        if current < total_qty:
            insufficient.append(f"{part_id} 当前库存 {current}，需要 {total_qty}")
    if insufficient:
        raise ValueError("库存不足：" + "；".join(insufficient))
    deducted = []
    try:
        for part_id, total_qty in part_totals.items():
            deduct_stock(db, "part", part_id, total_qty, "电镀发出")
            deducted.append((part_id, total_qty))
    except Exception:
        for part_id, qty in deducted:
            add_stock(db, "part", part_id, qty, "电镀发出回滚")
        raise
    for item in items:
        item.status = "电镀中"
    order.status = "processing"
    db.flush()
    return order



def get_plating_order(db: Session, plating_order_id: str) -> Optional[PlatingOrder]:
    return db.query(PlatingOrder).filter(PlatingOrder.id == plating_order_id).first()


def list_plating_orders(db: Session, status: str = None, supplier_name: str = None) -> list:
    # An explicitly empty / whitespace-only supplier_name means "caller
    # asked for this supplier but the value is empty" — return no rows
    # instead of falling through to an unfiltered query. supplier_name=None
    # (parameter not provided) still returns all rows.
    if supplier_name is not None and not supplier_name.strip():
        return []
    q = db.query(PlatingOrder)
    if status is not None:
        q = q.filter(PlatingOrder.status == status)
    clause = keyword_filter(supplier_name, PlatingOrder.supplier_name)
    if clause is not None:
        q = q.filter(clause)
    return q.order_by(PlatingOrder.created_at.desc(), PlatingOrder.id.desc()).all()


def get_plating_items(db: Session, order_id: str) -> list:
    from models.production_loss import ProductionLoss
    items = (
        db.query(PlatingOrderItem)
        .filter(PlatingOrderItem.plating_order_id == order_id)
        .order_by(PlatingOrderItem.id.asc())
        .all()
    )
    # Enrich with loss_qty
    losses = (
        db.query(ProductionLoss)
        .filter(ProductionLoss.order_id == order_id, ProductionLoss.order_type == "plating")
        .all()
    )
    loss_map = {l.item_id: float(l.loss_qty) for l in losses}
    for item in items:
        item.loss_qty = loss_map.get(item.id)
    return items


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
        weight=item.get("weight"),
        weight_unit=item.get("weight_unit"),
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
    for wf in ("weight", "weight_unit"):
        if wf in data:
            setattr(item, wf, data[wf])
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
    from models.plating_receipt import PlatingReceiptItem

    order = get_plating_order(db, order_id)
    if order is None:
        raise ValueError(f"PlatingOrder not found: {order_id}")

    items = get_plating_items(db, order_id)
    vendor_received = _vendor_receipt_totals_for_plating(db, order_id)

    # Compute PlatingReceiptItem totals per receive_part_id
    item_ids = [item.id for item in items]
    receipt_items = db.query(PlatingReceiptItem).filter(
        PlatingReceiptItem.plating_order_item_id.in_(item_ids)
    ).all() if item_ids else []
    plating_receipt_received: dict[str, float] = {}
    for ri in receipt_items:
        plating_receipt_received[ri.part_id] = plating_receipt_received.get(ri.part_id, 0.0) + float(ri.qty)

    sent_by_part: dict[str, float] = {}
    received_by_receive_part: dict[str, float] = {}
    for item in items:
        sent_by_part[item.part_id] = sent_by_part.get(item.part_id, 0.0) + float(item.qty)
        receive_id = item.receive_part_id or item.part_id
        received_by_receive_part[receive_id] = received_by_receive_part.get(receive_id, 0.0) + float(item.received_qty or 0)

    for receive_id, total_received in received_by_receive_part.items():
        legacy_received = total_received - vendor_received.get(receive_id, 0.0) - plating_receipt_received.get(receive_id, 0.0)
        if legacy_received > 0:
            deduct_stock(db, "part", receive_id, legacy_received, "电镀收回撤回")

    receipts = db.query(VendorReceipt).filter(
        VendorReceipt.order_id == order_id,
        VendorReceipt.order_type == "plating",
    ).all()
    for receipt in receipts:
        deduct_stock(db, receipt.item_type, receipt.item_id, float(receipt.qty), "电镀收回撤回")
        db.delete(receipt)

    # Reverse stock from PlatingReceiptItem records linked to this order's items
    affected_receipt_ids = set()
    for ri in receipt_items:
        receive_id = ri.part_id  # part_id on receipt item is already the receive target
        deduct_stock(db, "part", receive_id, float(ri.qty), "电镀收回撤回")
        affected_receipt_ids.add(ri.plating_receipt_id)
        db.delete(ri)
    db.flush()

    # Clean up PlatingReceipt records that became empty or recalc totals
    from models.plating_receipt import PlatingReceipt
    for pr_id in affected_receipt_ids:
        remaining_items = db.query(PlatingReceiptItem).filter(
            PlatingReceiptItem.plating_receipt_id == pr_id
        ).count()
        if remaining_items == 0:
            pr = db.query(PlatingReceipt).filter(PlatingReceipt.id == pr_id).first()
            if pr:
                db.delete(pr)
        else:
            pr = db.query(PlatingReceipt).filter(PlatingReceipt.id == pr_id).first()
            if pr:
                items_left = db.query(PlatingReceiptItem).filter(
                    PlatingReceiptItem.plating_receipt_id == pr_id
                ).all()
                from decimal import Decimal
                pr.total_amount = sum(Decimal(str(it.amount or 0)) for it in items_left)
    db.flush()

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
        raise ValueError("电镀单完成需通过创建电镀回收单（POST /api/plating-receipts/）完成收回")
    order.status = status
    db.flush()
    return order


def list_pending_receive_items(db: Session, part_keyword: str = None, supplier_name: str = None, date_on: date_type = None, exclude_item_ids: list[int] = None) -> list:
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
            SendPart.is_composite.label("part_is_composite"),
            PlatingOrderItem.receive_part_id,
            ReceivePart.name.label("receive_part_name"),
            PlatingOrderItem.plating_method,
            PlatingOrderItem.qty,
            PlatingOrderItem.received_qty,
            PlatingOrderItem.unit,
            PlatingOrderItem.weight,
            PlatingOrderItem.weight_unit,
            PlatingOrder.created_at,
        )
        .join(PlatingOrder, PlatingOrderItem.plating_order_id == PlatingOrder.id)
        .join(SendPart, PlatingOrderItem.part_id == SendPart.id)
        .outerjoin(ReceivePart, PlatingOrderItem.receive_part_id == ReceivePart.id)
        .filter(
            PlatingOrderItem.status == "电镀中",
            func.coalesce(PlatingOrderItem.received_qty, 0) < PlatingOrderItem.qty,
        )
    )
    if supplier_name:
        q = q.filter(PlatingOrder.supplier_name == supplier_name)
    if date_on:
        q = q.filter(func.cast(PlatingOrder.created_at, Date) == date_on)
    if exclude_item_ids:
        q = q.filter(PlatingOrderItem.id.notin_(exclude_item_ids))
    clause = keyword_filter(
        part_keyword,
        SendPart.id,
        SendPart.name,
        ReceivePart.id,
        ReceivePart.name,
    )
    if clause is not None:
        q = q.filter(clause)
    q = q.order_by(PlatingOrder.created_at.desc(), PlatingOrder.id.desc(), PlatingOrderItem.id.desc())
    rows = q.all()
    return [
        {
            "id": row.id,
            "plating_order_id": row.plating_order_id,
            "supplier_name": row.supplier_name,
            "part_id": row.part_id,
            "part_name": row.part_name,
            "part_image": row.part_image,
            "part_is_composite": row.part_is_composite,
            "receive_part_id": row.receive_part_id,
            "receive_part_name": row.receive_part_name,
            "plating_method": row.plating_method,
            "qty": float(row.qty),
            "received_qty": float(row.received_qty or 0),
            "unit": row.unit,
            "weight": float(row.weight) if row.weight is not None else None,
            "weight_unit": row.weight_unit,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def get_plating_supplier_names(db: Session) -> list[str]:
    rows = db.query(PlatingOrder.supplier_name).distinct().all()
    return [row[0] for row in rows]


def update_plating_order(db: Session, order_id: str, data: dict) -> PlatingOrder:
    order = get_plating_order(db, order_id)
    if order is None:
        raise ValueError(f"PlatingOrder not found: {order_id}")
    if "supplier_name" in data and data["supplier_name"] is not None:
        if order.status != "pending":
            raise ValueError("只有待处理状态的订单可以修改供应商")
        order.supplier_name = data["supplier_name"]
    if "created_at" in data and data["created_at"] is not None:
        order.created_at = _replace_date(order.created_at, data["created_at"])
    db.flush()
    return order


def update_plating_delivery_images(db: Session, order_id: str, delivery_images: Optional[list]) -> PlatingOrder:
    order = get_plating_order(db, order_id)
    if order is None:
        raise ValueError(f"PlatingOrder not found: {order_id}")
    order.delivery_images = _normalize_delivery_images(delivery_images)
    db.flush()
    return order
