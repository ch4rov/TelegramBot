import html
import json
import time
import os
from aiogram import F, types
from aiogram.filters import CommandStart, Command

from .router import user_router, check_access_and_update
from services.database_service import set_lastfm_username, save_user_cookie, get_module_status
from logs.logger import send_log
import messages as msg 
import settings

ADMIN_ID = os.getenv("ADMIN_ID")

def convert_json_to_netscape(json_content: str) -> str:
    try:
        cookies = json.loads(json_content)
        netscape_lines = ["# Netscape HTTP Cookie File"]
        for cookie in cookies:
            domain = cookie.get('domain', '')
            if not domain.startswith('.') and domain.count('.') > 1: domain = '.' + domain
            flag = "TRUE" if domain.startswith('.') else "FALSE"
            path = cookie.get('path', '/')
            secure = "TRUE" if cookie.get('secure') else "FALSE"
            expiration = str(int(cookie.get('expirationDate', time.time() + 31536000)))
            name, value = cookie.get('name', ''), cookie.get('value', '')
            netscape_lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}")
        return "\n".join(netscape_lines)
    except Exception: return None

async def build_start_message(bot_username: str) -> tuple[str, str]:
    """
    Генерирует два текста: список сервисов и инструкцию,
    основываясь на статусе модулей в БД.
    """
    
    # 1. СПИСОК СЕРВИСОВ
    services = []
    if await get_module_status("YouTube"): services.append("📺 <b>YouTube</b>")
    
    tt_vid = await get_module_status("TikTokVideos")
    tt_photo = await get_module_status("TikTokPhotos")
    if tt_vid or tt_photo: services.append(f"🎵 <b>TikTok</b>")
    
    if await get_module_status("Instagram"): services.append("📸 <b>Instagram</b>")
    if await get_module_status("VK"): services.append("🔵 <b>VK Video</b>")
    if await get_module_status("SoundCloud"): services.append("☁️ <b>SoundCloud</b>")
    if await get_module_status("Twitch"): services.append("👾 <b>Twitch</b>")
    if await get_module_status("Spotify"): services.append("🎧 <b>Spotify</b>")
    
    services_text = ", ".join(services) if services else "❌ <i>Нет активных сервисов</i>"

    # 2. ИНСТРУКЦИЯ (USAGE)
    usage_lines = []
    counter = 1

    # -- Пункт 1: ЛС (Ссылки + Текст) --
    text_find = await get_module_status("TextFind")
    if text_find:
        usage_lines.append(f"{counter}. <b>Личные сообщения:</b> Отправь ссылку на видео или название трека.")
    else:
        usage_lines.append(f"{counter}. <b>Личные сообщения:</b> Отправь ссылку на видео.")
    counter += 1

    # -- Пункт 2: Инлайн --
    inline_aud = await get_module_status("InlineAudio")
    inline_vid = await get_module_status("InlineVideo")
    
    if inline_aud or inline_vid:
        inline_parts = []
        if inline_aud:
            inline_parts.append(f"<code>@{bot_username} песня</code> для поиска музыки")
        if inline_vid:
            inline_parts.append(f"<code>@{bot_username} ссылка</code> для отправки видео")
            
        joiner = " или " if (inline_aud and inline_vid) else ""
        text = f"{counter}. <b>Инлайн:</b> Напиши {joiner.join(inline_parts)}."
        usage_lines.append(text)
        counter += 1

    # -- Пункт 3: Видеосообщения --
    if await get_module_status("TelegramVideo"):
        usage_lines.append(f"{counter}. <b>Видео-сообщения:</b> Команда /videomessage для создания \"кружочков\".")

    return services_text, "\n".join(usage_lines)

@user_router.message(CommandStart())
async def cmd_start(message: types.Message):
    can, is_new = await check_access_and_update(message.from_user, message)
    if not can: return
    
    bot_info = await message.bot.get_me()
    
    # Генерируем динамический текст
    services_txt, usage_txt = await build_start_message(bot_info.username)
    
    welcome_text = msg.MSG_START.format(
        name=html.escape(message.from_user.first_name),
        services_text=services_txt,
        usage_text=usage_txt
    )
    
    await message.answer(welcome_text, parse_mode="HTML")
    
    # Меню команд
    is_admin_user = str(message.from_user.id) == str(ADMIN_ID)
    text = "🤖 <b>Меню команд</b>\n\n"
    def format_cmd(cmd, desc, copy):
        return f"🔹 <code>/{cmd}</code> — {desc}\n" if copy else f"🔹 /{cmd} — {desc}\n"

    text += "👤 <b>Для всех:</b>\n"
    for cmd, desc, cat, copy in settings.BOT_COMMANDS_LIST:
        if cat == "user": text += format_cmd(cmd, desc, copy)
    
    # Добавляем кнопку кружочков в меню, только если модуль включен
    if await get_module_status("TelegramVideo"):
        text += "🔹 /videomessage — Сделать кружочек\n"

    if is_admin_user:
        text += "\n🛡 <b>Админ:</b>\n"
        for cmd, desc, cat, copy in settings.BOT_COMMANDS_LIST:
            if cat.startswith("admin"): text += format_cmd(cmd, desc, copy).replace("🔹", "🔸")

    await message.answer(text, parse_mode="HTML")

    if is_new:
        await send_log("NEW_USER", f"New: {message.from_user.full_name}", user=message.from_user)

@user_router.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await cmd_start(message)

@user_router.message(Command("login"))
async def cmd_login(message: types.Message):
    can, _ = await check_access_and_update(message.from_user, message)
    if not can: return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("🔑 <b>Авторизация Last.fm</b>\nУкажите ник:\n<code>/login ваш_ник</code>", parse_mode="HTML")
        return
    lfm_username = parts[1]
    await set_lastfm_username(message.from_user.id, lfm_username)
    await message.answer(f"✅ Профиль <b>{lfm_username}</b> привязан!", parse_mode="HTML")

@user_router.message(F.document)
async def handle_document(message: types.Message):
    if message.document.file_name and message.document.file_name.lower() == "cookies.txt":
        can, _ = await check_access_and_update(message.from_user, message)
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
        await message.answer("🍪 <b>Куки сохранены!</b>", parse_mode="HTML")
        await send_log("INFO", f"User uploaded cookies", user=message.from_user)