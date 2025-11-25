import os
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

# Загружаем переменные из файла .env
load_dotenv()

# Забираем токен
token = os.getenv('BOT_TOKEN')

# Создаем объекты бота и диспетчера
bot = Bot(token=token)
dp = Dispatcher()