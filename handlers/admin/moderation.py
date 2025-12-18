from aiogram import types
from aiogram.filters import Command
from .router import admin_router, is_admin
from services.database.core import get_all_users, set_ban_status
# --- ИСПРАВЛЕННЫЙ ИМПОРТ ---
from core.logger_system import send_log
# ---------------------------

@admin_router.message(Command("users"))
async def cmd_users(message: types.Message):
    if not is_admin(message.from_user.id): return
    all_entities = await get_all_users()
    
    groups = []
    users = []
    
    for u in all_entities:
        if u['user_id'] < 0: groups.append(u)
        else: users.append(u)
    
    txt = f"📊 <b>Database Report:</b>\nВсего: {len(all_entities)} (👥 {len(groups)} | 👤 {len(users)})\n\n"

    if groups:
        txt += "<b>👥 Группы:</b>\n"
        for g in groups[:20]:
            icon = "⛔" if g['is_banned'] else "✅"
            name = str(g['username']).replace("<", "&lt;")
            txt += f"{icon} {name} | <code>{g['user_id']}</code>\n"
        txt += "\n"

    if users:
        txt += "<b>👤 Пользователи:</b>\n"
        for u in users[:40]:
            icon = "❌" if u['is_banned'] else "✅"
            name = str(u['username']).replace("<", "&lt;") if u['username'] else ""
            txt += f"{icon} <code>{u['user_id']}</code> @{name}\n"

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
        
        # Логируем ответ в историю
        from services.database.core import log_activity
        await log_activity(uid, "Admin", "ADMIN", txt)
        await send_log("ADMIN", f"Answer to {uid}: {txt}", admin=message.from_user)
    except: await message.answer("Usage: <code>/answer ID TEXT</code> or reply", parse_mode="HTML")