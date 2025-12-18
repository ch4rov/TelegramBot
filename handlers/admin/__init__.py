from aiogram import Router
from . import system, users_mgmt, cookies, modules, testing, edit_user

admin_router = Router()

admin_router.include_router(system.router)
admin_router.include_router(users_mgmt.router)
admin_router.include_router(cookies.router)
admin_router.include_router(modules.router)
admin_router.include_router(testing.router)
admin_router.include_router(edit_user.router)