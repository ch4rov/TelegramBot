import asyncio
import logging
import sys
import shutil
import os
import time
import requests
import settings 
from loader import bot, dp
from core.logger_system import send_log, DBLoggingMiddleware
from aiogram import types, F
from aiogram.enums import MessageEntityType
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.exceptions import TelegramNetworkError
from languages import LANGUAGES
from services.database_service import init_db, get_module_status, get_system_value, log_message_to_db
from services.web_dashboard import run_web_server
from core.queue_manager import queue_manager
from handlers import user, admin, inline_handler, search_handler
from core.installs.ffmpeg_installer import check_and_install_ffmpeg 
from services.placeholder_service import ensure_placeholders

logging.getLogger('aiogram').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s', datefmt='%H:%M:%S')

# --- ЛОГГЕР КОНСОЛИ (Принты) ---
class ConsoleLoggerMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, types.Update) and event.message:
            msg = event.message
            u = msg.from_user
            text = msg.text or msg.caption or "[media]"
            if len(text) > 60: text = text[:57] + "..."
            username = u.username or u.first_name or "unknown"
            print(f"📨 @{username}({u.id}): {text}", flush=True)
        return await handler(event, data)

class GroupLoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not isinstance(event, types.Update) or not event.message:
            return await handler(event, data)

        message = event.message

        if message.chat.type not in {'group', 'supergroup'}:
            return await handler(event, data)

        should_log = False
        log_type = ""

        if message.reply_to_message:
            should_log = True
            log_type = f"[REPLY to {message.reply_to_message.message_id}]"

        if not should_log and (message.entities or message.caption_entities):
            all_entities = (message.entities or []) + (message.caption_entities or [])
            for entity in all_entities:
                if entity.type in [MessageEntityType.URL, MessageEntityType.TEXT_LINK, MessageEntityType.MENTION]:
                    should_log = True
                    log_type = "[LINK/TAG]"
                    break

        if should_log:
            user = message.from_user
            text_content = message.text or message.caption or "[Media]"
            username = user.username or user.first_name or "Unknown"
            
            # 1. Пишем в TXT (Файловая система)
            # Текст для лога формируем тут, но пометки [FROM GROUP] добавит сам логгер
            log_text = f"{log_type} Text: {text_content}"
            
            asyncio.create_task(send_log(
                log_text, 
                user_id=user.id, 
                chat_id=message.chat.id,
                username=username # Передаем имя для красоты
            ))

            # 2. Пишем в USERS.DB (База данных)
            asyncio.create_task(log_message_to_db(
                user_id=user.id,
                chat_id=message.chat.id,
                username=username,
                text=text_content,
                msg_type=log_type
            ))

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
    user_commands = []
    admin_commands = []
    en_strings = LANGUAGES.get('en', {})
    for key, desc_key, cat, copy in settings.BOT_COMMANDS_LIST:
        desc = en_strings.get(desc_key, desc_key)
        command = BotCommand(command=key, description=desc)
        if cat == "user":
            user_commands.append(command)
            admin_commands.append(command)
        elif cat.startswith("admin"):
            admin_commands.append(command)
    if await get_module_status("TelegramVideo"):
        vn_cmd = BotCommand(command="videomessage", description="📹 Video Note")
        user_commands.append(vn_cmd)
        admin_commands.append(vn_cmd)
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
    
    admin_id = os.getenv("ADMIN_ID")
    if admin_id:
        try: await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=int(admin_id)))
        except: pass

async def monitor_local_alive():
    print("🛡 [MONITOR] Слежу за здоровьем локального сервера...")
    while True:
        await asyncio.sleep(10)
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: requests.get(settings.LOCAL_SERVER_URL, timeout=5))
        except Exception as e:
            print(f"\n🚨 [MONITOR] Локальный сервер упал! Ошибка: {e}")
            print("🔄 Аварийное переключение на облако...")
            with open(settings.FORCE_CLOUD_FILE, "w") as f: f.write("1")
            sys.exit(65)

async def monitor_cloud_recovery():
    target_url = os.getenv("LOCAL_SERVER_URL")
    if not target_url: return

    print(f"🚑 [RECOVERY] Жду восстановления сервера: {target_url}")
    
    while True:
        await asyncio.sleep(30)
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: requests.get(target_url, timeout=5))
            
            print("\n🎉 [RECOVERY] Локальный сервер ожил! Удаляю флаг и перезагружаю...")
            
            if os.path.exists(settings.FORCE_CLOUD_FILE):
                os.remove(settings.FORCE_CLOUD_FILE)
            
            if settings.ADMIN_ID:
                try:
                    await bot.send_message(
                        settings.ADMIN_ID, 
                        "✅ <b>Локальный сервер снова в строю!</b>\nПереключаюсь обратно.",
                        parse_mode="HTML"
                    )
                    await asyncio.sleep(1)
                except: pass

            sys.exit(65)
            
        except Exception:
            pass

async def main():
    try:
        bot_info = await bot.get_me()
        settings.BOT_USERNAME = bot_info.username
        print(f"🤖 Бот авторизован: @{settings.BOT_USERNAME}")
    except Exception as e:
        print(f"❌ Ошибка авторизации: {e}")
        if settings.USE_LOCAL_SERVER:
            print("⚡️ Принудительное переключение на облако (Start Fail)...")
            with open(settings.FORCE_CLOUD_FILE, "w") as f: f.write("1")
            sys.exit(65)
        return

    check_and_install_ffmpeg()
    clean_downloads_on_startup()
    await init_db()
    saved_mode = await get_system_value("limit_mode")
    if saved_mode: queue_manager.set_mode(saved_mode)
    await run_web_server()
    if settings.IS_TEST_ENV: print("🛑 ВНИМАНИЕ: ВКЛЮЧЕН ТЕСТОВЫЙ РЕЖИМ")
    else: print("✅ ВКЛЮЧЕН STABLE РЕЖИМ")
    if settings.ENABLE_WEB_DASHBOARD: 
        await run_web_server()
        print("🌐 ВКЛЮЧЕН WEB DASHBOARD")

    # --- ПОДКЛЮЧЕНИЕ MIDDLEWARE ---
    dp.update.outer_middleware(DBLoggingMiddleware())
    dp.update.outer_middleware(ConsoleLoggerMiddleware())
    
    # Подключаем наш новый логгер групп (он пропустит сообщение дальше к скачиванию)
    dp.update.outer_middleware(GroupLoggingMiddleware())
    
    @dp.message(F.command == "return_local")
    async def cmd_return_local(message: types.Message):
        if str(message.from_user.id) != settings.ADMIN_ID: return
        if os.path.exists(settings.FORCE_CLOUD_FILE):
            os.remove(settings.FORCE_CLOUD_FILE)
            await message.answer("✅ Флаг удален. Перезагрузка...", parse_mode="HTML")
            sys.exit(65)
        else:
            await message.answer("⚠️ Бот уже в штатном режиме.")

    # Хендлера для групп здесь больше нет, он теперь Middleware
    
    dp.include_router(admin.admin_router)
    dp.include_router(search_handler.router)
    dp.include_router(inline_handler.router)
    dp.include_router(user.user_router)

    await set_ui_commands(bot)
    await ensure_placeholders()

    if settings.STARTUP_ERROR_MESSAGE and settings.ADMIN_ID:
        try: await bot.send_message(settings.ADMIN_ID, settings.STARTUP_ERROR_MESSAGE, parse_mode="HTML")
        except: pass
        settings.STARTUP_ERROR_MESSAGE = None
    settings.START_TIME = time.time()
    print("🚀 Бот запущен!")
    
    await send_log(f"[SYSTEM] Запуск ({'LOCAL' if settings.USE_LOCAL_SERVER else 'CLOUD'}).")
    
    if settings.USE_LOCAL_SERVER:
        asyncio.create_task(monitor_local_alive())
    elif os.path.exists(settings.FORCE_CLOUD_FILE):
        asyncio.create_task(monitor_cloud_recovery())

    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dp.start_polling(bot, polling_timeout=10)
        
    except (TelegramNetworkError, Exception) as e:
        print(f"\n❌ [CRITICAL] Ошибка сети: {e}")
        if settings.USE_LOCAL_SERVER:
            print("🔄 Падение. Ставлю флаг Cloud...")
            with open(settings.FORCE_CLOUD_FILE, "w") as f: f.write("1")
            sys.exit(65)
        else:
            sys.exit(65)
            
    finally:
        await bot.session.close()
        await send_log("[SYSTEM] Система остановлена.")
        print("Бот остановлен.")

if __name__ == "__main__":
    try:
        from aiogram import F 
        asyncio.run(main())
    except KeyboardInterrupt:
        pass