# -*- coding: utf-8 -*-
import logging
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, types
from aiogram.types import TelegramObject

from services.database.repo import get_user

logger = logging.getLogger(__name__)

# chat_id/user_id -> last notify unix seconds
_LAST_NOTIFY: dict[int, float] = {}


def _should_notify(entity_id: int, cooldown_s: int = 60) -> bool:
    now = time.time()
    last = _LAST_NOTIFY.get(entity_id, 0.0)
    if now - last >= cooldown_s:
        _LAST_NOTIFY[entity_id] = now
        return True
    return False


def _ban_text(reason: str | None, is_group: bool, lang: str | None = None) -> str:
    # Minimal RU/EN; language middleware may not be available at update-level.
    lang = (lang or "ru").lower()
    r = (reason or "").strip()
    if lang.startswith("ru"):
        base = "⛔ Обслуживание в этом чате заблокировано." if is_group else "⛔ Вам запрещено пользоваться ботом."
        return base + (f"\nПричина: {r}" if r else "")
    base = "⛔ Service is blocked in this chat." if is_group else "⛔ You are banned from using this bot."
    return base + (f"\nReason: {r}" if r else "")


class BanGuardMiddleware(BaseMiddleware):
    """Blocks banned users and banned group chats for any update type."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        chat = data.get("event_chat") or data.get("event_from_chat")

        # Try to infer chat for message/callback events
        if chat is None:
            try:
                if isinstance(event, types.CallbackQuery) and event.message:
                    chat = event.message.chat
                elif isinstance(event, types.Message):
                    chat = event.chat
            except Exception:
                chat = None

        try:
            # 1) Block banned group chats
            if chat is not None and isinstance(getattr(chat, "id", None), int):
                chat_id = int(chat.id)
                if chat_id < 0:
                    db_chat = await get_user(chat_id)
                    if db_chat and db_chat.is_banned:
                        text = _ban_text(db_chat.ban_reason, is_group=True, lang=getattr(user, "language_code", None) if user else None)

                        # Best-effort notify (rate-limited)
                        if isinstance(event, types.Message):
                            if _should_notify(chat_id):
                                try:
                                    await event.answer(text, disable_notification=True, disable_web_page_preview=True)
                                except Exception:
                                    pass
                            return

                        if isinstance(event, types.CallbackQuery):
                            try:
                                await event.answer(text, show_alert=True)
                            except Exception:
                                pass
                            return

                        if isinstance(event, types.InlineQuery):
                            # Inline in banned group isn't a thing; let it pass.
                            return await handler(event, data)

                        return

            # 2) Block banned users
            if user is not None:
                db_user = await get_user(int(user.id))
                if db_user and db_user.is_banned:
                    text = _ban_text(db_user.ban_reason, is_group=False, lang=getattr(user, "language_code", None))

                    if isinstance(event, types.Message):
                        if _should_notify(int(user.id), cooldown_s=20):
                            try:
                                await event.answer(text, disable_notification=True, disable_web_page_preview=True)
                            except Exception:
                                pass
                        return

                    if isinstance(event, types.CallbackQuery):
                        try:
                            await event.answer(text, show_alert=True)
                        except Exception:
                            pass
                        return

        except Exception:
            logger.exception("BanGuardMiddleware failed")

        return await handler(event, data)
