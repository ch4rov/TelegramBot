from .base import base_download
import os

async def download(url: str, custom_opts: dict = None):
    def apply_cookies(opts):
        if os.path.exists("cookies.txt"):
            opts['cookiefile'] = "cookies.txt"
        return opts

    # Оптимальные настройки для TikTok
    opts = {
        'format': 'best',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.tiktok.com/',
        },
        'socket_timeout': 20,
        'extractor_timeout': 30,
        'no_warnings': True,
        
        # ВАЖНО: Не используем конвертацию видео, она ломает процесс.
        # Просто добавляем метаданные.
        'postprocessors': [
            {'key': 'FFmpegMetadata', 'add_metadata': True}
        ]
    }

    opts = apply_cookies(opts)
    
    if custom_opts:
        if 'postprocessors' in custom_opts:
            # Если просим аудио - заменяем постпроцессоры полностью
            opts['postprocessors'] = custom_opts['postprocessors']
            del custom_opts['postprocessors']
        # Если в custom_opts есть формат (например, bestaudio), он перепишет 'best'
        opts.update(custom_opts)

    result = await base_download(url, opts)
    return result