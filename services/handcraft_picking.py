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

from collections import defaultdict
from decimal import Decimal

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

    atom_ids = sorted({atom_id for rows in expanded.values() for atom_id, _ in rows})
    parts_by_id = _load_parts(db, atom_ids + [pi.part_id for pi in part_items])
    stock_by_part = _load_stock(db, atom_ids)
    picked_keys = _load_picked_keys(db, handcraft_order_id)

    groups: list[HandcraftPickingGroup] = []
    total = 0
    picked_count = 0
    for pi in part_items:
        rows: list[HandcraftPickingVariant] = []
        for atom_id, needed_qty in expanded[pi.id]:
            atom_part = parts_by_id[atom_id]
            is_picked = (pi.id, atom_id) in picked_keys
            rows.append(HandcraftPickingVariant(
                part_id=atom_id,
                part_name=atom_part.name,
                part_image=atom_part.image,
                needed_qty=needed_qty,
                suggested_qty=None,  # filled in Task 4
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
) -> dict[int, list[tuple[str, float]]]:
    """For each HandcraftPartItem, return a list of (atom_part_id, needed_qty)
    tuples. Atomic part_items return a single tuple; composite items expand
    via BOM. Multiple paths arriving at the same atom are summed."""
    if not part_items:
        return {}

    parent_part_ids = list({pi.part_id for pi in part_items})
    parent_parts = db.query(Part).filter(Part.id.in_(parent_part_ids)).all()
    is_composite = {p.id: bool(p.is_composite) for p in parent_parts}

    out: dict[int, list[tuple[str, float]]] = {}
    for pi in part_items:
        if is_composite.get(pi.part_id, False):
            from services.picking import _expand_to_atoms

            atoms = _expand_to_atoms(db, pi.part_id, Decimal(str(pi.qty)))
            agg: dict[str, float] = defaultdict(float)
            for atom_id, atom_qty in atoms:
                agg[atom_id] += atom_qty
            out[pi.id] = [(aid, round(q, 4)) for aid, q in agg.items()]
        else:
            out[pi.id] = [(pi.part_id, float(pi.qty))]
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
