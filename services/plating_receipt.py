from datetime import datetime, date as date_type
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from models.part import Part
from models.plating_order import PlatingOrder, PlatingOrderItem
from models.plating_receipt import PlatingReceipt, PlatingReceiptItem
from services._helpers import _next_id
from services.inventory import add_stock, deduct_stock
from time_utils import now_beijing


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


_VALID_STATUSES = {"未付款", "已付款"}
_Q7 = Decimal("0.0000001")


def _require_part(db: Session, part_id: str) -> None:
    if db.get(Part, part_id) is None:
        raise ValueError(f"Part not found: {part_id}")


def _normalize_delivery_images(delivery_images: Optional[list]) -> list[str]:
    cleaned = [str(item).strip() for item in (delivery_images or []) if str(item).strip()]
    if len(cleaned) > 9:
        raise ValueError("图片最多上传 9 张")
    return cleaned


def _recalc_total(db: Session, receipt: PlatingReceipt) -> None:
    items = get_plating_receipt_items(db, receipt.id)
    total = sum(Decimal(str(item.amount or 0)) for item in items)
    receipt.total_amount = total


def _check_plating_order_completion(db: Session, plating_order_id: str) -> None:
    """If all items of a plating order are fully received, mark it completed."""
    all_items = (
        db.query(PlatingOrderItem)
        .filter(PlatingOrderItem.plating_order_id == plating_order_id)
        .all()
    )
    if all(float(i.received_qty or 0) >= float(i.qty) for i in all_items):
        order = db.query(PlatingOrder).filter(PlatingOrder.id == plating_order_id).first()
        if order and order.status == "processing":
            order.status = "completed"
            order.completed_at = now_beijing()
    else:
        # If previously completed but now not all received (e.g. after item edit/delete),
        # revert to processing
        order = db.query(PlatingOrder).filter(PlatingOrder.id == plating_order_id).first()
        if order and order.status == "completed":
            order.status = "processing"
            order.completed_at = None


def _apply_receive(db: Session, plating_order_item: PlatingOrderItem, qty: float) -> None:
    """Add qty to received_qty, update item status, add stock."""
    plating_order_item.received_qty = float(plating_order_item.received_qty or 0) + qty
    receive_id = plating_order_item.receive_part_id or plating_order_item.part_id
    add_stock(db, "part", receive_id, qty, "电镀收回")
    if float(plating_order_item.received_qty) >= float(plating_order_item.qty):
        plating_order_item.status = "已收回"
    else:
        plating_order_item.status = "电镀中"


def _reverse_receive(db: Session, plating_order_item: PlatingOrderItem, qty: float) -> None:
    """Reverse qty from received_qty, update item status, deduct stock."""
    plating_order_item.received_qty = float(plating_order_item.received_qty or 0) - qty
    receive_id = plating_order_item.receive_part_id or plating_order_item.part_id
    deduct_stock(db, "part", receive_id, qty, "电镀收回撤回")
    if float(plating_order_item.received_qty) >= float(plating_order_item.qty):
        plating_order_item.status = "已收回"
    else:
        plating_order_item.status = "电镀中"


def create_plating_receipt(
    db: Session,
    vendor_name: str,
    items: list,
    status: str = "未付款",
    note: str = None,
    created_at: Optional[date_type] = None,
) -> PlatingReceipt:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Valid: {', '.join(sorted(_VALID_STATUSES))}")

    receipt_id = _next_id(db, PlatingReceipt, "ER")
    receipt = PlatingReceipt(
        id=receipt_id,
        vendor_name=vendor_name,
        status=status,
        note=note,
    )
    if created_at is not None:
        receipt.created_at = _user_date_to_datetime(created_at)
    if status == "已付款":
        # For backfills, anchor paid_at to created_at so the timeline is consistent.
        receipt.paid_at = receipt.created_at if created_at is not None else now_beijing()
    db.add(receipt)
    db.flush()

    affected_plating_orders = set()
    total = Decimal(0)

    for item_data in items:
        poi = db.query(PlatingOrderItem).filter(
            PlatingOrderItem.id == item_data["plating_order_item_id"]
        ).first()
        if poi is None:
            raise ValueError(f"PlatingOrderItem not found: {item_data['plating_order_item_id']}")
        if poi.status not in ("电镀中", "已收回"):
            raise ValueError(f"PlatingOrderItem {poi.id} status is '{poi.status}', cannot receive")

        # Validate vendor consistency
        plating_order = db.query(PlatingOrder).filter(PlatingOrder.id == poi.plating_order_id).first()
        if plating_order and plating_order.supplier_name != vendor_name:
            raise ValueError(
                f"PlatingOrderItem {poi.id} 属于供应商「{plating_order.supplier_name}」，"
                f"与回收单商家「{vendor_name}」不一致"
            )

        qty = item_data["qty"]
        remaining = float(poi.qty) - float(poi.received_qty or 0)
        if qty > remaining:
            raise ValueError(f"PlatingOrderItem {poi.id}: 最多可回收 {remaining}, 当前填写 {qty}")

        # Validate part_id matches
        expected_part_id = item_data["part_id"]
        receive_id = poi.receive_part_id or poi.part_id
        if expected_part_id != receive_id:
            raise ValueError(f"part_id mismatch for PlatingOrderItem {poi.id}")

        price = Decimal(str(item_data["price"])).quantize(_Q7, rounding=ROUND_HALF_UP) if item_data.get("price") is not None else None
        amount = (Decimal(str(qty)) * price).quantize(_Q7, rounding=ROUND_HALF_UP) if price is not None else None
        if amount is not None:
            total += amount

        db.add(PlatingReceiptItem(
            plating_receipt_id=receipt_id,
            plating_order_item_id=poi.id,
            part_id=expected_part_id,
            qty=qty,
            weight=item_data.get("weight"),
            weight_unit=item_data.get("weight_unit"),
            unit=item_data.get("unit", "个"),
            price=price,
            amount=amount,
            note=item_data.get("note"),
        ))

        _apply_receive(db, poi, qty)
        affected_plating_orders.add(poi.plating_order_id)

    receipt.total_amount = total
    db.flush()

    for po_id in affected_plating_orders:
        _check_plating_order_completion(db, po_id)
    db.flush()

    _enrich_receipt(db, receipt)
    return receipt


def add_plating_receipt_items(
    db: Session,
    receipt_id: str,
    items: list,
) -> PlatingReceipt:
    receipt = db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"PlatingReceipt not found: {receipt_id}")
    if receipt.status == "已付款":
        raise ValueError("已付款的回收单不能添加明细")

    affected_plating_orders = set()

    for item_data in items:
        poi_id = item_data["plating_order_item_id"]
        poi = db.query(PlatingOrderItem).filter(
            PlatingOrderItem.id == poi_id
        ).first()
        if poi is None:
            raise ValueError(f"PlatingOrderItem not found: {poi_id}")
        if poi.status not in ("电镀中", "已收回"):
            raise ValueError(f"PlatingOrderItem {poi.id} status is '{poi.status}', cannot receive")

        # Validate vendor consistency
        plating_order = db.query(PlatingOrder).filter(PlatingOrder.id == poi.plating_order_id).first()
        if plating_order and plating_order.supplier_name != receipt.vendor_name:
            raise ValueError(
                f"PlatingOrderItem {poi.id} 属于供应商「{plating_order.supplier_name}」，"
                f"与回收单商家「{receipt.vendor_name}」不一致"
            )

        qty = item_data["qty"]
        remaining = float(poi.qty) - float(poi.received_qty or 0)
        if qty > remaining:
            raise ValueError(f"PlatingOrderItem {poi.id}: 最多可回收 {remaining}, 当前填写 {qty}")

        expected_part_id = item_data["part_id"]
        receive_id = poi.receive_part_id or poi.part_id
        if expected_part_id != receive_id:
            raise ValueError(f"part_id mismatch for PlatingOrderItem {poi.id}")

        price = Decimal(str(item_data["price"])).quantize(_Q7, rounding=ROUND_HALF_UP) if item_data.get("price") is not None else None
        amount = (Decimal(str(qty)) * price).quantize(_Q7, rounding=ROUND_HALF_UP) if price is not None else None

        db.add(PlatingReceiptItem(
            plating_receipt_id=receipt_id,
            plating_order_item_id=poi.id,
            part_id=expected_part_id,
            qty=qty,
            weight=item_data.get("weight"),
            weight_unit=item_data.get("weight_unit"),
            unit=item_data.get("unit", "个"),
            price=price,
            amount=amount,
            note=item_data.get("note"),
        ))

        _apply_receive(db, poi, qty)
        affected_plating_orders.add(poi.plating_order_id)

    _recalc_total(db, receipt)
    db.flush()

    for po_id in affected_plating_orders:
        _check_plating_order_completion(db, po_id)
    db.flush()

    db.expire(receipt, ["items"])
    _enrich_receipt(db, receipt)
    return receipt


def list_plating_receipts(db: Session, vendor_name: str = None) -> list:
    q = db.query(PlatingReceipt)
    if vendor_name is not None:
        q = q.filter(PlatingReceipt.vendor_name == vendor_name)
    return q.order_by(PlatingReceipt.created_at.desc(), PlatingReceipt.id.desc()).all()


def get_plating_receipt(db: Session, receipt_id: str) -> Optional[PlatingReceipt]:
    receipt = db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first()
    if receipt is not None:
        _enrich_receipt(db, receipt)
    return receipt


def get_plating_receipt_items(db: Session, receipt_id: str) -> list:
    return (
        db.query(PlatingReceiptItem)
        .filter(PlatingReceiptItem.plating_receipt_id == receipt_id)
        .order_by(PlatingReceiptItem.id.asc())
        .all()
    )


def delete_plating_receipt(db: Session, receipt_id: str) -> None:
    receipt = db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"PlatingReceipt not found: {receipt_id}")
    if receipt.status == "已付款":
        raise ValueError("已付款的回收单不能删除")

    items = get_plating_receipt_items(db, receipt_id)
    affected_plating_orders = set()

    for item in items:
        poi = db.query(PlatingOrderItem).filter(
            PlatingOrderItem.id == item.plating_order_item_id
        ).first()
        if poi:
            _reverse_receive(db, poi, float(item.qty))
            affected_plating_orders.add(poi.plating_order_id)

    db.query(PlatingReceiptItem).filter(
        PlatingReceiptItem.plating_receipt_id == receipt_id
    ).delete(synchronize_session="fetch")
    db.flush()
    db.delete(receipt)
    db.flush()

    for po_id in affected_plating_orders:
        _check_plating_order_completion(db, po_id)
    db.flush()


def update_plating_receipt(db: Session, receipt_id: str, data: dict) -> PlatingReceipt:
    receipt = db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"PlatingReceipt not found: {receipt_id}")
    if "created_at" in data and data["created_at"] is not None:
        new_created_at = _replace_date(receipt.created_at, data["created_at"])
        if receipt.paid_at is not None and new_created_at > receipt.paid_at:
            raise ValueError("创建时间不能晚于付款时间")
        receipt.created_at = new_created_at
    db.flush()
    _enrich_receipt(db, receipt)
    return receipt


def update_plating_receipt_status(db: Session, receipt_id: str, status: str) -> PlatingReceipt:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Valid: {', '.join(sorted(_VALID_STATUSES))}")
    receipt = db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"PlatingReceipt not found: {receipt_id}")
    if receipt.status == status:
        raise ValueError(f"回收单已经是「{status}」状态")
    if status == "已付款":
        # Clamp paid_at >= created_at to keep the timeline consistent.
        now = now_beijing()
        receipt.paid_at = max(now, receipt.created_at) if receipt.created_at else now
    else:
        receipt.paid_at = None
    receipt.status = status
    db.flush()
    _enrich_receipt(db, receipt)
    return receipt


def update_plating_receipt_images(db: Session, receipt_id: str, delivery_images: Optional[list]) -> PlatingReceipt:
    receipt = db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"PlatingReceipt not found: {receipt_id}")
    receipt.delivery_images = _normalize_delivery_images(delivery_images)
    db.flush()
    _enrich_receipt(db, receipt)
    return receipt


def update_plating_receipt_item(db: Session, receipt_id: str, item_id: int, data: dict) -> PlatingReceiptItem:
    receipt = db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"PlatingReceipt not found: {receipt_id}")
    if receipt.status == "已付款":
        raise ValueError("已付款的回收单不能修改明细")

    item = db.query(PlatingReceiptItem).filter(
        PlatingReceiptItem.id == item_id,
        PlatingReceiptItem.plating_receipt_id == receipt_id,
    ).first()
    if item is None:
        raise ValueError(f"PlatingReceiptItem {item_id} not found in receipt {receipt_id}")

    poi = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.id == item.plating_order_item_id
    ).first()

    old_qty = float(item.qty)

    for field in ("unit", "note"):
        if field in data:
            setattr(item, field, data[field])
    for wf in ("weight", "weight_unit"):
        if wf in data:
            setattr(item, wf, data[wf])
    if "price" in data:
        item.price = Decimal(str(data["price"])).quantize(_Q7, rounding=ROUND_HALF_UP) if data["price"] is not None else None
    if "qty" in data and data["qty"] is not None:
        new_qty = data["qty"]
        # Validate: new_qty must not exceed remaining + old_qty
        remaining = float(poi.qty) - float(poi.received_qty or 0) + old_qty
        if new_qty > remaining:
            raise ValueError(f"最多可回收 {remaining}, 当前填写 {new_qty}")
        item.qty = new_qty

    new_qty = float(item.qty)
    if new_qty != old_qty:
        diff = new_qty - old_qty
        if diff > 0:
            _apply_receive(db, poi, diff)
        else:
            _reverse_receive(db, poi, -diff)
        _check_plating_order_completion(db, poi.plating_order_id)

    if item.price is not None:
        item.amount = (Decimal(str(item.qty)) * Decimal(str(item.price))).quantize(_Q7, rounding=ROUND_HALF_UP)
    else:
        item.amount = None

    _recalc_total(db, receipt)
    db.flush()
    return item


def delete_plating_receipt_item(db: Session, receipt_id: str, item_id: int) -> None:
    receipt = db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"PlatingReceipt not found: {receipt_id}")
    if receipt.status == "已付款":
        raise ValueError("已付款的回收单不能删除明细")

    item = db.query(PlatingReceiptItem).filter(
        PlatingReceiptItem.id == item_id,
        PlatingReceiptItem.plating_receipt_id == receipt_id,
    ).first()
    if item is None:
        raise ValueError(f"PlatingReceiptItem {item_id} not found in receipt {receipt_id}")

    remaining_count = db.query(PlatingReceiptItem).filter(
        PlatingReceiptItem.plating_receipt_id == receipt_id,
        PlatingReceiptItem.id != item_id,
    ).count()
    if remaining_count == 0:
        raise ValueError("不能删除最后一条明细，请直接删除整个回收单")

    poi = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.id == item.plating_order_item_id
    ).first()
    if poi:
        _reverse_receive(db, poi, float(item.qty))
        affected_po_id = poi.plating_order_id
    else:
        affected_po_id = None

    db.delete(item)
    db.flush()
    _recalc_total(db, receipt)
    db.flush()

    if affected_po_id:
        _check_plating_order_completion(db, affected_po_id)
        db.flush()


def get_receipt_links_for_plating_order(db: Session, plating_order_id: str) -> dict:
    """Return {item_id: [{receipt_id, receipt_item_id, qty, price}, ...]} for all items in this order."""
    item_ids = [
        row.id for row in
        db.query(PlatingOrderItem.id).filter(PlatingOrderItem.plating_order_id == plating_order_id).all()
    ]
    if not item_ids:
        return {}
    rows = (
        db.query(PlatingReceiptItem)
        .filter(PlatingReceiptItem.plating_order_item_id.in_(item_ids))
        .all()
    )
    result = {}
    for r in rows:
        result.setdefault(r.plating_order_item_id, []).append({
            "receipt_id": r.plating_receipt_id,
            "receipt_item_id": r.id,
            "qty": float(r.qty),
            "price": float(r.price) if r.price is not None else None,
        })
    return result


def get_available_receipts_for_item(db: Session, plating_order_id: str, item_id: int) -> list:
    """Return unpaid receipts from the same supplier, excluding those already linked to this item."""
    poi = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.id == item_id,
        PlatingOrderItem.plating_order_id == plating_order_id,
    ).first()
    if poi is None:
        raise ValueError(f"PlatingOrderItem {item_id} not found in order {plating_order_id}")

    order = db.query(PlatingOrder).filter(PlatingOrder.id == plating_order_id).first()
    if order is None:
        raise ValueError(f"PlatingOrder {plating_order_id} not found")

    # Find receipt IDs already linked to this item
    linked_receipt_ids = {
        row.plating_receipt_id for row in
        db.query(PlatingReceiptItem.plating_receipt_id)
        .filter(PlatingReceiptItem.plating_order_item_id == item_id)
        .all()
    }

    query = db.query(PlatingReceipt).filter(
        PlatingReceipt.vendor_name == order.supplier_name,
        PlatingReceipt.status == "未付款",
    )
    if linked_receipt_ids:
        query = query.filter(PlatingReceipt.id.notin_(linked_receipt_ids))

    receipts = query.order_by(PlatingReceipt.created_at.desc()).all()
    result = []
    for r in receipts:
        item_count = db.query(PlatingReceiptItem).filter(
            PlatingReceiptItem.plating_receipt_id == r.id
        ).count()
        result.append({
            "id": r.id,
            "vendor_name": r.vendor_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "item_count": item_count,
        })
    return result


def link_plating_item_to_receipt(
    db: Session,
    plating_order_id: str,
    item_id: int,
    receipt_id: str,
    qty: float,
    price: float,
) -> dict:
    """Link a plating order item to an existing receipt. Returns {receipt_item_id, qty, price}."""
    # 1. Validate item exists and belongs to order
    poi = db.query(PlatingOrderItem).filter(
        PlatingOrderItem.id == item_id,
        PlatingOrderItem.plating_order_id == plating_order_id,
    ).first()
    if poi is None:
        raise ValueError(f"PlatingOrderItem {item_id} not found in order {plating_order_id}")

    # 2. Validate item status
    if poi.status not in ("电镀中", "已收回"):
        raise ValueError(f"配件项状态为「{poi.status}」，无法关联回收单")

    # 3. Validate qty
    remaining = float(poi.qty) - float(poi.received_qty or 0)
    if qty > remaining:
        raise ValueError(f"最多可回收 {remaining}，当前填写 {qty}")

    # 4. Validate receipt exists and is unpaid
    receipt = db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"回收单 {receipt_id} 不存在")
    if receipt.status == "已付款":
        raise ValueError("已付款的回收单不能添加明细")

    # 5. Validate vendor match
    order = db.query(PlatingOrder).filter(PlatingOrder.id == plating_order_id).first()
    if order.supplier_name != receipt.vendor_name:
        raise ValueError(
            f"电镀单供应商「{order.supplier_name}」与回收单商家「{receipt.vendor_name}」不一致"
        )

    # 6. Validate no duplicate
    existing = db.query(PlatingReceiptItem).filter(
        PlatingReceiptItem.plating_receipt_id == receipt_id,
        PlatingReceiptItem.plating_order_item_id == item_id,
    ).first()
    if existing:
        raise ValueError(f"该配件项已存在于回收单 {receipt_id} 中")

    # 7. Build item data and delegate to add_plating_receipt_items
    part_id = poi.receive_part_id or poi.part_id
    item_data = {
        "plating_order_item_id": poi.id,
        "part_id": part_id,
        "qty": qty,
        "price": price,
    }
    add_plating_receipt_items(db, receipt_id, [item_data])

    # Find the newly created receipt item
    new_item = db.query(PlatingReceiptItem).filter(
        PlatingReceiptItem.plating_receipt_id == receipt_id,
        PlatingReceiptItem.plating_order_item_id == item_id,
    ).first()

    return {
        "receipt_id": receipt_id,
        "receipt_item_id": new_item.id,
        "qty": float(new_item.qty),
        "price": float(new_item.price) if new_item.price is not None else None,
    }


def get_receipt_vendor_names(db: Session) -> list[str]:
    rows = db.query(PlatingReceipt.vendor_name).distinct().all()
    return [row[0] for row in rows]


def _enrich_receipt(db: Session, receipt: PlatingReceipt) -> PlatingReceipt:
    """Populate enriched fields (part_name, plating_order_id, plating_method) on receipt items."""
    for item in receipt.items:
        poi = db.query(PlatingOrderItem).filter(PlatingOrderItem.id == item.plating_order_item_id).first()
        if poi:
            item.plating_order_id = poi.plating_order_id
            item.plating_method = poi.plating_method
            item.source_qty = float(poi.qty)
            item.source_received_qty = float(poi.received_qty or 0)
        part = db.get(Part, item.part_id)
        if part:
            item.part_name = part.name
            item.part_is_composite = part.is_composite
    return receipt
