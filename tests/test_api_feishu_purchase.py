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
