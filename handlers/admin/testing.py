import os
import time
import shutil
import binascii
import traceback
import asyncio
import subprocess
from copy import copy
from aiogram import types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.enums import ChatAction

from .router import admin_router, is_admin
from logs.logger import send_log
# Импортируем загрузчик
from services.platforms.platform_manager import download_content

HEALTH_CHECK_URLS = [
    ("YouTube", "https://youtu.be/jNQXAC9IVRw"), 
    ("YouTube Music", "https://music.youtube.com/watch?v=BvwG48W0tcc&si=7nPv0BXusq5oze8j"),
    ("TikTok", "https://www.tiktok.com/@ch4rov/video/7552260996673375544"), 
    ("SoundCloud", "https://soundcloud.com/yayaheart/prosto-lera-ostav-menya-odnu"), 
    ("VK Video", "https://vk.com/video-22822305_456239018"),
    ("Instagram", "https://www.instagram.com/reel/DQyynEMinzX/?igsh=NmxhYmN6ZmkzbGE4"), 
    ("Twitch", "https://www.twitch.tv/ch4rov/clip/SmokyDirtyBobaResidentSleeper-geWW-E5kg0Tp-vs8"),
    ("Spotify", "https://open.spotify.com/track/7ouMYWpwJ422jRcDASZB7P?si=1234567890abcdef"),

]

@admin_router.message(Command("check"))
async def cmd_check(message: types.Message):
    if not is_admin(message.from_user.id): return

    # Импортируем хендлер внутри функции, чтобы избежать Circular Import
    from handlers.user.content import handle_link 

    status_msg = await message.answer("🏥 <b>Начинаю проверку...</b>", parse_mode="HTML")
    success_count = 0
    
    for name, url in HEALTH_CHECK_URLS:
        try:
            await status_msg.edit_text(f"⏳ Тестирую: <b>{name}</b>...\nСсылка: <code>{url}</code>", parse_mode="HTML", disable_web_page_preview=True)
            
            # Создаем фейковое сообщение
            fake_message = message.model_copy(update={'text': url})
            
            # Вызываем реальный обработчик
            await handle_link(fake_message)
            
            # Если handle_link отработал без исключений - считаем успехом
            # (Хотя реальную проверку скачивания лучше делать через download_content, 
            # но handle_link тестирует весь пайплайн вместе с отправкой)
            success_count += 1
            
            await asyncio.sleep(3)
        except Exception as e:
            await message.answer(f"❌ Ошибка в тесте {name}: {e}")

    await status_msg.edit_text(f"✅ <b>Проверка завершена!</b>\nТестов пройдено: {success_count}/{len(HEALTH_CHECK_URLS)}", parse_mode="HTML")
    await send_log("ADMIN", "Health Check завершен", admin=message.from_user)

# --- EXECUTE ---
@admin_router.message(Command("execute", "exec"))
async def cmd_execute(message: types.Message):
    if not is_admin(message.from_user.id): return
    try:
        code = message.text.split(maxsplit=1)[1]
    except IndexError:
        await message.answer("💻 <b>Exec:</b> <code>/exec code</code>", parse_mode="HTML")
        return

    import settings # Для доступа внутри exec
    
    indented_code = "".join(f"    {line}\n" for line in code.splitlines())
    func_def = f"async def _exec_func(message, bot, user, reply, settings):\n{indented_code}"
    
    local_vars = {}
    try:
        exec(func_def, globals(), local_vars)
        await local_vars['_exec_func'](message, message.bot, message.from_user, message.reply_to_message, settings)
        try: await message.react([types.ReactionTypeEmoji(emoji="👍")])
        except: await message.answer("✅ Выполнено")
    except Exception:
        error_msg = traceback.format_exc()
        if len(error_msg) > 3500: error_msg = error_msg[:3500] + "..."
        await message.answer(f"❌ <b>Error:</b>\n<pre>{error_msg}</pre>", parse_mode="HTML")