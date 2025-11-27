import asyncio
import os
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from dotenv import load_dotenv

# Загружаем токен
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

async def logout_from_cloud():
    print("🚪 Попытка выхода из ОБЛАКА Telegram...")
    bot = Bot(token=TOKEN)
    try:
        await bot.log_out()
        print("✅ Успешно вышли из облака. Теперь можно включать Локальный сервер.")
    except Exception as e:
        print(f"⚠️ Ошибка (возможно, уже вышли или сервер недоступен): {e}")
    finally:
        await bot.session.close()

async def logout_from_local():
    print("🚪 Попытка выхода из ЛОКАЛЬНОГО сервера...")
    # Здесь адрес жестко задан, или можно брать из .env
    local_url = os.getenv("LOCAL_SERVER_URL", "http://localhost:8081")
    
    try:
        api = TelegramAPIServer.from_base(local_url)
        session = AiohttpSession(api=api)
        bot = Bot(token=TOKEN, session=session)
        
        await bot.log_out()
        print("✅ Успешно вышли из локального сервера. Теперь можно переключаться на Облако.")
    except Exception as e:
        print(f"⚠️ Ошибка (возможно, сервер выключен): {e}")
    finally:
        await bot.session.close()

def main():
    print("=== Telegram Bot Server Switcher ===")
    print("1. Переезжаю на ЛОКАЛЬНЫЙ (Нужно выйти из Облака)")
    print("2. Переезжаю в ОБЛАКО (Нужно выйти из Локального)")
    
    choice = input("Ваш выбор (1 или 2): ").strip()
    
    if choice == "1":
        asyncio.run(logout_from_cloud())
    elif choice == "2":
        asyncio.run(logout_from_local())
    else:
        print("Отмена.")

if __name__ == "__main__":
    main()