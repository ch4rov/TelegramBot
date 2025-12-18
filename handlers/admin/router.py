from aiogram import Router

# Главный роутер админки
router = Router()

# Импортируем все модули админки
from . import users_mgmt
from . import system
from . import modules

# Подключаем их роутеры
router.include_router(users_mgmt.router)
router.include_router(system.router)
router.include_router(modules.router)