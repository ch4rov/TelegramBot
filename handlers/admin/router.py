import os
from aiogram import Router

admin_router = Router()

def is_admin(user_id):
    """Проверка: является ли юзер админом"""
    env_admin_id = os.getenv("ADMIN_ID")
    if not env_admin_id: return False
    return str(user_id) == str(env_admin_id)