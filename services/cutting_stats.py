"""Cutting statistics (裁剪统计) for orders and handcraft orders.

Identifies parts whose names contain a `数字+cm` pattern (e.g. "金色O字链-18cm"),
extracts the cm value, and aggregates cutting requirements with source traceability.
Composite parts are expanded via part BOM.
"""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

_CM_RE = re.compile(r"(\d+(?:\.\d+)?)cm", re.IGNORECASE)


def _extract_cm(name: str) -> Optional[float]:
    """Extract the cm value from a part name, or None if no match."""
    m = _CM_RE.search(name or "")
    if m:
        return float(m.group(1))
    return None


def _merge_items(items: list[dict]) -> list[dict]:
    """Merge cutting items by part_id: sum qty, collect all sources."""
    merged: dict[str, dict] = {}
    for item in items:
        pid = item["part_id"]
        if pid in merged:
            merged[pid]["qty"] += item["qty"]
            merged[pid]["sources"].extend(item["sources"])
        else:
            merged[pid] = {
                "part_id": pid,
                "part_name": item["part_name"],
                "part_image": item["part_image"],
                "cut_length_cm": item["cut_length_cm"],
                "qty": item["qty"],
                "sources": list(item["sources"]),
            }
    return list(merged.values())


def _expand_composite_part(
    db: Session,
    parent_part_id: str,
    parent_part_name: str,
    parent_total_qty: float,
    source_label_suffix: str,
    _ancestors: frozenset[str] = frozenset(),
) -> list[dict]:
    """Recursively expand a composite part via its BOM and return cutting items
    for all descendants that match cm. Handles nested composites.

    _ancestors tracks the current recursion PATH (not globally visited nodes)
    so that diamond-shaped DAGs (A->B->D, A->C->D) count D from both paths.
    Only true cycles (A->...->A) are skipped."""
    from services.part_bom import get_part_bom

    if parent_part_id in _ancestors:
        return []  # Cycle guard — only on current path
    path = _ancestors | {parent_part_id}

    children = get_part_bom(db, parent_part_id)
    items = []
    for child in children:
        child_name = child["child_part_name"]
        child_qty = parent_total_qty * child["qty_per_unit"]
        child_id = child["child_part_id"]
        label = f"{parent_part_name}({parent_part_id}) × {_fmt_qty(parent_total_qty)} [BOM展开]"

        cm = _extract_cm(child_name)
        if cm is not None:
            items.append({
                "part_id": child_id,
                "part_name": child_name,
                "part_image": child.get("child_part_image"),
                "cut_length_cm": cm,
                "qty": child_qty,
                "sources": [{"label": label, "qty": child_qty}],
            })

        # Recurse into nested composites
        if child.get("child_is_composite"):
            nested = _expand_composite_part(
                db, child_id, child_name, child_qty,
                source_label_suffix="",
                _ancestors=path,
            )
            items.extend(nested)

    return items


def _fmt_qty(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def get_order_cutting_stats(db: Session, order_id: str) -> list[dict]:
    """Get cutting stats for an order, using get_parts_summary for BOM-aggregated data."""
    from services.order import get_order, get_parts_summary
    from models.part import Part

    order = get_order(db, order_id)
    if order is None:
        raise ValueError(f"订单 {order_id} 不存在")

    summary = get_parts_summary(db, order_id)
    if not summary:
        return []

    items: list[dict] = []
    for row in summary:
        part_name = row["part_name"]
        part_id = row["part_id"]
        part_image = row.get("part_image")
        is_composite = row.get("part_is_composite", False)

        # Use raw remaining (pre-ceil) to avoid inflating fractional remainders.
        raw_remaining = row.get("_raw_remaining_qty", 0.0)

        # Direct match: part name contains cm
        cm = _extract_cm(part_name)
        if cm is not None and not is_composite:
            sources = []
            for src in row.get("source_jewelries", []):
                sources.append({
                    "label": f"{src['jewelry_id']} {src['jewelry_name']}",
                    "qty": src["subtotal"],
                })
            items.append({
                "part_id": part_id,
                "part_name": part_name,
                "part_image": part_image,
                "cut_length_cm": cm,
                "qty": raw_remaining,
                "sources": sources,
            })

        # Composite expansion — always expand so child chains appear in modal
        # even when fully stocked (qty=0). Uses raw_remaining as multiplier.
        if is_composite:
            expanded = _expand_composite_part(
                db, part_id, part_name, raw_remaining,
                source_label_suffix="",
            )
            items.extend(expanded)

    return _merge_items(items)


def get_handcraft_cutting_stats(db: Session, handcraft_id: str) -> list[dict]:
    """Get cutting stats for a handcraft order."""
    from services.handcraft import get_handcraft_order, get_handcraft_parts
    from models.part import Part

    order = get_handcraft_order(db, handcraft_id)
    if order is None:
        raise ValueError(f"手工单 {handcraft_id} 不存在")

    part_items = get_handcraft_parts(db, handcraft_id)
    if not part_items:
        return []

    # Load part info for is_composite check
    part_ids = list({item.part_id for item in part_items})
    parts = {
        p.id: p
        for p in db.query(Part).filter(Part.id.in_(part_ids)).all()
    }

    items: list[dict] = []
    for item in part_items:
        part = parts.get(item.part_id)
        if part is None:
            continue
        part_name = part.name
        part_image = part.image
        qty = float(item.qty)

        # Direct match
        cm = _extract_cm(part_name)
        if cm is not None and not part.is_composite:
            label = f"{part_name}({item.part_id}) × {_fmt_qty(qty)}"
            items.append({
                "part_id": item.part_id,
                "part_name": part_name,
                "part_image": part_image,
                "cut_length_cm": cm,
                "qty": qty,
                "sources": [{"label": label, "qty": qty}],
            })

        # Composite expansion
        if part.is_composite:
            expanded = _expand_composite_part(
                db, item.part_id, part_name, qty,
                source_label_suffix="",
            )
            items.extend(expanded)

    return _merge_items(items)
