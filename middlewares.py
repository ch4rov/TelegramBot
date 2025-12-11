from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineQuery, ChosenInlineResult, Update
from services.database_service import log_activity as db_log
from logs.user_logs.logger import log_user_event
import asyncio

class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        return await handler(event, data)

class DBLoggingMiddleware(BaseMiddleware):
    """
    Тотальный логгер.
    """
    async def __call__(self, handler, event: Update, data):
        user = None
        action = "UNKNOWN"
        details = ""

        # --- РАЗБОР СОБЫТИЯ ---
        if event.message:
            user = event.message.from_user
            msg = event.message
            
            if msg.text:
                if msg.text.startswith("/"):
                    action = "COMMAND"
                    details = msg.text
                else:
                    action = "TEXT"
                    details = msg.text
            elif msg.video:
                action = "FILE_VIDEO"
                details = f"{msg.video.file_id}" 
            elif msg.audio:
                action = "FILE_AUDIO"
                meta = f"{msg.audio.performer} - {msg.audio.title}"
                details = f"{meta} | {msg.audio.file_id}"
            elif msg.photo:
                action = "FILE_PHOTO"
                details = f"{msg.photo[-1].file_id}"
            elif msg.document:
                action = "FILE_DOC"
                details = f"{msg.document.file_name} | {msg.document.file_id}"
            elif msg.voice:
                action = "VOICE"
                details = f"{msg.voice.duration}s | {msg.voice.file_id}"
            elif msg.sticker:
                action = "STICKER"
                details = f"{msg.sticker.emoji or 'Sticker'}"
            else:
                action = "OTHER"
                details = f"[{msg.content_type}]"
        
        elif event.callback_query:
            user = event.callback_query.from_user
            action = "BTN_CLICK"
            details = event.callback_query.data
            
        elif event.inline_query:
            user = event.inline_query.from_user
            action = "INLINE_QUERY"
            if event.inline_query.query:
                details = f"Query: '{event.inline_query.query}'"
            else:
                return await handler(event, data)

        elif event.chosen_inline_result:
            user = event.chosen_inline_result.from_user
            action = "INLINE_SELECTED"
            details = f"{event.chosen_inline_result.result_id} | Query: {event.chosen_inline_result.query}"

        # --- ИГНОР TELEGRAM SERVICE USER (777000) ---
        if user and user.id == 777000:
            return await handler(event, data)
        # --------------------------------------------

        # --- ЗАПИСЬ ---
        if user:
            # Пишем в файл
            asyncio.create_task(log_user_event(user, action, details))
            
            # Пишем в БД
            u_name = user.username or user.first_name
            asyncio.create_task(db_log(user.id, u_name, action, details))

        return await handler(event, data)