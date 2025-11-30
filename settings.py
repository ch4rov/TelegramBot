import os
from dotenv import load_dotenv

load_dotenv()

BOT_VERSION = "2.5"

# --- ТОКЕНЫ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
TEST_BOT_TOKEN = os.getenv("TEST_BOT_TOKEN")
IS_TEST_ENV = (BOT_TOKEN == TEST_BOT_TOKEN) and (BOT_TOKEN is not None)

# --- СЕРВЕР ---
USE_LOCAL_SERVER = os.getenv("USE_LOCAL_SERVER", "False").lower() == "true"
LOCAL_SERVER_URL = os.getenv("LOCAL_SERVER_URL", "http://localhost:8081")

# --- ЛИМИТЫ ---
MAX_FILE_SIZE = 2000 * 1024 * 1024 if USE_LOCAL_SERVER else 50 * 1024 * 1024
MAX_CONCURRENT_DOWNLOADS = 3

# --- ПУТИ И API ---
DOWNLOADS_DIR = "downloadAndRemove"
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_API_URL = "http://ws.audioscrobbler.com/2.0/"
TECH_CHAT_ID = os.getenv("TECH_CHAT_ID")

# --- БЕЗОПАСНОСТЬ ---
env_testers = os.getenv("TESTERS_IDS", "")
TESTERS_LIST = set(int(x) for x in env_testers.split(",")) if env_testers else set()
if os.getenv("ADMIN_ID"): TESTERS_LIST.add(int(os.getenv("ADMIN_ID")))

SAFE_CHARS = r'[a-zA-Z0-9\-\_\.\/\?\=\&\%\+\~]+'

URL_PATTERNS = [
    r'^https?://(www\.|m\.)?vk\.(com|ru)/video.*',
    r'^https?://(www\.|m\.)?vk\.(com|ru)/clip.*',
    r'^https?://(www\.|m\.)?vkvideo\.ru/.*',
    r'^https?://(www\.|vm\.|vt\.|m\.)?tiktok\.com/.*', 
    r'^https?://(www\.|m\.)?instagram\.com/.*',
    r'^https?://(www\.|m\.|music\.)?youtube\.com/.*',
    r'^https?://(www\.)?youtu\.be/.*',
    r'^https?://(www\.|m\.)?soundcloud\.com/.*',
    r'^https?://(www\.|m\.|clips\.)?twitch\.tv/.*',
    r'^https?://(open\.)?spotify\.com/.*',
    r'^https?://spotify\.link/.*',
]

# --- СПИСОК КОМАНД ---
BOT_COMMANDS_LIST = [
    ("start", "Перезапустить бота", "user", False),
    ("login", "Привязать Last.fm", "user", True),
    ("users", "Список пользователей", "admin_mod", False),
    ("ban", "Бан (нажми и введи ID)", "admin_mod", True),
    ("unban", "Разбан (нажми и введи ID)", "admin_mod", True),
    ("answer", "Ответ (нажми и введи ID)", "admin_mod", True),
    ("status", "Состояние системы", "admin_tech", False),
    ("check", "Health Check", "admin_tech", False),
    ("update", "Обновить с GitHub", "admin_tech", False),
    ("clearcache", "Очистить кэш файлов", "admin_tech", False),
    ("fix_ffmpeg", "Переустановить FFmpeg", "admin_tech", False),
    ("get_placeholder", "ID видео-заглушки", "admin_tech", False),
    ("get_audio_placeholder", "ID аудио-заглушки", "admin_tech", False),
    ("modules", "Управление модулями", "admin_tech", False),
    ("exec", "Python Console", "admin_tech", True),
]

# --- МОДУЛИ (Вкл/Выкл) ---
# Добавлен TextFind
MODULES_LIST = [
    "YouTube", "YouTubeMusic", "Instagram", 
    "TikTokVideos", "TikTokPhotos", "TelegramVideo", 
    "Twitch", "VK", "SoundCloud", "Spotify",
    "InlineVideo", "InlineAudio", "TextFind"
]

# Имя бота (заполнится автоматически)
BOT_USERNAME = None