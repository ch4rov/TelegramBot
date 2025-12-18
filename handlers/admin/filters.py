# -*- coding: utf-8 -*-
from aiogram.filters import BaseFilter
from aiogram.types import Message
from core.config import config

class AdminFilter(BaseFilter):
    """Фильтр для проверки, является ли пользователь админом"""
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id in config.ADMIN_IDS