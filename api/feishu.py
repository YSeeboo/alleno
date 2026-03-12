import json
import logging

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from config import settings

router = APIRouter(prefix="/api/feishu", tags=["feishu"])
logger = logging.getLogger(__name__)

# Deduplicate events in memory (bounded to 1000 entries)
_seen_event_ids: set = set()
_MAX_SEEN = 1000


@router.post("/webhook")
async def feishu_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()

    # URL verification challenge (fired when binding webhook URL in Feishu console)
    if body.get("type") == "url_verification":
        return JSONResponse({"challenge": body.get("challenge")})

    header = body.get("header", {})
    event_id = header.get("event_id", "")

    # Deduplicate — Feishu may deliver the same event more than once
    if event_id:
        if event_id in _seen_event_ids:
            return JSONResponse({"code": 0})
        _seen_event_ids.add(event_id)
        if len(_seen_event_ids) > _MAX_SEEN:
            # Remove arbitrary oldest entries
            excess = list(_seen_event_ids)[: len(_seen_event_ids) - _MAX_SEEN]
            for eid in excess:
                _seen_event_ids.discard(eid)

    event = body.get("event", {})
    message = event.get("message", {})
    sender = event.get("sender", {})

    # Only handle text messages
    if message.get("message_type") != "text":
        return JSONResponse({"code": 0})

    # Whitelist check
    open_id = sender.get("sender_id", {}).get("open_id", "")
    whitelist = settings.feishu_whitelist_ids
    if whitelist and open_id not in whitelist:
        logger.warning("Feishu message from unlisted user: %s", open_id)
        return JSONResponse({"code": 0})

    chat_id = message.get("chat_id", "")
    try:
        content = json.loads(message.get("content", "{}"))
        text = content.get("text", "").strip()
    except (json.JSONDecodeError, AttributeError):
        return JSONResponse({"code": 0})

    if not text or not chat_id:
        return JSONResponse({"code": 0})

    from bot.handlers import process_feishu_message
    background_tasks.add_task(process_feishu_message, chat_id, text)

    # Must respond within 3 seconds; actual reply is sent asynchronously
    return JSONResponse({"code": 0})
