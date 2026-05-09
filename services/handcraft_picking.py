"""Handcraft picking simulation (手工单配货模拟) service.

Aggregates a handcraft order's part items into a picker-friendly grouped
structure: each ATOMIC PART_ID becomes one group with one or more rows.
Atomic part_items contribute one row; composite part_items expand to multiple
rows that land in different atom groups.

Picked state persists per (handcraft_part_item_id, atom_part_id) in
handcraft_picking_record. Per-atom weight persists in
handcraft_picking_weight. This module does NOT touch inventory_log or
order status — purely a UI helper.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.handcraft_order import (
    HandcraftOrder,
    HandcraftPartItem,
    HandcraftPickingRecord,
)
from models.inventory_log import InventoryLog
from models.part import Part
from schemas.handcraft import (
    HandcraftPickingProgress,
    HandcraftPickingResponse,
    PickingGroup,
    PickingSourceRow,
)
from services.handcraft import compute_suggested_qty
from services.handcraft_picking_weight import bulk_load_for_picking


def _compute_suggested_qty(theoretical: Optional[float], part: Optional[Part]) -> Optional[int]:
    """Picking-side adapter: convert float theoretical → quantized Decimal,
    then delegate to services.handcraft.compute_suggested_qty so override
    fields and Decimal precision are respected (a single source of truth
    for the buffer rule across suggest-parts and picking).

    Returns None when theoretical is missing/non-positive or part is missing.
    """
    if theoretical is None or theoretical <= 0 or part is None:
        return None
    # Quantize to 4 decimals (matches DB Numeric(10,4)) via str() to avoid
    # carrying float IEEE 754 noise into the Decimal computation.
    theo = Decimal(str(theoretical)).quantize(Decimal("0.0001"))
    if theo <= 0:
        return None
    return compute_suggested_qty(part, theo)


def get_handcraft_picking_simulation(
    db: Session, handcraft_order_id: str
) -> HandcraftPickingResponse:
    """Aggregate all parts needed for the handcraft order into a picking-oriented
    structure grouped by atom_part_id. Raises ValueError if the order does not exist."""
    order = db.query(HandcraftOrder).filter_by(id=handcraft_order_id).one_or_none()
    if order is None:
        raise ValueError(f"手工单 {handcraft_order_id} 不存在")

    part_items = (
        db.query(HandcraftPartItem)
        .filter_by(handcraft_order_id=handcraft_order_id)
        .order_by(HandcraftPartItem.id.asc())
        .all()
    )
    if not part_items:
        return HandcraftPickingResponse(
            handcraft_order_id=order.id,
            supplier_name=order.supplier_name,
            status=order.status,
            groups=[],
            progress=HandcraftPickingProgress(total=0, picked=0),
        )

    expanded = _expand_part_items(db, part_items)

    atom_ids = sorted({atom_id for rows in expanded.values() for atom_id, _, _ in rows})
    parent_part_ids = list({pi.part_id for pi in part_items})
    parts_by_id = _load_parts(db, atom_ids + parent_part_ids)
    stock_by_part = _load_stock(db, atom_ids)
    picked_keys = _load_picked_keys(db, handcraft_order_id)
    weights_by_key = bulk_load_for_picking(db, handcraft_order_id)

    atom_first_seen: dict[str, int] = {}
    rows_by_atom: dict[str, list[PickingSourceRow]] = defaultdict(list)
    total = 0
    picked_count = 0
    for pi in part_items:
        parent_part = parts_by_id.get(pi.part_id)
        is_composite = bool(parent_part and parent_part.is_composite)
        for atom_id, qty_for_row, atom_ratio in expanded[pi.id]:
            atom_part = parts_by_id[atom_id]
            ratio = atom_ratio if atom_ratio is not None else 1.0
            bom_qty_for_row = (
                float(pi.bom_qty) * ratio if pi.bom_qty is not None else None
            )
            needed_qty = bom_qty_for_row if bom_qty_for_row is not None else qty_for_row
            suggested = _compute_suggested_qty(needed_qty, atom_part)
            is_picked = (pi.id, atom_id) in picked_keys
            weight_row = weights_by_key.get((pi.id, atom_id))
            row = PickingSourceRow(
                part_item_id=pi.id,
                atom_part_id=atom_id,
                qty=qty_for_row,
                bom_qty=bom_qty_for_row,
                is_composite_expansion=is_composite,
                parent_composite_name=(parent_part.name if (is_composite and parent_part) else None),
                needed_qty=needed_qty,
                suggested_qty=suggested,
                weight=(float(weight_row.weight) if weight_row and weight_row.weight is not None else None),
                weight_unit=(weight_row.weight_unit if weight_row and weight_row.weight is not None else None),
                actual_qty=(float(weight_row.actual_qty) if weight_row and weight_row.actual_qty is not None else None),
                picked=is_picked,
            )
            rows_by_atom[atom_id].append(row)
            atom_first_seen.setdefault(atom_id, pi.id)
            total += 1
            if is_picked:
                picked_count += 1

    ordered_atom_ids = sorted(rows_by_atom.keys(), key=lambda a: atom_first_seen[a])
    groups: list[PickingGroup] = []
    for atom_id in ordered_atom_ids:
        atom_part = parts_by_id[atom_id]
        rows = rows_by_atom[atom_id]
        groups.append(PickingGroup(
            atom_part_id=atom_id,
            atom_part_name=atom_part.name,
            atom_part_image=atom_part.image,
            size_tier=atom_part.size_tier or "small",
            current_stock=stock_by_part.get(atom_id, 0.0),
            total_needed_qty=sum(
                (r.actual_qty if r.actual_qty is not None else r.needed_qty)
                for r in rows
            ),
            total_suggested_qty=sum((r.suggested_qty or 0) for r in rows),
            rows=rows,
        ))

    return HandcraftPickingResponse(
        handcraft_order_id=order.id,
        supplier_name=order.supplier_name,
        status=order.status,
        groups=groups,
        progress=HandcraftPickingProgress(total=total, picked=picked_count),
    )


def _expand_part_items(
    db: Session, part_items: list[HandcraftPartItem]
) -> dict[int, list[tuple[str, float, Optional[float]]]]:
    """For each HandcraftPartItem, return list of (atom_part_id, needed_qty, atom_ratio).

    - Atomic part_items: (part_id, pi.qty, 1.0). atom_ratio=1.0 means
      theoretical_for_atom = parent.bom_qty × 1.0 = parent.bom_qty.
    - Composite items: each expanded atom carries its BOM ratio
      (atom_qty_per_composite_unit). needed_qty = pi.qty × ratio.
    """
    if not part_items:
        return {}

    parent_part_ids = list({pi.part_id for pi in part_items})
    parent_parts = db.query(Part).filter(Part.id.in_(parent_part_ids)).all()
    is_composite = {p.id: bool(p.is_composite) for p in parent_parts}

    out: dict[int, list[tuple[str, float, Optional[float]]]] = {}
    for pi in part_items:
        if is_composite.get(pi.part_id, False):
            from services.picking import _expand_to_atoms
            # Get per-unit ratios first, then scale by pi.qty for needed_qty.
            # Two-pass keeps the math clear.
            atoms_per_unit = _expand_to_atoms(db, pi.part_id, Decimal("1.0"))
            agg_ratio: dict[str, float] = defaultdict(float)
            for atom_id, ratio in atoms_per_unit:
                agg_ratio[atom_id] += ratio
            qty = float(pi.qty)
            out[pi.id] = [
                (aid, round(r * qty, 4), round(r, 4))
                for aid, r in agg_ratio.items()
            ]
        else:
            out[pi.id] = [(pi.part_id, float(pi.qty), 1.0)]
    return out


def _load_parts(db: Session, part_ids: list[str]) -> dict[str, Part]:
    if not part_ids:
        return {}
    rows = db.query(Part).filter(Part.id.in_(set(part_ids))).all()
    return {p.id: p for p in rows}


def _load_stock(db: Session, atom_ids: list[str]) -> dict[str, float]:
    if not atom_ids:
        return {}
    rows = (
        db.query(InventoryLog.item_id,
                 func.coalesce(func.sum(InventoryLog.change_qty), 0))
        .filter(InventoryLog.item_type == "part",
                InventoryLog.item_id.in_(set(atom_ids)))
        .group_by(InventoryLog.item_id)
        .all()
    )
    return {pid: float(q) for pid, q in rows}


def _load_picked_keys(
    db: Session, handcraft_order_id: str
) -> set[tuple[int, str]]:
    """Existing PickingRecord uses `part_id` column (atom's id)."""
    rows = (
        db.query(HandcraftPickingRecord.handcraft_part_item_id, HandcraftPickingRecord.part_id)
        .filter_by(handcraft_order_id=handcraft_order_id)
        .all()
    )
    return {(pi_id, atom_id) for pi_id, atom_id in rows}


# --- State mutations ---


@dataclass
class HandcraftPickingMarkResult:
    picked: bool
    picked_at: Optional[datetime] = None


def _check_writable(order: HandcraftOrder) -> None:
    if order.status != "pending":
        raise ValueError("手工单已发出，配货模拟为只读")


def _validate_pair_in_order(
    db: Session, handcraft_order_id: str, part_item_id: int, part_id: str
) -> HandcraftOrder:
    """Verify the (part_item_id, part_id) pair is part of this handcraft order's
    picking aggregation. Returns the order for caller to use. Does NOT check
    writable status — that's a separate gate."""
    order = (
        db.query(HandcraftOrder)
        .filter_by(id=handcraft_order_id)
        .one_or_none()
    )
    if order is None:
        raise ValueError(f"手工单 {handcraft_order_id} 不存在")

    part_item = (
        db.query(HandcraftPartItem)
        .filter_by(id=part_item_id, handcraft_order_id=handcraft_order_id)
        .one_or_none()
    )
    if part_item is None:
        raise ValueError("该配件/变体不在此手工单配货范围内")

    expanded = _expand_part_items(db, [part_item])
    valid_atoms = {atom_id for atom_id, _, _ in expanded[part_item.id]}
    if part_id not in valid_atoms:
        raise ValueError("该配件/变体不在此手工单配货范围内")

    return order


def mark_picked(
    db: Session, handcraft_order_id: str, part_item_id: int, part_id: str
) -> HandcraftPickingMarkResult:
    """Mark a (part_item, atom) pair as picked. Idempotent."""
    order = _validate_pair_in_order(db, handcraft_order_id, part_item_id, part_id)
    _check_writable(order)

    existing = (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_part_item_id=part_item_id, part_id=part_id)
        .one_or_none()
    )
    if existing is not None:
        return HandcraftPickingMarkResult(picked=True, picked_at=existing.picked_at)

    # Note: under concurrent requests, two racing marks could both pass the
    # existing check and both INSERT. The unique constraint on
    # (handcraft_part_item_id, part_id) catches this at commit time (one
    # succeeds, the other raises IntegrityError). For this feature's
    # single-user intent that is acceptable; upgrade to INSERT ... ON CONFLICT
    # if multi-writer support is needed. Mirrors services/picking.mark_picked.
    rec = HandcraftPickingRecord(
        handcraft_order_id=handcraft_order_id,
        handcraft_part_item_id=part_item_id,
        part_id=part_id,
    )
    db.add(rec)
    db.flush()
    return HandcraftPickingMarkResult(picked=True, picked_at=rec.picked_at)


def unmark_picked(
    db: Session, handcraft_order_id: str, part_item_id: int, part_id: str
) -> HandcraftPickingMarkResult:
    """Unmark a (part_item, atom) pair. Idempotent — silent if no record exists.
    Validates that the order exists and is writable, but does NOT validate that
    the pair is still in the aggregation (allows cleanup of stale records)."""
    order = (
        db.query(HandcraftOrder)
        .filter_by(id=handcraft_order_id)
        .one_or_none()
    )
    if order is None:
        raise ValueError(f"手工单 {handcraft_order_id} 不存在")
    _check_writable(order)

    (
        db.query(HandcraftPickingRecord)
        .filter_by(
            handcraft_order_id=handcraft_order_id,
            handcraft_part_item_id=part_item_id,
            part_id=part_id,
        )
        .delete(synchronize_session=False)
    )
    db.flush()
    return HandcraftPickingMarkResult(picked=False)


def reset_picking(db: Session, handcraft_order_id: str) -> int:
    """Delete all picking records for the order. Returns delete count.
    Raises ValueError if order does not exist or is not writable."""
    order = (
        db.query(HandcraftOrder)
        .filter_by(id=handcraft_order_id)
        .one_or_none()
    )
    if order is None:
        raise ValueError(f"手工单 {handcraft_order_id} 不存在")
    _check_writable(order)

    deleted = (
        db.query(HandcraftPickingRecord)
        .filter_by(handcraft_order_id=handcraft_order_id)
        .delete(synchronize_session=False)
    )
    db.flush()
    return deleted
