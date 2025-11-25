import os
from aiogram import Router, types
from aiogram.filters import Command
from services.database import get_all_users, set_ban_status
from services.logger import send_log

router = Router()

# Получаем ID админа из .env
ADMIN_ID = os.getenv("ADMIN_ID")

def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

@router.message(Command("users"))
async def cmd_users(message: types.Message):
    if not is_admin(message.from_user.id): return

    users = await get_all_users()
    if not users:
        await message.answer("База данных пуста.")
        return

    text = "📋 **Список пользователей:**\n\n"
    for u in users:
        status = "⛔ BAN" if u['is_banned'] else "✅"
        # Экранируем имена на случай спецсимволов
        text += f"{status} ID: `{u['user_id']}` | @{u['username']}\n📅 First: {u['first_seen']}\n🕒 Last: {u['last_seen']}\n\n"
    
    # Разбиваем сообщение, если оно слишком длинное
    if len(text) > 4000:
        text = text[:4000] + "\n...(список обрезан)"
        
    await message.answer(text, parse_mode="Markdown")
    await send_log("ADMIN", "Запросил список пользователей")

@router.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    try:
        # Пример: /ban 123456789
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("Укажи ID: /ban 123456")
            return
            
        user_id_to_ban = int(parts[1])
        await set_ban_status(user_id_to_ban, True)
        await message.answer(f"Пользователь {user_id_to_ban} забанен ⛔")
        await send_log("ADMIN", f"Забанил пользователя {user_id_to_ban}")
    except ValueError:
        await message.answer("ID должен быть числом.")

@router.message(Command("unban"))
async def cmd_unban(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    try:
        parts = message.text.split()
        if len(parts) < 2: return
        user_id_to_unban = int(parts[1])
        await set_ban_status(user_id_to_unban, False)
        await message.answer(f"Пользователь {user_id_to_unban} разбанен ✅")
        await send_log("ADMIN", f"Разбанил пользователя {user_id_to_unban}")
    except:
        pass