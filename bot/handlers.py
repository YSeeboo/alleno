import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.agent.runner import run_agent

logger = logging.getLogger(__name__)

_MAX_MSG_LEN = 4096


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process an incoming text message through the Claude agent."""
    db_factory = context.bot_data.get("db_factory")
    if db_factory is None:
        await update.message.reply_text("系统未就绪，请稍后重试。")
        return

    db = db_factory()
    try:
        text = update.message.text or ""
        response = await run_agent(text, db)
        db.commit()
    except Exception as exc:
        logger.exception("run_agent failed: %s", exc)
        db.rollback()
        response = "处理失败，请稍后重试。"
    finally:
        db.close()

    # Split long responses to respect Telegram's 4096-char limit
    for i in range(0, max(len(response), 1), _MAX_MSG_LEN):
        await update.message.reply_text(response[i : i + _MAX_MSG_LEN])


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and notify the user if possible."""
    logger.error("Telegram error: %s", context.error, exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("处理失败，请稍后重试。")
