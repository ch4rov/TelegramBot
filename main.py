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
from aiogram.dispatcher.middlewares.base import BaseMiddleware
import settings 

# --- ИМПОРТЫ НОВЫХ ХЕНДЛЕРОВ ---
# (Старые users и admin мы больше не используем)
from handlers import message_handler, admin_handler, inline_handler, search_handler

# Отключаем многословные логи aiogram
logging.getLogger('aiogram').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO)


# Middleware для консоли
class ConsoleLoggerMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, types.Update) and event.message:
            msg = event.message
            user = msg.from_user
            text = msg.text or msg.caption or "[не-текстовое сообщение]"
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

async def main():
    clean_downloads_on_startup()
    await init_db()
    
    dp.update.middleware(ConsoleLoggerMiddleware())
    
    # --- ПОДКЛЮЧЕНИЕ РОУТЕРОВ (ЭТО ГЛАВНОЕ ИСПРАВЛЕНИЕ) ---
    # Порядок важен!
    
    # 1. Админка
    dp.include_router(admin_handler.router)
    
    # 2. Поиск музыки (Кнопки Callback) - Должен быть до message_handler!
    dp.include_router(search_handler.router)
    
    # 3. Инлайн режим
    dp.include_router(inline_handler.router)
    
    # 4. Обработка сообщений (текст/ссылки) - В самом конце
    dp.include_router(message_handler.router)

    print("🚀 Бот запущен (v2.5 Final)!")
    await send_log("SYSTEM", "Система запущена.")
    
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