# -*- coding: utf-8 -*-
import logging
import sys
import os
from logging.handlers import RotatingFileHandler

LOG_FILE = "bot_actions.log"

def setup_logger():
    """Настраивает логирование в консоль и файл"""
    # НЕ удаляем старый файл лога - сохраняем историю

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    
    # Очищаем предыдущие обработчики
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    
    # Формат логирования
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Консоль вывод (UTF-8 для правильного отображения)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # Файловый вывод
    try:
        file_handler = RotatingFileHandler(
            LOG_FILE, 
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except Exception as e:
        logging.warning(f"Could not setup file logging: {e}")

    # Снижаем уровень вывода для библиотек
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)

def log_event(user_id: int, action: str, details: str = ""):
    """Логирует событие пользователя"""
    logger = logging.getLogger("EVENT")
    logger.info(f"USER_ID: {user_id} | ACTION: {action} | DETAILS: {details}")