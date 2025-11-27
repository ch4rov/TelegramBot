import os
from dotenv import load_dotenv

load_dotenv()

# --- ТОКЕНЫ И РЕЖИМ РАБОТЫ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
TEST_BOT_TOKEN = os.getenv("TEST_BOT_TOKEN")

# Автоматическое определение: Тест или Основа?
# Если текущий токен совпадает с тестовым -> IS_TEST_ENV = True
IS_TEST_ENV = (BOT_TOKEN == TEST_BOT_TOKEN) and (BOT_TOKEN is not None)

# --- НАСТРОЙКИ СЕРВЕРА (DOCKER) ---
USE_LOCAL_SERVER = os.getenv("USE_LOCAL_SERVER", "False").lower() == "true"
LOCAL_SERVER_URL = os.getenv("LOCAL_SERVER_URL", "http://localhost:8081")

# --- ЛИМИТЫ ---
# 2 ГБ для локального сервера, 50 МБ для публичного
MAX_FILE_SIZE = 2000 * 1024 * 1024 if USE_LOCAL_SERVER else 50 * 1024 * 1024
MAX_CONCURRENT_DOWNLOADS = 3

# --- ПУТИ ---
DOWNLOADS_DIR = "downloadAndRemove"

# --- API И ЧАТЫ ---
TECH_CHAT_ID = os.getenv("TECH_CHAT_ID")

# Берем ключ из .env (безопасно)
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY") 
LASTFM_API_URL = "http://ws.audioscrobbler.com/2.0/"

# --- СПИСОК ТЕСТЕРОВ ---
env_testers = os.getenv("TESTERS_IDS", "")
TESTERS_LIST = set(int(x) for x in env_testers.split(",")) if env_testers else set()
# Админ всегда тестер
if os.getenv("ADMIN_ID"):
    TESTERS_LIST.add(int(os.getenv("ADMIN_ID")))

# --- БЕЗОПАСНОСТЬ И ВАЛИДАЦИЯ ---
SAFE_CHARS = r'[a-zA-Z0-9\-\_\.\/\?\=\&\%\+\~]+'

URL_PATTERNS = [
    # VK Video
    r'^https?://(www\.|m\.)?vk\.(com|ru)/video.*',
    r'^https?://(www\.|m\.)?vk\.(com|ru)/clip.*',
    r'^https?://(www\.|m\.)?vkvideo\.ru/.*',
    
    # TikTok
    r'^https?://(www\.|vm\.|vt\.|m\.)?tiktok\.com/.*', 
    
    # Instagram
    r'^https?://(www\.|m\.)?instagram\.com/.*',
    
    # YouTube
    r'^https?://(www\.|m\.|music\.)?youtube\.com/.*',
    r'^https?://(www\.)?youtu\.be/.*',
    
    # SoundCloud
    r'^https?://(www\.|m\.)?soundcloud\.com/.*',
    
    # Twitch
    r'^https?://(www\.|m\.|clips\.)?twitch\.tv/.*'
]