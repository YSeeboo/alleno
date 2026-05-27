# 飞书 bot 采购单名称解析 + 消歧 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users type a part NAME (not just the ID) when building a purchase order in Feishu; resolve names via fuzzy match, and when a name matches multiple parts, ask the user to pick via per-line disambiguation cards.

**Architecture:** Extend the existing resolver to a three-way outcome (resolved / needs-disambiguation / error) with per-line id→name-exact→name-fuzzy lookup. A single draft token threads through "disambiguating → ready → created": each disambiguation button click records a choice and advances; once all ambiguities are resolved, the draft becomes a normal `ResolvedPurchase` and the existing preview/confirm flow takes over.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, Decimal. Reuses `services/_helpers.py:keyword_filter` for ILIKE name search. No DB migration, no new env.

**Spec:** `docs/superpowers/specs/2026-05-27-bot-purchase-name-resolution-design.md`

**Branch:** `feature/bot-purchase-name-resolution` (already created). Use `/Users/ycb/workspace/allen_shop/.venv/bin/pytest` (system python lacks zoneinfo). PostgreSQL is up; test DB `allen_shop_test` exists.

---

## File Map

- `bot/purchase_resolver.py` (modify) — name resolution; new `Candidate`/`PendingLine`/`NeedsDisambiguation`; three-way `resolve`; helpers `assemble_resolved`, `first_unresolved`
- `bot/purchase_draft_store.py` (modify) — add `get_draft` (peek)
- `bot/feishu_cards.py` (modify) — add `render_disambiguation_card`
- `bot/handlers.py` (modify) — `_process_purchase_text` handles `NeedsDisambiguation`
- `bot/feishu_card_handler.py` (modify) — `handle_card_action` adds `disambiguate` branch
- Tests: extend `tests/test_bot_purchase_resolver.py`, `tests/test_bot_purchase_draft_store.py`, `tests/test_bot_feishu_cards.py`, `tests/test_api_feishu_purchase.py`

---

## Task 1: Resolver — name resolution + three-way result

**Files:**
- Modify: `bot/purchase_resolver.py`
- Test: `tests/test_bot_purchase_resolver.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_bot_purchase_resolver.py`)

```python
# add to the imports already at the top of the file (Decimal is already imported there)
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
    # "玫瑰吊坠" is a substring of the only part name → unique fuzzy hit
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
    assert ids == sorted(ids)  # candidates sorted by part_id
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
    # one ambiguous line + one not-found line → not_found wins
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
    # items sorted by line_no: line 2 (珍珠链条) then line 3 (chosen 玫瑰吊坠大)
    assert [i.line_no for i in resolved.items] == [2, 3]
    assert [i.part_id for i in resolved.items] == [uniq.id, a1.id]
    assert resolved.total_amount == Decimal("25")  # 5*1 + 10*2


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
```

(Note: `小配件` is a valid category — see `services/part.py:PART_CATEGORIES`. If a test category is rejected, check that dict and use a valid Chinese key.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_bot_purchase_resolver.py -k "name or ambiguous or assemble or first_unresolved or candidate" -v`
Expected: ImportError on `NeedsDisambiguation` / `Candidate` / `assemble_resolved` / `first_unresolved`.

- [ ] **Step 3: Rewrite `bot/purchase_resolver.py`**

Keep `ResolvedItem`, `ResolvedPurchase`, `ResolveError`, `_match_vendor`, `_MIN_FUZZY_LEN` unchanged. Add the new dataclasses and rewrite `resolve`; add helpers. Full new file:

```python
"""Resolve a parsed purchase against the DB.

Per-line part resolution priority: id exact -> name exact -> name fuzzy (ILIKE).
Vendor name resolved via exact / bidirectional substring fuzzy match.
Outcome is three-way: ResolvedPurchase (all unique) / NeedsDisambiguation
(some names match multiple parts) / ResolveError (a name matched nothing, or
the vendor name is ambiguous).
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
```

- [ ] **Step 4: Run the full resolver test file** (new + existing must all pass)

Run: `/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_bot_purchase_resolver.py -v`
Expected: all pass (existing id/vendor tests still green — id path via `db.get` is unchanged behaviour; vendor logic untouched).

- [ ] **Step 5: Commit**

```bash
git add bot/purchase_resolver.py tests/test_bot_purchase_resolver.py
git commit -m "feat(bot): name resolution + three-way resolve (disambiguation)"
```

---

## Task 2: Draft store — get_draft (peek)

**Files:**
- Modify: `bot/purchase_draft_store.py`
- Test: `tests/test_bot_purchase_draft_store.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_bot_purchase_draft_store.py`)

```python
from bot.purchase_draft_store import get_draft


def test_get_draft_peeks_without_removing():
    token = put(_draft(), sender_open_id="open-1")
    assert get_draft(token, "open-1") == _draft()
    # still there on a second peek
    assert get_draft(token, "open-1") == _draft()
    # and still poppable
    assert pop_draft(token, "open-1") == _draft()


def test_get_draft_wrong_sender_returns_none():
    token = put(_draft(), sender_open_id="open-1")
    assert get_draft(token, "open-2") is None


def test_get_draft_expired_returns_none():
    _set_ttl_for_test(0)
    token = put(_draft(), sender_open_id="open-1")
    time.sleep(0.01)
    assert get_draft(token, "open-1") is None


def test_get_draft_unknown_token_returns_none():
    assert get_draft("nope", "open-1") is None
```

- [ ] **Step 2: Run to verify fail**

Run: `/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_bot_purchase_draft_store.py -k get_draft -v`
Expected: ImportError on `get_draft`.

- [ ] **Step 3: Add `get_draft`** to `bot/purchase_draft_store.py` (insert after `pop_draft`)

```python
def get_draft(token: str, sender_open_id: str) -> Any | None:
    """Peek at a draft without removing it. Returns None on miss / expiry / sender mismatch."""
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
        return data
```

- [ ] **Step 4: Run to verify pass**

Run: `/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_bot_purchase_draft_store.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bot/purchase_draft_store.py tests/test_bot_purchase_draft_store.py
git commit -m "feat(bot): get_draft peek for disambiguation flow"
```

---

## Task 3: Card — render_disambiguation_card

**Files:**
- Modify: `bot/feishu_cards.py`
- Test: `tests/test_bot_feishu_cards.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_bot_feishu_cards.py`)

```python
from bot.purchase_resolver import PendingLine, Candidate
from bot.feishu_cards import render_disambiguation_card
from decimal import Decimal


def _pending():
    return PendingLine(
        line_no=2,
        query="玫瑰吊坠",
        qty=Decimal("10"),
        unit="个",
        price=Decimal("5"),
        candidates=[
            Candidate(part_id="PJ-DZ-00001", part_name="玫瑰吊坠大", spec="18mm", part_image=None),
            Candidate(part_id="PJ-DZ-00002", part_name="玫瑰吊坠小", spec=None, part_image=None),
        ],
    )


def test_disambiguation_card_json_safe():
    _serializable(render_disambiguation_card(_pending(), token="tk-1", done=0, total=2))


def test_disambiguation_card_shows_query_and_progress():
    s = json.dumps(render_disambiguation_card(_pending(), token="tk-1", done=0, total=2), ensure_ascii=False)
    assert "玫瑰吊坠" in s
    assert "第 2 行" in s
    assert "1/2" in s  # done+1 / total


def test_disambiguation_card_buttons_carry_line_no_and_part_id():
    card = render_disambiguation_card(_pending(), token="tk-abc", done=0, total=2)
    s = json.dumps(card, ensure_ascii=False)
    assert "tk-abc" in s
    assert "disambiguate" in s
    assert "PJ-DZ-00001" in s
    assert "PJ-DZ-00002" in s
    # spec shown to distinguish series
    assert "18mm" in s
    # locate an action element with buttons carrying line_no
    action = next(e for e in card["elements"] if e.get("tag") == "action")
    v = action["actions"][0]["value"]
    assert v["action"] == "disambiguate"
    assert v["line_no"] == 2
    assert v["part_id"] in ("PJ-DZ-00001", "PJ-DZ-00002")
```

- [ ] **Step 2: Run to verify fail**

Run: `/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_bot_feishu_cards.py -k disambiguation -v`
Expected: ImportError on `render_disambiguation_card`.

- [ ] **Step 3: Implement** — in `bot/feishu_cards.py`, extend the import line and add the renderer.

Change the import near the top:
```python
from bot.purchase_resolver import ResolvedPurchase, ResolveError, PendingLine
```

Add the function (after `render_preview_card`):
```python
def render_disambiguation_card(pending: PendingLine, token: str, done: int, total: int) -> dict:
    elements: list[dict] = [
        _md(
            f"**第 {pending.line_no} 行 “{pending.query}” 命中 {len(pending.candidates)} 个，选哪个？**"
        ),
        _md(
            f"（数量 {_fmt_qty(pending.qty)} × 单价 {_fmt_money(pending.price)}）　进度 {done + 1}/{total}"
        ),
    ]
    buttons = []
    for c in pending.candidates:
        spec_part = f"({c.spec})" if c.spec else ""
        buttons.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": f"{c.part_id} {c.part_name}{spec_part}"},
            "type": "default",
            "value": {
                "action": "disambiguate",
                "token": token,
                "line_no": pending.line_no,
                "part_id": c.part_id,
            },
        })
    elements.append({"tag": "action", "actions": buttons})
    return {"header": _header("需要确认", "orange"), "elements": elements}
```

- [ ] **Step 4: Run to verify pass**

Run: `/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_bot_feishu_cards.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bot/feishu_cards.py tests/test_bot_feishu_cards.py
git commit -m "feat(bot): disambiguation card renderer"
```

---

## Task 4: Dispatch — _process_purchase_text handles NeedsDisambiguation

**Files:**
- Modify: `bot/handlers.py`
- Test: `tests/test_api_feishu_purchase.py`

- [ ] **Step 1: Write failing test** (append to `tests/test_api_feishu_purchase.py`)

```python
def test_ambiguous_name_sends_disambiguation_card(client, db, captured_messages):
    create_part(db, {"name": "玫瑰吊坠大", "category": "吊坠"})
    create_part(db, {"name": "玫瑰吊坠小", "category": "吊坠"})
    db.commit()

    from bot.handlers import process_feishu_message
    text = "腾飞\n玫瑰吊坠 10 5"
    _run(process_feishu_message(chat_id="chat-1", text=text, sender_open_id="open-1"))

    assert len(captured_messages["card"]) == 1
    s = json.dumps(captured_messages["card"][0]["card"], ensure_ascii=False)
    assert "需要确认" in s
    assert "玫瑰吊坠" in s
    assert "disambiguate" in s


def test_unique_name_goes_straight_to_preview(client, db, captured_messages):
    create_part(db, {"name": "珍珠链条", "category": "链条"})
    db.commit()
    from bot.handlers import process_feishu_message
    _run(process_feishu_message(chat_id="chat-1", text="腾飞\n珍珠链条 10 5", sender_open_id="open-1"))
    s = json.dumps(captured_messages["card"][0]["card"], ensure_ascii=False)
    assert "采购单预览" in s
```

- [ ] **Step 2: Run to verify fail**

Run: `/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_feishu_purchase.py -k "ambiguous_name or unique_name" -v`
Expected: `test_ambiguous_name...` fails (currently a NeedsDisambiguation would hit the `_process_purchase_text` exception path or mis-render).

- [ ] **Step 3: Update `_process_purchase_text`** in `bot/handlers.py`.

Replace the body's imports and the result-handling block. The new function:

```python
async def _process_purchase_text(chat_id: str, text: str, sender_open_id: str) -> None:
    from database import SessionLocal
    from bot.purchase_parser import parse_purchase_text
    from bot.purchase_resolver import resolve, ResolveError, NeedsDisambiguation, first_unresolved
    from bot.purchase_draft_store import put
    from bot.feishu_cards import (
        render_preview_card,
        render_parse_error_card,
        render_resolve_error_card,
        render_system_error_card,
        render_disambiguation_card,
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

        if isinstance(result, NeedsDisambiguation):
            pl, done, total = first_unresolved(result)
            await send_feishu_card(chat_id, render_disambiguation_card(pl, token, done, total))
            return

        # ResolvedPurchase
        await send_feishu_card(chat_id, render_preview_card(result, token=token))
    except Exception as exc:
        logger.exception("_process_purchase_text failed: %s", exc)
        try:
            await send_feishu_card(chat_id, render_system_error_card("系统错误，请稍后重试"))
        except Exception:
            logger.exception("failed to send system_error_card")
```

- [ ] **Step 4: Run to verify pass** (and no regression in the file)

Run: `/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_feishu_purchase.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bot/handlers.py tests/test_api_feishu_purchase.py
git commit -m "feat(bot): route ambiguous-name purchases to disambiguation card"
```

---

## Task 5: Card action — disambiguate branch (state machine)

**Files:**
- Modify: `bot/feishu_card_handler.py`
- Test: `tests/test_api_feishu_purchase.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_api_feishu_purchase.py`)

```python
def _seed_ambiguous(db, base, qty, price, *suffixes):
    """Create parts named base+suffix; return their ids in creation order."""
    ids = []
    for suf in suffixes:
        cat = "吊坠"
        ids.append(create_part(db, {"name": f"{base}{suf}", "category": cat}).id)
    return ids


def _send_and_get_disambig_token(db, captured_messages, text):
    from bot.handlers import process_feishu_message
    _run(process_feishu_message(chat_id="chat-1", text=text, sender_open_id="open-1"))
    card = captured_messages["card"][-1]["card"]
    action = next(e for e in card["elements"] if e.get("tag") == "action")
    return action["actions"][0]["value"]["token"]


def test_single_line_disambiguation_to_preview_then_confirm(client, db, captured_messages):
    ids = _seed_ambiguous(db, "玫瑰吊坠", 10, 5, "大", "小")
    db.commit()
    token = _send_and_get_disambig_token(db, captured_messages, "腾飞\n玫瑰吊坠 10 5")
    captured_messages["card"].clear()

    from bot.feishu_card_handler import handle_card_action
    # pick the first candidate
    _run(handle_card_action(
        action_value={"action": "disambiguate", "token": token, "line_no": 2, "part_id": ids[0]},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    # should now be the preview card
    s = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "采购单预览" in s

    captured_messages["card"].clear()
    _run(handle_card_action(
        action_value={"action": "confirm", "token": token},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    from models.purchase_order import PurchaseOrder
    db.expire_all()
    pos = db.query(PurchaseOrder).all()
    assert len(pos) == 1
    s2 = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "已创建" in s2


def test_two_ambiguous_lines_take_two_picks(client, db, captured_messages):
    rose = _seed_ambiguous(db, "玫瑰吊坠", 0, 0, "大", "小")
    pearl = _seed_ambiguous(db, "珍珠扣", 0, 0, "大", "小")
    db.commit()
    token = _send_and_get_disambig_token(db, captured_messages, "腾飞\n玫瑰吊坠 10 5\n珍珠扣 20 2")

    from bot.feishu_card_handler import handle_card_action
    # first pick → still a disambiguation card (for line 3)
    captured_messages["card"].clear()
    _run(handle_card_action(
        action_value={"action": "disambiguate", "token": token, "line_no": 2, "part_id": rose[0]},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    s1 = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "需要确认" in s1
    assert "珍珠扣" in s1

    # second pick → preview
    captured_messages["card"].clear()
    _run(handle_card_action(
        action_value={"action": "disambiguate", "token": token, "line_no": 3, "part_id": pearl[0]},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    s2 = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "采购单预览" in s2


def test_disambiguate_expired_token(client, captured_messages):
    from bot.feishu_card_handler import handle_card_action
    _run(handle_card_action(
        action_value={"action": "disambiguate", "token": "nope", "line_no": 2, "part_id": "x"},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    s = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "失效" in s


def test_disambiguate_forged_part_id_ignored(client, db, captured_messages):
    ids = _seed_ambiguous(db, "玫瑰吊坠", 0, 0, "大", "小")
    db.commit()
    token = _send_and_get_disambig_token(db, captured_messages, "腾飞\n玫瑰吊坠 10 5")
    captured_messages["card"].clear()

    from bot.feishu_card_handler import handle_card_action
    # part_id not among candidates → ignored, still disambiguation card
    _run(handle_card_action(
        action_value={"action": "disambiguate", "token": token, "line_no": 2, "part_id": "PJ-FAKE-99999"},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    s = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "需要确认" in s  # still asking, not advanced


def test_disambiguate_repeat_pick_is_idempotent(client, db, captured_messages):
    ids = _seed_ambiguous(db, "玫瑰吊坠", 0, 0, "大", "小")
    db.commit()
    token = _send_and_get_disambig_token(db, captured_messages, "腾飞\n玫瑰吊坠 10 5")

    from bot.feishu_card_handler import handle_card_action
    for _ in range(2):
        _run(handle_card_action(
            action_value={"action": "disambiguate", "token": token, "line_no": 2, "part_id": ids[0]},
            sender_open_id="open-1", chat_id="chat-1",
        ))
    # both times end at preview; confirm builds exactly one PO
    _run(handle_card_action(
        action_value={"action": "confirm", "token": token},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    from models.purchase_order import PurchaseOrder
    db.expire_all()
    assert db.query(PurchaseOrder).count() == 1
```

- [ ] **Step 2: Run to verify fail**

Run: `/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_feishu_purchase.py -k "disambigu or two_ambiguous or forged or repeat_pick" -v`
Expected: fails — `disambiguate` action falls into the `action != "confirm"` branch returning "未知操作".

- [ ] **Step 3: Add the `disambiguate` branch** to `bot/feishu_card_handler.py`.

Add imports at top (extend existing import groups):
```python
from bot.feishu_cards import (
    render_success_card,
    render_cancel_card,
    render_token_expired_card,
    render_already_created_card,
    render_system_error_card,
    render_create_failed_card,
    render_preview_card,
    render_disambiguation_card,
)
from bot.purchase_draft_store import (
    pop_draft,
    put_with_token,
    mark_consumed,
    get_consumed_po,
    get_draft,
)
from bot.purchase_resolver import (
    NeedsDisambiguation,
    ResolvedPurchase,
    assemble_resolved,
    first_unresolved,
)
```

In `handle_card_action`, add the branch right after the `cancel` block (before the `action != "confirm"` guard):
```python
    if action == "disambiguate":
        await _handle_disambiguate(action_value, sender_open_id, chat_id)
        return
```

Add the handler function at module level:
```python
async def _handle_disambiguate(action_value: dict, sender_open_id: str, chat_id: str) -> None:
    token = action_value.get("token", "")
    line_no = action_value.get("line_no")
    part_id = action_value.get("part_id")

    draft = get_draft(token, sender_open_id)
    if draft is None:
        await _handlers.send_feishu_card(chat_id, render_token_expired_card())
        return

    # Stale tap after the flow already advanced to preview → re-show preview.
    if isinstance(draft, ResolvedPurchase):
        await _handlers.send_feishu_card(chat_id, render_preview_card(draft, token=token))
        return
    if not isinstance(draft, NeedsDisambiguation):
        await _handlers.send_feishu_card(chat_id, render_token_expired_card())
        return

    # Apply the choice if the line is still pending and the part_id is a real candidate.
    pl = next((p for p in draft.pending if p.line_no == line_no), None)
    if pl is not None and pl.chosen_part_id is None:
        if any(c.part_id == part_id for c in pl.candidates):
            pl.chosen_part_id = part_id
    put_with_token(token, draft, sender_open_id)

    nxt = first_unresolved(draft)
    if nxt is not None:
        next_pl, done, total = nxt
        await _handlers.send_feishu_card(
            chat_id, render_disambiguation_card(next_pl, token, done, total)
        )
        return

    # All resolved → assemble final purchase, store under same token, show preview.
    from database import SessionLocal
    db = SessionLocal()
    try:
        resolved = assemble_resolved(db, draft)
    finally:
        db.close()
    put_with_token(token, resolved, sender_open_id)
    await _handlers.send_feishu_card(chat_id, render_preview_card(resolved, token=token))
```

- [ ] **Step 4: Run the full feishu test file**

Run: `/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_api_feishu_purchase.py -v`
Expected: all pass (existing confirm/cancel/token tests still green).

- [ ] **Step 5: Commit**

```bash
git add bot/feishu_card_handler.py tests/test_api_feishu_purchase.py
git commit -m "feat(bot): disambiguate card-action state machine"
```

---

## Task 6: Final smoke

- [ ] **Step 1: Run all bot/feishu tests**

Run:
```bash
/Users/ycb/workspace/allen_shop/.venv/bin/pytest tests/test_bot_purchase_parser.py tests/test_bot_purchase_draft_store.py tests/test_bot_purchase_resolver.py tests/test_bot_feishu_cards.py tests/test_api_feishu_purchase.py -q
```
Expected: all green.

- [ ] **Step 2: Smoke imports**

```bash
/Users/ycb/workspace/allen_shop/.venv/bin/python -c "
from bot.purchase_resolver import resolve, NeedsDisambiguation, Candidate, PendingLine, assemble_resolved, first_unresolved
from bot.purchase_draft_store import get_draft
from bot.feishu_cards import render_disambiguation_card
from bot.feishu_card_handler import handle_card_action, _handle_disambiguate
print('imports OK')
"
```
Expected: `imports OK`.

- [ ] **Step 3: Commit** (only if anything trailing; otherwise skip)

---

## Out of Scope (per spec)

Do NOT implement: combined disambiguation card, auto-pick-best, recency/frequency candidate ordering, name resolution for plating/handcraft, agent/natural-language input. If tempted, stop and confirm with the user.
