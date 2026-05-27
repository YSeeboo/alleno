"""Resolve a parsed purchase against the DB.

Per-line part resolution priority: id exact -> name exact -> name fuzzy (ILIKE).
Vendor name resolved via exact / bidirectional substring fuzzy match.
Outcome is three-way: ResolvedPurchase (all unique) / NeedsDisambiguation
(some names match multiple parts) / ResolveError (a name matched nothing, or
the vendor name is ambiguous).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from bot.purchase_parser import ParsedPurchase, ParsedItem
from models.part import Part
from services._helpers import keyword_filter
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
class Candidate:
    part_id: str
    part_name: str
    spec: str | None
    part_image: str | None


@dataclass
class PendingLine:
    line_no: int
    query: str
    qty: Decimal
    unit: str
    price: Decimal
    candidates: list[Candidate]
    chosen_part_id: str | None = None


@dataclass
class NeedsDisambiguation:
    vendor_name: str
    vendor_is_new: bool
    resolved_items: list[ResolvedItem]
    pending: list[PendingLine]


@dataclass
class ResolveError:
    kind: str  # "part_not_found" | "vendor_ambiguous"
    detail: dict[str, Any]


def _match_vendor(input_name: str, existing: list[str]) -> tuple[str, bool] | ResolveError:
    """Return (canonical_name, is_new) or a ResolveError for ambiguity.

    Rules:
      1. exact match -> canonical = input, is_new=False
      2. existing names that are substrings of input -> pick longest (tie -> ambiguous)
      3. existing names that contain input as substring -> if 1 use it; if >1 ambiguous
      4. otherwise -> input is new
    """
    if input_name in existing:
        return (input_name, False)

    inp = input_name.strip()
    if len(inp) < _MIN_FUZZY_LEN:
        return (input_name, True)

    eligible = [e for e in existing if e is not None and len(e.strip()) >= _MIN_FUZZY_LEN]

    contained_in_input = [e for e in eligible if e in inp]
    if contained_in_input:
        max_len = max(len(e) for e in contained_in_input)
        longest = [e for e in contained_in_input if len(e) == max_len]
        if len(longest) > 1:
            return ResolveError(
                kind="vendor_ambiguous",
                detail={"input": input_name, "candidates": sorted(longest)},
            )
        return (longest[0], False)

    contains_input = [e for e in eligible if inp in e]
    if len(contains_input) == 1:
        return (contains_input[0], False)
    if len(contains_input) > 1:
        return ResolveError(
            kind="vendor_ambiguous",
            detail={"input": input_name, "candidates": sorted(contains_input)},
        )

    return (input_name, True)


def _candidates_for(db: Session, token: str) -> list[Part]:
    """Resolve one line's first token to part candidates.
    id exact -> [part]; else name exact -> matches; else name fuzzy (ILIKE) -> matches.
    Empty list = not found.
    """
    p = db.get(Part, token)
    if p is not None:
        return [p]
    exact = db.query(Part).filter(Part.name == token).all()
    if exact:
        return exact
    if len(token.strip()) < _MIN_FUZZY_LEN:
        return []
    clause = keyword_filter(token, Part.name)
    if clause is None:
        return []
    return db.query(Part).filter(clause).all()


def _build_item(it: ParsedItem, part: Part) -> ResolvedItem:
    amount = it.qty * it.price
    return ResolvedItem(
        line_no=it.line_no,
        part_id=part.id,
        part_name=part.name,
        part_image=getattr(part, "image", None),
        qty=it.qty,
        unit=it.unit,
        price=it.price,
        amount=amount,
    )


def _to_candidate(part: Part) -> Candidate:
    return Candidate(
        part_id=part.id,
        part_name=part.name,
        spec=getattr(part, "spec", None),
        part_image=getattr(part, "image", None),
    )


def resolve(db: Session, parsed: ParsedPurchase) -> ResolvedPurchase | NeedsDisambiguation | ResolveError:
    # 1. Per-line candidate lookup
    line_results: list[tuple[ParsedItem, list[Part]]] = []
    for it in parsed.items:
        line_results.append((it, _candidates_for(db, it.part_id)))

    # 2. not_found takes precedence (all-or-nothing)
    missing = [
        {"line_no": it.line_no, "part_id": it.part_id, "raw_line": it.raw_line}
        for it, cands in line_results
        if len(cands) == 0
    ]
    if missing:
        return ResolveError(kind="part_not_found", detail={"lines": missing})

    # 3. vendor (ambiguity before per-line part disambiguation)
    vendor_result = _match_vendor(parsed.vendor_name, get_vendor_names(db))
    if isinstance(vendor_result, ResolveError):
        return vendor_result
    vendor_name, is_new = vendor_result

    # 4. classify resolved vs ambiguous
    resolved_items: list[ResolvedItem] = []
    pending: list[PendingLine] = []
    for it, cands in line_results:
        if len(cands) == 1:
            resolved_items.append(_build_item(it, cands[0]))
        else:
            ordered = sorted(cands, key=lambda p: p.id)
            pending.append(PendingLine(
                line_no=it.line_no,
                query=it.part_id,
                qty=it.qty,
                unit=it.unit,
                price=it.price,
                candidates=[_to_candidate(p) for p in ordered],
            ))

    if pending:
        return NeedsDisambiguation(
            vendor_name=vendor_name,
            vendor_is_new=is_new,
            resolved_items=resolved_items,
            pending=pending,
        )

    total = sum((i.amount for i in resolved_items), Decimal(0))
    return ResolvedPurchase(
        vendor_name=vendor_name,
        vendor_is_new=is_new,
        items=resolved_items,
        total_amount=total,
    )


def first_unresolved(needs: NeedsDisambiguation) -> tuple[PendingLine, int, int] | None:
    """Return (pending_line, done_count, total) for the first line still awaiting a
    choice, or None if every pending line has been chosen."""
    total = len(needs.pending)
    done = sum(1 for pl in needs.pending if pl.chosen_part_id is not None)
    for pl in needs.pending:
        if pl.chosen_part_id is None:
            return pl, done, total
    return None


def assemble_resolved(db: Session, needs: NeedsDisambiguation) -> ResolvedPurchase:
    """All pending lines must have chosen_part_id set. Build the final purchase."""
    items: list[ResolvedItem] = list(needs.resolved_items)
    for pl in needs.pending:
        part = db.get(Part, pl.chosen_part_id)
        if part is None:
            raise ValueError(f"配件不存在: {pl.chosen_part_id}")
        amount = pl.qty * pl.price
        items.append(ResolvedItem(
            line_no=pl.line_no,
            part_id=part.id,
            part_name=part.name,
            part_image=getattr(part, "image", None),
            qty=pl.qty,
            unit=pl.unit,
            price=pl.price,
            amount=amount,
        ))
    items.sort(key=lambda i: i.line_no)
    total = sum((i.amount for i in items), Decimal(0))
    return ResolvedPurchase(
        vendor_name=needs.vendor_name,
        vendor_is_new=needs.vendor_is_new,
        items=items,
        total_amount=total,
    )
