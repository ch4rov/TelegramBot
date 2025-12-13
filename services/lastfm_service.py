import aiohttp
import settings

async def get_user_recent_track(username: str):
    if not username or not getattr(settings, 'LASTFM_API_KEY', None):
        return None
    
    params = {
        'method': 'user.getrecenttracks',
        'user': username,
        'api_key': settings.LASTFM_API_KEY,
        'format': 'json',
        'limit': 1
    }

    url = getattr(settings, 'LASTFM_API_URL', "http://ws.audioscrobbler.com/2.0/")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json()
                
                if 'recenttracks' in data and 'track' in data['recenttracks']:
                    tracks = data['recenttracks']['track']
                    if not tracks:
                        return None
                    
                    track = tracks[0]
                    artist = track.get('artist', {}).get('#text', 'Unknown')
                    name = track.get('name', 'Unknown')
                    
                    now_playing = False
                    attr = track.get('@attr')
                    if attr and attr.get('nowplaying') == 'true':
                        now_playing = True
                        
                    image = None
                    images = track.get('image', [])
                    if len(images) > 2:
                        image = images[2].get('#text')
                    
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