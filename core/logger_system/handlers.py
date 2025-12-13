import aiofiles
import os
import aiohttp
import asyncio
from datetime import datetime
from aiogram import Bot
from . import config

# Глобальный буфер для Дискорда
_discord_buffer = []
_discord_lock = asyncio.Lock()

async def log_to_file(user_id, username, event_type, content):
    """Пишет в файл юзера и общий файл"""
    ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{ts} | [{event_type}] | {username} ({user_id}) | {content}\n"
    try:
        async with aiofiles.open(config.FULL_LOG_PATH, mode='a', encoding='utf-8') as f:
            await f.write(line)
    except: pass

    if user_id > 0:
        u_path = os.path.join(config.USER_LOGS_DIR, f"{user_id}.txt")
        try:
            async with aiofiles.open(u_path, mode='a', encoding='utf-8') as f:
                await f.write(line)
        except: pass

async def log_to_telegram(bot: Bot, text):
    if not config.ENABLE_TELEGRAM_LOG or not config.LOG_TELEGRAM_CHAT_ID: return
    try:
        if len(text) > 4000: text = text[:4000] + "..."
        await bot.send_message(chat_id=config.LOG_TELEGRAM_CHAT_ID, text=text)
    except: pass

async def log_to_discord_bot(text):
    """Добавляет сообщение в очередь на отправку ботом"""
    if not config.ENABLE_DISCORD_BOT_LOG or not config.DISCORD_BOT_TOKEN: return
    async with _discord_lock:
        _discord_buffer.append(text)

# --- WORKER (API BOTA) ---
async def discord_bot_worker():
    print("[LOGGER] Discord Bot Worker STARTED") 
    
    # URL API Дискорда для отправки сообщения в канал/ветку
    # В Discord API ветка считается просто каналом
    api_url = f"https://discord.com/api/v10/channels/{config.DISCORD_TARGET_CHANNEL_ID}/messages"
    
    headers = {
        "Authorization": f"Bot {config.DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }

    while True:
        await asyncio.sleep(2.5) # Пауза между пачками
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
                async with aiohttp.ClientSession() as session:
                    try:
                        async with session.post(api_url, headers=headers, json={"content": payload}) as resp:
                            if resp.status != 200:
                                txt = await resp.text()
                                print(f"[LOGGER] Discord API Error {resp.status}: {txt}")
                    except Exception as e:
                        print(f"[LOGGER] Discord Exception: {e}")

async def distribute_log(bot: Bot, user_id, username, event_type, content):
    await log_to_file(user_id, username, event_type, content)
    
    clean_content = str(content).replace("<", "&lt;").replace(">", "&gt;")
    tg_text = f"<b>[{event_type}]</b> {username} (<code>{user_id}</code>): {clean_content}"
    
    # Форматирование для Дискорда
    ds_content = str(content).replace("`", "'")
    ds_text = f"**[{event_type}]** {username} ({user_id}): `{ds_content}`"

    if config.ENABLE_TELEGRAM_LOG:
        asyncio.create_task(log_to_telegram(bot, tg_text))

    if config.ENABLE_DISCORD_BOT_LOG:
        asyncio.create_task(log_to_discord_bot(ds_text))