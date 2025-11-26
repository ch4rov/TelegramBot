from .base import base_download
import os

async def download(url: str, custom_opts: dict = None):
    opts = {}

    if os.path.exists("cookies.txt"):
        opts['cookiefile'] = "cookies.txt"

    # Логика для Музыки (или если custom_opts просят аудио)
    is_music_request = False
    if "music.youtube.com" in url:
        is_music_request = True
    elif custom_opts and 'postprocessors' in custom_opts:
        # Проверяем, не просят ли нас сделать mp3
        for pp in custom_opts['postprocessors']:
            if pp['key'] == 'FFmpegExtractAudio':
                is_music_request = True
                break

    if is_music_request:
        # --- НАСТРОЙКИ ДЛЯ АУДИО ---
        opts.update({
            'format': 'bestaudio/best',
            # ВАЖНЕЙШИЙ МОМЕНТ: Порядок действий
            'postprocessors': [
                # 1. Сначала делаем MP3
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192'
                },
                # 2. Только ПОТОМ вшиваем обложку (MP3 это поддерживает)
                {'key': 'EmbedThumbnail'},
                # 3. И метаданные
                {'key': 'FFmpegMetadata', 'add_metadata': True}
            ],
        })
    else:
        # --- НАСТРОЙКИ ДЛЯ ВИДЕО ---
        opts.update({
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
            # Для видео обложка вшивается через base.py или тут, порядок не так критичен для MP4
        })

    # Если передали custom_opts, они имеют приоритет, но мы уже учли аудио выше
    if custom_opts:
        # Если мы уже настроили постпроцессоры для музыки, не даем custom_opts их сломать
        if is_music_request and 'postprocessors' in custom_opts:
            del custom_opts['postprocessors']
            
        opts.update(custom_opts)

    return await base_download(url, opts)