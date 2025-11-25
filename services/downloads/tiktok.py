from .base import base_download
import os

async def download(url: str, custom_opts: dict = None): # <---
    def apply_cookies(opts):
        if os.path.exists("cookies.txt"):
            opts['cookiefile'] = "cookies.txt"
        return opts

    # Попытка 1
    opts_1 = {
        'format': 'best',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Referer': 'https://www.tiktok.com/',
        },
        'socket_timeout': 20,
        'extractor_timeout': 30,
        'no_warnings': True,
        'extractor_args': {'tiktok': {'api_hostname': 'api22-normal-c-alisg.tiktokv.com'}}
    }
    opts_1 = apply_cookies(opts_1)
    
    # ВНЕДРЯЕМ CUSTOM OPTS (для инлайн аудио)
    if custom_opts:
        opts_1.update(custom_opts)

    result = await base_download(url, opts_1)
    if not result[2]: return result

    # Попытка 2
    print("⚠️ [TikTok] Retry 2...")
    opts_2 = {
        'format': 'best',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
        },
        'socket_timeout': 20,
        'no_warnings': True,
    }
    opts_2 = apply_cookies(opts_2)
    if custom_opts: opts_2.update(custom_opts) # <---
    
    result = await base_download(url, opts_2)
    if not result[2]: return result

    # Попытка 3
    print("⚠️ [TikTok] Retry 3...")
    opts_3 = {
        'format': 'best[height<=1080]',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
        },
        'socket_timeout': 30,
        'no_warnings': True,
    }
    opts_3 = apply_cookies(opts_3)
    if custom_opts: opts_3.update(custom_opts) # <---
    
    result = await base_download(url, opts_3)
    return result