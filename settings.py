import os
import sys
from dotenv import load_dotenv

load_dotenv()

IS_TEST_ENV = os.getenv("IS_TEST_ENV", "False").lower() in ("true", "1", "yes")

BOT_TOKEN = os.getenv("TEST_BOT_TOKEN") if IS_TEST_ENV else os.getenv("BOT_TOKEN")

ADMIN_ID_RAW = os.getenv("ADMIN_ID", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_ID_RAW.split(",") if x.strip().isdigit()]

TECH_CHAT_ID = os.getenv("TECH_CHAT_ID")
LOG_CHANNEL_ID = int(TECH_CHAT_ID) if (TECH_CHAT_ID and TECH_CHAT_ID.lstrip("-").isdigit()) else None

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "sqlite+aiosqlite:///users.db"

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_API_URL = "http://ws.audioscrobbler.com/2.0/"
LASTFM_SECRET = os.getenv("LASTFM_SECRET")

USE_LOCAL_SERVER = os.getenv("USE_LOCAL_SERVER", "False").lower() == "true"
LOCAL_SERVER_URL = os.getenv("LOCAL_SERVER_URL", "http://127.0.0.1:8081")

# === OAuth (Spotify) ===
PUBLIC_BASE_URL = (os.getenv("TEST_PUBLIC_BASE_URL") if IS_TEST_ENV else os.getenv("PUBLIC_BASE_URL")) or ""
PUBLIC_BASE_URL = PUBLIC_BASE_URL.strip().rstrip("/")

OAUTH_HTTP_HOST = (os.getenv("OAUTH_HTTP_HOST") or "127.0.0.1").strip() or "127.0.0.1"
try:
    OAUTH_HTTP_PORT = int((os.getenv("TEST_OAUTH_HTTP_PORT") if IS_TEST_ENV else os.getenv("OAUTH_HTTP_PORT")) or ("8089" if IS_TEST_ENV else "8088"))
except Exception:
    OAUTH_HTTP_PORT = 8089 if IS_TEST_ENV else 8088

SPOTIFY_CLIENT_ID = (os.getenv("TEST_SPOTIFY_CLIENT_ID") if IS_TEST_ENV else os.getenv("SPOTIFY_CLIENT_ID")) or ""
SPOTIFY_CLIENT_SECRET = (os.getenv("TEST_SPOTIFY_CLIENT_SECRET") if IS_TEST_ENV else os.getenv("SPOTIFY_CLIENT_SECRET")) or ""
SPOTIFY_SCOPES = (os.getenv("SPOTIFY_SCOPES") or "user-read-currently-playing user-read-recently-played").strip()

TEMP_DIR = "tempfiles"

ENABLE_DISCORD_BOT_LOG = os.getenv("ENABLE_DISCORD_BOT_LOG", "False").lower() == "true"
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_LOG_THREAD_ID_MAIN = int(os.getenv("DISCORD_LOG_THREAD_ID_MAIN", 0))
DISCORD_LOG_THREAD_ID_TEST = int(os.getenv("DISCORD_LOG_THREAD_ID_TEST", 0))

MAX_FILE_SIZE = 2000 * 1024 * 1024 if USE_LOCAL_SERVER else 50 * 1024 * 1024

# Все доступные платформы
MODULES_LIST = [
    "AppleMusic",
    "Instagram",
    "SoundCloud",
    "Spotify",
    "YouTube",
    "YouTubeMusic",
    "TelegramVideo",
    "TikTokVideo",
    "TikTokPhoto",
    "Twitch",
    "VK",
    "YandexMusic",
    "InlineAudio",
    "InlineVideo",
]

# Формат: (command_name, description_en, description_ru, user_type, show_in_menu)
# user_type: "user" или "admin"
# show_in_menu: должна ли команда отображаться в /start меню
BOT_COMMANDS_LIST = [
    # User commands
    ("start", "Main Menu", "Главное меню", "user", False),
    ("language", "Toggle Language", "Переключить язык", "user", True),
    ("login", "Last.fm Connect", "Подключить Last.fm", "user", False),
    ("links", "Toggle Links", "Переключить ссылки", "user", False),
    ("videomessage", "Video Note Mode", "Режим видеозаписи", "user", True),
    ("addcookies", "Add Cookies", "Добавить куки", "user", False),
    
    # Admin commands
    ("sharecookies", "Share Global Cookies", "Поделиться куки", "admin", True),
    ("users", "User List", "Список пользователей", "admin", True),
    ("ban", "Ban User", "Заблокировать", "admin", True),
    ("unban", "Unban User", "Разблокировать", "admin", True),
    ("check", "System Health Check", "Проверка системы", "admin", True),
    ("answer", "Send Message to User", "Отправить сообщение", "admin", True),
    ("status", "System Status", "Статус системы", "admin", True),
    ("clearcache", "Clear Cache", "Очистить кэш", "admin", True),
    ("modules", "Manage Modules", "Управление модулями", "admin", True),
    ("edituser", "Edit user/group", "Редактировать пользователя/группу", "admin", True),
    ("update", "Update bot commands", "Обновить команды", "admin", True),
    ("savedb", "Save DB to tech chat", "Сохранить БД в тех-чат", "admin", True),
    ("cmd", "All Commands", "Все команды", "admin", False),
]