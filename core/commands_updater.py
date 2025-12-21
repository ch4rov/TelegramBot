# -*- coding: utf-8 -*-
import logging
from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeAllChatAdministrators
from settings import BOT_COMMANDS_LIST, ADMIN_IDS

logger = logging.getLogger(__name__)


async def set_bot_commands(bot: Bot):
    """Обновляет команды в меню Telegram для всех пользователей и админов отдельно (EN/RU)."""
    try:
        # UX requirement: only 4 commands should be visible in Telegram menu for anyone.
        base_en = [
            BotCommand(command="start", description="Main Menu"),
            BotCommand(command="login", description="Login / Connections"),
            BotCommand(command="language", description="Toggle Language"),
            BotCommand(command="videomessage", description="Video Note Mode"),
        ]
        base_ru = [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="login", description="Логин / Подключения"),
            BotCommand(command="language", description="Переключить язык"),
            BotCommand(command="videomessage", description="Режим видеозаписи"),
        ]

        await bot.set_my_commands(commands=base_en, scope=BotCommandScopeDefault(), language_code="en")
        await bot.set_my_commands(commands=base_ru, scope=BotCommandScopeDefault(), language_code="ru")
        await bot.set_my_commands(commands=base_en, scope=BotCommandScopeAllChatAdministrators(), language_code="en")
        await bot.set_my_commands(commands=base_ru, scope=BotCommandScopeAllChatAdministrators(), language_code="ru")
        logger.info("Bot menu commands updated (fixed 4)")

    except Exception as e:
        logger.error(f"Error updating bot commands: {e}")
