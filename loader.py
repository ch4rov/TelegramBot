import os
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from handlers import users, admin

async def main():
    dp.include_router(admin.router)
    dp.include_router(users.router)

# Загружаем переменные из файла .env
load_dotenv()

# Забираем токен
token = os.getenv('BOT_TOKEN')

# Создаем объекты бота и диспетчера
bot = Bot(token=token)
dp = Dispatcher()