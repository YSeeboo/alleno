"""Parse a Feishu text message into a purchase-order draft.

Strict, deterministic, no DB access. The parser only checks line shape — part_id
existence and vendor matching happen in purchase_resolver.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation


@dataclass
class ParsedItem:
    line_no: int
    raw_line: str
    part_id: str
    qty: Decimal
    unit: str
    price: Decimal


@dataclass
class ParseError:
    line_no: int  # 0 = whole-message error (e.g. no items)
    raw_line: str
    reason: str


@dataclass
class ParsedPurchase:
    vendor_name: str
    items: list[ParsedItem] = field(default_factory=list)


# Item-shape detector: a part_id followed by a digit (any unit/suffix tail allowed).
_ITEM_FIRST_TOKEN_RE = re.compile(r"^\S+\s+\d")

_QTY_SUFFIXES = ("个", "件", "包")
_PRICE_SUFFIXES = ("元", "块", "￥", "¥")


# Part-ID prefix detector: first token looks like a part reference (PJ- prefix).
_PART_ID_TOKEN_RE = re.compile(r"^PJ-\S+\s+", re.IGNORECASE)


def is_purchase_text(text: str) -> bool:
    """Heuristic dispatch: does this look like a purchase-order message?

    Matches if the first item line either:
    - starts with any token followed by a digit (quantity-first format), OR
    - starts with a PJ-prefixed part ID (matches even when qty is malformed).
    """
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    second = lines[1].strip()
    return bool(_ITEM_FIRST_TOKEN_RE.match(second) or _PART_ID_TOKEN_RE.match(second))


def _strip_suffix(s: str, suffixes: tuple[str, ...]) -> str:
    s = s.strip()
    for suf in suffixes:
        if s.endswith(suf):
            return s[: -len(suf)].strip()
    for suf in suffixes:
        if s.startswith(suf):
            return s[len(suf):].strip()
    return s


def _parse_decimal(raw: str, suffixes: tuple[str, ...]) -> Decimal | None:
    cleaned = _strip_suffix(raw, suffixes)
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_item(line_no: int, raw_line: str) -> ParsedItem | ParseError:
    tokens = raw_line.split()
    # A trailing standalone currency word (e.g. "元") belongs to the price token.
    # Without this, "<id> <qty> <price> 元" (4 tokens) collides with the
    # "<id> <qty> <unit> <price>" 4-token form.
    if len(tokens) >= 2 and tokens[-1] and _strip_suffix(tokens[-1], _PRICE_SUFFIXES) == "":
        tokens = tokens[:-2] + [tokens[-2] + tokens[-1]]
    if len(tokens) == 3:
        part_id, qty_raw, price_raw = tokens
        unit = "个"
    elif len(tokens) == 4:
        part_id, qty_raw, unit, price_raw = tokens
    else:
        return ParseError(
            line_no=line_no,
            raw_line=raw_line,
            reason=f"格式错：每行需要 3 或 4 个 token，实际 {len(tokens)} 个",
        )

    qty = _parse_decimal(qty_raw, _QTY_SUFFIXES)
    if qty is None:
        return ParseError(
            line_no=line_no,
            raw_line=raw_line,
            reason=f"数量无法识别：'{qty_raw}'",
        )
    if qty <= 0:
        return ParseError(
            line_no=line_no,
            raw_line=raw_line,
            reason=f"数量需大于 0，得到 {qty}",
        )

    price = _parse_decimal(price_raw, _PRICE_SUFFIXES)
    if price is None:
        return ParseError(
            line_no=line_no,
            raw_line=raw_line,
            reason=f"单价无法识别：'{price_raw}'",
        )
    if price < 0:
        return ParseError(
            line_no=line_no,
            raw_line=raw_line,
            reason=f"单价不能为负，得到 {price}",
        )

    return ParsedItem(
        line_no=line_no,
        raw_line=raw_line,
        part_id=part_id,
        qty=qty,
        unit=unit,
        price=price,
    )


def parse_purchase_text(text: str) -> ParsedPurchase | list[ParseError]:
    """Return ParsedPurchase on success or list[ParseError] on any failure."""
    if not text:
        return [ParseError(line_no=0, raw_line="", reason="消息为空")]

    raw_lines = text.splitlines()
    enumerated = [(i + 1, ln) for i, ln in enumerate(raw_lines)]
    non_empty = [(i, ln) for i, ln in enumerated if ln.strip()]

    if not non_empty:
        return [ParseError(line_no=0, raw_line="", reason="消息为空")]

    vendor_line_no, vendor_raw = non_empty[0]
    vendor_name = vendor_raw.strip()
    errors: list[ParseError] = []

    if _ITEM_FIRST_TOKEN_RE.match(vendor_name):
        errors.append(ParseError(
            line_no=vendor_line_no,
            raw_line=vendor_raw,
            reason=f"首行看起来是配件编号，需要是店家名：'{vendor_name}'",
        ))

    item_lines = non_empty[1:]
    if not item_lines:
        errors.append(ParseError(
            line_no=0,
            raw_line="",
            reason="没有解析到明细行",
        ))

    items: list[ParsedItem] = []
    for line_no, raw_line in item_lines:
        result = _parse_item(line_no, raw_line)
        if isinstance(result, ParseError):
            errors.append(result)
        else:
            items.append(result)

    if errors:
        return errors
    return ParsedPurchase(vendor_name=vendor_name, items=items)
