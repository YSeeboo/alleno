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

    if body.get("type") == "url_verification":
        return JSONResponse({"challenge": body.get("challenge")})

    header = body.get("header", {})
    event_id = header.get("event_id", "")
    event_type = header.get("event_type", "")

    if event_id:
        if event_id in _seen_event_ids:
            return JSONResponse({"code": 0})
        _seen_event_ids.add(event_id)
        if len(_seen_event_ids) > _MAX_SEEN:
            excess = list(_seen_event_ids)[: len(_seen_event_ids) - _MAX_SEEN]
            for eid in excess:
                _seen_event_ids.discard(eid)

    if event_type == "card.action.trigger":
        return await _handle_card_action_event(body, background_tasks)
    # Default: im.message.receive_v1
    return await _handle_message_event(body, background_tasks)


def _check_whitelist(open_id: str) -> bool:
    whitelist = settings.feishu_whitelist_ids
    if whitelist and open_id not in whitelist:
        logger.warning("Feishu event from unlisted user: %s", open_id)
        return False
    return True


async def _handle_message_event(body: dict, background_tasks: BackgroundTasks) -> JSONResponse:
    event = body.get("event", {})
    message = event.get("message", {})
    sender = event.get("sender", {})

    if message.get("message_type") != "text":
        return JSONResponse({"code": 0})

    open_id = sender.get("sender_id", {}).get("open_id", "")
    if not _check_whitelist(open_id):
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
    background_tasks.add_task(process_feishu_message, chat_id, text, open_id)
    return JSONResponse({"code": 0})


async def _handle_card_action_event(body: dict, background_tasks: BackgroundTasks) -> JSONResponse:
    event = body.get("event", {})
    operator = event.get("operator", {})
    open_id = operator.get("open_id", "")
    if not _check_whitelist(open_id):
        return JSONResponse({"code": 0})

    chat_id = event.get("context", {}).get("open_chat_id", "")
    action_value = event.get("action", {}).get("value", {})
    if not chat_id or not action_value:
        return JSONResponse({"code": 0})

    from bot.feishu_card_handler import handle_card_action
    background_tasks.add_task(handle_card_action, action_value, open_id, chat_id)
    return JSONResponse({"code": 0})
