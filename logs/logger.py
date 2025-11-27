import aiohttp
import os
import time
import asyncio
import re
from collections import deque
from datetime import datetime
import settings # <--- ВАЖНО: Импортируем настройки

# Directory where this file lives
ROOT_DIR = os.path.dirname(__file__)
LOGS_DIR = os.path.join(ROOT_DIR, "files")
os.makedirs(LOGS_DIR, exist_ok=True)

FULL_LOG_PATH = os.path.join(LOGS_DIR, "full_log.txt")
OTHER_LOG_PATH = os.path.join(LOGS_DIR, "other_messages.txt")

# Discord styles
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

async def _write_full_log(text: str):
    """Always append to the local full log file (runs in thread)."""
    def _sync_write(t):
        try:
            with open(FULL_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(t + "\n")
        except Exception: pass
    await asyncio.to_thread(_sync_write, text)

async def _write_other_log(text: str):
    """Append to the separate other-messages log file."""
    def _sync_write(t):
        try:
            with open(OTHER_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(t + "\n")
        except Exception: pass
    await asyncio.to_thread(_sync_write, text)

def _format_local_entry(style_key: str, message: str, user=None, admin=None) -> str:
    ts = datetime.utcnow().isoformat()
    actor = ""
    if admin:
        actor = f"admin:{getattr(admin,'username',None)}({getattr(admin,'id',None)})"
    elif user:
        actor = f"user:{getattr(user,'username',None)}({getattr(user,'id',None)})"
    return f"{ts} | {style_key} | {actor} | {message}"

async def log_local(style_key: str, message: str, user=None, admin=None):
    """Write the full log locally and immediately."""
    try:
        entry = _format_local_entry(style_key, message, user=user, admin=admin)
        await _write_full_log(entry)
    except Exception: pass

# --- Discord sending + grouping ---
_user_states = {}
_user_states_lock = asyncio.Lock()

class _UserState:
    def __init__(self):
        self.timestamps = deque()
        self.buffer = {}
        self.flush_task = None

async def _post_webhook(content: str):
    # --- ЛОГИКА РАЗДЕЛЕНИЯ ВЕБХУКОВ ---
    if settings.IS_TEST_ENV:
        webhook_url = os.getenv("DISCORD_TEST_WEBHOOK_URL")
        # Если для теста вебхук не задан, берем основной (или можно return)
        if not webhook_url: 
            webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    else:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    if not webhook_url:
        return

    async with aiohttp.ClientSession() as session:
        try:
            await session.post(webhook_url, json={"content": content})
        except Exception as e:
            await log_local("FAIL", f"Discord post error: {e}")

async def _flush_user(user_id: int, username: str):
    async with _user_states_lock:
        state = _user_states.get(user_id)
        if not state or not state.buffer: return
        buf_dict = state.buffer.copy()
        state.buffer.clear()
        if state.flush_task: state.flush_task = None

    count = sum(buf_dict.values())
    items = list(buf_dict.items())[-6:]
    sample_lines = []
    for text, cnt in items:
        if cnt > 1: sample_lines.append(f"{text} (x{cnt})")
        else: sample_lines.append(text)

    sample = "\n".join(sample_lines)
    prefix = "**[TEST]** " if settings.IS_TEST_ENV else ""
    
    content = (
        f"{prefix}⚠️ [`SPAM`] • {username} (ID: {user_id}) прислал {count} сообщений за короткое время:\n{sample}"
    )
    await _post_webhook(content)

async def _schedule_flush(state: _UserState, user_id: int, username: str):
    if state.flush_task and not state.flush_task.done():
        state.flush_task.cancel()

    async def _wait_and_flush():
        try:
            await asyncio.sleep(1.0)
            await _flush_user(user_id, username)
        except asyncio.CancelledError: return

    state.flush_task = asyncio.create_task(_wait_and_flush())

# TikTok URL helper
_tiktok_re = re.compile(r'https?://(?:www\.|vm\.|vt\.|m\.)?tiktok\.com[^\s>]*', re.IGNORECASE)

def _wrap_tiktok_urls(text: str) -> str:
    def _repl(m):
        url = m.group(0)
        if url.startswith("<") and url.endswith(">"): return url
        return f"<{url}>"
    return _tiktok_re.sub(_repl, text)

async def send_log(style_key: str, message: str, user=None, admin=None):
    """Immediate send to Discord."""
    await log_local(style_key, message, user=user, admin=admin)

    ts = int(time.time())
    time_tag = f"<t:{ts}:T>"
    emoji = STYLES.get(style_key, "ℹ️")
    tag_text = style_key if style_key != "NEW_USER" else "NEW USER"
    
    # Добавляем префикс TEST
    prefix_str = "**[TEST]** " if settings.IS_TEST_ENV else ""

    actor_info = ""
    if admin:
        username = admin.username if admin.username else "NoUsername"
        actor_info = f" • {username} (ID: {admin.id})"
    elif user and style_key not in ["ADMIN", "SYSTEM"]:
        username = user.username if user.username else "NoUsername"
        actor_info = f" • {username} (ID: {user.id})"
    
    # Экранирование
    safe_message = message.replace("`", "'")
    formatted_msg = f"`{safe_message}`"

    if style_key == "SYSTEM":
        content = f"{prefix_str}{emoji} [`SYSTEM` {time_tag}] • {formatted_msg}"
    elif style_key == "NEW_USER":
        content = f"{prefix_str}{emoji} [`NEW` {time_tag}] • {formatted_msg}"
    elif style_key == "ADMIN":
        content = f"{prefix_str}{emoji} [`ADMIN` {time_tag}]{actor_info}: {formatted_msg}"
    else:
        content = f"{prefix_str}{emoji} [`{tag_text}` {time_tag}]{actor_info}: {formatted_msg}"

    await _post_webhook(content)


async def send_log_groupable(style_key: str, message: str, user=None, admin=None):
    """Groupable send."""
    await log_local(style_key, message, user=user, admin=admin)

    try: message_proc = _wrap_tiktok_urls(message)
    except: message_proc = message

    if user and style_key not in ["ADMIN", "SYSTEM"]:
        user_id = getattr(user, "id", None)
        username = getattr(user, "username", "NoUsername") or "NoUsername"
        if user_id is not None:
            now = time.time()
            async with _user_states_lock:
                state = _user_states.get(user_id)
                if not state:
                    state = _UserState()
                    _user_states[user_id] = state

                state.timestamps.append(now)
                while state.timestamps and state.timestamps[0] < now - 1.0:
                    state.timestamps.popleft()

                if len(state.timestamps) > 2:
                    key = f"{style_key}: {message_proc}"
                    state.buffer[key] = state.buffer.get(key, 0) + 1
                    await _schedule_flush(state, user_id, username)
                    return

    # Fallback: immediate send
    prefix_str = "**[TEST]** " if settings.IS_TEST_ENV else ""
    
    ts = int(time.time())
    time_tag = f"<t:{ts}:T>"
    emoji = STYLES.get(style_key, "ℹ️")
    tag_text = style_key if style_key != "NEW_USER" else "NEW USER"

    actor_info = ""
    if admin:
        username = admin.username if admin.username else "NoUsername"
        actor_info = f" • {username} (ID: {admin.id})"
    elif user and style_key not in ["ADMIN", "SYSTEM"]:
        username = user.username if user.username else "NoUsername"
        actor_info = f" • {username} (ID: {user.id})"

    safe_message = message_proc.replace("`", "'")
    formatted_msg = f"`{safe_message}`"

    if style_key == "SYSTEM":
        content = f"{prefix_str}{emoji} [`SYSTEM` {time_tag}] • {formatted_msg}"
    elif style_key == "NEW_USER":
        content = f"{prefix_str}{emoji} [`NEW` {time_tag}] • {formatted_msg}"
    elif style_key == "ADMIN":
        content = f"{prefix_str}{emoji} [`ADMIN` {time_tag}]{actor_info}: {formatted_msg}"
    else:
        content = f"{prefix_str}{emoji} [`{tag_text}` {time_tag}]{actor_info}: {formatted_msg}"

    await _post_webhook(content)


async def log_other_message(message_text: str, user=None):
    try:
        entry = _format_local_entry("OTHER_MSG", message_text, user=user)
        await asyncio.gather(
            _write_full_log(entry),
            _write_other_log(entry),
        )
    except Exception: pass