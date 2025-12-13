import os
import sys
from dotenv import load_dotenv

# === 1. ГЕНЕРАЦИЯ ШАБЛОНА .ENV ===
ENV_FILE = ".env"

ENV_TEMPLATE = """# ==========================================
#        ОБЯЗАТЕЛЬНЫЕ НАСТРОЙКИ (CORE)
# ==========================================

# 1. Режим среды
# True  = TESTING (Использует TEST_BOT_TOKEN, чистит кэш)
# False = STABLE  (Использует основной BOT_TOKEN)
IS_TEST_ENV=False

# 2. Токены Telegram
# Основной (Stable)
BOT_TOKEN=
# Тестовый (Testing)
TEST_BOT_TOKEN=

# 3. Доступ
# Ваш ID (Главный админ)
ADMIN_ID=
# ID Технического канала (Logs)
TECH_CHAT_ID=

# 4. API Ключи
LASTFM_API_KEY=


# ==========================================
#  TELEGRAM API: LOCAL SERVER (DOCKER)
# ==========================================
# Public Cloud API имеет лимит на отправку файлов 50 МБ.
# Local Bot API Server (telegram-bot-api в Docker) позволяет слать до 2000 МБ.
# Включайте только если у вас запущен этот контейнер.

# Использовать локальный сервер API? (True/False)
USE_LOCAL_SERVER=False

# Адрес вашего Docker-контейнера с API (обычно порт 8081)
# Пример: http://127.0.0.1:8081
LOCAL_SERVER_URL=http://127.0.0.1:8081


# ==========================================
#  TELEGRAM INPUT: WEBHOOK VS POLLING
# ==========================================
# Polling (False): Бот сам опрашивает сервера Telegram. (Удобно для разработки)
# Webhook (True):  Telegram шлет запросы боту. (Нужен "белый" IP/SSL, для VDS)

USE_WEBHOOK=False

# Настройки для поднятия aiohttp сервера (только если USE_WEBHOOK=True)
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8080
WEBHOOK_PATH=/webhook


# ==========================================
#       ЛОГИРОВАНИЕ (DISCORD)
# ==========================================

# --- ВАРИАНТ 1: ЧЕРЕЗ БОТА (РЕКОМЕНДУЕТСЯ) ---
# Требует токен бота и включенный "Message Content Intent"
ENABLE_DISCORD_BOT_LOG=False
DISCORD_BOT_TOKEN=
# ID Веток (Threads). Оставьте 0, если не используете ветки.
DISCORD_LOG_THREAD_ID_MAIN=0
DISCORD_LOG_THREAD_ID_TEST=0

# --- ВАРИАНТ 2: ЧЕРЕЗ ВЕБХУК (LEGACY) ---
# Устаревший метод. Просто ссылка на вебхук.
DISCORD_WEBHOOK_URL=


# ==========================================
#       ВЕБ-ПАНЕЛЬ (DASHBOARD)
# ==========================================
ENABLE_WEB_DASHBOARD=False
WEB_ADMIN_USER=admin
WEB_ADMIN_PASS=admin
WEB_SECRET_KEY=secret_key
"""

if not os.path.exists(ENV_FILE):
    print(f"⚠️ Файл {ENV_FILE} не найден!")
    print(f"⚙️ Создаю чистый файл {ENV_FILE} с документацией...")
    try:
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write(ENV_TEMPLATE)
        print(f"✅ Файл {ENV_FILE} создан.")
        print("🛑 БОТ ОСТАНОВЛЕН. Заполните настройки в .env")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Ошибка создания .env: {e}")
        sys.exit(1)

# === 2. ЗАГРУЗКА И ОБРАБОТКА ===
load_dotenv()

def get_bool(key, default=False):
    val = os.getenv(key, str(default)).lower()
    return val in ["true", "1", "yes", "on"]

def get_list(key):
    val = os.getenv(key, "")
    if not val or val == "0": return []
    try:
        return [int(x.strip()) for x in val.split(",") if x.strip().isdigit()]
    except:
        return []

# --- CORE SETTINGS ---
IS_TEST_ENV = get_bool("IS_TEST_ENV", False)

# Выбор токена
if IS_TEST_ENV:
    target = os.getenv("TEST_BOT_TOKEN")
    BOT_TOKEN = target if target else os.getenv("BOT_TOKEN")
else:
    BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("❌ ОШИБКА: Токен не найден в .env!")
    sys.exit(1)

# Админы
MAIN_ADMIN = os.getenv("ADMIN_ID")
ADMIN_IDS = [int(MAIN_ADMIN)] if (MAIN_ADMIN and MAIN_ADMIN.isdigit()) else []
# Тестеры (опционально можно добавить логику слияния списков, если нужно)

# Тех чат
TECH_CHAT_ID = os.getenv("TECH_CHAT_ID")
LOG_CHANNEL_ID = int(TECH_CHAT_ID) if (TECH_CHAT_ID and TECH_CHAT_ID.lstrip("-").isdigit()) else None

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")

# --- TELEGRAM API (LOCAL SERVER / DOCKER) ---
# Настройки для обхода лимита 50МБ
USE_LOCAL_SERVER = get_bool("USE_LOCAL_SERVER", False)
LOCAL_SERVER_URL = os.getenv("LOCAL_SERVER_URL", "http://127.0.0.1:8081")

# --- TELEGRAM INPUT (WEBHOOK) ---
# Настройки получения входящих сообщений
USE_WEBHOOK = get_bool("USE_WEBHOOK", False)
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", 8080))
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")

# --- DISCORD LOGGING ---
ENABLE_DISCORD_BOT_LOG = get_bool("ENABLE_DISCORD_BOT_LOG", False)
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_LOG_THREAD_ID_MAIN = int(os.getenv("DISCORD_LOG_THREAD_ID_MAIN", 0))
DISCORD_LOG_THREAD_ID_TEST = int(os.getenv("DISCORD_LOG_THREAD_ID_TEST", 0))

# Legacy
ENABLE_DISCORD_WEBHOOK_LOG = False
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# --- WEB DASHBOARD ---
ENABLE_WEB_DASHBOARD = get_bool("ENABLE_WEB_DASHBOARD", False)
WEB_ADMIN_USER = os.getenv("WEB_ADMIN_USER", "admin")
WEB_ADMIN_PASS = os.getenv("WEB_ADMIN_PASS", "admin")
WEB_SECRET_KEY = os.getenv("WEB_SECRET_KEY", "secret")

# --- CONSTANTS ---
MAX_FILE_SIZE = 2000 * 1024 * 1024 if USE_LOCAL_SERVER else 50 * 1024 * 1024

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