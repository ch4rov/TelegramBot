from .base import base_download

async def download(url: str, custom_opts: dict = None):
    # Настройки специально для Twitch
    opts = {
        # Twitch отдает потоковое видео. 
        # Принудительно собираем его в контейнер MP4, чтобы Телеграм принял файл.
        'merge_output_format': 'mp4'
    }

    # Если передали дополнительные настройки (например, конвертация в mp3 для инлайна)
    if custom_opts:
        opts.update(custom_opts)

    return await base_download(url, opts)