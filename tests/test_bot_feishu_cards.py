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
    _serializable(card)


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


def test_create_failed_card_is_json_safe_and_contains_message():
    from bot.feishu_cards import render_create_failed_card
    card = render_create_failed_card("oops")
    _serializable(card)
    s = json.dumps(card, ensure_ascii=False)
    assert "建单失败" in s
    assert "oops" in s


def _pending():
    from bot.purchase_resolver import PendingLine, Candidate
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
    from bot.feishu_cards import render_disambiguation_card
    _serializable(render_disambiguation_card(_pending(), token="tk-1", done=0, total=2))


def test_disambiguation_card_shows_query_and_progress():
    from bot.feishu_cards import render_disambiguation_card
    s = json.dumps(render_disambiguation_card(_pending(), token="tk-1", done=0, total=2), ensure_ascii=False)
    assert "玫瑰吊坠" in s
    assert "第 2 行" in s
    assert "1/2" in s


def test_disambiguation_card_buttons_carry_line_no_and_part_id():
    from bot.feishu_cards import render_disambiguation_card
    card = render_disambiguation_card(_pending(), token="tk-abc", done=0, total=2)
    s = json.dumps(card, ensure_ascii=False)
    assert "tk-abc" in s
    assert "disambiguate" in s
    assert "PJ-DZ-00001" in s and "PJ-DZ-00002" in s
    assert "18mm" in s
    action = next(e for e in card["elements"] if e.get("tag") == "action")
    v = action["actions"][0]["value"]
    assert v["action"] == "disambiguate"
    assert v["line_no"] == 2
    assert v["part_id"] in ("PJ-DZ-00001", "PJ-DZ-00002")
