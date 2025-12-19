# -*- coding: utf-8 -*-
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# Импорты конфигурации и базы
from core.config import config
from core.loader import bot, dp, on_startup, on_shutdown
from core.logger import setup_logger
from core.commands_updater import set_bot_commands
from services.database.core import init_db
from services.placeholder_service import ensure_placeholders
from services.oauth_server import OAuthServer

# Импорты мидлварей
from middlewares.logger import LoggingMiddleware
from middlewares.language import LanguageMiddleware
from middlewares.antiflood import ThrottlingMiddleware
from middlewares.registration import RegistrationMiddleware
from middlewares.test_mode_guard import TestModeGuardMiddleware
from middlewares.ban_guard import BanGuardMiddleware

# === ИМПОРТЫ РОУТЕРОВ ===
# 1. Админка
from handlers.admin import admin_router

# 2. Пользовательская часть - импортируем готовый user_router из __init__.py
from handlers.user import user_router

# 3. Инлайн и поиск
from handlers import inline_handler, search_handler

async def main():
    # Настройка логирования (на консоль и в файл)
    setup_logger()
    logger = logging.getLogger(__name__)
    logger.info("Starting bot initialization...")

    # Инициализация БД
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")

    # Ensure inline placeholders exist (cached file_ids for inline mode)
    try:
        await ensure_placeholders()
    except Exception as e:
        logger.error(f"Error ensuring placeholders: {e}")

    # Обновляем команды бота в Telegram UI
    try:
        await set_bot_commands(bot)
        logger.info("Bot commands updated successfully")
    except Exception as e:
        logger.error(f"Error updating bot commands: {e}")

    # Регистрация Middleware (порядок важен!)
    # 0) Block random users in test mode
    dp.update.middleware(TestModeGuardMiddleware())

    # 1) Ensure user/group exists in DB for any update
    dp.update.middleware(RegistrationMiddleware())

    # 2) Block banned users and banned chats
    dp.update.middleware(BanGuardMiddleware())

    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())
    dp.message.middleware(LanguageMiddleware())
    dp.message.middleware(ThrottlingMiddleware(limit=0.7))

    # === РЕГИСТРАЦИЯ РОУТЕРОВ ===
    
    # 1. Админка
    dp.include_router(admin_router)
    
    # 2. User Router
    dp.include_router(user_router)
    
    # 3. Inline & Search
    dp.include_router(inline_handler.router)
    dp.include_router(search_handler.router)

    # Регистрация событий
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # OAuth callback server (aiohttp) for Spotify/Yandex
    oauth_server = OAuthServer(bot)

    async def _oauth_startup(*args, **kwargs):
        await oauth_server.start()

    async def _oauth_shutdown(*args, **kwargs):
        await oauth_server.stop()

    dp.startup.register(_oauth_startup)
    dp.shutdown.register(_oauth_shutdown)

    # Запуск
    logger.info("Starting polling...")
    await bot.delete_webhook(drop_pending_updates=config.DROP_PENDING_UPDATES)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped.")
