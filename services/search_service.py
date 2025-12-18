import asyncio
import yt_dlp


def _norm_duration(seconds: int | None) -> str:
    try:
        if not seconds or seconds <= 0:
            return "?:??"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
    except Exception:
        return "?:??"


async def search_music(query: str, limit: int = 5):
    print(f"🔍 [SEARCH] Запрос: '{query}'") # Обычный принт

    # yt-dlp search is the most stable option in production
    print("⚠️ Поиск через YT-DLP...")
    results_yt = await _run_ytdlp_search(query, engine="ytsearch", limit=limit)
    
    if results_yt:
        return results_yt

    # --- РЕЗЕРВ (SoundCloud) ---
    results_sc = await _run_ytdlp_search(query, engine="scsearch", limit=limit)
    
    if results_sc:
        return results_sc

    print("❌ Ничего не найдено.")
    return []

async def _run_ytdlp_search(query: str, engine: str, limit: int):
    """Внутренний поиск через yt-dlp."""
    search_query = f"{engine}{int(limit)}:{query}"
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'extract_flat': True,
        'ignoreerrors': True,
        'no_warnings': True,
    }

    def _search():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(search_query, download=False)
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
                'source': 'SC' if engine == 'scsearch' else 'YT',
                'id': vid_id,
                'url': url,
                'title': title,
                'duration': item.get('duration_string') or _norm_duration(item.get('duration')),
                'uploader': item.get('uploader', 'Unknown')
            })
    return clean

# Алиас
search_youtube = search_music