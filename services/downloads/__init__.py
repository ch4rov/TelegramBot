from . import tiktok, instagram, youtube, soundcloud, twitch
import re
import settings

SAFE_CHARS = r'[a-zA-Z0-9\-\_\.\/\?\=\&\%]+'

def is_valid_url(url: str) -> bool:
    if re.search(r'[;$\`"\'\{\}\[\]\|\^]', url):
        return False
    for pattern in settings.URL_PATTERNS:
        if re.match(pattern, url):
            return True
    return False

# --- ВАЖНО: Добавили custom_opts=None ---
async def download_content(url: str, custom_opts: dict = None):
    if not is_valid_url(url):
        return None, None, "Ссылка не поддерживается или запрещена ⛔"

    # Передаем custom_opts во все модули
    if "tiktok.com" in url:
        return await tiktok.download(url, custom_opts)
        
    elif "instagram.com" in url:
        return await instagram.download(url, custom_opts)
        
    elif "youtube.com" in url or "youtu.be" in url:
        return await youtube.download(url, custom_opts)
        
    elif "soundcloud.com" in url:
        return await soundcloud.download(url, custom_opts)
    
    elif "twitch.tv" in url:
        return await twitch.download(url, custom_opts)

    else:
        return None, None, "Неизвестный сервис."