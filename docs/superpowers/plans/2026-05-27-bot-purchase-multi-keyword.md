# 飞书 bot 采购单多关键字（右锚定解析）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a purchase line carry a multi-keyword name (e.g. `玫瑰 大 100 5`) by parsing right-anchored — the trailing tokens are qty/[unit]/price, everything before is the name search string fed to `keyword_filter`.

**Architecture:** Rewrite `bot/purchase_parser.py`'s `_parse_item` from left-positional to right-anchored, and replace the dispatch heuristic `_ITEM_FIRST_TOKEN_RE` with `_looks_like_item_line` ("line ends with qty+price", plus the existing PJ- fallback). The resolver, draft store, cards, and card handler are unchanged — `keyword_filter` already does multi-keyword AND matching, so a multi-word name string flows straight through.

**Tech Stack:** Python, pytest, Decimal. No DB migration, no new deps.

**Spec:** `docs/superpowers/specs/2026-05-27-bot-purchase-multi-keyword-design.md`

**Branch:** `feature/bot-purchase-multi-keyword` (already created). Use `/Users/ycb/workspace/allen_shop/.venv/bin/pytest` (system python lacks zoneinfo). PG is up; test DB `allen_shop_test` exists.

---

## File Map

- `bot/purchase_parser.py` (modify) — right-anchored `_parse_item`; new `_glue_trailing_currency`, `_looks_like_item_line`; `is_purchase_text` + vendor-line check use the new predicate; remove `_ITEM_FIRST_TOKEN_RE`.
- Tests: `tests/test_bot_purchase_parser.py` (extend), `tests/test_bot_purchase_resolver.py` (extend), `tests/test_api_feishu_purchase.py` (extend).

Resolver / draft store / cards / handler: NO changes.

---

## Task 1: Right-anchored parser + multi-keyword names

**Files:**
- Modify: `bot/purchase_parser.py`
- Test: `tests/test_bot_purchase_parser.py`

- [ ] **Step 1: Append failing tests to `tests/test_bot_purchase_parser.py`**

(The file already imports `is_purchase_text, parse_purchase_text, ParsedPurchase, ParsedItem, ParseError` and `Decimal` at the top.)

```python
def test_parse_multi_keyword_name():
    result = parse_purchase_text("腾飞\n玫瑰 大 100 5")
    assert isinstance(result, ParsedPurchase), result
    item = result.items[0]
    assert item.part_id == "玫瑰 大"
    assert item.qty == Decimal("100")
    assert item.unit == "个"
    assert item.price == Decimal("5")


def test_parse_multi_keyword_with_unit():
    result = parse_purchase_text("腾飞\n玫瑰吊坠 镂空 50 件 3")
    assert isinstance(result, ParsedPurchase), result
    item = result.items[0]
    assert item.part_id == "玫瑰吊坠 镂空"
    assert item.unit == "件"
    assert item.qty == Decimal("50")
    assert item.price == Decimal("3")


def test_parse_name_first_token_is_unit_word():
    # "包" is a unit word but here it's the first name token, not the unit slot
    result = parse_purchase_text("腾飞\n包 玫瑰 100 5")
    assert isinstance(result, ParsedPurchase), result
    assert result.items[0].part_id == "包 玫瑰"
    assert result.items[0].unit == "个"
    assert result.items[0].qty == Decimal("100")


def test_parse_qty_position_non_numeric_errors():
    # "玫瑰 大 5": name=玫瑰, qty=大 (fails), price=5
    result = parse_purchase_text("腾飞\n玫瑰 大 5")
    assert isinstance(result, list)
    assert result[0].line_no == 2
    assert "数量" in result[0].reason


def test_is_purchase_text_recognises_multi_keyword_line():
    assert is_purchase_text("腾飞\n玫瑰 大 100 5") is True


def test_is_purchase_text_still_rejects_natural_language():
    assert is_purchase_text("帮我看看玫瑰吊坠\n还有多少库存") is False
```

- [ ] **Step 2: Run to verify the NEW tests fail (and note which existing ones the rewrite must keep)**

Run: `/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_bot_purchase_parser.py -k "multi_keyword or first_token_is_unit or qty_position_non_numeric" -v`
Expected: these fail under the current left-positional parser (e.g. `玫瑰 大 100 5` parses `part_id=玫瑰, qty=大` → error, or wrong token count).

- [ ] **Step 3: Rewrite the parsing internals in `bot/purchase_parser.py`**

Replace the module from the `_ITEM_FIRST_TOKEN_RE` definition down through `_parse_item` (keep the dataclasses, `_QTY_SUFFIXES`, `_PRICE_SUFFIXES`, `_PART_ID_TOKEN_RE`, `_strip_suffix`, `_parse_decimal`, and `parse_purchase_text` — except the one vendor-check line noted below).

Remove this line (the old left-positional detector):
```python
# Item-shape detector: a part_id followed by a digit (any unit/suffix tail allowed).
_ITEM_FIRST_TOKEN_RE = re.compile(r"^\S+\s+\d")
```

Keep `_PART_ID_TOKEN_RE` as-is. Replace `is_purchase_text` and `_parse_item`, and add two helpers `_glue_trailing_currency` and `_looks_like_item_line`:

```python
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
    parse-error card instead of falling through to the agent)."""
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
```

And the new `_parse_item` (right-anchored):
```python
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
```

Finally, in `parse_purchase_text`, replace the vendor-line check:
```python
    if _ITEM_FIRST_TOKEN_RE.match(vendor_name):
```
with:
```python
    if _looks_like_item_line(vendor_name):
```

- [ ] **Step 4: Run the FULL parser test file** (new + all existing must pass)

Run: `/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_bot_purchase_parser.py -v`
Expected: all pass. The existing back-compat cases (`PJ-DZ-0001 100 5`, `... 100 件 5`, `... 3.5 元`, `100个`, bad qty/price, wrong-token-count, first-line-looks-like-item, multi-item, blank lines, price 0) all resolve identically under right-anchored parsing.

- [ ] **Step 5: Commit**

```bash
git add bot/purchase_parser.py tests/test_bot_purchase_parser.py
git commit -m "feat(bot): right-anchored parsing for multi-keyword purchase names"
```

---

## Task 2: Verify multi-keyword narrows candidates (resolver + integration)

No production code changes — `keyword_filter` already handles multi-keyword. These tests lock in the end-to-end behaviour.

**Files:**
- Test: `tests/test_bot_purchase_resolver.py`, `tests/test_api_feishu_purchase.py`

- [ ] **Step 1: Append a resolver test to `tests/test_bot_purchase_resolver.py`**

(Reuses existing `_parsed`, `create_part`.)

```python
def test_resolve_multi_keyword_narrows_to_unique(db):
    create_part(db, {"name": "玫瑰吊坠大", "category": "吊坠"})
    create_part(db, {"name": "玫瑰吊坠小", "category": "吊坠"})
    db.commit()
    # single keyword "玫瑰吊坠" would be ambiguous; "玫瑰吊坠 大" narrows to one
    result = resolve(db, _parsed("店家", ("玫瑰吊坠 大", 1, 1)))
    assert isinstance(result, ResolvedPurchase)
    assert result.items[0].part_name == "玫瑰吊坠大"
```

- [ ] **Step 2: Append an integration test to `tests/test_api_feishu_purchase.py`**

(Reuses `captured_messages`, `_run`, `create_part`.)

```python
def test_multi_keyword_message_narrows_to_preview(client, db, captured_messages):
    create_part(db, {"name": "玫瑰吊坠大", "category": "吊坠"})
    create_part(db, {"name": "玫瑰吊坠小", "category": "吊坠"})
    db.commit()
    from bot.handlers import process_feishu_message
    # two keywords on the name → unique → straight to preview, no disambiguation
    _run(process_feishu_message(chat_id="chat-1", text="腾飞\n玫瑰吊坠 大 10 5", sender_open_id="open-1"))
    s = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "采购单预览" in s
    assert "玫瑰吊坠大" in s
    assert "需要确认" not in s
```

- [ ] **Step 3: Run both test files**

Run: `/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_bot_purchase_resolver.py tests/test_api_feishu_purchase.py -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_bot_purchase_resolver.py tests/test_api_feishu_purchase.py
git commit -m "test(bot): multi-keyword name narrows candidates end-to-end"
```

---

## Task 3: Final smoke

- [ ] **Step 1: Full feature suite**

Run:
```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_bot_purchase_parser.py tests/test_bot_purchase_draft_store.py tests/test_bot_purchase_resolver.py tests/test_bot_feishu_cards.py tests/test_api_feishu_purchase.py -q
```
Expected: all green.

- [ ] **Step 2: Smoke import**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/python -c "from bot.purchase_parser import is_purchase_text, parse_purchase_text, _looks_like_item_line, _glue_trailing_currency; print('ok')"
```
Expected: `ok`.

---

## Out of Scope (per spec)

No recency/weight candidate ordering, no thumbnails, no plating/handcraft, no agent. The resolver/store/cards/handler are NOT modified. If a change seems to need touching them, stop and confirm.
