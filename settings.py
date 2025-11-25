# Настройки путей
DOWNLOADS_DIR = "downloads"

# Debug mode
DEBUG = False  # Глобальный флаг для debug логирования

# Настройки кэширования и лимитов
CACHE_TTL = 180           # Время жизни кэша в секундах (3 минуты)
MAX_CONCURRENT_DOWNLOADS = 3  # Максимум одновременных загрузок на одного юзера

# Настройки безопасности
# Запрещаем спецсимволы, которые могут использоваться для Shell Injection
# Разрешаем только буквы, цифры, дефисы, подчеркивания, точки, слеши, вопросы, равно, амперсанды
SAFE_CHARS = r'[a-zA-Z0-9\-\_\.\/\?\=\&\%]+'

URL_PATTERNS = [
    # TikTok (строгое окончание строки $)
    r'^https?://(www\.|vm\.|vt\.|m\.)?tiktok\.com/' + SAFE_CHARS + r'$',
    
    # Instagram
    r'^https?://(www\.|m\.)?instagram\.com/' + SAFE_CHARS + r'$',
    
    # YouTube (Video/Shorts/Music)
    r'^https?://(www\.|m\.|music\.)?youtube\.com/' + SAFE_CHARS + r'$',
    r'^https?://(www\.)?youtu\.be/' + SAFE_CHARS + r'$',
    
    # SoundCloud
    r'^https?://(www\.|m\.)?soundcloud\.com/' + SAFE_CHARS + r'$',
    
    # Twitch
    r'^https?://(www\.|m\.|clips\.)?twitch\.tv/' + SAFE_CHARS + r'$'
]