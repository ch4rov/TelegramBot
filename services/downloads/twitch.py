from .base import base_download

async def download(url: str):
    opts = {
        # Twitch отдает потоковое видео (m3u8). 
        # Телеграм не понимает этот формат, поэтому принудительно
        # собираем (merge) видео и аудио в контейнер MP4.
        'merge_output_format': 'mp4'
    }
    return await base_download(url, opts)