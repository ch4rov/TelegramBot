import re
import settings

# --- ИМПОРТЫ СТРАТЕГИЙ ---
from .VKDownloader.vk_strategy import VKStrategy
# Исправленные импорты YouTube
from .YTDownloader.youtube_strategy import YouTubeVideoStrategy
from .YTDownloader.youtube_music_strategy import YouTubeMusicStrategy

from .TikTokDownloader.tiktok_strategy import TikTokStrategy
from .TikTokDownloader.tiktok_photo_strategy import TikTokPhotoStrategy
from .InstagramDownloader.instagram_strategy import InstagramStrategy
from .SoundCloudDownloader.soundcloud_strategy import SoundCloudStrategy
from .TwitchDownloader.twitch_strategy import TwitchStrategy 
from .common_downloader import CommonDownloader

# --- ВАЛИДАТОР ---
def is_valid_url(url: str) -> bool:
    if re.search(r'[;$\`"\'\{\}\[\]\|\^]', url): return False
    for pattern in settings.URL_PATTERNS:
        if re.match(pattern, url): return True
    return False

# --- РОУТЕР ---
async def route_download(url: str, custom_opts: dict = None):
    """
    Фабрика загрузчиков: выбирает нужный класс в зависимости от ссылки.
    """
    
    if not is_valid_url(url):
        return None, None, "Ссылка не поддерживается или запрещена ⛔"

    downloader: CommonDownloader = None

    # --- VK ---
    if "vk.com" in url or "vk.ru" in url or "vkvideo.ru" in url:
        downloader = VKStrategy(url)
        
    # --- YOUTUBE (Умный выбор) ---
    elif "youtube.com" in url or "youtu.be" in url:
        is_music_url = "music.youtube.com" in url
        
        # Проверяем флаги
        force_video = False
        force_audio = False
        
        if custom_opts:
            # Кнопка "Загрузить клип" передает force_video=True
            if custom_opts.get('force_video'):
                force_video = True
            
            # Инлайн-поиск передает постпроцессор Audio
            if 'postprocessors' in custom_opts:
                for pp in custom_opts['postprocessors']:
                    if pp.get('key') == 'FFmpegExtractAudio':
                        force_audio = True
                        break
        
        # Принимаем решение: какую стратегию использовать
        if (is_music_url and not force_video) or force_audio:
            downloader = YouTubeMusicStrategy(url)
        else:
            downloader = YouTubeVideoStrategy(url)
        
    # --- TIKTOK ---
    elif "tiktok.com" in url:
        if "/photo/" in url:
            downloader = TikTokPhotoStrategy(url)
        else:
            downloader = TikTokStrategy(url)
        
    # --- INSTAGRAM ---
    elif "instagram.com" in url:
        downloader = InstagramStrategy(url)
        
    # --- SOUNDCLOUD ---
    elif "soundcloud.com" in url:
        downloader = SoundCloudStrategy(url)
        
    # --- TWITCH ---
    elif "twitch.tv" in url:
        downloader = TwitchStrategy(url)

    # --- ЗАПУСК ---
    if downloader:
        if custom_opts:
            downloader.configure(**custom_opts)
        
        # Ловим ошибки инициализации (например "Модуль отключен")
        try:
            return await downloader.download()
        except Exception as e:
            return None, None, str(e)
    
    else:
        return None, None, "Сервис не найден (проверьте ссылку)."

# Алиас
download_content = route_download