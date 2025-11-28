import re
from urllib.parse import urlparse, parse_qs

def clean_url(url: str) -> str:
    """
    Приводит ссылки к каноническому виду.
    Сохраняет различие между YouTube Music и обычным YouTube.
    """
    url = url.strip()
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path

    # --- YOUTUBE & MUSIC ---
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
            # Вариант 3: Shorts
            elif '/shorts/' in path:
                video_id = path.split('/shorts/')[-1].strip('/')

        if video_id:
            # ВАЖНОЕ ИЗМЕНЕНИЕ: Если это Music, сохраняем домен music
            if "music.youtube.com" in domain:
                return f"https://music.youtube.com/watch?v={video_id}"
            else:
                return f"https://youtu.be/{video_id}"

    # --- TIKTOK ---
    if 'tiktok.com' in domain:
        # Убираем query параметры, оставляем путь
        return f"{parsed.scheme}://{domain}{path}"

    # --- INSTAGRAM ---
    if 'instagram.com' in domain:
        # Убираем query параметры
        return f"{parsed.scheme}://{domain}{path}".rstrip('/')

    # Остальные (SoundCloud, Twitch)
    # Просто убираем мусорные параметры (?si=...), если они есть,
    # но для простоты можно вернуть очищенный от пробелов URL
    # Для SoundCloud лучше отрезать query параметры вручную
    if 'soundcloud.com' in domain:
         return url.split('?')[0]

    return url