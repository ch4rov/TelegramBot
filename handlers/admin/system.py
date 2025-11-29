import sys
import time
import shutil
import subprocess
import platform
import asyncio
from aiogram import types
from aiogram.filters import Command
from aiogram.enums import ChatAction

from .router import admin_router, is_admin
from services.database_service import get_all_users, clear_file_cache, get_module_status, set_module_status
from logs.logger import send_log
from core.installs.ffmpeg_installer import check_and_install_ffmpeg
import settings

# --- STATUS ---
@admin_router.message(Command("status"))
async def cmd_status(message: types.Message):
    if not is_admin(message.from_user.id): return

    status_msg = await message.answer("🔍 <b>Диагностика...</b>", parse_mode="HTML")
    report = []
    start_time_total = time.perf_counter()

    # API Ping
    try:
        t1 = time.perf_counter()
        await message.bot.get_me()
        ping_ms = (time.perf_counter() - t1) * 1000
        st = f"🟢 Online ({ping_ms:.0f}ms)" if ping_ms < 500 else f"🟡 Slow"
    except Exception as e: st = f"🔴 Error: {e}"
    report.append(f"📡 <b>API:</b> {st}")

    # Server Mode
    try:
        import requests
        if settings.USE_LOCAL_SERVER:
            r = requests.get(settings.LOCAL_SERVER_URL, timeout=1)
            docker_st = "🟢 Docker OK" if r.status_code < 500 else "🔴 Docker Error"
        else:
            docker_st = "☁️ Cloud Mode"
        report.append(f"🖥️ <b>Server:</b> {docker_st}")
    except: report.append("🖥️ <b>Server:</b> 🔴 Down")

    # Tools
    tools_status = []
    local_ffmpeg = os.path.join("core", "installs", "ffmpeg.exe")
    if os.path.exists(local_ffmpeg): tools_status.append("FFmpeg: 🟢 (Local)")
    elif shutil.which("ffmpeg"): tools_status.append("FFmpeg: 🟢 (System)")
    else: tools_status.append("FFmpeg: 🔴")
    
    report.append(f"🛠 <b>Tools:</b> " + " | ".join(tools_status))
    
    # Disk
    try:
        total, _, free = shutil.disk_usage(".")
        report.append(f"💿 <b>Disk:</b> {free / (2**30):.1f}GB free")
    except: pass

    total_time = time.perf_counter() - start_time_total
    await status_msg.edit_text(f"📊 <b>SYSTEM STATUS</b> ({total_time:.2f}s)\n" + "─"*20 + "\n" + "\n".join(report), parse_mode="HTML")
    await send_log("ADMIN", "> /status", admin=message.from_user)

# --- MODULES ---
@admin_router.message(Command("modules"))
async def cmd_modules(message: types.Message):
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    
    if len(args) == 1:
        text = "🎛 <b>Управление модулями:</b>\n\n"
        for mod in settings.MODULES_LIST:
            is_on = await get_module_status(mod)
            icon = "🟢" if is_on else "🔴"
            text += f"{icon} <b>{mod}</b> — <code>/modules {mod}</code>\n"
        await message.answer(text, parse_mode="HTML")
        return

    module_name = args[1]
    target_mod = next((m for m in settings.MODULES_LIST if m.lower() == module_name.lower()), None)
    if not target_mod:
        await message.answer("❌ Неизвестный модуль.")
        return

    current = await get_module_status(target_mod)
    await set_module_status(target_mod, not current)
    st_text = "ВКЛЮЧЕН 🟢" if not current else "ОТКЛЮЧЕН 🔴"
    await message.answer(f"Модуль <b>{target_mod}</b> теперь {st_text}", parse_mode="HTML")
    await send_log("ADMIN", f"Module {target_mod} -> {not current}", admin=message.from_user)

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
    await clear_file_cache()
    await message.answer("🗑️ <b>Кэш файлов очищен!</b>", parse_mode="HTML")

@admin_router.message(Command("fix_ffmpeg"))
async def cmd_fix_ffmpeg(message: types.Message):
    if not is_admin(message.from_user.id): return
    msg = await message.answer("🛠 <b>Установка FFmpeg...</b>", parse_mode="HTML")
    try:
        await asyncio.to_thread(check_and_install_ffmpeg)
        if os.path.exists("core/installs/ffmpeg.exe"):
            await msg.edit_text("✅ <b>FFmpeg установлен!</b>")
        else:
            await msg.edit_text("❌ Файл не найден.")
    except Exception as e: await msg.edit_text(f"❌ Ошибка: {e}")

@admin_router.message(Command("restart"))
async def cmd_restart(message: types.Message):
    if not is_admin(message.from_user.id): return
    await message.answer("♻️ Перезагрузка...")
    await send_log("ADMIN", "Restart", admin=message.from_user)
    sys.exit(65)