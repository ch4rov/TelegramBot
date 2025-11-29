from .router import admin_router
# Импортируем модули, чтобы их хендлеры зарегистрировались в роутере
from . import system, moderation, testing

__all__ = ["admin_router"]