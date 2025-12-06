from .router import user_router
# Импортируем остальные файлы, чтобы их код выполнился и зарегистрировал хендлеры в user_router
from . import commands, video_notes, content, links

# Экспортируем роутер наружу
__all__ = ["user_router"]