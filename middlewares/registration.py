# -*- coding: utf-8 -*-
import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from services.database.repo import ensure_user_exists, get_user

logger = logging.getLogger(__name__)


def _safe_str(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


class RegistrationMiddleware(BaseMiddleware):
    """Ensures user/group is present in DB for any update type."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")

        # Best-effort chat extraction
        chat = data.get("event_chat") or data.get("event_from_chat")
        if chat is None:
            try:
                chat = getattr(event, "chat", None)
            except Exception:
                chat = None
        if chat is None:
            try:
                msg = getattr(event, "message", None)
                chat = getattr(msg, "chat", None)
            except Exception:
                chat = None

        try:
            if user:
                # Telegram system account (often appears as author for channel-posts in linked groups)
                if getattr(user, "id", None) == 777000:
                    return await handler(event, data)

                full_name = _safe_str(getattr(user, "full_name", None)) or "Unknown"
                username = _safe_str(getattr(user, "username", None))
                # Don't overwrite DB language on every update; respect /language and manual choice.
                existing = await get_user(user.id)
                language = None
                if not existing:
                    language = _safe_str(getattr(user, "language_code", None)) or "en"
                await ensure_user_exists(user.id, username, full_name, tag=None, language=language)

            # Register groups/supergroups/channels by chat.id (< 0)
            if chat is not None:
                chat_id = getattr(chat, "id", None)
                chat_type = _safe_str(getattr(chat, "type", None))
                if isinstance(chat_id, int) and chat_id < 0 and chat_type in ("group", "supergroup", "channel"):
                    title = _safe_str(getattr(chat, "title", None)) or f"{chat_type} {chat_id}"
                    chat_username = _safe_str(getattr(chat, "username", None))
                    lang = "en"
                    if user:
                        lang = _safe_str(getattr(user, "language_code", None)) or "en"
                    await ensure_user_exists(chat_id, chat_username, title, tag=chat_type, language=lang)
        except Exception:
            logger.exception("Registration middleware failed")

        return await handler(event, data)
