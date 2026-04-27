"""Handcraft picking simulation (手工单配货模拟) service.

Aggregates a handcraft order's part items into a picker-friendly grouped
structure: each HandcraftPartItem becomes one group with one or more rows.
Atomic part_items produce a single row; composite part_items expand to
multiple atom rows (via services.picking._expand_to_atoms).

Picked state persists per (handcraft_part_item_id, part_id) in
handcraft_picking_record. This module does NOT touch inventory_log or
order status — purely a UI helper.
"""

from __future__ import annotations

import math
from collections import defaultdict
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
    HandcraftPickingGroup,
    HandcraftPickingProgress,
    HandcraftPickingResponse,
    HandcraftPickingVariant,
)


# --- Suggested qty rule (mirror of frontend HandcraftDetail.computeSuggestedQty) ---

_BUFFER_RULES: dict[str, dict[str, float]] = {
    "small":  {"ratio": 0.02, "floor": 50},
    "medium": {"ratio": 0.01, "floor": 15},
}


def _compute_suggested_qty(theoretical: Optional[float], size_tier: Optional[str]) -> Optional[int]:
    """Apply: suggested = ceil(theoretical) + ceil(max(floor, theoretical * ratio)).
    Returns None when theoretical is missing or non-positive (no suggestion).
    Unknown size_tier falls back to 'small' (matches the frontend default)."""
    if theoretical is None or theoretical <= 0:
        return None
    rule = _BUFFER_RULES.get(size_tier or "small", _BUFFER_RULES["small"])
    # Round to 4 decimals (matches DB Numeric(10,4)) before ceil — same as frontend.
    t = round(theoretical, 4)
    buffer = math.ceil(max(rule["floor"], t * rule["ratio"]))
    return math.ceil(t) + buffer


def get_handcraft_picking_simulation(
    db: Session, handcraft_order_id: str
) -> HandcraftPickingResponse:
    """Aggregate all parts needed for the handcraft order into a picking-oriented
    structure. Raises ValueError if the order does not exist."""
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

    atom_ids = sorted({atom_id for rows in expanded.values() for atom_id, _, _ratio in rows})
    parts_by_id = _load_parts(db, atom_ids + [pi.part_id for pi in part_items])
    stock_by_part = _load_stock(db, atom_ids)
    picked_keys = _load_picked_keys(db, handcraft_order_id)

    groups: list[HandcraftPickingGroup] = []
    total = 0
    picked_count = 0
    for pi in part_items:
        rows: list[HandcraftPickingVariant] = []
        for atom_id, needed_qty, atom_ratio in expanded[pi.id]:
            atom_part = parts_by_id[atom_id]
            is_picked = (pi.id, atom_id) in picked_keys
            theoretical = (
                float(pi.bom_qty) * atom_ratio
                if pi.bom_qty is not None and atom_ratio is not None
                else None
            )
            suggested = _compute_suggested_qty(theoretical, atom_part.size_tier)
            rows.append(HandcraftPickingVariant(
                part_id=atom_id,
                part_name=atom_part.name,
                part_image=atom_part.image,
                needed_qty=needed_qty,
                suggested_qty=suggested,
                current_stock=stock_by_part.get(atom_id, 0.0),
                picked=is_picked,
            ))
            total += 1
            if is_picked:
                picked_count += 1
        parent_part = parts_by_id[pi.part_id]
        groups.append(HandcraftPickingGroup(
            part_item_id=pi.id,
            parent_part_id=pi.part_id,
            parent_part_name=parent_part.name,
            parent_part_image=parent_part.image,
            parent_is_composite=bool(parent_part.is_composite),
            parent_qty=float(pi.qty),
            parent_bom_qty=float(pi.bom_qty) if pi.bom_qty is not None else None,
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
    """For each HandcraftPartItem, return a list of
    (atom_part_id, needed_qty, atom_ratio_per_composite_unit) tuples.

    - Atomic part_items: (part_id, qty, 1.0). atom_ratio=1.0 means
      theoretical_for_atom = parent.bom_qty × 1.0 = parent.bom_qty.
    - Composite items: each expanded atom carries its BOM ratio
      (atom_qty_per_composite_unit). theoretical_for_atom = parent.bom_qty × ratio.
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


def _load_stock(db: Session, part_ids: list[str]) -> dict[str, float]:
    if not part_ids:
        return {}
    rows = (
        db.query(InventoryLog.item_id,
                 func.coalesce(func.sum(InventoryLog.change_qty), 0))
        .filter(InventoryLog.item_type == "part",
                InventoryLog.item_id.in_(part_ids))
        .group_by(InventoryLog.item_id)
        .all()
    )
    return {pid: float(q) for pid, q in rows}


def _load_picked_keys(
    db: Session, handcraft_order_id: str
) -> set[tuple[int, str]]:
    rows = (
        db.query(HandcraftPickingRecord)
        .filter(HandcraftPickingRecord.handcraft_order_id == handcraft_order_id)
        .all()
    )
    return {(r.handcraft_part_item_id, r.part_id) for r in rows}
