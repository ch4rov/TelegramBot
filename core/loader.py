# -*- coding: utf-8 -*-
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from core.config import config

logger = logging.getLogger(__name__)

# Инициализация бота с настройками по умолчанию (HTML разметка)
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