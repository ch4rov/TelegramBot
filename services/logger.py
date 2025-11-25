import aiohttp
import os
import time
from dotenv import load_dotenv

load_dotenv()

# Настройки отображения
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

async def send_log(style_key: str, message: str, user=None, admin=None):
    """
    admin: Объект message.from_user (если действие совершил админ)
    user: Объект пользователя (над которым совершили действие)
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url: return

    # UNIX время для Discord тегов
    # <t:X:f> - полная дата и время (25 November 2025 01:43)
    # <t:X:R> - относительное время (2 minutes ago)
    # <t:X:T> - только время (01:43:33)
    ts = int(time.time())
    time_tag = f"<t:{ts}:T>" 
    
    emoji = STYLES.get(style_key, "ℹ️")
    tag_text = style_key if style_key != "NEW_USER" else "NEW USER" # Красивое имя тега

    # --- Сборка строки "Кто совершил действие" ---
    # Пример: • AdminName (ID: 123)
    actor_info = ""
    if admin:
        username = admin.username if admin.username else "NoUsername"
        actor_info = f" • {username} (ID: {admin.id})"
    elif user and style_key not in ["ADMIN", "SYSTEM"]:
        # Если это действие обычного юзера, он и есть "актор"
        username = user.username if user.username else "NoUsername"
        actor_info = f" • {username} (ID: {user.id})"

    # --- Сборка основного контента ---
    # Формируем структуру: Эмодзи [ТЕГ ВРЕМЯ] • Актор: Сообщение
    
    # 1. СИСТЕМА
    if style_key == "SYSTEM":
        content = f"{emoji} [`SYSTEM` {time_tag}] • {message}"

    # 2. НОВЫЙ ПОЛЬЗОВАТЕЛЬ
    elif style_key == "NEW_USER":
        content = f"{emoji} [`NEW` {time_tag}] • {message}"

    # 3. АДМИН ДЕЙСТВИЯ (Бан/Разбан/Рестарт)
    elif style_key == "ADMIN":
        # Формат: 👑 [ADMIN Время] • AdminInfo: Сообщение
        content = f"{emoji} [`ADMIN` {time_tag}]{actor_info}: {message}"
    
    # 4. ОБЫЧНЫЕ ЛОГИ
    else:
        # Формат: ⏳ [USER Время] • UserInfo: Сообщение
        content = f"{emoji} [`{tag_text}` {time_tag}]{actor_info}: {message}"

    async with aiohttp.ClientSession() as session:
        try:
            await session.post(webhook_url, json={"content": content})
        except Exception as e:
            print(f"Log Error: {e}")