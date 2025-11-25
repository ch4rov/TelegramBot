import os
import sys
import time
import shutil
import subprocess
import platform
import traceback
import binascii
from datetime import datetime

from aiogram import Router, types, exceptions
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.exceptions import TelegramNetworkError

# Импорты сервисов
from services.database_service import get_all_users, set_ban_status, get_user
from logs.logger import send_log
from services.downloads import download_content

print("📢 [SYSTEM] Модуль handlers/admin_handler.py загружен!")

router = Router()

def is_admin(user_id):
    """Проверка прав администратора"""
    env_admin_id = os.getenv("ADMIN_ID")
    if not env_admin_id:
        return False
    return str(user_id) == str(env_admin_id)

# --- RESTART ---
@router.message(Command("restart"))
async def cmd_restart(message: types.Message):
    if not is_admin(message.from_user.id): return

    try: await message.answer("♻️ Перезагрузка системы...")
    except: pass
    
    await send_log("ADMIN", "Инициировал перезагрузку (Restart)", admin=message.from_user)
    
    # Создаем флаг рестарта (для некоторых хостингов)
    try:
        with open(".restart_flag", "w") as f: f.write("")
    except: pass
    
    sys.exit(65)

# --- STATUS (MONITOR) ---
@router.message(Command("status"))
async def cmd_status(message: types.Message):
    if not is_admin(message.from_user.id): return

    status_msg = await message.answer("🔍 <b>Диагностика...</b>", parse_mode="HTML")
    report = []
    start_time_total = time.perf_counter()

    # 1. Telegram API Ping
    try:
        t_start = time.perf_counter()
        await message.bot.get_me()
        ping_ms = (time.perf_counter() - t_start) * 1000
        if ping_ms < 200: api_status = f"🟢 Online ({ping_ms:.0f}ms)"
        elif ping_ms < 500: api_status = f"🟡 Slow ({ping_ms:.0f}ms)"
        else: api_status = f"🟠 High Latency ({ping_ms:.0f}ms)"
    except Exception as e: api_status = f"🔴 Error: {e}"
    report.append(f"📡 <b>API:</b> {api_status}")

    # 2. Database
    try:
        t_start = time.perf_counter()
        users = await get_all_users()
        db_ms = (time.perf_counter() - t_start) * 1000
        report.append(f"💾 <b>DB:</b> 🟢 ({len(users)} users, {db_ms:.1f}ms)")
    except Exception as e: report.append(f"💾 <b>DB:</b> 🔴 Error: {e}")

    # 3. Disk
    try:
        total, used, free = shutil.disk_usage(".")
        free_gb = free / (2**30)
        report.append(f"💿 <b>Disk:</b> {free_gb:.1f}GB free")
    except: report.append("💿 <b>Disk:</b> ⚠️ Error")

    # 4. System
    try:
        with open("VERSION", "r") as f: ver = f.read().strip()
    except: ver = "dev"
    report.append(f"📦 <b>Ver:</b> <code>{ver}</code> | Py {sys.version.split()[0]}")

    total_time = (time.perf_counter() - start_time_total)
    header = f"📊 <b>SYSTEM STATUS</b> (took {total_time:.2f}s)\n" + "─"*20
    
    await status_msg.edit_text(header + "\n" + "\n".join(report), parse_mode="HTML")
    await send_log("ADMIN", "> /status", admin=message.from_user)

# --- EXECUTE (RCE) ---
@router.message(Command("execute", "exec"))
async def cmd_execute(message: types.Message):
    if not is_admin(message.from_user.id): return

    try:
        code = message.text.split(maxsplit=1)[1]
    except IndexError:
        await message.answer("💻 <b>Exec:</b> <code>/exec code</code>", parse_mode="HTML")
        return

    indented_code = "".join(f"    {line}\n" for line in code.splitlines())
    func_def = f"async def _exec_func(message, bot, user, reply):\n{indented_code}"
    
    local_vars = {}
    try:
        exec(func_def, globals(), local_vars)
        await local_vars['_exec_func'](message, message.bot, message.from_user, message.reply_to_message)
        try: await message.react([types.ReactionTypeEmoji(emoji="👍")])
        except: pass
    except Exception:
        error_msg = traceback.format_exc()
        if len(error_msg) > 3000: error_msg = error_msg[:3000] + "..."
        await message.answer(f"❌ <b>Error:</b>\n<pre>{error_msg}</pre>", parse_mode="HTML")

# --- GET AUDIO PLACEHOLDER ---
@router.message(Command("get_audio_placeholder"))
async def cmd_get_audio_placeholder(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    file_path = "silence.mp3"
    # 1 секунда тишины (MP3 Hex)
    mp3_hex = "FFF304C40000000348000000004C414D45332E39382E3200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    
    with open(file_path, "wb") as f:
        f.write(binascii.unhexlify(mp3_hex))

    wait_msg = await message.answer("📤 Uploading audio placeholder...")
    try:
        audio = FSInputFile(file_path)
        sent_message = await message.answer_audio(audio, title="Searching...", performer="@ch4roff_bot")
        file_id = sent_message.audio.file_id
        await wait_msg.delete()
        await message.answer(f"✅ <b>Audio ID:</b>\n<code>{file_id}</code>", parse_mode="HTML")
        os.remove(file_path)
    except Exception as e:
        await message.answer(f"Error: {e}")

# --- GET VIDEO PLACEHOLDER ---
@router.message(Command("get_placeholder"))
async def cmd_get_placeholder(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    file_path = "placeholder.mp4" 
    if not os.path.exists(file_path):
        await message.answer(f"❌ Файл `{file_path}` не найден.")
        return

    wait_msg = await message.answer("📤 Uploading video placeholder...")
    try:
        video = FSInputFile(file_path)
        sent_message = await message.answer_video(video, caption="Loading...")
        file_id = sent_message.video.file_id
        await wait_msg.delete()
        await message.answer(f"✅ <b>Video ID:</b>\n<code>{file_id}</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"Error: {e}")

# --- USERS LIST ---
@router.message(Command("users"))
async def cmd_users(message: types.Message):
    if not is_admin(message.from_user.id): return

    users = await get_all_users()
    if not users:
        await message.answer("📂 Empty DB.")
        return

    text = f"📋 <b>Users: {len(users)}</b>\n\n"
    count = 0
    for u in users:
        if count >= 20:
            text += "\n<i>...more...</i>"
            break

        status_icon = "✅"
        is_dead = False
        if u['is_banned']: 
            status_icon = "⛔"; is_dead = True
        elif not u['is_active']: 
            status_icon = "💀"; is_dead = True

        clean_name = str(u['username']).replace("<", "&lt;") if u['username'] else "NoName"
        line = f"{status_icon} <code>{u['user_id']}</code> | @{clean_name}\n"
        
        if is_dead: line = f"<s>{line}</s>"
        text += line
        count += 1
        
    await message.answer(text, parse_mode="HTML")

# --- BAN / UNBAN / ANSWER ---
@router.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if not is_admin(message.from_user.id): return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2: return await message.answer("Usage: /ban ID [Reason]")
    try:
        uid, reason = int(parts[1]), parts[2] if len(parts) > 2 else "Rule Violation"
        await set_ban_status(uid, True, reason)
        await message.answer(f"⛔ Banned {uid}")
        await send_log("ADMIN", f"Banned {uid}: {reason}", admin=message.from_user)
        try: await message.bot.send_message(uid, f"⛔ You are banned: {reason}")
        except: pass
    except: await message.answer("Error")

@router.message(Command("unban"))
async def cmd_unban(message: types.Message):
    if not is_admin(message.from_user.id): return
    try:
        uid = int(message.text.split()[1])
        await set_ban_status(uid, False)
        await message.answer(f"✅ Unbanned {uid}")
        try: await message.bot.send_message(uid, "✅ Unbanned")
        except: pass
    except: pass

@router.message(Command("answer"))
async def cmd_answer(message: types.Message):
    if not is_admin(message.from_user.id): return
    # Логика ответа (упрощенная)
    try:
        if message.reply_to_message:
            uid = message.reply_to_message.from_user.id
            txt = message.text.split(maxsplit=1)[1]
        else:
            uid = int(message.text.split()[1])
            txt = message.text.split(maxsplit=2)[2]
        
        await message.bot.send_message(uid, f"📩 <b>Admin:</b>\n{txt}", parse_mode="HTML")
        await message.answer("✅ Sent.")
    except: await message.answer("Usage: /answer ID TEXT or Reply")