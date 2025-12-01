import aiohttp
import json
import os
from services.platforms.common_downloader import CommonDownloader

class TikTokStrategy(CommonDownloader):
    """
    Стратегия для ТикТок Видео (API Proxy).
    Использует внешний API (tikwm.com) для обхода блокировок IP и капчи.
    """
    
    def get_platform_settings(self) -> dict:
        return {}

    async def download(self):
        print(f"🎥 [TikTok API] Запрос через TikWM: {self.url}")
        
        api_url = "https://www.tikwm.com/api/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://www.tikwm.com',
            'Referer': 'https://www.tikwm.com/'
        }
        data = {'url': self.url, 'count': 12, 'cursor': 0, 'web': 1, 'hd': 1}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, data=data, headers=headers) as resp:
                    if resp.status != 200:
                        print(f"❌ [TikTok API] HTTP Error: {resp.status}")
                        return None, None, f"API Error: {resp.status}", None
                    
                    result_text = await resp.text()
                    
                    # --- ПИЗДЛИВЫЙ ЛОГ ---
                    print(f"\n📦 [TikTok API DUMP] Response:")
                    print(result_text[:1000]) # Первые 1000 символов
                    print("-" * 30 + "\n")
                    # ---------------------

                    try:
                        result = json.loads(result_text)
                    except:
                        return None, None, "API returned non-JSON response", None
            
            # Проверяем ответ
            if result.get('code') != 0:
                msg = result.get('msg', 'Unknown error')
                print(f"❌ [TikTok API] Logic Error: {msg}")
                return None, None, f"TikTok API Error: {msg}", None
            
            data = result.get('data', {})
            
            # Ищем ссылку на видео (hdplay или play)
            video_url = data.get('hdplay') or data.get('play')
            
            # --- ФИКС ОТНОСИТЕЛЬНОЙ ССЫЛКИ ---
            if video_url and not video_url.startswith("http"):
                print(f"⚠️ [TikTok API] Исправляю относительную ссылку: {video_url}")
                video_url = f"https://www.tikwm.com{video_url}"
            # ---------------------------------

            title = data.get('title', 'TikTok Video')
            author = data.get('author', {}).get('nickname', 'TikTok User')
            
            if not video_url:
                print("❌ [TikTok API] Ссылка на видео не найдена в JSON.")
                return None, None, "Video URL not found in API response", None

            print(f"✅ [TikTok API] Ссылка OK: {video_url}")
            print(f"⬇️ Скачиваю файл...")
            
            # Скачиваем файл вручную
            if not os.path.exists(self.download_path): os.makedirs(self.download_path)
            file_path = os.path.join(self.download_path, f"video.mp4")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(video_url) as vid_resp:
                    if vid_resp.status == 200:
                        with open(file_path, 'wb') as f:
                            f.write(await vid_resp.read())
                        print(f"✅ [TikTok API] Файл сохранен: {file_path}")
                    else:
                        print(f"❌ [TikTok API] Ошибка скачивания файла: {vid_resp.status}")
                        return None, None, "Failed to download video file", None

            # Формируем метаданные
            final_meta = {
                'title': title,
                'artist': author,
                'uploader': author,
                'track': title,
                'height': 1920, 'width': 1080
            }
            
            return [file_path], self.download_path, None, final_meta

        except Exception as e:
            print(f"❌ [TikTok API] Критическая ошибка: {e}")
            return None, None, str(e), None