import os
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from dotenv import load_dotenv
import settings

load_dotenv()
token = settings.BOT_TOKEN

# Логируем режим при старте
if settings.IS_TEST_ENV:
    print("⚠️  РЕЖИМ: ТЕСТОВЫЙ (Доступ ограничен)")
else:
    print("✅  РЕЖИМ: STABLE (Публичный)")

# Настройка сессии
session = None

if settings.USE_LOCAL_SERVER:
    server_url = settings.LOCAL_SERVER_URL
    print(f"🖥️  Сервер: ЛОКАЛЬНЫЙ ({server_url})")
    
    # ВАЖНО: Тут нет проверки requests, чтобы loader был быстрым.
    # Проверка (ping) осталась в admin_handler /status
    
    api_server = TelegramAPIServer.from_base(server_url)
    session = AiohttpSession(api=api_server)
else:
    print("☁️  Сервер: ОБЛАКО TELEGRAM")

bot = Bot(token=token, session=session)
dp = Dispatcher()