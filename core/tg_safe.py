from __future__ import annotations

from typing import Any

from aiogram import types


async def safe_reply(message: types.Message, text: str = "", **kwargs: Any):
    if text is None:
        text = ""
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
