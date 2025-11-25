import yt_dlp
import os
import asyncio

# Разрешенные домены
ALLOWED_DOMAINS = ["tiktok.com", "instagram.com", "twitch.tv", "youtube.com", "soundcloud.com"]

def is_valid_url(url: str) -> bool:
    return any(domain in url for domain in ALLOWED_DOMAINS)

async def download_video(url: str):
    if not is_valid_url(url):
        return None, "Ссылка не поддерживается или домен запрещен ⛔"

    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    # Настройки загрузчика
    ydl_opts = {
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'format': 'bestvideo+bestaudio/best', # Пытаемся скачать лучшее качество
        'noplaylist': True,
        'max_filesize': 50 * 1024 * 1024, # Лимит 50 МБ (ограничение Телеграм ботов)
    }

    try:
        # Запускаем синхронную библиотеку в асинхронном режиме
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            filename = ydl.prepare_filename(info)
            return filename, None
    except Exception as e:
        return None, str(e)