import html
import json
import time
import os
from aiogram import F, types
from aiogram.filters import CommandStart, Command
from .router import user_router, check_access_and_update
from services.database_service import set_lastfm_username, save_user_cookie
from logs.logger import send_log
import messages as msg 
import settings

ADMIN_ID = os.getenv("ADMIN_ID")

# Функция конвертации (нужна только здесь)
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

@user_router.message(CommandStart())
async def cmd_start(message: types.Message):
    can, is_new = await check_access_and_update(message.from_user, message)
    if not can: return
    
    bot_info = await message.bot.get_me()
    welcome_text = msg.MSG_START.format(
        name=html.escape(message.from_user.first_name),
        bot_name=bot_info.username
    )
    await message.answer(welcome_text, parse_mode="HTML")
    
    is_admin_user = str(message.from_user.id) == str(ADMIN_ID)
    text = "🤖 <b>Меню команд</b>\n\n"
    
    def format_cmd(cmd, desc, copy):
        return f"🔹 <code>/{cmd}</code> — {desc}\n" if copy else f"🔹 /{cmd} — {desc}\n"

    text += "👤 <b>Для всех:</b>\n"
    for cmd, desc, cat, copy in settings.BOT_COMMANDS_LIST:
        if cat == "user": text += format_cmd(cmd, desc, copy)

    if is_admin_user:
        text += "\n🛡 <b>Модерация:</b>\n"
        for cmd, desc, cat, copy in settings.BOT_COMMANDS_LIST:
            if cat == "admin_mod": text += format_cmd(cmd, desc, copy).replace("🔹", "🔸")
        text += "\n⚙️ <b>Технические:</b>\n"
        for cmd, desc, cat, copy in settings.BOT_COMMANDS_LIST:
            if cat == "admin_tech": text += format_cmd(cmd, desc, copy).replace("🔹", "🔧")

    await message.answer(text, parse_mode="HTML")
    if is_new: await send_log("NEW_USER", f"New: {message.from_user.full_name}", user=message.from_user)

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
    await set_lastfm_username(message.from_user.id, parts[1])
    await message.answer(f"✅ Профиль <b>{parts[1]}</b> привязан!", parse_mode="HTML")

@user_router.message(F.document)
async def handle_document(message: types.Message):
    if message.document.file_name and message.document.file_name.lower() == "cookies.txt":
        can, _ = await check_access_and_update(message.from_user, message)
        if not can: return
        file = await message.bot.get_file(message.document.file_id)
        
        # Исправление пути для Docker (импортируем локально, чтобы не циклило)
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