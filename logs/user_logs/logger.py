import os
import aiofiles
from datetime import datetime

# Путь к папке с логами пользователей
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # logs/user_logs/

async def log_user_event(user, action: str, text: str = ""):
    """
    Записывает событие в личный лог-файл пользователя.
    user: объект пользователя Telegram (содержит id, username, first_name)
    action: Тип действия (TEXT, COMMAND, BOT_RESPONSE, etc.)
    text: Содержимое
    """
    if not user: return

    user_id = user.id
    username = f"@{user.username}" if user.username else user.first_name
    
    filename = f"{user_id}.txt"
    filepath = os.path.join(BASE_DIR, filename)
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Форматируем строку лога
    # [Дата] [ДЕЙСТВИЕ] Текст
    log_line = f"[{timestamp}] [{action}] {text}\n"

    # Если файла нет, создаем шапку с инфой о юзере
    is_new = not os.path.exists(filepath)
    
    try:
        async with aiofiles.open(filepath, mode='a', encoding='utf-8') as f:
            if is_new:
                header = (
                    f"========================================\n"
                    f"USER ID: {user_id}\n"
                    f"NAME: {user.first_name} {user.last_name or ''}\n"
                    f"USERNAME: {username}\n"
                    f"CREATED: {timestamp}\n"
                    f"========================================\n"
                )
                await f.write(header)
            
            await f.write(log_line)
    except Exception as e:
        print(f"❌ Ошибка записи лога пользователя {user_id}: {e}")