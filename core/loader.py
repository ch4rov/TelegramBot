# -*- coding: utf-8 -*-
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from core.config import config
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

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

async def on_shutdown(bot: Bot):
    logger.info("Bot is shutting down...")