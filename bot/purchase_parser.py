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


_QTY_SUFFIXES = ("个", "件", "包")
_PRICE_SUFFIXES = ("元", "块", "￥", "¥")


# Part-ID prefix detector: first token looks like a part reference (PJ- prefix).
_PART_ID_TOKEN_RE = re.compile(r"^PJ-\S+\s+", re.IGNORECASE)


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


def _glue_trailing_currency(tokens: list[str]) -> list[str]:
    """A trailing standalone currency word (e.g. "元") belongs to the price token.
    Without this, "<name> <qty> <price> 元" collides with the unit form."""
    if len(tokens) >= 2 and tokens[-1] and _strip_suffix(tokens[-1], _PRICE_SUFFIXES) == "":
        return tokens[:-2] + [tokens[-2] + tokens[-1]]
    return tokens


def _looks_like_item_line(line: str) -> bool:
    """Heuristic: does this line look like an item ("<name…> <qty> [unit] <price>")?

    True when the line ends with a qty + price pair, OR starts with a PJ- token
    (so a typo'd-qty id line still routes to the purchase parser and yields a
    parse-error card instead of falling through to the agent).

    Known, accepted limitation: a natural-language second line that happens to
    end in two number-ish tokens (e.g. "今天 卖了 100 5") will false-trigger and
    be treated as a purchase. Rare in practice; the preview/confirm step is the
    safety net."""
    s = line.strip()
    if _PART_ID_TOKEN_RE.match(s):
        return True
    tokens = _glue_trailing_currency(s.split())
    if len(tokens) < 3:
        return False
    qpos = -3 if (len(tokens) >= 4 and tokens[-2] in _QTY_SUFFIXES) else -2
    price_ok = _parse_decimal(tokens[-1], _PRICE_SUFFIXES) is not None
    qty_ok = _parse_decimal(tokens[qpos], _QTY_SUFFIXES) is not None
    return price_ok and qty_ok


def is_purchase_text(text: str) -> bool:
    """Heuristic dispatch: does this look like a purchase-order message?"""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    return _looks_like_item_line(lines[1])


def _parse_item(line_no: int, raw_line: str) -> ParsedItem | ParseError:
    tokens = _glue_trailing_currency(raw_line.split())
    if len(tokens) < 3:
        return ParseError(
            line_no=line_no,
            raw_line=raw_line,
            reason=f"格式错：至少需要 名称 数量 价格，实际 {len(tokens)} 个 token",
        )

    price_raw = tokens[-1]
    if len(tokens) >= 4 and tokens[-2] in _QTY_SUFFIXES:
        unit = tokens[-2]
        qty_raw = tokens[-3]
        name_tokens = tokens[:-3]
    else:
        unit = "个"
        qty_raw = tokens[-2]
        name_tokens = tokens[:-2]
    # name_tokens is always non-empty here: len(tokens) >= 3 guarantees at least
    # one token before the qty/price tail.

    qty = _parse_decimal(qty_raw, _QTY_SUFFIXES)
    if qty is None:
        return ParseError(line_no=line_no, raw_line=raw_line, reason=f"数量无法识别：'{qty_raw}'")
    if qty <= 0:
        return ParseError(line_no=line_no, raw_line=raw_line, reason=f"数量需大于 0，得到 {qty}")

    price = _parse_decimal(price_raw, _PRICE_SUFFIXES)
    if price is None:
        return ParseError(line_no=line_no, raw_line=raw_line, reason=f"单价无法识别：'{price_raw}'")
    if price < 0:
        return ParseError(line_no=line_no, raw_line=raw_line, reason=f"单价不能为负，得到 {price}")

    return ParsedItem(
        line_no=line_no,
        raw_line=raw_line,
        part_id=" ".join(name_tokens),
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

    if _looks_like_item_line(vendor_name):
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
