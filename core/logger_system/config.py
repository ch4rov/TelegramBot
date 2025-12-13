import os
import settings

# === ГЛАВНЫЕ ПЕРЕКЛЮЧАТЕЛИ ===
ENABLE_TELEGRAM_LOG = True
# Включаем логирование через бота
ENABLE_DISCORD_BOT_LOG = True 

# Отключаем вебхук, так как переходим на бота
ENABLE_DISCORD_WEBHOOK_LOG = False

# === НАСТРОЙКИ ТЕЛЕГРАМ ===
LOG_TELEGRAM_CHAT_ID = getattr(settings, "LOG_CHANNEL_ID", None)

# === НАСТРОЙКИ DISCORD BOT ===
DISCORD_BOT_TOKEN = getattr(settings, "DISCORD_BOT_TOKEN", "")
is_test_env = getattr(settings, "IS_TEST_ENV", False)

# Выбираем целевую ветку
if is_test_env:
    # Тестовая ветка
    DISCORD_TARGET_CHANNEL_ID = getattr(settings, "DISCORD_LOG_THREAD_ID_TEST", 0)
    mode_name = "TEST"
else:
    # Основная ветка
    DISCORD_TARGET_CHANNEL_ID = getattr(settings, "DISCORD_LOG_THREAD_ID_MAIN", 0)
    mode_name = "MAIN"

# === ВЫВОД ИНФЫ ПРИ ЗАПУСКЕ ===
print(f"[LOGGER CONFIG] Bot Mode Enabled: {ENABLE_DISCORD_BOT_LOG}")

if ENABLE_DISCORD_BOT_LOG:
    if not DISCORD_BOT_TOKEN:
        print("[LOGGER CONFIG] ⚠️ WARNING: Bot Token is missing!")
    elif not DISCORD_TARGET_CHANNEL_ID:
        print("[LOGGER CONFIG] ⚠️ WARNING: Thread ID is missing!")
    else:
        print(f"[LOGGER CONFIG] 🤖 Bot Logging Active -> Thread {DISCORD_TARGET_CHANNEL_ID} ({mode_name})")

# Пути к файлам
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
USER_LOGS_DIR = os.path.join(LOGS_DIR, "user_logs")
FULL_LOG_PATH = os.path.join(LOGS_DIR, "full_log.txt")

os.makedirs(USER_LOGS_DIR, exist_ok=True)