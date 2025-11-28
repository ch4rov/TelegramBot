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
    Возвращает ID из базы. Если нет - пробует сгенерировать на лету.
    """
    key = f"placeholder_{placeholder_type}"
    file_id = await get_system_value(key)
    
    if file_id:
        return file_id
    
    # Если в базе нет - генерируем срочно
    print(f"⚠️ [SYSTEM] Плейсхолдер {placeholder_type} отсутствует. Генерирую...")
    return await generate_new_placeholder(placeholder_type)

async def ensure_placeholders():
    """
    Вызывается при старте main.py.
    Проверяет, есть ли заглушки. Если нет - создает.
    Если есть - ничего не делает (не спамит).
    """
    print("🔄 [SYSTEM] Проверка плейсхолдеров...")
    
    # 1. Видео
    vid = await get_system_value("placeholder_video")
    if not vid:
        print("   -> Видео нет. Создаем...")
        await generate_new_placeholder("video")
    else:
        print("   -> Видео OK.")

    # 2. Аудио
    aud = await get_system_value("placeholder_audio")
    if not aud:
        print("   -> Аудио нет. Создаем...")
        await generate_new_placeholder("audio")
    else:
        print("   -> Аудио OK.")

async def generate_new_placeholder(placeholder_type: str):
    if not settings.TECH_CHAT_ID:
        print("❌ ОШИБКА: TECH_CHAT_ID не задан! Не могу отправить заглушку.")
        return None

    filename = f"temp_placeholder.{'mp4' if placeholder_type == 'video' else 'mp3'}"
    file_id = None
    
    try:
        # --- ГЕНЕРАЦИЯ ---
        
        if placeholder_type == 'video':
            # 1. Ищем FFmpeg (точно по адресу)
            # os.getcwd() = папка с main.py
            local_ffmpeg = os.path.join(os.getcwd(), "core", "installs", "ffmpeg.exe")
            
            if os.path.exists(local_ffmpeg):
                ffmpeg_cmd = local_ffmpeg
            elif shutil.which("ffmpeg"):
                ffmpeg_cmd = "ffmpeg"
            else:
                print(f"❌ [ERROR] FFmpeg не найден для генерации видео! Путь: {local_ffmpeg}")
                return None

            # Генерируем 1 сек черного видео
            cmd = [
                ffmpeg_cmd, "-y", 
                "-f", "lavfi", "-i", "color=c=black:s=640x360:d=1",
                "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
                "-f", "mp4", filename
            ]
            
            # Запускаем и ждем (check=True выбросит ошибку если что-то не так)
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
            
            msg = await bot.send_video(
                settings.TECH_CHAT_ID, 
                FSInputFile(filename), 
                caption="System Video Placeholder"
            )
            file_id = msg.video.file_id

        elif placeholder_type == 'audio':
            # Генерируем 1 сек тишины (Hex)
            hex_data = "FFF304C40000000348000000004C414D45332E39382E320000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            with open(filename, "wb") as f: 
                f.write(binascii.unhexlify(hex_data))
            
            msg = await bot.send_audio(
                settings.TECH_CHAT_ID, 
                FSInputFile(filename), 
                title="Audio Placeholder", 
                performer="System"
            )
            file_id = msg.audio.file_id

        # --- СОХРАНЕНИЕ ---
        if file_id:
            key = f"placeholder_{placeholder_type}"
            await set_system_value(key, file_id)
            print(f"✅ [SYSTEM] Заглушка {placeholder_type} создана и сохранена.")
        
        return file_id

    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка FFmpeg: {e}")
        return None
    except Exception as e:
        print(f"❌ Ошибка генерации {placeholder_type}: {e}")
        return None
        
    finally:
        if os.path.exists(filename):
            try: os.remove(filename)
            except: pass