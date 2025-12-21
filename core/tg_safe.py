from __future__ import annotations

from typing import Any

from aiogram import types


async def safe_reply(message: types.Message, text: str, **kwargs: Any):
    """Reply to a message; fallback to non-reply send if original message is gone.

    This prevents crashes when the triggering message was deleted while we were processing.
    """
    try:
        return await message.reply(text, **kwargs)
    except Exception:
        try:
            return await message.answer(text, **kwargs)
        except Exception:
            return None


async def safe_reply_html(message: types.Message, text: str, **kwargs: Any):
    kwargs.setdefault("parse_mode", "HTML")
    return await safe_reply(message, text, **kwargs)
