import asyncio
import logging
import sys
import shutil
import os
import time
from loader import bot, dp
from services.database_service import init_db
from logs.logger import send_log
from aiogram import types
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from aiogram.dispatcher.middlewares.base import BaseMiddleware
import settings 

# --- ИМПОРТЫ ---
from handlers import message_handler, admin_handler, inline_handler, search_handler
from middlewares import AccessMiddleware
from core.installs.ffmpeg_installer import check_and_install_ffmpeg 
# Импорт функции обновления заглушек
from services.placeholder_service import ensure_placeholders
# ---------------

logging.getLogger('aiogram').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s', datefmt='%H:%M:%S')

class ConsoleLoggerMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, types.Update) and event.message:
            msg = event.message
            user = msg.from_user
            text = msg.text or msg.caption or "[media]"
            if len(text) > 60: text = text[:57] + "..."
            username = user.username or user.first_name or "unknown"
            print(f"📨 @{username}({user.id}): {text}", flush=True)
        return await handler(event, data)

def clean_downloads_on_startup():
    if not os.path.exists(settings.DOWNLOADS_DIR):
        os.makedirs(settings.DOWNLOADS_DIR)
        print(f"🧹 [STARTUP] Папка {settings.DOWNLOADS_DIR} создана.")
        return

    max_retries = 3
    for attempt in range(max_retries):
        try:
            shutil.rmtree(settings.DOWNLOADS_DIR)
            print(f"🧹 [STARTUP] Папка {settings.DOWNLOADS_DIR} очищена.")
            break
        except Exception as e:
            if attempt < max_retries - 1: time.sleep(0.5)
            else: print(f"⚠️ [STARTUP] Ошибка очистки: {e}")
    
    if not os.path.exists(settings.DOWNLOADS_DIR):
        os.makedirs(settings.DOWNLOADS_DIR)

async def set_ui_commands(bot):
    """Автоматически обновляет кнопку Menu в Telegram."""
    user_commands = []
    admin_commands = []

    for cmd, desc, cat, copy in settings.BOT_COMMANDS_LIST:
        command = BotCommand(command=cmd, description=desc)
        
        if cat == "user":
            user_commands.append(command)
            admin_commands.append(command)
        elif cat.startswith("admin"):
            admin_commands.append(command)
    
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
    
    admin_id = os.getenv("ADMIN_ID")
    if admin_id:
        try:
            await bot.set_my_commands(
                admin_commands, 
                scope=BotCommandScopeChat(chat_id=int(admin_id))
            )
            print(f"✅ [UI] Меню Админа обновлено для ID: {admin_id}")
        except Exception as e:
            print(f"⚠️ [UI] Не удалось обновить меню админа: {e}")
            
    print("✅ [UI] Общее меню обновлено")

async def main():
    # 1. Получение имени бота
    try:
        bot_info = await bot.get_me()
        settings.BOT_USERNAME = bot_info.username
        print(f"🤖 Бот авторизован: @{settings.BOT_USERNAME}")
    except Exception as e:
        print(f"❌ Ошибка авторизации бота: {e}")
        return

    # 2. Подготовка системы
    check_and_install_ffmpeg()
    clean_downloads_on_startup()
    await init_db()
    
    # 3. Проверка режима
    if settings.IS_TEST_ENV:
        print("🛑 ВНИМАНИЕ: ВКЛЮЧЕН ТЕСТОВЫЙ РЕЖИМ")
    else:
        print("✅ ВКЛЮЧЕН STABLE РЕЖИМ")

    # 4. Middleware
    dp.update.outer_middleware(AccessMiddleware()) 
    dp.update.outer_middleware(ConsoleLoggerMiddleware())
    
    # 5. Роутеры
    dp.include_router(admin_handler.router)
    dp.include_router(search_handler.router)
    dp.include_router(inline_handler.router)
    dp.include_router(message_handler.router)

    # 6. Обновление UI и Заглушек
    await set_ui_commands(bot)
    await ensure_placeholders()

    print("🚀 Бот запущен!")
    await send_log("SYSTEM", f"Система запущена ({'TEST' if settings.IS_TEST_ENV else 'STABLE'}).")
    
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await send_log("SYSTEM", "Система остановлена.")
        print("Бот остановлен.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass