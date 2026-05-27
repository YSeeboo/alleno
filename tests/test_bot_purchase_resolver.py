from decimal import Decimal

import pytest

from bot.purchase_parser import ParsedPurchase, ParsedItem
from bot.purchase_resolver import (
    resolve,
    ResolvedPurchase,
    ResolveError,
)
from services.part import create_part
from services.purchase_order import create_purchase_order


def _parsed(vendor: str, *items):
    parsed_items = [
        ParsedItem(
            line_no=i + 2,
            raw_line=f"{pid} {qty} {price}",
            part_id=pid,
            qty=Decimal(str(qty)),
            unit="个",
            price=Decimal(str(price)),
        )
        for i, (pid, qty, price) in enumerate(items)
    ]
    return ParsedPurchase(vendor_name=vendor, items=parsed_items)


def _seed_part(db, name="吊坠A"):
    return create_part(db, {"name": name, "category": "吊坠"})


def _seed_purchase_with_vendor(db, vendor_name, part_id):
    create_purchase_order(
        db,
        vendor_name=vendor_name,
        items=[{"part_id": part_id, "qty": 1, "unit": "个", "price": 1}],
    )


def test_resolve_success(db):
    p = _seed_part(db)
    parsed = _parsed("新店家", (p.id, 10, 2))
    result = resolve(db, parsed)
    assert isinstance(result, ResolvedPurchase)
    assert result.vendor_name == "新店家"
    assert result.vendor_is_new is True
    assert len(result.items) == 1
    item = result.items[0]
    assert item.part_id == p.id
    assert item.part_name == p.name
    assert item.qty == Decimal("10")
    assert item.price == Decimal("2")
    assert item.amount == Decimal("20")
    assert result.total_amount == Decimal("20")


def test_resolve_part_not_found_collects_all_missing_lines(db):
    p = _seed_part(db)
    parsed = _parsed("店家", (p.id, 10, 2), ("PJ-XX-9999", 5, 1), ("PJ-YY-8888", 3, 1))
    result = resolve(db, parsed)
    assert isinstance(result, ResolveError)
    assert result.kind == "part_not_found"
    missing = result.detail["lines"]
    missing_ids = {m["part_id"] for m in missing}
    assert missing_ids == {"PJ-XX-9999", "PJ-YY-8888"}


def test_resolve_vendor_exact_match(db):
    p = _seed_part(db)
    _seed_purchase_with_vendor(db, "腾飞", p.id)
    result = resolve(db, _parsed("腾飞", (p.id, 1, 1)))
    assert isinstance(result, ResolvedPurchase)
    assert result.vendor_name == "腾飞"
    assert result.vendor_is_new is False


def test_resolve_vendor_existing_is_substring_of_input(db):
    p = _seed_part(db)
    _seed_purchase_with_vendor(db, "腾飞", p.id)
    result = resolve(db, _parsed("腾飞商家", (p.id, 1, 1)))
    assert isinstance(result, ResolvedPurchase)
    assert result.vendor_name == "腾飞"  # canonical name wins
    assert result.vendor_is_new is False


def test_resolve_vendor_input_is_substring_of_existing(db):
    p = _seed_part(db)
    _seed_purchase_with_vendor(db, "腾飞商家", p.id)
    result = resolve(db, _parsed("腾飞", (p.id, 1, 1)))
    assert isinstance(result, ResolvedPurchase)
    assert result.vendor_name == "腾飞商家"
    assert result.vendor_is_new is False


def test_resolve_vendor_ambiguous_when_input_substring_of_multiple(db):
    p = _seed_part(db)
    _seed_purchase_with_vendor(db, "腾飞商家", p.id)
    _seed_purchase_with_vendor(db, "腾飞贸易", p.id)
    result = resolve(db, _parsed("腾飞", (p.id, 1, 1)))
    assert isinstance(result, ResolveError)
    assert result.kind == "vendor_ambiguous"
    cands = set(result.detail["candidates"])
    assert cands == {"腾飞商家", "腾飞贸易"}


def test_resolve_vendor_takes_longest_when_multiple_existing_inside_input(db):
    p = _seed_part(db)
    _seed_purchase_with_vendor(db, "腾飞", p.id)
    _seed_purchase_with_vendor(db, "腾飞贸易", p.id)
    # Input "腾飞贸易公司" contains both. Pick the longest = "腾飞贸易".
    result = resolve(db, _parsed("腾飞贸易公司", (p.id, 1, 1)))
    assert isinstance(result, ResolvedPurchase)
    assert result.vendor_name == "腾飞贸易"


def test_resolve_vendor_short_input_doesnt_match(db):
    p = _seed_part(db)
    _seed_purchase_with_vendor(db, "李四", p.id)
    # input "李" has length 1 → below 2-char minimum, treat as new
    result = resolve(db, _parsed("李", (p.id, 1, 1)))
    assert isinstance(result, ResolvedPurchase)
    assert result.vendor_is_new is True
    assert result.vendor_name == "李"


def test_resolve_amount_is_qty_times_price(db):
    p = _seed_part(db)
    result = resolve(db, _parsed("店家", (p.id, "10.5", "3.25")))
    assert isinstance(result, ResolvedPurchase)
    assert result.items[0].amount == Decimal("34.125")
    assert result.total_amount == Decimal("34.125")


def test_resolve_vendor_branch2_tie_is_ambiguous(db):
    p = _seed_part(db)
    _seed_purchase_with_vendor(db, "腾飞", p.id)
    _seed_purchase_with_vendor(db, "飞鸿", p.id)
    # input contains both "腾飞" and "飞鸿" at equal length → ambiguous
    result = resolve(db, _parsed("腾飞鸿", (p.id, 1, 1)))
    assert isinstance(result, ResolveError)
    assert result.kind == "vendor_ambiguous"
    assert set(result.detail["candidates"]) == {"腾飞", "飞鸿"}


def test_resolve_vendor_branch2_unique_longest_still_resolves(db):
    p = _seed_part(db)
    _seed_purchase_with_vendor(db, "腾飞", p.id)
    _seed_purchase_with_vendor(db, "腾飞贸易", p.id)
    result = resolve(db, _parsed("腾飞贸易公司", (p.id, 1, 1)))
    assert isinstance(result, ResolvedPurchase)
    assert result.vendor_name == "腾飞贸易"


# ---------------------------------------------------------------------------
# Name resolution + three-way result tests
# ---------------------------------------------------------------------------
from bot.purchase_resolver import (
    NeedsDisambiguation,
    Candidate,
    assemble_resolved,
    first_unresolved,
)


def test_resolve_by_name_exact_unique(db):
    p = create_part(db, {"name": "珍珠链条", "category": "链条"})
    db.commit()
    parsed = _parsed("店家", ("珍珠链条", 10, 2))
    result = resolve(db, parsed)
    assert isinstance(result, ResolvedPurchase)
    assert result.items[0].part_id == p.id
    assert result.items[0].part_name == "珍珠链条"


def test_resolve_by_name_fuzzy_unique(db):
    p = create_part(db, {"name": "玫瑰吊坠大号", "category": "吊坠"})
    db.commit()
    result = resolve(db, _parsed("店家", ("玫瑰吊坠", 10, 2)))
    assert isinstance(result, ResolvedPurchase)
    assert result.items[0].part_id == p.id


def test_resolve_by_name_fuzzy_multiple_needs_disambiguation(db):
    p1 = create_part(db, {"name": "玫瑰吊坠大", "category": "吊坠"})
    p2 = create_part(db, {"name": "玫瑰吊坠小", "category": "吊坠"})
    db.commit()
    result = resolve(db, _parsed("店家", ("玫瑰吊坠", 10, 2)))
    assert isinstance(result, NeedsDisambiguation)
    assert len(result.pending) == 1
    pend = result.pending[0]
    assert pend.line_no == 2
    assert pend.query == "玫瑰吊坠"
    assert pend.qty == Decimal("10")
    assert pend.price == Decimal("2")
    ids = [c.part_id for c in pend.candidates]
    assert set(ids) == {p1.id, p2.id}
    assert ids == sorted(ids)
    assert result.resolved_items == []


def test_resolve_name_not_found(db):
    result = resolve(db, _parsed("店家", ("不存在的名字", 1, 1)))
    assert isinstance(result, ResolveError)
    assert result.kind == "part_not_found"


def test_resolve_mixed_resolved_and_ambiguous(db):
    uniq = create_part(db, {"name": "珍珠链条", "category": "链条"})
    a1 = create_part(db, {"name": "玫瑰吊坠大", "category": "吊坠"})
    a2 = create_part(db, {"name": "玫瑰吊坠小", "category": "吊坠"})
    db.commit()
    result = resolve(db, _parsed("店家", ("珍珠链条", 5, 1), ("玫瑰吊坠", 10, 2)))
    assert isinstance(result, NeedsDisambiguation)
    assert [i.part_id for i in result.resolved_items] == [uniq.id]
    assert len(result.pending) == 1
    assert result.pending[0].line_no == 3


def test_resolve_not_found_takes_precedence_over_ambiguous(db):
    create_part(db, {"name": "玫瑰吊坠大", "category": "吊坠"})
    create_part(db, {"name": "玫瑰吊坠小", "category": "吊坠"})
    db.commit()
    result = resolve(db, _parsed("店家", ("玫瑰吊坠", 10, 2), ("查无此物", 1, 1)))
    assert isinstance(result, ResolveError)
    assert result.kind == "part_not_found"


def test_resolve_id_still_works(db):
    p = create_part(db, {"name": "吊坠A", "category": "吊坠"})
    db.commit()
    result = resolve(db, _parsed("店家", (p.id, 3, 4)))
    assert isinstance(result, ResolvedPurchase)
    assert result.items[0].part_id == p.id


def test_candidate_carries_spec(db):
    create_part(db, {"name": "玫瑰吊坠大", "category": "吊坠", "spec": "18mm"})
    create_part(db, {"name": "玫瑰吊坠小", "category": "吊坠", "spec": "12mm"})
    db.commit()
    result = resolve(db, _parsed("店家", ("玫瑰吊坠", 1, 1)))
    assert isinstance(result, NeedsDisambiguation)
    specs = {c.spec for c in result.pending[0].candidates}
    assert specs == {"18mm", "12mm"}


def test_assemble_resolved_builds_full_purchase(db):
    uniq = create_part(db, {"name": "珍珠链条", "category": "链条"})
    a1 = create_part(db, {"name": "玫瑰吊坠大", "category": "吊坠"})
    create_part(db, {"name": "玫瑰吊坠小", "category": "吊坠"})
    db.commit()
    needs = resolve(db, _parsed("店家", ("珍珠链条", 5, 1), ("玫瑰吊坠", 10, 2)))
    assert isinstance(needs, NeedsDisambiguation)
    needs.pending[0].chosen_part_id = a1.id
    resolved = assemble_resolved(db, needs)
    assert isinstance(resolved, ResolvedPurchase)
    assert [i.line_no for i in resolved.items] == [2, 3]
    assert [i.part_id for i in resolved.items] == [uniq.id, a1.id]
    assert resolved.total_amount == Decimal("25")


def test_first_unresolved_returns_next_pending_then_none(db):
    a1 = create_part(db, {"name": "玫瑰吊坠大", "category": "吊坠"})
    create_part(db, {"name": "玫瑰吊坠小", "category": "吊坠"})
    b1 = create_part(db, {"name": "珍珠扣大", "category": "小配件"})
    create_part(db, {"name": "珍珠扣小", "category": "小配件"})
    db.commit()
    needs = resolve(db, _parsed("店家", ("玫瑰吊坠", 1, 1), ("珍珠扣", 1, 1)))
    assert isinstance(needs, NeedsDisambiguation)
    pl, done, total = first_unresolved(needs)
    assert total == 2 and done == 0 and pl.line_no == 2
    needs.pending[0].chosen_part_id = a1.id
    pl, done, total = first_unresolved(needs)
    assert total == 2 and done == 1 and pl.line_no == 3
    needs.pending[1].chosen_part_id = b1.id
    assert first_unresolved(needs) is None
