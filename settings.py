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
SAFE_CHARS = r'[a-zA-Z0-9\-\_\.\/\?\=\&\%\+\~]+'

URL_PATTERNS = [
    # TikTok (поддерживаем и короткие vm., и полные ссылки)
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

# --- LAST.FM ---
LASTFM_API_KEY = "7e0a038de589099bb9443a8d25bc8766"
LASTFM_API_URL = "http://ws.audioscrobbler.com/2.0/"