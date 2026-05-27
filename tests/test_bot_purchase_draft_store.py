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


def test_get_draft_peeks_without_removing():
    from bot.purchase_draft_store import get_draft
    token = put(_draft(), sender_open_id="open-1")
    assert get_draft(token, "open-1") == _draft()
    assert get_draft(token, "open-1") == _draft()  # still there
    assert pop_draft(token, "open-1") == _draft()   # and still poppable


def test_get_draft_wrong_sender_returns_none():
    from bot.purchase_draft_store import get_draft
    token = put(_draft(), sender_open_id="open-1")
    assert get_draft(token, "open-2") is None


def test_get_draft_expired_returns_none():
    from bot.purchase_draft_store import get_draft
    _set_ttl_for_test(0)
    token = put(_draft(), sender_open_id="open-1")
    time.sleep(0.01)
    assert get_draft(token, "open-1") is None


def test_get_draft_unknown_token_returns_none():
    from bot.purchase_draft_store import get_draft
    assert get_draft("nope", "open-1") is None
