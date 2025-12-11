import aiohttp
import os
import time
import asyncio
import re
from datetime import datetime
import settings

# Локальные файлы логов
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(ROOT_DIR, "logs", "files")
os.makedirs(LOGS_DIR, exist_ok=True)

FULL_LOG_PATH = os.path.join(LOGS_DIR, "full_log.txt")
OTHER_LOG_PATH = os.path.join(LOGS_DIR, "other_messages.txt")

# Стили для Discord
STYLES = {
    "NEW_USER": "❤️",
    "ADMIN":    "👑",
    "USER_REQ": "⏳",
    "SUCCESS":  "✔️",
    "FAIL":     "❌",
    "SECURITY": "⚠️",
    "SYSTEM":   "💻",
    "INFO":     "ℹ️"
}

# --- БУФЕР СООБЩЕНИЙ ---
_log_buffer = []
_buffer_lock = asyncio.Lock()
_flush_task = None

async def _write_full_log(text: str):
    def _sync_write(t):
        try:
            with open(FULL_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(t + "\n")
        except Exception: pass
    await asyncio.to_thread(_sync_write, text)

async def _write_other_log(text: str):
    def _sync_write(t):
        try:
            with open(OTHER_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(t + "\n")
        except Exception: pass
    await asyncio.to_thread(_sync_write, text)

def _format_local_entry(style_key: str, message: str, user=None, admin=None) -> str:
    ts = datetime.utcnow().isoformat()
    actor = ""
    if admin: actor = f"admin:{getattr(admin,'username',None)}({getattr(admin,'id',None)})"
    elif user: actor = f"user:{getattr(user,'username',None)}({getattr(user,'id',None)})"
    return f"{ts} | {style_key} | {actor} | {message}"

async def log_local(style_key: str, message: str, user=None, admin=None):
    try:
        entry = _format_local_entry(style_key, message, user=user, admin=admin)
        await _write_full_log(entry)
    except Exception: pass

async def _post_webhook(content: str):
    if settings.IS_TEST_ENV:
        webhook_url = os.getenv("DISCORD_TEST_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK_URL")
    else:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    if not webhook_url: return

    async with aiohttp.ClientSession() as session:
        try:
            await session.post(webhook_url, json={"content": content})
        except Exception as e:
            await log_local("FAIL", f"Discord post error: {e}")

# --- ФОНОВАЯ ОТПРАВКА (5 секунд) ---
async def _flush_loop():
    while True:
        await asyncio.sleep(5)
        async with _buffer_lock:
            if not _log_buffer:
                continue
            
            # Собираем пачку сообщений
            chunk = []
            current_len = 0
            
            # Discord лимит ~2000, берем запас
            while _log_buffer:
                msg = _log_buffer[0]
                if current_len + len(msg) > 1900:
                    break # Пачка полная, остальное в следующий раз
                
                _log_buffer.pop(0)
                chunk.append(msg)
                current_len += len(msg) + 1
            
            if chunk:
                final_content = "\n".join(chunk)
                asyncio.create_task(_post_webhook(final_content))

def _ensure_loop_started():
    global _flush_task
    try:
        loop = asyncio.get_running_loop()
        if not _flush_task or _flush_task.done():
            _flush_task = loop.create_task(_flush_loop())
    except: pass

def _format_link_mono(text: str) -> str:
    """Оборачивает ссылки в ` ` для моноширинности"""
    # Ищем http/https ссылки и оборачиваем их в грависы, если они еще не обернуты
    return re.sub(r'(?<!`)(https?://\S+)(?!`)', r'`\1`', text)

async def _add_to_buffer(content: str):
    _ensure_loop_started()
    
    # Сразу форматируем ссылки в моноширинный
    content = _format_link_mono(content)
    
    async with _buffer_lock:
        # Если само сообщение гигантское, шлем сразу (обходя буфер)
        if len(content) > 1900:
            asyncio.create_task(_post_webhook(content))
        else:
            _log_buffer.append(content)

# --- ПУБЛИЧНЫЕ ФУНКЦИИ ---

async def send_log(style_key: str, message: str, user=None, admin=None):
    """Добавляет лог в буфер для отправки."""
    await log_local(style_key, message, user=user, admin=admin)

    ts = int(time.time())
    time_tag = f"<t:{ts}:T>"
    emoji = STYLES.get(style_key, "ℹ️")
    tag_text = style_key if style_key != "NEW_USER" else "NEW"
    
    prefix_str = "**[TEST]** " if settings.IS_TEST_ENV else ""

    actor_info = ""
    if admin:
        u_name = admin.username if admin.username else "NoName"
        actor_info = f" • {u_name} (ID: {admin.id})"
    elif user and style_key not in ["ADMIN", "SYSTEM"]:
        u_name = user.username if user.username else "NoName"
        actor_info = f" • {u_name} (ID: {user.id})"
    
    # Очистка сообщения от лишних "URL: " и скобок, если они пришли из кода
    clean_message = message.replace("URL: ", "").replace("<", "").replace(">", "")
    
    # Формируем строку для Дискорда
    content_line = f"{prefix_str}{emoji} [`{tag_text}` {time_tag}]{actor_info}: {clean_message}"
    
    await _add_to_buffer(content_line)


# send_log_groupable теперь просто алиас к send_log, так как у нас теперь
# глобальная буферизация на уровне 5 секунд для всех сообщений.
send_log_groupable = send_log 

async def log_other_message(message_text: str, user=None):
    try:
        entry = _format_local_entry("OTHER_MSG", message_text, user=user)
        await asyncio.gather(
            _write_full_log(entry),
            _write_other_log(entry),
        )
    except Exception: pass