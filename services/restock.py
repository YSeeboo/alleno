"""Restock request service. A pure 'todo list' for parts that need to be
restocked, scoped per handcraft order. No coupling to inventory_log or
purchase orders."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.handcraft_order import HandcraftOrder, HandcraftPartItem
from models.inventory_log import InventoryLog
from models.part import Part
from models.restock_request import RestockRequest
from time_utils import now_beijing


def _qty_by_pair(
    db: Session, pairs: set[tuple[str, str]]
) -> dict[tuple[str, str], float]:
    """For each (handcraft_order_id, part_id) pair, sum the qty across all
    matching rows in handcraft_part_item. Used to surface the requested
    quantity on restock list views. Pairs with no matching part_item are
    simply absent from the result (caller treats as None)."""
    if not pairs:
        return {}
    rows = (
        db.query(
            HandcraftPartItem.handcraft_order_id,
            HandcraftPartItem.part_id,
            func.sum(HandcraftPartItem.qty),
        )
        .filter(
            tuple_(HandcraftPartItem.handcraft_order_id, HandcraftPartItem.part_id).in_(pairs)
        )
        .group_by(HandcraftPartItem.handcraft_order_id, HandcraftPartItem.part_id)
        .all()
    )
    return {(hc, pid): float(q) for hc, pid, q in rows}


def _get_existing(db: Session, part_id: str, handcraft_order_id: Optional[str]) -> Optional[RestockRequest]:
    return (
        db.query(RestockRequest)
        .filter_by(part_id=part_id, handcraft_order_id=handcraft_order_id)
        .one_or_none()
    )


def _validate_part(db: Session, part_id: str) -> None:
    if db.get(Part, part_id) is None:
        raise ValueError("配件不存在")


def _validate_handcraft(db: Session, hc_id: Optional[str]) -> None:
    if hc_id is None:
        return
    if db.get(HandcraftOrder, hc_id) is None:
        raise ValueError("手工单不存在")


def _create(db: Session, *, part_id: str, handcraft_order_id: Optional[str], source: str, note: Optional[str]) -> RestockRequest:
    _validate_part(db, part_id)
    _validate_handcraft(db, handcraft_order_id)

    existing = _get_existing(db, part_id, handcraft_order_id)
    if existing is not None:
        if existing.status == "done":
            raise ValueError("该配件已为此手工单补过货")
        return existing

    rec = RestockRequest(
        part_id=part_id,
        handcraft_order_id=handcraft_order_id,
        source=source,
        status="pending",
        note=note,
    )
    try:
        with db.begin_nested():
            db.add(rec)
            db.flush()
    except IntegrityError:
        existing = _get_existing(db, part_id, handcraft_order_id)
        if existing is None:
            raise
        if existing.status == "done":
            raise ValueError("该配件已为此手工单补过货")
        return existing
    return rec


def create_from_picking(db: Session, part_id: str, handcraft_order_id: str) -> RestockRequest:
    """Add a restock request from the picking modal. Idempotent: re-adding
    an already-pending pair returns the existing record. Already-done pair
    raises ValueError."""
    return _create(db, part_id=part_id, handcraft_order_id=handcraft_order_id,
                   source="picking", note=None)


def create_manual(db: Session, part_id: str, handcraft_order_id: str, note: Optional[str] = None) -> RestockRequest:
    """Add a manually-typed restock request (from the handcraft detail page).
    Idempotent like create_from_picking. Note is preserved on insert; for an
    already-pending pair the existing note is NOT overwritten."""
    return _create(db, part_id=part_id, handcraft_order_id=handcraft_order_id,
                   source="manual", note=note)


def mark_done(db: Session, request_id: int) -> RestockRequest:
    """pending -> done. Raises ValueError if record does not exist or
    is already done. Single-direction transition."""
    rec = db.get(RestockRequest, request_id)
    if rec is None:
        raise ValueError("补货记录不存在")
    if rec.status == "done":
        raise ValueError("补货记录已完成，不可重置")
    rec.status = "done"
    rec.completed_at = now_beijing()
    db.flush()
    return rec


def mark_part_done(db: Session, part_id: str) -> int:
    """Bulk-transition all pending restock requests for `part_id` to done.
    Returns the number of rows updated. No-op if no pending exists."""
    now = now_beijing()
    count = (
        db.query(RestockRequest)
        .filter(RestockRequest.part_id == part_id, RestockRequest.status == "pending")
        .update({"status": "done", "completed_at": now}, synchronize_session=False)
    )
    db.flush()
    return count


def update_shortfall(
    db: Session, request_id: int, shortfall_qty: Optional[float]
) -> RestockRequest:
    """Set or clear the user-entered shortfall on a pending restock record.
    Pass None to clear. Done records reject updates (they're locked history)."""
    rec = db.get(RestockRequest, request_id)
    if rec is None:
        raise ValueError("补货记录不存在")
    if rec.status == "done":
        raise ValueError("已补货的记录不可修改差额")
    rec.shortfall_qty = shortfall_qty
    db.flush()
    return rec


def delete_pending(db: Session, request_id: int) -> None:
    """Cancel a pending restock request. Done records cannot be deleted
    via this path (they are kept as history). Raises ValueError otherwise."""
    rec = db.get(RestockRequest, request_id)
    if rec is None:
        raise ValueError("补货记录不存在")
    if rec.status == "done":
        raise ValueError("已补货的记录不可删除")
    db.delete(rec)
    db.flush()


def list_for_handcraft(db: Session, handcraft_order_id: str) -> list[RestockRequest]:
    """All restock requests (pending + done) for a single handcraft order,
    newest first."""
    return (
        db.query(RestockRequest)
        .filter_by(handcraft_order_id=handcraft_order_id)
        .order_by(RestockRequest.created_at.desc(), RestockRequest.id.desc())
        .all()
    )


def list_pending_summary(db: Session) -> list[dict]:
    """Aggregate pending restock requests by part. Each row carries
    the part metadata, current stock, source handcraft orders, and count."""
    rows = (
        db.query(
            RestockRequest.id,
            RestockRequest.part_id,
            RestockRequest.handcraft_order_id,
            RestockRequest.created_at,
            Part.name,
            Part.image,
            HandcraftOrder.supplier_name,
        )
        .join(Part, Part.id == RestockRequest.part_id)
        .outerjoin(HandcraftOrder, HandcraftOrder.id == RestockRequest.handcraft_order_id)
        .filter(RestockRequest.status == "pending")
        .order_by(RestockRequest.created_at.asc())
        .all()
    )
    if not rows:
        return []

    part_ids = list({r.part_id for r in rows})
    stock_rows = (
        db.query(InventoryLog.item_id, func.coalesce(func.sum(InventoryLog.change_qty), 0))
        .filter(InventoryLog.item_type == "part", InventoryLog.item_id.in_(part_ids))
        .group_by(InventoryLog.item_id)
        .all()
    )
    stock_by_part = {pid: float(qty) for pid, qty in stock_rows}

    qty_by_pair = _qty_by_pair(
        db, {(r.handcraft_order_id, r.part_id) for r in rows if r.handcraft_order_id}
    )

    # by_part preserves insertion order, which matches `rows` ordering
    # (created_at asc) — earliest-marked parts surface first.
    by_part: dict[str, dict] = {}
    for r in rows:
        bucket = by_part.setdefault(r.part_id, {
            "part_id": r.part_id,
            "part_name": r.name,
            "part_image": r.image,
            "current_stock": stock_by_part.get(r.part_id, 0.0),
            "sources": [],
        })
        bucket["sources"].append({
            "request_id": r.id,
            "handcraft_order_id": r.handcraft_order_id,
            "supplier_name": r.supplier_name or "",
            "created_at": r.created_at,
            "qty": qty_by_pair.get((r.handcraft_order_id, r.part_id)),
        })

    out = []
    for bucket in by_part.values():
        bucket["source_count"] = len(bucket["sources"])
        qtys = [s["qty"] for s in bucket["sources"] if s["qty"] is not None]
        bucket["total_qty"] = sum(qtys) if qtys else None
        out.append(bucket)
    return out


def list_history(
    db: Session,
    part_id: Optional[str] = None,
    handcraft_order_id: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """List done restock requests, newest completion first. Optional filters
    by part / handcraft order. limit caps result size."""
    q = (
        db.query(
            RestockRequest.id,
            RestockRequest.part_id,
            RestockRequest.handcraft_order_id,
            RestockRequest.source,
            RestockRequest.note,
            RestockRequest.created_at,
            RestockRequest.completed_at,
            Part.name.label("part_name"),
            HandcraftOrder.supplier_name,
        )
        .join(Part, Part.id == RestockRequest.part_id)
        .outerjoin(HandcraftOrder, HandcraftOrder.id == RestockRequest.handcraft_order_id)
        .filter(RestockRequest.status == "done")
    )
    if part_id:
        q = q.filter(RestockRequest.part_id == part_id)
    if handcraft_order_id:
        q = q.filter(RestockRequest.handcraft_order_id == handcraft_order_id)
    q = q.order_by(RestockRequest.completed_at.desc(), RestockRequest.id.desc()).limit(limit)

    history_rows = q.all()
    qty_by_pair = _qty_by_pair(
        db, {(r.handcraft_order_id, r.part_id) for r in history_rows if r.handcraft_order_id}
    )

    return [
        {
            "id": r.id,
            "part_id": r.part_id,
            "part_name": r.part_name,
            "handcraft_order_id": r.handcraft_order_id,
            "supplier_name": r.supplier_name,
            "source": r.source,
            "qty": qty_by_pair.get((r.handcraft_order_id, r.part_id)),
            "note": r.note,
            "created_at": r.created_at,
            "completed_at": r.completed_at,
        }
        for r in history_rows
    ]
