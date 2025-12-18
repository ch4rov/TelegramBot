# -*- coding: utf-8 -*-
import logging
from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeAllChatAdministrators
from settings import BOT_COMMANDS_LIST, ADMIN_IDS

logger = logging.getLogger(__name__)


async def set_bot_commands(bot: Bot):
    """Обновляет команды в меню Telegram для всех пользователей и админов отдельно (EN/RU)."""
    try:
        # Команды для всех пользователей (только user + show_in_menu=True)
        user_commands_en = []
        user_commands_ru = []
        for cmd_name, desc_en, desc_ru, cmd_type, show_in_menu in BOT_COMMANDS_LIST:
            if cmd_type == "user" and show_in_menu:
                user_commands_en.append(BotCommand(command=cmd_name, description=desc_en))
                user_commands_ru.append(BotCommand(command=cmd_name, description=desc_ru))

        # Устанавливаем команды для всех пользователей EN/RU
        await bot.set_my_commands(commands=user_commands_en, scope=BotCommandScopeDefault(), language_code="en")
        await bot.set_my_commands(commands=user_commands_ru, scope=BotCommandScopeDefault(), language_code="ru")
        logger.info(f"User commands updated: EN={len(user_commands_en)}, RU={len(user_commands_ru)}")

        # Команды для админов (user + admin с show_in_menu=True)
        admin_commands_en = []
        admin_commands_ru = []
        for cmd_name, desc_en, desc_ru, cmd_type, show_in_menu in BOT_COMMANDS_LIST:
            if show_in_menu:
                admin_commands_en.append(BotCommand(command=cmd_name, description=desc_en))
                admin_commands_ru.append(BotCommand(command=cmd_name, description=desc_ru))

        # Устанавливаем команды для админов EN/RU
        await bot.set_my_commands(commands=admin_commands_en, scope=BotCommandScopeAllChatAdministrators(), language_code="en")
        await bot.set_my_commands(commands=admin_commands_ru, scope=BotCommandScopeAllChatAdministrators(), language_code="ru")
        logger.info(f"Admin commands updated: EN={len(admin_commands_en)}, RU={len(admin_commands_ru)}")

    except Exception as e:
        logger.error(f"Error updating bot commands: {e}")
