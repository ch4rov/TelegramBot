from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from core.error_reporter import ErrorReporter


class TracebackReporterMiddleware(BaseMiddleware):
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

        where = "Update"
        preview = self._event_preview(event)
        extra = self._event_extra(event, data)
        await self._reporter.report(
            where=where,
            exc=exc,
            user_id=getattr(user, "id", None),
            chat_id=getattr(chat, "id", None) if chat is not None else None,
            preview=preview,
            extra=extra,
        )

    def _event_preview(self, event: TelegramObject) -> str:
        try:
            if isinstance(event, Message):
                t = event.text or event.caption or ""
                if not t:
                    mg = getattr(event, "media_group_id", None)
                    return f"[{event.content_type}]" + (f" media_group:{mg}" if mg else "")
                lines = t.splitlines()
                head = lines[0] if lines else t
                if len(lines) > 1:
                    head = head + f" (+{len(lines) - 1} lines)"
                return head[:200] + ("…" if len(head) > 200 else "")
            if isinstance(event, CallbackQuery):
                d = event.data or ""
                return d[:200] + ("…" if len(d) > 200 else "")
        except Exception:
            return ""
        return ""

    def _event_extra(self, event: TelegramObject, data: Dict[str, Any]) -> dict:
        extra: dict[str, Any] = {"Event": type(event).__name__}
        try:
            u = data.get("event_from_user")
            if u is not None:
                extra["User"] = f"{getattr(u, 'id', None)}" + (f" @{u.username}" if getattr(u, "username", None) else "")
                name = (getattr(u, "full_name", None) or "").strip()
                if name:
                    extra["UserName"] = name
        except Exception:
            pass

        try:
            if isinstance(event, Message):
                chat = event.chat
                extra["Chat"] = f"{chat.id}" + (f" ({chat.type})" if getattr(chat, "type", None) else "")
                title = (getattr(chat, "title", None) or "").strip()
                if title:
                    extra["ChatTitle"] = title
                if getattr(chat, "username", None):
                    extra["ChatUsername"] = f"@{chat.username}"
                extra["MessageId"] = getattr(event, "message_id", None)
                mg = getattr(event, "media_group_id", None)
                if mg:
                    extra["MediaGroup"] = mg

                cmd = ""
                try:
                    if event.entities:
                        for ent in event.entities:
                            if ent.type == "bot_command" and ent.offset == 0:
                                cmd = (event.text or "")[0:ent.length]
                                break
                except Exception:
                    cmd = ""
                if cmd:
                    extra["Command"] = cmd
                raw = (event.text or event.caption or "").strip()
                if raw:
                    extra["Text"] = (raw[:700] + "…") if len(raw) > 700 else raw

            if isinstance(event, CallbackQuery):
                extra["CallbackData"] = (event.data or "")
                if event.message is not None:
                    chat = event.message.chat
                    extra["Chat"] = f"{chat.id}" + (f" ({chat.type})" if getattr(chat, "type", None) else "")
                    title = (getattr(chat, "title", None) or "").strip()
                    if title:
                        extra["ChatTitle"] = title
                    if getattr(chat, "username", None):
                        extra["ChatUsername"] = f"@{chat.username}"
                    extra["MessageId"] = getattr(event.message, "message_id", None)
        except Exception:
            pass

        return extra

    # Dedupe handled by ErrorReporter
