import sys
import time
import shutil
import subprocess
import platform
import asyncio
from aiogram import types
from aiogram.filters import Command
from aiogram.enums import ChatAction
from services.database_service import clear_cache_older_than
from .router import admin_router, is_admin
from services.database_service import get_all_users, clear_file_cache, get_module_status, set_module_status, set_system_value, get_system_value
from logs.logger import send_log
from core.installs.ffmpeg_installer import check_and_install_ffmpeg
from core.queue_manager import queue_manager  # <--- Added import
import settings

# --- UPDATE ---
@admin_router.message(Command("update"))
async def cmd_update(message: types.Message):
    if not is_admin(message.from_user.id): return
    msg = await message.answer("🔄 <b>Принудительное обновление...</b>", parse_mode="HTML")
    try:
        await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
        
        # Fetch
        proc_fetch = await asyncio.create_subprocess_shell("git fetch origin", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc_fetch.communicate()

        # Hard Reset
        proc_reset = await asyncio.create_subprocess_shell("git reset --hard origin/main", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc_reset.communicate()
        
        if proc_reset.returncode != 0:
            await msg.edit_text(f"❌ <b>Ошибка Git:</b>\n<pre>{stderr.decode()}</pre>", parse_mode="HTML")
            return

        proc_log = await asyncio.create_subprocess_shell("git log -1 --pretty=%B", stdout=asyncio.subprocess.PIPE)
        log_out, _ = await proc_log.communicate()
        
        await msg.edit_text(f"✅ <b>Обновлено!</b>\n📝 {log_out.decode().strip()}\n\n♻️ Перезапуск...", parse_mode="HTML")
        await send_log("ADMIN", f"Force Update: {log_out.decode().strip()}", admin=message.from_user)
        sys.exit(65)
    except Exception as e: await msg.edit_text(f"❌ Error: {e}")

@admin_router.message(Command("clearcache"))
async def cmd_clearcache(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    args = message.text.split()
    minutes = 0
    
    if len(args) > 1:
        param = args[1].lower()
        try:
            if param.endswith('m'):
                minutes = int(param[:-1])
            elif param.endswith('h'):
                minutes = int(param[:-1]) * 60
            elif param.endswith('d'):
                minutes = int(param[:-1]) * 60 * 24
        except:
             await message.answer("❌ Формат: /clearcache 10m / 1h / 1d")
             return

    # Если аргумент был - чистим выборочно
    if minutes > 0:
        await clear_cache_older_than(minutes)
        await message.answer(f"🗑️ Кэш за последние {minutes} мин очищен.")
    else:
        # Иначе полный сброс
        await clear_file_cache()
        await message.answer("🗑️ <b>Весь кэш файлов очищен!</b>", parse_mode="HTML")

@admin_router.message(Command("restart"))
async def cmd_restart(message: types.Message):
    if not is_admin(message.from_user.id): return
    await message.answer("♻️ Перезагрузка...")
    await send_log("ADMIN", "Restart", admin=message.from_user)
    sys.exit(65)

# --- LIMIT ---
@admin_router.message(Command("limit"))
async def cmd_limit(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    args = message.text.split()
    
    # Status output
    if len(args) == 1:
        mode = queue_manager.limit_mode
        active = sum(queue_manager.active_tasks.values())
        await message.answer(
            f"🚦 <b>Limit Status:</b>\n"
            f"Mode: <b>{mode.upper()}</b>\n"
            f"Active tasks: {active}\n\n"
            f"<code>/limit on</code> - Global limit (3)\n"
            f"<code>/limit user</code> - Admin unlimited, others 3\n"
            f"<code>/limit off</code> - No global limit (User &lt;= 3)", # <--- FIXED HERE
            parse_mode="HTML"
        )
        return

    new_mode = args[1].lower()
    if new_mode not in ['on', 'off', 'user']:
        await message.answer("❌ Invalid mode. Use: on / off / user")
        return

    # Apply and save
    queue_manager.set_mode(new_mode)
    await set_system_value("limit_mode", new_mode)
    
    await message.answer(f"✅ Limit mode set to: <b>{new_mode.upper()}</b>", parse_mode="HTML")
    await send_log("ADMIN", f"Limit mode changed -> {new_mode}", admin=message.from_user)