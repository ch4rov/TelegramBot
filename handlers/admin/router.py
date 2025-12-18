from aiogram import Router

# Главный роутер админки
router = Router()

# Импортируем все модули админки
from . import users_mgmt
from . import system
from . import modules
from . import edit_user

# Подключаем их роутеры
router.include_router(users_mgmt.router)
router.include_router(system.router)
router.include_router(modules.router)
router.include_router(edit_user.router)