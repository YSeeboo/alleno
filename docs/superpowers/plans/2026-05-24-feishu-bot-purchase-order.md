# 飞书 bot 结构化建采购单 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the owner build a purchase order in Feishu by sending one structured text message (vendor + part lines), then confirming via inline card buttons.

**Architecture:** Pure-function parser → DB-backed resolver → in-memory draft store keyed by token → Feishu interactive card with confirm/cancel buttons → card-action handler creates the PO via existing `create_purchase_order` service (which already writes `inventory_log` 采购入库). All side-effects on confirm only.

**Tech Stack:** FastAPI, SQLAlchemy, httpx (Feishu API), pytest, Decimal arithmetic. No new dependencies, no DB migration.

**Spec reference:** `docs/superpowers/specs/2026-05-24-feishu-bot-purchase-order-design.md`

---

## File Map

**New files:**
- `bot/purchase_parser.py` — pure parser + `is_purchase_text`
- `bot/purchase_resolver.py` — DB lookup (parts + vendor names) + vendor fuzzy match
- `bot/purchase_draft_store.py` — in-memory draft + consumed tables, TTL
- `bot/feishu_cards.py` — pure card-JSON template functions
- `bot/feishu_card_handler.py` — handle `card.action.trigger`
- `tests/test_bot_purchase_parser.py`
- `tests/test_bot_purchase_resolver.py`
- `tests/test_bot_purchase_draft_store.py`
- `tests/test_bot_feishu_cards.py`
- `tests/test_api_feishu_purchase.py`

**Modified files:**
- `bot/handlers.py` — add `send_feishu_card`; dispatch on `is_purchase_text` in `process_feishu_message`; new `_process_purchase_text`; `process_feishu_message` gets `sender_open_id` param
- `api/feishu.py` — route on `header.event_type`; new `card.action.trigger` branch; pass `sender_open_id` to `process_feishu_message`

---

## Task 1: Parser — token splitting & is_purchase_text

**Files:**
- Create: `bot/purchase_parser.py`
- Test: `tests/test_bot_purchase_parser.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bot_purchase_parser.py
from decimal import Decimal

from bot.purchase_parser import (
    is_purchase_text,
    parse_purchase_text,
    ParsedPurchase,
    ParsedItem,
    ParseError,
)


def test_is_purchase_text_recognises_structured_message():
    text = "李老板\nPJ-DZ-0001 100 5\nPJ-LT-0003 50 3.5"
    assert is_purchase_text(text) is True


def test_is_purchase_text_rejects_natural_language():
    assert is_purchase_text("查一下吊坠库存") is False
    assert is_purchase_text("你好") is False
    assert is_purchase_text("") is False


def test_is_purchase_text_rejects_single_line():
    assert is_purchase_text("李老板") is False


def test_is_purchase_text_rejects_item_shaped_first_line():
    # first line looks like an item — caller should still route here so we can produce
    # a helpful "首行不像店家名" error, but is_purchase_text is the dispatch heuristic.
    # When first line matches item pattern, we *do* want to dispatch (so the user gets a
    # specific error instead of agent-LLM noise).
    text = "PJ-DZ-0001 100 5\nPJ-LT-0003 50 3.5"
    assert is_purchase_text(text) is True


def test_parse_three_token_line():
    text = "李老板\nPJ-DZ-0001 100 5"
    result = parse_purchase_text(text)
    assert isinstance(result, ParsedPurchase)
    assert result.vendor_name == "李老板"
    assert len(result.items) == 1
    item = result.items[0]
    assert item.line_no == 2
    assert item.part_id == "PJ-DZ-0001"
    assert item.qty == Decimal("100")
    assert item.unit == "个"
    assert item.price == Decimal("5")


def test_parse_four_token_line_with_unit():
    text = "李老板\nPJ-DZ-0001 100 件 5"
    result = parse_purchase_text(text)
    assert isinstance(result, ParsedPurchase)
    assert result.items[0].unit == "件"
    assert result.items[0].qty == Decimal("100")
    assert result.items[0].price == Decimal("5")


def test_parse_strips_qty_suffix():
    for suffix in ("个", "件", "包"):
        text = f"李老板\nPJ-DZ-0001 100{suffix} 5"
        result = parse_purchase_text(text)
        assert isinstance(result, ParsedPurchase), f"failed on {suffix}: {result}"
        assert result.items[0].qty == Decimal("100")


def test_parse_strips_price_suffix():
    for raw, expected in [("5元", "5"), ("5块", "5"), ("￥5", "5"), ("¥5.5", "5.5")]:
        text = f"李老板\nPJ-DZ-0001 100 {raw}"
        result = parse_purchase_text(text)
        assert isinstance(result, ParsedPurchase), f"failed on {raw}: {result}"
        assert result.items[0].price == Decimal(expected)


def test_parse_decimal_qty_and_price():
    text = "李老板\nPJ-DZ-0001 10.5 3.25"
    result = parse_purchase_text(text)
    assert isinstance(result, ParsedPurchase)
    assert result.items[0].qty == Decimal("10.5")
    assert result.items[0].price == Decimal("3.25")


def test_parse_multiple_items():
    text = "腾飞\nPJ-DZ-0001 100 5\nPJ-LT-0003 50 3.5\nPJ-X-0012 200 0.8"
    result = parse_purchase_text(text)
    assert isinstance(result, ParsedPurchase)
    assert result.vendor_name == "腾飞"
    assert [i.part_id for i in result.items] == ["PJ-DZ-0001", "PJ-LT-0003", "PJ-X-0012"]
    assert [i.line_no for i in result.items] == [2, 3, 4]


def test_parse_skips_blank_lines():
    text = "李老板\n\nPJ-DZ-0001 100 5\n\n\nPJ-LT-0003 50 3.5\n"
    result = parse_purchase_text(text)
    assert isinstance(result, ParsedPurchase)
    assert len(result.items) == 2
    # line_no preserves the original 1-based file position
    assert result.items[0].line_no == 3
    assert result.items[1].line_no == 6


def test_parse_bad_qty_returns_error():
    text = "李老板\nPJ-DZ-0001 abc 5"
    result = parse_purchase_text(text)
    assert isinstance(result, list)
    assert len(result) == 1
    err = result[0]
    assert err.line_no == 2
    assert "数量" in err.reason or "qty" in err.reason.lower()


def test_parse_bad_price_returns_error():
    text = "李老板\nPJ-DZ-0001 100 xyz"
    result = parse_purchase_text(text)
    assert isinstance(result, list)
    assert result[0].line_no == 2
    assert "单价" in result[0].reason or "price" in result[0].reason.lower()


def test_parse_wrong_token_count_returns_error():
    text = "李老板\nPJ-DZ-0001 100"  # only 2 tokens
    result = parse_purchase_text(text)
    assert isinstance(result, list)
    assert result[0].line_no == 2
    assert "token" in result[0].reason.lower() or "格式" in result[0].reason


def test_parse_collects_multiple_errors():
    text = "李老板\nPJ-DZ-0001 abc 5\nPJ-LT-0003 50 3.5\nPJ-X-0012 xx yy"
    result = parse_purchase_text(text)
    assert isinstance(result, list)
    assert len(result) == 2
    assert {e.line_no for e in result} == {2, 4}


def test_parse_first_line_looking_like_item_is_error():
    text = "PJ-DZ-0001 100 5\nPJ-LT-0003 50 3.5"
    result = parse_purchase_text(text)
    assert isinstance(result, list)
    assert any(e.line_no == 1 and "店家" in e.reason for e in result)


def test_parse_no_items_is_error():
    text = "李老板"
    result = parse_purchase_text(text)
    assert isinstance(result, list)
    assert any(e.line_no == 0 and "明细" in e.reason for e in result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bot_purchase_parser.py -v`
Expected: All fail with `ModuleNotFoundError: No module named 'bot.purchase_parser'`.

- [ ] **Step 3: Implement the parser**

Create `bot/purchase_parser.py`:

```python
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
# We use this to (a) decide whether the first line looks like an item (= bad vendor)
# and (b) decide whether the second line looks like an item (= dispatch to parser).
_ITEM_FIRST_TOKEN_RE = re.compile(r"^\S+\s+\d")

_QTY_SUFFIXES = ("个", "件", "包")
_PRICE_SUFFIXES = ("元", "块", "￥", "¥", "$")


def is_purchase_text(text: str) -> bool:
    """Heuristic dispatch: does this look like a purchase-order message?"""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    # Second line must look item-shaped. (First line being vendor or item-shaped
    # is fine — parser will produce the specific error.)
    return bool(_ITEM_FIRST_TOKEN_RE.match(lines[1].strip()))


def _strip_suffix(s: str, suffixes: tuple[str, ...]) -> str:
    s = s.strip()
    # Try trailing suffix
    for suf in suffixes:
        if s.endswith(suf):
            return s[: -len(suf)].strip()
    # Try leading suffix (for ￥ / ¥ / $)
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
    except (InvalidOperation, ValueError):
        return None


def _looks_like_item(line: str) -> bool:
    return bool(_ITEM_FIRST_TOKEN_RE.match(line.strip()))


def _parse_item(line_no: int, raw_line: str) -> ParsedItem | ParseError:
    tokens = raw_line.split()
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

    if not part_id:
        return ParseError(line_no=line_no, raw_line=raw_line, reason="配件编号为空")

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
    # Find first non-empty line index (vendor) and keep original 1-based positions
    enumerated = [(i + 1, ln) for i, ln in enumerate(raw_lines)]
    non_empty = [(i, ln) for i, ln in enumerated if ln.strip()]

    if not non_empty:
        return [ParseError(line_no=0, raw_line="", reason="消息为空")]

    vendor_line_no, vendor_raw = non_empty[0]
    vendor_name = vendor_raw.strip()
    errors: list[ParseError] = []

    if _looks_like_item(vendor_name):
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_bot_purchase_parser.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add bot/purchase_parser.py tests/test_bot_purchase_parser.py
git commit -m "feat(bot): structured purchase-order text parser"
```

---

## Task 2: Draft store — in-memory tokens with TTL

**Files:**
- Create: `bot/purchase_draft_store.py`
- Test: `tests/test_bot_purchase_draft_store.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bot_purchase_draft_store.py
import time

import pytest

from bot.purchase_draft_store import (
    put,
    put_with_token,
    pop_draft,
    mark_consumed,
    get_consumed_po,
    _reset_for_test,
    _set_ttl_for_test,
)


@pytest.fixture(autouse=True)
def reset():
    _reset_for_test()
    _set_ttl_for_test(3600)
    yield
    _reset_for_test()


def _draft():
    # store doesn't care about the type of data — pass any sentinel
    return {"vendor_name": "腾飞", "items": []}


def test_put_then_pop_returns_data():
    token = put(_draft(), sender_open_id="open-1")
    assert isinstance(token, str) and len(token) > 0
    data = pop_draft(token, sender_open_id="open-1")
    assert data == _draft()


def test_pop_twice_returns_none_second_time():
    token = put(_draft(), sender_open_id="open-1")
    assert pop_draft(token, sender_open_id="open-1") is not None
    assert pop_draft(token, sender_open_id="open-1") is None


def test_pop_with_wrong_sender_returns_none():
    token = put(_draft(), sender_open_id="open-1")
    assert pop_draft(token, sender_open_id="open-2") is None
    # The draft must still be there for the right sender
    assert pop_draft(token, sender_open_id="open-1") is not None


def test_pop_expired_returns_none():
    _set_ttl_for_test(0)
    token = put(_draft(), sender_open_id="open-1")
    time.sleep(0.01)
    assert pop_draft(token, sender_open_id="open-1") is None


def test_put_with_token_round_trip_with_same_token():
    token = put(_draft(), sender_open_id="open-1")
    data = pop_draft(token, sender_open_id="open-1")
    assert data is not None
    put_with_token(token, data, sender_open_id="open-1")
    again = pop_draft(token, sender_open_id="open-1")
    assert again == _draft()


def test_mark_consumed_then_get_consumed_returns_po_id():
    token = put(_draft(), sender_open_id="open-1")
    pop_draft(token, sender_open_id="open-1")
    mark_consumed(token, po_id="CG-0001", sender_open_id="open-1")
    assert get_consumed_po(token, sender_open_id="open-1") == "CG-0001"


def test_get_consumed_with_wrong_sender_returns_none():
    token = put(_draft(), sender_open_id="open-1")
    pop_draft(token, sender_open_id="open-1")
    mark_consumed(token, po_id="CG-0001", sender_open_id="open-1")
    assert get_consumed_po(token, sender_open_id="open-2") is None


def test_consumed_expires():
    _set_ttl_for_test(0)
    token = "tk-1"
    mark_consumed(token, po_id="CG-0001", sender_open_id="open-1")
    time.sleep(0.01)
    assert get_consumed_po(token, sender_open_id="open-1") is None


def test_unknown_token_returns_none_everywhere():
    assert pop_draft("nope", sender_open_id="open-1") is None
    assert get_consumed_po("nope", sender_open_id="open-1") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bot_purchase_draft_store.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the store**

Create `bot/purchase_draft_store.py`:

```python
"""In-memory draft and consumed-token tables for the Feishu purchase-order flow.

Drafts are short-lived (~1 hour). Process restart loses them — acceptable for an
interactive flow; the user can resend the message. Two tables:

- _drafts:  token -> (data, created_at, sender_open_id). Parsed-but-unconfirmed.
- _consumed: token -> (po_id, created_at, sender_open_id). Used so a second click
            of "confirm" can return a friendly "this PO is already created" reply.
"""
from __future__ import annotations

import secrets
import time
from threading import RLock
from typing import Any

_TTL_SECONDS = 3600
_lock = RLock()
_drafts: dict[str, tuple[Any, float, str]] = {}
_consumed: dict[str, tuple[str, float, str]] = {}


def _now() -> float:
    return time.monotonic()


def _gc_locked() -> None:
    """Caller must hold _lock."""
    cutoff = _now() - _TTL_SECONDS
    for tok in [t for t, (_, ts, _) in _drafts.items() if ts < cutoff]:
        _drafts.pop(tok, None)
    for tok in [t for t, (_, ts, _) in _consumed.items() if ts < cutoff]:
        _consumed.pop(tok, None)


def put(data: Any, sender_open_id: str) -> str:
    token = secrets.token_urlsafe(16)
    with _lock:
        _gc_locked()
        _drafts[token] = (data, _now(), sender_open_id)
    return token


def put_with_token(token: str, data: Any, sender_open_id: str) -> None:
    with _lock:
        _drafts[token] = (data, _now(), sender_open_id)


def pop_draft(token: str, sender_open_id: str) -> Any | None:
    with _lock:
        _gc_locked()
        entry = _drafts.get(token)
        if entry is None:
            return None
        data, ts, sender = entry
        if sender != sender_open_id:
            return None
        if _now() - ts > _TTL_SECONDS:
            _drafts.pop(token, None)
            return None
        _drafts.pop(token, None)
        return data


def mark_consumed(token: str, po_id: str, sender_open_id: str) -> None:
    with _lock:
        _gc_locked()
        _consumed[token] = (po_id, _now(), sender_open_id)


def get_consumed_po(token: str, sender_open_id: str) -> str | None:
    with _lock:
        _gc_locked()
        entry = _consumed.get(token)
        if entry is None:
            return None
        po_id, ts, sender = entry
        if sender != sender_open_id:
            return None
        if _now() - ts > _TTL_SECONDS:
            _consumed.pop(token, None)
            return None
        return po_id


# --- Test hooks ---

def _reset_for_test() -> None:
    with _lock:
        _drafts.clear()
        _consumed.clear()


def _set_ttl_for_test(seconds: int) -> None:
    global _TTL_SECONDS
    _TTL_SECONDS = seconds
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_bot_purchase_draft_store.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add bot/purchase_draft_store.py tests/test_bot_purchase_draft_store.py
git commit -m "feat(bot): in-memory purchase-order draft store"
```

---

## Task 3: Resolver — part existence + vendor fuzzy match

**Files:**
- Create: `bot/purchase_resolver.py`
- Test: `tests/test_bot_purchase_resolver.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bot_purchase_resolver.py
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
    return create_part(db, name=name, category="吊坠", image=None)


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
    # Canonical name from DB wins
    assert result.vendor_name == "腾飞"
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
    # input "李" is len 1 → below the 2-char minimum, treat as new
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bot_purchase_resolver.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the resolver**

Create `bot/purchase_resolver.py`:

```python
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
      2. existing names that are substrings of input → pick the longest, is_new=False
      3. existing names that contain input as substring → if exactly 1, use it; if >1, ambiguous
      4. otherwise → input is new
    """
    if input_name in existing:
        return (input_name, False)

    inp = input_name.strip()
    if len(inp) < _MIN_FUZZY_LEN:
        return (input_name, True)

    eligible = [e for e in existing if len(e.strip()) >= _MIN_FUZZY_LEN]

    contained_in_input = [e for e in eligible if e in inp]
    if contained_in_input:
        # pick the longest existing name that fits inside the input
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_bot_purchase_resolver.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add bot/purchase_resolver.py tests/test_bot_purchase_resolver.py
git commit -m "feat(bot): purchase-order resolver (part lookup + vendor fuzzy match)"
```

---

## Task 4: Card renderers — pure functions returning Feishu card JSON

**Files:**
- Create: `bot/feishu_cards.py`
- Test: `tests/test_bot_feishu_cards.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bot_feishu_cards.py
import json
from decimal import Decimal

from bot.feishu_cards import (
    render_preview_card,
    render_success_card,
    render_cancel_card,
    render_parse_error_card,
    render_resolve_error_card,
    render_token_expired_card,
    render_already_created_card,
    render_system_error_card,
)
from bot.purchase_parser import ParseError
from bot.purchase_resolver import ResolvedPurchase, ResolvedItem, ResolveError


def _resolved(vendor="腾飞", is_new=False):
    items = [
        ResolvedItem(line_no=2, part_id="PJ-DZ-00001", part_name="吊坠A", part_image=None,
                     qty=Decimal("100"), unit="个", price=Decimal("5"), amount=Decimal("500")),
        ResolvedItem(line_no=3, part_id="PJ-LT-00003", part_name="链条B", part_image=None,
                     qty=Decimal("50"), unit="个", price=Decimal("3.5"), amount=Decimal("175")),
    ]
    return ResolvedPurchase(
        vendor_name=vendor, vendor_is_new=is_new, items=items,
        total_amount=Decimal("675"),
    )


def _serializable(card):
    """Round-trip through JSON to catch non-JSON-safe values (e.g. Decimal)."""
    return json.loads(json.dumps(card, ensure_ascii=False))


def test_preview_card_is_json_safe():
    card = render_preview_card(_resolved(), token="tk-1")
    _serializable(card)  # must not raise


def test_preview_card_contains_vendor_and_total():
    s = json.dumps(render_preview_card(_resolved(vendor="腾飞"), token="tk-1"), ensure_ascii=False)
    assert "腾飞" in s
    assert "675" in s


def test_preview_card_marks_new_vendor():
    s = json.dumps(render_preview_card(_resolved(is_new=True), token="tk-1"), ensure_ascii=False)
    assert "新店家" in s


def test_preview_card_does_not_mark_when_existing_vendor():
    s = json.dumps(render_preview_card(_resolved(is_new=False), token="tk-1"), ensure_ascii=False)
    assert "新店家" not in s


def test_preview_card_buttons_carry_token():
    card = render_preview_card(_resolved(), token="tk-abc")
    s = json.dumps(card, ensure_ascii=False)
    assert "tk-abc" in s
    assert "confirm" in s
    assert "cancel" in s


def test_preview_card_lists_all_items():
    s = json.dumps(render_preview_card(_resolved(), token="tk-1"), ensure_ascii=False)
    assert "PJ-DZ-00001" in s
    assert "PJ-LT-00003" in s
    assert "吊坠A" in s
    assert "链条B" in s


def test_success_card_contains_po_id_and_total():
    s = json.dumps(render_success_card("CG-0123", "腾飞", Decimal("675"), 2), ensure_ascii=False)
    assert "CG-0123" in s
    assert "675" in s
    assert "腾飞" in s


def test_parse_error_card_lists_all_errors():
    errs = [
        ParseError(line_no=2, raw_line="PJ-DZ-0001 abc 5", reason="数量无法识别：'abc'"),
        ParseError(line_no=4, raw_line="PJ-X 5 5 5 5", reason="格式错"),
    ]
    s = json.dumps(render_parse_error_card(errs), ensure_ascii=False)
    assert "第 2 行" in s
    assert "第 4 行" in s
    assert "abc" in s


def test_resolve_error_card_part_not_found():
    err = ResolveError(kind="part_not_found", detail={
        "lines": [
            {"line_no": 2, "part_id": "PJ-XX-9999", "raw_line": "PJ-XX-9999 10 5"},
            {"line_no": 3, "part_id": "PJ-YY-8888", "raw_line": "PJ-YY-8888 3 1"},
        ]
    })
    s = json.dumps(render_resolve_error_card(err), ensure_ascii=False)
    assert "PJ-XX-9999" in s
    assert "PJ-YY-8888" in s


def test_resolve_error_card_vendor_ambiguous():
    err = ResolveError(kind="vendor_ambiguous", detail={
        "input": "腾飞",
        "candidates": ["腾飞商家", "腾飞贸易"],
    })
    s = json.dumps(render_resolve_error_card(err), ensure_ascii=False)
    assert "腾飞商家" in s
    assert "腾飞贸易" in s


def test_simple_cards_are_json_safe():
    for card in [
        render_cancel_card(),
        render_token_expired_card(),
        render_already_created_card("CG-0001"),
        render_system_error_card("boom"),
    ]:
        _serializable(card)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bot_feishu_cards.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement card renderers**

Create `bot/feishu_cards.py`:

```python
"""Pure functions returning Feishu interactive-card JSON.

All Decimals are formatted via `_fmt_money` / `_fmt_qty` so the returned dict is
JSON-serialisable. Card schema follows the Feishu v2 interactive card spec.
"""
from __future__ import annotations

import json
from decimal import Decimal

from bot.purchase_parser import ParseError
from bot.purchase_resolver import ResolvedPurchase, ResolveError


def _fmt_money(d: Decimal) -> str:
    # 2-decimal display, trims trailing zeros on whole numbers, but keep 2dp for clarity
    q = d.quantize(Decimal("0.01"))
    return format(q, "f")


def _fmt_qty(d: Decimal) -> str:
    # Drop trailing zeros so 100 stays "100" rather than "100.0000"
    return format(d.normalize(), "f") if d == d.to_integral_value() else format(d, "f")


def _md(text: str) -> dict:
    return {"tag": "div", "text": {"tag": "lark_md", "content": text}}


def _hr() -> dict:
    return {"tag": "hr"}


def _header(title: str, color: str = "blue") -> dict:
    return {
        "title": {"tag": "plain_text", "content": title},
        "template": color,
    }


def render_preview_card(data: ResolvedPurchase, token: str) -> dict:
    new_marker = " ⚠ 新店家" if data.vendor_is_new else ""
    elements: list[dict] = [
        _md(f"**店家：**{data.vendor_name}{new_marker}"),
        _hr(),
        _md("**明细：**"),
    ]
    for it in data.items:
        line = (
            f"`{it.part_id}` {it.part_name}\n"
            f"　 {_fmt_qty(it.qty)} × {it.unit} × {_fmt_money(it.price)} "
            f"= **{_fmt_money(it.amount)}**"
        )
        elements.append(_md(line))
    elements.append(_hr())
    elements.append(_md(
        f"**合计：{_fmt_money(data.total_amount)} 元 / 共 {len(data.items)} 项**"
    ))
    elements.append({
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✅ 确认建单"},
                "type": "primary",
                "value": {"action": "confirm", "token": token},
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "❌ 取消"},
                "type": "default",
                "value": {"action": "cancel", "token": token},
            },
        ],
    })
    return {"header": _header("采购单预览", "blue"), "elements": elements}


def render_success_card(po_id: str, vendor: str, total: Decimal, item_count: int) -> dict:
    elements = [
        _md(f"**单号：**`{po_id}`"),
        _md(f"**店家：**{vendor}"),
        _md(f"**合计：**{_fmt_money(total)} 元 / {item_count} 项"),
    ]
    return {"header": _header("✅ 采购单已创建", "green"), "elements": elements}


def render_cancel_card() -> dict:
    return {
        "header": _header("已取消", "grey"),
        "elements": [_md("草稿已丢弃，未建单。")],
    }


def render_parse_error_card(errors: list[ParseError]) -> dict:
    lines = []
    for e in errors:
        if e.line_no == 0:
            lines.append(f"- {e.reason}")
        else:
            lines.append(f"- 第 {e.line_no} 行 `{e.raw_line}`：{e.reason}")
    return {
        "header": _header("❌ 解析失败", "red"),
        "elements": [_md("\n".join(lines))],
    }


def render_resolve_error_card(error: ResolveError) -> dict:
    if error.kind == "part_not_found":
        lines = [
            f"- 第 {row['line_no']} 行：`{row['part_id']}`"
            for row in error.detail["lines"]
        ]
        return {
            "header": _header("❌ 配件不存在", "red"),
            "elements": [_md("以下配件编号在系统中未找到：\n" + "\n".join(lines))],
        }
    if error.kind == "vendor_ambiguous":
        cands = "、".join(f"`{c}`" for c in error.detail["candidates"])
        return {
            "header": _header("❌ 店家名歧义", "red"),
            "elements": [_md(
                f"`{error.detail['input']}` 匹配到多个店家：{cands}\n请打更具体一些。"
            )],
        }
    return {
        "header": _header("❌ 校验失败", "red"),
        "elements": [_md(json.dumps(error.detail, ensure_ascii=False))],
    }


def render_token_expired_card() -> dict:
    return {
        "header": _header("⚠ 预览已失效", "orange"),
        "elements": [_md("草稿已过期（>1 小时），请重新发送消息。")],
    }


def render_already_created_card(po_id: str) -> dict:
    return {
        "header": _header("ℹ 这张单已建好", "blue"),
        "elements": [_md(f"单号：`{po_id}`")],
    }


def render_system_error_card(message: str) -> dict:
    return {
        "header": _header("❌ 系统错误", "red"),
        "elements": [_md(message)],
    }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_bot_feishu_cards.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add bot/feishu_cards.py tests/test_bot_feishu_cards.py
git commit -m "feat(bot): Feishu interactive-card renderers for purchase flow"
```

---

## Task 5: send_feishu_card helper

**Files:**
- Modify: `bot/handlers.py` (add `send_feishu_card` next to `send_feishu_message`)

This task has no new tests of its own — the function is exercised by Task 7 / Task 9 integration tests, which monkeypatch it. We add it now so later tasks can import it.

- [ ] **Step 1: Add the function**

Edit `bot/handlers.py`. Insert immediately after `send_feishu_message` (around line 38):

```python
async def send_feishu_card(chat_id: str, card: dict) -> None:
    """Send an interactive card to a Feishu chat."""
    token = await _get_tenant_access_token()
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{_FEISHU_API}/im/v1/messages?receive_id_type=chat_id",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": chat_id,
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False),
            },
        )
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from bot.handlers import send_feishu_card; print(send_feishu_card)"`
Expected: prints the function object, no error.

- [ ] **Step 3: Commit**

```bash
git add bot/handlers.py
git commit -m "feat(bot): send_feishu_card helper for interactive messages"
```

---

## Task 6: Dispatch purchase text in process_feishu_message

This task is **integration-test driven**: the simplest way to verify the wiring is to call `process_feishu_message` directly with monkeypatched senders.

**Files:**
- Modify: `bot/handlers.py` — add `_process_purchase_text` and dispatch in `process_feishu_message`; add `sender_open_id` param
- Test: `tests/test_api_feishu_purchase.py` (start the file, adds more in Task 8)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_feishu_purchase.py
import asyncio
import json
from decimal import Decimal

import pytest

from services.part import create_part


@pytest.fixture
def captured_messages(monkeypatch):
    """Monkeypatch bot.handlers.send_feishu_message and send_feishu_card.

    Returns a dict {"text": [...], "card": [...]} of captured outbound payloads.
    Also stubs _get_tenant_access_token so no network is hit.
    """
    captured = {"text": [], "card": []}

    async def fake_send_text(chat_id, text):
        captured["text"].append({"chat_id": chat_id, "text": text})

    async def fake_send_card(chat_id, card):
        captured["card"].append({"chat_id": chat_id, "card": card})

    async def fake_token():
        return "fake-token"

    import bot.handlers as h
    monkeypatch.setattr(h, "send_feishu_message", fake_send_text)
    monkeypatch.setattr(h, "send_feishu_card", fake_send_card)
    monkeypatch.setattr(h, "_get_tenant_access_token", fake_token)
    return captured


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_purchase_text_dispatches_to_preview_card(client, db, captured_messages, monkeypatch):
    # client fixture ensures the test DB is in place and dependencies overridden
    p1 = create_part(db, name="吊坠A", category="吊坠", image=None)
    p2 = create_part(db, name="链条B", category="链条", image=None)
    db.commit()

    # The handler grabs its own SessionLocal — make sure SessionLocal returns
    # our test session by reusing conftest's monkeypatching: nothing extra needed
    # because conftest already redirected database.engine to the test DB.

    from bot.handlers import process_feishu_message
    text = f"腾飞\n{p1.id} 100 5\n{p2.id} 50 3.5"
    _run(process_feishu_message(chat_id="chat-1", text=text, sender_open_id="open-1"))

    assert len(captured_messages["card"]) == 1
    card_payload = captured_messages["card"][0]
    assert card_payload["chat_id"] == "chat-1"
    serialised = json.dumps(card_payload["card"], ensure_ascii=False)
    assert "采购单预览" in serialised
    assert "腾飞" in serialised
    assert p1.id in serialised
    assert p2.id in serialised
    assert "confirm" in serialised


def test_non_purchase_text_falls_through_to_agent(client, captured_messages, monkeypatch):
    """Messages that don't look like purchases must NOT short-circuit the agent."""
    called = {"n": 0}

    async def fake_run_agent(text, db):
        called["n"] += 1
        return "agent reply"

    monkeypatch.setattr("bot.agent.runner.run_agent", fake_run_agent)

    from bot.handlers import process_feishu_message
    _run(process_feishu_message(chat_id="chat-1", text="你好", sender_open_id="open-1"))

    assert called["n"] == 1
    assert len(captured_messages["text"]) == 1
    assert captured_messages["text"][0]["text"] == "agent reply"
    assert len(captured_messages["card"]) == 0


def test_purchase_text_with_unknown_part_sends_error_card_and_creates_no_po(client, db, captured_messages):
    from bot.handlers import process_feishu_message
    from models.purchase_order import PurchaseOrder

    text = "腾飞\nPJ-XX-9999 10 5"
    _run(process_feishu_message(chat_id="chat-1", text=text, sender_open_id="open-1"))

    assert len(captured_messages["card"]) == 1
    s = json.dumps(captured_messages["card"][0]["card"], ensure_ascii=False)
    assert "配件不存在" in s
    assert "PJ-XX-9999" in s
    # No PO created
    assert db.query(PurchaseOrder).count() == 0


def test_purchase_text_with_bad_qty_sends_parse_error_card(client, db, captured_messages):
    p = create_part(db, name="吊坠A", category="吊坠", image=None)
    db.commit()

    from bot.handlers import process_feishu_message
    text = f"腾飞\n{p.id} abc 5"
    _run(process_feishu_message(chat_id="chat-1", text=text, sender_open_id="open-1"))

    assert len(captured_messages["card"]) == 1
    s = json.dumps(captured_messages["card"][0]["card"], ensure_ascii=False)
    assert "解析失败" in s
    assert "abc" in s
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_feishu_purchase.py -v`
Expected: failures — most likely `TypeError: process_feishu_message() got unexpected keyword argument 'sender_open_id'` or similar.

- [ ] **Step 3: Update `bot/handlers.py`**

Replace `process_feishu_message` and add `_process_purchase_text`. The function below is the **complete new contents** to replace the existing `process_feishu_message`:

```python
async def process_feishu_message(chat_id: str, text: str, sender_open_id: str = "") -> None:
    """Entry point for Feishu text messages.

    - Structured-purchase-shaped messages → parser/resolver path, reply with a card.
    - Anything else → original DeepSeek agent path, reply with text.
    """
    from bot.purchase_parser import is_purchase_text

    if is_purchase_text(text):
        await _process_purchase_text(chat_id, text, sender_open_id)
        return

    from database import SessionLocal
    from bot.agent.runner import run_agent

    db = SessionLocal()
    try:
        response = await run_agent(text, db)
        db.commit()
    except Exception as exc:
        logger.exception("run_agent failed: %s", exc)
        db.rollback()
        response = "处理失败，请稍后重试。"
    finally:
        db.close()

    try:
        await send_feishu_message(chat_id, response)
    except Exception as exc:
        logger.exception("send_feishu_message failed: %s", exc)


async def _process_purchase_text(chat_id: str, text: str, sender_open_id: str) -> None:
    from database import SessionLocal
    from bot.purchase_parser import parse_purchase_text, ParseError
    from bot.purchase_resolver import resolve, ResolveError
    from bot.purchase_draft_store import put
    from bot.feishu_cards import (
        render_preview_card,
        render_parse_error_card,
        render_resolve_error_card,
        render_system_error_card,
    )

    try:
        parsed = parse_purchase_text(text)
        if isinstance(parsed, list):  # list[ParseError]
            await send_feishu_card(chat_id, render_parse_error_card(parsed))
            return

        db = SessionLocal()
        try:
            result = resolve(db, parsed)
        finally:
            db.close()

        if isinstance(result, ResolveError):
            await send_feishu_card(chat_id, render_resolve_error_card(result))
            return

        token = put(result, sender_open_id=sender_open_id)
        await send_feishu_card(chat_id, render_preview_card(result, token=token))
    except Exception as exc:
        logger.exception("_process_purchase_text failed: %s", exc)
        try:
            await send_feishu_card(chat_id, render_system_error_card(str(exc)))
        except Exception:
            logger.exception("failed to send system_error_card")
```

- [ ] **Step 4: Update `api/feishu.py` to pass sender_open_id**

In `api/feishu.py`, find the line that says
`background_tasks.add_task(process_feishu_message, chat_id, text)`
and change it to:
`background_tasks.add_task(process_feishu_message, chat_id, text, open_id)`

(`open_id` is already extracted earlier in the file via `sender.get("sender_id", {}).get("open_id", "")`.)

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/test_api_feishu_purchase.py -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add bot/handlers.py api/feishu.py tests/test_api_feishu_purchase.py
git commit -m "feat(bot): dispatch structured purchase messages to preview-card flow"
```

---

## Task 7: Card action handler — confirm / cancel

**Files:**
- Create: `bot/feishu_card_handler.py`
- Modify: `tests/test_api_feishu_purchase.py` (append confirm/cancel tests)

- [ ] **Step 1: Append failing tests**

Add to `tests/test_api_feishu_purchase.py`:

```python
def _put_draft_and_get_token(db, captured_messages, vendor, part_id, qty, price):
    """Helper: send a purchase message, return the token from the preview card."""
    from bot.handlers import process_feishu_message
    text = f"{vendor}\n{part_id} {qty} {price}"
    _run(process_feishu_message(chat_id="chat-1", text=text, sender_open_id="open-1"))
    assert len(captured_messages["card"]) >= 1
    card = captured_messages["card"][-1]["card"]
    # Drill into the action element to find the token
    actions = next(e for e in card["elements"] if e.get("tag") == "action")
    return actions["actions"][0]["value"]["token"]


def test_confirm_creates_po_and_writes_inventory_log(client, db, captured_messages):
    p = create_part(db, name="吊坠A", category="吊坠", image=None)
    db.commit()

    token = _put_draft_and_get_token(db, captured_messages, "腾飞", p.id, 100, 5)
    captured_messages["card"].clear()

    from bot.feishu_card_handler import handle_card_action
    _run(handle_card_action(
        action_value={"action": "confirm", "token": token},
        sender_open_id="open-1",
        chat_id="chat-1",
    ))

    from models.purchase_order import PurchaseOrder
    from models.inventory_log import InventoryLog
    # Fresh queries on the test session
    pos = db.query(PurchaseOrder).all()
    assert len(pos) == 1
    assert pos[0].vendor_name == "腾飞"
    logs = db.query(InventoryLog).filter_by(item_id=p.id).all()
    assert len(logs) == 1
    assert logs[0].reason == "采购入库"
    assert float(logs[0].change_qty) == 100

    s = json.dumps(captured_messages["card"][0]["card"], ensure_ascii=False)
    assert "已创建" in s
    assert pos[0].id in s


def test_cancel_drops_draft_and_creates_no_po(client, db, captured_messages):
    p = create_part(db, name="吊坠A", category="吊坠", image=None)
    db.commit()
    token = _put_draft_and_get_token(db, captured_messages, "腾飞", p.id, 100, 5)
    captured_messages["card"].clear()

    from bot.feishu_card_handler import handle_card_action
    _run(handle_card_action(
        action_value={"action": "cancel", "token": token},
        sender_open_id="open-1",
        chat_id="chat-1",
    ))

    from models.purchase_order import PurchaseOrder
    assert db.query(PurchaseOrder).count() == 0
    s = json.dumps(captured_messages["card"][0]["card"], ensure_ascii=False)
    assert "已取消" in s


def test_double_confirm_returns_already_created(client, db, captured_messages):
    p = create_part(db, name="吊坠A", category="吊坠", image=None)
    db.commit()
    token = _put_draft_and_get_token(db, captured_messages, "腾飞", p.id, 100, 5)

    from bot.feishu_card_handler import handle_card_action
    _run(handle_card_action(
        action_value={"action": "confirm", "token": token},
        sender_open_id="open-1",
        chat_id="chat-1",
    ))
    captured_messages["card"].clear()
    # Second click
    _run(handle_card_action(
        action_value={"action": "confirm", "token": token},
        sender_open_id="open-1",
        chat_id="chat-1",
    ))

    from models.purchase_order import PurchaseOrder
    assert db.query(PurchaseOrder).count() == 1  # not doubled
    s = json.dumps(captured_messages["card"][0]["card"], ensure_ascii=False)
    assert "已建好" in s


def test_confirm_unknown_token_returns_expired(client, captured_messages):
    from bot.feishu_card_handler import handle_card_action
    _run(handle_card_action(
        action_value={"action": "confirm", "token": "nonexistent"},
        sender_open_id="open-1",
        chat_id="chat-1",
    ))
    s = json.dumps(captured_messages["card"][0]["card"], ensure_ascii=False)
    assert "失效" in s
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_feishu_purchase.py -v -k confirm or cancel`
Expected: `ModuleNotFoundError: No module named 'bot.feishu_card_handler'`.

- [ ] **Step 3: Implement the card handler**

Create `bot/feishu_card_handler.py`:

```python
"""Handle Feishu card.action.trigger events for the purchase-order flow."""
from __future__ import annotations

import logging

from bot.handlers import send_feishu_card
from bot.feishu_cards import (
    render_success_card,
    render_cancel_card,
    render_token_expired_card,
    render_already_created_card,
    render_system_error_card,
)
from bot.purchase_draft_store import (
    pop_draft,
    put_with_token,
    mark_consumed,
    get_consumed_po,
)

logger = logging.getLogger(__name__)


async def handle_card_action(action_value: dict, sender_open_id: str, chat_id: str) -> None:
    action = action_value.get("action")
    token = action_value.get("token", "")

    if action == "cancel":
        pop_draft(token, sender_open_id)  # discard whatever is there
        await send_feishu_card(chat_id, render_cancel_card())
        return

    if action != "confirm":
        await send_feishu_card(chat_id, render_system_error_card(f"未知操作：{action}"))
        return

    # Idempotency: token already consumed → friendly reply
    already_po = get_consumed_po(token, sender_open_id)
    if already_po is not None:
        await send_feishu_card(chat_id, render_already_created_card(already_po))
        return

    data = pop_draft(token, sender_open_id)
    if data is None:
        await send_feishu_card(chat_id, render_token_expired_card())
        return

    from database import SessionLocal
    from services.purchase_order import create_purchase_order

    db = SessionLocal()
    try:
        items_payload = [
            {
                "part_id": it.part_id,
                "qty": it.qty,
                "unit": it.unit,
                "price": it.price,
            }
            for it in data.items
        ]
        try:
            po = create_purchase_order(
                db,
                vendor_name=data.vendor_name,
                items=items_payload,
                status="未付款",
            )
            db.commit()
        except ValueError as exc:
            db.rollback()
            put_with_token(token, data, sender_open_id)
            await send_feishu_card(chat_id, render_system_error_card(str(exc)))
            return
        except Exception as exc:
            db.rollback()
            logger.exception("create_purchase_order failed: %s", exc)
            await send_feishu_card(chat_id, render_system_error_card("建单失败，请稍后重试。"))
            return
    finally:
        db.close()

    mark_consumed(token, po_id=po.id, sender_open_id=sender_open_id)
    await send_feishu_card(
        chat_id,
        render_success_card(po.id, data.vendor_name, data.total_amount, len(data.items)),
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_api_feishu_purchase.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add bot/feishu_card_handler.py tests/test_api_feishu_purchase.py
git commit -m "feat(bot): card-action handler for purchase confirm/cancel"
```

---

## Task 8: Webhook routing — dispatch on event_type

**Files:**
- Modify: `api/feishu.py` — branch on `header.event_type`
- Modify: `tests/test_api_feishu_purchase.py` (append webhook-level tests)

- [ ] **Step 1: Append failing tests**

Add to `tests/test_api_feishu_purchase.py`:

```python
def _feishu_text_event(chat_id, open_id, text, event_id="e-text-1"):
    return {
        "header": {"event_id": event_id, "event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": open_id}},
            "message": {
                "message_type": "text",
                "chat_id": chat_id,
                "content": json.dumps({"text": text}),
            },
        },
    }


def _feishu_card_action_event(chat_id, open_id, action_value, event_id="e-card-1"):
    return {
        "header": {"event_id": event_id, "event_type": "card.action.trigger"},
        "event": {
            "operator": {"open_id": open_id},
            "action": {"value": action_value},
            "context": {"open_chat_id": chat_id},
        },
    }


def test_webhook_text_event_creates_preview_card(client, db, captured_messages):
    p = create_part(db, name="吊坠A", category="吊坠", image=None)
    db.commit()

    body = _feishu_text_event("chat-1", "open-1", f"腾飞\n{p.id} 100 5")
    r = client.post("/api/feishu/webhook", json=body)
    assert r.status_code == 200

    # background_tasks runs in the same event loop under TestClient
    assert len(captured_messages["card"]) == 1
    s = json.dumps(captured_messages["card"][0]["card"], ensure_ascii=False)
    assert "采购单预览" in s


def test_webhook_card_action_confirm_creates_po(client, db, captured_messages):
    p = create_part(db, name="吊坠A", category="吊坠", image=None)
    db.commit()

    # Step 1: send the text message to generate a preview + token
    body = _feishu_text_event("chat-1", "open-1", f"腾飞\n{p.id} 100 5")
    client.post("/api/feishu/webhook", json=body)
    card = captured_messages["card"][-1]["card"]
    actions = next(e for e in card["elements"] if e.get("tag") == "action")
    token = actions["actions"][0]["value"]["token"]
    captured_messages["card"].clear()

    # Step 2: simulate the confirm button click
    body2 = _feishu_card_action_event(
        "chat-1", "open-1",
        action_value={"action": "confirm", "token": token},
        event_id="e-card-2",
    )
    r = client.post("/api/feishu/webhook", json=body2)
    assert r.status_code == 200

    from models.purchase_order import PurchaseOrder
    assert db.query(PurchaseOrder).count() == 1
    s = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "已创建" in s


def test_webhook_url_verification_returns_challenge(client):
    body = {"type": "url_verification", "challenge": "abc123"}
    r = client.post("/api/feishu/webhook", json=body)
    assert r.status_code == 200
    assert r.json() == {"challenge": "abc123"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_feishu_purchase.py -v -k webhook`
Expected: the card-action test fails (event_type unhandled); other two may pass already.

- [ ] **Step 3: Update `api/feishu.py`**

Rewrite the webhook function to branch on `event_type`. Replace the existing `feishu_webhook` body — keep the URL verification, dedup, and whitelist parts — with the version below:

```python
@router.post("/webhook")
async def feishu_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()

    if body.get("type") == "url_verification":
        return JSONResponse({"challenge": body.get("challenge")})

    header = body.get("header", {})
    event_id = header.get("event_id", "")
    event_type = header.get("event_type", "")

    if event_id:
        if event_id in _seen_event_ids:
            return JSONResponse({"code": 0})
        _seen_event_ids.add(event_id)
        if len(_seen_event_ids) > _MAX_SEEN:
            excess = list(_seen_event_ids)[: len(_seen_event_ids) - _MAX_SEEN]
            for eid in excess:
                _seen_event_ids.discard(eid)

    if event_type == "card.action.trigger":
        return await _handle_card_action_event(body, background_tasks)
    # Default: im.message.receive_v1
    return await _handle_message_event(body, background_tasks)


def _check_whitelist(open_id: str) -> bool:
    whitelist = settings.feishu_whitelist_ids
    if whitelist and open_id not in whitelist:
        logger.warning("Feishu event from unlisted user: %s", open_id)
        return False
    return True


async def _handle_message_event(body: dict, background_tasks: BackgroundTasks) -> JSONResponse:
    event = body.get("event", {})
    message = event.get("message", {})
    sender = event.get("sender", {})

    if message.get("message_type") != "text":
        return JSONResponse({"code": 0})

    open_id = sender.get("sender_id", {}).get("open_id", "")
    if not _check_whitelist(open_id):
        return JSONResponse({"code": 0})

    chat_id = message.get("chat_id", "")
    try:
        content = json.loads(message.get("content", "{}"))
        text = content.get("text", "").strip()
    except (json.JSONDecodeError, AttributeError):
        return JSONResponse({"code": 0})

    if not text or not chat_id:
        return JSONResponse({"code": 0})

    from bot.handlers import process_feishu_message
    background_tasks.add_task(process_feishu_message, chat_id, text, open_id)
    return JSONResponse({"code": 0})


async def _handle_card_action_event(body: dict, background_tasks: BackgroundTasks) -> JSONResponse:
    event = body.get("event", {})
    operator = event.get("operator", {})
    open_id = operator.get("open_id", "")
    if not _check_whitelist(open_id):
        return JSONResponse({"code": 0})

    chat_id = event.get("context", {}).get("open_chat_id", "")
    action_value = event.get("action", {}).get("value", {})
    if not chat_id or not action_value:
        return JSONResponse({"code": 0})

    from bot.feishu_card_handler import handle_card_action
    background_tasks.add_task(handle_card_action, action_value, open_id, chat_id)
    return JSONResponse({"code": 0})
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_api_feishu_purchase.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add api/feishu.py tests/test_api_feishu_purchase.py
git commit -m "feat(api): route Feishu card.action.trigger events to purchase handler"
```

---

## Task 9: Final smoke run and cleanup

- [ ] **Step 1: Run the full test suite**

Run: `pytest -x`
Expected: All tests pass. Fix any unrelated breakage immediately (likely none — all changes are additive).

- [ ] **Step 2: Smoke-check the imports**

```bash
python -c "
from bot.purchase_parser import parse_purchase_text, is_purchase_text
from bot.purchase_resolver import resolve
from bot.purchase_draft_store import put, pop_draft, mark_consumed, get_consumed_po
from bot.feishu_cards import render_preview_card
from bot.feishu_card_handler import handle_card_action
from bot.handlers import process_feishu_message, send_feishu_card
print('all imports OK')
"
```
Expected: `all imports OK`.

- [ ] **Step 3: Verify dev server still starts**

```bash
python main.py &
SERVER_PID=$!
sleep 3
curl -sf http://127.0.0.1:8000/docs > /dev/null && echo "server OK" || echo "server FAILED"
kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null
```
Expected: prints `server OK`. No schema errors at startup (no DB migration involved).

- [ ] **Step 4: Final commit (if anything trailing)**

If there are no further code changes, skip this step. Otherwise:
```bash
git status
# stage and commit any leftover changes with a clear message
```

---

## Out of Scope (per spec)

The following are explicitly NOT in this plan. If you find yourself implementing them, stop and confirm with the user:

- Editing an existing purchase order (add/remove items, change price, change status) via bot
- Marking payment / uploading delivery images / item notes via bot
- Photo-based purchase creation (Vision)
- Inline editing on the preview card (cancel + resend is the workflow)
- Telegram inline-keyboard equivalent (planned for follow-up)
- Disambiguation buttons for the `vendor_ambiguous` case (currently asks user to retype)
