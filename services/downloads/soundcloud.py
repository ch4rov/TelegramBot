from .base import base_download

async def download(url: str, custom_opts: dict = None):
    opts = {
        # SoundCloud отдает mp3 или aac, проблем с контейнерами обычно нет.
        # Но на всякий случай просим лучшее аудио.
        'format': 'bestaudio/best',
        'postprocessors': [
            # Конвертируем в mp3 для совместимости
            {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'},
            # Вшиваем обложку и метаданные (SoundCloud это поддерживает в MP3)
            {'key': 'EmbedThumbnail'},
            {'key': 'FFmpegMetadata', 'add_metadata': True}
        ]
    }

    # Если передали настройки из инлайна (custom_opts), обновляем
    if custom_opts:
        # Если в custom_opts есть свои постпроцессоры, они заменят наши дефолтные
        if 'postprocessors' in custom_opts:
            opts['postprocessors'] = custom_opts['postprocessors']
            del custom_opts['postprocessors']
        opts.update(custom_opts)

    return await base_download(url, opts)