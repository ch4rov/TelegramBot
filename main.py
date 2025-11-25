import asyncio
import logging
from loader import bot, dp
from services.database import init_db
from handlers import users, admin

# Логирование в консоль
logging.basicConfig(level=logging.INFO)

async def main():
    # 1. Запускаем базу данных
    await init_db()
    print("✅ База данных подключена")

    # 2. Подключаем роутеры (Сначала админ, потом юзеры!)
    dp.include_router(admin.router)
    dp.include_router(users.router)

    print("🚀 Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")