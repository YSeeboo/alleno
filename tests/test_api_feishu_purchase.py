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
