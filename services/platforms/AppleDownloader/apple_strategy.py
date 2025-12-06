import re
import html
import aiohttp
import json
from urllib.parse import unquote
from services.platforms.common_downloader import CommonDownloader

class AppleStrategy(CommonDownloader):
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

    async def download(self):
        decoded_url = unquote(self.url)
        print(f"🎵 [Apple] Ссылка: {decoded_url}")
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
        
        try:
            async with aiohttp.ClientSession(headers=headers, connector=aiohttp.TCPConnector(ssl=False)) as session:
                async with session.get(self.url) as resp:
                    text = await resp.text()
            
            track_name = None
            artist_name = None

            # 1. JSON-LD (Улучшенный regex)
            # Ищем скрипт с id="schema:music-recording" или просто ld+json
            json_matches = re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.DOTALL)
            
            for j_str in json_matches:
                try:
                    data = json.loads(j_str)
                    # Apple часто заворачивает в массив
                    if isinstance(data, list): 
                        # Ищем объект MusicRecording или MusicAlbum
                        for item in data:
                            if item.get('@type') == 'MusicRecording':
                                data = item
                                break
                        else:
                            if data: data = data[0]

                    if data.get('@type') == 'MusicRecording':
                        track_name = data.get('name')
                        by_artist = data.get('byArtist')
                        
                        if isinstance(by_artist, list) and by_artist:
                            artist_name = by_artist[0].get('name')
                        elif isinstance(by_artist, dict):
                            artist_name = by_artist.get('name')
                        
                        if track_name: 
                            print(f"✅ [Apple] JSON-LD Found: {artist_name} - {track_name}")
                            break
                except: pass

            # 2. Title Tag Fallback (Если JSON не сработал)
            if not track_name:
                title_match = re.search(r'<title>(.*?)</title>', text)
                if title_match:
                    raw = html.unescape(title_match.group(1))
                    # Чистим системный мусор
                    raw = re.sub(r'\s*\|\s*Apple\s*Music.*', '', raw)
                    raw = raw.replace(" on Apple Music", "")
                    
                    # Пытаемся разбить по разделителям
                    # Польский: "Utwór wykonawcy" (Song by artist)
                    if " - Utwór wykonawcy " in raw:
                        parts = raw.split(" - Utwór wykonawcy ")
                        track_name = parts[0].strip()
                        artist_name = parts[1].strip()
                    elif " by " in raw:
                        parts = raw.split(" by ")
                        track_name = parts[0].strip()
                        artist_name = parts[1].strip()
                    elif " - " in raw:
                        parts = raw.split(" - ")
                        track_name = parts[0].strip()
                        if len(parts) > 1: artist_name = parts[1].strip()
                    else:
                        track_name = raw

            if track_name:
                # ЧИСТКА ОТ МУСОРА И НЕВИДИМЫХ СИМВОЛОВ
                # Удаляем все непечатные символы (кроме пробелов)
                def clean_str(s):
                    if not s: return ""
                    # Убираем BOM и прочую грязь
                    return re.sub(r'[^\w\s\-\(\)\.,]', '', s).strip()

                track_name = clean_str(track_name)
                artist_name = clean_str(artist_name)

                search_query = f"{artist_name} - {track_name} audio" if artist_name else f"{track_name} audio"
                print(f"🔎 [Apple] Поиск: '{search_query}'")
                self.url = f"ytsearch1:{search_query}"
            else:
                return None, None, "Не удалось получить название трека Apple.", None

        except Exception as e:
             return None, None, f"Apple Error: {e}", None

        # 3. Качаем
        files, folder, error, yt_meta = await super().download()
        
        if files and not error:
             final_meta = {
                 'artist': artist_name,
                 'title': track_name,
                 'track': track_name,
                 'uploader': artist_name
             }
             return files, folder, error, final_meta
             
        return files, folder, error, yt_meta