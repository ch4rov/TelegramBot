# -*- coding: utf-8 -*-
import os
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from core.config import config
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.types import MenuButtonWebApp, WebAppInfo

logger = logging.getLogger(__name__)

# Инициализация бота с настройками по умолчанию (HTML разметка)
if config.USE_LOCAL_SERVER:
    # Route Bot API calls to local server to allow >50MB uploads
    api_server = TelegramAPIServer.from_base(config.LOCAL_SERVER_URL)
    session = AiohttpSession(api=api_server)
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
else:
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

# Диспетчер
dp = Dispatcher()

# Функции для запуска/остановки
async def on_startup(bot: Bot):
    logger.info("Bot started successfully and ready to work!")

    try:
        is_test = bool(getattr(config, "IS_TEST", False))
    except Exception:
        is_test = False

    if is_test:
        url = (os.getenv("TEST_MINIAPP_PUBLIC_URL") or os.getenv("TEST_PUBLIC_BASE_URL") or os.getenv("MINIAPP_PUBLIC_URL") or os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    else:
        url = (os.getenv("MINIAPP_PUBLIC_URL") or os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")

    if url and getattr(config, "ADMIN_IDS", None):
        text = "Приложение" if not is_test else "Приложение (TEST)"
        for admin_id in list(getattr(config, "ADMIN_IDS", []) or []):
            try:
                await bot.set_chat_menu_button(
                    chat_id=int(admin_id),
                    menu_button=MenuButtonWebApp(text=text, web_app=WebAppInfo(url=url)),
                )
            except Exception as e:
                logger.warning(f"Failed to set menu button for {admin_id}: {e}")

        logger.info(f"Mini App URL for admins: {url}")

async def on_shutdown(bot: Bot):
    logger.info("Bot is shutting down...")