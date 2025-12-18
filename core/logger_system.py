import logging

# Простая функция логгирования в консоль
async def send_log(message: str, user_id: int = None):
    """
    Выводит сообщение в консоль вместо отправки админу.
    Нужна, чтобы код handlers/user/commands.py не падал.
    """
    if user_id:
        logging.info(f"📋 [SYSTEM LOG] User {user_id}: {message}")
    else:
        logging.info(f"📋 [SYSTEM LOG]: {message}")