from .base import base_download
import os

async def download(url: str):
    # Настройки по умолчанию
    opts = {}

    # Подключаем куки (если есть)
    if os.path.exists("cookies.txt"):
        opts['cookiefile'] = "cookies.txt"

    # 1. Логика для YouTube Music (Аудио)
    if "music.youtube.com" in url:
        opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    
    # 2. Логика для обычного YouTube / Shorts (Видео)
    else:
        opts.update({
            # ВАЖНО: Просим видео ИМЕННО в mp4 (h264) и аудио в m4a (aac)
            # Если такого нет, качаем лучшее, что есть, а base.py потом сконвертирует
            'format': 'bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            
            # Принудительно упаковываем в контейнер MP4
            'merge_output_format': 'mp4' 
        })

    return await base_download(url, opts)