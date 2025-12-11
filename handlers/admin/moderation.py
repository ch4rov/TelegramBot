from aiogram import types
from aiogram.filters import Command
from aiogram.exceptions import TelegramNetworkError

from .router import admin_router, is_admin
from services.database_service import get_all_users, set_ban_status, get_user
from logs.logger import send_log

@admin_router.message(Command("users"))
async def cmd_users(message: types.Message):
    if not is_admin(message.from_user.id): return
    all_entities = await get_all_users()
    
    # Разделяем на группы и людей
    groups = []
    users = []
    
    for u in all_entities:
        if u['user_id'] < 0: groups.append(u)
        else: users.append(u)
    
    txt = f"📊 <b>Database Report:</b>\n"
    txt += f"Всего: {len(all_entities)} (👥 {len(groups)} | 👤 {len(users)})\n\n"

    # 1. Группы
    if groups:
        txt += "<b>👥 Группы:</b>\n"
        for g in groups[:20]: # Лимит вывода 20
            icon = "✅"
            if g['is_banned']: icon = "⛔" # Забанена админом
            elif not g['is_active']: icon = "🚫" # Бот кикнут
            
            name = str(g['username']).replace("<", "&lt;")
            reason = f" | Причина: {g['ban_reason']}" if g['is_banned'] and g['ban_reason'] else ""
            
            line = f"{icon} {name} | <code>{g['user_id']}</code>{reason}\n"
            if g['is_banned']: line = f"<s>{line}</s>"
            txt += line
        txt += "\n"

    # 2. Пользователи
    if users:
        txt += "<b>👤 Пользователи:</b>\n"
        for u in users[:40]: # Лимит 40
            icon = "✅"
            if u['is_banned']: icon = "❌" # Забанен
            elif not u['is_active']: icon = "⛔" # Заблокировал бота
            
            name = str(u['username']).replace("<", "&lt;") if u['username'] else ""
            tag = f" | @{name}" if name else ""
            reason = f" | Причина: {u['ban_reason']}" if u['is_banned'] and u['ban_reason'] else ""
            
            line = f"{icon} {u['user_id']}{tag}{reason}\n"
            if u['is_banned']: line = f"<s>{line}</s>"
            txt += line

    if len(all_entities) > 60:
        txt += "\n<i>...список обрезан...</i>"

    await message.answer(txt, parse_mode="HTML")

@admin_router.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 2: raise ValueError
        uid = int(args[1])
        reason = args[2] if len(args) > 2 else "Admin ban"
        await set_ban_status(uid, True, reason)
        await message.answer(f"⛔ Banned {uid}")
        await send_log("ADMIN", f"Banned {uid}: {reason}", admin=message.from_user)
    except: await message.answer("Usage: <code>/ban ID [Reason]</code>", parse_mode="HTML")

@admin_router.message(Command("unban"))
async def cmd_unban(message: types.Message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split()
        if len(args) < 2: raise ValueError
        uid = int(args[1])
        await set_ban_status(uid, False)
        await message.answer(f"✅ Unbanned {uid}")
        await send_log("ADMIN", f"Unbanned {uid}", admin=message.from_user)
    except: await message.answer("Usage: <code>/unban ID</code>", parse_mode="HTML")

@admin_router.message(Command("answer"))
async def cmd_answer(message: types.Message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split(maxsplit=2)
        if message.reply_to_message: uid, txt = message.reply_to_message.from_user.id, args[1]
        else: uid, txt = int(args[1]), args[2]
        await message.bot.send_message(uid, f"📩 <b>Admin:</b>\n{txt}", parse_mode="HTML")
        await message.answer("✅ Sent")
        await send_log("ADMIN", f"Answer to {uid}: {txt}", admin=message.from_user)
    except: await message.answer("Usage: <code>/answer ID TEXT</code> or reply", parse_mode="HTML")