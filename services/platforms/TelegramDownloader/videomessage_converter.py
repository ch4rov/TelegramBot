import os
import subprocess
import asyncio

async def convert_to_video_note(input_path: str, output_path: str):
    """
    Превращает видео в квадратный MP4 (640x640) для Video Note.
    """
    
    # 1. Ищем FFmpeg
    # Мы находимся в services/platforms/TelegramDownloader/
    # Нам нужно подняться на 4 уровня вверх, чтобы найти core/installs
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    local_ffmpeg = os.path.join(base_dir, "core", "installs", "ffmpeg.exe")
    
    # Выбираем команду запуска (локальный exe или системный)
    if os.path.exists(local_ffmpeg):
        ffmpeg_cmd = local_ffmpeg
    else:
        ffmpeg_cmd = "ffmpeg" # Надеемся на системный PATH

    # 2. Формируем команду
    # -vf: crop=min(iw,ih):min(iw,ih) -> Вырезает квадрат по центру
    # scale=640:640 -> Ресайз до стандарта Телеграм
    cmd = [
        ffmpeg_cmd, "-y", "-i", input_path,
        "-vf", "crop=min(iw\\,ih):min(iw\\,ih),scale=640:640,format=yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "26", 
        "-c:a", "aac", "-b:a", "64k",
        "-t", "60", # Лимит 1 минута
        "-movflags", "+faststart",
        output_path
    ]
    
    # 3. Запускаем (в отдельном потоке, чтобы не блокировать бота)
    def run_ffmpeg():
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            raise Exception(f"FFmpeg Error: {stderr.decode()}")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_ffmpeg)
    
    return output_path