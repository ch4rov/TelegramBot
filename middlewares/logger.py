# -*- coding: utf-8 -*-
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from services.database.repo import increment_request_count

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseMiddleware):
    """Логирует каждое действие пользователя"""
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        
        if user:
            user_info = f"@{user.username}" if user.username else f"ID:{user.id}"
            
            # Определяем тип события
            event_type = type(event).__name__
            
            if isinstance(event, Message):
                # Для сообщений - логируем текст или тип контента
                text_preview = event.text or event.caption or f"[{event.content_type}]"
                if len(text_preview) > 100:
                    text_preview = text_preview[:100] + "..."
                logger.info(f"Message from {user_info}: {text_preview}")
                
                # Increment global command counter in system.py
                try:
                    from handlers.admin import system
                    system.BOT_COMMAND_COUNT += 1
                except:
                    pass
            
            elif isinstance(event, CallbackQuery):
                # Для callback_query - логируем данные
                logger.info(f"Callback from {user_info}: {event.data}")
                
                # Increment global command counter
                try:
                    from handlers.admin import system
                    system.BOT_COMMAND_COUNT += 1
                except:
                    pass
            
            else:
                logger.info(f"Update from {user_info}: {event_type}")
            
            # Увеличиваем счетчик запросов
            try:
                await increment_request_count(user.id)
            except:
                pass  # Тихо игнорируем ошибки БД
        
        return await handler(event, data)