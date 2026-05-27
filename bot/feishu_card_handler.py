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
    render_create_failed_card,
    render_preview_card,
    render_disambiguation_card,
)
from bot.purchase_draft_store import (
    pop_draft,
    put_with_token,
    mark_consumed,
    get_consumed_po,
    get_draft,
)
from bot.purchase_resolver import (
    NeedsDisambiguation,
    ResolvedPurchase,
    assemble_resolved,
    first_unresolved,
)

logger = logging.getLogger(__name__)


async def handle_card_action(action_value: dict, sender_open_id: str, chat_id: str) -> None:
    action = action_value.get("action")
    token = action_value.get("token", "")

    if action == "cancel":
        pop_draft(token, sender_open_id)  # discard whatever is there
        await _handlers.send_feishu_card(chat_id, render_cancel_card())
        return

    if action == "disambiguate":
        await _handle_disambiguate(action_value, sender_open_id, chat_id)
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

    if not isinstance(data, ResolvedPurchase):
        # token still mid-disambiguation (forged / replayed confirm) — restore and nudge
        put_with_token(token, data, sender_open_id)
        await _handlers.send_feishu_card(chat_id, render_system_error_card("请先完成选择再确认"))
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
            await _handlers.send_feishu_card(chat_id, render_create_failed_card(str(exc)))
            return
        except Exception as exc:
            db.rollback()
            logger.exception("create_purchase_order failed: %s", exc)
            await _handlers.send_feishu_card(chat_id, render_system_error_card("建单失败，请稍后重试。"))
            return
    finally:
        db.close()

    mark_consumed(token, po_id=po_id, sender_open_id=sender_open_id)
    try:
        await _handlers.send_feishu_card(
            chat_id,
            render_success_card(po_id, data.vendor_name, data.total_amount, len(data.items)),
        )
    except Exception:
        logger.exception("failed to send success card for %s", po_id)


async def _handle_disambiguate(action_value: dict, sender_open_id: str, chat_id: str) -> None:
    token = action_value.get("token", "")
    line_no = action_value.get("line_no")
    part_id = action_value.get("part_id")

    # Stale tap after the PO was already built → match the confirm path's reply.
    already_po = get_consumed_po(token, sender_open_id)
    if already_po is not None:
        await _handlers.send_feishu_card(chat_id, render_already_created_card(already_po))
        return

    draft = get_draft(token, sender_open_id)
    if draft is None:
        await _handlers.send_feishu_card(chat_id, render_token_expired_card())
        return

    # Stale tap after the flow already advanced to preview → re-show preview.
    if isinstance(draft, ResolvedPurchase):
        await _handlers.send_feishu_card(chat_id, render_preview_card(draft, token=token))
        return
    if not isinstance(draft, NeedsDisambiguation):
        await _handlers.send_feishu_card(chat_id, render_token_expired_card())
        return

    # Apply the choice if the line is still pending and the part_id is a real candidate.
    pl = next((p for p in draft.pending if p.line_no == line_no), None)
    if pl is not None and pl.chosen_part_id is None:
        if any(c.part_id == part_id for c in pl.candidates):
            pl.chosen_part_id = part_id
    put_with_token(token, draft, sender_open_id)

    nxt = first_unresolved(draft)
    if nxt is not None:
        next_pl, done, total = nxt
        await _handlers.send_feishu_card(
            chat_id, render_disambiguation_card(next_pl, token, done, total)
        )
        return

    # All resolved → assemble final purchase, store under same token, show preview.
    from database import SessionLocal
    db = SessionLocal()
    try:
        resolved = assemble_resolved(db, draft)
    except Exception:
        logger.exception("assemble_resolved failed for token %s", token)
        pop_draft(token, sender_open_id)  # clear the poison draft so a re-tap doesn't loop
        await _handlers.send_feishu_card(chat_id, render_system_error_card("系统错误，请稍后重试"))
        return
    finally:
        db.close()
    put_with_token(token, resolved, sender_open_id)
    await _handlers.send_feishu_card(chat_id, render_preview_card(resolved, token=token))
