import aiohttp
import os
from datetime import datetime

# Твои теги
TAGS = {
    "ADMIN": "🛡️ [ADMIN]",
    "USER": "👤 [USER]",
    "INFO": "ℹ️ [INFO]",
    "ERROR": "❌ [ERROR]"
}

async def send_log(tag_key: str, message: str):
    """Отправляет лог в Discord через Webhook"""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    
    if not webhook_url:
        print(f"[{tag_key}] {message} (Вебхук не настроен)")
        return

    tag = TAGS.get(tag_key, "ℹ️ [INFO]")
    time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Формируем сообщение для Дискорда
    content = f"`{time_now}` **{tag}** {message}"
    
    async with aiohttp.ClientSession() as session:
        try:
            await session.post(webhook_url, json={"content": content})
        except Exception as e:
            print(f"Ошибка отправки лога в Discord: {e}")