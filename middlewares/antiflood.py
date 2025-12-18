from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message
from cachetools import TTLCache

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, limit: float = 0.7):
        # Кэш хранит ID пользователей 0.7 секунды
        self.cache = TTLCache(maxsize=10_000, ttl=limit)

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Работаем только с сообщениями
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id

        if user_id in self.cache:
            # Если пользователь в кэше — игнорируем (или можно ответить "Не части")
            return
        
        # Добавляем в кэш и пропускаем дальше
        self.cache[user_id] = True
        return await handler(event, data)