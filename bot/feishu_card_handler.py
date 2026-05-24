"""Handle Feishu card.action.trigger events for the purchase-order flow."""
from __future__ import annotations

import logging

import bot.handlers as _handlers
from bot.feishu_cards import (
    render_success_card,
    render_cancel_card,
    render_token_expired_card,
    render_already_created_card,
    render_system_error_card,
)
from bot.purchase_draft_store import (
    pop_draft,
    put_with_token,
    mark_consumed,
    get_consumed_po,
)

logger = logging.getLogger(__name__)


async def handle_card_action(action_value: dict, sender_open_id: str, chat_id: str) -> None:
    action = action_value.get("action")
    token = action_value.get("token", "")

    if action == "cancel":
        pop_draft(token, sender_open_id)  # discard whatever is there
        await _handlers.send_feishu_card(chat_id, render_cancel_card())
        return

    if action != "confirm":
        await _handlers.send_feishu_card(chat_id, render_system_error_card(f"未知操作：{action}"))
        return

    # Idempotency: token already consumed → friendly reply
    already_po = get_consumed_po(token, sender_open_id)
    if already_po is not None:
        await _handlers.send_feishu_card(chat_id, render_already_created_card(already_po))
        return

    data = pop_draft(token, sender_open_id)
    if data is None:
        await _handlers.send_feishu_card(chat_id, render_token_expired_card())
        return

    from database import SessionLocal
    from services.purchase_order import create_purchase_order

    db = SessionLocal()
    po_id: str | None = None
    try:
        items_payload = [
            {
                "part_id": it.part_id,
                "qty": it.qty,
                "unit": it.unit,
                "price": it.price,
            }
            for it in data.items
        ]
        try:
            po = create_purchase_order(
                db,
                vendor_name=data.vendor_name,
                items=items_payload,
                status="未付款",
            )
            db.commit()
            po_id = po.id  # capture before session closes
        except ValueError as exc:
            db.rollback()
            put_with_token(token, data, sender_open_id)
            await _handlers.send_feishu_card(chat_id, render_system_error_card(str(exc)))
            return
        except Exception as exc:
            db.rollback()
            logger.exception("create_purchase_order failed: %s", exc)
            await _handlers.send_feishu_card(chat_id, render_system_error_card("建单失败，请稍后重试。"))
            return
    finally:
        db.close()

    mark_consumed(token, po_id=po_id, sender_open_id=sender_open_id)
    await _handlers.send_feishu_card(
        chat_id,
        render_success_card(po_id, data.vendor_name, data.total_amount, len(data.items)),
    )
