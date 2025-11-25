from .base import base_download
import os

# --- ВАЖНО: Добавили custom_opts=None ---
async def download(url: str, custom_opts: dict = None):
    opts = {}

    if os.path.exists("cookies.txt"):
        opts['cookiefile'] = "cookies.txt"

    if "music.youtube.com" in url:
        opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    else:
        opts.update({
            'format': 'bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4' 
        })

    # Передаем custom_opts в base_download
    return await base_download(url, opts if not custom_opts else {**opts, **custom_opts})