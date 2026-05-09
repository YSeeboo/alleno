"""Picking weight (per atom) service.

Stores actual measured weights per (handcraft_part_item × atom_part_id),
which is the granularity exposed in the picking simulation. Atomic part_items
have one row; composite part_items can have multiple atom rows after expansion.

This module does NOT touch inventory_log. Weights are reference data for
records-keeping (UI, PDF, possibly later cost calculation).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from models.handcraft_order import (
    HandcraftPartItem,
    HandcraftPickingWeight,
)
from models.part import Part


_UNIT_TO_KG = {"kg": Decimal("1"), "g": Decimal("0.001")}


def _validate_part_item_in_order(db: Session, order_id: str, part_item_id: int) -> HandcraftPartItem:
    pi = db.query(HandcraftPartItem).filter_by(id=part_item_id).one_or_none()
    if pi is None or pi.handcraft_order_id != order_id:
        raise ValueError(f"part_item {part_item_id} 不属于手工单 {order_id}")
    return pi


def _validate_atom_part_id(db: Session, atom_part_id: str) -> None:
    if db.query(Part).filter_by(id=atom_part_id).count() == 0:
        raise ValueError(f"配件 {atom_part_id} 不存在")


def upsert_weight(
    db: Session,
    order_id: str,
    part_item_id: int,
    atom_part_id: str,
    weight: float,
    weight_unit: str = "kg",
) -> HandcraftPickingWeight:
    """Insert or update the (part_item, atom_part) weight record.

    Raises ValueError if part_item is not in the order or atom_part_id does
    not exist. Caller (API layer) must check order status separately.
    """
    _validate_part_item_in_order(db, order_id, part_item_id)
    _validate_atom_part_id(db, atom_part_id)
    if weight_unit not in _UNIT_TO_KG:
        raise ValueError(f"unsupported weight_unit: {weight_unit}")

    row = (
        db.query(HandcraftPickingWeight)
        .filter_by(part_item_id=part_item_id, atom_part_id=atom_part_id)
        .one_or_none()
    )
    weight_dec = Decimal(str(weight)).quantize(Decimal("0.0001"))
    if row is None:
        row = HandcraftPickingWeight(
            handcraft_order_id=order_id,
            part_item_id=part_item_id,
            atom_part_id=atom_part_id,
            weight=weight_dec,
            weight_unit=weight_unit,
        )
        db.add(row)
    else:
        row.weight = weight_dec
        row.weight_unit = weight_unit
    db.flush()
    return row


def delete_weight(db: Session, order_id: str, part_item_id: int, atom_part_id: str) -> bool:
    """Clear the weight fields on a (part_item, atom_part) row.
    If actual_qty is also null after clearing, the whole row is removed.
    Otherwise the row stays so actual_qty is preserved.
    Returns True if the row existed (whether removed or just cleared)."""
    _validate_part_item_in_order(db, order_id, part_item_id)
    row = (
        db.query(HandcraftPickingWeight)
        .filter_by(part_item_id=part_item_id, atom_part_id=atom_part_id)
        .one_or_none()
    )
    if row is None:
        return False
    if row.actual_qty is None:
        db.delete(row)
    else:
        row.weight = None
        row.weight_unit = None
    db.flush()
    return True


def bulk_load_for_picking(
    db: Session, order_id: str
) -> dict[tuple[int, str], HandcraftPickingWeight]:
    """Load all weight rows for a handcraft order, keyed by (part_item_id, atom_part_id).
    Used by the picking simulation service to populate weights in one query."""
    rows = (
        db.query(HandcraftPickingWeight)
        .filter_by(handcraft_order_id=order_id)
        .all()
    )
    return {(r.part_item_id, r.atom_part_id): r for r in rows}


def sum_weight_by_part_item(
    db: Session, part_item_id: int, target_unit: str = "kg"
) -> Optional[float]:
    """SUM all atom weights for a part_item, normalized to target_unit.

    Returns None if no weight rows exist (so the caller can show '—' instead
    of '0'). target_unit defaults to 'kg' to match the picking sim default.
    """
    if target_unit not in _UNIT_TO_KG:
        raise ValueError(f"unsupported target_unit: {target_unit}")
    rows = (
        db.query(HandcraftPickingWeight)
        .filter_by(part_item_id=part_item_id)
        .all()
    )
    if not rows:
        return None
    target_factor = _UNIT_TO_KG[target_unit]
    total_kg = sum(
        Decimal(str(r.weight)) * _UNIT_TO_KG[r.weight_unit]
        for r in rows
    )
    return float(total_kg / target_factor)
