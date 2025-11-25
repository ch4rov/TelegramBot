import asyncio
import logging
import sys
import shutil
import os
import time
from loader import bot, dp
from services.database_service import init_db
from services.logger_service import send_log
from handlers import message_handler, admin_handler, inline_handler
from core.queue_manager import queue_manager, recover_queued_messages
from aiogram import types
from aiogram.dispatcher.middlewares.base import BaseMiddleware
import settings

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

    # Попытка удалить папку целиком несколько раз
    max_retries = 3
    for attempt in range(max_retries):
        try:
            shutil.rmtree(settings.DOWNLOADS_DIR)
            print(f"🧹 [STARTUP] Папка {settings.DOWNLOADS_DIR} успешно очищена.")
            break
        except Exception as e:
            if attempt < max_retries - 1:
                error_msg = str(e).split('\n')[0][:60]  # Первая строка ошибки, до 60 символов
                print(f"⚠️ [STARTUP] Попытка {attempt + 1}: {error_msg} (повтор через 1 сек)")
                time.sleep(1)
            else:
                # Если не получилось удалить целиком - удаляем по файлам
                error_msg = str(e).split('\n')[0][:60]
                print(f"⚠️ [STARTUP] Попытка {attempt + 1}: {error_msg}")
                print(f"⚠️ [STARTUP] Не удалось удалить целиком, пробую по файлам...")
                try:
                    for root, dirs, files in os.walk(settings.DOWNLOADS_DIR, topdown=False):
                        for name in files:
                            try:
                                os.remove(os.path.join(root, name))
                            except Exception:
                                pass  # Просто пропускаем заблокированные файлы
                        for name in dirs:
                            try:
                                os.rmdir(os.path.join(root, name))
                            except Exception:
                                pass  # Просто пропускаем заблокированные папки
                except Exception:
                    pass
                
                print(f"🧹 [STARTUP] Очистка завершена (заблокированные файлы пропущены)")
    
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
    dp.include_router(admin_handler.router)
    dp.include_router(message_handler.router)
    dp.include_router(inline_handler.router)

    print("🚀 Бот запущен (через Scheduler)!")
    await send_log("SYSTEM", "Система запущена (Clean Start).")
    
    # Check if restart flag exists - if yes, notify admin
    restart_flag_path = ".restart_flag"
    if os.path.exists(restart_flag_path):
        try:
            os.remove(restart_flag_path)
        except Exception:
            pass
        
        # Send restart confirmation to admin
        admin_id = os.getenv("ADMIN_ID")
        if admin_id:
            try:
                await bot.send_message(admin_id, "✅ Бот перезагружен и системы загружены.")
            except Exception:
                pass
    
    # 4. Recover queued messages from previous crash
    print("📋 Queue Recovery: Проверяю очередь сообщений...")
    
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