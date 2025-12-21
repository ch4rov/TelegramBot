import aiohttp
import json
import os
import asyncio
from services.platforms.common_downloader import CommonDownloader

class TikTokStrategy(CommonDownloader):
    """
    Стратегия для ТикТок Видео (API Proxy).
    Использует внешний API (tikwm.com) для обхода блокировок IP и капчи.
    Включает обработку Rate Limit и удаленных видео.
    """
    
    def get_platform_settings(self) -> dict:
        return {}

    async def download(self):
        print(f"🎥 [TikTok API] Start: {self.url}")
        
        api_url = "https://www.tikwm.com/api/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://www.tikwm.com',
            'Referer': 'https://www.tikwm.com/'
        }
        data = {'url': self.url, 'count': 12, 'cursor': 0, 'web': 1, 'hd': 1}

        max_retries = 5
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(api_url, data=data, headers=headers) as resp:
                        # 502/504 Bad Gateway -> Retry
                        if resp.status in [502, 504]:
                            print(f"⚠️ [TikTok API] HTTP {resp.status}. Retrying...")
                            await asyncio.sleep(2)
                            continue
                            
                        if resp.status != 200:
                            print(f"❌ [TikTok API] HTTP Error: {resp.status}")
                            return None, None, f"API Error: {resp.status}", None
                        
                        result_text = await resp.text()
                        try:
                            result = json.loads(result_text)
                        except:
                            return None, None, "API returned non-JSON", None
                
                # Проверка лимитов (Code -1)
                if result.get('code') == -1:
                    wait_time = 2 * (attempt + 1)
                    print(f"⚠️ [TikTok API] Rate Limit! Waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue 
                
                # Другие ошибки API
                if result.get('code') != 0:
                    msg = result.get('msg', 'Unknown error')
                    msg_l = str(msg).lower()
                    if any(s in msg_l for s in ("private", "not found", "removed", "deleted", "unavailable", "forbidden")):
                        return None, None, "Video unavailable", None
                    return None, None, f"TikTok API Error: {msg}", None
                
                data_obj = result.get('data', {})

                title = data_obj.get('title', 'TikTok')
                author = (data_obj.get('author') or {}).get('nickname', 'TikTok') if isinstance(data_obj.get('author'), dict) else 'TikTok'

                # Photo carousel (slideshow)
                want_photos = "/photo/" in (self.url or "")
                images = data_obj.get('images') or data_obj.get('image') or data_obj.get('imgs')
                if isinstance(images, list) and images:
                    want_photos = True

                def _extract_audio_url(obj: dict) -> str | None:
                    """Best-effort extraction of TikTok sound URL from tikwm payload."""
                    if not isinstance(obj, dict):
                        return None

                    # Common top-level candidates
                    for key in ("music", "music_info", "musicInfo", "music_url", "musicUrl", "audio", "audio_url", "audioUrl"):
                        v = obj.get(key)
                        if isinstance(v, str) and v.startswith("http"):
                            return v
                        if isinstance(v, dict):
                            for k2 in ("play_url", "playUrl", "play", "url", "download", "link"):
                                vv = v.get(k2)
                                if isinstance(vv, str) and vv.startswith("http"):
                                    return vv
                            # sometimes nested again
                            inner = v.get("music") or v.get("audio")
                            if isinstance(inner, dict):
                                for k3 in ("play_url", "play", "url", "download"):
                                    vv = inner.get(k3)
                                    if isinstance(vv, str) and vv.startswith("http"):
                                        return vv

                    # Last resort: scan shallow dict for any http audio-ish URL
                    for k, v in obj.items():
                        if not isinstance(v, str) or not v.startswith("http"):
                            continue
                        vl = v.lower()
                        if any(ext in vl for ext in (".mp3", ".m4a", ".aac", ".opus", ".ogg")):
                            return v
                    return None

                if want_photos and isinstance(images, list) and images:
                    if not os.path.exists(self.download_path):
                        os.makedirs(self.download_path)

                    async def _extract_img_url(obj):
                        if isinstance(obj, str):
                            return obj
                        if isinstance(obj, dict):
                            for key in ("url", "src", "download", "play"):
                                v = obj.get(key)
                                if isinstance(v, str) and v:
                                    return v
                            v = obj.get("url_list")
                            if isinstance(v, list) and v and isinstance(v[0], str):
                                return v[0]
                        return None

                    files: list[str] = []
                    async with aiohttp.ClientSession() as session:
                        for idx, img in enumerate(images[:35], start=1):
                            img_url = await _extract_img_url(img)
                            if not img_url:
                                continue
                            if not img_url.startswith("http"):
                                img_url = f"https://www.tikwm.com{img_url}" if img_url.startswith("/") else img_url
                            out_path = os.path.join(self.download_path, f"slide_{idx:02d}.jpg")
                            try:
                                async with session.get(img_url, timeout=30) as img_resp:
                                    if img_resp.status != 200:
                                        continue
                                    with open(out_path, 'wb') as f:
                                        f.write(await img_resp.read())
                                files.append(out_path)
                            except Exception:
                                continue

                        # Best-effort: download attached sound (if present)
                        audio_url = _extract_audio_url(data_obj)
                        if audio_url and isinstance(audio_url, str):
                            # Some payloads return relative paths
                            if not audio_url.startswith("http"):
                                audio_url = f"https://www.tikwm.com{audio_url}" if audio_url.startswith("/") else audio_url

                            audio_ext = ".mp3"
                            try:
                                lower = audio_url.lower().split("?", 1)[0]
                                for ext in (".mp3", ".m4a", ".aac", ".opus", ".ogg"):
                                    if lower.endswith(ext):
                                        audio_ext = ext
                                        break
                            except Exception:
                                audio_ext = ".mp3"

                            audio_path = os.path.join(self.download_path, f"sound{audio_ext}")
                            try:
                                async with session.get(audio_url, timeout=30) as a_resp:
                                    if a_resp.status == 200:
                                        with open(audio_path, "wb") as f:
                                            f.write(await a_resp.read())
                                        files.append(audio_path)
                            except Exception:
                                pass

                    if files:
                        final_meta = {
                            'title': title,
                            'artist': author,
                            'uploader': author,
                            'track': title,
                        }
                        return files, self.download_path, None, final_meta

                    return None, None, "Video unavailable", None

                video_url = data_obj.get('hdplay') or data_obj.get('play')
                
                # --- ФИКС ОТНОСИТЕЛЬНОЙ ССЫЛКИ ---
                if video_url and not video_url.startswith("http"):
                    video_url = f"https://www.tikwm.com{video_url}"
                
                # --- ПРОВЕРКА НА УДАЛЕННОЕ ВИДЕО ---
                if not video_url:
                    print("❌ [TikTok API] Ссылка пуста (Видео удалено или приватно).")
                    return None, None, "Video unavailable", None
                
                print(f"✅ [TikTok API] Ссылка OK. Скачиваю...")
                
                # Скачивание файла
                if not os.path.exists(self.download_path): os.makedirs(self.download_path)
                file_path = os.path.join(self.download_path, f"video.mp4")
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(video_url) as vid_resp:
                        if vid_resp.status == 200:
                            with open(file_path, 'wb') as f:
                                f.write(await vid_resp.read())
                        else:
                            return None, None, "Failed to download video file", None

                final_meta = {
                    'title': title, 
                    'artist': author, 
                    'uploader': author, 
                    'track': title, 
                    'height': 1920, 'width': 1080
                }
                
                return [file_path], self.download_path, None, final_meta

            except Exception as e:
                print(f"❌ [TikTok API] Exception: {e}")
                await asyncio.sleep(1)
        
        return None, None, "TikTok API Busy (Too many requests)", None