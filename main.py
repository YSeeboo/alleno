import logging
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import models  # noqa: F401 — ensures all models are registered with Base.metadata
from config import settings
from database import Base, SessionLocal, engine

from api.bom import router as bom_router
from api.parts import router as parts_router
from api.jewelries import router as jewelries_router
from api.inventory import router as inventory_router
from api.orders import router as orders_router
from api.plating import router as plating_router
from api.handcraft import router as handcraft_router

logger = logging.getLogger(__name__)


def start_bot() -> None:
    """Start the Telegram bot in blocking polling mode.

    Runs in a daemon thread so it exits when the main process exits.
    Only called when TELEGRAM_BOT_TOKEN is configured.
    """
    from telegram.ext import ApplicationBuilder, MessageHandler, filters
    from telegram.request import HTTPXRequest

    from bot.handlers import handle_message, handle_error
    from bot.middleware import WhitelistMiddleware, RateLimitMiddleware

    whitelist = WhitelistMiddleware()
    rate_limit = RateLimitMiddleware()

    async def guarded_handler(update, context):
        async def run_rate_limit(u):
            async def run_message(u):
                await handle_message(u, context)
            await rate_limit.process_update(u, run_message)
        await whitelist.process_update(update, run_rate_limit)

    builder = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN)
    if settings.TELEGRAM_PROXY_URL:
        builder = builder.request(HTTPXRequest(proxy=settings.TELEGRAM_PROXY_URL))
    bot_app = builder.build()
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, guarded_handler))
    bot_app.add_error_handler(handle_error)
    bot_app.bot_data["db_factory"] = SessionLocal
    bot_app.run_polling(stop_signals=())


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass  # allow startup without a live DB (e.g., during tests)
    if settings.TELEGRAM_BOT_TOKEN:
        thread = threading.Thread(target=start_bot, daemon=True, name="telegram-bot")
        thread.start()
        logger.info("Telegram bot started in background thread")
    else:
        logger.info("TELEGRAM_BOT_TOKEN not set — bot disabled")
    yield


app = FastAPI(title="Allen Shop", description="饰品店管理系统", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(parts_router)
app.include_router(jewelries_router)
app.include_router(bom_router)
app.include_router(inventory_router)
app.include_router(orders_router)
app.include_router(plating_router)
app.include_router(handcraft_router)


@app.get("/")
def root():
    return {"status": "ok", "app": "Allen Shop"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
