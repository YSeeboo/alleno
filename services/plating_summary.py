from datetime import date
from typing import Literal, Optional

from sqlalchemy import asc, case, desc, func
from sqlalchemy.orm import Session

from models.plating_order import PlatingOrder, PlatingOrderItem
from models.part import Part
from models.plating_receipt import PlatingReceipt, PlatingReceiptItem
from models.production_loss import ProductionLoss
from time_utils import now_beijing


def _to_beijing_date(dt) -> Optional[date]:
    """PlatingOrder.created_at is stored as naive Beijing time."""
    return dt.date() if dt is not None else None


def _serialize_dispatched(poi: PlatingOrderItem, po: PlatingOrder, part: Optional[Part],
                          recv_part: Optional[Part], today: date) -> dict:
    qty = float(poi.qty or 0)
    received = float(poi.received_qty or 0)
    is_completed = received >= qty
    dispatch_date = _to_beijing_date(po.created_at)
    days_out = None
    if not is_completed:
        days_out = max(0, (today - dispatch_date).days - 1)
    return {
        "plating_order_item_id": poi.id,
        "plating_order_id": po.id,
        "supplier_name": po.supplier_name,
        "part_id": part.id if part else None,
        "part_name": part.name if part else None,
        "part_image": part.image if part else None,
        "plating_method": poi.plating_method,
        "qty": qty,
        "unit": poi.unit,
        "weight": float(poi.weight) if poi.weight is not None else None,
        "weight_unit": poi.weight_unit,
        "note": poi.note,
        "dispatch_date": dispatch_date,
        "days_out": days_out,
        "is_completed": is_completed,
        "receive_part_id": recv_part.id if recv_part else None,
        "receive_part_name": recv_part.name if recv_part else None,
        "receive_part_image": recv_part.image if recv_part else None,
    }


def list_dispatched(
    db: Session,
    *,
    supplier_name: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    part_keyword: Optional[str] = None,
    sort: Literal["dispatch_date_desc", "days_out_desc"] = "dispatch_date_desc",
    skip: int = 0,
    limit: int = 30,
) -> tuple[list[dict], int]:
    from services._helpers import keyword_filter

    today = now_beijing().date()
    is_completed_expr = (PlatingOrderItem.received_qty >= PlatingOrderItem.qty)

    q = (
        db.query(PlatingOrderItem, PlatingOrder)
        .join(PlatingOrder, PlatingOrderItem.plating_order_id == PlatingOrder.id)
    )

    if supplier_name:
        q = q.filter(PlatingOrder.supplier_name == supplier_name)
    if date_from is not None:
        q = q.filter(func.date(PlatingOrder.created_at) >= date_from)
    if date_to is not None:
        q = q.filter(func.date(PlatingOrder.created_at) <= date_to)

    if part_keyword:
        q = q.join(Part, PlatingOrderItem.part_id == Part.id)
        kw = keyword_filter(part_keyword, Part.id, Part.name)
        if kw is not None:
            q = q.filter(kw)

    total = q.count()

    if sort == "days_out_desc":
        # days_out = max(0, today - dispatch_date - 1) is monotonically decreasing in
        # dispatch_date, so ordering by created_at asc gives the same row order as
        # days_out desc — without portable date-arithmetic SQL.
        q = q.order_by(
            case((is_completed_expr, 1), else_=0),
            asc(PlatingOrder.created_at),
            desc(PlatingOrderItem.id),
        )
    else:
        # Default sort: in-progress first (completed flag asc: False=0 before True=1),
        # then within each partition by dispatch date desc, then item id desc for stability.
        q = q.order_by(
            case((is_completed_expr, 1), else_=0),
            desc(PlatingOrder.created_at),
            desc(PlatingOrderItem.id),
        )

    rows = q.offset(skip).limit(limit).all()

    # Batch-load parts (original + receive)
    part_ids = {poi.part_id for poi, _ in rows} | {
        poi.receive_part_id for poi, _ in rows if poi.receive_part_id
    }
    parts = {p.id: p for p in db.query(Part).filter(Part.id.in_(part_ids)).all()} if part_ids else {}

    items = [
        _serialize_dispatched(poi, po, parts.get(poi.part_id),
                              parts.get(poi.receive_part_id) if poi.receive_part_id else None,
                              today)
        for poi, po in rows
    ]
    return items, total


def _serialize_received(poi: PlatingOrderItem, po: PlatingOrder, part: Optional[Part],
                        recv_part: Optional[Part], today: date,
                        receipts: list[dict], loss_total: float) -> dict:
    base = _serialize_dispatched(poi, po, part, recv_part, today)
    qty = base["qty"]
    received_qty = float(poi.received_qty or 0)
    actual_received = received_qty - loss_total

    if loss_total > 0:
        loss_state = "confirmed"
    elif qty > actual_received:
        loss_state = "pending"
    else:
        loss_state = "none"

    base.update({
        "actual_received_qty": actual_received,
        "unreceived_qty": qty - received_qty,
        "loss_total_qty": loss_total,
        "loss_state": loss_state,
        "receipts": receipts,
        "latest_receipt_id": receipts[0]["receipt_id"] if receipts else None,
    })
    return base


def list_received(
    db: Session,
    *,
    supplier_name: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    part_keyword: Optional[str] = None,
    skip: int = 0,
    limit: int = 30,
) -> tuple[list[dict], int]:
    from services._helpers import keyword_filter

    today = now_beijing().date()
    is_completed_expr = (PlatingOrderItem.received_qty >= PlatingOrderItem.qty)

    q = (
        db.query(PlatingOrderItem, PlatingOrder)
        .join(PlatingOrder, PlatingOrderItem.plating_order_id == PlatingOrder.id)
        .filter(PlatingOrderItem.received_qty > 0)
    )

    if supplier_name:
        q = q.filter(PlatingOrder.supplier_name == supplier_name)
    if part_keyword:
        q = q.join(Part, PlatingOrderItem.part_id == Part.id)
        kw = keyword_filter(part_keyword, Part.id, Part.name)
        if kw is not None:
            q = q.filter(kw)

    # Push date filter on receipt date to SQL. Items with NO receipts (full-loss
    # case) are excluded when any date filter is set — matches earlier behavior.
    if date_from is not None or date_to is not None:
        receipt_subq = (
            db.query(PlatingReceiptItem)
            .join(PlatingReceipt, PlatingReceiptItem.plating_receipt_id == PlatingReceipt.id)
            .filter(PlatingReceiptItem.plating_order_item_id == PlatingOrderItem.id)
        )
        if date_from is not None:
            receipt_subq = receipt_subq.filter(func.date(PlatingReceipt.created_at) >= date_from)
        if date_to is not None:
            receipt_subq = receipt_subq.filter(func.date(PlatingReceipt.created_at) <= date_to)
        q = q.filter(receipt_subq.exists())

    total = q.count()

    # Sort by latest receipt date desc within each partition. Aligns with the
    # date-filter dimension so "more recently returned" sorts to the top.
    # NULLS LAST handles the 100%-loss-no-receipt case (sinks to bottom).
    latest_receipt_at = (
        db.query(func.max(PlatingReceipt.created_at))
        .select_from(PlatingReceiptItem)
        .join(PlatingReceipt, PlatingReceiptItem.plating_receipt_id == PlatingReceipt.id)
        .filter(PlatingReceiptItem.plating_order_item_id == PlatingOrderItem.id)
        .correlate(PlatingOrderItem)
        .scalar_subquery()
    )

    q = q.order_by(
        case((is_completed_expr, 1), else_=0),
        desc(latest_receipt_at).nullslast(),
        desc(PlatingOrderItem.id),
    )

    rows = q.offset(skip).limit(limit).all()

    poi_ids = [poi.id for poi, _ in rows]
    if not poi_ids:
        return [], total

    # Batch-load receipts (newest first per item)
    receipt_rows = (
        db.query(PlatingReceiptItem, PlatingReceipt)
        .join(PlatingReceipt, PlatingReceiptItem.plating_receipt_id == PlatingReceipt.id)
        .filter(PlatingReceiptItem.plating_order_item_id.in_(poi_ids))
        .order_by(desc(PlatingReceipt.created_at), desc(PlatingReceiptItem.id))
        .all()
    )
    receipts_by_poi: dict[int, list[dict]] = {}
    for ri, rcpt in receipt_rows:
        receipts_by_poi.setdefault(ri.plating_order_item_id, []).append({
            "receipt_id": rcpt.id,
            "receipt_item_id": ri.id,
            "receipt_date": _to_beijing_date(rcpt.created_at),
        })

    # Batch-load losses
    loss_rows = (
        db.query(ProductionLoss.item_id, func.sum(ProductionLoss.loss_qty))
        .filter(
            ProductionLoss.order_type == "plating",
            ProductionLoss.item_type == "plating_item",
            ProductionLoss.item_id.in_(poi_ids),
        )
        .group_by(ProductionLoss.item_id)
        .all()
    )
    loss_by_poi = {item_id: float(total_loss) for item_id, total_loss in loss_rows}

    # Batch-load parts
    part_ids = {poi.part_id for poi, _ in rows} | {
        poi.receive_part_id for poi, _ in rows if poi.receive_part_id
    }
    parts = {p.id: p for p in db.query(Part).filter(Part.id.in_(part_ids)).all()} if part_ids else {}

    items = [
        _serialize_received(
            poi, po,
            parts.get(poi.part_id),
            parts.get(poi.receive_part_id) if poi.receive_part_id else None,
            today,
            receipts_by_poi.get(poi.id, []),
            loss_by_poi.get(poi.id, 0.0),
        )
        for poi, po in rows
    ]
    return items, total
