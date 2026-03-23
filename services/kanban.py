from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.plating_order import PlatingOrder, PlatingOrderItem
from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
from models.vendor_receipt import VendorReceipt
from models.part import Part
from models.jewelry import Jewelry
from schemas.kanban import (
    ReceiptItemIn,
    VendorCard,
    KanbanRow,
    KanbanResponse,
    VendorItemSummary,
    VendorOrderSummary,
    VendorDetailResponse,
    VendorOrderOption,
    OrderItemHint,
    OrderItemsForReceiptResponse,
)
from services.inventory import add_stock, deduct_stock
from services.plating import send_plating_order
from services.handcraft import send_handcraft_order
from time_utils import now_beijing

_DISPATCHED_STATUSES = ("processing", "completed")


# ──────────────────────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────────────────────

def _all_vendors(db: Session, order_type: str | None) -> dict[tuple, object]:
    """(vendor_name, order_type) → earliest created_at across all orders."""
    result: dict[tuple, object] = {}

    if order_type is None or order_type == "plating":
        rows = (
            db.query(PlatingOrder.supplier_name, func.min(PlatingOrder.created_at).label("earliest"))
            .group_by(PlatingOrder.supplier_name)
            .all()
        )
        for r in rows:
            result[(r.supplier_name, "plating")] = r.earliest

    if order_type is None or order_type == "handcraft":
        rows = (
            db.query(HandcraftOrder.supplier_name, func.min(HandcraftOrder.created_at).label("earliest"))
            .group_by(HandcraftOrder.supplier_name)
            .all()
        )
        for r in rows:
            result[(r.supplier_name, "handcraft")] = r.earliest

    return result


def _dispatched_global(db: Session, order_type: str | None) -> dict[tuple, float]:
    """(vendor_name, order_type, item_id, item_type) → dispatched qty.

    Only counts orders whose status is 'processing' or 'completed'.
    """
    result: dict[tuple, float] = {}

    if order_type is None or order_type == "plating":
        rows = (
            db.query(
                PlatingOrder.supplier_name,
                PlatingOrderItem.part_id,
                func.sum(PlatingOrderItem.qty).label("qty"),
            )
            .join(PlatingOrderItem, PlatingOrder.id == PlatingOrderItem.plating_order_id)
            .filter(PlatingOrder.status.in_(_DISPATCHED_STATUSES))
            .group_by(PlatingOrder.supplier_name, PlatingOrderItem.part_id)
            .all()
        )
        for r in rows:
            result[(r.supplier_name, "plating", r.part_id, "part")] = float(r.qty)

    if order_type is None or order_type == "handcraft":
        rows = (
            db.query(
                HandcraftOrder.supplier_name,
                HandcraftPartItem.part_id,
                func.sum(HandcraftPartItem.qty).label("qty"),
            )
            .join(HandcraftPartItem, HandcraftOrder.id == HandcraftPartItem.handcraft_order_id)
            .filter(HandcraftOrder.status.in_(_DISPATCHED_STATUSES))
            .group_by(HandcraftOrder.supplier_name, HandcraftPartItem.part_id)
            .all()
        )
        for r in rows:
            result[(r.supplier_name, "handcraft", r.part_id, "part")] = float(r.qty)

        # Jewelry expected return qty — used for pending_return / returned status calculation
        jewelry_rows = (
            db.query(
                HandcraftOrder.supplier_name,
                HandcraftJewelryItem.jewelry_id,
                func.sum(HandcraftJewelryItem.qty).label("qty"),
            )
            .join(HandcraftJewelryItem, HandcraftOrder.id == HandcraftJewelryItem.handcraft_order_id)
            .filter(HandcraftOrder.status.in_(_DISPATCHED_STATUSES))
            .group_by(HandcraftOrder.supplier_name, HandcraftJewelryItem.jewelry_id)
            .all()
        )
        for r in jewelry_rows:
            result[(r.supplier_name, "handcraft", r.jewelry_id, "jewelry")] = float(r.qty)

    return result


def _received_global(db: Session, order_type: str | None) -> dict[tuple, float]:
    """(vendor_name, order_type, item_id, item_type) → received qty from vendor_receipt."""
    q = (
        db.query(
            VendorReceipt.vendor_name,
            VendorReceipt.order_type,
            VendorReceipt.item_id,
            VendorReceipt.item_type,
            func.sum(VendorReceipt.qty).label("qty"),
        )
        .group_by(
            VendorReceipt.vendor_name,
            VendorReceipt.order_type,
            VendorReceipt.item_id,
            VendorReceipt.item_type,
        )
    )
    if order_type:
        q = q.filter(VendorReceipt.order_type == order_type)
    return {(r.vendor_name, r.order_type, r.item_id, r.item_type): float(r.qty) for r in q.all()}


def _pending_vendors(db: Session, order_type: str | None) -> set[tuple]:
    """Set of (vendor_name, order_type) that have at least one 'pending' order."""
    result: set[tuple] = set()

    if order_type is None or order_type == "plating":
        rows = (
            db.query(PlatingOrder.supplier_name)
            .filter(PlatingOrder.status == "pending")
            .distinct()
            .all()
        )
        for r in rows:
            result.add((r.supplier_name, "plating"))

    if order_type is None or order_type == "handcraft":
        rows = (
            db.query(HandcraftOrder.supplier_name)
            .filter(HandcraftOrder.status == "pending")
            .distinct()
            .all()
        )
        for r in rows:
            result.add((r.supplier_name, "handcraft"))

    return result


def _pending_part_counts(db: Session, order_type: str | None) -> dict[tuple, int]:
    """(vendor_name, order_type) → distinct part type count in pending orders."""
    counts: dict[tuple, int] = {}

    if order_type is None or order_type == "plating":
        rows = (
            db.query(
                PlatingOrder.supplier_name,
                func.count(PlatingOrderItem.part_id.distinct()).label("cnt"),
            )
            .join(PlatingOrderItem, PlatingOrder.id == PlatingOrderItem.plating_order_id)
            .filter(PlatingOrder.status == "pending")
            .group_by(PlatingOrder.supplier_name)
            .all()
        )
        for r in rows:
            counts[(r.supplier_name, "plating")] = r.cnt

    if order_type is None or order_type == "handcraft":
        rows = (
            db.query(
                HandcraftOrder.supplier_name,
                func.count(HandcraftPartItem.part_id.distinct()).label("cnt"),
            )
            .join(HandcraftPartItem, HandcraftOrder.id == HandcraftPartItem.handcraft_order_id)
            .filter(HandcraftOrder.status == "pending")
            .group_by(HandcraftOrder.supplier_name)
            .all()
        )
        for r in rows:
            counts[(r.supplier_name, "handcraft")] = r.cnt

    return counts


def _processing_outstanding_counts(db: Session, order_type: str | None) -> dict[tuple, int]:
    counts: dict[tuple, int] = {}
    outstanding_items: dict[tuple, set[tuple]] = defaultdict(set)

    if order_type is None or order_type == "plating":
        rows = (
            db.query(
                PlatingOrder.supplier_name,
                PlatingOrderItem.part_id,
                func.sum(PlatingOrderItem.qty).label("dispatched"),
                func.sum(func.coalesce(PlatingOrderItem.received_qty, 0)).label("received"),
            )
            .join(PlatingOrderItem, PlatingOrder.id == PlatingOrderItem.plating_order_id)
            .filter(PlatingOrder.status == "processing")
            .group_by(PlatingOrder.supplier_name, PlatingOrderItem.part_id)
            .all()
        )
        for row in rows:
            if float(row.dispatched) > float(row.received):
                outstanding_items[(row.supplier_name, "plating")].add((row.part_id, "part"))

    if order_type is None or order_type == "handcraft":
        part_rows = (
            db.query(
                HandcraftOrder.supplier_name,
                HandcraftPartItem.part_id,
                func.sum(HandcraftPartItem.qty).label("qty"),
            )
            .join(HandcraftPartItem, HandcraftOrder.id == HandcraftPartItem.handcraft_order_id)
            .filter(HandcraftOrder.status == "processing")
            .group_by(HandcraftOrder.supplier_name, HandcraftPartItem.part_id)
            .all()
        )
        jewelry_rows = (
            db.query(
                HandcraftOrder.supplier_name,
                HandcraftJewelryItem.jewelry_id,
                func.sum(HandcraftJewelryItem.qty).label("qty"),
            )
            .join(HandcraftJewelryItem, HandcraftOrder.id == HandcraftJewelryItem.handcraft_order_id)
            .filter(HandcraftOrder.status == "processing")
            .group_by(HandcraftOrder.supplier_name, HandcraftJewelryItem.jewelry_id)
            .all()
        )
        received_rows = (
            db.query(
                HandcraftOrder.supplier_name,
                VendorReceipt.item_id,
                VendorReceipt.item_type,
                func.sum(VendorReceipt.qty).label("qty"),
            )
            .join(HandcraftOrder, HandcraftOrder.id == VendorReceipt.order_id)
            .filter(
                VendorReceipt.order_type == "handcraft",
                HandcraftOrder.status == "processing",
            )
            .group_by(
                HandcraftOrder.supplier_name,
                VendorReceipt.item_id,
                VendorReceipt.item_type,
            )
            .all()
        )
        received_map = {
            (row.supplier_name, row.item_id, row.item_type): float(row.qty)
            for row in received_rows
        }
        for row in part_rows:
            item_key = (row.supplier_name, row.part_id, "part")
            if float(row.qty) > received_map.get(item_key, 0.0):
                outstanding_items[(row.supplier_name, "handcraft")].add((row.part_id, "part"))
        for row in jewelry_rows:
            item_key = (row.supplier_name, row.jewelry_id, "jewelry")
            if float(row.qty) > received_map.get(item_key, 0.0):
                outstanding_items[(row.supplier_name, "handcraft")].add((row.jewelry_id, "jewelry"))

    for key, items in outstanding_items.items():
        counts[key] = len(items)

    return counts


def _completed_item_counts(db: Session, order_type: str | None) -> dict[tuple, int]:
    counts: dict[tuple, int] = {}
    completed_items: dict[tuple, set[tuple]] = defaultdict(set)

    if order_type is None or order_type == "plating":
        rows = (
            db.query(
                PlatingOrder.supplier_name,
                PlatingOrderItem.part_id,
            )
            .join(PlatingOrderItem, PlatingOrder.id == PlatingOrderItem.plating_order_id)
            .filter(PlatingOrder.status == "completed")
            .group_by(PlatingOrder.supplier_name, PlatingOrderItem.part_id)
            .all()
        )
        for row in rows:
            completed_items[(row.supplier_name, "plating")].add((row.part_id, "part"))

    if order_type is None or order_type == "handcraft":
        part_rows = (
            db.query(
                HandcraftOrder.supplier_name,
                HandcraftPartItem.part_id,
            )
            .join(HandcraftPartItem, HandcraftOrder.id == HandcraftPartItem.handcraft_order_id)
            .filter(HandcraftOrder.status == "completed")
            .group_by(HandcraftOrder.supplier_name, HandcraftPartItem.part_id)
            .all()
        )
        jewelry_rows = (
            db.query(
                HandcraftOrder.supplier_name,
                HandcraftJewelryItem.jewelry_id,
            )
            .join(HandcraftJewelryItem, HandcraftOrder.id == HandcraftJewelryItem.handcraft_order_id)
            .filter(HandcraftOrder.status == "completed")
            .group_by(HandcraftOrder.supplier_name, HandcraftJewelryItem.jewelry_id)
            .all()
        )
        for row in part_rows:
            completed_items[(row.supplier_name, "handcraft")].add((row.part_id, "part"))
        for row in jewelry_rows:
            completed_items[(row.supplier_name, "handcraft")].add((row.jewelry_id, "jewelry"))

    for key, items in completed_items.items():
        counts[key] = len(items)

    return counts


def _dispatched_for_vendor(db: Session, vendor_name: str, order_type: str) -> dict[tuple, float]:
    """(item_id, 'part') → dispatched qty for a specific vendor."""
    result: dict[tuple, float] = {}

    if order_type == "plating":
        rows = (
            db.query(PlatingOrderItem.part_id, func.sum(PlatingOrderItem.qty).label("qty"))
            .join(PlatingOrder, PlatingOrder.id == PlatingOrderItem.plating_order_id)
            .filter(
                PlatingOrder.supplier_name == vendor_name,
                PlatingOrder.status.in_(_DISPATCHED_STATUSES),
            )
            .group_by(PlatingOrderItem.part_id)
            .all()
        )
        for r in rows:
            result[(r.part_id, "part")] = float(r.qty)

    elif order_type == "handcraft":
        rows = (
            db.query(HandcraftPartItem.part_id, func.sum(HandcraftPartItem.qty).label("qty"))
            .join(HandcraftOrder, HandcraftOrder.id == HandcraftPartItem.handcraft_order_id)
            .filter(
                HandcraftOrder.supplier_name == vendor_name,
                HandcraftOrder.status.in_(_DISPATCHED_STATUSES),
            )
            .group_by(HandcraftPartItem.part_id)
            .all()
        )
        for r in rows:
            result[(r.part_id, "part")] = float(r.qty)

    return result


def _received_for_vendor(db: Session, vendor_name: str, order_type: str) -> dict[tuple, float]:
    """(item_id, item_type) → received qty for a specific vendor from vendor_receipt."""
    rows = (
        db.query(
            VendorReceipt.item_id,
            VendorReceipt.item_type,
            func.sum(VendorReceipt.qty).label("qty"),
        )
        .filter(VendorReceipt.vendor_name == vendor_name, VendorReceipt.order_type == order_type)
        .group_by(VendorReceipt.item_id, VendorReceipt.item_type)
        .all()
    )
    return {(r.item_id, r.item_type): float(r.qty) for r in rows}


def _validate_order_ownership(
    db: Session, order_id: str, order_type: str, vendor_name: str
) -> None:
    """Raise ValueError if order_id doesn't exist or doesn't belong to vendor_name."""
    if order_type == "plating":
        order = db.query(PlatingOrder).filter(PlatingOrder.id == order_id).first()
    else:
        order = db.query(HandcraftOrder).filter(HandcraftOrder.id == order_id).first()
    if order is None:
        raise ValueError(f"订单 {order_id} 不存在")
    if order.supplier_name != vendor_name:
        raise ValueError(f"订单 {order_id} 不属于厂家 {vendor_name}")


def _dispatched_for_order(db: Session, order_id: str, order_type: str) -> dict[tuple, float]:
    """(item_id, item_type) → dispatched qty for a specific order."""
    result: dict[tuple, float] = {}
    if order_type == "plating":
        rows = (
            db.query(PlatingOrderItem.part_id, func.sum(PlatingOrderItem.qty).label("qty"))
            .filter(PlatingOrderItem.plating_order_id == order_id)
            .group_by(PlatingOrderItem.part_id)
            .all()
        )
        for r in rows:
            result[(r.part_id, "part")] = float(r.qty)
    elif order_type == "handcraft":
        rows = (
            db.query(HandcraftPartItem.part_id, func.sum(HandcraftPartItem.qty).label("qty"))
            .filter(HandcraftPartItem.handcraft_order_id == order_id)
            .group_by(HandcraftPartItem.part_id)
            .all()
        )
        for r in rows:
            result[(r.part_id, "part")] = float(r.qty)
    return result


def _received_for_order(db: Session, order_id: str, order_type: str) -> dict[tuple, float]:
    """(item_id, item_type) → received qty for a specific order from vendor_receipt."""
    rows = (
        db.query(
            VendorReceipt.item_id,
            VendorReceipt.item_type,
            func.sum(VendorReceipt.qty).label("qty"),
        )
        .filter(VendorReceipt.order_id == order_id, VendorReceipt.order_type == order_type)
        .group_by(VendorReceipt.item_id, VendorReceipt.item_type)
        .all()
    )
    return {(r.item_id, r.item_type): float(r.qty) for r in rows}


def _sync_plating_item_receipts(db: Session, order_id: str) -> None:
    received_rows = (
        db.query(VendorReceipt.item_id, func.sum(VendorReceipt.qty).label("qty"))
        .filter(
            VendorReceipt.order_id == order_id,
            VendorReceipt.order_type == "plating",
            VendorReceipt.item_type == "part",
        )
        .group_by(VendorReceipt.item_id)
        .all()
    )
    received_by_part = {row.item_id: float(row.qty) for row in received_rows}

    items = (
        db.query(PlatingOrderItem)
        .filter(PlatingOrderItem.plating_order_id == order_id)
        .order_by(PlatingOrderItem.id.asc())
        .all()
    )
    for item in items:
        remaining = received_by_part.get(item.part_id, 0.0)
        applied = min(float(item.qty), max(remaining, 0.0))
        item.received_qty = applied
        item.status = "已收回" if applied >= float(item.qty) else "电镀中"
        received_by_part[item.part_id] = max(0.0, remaining - applied)


def _set_plating_items_pending(db: Session, order_id: str) -> None:
    items = (
        db.query(PlatingOrderItem)
        .filter(PlatingOrderItem.plating_order_id == order_id)
        .all()
    )
    for item in items:
        item.received_qty = 0
        item.status = "未送出"


def _set_plating_items_processing(db: Session, order_id: str) -> None:
    items = (
        db.query(PlatingOrderItem)
        .filter(PlatingOrderItem.plating_order_id == order_id)
        .all()
    )
    for item in items:
        item.received_qty = 0
        item.status = "电镀中"


def _expected_jewelry_for_order(db: Session, order_id: str) -> dict[str, float]:
    """jewelry_id → expected return qty for a specific handcraft order."""
    rows = (
        db.query(HandcraftJewelryItem.jewelry_id, func.sum(HandcraftJewelryItem.qty).label("qty"))
        .filter(HandcraftJewelryItem.handcraft_order_id == order_id)
        .group_by(HandcraftJewelryItem.jewelry_id)
        .all()
    )
    return {jid: float(qty) for jid, qty in rows}


def _sync_handcraft_jewelry_receipts(db: Session, order_id: str) -> None:
    received_rows = (
        db.query(VendorReceipt.item_id, func.sum(VendorReceipt.qty).label("qty"))
        .filter(
            VendorReceipt.order_id == order_id,
            VendorReceipt.order_type == "handcraft",
            VendorReceipt.item_type == "jewelry",
        )
        .group_by(VendorReceipt.item_id)
        .all()
    )
    received_by_jewelry = {row.item_id: float(row.qty) for row in received_rows}

    items = (
        db.query(HandcraftJewelryItem)
        .filter(HandcraftJewelryItem.handcraft_order_id == order_id)
        .order_by(HandcraftJewelryItem.id.asc())
        .all()
    )
    for item in items:
        remaining = received_by_jewelry.get(item.jewelry_id, 0.0)
        applied = min(float(item.qty), max(remaining, 0.0))
        item.received_qty = int(applied)
        item.status = "已收回" if applied >= float(item.qty) else "制作中"
        received_by_jewelry[item.jewelry_id] = max(0.0, remaining - applied)


def _set_handcraft_jewelry_pending(db: Session, order_id: str) -> None:
    items = (
        db.query(HandcraftJewelryItem)
        .filter(HandcraftJewelryItem.handcraft_order_id == order_id)
        .all()
    )
    for item in items:
        item.received_qty = 0
        item.status = "未送出"


def _set_handcraft_jewelry_processing(db: Session, order_id: str) -> None:
    items = (
        db.query(HandcraftJewelryItem)
        .filter(HandcraftJewelryItem.handcraft_order_id == order_id)
        .all()
    )
    for item in items:
        item.received_qty = 0
        item.status = "制作中"


def _expected_jewelry_for_vendor(db: Session, vendor_name: str) -> dict[str, float]:
    """jewelry_id → expected return qty, *processing orders only*.

    Used for over-receipt warning in record_vendor_receipt so that historical
    completed orders do not inflate the cap and mask genuine over-receipts.
    """
    rows = (
        db.query(
            HandcraftJewelryItem.jewelry_id,
            func.sum(HandcraftJewelryItem.qty).label("qty"),
        )
        .join(HandcraftOrder, HandcraftOrder.id == HandcraftJewelryItem.handcraft_order_id)
        .filter(
            HandcraftOrder.supplier_name == vendor_name,
            HandcraftOrder.status == "processing",
        )
        .group_by(HandcraftJewelryItem.jewelry_id)
        .all()
    )
    return {jid: float(qty) for jid, qty in rows}


def _all_expected_jewelry_for_vendor(db: Session, vendor_name: str) -> dict[str, float]:
    """jewelry_id → expected return qty across processing *and* completed orders.

    Used for vendor detail display so historical completed orders are visible.
    """
    rows = (
        db.query(
            HandcraftJewelryItem.jewelry_id,
            func.sum(HandcraftJewelryItem.qty).label("qty"),
        )
        .join(HandcraftOrder, HandcraftOrder.id == HandcraftJewelryItem.handcraft_order_id)
        .filter(
            HandcraftOrder.supplier_name == vendor_name,
            HandcraftOrder.status.in_(_DISPATCHED_STATUSES),
        )
        .group_by(HandcraftJewelryItem.jewelry_id)
        .all()
    )
    return {jid: float(qty) for jid, qty in rows}


def _try_complete_vendor_orders(db: Session, vendor_name: str, order_type: str) -> None:
    """Mark processing orders as completed when all outstanding items have been received.

    Only looks at *processing* orders (not historical completed ones) to avoid false positives
    from old orders that predate the vendor_receipt table.

    - plating: compares parts dispatched vs parts received (item_type='part')
    - handcraft: compares expected jewelry qty vs jewelry received (item_type='jewelry')
    """
    now = datetime.now(timezone.utc)

    if order_type == "plating":
        # Plating completion is handled by receive_plating_items in services/plating.py
        # This branch is kept for completeness but should not be reached via record_vendor_receipt
        rows = (
            db.query(
                func.sum(PlatingOrderItem.qty).label("dispatched"),
                func.sum(func.coalesce(PlatingOrderItem.received_qty, 0)).label("received"),
            )
            .join(PlatingOrder, PlatingOrder.id == PlatingOrderItem.plating_order_id)
            .filter(
                PlatingOrder.supplier_name == vendor_name,
                PlatingOrder.status == "processing",
            )
            .first()
        )
        if rows is None or rows.dispatched is None:
            return
        if float(rows.received) < float(rows.dispatched):
            return

        db.query(PlatingOrder).filter(
            PlatingOrder.supplier_name == vendor_name,
            PlatingOrder.status == "processing",
        ).update({"status": "completed", "completed_at": now}, synchronize_session=False)

    else:  # handcraft
        expected_rows = (
            db.query(HandcraftJewelryItem.jewelry_id, func.sum(HandcraftJewelryItem.qty))
            .join(HandcraftOrder, HandcraftOrder.id == HandcraftJewelryItem.handcraft_order_id)
            .filter(
                HandcraftOrder.supplier_name == vendor_name,
                HandcraftOrder.status == "processing",
            )
            .group_by(HandcraftJewelryItem.jewelry_id)
            .all()
        )
        if not expected_rows:
            return
        expected = {jid: float(qty) for jid, qty in expected_rows}

        received_rows = (
            db.query(VendorReceipt.item_id, func.sum(VendorReceipt.qty))
            .filter(
                VendorReceipt.vendor_name == vendor_name,
                VendorReceipt.order_type == "handcraft",
                VendorReceipt.item_type == "jewelry",
            )
            .group_by(VendorReceipt.item_id)
            .all()
        )
        received = {jid: float(qty) for jid, qty in received_rows}

        if not all(received.get(jid, 0.0) >= eqty for jid, eqty in expected.items()):
            return

        db.query(HandcraftOrder).filter(
            HandcraftOrder.supplier_name == vendor_name,
            HandcraftOrder.status == "processing",
        ).update({"status": "completed", "completed_at": now}, synchronize_session=False)


# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────

def get_kanban(
    db: Session,
    order_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> KanbanResponse:
    all_vnd = _all_vendors(db, order_type)
    pend_set = _pending_vendors(db, order_type)
    pend_counts = _pending_part_counts(db, order_type)
    processing_outstanding_counts = _processing_outstanding_counts(db, order_type)
    completed_counts = _completed_item_counts(db, order_type)

    pending_dispatch_list: list[tuple] = []
    pending_return_list: list[tuple] = []
    returned_list: list[tuple] = []

    all_keys = (
        set(all_vnd.keys())
        | pend_set
        | set(processing_outstanding_counts.keys())
        | set(completed_counts.keys())
    )

    for key in all_keys:
        vn, ot = key
        earliest = all_vnd.get(key, now_beijing())

        # 待发出：有 pending 订单
        if key in pend_set:
            part_count = pend_counts.get(key, 0)
            pending_dispatch_list.append(
                (earliest, VendorCard(vendor_name=vn, order_type=ot, part_count=part_count, created_at=earliest))
            )

        outstanding_count = processing_outstanding_counts.get(key, 0)
        if outstanding_count > 0:
            pending_return_list.append(
                (
                    earliest,
                    VendorCard(
                        vendor_name=vn,
                        order_type=ot,
                        part_count=outstanding_count,
                        created_at=earliest,
                    ),
                )
            )

        completed_count = completed_counts.get(key, 0)
        if completed_count > 0:
            returned_list.append(
                (
                    earliest,
                    VendorCard(
                        vendor_name=vn,
                        order_type=ot,
                        part_count=completed_count,
                        created_at=earliest,
                    ),
                )
            )

    for lst in (pending_dispatch_list, pending_return_list, returned_list):
        lst.sort(key=lambda x: x[0])

    offset = (page - 1) * page_size

    def _make_row(status: str, lst: list) -> KanbanRow:
        return KanbanRow(
            status=status,
            vendors=[card for _, card in lst[offset: offset + page_size]],
            total=len(lst),
        )

    return KanbanResponse(
        pending_dispatch=_make_row("pending_dispatch", pending_dispatch_list),
        pending_return=_make_row("pending_return", pending_return_list),
        returned=_make_row("returned", returned_list),
    )


def get_vendor_detail(db: Session, vendor_name: str, order_type: str) -> VendorDetailResponse:
    # Merge dispatched + received into a unified item map
    # key: (item_id, item_type, plating_method)
    item_map: dict[tuple, dict] = {}

    if order_type == "plating":
        # Read dispatched + received directly from PlatingOrderItem (no VendorReceipt)
        rows = (
            db.query(
                PlatingOrderItem.part_id,
                PlatingOrderItem.plating_method,
                func.sum(PlatingOrderItem.qty).label("dispatched"),
                func.sum(func.coalesce(PlatingOrderItem.received_qty, 0)).label("received"),
            )
            .join(PlatingOrder, PlatingOrder.id == PlatingOrderItem.plating_order_id)
            .filter(
                PlatingOrder.supplier_name == vendor_name,
                PlatingOrder.status.in_(_DISPATCHED_STATUSES),
            )
            .group_by(PlatingOrderItem.part_id, PlatingOrderItem.plating_method)
            .all()
        )
        for r in rows:
            key = (r.part_id, "part", r.plating_method)
            item_map[key] = {"dispatched_qty": float(r.dispatched), "received_qty": float(r.received or 0)}

    else:  # handcraft
        dispatched = _dispatched_for_vendor(db, vendor_name, order_type)
        received = _received_for_vendor(db, vendor_name, order_type)

        # Parts: from HandcraftPartItem (actual dispatched qty)
        for (item_id, item_type), d_qty in dispatched.items():
            item_map[(item_id, item_type, None)] = {"dispatched_qty": d_qty, "received_qty": 0.0}

        # Jewelry: from HandcraftJewelryItem (expected return qty, including completed orders)
        expected_jewelry = _all_expected_jewelry_for_vendor(db, vendor_name)
        for jewelry_id, exp_qty in expected_jewelry.items():
            item_map[(jewelry_id, "jewelry", None)] = {"dispatched_qty": exp_qty, "received_qty": 0.0}

        # Fill actual received quantities
        for (item_id, item_type), r_qty in received.items():
            key = (item_id, item_type, None)
            if key in item_map:
                item_map[key]["received_qty"] += r_qty
            else:
                item_map[key] = {"dispatched_qty": 0.0, "received_qty": r_qty}

    part_ids = {item_id for (item_id, item_type, _) in item_map if item_type == "part"}
    jewelry_ids = {item_id for (item_id, item_type, _) in item_map if item_type == "jewelry"}
    parts_by_id = {
        part.id: part
        for part in db.query(Part).filter(Part.id.in_(part_ids)).all()
    } if part_ids else {}
    jewelries_by_id = {
        jewelry.id: jewelry
        for jewelry in db.query(Jewelry).filter(Jewelry.id.in_(jewelry_ids)).all()
    } if jewelry_ids else {}

    items = []
    for (item_id, item_type, pm), vals in item_map.items():
        item_obj = parts_by_id.get(item_id) if item_type == "part" else jewelries_by_id.get(item_id)
        items.append(
            VendorItemSummary(
                item_id=item_id,
                item_type=item_type,
                item_name=item_obj.name if item_obj else None,
                image=item_obj.image if item_obj else None,
                plating_method=pm,
                dispatched_qty=vals["dispatched_qty"],
                received_qty=vals["received_qty"],
            )
        )

    # Orders
    if order_type == "plating":
        order_rows = (
            db.query(PlatingOrder)
            .filter(PlatingOrder.supplier_name == vendor_name)
            .order_by(PlatingOrder.created_at.desc())
            .all()
        )
        orders = [
            VendorOrderSummary(
                order_id=o.id, order_type="plating", status=o.status, created_at=o.created_at
            )
            for o in order_rows
        ]
    else:
        order_rows = (
            db.query(HandcraftOrder)
            .filter(HandcraftOrder.supplier_name == vendor_name)
            .order_by(HandcraftOrder.created_at.desc())
            .all()
        )
        orders = [
            VendorOrderSummary(
                order_id=o.id, order_type="handcraft", status=o.status, created_at=o.created_at
            )
            for o in order_rows
        ]

    return VendorDetailResponse(
        vendor_name=vendor_name,
        order_type=order_type,
        items=items,
        orders=orders,
    )


def record_vendor_receipt(
    db: Session,
    vendor_name: str,
    order_type: str,
    order_id: str,
    items: list[ReceiptItemIn],
    note: str | None = None,
) -> tuple[list[VendorReceipt], list[str]]:
    if order_type == "plating":
        raise ValueError("电镀单收回请使用电镀回收单（POST /api/plating-receipts/）")

    # Validate order exists and belongs to this vendor
    _validate_order_ownership(db, order_id, order_type, vendor_name)

    # Pre-compute caps scoped to this specific order
    dispatched_map = _dispatched_for_order(db, order_id, order_type)
    received_map = _received_for_order(db, order_id, order_type)
    expected_jewelry_map = (
        _expected_jewelry_for_order(db, order_id) if order_type == "handcraft" else {}
    )

    warnings: list[str] = []
    receipts: list[VendorReceipt] = []
    pending_in_request: dict[tuple, float] = {}  # 本次请求内已累积量，防止同 item 多行漏检

    _reason_map = {
        ("plating", "part"): "电镀收回",
        ("handcraft", "part"): "手工退回",
        ("handcraft", "jewelry"): "手工完成",
    }

    for item in items:
        key = (item.item_id, item.item_type)
        already_received = received_map.get(key, 0.0)
        pending = pending_in_request.get(key, 0.0)
        total_so_far = already_received + pending  # DB 历史 + 本次已录

        if item.item_type == "jewelry":
            cap = expected_jewelry_map.get(item.item_id, 0.0)
        else:
            cap = dispatched_map.get(key, 0.0)

        if cap == 0.0:
            raise ValueError(f"{item.item_id} 不属于订单 {order_id} 或未发出")

        remaining = cap - total_so_far
        if item.qty > remaining:
            warnings.append(
                f"{item.item_id} 收回数量({item.qty}) > 剩余量({max(remaining, 0):.2f})，请检查！"
            )

        pending_in_request[key] = pending + item.qty

        receipt = VendorReceipt(
            vendor_name=vendor_name,
            order_type=order_type,
            order_id=order_id,
            item_type=item.item_type,
            item_id=item.item_id,
            qty=item.qty,
            note=note,
            created_at=now_beijing(),
        )
        db.add(receipt)
        db.flush()
        receipts.append(receipt)

        reason = _reason_map.get((order_type, item.item_type))
        if reason:
            add_stock(db, item.item_type, item.item_id, item.qty, reason=reason)

    if order_type == "plating":
        _sync_plating_item_receipts(db, order_id)
    else:
        _sync_handcraft_jewelry_receipts(db, order_id)

    _try_complete_vendor_orders(db, vendor_name, order_type)
    return receipts, warnings


def get_orders_for_vendor(
    db: Session, vendor_name: str, order_type: str
) -> list[VendorOrderOption]:
    if order_type == "plating":
        raise ValueError("电镀单收回请使用电镀回收单（POST /api/plating-receipts/）")
    else:
        rows = (
            db.query(HandcraftOrder)
            .filter(HandcraftOrder.supplier_name == vendor_name, HandcraftOrder.status == "processing")
            .order_by(HandcraftOrder.created_at.desc())
            .all()
        )
        return [VendorOrderOption(order_id=o.id, status=o.status, created_at=o.created_at) for o in rows]


def get_order_items_for_receipt(
    db: Session, order_id: str, order_type: str
) -> OrderItemsForReceiptResponse:
    if order_type == "plating":
        raise ValueError("电镀单收回请使用电镀回收单（POST /api/plating-receipts/）")

    # Handcraft only — plating is blocked above
    received_rows = (
        db.query(VendorReceipt.item_id, VendorReceipt.item_type, func.sum(VendorReceipt.qty).label("qty"))
        .filter(VendorReceipt.order_id == order_id)
        .group_by(VendorReceipt.item_id, VendorReceipt.item_type)
        .all()
    )
    received = {(r.item_id, r.item_type): float(r.qty) for r in received_rows}
    part_rows = (
        db.query(HandcraftPartItem.part_id, func.sum(HandcraftPartItem.qty).label("qty"))
        .filter(HandcraftPartItem.handcraft_order_id == order_id)
        .group_by(HandcraftPartItem.part_id)
        .all()
    )
    jewelry_rows = (
        db.query(HandcraftJewelryItem.jewelry_id, func.sum(HandcraftJewelryItem.qty).label("qty"))
        .filter(HandcraftJewelryItem.handcraft_order_id == order_id)
        .group_by(HandcraftJewelryItem.jewelry_id)
        .all()
    )
    raw_items = (
        [(r.part_id, "part", float(r.qty)) for r in part_rows]
        + [(r.jewelry_id, "jewelry", float(r.qty)) for r in jewelry_rows]
    )

    hints: list[OrderItemHint] = []
    for item_id, item_type, dispatched_qty in raw_items:
        recv_qty = received.get((item_id, item_type), 0.0)
        if item_type == "part":
            obj = db.query(Part).filter(Part.id == item_id).first()
            item_name = obj.name if obj else None
        else:
            obj = db.query(Jewelry).filter(Jewelry.id == item_id).first()
            item_name = obj.name if obj else None

        hints.append(OrderItemHint(
            item_id=item_id,
            item_type=item_type,
            item_name=item_name,
            dispatched_qty=dispatched_qty,
            received_qty=recv_qty,
            remaining_qty=dispatched_qty - recv_qty,
        ))

    return OrderItemsForReceiptResponse(order_id=order_id, order_type=order_type, items=hints)


def _undo_receipts_for_order(db: Session, order_id: str, order_type: str) -> None:
    """Delete all VendorReceipt rows for this order_id and reverse the stock additions."""
    receipts = db.query(VendorReceipt).filter(VendorReceipt.order_id == order_id).all()
    _reason_undo_map = {
        ("plating", "part"): "电镀收回撤回",
        ("handcraft", "part"): "手工退回撤回",
        ("handcraft", "jewelry"): "手工完成撤回",
    }
    for r in receipts:
        reason = _reason_undo_map.get((order_type, r.item_type), "收回撤回")
        deduct_stock(db, r.item_type, r.item_id, r.qty, reason=reason)
        db.delete(r)


def _undo_plating_receipts(db: Session, order_id: str) -> None:
    """Reverse all received stock for a plating order and clean up receipt records."""
    from models.plating_receipt import PlatingReceipt, PlatingReceiptItem

    items = (
        db.query(PlatingOrderItem)
        .filter(PlatingOrderItem.plating_order_id == order_id)
        .all()
    )

    # Collect PlatingReceiptItem records linked to this order's items
    item_ids = [item.id for item in items]
    receipt_items = (
        db.query(PlatingReceiptItem)
        .filter(PlatingReceiptItem.plating_order_item_id.in_(item_ids))
        .all()
    ) if item_ids else []

    # Track which PlatingReceipts are affected
    affected_receipt_ids = {ri.plating_receipt_id for ri in receipt_items}

    # Reverse stock using PlatingReceiptItem as source of truth (not received_qty)
    plating_receipt_received: dict[str, float] = {}
    for ri in receipt_items:
        plating_receipt_received[ri.part_id] = plating_receipt_received.get(ri.part_id, 0.0) + float(ri.qty)
        db.delete(ri)

    # Reverse stock from VendorReceipt records (legacy kanban path)
    vendor_receipts = db.query(VendorReceipt).filter(
        VendorReceipt.order_id == order_id,
        VendorReceipt.order_type == "plating",
    ).all()
    vendor_received: dict[str, float] = {}
    for r in vendor_receipts:
        vendor_received[r.item_id] = vendor_received.get(r.item_id, 0.0) + float(r.qty)
        deduct_stock(db, r.item_type, r.item_id, r.qty, reason="电镀收回撤回")
        db.delete(r)

    # Reverse stock from PlatingReceiptItem records
    for part_id, qty in plating_receipt_received.items():
        deduct_stock(db, "part", part_id, qty, reason="电镀收回撤回")

    # Reverse any legacy received stock not tracked by either receipt type
    for item in items:
        recv = float(item.received_qty or 0)
        if recv > 0:
            receive_id = item.receive_part_id or item.part_id
            tracked = plating_receipt_received.get(receive_id, 0.0) + vendor_received.get(receive_id, 0.0)
            legacy = recv - tracked
            if legacy > 0:
                deduct_stock(db, "part", receive_id, legacy, reason="电镀收回撤回")

    db.flush()

    # Clean up empty PlatingReceipt records and recalc non-empty ones
    for receipt_id in affected_receipt_ids:
        receipt = db.query(PlatingReceipt).filter(PlatingReceipt.id == receipt_id).first()
        if receipt is None:
            continue
        remaining = db.query(PlatingReceiptItem).filter(
            PlatingReceiptItem.plating_receipt_id == receipt_id
        ).count()
        if remaining == 0:
            db.delete(receipt)
        else:
            # Recalc total for receipts that span multiple orders
            remaining_items = db.query(PlatingReceiptItem).filter(
                PlatingReceiptItem.plating_receipt_id == receipt_id
            ).all()
            from decimal import Decimal
            receipt.total_amount = sum(Decimal(str(ri.amount or 0)) for ri in remaining_items)
    db.flush()


def _force_complete_plating(db: Session, order: PlatingOrder, now) -> None:
    """For plating order, supplement missing receipts to force completion."""
    items = (
        db.query(PlatingOrderItem)
        .filter(PlatingOrderItem.plating_order_id == order.id)
        .all()
    )
    for item in items:
        remaining = float(item.qty) - float(item.received_qty or 0)
        if remaining > 0:
            receive_id = item.receive_part_id or item.part_id
            add_stock(db, "part", receive_id, remaining, reason="电镀收回")
            item.received_qty = item.qty
        item.status = "已收回"
    order.status = "completed"
    order.completed_at = now


def _force_complete_handcraft(db: Session, order: HandcraftOrder, now) -> None:
    """For handcraft order, supplement missing receipts for parts (returned) and jewelry (completed)."""
    received_rows = (
        db.query(VendorReceipt.item_id, VendorReceipt.item_type, func.sum(VendorReceipt.qty).label("qty"))
        .filter(VendorReceipt.order_id == order.id)
        .group_by(VendorReceipt.item_id, VendorReceipt.item_type)
        .all()
    )
    received = {(r.item_id, r.item_type): float(r.qty) for r in received_rows}

    # Parts (返回配件) - using direct query
    part_items = (
        db.query(HandcraftPartItem.part_id, func.sum(HandcraftPartItem.qty).label("qty"))
        .filter(HandcraftPartItem.handcraft_order_id == order.id)
        .group_by(HandcraftPartItem.part_id)
        .all()
    )
    part_dispatched: dict[str, float] = {r.part_id: float(r.qty) for r in part_items}

    for part_id, d_qty in part_dispatched.items():
        r_qty = received.get((part_id, "part"), 0.0)
        remaining = d_qty - r_qty
        if remaining > 0:
            db.add(VendorReceipt(
                vendor_name=order.supplier_name, order_type="handcraft",
                order_id=order.id, item_type="part", item_id=part_id,
                qty=remaining, note="强制完成", created_at=now_beijing(),
            ))
            add_stock(db, "part", part_id, remaining, reason="手工退回")

    # Jewelry (完成) - using direct query
    jewelry_items = (
        db.query(HandcraftJewelryItem.jewelry_id, func.sum(HandcraftJewelryItem.qty).label("qty"))
        .filter(HandcraftJewelryItem.handcraft_order_id == order.id)
        .group_by(HandcraftJewelryItem.jewelry_id)
        .all()
    )
    jewelry_expected: dict[str, float] = {r.jewelry_id: float(r.qty) for r in jewelry_items}

    for jewelry_id, e_qty in jewelry_expected.items():
        r_qty = received.get((jewelry_id, "jewelry"), 0.0)
        remaining = e_qty - r_qty
        if remaining > 0:
            db.add(VendorReceipt(
                vendor_name=order.supplier_name, order_type="handcraft",
                order_id=order.id, item_type="jewelry", item_id=jewelry_id,
                qty=remaining, note="强制完成", created_at=now_beijing(),
            ))
            add_stock(db, "jewelry", jewelry_id, remaining, reason="手工完成")

    _sync_handcraft_jewelry_receipts(db, order.id)
    order.status = "completed"
    order.completed_at = now


def change_order_status(
    db: Session,
    order_id: str,
    order_type: str,
    new_status: str,
) -> None:
    now = datetime.now(timezone.utc)

    if order_type == "plating":
        order = db.query(PlatingOrder).filter(PlatingOrder.id == order_id).first()
        if order is None:
            raise ValueError(f"电镀单 {order_id} 不存在")
        current_status = order.status

        if current_status == new_status:
            return

        if current_status == "pending" and new_status == "processing":
            send_plating_order(db, order_id)

        elif current_status == "processing" and new_status == "pending":
            _undo_plating_receipts(db, order_id)
            items = (
                db.query(PlatingOrderItem)
                .filter(PlatingOrderItem.plating_order_id == order_id)
                .all()
            )
            for item in items:
                add_stock(db, "part", item.part_id, float(item.qty), reason="电镀发出撤回")
            _set_plating_items_pending(db, order_id)
            order.status = "pending"

        elif current_status == "processing" and new_status == "completed":
            raise ValueError("电镀单完成需通过创建电镀回收单（POST /api/plating-receipts/），不支持直接改状态")

        elif current_status == "completed" and new_status == "processing":
            _undo_plating_receipts(db, order_id)
            _set_plating_items_processing(db, order_id)
            order.status = "processing"
            order.completed_at = None

        else:
            raise ValueError(f"不支持的状态转换：{current_status} → {new_status}")

    else:  # handcraft
        order = db.query(HandcraftOrder).filter(HandcraftOrder.id == order_id).first()
        if order is None:
            raise ValueError(f"手工单 {order_id} 不存在")
        current_status = order.status

        if current_status == new_status:
            return

        if current_status == "pending" and new_status == "processing":
            send_handcraft_order(db, order_id)

        elif current_status == "processing" and new_status == "pending":
            _undo_receipts_for_order(db, order_id, order_type)
            part_items = (
                db.query(HandcraftPartItem)
                .filter(HandcraftPartItem.handcraft_order_id == order_id)
                .all()
            )
            for item in part_items:
                add_stock(db, "part", item.part_id, float(item.qty), reason="手工发出撤回")
            _set_handcraft_jewelry_pending(db, order_id)
            order.status = "pending"

        elif current_status == "processing" and new_status == "completed":
            _force_complete_handcraft(db, order, now)

        elif current_status == "completed" and new_status == "processing":
            _undo_receipts_for_order(db, order_id, order_type)
            _set_handcraft_jewelry_processing(db, order_id)
            order.status = "processing"
            order.completed_at = None

        else:
            raise ValueError(f"不支持的状态转换：{current_status} → {new_status}")

    db.flush()


def list_vendors(db: Session, order_type: str | None = None, q: str | None = None) -> list[str]:
    """Return distinct vendor names for dropdown search."""
    names: set[str] = set()

    if order_type is None or order_type == "plating":
        qb = db.query(PlatingOrder.supplier_name).distinct()
        if q:
            qb = qb.filter(PlatingOrder.supplier_name.ilike(f"%{q}%"))
        for (name,) in qb.all():
            names.add(name)

    if order_type is None or order_type == "handcraft":
        qb = db.query(HandcraftOrder.supplier_name).distinct()
        if q:
            qb = qb.filter(HandcraftOrder.supplier_name.ilike(f"%{q}%"))
        for (name,) in qb.all():
            names.add(name)

    return sorted(names)
