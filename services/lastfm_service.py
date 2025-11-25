import aiohttp
import settings

async def get_user_recent_track(username: str):
    """
    Возвращает текущий или последний трек пользователя.
    Вернет словарь: {'artist': '...', 'track': '...', 'image': '...', 'now_playing': Bool}
    """
    if not username: return None
    
    params = {
        'method': 'user.getrecenttracks',
        'user': username,
        'api_key': settings.LASTFM_API_KEY,
        'format': 'json',
        'limit': 1
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(settings.LASTFM_API_URL, params=params) as resp:
                data = await resp.json()
                
                if 'recenttracks' in data and 'track' in data['recenttracks']:
                    tracks = data['recenttracks']['track']
                    if not tracks: return None
                    
                    track = tracks[0]
                    artist = track['artist']['#text']
                    name = track['name']
                    
                    # Проверка: играет ли сейчас?
                    now_playing = False
                    if '@attr' in track and track['@attr'].get('nowplaying') == 'true':
                        now_playing = True
                        
                    # Картинка (Large)
                    image = track['image'][2]['#text'] if 'image' in track else None
                    
                    return {
                        'artist': artist,
                        'track': name,
                        'image': image,
                        'now_playing': now_playing,
                        'query': f"{artist} - {name}"
                    }
    except Exception as e:
        print(f"LastFM Error: {e}")
    
    return None