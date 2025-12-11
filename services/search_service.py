import asyncio
import traceback
import yt_dlp
from youtubesearchpython import VideosSearch


async def search_music(query: str, limit: int = 5):
    print(f"🔍 [SEARCH] Запрос: '{query}'") # Обычный принт

    # --- СПОСОБ 1: БЫСТРАЯ БИБЛИОТЕКА ---
    try:
        # print("   --> Попытка 1: youtube-search-python...") # Можно закомментить лишнее
        
        def _lib_search():
            search = VideosSearch(query, limit=limit)
            return search.result()

        loop = asyncio.get_event_loop()
        raw_data = await loop.run_in_executor(None, _lib_search)
        
        if raw_data and 'result' in raw_data and len(raw_data['result']) > 0:
            results = []
            for item in raw_data['result']:
                results.append({
                    'source': 'YT',
                    'id': item['id'],
                    'url': item['link'],
                    'title': item['title'],
                    'duration': item.get('duration') or "Live",
                    'uploader': item['channel']['name']
                })
            print(f"✅ Найдено {len(results)} треков.")
            return results
            
    except Exception as e:
        print(f"⚠️ Ошибка библиотеки поиска: {e}")

    # --- СПОСОБ 2: РЕЗЕРВ (YT-DLP) ---
    print("⚠️ Переход на резервный поиск (YT-DLP)...")
    results_yt = await _run_ytdlp_search(query, f'ytsearch{limit}')
    
    if results_yt:
        return results_yt

    # --- СПОСОБ 3: РЕЗЕРВ (SoundCloud) ---
    results_sc = await _run_ytdlp_search(query, f'scsearch{limit}')
    
    if results_sc:
        return results_sc

    print("❌ Ничего не найдено.")
    return []

async def _run_ytdlp_search(query: str, engine_prefix: str):
    """Внутренний поиск через yt-dlp"""
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'extract_flat': True,
        'default_search': engine_prefix,
        'ignoreerrors': True,
        'no_warnings': True,
    }

    def _search():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(query, download=False)
                if not info: return []
                if 'entries' in info: return info['entries']
                return []
            except Exception:
                return []

    loop = asyncio.get_event_loop()
    raw_results = await loop.run_in_executor(None, _search)
    
    clean = []
    if raw_results:
        for item in raw_results:
            if not item: continue
            title = item.get('title', 'Unknown')
            vid_id = item.get('id')
            if not vid_id: continue
            
            url = item.get('url') or f"https://youtu.be/{vid_id}"
            
            clean.append({
                'source': 'SC' if 'scsearch' in engine_prefix else 'YT',
                'id': vid_id,
                'url': url,
                'title': title,
                'duration': item.get('duration_string', '?:??'),
                'uploader': item.get('uploader', 'Unknown')
            })
    return clean

# Алиас
search_youtube = search_music