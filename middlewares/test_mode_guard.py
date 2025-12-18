# -*- coding: utf-8 -*-
import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram import types
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent

from core.config import config

logger = logging.getLogger(__name__)


def _redirect_text() -> str:
    prod = getattr(config, "PROD_BOT_USERNAME", None)
    prod = (prod or "").strip().lstrip("@").strip()
    if prod:
        return f"⚠️ Это тестовый бот. Перейдите в основного бота: @{prod}"
    return "⚠️ Это тестовый бот. Доступ только для админов."


class TestModeGuardMiddleware(BaseMiddleware):
    """Blocks non-admin users in test mode."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not getattr(config, "IS_TEST", False):
            return await handler(event, data)

        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        if user.id in getattr(config, "ADMIN_IDS", []) or []:
            return await handler(event, data)

        text = _redirect_text()

        try:
            if isinstance(event, types.InlineQuery):
                await event.answer(
                    [
                        InlineQueryResultArticle(
                            id="test_mode",
                            title="⚠️ Test bot",
                            description="Use production bot",
                            input_message_content=InputTextMessageContent(message_text=text),
                        )
                    ],
                    cache_time=1,
                    is_personal=True,
                )
                return

            if isinstance(event, types.CallbackQuery):
                try:
                    await event.answer(text, show_alert=True)
                except Exception:
                    pass
                return

            if isinstance(event, types.Message):
                try:
                    await event.answer(text, disable_web_page_preview=True)
                except Exception:
                    pass
                return
        except Exception:
            logger.exception("TestModeGuard failed")
            return

        return
