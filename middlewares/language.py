from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from services.database.repo import get_user
from services.localization import i18n

class LanguageMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user: User = data.get("event_from_user")
        
        lang_code = "en"
        
        if user:
            db_user = await get_user(user.id)
            if db_user:
                lang_code = db_user.language
        
        # Передаем в хендлер готовый код языка и функцию перевода
        data["user_lang"] = lang_code
        data["i18n"] = i18n
        
        return await handler(event, data)