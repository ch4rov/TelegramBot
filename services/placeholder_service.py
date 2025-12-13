import os
import shutil
import asyncio
import binascii
import subprocess
import settings
from aiogram.types import FSInputFile
from loader import bot
from services.database_service import get_system_value, set_system_value

async def get_placeholder(placeholder_type: str):
    key = f"placeholder_{placeholder_type}"
    file_id = await get_system_value(key)
    
    if file_id:
        return file_id
    
    print(f"⚠️ [SYSTEM] Плейсхолдер {placeholder_type} отсутствует. Генерирую...")
    return await generate_new_placeholder(placeholder_type)

async def ensure_placeholders():
    print("🔄 [SYSTEM] Проверка плейсхолдеров...")
    
    vid = await get_system_value("placeholder_video")
    if not vid:
        print("   -> Видео нет. Создаем...")
        await generate_new_placeholder("video")
    else:
        print("   -> Видео OK.")

    aud = await get_system_value("placeholder_audio")
    if not aud:
        print("   -> Аудио нет. Создаем...")
        await generate_new_placeholder("audio")
    else:
        print("   -> Аудио OK.")

async def generate_new_placeholder(placeholder_type: str):
    tech_chat_id = settings.TECH_CHAT_ID
    
    if not tech_chat_id:
        print("❌ [ERROR] TECH_CHAT_ID не задан в .env! Не могу создать заглушку.")
        return None

    filename = f"temp_placeholder.{'mp4' if placeholder_type == 'video' else 'mp3'}"
    file_id = None
    
    try:
        if placeholder_type == 'video':
            local_ffmpeg = os.path.join(os.getcwd(), "core", "installs", "ffmpeg.exe")
            
            ffmpeg_cmd = "ffmpeg"
            if os.path.exists(local_ffmpeg):
                ffmpeg_cmd = local_ffmpeg
            elif shutil.which("ffmpeg"):
                ffmpeg_cmd = "ffmpeg"
            else:
                print(f"❌ [ERROR] FFmpeg не найден! Путь: {local_ffmpeg}")
                return None

            cmd = [
                ffmpeg_cmd, "-y", 
                "-f", "lavfi", "-i", "color=c=black:s=640x360:d=1",
                "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
                "-f", "mp4", filename
            ]
            
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
            
            msg = await bot.send_video(
                tech_chat_id, 
                FSInputFile(filename), 
                caption="System Video Placeholder"
            )
            file_id = msg.video.file_id

        elif placeholder_type == 'audio':
            hex_data = "FFF304C40000000348000000004C414D45332E39382E320000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            with open(filename, "wb") as f: 
                f.write(binascii.unhexlify(hex_data))
            
            msg = await bot.send_audio(
                tech_chat_id, 
                FSInputFile(filename), 
                title="Audio Placeholder", 
                performer="System"
            )
            file_id = msg.audio.file_id

        if file_id:
            key = f"placeholder_{placeholder_type}"
            await set_system_value(key, file_id)
            print(f"✅ [SYSTEM] Заглушка {placeholder_type} создана: {file_id}")
        
        return file_id

    except Exception as e:
        print(f"❌ Ошибка генерации {placeholder_type}: {e}")
        return None
        
    finally:
        if os.path.exists(filename):
            try: os.remove(filename)
            except: pass