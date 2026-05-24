"""Resolve a parsed purchase against the DB:
  - look up parts (strict equality on part_id)
  - resolve vendor name via exact / bidirectional substring fuzzy match
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from bot.purchase_parser import ParsedPurchase
from models.part import Part
from services.purchase_order import get_vendor_names


_MIN_FUZZY_LEN = 2


@dataclass
class ResolvedItem:
    line_no: int
    part_id: str
    part_name: str
    part_image: str | None
    qty: Decimal
    unit: str
    price: Decimal
    amount: Decimal


@dataclass
class ResolvedPurchase:
    vendor_name: str
    vendor_is_new: bool
    items: list[ResolvedItem]
    total_amount: Decimal


@dataclass
class ResolveError:
    kind: str  # "part_not_found" | "vendor_ambiguous"
    detail: dict[str, Any]


def _match_vendor(input_name: str, existing: list[str]) -> tuple[str, bool] | ResolveError:
    """Return (canonical_name, is_new) or a ResolveError for ambiguity.

    Rules:
      1. exact match → canonical = input, is_new=False
      2. existing names that are substrings of input → pick longest, is_new=False
      3. existing names that contain input as substring → if 1, use it; if >1, ambiguous
      4. otherwise → input is new
    """
    if input_name in existing:
        return (input_name, False)

    inp = input_name.strip()
    if len(inp) < _MIN_FUZZY_LEN:
        return (input_name, True)

    eligible = [e for e in existing if e is not None and len(e.strip()) >= _MIN_FUZZY_LEN]

    contained_in_input = [e for e in eligible if e in inp]
    if contained_in_input:
        canonical = max(contained_in_input, key=len)
        return (canonical, False)

    contains_input = [e for e in eligible if inp in e]
    if len(contains_input) == 1:
        return (contains_input[0], False)
    if len(contains_input) > 1:
        return ResolveError(
            kind="vendor_ambiguous",
            detail={"input": input_name, "candidates": sorted(contains_input)},
        )

    return (input_name, True)


def resolve(db: Session, parsed: ParsedPurchase) -> ResolvedPurchase | ResolveError:
    # 1. Bulk-look up all parts in one query
    part_ids = [it.part_id for it in parsed.items]
    rows = db.query(Part).filter(Part.id.in_(part_ids)).all()
    found_map = {p.id: p for p in rows}

    missing = [
        {"line_no": it.line_no, "part_id": it.part_id, "raw_line": it.raw_line}
        for it in parsed.items
        if it.part_id not in found_map
    ]
    if missing:
        return ResolveError(kind="part_not_found", detail={"lines": missing})

    # 2. Resolve vendor
    existing_vendors = get_vendor_names(db)
    vendor_result = _match_vendor(parsed.vendor_name, existing_vendors)
    if isinstance(vendor_result, ResolveError):
        return vendor_result
    vendor_name, is_new = vendor_result

    # 3. Build ResolvedItems
    items: list[ResolvedItem] = []
    total = Decimal(0)
    for it in parsed.items:
        part = found_map[it.part_id]
        amount = it.qty * it.price
        items.append(ResolvedItem(
            line_no=it.line_no,
            part_id=it.part_id,
            part_name=part.name,
            part_image=getattr(part, "image", None),
            qty=it.qty,
            unit=it.unit,
            price=it.price,
            amount=amount,
        ))
        total += amount

    return ResolvedPurchase(
        vendor_name=vendor_name,
        vendor_is_new=is_new,
        items=items,
        total_amount=total,
    )
