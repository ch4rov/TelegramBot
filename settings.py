import os
import time
from dotenv import load_dotenv

load_dotenv()
START_TIME = time.time()
BOT_VERSION = "2.5.8"

# --- ТОКЕНЫ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
TEST_BOT_TOKEN = os.getenv("TEST_BOT_TOKEN")
IS_TEST_ENV = (BOT_TOKEN == TEST_BOT_TOKEN) and (BOT_TOKEN is not None)

# --- СЕРВЕР ---
FORCE_CLOUD_FILE = ".force_cloud"
IS_FORCED_CLOUD = os.path.exists(FORCE_CLOUD_FILE)

if IS_FORCED_CLOUD:
    USE_LOCAL_SERVER = False
    LOCAL_SERVER_URL = None
    # Сообщение для админа, которое отправится после рестарта
    STARTUP_ERROR_MESSAGE = "⚠️ <b>Аварийный режим!</b>\nЛокальный сервер упал во время работы. Бот переведен на Cloud API."
else:
    # 2. Иначе берем настройки из .env
    USE_LOCAL_SERVER = os.getenv("USE_LOCAL_SERVER", "False").lower() == "true"
    LOCAL_SERVER_URL = os.getenv("LOCAL_SERVER_URL", "http://localhost:8081")
    STARTUP_ERROR_MESSAGE = None

# --- ЛИМИТЫ (НОВОЕ) ---
# Глобальный лимит (для режима /limit on)
GLOBAL_MAX_CONCURRENT = 3
# Лимит на одного пользователя (всегда активен)
USER_MAX_CONCURRENT = 3
# --- ЛИМИТЫ ---
MAX_FILE_SIZE = 2000 * 1024 * 1024 if USE_LOCAL_SERVER else 50 * 1024 * 1024
MAX_CONCURRENT_DOWNLOADS = 3

# --- ПУТИ И API ---
DOWNLOADS_DIR = "downloads"
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_API_URL = "http://ws.audioscrobbler.com/2.0/"
TECH_CHAT_ID = os.getenv("TECH_CHAT_ID")

# --- БЕЗОПАСНОСТЬ ---
env_testers = os.getenv("TESTERS_IDS", "")
TESTERS_LIST = set(int(x) for x in env_testers.split(",")) if env_testers else set()
if os.getenv("ADMIN_ID"): TESTERS_LIST.add(int(os.getenv("ADMIN_ID")))

# --- WEB DASHBOARD (НОВОЕ) ---
ENABLE_WEB_DASHBOARD = os.getenv("ENABLE_WEB_DASHBOARD", "False").lower() == "true"
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = 8082
WEB_ADMIN_USER = os.getenv("WEB_ADMIN_USER", "admin")
WEB_ADMIN_PASS = os.getenv("WEB_ADMIN_PASS", "admin")
WEB_SECRET_KEY = os.getenv("WEB_SECRET_KEY", "super_secret_cookie_key_123")

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
    r'.*googleusercontent\.com/spotify\.com/.*',
    r'^https?://spotify\.link/.*',
    r'^https?://music\.yandex\.[a-z]{2,3}/.*',
    r'^https?://(geo\.)?music\.apple\.com/.*',
]

# --- СПИСОК КОМАНД ---
BOT_COMMANDS_LIST = [
    # Пользователь
    ("start", "cmd_start", "user", False),
    ("login", "cmd_login", "user", True),
    ("language", "cmd_language", "user", False),
    
    # Админ - Модерация
    ("users", "cmd_users", "admin_mod", False),
    ("ban", "cmd_ban", "admin_mod", True),
    ("unban", "cmd_unban", "admin_mod", True),
    ("answer", "cmd_answer", "admin_mod", True),
    ("check", "cmd_check", "admin_tech", False),
    ("update", "cmd_update", "admin_tech", False),
    ("clearcache", "cmd_clearcache", "admin_tech", False),
]

# --- МОДУЛИ (Вкл/Выкл) ---
# Добавлен TextFind
MODULES_LIST = [
    "YouTube", "YouTubeMusic", "Instagram", 
    "TikTokVideos", "TikTokPhotos", "TelegramVideo", 
    "Twitch", "VK", "SoundCloud", "Spotify",
    "InlineVideo", "InlineAudio", "TextFind",
    "YandexMusic", "AppleMusic"
]

# Имя бота (заполнится автоматически)
BOT_USERNAME = None