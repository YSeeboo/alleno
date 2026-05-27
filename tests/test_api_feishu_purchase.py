import asyncio
import json
from decimal import Decimal

import pytest

from services.part import create_part


@pytest.fixture
def captured_messages(monkeypatch):
    """Monkeypatch outbound Feishu calls. Returns captured payloads."""
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


@pytest.fixture(autouse=True)
def _clear_event_dedup():
    """The webhook's _seen_event_ids is process-level state. Clear it between
    tests so a reused default event_id can't be silently deduped (flaky)."""
    import api.feishu as feishu
    feishu._seen_event_ids.clear()
    yield
    feishu._seen_event_ids.clear()


def _run(coro):
    return asyncio.run(coro)


def test_purchase_text_dispatches_to_preview_card(client, db, captured_messages):
    p1 = create_part(db, {"name": "吊坠A", "category": "吊坠"})
    p2 = create_part(db, {"name": "链条B", "category": "链条"})
    db.commit()

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
    assert db.query(PurchaseOrder).count() == 0


def test_purchase_text_with_bad_qty_sends_parse_error_card(client, db, captured_messages):
    p = create_part(db, {"name": "吊坠A", "category": "吊坠"})
    db.commit()

    from bot.handlers import process_feishu_message
    text = f"腾飞\n{p.id} abc 5"
    _run(process_feishu_message(chat_id="chat-1", text=text, sender_open_id="open-1"))

    assert len(captured_messages["card"]) == 1
    s = json.dumps(captured_messages["card"][0]["card"], ensure_ascii=False)
    assert "解析失败" in s
    assert "abc" in s


def _put_draft_and_get_token(db, captured_messages, vendor, part_id, qty, price):
    """Helper: send a purchase message, return the token from the preview card."""
    from bot.handlers import process_feishu_message
    text = f"{vendor}\n{part_id} {qty} {price}"
    _run(process_feishu_message(chat_id="chat-1", text=text, sender_open_id="open-1"))
    assert len(captured_messages["card"]) >= 1
    card = captured_messages["card"][-1]["card"]
    actions = next(e for e in card["elements"] if e.get("tag") == "action")
    return actions["actions"][0]["value"]["token"]


def test_confirm_creates_po_and_writes_inventory_log(client, db, captured_messages):
    p = create_part(db, {"name": "吊坠A", "category": "吊坠"})
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
    db.expire_all()  # see commits made by the handler's session
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
    p = create_part(db, {"name": "吊坠A", "category": "吊坠"})
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
    db.expire_all()
    assert db.query(PurchaseOrder).count() == 0
    s = json.dumps(captured_messages["card"][0]["card"], ensure_ascii=False)
    assert "已取消" in s


def test_double_confirm_returns_already_created(client, db, captured_messages):
    p = create_part(db, {"name": "吊坠A", "category": "吊坠"})
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
    db.expire_all()
    assert db.query(PurchaseOrder).count() == 1
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
    p = create_part(db, {"name": "吊坠A", "category": "吊坠"})
    db.commit()

    body = _feishu_text_event("chat-1", "open-1", f"腾飞\n{p.id} 100 5")
    r = client.post("/api/feishu/webhook", json=body)
    assert r.status_code == 200

    assert len(captured_messages["card"]) == 1
    s = json.dumps(captured_messages["card"][0]["card"], ensure_ascii=False)
    assert "采购单预览" in s


def test_webhook_card_action_confirm_creates_po(client, db, captured_messages):
    p = create_part(db, {"name": "吊坠A", "category": "吊坠"})
    db.commit()

    body = _feishu_text_event("chat-1", "open-1", f"腾飞\n{p.id} 100 5", event_id="e-text-2")
    client.post("/api/feishu/webhook", json=body)
    card = captured_messages["card"][-1]["card"]
    actions = next(e for e in card["elements"] if e.get("tag") == "action")
    token = actions["actions"][0]["value"]["token"]
    captured_messages["card"].clear()

    body2 = _feishu_card_action_event(
        "chat-1", "open-1",
        action_value={"action": "confirm", "token": token},
        event_id="e-card-2",
    )
    r = client.post("/api/feishu/webhook", json=body2)
    assert r.status_code == 200

    from models.purchase_order import PurchaseOrder
    db.expire_all()
    assert db.query(PurchaseOrder).count() == 1
    s = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "已创建" in s


def test_webhook_url_verification_returns_challenge(client):
    body = {"type": "url_verification", "challenge": "abc123"}
    r = client.post("/api/feishu/webhook", json=body)
    assert r.status_code == 200
    assert r.json() == {"challenge": "abc123"}


def test_confirm_value_error_restores_draft_and_sends_failure_card(client, db, captured_messages, monkeypatch):
    """If create_purchase_order raises ValueError, draft is restored and user can retry."""
    p = create_part(db, {"name": "吊坠A", "category": "吊坠"})
    db.commit()

    token = _put_draft_and_get_token(db, captured_messages, "腾飞", p.id, 100, 5)
    captured_messages["card"].clear()

    # Force create_purchase_order to raise ValueError on the first call only
    import services.purchase_order as po_module
    original = po_module.create_purchase_order
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("模拟业务错误")
        return original(*args, **kwargs)

    monkeypatch.setattr(po_module, "create_purchase_order", flaky)

    from bot.feishu_card_handler import handle_card_action
    _run(handle_card_action(
        action_value={"action": "confirm", "token": token},
        sender_open_id="open-1",
        chat_id="chat-1",
    ))

    from models.purchase_order import PurchaseOrder
    db.expire_all()
    assert db.query(PurchaseOrder).count() == 0  # no PO created
    s = json.dumps(captured_messages["card"][0]["card"], ensure_ascii=False)
    assert "建单失败" in s
    assert "模拟业务错误" in s

    # Draft was restored — user can retry by clicking confirm again
    captured_messages["card"].clear()
    _run(handle_card_action(
        action_value={"action": "confirm", "token": token},
        sender_open_id="open-1",
        chat_id="chat-1",
    ))
    db.expire_all()
    assert db.query(PurchaseOrder).count() == 1
    s2 = json.dumps(captured_messages["card"][0]["card"], ensure_ascii=False)
    assert "已创建" in s2


def test_confirm_generic_exception_does_not_restore_draft(client, db, captured_messages, monkeypatch):
    """Non-ValueError exceptions during confirm leave token consumed (no retry loop on dirty state)."""
    p = create_part(db, {"name": "吊坠A", "category": "吊坠"})
    db.commit()

    token = _put_draft_and_get_token(db, captured_messages, "腾飞", p.id, 100, 5)
    captured_messages["card"].clear()

    import services.purchase_order as po_module

    def explode(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(po_module, "create_purchase_order", explode)

    from bot.feishu_card_handler import handle_card_action
    _run(handle_card_action(
        action_value={"action": "confirm", "token": token},
        sender_open_id="open-1",
        chat_id="chat-1",
    ))

    s = json.dumps(captured_messages["card"][0]["card"], ensure_ascii=False)
    assert "系统错误" in s or "建单失败" in s  # whichever the impl chose for generic Exception

    # Token consumed — second click should NOT retry
    from bot.purchase_draft_store import pop_draft
    assert pop_draft(token, "open-1") is None


def test_webhook_rejects_bad_verification_token(client, captured_messages, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "FEISHU_VERIFICATION_TOKEN", "secret-token")

    body = _feishu_text_event("chat-1", "open-1", "腾飞\nPJ-DZ-00001 100 5")
    # builder doesn't set a token → mismatch
    body["header"]["token"] = "WRONG"
    r = client.post("/api/feishu/webhook", json=body)
    assert r.status_code == 403
    assert len(captured_messages["card"]) == 0


def test_webhook_card_action_rejects_bad_verification_token(client, captured_messages, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "FEISHU_VERIFICATION_TOKEN", "secret-token")

    body = _feishu_card_action_event(
        "chat-1", "open-1",
        action_value={"action": "confirm", "token": "whatever"},
        event_id="e-card-badtoken-1",
    )
    body["header"]["token"] = "WRONG"
    r = client.post("/api/feishu/webhook", json=body)
    assert r.status_code == 403
    assert len(captured_messages["card"]) == 0


def test_webhook_accepts_matching_verification_token(client, db, captured_messages, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "FEISHU_VERIFICATION_TOKEN", "secret-token")
    p = create_part(db, {"name": "吊坠A", "category": "吊坠"})
    db.commit()

    body = _feishu_text_event("chat-1", "open-1", f"腾飞\n{p.id} 100 5", event_id="e-token-accept-1")
    body["header"]["token"] = "secret-token"
    r = client.post("/api/feishu/webhook", json=body)
    assert r.status_code == 200
    assert len(captured_messages["card"]) == 1


def test_webhook_whitelist_rejection_does_not_dispatch(client, db, captured_messages, monkeypatch):
    from config import settings
    # Configure a whitelist that does NOT include open-evil
    monkeypatch.setattr(settings, "FEISHU_WHITELIST", "open-good")
    p = create_part(db, {"name": "吊坠A", "category": "吊坠"})
    db.commit()

    body = _feishu_text_event("chat-1", "open-evil", f"腾飞\n{p.id} 100 5", event_id="e-whitelist-1")
    r = client.post("/api/feishu/webhook", json=body)
    assert r.status_code == 200
    assert len(captured_messages["card"]) == 0  # background task not triggered


def test_webhook_card_action_with_null_value_is_safe(client, captured_messages):
    body = _feishu_card_action_event("chat-1", "open-1", action_value=None, event_id="e-null-1")
    r = client.post("/api/feishu/webhook", json=body)
    assert r.status_code == 200
    assert len(captured_messages["card"]) == 0


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


def _seed_ambiguous(db, base, *suffixes):
    """Create parts named base+suffix (category 吊坠); return their ids in order."""
    return [create_part(db, {"name": f"{base}{suf}", "category": "吊坠"}).id for suf in suffixes]


def _send_and_get_disambig_token(db, captured_messages, text):
    from bot.handlers import process_feishu_message
    _run(process_feishu_message(chat_id="chat-1", text=text, sender_open_id="open-1"))
    card = captured_messages["card"][-1]["card"]
    action = next(e for e in card["elements"] if e.get("tag") == "action")
    return action["actions"][0]["value"]["token"]


def test_single_line_disambiguation_to_preview_then_confirm(client, db, captured_messages):
    ids = _seed_ambiguous(db, "玫瑰吊坠", "大", "小")
    db.commit()
    token = _send_and_get_disambig_token(db, captured_messages, "腾飞\n玫瑰吊坠 10 5")
    captured_messages["card"].clear()

    from bot.feishu_card_handler import handle_card_action
    _run(handle_card_action(
        action_value={"action": "disambiguate", "token": token, "line_no": 2, "part_id": ids[0]},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    s = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "采购单预览" in s

    captured_messages["card"].clear()
    _run(handle_card_action(
        action_value={"action": "confirm", "token": token},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    from models.purchase_order import PurchaseOrder
    db.expire_all()
    assert db.query(PurchaseOrder).count() == 1
    s2 = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "已创建" in s2


def test_two_ambiguous_lines_take_two_picks(client, db, captured_messages):
    rose = _seed_ambiguous(db, "玫瑰吊坠", "大", "小")
    pearl = _seed_ambiguous(db, "珍珠扣", "大", "小")
    db.commit()
    token = _send_and_get_disambig_token(db, captured_messages, "腾飞\n玫瑰吊坠 10 5\n珍珠扣 20 2")

    from bot.feishu_card_handler import handle_card_action
    captured_messages["card"].clear()
    _run(handle_card_action(
        action_value={"action": "disambiguate", "token": token, "line_no": 2, "part_id": rose[0]},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    s1 = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "需要确认" in s1
    assert "珍珠扣" in s1

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
    _seed_ambiguous(db, "玫瑰吊坠", "大", "小")
    db.commit()
    token = _send_and_get_disambig_token(db, captured_messages, "腾飞\n玫瑰吊坠 10 5")
    captured_messages["card"].clear()

    from bot.feishu_card_handler import handle_card_action
    _run(handle_card_action(
        action_value={"action": "disambiguate", "token": token, "line_no": 2, "part_id": "PJ-FAKE-99999"},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    s = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "需要确认" in s  # still asking, not advanced


def test_disambiguate_repeat_pick_is_idempotent(client, db, captured_messages):
    ids = _seed_ambiguous(db, "玫瑰吊坠", "大", "小")
    db.commit()
    token = _send_and_get_disambig_token(db, captured_messages, "腾飞\n玫瑰吊坠 10 5")

    from bot.feishu_card_handler import handle_card_action
    for _ in range(2):
        _run(handle_card_action(
            action_value={"action": "disambiguate", "token": token, "line_no": 2, "part_id": ids[0]},
            sender_open_id="open-1", chat_id="chat-1",
        ))
    _run(handle_card_action(
        action_value={"action": "confirm", "token": token},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    from models.purchase_order import PurchaseOrder
    db.expire_all()
    assert db.query(PurchaseOrder).count() == 1


def test_disambiguation_confirm_writes_inventory_log(client, db, captured_messages):
    ids = _seed_ambiguous(db, "玫瑰吊坠", "大", "小")
    db.commit()
    token = _send_and_get_disambig_token(db, captured_messages, "腾飞\n玫瑰吊坠 10 5")

    from bot.feishu_card_handler import handle_card_action
    _run(handle_card_action(
        action_value={"action": "disambiguate", "token": token, "line_no": 2, "part_id": ids[0]},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    _run(handle_card_action(
        action_value={"action": "confirm", "token": token},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    from models.inventory_log import InventoryLog
    db.expire_all()
    logs = db.query(InventoryLog).filter_by(item_id=ids[0]).all()
    assert len(logs) == 1
    assert logs[0].reason == "采购入库"
    assert float(logs[0].change_qty) == 10


def test_cancel_during_disambiguation_clears_draft(client, db, captured_messages):
    _seed_ambiguous(db, "玫瑰吊坠", "大", "小")
    db.commit()
    token = _send_and_get_disambig_token(db, captured_messages, "腾飞\n玫瑰吊坠 10 5")

    from bot.feishu_card_handler import handle_card_action
    _run(handle_card_action(
        action_value={"action": "cancel", "token": token},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    from bot.purchase_draft_store import get_draft
    assert get_draft(token, "open-1") is None


def test_confirm_on_mid_disambiguation_token_restores_draft(client, db, captured_messages):
    _seed_ambiguous(db, "玫瑰吊坠", "大", "小")
    db.commit()
    token = _send_and_get_disambig_token(db, captured_messages, "腾飞\n玫瑰吊坠 10 5")
    captured_messages["card"].clear()

    from bot.feishu_card_handler import handle_card_action
    # confirm before finishing picks → nudge, draft preserved
    _run(handle_card_action(
        action_value={"action": "confirm", "token": token},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    s = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "先完成选择" in s
    from bot.purchase_draft_store import get_draft
    assert get_draft(token, "open-1") is not None  # not destroyed


def test_short_name_query_not_fuzzy_matched(client, db, captured_messages):
    # two parts both contain "A"; a 1-char query must NOT fuzzy-match them → not_found
    create_part(db, {"name": "A大", "category": "吊坠"})
    create_part(db, {"name": "A小", "category": "吊坠"})
    db.commit()
    from bot.handlers import process_feishu_message
    _run(process_feishu_message(chat_id="chat-1", text="腾飞\nA 1 1", sender_open_id="open-1"))
    s = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "配件不存在" in s


def test_disambiguation_card_has_cancel_button(client, db, captured_messages):
    _seed_ambiguous(db, "玫瑰吊坠", "大", "小")
    db.commit()
    token = _send_and_get_disambig_token(db, captured_messages, "腾飞\n玫瑰吊坠 10 5")
    card = captured_messages["card"][-1]["card"]
    all_buttons = [b for e in card["elements"] if e.get("tag") == "action" for b in e["actions"]]
    assert any(b["value"].get("action") == "cancel" for b in all_buttons)


def test_assemble_failure_clears_poison_draft(client, db, captured_messages, monkeypatch):
    ids = _seed_ambiguous(db, "玫瑰吊坠", "大", "小")
    db.commit()
    token = _send_and_get_disambig_token(db, captured_messages, "腾飞\n玫瑰吊坠 10 5")
    captured_messages["card"].clear()

    import bot.feishu_card_handler as h
    def _boom(*a, **k):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(h, "assemble_resolved", _boom)

    from bot.feishu_card_handler import handle_card_action
    _run(handle_card_action(
        action_value={"action": "disambiguate", "token": token, "line_no": 2, "part_id": ids[0]},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    s = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "系统错误" in s
    from bot.purchase_draft_store import get_draft
    assert get_draft(token, "open-1") is None  # poison draft cleared, no infinite loop


def test_stale_disambiguate_after_confirm_says_already_created(client, db, captured_messages):
    ids = _seed_ambiguous(db, "玫瑰吊坠", "大", "小")
    db.commit()
    token = _send_and_get_disambig_token(db, captured_messages, "腾飞\n玫瑰吊坠 10 5")
    from bot.feishu_card_handler import handle_card_action
    _run(handle_card_action(
        action_value={"action": "disambiguate", "token": token, "line_no": 2, "part_id": ids[0]},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    _run(handle_card_action(
        action_value={"action": "confirm", "token": token},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    captured_messages["card"].clear()
    # stale disambiguation tap after the PO is already built
    _run(handle_card_action(
        action_value={"action": "disambiguate", "token": token, "line_no": 2, "part_id": ids[0]},
        sender_open_id="open-1", chat_id="chat-1",
    ))
    s = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "已建好" in s


def test_multi_keyword_message_narrows_to_preview(client, db, captured_messages):
    create_part(db, {"name": "玫瑰吊坠大", "category": "吊坠"})
    create_part(db, {"name": "玫瑰吊坠小", "category": "吊坠"})
    db.commit()
    from bot.handlers import process_feishu_message
    _run(process_feishu_message(chat_id="chat-1", text="腾飞\n玫瑰吊坠 大 10 5", sender_open_id="open-1"))
    s = json.dumps(captured_messages["card"][-1]["card"], ensure_ascii=False)
    assert "采购单预览" in s
    assert "玫瑰吊坠大" in s
    assert "需要确认" not in s
