from aiogram import types
from aiogram.filters import Command
from aiogram.exceptions import TelegramNetworkError

from .router import admin_router, is_admin
from services.database_service import get_all_users, set_ban_status, get_user
from logs.logger import send_log

@admin_router.message(Command("users"))
async def cmd_users(message: types.Message):
    if not is_admin(message.from_user.id): return
    users = await get_all_users()
    txt = f"📋 <b>Database ({len(users)}):</b>\n\n"
    
    count = 0
    for u in users:
        if count >= 30: # Лимит вывода
            txt += "<i>... и другие ...</i>"
            break
            
        uid = u['user_id']
        name = str(u['username']).replace("<", "&lt;") if u['username'] else "NoName"
        
        # Иконки
        if uid < 0: # Группа
            type_icon = "👥"
        else: # Юзер
            type_icon = "👤"
            
        status_icon = "⛔" if u['is_banned'] else "✅"
        
        line = f"{status_icon} {type_icon} <code>{uid}</code> | {name}\n"
        if u['is_banned']: line = f"<s>{line}</s>"
        
        txt += line
        count += 1
        
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