import os
import sys
from dotenv import load_dotenv

# === 1. КОНФИГУРАЦИЯ И ШАБЛОН ===
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

# 4. Технический чат (Storage)
# Чат для хранения файлов, плейсхолдеров и кэширования file_id.
# Бот должен быть администратором.
TECH_CHAT_ID=

# 5. API Ключи
LASTFM_API_KEY=


# ==========================================
#  TELEGRAM API: LOCAL SERVER (DOCKER)
# ==========================================
# Использовать локальный сервер API? (True/False)
USE_LOCAL_SERVER=False

# Адрес вашего Docker-контейнера с API (обычно порт 8081)
LOCAL_SERVER_URL=http://127.0.0.1:8081


# ==========================================
#  TELEGRAM INPUT: WEBHOOK VS POLLING
# ==========================================
USE_WEBHOOK=False
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8080
WEBHOOK_PATH=/webhook


# ==========================================
#       ЛОГИРОВАНИЕ (DISCORD)
# ==========================================
ENABLE_DISCORD_BOT_LOG=False
DISCORD_BOT_TOKEN=
DISCORD_LOG_THREAD_ID_MAIN=0
DISCORD_LOG_THREAD_ID_TEST=0

# Legacy
DISCORD_WEBHOOK_URL=


# ==========================================
#       ВЕБ-ПАНЕЛЬ (DASHBOARD)
# ==========================================
ENABLE_WEB_DASHBOARD=False
WEB_ADMIN_USER=admin
WEB_ADMIN_PASS=admin
WEB_SECRET_KEY=secret_key
"""

# === 2. ФУНКЦИИ-ПОМОЩНИКИ ===

def save_key_to_env(key, value):
    """Безопасно сохраняет переменную в .env файл"""
    try:
        # Читаем все строки
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        new_lines = []
        key_found = False
        
        for line in lines:
            # Если нашли строку с нашим ключом, заменяем её
            if line.strip().startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                key_found = True
            else:
                new_lines.append(line)
        
        # Если ключа не было в файле, добавляем в конец
        if not key_found:
            new_lines.append(f"\n{key}={value}\n")
            
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
            
    except Exception as e:
        print(f"❌ Не удалось записать в .env: {e}")

def ask_user(prompt_text):
    """Запрашивает ввод у пользователя в консоли"""
    while True:
        val = input(f"✍️  {prompt_text}: ").strip()
        if val:
            return val
        print("⚠️ Значение не может быть пустым.")

# === 3. ИНИЦИАЛИЗАЦИЯ ФАЙЛА ===
if not os.path.exists(ENV_FILE):
    print(f"⚙️ Файл {ENV_FILE} не найден. Создаю шаблон...")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write(ENV_TEMPLATE)
    print(f"✅ Файл {ENV_FILE} создан.")

# Загружаем то, что есть
load_dotenv()

# === 4. ПРОВЕРКА И ИНТЕРАКТИВНЫЙ ВВОД ===

# --- РЕЖИМ ---
IS_TEST_ENV_STR = os.getenv("IS_TEST_ENV", "False").lower()
IS_TEST_ENV = IS_TEST_ENV_STR in ["true", "1", "yes", "on"]

# --- ТОКЕН БОТА ---
# Определяем, какой ключ нам нужен
TARGET_TOKEN_KEY = "TEST_BOT_TOKEN" if IS_TEST_ENV else "BOT_TOKEN"
BOT_TOKEN = os.getenv(TARGET_TOKEN_KEY)

# --- ID АДМИНА ---
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "")
clean_admin = ADMIN_ID_RAW.replace('"', '').replace("'", "").strip()

if not clean_admin:
    print("❌ ADMIN_ID не найден.")
    print("💡 Введите ваш Telegram ID (число). Бот выдаст вам права администратора.")
    
    user_input_id = ask_user("Введите ваш ID")
    
    # Простая проверка на число
    if not user_input_id.isdigit():
        print("⚠️ Это не похоже на ID, но я сохраню.")
    
    save_key_to_env("ADMIN_ID", user_input_id)
    clean_admin = user_input_id
    print("✅ ID Админа сохранен!\n")

# Парсинг админов
ADMIN_IDS = []
if clean_admin:
    parts = [x.strip() for x in clean_admin.split(",") if x.strip().isdigit()]
    ADMIN_IDS = [int(x) for x in parts]

print(f"👑 ADMIN_IDS загружены: {ADMIN_IDS}")

# === 5. ОСТАЛЬНЫЕ НАСТРОЙКИ (ТИХИЕ) ===

def get_bool(key, default=False):
    val = os.getenv(key, str(default)).lower()
    return val in ["true", "1", "yes", "on"]

# Tech Chat / Storage
TECH_CHAT_ID = os.getenv("TECH_CHAT_ID")
# Если нужно включить логи в канал, раскомментируйте следующую строку:
# LOG_CHANNEL_ID = int(TECH_CHAT_ID) if (TECH_CHAT_ID and TECH_CHAT_ID.lstrip("-").isdigit()) else None
LOG_CHANNEL_ID = None 

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_API_URL = "http://ws.audioscrobbler.com/2.0/"
LASTFM_SECRET = os.getenv("LASTFM_SECRET")

# Local Server
USE_LOCAL_SERVER = os.getenv("USE_LOCAL_SERVER", "False").lower() == "true"
LOCAL_SERVER_URL = os.getenv("LOCAL_SERVER_URL")

DB_NAME = "users.db"
# Webhook
USE_WEBHOOK = get_bool("USE_WEBHOOK", False)
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", 8080))
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")

# Discord
ENABLE_DISCORD_BOT_LOG = get_bool("ENABLE_DISCORD_BOT_LOG", False)
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_LOG_THREAD_ID_MAIN = int(os.getenv("DISCORD_LOG_THREAD_ID_MAIN", 0))
DISCORD_LOG_THREAD_ID_TEST = int(os.getenv("DISCORD_LOG_THREAD_ID_TEST", 0))

ENABLE_DISCORD_WEBHOOK_LOG = False
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# Dashboard
ENABLE_WEB_DASHBOARD = get_bool("ENABLE_WEB_DASHBOARD", False)
WEB_ADMIN_USER = os.getenv("WEB_ADMIN_USER", "admin")
WEB_ADMIN_PASS = os.getenv("WEB_ADMIN_PASS", "admin")
WEB_SECRET_KEY = os.getenv("WEB_SECRET_KEY", "secret")

# === 6. КОНСТАНТЫ ===
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

BOT_COMMANDS_LIST = [
    # Пользователь
    ("start", "Перезапустить бота", "user", False),
    ("login", "Привязать Last.fm", "user", True),    
    
    # Админ - Модерация
    ("users", "Список пользователей", "admin_mod", False),
    ("ban", "Бан (нажми и введи ID)", "admin_mod", True),
    ("unban", "Разбан (нажми и введи ID)", "admin_mod", True),
    ("answer", "Ответ (нажми и введи ID)", "admin_mod", True),
    
    # Админ - Техническое
    ("status", "Состояние системы", "admin_tech", False),
    ("check", "Health Check (проверка загрузки)", "admin_tech", False),
    ("update", "Обновить с GitHub", "admin_tech", False),
    ("clearcache", "Очистить кэш файлов", "admin_tech", False),
    ("exec", "Python Console", "admin_tech", True),
]