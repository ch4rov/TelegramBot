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
                    return None, None, f"TikTok API Error: {msg}", None
                
                data_obj = result.get('data', {})
                video_url = data_obj.get('hdplay') or data_obj.get('play')
                
                # --- ФИКС ОТНОСИТЕЛЬНОЙ ССЫЛКИ ---
                if video_url and not video_url.startswith("http"):
                    video_url = f"https://www.tikwm.com{video_url}"
                
                # --- ПРОВЕРКА НА УДАЛЕННОЕ ВИДЕО ---
                if not video_url:
                    print("❌ [TikTok API] Ссылка пуста (Видео удалено или приватно).")
                    return None, None, "Video not found or deleted", None

                title = data_obj.get('title', 'TikTok Video')
                author = data_obj.get('author', {}).get('nickname', 'TikTok User')
                
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