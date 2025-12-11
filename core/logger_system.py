import os
import aiofiles
import asyncio
import time
import re
import json
from datetime import datetime
import aiohttp
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineQuery, Update
import settings
from services.database_service import add_message_log

# Пути
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
USER_LOGS_DIR = os.path.join(LOGS_DIR, "user_logs")
FULL_LOG_PATH = os.path.join(LOGS_DIR, "files", "full_log.txt")

os.makedirs(USER_LOGS_DIR, exist_ok=True)
os.makedirs(os.path.join(LOGS_DIR, "files"), exist_ok=True)

# Discord Buffer
_discord_buffer = []
_discord_lock = asyncio.Lock()

# Icons
ICONS = {
    "MSG_CMD": "🤖", "MSG_LINK": "🔗", "MSG_NOT_LINK": "💬", "MSG_TEXT": "📄",
    "MSG_SENT": "📤", "MSG_FAIL": "❌", "MSG_SYS": "⚙️",
    "ADMIN": "👑", "BTN_CLICK": "🔘", "INLINE_QUERY": "🔍"
}

# --- MIDDLEWARE ---
class DBLoggingMiddleware(BaseMiddleware):
    """Перехватывает ВСЕ события и отправляет в логгер"""
    async def __call__(self, handler, event: Update, data):
        user = None
        event_type = "MSG_UNKNOWN"
        content = ""
        msg_obj = None

        if event.message:
            user = event.message.from_user
            msg_obj = event.message
            text = msg_obj.text or msg_obj.caption or ""
            
            if user.id == 777000: return await handler(event, data) # Игнор сервисного акка

            if text.startswith("/"):
                event_type = "MSG_CMD"
                content = text
            elif "http" in text:
                is_valid = any(re.search(p, text) for p in settings.URL_PATTERNS)
                event_type = "MSG_LINK" if is_valid else "MSG_NOT_LINK"
                content = text
            elif msg_obj.video or msg_obj.audio or msg_obj.photo:
                event_type = "MSG_FILE_IN"
                content = f"File: {msg_obj.content_type}"
            else:
                event_type = "MSG_TEXT"
                content = text
                
        elif event.callback_query:
            user = event.callback_query.from_user
            event_type = "BTN_CLICK"
            content = event.callback_query.data
            
        elif event.inline_query:
            user = event.inline_query.from_user
            event_type = "INLINE_QUERY"
            content = event.inline_query.query

        elif event.chosen_inline_result:
            user = event.chosen_inline_result.from_user
            event_type = "INLINE_SELECTED"
            content = event.chosen_inline_result.result_id

        # ЗАПИСЫВАЕМ
        if user:
            # Fire and forget
            asyncio.create_task(logger(user, event_type, content, msg_obj))

        return await handler(event, data)


# --- MAIN LOGGER ---
async def logger(user, event_type: str, content: str, message: Message = None):
    """Центральная функция логирования"""
    if not user: return
    
    # Нормализация данных юзера
    if isinstance(user, dict): # Если передали dict (например System)
        user_id = user.get('id', 0)
        username = user.get('username', 'System')
        full_name = "System"
    else:
        user_id = user.id
        username = user.username or user.first_name or "NoName"
        full_name = f"{user.first_name} {user.last_name or ''}".strip()

    ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    
    # 1. КОНСОЛЬ
    print(f"{ts} | [{event_type}] {username} ({user_id}): {content}")

    # 2. ФАЙЛ ЮЗЕРА
    log_line = f"{ts} [{event_type}] {content}"
    await _write_user_file(user_id, username, log_line)
    
    # 3. ОБЩИЙ ФАЙЛ
    await _write_full_log(f"{ts} | {event_type} | {username}({user_id}) | {content}")

    # 4. БАЗА ДАННЫХ (Самое важное)
    msg_id = message.message_id if message else None
    
    # Пытаемся получить raw data
    raw_data = None
    if message:
        try: raw_data = message.model_dump()
        except: pass
    
    await add_message_log(user_id, username, event_type, content, msg_id, raw_data)

    # 5. DISCORD
    icon = ICONS.get(event_type, "ℹ️")
    prefix = "**[TEST]** " if settings.IS_TEST_ENV else ""
    clean_content = content.replace("URL: ", "").replace("<", "").replace(">", "")
    user_link = f"[{username}](tg://user?id={user_id})" if user_id > 0 else username
    
    discord_line = f"{prefix}{icon} **{event_type}** | {user_link}: `{clean_content}`"
    
    async with _discord_lock:
        _discord_buffer.append(discord_line)


# --- FILE HELPERS ---
async def _write_user_file(uid, uname, line):
    path = os.path.join(USER_LOGS_DIR, f"{uid}.txt")
    is_new = not os.path.exists(path)
    try:
        async with aiofiles.open(path, mode='a', encoding='utf-8') as f:
            if is_new: await f.write(f"=== CHAT START: {uname} ({uid}) ===\n")
            await f.write(line + "\n")
    except: pass

async def _write_full_log(line):
    try:
        async with aiofiles.open(FULL_LOG_PATH, mode='a', encoding='utf-8') as f:
            await f.write(line + "\n")
    except: pass

# --- DISCORD LOOP ---
async def _discord_loop():
    while True:
        await asyncio.sleep(5)
        async with _discord_lock:
            if not _discord_buffer: continue
            chunk = []
            curr_len = 0
            while _discord_buffer:
                msg = _discord_buffer[0]
                if curr_len + len(msg) > 1900: break
                _discord_buffer.pop(0)
                chunk.append(msg)
                curr_len += len(msg) + 1
            if chunk:
                payload = "\n".join(chunk)
                asyncio.create_task(_send_webhook(payload))

async def _send_webhook(content):
    url = settings.DISCORD_WEBHOOK_URL
    if not url: return
    async with aiohttp.ClientSession() as session:
        try: await session.post(url, json={"content": content})
        except: pass

loop = asyncio.get_event_loop()
loop.create_task(_discord_loop())

# --- ALIASES (Для совместимости с content.py) ---
async def send_log(style_key, message, user=None, admin=None):
    target = user or admin
    # Преобразуем старые ключи в новые
    new_key = style_key
    if style_key == "SUCCESS": new_key = "MSG_SENT"
    elif style_key == "FAIL": new_key = "MSG_FAIL"
    elif style_key == "USER_REQ": new_key = "MSG_LINK"
    
    await logger(target, new_key, message)

async def send_log_groupable(style_key, message, user=None, admin=None):
    await send_log(style_key, message, user, admin)

async def log_other_message(message, user=None):
    await logger(user, "MSG_TEXT", message)

async def send_log(text, user_id=None, chat_id=None, username="Unknown", **kwargs):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logs_dir = os.path.join(base_dir, "logs")
    
    users_dir = os.path.join(logs_dir, "user_logs")
    groups_dir = os.path.join(logs_dir, "group_logs")
    
    for d in [logs_dir, users_dir, groups_dir]:
        if not os.path.exists(d):
            os.makedirs(d)

    time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- ЛОГИКА ЗАПИСИ ---

    # 1. Если это ГРУППА (есть chat_id)
    if chat_id:
        # А. Пишем в файл группы
        group_file = os.path.join(groups_dir, f"{chat_id}.txt")
        group_entry = f"[{time_now}] User: {username} ({user_id}) | {text}\n"
        try:
            with open(group_file, "a", encoding="utf-8") as f: f.write(group_entry)
        except: pass

        # Б. ДУБЛИРУЕМ в файл пользователя (если передан user_id)
        if user_id:
            user_file = os.path.join(users_dir, f"{user_id}.txt")
            # Добавляем пометку, что это было в группе
            user_entry = f"[{time_now}] [FROM GROUP {chat_id}] {text}\n"
            try:
                with open(user_file, "a", encoding="utf-8") as f: f.write(user_entry)
            except: pass

    # 2. Если это ЛИЧКА (есть user_id, но нет chat_id)
    elif user_id:
        user_file = os.path.join(users_dir, f"{user_id}.txt")
        user_entry = f"[{time_now}] {text}\n"
        try:
            with open(user_file, "a", encoding="utf-8") as f: f.write(user_entry)
        except: pass

    # 3. СИСТЕМНЫЙ ЛОГ (нет ни того, ни другого)
    else:
        sys_file = os.path.join(logs_dir, "system.txt")
        sys_entry = f"[{time_now}] {text}\n"
        try:
            with open(sys_file, "a", encoding="utf-8") as f: f.write(sys_entry)
        except: pass