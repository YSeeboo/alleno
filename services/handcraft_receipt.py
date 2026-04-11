from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
from models.handcraft_receipt import HandcraftReceipt, HandcraftReceiptItem
from models.jewelry import Jewelry
from models.part import Part
from services._helpers import _next_id
from services.inventory import add_stock, deduct_stock
from time_utils import now_beijing


_VALID_STATUSES = {"未付款", "已付款"}
_Q7 = Decimal("0.0000001")


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


def _normalize_delivery_images(delivery_images: Optional[list]) -> list[str]:
    cleaned = [str(item).strip() for item in (delivery_images or []) if str(item).strip()]
    if len(cleaned) > 9:
        raise ValueError("图片最多上传 9 张")
    return cleaned


def _recalc_total(db: Session, receipt: HandcraftReceipt) -> None:
    items = get_handcraft_receipt_items(db, receipt.id)
    total = sum(Decimal(str(item.amount or 0)) for item in items)
    receipt.total_amount = total


def _check_handcraft_order_completion(db: Session, handcraft_order_id: str) -> None:
    """If all part items AND jewelry items are fully received, mark order completed."""
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
    all_items = part_items + jewelry_items
    if all(float(i.received_qty or 0) >= float(i.qty) for i in all_items):
        order = db.query(HandcraftOrder).filter(HandcraftOrder.id == handcraft_order_id).first()
        if order and order.status == "processing":
            order.status = "completed"
            order.completed_at = now_beijing()
    else:
        order = db.query(HandcraftOrder).filter(HandcraftOrder.id == handcraft_order_id).first()
        if order and order.status == "completed":
            order.status = "processing"
            order.completed_at = None


def _apply_receive(db: Session, order_item, item_type: str, qty: float) -> None:
    """Add qty to received_qty, update item status, add stock.

    For jewelry items, also auto-consume corresponding parts via BOM.
    For part output items (jewelry_item with part_id), auto-consume child parts via part_bom.
    """
    order_item.received_qty = float(order_item.received_qty or 0) + qty
    if item_type == "part":
        add_stock(db, "part", order_item.part_id, qty, "手工收回")
    else:
        # "jewelry" item_type covers both jewelry output and part output
        if order_item.jewelry_id:
            add_stock(db, "jewelry", order_item.jewelry_id, qty, "手工收回")
            _auto_consume_parts(db, order_item.handcraft_order_id, order_item.jewelry_id, qty)
        elif order_item.part_id:
            add_stock(db, "part", order_item.part_id, qty, "手工收回")
            _auto_consume_child_parts(db, order_item.handcraft_order_id, order_item.part_id, qty)
    if float(order_item.received_qty) >= float(order_item.qty):
        order_item.status = "已收回"
    else:
        order_item.status = "制作中"


def _auto_consume_parts(db: Session, handcraft_order_id: str, jewelry_id: str, jewelry_qty: float) -> None:
    """When jewelry is received, auto-consume parts in the same handcraft order based on BOM.

    Total consumption per part_id = BOM qty_per_unit × jewelry_qty,
    distributed across rows (if same part_id appears multiple times), capped at each row's remaining qty.
    """
    from models.bom import Bom
    from collections import defaultdict

    bom_rows = db.query(Bom).filter_by(jewelry_id=jewelry_id).all()
    if not bom_rows:
        return

    bom_map = {b.part_id: float(b.qty_per_unit) for b in bom_rows}
    part_items = db.query(HandcraftPartItem).filter_by(handcraft_order_id=handcraft_order_id).all()

    # Group by part_id to distribute consumption correctly
    by_part: dict[str, list] = defaultdict(list)
    for pi in part_items:
        if pi.part_id in bom_map:
            by_part[pi.part_id].append(pi)

    for part_id, rows in by_part.items():
        total_consumption = bom_map[part_id] * jewelry_qty
        # Distribute across rows, filling each up to its remaining capacity
        for pi in rows:
            if total_consumption <= 0:
                break
            remaining = float(pi.qty) - float(pi.received_qty or 0)
            actual = min(total_consumption, remaining)
            if actual <= 0:
                continue
            pi.received_qty = float(pi.received_qty or 0) + actual
            if float(pi.received_qty) >= float(pi.qty):
                pi.status = "已收回"
            else:
                pi.status = "制作中"
            total_consumption -= actual

    db.flush()


def _auto_consume_child_parts(db: Session, handcraft_order_id: str, parent_part_id: str, parent_qty: float) -> None:
    """When a composite part is received, auto-consume child parts based on part_bom."""
    from models.part_bom import PartBom

    bom_rows = db.query(PartBom).filter_by(parent_part_id=parent_part_id).all()
    if not bom_rows:
        return

    bom_map = {b.child_part_id: float(b.qty_per_unit) for b in bom_rows}
    part_items = db.query(HandcraftPartItem).filter_by(handcraft_order_id=handcraft_order_id).all()

    from collections import defaultdict
    by_part: dict[str, list] = defaultdict(list)
    for pi in part_items:
        if pi.part_id in bom_map:
            by_part[pi.part_id].append(pi)

    for part_id, rows in by_part.items():
        total_consumption = bom_map[part_id] * parent_qty
        for pi in rows:
            if total_consumption <= 0:
                break
            remaining = float(pi.qty) - float(pi.received_qty or 0)
            actual = min(total_consumption, remaining)
            if actual <= 0:
                continue
            pi.received_qty = float(pi.received_qty or 0) + actual
            if float(pi.received_qty) >= float(pi.qty):
                pi.status = "已收回"
            else:
                pi.status = "制作中"
            total_consumption -= actual

    db.flush()


def _reverse_receive(db: Session, order_item, item_type: str, qty: float) -> None:
    """Reverse qty from received_qty, update item status, deduct stock.

    For jewelry items, also reverse the auto-consumed parts.
    For part output items, reverse the auto-consumed child parts.
    """
    order_item.received_qty = float(order_item.received_qty or 0) - qty
    if item_type == "part":
        deduct_stock(db, "part", order_item.part_id, qty, "手工收回撤回")
    else:
        if order_item.jewelry_id:
            deduct_stock(db, "jewelry", order_item.jewelry_id, qty, "手工收回撤回")
            _reverse_auto_consume_parts(db, order_item.handcraft_order_id, order_item.jewelry_id, qty)
        elif order_item.part_id:
            deduct_stock(db, "part", order_item.part_id, qty, "手工收回撤回")
            _reverse_auto_consume_child_parts(db, order_item.handcraft_order_id, order_item.part_id, qty)
    if float(order_item.received_qty) >= float(order_item.qty):
        order_item.status = "已收回"
    else:
        order_item.status = "制作中"


def _reverse_auto_consume_parts(db: Session, handcraft_order_id: str, jewelry_id: str, jewelry_qty: float) -> None:
    """Reverse the auto-consumed parts when jewelry receive is reversed."""
    from models.bom import Bom

    bom_rows = db.query(Bom).filter_by(jewelry_id=jewelry_id).all()
    if not bom_rows:
        return

    bom_map = {b.part_id: float(b.qty_per_unit) for b in bom_rows}
    part_items = db.query(HandcraftPartItem).filter_by(handcraft_order_id=handcraft_order_id).all()

    # Group by part_id to handle multiple rows correctly
    from collections import defaultdict
    by_part: dict[str, list] = defaultdict(list)
    for pi in part_items:
        if pi.part_id in bom_map:
            by_part[pi.part_id].append(pi)

    for part_id, rows in by_part.items():
        total_to_reverse = bom_map[part_id] * jewelry_qty
        # Reverse from rows (last first to undo in order)
        for pi in reversed(rows):
            current = float(pi.received_qty or 0)
            reverse_amount = min(total_to_reverse, current)
            if reverse_amount <= 0:
                continue
            pi.received_qty = current - reverse_amount
            if float(pi.received_qty) >= float(pi.qty):
                pi.status = "已收回"
            elif float(pi.received_qty) > 0:
                pi.status = "制作中"
            else:
                pi.status = "制作中"
            total_to_reverse -= reverse_amount
            if total_to_reverse <= 0:
                break

    db.flush()


def _reverse_auto_consume_child_parts(db: Session, handcraft_order_id: str, parent_part_id: str, parent_qty: float) -> None:
    """Reverse the auto-consumed child parts when part output receive is reversed."""
    from models.part_bom import PartBom

    bom_rows = db.query(PartBom).filter_by(parent_part_id=parent_part_id).all()
    if not bom_rows:
        return

    bom_map = {b.child_part_id: float(b.qty_per_unit) for b in bom_rows}
    part_items = db.query(HandcraftPartItem).filter_by(handcraft_order_id=handcraft_order_id).all()

    from collections import defaultdict
    by_part: dict[str, list] = defaultdict(list)
    for pi in part_items:
        if pi.part_id in bom_map:
            by_part[pi.part_id].append(pi)

    for part_id, rows in by_part.items():
        total_to_reverse = bom_map[part_id] * parent_qty
        for pi in reversed(rows):
            current = float(pi.received_qty or 0)
            reverse_amount = min(total_to_reverse, current)
            if reverse_amount <= 0:
                continue
            pi.received_qty = current - reverse_amount
            if float(pi.received_qty) >= float(pi.qty):
                pi.status = "已收回"
            else:
                pi.status = "制作中"
            total_to_reverse -= reverse_amount
            if total_to_reverse <= 0:
                break

    db.flush()


def _resolve_order_item(db: Session, item_data: dict):
    """Resolve item_data to (order_item, item_id, item_type, handcraft_order_id)."""
    part_item_id = item_data.get("handcraft_part_item_id")
    jewelry_item_id = item_data.get("handcraft_jewelry_item_id")

    has_part = part_item_id is not None
    has_jewelry = jewelry_item_id is not None
    if has_part == has_jewelry:
        raise ValueError("必须且只能指定 handcraft_part_item_id 或 handcraft_jewelry_item_id 其中之一")

    qty = item_data.get("qty")

    if has_part:
        oi = db.query(HandcraftPartItem).filter(HandcraftPartItem.id == part_item_id).first()
        if oi is None:
            raise ValueError(f"HandcraftPartItem not found: {part_item_id}")
        return oi, oi.part_id, "part", oi.handcraft_order_id
    else:
        oi = db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.id == jewelry_item_id).first()
        if oi is None:
            raise ValueError(f"HandcraftJewelryItem not found: {jewelry_item_id}")
        if oi.jewelry_id:
            if qty is not None and qty != int(qty):
                raise ValueError("饰品收回数量必须为整数")
            return oi, oi.jewelry_id, "jewelry", oi.handcraft_order_id
        else:
            # Part output item
            return oi, oi.part_id, "jewelry", oi.handcraft_order_id


def _enrich_receipt(db: Session, receipt: HandcraftReceipt) -> HandcraftReceipt:
    """Populate enriched fields on receipt items."""
    for item in receipt.items:
        if item.item_type == "part":
            oi = db.query(HandcraftPartItem).filter(HandcraftPartItem.id == item.handcraft_part_item_id).first()
            if oi:
                item.handcraft_order_id = oi.handcraft_order_id
                item.source_qty = float(oi.qty)
                item.source_received_qty = float(oi.received_qty or 0)
            part = db.get(Part, item.item_id)
            if part:
                item.item_name = part.name
                item.color = part.color
        else:
            oi = db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.id == item.handcraft_jewelry_item_id).first()
            if oi:
                item.handcraft_order_id = oi.handcraft_order_id
                item.source_qty = float(oi.qty)
                item.source_received_qty = float(oi.received_qty or 0)
            if oi and oi.part_id:
                # Part output item
                part = db.get(Part, item.item_id)
                if part:
                    item.item_name = part.name
            else:
                jewelry = db.get(Jewelry, item.item_id)
                if jewelry:
                    item.item_name = jewelry.name
    return receipt


def create_handcraft_receipt(
    db: Session,
    supplier_name: str,
    items: list,
    status: str = "未付款",
    note: str = None,
    created_at: Optional[date_type] = None,
) -> HandcraftReceipt:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Valid: {', '.join(sorted(_VALID_STATUSES))}")

    receipt_id = _next_id(db, HandcraftReceipt, "HR")
    receipt = HandcraftReceipt(
        id=receipt_id,
        supplier_name=supplier_name,
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

    affected_orders = set()
    total = Decimal(0)

    for item_data in items:
        order_item, item_id, item_type, hc_order_id = _resolve_order_item(db, item_data)

        if order_item.status not in ("制作中", "已收回"):
            raise ValueError(f"{'HandcraftPartItem' if item_type == 'part' else 'HandcraftJewelryItem'} {order_item.id} status is '{order_item.status}', cannot receive")

        # Validate supplier consistency
        hc_order = db.query(HandcraftOrder).filter(HandcraftOrder.id == hc_order_id).first()
        if hc_order and hc_order.supplier_name != supplier_name:
            raise ValueError(
                f"手工单 {hc_order_id} 的商家「{hc_order.supplier_name}」与回收单商家「{supplier_name}」不一致"
            )

        qty = item_data["qty"]
        remaining = float(order_item.qty) - float(order_item.received_qty or 0)
        if qty > remaining:
            raise ValueError(f"{'HandcraftPartItem' if item_type == 'part' else 'HandcraftJewelryItem'} {order_item.id}: 最多可回收 {remaining}, 当前填写 {qty}")

        price = Decimal(str(item_data["price"])).quantize(_Q7, rounding=ROUND_HALF_UP) if item_data.get("price") is not None else None
        amount = (Decimal(str(qty)) * price).quantize(_Q7, rounding=ROUND_HALF_UP) if price is not None else None
        if amount is not None:
            total += amount

        db.add(HandcraftReceiptItem(
            handcraft_receipt_id=receipt_id,
            handcraft_part_item_id=item_data.get("handcraft_part_item_id"),
            handcraft_jewelry_item_id=item_data.get("handcraft_jewelry_item_id"),
            item_id=item_id,
            item_type=item_type,
            qty=qty,
            weight=item_data.get("weight"),
            weight_unit=item_data.get("weight_unit"),
            unit=item_data.get("unit", "个"),
            price=price,
            amount=amount,
            note=item_data.get("note"),
        ))

        _apply_receive(db, order_item, item_type, qty)
        affected_orders.add(hc_order_id)

    receipt.total_amount = total
    db.flush()

    for order_id in affected_orders:
        _check_handcraft_order_completion(db, order_id)
    db.flush()

    _enrich_receipt(db, receipt)
    return receipt


def add_handcraft_receipt_items(
    db: Session,
    receipt_id: str,
    items: list,
) -> HandcraftReceipt:
    receipt = db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"HandcraftReceipt not found: {receipt_id}")
    if receipt.status == "已付款":
        raise ValueError("已付款的回收单不能添加明细")

    affected_orders = set()

    for item_data in items:
        order_item, item_id, item_type, hc_order_id = _resolve_order_item(db, item_data)

        if order_item.status not in ("制作中", "已收回"):
            raise ValueError(f"{'HandcraftPartItem' if item_type == 'part' else 'HandcraftJewelryItem'} {order_item.id} status is '{order_item.status}', cannot receive")

        # Validate supplier consistency
        hc_order = db.query(HandcraftOrder).filter(HandcraftOrder.id == hc_order_id).first()
        if hc_order and hc_order.supplier_name != receipt.supplier_name:
            raise ValueError(
                f"手工单 {hc_order_id} 的商家「{hc_order.supplier_name}」与回收单商家「{receipt.supplier_name}」不一致"
            )

        qty = item_data["qty"]
        remaining = float(order_item.qty) - float(order_item.received_qty or 0)
        if qty > remaining:
            raise ValueError(f"{'HandcraftPartItem' if item_type == 'part' else 'HandcraftJewelryItem'} {order_item.id}: 最多可回收 {remaining}, 当前填写 {qty}")

        price = Decimal(str(item_data["price"])).quantize(_Q7, rounding=ROUND_HALF_UP) if item_data.get("price") is not None else None
        amount = (Decimal(str(qty)) * price).quantize(_Q7, rounding=ROUND_HALF_UP) if price is not None else None

        db.add(HandcraftReceiptItem(
            handcraft_receipt_id=receipt_id,
            handcraft_part_item_id=item_data.get("handcraft_part_item_id"),
            handcraft_jewelry_item_id=item_data.get("handcraft_jewelry_item_id"),
            item_id=item_id,
            item_type=item_type,
            qty=qty,
            weight=item_data.get("weight"),
            weight_unit=item_data.get("weight_unit"),
            unit=item_data.get("unit", "个"),
            price=price,
            amount=amount,
            note=item_data.get("note"),
        ))

        _apply_receive(db, order_item, item_type, qty)
        affected_orders.add(hc_order_id)

    _recalc_total(db, receipt)
    db.flush()

    for order_id in affected_orders:
        _check_handcraft_order_completion(db, order_id)
    db.flush()

    db.expire(receipt, ["items"])
    _enrich_receipt(db, receipt)
    return receipt


def list_handcraft_receipts(db: Session, supplier_name: str = None) -> list:
    q = db.query(HandcraftReceipt)
    if supplier_name is not None:
        q = q.filter(HandcraftReceipt.supplier_name == supplier_name)
    return q.order_by(HandcraftReceipt.created_at.desc(), HandcraftReceipt.id.desc()).all()


def get_handcraft_receipt(db: Session, receipt_id: str) -> Optional[HandcraftReceipt]:
    receipt = db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first()
    if receipt is not None:
        _enrich_receipt(db, receipt)
    return receipt


def get_handcraft_receipt_items(db: Session, receipt_id: str) -> list:
    return (
        db.query(HandcraftReceiptItem)
        .filter(HandcraftReceiptItem.handcraft_receipt_id == receipt_id)
        .order_by(HandcraftReceiptItem.id.asc())
        .all()
    )


def delete_handcraft_receipt(db: Session, receipt_id: str) -> None:
    receipt = db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"HandcraftReceipt not found: {receipt_id}")
    if receipt.status == "已付款":
        raise ValueError("已付款的回收单不能删除")

    items = get_handcraft_receipt_items(db, receipt_id)
    affected_orders = set()

    for item in items:
        if item.item_type == "part":
            oi = db.query(HandcraftPartItem).filter(HandcraftPartItem.id == item.handcraft_part_item_id).first()
        else:
            oi = db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.id == item.handcraft_jewelry_item_id).first()
        if oi:
            _reverse_receive(db, oi, item.item_type, float(item.qty))
            affected_orders.add(oi.handcraft_order_id)

    db.query(HandcraftReceiptItem).filter(
        HandcraftReceiptItem.handcraft_receipt_id == receipt_id
    ).delete(synchronize_session="fetch")
    db.flush()
    db.delete(receipt)
    db.flush()

    for order_id in affected_orders:
        _check_handcraft_order_completion(db, order_id)
    db.flush()


def update_handcraft_receipt(db: Session, receipt_id: str, data: dict) -> HandcraftReceipt:
    receipt = db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"HandcraftReceipt not found: {receipt_id}")
    if "created_at" in data and data["created_at"] is not None:
        new_created_at = _replace_date(receipt.created_at, data["created_at"])
        if receipt.paid_at is not None and new_created_at > receipt.paid_at:
            raise ValueError("创建时间不能晚于付款时间")
        receipt.created_at = new_created_at
    db.flush()
    _enrich_receipt(db, receipt)
    return receipt


def update_handcraft_receipt_status(db: Session, receipt_id: str, status: str) -> HandcraftReceipt:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Valid: {', '.join(sorted(_VALID_STATUSES))}")
    receipt = db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"HandcraftReceipt not found: {receipt_id}")
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


def update_handcraft_receipt_images(db: Session, receipt_id: str, delivery_images: Optional[list]) -> HandcraftReceipt:
    receipt = db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"HandcraftReceipt not found: {receipt_id}")
    receipt.delivery_images = _normalize_delivery_images(delivery_images)
    db.flush()
    _enrich_receipt(db, receipt)
    return receipt


def update_handcraft_receipt_item(db: Session, receipt_id: str, item_id: int, data: dict) -> HandcraftReceiptItem:
    receipt = db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"HandcraftReceipt not found: {receipt_id}")
    if receipt.status == "已付款":
        raise ValueError("已付款的回收单不能修改明细")

    item = db.query(HandcraftReceiptItem).filter(
        HandcraftReceiptItem.id == item_id,
        HandcraftReceiptItem.handcraft_receipt_id == receipt_id,
    ).first()
    if item is None:
        raise ValueError(f"HandcraftReceiptItem {item_id} not found in receipt {receipt_id}")

    # Resolve the order item
    if item.item_type == "part":
        oi = db.query(HandcraftPartItem).filter(HandcraftPartItem.id == item.handcraft_part_item_id).first()
    else:
        oi = db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.id == item.handcraft_jewelry_item_id).first()

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
        if item.item_type == "jewelry" and new_qty != int(new_qty):
            raise ValueError("饰品收回数量必须为整数")
        remaining = float(oi.qty) - float(oi.received_qty or 0) + old_qty
        if new_qty > remaining:
            raise ValueError(f"最多可回收 {remaining}, 当前填写 {new_qty}")
        item.qty = new_qty

    new_qty = float(item.qty)
    if new_qty != old_qty:
        diff = new_qty - old_qty
        if diff > 0:
            _apply_receive(db, oi, item.item_type, diff)
        else:
            _reverse_receive(db, oi, item.item_type, -diff)
        _check_handcraft_order_completion(db, oi.handcraft_order_id)

    if item.price is not None:
        item.amount = (Decimal(str(item.qty)) * Decimal(str(item.price))).quantize(_Q7, rounding=ROUND_HALF_UP)
    else:
        item.amount = None

    _recalc_total(db, receipt)
    db.flush()
    return item


def delete_handcraft_receipt_item(db: Session, receipt_id: str, item_id: int) -> None:
    receipt = db.query(HandcraftReceipt).filter(HandcraftReceipt.id == receipt_id).first()
    if receipt is None:
        raise ValueError(f"HandcraftReceipt not found: {receipt_id}")
    if receipt.status == "已付款":
        raise ValueError("已付款的回收单不能删除明细")

    item = db.query(HandcraftReceiptItem).filter(
        HandcraftReceiptItem.id == item_id,
        HandcraftReceiptItem.handcraft_receipt_id == receipt_id,
    ).first()
    if item is None:
        raise ValueError(f"HandcraftReceiptItem {item_id} not found in receipt {receipt_id}")

    remaining_count = db.query(HandcraftReceiptItem).filter(
        HandcraftReceiptItem.handcraft_receipt_id == receipt_id,
        HandcraftReceiptItem.id != item_id,
    ).count()
    if remaining_count == 0:
        raise ValueError("不能删除最后一条明细，请直接删除整个回收单")

    if item.item_type == "part":
        oi = db.query(HandcraftPartItem).filter(HandcraftPartItem.id == item.handcraft_part_item_id).first()
    else:
        oi = db.query(HandcraftJewelryItem).filter(HandcraftJewelryItem.id == item.handcraft_jewelry_item_id).first()

    if oi:
        _reverse_receive(db, oi, item.item_type, float(item.qty))
        affected_order_id = oi.handcraft_order_id
    else:
        affected_order_id = None

    db.delete(item)
    db.flush()
    _recalc_total(db, receipt)
    db.flush()

    if affected_order_id:
        _check_handcraft_order_completion(db, affected_order_id)
        db.flush()


def get_handcraft_receipt_supplier_names(db: Session) -> list[str]:
    rows = db.query(HandcraftReceipt.supplier_name).distinct().all()
    return [row[0] for row in rows]
