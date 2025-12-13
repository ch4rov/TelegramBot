import asyncio
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineQuery, Update
from .handlers import distribute_log

class LoggerMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        # Получаем объект бота из контекста
        bot = data.get("bot")

        # Определяем тип события и извлекаем данные
        user = None
        event_type = "UNKNOWN"
        content = ""

        # Aiogram передает в event сам объект (Message, CallbackQuery), а не Update,
        # если middleware зарегистрирован на router.message/router.callback_query
        # Но если глобально, то может быть Update. Проверяем типы.

        if isinstance(event, Message):
            user = event.from_user
            text = event.text or event.caption or ""
            if text.startswith("/"):
                event_type = "CMD"
                content = text
            elif event.video or event.audio or event.photo:
                event_type = "FILE"
                content = f"Media: {event.content_type}"
            else:
                event_type = "MSG"
                content = text

        elif isinstance(event, CallbackQuery):
            user = event.from_user
            event_type = "BTN"
            content = event.data

        elif isinstance(event, InlineQuery):
            user = event.from_user
            event_type = "INLINE"
            content = event.query
            
        elif isinstance(event, Update):
            # Если вдруг пришел сырой Update (редко при такой регистрации)
            if event.message:
                return await self(handler, event.message, data)
            elif event.callback_query:
                return await self(handler, event.callback_query, data)

        # Отправляем в логгер (fire and forget)
        if user and bot:
            username = user.username or user.first_name or "Anon"
            asyncio.create_task(distribute_log(bot, user.id, username, event_type, content))

        return await handler(event, data)