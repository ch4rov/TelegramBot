import asyncio
import logging
import sys
import shutil
import os
from loader import bot, dp
from services.database import init_db
from logs.logger import send_log
from handlers import users, admin
import settings  # Импортируем настройки

logging.basicConfig(level=logging.INFO)

def clean_downloads_on_startup():
    """Удаляет папку downloads при запуске, чтобы очистить старый мусор."""
    if os.path.exists(settings.DOWNLOADS_DIR):
        try:
            shutil.rmtree(settings.DOWNLOADS_DIR)
            print(f"🧹 [STARTUP] Папка {settings.DOWNLOADS_DIR} очищена.")
        except Exception as e:
            print(f"⚠️ [STARTUP] Не удалось очистить папку: {e}")
    
    # Создаем чистую папку заново
    if not os.path.exists(settings.DOWNLOADS_DIR):
        os.makedirs(settings.DOWNLOADS_DIR)

async def main():
    # 1. Чистим мусор перед запуском
    clean_downloads_on_startup()
    
    # 2. Инициализация БД
    await init_db()
    
    # 3. Роутеры
    dp.include_router(admin.router)
    dp.include_router(users.router)

    print("🚀 Бот запущен (через Scheduler)!")
    await send_log("SYSTEM", "Система запущена (Clean Start).")
    
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