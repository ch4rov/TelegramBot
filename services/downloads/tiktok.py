from .base import base_download
import os

async def download(url: str):
    """
    Умный загрузчик для TikTok с тремя стратегиями обхода блокировок.
    """
    
    # Вспомогательная функция для добавления куки, если они есть
    def apply_cookies(opts):
        if os.path.exists("cookies.txt"):
            opts['cookiefile'] = "cookies.txt"
        return opts

    # --- Попытка 1: PC User-Agent + API Hostname ---
    # Обычно хорошо работает для видео
    opts_1 = {
        'format': 'best',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.tiktok.com/',
        },
        'socket_timeout': 20,
        'extractor_timeout': 30,
        'no_warnings': True,
        # Специфичный хост API, который часто работает стабильнее
        'extractor_args': {
            'tiktok': {
                'api_hostname': 'api22-normal-c-alisg.tiktokv.com'
            }
        }
    }
    opts_1 = apply_cookies(opts_1)
    
    # Пробуем скачать
    result = await base_download(url, opts_1)
    
    # Если успешно (ошибки нет) - возвращаем результат сразу
    if not result[2]: 
        return result

    # --- Попытка 2: iPhone User-Agent ---
    # Часто помогает для Слайдшоу (фото) и если забанен PC-агент
    print("⚠️ [TikTok] Попытка 1 не удалась, пробую режим iPhone...")
    
    opts_2 = {
        'format': 'best',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.tiktok.com/'
        },
        'socket_timeout': 20,
        'extractor_timeout': 30,
        'no_warnings': True,
        'getcomments': False,
        'skip_unavailable_fragments': True,
    }
    opts_2 = apply_cookies(opts_2)
    
    result = await base_download(url, opts_2)
    
    if not result[2]:
        return result

    # --- Попытка 3: Android User-Agent + Ограничение качества ---
    # Последний шанс: притворяемся Андроидом и не требуем 4K
    print("⚠️ [TikTok] Попытка 2 не удалась, пробую режим Android (Legacy)...")
    
    opts_3 = {
        'format': 'best[height<=1080]', # Иногда 4k видео вызывают ошибки CDN
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
        },
        'socket_timeout': 30,
        'extractor_timeout': 60,
        'no_warnings': True,
        'skip_unavailable_fragments': True,
        'fragment_retries': 5,
    }
    opts_3 = apply_cookies(opts_3)
    
    result = await base_download(url, opts_3)
    
    return result