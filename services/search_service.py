import asyncio
import yt_dlp

async def _run_search(query: str, engine_prefix: str):
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'extract_flat': True,
        'default_search': engine_prefix,
        'ignoreerrors': True,
    }

    def _search():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(query, download=False)
                # Добавлена проверка на None
                if not info: 
                    return []
                if 'entries' in info:
                    return info['entries']
                return []
            except Exception as e:
                print(f"Search Error ({engine_prefix}): {e}")
                return []

    loop = asyncio.get_event_loop()
    raw_results = await loop.run_in_executor(None, _search)
    
    # Если вернулся None (критическая ошибка), делаем пустой список
    if raw_results is None: 
        raw_results = []
    
    clean_results = []
    for item in raw_results:
        if not item: continue
        
        if item.get('url'): link = item['url']
        else: link = f"https://youtu.be/{item.get('id')}"
            
        clean_results.append({
            'id': item.get('id'),
            'url': link,
            'title': item.get('title', 'Unknown'),
            'uploader': item.get('uploader', 'Unknown'),
            'duration': item.get('duration_string', '?:??')
        })
    
    return clean_results

async def search_music(query: str, limit: int = 5):
    results = await _run_search(query, f'ytsearch{limit}')
    if not results:
        print(f"🔍 YouTube пуст, ищу на SoundCloud: {query}")
        results = await _run_search(query, f'scsearch{limit}')
    return results

async def search_youtube(query: str, limit: int = 5):
    return await _run_search(query, f'ytsearch{limit}')