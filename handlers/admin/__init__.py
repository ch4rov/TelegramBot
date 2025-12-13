from aiogram import Router
from . import system  # <-- Вот это самое важное!

admin_router = Router()
admin_router.include_router(system.router)