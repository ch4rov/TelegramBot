import html
import json
import time
import os
from aiogram import F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command

from .router import user_router, check_access_and_update
from services.database_service import set_lastfm_username, save_user_cookie, get_module_status, set_user_language
from logs.logger import send_log
from languages import t
import settings

ADMIN_ID = os.getenv("ADMIN_ID")

def convert_json_to_netscape(json_content: str) -> str:
    # (Код конвертера без изменений, скопируй его или оставь)
    try:
        cookies = json.loads(json_content)
        lines = ["# Netscape HTTP Cookie File"]
        for c in cookies:
            d = c.get('domain', ''); p = c.get('path', '/'); n = c.get('name', ''); v = c.get('value', '')
            if not d.startswith('.') and d.count('.') > 1: d = '.' + d
            f = "TRUE" if d.startswith('.') else "FALSE"; s = "TRUE" if c.get('secure') else "FALSE"
            e = str(int(c.get('expirationDate', time.time() + 31536000)))
            lines.append(f"{d}\t{f}\t{p}\t{s}\t{e}\t{n}\t{v}")
        return "\n".join(lines)
    except: return None

async def build_services_list() -> str:
    services = []
    if await get_module_status("YouTube"): services.append("📺 YouTube")
    tt = await get_module_status("TikTokVideos") or await get_module_status("TikTokPhotos")
    if tt: services.append("🎵 TikTok")
    if await get_module_status("Instagram"): services.append("📸 Instagram")
    if await get_module_status("VK"): services.append("🔵 VK")
    if await get_module_status("SoundCloud"): services.append("☁️ SoundCloud")
    if await get_module_status("Twitch"): services.append("👾 Twitch")
    if await get_module_status("Spotify"): services.append("🎧 Spotify")
    if await get_module_status("YandexMusic"): services.append("🟡 Yandex Music")
    if await get_module_status("AppleMusic"): services.append("🍎 Apple Music")
    return ", ".join(services) if services else "❌"

@user_router.message(CommandStart())
async def cmd_start(message: types.Message):
    # Получаем язык при проверке
    can, is_new, _, lang = await check_access_and_update(message.from_user, message)
    if not can: return
    
    user_id = message.from_user.id
    bot_info = await message.bot.get_me()
    
    # 1. Приветствие
    hello = await t(user_id, 'start_hello', name=html.escape(message.from_user.first_name))
    
    # 2. Сервисы
    serv_list = await build_services_list()
    
    # 3. Меню
    is_admin = str(user_id) == str(ADMIN_ID)
    
    # Функция для форматирования строки меню с переводом
    async def fmt(key, desc_key, copy):
        # Переводим описание команды!
        translated_desc = await t(user_id, desc_key)
        icon = "🔹"
        if copy: return f"{icon} <code>/{key}</code> — {translated_desc}\n"
        return f"{icon} /{key} — {translated_desc}\n"

    menu_txt = f"{hello}\n\n🚀 <b>Services:</b>\n{serv_list}\n\n🤖 <b>Menu:</b>\n"
    
    # Перебираем команды
    for key, desc_key, cat, copy in settings.BOT_COMMANDS_LIST:
        if cat == "user":
            menu_txt += await fmt(key, desc_key, copy)
            
    if await get_module_status("TelegramVideo"):
        vn_desc = await t(user_id, 'cmd_videomessage')
        menu_txt += f"🔹 /videomessage — {vn_desc}\n"

    if is_admin:
        menu_txt += await t(user_id, 'menu_admin_mod') # Заголовок админки
        for key, desc_key, cat, copy in settings.BOT_COMMANDS_LIST:
            if cat == "admin_mod":
                line = await fmt(key, desc_key, copy)
                menu_txt += line.replace("🔹", "🔸")
                
        menu_txt += await t(user_id, 'menu_admin_tech')
        for key, desc_key, cat, copy in settings.BOT_COMMANDS_LIST:
            if cat == "admin_tech":
                line = await fmt(key, desc_key, copy)
                menu_txt += line.replace("🔹", "🔧")

    await message.answer(menu_txt, parse_mode="HTML")
    if is_new: await send_log("NEW_USER", f"New: {message.from_user.full_name}", user=message.from_user)

@user_router.message(Command("menu"))
async def cmd_menu(message: types.Message): await cmd_start(message)

@user_router.message(Command("login"))
async def cmd_login(message: types.Message):
    can, _, _, _ = await check_access_and_update(message.from_user, message)
    if not can: return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("🔑 <code>/login username</code>", parse_mode="HTML")
        return
    await set_lastfm_username(message.from_user.id, parts[1])
    await message.answer(f"✅ OK: <b>{parts[1]}</b>", parse_mode="HTML")

@user_router.message(Command("language"))
async def cmd_lang(message: types.Message):
    can, _, _, lang = await check_access_and_update(message.from_user, message)
    if not can: return
    txt = await t(message.from_user.id, 'language_select')
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇸 English", callback_data="lang:en"),
         InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")],
        [InlineKeyboardButton(text="🇵🇱 Polski", callback_data="lang:pl")]
    ])
    await message.answer(txt, reply_markup=kb, parse_mode="HTML")

@user_router.callback_query(F.data.startswith("lang:"))
async def lang_cb(callback: types.CallbackQuery):
    code = callback.data.split(":")[1]
    await set_user_language(callback.from_user.id, code)
    txt = await t(callback.from_user.id, 'language_set')
    await callback.message.edit_text(txt, parse_mode="HTML")

# --- COOKIES ---
@user_router.message(F.document)
async def handle_document(message: types.Message):
    if message.document.file_name and message.document.file_name.lower() == "cookies.txt":
        # FIXED UNPACKING
        can, _, _, _ = await check_access_and_update(message.from_user, message)
        if not can: return
        file = await message.bot.get_file(message.document.file_id)
        
        from services.platforms.TelegramDownloader.workflow import fix_local_path
        file_path = fix_local_path(file.file_path, message.bot.token)
        
        res = await message.bot.download_file(file_path)
        content = res.read().decode('utf-8', errors='ignore')
        
        if content.strip().startswith(('[', '{')):
            converted = convert_json_to_netscape(content)
            if converted: content = converted
            
        await save_user_cookie(message.from_user.id, content)
        
        txt = await t(message.from_user.id, 'cookies_saved')
        await message.answer(txt, parse_mode="HTML")
        await send_log("INFO", f"User uploaded cookies", user=message.from_user)