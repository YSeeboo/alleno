import json
import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

_FEISHU_API = "https://open.feishu.cn/open-apis"


async def _get_tenant_access_token() -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_FEISHU_API}/auth/v3/tenant_access_token/internal",
            json={"app_id": settings.FEISHU_APP_ID, "app_secret": settings.FEISHU_APP_SECRET},
        )
        resp.raise_for_status()
        return resp.json()["tenant_access_token"]


async def send_feishu_message(chat_id: str, text: str) -> None:
    """Send a text message to a Feishu chat."""
    # Feishu message limit is 4000 chars; split if needed
    chunks = [text[i:i + 4000] for i in range(0, max(len(text), 1), 4000)]
    token = await _get_tenant_access_token()
    async with httpx.AsyncClient() as client:
        for chunk in chunks:
            await client.post(
                f"{_FEISHU_API}/im/v1/messages?receive_id_type=chat_id",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": chat_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": chunk}),
                },
            )


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
    from bot.purchase_parser import parse_purchase_text
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
