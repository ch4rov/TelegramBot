import asyncio
import logging
import sys
import os
import shutil
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

import settings
from services.database_service import init_db, get_all_users, clear_file_cache
from handlers import user, admin, inline_handler, search_handler
from middlewares.antiflood import ThrottlingMiddleware
from core.logger_system import setup_logger, sys_log

async def on_startup(bot: Bot):
    await init_db()
    
    # АВТОМАТИЧЕСКИ ПОЛУЧАЕМ ЮЗЕРНЕЙМ БОТА
    try:
        bot_info = await bot.get_me()
        settings.BOT_USERNAME = bot_info.username
        await sys_log(bot, f"Bot initialized as @{settings.BOT_USERNAME}")
    except Exception as e:
        await sys_log(bot, f"Failed to get bot username: {e}")

    if settings.IS_TEST_ENV:
        await clear_file_cache()
        if os.path.exists("downloads"):
            shutil.rmtree("downloads", ignore_errors=True)
            os.makedirs("downloads")
        await sys_log(bot, "Bot started in TEST mode. Cache cleared.")
    else:
        await sys_log(bot, "Bot started.")
    
    users = await get_all_users()
    print(f"Users in DB: {len(users)}")

async def on_shutdown(bot: Bot):
    await sys_log(bot, "Bot stopped.")
    await bot.session.close()

def main():
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.message.middleware(ThrottlingMiddleware())
    
    setup_logger(dp)
    
    dp.include_router(admin.admin_router)
    dp.include_router(user.user_router)
    dp.include_router(inline_handler.router)
    dp.include_router(search_handler.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    if settings.USE_WEBHOOK:
        app = web.Application()
        webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_requests_handler.register(app, path=settings.WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
        web.run_app(app, host=settings.WEBHOOK_HOST, port=settings.WEBHOOK_PORT)
    else:
        asyncio.run(dp.start_polling(bot))

if __name__ == "__main__":
    main()