import re
import os
import aiohttp
import base64
import json
import html
import asyncio
import yt_dlp
from services.platforms.common_downloader import CommonDownloader

class SpotifyStrategy(CommonDownloader):
    
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

    def _clean_artist_name(self, artist: str) -> str:
        """Удаляет мусорные префиксы Spotify из имени артиста"""
        if not artist: return ""
        
        # Регулярка для удаления "song and lyrics by", "song by" и т.д. (регистронезависимо)
        # (?i) - игнор регистра, ^ - начало строки
        clean = re.sub(r'(?i)^(song\s+and\s+lyrics\s+by|lyrics\s+by|song\s+by|music\s+by)\s+', '', artist)
        
        # Иногда бывает суффикс " on Spotify"
        clean = re.sub(r'(?i)\s+on\s+spotify$', '', clean)
        
        return clean.strip()

    async def get_playlist_tracks(self):
        print(f"🎵 [Spotify Playlist] Входная ссылка: {self.url}")
        
        clean_url, html_content = await self._resolve_url(self.url)
        print(f"✅ [Spotify Playlist] Clean URL: {clean_url}")

        # 1. yt-dlp (Fast)
        print("🔹 [Spotify Playlist] Пробую yt-dlp...")
        opts = {
            'extract_flat': True, 'dump_single_json': True, 'quiet': True, 'ignoreerrors': True,
            'allow_unplayable_formats': True, 'check_formats': False,
        }
        def _extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                try: return ydl.extract_info(clean_url, download=False)
                except: return None

        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, _extract)
        
        if info and 'entries' in info and len(info['entries']) > 0:
            tracks = []
            for entry in info['entries']:
                if not entry: continue
                artist = entry.get('artist') or entry.get('uploader')
                title = entry.get('title') or entry.get('track')
                
                # Чистим автора тут тоже
                if artist: artist = self._clean_artist_name(artist)
                
                if artist and title:
                    tracks.append(f"{artist} - {title}")
            
            if tracks:
                pl_title = info.get('title', 'Spotify Playlist')
                return pl_title, tracks

        # 2. HTML Scraper (Fallback)
        print("⚠️ [Spotify Playlist] yt-dlp не справился. Запускаю HTML парсер...")
        return self._scrape_playlist_html_fallback(html_content)

    def _scrape_playlist_html_fallback(self, html_content):
        try:
            title_match = re.search(r'<title>(.*?)</title>', html_content)
            pl_title = "Spotify Playlist"
            if title_match:
                pl_title = html.unescape(title_match.group(1)).replace(" | Spotify", "")

            tracks = []
            json_matches = re.findall(r'<script[^>]*>({.*?})</script>', html_content, re.DOTALL)
            json_matches += re.findall(r'Spotify\.Entity\s*=\s*({.*?});', html_content, re.DOTALL)

            def find_tracks_recursive(data):
                found = []
                if isinstance(data, dict):
                    if 'name' in data and 'artists' in data:
                        artists = data['artists']
                        if isinstance(artists, list) and len(artists) > 0 and 'name' in artists[0]:
                            if 'uri' in data and 'spotify:track:' in data['uri'] or 'duration_ms' in data:
                                t = data['name']
                                a = artists[0]['name']
                                # Чистим
                                a = self._clean_artist_name(a)
                                found.append(f"{a} - {t}")
                    
                    for v in data.values():
                        if isinstance(v, (dict, list)): found.extend(find_tracks_recursive(v))
                elif isinstance(data, list):
                    for item in data: found.extend(find_tracks_recursive(item))
                return found

            for json_str in json_matches:
                try:
                    if not json_str.strip().startswith(("{", "[")):
                        try: json_str = base64.b64decode(json_str).decode('utf-8')
                        except: pass
                    data = json.loads(json_str)
                    tracks.extend(find_tracks_recursive(data))
                except: pass

            # Fallback Regex
            if not tracks:
                raw_matches = re.findall(r'"name":"(.*?)".*?"artists":\[\{"name":"(.*?)"', html_content)
                for t_name, a_name in raw_matches:
                    if t_name.lower() in ["spotify"] or a_name.lower() in ["spotify"]: continue
                    t_name = t_name.encode().decode('unicode-escape')
                    a_name = a_name.encode().decode('unicode-escape')
                    a_name = self._clean_artist_name(a_name) # Чистим
                    tracks.append(f"{a_name} - {t_name}")

            seen = set()
            clean_tracks = [x for x in tracks if not (x in seen or seen.add(x))]
            if clean_tracks: return pl_title, clean_tracks
                
        except Exception as e: print(f"❌ [Spotify Playlist] Ошибка: {e}")
        return None

    async def download(self):
        print(f"🎵 [Spotify Track] Старт: {self.url}")
        
        clean_url, html_content = await self._resolve_url(self.url)
        meta = await self._parse_metadata(clean_url, html_content)
        
        if not meta: return None, None, "No Metadata", None
        
        artist, track = meta.get('artist'), meta.get('track')
        
        artist = self._clean_artist_name(artist)
        
        search_query = f"{artist} - {track} audio" if artist else f"{track} audio"
        
        print(f"🔎 [Spotify] Поиск: '{search_query}'")
        self.url = f"ytsearch1:{search_query}"
        
        files, folder, error, yt_meta = await super().download()
        
        if files and not error:
            final_meta = {'artist': artist, 'title': track, 'track': track, 'uploader': artist, 'height': None, 'width': None}
            return files, folder, error, final_meta
            
        return files, folder, error, yt_meta

    async def _resolve_url(self, url: str):
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'}
        cookies = self._get_cookies_dict()
        async def fetch_recursive(target_url, depth=0):
            if depth > 5: return target_url, ""
            try:
                async with aiohttp.ClientSession(headers=headers, cookies=cookies, connector=aiohttp.TCPConnector(ssl=False)) as session:
                    async with session.get(target_url, allow_redirects=True) as resp:
                        text = await resp.text()
                        final = str(resp.url)
                        m = re.search(r'<script id="urlSchemeConfig" type="text/plain">(.*?)</script>', text)
                        if m:
                            try:
                                j = json.loads(base64.b64decode(m.group(1)).decode('utf-8'))
                                real = j.get('redirectUrl') or j.get('urlScheme')
                                if real: return await fetch_recursive(real, depth+1)
                            except: pass
                        return final, text
            except: return target_url, ""
        return await fetch_recursive(url)

    async def _parse_metadata(self, url, html_content):
        print("🔍 [Spotify Meta] Парсинг...")
        artist_res, track_res = None, None
        
        # 1. OEmbed
        try:
            clean_url = url.split('?')[0]
            oembed_api = f"https://open.spotify.com/oembed?url={clean_url}"
            async with aiohttp.ClientSession() as session:
                async with session.get(oembed_api) as resp:
                    if resp.status == 200:
                        d = await resp.json()
                        track_res = d.get("title")
                        artist_res = d.get("author_name")
        except: pass

        # 2. JSON-LD
        if not artist_res:
            m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html_content, re.DOTALL)
            if m:
                try:
                    d = json.loads(m.group(1))
                    if not track_res: track_res = d.get("name")
                    ad = d.get("byArtist") or d.get("musicBy")
                    if isinstance(ad, list) and ad: artist_res = ad[0].get("name")
                    elif isinstance(ad, dict): artist_res = ad.get("name")
                except: pass
        
        # 3. HTML Tags
        if not artist_res:
             tm = re.search(r'<title>(.*?)</title>', html_content)
             if tm:
                 t = html.unescape(tm.group(1)).replace(" | Spotify", "")
                 if " - " in t:
                     p = t.split(" - ")
                     if track_res and p[0].lower() == track_res.lower(): artist_res = p[1].strip()
                     elif track_res and p[1].lower() == track_res.lower(): artist_res = p[0].strip()

        if track_res:
             if "Spotify" in track_res: track_res = track_res.replace("Spotify", "").strip(" -|")
             return {'artist': artist_res, 'track': track_res}
        return None

    def _get_cookies_dict(self):
        cookie_file = None
        if os.path.exists(os.path.join(self.download_path, "user.txt")): cookie_file = os.path.join(self.download_path, "user.txt")
        elif os.path.exists("cookies.txt"): cookie_file = "cookies.txt"
        if not cookie_file: return {}
        cookies = {}
        try:
            with open(cookie_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('#') or not line.strip(): continue
                    parts = line.split('\t')
                    if len(parts) >= 7: cookies[parts[5]] = parts[6].strip()
        except: pass
        return cookies