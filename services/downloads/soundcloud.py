from .base import base_download

async def download(url: str):
    opts = {
        'format': 'bestaudio/best',
        # Добавляем процессоры. Base.py сам склеит их с EmbedThumbnail
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    return await base_download(url, opts)