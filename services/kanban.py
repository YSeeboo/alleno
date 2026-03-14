from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.plating_order import PlatingOrder, PlatingOrderItem
from models.handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem
from models.vendor_receipt import VendorReceipt
from schemas.kanban import (
    ReceiptItemIn,
    VendorCard,
    KanbanRow,
    KanbanResponse,
    VendorItemSummary,
    VendorOrderSummary,
    VendorDetailResponse,
)
from services.inventory import add_stock
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
        dispatched_rows = (
            db.query(PlatingOrderItem.part_id, func.sum(PlatingOrderItem.qty))
            .join(PlatingOrder, PlatingOrder.id == PlatingOrderItem.plating_order_id)
            .filter(
                PlatingOrder.supplier_name == vendor_name,
                PlatingOrder.status == "processing",
            )
            .group_by(PlatingOrderItem.part_id)
            .all()
        )
        if not dispatched_rows:
            return
        dispatched = {pid: float(qty) for pid, qty in dispatched_rows}

        received_rows = (
            db.query(VendorReceipt.item_id, func.sum(VendorReceipt.qty))
            .filter(
                VendorReceipt.vendor_name == vendor_name,
                VendorReceipt.order_type == "plating",
                VendorReceipt.item_type == "part",
            )
            .group_by(VendorReceipt.item_id)
            .all()
        )
        received = {iid: float(qty) for iid, qty in received_rows}

        if not all(received.get(pid, 0.0) >= dqty for pid, dqty in dispatched.items()):
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
    dispatched = _dispatched_global(db, order_type)
    received = _received_global(db, order_type)
    pend_set = _pending_vendors(db, order_type)
    pend_counts = _pending_part_counts(db, order_type)

    # Group dispatched / received by (vendor_name, order_type)
    vnd_dispatched: dict[tuple, dict] = defaultdict(dict)
    for (vn, ot, item_id, item_type), qty in dispatched.items():
        vnd_dispatched[(vn, ot)][(item_id, item_type)] = qty

    vnd_received: dict[tuple, dict] = defaultdict(dict)
    for (vn, ot, item_id, item_type), qty in received.items():
        vnd_received[(vn, ot)][(item_id, item_type)] = qty

    pending_dispatch_list: list[tuple] = []
    pending_return_list: list[tuple] = []
    returned_list: list[tuple] = []

    all_keys = set(all_vnd.keys()) | pend_set

    for key in all_keys:
        vn, ot = key
        earliest = all_vnd.get(key, now_beijing())

        d_items = vnd_dispatched.get(key, {})
        r_items = vnd_received.get(key, {})
        total_dispatched = sum(d_items.values())

        # 待发出：有 pending 订单
        if key in pend_set:
            part_count = pend_counts.get(key, 0)
            pending_dispatch_list.append(
                (earliest, VendorCard(vendor_name=vn, order_type=ot, part_count=part_count, created_at=earliest))
            )

        if total_dispatched > 0:
            outstanding = {k: v for k, v in d_items.items() if v > r_items.get(k, 0.0)}
            if outstanding:
                # 待收回：至少有一个 item 尚未完全收回
                pending_return_list.append(
                    (
                        earliest,
                        VendorCard(
                            vendor_name=vn,
                            order_type=ot,
                            part_count=len(outstanding),
                            created_at=earliest,
                        ),
                    )
                )
            else:
                # 已收回：全部 item 均已收回
                returned_list.append(
                    (
                        earliest,
                        VendorCard(
                            vendor_name=vn,
                            order_type=ot,
                            part_count=len(d_items),
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
    dispatched = _dispatched_for_vendor(db, vendor_name, order_type)
    received = _received_for_vendor(db, vendor_name, order_type)

    # Merge dispatched + received into a unified item map
    # key: (item_id, item_type, plating_method)
    item_map: dict[tuple, dict] = {}

    if order_type == "plating":
        rows = (
            db.query(
                PlatingOrderItem.part_id,
                PlatingOrderItem.plating_method,
                func.sum(PlatingOrderItem.qty).label("qty"),
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
            item_map[key] = {"dispatched_qty": float(r.qty), "received_qty": 0.0}

        # Distribute received qty proportionally across plating methods for the same part
        for (item_id, item_type), recv_qty in received.items():
            matched = [k for k in item_map if k[0] == item_id and k[1] == item_type]
            if matched:
                total_dispatched_for_part = sum(item_map[k]["dispatched_qty"] for k in matched)
                for k in matched:
                    ratio = (
                        item_map[k]["dispatched_qty"] / total_dispatched_for_part
                        if total_dispatched_for_part > 0
                        else 1 / len(matched)
                    )
                    item_map[k]["received_qty"] += round(recv_qty * ratio, 4)
            else:
                item_map[(item_id, item_type, None)] = {"dispatched_qty": 0.0, "received_qty": recv_qty}

    else:  # handcraft
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

    items = [
        VendorItemSummary(
            item_id=item_id,
            item_type=item_type,
            plating_method=pm,
            dispatched_qty=vals["dispatched_qty"],
            received_qty=vals["received_qty"],
        )
        for (item_id, item_type, pm), vals in item_map.items()
    ]

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
    items: list[ReceiptItemIn],
    note: str | None = None,
) -> tuple[list[VendorReceipt], list[str]]:
    # Pre-compute caps once
    dispatched_map = _dispatched_for_vendor(db, vendor_name, order_type)
    received_map = _received_for_vendor(db, vendor_name, order_type)
    expected_jewelry_map = (
        _expected_jewelry_for_vendor(db, vendor_name) if order_type == "handcraft" else {}
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

        remaining = cap - total_so_far
        if item.qty > remaining:
            warnings.append(
                f"{item.item_id} 收回数量({item.qty}) > 剩余量({max(remaining, 0):.2f})，请检查！"
            )

        pending_in_request[key] = pending + item.qty

        receipt = VendorReceipt(
            vendor_name=vendor_name,
            order_type=order_type,
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

    _try_complete_vendor_orders(db, vendor_name, order_type)
    return receipts, warnings


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
