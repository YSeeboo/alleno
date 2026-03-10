import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_update(user_id: int, text: str = "hello"):
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.text = text
    return update


def test_whitelist_allows_listed_user():
    from bot.middleware import WhitelistMiddleware
    with patch("bot.middleware.settings") as mock_settings:
        mock_settings.telegram_whitelist_ids = [111]
        mw = WhitelistMiddleware()
        update = _make_update(111)
        next_handler = AsyncMock()
        asyncio.run(mw.process_update(update, next_handler))
        next_handler.assert_awaited_once()


def test_whitelist_blocks_unlisted_user():
    from bot.middleware import WhitelistMiddleware
    with patch("bot.middleware.settings") as mock_settings:
        mock_settings.telegram_whitelist_ids = [111]
        mw = WhitelistMiddleware()
        update = _make_update(999)
        next_handler = AsyncMock()
        asyncio.run(mw.process_update(update, next_handler))
        next_handler.assert_not_awaited()
        update.message.reply_text.assert_awaited_once_with("无权限访问")


def test_whitelist_empty_allows_all():
    from bot.middleware import WhitelistMiddleware
    with patch("bot.middleware.settings") as mock_settings:
        mock_settings.telegram_whitelist_ids = []
        mw = WhitelistMiddleware()
        update = _make_update(999)
        next_handler = AsyncMock()
        asyncio.run(mw.process_update(update, next_handler))
        next_handler.assert_awaited_once()


def test_rate_limit_allows_first_message():
    from bot.middleware import RateLimitMiddleware
    mw = RateLimitMiddleware()
    update = _make_update(111)
    next_handler = AsyncMock()
    asyncio.run(mw.process_update(update, next_handler))
    next_handler.assert_awaited_once()


def test_rate_limit_silently_blocks_rapid_second():
    from bot.middleware import RateLimitMiddleware
    mw = RateLimitMiddleware()
    update = _make_update(111)
    next_handler = AsyncMock()
    asyncio.run(mw.process_update(update, next_handler))  # first — allowed
    next_handler.reset_mock()
    asyncio.run(mw.process_update(update, next_handler))  # immediate second — blocked
    next_handler.assert_not_awaited()


def test_rate_limit_allows_after_cooldown():
    from bot.middleware import RateLimitMiddleware
    mw = RateLimitMiddleware()
    update = _make_update(111)
    next_handler = AsyncMock()
    mw._last_seen[111] = time.time() - 5.0
    asyncio.run(mw.process_update(update, next_handler))
    next_handler.assert_awaited_once()
