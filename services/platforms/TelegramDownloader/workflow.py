import os
import shutil
from uuid import uuid4
from aiogram import Bot
from aiogram.types import Video
from .videomessage_converter import convert_to_video_note

# --- РУБИЛЬНИК МОДУЛЯ ---
IS_ENABLED = True  # Поставь False, чтобы отключить кружочки
# ------------------------

def fix_local_path(file_path: str, bot_token: str) -> str:
    """
    Обрезает абсолютный путь Docker (/var/lib/...) до относительного (videos/file.mp4),
    чтобы скачивание по HTTP работало корректно.
    """
    path = file_path.replace("\\", "/")
    
    # 1. Если путь содержит токен
    if bot_token in path:
        return path.split(bot_token)[-1].lstrip("/")
    
    # 2. Резерв: ищем стандартные папки
    for folder in ["documents", "videos", "photos", "music", "voice", "animations"]:
        if f"/{folder}/" in path:
            return path[path.find(folder):]
            
    return path

async def process_video_note_creation(bot: Bot, video: Video) -> tuple[str, str]:
    """
    Полный цикл: Скачивание -> Конвертация -> Возврат пути.
    Возвращает: (путь_к_готовому_файлу, путь_к_папке_для_удаления)
    """
    
    # 1. ПРОВЕРКА СТАТУСА
    if not IS_ENABLED:
        raise Exception("Создание видеосообщений временно отключено на тех. обслуживание.")

    unique_id = str(uuid4())
    temp_dir = os.path.join("downloads", f"tg_{unique_id}")
    os.makedirs(temp_dir, exist_ok=True)

    input_path = os.path.join(temp_dir, "input.mp4")
    output_path = os.path.join(temp_dir, "output.mp4")
    
    try:
        # 2. Получаем инфо о файле
        file_info = await bot.get_file(video.file_id)
        
        # 3. Исправляем путь (для Docker)
        relative_path = fix_local_path(file_info.file_path, bot.token)
        
        # 4. Скачиваем
        await bot.download_file(relative_path, input_path)
        
        # 5. Конвертируем
        await convert_to_video_note(input_path, output_path)
        
        return output_path, temp_dir
        
    except Exception as e:
        # Если ошибка - чистим сразу
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise e