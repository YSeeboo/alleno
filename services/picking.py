"""Picking simulation (配货模拟) service.

Aggregates an order's parts into a picker-friendly structure: each part may
have multiple variants distinguished by qty_per_unit. Composite parts are
expanded to atomic children. Picked state is persisted per
(order, part, qty_per_unit) in the order_picking_record table.

This module covers:
- Read: get_picking_simulation() aggregates BOMs, joins current_stock from
  inventory_log, and joins picked state from order_picking_record.
- Mutate: mark_picked / unmark_picked / reset_picking toggle picked state.
  These do NOT touch inventory_log or order status — they are UI helpers.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import NamedTuple, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.bom import Bom
from models.inventory_log import InventoryLog
from models.order import Order, OrderItem, OrderPickingRecord
from models.part import Part
from schemas.order import (
    PickingPartRow,
    PickingProgress,
    PickingSimulationResponse,
    PickingVariant,
)


class _Triple(NamedTuple):
    """Internal representation of one BOM expansion: a single contribution to
    one (part, qty_per_unit) combination from one order item."""
    part_id: str
    qty_per_unit: float
    units_count: int
    from_composite: bool = False


def get_picking_simulation(db: Session, order_id: str) -> PickingSimulationResponse:
    """Aggregate all parts needed for `order_id` into a picking-oriented
    structure. Raises ValueError if the order does not exist."""
    order = db.query(Order).filter_by(id=order_id).one_or_none()
    if order is None:
        raise ValueError(f"订单 {order_id} 不存在")

    order_items = db.query(OrderItem).filter_by(order_id=order_id).all()
    if not order_items:
        return PickingSimulationResponse(
            order_id=order.id,
            customer_name=order.customer_name,
            rows=[],
            progress=PickingProgress(total=0, picked=0),
        )

    # Step 1: collect (part_id, qty_per_unit, units_count, from_composite) triples.
    triples = _collect_triples(db, order_items)

    # Step 2: aggregate into parts → variants.
    rows = _build_rows(db, triples, order.id)

    # Compute progress counts.
    total_variants = sum(len(r.variants) for r in rows)
    picked_count = sum(1 for r in rows for v in r.variants if v.picked)

    return PickingSimulationResponse(
        order_id=order.id,
        customer_name=order.customer_name,
        rows=rows,
        progress=PickingProgress(total=total_variants, picked=picked_count),
    )


def _expand_to_atoms(
    db: Session,
    composite_part_id: str,
    multiplier: Decimal,
    _ancestors: frozenset[str] = frozenset(),
) -> list[tuple[str, float]]:
    """Recursively walk a composite part's BOM. Return a list of
    (atom_part_id, effective_qty_per_unit) tuples for every non-composite
    descendant. `multiplier` is a Decimal running product of qty_per_unit
    along the path from the jewelry BOM root — kept as Decimal throughout
    recursion to avoid cumulative rounding errors. Only leaf nodes are
    quantized to 4 decimal places (matching the DB column precision).

    Uses `services.part_bom.get_part_bom()` just like
    `services.cutting_stats._expand_composite_part` does, but does NOT
    filter by name pattern — we want ALL atoms. _ancestors guards against
    cycles, matching the existing helper's semantics."""
    from services.part_bom import get_part_bom

    if composite_part_id in _ancestors:
        return []
    path = _ancestors | {composite_part_id}

    children = get_part_bom(db, composite_part_id)
    out: list[tuple[str, float]] = []
    for child in children:
        child_id = child["child_part_id"]
        child_qty = multiplier * Decimal(str(child["qty_per_unit"]))
        if child.get("child_is_composite"):
            out.extend(_expand_to_atoms(db, child_id, child_qty, path))
        else:
            out.append((child_id, float(round(child_qty, 4))))
    return out


def _collect_triples(db: Session, order_items: list[OrderItem]) -> list[_Triple]:
    """Return list of _Triple. Composite parts in a jewelry's BOM are expanded;
    direct part purchases are added as a single triple per part item with
    qty_per_unit=quantity, units_count=1, from_composite=False."""
    jewelry_items = [oi for oi in order_items if oi.jewelry_id is not None]
    part_items = [oi for oi in order_items if oi.part_id is not None]

    out: list[_Triple] = []

    # Direct part purchases — one variant per item
    for oi in part_items:
        out.append(_Triple(
            part_id=oi.part_id,
            qty_per_unit=float(oi.quantity),
            units_count=1,
            from_composite=False,
        ))

    if not jewelry_items:
        return out

    jewelry_ids = list({oi.jewelry_id for oi in jewelry_items})
    boms = db.query(Bom).filter(Bom.jewelry_id.in_(jewelry_ids)).all()
    bom_by_jewelry: dict[str, list[Bom]] = defaultdict(list)
    for b in boms:
        bom_by_jewelry[b.jewelry_id].append(b)

    direct_part_ids = list({b.part_id for bs in bom_by_jewelry.values() for b in bs})
    direct_parts = db.query(Part).filter(Part.id.in_(direct_part_ids)).all() if direct_part_ids else []
    is_composite = {p.id: p.is_composite for p in direct_parts}

    for oi in jewelry_items:
        for b in bom_by_jewelry.get(oi.jewelry_id, []):
            qpu_root = float(b.qty_per_unit)
            if is_composite.get(b.part_id):
                atoms = _expand_to_atoms(db, b.part_id, Decimal(str(b.qty_per_unit)))
                for atom_id, atom_qpu in atoms:
                    out.append(_Triple(
                        part_id=atom_id,
                        qty_per_unit=atom_qpu,
                        units_count=oi.quantity,
                        from_composite=True,
                    ))
            else:
                out.append(_Triple(
                    part_id=b.part_id,
                    qty_per_unit=qpu_root,
                    units_count=oi.quantity,
                    from_composite=False,
                ))
    return out


def _build_rows(db: Session, triples: list[_Triple], order_id: str) -> list[PickingPartRow]:
    """Group triples by (part_id, qty_per_unit) → variants, then by part_id.
    Attach current_stock (from inventory_log) and picked (from
    order_picking_record)."""
    if not triples:
        return []

    grouped: dict[tuple[str, float], dict] = {}
    for t in triples:
        key = (t.part_id, t.qty_per_unit)
        entry = grouped.get(key)
        if entry is None:
            grouped[key] = {"units_count": 0, "from_composite": False}
            entry = grouped[key]
        entry["units_count"] += t.units_count
        if t.from_composite:
            entry["from_composite"] = True

    part_ids = sorted({k[0] for k in grouped.keys()})
    parts = db.query(Part).filter(Part.id.in_(part_ids)).all()
    part_by_id = {p.id: p for p in parts}

    # Batch-load current_stock per part.
    stock_rows = (
        db.query(InventoryLog.item_id,
                 func.coalesce(func.sum(InventoryLog.change_qty), 0))
        .filter(InventoryLog.item_type == "part",
                InventoryLog.item_id.in_(part_ids))
        .group_by(InventoryLog.item_id)
        .all()
    )
    stock_by_part: dict[str, float] = {pid: float(q) for pid, q in stock_rows}

    # Batch-load picked records for this order, keyed by (part_id, qty_per_unit).
    picked_records = (
        db.query(OrderPickingRecord)
        .filter(OrderPickingRecord.order_id == order_id,
                OrderPickingRecord.part_id.in_(part_ids))
        .all()
    )
    picked_keys = {(r.part_id, float(r.qty_per_unit)) for r in picked_records}

    variants_by_part: dict[str, list[PickingVariant]] = defaultdict(list)
    composite_pids: set[str] = set()
    for (pid, qpu), entry in grouped.items():
        units = entry["units_count"]
        variants_by_part[pid].append(
            PickingVariant(
                qty_per_unit=qpu,
                units_count=units,
                subtotal=round(qpu * units, 10),
                picked=(pid, qpu) in picked_keys,
            )
        )
        if entry["from_composite"]:
            composite_pids.add(pid)

    rows: list[PickingPartRow] = []
    for pid in part_ids:
        part = part_by_id[pid]  # FK guarantees presence
        variants = sorted(variants_by_part[pid], key=lambda v: v.qty_per_unit)
        total_required = round(sum(v.subtotal for v in variants), 10)
        rows.append(
            PickingPartRow(
                part_id=pid,
                part_name=part.name,
                part_image=part.image,
                current_stock=stock_by_part.get(pid, 0.0),
                is_composite_child=(pid in composite_pids),
                variants=variants,
                total_required=total_required,
            )
        )
    return rows


# --- State mutations ---


@dataclass
class PickingMarkResult:
    picked: bool
    picked_at: Optional[datetime] = None


def _validate_variant_in_order(
    db: Session, order_id: str, part_id: str, qty_per_unit: float
) -> None:
    """Raise ValueError unless (part_id, qty_per_unit) is a valid variant of
    the order's picking aggregation. Does the minimum work needed: loads the
    order, its items, and BOM triples (including composite expansion) — skips
    stock and picked joins which get_picking_simulation would do."""
    order = db.query(Order).filter_by(id=order_id).one_or_none()
    if order is None:
        raise ValueError(f"订单 {order_id} 不存在")

    order_items = db.query(OrderItem).filter_by(order_id=order_id).all()
    if not order_items:
        raise ValueError("该配件/变体不在此订单配货范围内")

    triples = _collect_triples(db, order_items)
    valid = {(t.part_id, t.qty_per_unit) for t in triples}
    if (part_id, qty_per_unit) not in valid:
        raise ValueError("该配件/变体不在此订单配货范围内")


def mark_picked(
    db: Session, order_id: str, part_id: str, qty_per_unit: float
) -> PickingMarkResult:
    """Mark a variant as picked. Idempotent — calling twice produces one row."""
    _validate_variant_in_order(db, order_id, part_id, qty_per_unit)

    existing = (
        db.query(OrderPickingRecord)
        .filter_by(order_id=order_id, part_id=part_id,
                   qty_per_unit=Decimal(str(qty_per_unit)))
        .one_or_none()
    )
    if existing is not None:
        return PickingMarkResult(picked=True, picked_at=existing.picked_at)

    # Note: under concurrent requests, two racing marks could both pass the
    # existing check and both INSERT. The unique constraint catches this at
    # commit time (one succeeds, the other raises IntegrityError). For the
    # feature's single-user intent this is acceptable; upgrade to
    # INSERT ... ON CONFLICT if multi-writer support is needed.
    rec = OrderPickingRecord(
        order_id=order_id,
        part_id=part_id,
        qty_per_unit=Decimal(str(qty_per_unit)),
    )
    db.add(rec)
    db.flush()
    return PickingMarkResult(picked=True, picked_at=rec.picked_at)


def unmark_picked(
    db: Session, order_id: str, part_id: str, qty_per_unit: float
) -> PickingMarkResult:
    """Unmark a variant. Idempotent — unmarking a non-existent record is silent.

    Does NOT validate that (part_id, qty_per_unit) is still in the order's
    aggregation. This allows cleaning up orphan rows left behind after order
    edits (e.g., a jewelry was removed from the order after a variant was
    marked picked). Requires only that the order exists."""
    order = db.query(Order).filter_by(id=order_id).one_or_none()
    if order is None:
        raise ValueError(f"订单 {order_id} 不存在")

    (
        db.query(OrderPickingRecord)
        .filter_by(order_id=order_id, part_id=part_id,
                   qty_per_unit=Decimal(str(qty_per_unit)))
        .delete(synchronize_session=False)
    )
    db.flush()
    return PickingMarkResult(picked=False)


def reset_picking(db: Session, order_id: str) -> int:
    """Delete all picking records for the order. Returns the delete count.
    Raises ValueError if the order does not exist."""
    order = db.query(Order).filter_by(id=order_id).one_or_none()
    if order is None:
        raise ValueError(f"订单 {order_id} 不存在")

    deleted = (
        db.query(OrderPickingRecord)
        .filter_by(order_id=order_id)
        .delete(synchronize_session=False)
    )
    db.flush()
    return deleted
