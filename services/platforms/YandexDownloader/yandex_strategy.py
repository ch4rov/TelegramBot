import re
import html
import os
import aiohttp
from urllib.parse import quote
from services.platforms.common_downloader import CommonDownloader

class YandexStrategy(CommonDownloader):
    def get_platform_settings(self) -> dict:
        return {
            'format': 'bestaudio/best',
            'postprocessors': [
                {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'},
                {'key': 'EmbedThumbnail'},
                {'key': 'FFmpegMetadata', 'add_metadata': True}
            ],
            'extractor_args': {'youtube': {'player_client': 'android'}}
        }

    def _get_cookies_dict(self):
        """
        Ищет ВСЕ файлы cookies_yandex*.txt в папке модуля и объединяет их.
        """
        module_dir = os.path.dirname(os.path.abspath(__file__))
        cookies = {}
        
        # 1. Ищем все файлы кук в папке модуля
        found_files = [f for f in os.listdir(module_dir) if f.startswith("cookies_yandex") and f.endswith(".txt")]
        # Добавляем общий
        if os.path.exists("cookies.txt"): found_files.append("../../cookies.txt") # Путь относительно модуля сложный, лучше абсолютный
        
        # Простой поиск в корне
        root_cookies = os.path.join(os.getcwd(), "cookies.txt")
        if os.path.exists(root_cookies): 
            # Читаем общие куки
            self._load_cookie_file(root_cookies, cookies)

        # Читаем специфичные куки
        for fname in found_files:
            fpath = os.path.join(module_dir, fname)
            self._load_cookie_file(fpath, cookies)
            
        return cookies

    def _load_cookie_file(self, path, cookie_dict):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('#') or not line.strip(): continue
                    parts = line.split('\t')
                    if len(parts) >= 7: cookie_dict[parts[5]] = parts[6].strip()
        except: pass

    async def download(self):
        print(f"🎵 [Yandex] Ссылка: {self.url}")
        
        # 1. Пытаемся через OEmbed (Официальный API для виджетов)
        # Это работает даже если основной сайт выдает капчу
        meta = await self._get_metadata_oembed()
        
        # 2. Если OEmbed не сработал - пробуем парсить HTML (как браузер)
        if not meta:
            print("⚠️ [Yandex] OEmbed не сработал. Пробую парсинг HTML...")
            meta = await self._get_metadata_html()

        if not meta:
            return None, None, "Яндекс блокирует доступ (капча). Проверьте куки.", None

        artist = meta['artist']
        track = meta['track']

        # Формируем поиск
        search_query = f"{artist} - {track} audio"
        # Чистим от бренда
        search_query = search_query.replace("Яндекс Музыка", "").replace("Yandex Music", "").strip()
        
        print(f"🔎 [Yandex] Поиск: '{search_query}'")
        self.url = f"ytsearch1:{search_query}"

        # 3. Качаем
        files, folder, error, yt_meta = await super().download()
        
        if files and not error:
             final_meta = {
                 'artist': artist,
                 'title': track,
                 'track': track,
                 'uploader': artist
             }
             return files, folder, error, final_meta
             
        return files, folder, error, yt_meta

    async def _get_metadata_oembed(self):
        """Запрос к JSON API Яндекса"""
        # Эндпоинт один для всех доменов (.ru, .by, .kz)
        oembed_url = f"https://music.yandex.ru/oembed?url={quote(self.url)}&format=json"
        
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; TelegramBot/1.0)'}
        # OEmbed обычно публичный, куки не обязательны, но можно передать
        
        try:
            async with aiohttp.ClientSession(headers=headers, connector=aiohttp.TCPConnector(ssl=False)) as session:
                async with session.get(oembed_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        title = data.get('title')
                        # Яндекс отдает title в формате "Track — Artist"
                        if title and " — " in title:
                            parts = title.split(" — ")
                            return {'track': parts[0].strip(), 'artist': parts[1].strip()}
                        elif title:
                             return {'track': title, 'artist': ''}
                    else:
                        print(f"🔸 [Yandex OEmbed] Error: {resp.status}")
        except Exception as e:
            print(f"🔸 [Yandex OEmbed] Exception: {e}")
        return None

    async def _get_metadata_html(self):
        """Резервный парсинг HTML"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8'
        }
        cookies = self._get_cookies_dict()
        
        try:
            async with aiohttp.ClientSession(headers=headers, cookies=cookies, connector=aiohttp.TCPConnector(ssl=False)) as session:
                async with session.get(self.url) as resp:
                    if resp.status != 200: return None
                    text = await resp.text()

            # Проверка на заглушку
            if "собираем музыку" in text or "Verify" in text:
                print("❌ [Yandex HTML] Поймана заглушка.")
                return None

            # Open Graph
            og_title = re.search(r'<meta property="og:title" content="(.*?)"', text)
            if og_title:
                track = html.unescape(og_title.group(1))
                artist = ""
                
                og_desc = re.search(r'<meta property="og:description" content="(.*?)"', text)
                if og_desc:
                    desc = html.unescape(og_desc.group(1))
                    if "." in desc: artist = desc.split(".")[0].strip()
                    else: artist = desc.strip()
                
                return {'track': track, 'artist': artist}
                
        except: pass
        return None