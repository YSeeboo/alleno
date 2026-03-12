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


async def process_feishu_message(chat_id: str, text: str) -> None:
    """Run the agent and send the reply to Feishu. Called as a background task."""
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
