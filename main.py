import asyncio
import logging
import sys
from loader import bot, dp
from services.database import init_db
from services.logger import send_log
from handlers import users, admin

logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()
    
    dp.include_router(admin.router)
    dp.include_router(users.router)

    print("🚀 Бот запущен (через Scheduler)!")
    await send_log("SYSTEM", "Система запущена (Run/Restart).")
    
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        # Этот блок сработает при остановке
        await bot.session.close()
        await send_log("SYSTEM", "Система остановлена.")
        print("Бот остановлен.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass