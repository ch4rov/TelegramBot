import os
import sys
from aiogram import Router, types
from aiogram.filters import Command
from services.database import get_all_users, set_ban_status, get_user
from services.logger import send_log

router = Router()
ADMIN_ID = os.getenv("ADMIN_ID")

def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

# --- RESTART ---
@router.message(Command("restart"))
async def cmd_restart(message: types.Message):
    if not is_admin(message.from_user.id): return

    await message.answer("♻️ Перезагрузка системы...")
    await send_log("ADMIN", "Инициировал перезагрузку системы (Restart)", admin=message.from_user)
    
    # Завершаем процесс кодом 65. run.py поймает его и перезапустит бота.
    sys.exit(65)

# --- STATUS / USERS ---
@router.message(Command("status"))
async def cmd_status(message: types.Message):
    if not is_admin(message.from_user.id): return
    await message.answer("✅ Система работает штатно (v2.1 Album Support).")
    await send_log("ADMIN", "> /status", admin=message.from_user)

@router.message(Command("users"))
async def cmd_users(message: types.Message):
    if not is_admin(message.from_user.id): return

    users = await get_all_users()
    if not users:
        await message.answer("📂 База данных пуста.")
        return

    text = f"📋 **Всего пользователей: {len(users)}**\n\n"
    for u in users:
        status = "⛔" if u['is_banned'] else "✅"
        clean_name = str(u['username']).replace("_", "\\_")
        reason_txt = f"\n   Reason: _{u['ban_reason']}_" if u['is_banned'] and u['ban_reason'] else ""
        
        text += f"{status} `{u['user_id']}` | @{clean_name}{reason_txt}\n🕒 {u['last_seen']}\n\n"
        
    if len(text) > 4000:
        text = text[:4000] + "\n...(обрезано)"
    await message.answer(text, parse_mode="Markdown")

# --- BAN LOGIC ---
@router.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("⚠️ Использование: `/ban ID [Причина]`", parse_mode="Markdown")
        return
        
    try:
        target_id = int(parts[1])
        new_reason = parts[2] if len(parts) > 2 else "Нарушение правил"
        
        # 1. Получаем инфу о юзере из БД
        user_data = await get_user(target_id)
        
        if not user_data:
            await message.answer("❌ Пользователь не найден в базе данных.")
            return

        is_already_banned = user_data['is_banned']
        old_reason = user_data['ban_reason']

        # 2. Логика проверки
        if is_already_banned:
            if old_reason == new_reason:
                await message.answer(f"⚠️ Пользователь `{target_id}` уже забанен по этой причине.")
                return
            else:
                await set_ban_status(target_id, True, new_reason)
                await message.answer(f"🔄 Причина бана для `{target_id}` обновлена на: {new_reason}")
                await send_log("ADMIN", f"Обновил причину бана для {target_id} на: {new_reason}", admin=message.from_user)
                return

        # 3. Бан
        await set_ban_status(target_id, True, new_reason)
        await message.answer(f"⛔ Пользователь `{target_id}` забанен.\nПричина: {new_reason}", parse_mode="Markdown")
        
        log_msg = f"Забанил {target_id} (Причина: {new_reason})"
        await send_log("ADMIN", log_msg, admin=message.from_user)
        
        try:
            await message.bot.send_message(target_id, f"⛔ Вы были заблокированы администратором.\nПричина: {new_reason}\nСвязь: @ch4rov")
        except:
            pass 

    except ValueError:
        await message.answer("ID должен быть числом.")

# --- UNBAN LOGIC ---
@router.message(Command("unban"))
async def cmd_unban(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    try:
        parts = message.text.split()
        if len(parts) < 2: return
        target_id = int(parts[1])
        
        user_data = await get_user(target_id)
        if not user_data or not user_data['is_banned']:
            await message.answer("⚠️ Этот пользователь не забанен.")
            return

        await set_ban_status(target_id, False)
        
        await message.answer(f"✅ Пользователь `{target_id}` разбанен.", parse_mode="Markdown")
        await send_log("ADMIN", f"Разбанил {target_id}", admin=message.from_user)
        
        try:
            await message.bot.send_message(target_id, "✅ Ваш аккаунт разблокирован.")
        except: pass
    except: pass