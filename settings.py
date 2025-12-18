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
]