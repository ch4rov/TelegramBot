import asyncio
import logging
import sys
import shutil
import os
import time
from loader import bot, dp
from services.database import init_db
from logs.logger import send_log
from handlers import users, admin
from aiogram import types
from aiogram.dispatcher.middlewares.base import BaseMiddleware
import settings  # Импортируем настройки

# Отключаем многословные логи aiogram
logging.getLogger('aiogram').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO)


# Middleware для вывода в консоль информации о сообщениях
class ConsoleLoggerMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, types.Update) and event.message:
            msg = event.message
            user = msg.from_user
            text = msg.text or msg.caption or "[не-текстовое сообщение]"
            
            # Сокращаем длинный текст
            if len(text) > 60:
                text = text[:57] + "..."
            
            username = user.username or user.first_name or "unknown"
            print(f"📨 @{username}({user.id}): {text}", flush=True)
        
        return await handler(event, data)

def clean_downloads_on_startup():
    """
    Удаляет папку downloads при запуске, чтобы очистить старый мусор.
    Обработка заблокированных файлов: пропускаем их и пробуем несколько раз.
    """
    if not os.path.exists(settings.DOWNLOADS_DIR):
        os.makedirs(settings.DOWNLOADS_DIR)
        print(f"🧹 [STARTUP] Папка {settings.DOWNLOADS_DIR} создана.")
        return

    max_retries = 3
    for attempt in range(max_retries):
        try:
            shutil.rmtree(settings.DOWNLOADS_DIR)
            print(f"🧹 [STARTUP] Папка {settings.DOWNLOADS_DIR} очищена (попытка {attempt + 1}).")
            break
        except PermissionError as e:
            if attempt < max_retries - 1:
                print(f"⚠️ [STARTUP] Ошибка доступа (попытка {attempt + 1}): {e}")
                time.sleep(0.5)  # Небольшая задержка перед повтором
            else:
                print(f"⚠️ [STARTUP] Не удалось полностью очистить папку после {max_retries} попыток.")
                # Пробуем удалить содержимое по одному файлу/папке
                try:
                    for root, dirs, files in os.walk(settings.DOWNLOADS_DIR, topdown=False):
                        for name in files:
                            try:
                                os.remove(os.path.join(root, name))
                            except Exception as fe:
                                print(f"  ⚠️ Пропущен файл: {name}")
                        for name in dirs:
                            try:
                                os.rmdir(os.path.join(root, name))
                            except Exception as de:
                                print(f"  ⚠️ Пропущена папка: {name}")
                except Exception as ex:
                    print(f"⚠️ [STARTUP] Ошибка при удалении по одному: {ex}")
        except Exception as e:
            print(f"⚠️ [STARTUP] Неожиданная ошибка при очистке: {e}")
            break
    
    # Гарантируем создание чистой папки
    if not os.path.exists(settings.DOWNLOADS_DIR):
        os.makedirs(settings.DOWNLOADS_DIR)
        print(f"🧹 [STARTUP] Папка {settings.DOWNLOADS_DIR} пересоздана.")

async def main():
    # 1. Чистим мусор перед запуском
    clean_downloads_on_startup()
    
    # 2. Инициализация БД
    await init_db()
    
    # 3. Роутеры
    # 3. Добавляем middleware для логирования в консоль
    dp.message.middleware(ConsoleLoggerMiddleware())
    
    # 4. Роутеры
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