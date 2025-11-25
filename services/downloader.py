import yt_dlp
import os
import asyncio

# Разрешенные домены
ALLOWED_DOMAINS = ["tiktok.com", "instagram.com", "twitch.tv", "youtube.com", "youtu.be", "soundcloud.com"]

def is_valid_url(url: str) -> bool:
    return any(domain in url for domain in ALLOWED_DOMAINS)

async def download_video(url: str):
    # 1. Проверка домена
    if not is_valid_url(url):
        return None, "Ссылка не поддерживается или домен запрещен ⛔"

    # 2. Проверка на TikTok Photo (Слайдшоу)
    if "tiktok.com" in url and "/photo/" in url:
        return None, "Слайдшоу (фото) TikTok пока не поддерживаются 📷. Пришлите видео."

    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    ydl_opts = {
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'format': 'bestvideo+bestaudio/best',
        'noplaylist': True,
        'max_filesize': 50 * 1024 * 1024,
        # Добавляем user-agent, чтобы тикток меньше блокировал
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    }

    try:
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # extract_info может выкинуть ошибку, если ссылка "битая"
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            
            # Дополнительная защита: если скачалось не видео, а что-то странное
            if 'entries' in info:
                return None, "Это плейлист или альбом, я умею качать только одиночные видео."
                
            filename = ydl.prepare_filename(info)
            return filename, None
            
    except yt_dlp.utils.DownloadError as e:
        # Очищаем сообщение об ошибке от лишнего мусора
        error_str = str(e)
        if "Unsupported URL" in error_str:
            return None, "Не удалось обработать ссылку (возможно, приватное видео или формат не поддерживается)."
        return None, "Ошибка загрузки (сервис недоступен или ссылка неверна)."
        
    except Exception as e:
        return None, str(e)