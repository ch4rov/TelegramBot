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
HEALTH_CHECK_URLS = [
    ("YouTube", "https://youtu.be/jNQXAC9IVRw"), 
    ("TikTok", "https://www.tiktok.com/@ch4rov/video/7552260996673375544"), 
    ("SoundCloud", "https://soundcloud.com/yayaheart/prosto-lera-ostav-menya-odnu?si=34569021a68c4f51be2bf943e5b38032&utm_source=clipboard&utm_medium=text&utm_campaign=social_sharing"), # NASA (Audio)
    ("VK Video", "https://vk.com/video-22822305_456239018"),
    ("Instagram", "https://www.instagram.com/reel/DQyynEMinzX/?igsh=NmxhYmN6ZmkzbGE4"), 
    ("Twitch", "https://www.twitch.tv/ch4rov/clip/SmokyDirtyBobaResidentSleeper-geWW-E5kg0Tp-vs8"),
]

def is_admin(user_id):
    env_admin_id = os.getenv("ADMIN_ID")
    if not env_admin_id: return False
    return str(user_id) == str(env_admin_id)

# --- RESTART ---
@router.message(Command("restart"))
async def cmd_restart(message: types.Message):
    if not is_admin(message.from_user.id): return
    try: await message.answer("♻️ Перезагрузка системы...")
    except: pass
    await send_log("ADMIN", "Инициировал перезагрузку (Restart)", admin=message.from_user)
    try:
        with open(".restart_flag", "w") as f: f.write("")
    except: pass
    sys.exit(65)

# --- STATUS ---
@router.message(Command("status"))
async def cmd_status(message: types.Message):
    if not is_admin(message.from_user.id): return
    status_msg = await message.answer("🔍 <b>Запуск диагностики...</b>", parse_mode="HTML")
    report = []
    start_time = time.perf_counter()

    # 1. API Ping
    try:
        t1 = time.perf_counter()
        await message.bot.get_me()
        ping = (time.perf_counter() - t1) * 1000
        status = f"🟢 Online ({ping:.0f}ms)" if ping < 500 else f"🟡 Slow ({ping:.0f}ms)"
    except Exception as e: status = f"🔴 Error: {e}"
    report.append(f"📡 <b>API:</b> {status}")

    # 2. DB
    try:
        t1 = time.perf_counter()
        u = await get_all_users()
        db_ms = (time.perf_counter() - t1) * 1000
        report.append(f"💾 <b>DB:</b> 🟢 ({len(u)} users, {db_ms:.1f}ms)")
    except Exception as e: report.append(f"💾 <b>DB:</b> 🔴 Error: {e}")

    # 3. Disk & System
    try:
        total, _, free = shutil.disk_usage(".")
        report.append(f"💿 <b>Disk:</b> {free / (2**30):.1f}GB free")
    except: pass
    report.append(f"🐍 <b>Py:</b> {sys.version.split()[0]} | {platform.system()}")

    total_time = time.perf_counter() - start_time
    await status_msg.edit_text(f"📊 <b>SYSTEM STATUS</b> ({total_time:.2f}s)\n" + "─"*20 + "\n" + "\n".join(report), parse_mode="HTML")

# --- EXECUTE ---
@router.message(Command("execute", "exec"))
async def cmd_execute(message: types.Message):
    if not is_admin(message.from_user.id): return
    try:
        code = message.text.split(maxsplit=1)[1]
    except: return await message.answer("Usage: `/exec code`", parse_mode="Markdown")
    
    indented = "".join(f"    {line}\n" for line in code.splitlines())
    func_def = f"async def _exec(message, bot, user, reply):\n{indented}"
    loc = {}
    try:
        exec(func_def, globals(), loc)
        await loc['_exec'](message, message.bot, message.from_user, message.reply_to_message)
        try: await message.react([types.ReactionTypeEmoji(emoji="👍")])
        except: pass
    except Exception:
        err = traceback.format_exc()
        if len(err) > 3000: err = err[:3000] + "..."
        await message.answer(f"❌ Error:\n<pre>{err}</pre>", parse_mode="HTML")

# --- HEALTH CHECK (REAL DOWNLOAD TEST) ---
@router.message(Command("check"))
async def cmd_check(message: types.Message):
    if not is_admin(message.from_user.id): return

    status_msg = await message.answer("🏥 <b>Начинаю проверку сервисов...</b>\n<i>(Это реальная загрузка, подождите)</i>", parse_mode="HTML")
    
    report = "📊 <b>HEALTH CHECK REPORT</b>\n" + "─"*20 + "\n"
    success_count = 0
    
    for name, url in HEALTH_CHECK_URLS:
        try: await status_msg.edit_text(report + f"⏳ Testing: <b>{name}</b>...", parse_mode="HTML")
        except: pass

        start = time.perf_counter()
        result_icon = "❓"
        details = ""

        try:
            files, folder, error = await download_content(url)
            duration = time.perf_counter() - start
            
            if error:
                result_icon = "🔴"
                # ИСПРАВЛЕНИЕ: Берем первую строку ошибки целиком (до 150 символов)
                # Убираем лишние пробелы и 'ERROR: ' если есть
                err_clean = str(error).strip()
                if "ERROR:" in err_clean:
                    err_clean = err_clean.split("ERROR:", 1)[1].strip()
                
                # Берем только первую строку (чтобы не спамить путями)
                err_line = err_clean.split('\n')[0]
                
                # Лимит символов побольше
                if len(err_line) > 150: 
                    err_line = err_line[:147] + "..."
                
                # Экранируем HTML теги, чтобы не сломать верстку
                err_line = err_line.replace("<", "&lt;").replace(">", "&gt;")
                details = f"\n❌ <code>{err_line}</code>"
            else:
                if files:
                    result_icon = "🟢"
                    success_count += 1
                    file_size_mb = os.path.getsize(files[0]) / (1024*1024)
                    details = f" <b>{duration:.1f}s</b> | {file_size_mb:.1f}MB"
                else:
                    result_icon = "⚠️"
                    details = " No files found"

            if folder and os.path.exists(folder):
                shutil.rmtree(folder, ignore_errors=True)

        except Exception as e:
            result_icon = "💥"
            details = f"\nException: {str(e)[:100]}"
        
        report += f"{result_icon} <b>{name}</b>{details}\n"

    footer = f"\n🏁 <b>Результат:</b> {success_count}/{len(HEALTH_CHECK_URLS)} работают."
    await status_msg.edit_text(report + footer, parse_mode="HTML")
    await send_log("ADMIN", f"Check ({success_count}/{len(HEALTH_CHECK_URLS)})", admin=message.from_user)

# --- UPDATE ---
@router.message(Command("update"))
async def cmd_update(message: types.Message):
    if not is_admin(message.from_user.id): return
    msg = await message.answer("🔄 <b>Git Pull...</b>", parse_mode="HTML")
    try:
        proc = await asyncio.create_subprocess_shell("git pull", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        res = stdout.decode()
        if "Already up to date" in res: return await msg.edit_text("✅ Версия актуальна.")
        if proc.returncode != 0: return await msg.edit_text(f"❌ Git Error:\n<pre>{stderr.decode()}</pre>", parse_mode="HTML")
        await msg.edit_text(f"✅ Updated!\n<pre>{res}</pre>\n♻️ Restarting...", parse_mode="HTML")
        sys.exit(65)
    except Exception as e: await msg.edit_text(f"❌ Error: {e}")

# --- GET PLACEHOLDER ---
@router.message(Command("get_placeholder"))
async def cmd_get_placeholder(message: types.Message):
    if not is_admin(message.from_user.id): return
    # Универсальная команда для видео
    if not os.path.exists("placeholder.mp4"): return await message.answer("❌ Нет файла placeholder.mp4")
    msg = await message.answer_video(FSInputFile("placeholder.mp4"), caption="Placeholder")
    await message.answer(f"Video ID: <code>{msg.video.file_id}</code>", parse_mode="HTML")

@router.message(Command("get_audio_placeholder"))
async def cmd_get_audio_ph(message: types.Message):
    if not is_admin(message.from_user.id): return
    # Генерируем аудио на лету
    with open("silence.mp3", "wb") as f:
        f.write(binascii.unhexlify("FFF304C40000000348000000004C414D45332E39382E320000000000000000000000000000000000000000000000000000000000000000000000000000000000"))
    msg = await message.answer_audio(FSInputFile("silence.mp3"), title="Loading...", performer="Bot")
    await message.answer(f"Audio ID: <code>{msg.audio.file_id}</code>", parse_mode="HTML")
    os.remove("silence.mp3")

# --- USERS / BAN ---
@router.message(Command("users"))
async def cmd_users(message: types.Message):
    if not is_admin(message.from_user.id): return
    users = await get_all_users()
    txt = f"📋 <b>Users: {len(users)}</b>\n\n"
    for i, u in enumerate(users):
        if i >= 20: 
            txt += "<i>...more...</i>"
            break
        icon = "⛔" if u['is_banned'] else ("💀" if not u['is_active'] else "✅")
        line = f"{icon} <code>{u['user_id']}</code> | @{u['username'] or 'NoName'}\n"
        if u['is_banned'] or not u['is_active']: line = f"<s>{line}</s>"
        txt += line
    await message.answer(txt, parse_mode="HTML")

@router.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if not is_admin(message.from_user.id): return
    try:
        uid = int(message.text.split()[1])
        await set_ban_status(uid, True, "Banned by admin")
        await message.answer(f"⛔ Banned {uid}")
    except: await message.answer("Usage: /ban ID")

@router.message(Command("unban"))
async def cmd_unban(message: types.Message):
    if not is_admin(message.from_user.id): return
    try:
        uid = int(message.text.split()[1])
        await set_ban_status(uid, False)
        await message.answer(f"✅ Unbanned {uid}")
    except: await message.answer("Usage: /unban ID")

@router.message(Command("answer"))
async def cmd_ans(message: types.Message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split(maxsplit=2)
        if message.reply_to_message: uid, txt = message.reply_to_message.from_user.id, args[1]
        else: uid, txt = int(args[1]), args[2]
        await message.bot.send_message(uid, f"📩 <b>Admin:</b>\n{txt}", parse_mode="HTML")
        await message.answer("✅ Sent")
    except: await message.answer("Error")