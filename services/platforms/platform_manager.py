import re
import settings
from services.database_service import get_module_status
import messages as msg

# Импорты стратегий
from .VKDownloader.vk_strategy import VKStrategy
from .YTDownloader.youtube_strategy import YouTubeVideoStrategy
from .YTDownloader.youtube_music_strategy import YouTubeMusicStrategy
from .TikTokDownloader.tiktok_strategy import TikTokStrategy
from .TikTokDownloader.tiktok_photo_strategy import TikTokPhotoStrategy
from .InstagramDownloader.instagram_strategy import InstagramStrategy
from .SoundCloudDownloader.soundcloud_strategy import SoundCloudStrategy
from .TwitchDownloader.twitch_strategy import TwitchStrategy 
from .SpotifyDownloader.spotify_strategy import SpotifyStrategy
# --- НОВЫЕ ИМПОРТЫ ---
from .YandexDownloader.yandex_strategy import YandexStrategy
from .AppleDownloader.apple_strategy import AppleStrategy
# ---------------------
from .common_downloader import CommonDownloader

def is_valid_url(url: str) -> bool:
    if re.search(r'[;$\`"\'\{\}\[\]\|\^]', url): return False
    for pattern in settings.URL_PATTERNS:
        if re.match(pattern, url): return True
    return False

async def route_download(url: str, custom_opts: dict = None):
    if not is_valid_url(url):
        return None, None, "Ссылка не поддерживается или запрещена ⛔", None

    downloader: CommonDownloader = None
    module_key = None 

    # --- VK ---
    if "vk.com" in url or "vk.ru" in url or "vkvideo.ru" in url:
        downloader = VKStrategy(url)
        module_key = "VK"
        
    # --- YOUTUBE ---
    elif "youtube.com" in url or "youtu.be" in url:
        is_music_url = "music.youtube.com" in url
        force_video = custom_opts.get('force_video') if custom_opts else False
        force_audio = False
        if custom_opts and 'postprocessors' in custom_opts:
            for pp in custom_opts['postprocessors']:
                if pp.get('key') == 'FFmpegExtractAudio': force_audio = True

        if (is_music_url and not force_video) or force_audio:
            downloader = YouTubeMusicStrategy(url)
            module_key = "YouTubeMusic"
        else:
            downloader = YouTubeVideoStrategy(url)
            module_key = "YouTube"
        
    # --- TIKTOK ---
    elif "tiktok.com" in url:
        if "/photo/" in url:
            downloader = TikTokPhotoStrategy(url)
            module_key = "TikTokPhotos"
        else:
            downloader = TikTokStrategy(url)
            module_key = "TikTokVideos"
        
    # --- INSTAGRAM ---
    elif "instagram.com" in url:
        downloader = InstagramStrategy(url)
        module_key = "Instagram"
        
    # --- SOUNDCLOUD ---
    elif "soundcloud.com" in url:
        downloader = SoundCloudStrategy(url)
        module_key = "SoundCloud"
        
    # --- TWITCH ---
    elif "twitch.tv" in url:
        downloader = TwitchStrategy(url)
        module_key = "Twitch"

    # --- SPOTIFY ---
    elif "spotify.com" in url or "spotify.link" in url or "spotify.com" in url:
        downloader = SpotifyStrategy(url)
        module_key = "Spotify"

    # --- YANDEX (НОВОЕ) ---
    elif "music.yandex" in url:
        downloader = YandexStrategy(url)
        module_key = "YandexMusic"

    # --- APPLE (НОВОЕ) ---
    elif "music.apple.com" in url:
        downloader = AppleStrategy(url)
        module_key = "AppleMusic"

    # --- ПРОВЕРКА СТАТУСА ---
    if module_key:
        is_enabled = await get_module_status(module_key)
        if not is_enabled:
            return None, None, msg.MSG_DISABLE_MODULE, None

    # --- ЗАПУСК ---
    if downloader:
        if custom_opts:
            downloader.configure(**custom_opts)
        try:
            return await downloader.download()
        except Exception as e:
            return None, None, str(e), None
    
    else:
        return None, None, "Сервис не найден.", None

download_content = route_download