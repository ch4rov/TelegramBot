import os
import asyncio
import binascii
import subprocess
from aiogram.types import FSInputFile
from loader import bot
import settings
from services.database_service import get_system_value, set_system_value

async def get_placeholder(placeholder_type: str):
    """
    Возвращает валидный File ID.
    Если его нет в базе - генерирует, отправляет, сохраняет и удаляет файл.
    """
    key = f"placeholder_{placeholder_type}"
    
    # 1. Пробуем достать из базы
    file_id = await get_system_value(key)
    if file_id:
        return file_id
    
    print(f"⚠️ [SYSTEM] Плейсхолдер {placeholder_type} не найден. Генерирую новый...")
    return await generate_new_placeholder(placeholder_type)

async def generate_new_placeholder(placeholder_type: str):
    if not settings.TECH_CHAT_ID:
        print("❌ ОШИБКА: Не задан TECH_CHAT_ID в .env! Инлайн не будет работать.")
        return None

    # Имя временного файла
    filename = f"temp_placeholder.{'mp4' if placeholder_type == 'video' else 'mp3'}"
    file_id = None
    
    try:
        # --- ГЕНЕРАЦИЯ ФАЙЛА ---
        
        if placeholder_type == 'video':
            # Генерируем 1 секунду черного видео через FFmpeg
            # Это гарантированно валидный MP4, который примет Телеграм
            cmd = [
                "ffmpeg", "-y",                 # Перезаписать если есть
                "-f", "lavfi",                  # Виртуальный источник
                "-i", "color=c=black:s=640x360:d=1", # Черный цвет, 640x360, 1 сек
                "-c:v", "libx264",              # Кодек H.264 (самый совместимый)
                "-t", "1",                      # Длительность
                "-pix_fmt", "yuv420p",          # Формат пикселей для совместимости
                "-f", "mp4",                    # Контейнер
                filename
            ]
            
            # Запускаем тихо (без вывода в консоль)
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            except FileNotFoundError:
                print("❌ Ошибка: FFmpeg не установлен в системе! Не могу создать видео.")
                return None
            except subprocess.CalledProcessError:
                print("❌ Ошибка FFmpeg при создании видео.")
                return None

            # Отправляем в тех чат
            msg = await bot.send_video(
                settings.TECH_CHAT_ID, 
                FSInputFile(filename), 
                caption="System Video Placeholder"
            )
            file_id = msg.video.file_id

        elif placeholder_type == 'audio':
            # Генерируем 1 сек тишины (Hex-код MP3) - это быстрее, чем звать ffmpeg
            hex_data = "FFF304C40000000348000000004C414D45332E39382E3200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            with open(filename, "wb") as f: 
                f.write(binascii.unhexlify(hex_data))
            
            msg = await bot.send_audio(
                settings.TECH_CHAT_ID, 
                FSInputFile(filename), 
                title="Audio Placeholder", 
                performer="System"
            )
            file_id = msg.audio.file_id

        # --- СОХРАНЕНИЕ В БАЗУ ---
        if file_id:
            key = f"placeholder_{placeholder_type}"
            await set_system_value(key, file_id)
            print(f"✅ [SYSTEM] Новый {placeholder_type} ID сгенерирован и сохранен.")
        
        return file_id

    except Exception as e:
        print(f"❌ Ошибка генерации плейсхолдера: {e}")
        return None
        
    finally:
        # --- УДАЛЕНИЕ ЛОКАЛЬНОГО ФАЙЛА ---
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except: pass