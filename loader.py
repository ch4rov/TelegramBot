import os
import sys
import time
import requests
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from dotenv import load_dotenv
import settings

load_dotenv()
token = settings.BOT_TOKEN

if settings.IS_TEST_ENV:
    print("⚠️  РЕЖИМ: ТЕСТОВЫЙ (Доступ ограничен)")
else:
    print("✅  РЕЖИМ: STABLE (Публичный)")

session = None

if settings.USE_LOCAL_SERVER:
    print(f"🖥️  Проверка локального сервера ({settings.LOCAL_SERVER_URL})...")
    
    server_available = False
    
    # --- ЛОГИКА ПОВТОРНЫХ ПОПЫТОК (RETRY) ---
    # Пробуем 3 раза с паузой, чтобы дать серверу "прогреться"
    for i in range(3):
        try:
            # Таймаут 10 секунд (достаточно даже для медленного HDD)
            requests.get(f"{settings.LOCAL_SERVER_URL}", timeout=10)
            server_available = True
            break
        except:
            print(f"   ⏳ Попытка {i+1}/3 неудачна... ждем 2 сек...")
            time.sleep(2)
    # ----------------------------------------

    if server_available:
        print("✅  Связь с Docker есть. Работаем локально.")
        # Создаем сессию с is_local=False (чтобы качать по HTTP, а не путям)
        api_server = TelegramAPIServer(
            base=f"{settings.LOCAL_SERVER_URL}/bot{{token}}/{{method}}",
            file=f"{settings.LOCAL_SERVER_URL}/file/bot{{token}}/{{path}}",
            is_local=False 
        )
        session = AiohttpSession(api=api_server)
    else:
        print("❌  Docker недоступен после 3 попыток.")
        print("☁️  АВАРИЙНОЕ ПЕРЕКЛЮЧЕНИЕ НА ОБЛАКО.")
        
        # Ставим флаг аварии
        with open(settings.FORCE_CLOUD_FILE, "w") as f: 
            f.write("1")
            
        settings.USE_LOCAL_SERVER = False
        settings.STARTUP_ERROR_MESSAGE = "🚨 <b>Сбой при старте!</b>\nЛокальный сервер не ответил на пинг (3 попытки).\nБот перешел на Облако."
        session = None 
else:
    print("☁️  Сервер: ОБЛАКО TELEGRAM")

bot = Bot(token=token, session=session)
dp = Dispatcher()