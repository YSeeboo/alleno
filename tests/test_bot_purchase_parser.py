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
    # First line item-shaped is still routed here so we can produce a "首行不像店家名"
    # error rather than confusing agent-LLM noise.
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
    text = "李老板\nPJ-DZ-0001 100"
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


def test_parse_price_zero_is_accepted():
    text = "李老板\nPJ-DZ-0001 100 0"
    result = parse_purchase_text(text)
    assert isinstance(result, ParsedPurchase)
    assert result.items[0].price == Decimal("0")


def test_parse_trailing_currency_word_4_tokens():
    result = parse_purchase_text("腾飞\nPJ-LT-00003 50 3.5 元")
    assert isinstance(result, ParsedPurchase), result
    item = result.items[0]
    assert item.qty == Decimal("50")
    assert item.unit == "个"
    assert item.price == Decimal("3.5")


def test_parse_unit_and_trailing_currency_word_5_tokens():
    result = parse_purchase_text("腾飞\nPJ-LT-00003 50 件 3.5 元")
    assert isinstance(result, ParsedPurchase), result
    item = result.items[0]
    assert item.qty == Decimal("50")
    assert item.unit == "件"
    assert item.price == Decimal("3.5")
