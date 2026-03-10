import time
from typing import Callable, Dict

from telegram import Update

from config import settings


class BaseMiddleware:
    """Base class for middleware implementing common interface.

    Subclasses should override process_update to implement custom logic.
    """

    def __init__(self, block: bool = True):
        """Initialize the middleware.

        Args:
            block: Whether to block updates (not used in this simple version)
        """
        self.block = block

    async def process_update(self, update: Update, next_handler: Callable) -> None:
        """Process an update and pass to next handler.

        Default implementation just calls next_handler.
        """
        await next_handler(update)


class WhitelistMiddleware(BaseMiddleware):
    """Allow only users whose Telegram user_id is in the whitelist.

    If the whitelist is empty, all users are allowed.
    """

    def __init__(self):
        super().__init__(block=True)

    async def process_update(self, update: Update, next_handler: Callable) -> None:
        whitelist = settings.telegram_whitelist_ids
        if whitelist:
            user_id = update.effective_user.id if update.effective_user else None
            if user_id not in whitelist:
                if update.message:
                    await update.message.reply_text("无权限访问")
                return
        await next_handler(update)


class RateLimitMiddleware(BaseMiddleware):
    """Allow each user at most 1 message per 3 seconds."""

    COOLDOWN_SECONDS = 3.0

    def __init__(self):
        super().__init__(block=True)
        self._last_seen: Dict[int, float] = {}

    async def process_update(self, update: Update, next_handler: Callable) -> None:
        user_id = update.effective_user.id if update.effective_user else None
        if user_id is not None:
            now = time.time()
            last = self._last_seen.get(user_id, 0.0)
            if now - last < self.COOLDOWN_SECONDS:
                return  # silent ignore
            self._last_seen[user_id] = now
        await next_handler(update)
