import os
import sys
import time
import shutil
import subprocess
import platform
import traceback
import binascii
import asyncio
from copy import copy

from aiogram import Router, types, exceptions
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.exceptions import TelegramNetworkError
from aiogram.enums import ChatAction 
from services.database_service import get_all_users, set_ban_status, get_user, clear_file_cache
from logs.logger import send_log
from handlers.message_handler import handle_link 
from core.installs.ffmpeg_installer import check_and_install_ffmpeg

print("📢 [SYSTEM] Модуль handlers/admin_handler.py загружен!")

router = Router()

# --- СПИСОК ДЛЯ ТЕСТА СИСТЕМЫ ---
HEALTH_CHECK_URLS = [
    ("YouTube", "https://youtu.be/jNQXAC9IVRw"), 
    ("YouTube Music", "https://music.youtube.com/watch?v=BvwG48W0tcc&si=7nPv0BXusq5oze8j"),
    ("TikTok", "https://www.tiktok.com/@ch4rov/video/7552260996673375544"), 
    ("SoundCloud", "https://soundcloud.com/yayaheart/prosto-lera-ostav-menya-odnu"), 
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

    status_msg = await message.answer("🔍 <b>Диагностика...</b>", parse_mode="HTML")
    report = []
    start_time_total = time.perf_counter()

    # 1. API Ping
    try:
        t1 = time.perf_counter()
        await message.bot.get_me()
        ping = (time.perf_counter() - t1) * 1000
        st = f"🟢 Online ({ping:.0f}ms)" if ping < 500 else f"🟡 Slow ({ping:.0f}ms)"
    except Exception as e: st = f"🔴 Error: {e}"
    report.append(f"📡 <b>API:</b> {st}")

    # 2. DB
    try:
        t1 = time.perf_counter()
        u = await get_all_users()
        db_ms = (time.perf_counter() - t1) * 1000
        report.append(f"💾 <b>DB:</b> 🟢 ({len(u)} users, {db_ms:.1f}ms)")
    except Exception as e: report.append(f"💾 <b>DB:</b> 🔴 Error: {e}")

    # 3. Tools
    tools_status = []
    local_ffmpeg = os.path.join("core", "installs", "ffmpeg.exe")
    if os.path.exists(local_ffmpeg):
        tools_status.append("FFmpeg: 🟢 (Local)")
    elif shutil.which("ffmpeg"):
        tools_status.append("FFmpeg: 🟢 (System)")
    else:
        tools_status.append("FFmpeg: 🔴 (Missing)")

    try: 
        import yt_dlp; v = yt_dlp.version.__version__; tools_status.append(f"yt-dlp: 🟢 (v{v})")
    except: tools_status.append("yt-dlp: 🔴")
    
    report.append(f"🛠 <b>Tools:</b> " + " | ".join(tools_status))
    
    # 4. Disk & System
    try:
        total, _, free = shutil.disk_usage(".")
        report.append(f"💿 <b>Disk:</b> {free / (2**30):.1f}GB free")
    except: pass
    report.append(f"🐍 <b>Py:</b> {sys.version.split()[0]} | {platform.system()}")

    total_time = time.perf_counter() - start_time_total
    await status_msg.edit_text(f"📊 <b>SYSTEM STATUS</b> ({total_time:.2f}s)\n" + "─"*20 + "\n" + "\n".join(report), parse_mode="HTML")

# --- CHECK (ИМИТАЦИЯ) ---
@router.message(Command("check"))
async def cmd_check(message: types.Message):
    if not is_admin(message.from_user.id): return

    status_msg = await message.answer("🏥 <b>Начинаю проверку...</b>", parse_mode="HTML")
    
    for name, url in HEALTH_CHECK_URLS:
        try:
            await status_msg.edit_text(f"⏳ Тестирую: <b>{name}</b>...\nСсылка: {url}", parse_mode="HTML")
            
            fake_message = message.model_copy(update={'text': url})
            await handle_link(fake_message)
            await asyncio.sleep(2)
        except Exception as e:
            await message.answer(f"❌ Ошибка в тесте {name}: {e}")

    await status_msg.edit_text("✅ <b>Проверка завершена!</b>\nПроверьте сообщения выше.", parse_mode="HTML")
    await send_log("ADMIN", "Health Check завершен", admin=message.from_user)

@router.message(Command("update"))
async def cmd_update(message: types.Message):
    if not is_admin(message.from_user.id): return

    status_msg = await message.answer("🔄 <b>Принудительное обновление...</b>", parse_mode="HTML")
    
    try:
        await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
        
        # 1. Fetch
        proc_fetch = await asyncio.create_subprocess_shell(
            "git fetch origin",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc_fetch.communicate()

        # 2. Hard Reset (Затираем локальные изменения, кроме .env и DB)
        proc_reset = await asyncio.create_subprocess_shell(
            "git reset --hard origin/main",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc_reset.communicate()
        
        if proc_reset.returncode != 0:
            await status_msg.edit_text(f"❌ <b>Ошибка Git:</b>\n<pre>{stderr.decode()}</pre>", parse_mode="HTML")
            return

        # Получаем инфо о коммите
        proc_log = await asyncio.create_subprocess_shell("git log -1 --pretty=%B", stdout=asyncio.subprocess.PIPE)
        log_out, _ = await proc_log.communicate()
        commit_msg = log_out.decode().strip()

        await status_msg.edit_text(
            f"✅ <b>Обновлено успешно!</b>\n"
            f"📝 Коммит: <i>{commit_msg}</i>\n\n"
            f"♻️ Перезапуск...", 
            parse_mode="HTML"
        )
        
        await send_log("ADMIN", f"Система обновлена (Force Update). Коммит: {commit_msg}", admin=message.from_user)
        sys.exit(65)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Критическая ошибка: {e}")

# --- CLEAR CACHE ---
@router.message(Command("clearcache"))
async def cmd_clearcache(message: types.Message):
    if not is_admin(message.from_user.id): return
    try:
        await clear_file_cache()
        await message.answer("🗑️ <b>Кэш файлов (File IDs) очищен!</b>", parse_mode="HTML")
        await send_log("ADMIN", "Очистил кэш (/clearcache)", admin=message.from_user)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# --- FIX FFMPEG ---
@router.message(Command("fix_ffmpeg"))
async def cmd_fix_ffmpeg(message: types.Message):
    if not is_admin(message.from_user.id): return
    msg = await message.answer("🛠 <b>Установка FFmpeg...</b>", parse_mode="HTML")
    try:
        await asyncio.to_thread(check_and_install_ffmpeg)
        if os.path.exists(os.path.join("core", "installs", "ffmpeg.exe")):
            await msg.edit_text("✅ <b>FFmpeg установлен!</b>")
        else:
            await msg.edit_text("❌ Файл не найден после установки.")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

# --- EXECUTE ---
@router.message(Command("execute", "exec"))
async def cmd_execute(message: types.Message):
    if not is_admin(message.from_user.id): return

    try:
        code = message.text.split(maxsplit=1)[1]
    except IndexError:
        await message.answer("💻 <b>Exec:</b> <code>/exec code</code>", parse_mode="HTML")
        return

    reply = message.reply_to_message
    user = message.from_user
    bot = message.bot
    import settings 
    
    indented_code = "".join(f"    {line}\n" for line in code.splitlines())
    func_def = f"async def _exec_func(message, bot, user, reply, settings):\n{indented_code}"
    
    local_vars = {}
    try:
        exec(func_def, globals(), local_vars)
        await local_vars['_exec_func'](message, bot, user, reply, settings)
        try: await message.react([types.ReactionTypeEmoji(emoji="👍")])
        except: await message.answer("✅ Выполнено")
    except Exception:
        error_msg = traceback.format_exc()
        if len(error_msg) > 3500: error_msg = error_msg[:3500] + "..."
        await message.answer(f"❌ <b>Error:</b>\n{error_msg}", parse_mode=None)

# --- GET PLACEHOLDER ---
@router.message(Command("get_placeholder"))
async def cmd_get_placeholder(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    filename = "temp_video_ph.mp4"
    wait_msg = await message.answer("📤 Генерирую видео-заглушку...")
    
    try:
        local_ffmpeg = os.path.join("core", "installs", "ffmpeg.exe")
        ffmpeg_cmd = local_ffmpeg if os.path.exists(local_ffmpeg) else "ffmpeg"
        
        subprocess.run([
            ffmpeg_cmd, "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:d=1",
            "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p", "-f", "mp4", filename
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
        video = FSInputFile(filename)
        sent_message = await message.answer_video(video, caption="Video Placeholder")
        file_id = sent_message.video.file_id
        
        await wait_msg.delete()
        await message.answer(f"✅ <b>Video ID:</b>\n<code>{file_id}</code>", parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка генерации: {e}")
    finally:
        if os.path.exists(filename): os.remove(filename)

@router.message(Command("get_audio_placeholder"))
async def cmd_get_audio_placeholder(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    file_path = "silence.mp3"
    mp3_hex = "FFF304C40000000348000000004C414D45332E39382E320000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    
    with open(file_path, "wb") as f: f.write(binascii.unhexlify(mp3_hex))

    try:
        bot_info = await message.bot.get_me()
        msg = await message.answer_audio(
            FSInputFile(file_path), 
            title="Searching...", 
            performer=f"@{bot_info.username}"
        )
        await message.answer(f"Audio ID: <code>{msg.audio.file_id}</code>", parse_mode="HTML")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

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
        name = str(u['username']).replace("<", "&lt;") if u['username'] else "NoName"
        line = f"{icon} <code>{u['user_id']}</code> | @{name}\n"
        if u['is_banned'] or not u['is_active']: line = f"<s>{line}</s>"
        txt += line
    await message.answer(txt, parse_mode="HTML")

@router.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 2: raise ValueError
        uid = int(args[1])
        reason = args[2] if len(args) > 2 else "Admin ban"
        await set_ban_status(uid, True, reason)
        await message.answer(f"⛔ Banned {uid}")
    except: await message.answer("Usage: <code>/ban ID [Reason]</code>", parse_mode="HTML")

@router.message(Command("unban"))
async def cmd_unban(message: types.Message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split()
        if len(args) < 2: raise ValueError
        uid = int(args[1])
        await set_ban_status(uid, False)
        await message.answer(f"✅ Unbanned {uid}")
    except: await message.answer("Usage: <code>/unban ID</code>", parse_mode="HTML")

@router.message(Command("answer"))
async def cmd_answer(message: types.Message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split(maxsplit=2)
        if message.reply_to_message: uid, txt = message.reply_to_message.from_user.id, args[1]
        else: uid, txt = int(args[1]), args[2]
        await message.bot.send_message(uid, f"📩 <b>Admin:</b>\n{txt}", parse_mode="HTML")
        await message.answer("✅ Sent")
    except: await message.answer("Usage: <code>/answer ID TEXT</code> or reply", parse_mode="HTML")

# --- UPDATE ---
@router.message(Command("update"))
async def cmd_update(message: types.Message):
    if not is_admin(message.from_user.id): return
    msg = await message.answer("🔄 <b>Принудительное обновление...</b>", parse_mode="HTML")
    try:
        # 1. Fetch
        await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
        proc_fetch = await asyncio.create_subprocess_shell(
            "git fetch origin",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc_fetch.communicate()

        # 2. Hard Reset
        proc_reset = await asyncio.create_subprocess_shell(
            "git reset --hard origin/main",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc_reset.communicate()
        
        if proc_reset.returncode != 0:
            await msg.edit_text(f"❌ <b>Ошибка Git:</b>\n<pre>{stderr.decode()}</pre>", parse_mode="HTML")
            return

        # 3. Log info
        proc_log = await asyncio.create_subprocess_shell("git log -1 --pretty=%B", stdout=asyncio.subprocess.PIPE)
        log_out, _ = await proc_log.communicate()
        commit_msg = log_out.decode().strip()

        await msg.edit_text(
            f"✅ <b>Обновлено успешно!</b>\n"
            f"📝 Коммит: <i>{commit_msg}</i>\n\n"
            f"♻️ Перезапуск...", 
            parse_mode="HTML"
        )
        await send_log("ADMIN", f"Система обновлена (Force Update). Коммит: {commit_msg}", admin=message.from_user)
        sys.exit(65)
        
    except Exception as e:
        await msg.edit_text(f"❌ Критическая ошибка: {e}")