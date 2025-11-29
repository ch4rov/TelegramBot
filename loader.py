import os
import sys
import requests
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from dotenv import load_dotenv
import settings

load_dotenv()

token = os.getenv('BOT_TOKEN')

# Логируем режим при старте
if settings.IS_TEST_ENV:
    print("⚠️  РЕЖИМ: ТЕСТОВЫЙ (Доступ ограничен)")
else:
    print("✅  РЕЖИМ: STABLE (Публичный)")

session = None

if settings.USE_LOCAL_SERVER:
    server_url = settings.LOCAL_SERVER_URL
    print(f"🖥️  Сервер: ЛОКАЛЬНЫЙ (Docker) -> {server_url}")
    
    # Проверка доступности
    try:
        requests.get(server_url, timeout=2)
        print("✅  Связь с Docker есть.")
    except Exception as e:
        print(f"❌  Нет связи с Docker: {e}")
        sys.exit(1)

    # --- ВАЖНЫЙ ФИКС ---
    # Мы используем TelegramAPIServer.from_base(...)
    # Но нам нужно, чтобы aiogram НЕ пытался искать файлы на диске Windows,
    # так как они лежат внутри Linux-контейнера.
    # Поэтому мы создаем объект сервера вручную с правильным шаблоном.
    
    api_server = TelegramAPIServer(
        base=f"{server_url}/bot{{token}}/{{method}}",
        file=f"{server_url}/file/bot{{token}}/{{path}}",
        is_local=False # <--- ЭТО РЕШАЕТ ОШИБКУ 404. Заставляет качать по HTTP.
    )
    
    session = AiohttpSession(api=api_server)
else:
    print("☁️  Сервер: ОБЛАКО TELEGRAM")

bot = Bot(token=token, session=session)
dp = Dispatcher()