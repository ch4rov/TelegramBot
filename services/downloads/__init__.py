from . import tiktok, instagram, youtube, soundcloud, twitch
import re

# Строгая проверка доменов через регулярные выражения
# ^ - начало строки, https? - http или https, (www\.)? - с www или без
URL_PATTERNS = [
    r'^https?://(www\.|vm\.|vt\.|m\.)?tiktok\.com/.*',
    r'^https?://(www\.|m\.)?instagram\.com/.*',
    r'^https?://(www\.|m\.|music\.)?youtube\.com/.*',
    r'^https?://(www\.)?youtu\.be/.*',
    r'^https?://(www\.|m\.)?soundcloud\.com/.*',
    r'^https?://(www\.|m\.|clips\.)?twitch\.tv/.*'
]

def is_valid_url(url: str) -> bool:
    for pattern in URL_PATTERNS:
        if re.match(pattern, url):
            return True
    return False

async def download_content(url: str):
    """
    Главная функция-роутер.
    """
    if not is_valid_url(url):
        return None, None, "Ссылка не поддерживается или домен запрещен ⛔"

    # Роутинг
    if "tiktok.com" in url:
        return await tiktok.download(url)
        
    elif "instagram.com" in url:
        return await instagram.download(url)
        
    elif "youtube.com" in url or "youtu.be" in url:
        return await youtube.download(url)
        
    elif "soundcloud.com" in url:
        return await soundcloud.download(url)
    
    elif "twitch.tv" in url:
        return await twitch.download(url)

    else:
        return None, None, "Неизвестный сервис."