"""Restock request service. A pure 'todo list' for parts that need to be
restocked, scoped per handcraft order. No coupling to inventory_log or
purchase orders."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.handcraft_order import HandcraftOrder
from models.part import Part
from models.restock_request import RestockRequest


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
