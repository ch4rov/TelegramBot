# Настройки путей
DOWNLOADS_DIR = "downloads"

# Настройки кэширования и лимитов
CACHE_TTL = 180           # Время жизни кэша в секундах (3 минуты)
MAX_CONCURRENT_DOWNLOADS = 3  # Максимум одновременных загрузок на одного юзера

# Настройки безопасности
# Список доменов для валидации (Regex)
URL_PATTERNS = [
    r'^https?://(www\.|vm\.|vt\.|m\.)?tiktok\.com/.*',
    r'^https?://(www\.|m\.)?instagram\.com/.*',
    r'^https?://(www\.|m\.|music\.)?youtube\.com/.*',
    r'^https?://(www\.)?youtu\.be/.*',
    r'^https?://(www\.|m\.)?soundcloud\.com/.*',
    r'^https?://(www\.|m\.|clips\.)?twitch\.tv/.*'
]