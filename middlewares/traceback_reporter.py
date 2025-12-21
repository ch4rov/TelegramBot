"""Global middleware to DM admins about unhandled exceptions."""

# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from core.error_reporter import ErrorReporter


class TracebackReporterMiddleware(BaseMiddleware):
    """Report any unhandled exception to admin(s) via DM."""

    def __init__(self, bot, dedupe_window_s: float = 60.0):
        self._bot = bot
        self._reporter = ErrorReporter(bot, dedupe_window_s=float(dedupe_window_s))

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            try:
                await self._report_exception(event, data, e)
            except Exception:
                # Never let reporting crash the dispatcher.
                pass
            raise

    async def _report_exception(self, event: TelegramObject, data: Dict[str, Any], exc: Exception) -> None:
        user = data.get("event_from_user")
        chat = getattr(event, "chat", None)

        where = type(event).__name__
        preview = self._event_preview(event)
        await self._reporter.report(
            where=where,
            exc=exc,
            user_id=getattr(user, "id", None),
            chat_id=getattr(chat, "id", None) if chat is not None else None,
            preview=preview,
        )

    def _event_preview(self, event: TelegramObject) -> str:
        try:
            if isinstance(event, Message):
                t = event.text or event.caption or ""
                if not t:
                    return f"[{event.content_type}]"
                return t[:200] + ("…" if len(t) > 200 else "")
            if isinstance(event, CallbackQuery):
                d = event.data or ""
                return d[:200] + ("…" if len(d) > 200 else "")
        except Exception:
            return ""
        return ""

    # Dedupe handled by ErrorReporter
