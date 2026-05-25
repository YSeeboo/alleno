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
