import re
from urllib.parse import urlparse, parse_qs

def clean_url(url: str) -> str:
    """
    Приводит ссылки к каноническому виду для идеального кэширования.
    """
    url = url.strip()
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path

    # --- YOUTUBE (Видео и Shorts) ---
    if 'youtube.com' in domain or 'youtu.be' in domain:
        video_id = None
        
        # Вариант 1: youtu.be/ID
        if 'youtu.be' in domain:
            video_id = path.strip('/')
        
        # Вариант 2: youtube.com/watch?v=ID
        if 'youtube.com' in domain:
            if '/watch' in path:
                qs = parse_qs(parsed.query)
                video_id = qs.get('v', [None])[0]
            # Вариант 3: youtube.com/shorts/ID
            elif '/shorts/' in path:
                video_id = path.split('/shorts/')[-1].strip('/')

        if video_id:
            # Возвращаем единый стандарт для базы
            return f"https://youtu.be/{video_id}"

    # --- TIKTOK (Убираем мусор ?share_id=...) ---
    if 'tiktok.com' in domain:
        # Для тиктока важно сохранить путь (там ID автора и видео), но убрать query параметры
        # https://www.tiktok.com/@user/video/12345?is_from_webapp=1 -> https://www.tiktok.com/@user/video/12345
        no_query_url = f"{parsed.scheme}://{domain}{path}"
        return no_query_url

    # --- INSTAGRAM (Убираем ?igsh=...) ---
    if 'instagram.com' in domain:
        no_query_url = f"{parsed.scheme}://{domain}{path}"
        # Убираем слэш в конце для красоты
        return no_query_url.rstrip('/')

    # Если сервис не специфичный, просто возвращаем url без пробелов
    return url