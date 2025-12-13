import asyncio
from aiogram import Dispatcher, Bot
from .middleware import LoggerMiddleware
# Импортируем новый воркер discord_bot_worker
from .handlers import discord_bot_worker, distribute_log, log_to_file, log_to_discord_bot
from . import config

async def _start_background_tasks(bot: Bot):
    """Запуск фоновых задач"""
    if config.ENABLE_DISCORD_BOT_LOG:
        asyncio.create_task(discord_bot_worker())

def setup_logger(dp: Dispatcher):
    """Подключает middleware и регистрирует фоновые задачи"""
    dp.message.middleware(LoggerMiddleware())
    dp.callback_query.middleware(LoggerMiddleware())
    dp.inline_query.middleware(LoggerMiddleware())
    
    dp.startup.register(_start_background_tasks)

async def sys_log(bot: Bot, text: str):
    await distribute_log(bot, 0, "SYSTEM", "INFO", text)

# === СОВМЕСТИМОСТЬ ===

async def send_log(style_key, message, user=None, admin=None):
    new_key = style_key
    if style_key == "SUCCESS": new_key = "MSG_SENT"
    elif style_key == "FAIL": new_key = "MSG_FAIL"
    elif style_key == "USER_REQ": new_key = "MSG_LINK"
    elif style_key == "WARN": new_key = "SYS"
    
    target = user or admin
    user_id = 0
    username = "System"
    
    if target:
        if hasattr(target, 'id'):
            user_id = target.id
            username = target.username or target.first_name or "Unknown"
        elif isinstance(target, dict):
            user_id = target.get('id', 0)
            username = target.get('username', 'System')

    print(f"[LOG] [{new_key}] {username}: {message}")
    await log_to_file(user_id, username, new_key, message)
    
    if config.ENABLE_DISCORD_BOT_LOG:
        ds_text = f"**[{new_key}]** {username} ({user_id}): `{message}`"
        asyncio.create_task(log_to_discord_bot(ds_text))

async def logger(user, event_type: str, content: str, message=None):
    await send_log(event_type, content, user=user)